# CampusCloud ☁️ — Laboratory Demonstration Checklist & Viva Guide

Use this checklist during your college laboratory examination / viva to demonstrate the working system step-by-step to the examiner.

---

## 📋 Part 1: Pre-Demonstration Verification (2 Minutes Before Demo)

- [ ] **Step 1: Check Services are Running**
  ```bash
  jps | grep -E "NameNode|DataNode"
  ```
  *Expected Output:* Two Java process IDs showing `NameNode` and `DataNode`.

- [ ] **Step 2: Check API Health Endpoint**
  ```bash
  curl -s http://localhost:5000/api/health | jq .
  ```
  *Expected Output:* `"status": "healthy"`, `"hdfs_reachable": true`.

- [ ] **Step 3: Retrieve Host LAN IP**
  ```bash
  # macOS
  ipconfig getifaddr en0
  ```
  *Note down the IP address (e.g., `192.168.1.16`).*

---

## 🎯 Part 2: Step-by-Step Live Demonstration Flow

### Step 1: Open the Web Dashboard
1. Open Chrome or Firefox on the host machine at:
   `http://localhost:5000`
2. Open the same URL from a peer lab computer or smartphone on the same Wi-Fi:
   `http://<LAN_IP>:5000`
3. Point out to the examiner:
   - Modern dark-mode glassmorphism interface.
   - Live HDFS Cluster Status badge showing **"Online · Hadoop 3.5.0 · WebHDFS"**.
   - Metric cards displaying stored files count and cumulative storage used.

### Step 2: Upload a File via Web Interface
1. Drag and drop a document (e.g., `syllabus.pdf` or `notes.txt`) into the upload zone or click **Browse File**.
2. Click **Upload to CampusCloud**.
3. Point out:
   - Instant upload progress toast notification.
   - Dynamic insertion into the **My Files** table with human-readable file size and upload timestamp.

### Step 3: Prove Real HDFS Storage (Crucial for High Marks)
Show the examiner that the file was **NOT** merely saved to a local folder, but genuinely written into the Hadoop Distributed File System:

```bash
# 1. View files inside HDFS directory using Hadoop CLI:
hdfs dfs -ls /campuscloud/files

# 2. View detailed block locations and health report:
hdfs fsck /campuscloud/files -files -blocks -locations
```
*Examiner can see the exact HDFS block ID (e.g., `blk_1073741825_1001`) and replica count.*

### Step 4: Download and Verify Integrity
1. Click the **Download** button in the Web UI table.
2. Verify that the downloaded file opens correctly and has identical contents.
3. Show that the file is streamed straight from HDFS through the Cloud Controller.

### Step 5: Delete and Verify Clean Deallocation
1. Click the **Delete** button in the Web UI table and confirm.
2. Run the HDFS command in terminal:
   ```bash
   hdfs dfs -ls /campuscloud/files
   ```
3. Show that the file is completely removed from HDFS storage.

---

## 🧑‍🏫 Part 3: Top Examiner Viva Questions & Model Answers

### Q1: What makes this a "Cloud Storage SaaS" rather than just a standard web file uploader?
> **Answer:**  
> A standard uploader saves files onto the web server's local disk partition. CampusCloud decouples the compute layer (Cloud Controller) from the storage layer (HDFS). Files are sent over HTTP to the Cloud Controller, which delegates storage to a distributed cluster of NameNodes and DataNodes using the WebHDFS REST API. The storage layer can scale horizontally across multiple machines without changing the application logic.

---

### Q2: Why did you use WebHDFS instead of the native Java HDFS client?
> **Answer:**  
> The native Hadoop client requires Java Native Interface (JNI) bindings (`libhdfs.so`) or JVM wrappers (`pyarrow`/`hdfs-cli`), which introduce heavy binary dependencies and platform compatibility issues on macOS Apple Silicon. WebHDFS is an official, standardized REST API supported directly by Hadoop that allows language-agnostic HTTP communication with full support for streaming uploads and downloads.

---

### Q3: Explain the two-step upload protocol used by WebHDFS.
> **Answer:**  
> 1. When a client initiates an upload, it first contacts the **NameNode** with a `PUT ?op=CREATE` request.  
> 2. Because the NameNode only manages metadata and does not store data blocks, it responds with an **HTTP 307 Temporary Redirect** pointing to an available **DataNode**.  
> 3. The Cloud Controller follows this redirect and streams the actual file bytes directly to the DataNode on port 9864. This prevents the NameNode from becoming a network throughput bottleneck.

---

### Q4: What is the purpose of the SQLite database if HDFS already stores files?
> **Answer:**  
> HDFS is optimized for high-throughput sequential reads and writes of large data blocks, but is not designed for fast low-latency queries, indexing original filenames, or storing user-specific metadata. The SQLite database serves as an auxiliary metadata ledger to track original human-readable filenames, UUIDs, MIME types, and cryptographic SHA-256 hashes for fast instantaneous UI rendering.

---

### Q5: How is data integrity guaranteed?
> **Answer:**  
> During upload, the Cloud Controller computes the SHA-256 cryptographic hash of the stream in memory before storing it in the metadata ledger. HDFS simultaneously computes internal CRC32 checksums on each block. This ensures end-to-end data integrity detection against transmission errors or bit rot.
