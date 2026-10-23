"""SSRF protection for every outbound request made with a user- or feed-supplied URL.

Rules
- http/https only, no credentials in the URL, ports limited to an allow-list.
- The host is resolved *here* and every returned address must be a public address.
  The request is then sent to the validated IP (connection pinning), so a DNS answer that
  changes between the check and the connection cannot redirect us to an internal host.
- Redirects are followed manually (max N) and every hop is validated again.
- Responses are streamed with a hard size cap and a content-type allow-list.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Callable, Protocol
from urllib.parse import urljoin, urlsplit

import httpx


class FetchError(Exception):
    """Base class for fetch failures."""


class BlockedURLError(FetchError):
    """The URL points somewhere we refuse to connect to."""


class ResponseTooLargeError(FetchError):
    pass


class UnsupportedContentError(FetchError):
    pass


@dataclass
class FetchResult:
    url: str
    status_code: int
    content: bytes
    content_type: str = ""
    headers: dict[str, str] = field(default_factory=dict)


class Fetcher(Protocol):
    def get(self, url: str, *, max_bytes: int | None = None, accept_types: tuple[str, ...] | None = None) -> FetchResult: ...


Resolver = Callable[[str, int], list[str]]

_BLOCKED_NAMES = {"localhost", "localhost.localdomain", "metadata.google.internal", "metadata"}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".intranet", ".corp", ".home", ".lan")


def default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_url(url: str, *, allowed_ports: list[int] | None = None, resolver: Resolver | None = None) -> tuple[str, list[str]]:
    """Return (hostname, public_ips) or raise BlockedURLError."""
    if not url or len(url) > 2048:
        raise BlockedURLError("URL is empty or too long")
    if any(c in url for c in ("\r", "\n", "\t", " ")):
        raise BlockedURLError("URL contains whitespace or control characters")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise BlockedURLError("Only http and https URLs are allowed")
    if parts.username or parts.password:
        raise BlockedURLError("URLs with embedded credentials are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise BlockedURLError("URL has no host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise BlockedURLError("URL has an invalid port") from exc
    if allowed_ports is not None and port not in allowed_ports:
        raise BlockedURLError(f"Port {port} is not allowed")
    if host in _BLOCKED_NAMES or host.endswith(_BLOCKED_SUFFIXES):
        raise BlockedURLError("Internal host names are not allowed")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    try:
        addrs = [str(literal)] if literal is not None else (resolver or default_resolver)(host, port)
    except (OSError, UnicodeError) as exc:
        raise FetchError(f"Could not resolve host: {exc}") from exc
    if not addrs:
        raise FetchError("Host did not resolve")
    bad = [a for a in addrs if not is_public_ip(a)]
    if bad:
        raise BlockedURLError("Host resolves to a non-public address")
    return host, addrs


class SafeFetcher:
    """HTTP GET with SSRF protection, redirect re-validation, size and type limits."""

    def __init__(self, *, timeout: float = 10.0, max_bytes: int = 2 * 1024 * 1024, max_redirects: int = 3,
                 allowed_ports: list[int] | None = None, resolver: Resolver | None = None,
                 transport: httpx.BaseTransport | None = None, user_agent: str = "TechRadarBot/1.0") -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.allowed_ports = allowed_ports or [80, 443]
        self.resolver = resolver
        self.transport = transport
        self.user_agent = user_agent

    def get(self, url: str, *, max_bytes: int | None = None, accept_types: tuple[str, ...] | None = None) -> FetchResult:
        limit = max_bytes or self.max_bytes
        current = url
        for _hop in range(self.max_redirects + 1):
            host, addrs = validate_url(current, allowed_ports=self.allowed_ports, resolver=self.resolver)
            parts = urlsplit(current)
            ip = addrs[0]
            netloc_ip = f"[{ip}]" if ":" in ip else ip
            if parts.port:
                netloc_ip += f":{parts.port}"
            pinned = parts._replace(netloc=netloc_ip).geturl()
            headers = {"Host": parts.netloc.split("@")[-1], "User-Agent": self.user_agent, "Accept-Encoding": "identity"}
            extensions = {"sni_hostname": host} if parts.scheme == "https" else {}
            client_kwargs: dict = {"timeout": self.timeout, "follow_redirects": False, "trust_env": False}
            if self.transport is not None:
                client_kwargs["transport"] = self.transport
            try:
                with httpx.Client(**client_kwargs) as client:
                    with client.stream("GET", pinned, headers=headers, extensions=extensions) as resp:
                        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                            current = urljoin(current, resp.headers["location"])
                            continue
                        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                        if accept_types and resp.status_code < 400 and not any(ctype.startswith(t) for t in accept_types):
                            raise UnsupportedContentError(f"Content type '{ctype or 'unknown'}' is not accepted")
                        declared = resp.headers.get("content-length")
                        if declared and declared.isdigit() and int(declared) > limit:
                            raise ResponseTooLargeError("Response is larger than the allowed size")
                        body = bytearray()
                        for chunk in resp.iter_bytes():
                            body.extend(chunk)
                            if len(body) > limit:
                                raise ResponseTooLargeError("Response is larger than the allowed size")
                        return FetchResult(url=current, status_code=resp.status_code, content=bytes(body),
                                           content_type=ctype, headers=dict(resp.headers))
            except httpx.HTTPError as exc:
                raise FetchError(f"Request failed: {exc.__class__.__name__}") from exc
        raise FetchError("Too many redirects")
