#!/usr/bin/env bash
# =============================================================================
# CampusCloud — setup.sh
# One-time environment setup: configure Hadoop and Python virtual environment.
# Run once before first use.  Safe to re-run (idempotent).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
HADOOP_HOME="$(brew --prefix hadoop)/libexec"
HADOOP_CONF_DIR="$HADOOP_HOME/etc/hadoop"
JAVA17_HOME="$(brew --prefix openjdk@17)"

echo "======================================================"
echo "  CampusCloud Setup"
echo "======================================================"
echo "  Project:      $PROJECT_DIR"
echo "  Hadoop:       $HADOOP_HOME"
echo "  Java 17:      $JAVA17_HOME"
echo "======================================================"

# ── 1. System checks ──────────────────────────────────────────────────────────
echo ""
echo "[1/6] System checks..."

if ! command -v hadoop &>/dev/null; then
    echo "ERROR: hadoop not found. Run: brew install hadoop"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    exit 1
fi

HADOOP_VERSION=$(hadoop version 2>&1 | head -1)
JAVA_VERSION=$(java -version 2>&1 | head -1)
PYTHON_VERSION=$(python3 --version)
echo "  ✓ $HADOOP_VERSION"
echo "  ✓ $JAVA_VERSION"
echo "  ✓ $PYTHON_VERSION"

# ── 2. Configure Hadoop ───────────────────────────────────────────────────────
echo ""
echo "[2/6] Configuring Hadoop..."

# Set JAVA_HOME in hadoop-env.sh (required for Hadoop 3.5 on macOS)
HADOOP_ENV="$HADOOP_CONF_DIR/hadoop-env.sh"

if grep -q "CAMPUSCLOUD_CONFIGURED" "$HADOOP_ENV" 2>/dev/null; then
    echo "  ✓ hadoop-env.sh already configured"
else
    cat >> "$HADOOP_ENV" << EOF

# ── CampusCloud configuration (added by setup.sh) ────────────────────────────
# CAMPUSCLOUD_CONFIGURED
export JAVA_HOME=$JAVA17_HOME
export HADOOP_HEAPSIZE_MAX=512
export HADOOP_HEAPSIZE_MIN=256
export HADOOP_NAMENODE_OPTS="-Xmx512m -Xms256m"
export HADOOP_DATANODE_OPTS="-Xmx512m -Xms256m"
EOF
    echo "  ✓ Wrote JAVA_HOME and heap settings to hadoop-env.sh"
fi

# Copy our site XML files
cp "$SCRIPT_DIR/hadoop_conf/core-site.xml" "$HADOOP_CONF_DIR/core-site.xml"
cp "$SCRIPT_DIR/hadoop_conf/hdfs-site.xml" "$HADOOP_CONF_DIR/hdfs-site.xml"
echo "  ✓ Deployed core-site.xml and hdfs-site.xml"

# ── 3. SSH localhost (required for HDFS daemons) ──────────────────────────────
echo ""
echo "[3/6] Checking SSH localhost access..."
if ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no -o BatchMode=yes localhost exit 2>/dev/null; then
    echo "  ✓ SSH to localhost works"
else
    echo "  ⚠ SSH to localhost failed."
    echo "    Enable it: System Settings → General → Sharing → Remote Login → ON"
    echo "    Then add your key: cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys"
    echo "    If no key exists: ssh-keygen -t rsa -P '' -f ~/.ssh/id_rsa"
    echo ""
    echo "    SSH is needed by Hadoop start scripts to launch daemons."
    echo "    Alternatively, use start.sh which calls daemons directly."
fi

# ── 4. Initialize HDFS NameNode ───────────────────────────────────────────────
echo ""
echo "[4/6] HDFS NameNode initialization..."

NAMENODE_DIR="/tmp/campuscloud-hadoop/dfs/name"
if [ -d "$NAMENODE_DIR/current" ]; then
    echo "  ✓ NameNode already formatted (skipping to preserve data)"
else
    echo "  Formatting NameNode (first time only)..."
    JAVA_HOME="$JAVA17_HOME" hdfs namenode -format -nonInteractive -force 2>&1 | tail -5
    echo "  ✓ NameNode formatted"
fi

# ── 5. Python virtual environment ─────────────────────────────────────────────
echo ""
echo "[5/6] Python virtual environment..."

VENV_DIR="$PROJECT_DIR/.venv"
if [ -d "$VENV_DIR" ]; then
    echo "  ✓ Virtual environment already exists at $VENV_DIR"
else
    python3 -m venv "$VENV_DIR"
    echo "  ✓ Created virtual environment at $VENV_DIR"
fi

# Activate and install
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet
pip install -r "$PROJECT_DIR/requirements.txt" --quiet
echo "  ✓ Python dependencies installed"

# ── 6. Create .env if missing ─────────────────────────────────────────────────
echo ""
echo "[6/6] Environment file..."

ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "  ✓ .env already exists"
else
    cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
    # Set HDFS_USER to current macOS user
    sed -i '' "s/^HDFS_USER=.*/HDFS_USER=$(whoami)/" "$ENV_FILE"
    echo "  ✓ Created .env from .env.example (HDFS_USER=$(whoami))"
fi

echo ""
echo "======================================================"
echo "  Setup complete!"
echo "  Next: ./scripts/start.sh"
echo "======================================================"
