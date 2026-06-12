"""OAuth interno de Zoho con cache TTL — reemplaza el webhook n8n.

Refresca el access token dentro del proceso contra accounts.zoho.com cuando
ZOHO_OAUTH_CLIENT_ID / ZOHO_OAUTH_CLIENT_SECRET / ZOHO_OAUTH_REFRESH_TOKEN
están configurados. Lee env vars dinámicamente en cada llamada (multi-env
friendly). Cache key por (client_id, refresh_token).
"""
from __future__ import annotations

import asyncio
import os
import time

import httpx

from ..subagents.common import log_event

_token_cache: dict[tuple[str, str], tuple[str, float]] = {}
_lock = asyncio.Lock()


def _cid() -> str:
    return (os.getenv("ZOHO_OAUTH_CLIENT_ID") or "").strip()


def _secret() -> str:
    return (os.getenv("ZOHO_OAUTH_CLIENT_SECRET") or "").strip()


def _rtok() -> str:
    return (os.getenv("ZOHO_OAUTH_REFRESH_TOKEN") or "").strip()


def _host() -> str:
    return (os.getenv("ZOHO_ACCOUNTS_HOST") or "https://accounts.zoho.com").rstrip("/")


def is_configured() -> bool:
    return bool(_cid() and _secret() and _rtok())


async def get_access_token(force_refresh: bool = False) -> str:
    cid, sec, rt, host = _cid(), _secret(), _rtok(), _host()
    if not (cid and sec and rt):
        raise RuntimeError("ZOHO_OAUTH_* no configurado")
    key = (cid, rt)
    now = time.time()
    if not force_refresh:
        cached = _token_cache.get(key)
        if cached and cached[1] > now:
            return cached[0]
    async with _lock:
        cached = _token_cache.get(key)
        if not force_refresh and cached and cached[1] > time.time():
            return cached[0]
        log_event("ZOHO_OAUTH_REFRESH", client_id=cid[:12] + "...", host=host)
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(
                f"{host}/oauth/v2/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": cid,
                    "client_secret": sec,
                    "refresh_token": rt,
                },
            )
            r.raise_for_status()
            data = r.json()
        token = data.get("access_token")
        if not token:
            raise ValueError(f"access_token no presente en respuesta OAuth: {list(data)[:5]}")
        ttl = max(int(data.get("expires_in", 3600)) - 60, 60)
        _token_cache[key] = (token, time.time() + ttl)
        return token


def invalidate() -> None:
    _token_cache.clear()
