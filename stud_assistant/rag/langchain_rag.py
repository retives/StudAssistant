from langchain_google_genai import ChatGoogleGenerativeAI
from rag.vector_storage import get_vectorstore

# Loading the existing vector storage
vectorstore = get_vectorstore()

retriever = vectorstore.as_retriever(search_kwargs={"k":3})

