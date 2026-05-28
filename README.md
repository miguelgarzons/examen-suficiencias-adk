# cun_suficiencias_agent

Agente enterprise Google ADK para automatizar solicitudes de la **Corporación Unificada Nacional de Educación Superior — CUN**, categoría **EMISIÓN DE RECIBOS DE PAGO / SUBCATEGORÍA EXAMEN DE SUFICIENCIA** (también aplicable a supletorios, habilitaciones, derechos pecuniarios, liquidaciones académicas, validación de pagos empresariales).

Patrón: `adk api_server` puro + `BaseAgent` determinístico + Jinja institucional + Cloud Run.

---

## 1. Arquitectura

- **`adk api_server`** sirve el agente. No FastAPI, no Flask, no uvicorn directo.
- **`root_agent`** = `OrchestratorAgent` (`BaseAgent` custom) que encadena subagentes y ramifica según `session.state`.
- Cada subagente es un `BaseAgent` con `_run_async_impl`, emite `Event` con `EventActions(state_delta={...})`.
- El LLM **no** participa en lógica de negocio ni en el cierre — todo es determinístico.
- Persistencia: vistas Iceberg vía `asyncpg`. Pool lazy, lectura de env en runtime.
- Integraciones: Zoho Desk MCP (escritura) + Zoho REST (descarga de adjuntos) + n8n webhook (refresh OAuth).

## 2. Flujo del pipeline

```
receptor                       ← parsea newMessage.parts[0].text
  → consulta_liquidacion       ← SELECT … ICEBERG.V_ADK_LIQUIDACION
    → validador                ← 7 reglas determinísticas
      → IF procede:
          consulta_pagos       ← SELECT … V_ADK_PAGOS + pago_validado
          consulta_pecuniarios ← SELECT … V_ADK_PECUNIARIOS
          generador_recibo     ← dict canónico del recibo
      → cierre (SIEMPRE)       ← Jinja → RESPONSE_HTML → Event final
```

**Garantía**: el `cierre` se ejecuta siempre, incluso si:
- el payload no se puede parsear
- faltan campos obligatorios
- una consulta SQL falla
- la solicitud no procede
- falta una variable de entorno
- Zoho no responde

## 3. Estructura de carpetas

```
cun_suficiencias_agent/                   (= "mi_agente" del spec; raíz del proyecto ADK)
├── Dockerfile                            single-stage, python:3.12-slim-bookworm
├── docker-compose.yml                    1 servicio adk-api en :8080
├── requirements.txt
├── .env / .env.example                   ADK + Zoho + DB vars
├── .gitignore / .dockerignore
├── README.md                             este archivo
├── .github/workflows/deploy.yml          GH Actions → Artifact Registry → Cloud Run
├── config/mcp/servers.yaml               Zoho MCP (max_tools, include_name_patterns)
└── agents/
    ├── __init__.py
    └── cun_suficiencias_agent/           paquete Python que `adk api_server` descubre
        ├── __init__.py
        ├── agent.py                      root_agent = build_orchestrator()
        ├── subagents/
        │   ├── common.py                 StateKeys, logging estructurado, helpers
        │   ├── receptor.py               parser JSON/repr/log + normaliza ticket
        │   ├── consulta_liquidacion.py
        │   ├── validador.py              reglas determinísticas
        │   ├── consulta_pagos.py
        │   ├── consulta_pecuniarios.py
        │   ├── generador_recibo.py
        │   ├── cierre.py                 render Jinja + Event final (sin LLM)
        │   └── orchestrator.py           ramifica según PROCEDE
        ├── tools/
        │   ├── sql_client.py             pool asyncpg + Repositories
        │   ├── template_renderer.py      Jinja2 con autoescape + fallback
        │   ├── validators.py             helpers + evaluar_procedencia
        │   ├── response_builder.py       construir_recibo + elegir_template
        │   ├── zoho_config.py            credenciales Zoho por env vars
        │   ├── zoho_actions.py           MCP: comentar/cerrar/responder reply
        │   └── zoho_attachments.py       REST + n8n token
        └── templates/
            ├── base.html
            ├── solicitud_incompleta.html
            ├── extemporaneo.html
            ├── no_procede.html
            ├── recibo_generado.html
            └── pago_validado.html
```

## 4. Variables de entorno

Copiar `.env.example` a `.env` y rellenar. Las vars `VPS_*` son del helper `connect.sh` (no las usa el agente). Las que sí usa el agente:

### Google ADK / Gemini

| Variable | Default | Descripción |
|---|---|---|
| `AGENT_MODEL` | `gemini-2.5-flash` | Modelo del SDK. `flash` recomendado (cuota gratis y suficiente). |
| `GEMINI_API_KEY` | — | API key de Google AI Studio. |
| `GOOGLE_GENAI_USE_VERTEXAI` | `false` | `true` solo si usa Vertex. |
| `APP_LOG_LEVEL` | `INFO` | `DEBUG` para verbose. |

### Zoho

