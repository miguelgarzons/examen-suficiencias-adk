"""Orquestador — ejecuta el pipeline con ramificación según PROCEDE.

Pipeline:
    receptor → consulta_liquidacion → validador
      → IF procede: consulta_pagos + consulta_pecuniarios + generador_recibo
    → cierre (SIEMPRE)
"""
from __future__ import annotations

from typing import ClassVar

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext

from .cierre import CierreAgent
from .common import StateKeys, log_event
from .consulta_liquidacion import ConsultaLiquidacionAgent
from .consulta_pagos import ConsultaPagosAgent
from .consulta_pecuniarios import ConsultaPecuniariosAgent
from .generador_recibo import GeneradorReciboAgent
from .receptor import ReceptorAgent
from .validador import ValidadorAgent


class OrchestratorAgent(BaseAgent):
    receptor: BaseAgent
    consulta_liquidacion: BaseAgent
    validador: BaseAgent
    consulta_pagos: BaseAgent
    consulta_pecuniarios: BaseAgent
    generador_recibo: BaseAgent
    cierre: BaseAgent

    model_config: ClassVar[dict] = {"arbitrary_types_allowed": True}

    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        log_event("PIPELINE_START", session=ctx.session.id if ctx.session else None)

        async for ev in self.receptor.run_async(ctx):
            yield ev
        async for ev in self.consulta_liquidacion.run_async(ctx):
            yield ev
        async for ev in self.validador.run_async(ctx):
            yield ev

        if ctx.session.state.get(StateKeys.PROCEDE):
            async for ev in self.consulta_pagos.run_async(ctx):
                yield ev
            async for ev in self.consulta_pecuniarios.run_async(ctx):
                yield ev
            async for ev in self.generador_recibo.run_async(ctx):
                yield ev

        # Cierre SIEMPRE corre — incluso si todo lo anterior falló
        async for ev in self.cierre.run_async(ctx):
            yield ev


def build_orchestrator() -> OrchestratorAgent:
    return OrchestratorAgent(
        name="cun_suficiencias_orchestrator",
        description=(
            "Orquestador determinístico para Pruebas de Suficiencia CUN. "
            "Pipeline: receptor → liquidación → validador → (pagos + pecuniarios + recibo) → cierre."
        ),
        sub_agents=[],
        receptor=ReceptorAgent(name="receptor"),
        consulta_liquidacion=ConsultaLiquidacionAgent(name="consulta_liquidacion"),
        validador=ValidadorAgent(name="validador"),
        consulta_pagos=ConsultaPagosAgent(name="consulta_pagos"),
        consulta_pecuniarios=ConsultaPecuniariosAgent(name="consulta_pecuniarios"),
        generador_recibo=GeneradorReciboAgent(name="generador_recibo"),
        cierre=CierreAgent(name="cierre"),
    )
