from __future__ import annotations

from xml.sax.saxutils import escape

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request

from app.auth import login_required
from app.security import csrf_exempt, validate_twilio_request
from app.services.whatsapp_service import coerce_incoming, process_incoming


whatsapp_bp = Blueprint("whatsapp", __name__)


def _twiml_message(body: str) -> str:
    safe = escape(body)
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{safe}</Message></Response>"


@whatsapp_bp.route("/webhooks/whatsapp", methods=["POST"])
@csrf_exempt
def whatsapp_webhook():
    is_twilio_form = bool(request.form)
    if is_twilio_form and not validate_twilio_request():
        return jsonify({"ok": False, "error": "invalid webhook signature"}), 403

    if not is_twilio_form and not current_app.config["ALLOW_JSON_WEBHOOKS"]:
        return jsonify({"ok": False, "error": "json webhooks are disabled"}), 403

    payload = request.get_json(silent=True) or {}
    incoming = coerce_incoming(payload, request.form if is_twilio_form else None)
    if not incoming.phone:
        return jsonify({"ok": False, "error": "phone is required"}), 400

    result = process_incoming(
        incoming,
        base_url=current_app.config["BASE_URL"],
        default_plan=current_app.config["DEFAULT_PLAN"],
    )

    if is_twilio_form:
        return current_app.response_class(_twiml_message(result.reply_text), mimetype="application/xml")

    return jsonify(
        {
            "ok": True,
            "phone": incoming.phone,
            "reply_text": result.reply_text,
            "created_user": result.created_user,
            "duplicate": result.duplicate,
            "temporary_password": result.temporary_password,
            "setup_url": result.setup_url,
        }
    )


@whatsapp_bp.route("/simulator", methods=["GET", "POST"])
@login_required
def simulator():
    if not current_app.config["ENABLE_SIMULATOR"]:
        abort(404)

    response_data = None
    if request.method == "POST":
        phone = request.form.get("phone", "").strip() or g.user["phone"]
        text = request.form.get("text", "").strip()
        payload = {
            "phone": phone,
            "text": text,
            "provider": "local",
            "message_id": request.form.get("message_id", "").strip() or "",
        }
        incoming = coerce_incoming(payload)
        result = process_incoming(
            incoming,
            base_url=current_app.config["BASE_URL"],
            default_plan=current_app.config["DEFAULT_PLAN"],
        )
        response_data = {
            "payload": payload,
            "reply_text": result.reply_text,
            "created_user": result.created_user,
            "duplicate": result.duplicate,
            "temporary_password": result.temporary_password,
            "setup_url": result.setup_url,
        }
    return render_template("simulator.html", response_data=response_data)
