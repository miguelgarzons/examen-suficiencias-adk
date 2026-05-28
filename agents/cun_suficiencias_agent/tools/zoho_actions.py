"""Acciones de escritura sobre Zoho Desk vía MCP (streamablehttp + ClientSession).

Todas las funciones envían `contentType: "html"` para evitar el escape visible
en el ticket.
"""
from __future__ import annotations

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
        raise RuntimeError(f"Zoho MCP no configurado para env={settings.env}")

    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    log_event("ZOHO_MCP_CALL", env=settings.env, tool=tool_name)
    async with streamablehttp_client(url=settings.mcp_url, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool(tool_name, args)
    return _to_dict(result)


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
