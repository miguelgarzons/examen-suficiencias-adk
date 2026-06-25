"""Helpers defensivos + reglas de procedencia de Pruebas de Suficiencia."""
from __future__ import annotations

import unicodedata
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


def _norm_text(value: Any) -> str:
    text = safe_str(value).lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(text.split())


def es_uso_saldo_favor(ticket: dict[str, Any]) -> bool:
    """Detecta tickets de Pagos / Uso de saldo a favor desde campos Zoho."""
    haystack = " ".join(
        _norm_text(ticket.get(key))
        for key in ("category", "subcategory", "tipo_solicitud", "subject")
    )
    raw = ticket.get("raw")
    if isinstance(raw, dict):
        haystack = " ".join(
            [
                haystack,
                _norm_text(raw.get("category")),
                _norm_text(raw.get("subCategory")),
                _norm_text(raw.get("cf_categoria")),
                _norm_text(raw.get("cf_sub_categorias")),
                _norm_text(raw.get("subject")),
            ]
        )
    return "saldo a favor" in haystack


def es_examen_supletorio(ticket: dict[str, Any]) -> bool:
    """Detecta solicitudes de supletorio mal clasificadas como suficiencia."""
    campos = [
        ticket.get("subject"),
        ticket.get("tipo_solicitud"),
        ticket.get("descripcion"),
        ticket.get("asignatura"),
        ticket.get("category"),
        ticket.get("subcategory"),
    ]
    raw = ticket.get("raw")
    if isinstance(raw, dict):
        campos.extend(
            [
                raw.get("subject"),
                raw.get("description"),
                raw.get("plainText"),
                raw.get("cf_categoria"),
                raw.get("cf_sub_categorias"),
            ]
        )
    haystack = " ".join(_norm_text(value) for value in campos)
    return "supletorio" in haystack or "supletoria" in haystack


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
        TEMPLATE_SALDO_FAVOR_INCOMPLETA,
        TEMPLATE_SALDO_FAVOR_SIN_LIQUIDACION,
        TEMPLATE_SALDO_FAVOR_VALIDADO,
        TEMPLATE_SOLICITUD_INCOMPLETA,
        TEMPLATE_REVISION_MANUAL,
    )

    if es_examen_supletorio(ticket):
        return (
            False,
            "La solicitud corresponde a examen supletorio y requiere revisión manual",
            TEMPLATE_REVISION_MANUAL,
        )

    if es_uso_saldo_favor(ticket):
        faltantes = require_fields(ticket, ["identificacion"])
        if faltantes:
            return False, f"Faltan datos obligatorios: {', '.join(faltantes)}", TEMPLATE_SALDO_FAVOR_INCOMPLETA
        if not liquidacion:
            return (
                False,
                "No se encontraron liquidaciones activas para asociar el saldo a favor",
                TEMPLATE_SALDO_FAVOR_SIN_LIQUIDACION,
            )
        return (
            False,
            "Se encontraron liquidaciones activas para validar aplicación de saldo a favor",
            TEMPLATE_SALDO_FAVOR_VALIDADO,
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
