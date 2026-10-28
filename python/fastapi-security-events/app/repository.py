from typing import Protocol

from app.schemas import SecurityEvent


class DuplicateEventError(Exception):
    """Signal a domain-level uniqueness violation."""

    pass


class EventRepository(Protocol):
    """Define the storage contract without coupling services to a database."""

    def add(self, event: SecurityEvent) -> None: ...

    def get(self, event_id: str) -> SecurityEvent | None: ...


class InMemoryEventRepository:
    """Educational storage: not durable, shared, or concurrency-safe."""

    def __init__(self) -> None:
        self._events: dict[str, SecurityEvent] = {}

    def add(self, event: SecurityEvent) -> None:
        # This check is not atomic across concurrent requests.
        if event.event_id in self._events:
            raise DuplicateEventError(event.event_id)

        self._events[event.event_id] = event

    def get(self, event_id: str) -> SecurityEvent | None:
        return self._events.get(event_id)
