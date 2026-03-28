from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

from flask import current_app
from werkzeug.security import generate_password_hash

from app import db
from app.services.parser import HELP_TEXT, parse_line
from app.utils import format_chat_date, format_rupiah, generate_temp_password, parse_amount


PLAN_TEXT = (
    "📦 Paket Langganan Catat Uang\n\n"
    "🆓 FREE (Gratis)\n"
    "* 10 teks / bulan\n"
    "* 3 struk / bulan\n\n"
    "✨ LITE - Rp 9.000 / bulan\n"
    "* 200 teks / bulan\n"
    "* 20 struk / bulan\n\n"
    "⭐ STARTER - Rp 19.000 / bulan\n"
    "* 450 teks / bulan\n"
    "* 90 struk / bulan\n"
    "* Edit/delete transaksi\n\n"
    "💎 PREMIUM - Rp 39.000 / bulan\n"
    "* 1.200 teks / bulan\n"
    "* 250 struk / bulan\n"
    "* Edit/delete transaksi\n"
    "* Export CSV\n\n"
    "🚀 PRO - Rp 89.000 / bulan\n"
    "* Unlimited semua\n"
    "* Export CSV\n"
    "* Priority support\n\n"
    "Ketik: upgrade lite / upgrade starter / upgrade premium / upgrade pro"
)

UPGRADE_PLANS = {
    "lite": "LITE",
    "starter": "STARTER",
    "premium": "PREMIUM",
    "pro": "PRO",
}


@dataclass
class IncomingMessage:
    provider: str
    provider_message_id: str
    phone: str
    text: str
    raw_payload: dict[str, Any]


@dataclass
class ProcessResult:
    user_id: int
    reply_text: str
    created_user: bool = False
    duplicate: bool = False
    temporary_password: str | None = None
    setup_url: str | None = None


def normalize_phone(phone: str) -> str:
    return phone.replace("whatsapp:", "").replace("+", "").strip()


def coerce_incoming(payload: dict[str, Any], form_data: dict[str, Any] | None = None) -> IncomingMessage:
    if form_data and form_data.get("From"):
        phone = normalize_phone(form_data.get("From", ""))
        text = (form_data.get("Body") or "").strip()
        message_id = form_data.get("MessageSid") or f"twilio-{int(time.time() * 1000)}"
        return IncomingMessage(
            provider="twilio",
            provider_message_id=message_id,
            phone=phone,
            text=text,
            raw_payload=dict(form_data),
        )

    phone = normalize_phone(str(payload.get("phone", "")))
    text = str(payload.get("text", "")).strip()
    provider = str(payload.get("provider", "local")).strip() or "local"
    message_id = str(payload.get("message_id", "")).strip() or _deterministic_message_id(provider, phone, text)
    return IncomingMessage(provider=provider, provider_message_id=message_id, phone=phone, text=text, raw_payload=payload)


def _deterministic_message_id(provider: str, phone: str, text: str) -> str:
    digest = hashlib.sha1(f"{provider}|{phone}|{text}".encode()).hexdigest()
    return f"{provider}-{digest[:16]}"


def _dashboard_url(base_url: str) -> str:
    return f"{base_url}/login"


def create_user_and_welcome(phone: str, base_url: str, default_plan: str) -> tuple[int, str, str]:
    temp_password = generate_temp_password(8)
    user_id = db.create_user(
        phone=phone,
        password_hash=generate_password_hash(temp_password),
        name=phone,
        initial_balance=0,
        plan=default_plan,
    )
    terms_url = current_app.config["TERMS_URL"]
    welcome = (
        f"🎉 Selamat datang di {current_app.config['APP_NAME']}!\n\n"
        "Akun kamu sudah dibuat:\n"
        f"📱 Username: {phone}\n"
        f"🔐 Password: {temp_password}\n\n"
        f"🌐 Login di: {_dashboard_url(base_url)}\n"
        "⚙️ Jangan lupa ubah password di Settings\n\n"
        "📝 Cara catat transaksi:\n"
        "35k jajan kopi\n"
        "+3jt gaji bulanan\n"
        "+3 juta freelance\n\n"
        "📦 Ketik 'upgrade' untuk lihat paket premium\n\n"
        f"📋 Syarat & Ketentuan: {terms_url}\n"
        "Dengan menggunakan layanan ini, kamu menyetujui ketentuan tersebut.\n\n"
        "Ketik 'bantuan' untuk panduan lengkap"
    )
    return user_id, temp_password, welcome


