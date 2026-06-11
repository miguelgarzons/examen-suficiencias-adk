"""Paso de compatibilidad: consulta externa de liquidación deshabilitada."""
from __future__ import annotations

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from .common import StateKeys, log_event


class ConsultaLiquidacionAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        identificacion = (ctx.session.state.get(StateKeys.IDENTIFICACION) or "").strip()
        log_event("PIPELINE_LIQUIDACION", step="start", identificacion=identificacion)

        log_event("PIPELINE_LIQUIDACION", step="skip_external_query_removed")
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={StateKeys.LIQUIDACION: []}),
            content=genai_types.Content(
                parts=[genai_types.Part(text="Consulta externa de liquidación deshabilitada.")]
            ),
        )
