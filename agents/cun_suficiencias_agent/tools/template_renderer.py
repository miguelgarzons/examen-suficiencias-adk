"""Renderer Jinja2 con autoescape HTML + fallback institucional."""
from __future__ import annotations

from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from ..subagents.common import TEMPLATES_DIR, log_event

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "htm"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_template(template_name: str, **context: Any) -> str:
    """Renderiza `template_name` con `context`. Devuelve fallback institucional si falla."""
    try:
        tpl = _env.get_template(template_name)
        return tpl.render(**context)
    except TemplateNotFound:
        log_event("TEMPLATE_NOT_FOUND", template=template_name)
        return _fallback_html(context, motivo="Plantilla no encontrada")
    except Exception as exc:  # noqa: BLE001 - renderer NUNCA debe romper el flujo
        log_event("TEMPLATE_RENDER_ERROR", template=template_name, error=str(exc))
        return _fallback_html(context, motivo="Error al generar la respuesta")


def _fallback_html(context: dict[str, Any], motivo: str) -> str:
    nombre = (context.get("nombre") or "estudiante").strip() or "estudiante"
    return (
        "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
        "<title>CUN — Respuesta institucional</title></head>"
        "<body style='font-family:Arial,Helvetica,sans-serif;color:#1f2937;padding:24px;'>"
        f"<h2 style='color:#c8102e;margin:0 0 12px;'>Corporación Unificada Nacional de Educación Superior — CUN</h2>"
        f"<p>Estimado(a) {nombre},</p>"
        "<p>Hemos recibido su solicitud y se encuentra en revisión por el área correspondiente. "
        "Le informaremos por este mismo canal el resultado en el menor tiempo posible.</p>"
        f"<p style='color:#6b7280;font-size:12px;margin-top:24px;'>Ref. interna: {motivo}</p>"
        "<p>Atentamente,<br><strong>Líder de Innovación y Transformación Educativa (LITE)</strong><br>CUN</p>"
        "</body></html>"
    )
