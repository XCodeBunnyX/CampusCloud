"""
Cloud Controller Services — business logic layer.

Sits between the HTTP routes and the HDFS client.
Handles: metadata persistence (SQLite), validation,
         safe filename mapping, and orchestration.
"""

import hashlib
import logging
import os
import re
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

from werkzeug.utils import secure_filename

from cloud_controller.hdfs_client import hdfs_client, HDFSError, HDFSConnectionError
from config import active_config as cfg

logger = logging.getLogger(__name__)

# ─── SQLite schema ──────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id            TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    hdfs_name     TEXT NOT NULL UNIQUE,
    size_bytes    INTEGER NOT NULL,
    content_type  TEXT,
    sha256        TEXT,
    uploaded_at   REAL NOT NULL,
    deleted       INTEGER NOT NULL DEFAULT 0
);
"""


class ValidationError(Exception):
    pass


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize the SQLite metadata database."""
    with _get_db() as conn:
        conn.executescript(SCHEMA)
    logger.info("SQLite database ready at %s", cfg.DB_PATH)


def _validate_filename(filename: str) -> str:
    """
    Sanitize and validate the uploaded filename.
    Raises ValidationError on problems.
    Returns the safe filename.
    """
    if not filename or filename.strip() == "":
        raise ValidationError("Filename is empty.")

    # Reject hidden files before sanitization (original check)
    stripped = filename.strip()
    if stripped.startswith("."):
        raise ValidationError("Hidden filenames are not allowed.")

    safe = secure_filename(filename)
    if not safe:
        raise ValidationError(f"Filename '{filename}' cannot be safely stored.")

    if len(safe) > 255:
        raise ValidationError("Filename is too long (max 255 characters).")

    # Optionally enforce allowed extensions
    if cfg.ALLOWED_EXTENSIONS:
        ext = Path(safe).suffix.lower().lstrip(".")
        if ext not in cfg.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"File type '.{ext}' is not allowed. "
                f"Allowed: {', '.join(sorted(cfg.ALLOWED_EXTENSIONS))}"
            )

    return safe


def _sha256_of_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_hdfs_name(file_id: str, safe_filename: str) -> str:
    """
    Build a collision-resistant HDFS filename.
    Format: <uuid>_<safe_original_name>
    This avoids path-traversal and filename collisions.
    """
    return f"{file_id}_{safe_filename}"


# ─── Public service functions ────────────────────────────────────────────────────