def process_incoming(incoming: IncomingMessage, *, base_url: str, default_plan: str) -> ProcessResult:
    user = db.get_user_by_phone(incoming.phone)

    if not user:
        user_id, temp_password, welcome_text = create_user_and_welcome(incoming.phone, base_url, default_plan)
        logged = db.log_message(
            user_id=user_id,
            provider=incoming.provider,
            provider_message_id=incoming.provider_message_id,
            direction="inbound",
            phone=incoming.phone,
            body=incoming.text,
            raw_payload=incoming.raw_payload,
        )
        if not logged:
            return ProcessResult(user_id=user_id, reply_text="Pesan duplikat diabaikan.", duplicate=True)

        db.log_message(
            user_id=user_id,
            provider=incoming.provider,
            provider_message_id=f"reply-{incoming.provider_message_id}",
            direction="outbound",
            phone=incoming.phone,
            body=welcome_text,
            raw_payload={"reply_to": incoming.provider_message_id},
        )
        return ProcessResult(user_id=user_id, reply_text=welcome_text, created_user=True, temporary_password=temp_password)

    user_id = int(user["id"])
    logged = db.log_message(
        user_id=user_id,
        provider=incoming.provider,
        provider_message_id=incoming.provider_message_id,
        direction="inbound",
        phone=incoming.phone,
        body=incoming.text,
        raw_payload=incoming.raw_payload,
    )
    if not logged:
        return ProcessResult(user_id=user_id, reply_text="Pesan duplikat diabaikan.", duplicate=True)

    replies: list[str] = []
    for raw_line in [line.strip() for line in incoming.text.splitlines() if line.strip()]:
        special_reply = maybe_handle_special_line(user_id, raw_line)
        if special_reply is not None:
            replies.append(special_reply)
            continue

        parsed = parse_line(raw_line)
        if parsed.kind == "command":
            replies.append(_handle_command(user_id, parsed.command or "", base_url=base_url))
        elif parsed.kind == "transaction":
            tx_id = db.create_transaction(
                user_id=user_id,
                amount=int(parsed.amount or 0),
                description=parsed.description or "Tanpa deskripsi",
                category=None,
                source="whatsapp",
            )
            balance = db.get_balance(user_id)
            tx = db.get_transaction(tx_id)
            today = db.summarize(user_id, days=1)
            replies.append(
                f"✅ {tx['description']}: {format_rupiah(int(tx['amount']))}\n\n"
                f"💰 Saldo: {format_rupiah(balance)}\n"
                f"📉 Keluar hari ini: {format_rupiah(today['expense'])}"
            )
        else:
            if len(raw_line.split()) == 1:
                replies.append(_help_reply(base_url))
            else:
                replies.append(_invalid_format_reply())

    reply_text = "\n\n".join(replies).strip() or _help_reply(base_url)
    db.log_message(
        user_id=user_id,
        provider=incoming.provider,
        provider_message_id=f"reply-{incoming.provider_message_id}",
        direction="outbound",
        phone=incoming.phone,
        body=reply_text,
        raw_payload={"reply_to": incoming.provider_message_id},
    )
    return ProcessResult(user_id=user_id, reply_text=reply_text)


def _help_reply(base_url: str) -> str:
    return f"{HELP_TEXT}\n\nDashboard: {_dashboard_url(base_url)}"


def _invalid_format_reply() -> str:
    return (
        "❌ Format tidak valid\n\n"
        "Contoh yang benar:\n"
        "+20000 makan\n"
        "-15000 bensin\n"
        "20k kopi\n"
        "+3 juta freelance\n\n"
        "Ketik 'bantuan' untuk panduan lengkap"
    )


