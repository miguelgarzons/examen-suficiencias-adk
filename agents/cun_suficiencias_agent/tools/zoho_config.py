"""Resolución de credenciales Zoho desde variables de entorno únicas."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ZohoSettings:
    env: str
    mcp_url: str
    org_id: str
    default_department_id: str
    desk_api_base: str
    token_webhook_url: str
    token_webhook_user: str
    token_webhook_pass: str

    def is_configured_mcp(self) -> bool:
        return bool(self.mcp_url and self.org_id)

    def is_configured_rest(self) -> bool:
        return bool(self.desk_api_base and self.token_webhook_url and self.org_id)


def _g(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def get_zoho_settings() -> ZohoSettings:
    """Lee env vars en runtime (no en import-time)."""
    return ZohoSettings(
        env="configured",
        mcp_url=_g("ZOHO_MCP_URL"),
        org_id=_g("ZOHO_ORG_ID"),
        default_department_id=_g("ZOHO_DEFAULT_DEPARTMENT_ID"),
        desk_api_base=_g("ZOHO_DESK_API_BASE", "https://desk.zoho.com/api/v1"),
        token_webhook_url=_g("ZOHO_TOKEN_WEBHOOK_URL"),
        token_webhook_user=_g("ZOHO_TOKEN_WEBHOOK_USER"),
        token_webhook_pass=_g("ZOHO_TOKEN_WEBHOOK_PASS"),
    )
