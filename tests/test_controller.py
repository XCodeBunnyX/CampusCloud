"""
CampusCloud - test_controller.py
Integration tests for the Cloud Controller and HDFS client.

Unit tests mock the HDFS layer.
Integration tests (marked @pytest.mark.integration) require a live HDFS instance.
Run unit tests only: pytest tests/test_controller.py -m "not integration"
Run integration tests: pytest tests/test_controller.py -m integration
"""

import io
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import responses as resp_lib

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL  = "http://localhost:9870/webhdfs/v1"
BASE_PATH = "/campuscloud/files"


def _make_isolated_client():
    """
    Create a fresh HDFSClient with known URLs, bypassing module-level
    singleton issues when tests run in sequence.
    """
    from cloud_controller.hdfs_client import HDFSClient
    client = HDFSClient()
    # Override instance attrs directly so mock URLs match exactly
    client.base_url  = BASE_URL
    client.user      = "testuser"
    client.base_path = BASE_PATH
    return client


# ============================================================================
# HDFSClient Unit Tests
# ============================================================================

class TestHDFSClientUnit:
    """Test HDFSClient methods by mocking HTTP with the responses library."""

    def setup_method(self):
        self.client = _make_isolated_client()

    @resp_lib.activate
    def test_ping_returns_true_on_200(self):
        resp_lib.add(resp_lib.GET, f"{BASE_URL}/", status=200, json={"FileStatuses": {}})
        assert self.client.ping() is True

    @resp_lib.activate
    def test_ping_returns_false_on_connection_error(self):
        # No registered URL -> responses raises ConnectionError -> ping returns False
        result = self.client.ping()
        assert result is False

    @resp_lib.activate
    def test_upload_file_two_step(self, tmp_path):
        """Verify the two-step WebHDFS PUT CREATE protocol."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"hello world")

        hdfs_path    = f"{BASE_PATH}/uuid_test.txt"
        datanode_url = f"http://localhost:9864/webhdfs/v1{BASE_PATH}/uuid_test.txt?op=CREATE"

        # Step 1: NameNode returns 307 redirect
        resp_lib.add(
            resp_lib.PUT,
            f"{BASE_URL}{hdfs_path}",
            status=307,
            headers={"Location": datanode_url},
        )
        # Step 2: DataNode accepts the data
        resp_lib.add(resp_lib.PUT, datanode_url, status=201)

        result = self.client.upload_file(test_file, "uuid_test.txt")
        assert result == hdfs_path

    @resp_lib.activate
    def test_download_file(self):
        hdfs_path = f"{BASE_PATH}/uuid_testfile.txt"
        resp_lib.add(
            resp_lib.GET,
            f"{BASE_URL}{hdfs_path}",
            status=200,
            body=b"file contents",
        )
        data = self.client.download_file("uuid_testfile.txt")
        assert data == b"file contents"

    @resp_lib.activate
    def test_download_file_not_found(self):
        from cloud_controller.hdfs_client import HDFSError
        hdfs_path = f"{BASE_PATH}/missing.txt"
        resp_lib.add(
            resp_lib.GET,
            f"{BASE_URL}{hdfs_path}",
            status=404,
            json={"RemoteException": {"message": "not found"}},
        )
        with pytest.raises(HDFSError) as exc:
            self.client.download_file("missing.txt")
        assert exc.value.status_code == 404

    @resp_lib.activate
    def test_delete_file_returns_true(self):
        hdfs_path = f"{BASE_PATH}/uuid_del.txt"
        resp_lib.add(
            resp_lib.DELETE,
            f"{BASE_URL}{hdfs_path}",
            status=200,
            json={"boolean": True},
        )
        result = self.client.delete_file("uuid_del.txt")
        assert result is True

    @resp_lib.activate
    def test_delete_file_not_found_returns_false(self):
        hdfs_path = f"{BASE_PATH}/ghost.txt"
        resp_lib.add(
            resp_lib.DELETE,
            f"{BASE_URL}{hdfs_path}",
            status=404,
        )
        result = self.client.delete_file("ghost.txt")
        assert result is False

    @resp_lib.activate
    def test_list_files_returns_only_files_not_dirs(self):
        resp_lib.add(
            resp_lib.GET,
            f"{BASE_URL}{BASE_PATH}",
            status=200,
            json={
                "FileStatuses": {
                    "FileStatus": [
                        {"pathSuffix": "file1.txt", "length": 100, "modificationTime": 0, "type": "FILE"},
                        {"pathSuffix": "subdir",    "length": 0,   "modificationTime": 0, "type": "DIRECTORY"},
                    ]
                }
            },
        )
        files = self.client.list_files()
        assert len(files) == 1  # DIRECTORY should be excluded
        assert files[0]["name"] == "file1.txt"
        assert files[0]["size"] == 100

    @resp_lib.activate
    def test_ensure_base_dir_success(self):
        resp_lib.add(
            resp_lib.PUT,
            f"{BASE_URL}{BASE_PATH}",
            status=200,
            json={"boolean": True},
        )
        # Should not raise
        self.client.ensure_base_dir()

    @resp_lib.activate
    def test_upload_raises_hdfs_error_on_non_307(self, tmp_path):
        from cloud_controller.hdfs_client import HDFSError
        test_file = tmp_path / "fail.txt"
        test_file.write_bytes(b"data")

        resp_lib.add(
            resp_lib.PUT,
            f"{BASE_URL}{BASE_PATH}/uuid_fail.txt",
            status=500,
            json={"RemoteException": {"message": "Internal Server Error"}},
        )
        with pytest.raises(HDFSError):
            self.client.upload_file(test_file, "uuid_fail.txt")

    @resp_lib.activate
    def test_list_returns_empty_on_404(self):
        """If the base dir doesn't exist yet, listing returns []."""
        resp_lib.add(
            resp_lib.GET,
            f"{BASE_URL}{BASE_PATH}",
            status=404,
        )
        files = self.client.list_files()
        assert files == []