`ZOHO_MCP_URL`, `ZOHO_ORG_ID`, `ZOHO_DEFAULT_DEPARTMENT_ID`, `ZOHO_DESK_API_BASE`, `ZOHO_TOKEN_WEBHOOK_URL`, `ZOHO_TOKEN_WEBHOOK_USER`, `ZOHO_TOKEN_WEBHOOK_PASS`.

Para usar sandbox o production se cambian manualmente los valores de esas mismas variables; el código no usa selector de ambiente ni sufijos.

### Base de datos Oracle CUN

`DB_HOST_ORACLE`, `DB_PORT_ORACLE` (default `1521`), `DB_USERNAME_ORACLE`, `DB_PASSWORD_ORACLE`, `DB_SERVICE_NAME_ORACLE`, `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE`, `DB_QUERY_TIMEOUT_SECONDS`.

DSN se construye automáticamente como `host:port/service_name` (formato Easy Connect).

## 5. Ejecución local

### Con Python directo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # rellenar valores

cd agents
adk api_server . --host 0.0.0.0 --port 8080 --no_use_local_storage
```

### Con Docker Compose

```bash
cp .env.example .env   # rellenar valores
docker compose up --build
```

El agente queda en `http://localhost:8080`.

## 6. Pruebas con `curl`

### Listar apps (healthcheck)

```bash
curl -s http://localhost:8080/list-apps
# → ["cun_suficiencias_agent"]
```

### Crear sesión

```bash
curl -X POST http://localhost:8080/apps/cun_suficiencias_agent/users/test-user/sessions/test-1 \
  -H "Content-Type: application/json" -d '{}'
```

### Ejecutar el agente

```bash
curl -X POST http://localhost:8080/run \
  -H "Content-Type: application/json" \
  -d '{
    "appName": "cun_suficiencias_agent",
    "userId": "test-user",
    "sessionId": "test-1",
    "newMessage": {
      "role": "user",
      "parts": [
        {
          "text": "{\"ticket_id\":\"T-1001\",\"cf_numero_de_documento\":\"1023456789\",\"cf_asignatura\":\"Cálculo Diferencial\",\"cf_codigo_asignatura\":\"MAT-101\",\"cf_categoria\":\"EMISION DE RECIBOS DE PAGO\",\"cf_sub_categorias\":\"EXAMEN DE SUFICIENCIA\",\"contact\":{\"fullName\":\"Juan Pérez\",\"email\":\"juan@example.com\"}}"
        }
      ]
    }
  }'
```

El último evento del stream contiene el HTML institucional (`StateKeys.RESPONSE_HTML`).

### Casos de prueba sugeridos

1. **Payload sin `cf_asignatura`** → `solicitud_incompleta.html`.
2. **Estudiante ya cursó la materia** (mock en V_ADK_LIQUIDACION) → `no_procede.html`.
3. **Fuera de calendario** (flag `extemporaneo=true`) → `extemporaneo.html`.
4. **Procede + sin pago previo** → `recibo_generado.html`.
5. **Pago empresarial APROBADO** en V_ADK_PAGOS → `pago_validado.html`.
6. **DB caída** → `no_procede.html` + `ERRORES` poblado, sin HTTP 500.

## 7. Despliegue a Cloud Run

Push a `main` → prod · `qa` → qa · cualquier otra → dev.

```
us-central1 · 1Gi · 1 CPU · timeout 300s · concurrency 10
min-instances 0 · max-instances 10 · allow-unauthenticated
```

El workflow construye imagen single-stage, sube a Artifact Registry y despliega con `--set-env-vars="^|^...|..."` (delimitador `|` para tolerar `,` `#` `&` en secrets). Después hace healthcheck contra `/list-apps` y **falla la run** si `cun_suficiencias_agent` no aparece.

## 8. GitHub Secrets requeridos

| Secret | Notas |
|---|---|
| `GCP_PROJECT_ID` | ID del proyecto GCP |
| `GCP_SA_KEY` | JSON completo del SA con `roles/run.admin` + `roles/artifactregistry.writer` + `roles/iam.serviceAccountUser` |
| `AGENT_MODEL` | `gemini-2.5-flash` |
| `GEMINI_API_KEY` | API key Google AI Studio |
| `GOOGLE_GENAI_USE_VERTEXAI` | `false` |
| `ZOHO_MCP_URL`, `ZOHO_ORG_ID`, `ZOHO_DEFAULT_DEPARTMENT_ID`, `ZOHO_DESK_API_BASE` | Zoho Desk |
| `ZOHO_TOKEN_WEBHOOK_URL`, `ZOHO_TOKEN_WEBHOOK_USER`, `ZOHO_TOKEN_WEBHOOK_PASS` | n8n token webhook |
| `DB_HOST_ORACLE`, `DB_PORT_ORACLE`, `DB_USERNAME_ORACLE`, `DB_PASSWORD_ORACLE`, `DB_SERVICE_NAME_ORACLE` | Base académica/financiera Oracle |
| `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE`, `DB_QUERY_TIMEOUT_SECONDS` | Tunings opcionales |

### Bootstrap GCP (una sola vez)

