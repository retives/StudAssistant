import django
import uuid
import os
from functools import lru_cache

from langchain_classic.callbacks.tracers import logging
from langchain_core.tools import tool
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stud_assistant.settings')
django.setup()


import os
import uuid
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableWithMessageHistory, ConfigurableFieldSpec, RunnableConfig
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from rag.vector_storage import get_retriever
from langsmith import traceable
from rag.models import Message
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from playwright.sync_api import sync_playwright
import logging

logging.basicConfig(level=logging.INFO, format="[%(levelname)s]: %(message)s")

retriever = get_retriever()

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
def search_university_docs(query: str) -> tuple[str, str]:
    """
    Використовуй цей інструмент ЗАВЖДИ, коли користувач запитує про ІФНТУНГ (співробітники,
    ректорат, статут, навчальні плани, дисципліни, спеціальності, кафедри, факультети).

    Аргумент `query` повинен містити лише ключові слова або коротку фразу для пошуку українською мовою
    (наприклад, замість "Ознайом мене з ректоратом" передавай "склад ректорату").

    Після отримання результату обов'язково проаналізуй його та виклади студенту у простому форматі.

    Дані повертаються у форматі tuple(результат, джерело)

    Включай джерело у відповідь обов'язково завжди коли звертаєшся до цього інструменту.
    """
    try:
        retriever = get_retriever()
        if not retriever:
            logging.info("Retriever not found. Skipping search.")
            return "База знань наразі недоступна. Спробуйте повторити запит пізніше.", ""

        docs = retriever.invoke(query)
        if not docs:
            logging.error("No info in the knowledge base")
            return "У базі знань не знайдено релевантної інформації за цим запитом.", ""

        return "\n\n".join([doc.page_content for doc in docs]), "\n".join([doc.metadata['source'] for doc in docs])

    except Exception:
        logging.exception("Failed during university document similarity search")
        return "Під час пошуку в базі знань сталася помилка. Спробуйте повторити запит пізніше.", ""


@tool
def get_timetable(group: str) -> dict:
    """
    Коли студент запитує у тебе про власний розклад, використовуй шифр групи (ІП-22-1, ГМ-23-2 і подібні) дослівно або коли в нього пари, звертайся до цієї функції.
    Структура отриманого розкладу - [день{1 пара{час:"", назва_предмету:""}..} ...], не вигадуй пари й використовуй
    тільки новий розклад, а не з історії повідомлень, щоб він завжди був актуальним
    При наданні відповіді не змінюй положення пар, цитуй отриману інформацію з функції
    Сортуй розклад за датою
    """
    with sync_playwright() as p:
        # Navigate to the website
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"https://dekanat.nung.edu.ua/cgi-bin/timetable.cgi?n=700")
        # Fill in the form
        page.fill("input[id=\"group\"]", group)
        page.click("button.btn")

        page.wait_for_selector("table")

        # Gather all the data
        tables = page.locator("table").all()
        dates = page.locator("h4").all_text_contents()[4:]
        timetable = {}
        for index, table in enumerate(tables):
            table_data = table.locator("td").all_text_contents()
            timetable[dates[index]] = table_data

        for day_of_week, schedule in timetable.items():
            timetable[day_of_week] = {}
            for i in range(0, len(schedule), 3):
                # print(schedule[i], schedule[i+1], schedule[i+2])
                index = str(schedule[i])
                timetable[day_of_week][index] = {}
                timetable[day_of_week][index]["class_time"] = schedule[i + 1][:5]
                timetable[day_of_week][index]["class_name"] = schedule[i + 2]

        return timetable
# ============================


class StudAgent:
    def __init__(self, group, faculty, department):
        self.group = group
        self.faculty = faculty
        self.department = department

        self.llm = ChatGoogleGenerativeAI(
            google_api_key=os.environ['GEMINI_API_KEY'],
            model='gemini-2.5-flash',
            temperature = 0,
            # max_output_tokens=1024,
        )

        self.chat_prompt =  ChatPromptTemplate.from_messages([
            ("system", """"
            Ти помічник студента Івано-Франківського національного технічного університету нафти і газу(ІФНТУНГ) студенту групи {group}, що навчається на факультеті {faculty}, на кафедрі {department}.
            Ти допомагаєш студенту з навчальними питаннями, пов'язаними з його курсами а саме надаєш відповіді на питання, пояснюєш матеріал, допомагаєш з домашніми завданнями та підготовкою до іспитів.
            Ти володієш загальною інформацією про ІФНТУНГ та про загальні положення, щоб допомготи з усіма питаннями пов'язаними з університетом станом на поточний рік
            Користуйся інформацією, що є в твоїй базі знань.
            Не вигадуй інформацію, якщо не впевнений у відповіді.
            Відповідай українською мовою.
            Якщо студенту потрібен розклад, обов'язково використовуй інструмент 'get_timetable'
            Якщо студент задає питання не пов'язане з ІФНТУНГ поясни йому, що дане питання не входить в твою компетенцію.
            Якщо тобі не вистачає інформації про студента, запитай його щодо уточнення цих даних.
            Форматуй відповіді відповідно до markdown-розмітки.
            
            Якщо ти використовуєш search_university завжди за будь-яких умов вказуй джерело/джерела, що були отримуні з search_university_docs
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

        if isinstance(raw_output, list):
            text_pieces = []
            for chunk in raw_output:
                if isinstance(chunk, dict) and 'text' in chunk:
                    text_pieces.append(chunk['text'])
                elif isinstance(chunk, str):
                    text_pieces.append(chunk)

            return "".join(text_pieces)

        return str(raw_output)

    @traceable
    def get_title(self, message):
        prompt = f"Проаналізуй повідомлення: \"{message}\" і створи короткий заголовок. Відповідай лише заголовком."
        response = self.llm.invoke(prompt)
        return response.content


@lru_cache(maxsize=256)
def get_cached_agent(group: str, faculty: str, department: str) -> StudAgent:
    """
    Cache agents per-process to avoid rebuilding LLM/prompt/executor on every request.
    This is safe for typical gunicorn/uvicorn multi-worker setups (each worker has its own cache).
    """
    return StudAgent(group=group, faculty=faculty, department=department)

if __name__ == "__main__":
    agent = StudAgent("ІП-22-1", "Інженерія програмного забезпечення", "Факультет Інформаційних технологій")
    response = agent.ask("Переліч співробітників кафедри інженерії програмного забезпечення", uuid.uuid4())
    print(response)

