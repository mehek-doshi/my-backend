"""RSS 2.0, RSS 1.0 (RDF) and Atom parsing.

Uses defusedxml, so external entities, entity-expansion bombs and DTD tricks are rejected.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from app.core.textutil import clean_text


class FeedParseError(Exception):
    pass


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str
    published_at: datetime | None
    guid: str = ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text(el) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _child(el, *names: str):
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _atom_link(entry) -> str:
    best = ""
    for c in entry:
        if _local(c.tag) == "link":
            rel, href = c.get("rel", "alternate"), c.get("href", "")
            if rel == "alternate" and href:
                return href
            if href and not best:
                best = href
    return best


def parse_feed(content: bytes, limit: int = 50) -> list[FeedItem]:
    try:
        root = ET.fromstring(content, forbid_dtd=True)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise FeedParseError(f"Not a valid feed: {exc.__class__.__name__}") from exc
    kind = _local(root.tag)
    items: list[FeedItem] = []
    if kind == "feed":  # Atom
        for entry in [e for e in root if _local(e.tag) == "entry"]:
            link = _atom_link(entry)
            body = _child(entry, "summary", "content")
            items.append(FeedItem(
                title=clean_text(_text(_child(entry, "title")), 300), link=link.strip(),
                summary=clean_text(_text(body), 2000),
                published_at=parse_date(_text(_child(entry, "published", "updated"))),
                guid=_text(_child(entry, "id"))))
    elif kind in ("rss", "RDF"):
        channel = root if kind == "RDF" else _child(root, "channel")
        if channel is None:
            raise FeedParseError("RSS feed has no channel")
        for it in [e for e in (root if kind == "RDF" else channel) if _local(e.tag) == "item"]:
            link = _text(_child(it, "link"))
            guid = _text(_child(it, "guid"))
            if not link and re.match(r"https?://", guid or ""):
                link = guid
            body = _child(it, "encoded", "description")
            items.append(FeedItem(
                title=clean_text(_text(_child(it, "title")), 300), link=link.strip(),
                summary=clean_text(_text(body), 2000),
                published_at=parse_date(_text(_child(it, "pubDate", "date"))), guid=guid))
    else:
        raise FeedParseError(f"Unsupported feed type '{kind}'")
    return [i for i in items if i.title and i.link][:limit]
