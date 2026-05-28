"""StateKeys, logging estructurado y helpers compartidos por subagentes."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"


class StateKeys:
    RAW_TICKET = "raw_ticket"
    TICKET = "ticket"
    IDENTIFICACION = "identificacion"
    ASIGNATURA = "asignatura"
    CODIGO_ASIGNATURA = "codigo_asignatura"
    PROCEDE = "procede"
    CAUSAL = "causal"
    LIQUIDACION = "liquidacion"
    PAGOS = "pagos"
    PECUNIARIOS = "pecuniarios"
    RECIBO = "recibo"
    TEMPLATE = "template"
    RESPONSE_HTML = "response_html"
    ERRORES = "errores"
    WARNINGS = "warnings"
    PAGO_VALIDADO = "pago_validado"


class TemplateNames:
    SOLICITUD_INCOMPLETA = "solicitud_incompleta.html"
    EXTEMPORANEO = "extemporaneo.html"
    NO_PROCEDE = "no_procede.html"
    RECIBO_GENERADO = "recibo_generado.html"
    PAGO_VALIDADO = "pago_validado.html"


_log_level = os.getenv("APP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("cun_suficiencias")


def log_event(event: str, **fields: Any) -> None:
    """Logging estructurado: emite `EVENT k=v k=v ...` y un JSON compacto."""
    safe: dict[str, Any] = {}
    for k, v in fields.items():
        try:
            json.dumps(v, default=str)
            safe[k] = v
        except (TypeError, ValueError):
            safe[k] = str(v)
    kv = " ".join(f"{k}={json.dumps(v, default=str, ensure_ascii=False)}" for k, v in safe.items())
    logger.info("%s %s", event, kv)


def append_error(state: dict[str, Any], stage: str, message: str) -> list[dict[str, Any]]:
    errores = list(state.get(StateKeys.ERRORES) or [])
    errores.append({"stage": stage, "message": message})
    return errores


def append_warning(state: dict[str, Any], stage: str, message: str) -> list[dict[str, Any]]:
    warnings = list(state.get(StateKeys.WARNINGS) or [])
    warnings.append({"stage": stage, "message": message})
    return warnings
