"""Authentication contract tests for the HTTP boundary."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


TEST_API_KEY = "test-only-api-key"
VALID_EVENT = {
    "event_id": "evt-auth-001",
    "source": "firewall-01",
    "severity": "HIGH",
    "timestamp": "2026-10-28T09:30:00Z",
}


@pytest.fixture
def client():
    """Provide an isolated app with a non-production test credential."""
    with TestClient(create_app(api_key=TEST_API_KEY)) as test_client:
        yield test_client


def test_valid_api_key_allows_post(client):
    response = client.post(
        "/events",
        json=VALID_EVENT,
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 201


def test_missing_api_key_returns_401(client):
    assert client.post("/events", json=VALID_EVENT).status_code == 401


def test_invalid_api_key_returns_401(client):
    response = client.post(
        "/events",
        json=VALID_EVENT,
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401
    assert TEST_API_KEY not in response.text


def test_get_remains_public(client):
    assert client.get("/events/missing").status_code == 404


def test_missing_configuration_prevents_startup(monkeypatch):
    """The app is importable but cannot start without a secret."""
    monkeypatch.delenv("SECURITY_EVENTS_API_KEY", raising=False)
    with pytest.raises(ValueError, match="must be configured"):
        with TestClient(create_app()):
            pass


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("SECURITY_EVENTS_API_KEY", TEST_API_KEY)
    with TestClient(create_app()) as client:
        response = client.post(
            "/events",
            json=VALID_EVENT,
            headers={"X-API-Key": TEST_API_KEY},
        )
    assert response.status_code == 201


def test_empty_explicit_api_key_prevents_startup():
    with pytest.raises(ValueError, match="must be configured"):
        with TestClient(create_app(api_key="")):
            pass
