import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import APIKeyHeader

from app.repository import (
    DuplicateEventError,
    InMemoryEventRepository,
)
from app.schemas import SecurityEvent, SecurityEventCreate
from app.service import EventService
from app.sqlite_repository import SQLiteEventRepository


def create_app(
    database_path: str | Path | None = None,
    *,
    api_key: str | None = None,
) -> FastAPI:
    """Build an app with authenticated writes and configurable storage."""
    # Resolve configuration at startup, not during module import.
    # This keeps the ASGI module importable by test runners.
    expected_api_key = (
        os.environ.get("SECURITY_EVENTS_API_KEY")
        if api_key is None
        else api_key
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Reject missing credentials before serving requests."""
        if not expected_api_key:
            raise ValueError("SECURITY_EVENTS_API_KEY must be configured")
        yield

    app = FastAPI(
        title="Security Events Lab",
        version="0.1.0",
        lifespan=lifespan,
    )
    # The default preserves the original isolated test behavior.
    # A supplied database path enables durable, shared SQLite storage.
    repository = (
        InMemoryEventRepository()
        if database_path is None
        else SQLiteEventRepository(database_path)
    )

    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def require_api_key(
        supplied_api_key: str | None = Depends(api_key_header),
    ) -> None:
        """Authenticate event ingestion at the HTTP boundary."""
        if (
            not expected_api_key
            or supplied_api_key is None
            or not hmac.compare_digest(supplied_api_key, expected_api_key)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

    def get_service() -> EventService:
        """Inject the application service into HTTP handlers."""
        return EventService(repository)

    @app.post(
        "/events",
        response_model=SecurityEvent,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_api_key)],
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
