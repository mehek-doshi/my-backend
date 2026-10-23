"""Microsoft Graph (directory, mail, SharePoint) and Teams incoming-webhook clients.

Auth: OAuth2 client-credentials (application permissions). Required Graph application permissions, granted by a tenant admin:
  directory  -> User.Read.All
  mail       -> Mail.Send   (restrict to the sender mailbox with an Exchange application access policy)
  SharePoint -> Files.ReadWrite.All or Sites.Selected (preferred)
Tested ONLY against mocked HTTP transports. Not verified against a live tenant.
"""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.integrations.base import DirectoryUser, IntegrationError, NotConfigured

GRAPH = "https://graph.microsoft.com/v1.0"
SIMPLE_UPLOAD_LIMIT = 4 * 1024 * 1024
CHUNK = 320 * 1024 * 10  # must be a multiple of 320 KiB


class GraphClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        if not (settings.graph_tenant_id and settings.graph_client_id and settings.graph_client_secret):
            raise NotConfigured("GRAPH_TENANT_ID, GRAPH_CLIENT_ID and GRAPH_CLIENT_SECRET are required")
        self.s = settings
        self.transport = transport
        self._token: tuple[float, str] | None = None

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=30, transport=self.transport, trust_env=False)

    def token(self) -> str:
        if self._token and self._token[0] > time.time() + 60:
            return self._token[1]
        url = f"https://login.microsoftonline.com/{self.s.graph_tenant_id}/oauth2/v2.0/token"
        data = {"grant_type": "client_credentials", "client_id": self.s.graph_client_id,
                "client_secret": self.s.graph_client_secret, "scope": "https://graph.microsoft.com/.default"}
        try:
            with self._client() as c:
                r = c.post(url, data=data)
                r.raise_for_status()
                body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IntegrationError(f"Graph token request failed: {exc.__class__.__name__}") from exc
        self._token = (time.time() + int(body.get("expires_in", 3600)), body["access_token"])
        return self._token[1]

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token()}", **kw.pop("headers", {})}
        for attempt in range(3):
            try:
                with self._client() as c:
                    r = c.request(method, url, headers=headers, **kw)
            except httpx.HTTPError as exc:
                raise IntegrationError(f"Graph request failed: {exc.__class__.__name__}") from exc
            if r.status_code in (429, 503) and attempt < 2:
                time.sleep(min(float(r.headers.get("Retry-After", "1") or 1), 5))
                continue
            if r.status_code >= 400:
                raise IntegrationError(f"Graph returned HTTP {r.status_code}")
            return r
        raise IntegrationError("Graph is throttling requests")


class GraphDirectory:
    name = "graph"

    def __init__(self, client: GraphClient) -> None:
        self.c = client

    def list_users(self) -> list[DirectoryUser]:
        url = f"{GRAPH}/users?$select=id,displayName,mail,userPrincipalName,jobTitle,department,accountEnabled&$top=200"
        out: list[DirectoryUser] = []
        while url and len(out) < 100_000:
            body = self.c.request("GET", url).json()
            for u in body.get("value", []):
                email = (u.get("mail") or u.get("userPrincipalName") or "").lower()
                if "@" in email:
                    out.append(DirectoryUser(u["id"], email, u.get("displayName") or email, u.get("jobTitle"),
                                             u.get("department"), bool(u.get("accountEnabled", True))))
            url = body.get("@odata.nextLink")
        return out


class GraphMail:
    name = "graph"

    def __init__(self, client: GraphClient, sender: str) -> None:
        if not sender:
            raise NotConfigured("MAIL_SENDER is required")
        self.c, self.sender = client, sender

    def send(self, to: str, subject: str, body: str) -> None:
        payload = {"message": {"subject": subject[:200], "body": {"contentType": "Text", "content": body},
                               "toRecipients": [{"emailAddress": {"address": to}}]}, "saveToSentItems": False}
        self.c.request("POST", f"{GRAPH}/users/{quote(self.sender)}/sendMail", json=payload)


class GraphSharePoint:
    name = "graph"

    def __init__(self, client: GraphClient, drive_id: str) -> None:
        if not drive_id:
            raise NotConfigured("SHAREPOINT_DRIVE_ID is required")
        self.c, self.drive = client, drive_id

    def upload(self, local_path: Path, folder: str, filename: str) -> str:
        path = quote(f"{folder.strip('/')}/{filename}")
        size = Path(local_path).stat().st_size
        base = f"{GRAPH}/drives/{self.drive}/root:/{path}:"
        if size <= SIMPLE_UPLOAD_LIMIT:
            r = self.c.request("PUT", f"{base}/content", content=Path(local_path).read_bytes(),
                               headers={"Content-Type": "application/octet-stream"})
            return r.json()["id"]
        session = self.c.request("POST", f"{base}/createUploadSession", json={"item": {"@microsoft.graph.conflictBehavior": "replace"}}).json()
        upload_url, sent, last = session["uploadUrl"], 0, None
        with Path(local_path).open("rb") as fh:
            while chunk := fh.read(CHUNK):
                end = sent + len(chunk) - 1
                with httpx.Client(timeout=120, transport=self.c.transport, trust_env=False) as c:  # upload URL is pre-authorised
                    last = c.put(upload_url, content=chunk, headers={"Content-Range": f"bytes {sent}-{end}/{size}"})
                if last.status_code >= 400:
                    raise IntegrationError(f"SharePoint upload returned HTTP {last.status_code}")
                sent = end + 1
        try:
            return last.json()["id"]
        except (ValueError, KeyError, AttributeError) as exc:
            raise IntegrationError("SharePoint upload did not return an item id") from exc


class TeamsWebhook:
    """Posts to a Teams incoming webhook / Workflows URL. It targets a channel, not a person."""

    name = "webhook"

    def __init__(self, url: str, transport: httpx.BaseTransport | None = None) -> None:
        if not url.startswith("https://"):
            raise NotConfigured("TEAMS_WEBHOOK_URL must be an https URL")
        self.url, self.transport = url, transport

    def post(self, title: str, text: str) -> None:
        try:
            with httpx.Client(timeout=15, transport=self.transport, trust_env=False) as c:
                r = c.post(self.url, json={"type": "message", "text": f"**{title}**\n\n{text}"})
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Teams webhook failed: {exc.__class__.__name__}") from exc
