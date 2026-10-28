from app.repository import EventRepository
from app.schemas import SecurityEvent, SecurityEventCreate


class EventService:
    """Coordinate use cases independently of HTTP and storage details."""

    def __init__(self, repository: EventRepository) -> None:
        self.repository = repository

    def create(self, payload: SecurityEventCreate) -> SecurityEvent:
        # Keep the application boundary explicit even with identical schemas.
        event = SecurityEvent.model_validate(payload.model_dump())
        self.repository.add(event)
        return event

    def get(self, event_id: str) -> SecurityEvent | None:
        return self.repository.get(event_id)
