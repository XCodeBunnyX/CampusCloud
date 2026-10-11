#!/usr/bin/env bash
# =============================================================================
# CampusCloud — stop.sh
# Gracefully stops Flask and HDFS daemons.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"

echo "======================================================"
echo "  CampusCloud — Stopping Services"
echo "======================================================"

stop_pid() {
    local name="$1"
    local pid_file="$PID_DIR/$2.pid"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            echo "  ✓ Stopped $name (PID $pid)"
        else
            echo "  ⚠ $name PID $pid not running"
        fi
        rm -f "$pid_file"
    else
        echo "  - No PID file for $name"
        # Try pkill as fallback
        pkill -f "$2" 2>/dev/null && echo "  ✓ Killed $name via pkill" || true
    fi
}

stop_pid "Flask"    "flask"
stop_pid "DataNode" "datanode"
stop_pid "NameNode" "namenode"

# Belt-and-suspenders: kill any remaining hadoop daemons
pkill -f "hadoop.hdfs" 2>/dev/null || true
pkill -f "NameNode"    2>/dev/null || true
pkill -f "DataNode"    2>/dev/null || true

echo ""
echo "  All services stopped."
echo "======================================================"
