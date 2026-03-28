from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "APP_ENV": "testing",
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "ALLOW_JSON_WEBHOOKS": True,
            "ENABLE_SIMULATOR": True,
            "BASE_URL": "http://localhost:5000",
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()
