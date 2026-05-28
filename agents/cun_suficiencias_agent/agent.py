"""Punto de entrada del agente — `root_agent` que descubre `adk api_server`."""
from __future__ import annotations

from .subagents.orchestrator import build_orchestrator

root_agent = build_orchestrator()
