from langchain_classic.agents.agent_toolkits import vectorstore
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from vector_storage import get_vectorstore

retriever = get_vectorstore()
class DjangoSummaryMemory(BaseChatMessageHistory):
    def __init__(self, agent_instance):
        self.messages = []
        self.llm = agent_instance

    def add_messages(self, messages: list[BaseMessage]):
        self.messages.extend(messages)

        summary_prompt = ChatPromptTemplate([
            SystemMessagePromptTemplate.from_template(
                "Тобі треба проаналізувати повідомлення та згенерувати новий короткий підсумок."
            ),
            HumanMessagePromptTemplate.from_template(
                "Історія: \n{existing_summary}\nНові: \n{new_messages}"
            )
        ])

        existing_content = " ".join([m.content for m in self.messages[:-len(messages)]])
        new_content = " ".join([m.content for m in messages])

        chain = summary_prompt | self.llm.agent
        response = chain.invoke({
            "existing_summary": existing_content,
            "new_messages": new_content
        })

        # Keep only the summary as a SystemMessage to save tokens
        self.messages = [SystemMessage(content=response.content)]

    def clear(self):
        self.messages = []