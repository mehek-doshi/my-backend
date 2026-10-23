"""Certificate PDFs. A tiny hand-written PDF writer (one page, built-in Helvetica) so no extra dependency is needed."""
from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.textutil import sha256_hex
from app.db.models import Certificate, Topic, User
from app.db.types import utcnow
from app.storage.local import LocalStorage


def _esc(text: str) -> str:
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(lines: list[tuple[int, int, int, str]]) -> bytes:
    """lines = (x, y, font_size, text). Returns a valid single-page A4 landscape PDF."""
    content = "\n".join(f"BT /F1 {size} Tf {x} {y} Td ({_esc(t)}) Tj ET" for x, y, size, t in lines).encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def issue_certificate(db: Session, user: User, topic: Topic, storage: LocalStorage | None = None) -> Certificate:
    existing = db.scalar(select(Certificate).where(Certificate.user_id == user.id, Certificate.topic_id == topic.id))
    if existing:
        return existing
    storage = storage or LocalStorage()
    serial = f"TR-{utcnow():%Y}-{secrets.token_hex(4).upper()}"
    issued = utcnow()
    pdf = build_pdf([(250, 480, 28, "Certificate of Contribution"), (150, 400, 14, "Neuleap.ai Tech Radar certifies that"),
                     (150, 360, 24, user.display_name[:60]), (150, 320, 14, "completed all contribution stages for"),
                     (150, 285, 20, topic.title[:70]), (150, 200, 12, f"Issued: {issued:%Y-%m-%d}"),
                     (150, 180, 12, f"Certificate no: {serial}")])
    cert = Certificate(user_id=user.id, topic_id=topic.id, title=topic.title[:300], serial=serial, issued_at=issued, sha256=sha256_hex(pdf))
    db.add(cert)
    db.flush()
    cert.storage_key = f"certificates/{cert.id}.pdf"
    storage.write_bytes(cert.storage_key, pdf)
    return cert
