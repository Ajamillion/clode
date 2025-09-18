# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/python:/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY python ./python
COPY services ./services

RUN mkdir -p /data

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir fastapi==0.111.0 uvicorn[standard]==0.29.0 python-multipart==0.0.9

EXPOSE 8000
VOLUME ["/data"]
ENV BAGGER_SPL_DB_PATH=/data/runs.db

CMD ["uvicorn", "services.gateway.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
