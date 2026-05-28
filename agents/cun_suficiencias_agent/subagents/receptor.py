"""Receptor — extrae el payload de `newMessage.parts[0].text` y normaliza ticket.

Soporta:
1. JSON limpio: `{"id": "...", ...}`
2. Python repr:  `{'id': '...', ...}`
3. Log line con texto antes/después del JSON
4. Mezcla de comillas simples + false/true/null lowercase
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from ..tools.validators import safe_str
from .common import StateKeys, log_event


def _normalizar_literales_py(s: str) -> str:
    """Convierte false/true/null (en posiciones de valor) a False/True/None."""
    s = re.sub(r"([:\[,]\s*)false\b", r"\1False", s)
    s = re.sub(r"([:\[,]\s*)true\b", r"\1True", s)
    s = re.sub(r"([:\[,]\s*)null\b", r"\1None", s)
    return s


def _extraer_dict(texto: str) -> dict[str, Any] | None:
    if not texto:
        return None
    s = texto.strip()
    try:
        v = json.loads(s)
        if isinstance(v, dict):
            return v
    except (ValueError, TypeError):
        pass
    inicio, fin = s.find("{"), s.rfind("}")
    if inicio == -1 or fin <= inicio:
        return None
    candidato = s[inicio : fin + 1]
    for parser in (
        json.loads,
        ast.literal_eval,
        lambda x: ast.literal_eval(_normalizar_literales_py(x)),
    ):
        try:
            v = parser(candidato)
            if isinstance(v, dict):
                return v
        except (ValueError, SyntaxError, TypeError):
            continue
    return None


def _extraer_raw_de_eventos(ctx: InvocationContext) -> dict[str, Any] | None:
    for ev in reversed(list(ctx.session.events or [])):
        author = (getattr(ev, "author", "") or "").lower()
        role = (
            ev.content.role.lower()
            if ev.content and getattr(ev.content, "role", None)
            else ""
        )
        if author not in ("user", "") and role != "user":
            continue
        for part in (ev.content.parts if ev.content else []):
            text = getattr(part, "text", None)
            if not text:
                continue
            d = _extraer_dict(text)
            if d:
                return d
    return None


def _dig(raw: dict[str, Any], *keys: str) -> Any:
    """Busca el primer valor presente en `raw` (también dentro de `cf` si existe)."""
    cf = raw.get("cf") if isinstance(raw.get("cf"), dict) else {}
    for k in keys:
        if k in raw and raw[k] not in (None, ""):
            return raw[k]
        if cf and k in cf and cf[k] not in (None, ""):
            return cf[k]
    return None


def _normalizar_ticket(raw: dict[str, Any]) -> dict[str, Any]:
    """Normaliza el ticket a campos canónicos. Soporta custom fields cf_*.

    NO usa estos campos para filtrar la ejecución; solo los normaliza.
    """
    contact = raw.get("contact") if isinstance(raw.get("contact"), dict) else {}
    ticket_id = safe_str(_dig(raw, "ticket_id", "id", "ticketNumber"))
    identificacion = safe_str(_dig(raw, "identificacion", "cf_numero_de_documento", "documento", "numero_documento"))
    asignatura = safe_str(_dig(raw, "asignatura", "cf_asignatura", "materia"))
    codigo = safe_str(_dig(raw, "codigo_asignatura", "cf_codigo_asignatura", "codigo"))
    categoria = safe_str(_dig(raw, "category", "cf_categoria", "categoria"))
    subcategoria = safe_str(_dig(raw, "subCategory", "cf_sub_categorias", "subcategoria"))
    tipo = safe_str(_dig(raw, "tipo_solicitud", "subject"))
    nombre = safe_str(_dig(raw, "nombre") or contact.get("fullName") or contact.get("name"))
    email = safe_str(_dig(raw, "email") or contact.get("email"))

    return {
        "ticket_id": ticket_id,
        "subject": safe_str(raw.get("subject")),
        "category": categoria,
        "subcategory": subcategoria,
        "tipo_solicitud": tipo,
        "identificacion": identificacion,
        "asignatura": asignatura,
        "codigo_asignatura": codigo,
        "nombre": nombre,
        "email": email,
        "extemporaneo": raw.get("extemporaneo"),
        "raw": raw,
    }


class ReceptorAgent(BaseAgent):
    """Parsea el payload entrante y lo deja normalizado en session.state."""

    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        log_event("PIPELINE_RECEPTOR", step="start")
        raw = ctx.session.state.get(StateKeys.RAW_TICKET) or _extraer_raw_de_eventos(ctx)
        if not raw:
            log_event("PIPELINE_RECEPTOR", step="no_payload")
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        StateKeys.TICKET: {},
                        StateKeys.WARNINGS: [{"stage": "receptor", "message": "Payload no parseable"}],
                    }
                ),
                content=genai_types.Content(
                    parts=[genai_types.Part(text="Sin payload parseable.")]
                ),
            )
            return

        ticket = _normalizar_ticket(raw)
        log_event(
            "PIPELINE_RECEPTOR",
            step="ok",
            ticket_id=ticket["ticket_id"],
            identificacion=ticket["identificacion"],
            asignatura=ticket["asignatura"],
        )
        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    StateKeys.RAW_TICKET: raw,
                    StateKeys.TICKET: ticket,
                    StateKeys.IDENTIFICACION: ticket["identificacion"],
                    StateKeys.ASIGNATURA: ticket["asignatura"],
                    StateKeys.CODIGO_ASIGNATURA: ticket["codigo_asignatura"],
                }
            ),
            content=genai_types.Content(
                parts=[
                    genai_types.Part(
                        text=(
                            f"Ticket normalizado id={ticket['ticket_id']} "
                            f"doc={ticket['identificacion']} asignatura={ticket['asignatura']}"
                        )
                    )
                ]
            ),
        )
