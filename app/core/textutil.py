"""Small, dependency-free text helpers used by discovery, dedup and guardrails."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = {"fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid", "igshid", "source", "spm"}
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "into", "is", "it", "its", "new",
    "now", "of", "on", "or", "our", "that", "the", "this", "to", "we", "what", "why", "with", "your", "you",
}
# zero-width, bidi and other invisible control characters that are used to hide instructions
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿­]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    return hashlib.sha256(data).hexdigest()


def canonicalize_url(url: str) -> str:
    """Normalise a URL so that trivially different links compare equal."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit(("https" if parts.scheme in ("http", "https") else parts.scheme, netloc, path, urlencode(sorted(query)), ""))


def url_hash(url: str) -> str:
    return sha256_hex(canonicalize_url(url))


def title_tokens(title: str) -> frozenset[str]:
    text = unicodedata.normalize("NFKC", title).lower()
    return frozenset(t for t in re.findall(r"[a-z0-9][a-z0-9+#.\-]*", text) if t not in _STOPWORDS and len(t) > 1)


def title_fingerprint(title: str) -> str:
    return sha256_hex(" ".join(sorted(title_tokens(title))))


def jaccard(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def strip_html(text: str) -> str:
    parser = _Stripper()
    try:
        parser.feed(text or "")
        parser.close()
    except Exception:  # malformed markup: fall back to a blunt tag removal
        return re.sub(r"<[^>]*>", " ", text or "")
    return "".join(parser.parts)


def clean_text(text: str, max_len: int = 4000) -> str:
    """Strip markup and invisible characters, collapse whitespace, truncate."""
    text = strip_html(text or "")
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = _CONTROL.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]
