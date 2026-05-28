"""Cliente SQL async (python-oracledb, thin mode) + repositories CUN.

Usa `oracledb` 2.x en modo thin: implementación pura Python, sin Oracle
Instant Client. Funciona out-of-the-box en Cloud Run (requiere Oracle
Database 12.1+ en el servidor).

Si en el futuro hay que cambiar a otro backend (PostgreSQL/Trino/BigQuery),
basta sustituir el driver respetando esta interfaz pública:
- `fetch_one(query, **params) -> dict | None`
- `fetch_all(query, **params) -> list[dict]`
- `LiquidacionRepository.by_identificacion(...)`
- `PagosRepository.by_nit(...)`
- `PecuniariosRepository.all()`
"""
from __future__ import annotations

import os
from typing import Any

try:
    import oracledb  # type: ignore
except ImportError:  # pragma: no cover - import opcional al testear
    oracledb = None  # type: ignore

from ..subagents.common import log_event

_pool: Any = None


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    try:
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


async def get_pool() -> Any:
    """Crea (lazy) y devuelve un pool asíncrono `oracledb`."""
    global _pool
    if _pool is not None:
        return _pool

    if oracledb is None:
        raise RuntimeError("oracledb no está instalado (pip install oracledb)")

    host = _env("DB_HOST_ORACLE")
    user = _env("DB_USERNAME_ORACLE")
    password = _env("DB_PASSWORD_ORACLE")
    service = _env("DB_SERVICE_NAME_ORACLE")
    if not all([host, user, password, service]):
        raise RuntimeError(
            "Faltan variables: DB_HOST_ORACLE / DB_USERNAME_ORACLE / "
            "DB_PASSWORD_ORACLE / DB_SERVICE_NAME_ORACLE"
        )

    port = _env_int("DB_PORT_ORACLE", 1521)
    dsn = f"{host}:{port}/{service}"
    min_size = _env_int("DB_POOL_MIN_SIZE", 1)
    max_size = _env_int("DB_POOL_MAX_SIZE", 5)

    log_event(
        "SQL_POOL_INIT",
        driver="oracledb-thin",
        dsn=f"{host}:{port}/{service}",
        user=user,
        min=min_size,
        max=max_size,
    )

    # create_pool_async devuelve el pool sincrónicamente; las conexiones que
    # entrega vía acquire() son async.
    _pool = oracledb.create_pool_async(
        user=user,
        password=password,
        dsn=dsn,
        min=min_size,
        max=max_size,
        increment=1,
    )
    return _pool


def _rows_as_dicts(cursor: Any, rows: list[Any]) -> list[dict[str, Any]]:
    """Convierte tuplas a dicts con keys lowercase.

    Oracle devuelve nombres de columna en UPPERCASE por defecto; normalizamos
    a lowercase para que el resto del agente trabaje con keys consistentes.
    """
    desc = cursor.description or []
    cols = [
        (d[0].lower() if d and d[0] else f"col_{i}")
        for i, d in enumerate(desc)
    ]
    return [dict(zip(cols, r)) for r in rows]


async def _execute(query: str, params: dict[str, Any]) -> tuple[Any, list[Any]]:
    pool = await get_pool()
    timeout_s = _env_int("DB_QUERY_TIMEOUT_SECONDS", 30)
    async with pool.acquire() as conn:
        # call_timeout en milisegundos (0 = sin límite)
        try:
            conn.call_timeout = max(0, timeout_s * 1000)
        except Exception:  # noqa: BLE001
            pass
        with conn.cursor() as cursor:
            await cursor.execute(query, params or {})
            rows = await cursor.fetchall()
            return cursor, rows


async def fetch_all(query: str, **params: Any) -> list[dict[str, Any]]:
    cursor, rows = await _execute(query, params)
    return _rows_as_dicts(cursor, rows)


async def fetch_one(query: str, **params: Any) -> dict[str, Any] | None:
    cursor, rows = await _execute(query, params)
    if not rows:
        return None
    return _rows_as_dicts(cursor, rows[:1])[0]


class LiquidacionRepository:
    QUERY = (
        "SELECT * FROM ICEBERG.V_ADK_LIQUIDACION "
        "WHERE identificacion = :identificacion"
    )

    @classmethod
    async def by_identificacion(cls, identificacion: str) -> list[dict[str, Any]]:
        if not identificacion:
            return []
        return await fetch_all(cls.QUERY, identificacion=identificacion)


class PagosRepository:
    QUERY = (
        "SELECT * FROM ICEBERG.V_ADK_PAGOS "
        "WHERE NIT_EMPRESA = :nit"
    )

    @classmethod
    async def by_nit(cls, nit: str) -> list[dict[str, Any]]:
        if not nit:
            return []
        return await fetch_all(cls.QUERY, nit=nit)


class PecuniariosRepository:
    QUERY = "SELECT * FROM ICEBERG.V_ADK_PECUNIARIOS"

    @classmethod
    async def all(cls) -> list[dict[str, Any]]:
        return await fetch_all(cls.QUERY)
