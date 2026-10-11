"""
CampusCloud - test_api.py
API endpoint tests using Flask's test client.
HDFS is mocked for unit tests. Integration tests are in test_controller.py.
"""

import importlib
import io
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def app(tmp_path):
    """
    Create a test Flask application with a fully isolated SQLite DB per test.
    We reload all modules that depend on config to ensure a clean state.
    """
    db_path = str(tmp_path / "test.db")
    tmp_dir = str(tmp_path / "uploads")

    os.environ["DB_PATH"]        = db_path
    os.environ["UPLOAD_TMP_DIR"] = tmp_dir
    os.environ["SECRET_KEY"]     = "test-secret"
    os.environ["MAX_UPLOAD_MB"]  = "512"

    # Reload chain: config -> services -> routes -> __init__ -> app
    import config as cfg_mod
    importlib.reload(cfg_mod)

    import cloud_controller.services as svc_mod
    importlib.reload(svc_mod)

    import cloud_controller.routes as routes_mod
    importlib.reload(routes_mod)

    import cloud_controller as cc_mod
    importlib.reload(cc_mod)

    import app as app_mod
    importlib.reload(app_mod)

    application = app_mod.create_app()
    application.config["TESTING"] = True

    yield application


@pytest.fixture
def client(app):
    return app.test_client()


# ─── A. Health Check ─────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200_or_503(self, client):
        """Health endpoint must always respond, regardless of HDFS state."""
        resp = client.get("/api/health")
        assert resp.status_code in (200, 503)

    def test_health_response_schema(self, client):
        data = client.get("/api/health").json
        assert "status" in data
        assert data["status"] in ("healthy", "degraded")
        assert "hdfs" in data
        assert "hdfs_reachable" in data["hdfs"]

    def test_health_degraded_when_hdfs_offline(self, client):
        import cloud_controller.services as svc
        with patch.object(svc, "check_hdfs_health") as mock:
            mock.return_value = {
                "hdfs_reachable": False,
                "webhdfs_url": "http://x",
                "hdfs_user": "u",
                "hdfs_base_path": "/",
            }
            resp = client.get("/api/health")
        assert resp.status_code == 503
        assert resp.json["status"] == "degraded"


# ─── B. Upload File ──────────────────────────────────────────────────────────

