from __future__ import annotations

from functools import wraps

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.security import consume_user_token, validate_turnstile_token


auth_bp = Blueprint("auth", __name__)


@auth_bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = db.get_user_by_id(user_id) if user_id else None


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(**kwargs)

    return wrapped_view


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        phone = request.form.get("phone", "").strip().replace("+", "")
        password = request.form.get("password", "")
        user = db.get_user_by_phone(phone)
        error = None
        turnstile_ok, turnstile_error = validate_turnstile_token(
            request.form.get("cf-turnstile-response", ""),
            remote_ip=request.headers.get("CF-Connecting-IP", request.remote_addr),
        )
        if not turnstile_ok:
            error = turnstile_error
        elif not user:
            error = "Nomor belum terdaftar. Kirim chat pertama ke webhook WhatsApp dulu."
        elif not check_password_hash(user["password_hash"], password):
            error = "Password salah."

        if error is None:
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            flash("Login berhasil.", "success")
            return redirect(url_for("main.dashboard"))
        flash(error, "error")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Kamu sudah logout.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/set-password", methods=["GET", "POST"])
def set_password():
    token = request.values.get("token", "").strip()
    purpose = request.values.get("purpose", "setup").strip() or "setup"

    token_data = consume_user_token(
        token,
        purpose=purpose,
        max_age=int(current_app.config["PASSWORD_TOKEN_MAX_AGE"]),
    )

    if token_data is None:
        flash("Link tidak valid atau sudah kedaluwarsa. Minta link baru lewat WhatsApp.", "error")
        return render_template("set_password.html", token=token, purpose=purpose, token_valid=False)

    user = db.get_user_by_id(int(token_data["user_id"]))
    if not user:
        flash("Akun tidak ditemukan.", "error")
        return render_template("set_password.html", token=token, purpose=purpose, token_valid=False)

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(new_password) < 10:
            flash("Password minimal 10 karakter.", "error")
        elif new_password != confirm_password:
            flash("Konfirmasi password tidak sama.", "error")
        else:
            db.update_user_password(int(user["id"]), generate_password_hash(new_password))
            session.clear()
            flash("Password berhasil disimpan. Silakan login.", "success")
            return redirect(url_for("auth.login"))

    return render_template("set_password.html", token=token, purpose=purpose, token_valid=True, user=user)
