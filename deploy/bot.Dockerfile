FROM python:3.12.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN mkdir -p /app/bot/data && chown 10001:10001 /app/bot/data
COPY bot/bot.py bot/catalog.py bot/crm_client.py bot/draft_store.py /app/bot/
COPY content/en.json /app/content/

USER 10001:10001
CMD ["python", "/app/bot/bot.py"]
