import hashlib
import copy
from langchain_classic.storage import LocalFileStore, create_kv_docstore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv
from bs4 import SoupStrainer
from langchain_community.document_loaders import WebBaseLoader, UnstructuredPDFLoader
from langchain_core.documents import Document
from langchain_classic.retrievers import MultiVectorRetriever
from flashrank import Ranker
from langchain_classic.retrievers.multi_vector import SearchType
from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_community.document_compressors import FlashrankRerank
import rag.configs as config
import os
import logging
import re
import getpass
import json
import uuid
load_dotenv()

# Configuration ----------
logging.basicConfig(level=logging.INFO, format="[%(levelname)s]: %(message)s")

OLLAMA_HOST_URL = os.environ.get("OLLAMA_HOST")

if not OLLAMA_HOST_URL:
    logging.error("OLLAMA_HOST environment variable is not set.")

if not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = getpass.getpass("Enter your Gemini API key: ")

embedding_model = OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_HOST_URL)
# ----------------------------

def clean_document_content(content: str) -> str:
    """
    Method for removing messy characters
    """
    content = re.sub(r'\n+', '\n', content)

    content = re.sub(r' +', ' ', content)

    return content.strip()

def calculate_content_hash(text: str) -> str:
    """Generates a stable hash based solely on text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_index_state(state_path: str) -> dict:
    if os.path.exists(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_index_state(state_path: str, state: dict):
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_filenames(path: str):
    """
    Returns all the filenames from a folder
    Input:
    - path:str - folder path
    """

    try:
        filepaths = os.listdir(path)
        if not filepaths:
            logging.error(f"No documents found at {path}")
            return None
        logging.info(f"Files found: {len(filepaths)}")
        return filepaths
    except FileNotFoundError:
        os.makedirs(path)
        logging.error(f"Folder {path} created successfully.")
        return None
    except Exception as e:
        logging.error(e)

def load_html(filepath: str = "../docs/source/html/links.json"):
    web_data = []

    try:
        with open(filepath, "r", encoding="utf-8") as jsonfile:
            data = json.load(jsonfile)
    except FileNotFoundError:
        logging.error(f"File not found at {filepath}")
        return []

    for link in data.get("links", []):
        logging.info(f"Full-page ingestion: {link['url']}")

        try:
            loader = WebBaseLoader(link["url"])
            raw_html_doc = loader.scrape()

            for script_or_style in raw_html_doc(["script", "style", "noscript", "iframe"]):
                script_or_style.decompose()
            main_content = (raw_html_doc.find('region') or \
                            raw_html_doc.find('region-content') or \
                            raw_html_doc.find('main') or \
                           raw_html_doc.find(class_='region-content') or \
                           raw_html_doc.find('article'))
            if main_content:

                combined_text = main_content.get_text(separator=" ", strip=True)
                print(combined_text)
            else:
                for noisy_tag in raw_html_doc(["header", "footer", "nav", "aside"]):
                    noisy_tag.decompose()
                combined_text = raw_html_doc.get_text(separator=" ", strip=True)

            if combined_text:
                cleaned_content = clean_document_content(combined_text)

                logging.info(f"Total processed length for {link['name']}: {len(cleaned_content)} chars.")

                new_doc = Document(
                    page_content=f"Назва сайту: {link['name']}\nДані: {cleaned_content}",
                    metadata={
                        "source": link["url"],
                        "site_name": link["name"]
                    }
                )
                web_data.append(new_doc)

        except Exception as e:
            logging.error(f"Failed to ingest full page {link['url']}: {e}")
    print(web_data)
    return web_data

def stable_doc_id(doc):
    """
    Helper function to create consistent document IDs
    """
    source = doc.metadata.get("source", "")
    page = doc.metadata.get("page", "")
    content = doc.page_content
    raw = f"{source}:{page}:{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def process_single_source(
        vectorstore,
        docstore,
        documents,
        parent_splitter,
        child_splitter,
        embedding_model=embedding_model,
        batch_size=10,
        storage_path: str = "../docs/vectorstore",
        parent_doc_id=config.DOC_ID
):
    if not documents:
        logging.error("No documents found to process.")
        return vectorstore, []

    # 1. Робимо ГЛИБОКУ КОПІЮ, щоб ніякі маніпуляції всередині LangChain
    # не ламали оригінальні дані в пам'яті вашого скрипта
    docs_copy = copy.deepcopy(documents)

    # 2. Нарізаємо батьківські документи
    parent_docs = parent_splitter.split_documents(docs_copy)
    doc_ids = [stable_doc_id(doc) for doc in parent_docs]

    child_docs = []
    for parent_doc, doc_id in zip(parent_docs, doc_ids):

        # 3. ЗАХИСНИЙ ЕКРАН: Перевіряємо, чи текст чанка не злетів.
        # Якщо в чанку залишився тільки тайтл "Назва сайту:", а "Дані:" пропали або порожні,
        # ми примусово відновлюємо контент з оригінального збереженого документа.
        if len(parent_doc.page_content) < 150 and "Назва сайту:" in parent_doc.page_content:
            logging.warning(
                f"[!] Виявлено обрізаний чанк для {parent_doc.metadata.get('site_name')}. Відновлюємо контент...")
            # Знаходимо оригінальний документ по джерелу
            orig_doc = next((d for d in documents if d.metadata.get("source") == parent_doc.metadata.get("source")),
                            None)
            if orig_doc:
                parent_doc.page_content = orig_doc.page_content

        # 4. Нарізаємо дочірні чанки для векторної бази
        children = child_splitter.split_documents([parent_doc])
        for child in children:
            child.metadata[parent_doc_id] = doc_id
        child_docs.extend(children)

    # 5. Контрольний принт перед збереженням в docstore
    print("\n=== ЩО ЗАПИСУЄТЬСЯ В DOCSTORE ===")
    for i, p_doc in enumerate(parent_docs):
        print(f"Документ #{i} | Довжина тексту: {len(p_doc.page_content)} | Прев'ю: {p_doc.page_content[:150]}...")
    print("=================================\n")

    # Зберігаємо гарантовано повні parent_docs
    docstore.mset(list(zip(doc_ids, parent_docs)))

    if vectorstore is None:
        vectorstore = FAISS.from_documents(child_docs, embedding_model)
    else:
        vectorstore.add_documents(child_docs)

    logging.info(f"Indexed {len(child_docs)} documents.")
    return vectorstore, doc_ids



def get_vectorstore(storage_path=config.VECTORSTORE_PATH, ollama_url=OLLAMA_HOST_URL):
    try:
        embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=ollama_url)
        logging.info("Embeddings object initialized.")

        vectorstore = FAISS.load_local(storage_path, embeddings, allow_dangerous_deserialization=True)
        logging.info(f"Vectorstore loaded from {storage_path}.")
        return vectorstore
    except Exception:
        logging.exception(f"Failed to load vectorstore from {storage_path}")

def get_docstore(storage_path=config.FILESTORE_PATH):
    try:
        byte_store = LocalFileStore(storage_path)
        docstore = create_kv_docstore(byte_store)

        logging.info(f"Docstore initialized from {storage_path}.")
        return docstore

    except Exception:
        logging.exception(f"Failed to initialize docstore from {storage_path}")
        return None

def get_retriever(vectorstore_path=config.VECTORSTORE_PATH, docstore_path=config.FILESTORE_PATH):
    vectorstore = get_vectorstore(storage_path=vectorstore_path)
    docstore = get_docstore(storage_path=docstore_path)

    if not vectorstore or not docstore:
        logging.error("Could not initialize MultiVectorRetriever.")
        return None

    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=docstore,
        id_key=config.DOC_ID,
        search_type=SearchType.similarity,
        search_kwargs={"k": 3},
    )
    flashrank_client = Ranker()
    compressor = FlashrankRerank(top_n=5, client=flashrank_client)

    compression_retriever = ContextualCompressionRetriever(base_compressor=compressor, base_retriever=retriever)

    return compression_retriever

def save_files(path, loader_cls):
    filenames = get_filenames(path)
    if not filenames:
        return None
    filepaths = [os.path.join(path, filename) for filename in filenames]
    files = []

    for filepath in filepaths:
        if loader_cls == UnstructuredPDFLoader:
            loader = loader_cls(filepath, strategy="ocr_only", languages=["ukr"])
        else:
            loader = loader_cls(filepath)
        loaded_docs = loader.load()

        files.extend(loaded_docs)
    return files

def update_storage(embedding_model=embedding_model,
                   file_path=config.FILE_PATHS,
                   doc_path = config.LOCAL_FILESTORE_PATH,
                   vector_path=config.LOCAL_VECTORSTORE_PATH,
                   parent_chunk_size = config.PARENT_CHUNK_SIZE,
                   parent_chunk_overlap_size = config.PARENT_CHUNK_OVERLAP_SIZE,
                   child_chunk_size = config.CHILD_CHUNK_SIZE,
                   child_chunk_overlap_size = config.CHILD_CHUNK_OVERLAP_SIZE):
    # Configure storagge
    vectorstore = None
    byte_store = LocalFileStore(doc_path)
    docstore = create_kv_docstore(byte_store)

    source_names = ["docs", "html", "pdf"]
    for name in source_names:
        path = os.path.join("docs/source", name)
        os.makedirs(path)
        
    os.makedirs(vector_path, exist_ok=True)
    os.makedirs(doc_path, exist_ok=True)
    # Load the state
    state_file_path = os.path.join(doc_path, "file_state.json")
    tracking_state = load_index_state(state_file_path)


    # Check if vectorstore exists
    if os.path.exists(vector_path) and os.listdir(vector_path):
        vectorstore = FAISS.load_local(
            vector_path,
            embedding_model,
            allow_dangerous_deserialization=True
        )
        logging.info("Existing vectorstore loaded.")

    # Splitters
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(parent_chunk_size),
        chunk_overlap=int(parent_chunk_overlap_size),
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(child_chunk_size),
        chunk_overlap=int(child_chunk_overlap_size),
    )

    # Create a dictionary of current files to compare with the state
    # the hash identifies each file
    current_sources = {}
    for entry in file_path:
        filenames = get_filenames(entry['path'])
        if not filenames:
            continue
        for filename in filenames:
            filepath = os.path.join(entry['path'], filename)
            if entry['loader'] == UnstructuredPDFLoader:
                loader = entry['loader'](filepath, strategy="ocr_only", languages=["ukr"])
            else:
                loader = entry['loader'](filepath)

            loaded_docs = loader.load()
            combined_text = "".join([d.page_content for d in loaded_docs])

            current_sources[filepath] = {
                "docs": loaded_docs,
                "hash": calculate_content_hash(combined_text)
            }
    # Same for web pages
    web_docs = load_html()
    for doc in web_docs:
        url = doc.metadata["source"]
        current_sources[url] = {
            "docs": [doc],
            "hash": calculate_content_hash(doc.page_content)
        }
    print(web_docs)
    # Identifying the changes
    sources_to_delete = []
    for old_source, tracking_info in list(tracking_state.items()):
        if old_source not in current_sources:
            sources_to_delete.append(old_source)
        elif tracking_state[old_source]["hash"] != current_sources[old_source]["hash"]:
            sources_to_delete.append(old_source)

    # Clean up stale or modified sources
    if sources_to_delete and vectorstore:
        logging.info(f"Cleaning up {len(sources_to_delete)} stale or modified sources...")
        for source in sources_to_delete:
            old_parent_ids = tracking_state[source]["parent_ids"]

            docstore.mdelete(old_parent_ids)

            v_ids_to_delete = [
                v_id for v_id, doc in vectorstore.docstore._dict.items()
                if doc.metadata.get(config.DOC_ID) in old_parent_ids
            ]
            if v_ids_to_delete:
                vectorstore.delete(v_ids_to_delete)

            del tracking_state[source]
        logging.info("Stale data purge finished.")

    # Processing
    has_changes = False

    for source, data in current_sources.items():
        if source in tracking_state:
            continue

        logging.info(f"Incremental Update: Indexing {source}")
        vectorstore, new_parent_ids = process_single_source(
            vectorstore=vectorstore,
            docstore=docstore,
            documents=data["docs"],
            parent_splitter=parent_splitter,
            child_splitter=child_splitter
        )

        # Save historical trace to state tracking
        tracking_state[source] = {
            "hash": data["hash"],
            "parent_ids": new_parent_ids
        }
        has_changes = True

    # 5. Save everything back
    if vectorstore and has_changes:
        vectorstore.save_local(vector_path)
        save_index_state(state_file_path, tracking_state)
        logging.info(f"Vectorstore and file tracking maps synced at {vector_path}!")
    else:
        logging.info("No modifications detected. Storage is already up-to-date.")

if __name__ == "__main__":
    # filenames = get_files_doc()
    # chunks = create_chunks(filenames)
    #
    # get_embeddings(chunks)
    update_storage(embedding_model)