def upload_file(file_storage, content_type: Optional[str] = None) -> dict:
    """
    Orchestrate file upload:
      1. Validate filename and size
      2. Save to temp location
      3. Upload to HDFS
      4. Record metadata in SQLite
      5. Clean up temp file
    Returns the metadata dict for the stored file.
    """
    # ── Validate filename ──────────────────────────────────────────────────────
    safe_name = _validate_filename(file_storage.filename)

    # ── Prepare temp directory ─────────────────────────────────────────────────
    cfg.UPLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    tmp_path = cfg.UPLOAD_TMP_DIR / f"{file_id}_{safe_name}"

    try:
        # ── Save to disk temporarily ───────────────────────────────────────────
        file_storage.save(str(tmp_path))

        size_bytes = tmp_path.stat().st_size

        # ── Validate size ──────────────────────────────────────────────────────
        max_bytes = cfg.MAX_UPLOAD_MB * 1024 * 1024
        if size_bytes > max_bytes:
            raise ValidationError(
                f"File size ({size_bytes / 1024 / 1024:.1f} MB) exceeds "
                f"the {cfg.MAX_UPLOAD_MB} MB limit."
            )

        if size_bytes == 0:
            raise ValidationError("Uploaded file is empty.")

        # ── Compute checksum ───────────────────────────────────────────────────
        sha256 = _sha256_of_file(tmp_path)

        # ── Upload to HDFS ─────────────────────────────────────────────────────
        hdfs_name = _make_hdfs_name(file_id, safe_name)
        try:
            hdfs_client.ensure_base_dir()
            hdfs_client.upload_file(tmp_path, hdfs_name)
        except HDFSConnectionError as exc:
            raise HDFSConnectionError(str(exc)) from exc
        except HDFSError as exc:
            raise HDFSError(f"HDFS upload failed: {exc}") from exc

        # ── Record metadata in SQLite ──────────────────────────────────────────
        uploaded_at = time.time()
        with _get_db() as conn:
            conn.execute(
                """
                INSERT INTO files (id, original_name, hdfs_name, size_bytes,
                                   content_type, sha256, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, safe_name, hdfs_name, size_bytes,
                 content_type, sha256, uploaded_at),
            )

        logger.info("File stored: id=%s original=%s hdfs=%s size=%d",
                    file_id, safe_name, hdfs_name, size_bytes)

        return {
            "id": file_id,
            "original_name": safe_name,
            "size_bytes": size_bytes,
            "content_type": content_type,
            "sha256": sha256,
            "uploaded_at": uploaded_at,
        }

    finally:
        # Always remove temp file
        if tmp_path.exists():
            tmp_path.unlink()


def list_files() -> list[dict]:
    """Return all non-deleted file records from SQLite metadata."""
    with _get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, original_name, hdfs_name, size_bytes, content_type,
                   sha256, uploaded_at
            FROM files
            WHERE deleted = 0
            ORDER BY uploaded_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_file(file_id: str) -> Optional[dict]:
    """Return metadata for a single file or None if not found/deleted."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE id = ? AND deleted = 0", (file_id,)
        ).fetchone()
    return dict(row) if row else None


def download_file(file_id: str) -> tuple[bytes, str, str]:
    """
    Retrieve file bytes from HDFS.
    Returns (data_bytes, original_filename, content_type).
    Raises KeyError if file_id is not found.
    Raises HDFSError on HDFS problems.
    """
    meta = get_file(file_id)
    if not meta:
        raise KeyError(f"File not found: {file_id}")

    data = hdfs_client.download_file(meta["hdfs_name"])
    ct = meta.get("content_type") or "application/octet-stream"
    return data, meta["original_name"], ct


def delete_file(file_id: str) -> dict:
    """
    Delete a file from HDFS and mark it deleted in SQLite.
    Returns the deleted file's metadata.
    Raises KeyError if file_id not found.
    """
    meta = get_file(file_id)
    if not meta:
        raise KeyError(f"File not found: {file_id}")

    # Delete from HDFS (don't fail if already absent)
    try:
        hdfs_client.delete_file(meta["hdfs_name"])
    except HDFSError as exc:
        logger.warning("HDFS delete error (marking deleted anyway): %s", exc)

    # Mark deleted in SQLite
    with _get_db() as conn:
        conn.execute(
            "UPDATE files SET deleted = 1 WHERE id = ?", (file_id,)
        )

    logger.info("File deleted: id=%s original=%s", file_id, meta["original_name"])
    return meta


def get_storage_stats() -> dict:
    """
    Return combined storage statistics from SQLite metadata + HDFS summary.
    """
    with _get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as file_count, SUM(size_bytes) as total_bytes "
            "FROM files WHERE deleted = 0"
        ).fetchone()

    file_count = row["file_count"] or 0
    total_bytes = row["total_bytes"] or 0

    hdfs_summary = {}
    try:
        hdfs_summary = hdfs_client.get_storage_summary()
    except HDFSError as exc:
        logger.warning("Could not fetch HDFS storage summary: %s", exc)

    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1024 / 1024, 2),
        "hdfs_summary": hdfs_summary,
    }


def check_hdfs_health() -> dict:
    """Return a health-check dict describing HDFS connectivity."""
    reachable = hdfs_client.ping()
    return {
        "hdfs_reachable": reachable,
        "webhdfs_url": hdfs_client.base_url,
        "hdfs_user": hdfs_client.user,
        "hdfs_base_path": hdfs_client.base_path,
    }
