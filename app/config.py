from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "instance" / "wa_finance_bot.db"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


class BaseConfig:
    APP_NAME = os.getenv("APP_NAME", "WA Finance Bot")
    APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
    SECRET_KEY = os.getenv("SECRET_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000").rstrip("/")
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Jakarta")
    DEFAULT_PLAN = os.getenv("DEFAULT_PLAN", "FREE")
    SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "support@example.com")
    SUPPORT_WHATSAPP = os.getenv("SUPPORT_WHATSAPP", "")
    WHATSAPP_BOT_PHONE = os.getenv("WHATSAPP_BOT_PHONE", os.getenv("SUPPORT_WHATSAPP", "")).replace("+", "").strip()
    WHATSAPP_DEFAULT_TEXT = os.getenv("WHATSAPP_DEFAULT_TEXT", "Halo, saya mau mulai catat uang via WA")
    TERMS_URL = os.getenv("TERMS_URL", "")
    TURNSTILE_ENABLED = env_bool("TURNSTILE_ENABLED", False)
    TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "").strip()
    TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
    TURNSTILE_EXPECTED_HOSTNAME = os.getenv("TURNSTILE_EXPECTED_HOSTNAME", "").strip()
    MAX_CONTENT_LENGTH = env_int("MAX_CONTENT_LENGTH", 256 * 1024)
    MAX_EXPORT_ROWS = env_int("MAX_EXPORT_ROWS", 5000)
    DEFAULT_PAGE_SIZE = env_int("DEFAULT_PAGE_SIZE", 25)
    MAX_PAGE_SIZE = env_int("MAX_PAGE_SIZE", 100)
    PASSWORD_TOKEN_MAX_AGE = env_int("PASSWORD_TOKEN_MAX_AGE", 1800)
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "wa_finance_bot_session")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
    SESSION_REFRESH_EACH_REQUEST = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=env_int("SESSION_LIFETIME_HOURS", 12))
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "http")
    TRUSTED_HOSTS = env_list("TRUSTED_HOSTS") or None
    ENABLE_SIMULATOR = env_bool("ENABLE_SIMULATOR", True)
    ALLOW_JSON_WEBHOOKS = env_bool("ALLOW_JSON_WEBHOOKS", True)
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    TWILIO_SANDBOX_ENABLED = env_bool("TWILIO_SANDBOX_ENABLED", False)
    TWILIO_SANDBOX_NUMBER = os.getenv("TWILIO_SANDBOX_NUMBER", "14155238886").replace("+", "").strip()
    TWILIO_SANDBOX_JOIN_CODE = os.getenv("TWILIO_SANDBOX_JOIN_CODE", "").strip()
    TWILIO_SANDBOX_START_TEXT = os.getenv("TWILIO_SANDBOX_START_TEXT", "halo").strip() or "halo"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    USE_PROXY_FIX = env_bool("USE_PROXY_FIX", False)
    PROXY_FIX_X_FOR = env_int("PROXY_FIX_X_FOR", 1)
    PROXY_FIX_X_PROTO = env_int("PROXY_FIX_X_PROTO", 1)
    PROXY_FIX_X_HOST = env_int("PROXY_FIX_X_HOST", 1)
    PROXY_FIX_X_PORT = env_int("PROXY_FIX_X_PORT", 1)
    DB_POOL_SIZE = env_int("DB_POOL_SIZE", 5)
    DB_MAX_OVERFLOW = env_int("DB_MAX_OVERFLOW", 10)
    DB_POOL_RECYCLE_SECONDS = env_int("DB_POOL_RECYCLE_SECONDS", 1800)
    TESTING = False


class DevelopmentConfig(BaseConfig):
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ALLOW_JSON_WEBHOOKS = env_bool("ALLOW_JSON_WEBHOOKS", True)
    ENABLE_SIMULATOR = env_bool("ENABLE_SIMULATOR", True)
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)


class TestingConfig(BaseConfig):
    SECRET_KEY = os.getenv("SECRET_KEY", "test-secret")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///:memory:")
    ENABLE_SIMULATOR = True
    ALLOW_JSON_WEBHOOKS = True
    TESTING = True


class ProductionConfig(BaseConfig):
    ENABLE_SIMULATOR = env_bool("ENABLE_SIMULATOR", False)
    ALLOW_JSON_WEBHOOKS = env_bool("ALLOW_JSON_WEBHOOKS", False)
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https")


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "test": TestingConfig,
    "production": ProductionConfig,
}


def get_config_class():
    env_name = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")).strip().lower()
    return CONFIG_MAP.get(env_name, DevelopmentConfig)
