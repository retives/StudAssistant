from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders.word_document import Docx2txtLoader
from playwright.sync_api import sync_playwright
# Vector storage
VECTORSTORE_PATH = "docs/vectorstore"
FILESTORE_PATH = "docs/docstore"
PARENT_CHUNK_SIZE=3000
PARENT_CHUNK_OVERLAP_SIZE=200

CHILD_CHUNK_SIZE=700
CHILD_CHUNK_OVERLAP_SIZE=100

DOC_ID = "parent_id"

OLLAMA_HOST = "http://ollama:11434"

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
# Agent config