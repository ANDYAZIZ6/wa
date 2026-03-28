from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.auth import login_required
from app.utils import app_now, build_csv, build_pagination, format_datetime, format_rupiah, parse_amount, parse_positive_int


main_bp = Blueprint("main", __name__)
EDIT_DELETE_PLANS = {"STARTER", "PREMIUM", "PRO"}


@main_bp.app_context_processor
def inject_helpers():
    return {
        "format_rupiah": format_rupiah,
        "format_datetime": format_datetime,
        "today_iso": app_now().date().isoformat(),
    }


def _per_page() -> int:
    requested = parse_positive_int(request.args.get("per_page"), current_app.config["DEFAULT_PAGE_SIZE"])
    return min(requested, current_app.config["MAX_PAGE_SIZE"])


@main_bp.route("/")
def index():
    if g.user:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.route("/terms")
def terms():
    return render_template("terms.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    balance = db.get_balance(g.user["id"])
    today = db.summarize(g.user["id"], days=1)
    week = db.summarize(g.user["id"], days=7)
    month = db.summarize(g.user["id"], days=30)
    all_time = db.summarize(g.user["id"])
    today_count = db.count_transactions(user_id=g.user["id"], start_date=app_now().date().isoformat(), end_date=app_now().date().isoformat())
    recent_transactions = db.list_transactions(user_id=g.user["id"], limit=8)
    recent_messages = db.list_messages(g.user["id"], limit=8)
    return render_template(
        "dashboard.html",
        balance=balance,
        today=today,
        week=week,
        month=month,
        all_time=all_time,
        today_count=today_count,
        recent_transactions=recent_transactions,
        recent_messages=recent_messages,
    )


@main_bp.route("/transactions", methods=["GET", "POST"])
@login_required
def transactions():
    if request.method == "POST":
        amount_text = request.form.get("amount", "").strip()
        description = request.form.get("description", "").strip() or "Tanpa deskripsi"
        category = request.form.get("category", "").strip() or None
        source = request.form.get("source", "web") or "web"
        amount = parse_amount(amount_text)
        if amount is None:
            flash("Nominal tidak valid. Contoh: 10k atau +2jt", "error")
        else:
            db.create_transaction(
                user_id=g.user["id"],
                amount=amount,
                description=description,
                category=category,
                source=source,
            )
            flash("Transaksi berhasil ditambahkan.", "success")
        return redirect(url_for("main.transactions"))

    search = request.args.get("q", "").strip()
    tx_type = request.args.get("type", "").strip() or None
    start_date = request.args.get("start", "").strip() or None
    end_date = request.args.get("end", "").strip() or None
    page = parse_positive_int(request.args.get("page"), 1)
    per_page = _per_page()
    total_items = db.count_transactions(
        user_id=g.user["id"],
        search=search or None,
        tx_type=tx_type,
        start_date=start_date,
        end_date=end_date,
    )
    pagination = build_pagination(page=page, per_page=per_page, total_items=total_items)
    rows = db.list_transactions(
        user_id=g.user["id"],
        search=search or None,
        tx_type=tx_type,
        start_date=start_date,
        end_date=end_date,
        limit=per_page,
        offset=pagination["offset"],
    )
    balance = db.get_balance(g.user["id"])
    return render_template(
        "transactions/list.html",
        balance=balance,
        rows=rows,
        filters={"q": search, "type": tx_type or "", "start": start_date or "", "end": end_date or "", "per_page": per_page},
        pagination=pagination,
    )


@main_bp.route("/transactions/<int:tx_id>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(tx_id: int):
    if str(g.user.get("plan") or "FREE").upper() not in EDIT_DELETE_PLANS:
        flash("Fitur edit transaksi khusus paket STARTER/PREMIUM/PRO.", "error")
        return redirect(url_for("main.transactions"))

    row = db.get_transaction(tx_id)
    if not row or int(row["user_id"]) != int(g.user["id"]):
        flash("Transaksi tidak ditemukan.", "error")
        return redirect(url_for("main.transactions"))

    if request.method == "POST":
        amount_text = request.form.get("amount", "").strip()
        description = request.form.get("description", "").strip() or "Tanpa deskripsi"
        category = request.form.get("category", "").strip() or None
        amount = parse_amount(amount_text)
        if amount is None:
            flash("Nominal tidak valid.", "error")
        else:
            db.update_transaction(tx_id, amount=amount, description=description, category=category)
            flash("Transaksi berhasil diubah.", "success")
            return redirect(url_for("main.transactions"))

    return render_template("transactions/edit.html", row=row)


@main_bp.route("/transactions/<int:tx_id>/delete", methods=["POST"])
@login_required
def delete_transaction(tx_id: int):
    if str(g.user.get("plan") or "FREE").upper() not in EDIT_DELETE_PLANS:
        flash("Fitur hapus transaksi khusus paket STARTER/PREMIUM/PRO.", "error")
        return redirect(url_for("main.transactions"))

    row = db.get_transaction(tx_id)
    if row and int(row["user_id"]) == int(g.user["id"]):
        db.delete_transaction(tx_id)
        flash("Transaksi dihapus.", "success")
    else:
        flash("Transaksi tidak ditemukan.", "error")
    return redirect(url_for("main.transactions"))


@main_bp.route("/reports")
@login_required
def reports():
    start_date = request.args.get("start", "").strip() or None
    end_date = request.args.get("end", "").strip() or None
    tx_type = request.args.get("type", "").strip() or None
    page = parse_positive_int(request.args.get("page"), 1)
    per_page = _per_page()
    total_items = db.count_transactions(
        user_id=g.user["id"],
        tx_type=tx_type,
        start_date=start_date,
        end_date=end_date,
    )
    pagination = build_pagination(page=page, per_page=per_page, total_items=total_items)
    rows = db.list_transactions(
        user_id=g.user["id"],
        tx_type=tx_type,
        start_date=start_date,
        end_date=end_date,
        limit=per_page,
        offset=pagination["offset"],
    )
    summary = db.summarize(g.user["id"], start_date=start_date, end_date=end_date)
    rollup = db.daily_rollup(g.user["id"], start_date=start_date, end_date=end_date, limit=90)
    return render_template(
        "reports.html",
        rows=rows,
        summary=summary,
        rollup=rollup,
        filters={"start": start_date or "", "end": end_date or "", "type": tx_type or "", "per_page": per_page},
        pagination=pagination,
    )


@main_bp.route("/reports/export.csv")
@login_required
def export_csv():
    start_date = request.args.get("start", "").strip() or None
    end_date = request.args.get("end", "").strip() or None
    tx_type = request.args.get("type", "").strip() or None
    rows = db.list_transactions(
        user_id=g.user["id"],
        tx_type=tx_type,
        start_date=start_date,
        end_date=end_date,
        limit=current_app.config["MAX_EXPORT_ROWS"],
    )
    csv_data = build_csv(rows)
    filename = f"transactions-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@main_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        form_name = request.form.get("form_name")
        if form_name == "balance":
            amount = parse_amount(request.form.get("initial_balance", "").strip())
            if amount is None:
                flash("Saldo awal tidak valid.", "error")
            else:
                db.update_user_balance(g.user["id"], amount)
                flash("Saldo awal berhasil diperbarui.", "success")
        elif form_name == "password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            if not check_password_hash(g.user["password_hash"], current_password):
                flash("Password saat ini salah.", "error")
            elif len(new_password) < 10:
                flash("Password baru minimal 10 karakter.", "error")
            elif new_password != confirm_password:
                flash("Konfirmasi password tidak sama.", "error")
            else:
                db.update_user_password(g.user["id"], generate_password_hash(new_password))
                flash("Password berhasil diganti.", "success")
        else:
            abort(400)
        return redirect(url_for("main.settings"))

    fresh_user = db.get_user_by_id(g.user["id"])
    return render_template("settings.html", user=fresh_user)


@main_bp.route("/simulator", methods=["GET"])
@login_required
def simulator_redirect():
    if not current_app.config["ENABLE_SIMULATOR"]:
        abort(404)
    return redirect(url_for("whatsapp.simulator"))
