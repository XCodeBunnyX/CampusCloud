# CampusCloud ☁️

**A LAN-Based Distributed Cloud Storage System (SaaS) Using Apache Hadoop HDFS & Custom Python Cloud Controller**

> **Academic Assignment Requirement:**  
> *"Setup your own Cloud for Software as a Service (SaaS) over the existing LAN in your laboratory. Write your own code for Cloud Controller using Open Source Technologies to implement with HDFS."*

---

## 📌 1. Project Overview

**CampusCloud** is an educational, production-grade Cloud Storage (SaaS) platform built for campus laboratory environments. It provides users across a Local Area Network (LAN) with a centralized, web-based interface to upload, download, list, inspect, and delete files. 

Unlike naive toy implementations that store uploaded files in a local folder, CampusCloud features a **custom Cloud Controller written in Python** that interfaces directly with **Apache Hadoop Distributed File System (HDFS)** using the **WebHDFS REST API**. Every uploaded file is chunked, hashed (SHA-256), and physically stored as distributed blocks in HDFS.

### Key Highlights
- **Genuine HDFS Backend:** Data blocks are managed by HDFS NameNode and DataNode daemons.
- **Custom Cloud Controller:** Clean modular Python architecture handling validation, hashing, streaming transfers, and transactional metadata.
- **Zero-Dependency Web Client:** Native WebHDFS REST integration requiring no heavy Java client libraries on the Python host.
- **LAN-Ready:** Configured to bind on `0.0.0.0:5000`, enabling seamless peer-to-peer file sharing and access across lab workstations.
- **Modern Dark-Mode UI:** Glassmorphism dashboard built with responsive CSS, Google Fonts, live cluster telemetry, and drag-and-drop file upload.
- **100% Tested:** 56 passing automated tests (51 unit tests with HTTP mocks + 5 end-to-end integration tests against a live HDFS cluster).

---

## 🏗️ 2. System Architecture

```mermaid
flowchart TD
    subgraph LAN ["Laboratory Local Area Network (LAN)"]
        BrowserA["Lab Workstation A\n(Chrome/Firefox)"]
        BrowserB["Lab Workstation B\n(Mobile/Laptop)"]
    end

    subgraph Host ["CampusCloud Host Machine"]
        subgraph CC ["Python Cloud Controller (Flask :5000)"]
            Router["API Router\n(/api/v1)"]
            Validator["Input Validator &\nSHA-256 Engine"]
            Services["Service Layer\n(Stream Controller)"]
            SQLite[("SQLite Metadata Store\n(UUID, Hashes, Sizes)")]
            HDFSClient["WebHDFS Client\n(HTTP REST Gateway)"]
        end

        subgraph HDFS ["Apache Hadoop 3.5.0 HDFS Cluster"]
            NameNode["NameNode (:9870)\n- File Namespace\n- Block Mapping\n- WebHDFS Gateway"]
            DataNode["DataNode (:9864)\n- Block Storage\n- Block Streaming"]
            Storage[("Physical Disk Blocks\n(/tmp/campuscloud-hadoop/)")]
        end
    end

    BrowserA -->|HTTP / LAN| Router
    BrowserB -->|HTTP / LAN| Router
    Router --> Validator
    Validator --> Services
    Services <--> SQLite
    Services --> HDFSClient
    HDFSClient -->|1. CREATE Request| NameNode
    NameNode -->|2. 307 Redirect (DataNode URL)| HDFSClient
    HDFSClient -->|3. PUT Block Data| DataNode
    DataNode --> Storage
    NameNode -.->|Heartbeat & Block Reports| DataNode
```

### Architectural Flow of an Upload:
1. **Client Request:** User selects a file on the web dashboard and sends `POST /api/files`.
2. **Controller Validation:** Cloud Controller validates the filename, rejects path traversals or dangerous characters, and checks file size against `MAX_UPLOAD_MB`.
3. **Integrity & Hashing:** The incoming stream is written to a temporary buffer and its SHA-256 checksum is computed simultaneously.
4. **WebHDFS Handshake (Two-Step Redirect):**
   - The Cloud Controller sends a `PUT /webhdfs/v1/<path>?op=CREATE&overwrite=true` request to the **NameNode** (port 9870).
   - The NameNode creates the namespace inode, selects available DataNodes, and responds with `307 Temporary Redirect` containing the direct DataNode upload URL.
