import os
import uuid

# ---Temp ---
import django
import uuid
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stud_assistant.settings')


django.setup()
from django.conf import settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableWithMessageHistory, ConfigurableFieldSpec, RunnableConfig
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from vector_storage import get_vectorstore
from langsmith import traceable
from rag.models import Message


def get_chat_history(chat_id: str):
    """Bridge between Django ORM and LangChain History"""
    db_messages = Message.objects.filter(chat_id=chat_id).order_by('date')

    langchain_history = ChatMessageHistory()
    system_id = os.getenv("SYSTEM_ID")

    for msg in db_messages:
        if msg.sender_id != system_id:
            langchain_history.add_message(HumanMessage(content=msg.content))
        else:
            langchain_history.add_message(AIMessage(content=msg.content))
    return langchain_history


class StudAgent:
    def __init__(self, faculty, department, group):
        self.faculty = faculty
        self.department = department
        self.group = group
        self.agent = ChatGoogleGenerativeAI(
            google_api_key=os.environ['GEMINI_API_KEY'],
            model='gemini-2.5-flash'
        )

        contextualize_q_system_prompt = (
            "Зважаючи на історію чату та останнє запитання користувача, "
            "яке може посилатися на контекст в історії чату, сформулюй окреме запитання, "
            "яке можна зрозуміти без історії чату. НЕ відповідай на запитання, "
            "просто перефразуй його, якщо потрібно, або залиш як є."
        )
        contextualize_q_prompt = ChatPromptTemplate.from_messages([
            ("system", contextualize_q_system_prompt),
            MessagesPlaceholder("history"),
            ("human", "{input}"),
        ])

        self.vectorstore = get_vectorstore()
        history_aware_retriever = create_history_aware_retriever(
            self.agent, self.vectorstore.as_retriever(), contextualize_q_prompt
        )

        self.chat_prompt = ChatPromptTemplate.from_messages([
            ("system", """"
    Ти помічник студента Івано-Франківського національного технічного університету нафти і газу(ІФНТУНГ) студенту групи {group}, що навчається на факультеті {faculty}, на кафедрі {department}.
    Ти допомагаєш студенту з навчальними питаннями, пов'язаними з його курсами а саме надаєш відповіді на питання, пояснюєш матеріал, допомагаєш з домашніми завданнями та підготовкою до іспитів.
    Ти володієш загальною інформацією про ІФНТУНГ та про загальні положення, щоб допомготи з усіма питаннями пов'язаними з університетом станом на поточний рік
    Якщо ти не знаєш відповіді на питання, чесно про це скажи.
    Не вигадуй інформацію, якщо не впевнений у відповіді.
    Відповідай українською мовою.
    Якщо студент задає питання не пов'язане з ІФНТУНГ поясни йому, що дане питання не входить в твою компетенцію.
    Якщо тобі не вистачає інформації про студента, запитай його щодо уточнення цих даних.

                Контекст:
                {context}
            """),
            MessagesPlaceholder("history"),
            ("human", "{input}"),
        ])

        question_answer_chain = create_stuff_documents_chain(self.agent, self.chat_prompt)

        rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

        self.pipeline_with_history = RunnableWithMessageHistory(
            rag_chain,
            get_session_history=get_chat_history,
            history_messages_key='history',
            input_messages_key='input',
            output_messages_key='answer',
            history_factory_config=[
                ConfigurableFieldSpec(
                    id='chat_history',
                    annotation=str,
                    name='Chat History',
                    description='Conversation ID',
                    default=None,
                )
            ]
        )

    @traceable
    def ask(self, message, chat_id):
        config = RunnableConfig(configurable={"chat_history": str(chat_id)})
        response = self.pipeline_with_history.invoke(
            {
                "input": message,
                "group": self.group,
                "faculty": self.faculty,
                "department": self.department,
            },
            config=config
        )
        return response['answer']

    @traceable
    def get_title(self, message):
        prompt = f"Проаналізуй повідомлення: \"{message}\" і створи короткий заголовок. Відповідай лише заголовком."
        response = self.agent.invoke(prompt)
        return response.content


if __name__ == "__main__":
    agent = StudAgent("Факультет Інформаційних технологій", "Інженерія програмного забезпечення", "ІП-22-1")
    example_res = agent.ask("Чи володієш ти іфнормацією та вмістом про статут ІФНТУНГ? Якщо так то опиши деякі положення з нього.", uuid.uuid4())
    print(example_res)