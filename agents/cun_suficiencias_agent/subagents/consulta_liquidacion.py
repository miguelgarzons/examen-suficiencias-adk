"""Consulta de liquidación académica desde ICEBERG.V_ADK_LIQUIDACION."""
from __future__ import annotations

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from ..tools.sql_client import LiquidacionRepository
from .common import StateKeys, append_error, log_event


class ConsultaLiquidacionAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        state = ctx.session.state
        identificacion = (state.get(StateKeys.IDENTIFICACION) or "").strip()
        log_event("PIPELINE_LIQUIDACION", step="start", identificacion=identificacion)

        if not identificacion:
            log_event("PIPELINE_LIQUIDACION", step="skip_no_id")
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={StateKeys.LIQUIDACION: []}),
                content=genai_types.Content(
                    parts=[genai_types.Part(text="Sin identificación; se omite consulta de liquidación.")]
                ),
            )
            return

        try:
            rows = await LiquidacionRepository.by_identificacion(identificacion)
            log_event("PIPELINE_LIQUIDACION", step="ok", rows=len(rows))
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={StateKeys.LIQUIDACION: rows}),
                content=genai_types.Content(
                    parts=[genai_types.Part(text=f"Liquidación consultada: {len(rows)} registro(s).")]
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log_event("PIPELINE_LIQUIDACION", step="error", error=str(exc))
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        StateKeys.LIQUIDACION: [],
                        StateKeys.ERRORES: append_error(state, "consulta_liquidacion", str(exc)),
                    }
                ),
                content=genai_types.Content(
                    parts=[genai_types.Part(text=f"Error consultando liquidación: {exc}")]
                ),
            )
