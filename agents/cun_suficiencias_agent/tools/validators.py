"""Helpers defensivos + reglas de procedencia de Pruebas de Suficiencia."""
from __future__ import annotations

from typing import Any

_TRUE_VALUES = {"1", "true", "t", "si", "sí", "yes", "y", "x", "ok", "approved", "aprobado"}
_FALSE_VALUES = {"0", "false", "f", "no", "n", "null", "none", ""}


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = safe_str(value).lower()
    if s in _TRUE_VALUES:
        return True
    if s in _FALSE_VALUES:
        return False
    return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def require_fields(payload: dict[str, Any], fields: list[str]) -> list[str]:
    """Devuelve la lista de campos faltantes."""
    return [f for f in fields if not safe_str(payload.get(f))]


def row_flag(rows: list[dict[str, Any]], column: str) -> bool:
    """True si alguna fila tiene `column` en true."""
    if not rows:
        return False
    for row in rows:
        if safe_bool(row.get(column)):
            return True
        for alt in (column.upper(), column.lower()):
            if alt in row and safe_bool(row[alt]):
                return True
    return False


def row_any_value(rows: list[dict[str, Any]], column: str, allowed: set[str]) -> bool:
    """True si alguna fila tiene `column` en alguno de los valores (case-insensitive)."""
    if not rows:
        return False
    norm = {v.upper() for v in allowed}
    for row in rows:
        for k, v in row.items():
            if k and k.upper() == column.upper():
                if safe_str(v).upper() in norm:
                    return True
    return False


def evaluar_procedencia(
    ticket: dict[str, Any],
    liquidacion: list[dict[str, Any]],
) -> tuple[bool, str, str]:
    """Aplica las 7 reglas determinísticas de procedencia.

    Devuelve (procede, causal, template_name).
    No usa LLM. Sin efectos secundarios.
    """
    from .response_builder import (  # import local para evitar ciclos
        TEMPLATE_EXTEMPORANEO,
        TEMPLATE_NO_PROCEDE,
        TEMPLATE_RECIBO_GENERADO,
        TEMPLATE_SOLICITUD_INCOMPLETA,
    )

    # Regla 1 — campos obligatorios
    faltantes = require_fields(ticket, ["identificacion", "asignatura"])
    if faltantes:
        return False, f"Faltan datos obligatorios: {', '.join(faltantes)}", TEMPLATE_SOLICITUD_INCOMPLETA

    # Regla 2 — extemporáneo (flag explícito del ticket o de la liquidación)
    if safe_bool(ticket.get("extemporaneo")) or row_flag(liquidacion, "extemporaneo"):
        return False, "Solicitud radicada fuera del calendario académico", TEMPLATE_EXTEMPORANEO

    # Regla 3 — ya cursó la asignatura
    if row_flag(liquidacion, "ya_curso") or row_flag(liquidacion, "cursada"):
        return False, "El estudiante ya cursó la asignatura", TEMPLATE_NO_PROCEDE

    # Regla 4 — reprobada
    if row_flag(liquidacion, "reprobada") or row_flag(liquidacion, "perdida"):
        return False, "El estudiante reprobó previamente la asignatura", TEMPLATE_NO_PROCEDE

    # Regla 5 — ya presentó suficiencia
    if row_flag(liquidacion, "ya_presento_suficiencia") or row_flag(liquidacion, "suficiencia_previa"):
        return False, "El estudiante ya presentó suficiencia para esta asignatura", TEMPLATE_NO_PROCEDE

    # Regla 6 — matriculado actualmente
    if row_flag(liquidacion, "matriculado_actualmente") or row_flag(liquidacion, "matriculada"):
        return False, "El estudiante se encuentra matriculado actualmente en la asignatura", TEMPLATE_NO_PROCEDE

    # Regla 7 — componente práctico
    if row_flag(liquidacion, "componente_practico") or row_flag(liquidacion, "practica"):
        return False, "La asignatura tiene componente práctico/clínico no validable por suficiencia", TEMPLATE_NO_PROCEDE

    return True, "Procede emisión de recibo de pago de suficiencia", TEMPLATE_RECIBO_GENERADO
