# FastAPI Security Events Lab

An educational REST API for ingesting security events using Python,
FastAPI, Pydantic, dependency injection, and the repository pattern.

## Architecture

- `app/schemas.py`: input validation and response schemas.
- `app/main.py`: HTTP endpoints and dependency injection.
- `app/service.py`: application use cases, independent of HTTP.
- `app/repository.py`: storage contract and in-memory implementation.
- `tests/test_events.py`: HTTP contract and validation tests.

The request flow is:

`HTTP request -> Pydantic validation -> EventService -> EventRepository`

## Run the tests

From this exercise directory:

```bash
uv sync
uv run --no-sync pytest -q
```

Alternatively:

```bash
uv run --no-sync python -m pytest -q
```

The explicit `pythonpath` pytest setting makes both commands work
with the local `app` package. This is an educational layout, not an
installable Python distribution.

## Run the API

```bash
uv run --no-sync uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation.
Use this development server only in a trusted local environment.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/events \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"evt-001","source":"firewall-01","severity":"HIGH","timestamp":"2026-10-28T09:30:00Z"}'
```

## HTTP contract

- `POST /events`: 201 on creation, 409 for duplicate identifiers.
- Invalid request bodies: 422.
- `GET /events/{event_id}`: 200 when found, 404 otherwise.

## Important limitations

This first version is **not production-ready**:

- Events are lost when the process restarts.
- Multiple processes do not share stored events.
- The duplicate check is not atomic under concurrent access.
- Authentication, authorization, rate limiting, and audit controls
  have not yet been implemented.
- Timestamp timezone information is required, but timestamp policy
  and event authenticity are not yet addressed.

The current dependency set emits a Starlette deprecation warning
concerning `httpx` and `starlette.testclient`. This is tracked as a
compatibility issue; it is not suppressed in the test configuration.

## Interview questions

1. Why separate API, application service, and repository?
2. What does `typing.Protocol` contribute to this design?
3. Why can an in-memory duplicate check fail under concurrency?
4. How would a database uniqueness constraint change the design?
5. When should a FastAPI endpoint use `def` versus `async def`?
6. How would you test authorization and idempotent retries?
