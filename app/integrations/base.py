"""Integration interfaces. Every external system sits behind one of these so the rest of the code never
imports an SDK, and so a missing integration is an explicit, visible state instead of a silent no-op.

HONESTY NOTE: the Graph / webhook implementations here are verified only against mocked HTTP transports.
They have NOT been run against a real Microsoft 365 tenant. Buddy has no real implementation at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class NotConfigured(Exception):
    """The integration is not configured; the caller should record 'skipped', not 'failed'."""


class IntegrationError(Exception):
    """The external call failed (network, permission, throttling)."""


@dataclass
class DirectoryUser:
    object_id: str
    email: str
    display_name: str
    job_title: str | None = None
    department: str | None = None
    enabled: bool = True


class DirectoryProvider(Protocol):
    name: str
    def list_users(self) -> list[DirectoryUser]: ...


class MailProvider(Protocol):
    name: str
    def send(self, to: str, subject: str, body: str) -> None: ...


class TeamsProvider(Protocol):
    name: str
    def post(self, title: str, text: str) -> None: ...


class SharePointProvider(Protocol):
    name: str
    def upload(self, local_path: Path, folder: str, filename: str) -> str:
        """Upload a file and return the SharePoint item id."""


class BuddyProvider(Protocol):
    name: str
    def notify(self, user_email: str, message: str) -> None: ...
