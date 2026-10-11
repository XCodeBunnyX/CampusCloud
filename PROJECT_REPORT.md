# CampusCloud: A LAN-Based Distributed Cloud Storage System Using HDFS

**Course:** Cloud Computing Laboratory (CS601)  
**Project Category:** Mini-Project / Cloud Software as a Service (SaaS) Implementation  
**Academic Year:** 2026–2027  
**Department:** Computer Science and Engineering  

---

## Abstract

Distributed cloud storage is a core foundation of modern Cloud Computing, offering high throughput, fault tolerance, and scalable capacity across networked clusters. This project presents **CampusCloud**, a private Cloud Storage as a Service (SaaS) solution engineered for deployment across a college laboratory Local Area Network (LAN). The system integrates a custom Python-based **Cloud Controller** with the **Apache Hadoop Distributed File System (HDFS)**. Rather than simulating storage on a conventional local disk, CampusCloud utilizes HDFS's native NameNode and DataNode daemons via the WebHDFS REST protocol to perform genuine block-level distributed storage. The platform provides secure file ingestion, cryptographic data integrity checking (SHA-256), metadata indexing, streaming file downloads, and safe resource deallocation, all accessible through a responsive, modern web interface. Comprehensive verification is established via an automated test suite comprising 56 unit and end-to-end integration test cases.

---

## 1. Introduction & Problem Statement

### 1.1 College Assignment Mandate
The academic objective requires students to:
> *"Setup your own Cloud for Software as a Service (SaaS) over the existing LAN in your laboratory. Write your own code for Cloud Controller using Open Source Technologies to implement with HDFS."*

### 1.2 Problem Formulation
Traditional web applications that handle file uploads typically write incoming files directly to a local filesystem directory (e.g., `/var/www/uploads/`). While straightforward, this monolithic approach suffers from critical limitations in cloud environments:
- Single point of disk failure and storage exhaustion.
- Inability to scale storage across distinct networked physical machines.
- Lack of native block replication, automatic rebalancing, and cluster-wide telemetry.

To satisfy the requirements of a true SaaS cloud model, the application must separate the **compute/orchestration tier** (Cloud Controller) from the **storage tier** (Distributed File System). Furthermore, students in a campus computer laboratory must be able to interact with the platform concurrently from separate client workstations across the campus LAN.

---

## 2. System Architecture

The CampusCloud architecture follows a decoupled, three-tier cloud model:
1. **Presentation Tier (Client):** Single Page Application (SPA) dashboard executed in the client browser across the laboratory LAN.
2. **Logic & Orchestration Tier (Cloud Controller):** Python/Flask controller handling client authentication, file validation, SHA-256 hashing, metadata transactions, and WebHDFS communication.
3. **Storage Tier (Apache Hadoop HDFS):** Clustered file system containing a master NameNode and worker DataNodes.

```
+-------------------------------------------------------------------------+
|                        LABORATORY LAN CLIENTS                           |
|      Workstation 1 (192.168.1.20)         Workstation 2 (192.168.1.35)   |
|            [Web Browser]                         [Web Browser]          |
+------------------------------------+------------------------------------+
                                     |  HTTP (Port 5000)
                                     v
+-------------------------------------------------------------------------+
|                  CAMPUSCLOUD CONTROLLER (Python / Flask)                |
|                                                                         |
|  +--------------------+   +---------------------+   +----------------+  |
|  | Request Validation |-->| SHA-256 Hash Engine |-->| Metadata Store |  |
|  +--------------------+   +---------------------+   | (SQLite WAL)   |  |
|                                                     +----------------+  |
|                                 |                                       |
|                                 v WebHDFS Protocol                      |
|                  +------------------------------+                       |
|                  |     HDFS Client Wrapper      |                       |
|                  +------------------------------+                       |
+-------------------+-----------------------------+-----------------------+
                    |                             |
      1. CREATE     |                             | 3. Streaming PUT
     (Redirect 307) |                             |    (Block Data)
                    v                             v
+-----------------------------+         +-------------------------------+
|     HADOOP NAMENODE         |         |       HADOOP DATANODE         |
|       (Port 9870)           |<------->|         (Port 9864)           |
| - File Namespace Tree       | Heartbeat - Physical Block Storage      |
| - Inode to Block Mapping    |  Report   - Block Checksums             |
| - WebHDFS REST API Gateway  |           - Disk Read/Write Pipeline    |
+-----------------------------+         +-------------------------------+
```

---

## 3. Design of the Custom Cloud Controller

The Cloud Controller is the central coordinator of CampusCloud. Its responsibilities are rigorously modularized:

### 3.1 Two-Stage WebHDFS Streaming Protocol
HDFS writes are coordinated by the NameNode but physically executed by DataNodes. The controller implements the standard two-step WebHDFS protocol:
1. **Initial Handshake:** The controller dispatches a `PUT` request to `http://<namenode>:9870/webhdfs/v1/<path>?op=CREATE&overwrite=true`.
2. **Cluster Redirection:** Because the NameNode does not store data blocks, it responds with an HTTP `307 Temporary Redirect` containing the direct URL of the assigned DataNode (`http://<datanode>:9864/webhdfs/v1/...`).
3. **Payload Stream:** The controller follows this redirect and streams the file payload directly into the DataNode, which writes the blocks to disk and confirms with `201 Created`.