5. **Direct Data Transfer:** The Cloud Controller follows the redirect and streams the file payload directly to the **DataNode** (port 9864).
6. **Metadata Persistence:** Upon DataNode confirmation (`201 Created`), the file's UUID, original filename, HDFS block path, size, MIME type, and SHA-256 hash are recorded into the SQLite database.
7. **Cleanup:** Temporary buffer is deleted, and the client receives a JSON `201 Created` response.

---

## ⚙️ 3. Core Components

### A. The Custom Cloud Controller (`cloud_controller/`)
- `hdfs_client.py`: Implements a resilient client for WebHDFS REST endpoints. Wraps `MKDIRS`, `CREATE` (with 307 redirect handling), `OPEN` (streaming download), `DELETE`, `LISTSTATUS`, and `GETCONTENTSUMMARY`. Translates low-level network errors into structured `HDFSConnectionError` and `HDFSError` exceptions.
- `services.py`: Business logic orchestrator. Handles file validations, SHA-256 calculations, atomic database writes, and HDFS cluster health polling.
- `routes.py`: Flask blueprint defining RESTful endpoints with consistent JSON envelopes (`status: "ok"` or `status: "error"`).
- `__init__.py`: Database initialization and schema management using WAL-mode SQLite.

### B. Hadoop HDFS Daemons
- **NameNode (Port 9870):** The master coordinator. Maintains the directory tree and file metadata in memory (`fsimage` + `edits`). It exposes the WebHDFS REST API.
- **DataNode (Port 9864):** The worker daemon. Stores the raw block replicas on the local filesystem and performs block-level read/write operations.

---

## 🚀 4. Installation & Setup

### Prerequisites
- **Operating System:** macOS (Apple Silicon M1/M2/M3/M4 or Intel) or Linux (Ubuntu 22.04+).
- **Homebrew Packages:** `hadoop` (v3.5.0), `openjdk@17`.
- **Python:** Python 3.10+ (Tested on Python 3.14).

```bash
# macOS installation via Homebrew
brew install hadoop openjdk@17
```

### 1. Clone & Configure
```bash
git clone https://github.com/XCodeBunnyX/CampusCloud.git
cd CampusCloud

# Create your .env from the example template
cp .env.example .env
```

### 2. Run Automated Setup Script
The project includes an idempotent automated setup script that configures Hadoop's `core-site.xml`, `hdfs-site.xml`, `hadoop-env.sh`, formats the NameNode, and creates the Python virtual environment:

```bash
chmod +x scripts/*.sh
./scripts/setup.sh
```

---

## 🖥️ 5. Starting & Stopping Services

### Starting Services
To start HDFS NameNode, DataNode, and the Cloud Controller Flask daemon in the background:
```bash
./scripts/start.sh
```
*Console output displays:*
- Local URL: `http://localhost:5000`
- LAN Access URL: `http://<YOUR_LOCAL_IP>:5000`
- HDFS Web UI: `http://localhost:9870`
- Log output: `logs/`

### Stopping Services
```bash
./scripts/stop.sh
```

---

## 📡 6. REST API Documentation

All endpoints return JSON responses formatted with standard HTTP status codes.

| Method | Endpoint | Description | Success Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | Service and HDFS cluster health status | `200 OK` / `503 Degraded` |
| `POST` | `/api/files` | Upload a file (`multipart/form-data`) | `201 Created` |
| `GET` | `/api/files` | List all active stored files | `200 OK` |
| `GET` | `/api/files/<id>/download` | Download raw file from HDFS | `200 OK` (binary attachment) |
| `DELETE` | `/api/files/<id>` | Delete file from HDFS and metadata store | `200 OK` |
| `GET` | `/api/storage` | Aggregate storage usage statistics | `200 OK` |

### Example API Request / Responses

