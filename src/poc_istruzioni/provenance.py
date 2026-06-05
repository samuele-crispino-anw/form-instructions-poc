"""Primitive di tracciabilità (FR-T1/FR-T3): hashing sha256, run_id, timestamp UTC.

Gli artefatti deterministici (PNG pagina, markdown) si identificano per hash stabile;
gli artefatti prodotti da LLM si versionano per `run_id` e non si sovrascrivono mai.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB


def sha256_bytes(data: bytes) -> str:
    """Hash esadecimale sha256 di una sequenza di byte."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Hash sha256 di una stringa, codificata in UTF-8."""
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path | str) -> str:
    """Hash sha256 di un file, letto a blocchi (gestisce file grandi come il PDF)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def new_run_id() -> str:
    """Identificatore univoco di esecuzione per gli artefatti LLM (FR-T3)."""
    return f"run_{uuid.uuid4().hex}"


def utc_now_iso() -> str:
    """Timestamp corrente in UTC, ISO-8601 con offset esplicito (timezone-aware)."""
    return datetime.now(UTC).isoformat()
