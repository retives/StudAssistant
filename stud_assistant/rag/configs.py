from langchain_community.document_loaders import PyPDFLoader, UnstructuredPDFLoader
from langchain_community.document_loaders.word_document import Docx2txtLoader
from playwright.sync_api import sync_playwright
# Vector storage
VECTORSTORE_PATH = "docs/vectorstore"
FILESTORE_PATH = "docs/docstore"
LOCAL_VECTORSTORE_PATH = "../docs/vectorstore"
LOCAL_FILESTORE_PATH = "../docs/docstore"

PARENT_CHUNK_SIZE=2000
PARENT_CHUNK_OVERLAP_SIZE=200

CHILD_CHUNK_SIZE=500
CHILD_CHUNK_OVERLAP_SIZE=100

DOC_ID = "parent_id"


FILE_PATHS = [
    {
        "path":"../docs/source/docx",
        "loader": Docx2txtLoader,
    },
    {
        "path":"../docs/source/pdf",
        "loader": UnstructuredPDFLoader,
    },
]
# Agent config