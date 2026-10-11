"""
Cloud Controller Routes — Flask Blueprint.

Every route delegates to cloud_controller.services for business logic.
This module only handles HTTP concerns: parsing requests, formatting responses.
"""

import logging
import time

from flask import Blueprint, jsonify, request, send_file, current_app
import io

from cloud_controller import services
from cloud_controller.hdfs_client import HDFSConnectionError, HDFSError
from cloud_controller.services import ValidationError

logger = logging.getLogger(__name__)

bp = Blueprint("api", __name__, url_prefix="/api")


def _ok(data: dict, status: int = 200):
    return jsonify({"status": "ok", **data}), status


def _err(message: str, status: int = 400, details: str = ""):
    payload = {"status": "error", "message": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status


# ─── A. Health Check ─────────────────────────────────────────────────────────

@bp.route("/health", methods=["GET"])
def health_check():
    """GET /api/health — application and HDFS health status."""
    hdfs_health = services.check_hdfs_health()
    overall = "healthy" if hdfs_health["hdfs_reachable"] else "degraded"

    return jsonify({
        "status": overall,
        "timestamp": time.time(),
        "application": "CampusCloud",
        "version": "1.0.0",
        "hdfs": hdfs_health,
    }), 200 if overall == "healthy" else 503


# ─── B. Upload File ──────────────────────────────────────────────────────────

@bp.route("/files", methods=["POST"])
def upload_file():
    """POST /api/files — accept a multipart upload and store in HDFS."""
    if "file" not in request.files:
        return _err("No file part in the request. Use field name 'file'.")

    file = request.files["file"]
    if not file or file.filename == "":
        return _err("No file selected.")

    content_type = file.content_type or "application/octet-stream"

    try:
        meta = services.upload_file(file, content_type)
        return _ok({"message": "File uploaded successfully.", "file": meta}, status=201)

    except ValidationError as exc:
        logger.warning("Validation error: %s", exc)
        return _err(str(exc), status=422)

    except HDFSConnectionError as exc:
        logger.error("HDFS connection error during upload: %s", exc)
        return _err(
            "HDFS is not reachable. Ensure Hadoop services are running.",
            status=503,
            details=str(exc),
        )

    except HDFSError as exc:
        logger.error("HDFS error during upload: %s", exc)
        return _err("HDFS storage operation failed.", status=500, details=str(exc))

    except Exception as exc:
        logger.exception("Unexpected error during upload: %s", exc)
        return _err("An unexpected server error occurred.", status=500)


# ─── C. List Files ───────────────────────────────────────────────────────────

@bp.route("/files", methods=["GET"])
def list_files():
    """GET /api/files — list all stored files with metadata."""
    try:
        files = services.list_files()
        return _ok({"files": files, "count": len(files)})
    except Exception as exc:
        logger.exception("Error listing files: %s", exc)
        return _err("Failed to retrieve file list.", status=500)


# ─── D. Download File ────────────────────────────────────────────────────────

@bp.route("/files/<file_id>/download", methods=["GET"])
def download_file(file_id: str):
    """GET /api/files/<file_id>/download — retrieve file from HDFS."""
    # Basic UUID validation
    if not _valid_id(file_id):
        return _err("Invalid file ID.", status=400)

    try:
        data, filename, content_type = services.download_file(file_id)
        return send_file(
            io.BytesIO(data),
            download_name=filename,
            mimetype=content_type,
            as_attachment=True,
        )

    except KeyError:
        return _err("File not found.", status=404)

    except HDFSConnectionError as exc:
        return _err(
            "HDFS is not reachable.", status=503, details=str(exc)
        )

    except HDFSError as exc:
        return _err("HDFS retrieval failed.", status=500, details=str(exc))

    except Exception as exc:
        logger.exception("Unexpected error during download: %s", exc)
        return _err("An unexpected server error occurred.", status=500)


# ─── E. Delete File ──────────────────────────────────────────────────────────

@bp.route("/files/<file_id>", methods=["DELETE"])
def delete_file(file_id: str):
    """DELETE /api/files/<file_id> — delete from HDFS and metadata store."""
    if not _valid_id(file_id):
        return _err("Invalid file ID.", status=400)

    try:
        meta = services.delete_file(file_id)
        return _ok({"message": "File deleted.", "file": {"id": meta["id"], "name": meta["original_name"]}})

    except KeyError:
        return _err("File not found.", status=404)

    except HDFSConnectionError as exc:
        return _err("HDFS is not reachable.", status=503, details=str(exc))

    except HDFSError as exc:
        return _err("HDFS delete failed.", status=500, details=str(exc))

    except Exception as exc:
        logger.exception("Unexpected error during delete: %s", exc)
        return _err("An unexpected server error occurred.", status=500)


# ─── F. Storage Information ──────────────────────────────────────────────────

@bp.route("/storage", methods=["GET"])
def storage_info():
    """GET /api/storage — storage statistics from HDFS and metadata DB."""
    try:
        stats = services.get_storage_stats()
        return _ok({"storage": stats})
    except Exception as exc:
        logger.exception("Error fetching storage info: %s", exc)
        return _err("Failed to retrieve storage information.", status=500)


# ─── Helpers ─────────────────────────────────────────────────────────────────

import re as _re
_UUID_RE = _re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    _re.IGNORECASE,
)


def _valid_id(file_id: str) -> bool:
    return bool(_UUID_RE.match(file_id))
