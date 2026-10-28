"""SQLite implementation of the security event repository contract."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from app.repository import DuplicateEventError
from app.schemas import SecurityEvent


class SQLiteEventRepository:
    """Persist events in a SQLite database shared through a file path."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        """Create an independent connection for each repository operation."""
        return sqlite3.connect(self.database_path, timeout=5.0)

    def _initialize_schema(self) -> None:
        """Create the table once and always close the connection."""
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS security_events (
                        event_id TEXT PRIMARY KEY,
                        source TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                    """
                )

    def add(self, event: SecurityEvent) -> None:
        """Commit valid inserts and translate only duplicate-key errors."""
        with closing(self._connect()) as connection:
            with connection:
                try:
                    # The database enforces uniqueness atomically.
                    connection.execute(
                        """
                        INSERT INTO security_events
                            (event_id, source, severity, timestamp)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            event.event_id,
                            event.source,
                            event.severity.value,
                            event.timestamp.isoformat(),
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    # A primary-key conflict is a domain-level duplicate.
                    # Other integrity errors must remain distinguishable.
                    if (
                        exc.sqlite_errorcode
                        == sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY
                    ):
                        raise DuplicateEventError(event.event_id) from exc
                    raise

    def get(self, event_id: str) -> SecurityEvent | None:
        """Read an event using a parameterized SQL query."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT event_id, source, severity, timestamp
                FROM security_events
                WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()

        if row is None:
            return None

        # Pydantic reconstructs and validates the public domain schema.
        return SecurityEvent.model_validate(
            {
                "event_id": row[0],
                "source": row[1],
                "severity": row[2],
                "timestamp": datetime.fromisoformat(row[3]),
            }
        )
