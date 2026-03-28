from __future__ import annotations

from app import create_app
from app import db
from app.security import issue_user_token


def login_csrf(client) -> str:
    response = client.get("/login")
    html = response.get_data(as_text=True)
    marker = 'name="_csrf_token" value="'
    return html.split(marker, 1)[1].split('"', 1)[0]


def test_health_and_readiness(client):
    health = client.get("/healthz")
    ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.json["ok"] is True
    assert ready.status_code == 200
    assert ready.json["status"] == "ready"


def test_onboarding_temp_password_and_login(app, client):
    create_response = client.post(
        "/webhooks/whatsapp",
        json={"phone": "628111111111", "text": "halo", "message_id": "msg-1", "provider": "local"},
    )

    assert create_response.status_code == 200
    payload = create_response.get_json()
    assert payload["created_user"] is True
    assert payload["temporary_password"]

    csrf = login_csrf(client)
    login_response = client.post(
        "/login",
        data={"_csrf_token": csrf, "phone": "628111111111", "password": payload["temporary_password"]},
        follow_redirects=False,
    )
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith("/dashboard")


def test_transaction_flow_and_duplicate_message(app, client):
    with app.app_context():
        user_id = db.create_user(phone="628222222222", password_hash="pbkdf2:sha256:1$test$hash")
        token = issue_user_token(user_id=user_id, purpose="reset")
        assert token

    first = client.post(
        "/webhooks/whatsapp",
        json={"phone": "628222222222", "text": "+100k jualan\n+3 juta freelance\nsaldo", "message_id": "msg-2", "provider": "local"},
    )
    assert first.status_code == 200
    first_body = first.get_json()
    assert first_body["duplicate"] is False
    assert "Saldo Total" in first_body["reply_text"]
    assert "Rp 3.100.000" in first_body["reply_text"]

    duplicate = client.post(
        "/webhooks/whatsapp",
        json={"phone": "628222222222", "text": "+100k jualan\nsaldo", "message_id": "msg-2", "provider": "local"},
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["duplicate"] is True


def test_login_shows_twilio_sandbox_actions(tmp_path):
    sandbox_app = create_app(
        {
            "APP_ENV": "testing",
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": f"sqlite:///{(tmp_path / 'sandbox.db').as_posix()}",
            "ALLOW_JSON_WEBHOOKS": True,
            "ENABLE_SIMULATOR": True,
            "BASE_URL": "http://localhost:5000",
            "TWILIO_SANDBOX_ENABLED": True,
            "TWILIO_SANDBOX_JOIN_CODE": "join-demo",
            "TWILIO_SANDBOX_START_TEXT": "halo",
        }
    )
    client = sandbox_app.test_client()

    response = client.get("/login")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Gabung Sandbox WhatsApp" in html
    assert "join-demo" in html
    assert 'Kirim "halo"' in html


def test_login_shows_twilio_sandbox_setup_hint_without_join_code(tmp_path):
    sandbox_app = create_app(
        {
            "APP_ENV": "testing",
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": f"sqlite:///{(tmp_path / 'sandbox-hint.db').as_posix()}",
            "ALLOW_JSON_WEBHOOKS": True,
            "ENABLE_SIMULATOR": True,
            "BASE_URL": "http://localhost:5000",
            "TWILIO_SANDBOX_ENABLED": True,
            "TWILIO_SANDBOX_JOIN_CODE": "",
        }
    )
    client = sandbox_app.test_client()

    response = client.get("/login")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Twilio Sandbox aktif sebagian" in html
    assert "TWILIO_SANDBOX_JOIN_CODE" in html
