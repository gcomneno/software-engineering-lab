import pytest
from fastapi.testclient import TestClient

from app.main import create_app

TEST_API_KEY = "test-only-api-key"
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def client():
    """Give each test a fresh application and isolated event storage."""
    with TestClient(create_app(api_key=TEST_API_KEY)) as test_client:
        yield test_client


@pytest.fixture
def valid_event():
    return {
        "event_id": "evt-001",
        "source": "firewall-01",
        "severity": "HIGH",
        "timestamp": "2026-10-28T09:30:00Z",
    }


def test_create_event(client, valid_event):
    response = client.post("/events", json=valid_event, headers=AUTH_HEADERS)

    assert response.status_code == 201
    assert response.json()["event_id"] == "evt-001"


def test_get_event(client, valid_event):
    client.post("/events", json=valid_event, headers=AUTH_HEADERS)

    response = client.get("/events/evt-001")

    assert response.status_code == 200
    assert response.json()["severity"] == "HIGH"


def test_invalid_severity(client, valid_event):
    valid_event["severity"] = "EXTREME"

    response = client.post("/events", json=valid_event, headers=AUTH_HEADERS)

    assert response.status_code == 422


def test_missing_required_field(client, valid_event):
    del valid_event["source"]

    response = client.post("/events", json=valid_event, headers=AUTH_HEADERS)

    assert response.status_code == 422


def test_unexpected_field(client, valid_event):
    valid_event["unexpected"] = "value"

    response = client.post("/events", json=valid_event, headers=AUTH_HEADERS)

    assert response.status_code == 422


def test_duplicate_event(client, valid_event):
    """The current API contract rejects duplicate identifiers with 409."""
    first = client.post("/events", json=valid_event, headers=AUTH_HEADERS)
    second = client.post("/events", json=valid_event, headers=AUTH_HEADERS)

    assert first.status_code == 201
    assert second.status_code == 409


def test_event_not_found(client):
    response = client.get("/events/missing")

    assert response.status_code == 404


def test_timestamp_requires_timezone(client, valid_event):
    valid_event["timestamp"] = "2026-10-28T09:30:00"

    response = client.post("/events", json=valid_event, headers=AUTH_HEADERS)

    assert response.status_code == 422


def test_state_isolated_between_clients(valid_event):
    """Different application instances must not share in-memory state."""
    with TestClient(create_app(api_key=TEST_API_KEY)) as first:
        assert first.post("/events", json=valid_event, headers=AUTH_HEADERS).status_code == 201

    with TestClient(create_app(api_key=TEST_API_KEY)) as second:
        assert second.get("/events/evt-001").status_code == 404
