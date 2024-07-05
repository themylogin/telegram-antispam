FROM python:3.12

RUN pip install python-telegram-bot

WORKDIR /app
COPY telegram_antispam /app/telegram_antispam
ENTRYPOINT ["python", "-m", "telegram_antispam"]
