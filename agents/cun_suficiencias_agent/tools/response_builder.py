"""Construcción determinística del recibo y selección final de template."""
from __future__ import annotations

from typing import Any

from .validators import safe_str

TEMPLATE_SOLICITUD_INCOMPLETA = "solicitud_incompleta.html"
TEMPLATE_EXTEMPORANEO = "extemporaneo.html"
TEMPLATE_NO_PROCEDE = "no_procede.html"
TEMPLATE_RECIBO_GENERADO = "recibo_generado.html"
TEMPLATE_PAGO_VALIDADO = "pago_validado.html"


def _first_row(rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not rows:
        return {}
    return rows[0] or {}


def _pick(*candidates: Any) -> str:
    for c in candidates:
        s = safe_str(c)
        if s:
            return s
    return ""


def _valor_suficiencia(pecuniarios: list[dict[str, Any]] | None) -> str:
    """Busca el valor de Examen de Suficiencia en derechos pecuniarios."""
    for row in pecuniarios or []:
        concepto = safe_str(row.get("concepto") or row.get("CONCEPTO") or row.get("descripcion"))
        if "SUFICIENCIA" in concepto.upper():
            return _pick(row.get("valor"), row.get("VALOR"), row.get("precio"), row.get("PRECIO"))
    return ""


def construir_recibo(
    ticket: dict[str, Any],
    liquidacion: list[dict[str, Any]] | None,
    pecuniarios: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Construye el dict canónico del recibo a partir del state."""
    liq = _first_row(liquidacion)

    estudiante = _pick(
        ticket.get("nombre"),
        liq.get("nombre"),
        liq.get("NOMBRE"),
        liq.get("estudiante"),
    )
    identificacion = _pick(
        ticket.get("identificacion"),
        liq.get("identificacion"),
        liq.get("IDENTIFICACION"),
    )
    asignatura = _pick(
        ticket.get("asignatura"),
        liq.get("asignatura"),
        liq.get("ASIGNATURA"),
    )
    codigo_asignatura = _pick(
        ticket.get("codigo_asignatura"),
        liq.get("codigo_asignatura"),
        liq.get("CODIGO_ASIGNATURA"),
    )
    referencia = _pick(
        liq.get("referencia"),
        liq.get("REFERENCIA"),
        liq.get("orden"),
        liq.get("ORDEN"),
        ticket.get("ticket_id"),
    )
    valor = _valor_suficiencia(pecuniarios)

    return {
        "identificacion": identificacion,
        "estudiante": estudiante,
        "concepto": "Examen de Suficiencia",
        "asignatura": asignatura,
        "codigo_asignatura": codigo_asignatura,
        "valor": valor,
        "referencia": referencia,
    }


def elegir_template(
    *,
    procede: bool,
    template_propuesto: str,
    pago_validado: bool,
) -> str:
    """Decide el template final dado el estado."""
    if pago_validado:
        return TEMPLATE_PAGO_VALIDADO
    if procede:
        return TEMPLATE_RECIBO_GENERADO
    return template_propuesto or TEMPLATE_NO_PROCEDE
