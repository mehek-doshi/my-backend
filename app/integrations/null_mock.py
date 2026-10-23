"""Null (not configured) and Mock (tests / local development only) providers."""
from __future__ import annotations

from pathlib import Path

from app.integrations.base import DirectoryUser, NotConfigured


class _Null:
    name = "none"

    def _no(self, what: str):
        raise NotConfigured(f"{what} integration is not configured")


class NullDirectory(_Null):
    def list_users(self): self._no("Directory")


class NullMail(_Null):
    def send(self, to, subject, body): self._no("Mail")


class NullTeams(_Null):
    def post(self, title, text): self._no("Teams")


class NullSharePoint(_Null):
    def upload(self, local_path, folder, filename): self._no("SharePoint")


class NullBuddy(_Null):
    def notify(self, user_email, message): self._no("Buddy")


class MockDirectory:
    name = "mock"

    def __init__(self, users: list[DirectoryUser] | None = None) -> None:
        self.users = users or []

    def list_users(self) -> list[DirectoryUser]:
        return list(self.users)


class MockMail:
    name = "mock"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail = False

    def send(self, to: str, subject: str, body: str) -> None:
        if self.fail:
            from app.integrations.base import IntegrationError
            raise IntegrationError("mock failure")
        self.sent.append((to, subject, body))


class MockTeams:
    name = "mock"

    def __init__(self) -> None:
        self.posts: list[tuple[str, str]] = []

    def post(self, title: str, text: str) -> None:
        self.posts.append((title, text))


class MockSharePoint:
    name = "mock"

    def __init__(self) -> None:
        self.files: dict[str, tuple[str, str, int]] = {}
        self.fail = False

    def upload(self, local_path: Path, folder: str, filename: str) -> str:
        if self.fail:
            from app.integrations.base import IntegrationError
            raise IntegrationError("mock failure")
        item_id = f"mock-item-{len(self.files) + 1}"
        self.files[item_id] = (folder, filename, Path(local_path).stat().st_size)
        return item_id


class MockBuddy:
    name = "mock"

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def notify(self, user_email: str, message: str) -> None:
        self.messages.append((user_email, message))
