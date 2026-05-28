"""Construye el dict canónico de recibo cuando PROCEDE."""
from __future__ import annotations

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from ..tools.response_builder import construir_recibo
from .common import StateKeys, append_error, log_event


class GeneradorReciboAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        state = ctx.session.state
        if not state.get(StateKeys.PROCEDE):
            log_event("PIPELINE_RECIBO", step="skip_no_procede")
            yield Event(
                author=self.name,
                content=genai_types.Content(
                    parts=[genai_types.Part(text="No procede — se omite generación de recibo.")]
                ),
            )
            return

        log_event("PIPELINE_RECIBO", step="start")
        try:
            recibo = construir_recibo(
                ticket=state.get(StateKeys.TICKET) or {},
                liquidacion=state.get(StateKeys.LIQUIDACION),
                pecuniarios=state.get(StateKeys.PECUNIARIOS),
            )
            log_event(
                "PIPELINE_RECIBO",
                step="ok",
                referencia=recibo.get("referencia"),
                valor=recibo.get("valor"),
            )
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={StateKeys.RECIBO: recibo}),
                content=genai_types.Content(
                    parts=[
                        genai_types.Part(
                            text=(
                                f"Recibo construido ref={recibo.get('referencia')} "
                                f"valor={recibo.get('valor')}."
                            )
                        )
                    ]
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log_event("PIPELINE_RECIBO", step="error", error=str(exc))
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        StateKeys.RECIBO: {},
                        StateKeys.ERRORES: append_error(state, "generador_recibo", str(exc)),
                    }
                ),
                content=genai_types.Content(
                    parts=[genai_types.Part(text=f"Error generando recibo: {exc}")]
                ),
            )
