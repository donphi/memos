# ============================================================================
# API CONTAINER (MEMOS ROUTER)
# PURPOSE: FastAPI webhook receiver, category routing, LLM classification,
#          immutable event log, git-tracked action generation
# ============================================================================
#
# VERSION: PYTHON_VERSION passed as build arg from docker-compose.yml,
#          sourced from config/versions.yaml. No default — must be set.
# ============================================================================
ARG PYTHON_VERSION
FROM python:${PYTHON_VERSION}

LABEL maintainer="don"
LABEL description="Memos Router API - webhook receiver, classifier, event log"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

RUN mkdir -p /app/data

CMD ["python", "src/server.py"]
