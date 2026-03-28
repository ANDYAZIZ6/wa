from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.utils import parse_amount


COMMAND_ALIASES = {
    "hello": {"halo", "hai", "hi", "start", "mulai"},
    "bantuan": {"bantuan", "help", "menu", "panduan"},
    "saldo": {"saldo", "cek saldo"},
    "harian": {"harian", "rekap", "hari ini"},
    "mingguan": {"mingguan", "minggu", "weekly"},
    "bulanan": {"bulanan", "bulan", "monthly"},
    "upgrade": {"upgrade", "paket", "langganan"},
    "reset": {"reset saldo", "reset"},
    "forgot_password": {"lupa password", "reset password"},
}


@dataclass
class ParsedLine:
    kind: Literal["command", "transaction", "unknown"]
    command: str | None = None
    amount: int | None = None
    description: str | None = None
    raw: str = ""


HELP_TEXT = (
    "📖 Panduan Catat WA\n\n"
    "💰 Set Saldo Awal:\n"
    "* saldo awal 1000000\n"
    "* saldo awal 500rb\n\n"
    "Format pencatatan:\n"
    "10k jajan kopi\n"
    "+5jt gaji freelance\n"
    "-20000 makan siang resto\n"
    "+3 juta freelance\n\n"
    "Perintah:\n"
    "* saldo\n"
    "* rekap / harian\n"
    "* mingguan\n"
    "* bulanan\n"
    "* upgrade\n"
    "* lupa password\n"
    "* reset saldo\n"
    "* bantuan"
)


def normalize_command(text: str) -> str | None:
    cleaned = " ".join(text.lower().strip().split())
    if cleaned.startswith("saldo awal "):
        return "set_opening_balance"
    for canonical, aliases in COMMAND_ALIASES.items():
        if cleaned in aliases:
            return canonical
    return None


def parse_line(line: str) -> ParsedLine:
    raw = line.strip()
    if not raw:
        return ParsedLine(kind="unknown", raw=line)

    command = normalize_command(raw)
    if command:
        return ParsedLine(kind="command", command=command, raw=raw)

    parts = raw.split()
    if not parts:
        return ParsedLine(kind="unknown", raw=raw)

    candidates: list[tuple[str, str]] = []
    if len(parts) >= 2:
        candidates.append((f"{parts[0]} {parts[1]}", " ".join(parts[2:])))
    candidates.append((parts[0], " ".join(parts[1:])))

    for token, description_text in candidates:
        amount = parse_amount(token)
        if amount is not None:
            description = description_text.strip() or "Tanpa deskripsi"
            return ParsedLine(kind="transaction", amount=amount, description=description, raw=raw)

    return ParsedLine(kind="unknown", raw=raw)
