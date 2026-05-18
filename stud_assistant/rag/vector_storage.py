import hashlib

from langchain_classic.storage import LocalFileStore, create_kv_docstore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv
from bs4 import SoupStrainer
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.documents import Document
from langchain_classic.retrievers import MultiVectorRetriever
import rag.configs as config
import os
import logging
import re
import getpass
import json
import uuid

# Configuration ----------
logging.basicConfig(level=logging.INFO, format="[%(levelname)s]: %(message)s")

file_path = config.FILE_PATHS
vector_path = config.VECTORSTORE_PATH
docstore = config.FILESTORE_PATH
parent_id = config.DOC_ID

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")

load_dotenv()
if not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = getpass.getpass("Enter your Gemini API key: ")

embedding_model = OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL)
# ----------------------------

def clean_document_content(content: str) -> str:
    """
    Method for removing messy characters
    """
    content = re.sub(r'\n+', '\n', content)

    content = re.sub(r' +', ' ', content)

    return content.strip()

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
        isolator = SoupStrainer(class_=["content", "view-content", "page-header"])

        loader = WebBaseLoader(link["url"])
        raw_html_doc = loader.scrape()

        relevant_html = raw_html_doc.find_all(isolator)

        combined_text = ""
        for element in relevant_html:
            combined_text += element.get_text(separator=" ", strip=True) + "\n"

        if combined_text:
            cleaned_content = clean_document_content(combined_text)

            new_doc = Document(
                page_content=f"Назва сайту: {link['name']}\nДані: {cleaned_content}",
                metadata={
                    "source": link["url"],
                    "site_name": link["name"]
                }
            )
            web_data.append(new_doc)

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

def save_batches(batch_size=10, vectorstore=None, chunks=None):
    batch_size = 10
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i: i + batch_size]
        if vectorstore is None:
            vectorstore = FAISS.from_documents(batch, embedding_model)
        else:
            vectorstore.add_documents(batch)
        logging.info(f"Indexed chunks {i} to {min(i + batch_size, len(chunks))}")

def process_documents(
        vectorstore,
        docstore,
        documents,
        parent_splitter,
        child_splitter,
        embedding_model,
        batch_size=10,
        storage_path: str = "../docs/vectorstore"
):
    # Empty documents handling
    if not documents:
        logging.error("No documents found to process.")
        return vectorstore

    parent_docs = parent_splitter.split_documents(documents)
    doc_ids = [stable_doc_id(doc) for doc in parent_docs]
    child_docs = []
    for parent_doc, doc_id in zip(parent_docs, doc_ids):
        children = child_splitter.split_documents([parent_doc])
        for chils in children:
            chils.metadata[parent_id] = doc_id
        child_docs.extend(children)

    docstore.mset(list(zip(doc_ids, parent_docs)))

    save_batches(batch_size=batch_size, vectorstore=vectorstore, chunks=child_docs)
    return vectorstore

def get_vectorstore(storage_path=vector_path):
    try:
        embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL)
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

def get_retriever():
    vectorstore = get_vectorstore()
    docstore = get_docstore()

    if not vectorstore or not docstore:
        logging.error("Could not initialize MultiVectorRetriever.")
        return None

    return MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=docstore,
        id_key=parent_id,
        search_type="similarity",
        search_kwargs={"k": 3},
    )

def save_files(path, loader_cls):
    filenames = get_filenames(path)
    if not filenames:
        return None
    filepaths = [os.path.join(path, filename) for filename in filenames]

    files = [loader_cls(filepath).load() for filepath in filepaths]

    return files

def update_storage(embedding_model):
    vectorstore = None
    byte_store = LocalFileStore(config.FILESTORE_PATH)
    docstore = create_kv_docstore(byte_store)

    # Check if vectorstore exists
    if os.path.exists(vector_path) and os.listdir(vector_path):
        vectorstore = FAISS.load_local(
            vector_path,
            embedding_model,
            allow_dangerous_deserialization=True
        )
        logging.info("Existing vectorstore loaded.")
    # Split documents into chunks
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(config.PARENT_CHUNK_SIZE),
        chunk_overlap=int(config.PARENT_CHUNK_OVERLAP_SIZE),
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(config.CHILD_CHUNK_SIZE),
        chunk_overlap=int(config.CHILD_CHUNK_OVERLAP_SIZE),
    )

    docs = []
    for entry in file_path:
        logging.info(f"Processing folder: {entry['path']}")
        documents = save_files(entry['path'], entry['loader'])

        if not documents:
            logging.error(f"No documents found in {entry['path']}")
            continue

        for item in documents:
            if isinstance(item, list): docs.extend(item)
            else: docs.append(item)
    docs.extend(load_html())

    vectorstore = process_documents(vectorstore, docstore, docs, parent_splitter, child_splitter, embedding_model, batch_size=10, storage_path=config.VECTORSTORE_PATH)

    if vectorstore:
        vectorstore.save_local(config.VECTORSTORE_PATH)
        logging.info(f"Vectorstore saved successfully at {config.VECTORSTORE_PATH}!")
    else:
        logging.warning("No documents were indexed. Vectorstore was not created.")

if __name__ == "__main__":
    # filenames = get_files_doc()
    # chunks = create_chunks(filenames)
    #
    # get_embeddings(chunks)
    update_storage(embedding_model)