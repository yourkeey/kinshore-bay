FROM python:3.12.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.preview
WORKDIR /app

COPY crm/requirements.txt /tmp/kinshore-requirements.txt
RUN pip install --no-cache-dir -r /tmp/kinshore-requirements.txt gunicorn==27.0.1 'psycopg[binary]==3.3.9' \
    && mkdir /data \
    && chown 10001:10001 /data

COPY crm/manage.py /app/crm/
COPY --chown=10001:10001 crm/config /app/crm/config
COPY --chown=10001:10001 crm/reception /app/crm/reception
COPY content/en.json /app/content/
COPY site/index.html site/miniapp.html site/site.js site/miniapp.js site/club-guide.js site/apartment-details.js site/style.css /app/site/
COPY --chown=10001:10001 site/assets /app/site/assets

WORKDIR /app/crm
USER 10001:10001
