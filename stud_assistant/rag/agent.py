import django
import uuid
import os

from langchain_classic.agents.react import agent
from langchain_classic.callbacks.tracers import logging
from langchain_core.tools import tool
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stud_assistant.settings')
django.setup()


import os
import uuid
from django.conf import settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableWithMessageHistory, ConfigurableFieldSpec, RunnableConfig
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from rag.vector_storage import get_vectorstore
from langsmith import traceable
from rag.models import Message
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
import re
from playwright.sync_api import sync_playwright
from django.conf import settings
import logging

def create_ai_agent(llm, tools, chat_prompt):
    agent = create_tool_calling_agent(llm, tools, chat_prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, return_intermediate_steps=True)

    pipeline_with_history = RunnableWithMessageHistory(
        agent_executor,
        get_session_history=get_chat_history,
        history_messages_key='history',
        input_messages_key='input',
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
    return pipeline_with_history

# ====== Tool management =====
def get_chat_history(chat_id: str):
    """Bridge between Django ORM and LangChain History"""
    db_messages = Message.objects.filter(chat_id=chat_id).order_by('sent_at')

    langchain_history = ChatMessageHistory()
    system_id = os.getenv("SYSTEM_ID")

    for msg in db_messages:
        if msg.sender_id != system_id:
            langchain_history.add_message(HumanMessage(content=msg.content))
        else:
            langchain_history.add_message(AIMessage(content=msg.content))
    return langchain_history

@tool
def search_university_docs(query: str) -> str:
    """
    Корисно для пошуку інформації про правила університету ІФНТУНГ,
    положення, статут, методичні вказівки та загальні запитання.
    """
    vectorstore = get_vectorstore()
    if not vectorstore:
        logging.info("VectorStore not found. Skipping search.")
    docs = vectorstore.similarity_search(query, k=3)
    return "\n\n".join([doc.page_content for doc in docs])

@tool
def get_timetable(group: str):
    """
    Коли студент запитує у тебе про власний розклад, використовуй шифр групи (ІП-22-1, ГМ-23-2 і подібні) дослівно або коли в нього пари, звертайся до цієї функції.
    Структура отриманого розкладу - [день{1 пара{час:"", назва_предмету:""}..} ...], не вигадуй пари й використовуй
    тільки новий розклад звідси, а не з історії повідомлень, щоб він завжди був актуальним
    При наданні відповіді не змінюй положення пар, цитуй отриману інформацію з функції
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"https://dekanat.nung.edu.ua/cgi-bin/timetable.cgi?n=700")

        page.fill("input[id=\"group\"]", group)
        page.click("button.btn")

        page.wait_for_selector("table")

        rows = page.locator("tr").all()
        dow = page.locator("small").all()
        dow = [day.text_content() for day in dow]
        print(dow)
        timetable_data = {}
        for day_index, day in enumerate(dow):
            classes = {}
            for index, row in enumerate(rows):
                classes[str(index)] = {}
                cells = row.locator("td").all_text_contents()
                if cells:
                    classes[str(index)]["time"] = cells[1][:5]
                    classes[str(index)]["name"] = cells[2]
                if len(classes) == 8:
                    break
            rows = rows[7:]
            timetable_data[day] = classes
        browser.close()
        print(timetable_data)
        return timetable_data
# ============================

class StudAgent:
    def __init__(self, group, faculty, department):
        self.group = group
        self.faculty = faculty
        self.department = department

        self.llm = ChatGoogleGenerativeAI(
            google_api_key=os.environ['GEMINI_API_KEY'],
            model='gemini-2.5-flash-lite',
            temperature = 0
        )

        self.chat_prompt =  ChatPromptTemplate.from_messages([
            ("system", """"
            Ти помічник студента Івано-Франківського національного технічного університету нафти і газу(ІФНТУНГ) студенту групи {group}, що навчається на факультеті {faculty}, на кафедрі {department}.
            Ти допомагаєш студенту з навчальними питаннями, пов'язаними з його курсами а саме надаєш відповіді на питання, пояснюєш матеріал, допомагаєш з домашніми завданнями та підготовкою до іспитів.
            Ти володієш загальною інформацією про ІФНТУНГ та про загальні положення, щоб допомготи з усіма питаннями пов'язаними з університетом станом на поточний рік
            Користуйся інформацвією, що є в твоїй базі знань.
            Не вигадуй інформацію, якщо не впевнений у відповіді.
            Відповідай українською мовою.
            Якщо студенту потрібен розклад, обов'язково використовуй інструмент 'get_timetable'
            Якщо студент задає питання не пов'язане з ІФНТУНГ поясни йому, що дане питання не входить в твою компетенцію.
            Якщо тобі не вистачає інформації про студента, запитай його щодо уточнення цих даних.
                Контекст:
                {{context}}
            """),
            MessagesPlaceholder("history"),
            ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),

        ])
        self.tools = [search_university_docs, get_timetable]

        self.ai_agent = create_ai_agent(self.llm, self.tools, self.chat_prompt)

    @traceable
    def ask(self, message, chat_id):
        config = RunnableConfig(configurable={"chat_history": str(chat_id)})
        response = self.ai_agent.invoke(
            {
                "input": message,
                "group": self.group,
                "faculty": self.faculty,
                "department": self.department,
            },
            config=config
        )
        raw_output = response['output']

        if isinstance(raw_output, list) and len(raw_output) > 0:
            return raw_output[0].get('text', str(raw_output))
        return str(raw_output)

    @traceable
    def get_title(self, message):
        prompt = f"Проаналізуй повідомлення: \"{message}\" і створи короткий заголовок. Відповідай лише заголовком."
        response = self.llm.invoke(prompt)
        return response.content

if __name__ == "__main__":
    agent = StudAgent("ІП-22-1", "Інженерія програмного забезпечення", "Факультет Інформаційних технологій")
    response = agent.ask("Який розклад групи іп-22-1 на цей тиждень?", uuid.uuid4())
    print(response)
