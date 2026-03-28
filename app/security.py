from __future__ import annotations

import json
import logging
import secrets
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import abort, current_app, g, request, session
from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer
from twilio.request_validator import RequestValidator


logger = logging.getLogger(__name__)
CSRF_SESSION_KEY = "_csrf_token"
TOKEN_SALT = "wa-finance-bot-auth"
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=TOKEN_SALT)


def generate_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def csrf_exempt(view):
    view._csrf_exempt = True
    return view


def issue_user_token(*, user_id: int, purpose: str) -> str:
    return _serializer().dumps({"user_id": int(user_id), "purpose": purpose})


def consume_user_token(token: str, *, purpose: str, max_age: int) -> dict | None:
    try:
        payload = _serializer().loads(token, max_age=max_age)
    except (BadSignature, BadTimeSignature):
        return None
    if payload.get("purpose") != purpose:
        return None
    return payload


def validate_twilio_request() -> bool:
    auth_token = current_app.config.get("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False

    validator = RequestValidator(auth_token)
    return validator.validate(request.url, request.form.to_dict(flat=True), signature)


def validate_turnstile_token(token: str, *, remote_ip: str | None = None) -> tuple[bool, str | None]:
    secret_key = current_app.config.get("TURNSTILE_SECRET_KEY", "")
    if not current_app.config.get("TURNSTILE_ENABLED"):
        return True, None
    if not secret_key:
        logger.warning("Turnstile enabled but TURNSTILE_SECRET_KEY is missing.")
        return False, "Konfigurasi verifikasi Cloudflare belum lengkap."
    if not token:
        return False, "Verifikasi Cloudflare wajib diisi."

    payload = {"secret": secret_key, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    request_body = urlencode(payload).encode()
    siteverify_request = Request(
        TURNSTILE_VERIFY_URL,
        data=request_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(siteverify_request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.exception("Failed to validate Turnstile token.")
        return False, "Verifikasi Cloudflare gagal diproses. Coba lagi."

    if not result.get("success"):
        return False, "Verifikasi Cloudflare gagal. Coba ulangi centangnya."

    expected_hostname = current_app.config.get("TURNSTILE_EXPECTED_HOSTNAME", "")
    if expected_hostname and result.get("hostname") != expected_hostname:
        logger.warning("Turnstile hostname mismatch: %s", result.get("hostname"))
        return False, "Hostname verifikasi Cloudflare tidak cocok."

    return True, None


def _should_validate_csrf() -> bool:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    view = current_app.view_functions.get(request.endpoint or "")
    return not getattr(view, "_csrf_exempt", False)


def _before_request() -> None:
    g.request_started_at = time.perf_counter()
    g.request_id = request.headers.get("X-Request-ID", secrets.token_hex(8))

    if _should_validate_csrf():
        expected = session.get(CSRF_SESSION_KEY, "")
        received = request.form.get("_csrf_token", "") or request.headers.get("X-CSRFToken", "")
        if not expected or not received or not secrets.compare_digest(expected, received):
            abort(400, description="Invalid CSRF token.")


def _after_request(response):
    response.headers["X-Request-ID"] = g.get("request_id", "")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

    duration_ms = 0.0
    if g.get("request_started_at") is not None:
        duration_ms = (time.perf_counter() - g.request_started_at) * 1000
    logger.info(
        "%s %s status=%s duration_ms=%.2f request_id=%s remote_addr=%s",
        request.method,
        request.path,
        response.status_code,
        duration_ms,
        g.get("request_id", "-"),
        request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return response


def init_app(app) -> None:
    app.before_request(_before_request)
    app.after_request(_after_request)
    app.jinja_env.globals["csrf_token"] = generate_csrf_token


def password_token_url(base_url: str, *, user_id: int, purpose: str) -> str:
    token = issue_user_token(user_id=user_id, purpose=purpose)
    return f"{base_url}/set-password?token={token}&purpose={purpose}"
