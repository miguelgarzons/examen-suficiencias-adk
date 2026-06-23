"""Consulta liquidaciones activas y calendario académico CUN."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from ..tools.cun_services import (
    CalendarioAcademicoRepository,
    LiquidacionesActivasRepository,
)
from .common import StateKeys, log_event


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _periodos_vigentes(periodos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    vigentes: list[dict[str, Any]] = []
    for periodo in periodos:
        inicio = _parse_date(periodo.get("fechaInicioGlobal"))
        fin = _parse_date(periodo.get("fechaFinalGlobal"))
        if inicio and fin and inicio <= now <= fin:
            vigentes.append(periodo)
    return sorted(
        vigentes,
        key=lambda row: _parse_date(row.get("fechaInicioGlobal")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


class ConsultaLiquidacionAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        state = ctx.session.state
        identificacion = (ctx.session.state.get(StateKeys.IDENTIFICACION) or "").strip()
        log_event("PIPELINE_LIQUIDACION", step="start", identificacion=identificacion)

        if not identificacion:
            log_event("PIPELINE_LIQUIDACION", step="skip_no_id")
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        StateKeys.LIQUIDACION: [],
                        StateKeys.CALENDARIO_GLOBAL: [],
                        StateKeys.PERIODO_ACTUAL: {},
                    }
                ),
                content=genai_types.Content(
                    parts=[genai_types.Part(text="Sin identificación; se omite consulta de liquidación.")]
                ),
            )
            return

        try:
            liquidaciones = await LiquidacionesActivasRepository.by_documento(identificacion)
            calendario = await CalendarioAcademicoRepository.global_periods()
            periodos_actuales = _periodos_vigentes(calendario)
            periodo_actual = periodos_actuales[0] if periodos_actuales else {}

            log_event(
                "PIPELINE_LIQUIDACION",
                step="ok",
                rows=len(liquidaciones),
                calendario_rows=len(calendario),
                periodo_actual=periodo_actual.get("codigoPeriodo", ""),
            )
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        StateKeys.LIQUIDACION: liquidaciones,
                        StateKeys.CALENDARIO_GLOBAL: calendario,
                        StateKeys.PERIODO_ACTUAL: periodo_actual,
                    }
                ),
                content=genai_types.Content(
                    parts=[
                        genai_types.Part(
                            text=(
                                f"Liquidaciones activas: {len(liquidaciones)}; "
                                f"periodo vigente: {periodo_actual.get('codigoPeriodo', 'sin identificar')}."
                            )
                        )
                    ]
                ),
            )
        except Exception as exc:  # noqa: BLE001
            errores = list(state.get(StateKeys.ERRORES) or [])
            errores.append({"stage": "consulta_liquidacion", "message": str(exc)})
            log_event("PIPELINE_LIQUIDACION", step="error", error=str(exc))
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        StateKeys.LIQUIDACION: [],
                        StateKeys.CALENDARIO_GLOBAL: [],
                        StateKeys.PERIODO_ACTUAL: {},
                        StateKeys.ERRORES: errores,
                    }
                ),
                content=genai_types.Content(
                    parts=[genai_types.Part(text=f"Error consultando liquidaciones: {exc}")]
                ),
            )
