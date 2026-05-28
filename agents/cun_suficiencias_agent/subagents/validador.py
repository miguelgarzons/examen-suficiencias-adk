"""Validador determinístico — aplica reglas de procedencia (sin LLM)."""
from __future__ import annotations

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from ..tools.validators import evaluar_procedencia
from .common import StateKeys, log_event


class ValidadorAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        state = ctx.session.state
        ticket = state.get(StateKeys.TICKET) or {}
        liquidacion = state.get(StateKeys.LIQUIDACION) or []

        log_event("PIPELINE_VALIDADOR", step="start")
        procede, causal, template = evaluar_procedencia(ticket, liquidacion)
        log_event(
            "PIPELINE_VALIDADOR",
            step="ok",
            procede=procede,
            causal=causal,
            template=template,
        )

        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    StateKeys.PROCEDE: procede,
                    StateKeys.CAUSAL: causal,
                    StateKeys.TEMPLATE: template,
                }
            ),
            content=genai_types.Content(
                parts=[genai_types.Part(text=f"Validación: procede={procede}. {causal}")]
            ),
        )
