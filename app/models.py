"""Domain model and domain errors for the booking service."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class AppointmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Appointment:
    """Immutable: objects handed to callers can't be used to change stored state.

    Cancelling stores a new copy with status CANCELLED (dataclasses.replace).
    """

    id: str
    provider_id: str
    start: datetime  # tz-aware, UTC
    end: datetime  # tz-aware, UTC
    status: AppointmentStatus = AppointmentStatus.ACTIVE


class BookingError(Exception):
    """Base class for domain errors. Each subclass has a stable machine-readable code."""

    code = "BOOKING_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputError(BookingError):
    code = "INVALID_INPUT"

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.field = field  # which input was wrong, exposed to clients as error.field


class ConflictError(BookingError):
    code = "CONFLICT"

    def __init__(self, message: str, conflicting_id: Optional[str] = None) -> None:
        super().__init__(message)
        # Exposed as error.conflicting_appointment_id so clients needn't parse the message.
        self.conflicting_id = conflicting_id


class NotFoundError(BookingError):
    code = "NOT_FOUND"


class AlreadyCancelledError(BookingError):
    code = "ALREADY_CANCELLED"
