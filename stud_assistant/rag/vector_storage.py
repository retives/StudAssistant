from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders.word_document import Docx2txtLoader
# from langchain_community.document_loaders.url import UnstructuredURLLoader
from langchain_community.document_loaders.base import BaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv
import os
import logging
import re
import getpass

logging.basicConfig(level=logging.INFO, format="[%(levelname)s]: %(message)s")

load_dotenv()
if not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = getpass.getpass("Enter your Gemini API key: ")

FILE_PATHS = [
    {
        "path":"../docs/source/docx",
        "loader": Docx2txtLoader,
    },
    {
        "path":"../docs/source/pdf",
        "loader": PyPDFLoader,
    },
]

VECTORSTORE_PATH = "../docs/vectorstore"
CHUNK_SIZE=500
CHUNK_OVERLAP_SIZE=50

embedding_model = OllamaEmbeddings(model="nomic-embed-text")

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

def get_vectorstore(storage_path="../docs/vectorstore"):
    try:
        embeddings = OllamaEmbeddings(model="nomic-embed-text")
        vectorstore = FAISS.load_local(storage_path, embeddings, allow_dangerous_deserialization=True)

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

    if os.path.exists(VECTORSTORE_PATH) and os.listdir(VECTORSTORE_PATH):
        vectorstore = FAISS.load_local(
            VECTORSTORE_PATH,
            embedding_model,
            allow_dangerous_deserialization=True
        )
        logging.info("Existing vectorstore loaded.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP_SIZE
    )

    for entry in FILE_PATHS:
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
        vectorstore.save_local(VECTORSTORE_PATH)
        logging.info(f"Vectorstore saved successfully at {VECTORSTORE_PATH}!")


if __name__ == "__main__":
    # filenames = get_files_doc()
    # chunks = create_chunks(filenames)
    #
    # get_embeddings(chunks)
    update_storage(embedding_model)