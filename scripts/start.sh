#!/usr/bin/env bash
# =============================================================================
# CampusCloud — start.sh
# Starts HDFS daemons and the Flask application.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
HADOOP_HOME="$(brew --prefix hadoop)/libexec"
JAVA17_HOME="$(brew --prefix openjdk@17)"
VENV="$PROJECT_DIR/.venv/bin/activate"
PID_DIR="$PROJECT_DIR/.pids"
mkdir -p "$PID_DIR"

export JAVA_HOME="$JAVA17_HOME"
export HADOOP_HEAPSIZE_MAX=512
export HADOOP_HEAPSIZE_MIN=256
export HADOOP_NAMENODE_OPTS="-Xmx512m -Xms256m"
export HADOOP_DATANODE_OPTS="-Xmx512m -Xms256m"

echo "======================================================"
echo "  CampusCloud — Starting Services"
echo "======================================================"

# ── 1. Start NameNode ─────────────────────────────────────────────────────────
echo ""
echo "[1/3] Starting HDFS NameNode..."

if pgrep -f "NameNode" &>/dev/null; then
    echo "  ✓ NameNode already running"
else
    # Check NameNode is formatted
    if [ ! -d "/tmp/campuscloud-hadoop/dfs/name/current" ]; then
        echo "  ERROR: NameNode not formatted. Run scripts/setup.sh first."
        exit 1
    fi

    HADOOP_LOG_DIR="$PROJECT_DIR/logs" \
    nohup hdfs namenode > "$PROJECT_DIR/logs/namenode.log" 2>&1 &
    echo $! > "$PID_DIR/namenode.pid"

    # Wait for NameNode to start (up to 30s)
    echo -n "  Waiting for NameNode"
    for i in $(seq 1 30); do
        if curl -sf "http://localhost:9870/webhdfs/v1/?op=LISTSTATUS&user.name=$(whoami)" &>/dev/null; then
            echo " ✓"
            break
        fi
        echo -n "."
        sleep 1
    done
    echo "  ✓ NameNode started (PID $(cat "$PID_DIR/namenode.pid"))"
fi

# ── 2. Start DataNode ─────────────────────────────────────────────────────────
echo ""
echo "[2/3] Starting HDFS DataNode..."

if pgrep -f "DataNode" &>/dev/null; then
    echo "  ✓ DataNode already running"
else
    mkdir -p "$PROJECT_DIR/logs"
    HADOOP_LOG_DIR="$PROJECT_DIR/logs" \
    nohup hdfs datanode > "$PROJECT_DIR/logs/datanode.log" 2>&1 &
    echo $! > "$PID_DIR/datanode.pid"
    sleep 3
    echo "  ✓ DataNode started (PID $(cat "$PID_DIR/datanode.pid"))"
fi

# Wait for WebHDFS to be accessible
echo ""
echo "  Verifying WebHDFS..."
WEBHDFS_READY=false
for i in $(seq 1 15); do
    if curl -sf "http://localhost:9870/webhdfs/v1/?op=LISTSTATUS&user.name=$(whoami)" &>/dev/null; then
        WEBHDFS_READY=true
        break
    fi
    sleep 1
done

if $WEBHDFS_READY; then
    echo "  ✓ WebHDFS is accessible at http://localhost:9870"
else
    echo "  ⚠ WebHDFS not responding yet — Flask will handle connection errors gracefully"
fi

# ── 3. Start Flask ────────────────────────────────────────────────────────────
echo ""
echo "[3/3] Starting Flask application..."

if [ ! -f "$VENV" ]; then
    echo "  ERROR: Virtual environment not found. Run scripts/setup.sh first."
    exit 1
fi

# shellcheck disable=SC1090
source "$VENV"

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "127.0.0.1")
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5000}"

nohup python "$PROJECT_DIR/app.py" > "$PROJECT_DIR/logs/flask.log" 2>&1 &
echo $! > "$PID_DIR/flask.pid"
sleep 2

echo "  ✓ Flask started (PID $(cat "$PID_DIR/flask.pid"))"

echo ""
echo "======================================================"
echo "  CampusCloud is RUNNING"
echo "  Dashboard:  http://localhost:$PORT"
echo "  LAN Access: http://$LAN_IP:$PORT"
echo "  HDFS UI:    http://localhost:9870"
echo "  Logs:       $PROJECT_DIR/logs/"
echo "  Stop:       ./scripts/stop.sh"
echo "======================================================"
