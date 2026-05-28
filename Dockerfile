FROM python:3.11-slim-bookworm AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN groupadd --system adk \
    && useradd --system --create-home --gid adk --shell /usr/sbin/nologin adk

FROM base AS deps

COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-compile -r /tmp/requirements.txt \
    && find /opt/venv -type d -name __pycache__ -prune -exec rm -rf {} + \
    && find /opt/venv -type f -name "*.pyc" -delete \
    && find /opt/venv/lib -type d \( -name tests -o -name test -o -name docs -o -name doc \) -prune -exec rm -rf {} +

FROM base AS dev

COPY --from=deps /opt/venv /opt/venv
RUN mkdir -p /app/agents \
    && chown -R adk:adk /app /opt/venv

USER adk

EXPOSE 8000 8001 8080

CMD ["adk", "web", ".", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS runtime

COPY --from=deps /opt/venv /opt/venv
COPY --chown=adk:adk agents /app/agents

WORKDIR /app/agents

USER adk

# Cloud Run requiere este puerto
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "adk api_server . --host 0.0.0.0 --port ${PORT} "]
