from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Severity(str, Enum):
    """Restrict severity to values accepted by the API contract."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityEventCreate(BaseModel):
    """Validate untrusted input before it reaches application logic."""

    # Reject unknown fields instead of silently ignoring client mistakes.
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    severity: Severity
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Reject ambiguous timestamps without timezone information."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class SecurityEvent(SecurityEventCreate):
    """Represent an event returned by the API in this first iteration."""

    pass
