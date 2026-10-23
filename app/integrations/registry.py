"""Builds the configured providers and reports their state honestly."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.integrations import null_mock as nm
from app.integrations.base import NotConfigured
from app.integrations.graph import GraphClient, GraphDirectory, GraphMail, GraphSharePoint, TeamsWebhook


@dataclass
class Integrations:
    directory: Any
    mail: Any
    teams: Any
    sharepoint: Any
    buddy: Any
    errors: dict[str, str] = field(default_factory=dict)

    def status(self) -> dict[str, dict[str, Any]]:
        out = {}
        for key in ("directory", "mail", "teams", "sharepoint", "buddy"):
            p = getattr(self, key)
            out[key] = {"provider": p.name, "configured": p.name != "none", "mock": p.name == "mock",
                        "verified_against_live_system": False, "error": self.errors.get(key)}
        return out


def build_integrations(settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> Integrations:
    s = settings or get_settings()
    errors: dict[str, str] = {}
    graph = None

    def graph_client() -> GraphClient:
        nonlocal graph
        graph = graph or GraphClient(s, transport)
        return graph

    def make(key: str, kind: str, factories: dict[str, Any], null: Any):
        try:
            return factories[kind]()
        except NotConfigured as exc:
            errors[key] = str(exc)
            return null
        except KeyError:
            errors[key] = f"unknown provider '{kind}'"
            return null

    return Integrations(
        directory=make("directory", s.directory_provider, {"none": nm.NullDirectory, "mock": nm.MockDirectory,
                                                           "graph": lambda: GraphDirectory(graph_client())}, nm.NullDirectory()),
        mail=make("mail", s.mail_provider, {"none": nm.NullMail, "mock": nm.MockMail,
                                            "graph": lambda: GraphMail(graph_client(), s.mail_sender)}, nm.NullMail()),
        teams=make("teams", s.teams_provider, {"none": nm.NullTeams, "mock": nm.MockTeams,
                                               "webhook": lambda: TeamsWebhook(s.teams_webhook_url, transport)}, nm.NullTeams()),
        sharepoint=make("sharepoint", s.sharepoint_provider, {"none": nm.NullSharePoint, "mock": nm.MockSharePoint,
                                                              "graph": lambda: GraphSharePoint(graph_client(), s.sharepoint_drive_id)}, nm.NullSharePoint()),
        buddy=make("buddy", s.buddy_provider, {"none": nm.NullBuddy, "mock": nm.MockBuddy}, nm.NullBuddy()),
        errors=errors,
    )


_factory = None
_cached: Integrations | None = None


def set_integrations_factory(factory) -> None:
    """Tests inject mock providers here."""
    global _factory, _cached
    _factory, _cached = factory, None


def get_integrations() -> Integrations:
    global _cached
    if _factory:
        return _factory()
    if _cached is None:
        _cached = build_integrations()
    return _cached
