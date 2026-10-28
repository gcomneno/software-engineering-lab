"""Contract tests for durable and concurrent SQLite event storage."""

import sqlite3
from unittest.mock import patch

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import DuplicateEventError
from app.schemas import SecurityEvent
from app.sqlite_repository import SQLiteEventRepository

TEST_API_KEY = "test-only-api-key"
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


def make_event(event_id: str = "evt-001") -> SecurityEvent:
    """Create a valid event without involving HTTP."""
    return SecurityEvent.model_validate(
        {
            "event_id": event_id,
            "source": "firewall-01",
            "severity": "HIGH",
            "timestamp": "2026-10-28T09:30:00Z",
        }
    )


def test_sqlite_round_trip(tmp_path: Path):
    """Stored events retain their validated fields."""
    repository = SQLiteEventRepository(tmp_path / "events.sqlite3")
    event = make_event()

    repository.add(event)

    assert repository.get(event.event_id) == event


def test_sqlite_missing_event(tmp_path: Path):
    """Missing records follow the repository's None contract."""
    repository = SQLiteEventRepository(tmp_path / "events.sqlite3")

    assert repository.get("missing") is None


def test_sqlite_duplicate_event(tmp_path: Path):
    """The primary key rejects a repeated event identifier."""
    repository = SQLiteEventRepository(tmp_path / "events.sqlite3")
    event = make_event()

    repository.add(event)

    try:
        repository.add(event)
    except DuplicateEventError:
        pass
    else:
        raise AssertionError("DuplicateEventError was not raised")


def test_sqlite_persists_between_repository_instances(tmp_path: Path):
    """Independent repositories observe the same database contents."""
    database_path = tmp_path / "events.sqlite3"
    first = SQLiteEventRepository(database_path)
    first.add(make_event())

    second = SQLiteEventRepository(database_path)

    assert second.get("evt-001") == make_event()


def test_sqlite_persists_between_application_instances(tmp_path: Path):
    """The HTTP layer can reuse durable storage across app instances."""
    database_path = tmp_path / "events.sqlite3"
    payload = make_event().model_dump(mode="json")

    with TestClient(create_app(database_path=database_path, api_key=TEST_API_KEY)) as first:
        assert first.post("/events", json=payload, headers=AUTH_HEADERS).status_code == 201

    with TestClient(create_app(database_path=database_path, api_key=TEST_API_KEY)) as second:
        response = second.get("/events/evt-001")

    assert response.status_code == 200
    assert response.json()["event_id"] == "evt-001"


def test_sqlite_http_duplicate_returns_conflict(tmp_path: Path):
    """A database uniqueness violation remains an HTTP 409."""
    database_path = tmp_path / "events.sqlite3"
    payload = make_event().model_dump(mode="json")

    with TestClient(create_app(database_path=database_path, api_key=TEST_API_KEY)) as client:
        first = client.post("/events", json=payload, headers=AUTH_HEADERS)
        second = client.post("/events", json=payload, headers=AUTH_HEADERS)

    assert first.status_code == 201
    assert second.status_code == 409


def test_sqlite_concurrent_duplicate_insert(tmp_path: Path):
    """Exactly one concurrent insert wins the database uniqueness race."""
    database_path = tmp_path / "events.sqlite3"
    SQLiteEventRepository(database_path)
    barrier = Barrier(2, timeout=5)

    def attempt_insert() -> str:
        # Separate instances ensure separate SQLite connections.
        repository = SQLiteEventRepository(database_path)
        barrier.wait()
        try:
            repository.add(make_event())
        except DuplicateEventError:
            return "duplicate"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt_insert) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]

    assert sorted(results) == ["created", "duplicate"]

    repository = SQLiteEventRepository(database_path)
    assert repository.get("evt-001") == make_event()


def test_sqlite_connection_closed_after_success(tmp_path: Path):
    """Repository operations must release their SQLite connections."""
    database_path = tmp_path / "events.sqlite3"
    repository = SQLiteEventRepository(database_path)

    class TrackedConnection:
        def __init__(self, real_connection):
            self.real_connection = real_connection
            self.closed = False

        def __enter__(self):
            return self.real_connection.__enter__()

        def __exit__(self, *args):
            return self.real_connection.__exit__(*args)

        def execute(self, *args, **kwargs):
            return self.real_connection.execute(*args, **kwargs)

        def close(self):
            self.closed = True
            self.real_connection.close()

    connections = []
    original_connect = repository._connect

    def tracked_connect():
        connection = TrackedConnection(original_connect())
        connections.append(connection)
        return connection

    with patch.object(repository, "_connect", side_effect=tracked_connect):
        repository.add(make_event())
        repository.get("evt-001")

    assert len(connections) == 2
    assert all(connection.closed for connection in connections)


def test_sqlite_rollback_on_integrity_failure(tmp_path: Path):
    """A rejected insert must not leave a partial transaction."""
    database_path = tmp_path / "events.sqlite3"
    repository = SQLiteEventRepository(database_path)
    repository.add(make_event())

    try:
        repository.add(make_event())
    except DuplicateEventError:
        pass
    else:
        raise AssertionError("Expected duplicate-key rejection")

    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM security_events"
        ).fetchone()[0]

    assert count == 1


def test_sqlite_non_duplicate_integrity_error(tmp_path: Path):
    """A non-primary-key integrity failure must not become HTTP 409."""
    database_path = tmp_path / "events.sqlite3"
    repository = SQLiteEventRepository(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_event
            BEFORE INSERT ON security_events
            BEGIN
                SELECT RAISE(ABORT, 'policy rejection');
            END
            """
        )

    try:
        repository.add(make_event())
    except sqlite3.IntegrityError as exc:
        assert "policy rejection" in str(exc)
    else:
        raise AssertionError("Expected non-duplicate integrity failure")


def test_sqlite_repeated_concurrent_inserts(tmp_path: Path):
    """Repeat the uniqueness race with independent identifiers."""
    for index in range(5):
        database_path = tmp_path / f"race-{index}.sqlite3"
        SQLiteEventRepository(database_path)
        barrier = Barrier(2, timeout=5)
        event_id = f"evt-race-{index}"

        def attempt():
            repository = SQLiteEventRepository(database_path)
            barrier.wait()
            try:
                repository.add(make_event(event_id))
            except DuplicateEventError:
                return "duplicate"
            return "created"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: attempt(), range(2)))

        assert sorted(results) == ["created", "duplicate"]
