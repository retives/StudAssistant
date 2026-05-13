from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders.word_document import Docx2txtLoader
from playwright.sync_api import sync_playwright
# Vector storage
VECTORSTORE_PATH = "../docs/vectorstore"
CHUNK_SIZE=3000
CHUNK_OVERLAP_SIZE=200

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