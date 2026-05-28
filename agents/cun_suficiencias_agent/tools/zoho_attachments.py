"""Descarga de adjuntos Zoho Desk via REST + token OAuth desde webhook n8n.

MCP no descarga bytes; por eso se usa REST con Authorization: Zoho-oauthtoken.
Token cacheado por (label, url, user). Refresh automático en 401.
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from ..subagents.common import log_event
from .zoho_config import get_zoho_settings

_token_cache: dict[tuple[str, str, str], str] = {}


async def _get_zoho_token(force_refresh: bool = False) -> str:
    settings = get_zoho_settings()
    if not settings.token_webhook_url:
        raise RuntimeError("ZOHO_TOKEN_WEBHOOK_URL no configurado")

    key = (settings.env, settings.token_webhook_url, settings.token_webhook_user)
    if not force_refresh and key in _token_cache:
        return _token_cache[key]

    auth = (
        (settings.token_webhook_user, settings.token_webhook_pass)
        if settings.token_webhook_user
        else None
    )
    log_event("ZOHO_TOKEN_FETCH", env=settings.env, force_refresh=force_refresh)
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(settings.token_webhook_url, auth=auth)
        r.raise_for_status()
        data = r.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise ValueError(f"Token no presente en respuesta del webhook: {list(data)[:5]}")
    _token_cache[key] = token
    return token


def _headers(token: str, org_id: str) -> dict[str, str]:
    return {"orgId": org_id, "Authorization": f"Zoho-oauthtoken {token}"}


async def list_attachments(ticket_id: str) -> list[dict[str, Any]]:
    """Devuelve [{"name", "url", "size"}, ...] para todos los adjuntos del ticket."""
    settings = get_zoho_settings()
    if not settings.is_configured_rest() or not ticket_id:
        return []

    token = await _get_zoho_token()
    base = settings.desk_api_base.rstrip("/")
    out: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{base}/tickets/{ticket_id}/threads", headers=_headers(token, settings.org_id))
        if r.status_code == 401:
            token = await _get_zoho_token(force_refresh=True)
            r = await c.get(f"{base}/tickets/{ticket_id}/threads", headers=_headers(token, settings.org_id))
        if not r.is_success:
            log_event("ZOHO_LIST_THREADS_FAIL", status=r.status_code)
            return []
        for thread in (r.json().get("data") or []):
            tid = thread.get("id")
            if not tid:
                continue
            detail = await c.get(
                f"{base}/tickets/{ticket_id}/threads/{tid}", headers=_headers(token, settings.org_id)
            )
            if not detail.is_success:
                continue
            for att in (detail.json().get("attachments") or []):
                name = att.get("name", "")
                href = att.get("href") or att.get("downloadUrl")
                if name and href:
                    out.append({"name": name, "url": href, "size": att.get("size")})
    return out


async def download_attachment(url: str) -> dict[str, Any]:
    """Descarga un adjunto y lo devuelve en base64."""
    settings = get_zoho_settings()
    if not settings.is_configured_rest():
        return {"ok": False, "error": "Zoho REST no configurado"}

    token = await _get_zoho_token()
    headers = _headers(token, settings.org_id)
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(url, headers=headers, follow_redirects=True)
        if r.status_code == 401:
            token = await _get_zoho_token(force_refresh=True)
            r = await c.get(url, headers=_headers(token, settings.org_id), follow_redirects=True)
        if not r.is_success:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        ct = r.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        return {
            "ok": True,
            "content_type": ct,
            "bytes_b64": base64.b64encode(r.content).decode("ascii"),
        }
