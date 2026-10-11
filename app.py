"""
CampusCloud — Flask Application Entry Point

Initializes the Flask app, registers the Cloud Controller blueprint,
and configures logging.  Run with:

    python app.py                           # development (localhost)
    HOST=0.0.0.0 PORT=5000 python app.py   # LAN access
"""

import logging
import os
import sys
from pathlib import Path

from flask import Flask, render_template
from dotenv import load_dotenv

# Load .env if present (development convenience)
load_dotenv()

from config import active_config as cfg
from cloud_controller import bp, init_db


def create_app() -> Flask:
    app = Flask(__name__)

    # ── Core config ────────────────────────────────────────────────────────────
    app.config["SECRET_KEY"] = cfg.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_CONTENT_LENGTH

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level = getattr(logging, cfg.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(cfg.LOG_FILE, encoding="utf-8"),
        ],
    )

    # ── Initialize metadata DB ─────────────────────────────────────────────────
    init_db()

    # ── Register Cloud Controller blueprint ────────────────────────────────────
    app.register_blueprint(bp)

    # ── Frontend route ─────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        return render_template("index.html")

    # ── Custom error handlers ──────────────────────────────────────────────────
    @app.errorhandler(413)
    def request_too_large(e):
        from flask import jsonify
        return jsonify({
            "status": "error",
            "message": f"File too large. Maximum upload size is {cfg.MAX_UPLOAD_MB} MB.",
        }), 413

    @app.errorhandler(404)
    def not_found(e):
        from flask import jsonify, request
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "Endpoint not found."}), 404
        return render_template("index.html"), 404

    return app


if __name__ == "__main__":
    application = create_app()
    host = cfg.HOST
    port = cfg.PORT
    debug = cfg.DEBUG

    print(f"""
╔══════════════════════════════════════════════════════════╗
║            CampusCloud — Starting Up                     ║
╠══════════════════════════════════════════════════════════╣
║  Local:   http://localhost:{port:<29} ║
║  Network: http://192.168.1.16:{port:<25} ║
║  HDFS:    {cfg.WEBHDFS_URL:<46} ║
╚══════════════════════════════════════════════════════════╝
""")

    application.run(host=host, port=port, debug=debug)
