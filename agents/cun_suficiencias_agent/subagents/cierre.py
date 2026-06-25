"""Cierre — renderiza HTML institucional con Jinja y emite el Event final.

NO usa LlmAgent. NO llama al modelo. NO lanza 500. SIEMPRE produce HTML.

Si ZOHO_ACTIONS_ENABLED=true, publica la respuesta en el ticket (comentario
público, respuesta por correo si hay email y cierre del ticket) en modo
best-effort. Los casos fuera del alcance del agente dejan solo nota interna y
no se cierran. Ningún fallo de Zoho rompe el pipeline ni impide el HTML final.
"""
from __future__ import annotations

import os
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from ..tools.response_builder import elegir_template
from ..tools.response_builder import TEMPLATE_REVISION_MANUAL
from ..tools.template_renderer import render_template
from ..tools.zoho_actions import (
    cerrar_ticket,
    enviar_respuesta_correo,
    publicar_comentario_ticket,
)
from .common import StateKeys, log_event


def _zoho_actions_flag() -> str:
    return (os.getenv("ZOHO_ACTIONS_ENABLED") or "").strip().lower()


def _zoho_actions_enabled() -> bool:
    return _zoho_actions_flag() in {"1", "true", "yes"}


def _build_context(state: dict[str, Any]) -> dict[str, Any]:
    ticket = state.get(StateKeys.TICKET) or {}
    recibo = state.get(StateKeys.RECIBO) or {}
    liquidacion = state.get(StateKeys.LIQUIDACION) or []
    periodo_actual = state.get(StateKeys.PERIODO_ACTUAL) or {}
    return {
        "ticket": ticket,
        "ticket_id": ticket.get("ticket_id", ""),
        "nombre": ticket.get("nombre", "") or "estudiante",
        "identificacion": ticket.get("identificacion", ""),
        "asignatura": ticket.get("asignatura", ""),
        "codigo_asignatura": ticket.get("codigo_asignatura", ""),
        "causal": state.get(StateKeys.CAUSAL, ""),
        "procede": bool(state.get(StateKeys.PROCEDE)),
        "pago_validado": bool(state.get(StateKeys.PAGO_VALIDADO)),
        "recibo": recibo,
        "liquidacion": liquidacion,
        "liquidaciones": liquidacion,
        "periodo_actual": periodo_actual,
        "errores": state.get(StateKeys.ERRORES, []) or [],
        "warnings": state.get(StateKeys.WARNINGS, []) or [],
    }


async def _publicar_en_zoho(
    ticket: dict[str, Any], html: str, warnings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Comenta, responde por correo y cierra el ticket. Best-effort por acción."""
    resultado: dict[str, Any] = {"comentario": "", "correo": "", "cierre": ""}
    ticket_id = (ticket.get("ticket_id") or "").strip()
    if not ticket_id:
        log_event("PIPELINE_CIERRE", step="zoho_skip_sin_ticket_id")
        return resultado

    try:
        await publicar_comentario_ticket(ticket_id, html)
        resultado["comentario"] = "ok"
    except Exception as exc:  # noqa: BLE001
        resultado["comentario"] = f"error: {exc}"
        warnings.append({"stage": "cierre", "message": f"Comentario Zoho falló: {exc}"})

    email = (ticket.get("email") or "").strip()
    if email:
        try:
            await enviar_respuesta_correo(ticket_id, html, email)
            resultado["correo"] = "ok"
        except Exception as exc:  # noqa: BLE001
            resultado["correo"] = f"error: {exc}"
            warnings.append({"stage": "cierre", "message": f"Respuesta por correo falló: {exc}"})
    else:
        resultado["correo"] = "skip_sin_email"

    try:
        await cerrar_ticket(ticket_id)
        resultado["cierre"] = "ok"
    except Exception as exc:  # noqa: BLE001
        resultado["cierre"] = f"error: {exc}"
        warnings.append({"stage": "cierre", "message": f"Cierre de ticket falló: {exc}"})

    log_event("PIPELINE_CIERRE", step="zoho_done", ticket_id=ticket_id, **resultado)
    return resultado


async def _registrar_revision_manual(
    ticket: dict[str, Any], html: str, warnings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Deja nota interna y evita responder/cerrar cuando el caso no es del agente."""
    resultado: dict[str, Any] = {
        "comentario": "",
        "correo": "skip_revision_manual",
        "cierre": "skip_revision_manual",
    }
    ticket_id = (ticket.get("ticket_id") or "").strip()
    if not ticket_id:
        log_event("PIPELINE_CIERRE", step="zoho_skip_sin_ticket_id")
        return resultado

    try:
        await publicar_comentario_ticket(ticket_id, html, is_public=False)
        resultado["comentario"] = "ok"
    except Exception as exc:  # noqa: BLE001
        resultado["comentario"] = f"error: {exc}"
        warnings.append({"stage": "cierre", "message": f"Nota interna Zoho falló: {exc}"})

    log_event("PIPELINE_CIERRE", step="zoho_revision_manual", ticket_id=ticket_id, **resultado)
    return resultado


class CierreAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        state = ctx.session.state
        log_event("PIPELINE_CIERRE", step="start")

        context = _build_context(state)
        template = elegir_template(
            procede=context["procede"],
            template_propuesto=state.get(StateKeys.TEMPLATE) or "",
            pago_validado=context["pago_validado"],
        )

        warnings = list(state.get(StateKeys.WARNINGS) or [])
        try:
            html = render_template(template, **context)
        except Exception as exc:  # noqa: BLE001 — renderer ya tiene fallback, esto es belt+suspenders
            log_event("PIPELINE_CIERRE", step="render_fail", error=str(exc))
            html = render_template("no_procede.html", **context)
            warnings.append({"stage": "cierre", "message": f"Render fail: {exc}"})

        zoho_result: dict[str, Any] = {}
        if _zoho_actions_enabled():
            if template == TEMPLATE_REVISION_MANUAL:
                zoho_result = await _registrar_revision_manual(context["ticket"], html, warnings)
            else:
                zoho_result = await _publicar_en_zoho(context["ticket"], html, warnings)
        else:
            log_event(
                "PIPELINE_CIERRE",
                step="zoho_actions_disabled",
                zoho_actions_enabled=_zoho_actions_flag() or "unset",
            )

        log_event(
            "PIPELINE_CIERRE",
            step="ok",
            template=template,
            html_bytes=len(html),
        )
        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    StateKeys.TEMPLATE: template,
                    StateKeys.RESPONSE_HTML: html,
                    StateKeys.WARNINGS: warnings,
                    StateKeys.ZOHO_RESULT: zoho_result,
                }
            ),
            content=genai_types.Content(
                parts=[genai_types.Part(text=html)]
            ),
        )
        log_event("PIPELINE_END")
