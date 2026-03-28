from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from app import db


ops_bp = Blueprint("ops", __name__)


@ops_bp.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"ok": True, "app": current_app.config["APP_NAME"]}), 200


@ops_bp.route("/readyz", methods=["GET"])
def readyz():
    if not db.healthcheck():
        return jsonify({"ok": False, "status": "db_unavailable"}), 503
    return jsonify({"ok": True, "status": "ready"}), 200
