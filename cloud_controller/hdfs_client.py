"""
HDFS Client — wraps WebHDFS REST API.

WebHDFS is the safest cross-version integration mechanism for Hadoop 3.x.
It requires no native Hadoop client on the Python side and works over HTTP.
All HDFS operations pass through this module; the rest of the application
never touches HDFS directly.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import requests
from requests.exceptions import ConnectionError, Timeout, RequestException

from config import active_config as cfg

logger = logging.getLogger(__name__)

# WebHDFS operation constants
OP_MKDIRS = "MKDIRS"
OP_CREATE = "CREATE"
OP_OPEN = "OPEN"
OP_DELETE = "DELETE"
OP_LISTSTATUS = "LISTSTATUS"
OP_GETFILESTATUS = "GETFILESTATUS"
OP_GETCONTENTSUMMARY = "GETCONTENTSUMMARY"

# Timeouts (seconds)
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 300   # large file downloads can take time


class HDFSError(Exception):
    """Raised when an HDFS operation fails."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class HDFSConnectionError(HDFSError):
    """Raised when the HDFS cluster is unreachable."""


class HDFSClient:
    """
    Thin wrapper around the WebHDFS v1 REST API.

    WebHDFS reference: https://hadoop.apache.org/docs/stable/hadoop-project-dist/
                       hadoop-hdfs/WebHDFS.html
    """

    def __init__(self):
        self.base_url = cfg.WEBHDFS_URL
        self.user = cfg.HDFS_USER
        self.base_path = cfg.HDFS_BASE_PATH
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "CampusCloud/1.0"})

    # ─── Internal helpers ───────────────────────────────────────────────────────

    def _url(self, hdfs_path: str) -> str:
        """Build the full WebHDFS URL for a given HDFS path."""
        return f"{self.base_url}{hdfs_path}"

    def _params(self, op: str, **kwargs) -> dict:
        """Build query-parameter dict including user.name."""
        params = {"op": op, "user.name": self.user}
        params.update(kwargs)
        return params

    def _request(self, method: str, hdfs_path: str, op: str, **kwargs):
        """Execute a WebHDFS request, translating exceptions to HDFSError."""
        url = self._url(hdfs_path)
        params = self._params(op)
        # Merge caller-supplied params
        if "params" in kwargs:
            params.update(kwargs.pop("params"))
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                **kwargs,
            )
            return response
        except ConnectionError as exc:
            raise HDFSConnectionError(
                f"Cannot reach HDFS at {self.base_url}. "
                "Ensure NameNode is running and WebHDFS is enabled."
            ) from exc
        except Timeout as exc:
            raise HDFSError(f"HDFS request timed out: {exc}") from exc
        except RequestException as exc:
            raise HDFSError(f"HDFS request failed: {exc}") from exc

    # ─── Health / Connectivity ──────────────────────────────────────────────────

    def ping(self) -> bool:
        """Return True if WebHDFS is reachable, False otherwise."""
        try:
            resp = self._request("GET", "/", OP_LISTSTATUS)
            return resp.status_code in (200, 403)   # 403 = auth issue, but HDFS is up
        except HDFSError:
            return False

    # ─── Directory management ───────────────────────────────────────────────────

    def ensure_base_dir(self):
        """Create the base application directory in HDFS if it doesn't exist."""
        resp = self._request("PUT", self.base_path, OP_MKDIRS)
        if resp.status_code not in (200, 201):
            raise HDFSError(
                f"Failed to create HDFS directory {self.base_path}: "
                f"HTTP {resp.status_code} — {resp.text}"
            )
        logger.info("HDFS base directory ensured: %s", self.base_path)

    # ─── File upload ────────────────────────────────────────────────────────────

    def upload_file(self, local_path: Path, hdfs_filename: str) -> str:
        """
        Upload a local file to HDFS.

        WebHDFS two-step CREATE:
          1. PUT with op=CREATE → 307 redirect to DataNode URL
          2. PUT file data to DataNode URL

        Returns the HDFS path of the stored file.
        """
        hdfs_path = f"{self.base_path}/{hdfs_filename}"

        # Step 1 — initiate create, do NOT follow redirect automatically
        resp = self._request(
            "PUT",
            hdfs_path,
            OP_CREATE,
            allow_redirects=False,
            params={"overwrite": "true"},
        )

        if resp.status_code != 307:
            raise HDFSError(
                f"HDFS CREATE initiation failed (expected 307, got {resp.status_code}): "
                f"{resp.text}",
                status_code=resp.status_code,
            )

        datanode_url = resp.headers.get("Location")
        if not datanode_url:
            raise HDFSError("HDFS did not return a DataNode redirect URL.")

        # Step 2 — stream file data to DataNode
        file_size = local_path.stat().st_size
        with local_path.open("rb") as fh:
            upload_resp = self.session.put(
                datanode_url,
                data=fh,
                headers={"Content-Type": "application/octet-stream"},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )

        if upload_resp.status_code not in (200, 201):
            raise HDFSError(
                f"HDFS file upload failed: HTTP {upload_resp.status_code} — "
                f"{upload_resp.text}",
                status_code=upload_resp.status_code,
            )

        logger.info("Uploaded %s to HDFS path %s (%d bytes)", local_path.name, hdfs_path, file_size)
        return hdfs_path

    # ─── File download ──────────────────────────────────────────────────────────

    def download_file(self, hdfs_filename: str) -> bytes:
        """
        Download a file from HDFS and return its raw bytes.
        For large files, use download_file_stream instead.
        """
        hdfs_path = f"{self.base_path}/{hdfs_filename}"
        resp = self._request("GET", hdfs_path, OP_OPEN, allow_redirects=True)

        if resp.status_code == 404:
            raise HDFSError(f"File not found in HDFS: {hdfs_path}", status_code=404)
        if resp.status_code != 200:
            raise HDFSError(
                f"HDFS download failed: HTTP {resp.status_code} — {resp.text}",
                status_code=resp.status_code,
            )
        return resp.content

    def download_file_stream(self, hdfs_filename: str):
        """
        Return a streaming response object for a file in HDFS.
        Caller is responsible for reading and closing the stream.
        """
        hdfs_path = f"{self.base_path}/{hdfs_filename}"
        resp = self._request(
            "GET", hdfs_path, OP_OPEN, allow_redirects=True, stream=True
        )

        if resp.status_code == 404:
            raise HDFSError(f"File not found in HDFS: {hdfs_path}", status_code=404)
        if resp.status_code != 200:
            raise HDFSError(
                f"HDFS download failed: HTTP {resp.status_code} — {resp.text}",
                status_code=resp.status_code,
            )
        return resp

    # ─── File deletion ──────────────────────────────────────────────────────────

    def delete_file(self, hdfs_filename: str) -> bool:
        """
        Delete a file from HDFS.
        Returns True if deleted, False if it was already absent.
        """
        hdfs_path = f"{self.base_path}/{hdfs_filename}"
        resp = self._request("DELETE", hdfs_path, OP_DELETE, params={"recursive": "false"})

        if resp.status_code == 200:
            data = resp.json()
            deleted = data.get("boolean", False)
            logger.info("HDFS delete %s → %s", hdfs_path, deleted)
            return deleted
        if resp.status_code == 404:
            logger.warning("HDFS delete: file not found %s", hdfs_path)
            return False

        raise HDFSError(
            f"HDFS delete failed: HTTP {resp.status_code} — {resp.text}",
            status_code=resp.status_code,
        )

    # ─── File listing ───────────────────────────────────────────────────────────

    def list_files(self) -> list[dict]:
        """
        List files in the application's HDFS directory.
        Returns a list of dicts with 'name', 'size', 'modificationTime'.
        """
        resp = self._request("GET", self.base_path, OP_LISTSTATUS)

        if resp.status_code == 404:
            logger.warning("HDFS base path does not exist: %s", self.base_path)
            return []
        if resp.status_code != 200:
            raise HDFSError(
                f"HDFS list failed: HTTP {resp.status_code} — {resp.text}",
                status_code=resp.status_code,
            )

        statuses = resp.json().get("FileStatuses", {}).get("FileStatus", [])
        return [
            {
                "name": s["pathSuffix"],
                "size": s["length"],
                "modification_time": s["modificationTime"],
                "type": s["type"],
            }
            for s in statuses
            if s["type"] == "FILE"
        ]

    # ─── Storage summary ────────────────────────────────────────────────────────

    def get_storage_summary(self) -> dict:
        """Return content summary for the application's HDFS directory."""
        resp = self._request("GET", self.base_path, OP_GETCONTENTSUMMARY)

        if resp.status_code == 404:
            return {"length": 0, "fileCount": 0}
        if resp.status_code != 200:
            raise HDFSError(
                f"HDFS content summary failed: HTTP {resp.status_code} — {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json().get("ContentSummary", {})

    def get_file_status(self, hdfs_filename: str) -> Optional[dict]:
        """Return file status dict or None if not found."""
        hdfs_path = f"{self.base_path}/{hdfs_filename}"
        resp = self._request("GET", hdfs_path, OP_GETFILESTATUS)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise HDFSError(
                f"HDFS getfilestatus failed: HTTP {resp.status_code} — {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json().get("FileStatus")


# Module-level singleton
hdfs_client = HDFSClient()
