from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv
import rag.config as config
import configparser
import os
import logging
import re
import getpass

# Configuration ----------
logging.basicConfig(level=logging.INFO, format="[%(levelname)s]: %(message)s")

file_path = config.FILE_PATHS
vector_path = config.VECTORSTORE_PATH

load_dotenv()
if not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = getpass.getpass("Enter your Gemini API key: ")

embedding_model = OllamaEmbeddings(model="nomic-embed-text")
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

def embed_documents(vectorstore, documents, storage_path: str = "../docs/vectorstore"):
    if not documents:
        logging.error("No chunks to embed.")
        return None

    try:
        vectorstore.save_local(storage_path)
        print(f"Total chunks in FAISS: {vectorstore.index.ntotal}")
        return vectorstore
    except Exception as e:
        logging.error(f"Error during embedding: {e}")
        return None

def get_vectorstore(storage_path=vector_path):
    try:
        embeddings = OllamaEmbeddings(model="nomic-embed-text")
        vectorstore = FAISS.load_local(storage_path, embeddings, allow_dangerous_deserialization=True)
        logging.info("Vectorstore loaded.")
        return vectorstore
    except Exception as e:
        logging.error(f"Error during embedding: {e}")

def save_files(path, loader_cls):
    filenames = get_filenames(path)
    if not filenames:
        return None
    filepaths = [os.path.join(path, filename) for filename in filenames]

    files = [loader_cls(filepath).load() for filepath in filepaths]

    return files


def update_storage(embedding_model):
    vectorstore = None
    # Check if vectorstore exists
    if os.path.exists(vector_path) and os.listdir(vector_path):
        vectorstore = FAISS.load_local(
            vector_path,
            embedding_model,
            allow_dangerous_deserialization=True
        )
        logging.info("Existing vectorstore loaded.")
    # Split documents into chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(config.CHUNK_SIZE),
        chunk_overlap=int(config.CHUNK_OVERLAP_SIZE),
    )

    for entry in file_path:
        logging.info(f"Processing folder: {entry['path']}")
        documents = save_files(entry['path'], entry['loader'])

        if not documents:
            continue

        flat_docs = []
        for item in documents:
            if isinstance(item, list): flat_docs.extend(item)
            else: flat_docs.append(item)

        chunks = splitter.split_documents(flat_docs)
        logging.info(f"Total chunks to process: {len(chunks)}")

        batch_size = 10
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            if vectorstore is None:
                vectorstore = FAISS.from_documents(batch, embedding_model)
            else:
                vectorstore.add_documents(batch)
            logging.info(f"Indexed chunks {i} to {min(i + batch_size, len(chunks))}")

    if vectorstore:
        vectorstore.save_local(config.VECTORSTORE_PATH)
        logging.info(f"Vectorstore saved successfully at {config.VECTORSTORE_PATH}!")


if __name__ == "__main__":
    # filenames = get_files_doc()
    # chunks = create_chunks(filenames)
    #
    # get_embeddings(chunks)
    update_storage(embedding_model)