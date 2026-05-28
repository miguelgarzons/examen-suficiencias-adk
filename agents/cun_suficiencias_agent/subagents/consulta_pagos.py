"""Consulta de pagos empresariales desde iceberg.V_ADK_PAGOS.

Calcula `pago_validado=True` si algún registro tiene estado APROBADO/VALIDADO/PAGADO.
"""
from __future__ import annotations

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from ..tools.sql_client import PagosRepository
from ..tools.validators import row_any_value
from .common import StateKeys, append_error, log_event

_ESTADOS_VALIDOS = {"APROBADO", "VALIDADO", "PAGADO"}


class ConsultaPagosAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        state = ctx.session.state
        identificacion = (state.get(StateKeys.IDENTIFICACION) or "").strip()
        log_event("PIPELINE_PAGOS", step="start", identificacion=identificacion)

        if not identificacion:
            log_event("PIPELINE_PAGOS", step="skip_no_id")
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={StateKeys.PAGOS: [], StateKeys.PAGO_VALIDADO: False}
                ),
                content=genai_types.Content(
                    parts=[genai_types.Part(text="Sin identificación; se omite consulta de pagos.")]
                ),
            )
            return

        try:
            rows = await PagosRepository.by_nit(identificacion)
            pago_validado = row_any_value(rows, "ESTADO", _ESTADOS_VALIDOS) or row_any_value(
                rows, "estado", _ESTADOS_VALIDOS
            )
            log_event(
                "PIPELINE_PAGOS",
                step="ok",
                rows=len(rows),
                pago_validado=pago_validado,
            )
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        StateKeys.PAGOS: rows,
                        StateKeys.PAGO_VALIDADO: pago_validado,
                    }
                ),
                content=genai_types.Content(
                    parts=[
                        genai_types.Part(
                            text=f"Pagos consultados: {len(rows)} registro(s); pago_validado={pago_validado}."
                        )
                    ]
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log_event("PIPELINE_PAGOS", step="error", error=str(exc))
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        StateKeys.PAGOS: [],
                        StateKeys.PAGO_VALIDADO: False,
                        StateKeys.ERRORES: append_error(state, "consulta_pagos", str(exc)),
                    }
                ),
                content=genai_types.Content(
                    parts=[genai_types.Part(text=f"Error consultando pagos: {exc}")]
                ),
            )
