FROM python:3.13
LABEL authors="srgtkrvvv"

ENV PYTHONBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE=1

RUN mkdir /app

WORKDIR /app

RUN pip install --upgrade pip
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps chromium

COPY . /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]

CMD gunicorn your_project_name.wsgi:application --bind 0.0.0.0:$PORT
