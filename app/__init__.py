from __future__ import annotations

import logging
import sys

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app import db
from app.auth import auth_bp
from app.config import BASE_DIR, get_config_class
from app.main import main_bp
from app.ops import ops_bp
from app.security import init_app as init_security
from app.utils import build_whatsapp_link
from app.whatsapp import whatsapp_bp


def _configure_logging(app: Flask) -> None:
    level_name = app.config["LOG_LEVEL"]
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)


def _validate_config(app: Flask) -> None:
    env_name = app.config["APP_ENV"]
    if env_name == "production":
        if not app.config.get("SECRET_KEY"):
            raise RuntimeError("SECRET_KEY must be set in production.")
        if app.config["DATABASE_URL"].startswith("sqlite"):
            raise RuntimeError("Production requires a PostgreSQL-compatible DATABASE_URL.")
    if not app.config.get("TERMS_URL"):
        app.config["TERMS_URL"] = f"{app.config['BASE_URL']}/terms"


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
        static_url_path="/static",
    )
    app.config.from_object(get_config_class())
    if config_overrides:
        app.config.update(config_overrides)

    _configure_logging(app)
    _validate_config(app)

    if app.config["USE_PROXY_FIX"]:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config["PROXY_FIX_X_FOR"],
            x_proto=app.config["PROXY_FIX_X_PROTO"],
            x_host=app.config["PROXY_FIX_X_HOST"],
            x_port=app.config["PROXY_FIX_X_PORT"],
        )

    db.init_app(app)
    init_security(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(ops_bp)

    @app.context_processor
    def inject_global_links():
        sandbox_mode = bool(app.config.get("TWILIO_SANDBOX_ENABLED"))
        sandbox_join_code = app.config.get("TWILIO_SANDBOX_JOIN_CODE", "")
        sandbox_number = app.config.get("TWILIO_SANDBOX_NUMBER")
        return {
            "whatsapp_chat_url": build_whatsapp_link(
                app.config.get("WHATSAPP_BOT_PHONE"),
                app.config.get("WHATSAPP_DEFAULT_TEXT"),
            ),
            "twilio_sandbox_enabled": sandbox_mode,
            "twilio_sandbox_join_code": sandbox_join_code,
            "twilio_sandbox_join_url": build_whatsapp_link(
                sandbox_number,
                f"join {sandbox_join_code}".strip(),
            ) if sandbox_mode and sandbox_join_code else None,
            "twilio_sandbox_start_url": build_whatsapp_link(
                sandbox_number,
                app.config.get("TWILIO_SANDBOX_START_TEXT"),
            ) if sandbox_mode and sandbox_join_code else None,
        }

    return app
