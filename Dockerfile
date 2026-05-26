FROM python:3.13
LABEL authors="srgtkrvvv"

ENV PYTHONBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE=1

RUN mkdir /app

WORKDIR /app

RUN curl -fsSL https://ollama.com/install.sh | sh

RUN ollama serve & \
    sleep 5 && \
    ollama pull nomic-embed-text && \
    pkill ollama

RUN pip install --upgrade pip
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]

CMD gunicorn stud_assistant.wsgi:application --bind 0.0.0.0:$PORT
