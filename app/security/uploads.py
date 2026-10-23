"""Upload validation and content scanning.

Two stages:
- `validate_upload_header` runs while the upload is received (name, extension, magic bytes). A failure
  rejects the upload; nothing is stored.
- `scan_file` runs in the worker on the stored file (zip structure, secrets, client names, executables
  inside archives). Findings quarantine the artifact until a new file replaces it.

There is NO antivirus engine in this codebase. `VirusScanner` is the integration point (ClamAV etc.);
until one is configured every scan result says `antivirus: not_configured`.
"""
from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.core.textutil import sha256_hex

BLOCKED_EXT = {"exe", "dll", "msi", "bin", "com", "bat", "cmd", "scr", "so", "dylib", "dmg", "app", "apk", "jar",
               "ps1", "vbs", "sh", "lnk", "pif", "cpl", "msc", "wsf", "hta"}
ALLOWED_EXT = {"zip", "pdf", "ppt", "pptx", "key", "doc", "docx", "md", "txt", "ipynb", "xls", "xlsx", "csv", "py",
               "js", "ts", "json", "png", "jpg", "jpeg"}
ZIP_BASED = {"zip", "docx", "pptx", "xlsx"}
TEXT_EXT = {"md", "txt", "ipynb", "csv", "py", "js", "ts", "json"}
# magic number -> description, for content that must never be accepted whatever the extension says
EXECUTABLE_MAGIC = [(b"MZ", "Windows executable"), (b"\x7fELF", "Linux executable"),
                    (b"\xcf\xfa\xed\xfe", "macOS executable"), (b"\xce\xfa\xed\xfe", "macOS executable"),
                    (b"\xca\xfe\xba\xbe", "Java class / universal binary"), (b"#!", "script with interpreter line")]
MAGIC = {"pdf": b"%PDF", "png": b"\x89PNG", "jpg": b"\xff\xd8\xff", "jpeg": b"\xff\xd8\xff"}
MAX_ZIP_ENTRIES = 5000
MAX_ZIP_UNCOMPRESSED = 1024 * 1024 * 1024  # 1 GiB
MAX_ZIP_RATIO = 200
MAX_TEXT_SCAN_BYTES = 1024 * 1024
MAX_FILES_TEXT_SCANNED = 500

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("generic_secret", re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|token|client[_-]?secret)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{12,}")),
]
_PLACEHOLDER = re.compile(r"(?i)(example|your[_-]|<.*>|xxx+|\*{4,}|changeme|placeholder)")


class VirusScanner(Protocol):
    name: str

    def scan(self, path: Path) -> dict[str, Any]: ...


class NullVirusScanner:
    """Honest default: nothing was scanned for malware."""

    name = "none"

    def scan(self, path: Path) -> dict[str, Any]:
        return {"engine": "none", "status": "not_configured"}


class UploadRejected(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def sanitize_filename(name: str) -> str:
    name = os.path.basename((name or "").replace("\\", "/")).strip().strip(".")
    name = re.sub(r"[^A-Za-z0-9._\- ]", "_", name)
    name = re.sub(r"\s+", " ", name)[:120]
    return name or "file"


def extension_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def validate_upload_header(filename: str, head: bytes) -> str:
    """Return the sanitised filename or raise UploadRejected."""
    clean = sanitize_filename(filename)
    ext = extension_of(clean)
    if not ext:
        raise UploadRejected("Files need an extension")
    if ext in BLOCKED_EXT:
        raise UploadRejected(f".{ext} files are not allowed because they cannot be scanned safely")
    if ext not in ALLOWED_EXT:
        raise UploadRejected(f".{ext} is not a supported file type")
    if not head:
        raise UploadRejected("The file is empty")
    for magic, label in EXECUTABLE_MAGIC:
        if head.startswith(magic) and not (magic == b"#!" and ext in TEXT_EXT):
            raise UploadRejected(f"The file content looks like a {label}")
    if ext in ZIP_BASED and not head.startswith(b"PK\x03\x04"):
        raise UploadRejected(f"The file content does not match a .{ext} file")
    if ext in MAGIC and not head.startswith(MAGIC[ext]):
        raise UploadRejected(f"The file content does not match a .{ext} file")
    if ext in TEXT_EXT:
        if b"\x00" in head:
            raise UploadRejected(f"The file content does not look like a .{ext} text file")
        try:
            head.decode("utf-8")
        except UnicodeDecodeError as exc:
            if exc.start < len(head) - 4:  # ignore a multi-byte character cut by the sampling window
                raise UploadRejected(f"The file content is not valid UTF-8 text") from exc
    return clean


@dataclass
class Finding:
    kind: str
    severity: str  # "block" | "warn"
    file: str
    line: int | None = None
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "severity": self.severity, "file": self.file, "line": self.line, "detail": self.detail}


