from fastapi import Depends, FastAPI, HTTPException, status

from app.repository import (
    DuplicateEventError,
    InMemoryEventRepository,
)
from app.schemas import SecurityEvent, SecurityEventCreate
from app.service import EventService


def create_app() -> FastAPI:
    """Build an isolated application instance for each test fixture."""
    app = FastAPI(title="Security Events Lab", version="0.1.0")
    # This repository belongs to one application instance only.
    repository = InMemoryEventRepository()

    def get_service() -> EventService:
        """Inject the application service into HTTP handlers."""
        return EventService(repository)

    @app.post(
        "/events",
        response_model=SecurityEvent,
        status_code=status.HTTP_201_CREATED,
    )
    def create_event(
        payload: SecurityEventCreate,
        service: EventService = Depends(get_service),
    ) -> SecurityEvent:
        try:
            return service.create(payload)
        except DuplicateEventError as exc:
            # Translate a domain error into an HTTP response at the edge.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Event already exists",
            ) from exc

    @app.get("/events/{event_id}", response_model=SecurityEvent)
    def get_event(
        event_id: str,
        service: EventService = Depends(get_service),
    ) -> SecurityEvent:
        event = service.get(event_id)

        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )

        return event

    return app


app = create_app()
