"""Cliente HTTP para servicios internos CUN usados por el agente."""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..subagents.common import log_event

DEFAULT_ADDITIONAL_FEES_URL = (
    "https://appzoho-stg.cunapp.pro/api/v1/adk/catalogos/additional-fees"
)
DEFAULT_COMPANY_PAYMENTS_URL = (
    "https://appzoho-stg.cunapp.pro/api/v1/adk/validaciones-financieras/company-payments"
)
DEFAULT_AUTH_URL = "https://appzoho-stg.cunapp.pro/api/v1/auth/login"

_token_cache: str = ""


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _timeout() -> float:
    raw = _env("CUN_SERVICES_TIMEOUT_SECONDS", "15")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 15.0


def _verify_ssl() -> bool:
    return _env("CUN_SERVICES_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}


async def _get_token(force_refresh: bool = False) -> str:
    global _token_cache
    if _token_cache and not force_refresh:
        return _token_cache

    static_token = _env("CUN_SERVICES_API_TOKEN")
    if static_token and not force_refresh:
        _token_cache = static_token
        return _token_cache

    username = _env("CUN_SERVICES_USERNAME")
    password = _env("CUN_SERVICES_PASSWORD")
    if not username or not password:
        return ""

    auth_url = _env("CUN_SERVICES_AUTH_URL", DEFAULT_AUTH_URL)
    log_event("CUN_SERVICES_TOKEN_FETCH", auth_url=auth_url)
    async with httpx.AsyncClient(timeout=_timeout(), verify=_verify_ssl()) as client:
        response = await client.post(
            auth_url,
            json={"username": username, "password": password},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

    token = data.get("access_token") or data.get("token")
    if not token:
        raise ValueError(f"Token no presente en respuesta de auth: {list(data)[:5]}")
    _token_cache = str(token)
    return _token_cache


async def _headers(force_refresh: bool = False) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    token = await _get_token(force_refresh=force_refresh)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("data", "items", "results", "records", "content"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = _extract_rows(value)
            if nested:
                return nested

    return [payload] if payload else []


async def _get_rows(url: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_timeout(), verify=_verify_ssl()) as client:
        response = await client.get(url, params=params or {}, headers=await _headers())
        if response.status_code == 401:
            response = await client.get(
                url,
                params=params or {},
                headers=await _headers(force_refresh=True),
            )
        response.raise_for_status()
        return _extract_rows(response.json())


def _row_matches_nit(row: dict[str, Any], nit: str) -> bool:
    if not nit:
        return False
    wanted = nit.strip()
    for key, value in row.items():
        if key and key.upper() in {"NIT", "NIT_EMPRESA", "IDENTIFICACION", "DOCUMENTO"}:
            if str(value).strip() == wanted:
                return True
    return False


class PagosRepository:
    @classmethod
    async def by_nit(cls, nit: str) -> list[dict[str, Any]]:
        if not nit:
            return []
        url = _env("CUN_COMPANY_PAYMENTS_URL", DEFAULT_COMPANY_PAYMENTS_URL)
        nit_param = _env("CUN_COMPANY_PAYMENTS_NIT_PARAM", "nitEmpresa")
        rows = await _get_rows(url, params={nit_param: nit})
        filtered = [row for row in rows if _row_matches_nit(row, nit)]
        log_event("CUN_COMPANY_PAYMENTS", rows=len(rows), filtered=len(filtered))
        return filtered or rows


class PecuniariosRepository:
    @classmethod
    async def all(cls) -> list[dict[str, Any]]:
        url = _env("CUN_ADDITIONAL_FEES_URL", DEFAULT_ADDITIONAL_FEES_URL)
        rows = await _get_rows(url)
        log_event("CUN_ADDITIONAL_FEES", rows=len(rows))
        return rows
