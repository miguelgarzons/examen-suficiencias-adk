FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system adk \
    && useradd --system --create-home --gid adk --shell /usr/sbin/nologin adk

COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-compile -r /tmp/requirements.txt

COPY --chown=adk:adk agents /app/agents
COPY --chown=adk:adk config /app/config

USER adk

ENV PORT=8080
EXPOSE 8080

CMD ["sh","-c","cd /app/agents && adk api_server . --host 0.0.0.0 --port ${PORT:-8080} --no_use_local_storage"]