def _handle_command(user_id: int, command: str, *, base_url: str) -> str:
    if command == "hello":
        return (
            "Halo, siap bantu catat uang via WA.\n\n"
            "Kirim transaksi seperti:\n"
            "10k makan\n"
            "+3jt freelance\n"
            "+3 juta freelance\n\n"
            f"Dashboard: {_dashboard_url(base_url)}"
        )
    if command == "bantuan":
        return _help_reply(base_url)
    if command == "saldo":
        user = db.get_user_by_id(user_id) or {}
        summary = db.summarize(user_id)
        overview = db.get_transaction_overview(user_id)
        return (
            f"💰 Saldo Total: {format_rupiah(db.get_balance(user_id))}\n\n"
            "Detail:\n"
            f"📊 Saldo Awal: {format_rupiah(int(user.get('initial_balance', 0)))}\n"
            f"📈 Total Pemasukan: {format_rupiah(summary['income'])}\n"
            f"📉 Total Pengeluaran: {format_rupiah(summary['expense'])}\n"
            f"📅 Sejak: {format_chat_date(overview['since'])}\n"
            f"📝 Total Transaksi: {overview['count']}"
        )
    if command == "harian":
        summary = db.summarize(user_id, days=1)
        return (
            "📆 Rekap Hari Ini\n"
            f"📈 Masuk: {format_rupiah(summary['income'])}\n"
            f"📉 Keluar: {format_rupiah(summary['expense'])}\n"
            f"⚖️ Net: {format_rupiah(summary['net'])}"
        )
    if command == "mingguan":
        summary = db.summarize(user_id, days=7)
        return (
            "🗓️ Rekap 7 Hari Terakhir\n"
            f"📈 Masuk: {format_rupiah(summary['income'])}\n"
            f"📉 Keluar: {format_rupiah(summary['expense'])}\n"
            f"⚖️ Net: {format_rupiah(summary['net'])}"
        )
    if command == "bulanan":
        summary = db.summarize(user_id, days=30)
        return (
            "🗓️ Rekap 30 Hari Terakhir\n"
            f"📈 Masuk: {format_rupiah(summary['income'])}\n"
            f"📉 Keluar: {format_rupiah(summary['expense'])}\n"
            f"⚖️ Net: {format_rupiah(summary['net'])}"
        )
    if command == "upgrade":
        return PLAN_TEXT
    if command == "forgot_password":
        new_password = generate_temp_password(8)
        db.update_user_password(user_id, generate_password_hash(new_password))
        return (
            "🔐 Password berhasil direset\n"
            f"Password baru: {new_password}\n\n"
            f"🌐 Login di: {_dashboard_url(base_url)}\n"
            "⚙️ Setelah login, segera ganti password di Settings."
        )
    if command == "reset":
        db.reset_user_ledger(user_id)
        return "🧹 Semua transaksi dan saldo awal berhasil direset ke 0."
    if command == "set_opening_balance":
        return "Gunakan format: saldo awal 500k"
    return _help_reply(base_url)


def maybe_handle_special_line(user_id: int, line: str) -> str | None:
    normalized = " ".join(line.lower().split())
    if normalized.startswith("saldo awal "):
        amount_text = normalized.replace("saldo awal", "", 1).strip()
        amount = parse_amount(amount_text)
        if amount is None:
            return "❌ Format saldo awal tidak valid. Contoh: saldo awal 500k"
        db.update_user_balance(user_id, amount)
        return f"✅ Saldo awal diubah menjadi {format_rupiah(amount)}"

    if normalized.startswith("upgrade "):
        requested = normalized.replace("upgrade", "", 1).strip()
        plan = UPGRADE_PLANS.get(requested)
        if not plan:
            return PLAN_TEXT
        db.update_user_plan(user_id, plan)
        return f"✅ Paket {plan} berhasil diaktifkan untuk akun ini."

    return None