# ============================================================================
# Services Unit Tests
# ============================================================================

class TestServicesUnit:

    def setup_method(self, method):
        self._tmp = tempfile.mkdtemp()
        os.environ["DB_PATH"]        = os.path.join(self._tmp, "test.db")
        os.environ["UPLOAD_TMP_DIR"] = os.path.join(self._tmp, "uploads")
        os.environ["MAX_UPLOAD_MB"]  = "10"

        import importlib
        import config as cfg_mod
        importlib.reload(cfg_mod)
        import cloud_controller.services as svc
        importlib.reload(svc)
        self.services = svc
        svc.init_db()

    def test_validate_filename_rejects_empty(self):
        from cloud_controller.services import ValidationError, _validate_filename
        with pytest.raises(ValidationError, match="empty"):
            _validate_filename("")

    def test_validate_filename_rejects_hidden(self):
        from cloud_controller.services import ValidationError, _validate_filename
        with pytest.raises(ValidationError, match="Hidden"):
            _validate_filename(".hidden_file.txt")

    def test_validate_filename_rejects_leading_dot(self):
        from cloud_controller.services import ValidationError, _validate_filename
        with pytest.raises(ValidationError):
            _validate_filename(".bashrc")

    def test_validate_filename_rejects_long_name(self):
        from cloud_controller.services import ValidationError, _validate_filename
        with pytest.raises(ValidationError, match="long"):
            _validate_filename("a" * 300 + ".txt")

    def test_validate_filename_accepts_normal(self):
        from cloud_controller.services import _validate_filename
        assert _validate_filename("my_file-2024.pdf") == "my_file-2024.pdf"

    def test_validate_filename_accepts_spaces_sanitized(self):
        from cloud_controller.services import _validate_filename
        result = _validate_filename("my document.txt")
        # werkzeug converts spaces to underscores
        assert "document" in result

    def test_sha256_computation(self):
        import hashlib
        from cloud_controller.services import _sha256_of_file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"unit test content")
            path = Path(f.name)
        try:
            expected = hashlib.sha256(b"unit test content").hexdigest()
            assert _sha256_of_file(path) == expected
        finally:
            path.unlink(missing_ok=True)

    def test_list_files_empty_initially(self):
        assert self.services.list_files() == []

    def test_get_file_returns_none_for_unknown_id(self):
        assert self.services.get_file(str(uuid.uuid4())) is None

    def test_get_storage_stats_empty_db(self):
        with patch.object(self.services.hdfs_client, "get_storage_summary", return_value={}):
            stats = self.services.get_storage_stats()
        assert stats["file_count"] == 0
        assert stats["total_bytes"] == 0
        assert stats["total_mb"] == 0

    def _mock_upload(self, filename: str = "unit_test.txt", content: bytes = b"unit test data"):
        with patch.object(self.services.hdfs_client, "ensure_base_dir"), \
             patch.object(self.services.hdfs_client, "upload_file", return_value="/campuscloud/files/x"):
            mock_file = MagicMock()
            mock_file.filename = filename
            mock_file.save = lambda path: Path(path).write_bytes(content)
            return self.services.upload_file(mock_file, "text/plain")

    def test_upload_returns_correct_metadata(self):
        meta = self._mock_upload("unit_test.txt", b"unit test data")
        assert meta["original_name"] == "unit_test.txt"
        assert meta["size_bytes"] == 14
        assert len(meta["sha256"]) == 64  # hex SHA-256

    def test_upload_appears_in_listing(self):
        meta = self._mock_upload()
        files = self.services.list_files()
        assert len(files) == 1
        assert files[0]["id"] == meta["id"]

    def test_upload_rejects_empty_file(self):
        from cloud_controller.services import ValidationError
        with pytest.raises(ValidationError, match="empty"):
            self._mock_upload("empty.txt", b"")

    def test_delete_removes_from_listing(self):
        meta = self._mock_upload()
        with patch.object(self.services.hdfs_client, "delete_file", return_value=True):
            self.services.delete_file(meta["id"])
        assert self.services.list_files() == []

    def test_delete_marks_record_deleted(self):
        meta = self._mock_upload()
        with patch.object(self.services.hdfs_client, "delete_file", return_value=True):
            self.services.delete_file(meta["id"])
        assert self.services.get_file(meta["id"]) is None

    def test_delete_nonexistent_raises_key_error(self):
        with pytest.raises(KeyError):
            self.services.delete_file(str(uuid.uuid4()))

    def test_check_hdfs_health_offline(self):
        with patch.object(self.services.hdfs_client, "ping", return_value=False):
            health = self.services.check_hdfs_health()
        assert health["hdfs_reachable"] is False

    def test_check_hdfs_health_online(self):
        with patch.object(self.services.hdfs_client, "ping", return_value=True):
            health = self.services.check_hdfs_health()
        assert health["hdfs_reachable"] is True