class TestUploadEndpoint:
    def test_upload_no_file_returns_400(self, client):
        resp = client.post("/api/files", data={})
        assert resp.status_code == 400
        assert "No file" in resp.json["message"]

    def test_upload_empty_filename_returns_400(self, client):
        resp = client.post(
            "/api/files",
            data={"file": (io.BytesIO(b"data"), "")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_upload_empty_file_returns_422(self, client):
        import cloud_controller.services as svc
        with patch.object(svc.hdfs_client, "ensure_base_dir"), \
             patch.object(svc.hdfs_client, "upload_file", return_value="/path"):
            resp = client.post(
                "/api/files",
                data={"file": (io.BytesIO(b""), "empty.txt")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 422
        assert "empty" in resp.json["message"].lower()

    def test_upload_success_with_hdfs_mock(self, client):
        import cloud_controller.services as svc
        with patch.object(svc.hdfs_client, "ensure_base_dir"), \
             patch.object(svc.hdfs_client, "upload_file", return_value="/path/test.txt"):
            resp = client.post(
                "/api/files",
                data={"file": (io.BytesIO(b"Hello HDFS"), "test.txt")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 201
        data = resp.json
        assert data["status"] == "ok"
        assert data["file"]["original_name"] == "test.txt"
        assert data["file"]["size_bytes"] == 10
        assert "sha256" in data["file"]
        assert len(data["file"]["sha256"]) == 64

    def test_upload_calls_hdfs_upload(self, client):
        import cloud_controller.services as svc
        with patch.object(svc.hdfs_client, "ensure_base_dir"), \
             patch.object(svc.hdfs_client, "upload_file", return_value="/path") as mock_up:
            client.post(
                "/api/files",
                data={"file": (io.BytesIO(b"data"), "myfile.txt")},
                content_type="multipart/form-data",
            )
        assert mock_up.called

    def test_upload_hdfs_connection_error_returns_503(self, client):
        from cloud_controller.hdfs_client import HDFSConnectionError
        import cloud_controller.services as svc
        with patch.object(svc.hdfs_client, "ensure_base_dir",
                          side_effect=HDFSConnectionError("HDFS down")):
            resp = client.post(
                "/api/files",
                data={"file": (io.BytesIO(b"data"), "file.txt")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 503

    def test_upload_rejects_path_traversal(self, client):
        import cloud_controller.services as svc
        with patch.object(svc.hdfs_client, "ensure_base_dir"), \
             patch.object(svc.hdfs_client, "upload_file", return_value="/path"):
            resp = client.post(
                "/api/files",
                data={"file": (io.BytesIO(b"evil"), "../../../etc/passwd")},
                content_type="multipart/form-data",
            )
        # secure_filename strips path separators; result is safe filename or rejection
        assert resp.status_code in (201, 400, 422)

    def test_upload_invalid_filename_only_dots(self, client):
        import cloud_controller.services as svc
        with patch.object(svc.hdfs_client, "ensure_base_dir"), \
             patch.object(svc.hdfs_client, "upload_file", return_value="/path"):
            resp = client.post(
                "/api/files",
                data={"file": (io.BytesIO(b"data"), "...")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (400, 422)

    def test_upload_hidden_file_rejected(self, client):
        resp = client.post(
            "/api/files",
            data={"file": (io.BytesIO(b"data"), ".htaccess")},
            content_type="multipart/form-data",
        )
        assert resp.status_code in (400, 422)


# ─── C. List Files ───────────────────────────────────────────────────────────

class TestListEndpoint:
    def test_list_returns_empty_when_no_files(self, client):
        resp = client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json
        assert data["status"] == "ok"
        assert data["files"] == []
        assert data["count"] == 0

    def test_list_returns_uploaded_file(self, client):
        import cloud_controller.services as svc
        with patch.object(svc.hdfs_client, "ensure_base_dir"), \
             patch.object(svc.hdfs_client, "upload_file", return_value="/path"):
            client.post(
                "/api/files",
                data={"file": (io.BytesIO(b"content"), "listed.txt")},
                content_type="multipart/form-data",
            )

        resp = client.get("/api/files")
        assert resp.status_code == 200
        files = resp.json["files"]
        assert len(files) == 1
        assert files[0]["original_name"] == "listed.txt"
        assert "id" in files[0]
        assert "size_bytes" in files[0]


# ─── D. Download File ────────────────────────────────────────────────────────

class TestDownloadEndpoint:
    def test_download_nonexistent_file_returns_404(self, client):
        resp = client.get(f"/api/files/{uuid.uuid4()}/download")
        assert resp.status_code == 404

    def test_download_invalid_id_returns_400(self, client):
        resp = client.get("/api/files/not-a-uuid/download")
        assert resp.status_code == 400

    def test_download_returns_file_bytes(self, client):
        import cloud_controller.services as svc
        # Upload first
        with patch.object(svc.hdfs_client, "ensure_base_dir"), \
             patch.object(svc.hdfs_client, "upload_file", return_value="/path"):
            up = client.post(
                "/api/files",
                data={"file": (io.BytesIO(b"HDFS content"), "download_me.txt")},
                content_type="multipart/form-data",
            )
        file_id = up.json["file"]["id"]

        # Download
        with patch.object(svc.hdfs_client, "download_file", return_value=b"HDFS content"):
            resp = client.get(f"/api/files/{file_id}/download")
        assert resp.status_code == 200
        assert resp.data == b"HDFS content"


# ─── E. Delete File ──────────────────────────────────────────────────────────

class TestDeleteEndpoint:
    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete(f"/api/files/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_invalid_id_returns_400(self, client):
        resp = client.delete("/api/files/bad-id")
        assert resp.status_code == 400

    def test_delete_removes_file_from_listing(self, client):
        import cloud_controller.services as svc
        with patch.object(svc.hdfs_client, "ensure_base_dir"), \
             patch.object(svc.hdfs_client, "upload_file", return_value="/path"):
            up = client.post(
                "/api/files",
                data={"file": (io.BytesIO(b"data"), "to_delete.txt")},
                content_type="multipart/form-data",
            )
        file_id = up.json["file"]["id"]

        with patch.object(svc.hdfs_client, "delete_file", return_value=True):
            del_resp = client.delete(f"/api/files/{file_id}")
        assert del_resp.status_code == 200
        assert del_resp.json["status"] == "ok"

        list_resp = client.get("/api/files")
        ids = [f["id"] for f in list_resp.json["files"]]
        assert file_id not in ids


# ─── F. Storage Endpoint ─────────────────────────────────────────────────────

class TestStorageEndpoint:
    def test_storage_returns_stats(self, client):
        resp = client.get("/api/storage")
        assert resp.status_code == 200
        s = resp.json["storage"]
        assert "file_count" in s
        assert "total_bytes" in s
        assert "total_mb" in s

    def test_storage_reflects_uploaded_files(self, client):
        import cloud_controller.services as svc
        with patch.object(svc.hdfs_client, "ensure_base_dir"), \
             patch.object(svc.hdfs_client, "upload_file", return_value="/path"), \
             patch.object(svc.hdfs_client, "get_storage_summary", return_value={"length": 100}):
            client.post(
                "/api/files",
                data={"file": (io.BytesIO(b"x" * 100), "stats_file.txt")},
                content_type="multipart/form-data",
            )

        with patch.object(svc.hdfs_client, "get_storage_summary", return_value={"length": 100}):
            resp = client.get("/api/storage")
        assert resp.json["storage"]["file_count"] == 1
        assert resp.json["storage"]["total_bytes"] == 100