#### 1. Check Health (`GET /api/health`)
```bash
curl -s http://localhost:5000/api/health | jq .
```
```json
{
  "application": "CampusCloud",
  "hdfs": {
    "hdfs_base_path": "/campuscloud/files",
    "hdfs_reachable": true,
    "hdfs_user": "bunny",
    "webhdfs_url": "http://localhost:9870/webhdfs/v1"
  },
  "status": "healthy",
  "timestamp": 1791729039.48,
  "version": "1.0.0"
}
```

#### 2. Upload File (`POST /api/files`)
```bash
curl -X POST http://localhost:5000/api/files \
  -F "file=@sample_lab_report.pdf" | jq .
```
```json
{
  "message": "File uploaded successfully.",
  "status": "ok",
  "file": {
    "id": "4237dab6-213a-4d21-9672-88d4492ccee6",
    "original_name": "sample_lab_report.pdf",
    "size_bytes": 1048576,
    "sha256": "0c3b9f2066b93bd9c943fd348116949cfdcbc3cee3deeeef6dc5b6ad8a0bc52a",
    "content_type": "application/pdf",
    "uploaded_at": 1791729134.78
  }
}
```

#### 3. List Files (`GET /api/files`)
```bash
curl -s http://localhost:5000/api/files | jq .
```
```json
{
  "count": 1,
  "files": [
    {
      "id": "4237dab6-213a-4d21-9672-88d4492ccee6",
      "original_name": "sample_lab_report.pdf",
      "hdfs_name": "4237dab6-213a-4d21-9672-88d4492ccee6_sample_lab_report.pdf",
      "size_bytes": 1048576,
      "sha256": "0c3b9f2066b93bd9c943fd348116949cfdcbc3cee3deeeef6dc5b6ad8a0bc52a",
      "content_type": "application/pdf",
      "uploaded_at": 1791729134.78
    }
  ],
  "status": "ok"
}
```

#### 4. Download File (`GET /api/files/<id>/download`)
```bash
curl -O -J http://localhost:5000/api/files/4237dab6-213a-4d21-9672-88d4492ccee6/download
```

#### 5. Delete File (`DELETE /api/files/<id>`)
```bash
curl -X DELETE http://localhost:5000/api/files/4237dab6-213a-4d21-9672-88d4492ccee6 | jq .
```
```json
{
  "file": {
    "id": "4237dab6-213a-4d21-9672-88d4492ccee6",
    "name": "sample_lab_report.pdf"
  },
  "message": "File deleted.",
  "status": "ok"
}
```

---

## 🧪 7. Automated Testing Suite

CampusCloud comes with an automated test suite implemented in `pytest`.

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all unit tests (HDFS mocked via responses and unittest.mock)
pytest tests/test_api.py tests/test_controller.py -m "not integration" -v

# Run full suite including live HDFS integration tests
pytest -v
```

### Actual Execution Results:
```text
============================== test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
collected 56 items