@dataclass
class ScanReport:
    sha256: str
    size_bytes: int
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    antivirus: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return any(f.severity == "block" for f in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {"sha256": self.sha256, "size_bytes": self.size_bytes, "files_scanned": self.files_scanned,
                "blocked": self.blocked, "antivirus": self.antivirus, "findings": [f.as_dict() for f in self.findings]}


def scan_text(name: str, text: str, client_names: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    lowered = text.lower()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pat in _SECRET_PATTERNS:
            m = pat.search(line)
            if m and not _PLACEHOLDER.search(m.group(0)):
                # never keep the secret itself: only its type, location and a hash prefix
                findings.append(Finding("secret:" + kind, "block", name, lineno, f"sha256:{sha256_hex(m.group(0))[:10]}"))
                break
        if len(findings) >= 50:
            break
    for client in client_names:
        if client and client.lower() in lowered:
            findings.append(Finding("client_name", "block", name, None, "A configured client name appears in this file"))
    return findings


def _sha256_file(path: Path) -> tuple[str, int]:
    import hashlib
    h, size = hashlib.sha256(), 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _scan_zip(path: Path, report: ScanReport, client_names: list[str]) -> None:
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        report.findings.append(Finding("corrupt_archive", "block", path.name, detail="Not a valid zip archive"))
        return
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            report.findings.append(Finding("too_many_entries", "block", path.name, detail=f"{len(infos)} entries"))
            return
        total = sum(i.file_size for i in infos)
        compressed = max(1, sum(i.compress_size for i in infos))
        if total > MAX_ZIP_UNCOMPRESSED or total / compressed > MAX_ZIP_RATIO:
            report.findings.append(Finding("zip_bomb", "block", path.name, detail=f"{total} bytes uncompressed"))
            return
        scanned = 0
        for info in infos:
            name = info.filename
            parts = name.replace("\\", "/").split("/")
            if name.startswith(("/", "\\")) or ".." in parts or re.match(r"^[A-Za-z]:", name):
                report.findings.append(Finding("path_traversal", "block", name))
                continue
            if info.flag_bits & 0x1:
                report.findings.append(Finding("encrypted_entry", "block", name, detail="Encrypted entries cannot be scanned"))
                continue
            if info.is_dir():
                continue
            ext = extension_of(name)
            if ext in BLOCKED_EXT:
                report.findings.append(Finding("executable_in_archive", "block", name))
                continue
            if ext in ZIP_BASED and ext == "zip":
                report.findings.append(Finding("nested_archive", "warn", name, detail="Nested archives are not unpacked"))
                continue
            if ext in TEXT_EXT or ext in ("html", "yml", "yaml", "toml", "env", "cfg", "ini", "xml", "sql", "tf", "sh") or name.endswith((".env", "Dockerfile")):
                if scanned >= MAX_FILES_TEXT_SCANNED:
                    report.findings.append(Finding("scan_limit", "warn", path.name, detail="Not every file was scanned"))
                    break
                with zf.open(info) as fh:
                    raw = fh.read(MAX_TEXT_SCAN_BYTES)
                head = raw[:8]
                if any(head.startswith(m) for m, _ in EXECUTABLE_MAGIC if m != b"#!"):
                    report.findings.append(Finding("executable_in_archive", "block", name, detail="Executable content"))
                    continue
                report.findings.extend(scan_text(name, raw.decode("utf-8", "replace"), client_names))
                scanned += 1
        report.files_scanned = scanned


def scan_file(path: Path, *, client_names: list[str] | None = None, antivirus: VirusScanner | None = None) -> ScanReport:
    sha, size = _sha256_file(path)
    report = ScanReport(sha256=sha, size_bytes=size)
    client_names = client_names or []
    ext = extension_of(path.name)
    with path.open("rb") as fh:
        head = fh.read(16)
    for magic, label in EXECUTABLE_MAGIC:
        if head.startswith(magic) and not (magic == b"#!" and ext in TEXT_EXT):
            report.findings.append(Finding("executable_content", "block", path.name, detail=label))
    if ext in ZIP_BASED:
        if ext == "zip":
            _scan_zip(path, report, client_names)
        else:  # office files are zips too: look inside for executables and embedded macros only
            try:
                with zipfile.ZipFile(path) as zf:
                    for info in zf.infolist():
                        if extension_of(info.filename) in BLOCKED_EXT or info.filename.lower().endswith("vbaproject.bin"):
                            report.findings.append(Finding("embedded_code", "block", info.filename))
            except zipfile.BadZipFile:
                report.findings.append(Finding("corrupt_archive", "block", path.name))
    elif ext in TEXT_EXT:
        raw = path.read_bytes()[:MAX_TEXT_SCAN_BYTES]
        report.findings.extend(scan_text(path.name, raw.decode("utf-8", "replace"), client_names))
        report.files_scanned = 1
    report.antivirus = (antivirus or NullVirusScanner()).scan(path)
    if report.antivirus.get("status") == "infected":
        report.findings.append(Finding("malware", "block", path.name, detail=str(report.antivirus.get("signature", ""))))
    return report
