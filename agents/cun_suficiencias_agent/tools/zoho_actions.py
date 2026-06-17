"""Acciones de escritura sobre Zoho Desk vía MCP (streamablehttp + ClientSession).

Todas las funciones envían `contentType: "html"` para evitar el escape visible
en el ticket.
"""
from __future__ import annotations

import json
from typing import Any

from ..subagents.common import log_event
from .zoho_config import get_zoho_settings

try:
    from mcp import ClientSession  # type: ignore
    from mcp.client.streamable_http import streamablehttp_client  # type: ignore
except ImportError:  # pragma: no cover
    ClientSession = None  # type: ignore
    streamablehttp_client = None  # type: ignore


async def _call_mcp(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    if ClientSession is None or streamablehttp_client is None:
        raise RuntimeError("mcp client no disponible (instala `mcp>=1.2.0`)")

    settings = get_zoho_settings()
    if not settings.is_configured_mcp():
        missing = ", ".join(settings.missing_mcp_vars())
        raise RuntimeError(f"Zoho MCP no configurado para env={settings.env}; faltan: {missing}")

    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    log_event("ZOHO_MCP_CALL", env=settings.env, tool=tool_name)
    async with streamablehttp_client(url=settings.mcp_url, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool(tool_name, args)

    data = _to_dict(result)
    summary = _summarize_result(data)
    is_error = _is_error_result(data)
    log_event("ZOHO_MCP_RESULT", tool=tool_name, is_error=is_error, summary=summary)
    if is_error:
        raise RuntimeError(f"{tool_name} devolvió error: {summary}")
    return data


def _to_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    for attr in ("model_dump", "dict"):
        fn = getattr(result, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                continue
    return {"raw": str(result)}


def _summarize_result(data: dict[str, Any], max_chars: int = 900) -> str:
    """Resumen compacto para logs sin imprimir payloads gigantes."""
    content = data.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("data") or item.get("content")
                if text:
                    parts.append(str(text))
            elif item:
                parts.append(str(item))
        if parts:
            text = " | ".join(parts)
            return text[:max_chars]

    for key in ("structuredContent", "structured_content", "result", "error", "errors", "raw"):
        value = data.get(key)
        if value:
            try:
                text = json.dumps(value, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                text = str(value)
            return text[:max_chars]

    try:
        text = json.dumps(data, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(data)
    return text[:max_chars]


def _is_error_result(data: dict[str, Any]) -> bool:
    """Detecta errores lógicos del MCP aunque el transporte HTTP sea 200/202."""
    for key in ("isError", "is_error"):
        if data.get(key) is True:
            return True

    for key in ("error", "errors"):
        if data.get(key):
            return True

    content = data.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str):
                continue
            stripped = text.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                if parsed.get("isError") is True or parsed.get("is_error") is True:
                    return True
                if parsed.get("error") or parsed.get("errors"):
                    return True
                status = str(parsed.get("status") or parsed.get("status_code") or "").lower()
                if status in {"error", "failed", "failure"}:
                    return True

    return False


async def publicar_comentario_ticket(
    ticket_id: str, content: str, is_public: bool = True
) -> dict[str, Any]:
    """Publica un comentario HTML en un ticket Zoho Desk."""
    settings = get_zoho_settings()
    return await _call_mcp(
        "ZohoDesk_createTicketComment",
        {
            "query_params": {"orgId": settings.org_id},
            "path_variables": {"ticketId": ticket_id},
            "request_body": {
                "content": content,
                "contentType": "html",
                "isPublic": is_public,
            },
        },
    )


async def cerrar_ticket(ticket_id: str) -> dict[str, Any]:
    """Cierra un ticket Zoho Desk."""
    settings = get_zoho_settings()
    return await _call_mcp(
        "ZohoDesk_closeTickets",
        {
            "query_params": {"orgId": settings.org_id},
            "request_body": {"ids": [ticket_id]},
        },
    )


async def enviar_respuesta_correo(
    ticket_id: str, content: str, to_email: str
) -> dict[str, Any]:
    """Envía una respuesta por correo (canal EMAIL) al solicitante del ticket."""
    settings = get_zoho_settings()
    return await _call_mcp(
        "ZohoDesk_sendReply",
        {
            "query_params": {"orgId": settings.org_id},
            "path_variables": {"ticketId": ticket_id},
            "request_body": {
                "channel": "EMAIL",
                "content": content,
                "contentType": "html",
                "to": to_email,
            },
        },
    )