tests/test_api.py::TestHealthEndpoint::test_health_returns_200_or_503 PASSED      [  1%]
tests/test_api.py::TestHealthEndpoint::test_health_response_schema PASSED         [  3%]
tests/test_api.py::TestHealthEndpoint::test_health_degraded_when_hdfs_offline PASSED [  5%]
tests/test_api.py::TestUploadEndpoint::test_upload_no_file_returns_400 PASSED     [  7%]
tests/test_api.py::TestUploadEndpoint::test_upload_empty_filename_returns_400 PASSED [  8%]
tests/test_api.py::TestUploadEndpoint::test_upload_empty_file_returns_422 PASSED [ 10%]
tests/test_api.py::TestUploadEndpoint::test_upload_success_with_hdfs_mock PASSED [ 12%]
tests/test_api.py::TestUploadEndpoint::test_upload_calls_hdfs_upload PASSED      [ 14%]
tests/test_api.py::TestUploadEndpoint::test_upload_hdfs_connection_error_returns_503 PASSED [ 16%]
tests/test_api.py::TestUploadEndpoint::test_upload_rejects_path_traversal PASSED [ 17%]
tests/test_api.py::TestUploadEndpoint::test_upload_invalid_filename_only_dots PASSED [ 19%]
tests/test_api.py::TestUploadEndpoint::test_upload_hidden_file_rejected PASSED   [ 21%]
tests/test_api.py::TestListEndpoint::test_list_returns_empty_when_no_files PASSED [ 23%]
tests/test_api.py::TestListEndpoint::test_list_returns_uploaded_file PASSED      [ 25%]
tests/test_api.py::TestDownloadEndpoint::test_download_nonexistent_file_returns_404 PASSED [ 26%]
tests/test_api.py::TestDownloadEndpoint::test_download_invalid_id_returns_400 PASSED [ 28%]
tests/test_api.py::TestDownloadEndpoint::test_download_returns_file_bytes PASSED [ 30%]
tests/test_api.py::TestDeleteEndpoint::test_delete_nonexistent_returns_404 PASSED [ 32%]
tests/test_api.py::TestDeleteEndpoint::test_delete_invalid_id_returns_400 PASSED [ 33%]
tests/test_api.py::TestDeleteEndpoint::test_delete_removes_file_from_listing PASSED [ 35%]
tests/test_api.py::TestStorageEndpoint::test_storage_returns_stats PASSED         [ 37%]
tests/test_api.py::TestStorageEndpoint::test_storage_reflects_uploaded_files PASSED [ 39%]
tests/test_controller.py::TestHDFSClientUnit::test_ping_returns_true_on_200 PASSED [ 41%]
tests/test_controller.py::TestHDFSClientUnit::test_ping_returns_false_on_connection_error PASSED [ 42%]
tests/test_controller.py::TestHDFSClientUnit::test_upload_file_two_step PASSED   [ 44%]
tests/test_controller.py::TestHDFSClientUnit::test_download_file PASSED          [ 46%]
tests/test_controller.py::TestHDFSClientUnit::test_download_file_not_found PASSED [ 48%]
tests/test_controller.py::TestHDFSClientUnit::test_delete_file_returns_true PASSED [ 50%]
tests/test_controller.py::TestHDFSClientUnit::test_delete_file_not_found_returns_false PASSED [ 51%]
tests/test_controller.py::TestHDFSClientUnit::test_list_files_returns_only_files_not_dirs PASSED [ 53%]
tests/test_controller.py::TestHDFSClientUnit::test_ensure_base_dir_success PASSED [ 55%]
tests/test_controller.py::TestHDFSClientUnit::test_upload_raises_hdfs_error_on_non_307 PASSED [ 57%]
tests/test_controller.py::TestHDFSClientUnit::test_list_returns_empty_on_404 PASSED [ 58%]
tests/test_controller.py::TestServicesUnit::test_validate_filename_rejects_empty PASSED [ 60%]
tests/test_controller.py::TestServicesUnit::test_validate_filename_rejects_hidden PASSED [ 62%]
tests/test_controller.py::TestServicesUnit::test_validate_filename_rejects_leading_dot PASSED [ 64%]
tests/test_controller.py::TestServicesUnit::test_validate_filename_rejects_long_name PASSED [ 66%]
tests/test_controller.py::TestServicesUnit::test_validate_filename_accepts_normal PASSED [ 67%]
tests/test_controller.py::TestServicesUnit::test_validate_filename_accepts_spaces_sanitized PASSED [ 69%]
tests/test_controller.py::TestServicesUnit::test_sha256_computation PASSED      [ 71%]
tests/test_controller.py::TestServicesUnit::test_list_files_empty_initially PASSED [ 73%]
tests/test_controller.py::TestServicesUnit::test_get_file_returns_none_for_unknown_id PASSED [ 75%]
tests/test_controller.py::TestServicesUnit::test_get_storage_stats_empty_db PASSED [ 76%]
tests/test_controller.py::TestServicesUnit::test_upload_returns_correct_metadata PASSED [ 78%]
tests/test_controller.py::TestServicesUnit::test_upload_appears_in_listing PASSED [ 80%]
tests/test_controller.py::TestServicesUnit::test_upload_rejects_empty_file PASSED [ 82%]
tests/test_controller.py::TestServicesUnit::test_delete_removes_from_listing PASSED [ 83%]
tests/test_controller.py::TestServicesUnit::test_delete_marks_record_deleted PASSED [ 85%]
tests/test_controller.py::TestServicesUnit::test_delete_nonexistent_raises_key_error PASSED [ 87%]
tests/test_controller.py::TestServicesUnit::test_check_hdfs_health_offline PASSED [ 89%]
tests/test_controller.py::TestServicesUnit::test_check_hdfs_health_online PASSED  [ 91%]
tests/test_controller.py::TestHDFSIntegration::test_step1_hdfs_is_reachable PASSED [ 92%]
tests/test_controller.py::TestHDFSIntegration::test_step2_ensure_base_dir PASSED [ 94%]
tests/test_controller.py::TestHDFSIntegration::test_step3_upload_and_verify_in_listing PASSED [ 96%]
tests/test_controller.py::TestHDFSIntegration::test_step4_download_and_compare PASSED [ 98%]
tests/test_controller.py::TestHDFSIntegration::test_step5_delete_and_verify_gone PASSED [100%]

