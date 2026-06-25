"""Extracción defensiva de datos desde texto libre de tickets Zoho."""
from __future__ import annotations

import re
from html import unescape


_SEMESTRE_RE = re.compile(r"\b(?:primer|segundo|tercer|cuarto|quinto|sexto|septimo|séptimo|octavo|noveno|decimo|décimo)\s+semestre\b", re.IGNORECASE)
_STOP_RE = re.compile(r"\b(?:agradezco|quedo atent[ao]s?|cordialmente|buenas tardes|buenos dias|buenos días|solicito)\b", re.IGNORECASE)
_GENERIC_RE = re.compile(
    r"\b(?:ticket|recibo|pago|prueba[s]?|ex[aá]men(?:es)? de suficiencia|suficiencia|sinu|opcion|opción|colaboracion|colaboración|apartado)\b",
    re.IGNORECASE,
)
_LETTER_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")


def _clean_text(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return text.replace("\r", "\n")


def _clean_candidate(text: str) -> str:
    text = re.sub(r"^[\s\-–—*•\d.)]+", "", text.strip())
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .;:-")


def _is_subject_candidate(text: str) -> bool:
    if not text or len(text) < 3:
        return False
    if not _LETTER_RE.search(text):
        return False
    if _SEMESTRE_RE.search(text):
        return False
    if _STOP_RE.search(text):
        return False
    if _GENERIC_RE.search(text):
        return False
    if len(text.split()) > 8:
        return False
    return True


def extraer_asignaturas_desde_texto(text: str) -> list[str]:
    """Extrae nombres de asignaturas desde descripciones libres.

    Pensado para tickets que listan materias por semestre, por ejemplo:
    "Tercer Semestre. Anatomía Ilustrada. Sexto Semestre. Ilustración II...".
    """
    cleaned = _clean_text(text)
    if not cleaned.strip():
        return []

    # Convertir encabezados "Tercer Semestre." en separadores explícitos.
    cleaned = _SEMESTRE_RE.sub(lambda m: f"\n{m.group(0)}\n", cleaned)
    raw_parts = re.split(r"[\n]+|(?<=[.?!])\s+", cleaned)

    subjects: list[str] = []
    capture = False
    for raw in raw_parts:
        part = _clean_candidate(raw)
        if not part:
            continue

        lower = part.lower()
        if "materia" in lower or "asignatura" in lower:
            capture = True
            continue
        if _SEMESTRE_RE.search(part):
            capture = True
            continue
        if _STOP_RE.search(part):
            if subjects:
                break
            continue
        if not capture:
            continue

        for candidate in re.split(r"\s*[,;]\s*", part):
            candidate = _clean_candidate(candidate)
            if _is_subject_candidate(candidate) and candidate not in subjects:
                subjects.append(candidate)

    return subjects