# ============================================================================
# Integration Tests (require live HDFS)
# ============================================================================

@pytest.mark.integration
class TestHDFSIntegration:
    """
    These tests require a running HDFS instance.
    Run with: pytest tests/test_controller.py -m integration

    Integration test procedure:
    1. Upload a test file through the HDFS client
    2. Verify the file exists in HDFS using the listing
    3. Download it and compare contents with original
    4. Delete the test file
    5. Verify the HDFS entry is removed
    """

    CONTENT = b"CampusCloud HDFS Integration Test - " + str(time.time()).encode()

    def setup_method(self):
        import importlib
        import config as cfg_mod
        importlib.reload(cfg_mod)
        from cloud_controller.hdfs_client import HDFSClient
        self.hdfs = HDFSClient()
        if not self.hdfs.ping():
            pytest.skip("HDFS is not reachable. Start HDFS with ./scripts/start.sh")

    def test_step1_hdfs_is_reachable(self):
        """Step 1: Verify HDFS connectivity."""
        assert self.hdfs.ping(), "HDFS WebHDFS must be reachable"

    def test_step2_ensure_base_dir(self):
        """Step 2: Ensure the base directory exists in HDFS."""
        self.hdfs.ensure_base_dir()  # Should not raise

    def test_step3_upload_and_verify_in_listing(self, tmp_path):
        """Step 3: Upload a file and verify it appears in HDFS listing."""
        test_name = f"integration_{uuid.uuid4()}.txt"
        test_file = tmp_path / test_name
        test_file.write_bytes(self.CONTENT)

        self.hdfs.ensure_base_dir()
        self.hdfs.upload_file(test_file, test_name)

        files = self.hdfs.list_files()
        names = [f["name"] for f in files]
        assert test_name in names, f"Uploaded {test_name} not found in HDFS listing. Found: {names}"
        TestHDFSIntegration._test_filename = test_name

    def test_step4_download_and_compare(self):
        """Step 4: Download the file and verify byte-exact match."""
        if not hasattr(TestHDFSIntegration, "_test_filename"):
            pytest.skip("Depends on test_step3")
        data = self.hdfs.download_file(TestHDFSIntegration._test_filename)
        assert data == self.CONTENT, "Downloaded bytes do not match original"

    def test_step5_delete_and_verify_gone(self):
        """Step 5: Delete and confirm removal from HDFS listing."""
        if not hasattr(TestHDFSIntegration, "_test_filename"):
            pytest.skip("Depends on test_step3")
        result = self.hdfs.delete_file(TestHDFSIntegration._test_filename)
        assert result is True

        files = self.hdfs.list_files()
        names = [f["name"] for f in files]
        assert TestHDFSIntegration._test_filename not in names, \
            "Deleted file still appears in HDFS listing"