============================== 56 passed in 0.73s ==============================
```

---

## 🌐 8. LAN Demonstration Guide (College Laboratory)

To demonstrate CampusCloud across your college computer laboratory:

### Step 1: Find the Host Machine IP Address
On the host computer running CampusCloud:
```bash
# macOS
ipconfig getifaddr en0

# Linux
hostname -I | awk '{print $1}'
```
*Example IP:* `192.168.1.16`

### Step 2: Ensure Firewall Permits Incoming Connections
On macOS:
- Go to **System Settings → Network → Firewall**.
- Ensure Python / Incoming connections on port `5000` are allowed.

### Step 3: Access from Client Laboratory Workstations
Open any web browser on another computer connected to the same Wi-Fi / Ethernet switch:
```text
http://192.168.1.16:5000
```

### Step 4: Verification via Native Hadoop CLI
To prove to the laboratory examiner that files are genuinely stored in HDFS and not in a regular local folder, run on the host terminal:
```bash
# List all files inside the HDFS base path
hdfs dfs -ls /campuscloud/files

# Inspect file blocks and locations
hdfs fsck /campuscloud/files -files -blocks -locations
```

---

## 🔍 9. Single-Node vs Distributed Multi-Node Deployment

| Characteristic | Laboratory Development Setup | Production Enterprise Cluster |
| :--- | :--- | :--- |
| **Topology** | Pseudo-Distributed (Single Machine) | Fully Distributed (Multi-Server) |
| **NameNode** | 1 instance running on `localhost` | Active + Standby NameNodes with ZooKeeper failover |
| **DataNodes** | 1 instance storing local blocks | Multiple physical rack-mounted worker servers |
| **Replication** | Factor = 1 (`dfs.replication=1`) | Factor = 3 (rack-aware cross-host replication) |
| **WebHDFS** | Redirects to `localhost:9864` | Redirects to individual cluster worker nodes |
| **Network** | Loopback IPC + Host LAN interface | High-throughput 10/25 Gbps Top-of-Rack fabric |

---

## ⚠️ 10. Known Limitations

1. **Replication Factor = 1:** Because only one physical DataNode runs on the development machine, fault-tolerant replication cannot be demonstrated natively without adding remote worker nodes.
2. **Metadata Store Concurrency:** The metadata database uses SQLite with Write-Ahead Logging (WAL). For enterprise installations with thousands of concurrent operations, PostgreSQL should replace SQLite.
3. **Authentication:** The current system operates within a trusted college LAN without Kerberos authentication on WebHDFS.

---

## 📄 11. Academic Deliverables & Project Report

- Comprehensive Academic Mini-Project Report: [PROJECT_REPORT.md](file:///Users/bunny/Desktop/CampusCloud/PROJECT_REPORT.md)
- Laboratory Viva / Demonstration Checklist: [DEMO_CHECKLIST.md](file:///Users/bunny/Desktop/CampusCloud/DEMO_CHECKLIST.md)

---

## 📜 12. License & Author

Developed by **Bunny** for the 3rd-Year Cloud Computing Laboratory Mini-Project.  
Released under the MIT License.
