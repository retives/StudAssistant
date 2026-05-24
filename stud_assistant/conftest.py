import sys
from unittest.mock import MagicMock

# Avoid loading RAG / vectorstore when Django imports rag.views during URLconf setup.
_agent_module = MagicMock()
_agent_module.StudAgent = MagicMock
sys.modules.setdefault("rag.agent", _agent_module)
