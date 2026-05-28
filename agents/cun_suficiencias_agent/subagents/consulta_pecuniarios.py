"""Consulta de derechos pecuniarios (catálogo) desde iceberg.V_ADK_PECUNIARIOS."""
from __future__ import annotations

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from ..tools.sql_client import PecuniariosRepository
from .common import StateKeys, append_error, log_event


class ConsultaPecuniariosAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        state = ctx.session.state
        log_event("PIPELINE_PECUNIARIOS", step="start")
        try:
            rows = await PecuniariosRepository.all()
            log_event("PIPELINE_PECUNIARIOS", step="ok", rows=len(rows))
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={StateKeys.PECUNIARIOS: rows}),
                content=genai_types.Content(
                    parts=[genai_types.Part(text=f"Pecuniarios cargados: {len(rows)} registro(s).")]
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log_event("PIPELINE_PECUNIARIOS", step="error", error=str(exc))
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        StateKeys.PECUNIARIOS: [],
                        StateKeys.ERRORES: append_error(state, "consulta_pecuniarios", str(exc)),
                    }
                ),
                content=genai_types.Content(
                    parts=[genai_types.Part(text=f"Error consultando pecuniarios: {exc}")]
                ),
            )