```bash
PROJECT_ID="<tu-proyecto>"
REGION="us-central1"

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

for env in dev qa prod; do
  gcloud artifacts repositories create "cun-suficiencias-agent-$env" \
    --repository-format=docker --location=$REGION
done

SA="github-actions-deployer"
gcloud iam service-accounts create $SA
SA_EMAIL="${SA}@${PROJECT_ID}.iam.gserviceaccount.com"
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" --role=$role
done

gcloud iam service-accounts keys create /tmp/sa-key.json --iam-account=$SA_EMAIL
cat /tmp/sa-key.json   # → copiar a GitHub Secret `GCP_SA_KEY`
rm /tmp/sa-key.json
```

## 9. Notas sobre SQL driver

El cliente usa **`python-oracledb` 2.x en modo thin** (pura implementación Python, sin Oracle Instant Client). Funciona out-of-the-box en Cloud Run.

- **Requisito en el servidor**: Oracle Database **12.1 o superior** (thin mode no soporta 11g; si la base CUN es más vieja, hay que habilitar thick mode + Instant Client en el Dockerfile).
- **DSN**: se construye como `${DB_HOST_ORACLE}:${DB_PORT_ORACLE}/${DB_SERVICE_NAME_ORACLE}` (Easy Connect). Para wallets/TLS hay que adaptar a `tcps://...` y montar el wallet.
- **Placeholders**: nombrados (`:identificacion`, `:nit`). No usar `?` ni `$1`.
- **Normalización de columnas**: Oracle devuelve nombres en UPPERCASE; `fetch_all`/`fetch_one` los normaliza a lowercase para consistencia con el resto del agente.
- **Timeout**: `DB_QUERY_TIMEOUT_SECONDS` se aplica como `connection.call_timeout` (en ms).

**Si en el futuro hay que migrar a otro backend** (PostgreSQL, Trino, BigQuery, Snowflake), sustituir el driver manteniendo la interfaz pública de [tools/sql_client.py](agents/cun_suficiencias_agent/tools/sql_client.py):

- `fetch_one(query, **params) -> dict | None`
- `fetch_all(query, **params) -> list[dict]`
- `LiquidacionRepository.by_identificacion(...)`
- `PagosRepository.by_nit(...)`
- `PecuniariosRepository.all()`

Y ajustar los placeholders según el driver (`$1` para asyncpg, `?` para SQLAlchemy/Trino). El resto del agente no cambia.

## 10. Notas sobre Zoho

- `tools/zoho_config.py` resuelve **en runtime** (no en import-time) las variables únicas `ZOHO_*`.
- Para cambiar entre sandbox y production, actualiza manualmente los valores de esas variables en `.env`, GitHub Secrets o Cloud Run.
- El servidor MCP de Zoho expone **300+ tools**. `config/mcp/servers.yaml` limita a 60 via `max_tools` + `include_name_patterns` para evitar saturar el contexto de eventuales tool-calls.
- `tools/zoho_actions.py` siempre envía `contentType: "html"` — sin esto, el HTML aparece escapado en el ticket.
- `tools/zoho_attachments.py` usa REST (`Zoho-oauthtoken`) porque MCP no descarga bytes; el token se obtiene del webhook n8n y se cachea por `(label, url, user)` con refresh automático en 401.

## 11. Antipatrones evitados

- ❌ FastAPI/Flask envolviendo el agente. Solo `adk api_server`.
- ❌ Multi-stage Dockerfile. Single-stage con venv en `/opt/venv`.
- ❌ `LlmAgent` en el cierre. `BaseAgent` puro renderiza Jinja y devuelve `Event`.
- ❌ `SequentialAgent` cuando hay ramificación condicional. `OrchestratorAgent` custom con `if`.
- ❌ `FunctionTool` para plumbing (downloads, render, OAuth refresh). Funciones Python normales.
- ❌ Filtros `ZOHO_CATEGORY_FILTER` / `ZOHO_SUBCATEGORY_FILTER` dentro del agente — el ruteo es externo.
- ❌ OCR local (tesseract/poppler). Si se necesita visión, usar Gemini Vision directo.
- ❌ Env vars leídas a import-time. Todas se leen en runtime con `os.getenv(...)`.
- ❌ Excepción no controlada que rompe el request. Cada falla se registra en `ERRORES`/`WARNINGS` y el cierre continúa.
- ❌ Commit de `.env`. El `.gitignore` lo protege.

## 12. Relación con el VPS Hermes

Este proyecto **no se despliega al VPS** — va a Cloud Run. El VPS Hermes (62.171.161.15) corre el agente Hermes de Nous Research, un proyecto separado.

El helper SSH (`connect.sh`) y las credenciales VPS viven en la **carpeta padre** ([../](../)). Ver [../README.md](../README.md).

---

**Logging estructurado** — eventos emitidos por el pipeline (cada línea es buscable):

`PIPELINE_START`, `PIPELINE_RECEPTOR`, `PIPELINE_LIQUIDACION`, `PIPELINE_VALIDADOR`, `PIPELINE_PAGOS`, `PIPELINE_PECUNIARIOS`, `PIPELINE_RECIBO`, `PIPELINE_CIERRE`, `PIPELINE_END`.

Cada uno incluye `ticket_id`, `identificacion`, `procede`, `causal`, `template`, `rows`, `error` cuando aplica.
