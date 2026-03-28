from __future__ import annotations

import csv
import io
import random
import re
import string
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from flask import current_app


AMOUNT_RE = re.compile(r"^([+-]?)(\d+(?:[\.,]\d+)?)(k|rb|ribu|jt|juta|m)?$", re.IGNORECASE)


def generate_temp_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def format_rupiah(value: int) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}Rp {abs(int(value)):,}".replace(",", ".")


def parse_amount(token: str) -> int | None:
    token = token.strip().lower().replace(" ", "")
    token = token.replace("rp", "")
    match = AMOUNT_RE.match(token)
    if not match:
        return None
    sign_text, number_text, suffix = match.groups()
    number_text = number_text.replace(",", ".")
    value = float(number_text)
    multiplier = 1
    if suffix in {"k", "rb", "ribu"}:
        multiplier = 1_000
    elif suffix in {"jt", "juta", "m"}:
        multiplier = 1_000_000
    amount = int(round(value * multiplier))
    if sign_text == "-":
        amount *= -1
    return amount


def app_now() -> datetime:
    tz = ZoneInfo(current_app.config["APP_TIMEZONE"])
    return datetime.now(tz)


def iso_local_now() -> str:
    return app_now().replace(microsecond=0).isoformat()


def build_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "tanggal", "jenis", "nominal", "deskripsi", "kategori", "sumber"])
    for row in rows:
        writer.writerow(
            [
                row.get("id"),
                row.get("transaction_at"),
                row.get("type"),
                row.get("amount"),
                row.get("description"),
                row.get("category") or "",
                row.get("source") or "",
            ]
        )
    return buffer.getvalue()


def format_datetime(value: str | None) -> str:
    if not value:
        return "-"
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(current_app.config["APP_TIMEZONE"])).strftime("%Y-%m-%d %H:%M")


def format_chat_date(value: str | None) -> str:
    if not value:
        return "Belum ada transaksi"
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(current_app.config["APP_TIMEZONE"])).strftime("%d %b %Y")


def parse_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or "")
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def build_pagination(*, page: int, per_page: int, total_items: int) -> dict:
    total_pages = max((total_items + per_page - 1) // per_page, 1)
    current_page = min(max(page, 1), total_pages)
    return {
        "page": current_page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_page": current_page - 1,
        "next_page": current_page + 1,
        "offset": (current_page - 1) * per_page,
    }


def build_whatsapp_link(phone: str | None, text: str | None = None) -> str | None:
    if not phone:
        return None
    base = f"https://wa.me/{phone.replace('+', '').strip()}"
    if not text:
        return base
    return f"{base}?text={quote(text)}"
