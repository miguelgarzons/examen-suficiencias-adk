"""Cierre — renderiza HTML institucional con Jinja y emite el Event final.

NO usa LlmAgent. NO llama al modelo. NO lanza 500. SIEMPRE produce HTML.
"""
from __future__ import annotations

from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from ..tools.response_builder import elegir_template
from ..tools.template_renderer import render_template
from .common import StateKeys, append_warning, log_event


def _build_context(state: dict[str, Any]) -> dict[str, Any]:
    ticket = state.get(StateKeys.TICKET) or {}
    recibo = state.get(StateKeys.RECIBO) or {}
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
        "errores": state.get(StateKeys.ERRORES, []) or [],
        "warnings": state.get(StateKeys.WARNINGS, []) or [],
    }


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

        try:
            html = render_template(template, **context)
        except Exception as exc:  # noqa: BLE001 — renderer ya tiene fallback, esto es belt+suspenders
            log_event("PIPELINE_CIERRE", step="render_fail", error=str(exc))
            html = render_template("no_procede.html", **context)
            state_delta_warnings = append_warning(state, "cierre", f"Render fail: {exc}")
        else:
            state_delta_warnings = state.get(StateKeys.WARNINGS) or []

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
                    StateKeys.WARNINGS: state_delta_warnings,
                }
            ),
            content=genai_types.Content(
                parts=[genai_types.Part(text=html)]
            ),
        )
        log_event("PIPELINE_END")