### 3.2 Data Integrity & Security
- **Cryptographic Hashing:** Every uploaded stream is hashed using SHA-256 in real time. The hash is preserved in the metadata database, enabling clients to verify file authenticity and integrity.
- **Path Traversal Prevention:** Incoming filenames are sanitized using Werkzeug's `secure_filename`, rejecting directory traversals (`../`), null bytes, and hidden files (`.env`, `.bashrc`).
- **UUID Namespacing:** Files stored in HDFS are prefixed with an RFC 4122 version 4 UUID (`<uuid>_<sanitized_name>`) to prevent collision vulnerabilities when different users upload files with identical names.

---

## 4. Hadoop HDFS Architecture Details

### 4.1 NameNode Responsibilities
The NameNode operates as the primary master node in the HDFS cluster:
- **Namespace Management:** Maintains the entire hierarchical file system directory tree (`/campuscloud/files/`).
- **Block Mapping:** Maps logical file paths to distributed physical blocks (`blk_<id>`).
- **Cluster State Tracking:** Monitors DataNode health via 3-second periodic heartbeats and block reports.
- **REST Gateway:** Exposes the WebHDFS REST interface on TCP port 9870.

### 4.2 DataNode Responsibilities
The DataNode serves as the storage worker node:
- **Block Storage:** Stores individual 128 MB blocks as regular files within the host's configured disk directory (`/tmp/campuscloud-hadoop/dfs/data`).
- **Read/Write Execution:** Serves raw block reads (`GET /webhdfs/v1/...`) and writes (`PUT /webhdfs/v1/...`) on TCP port 9864.
- **Block Integrity:** Computes cyclic redundancy checks (CRC32) on every stored block to guard against bit rot.

---

## 5. Implementation Details

The implementation comprises the following technical stack:
- **Backend Language:** Python 3.14 (compatible with Python 3.10+)
- **Web Framework:** Flask 3.1
- **HTTP Engine:** Requests 2.32 with persistent connection pooling
- **Metadata Storage:** SQLite 3 with Write-Ahead Logging (WAL) mode
- **Distributed Storage:** Apache Hadoop 3.5.0 (HDFS)
- **Frontend:** Vanilla HTML5, Modern CSS3 (Glassmorphism, CSS Custom Properties), Vanilla JavaScript (ES6+ Fetch API)
- **Testing:** Pytest 9.1 with Pytest-Mock and Responses

### Directory Hierarchy:
```
CampusCloud/
├── app.py                      # Application bootstrap & entry point
├── config.py                   # Environment configuration & defaults
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Pytest configuration & markers
├── cloud_controller/           # Custom Cloud Controller Package
│   ├── __init__.py             # Database schema initialization
│   ├── hdfs_client.py          # WebHDFS REST API client
│   ├── services.py             # Business logic & validations
│   └── routes.py               # REST API endpoints
├── static/                     # Web UI Static Assets
│   ├── css/style.css           # Glassmorphism styling & animations
│   └── js/app.js               # Frontend controller & API fetchers
├── templates/
│   └── index.html              # Responsive single-page dashboard
├── scripts/
│   ├── setup.sh                # Automated Hadoop & venv setup
│   ├── start.sh                # Service startup daemon
│   ├── stop.sh                 # Graceful shutdown script
│   └── hadoop_conf/            # core-site.xml and hdfs-site.xml
└── tests/
    ├── test_api.py             # Unit tests for HTTP endpoints
    └── test_controller.py      # Unit & live HDFS integration tests
```

---

## 6. Experimental Verification & Test Results

Testing was conducted across two distinct layers:
1. **Unit Testing Layer:** Isolates the controller logic by mocking HDFS HTTP responses via the `responses` library.
2. **Integration Testing Layer:** Directly executes against running local NameNode and DataNode daemons to verify end-to-end distributed storage operations.

### Automated Test Execution Log:
```text
pytest -v
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

## 7. Analysis: Development vs Production Topology

An important consideration in evaluating CampusCloud is distinguishing between a **Single-Machine Pseudo-Distributed Setup** and a **Fully Distributed Production Deployment**:

| Metric | Single-Node Pseudo-Distributed (Current Lab Setup) | Fully Distributed Multi-Node Cluster (Production) |
| :--- | :--- | :--- |
| **Physical Nodes** | 1 Host Machine | 1 Master Server + N Worker Servers |
| **Daemon Distribution** | NameNode & DataNode run on same machine | NameNode on dedicated master; DataNodes on worker nodes |
| **Replication Factor** | 1 (`dfs.replication=1`) | 3 (`dfs.replication=3` across rack domains) |
| **Network Overhead** | IPC loopback (`127.0.0.1`) | Dedicated Top-of-Rack (ToR) Ethernet switches |
| **Fault Tolerance** | Limited (node crash halts both daemons) | High (survives loss of up to 2 simultaneous DataNodes) |
| **WebHDFS Redirection** | Redirects to `localhost:9864` | Redirects to the specific DataNode hosting the replica |

---

## 8. Conclusion & Future Enhancements

CampusCloud successfully meets and exceeds all objectives specified in the Cloud Computing Laboratory assignment:
1. Deploys an accessible SaaS storage service over the laboratory LAN.
2. Formulates and executes a custom Python Cloud Controller integrating directly with Apache Hadoop HDFS.
3. Provides full CRUD functionality (Create, Read, List, Delete) verified against actual HDFS file blocks.
4. Delivers an intuitive, modern user interface alongside a verified test suite.

### Future Scope
- **Multi-Tenant User Authentication:** Implement role-based access control (RBAC) with JWT tokens and quotas per student.
- **Kerberos Security Integration:** Enable Kerberos ticket authentication for enterprise WebHDFS clusters.
- **Erasure Coding:** Upgrade from 3x replication to HDFS Reed-Solomon Erasure Coding (`RS-6-3`) to reduce raw storage overhead by 50%.
