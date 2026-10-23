"""Ingestion agent: receives an upload safely and scans the stored file.

receive(): streaming write with a hard size cap, header validation, sha256 -> returns where it landed.
scan():    runs in the worker on the stored file (secrets, client names, archive structure, executables).
There is no antivirus engine: the report says `antivirus: not_configured` unless a VirusScanner is plugged in.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.config import Settings
from app.core.errors import PayloadTooLarge, Unprocessable
from app.security.uploads import (NullVirusScanner, ScanReport, UploadRejected, VirusScanner, scan_file,
                                  validate_upload_header)
from app.storage.local import LocalStorage

CHUNK = 1024 * 1024


@dataclass
class Received:
    filename: str
    tmp_path: Path
    sha256: str
    size: int


class IngestionAgent:
    name = "ingestion"

    def __init__(self, settings: Settings, storage: LocalStorage | None = None, antivirus: VirusScanner | None = None) -> None:
        self.settings = settings
        self.storage = storage or LocalStorage(settings.storage_dir)
        self.antivirus = antivirus or NullVirusScanner()

    def receive(self, filename: str, stream: BinaryIO) -> Received:
        tmp = self.storage.new_temp()
        h, size, clean = hashlib.sha256(), 0, ""
        try:
            with tmp.open("wb") as out:
                while chunk := stream.read(CHUNK):
                    if size == 0:
                        try:
                            clean = validate_upload_header(filename, chunk[:8192])
                        except UploadRejected as exc:
                            raise Unprocessable(exc.message) from exc
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise PayloadTooLarge(f"Files can be at most {self.settings.max_upload_bytes // (1024 * 1024)} MB")
                    h.update(chunk)
                    out.write(chunk)
            if size == 0:
                raise Unprocessable("The file is empty")
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return Received(clean, tmp, h.hexdigest(), size)

    def scan(self, path: Path) -> ScanReport:
        return scan_file(path, client_names=self.settings.client_denylist, antivirus=self.antivirus)
