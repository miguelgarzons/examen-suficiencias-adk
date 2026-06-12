"""Descarga de adjuntos Zoho Desk via REST + token OAuth.

MCP no descarga bytes; por eso se usa REST con Authorization: Zoho-oauthtoken.
El token sale del OAuth interno (zoho_oauth, preferido) o del webhook n8n
(camino legado mientras se migran las credenciales). Cache con TTL y refresh
automático en 401.
"""
from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from ..subagents.common import log_event
from . import zoho_oauth
from .zoho_config import get_zoho_settings

_WEBHOOK_TOKEN_TTL_SECONDS = 3000  # tokens Zoho viven 3600s; margen de 10 min

_token_cache: dict[tuple[str, str], tuple[str, float]] = {}


async def _get_zoho_token(force_refresh: bool = False) -> str:
    if zoho_oauth.is_configured():
        return await zoho_oauth.get_access_token(force_refresh=force_refresh)

    # Camino legado: webhook n8n. Anti-patrón según skill v2 — migrar a
    # ZOHO_OAUTH_* y eliminar este bloque.
    settings = get_zoho_settings()
    if not settings.token_webhook_url:
        raise RuntimeError("Ni ZOHO_OAUTH_* ni ZOHO_TOKEN_WEBHOOK_URL configurados")

    key = (settings.token_webhook_url, settings.token_webhook_user)
    now = time.time()
    if not force_refresh:
        cached = _token_cache.get(key)
        if cached and cached[1] > now:
            return cached[0]

    auth = (
        (settings.token_webhook_user, settings.token_webhook_pass)
        if settings.token_webhook_user
        else None
    )
    log_event("ZOHO_TOKEN_FETCH", source="webhook_n8n", force_refresh=force_refresh)
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(settings.token_webhook_url, auth=auth)
        r.raise_for_status()
        data = r.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise ValueError(f"Token no presente en respuesta del webhook: {list(data)[:5]}")
    ttl = max(int(data.get("expires_in", _WEBHOOK_TOKEN_TTL_SECONDS)) - 60, 60)
    _token_cache[key] = (token, time.time() + ttl)
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
