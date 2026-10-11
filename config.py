"""
CampusCloud Configuration Module
All settings are loaded from environment variables with safe defaults.
Never hardcode secrets or credentials here.
"""

import os
from pathlib import Path

# ─── Base Paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()

# ─── Flask ─────────────────────────────────────────────────────────────────────
class Config:
    # Flask secret key — override in production via SECRET_KEY env var
    SECRET_KEY = os.environ.get("SECRET_KEY", "campus-cloud-dev-change-me")

    # Network binding
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

    # Upload limits
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", 512)) * 1024 * 1024  # bytes
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 512))

    # Allowed extensions (empty set = allow all)
    ALLOWED_EXTENSIONS_STR = os.environ.get("ALLOWED_EXTENSIONS", "")
    ALLOWED_EXTENSIONS = (
        set(ALLOWED_EXTENSIONS_STR.split(",")) if ALLOWED_EXTENSIONS_STR else set()
    )

    # Temporary directory for in-transit files
    UPLOAD_TMP_DIR = Path(os.environ.get("UPLOAD_TMP_DIR", str(BASE_DIR / "tmp_uploads")))

    # SQLite metadata database
    DB_PATH = Path(os.environ.get("DB_PATH", str(BASE_DIR / "campuscloud.db")))

    # ─── HDFS Settings ─────────────────────────────────────────────────────────
    HDFS_HOST = os.environ.get("HDFS_HOST", "localhost")
    HDFS_PORT = int(os.environ.get("HDFS_PORT", 9870))        # WebHDFS REST port
    HDFS_NAMENODE_PORT = int(os.environ.get("HDFS_NAMENODE_PORT", 9000))  # IPC port
    HDFS_USER = os.environ.get("HDFS_USER", os.environ.get("USER", "hadoop"))
    HDFS_BASE_PATH = os.environ.get("HDFS_BASE_PATH", "/campuscloud/files")

    # WebHDFS base URL constructed from host/port
    @property
    def WEBHDFS_URL(self):
        return f"http://{self.HDFS_HOST}:{self.HDFS_PORT}/webhdfs/v1"

    # ─── Logging ────────────────────────────────────────────────────────────────
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE", str(BASE_DIR / "campuscloud.log"))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


# Active config selection
_config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}

active_config = _config_map.get(
    os.environ.get("FLASK_ENV", "development"), DevelopmentConfig
)()
