#############################
# Verificacion Academica CUN - 2.0
#############################

FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:${PATH}"

# Solo lo minimo para que healthcheck y conexion HTTPS funcionen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root.
RUN groupadd --system adk \
    && useradd --system --create-home --gid adk --shell /usr/sbin/nologin adk

# Venv aislado con dependencias del agente.
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-compile -r /tmp/requirements.txt \
    && find /opt/venv -type d -name __pycache__ -prune -exec rm -rf {} + \
    && find /opt/venv -type f -name "*.pyc" -delete

# Codigo de la aplicacion.
COPY --chown=adk:adk agents /app/agents

USER adk

ENV PORT=8080
EXPOSE 8080

# Cloud Run inyecta $PORT en runtime; mantenemos el default para `docker run`
# local sin -e PORT.
CMD ["sh", "-c", "cd /app/agents && adk api_server . --host 0.0.0.0 --port ${PORT:-8080} --no_use_local_storage"]
