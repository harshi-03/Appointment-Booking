"""BookingService: owns every booking rule (validation, UTC, overlap invariant, locking).

Invariant: for any provider, no two ACTIVE appointments overlap, using half-open
intervals [start, end). See DESIGN.md §5.
"""
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Optional

from app.models import (
    AlreadyCancelledError,
    Appointment,
    AppointmentStatus,
    ConflictError,
    InvalidInputError,
    NotFoundError,
)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _preview(value: str, limit: int = 40) -> str:
    """Shorten client-supplied text before echoing it back in an error message."""
    return value if len(value) <= limit else value[:limit] + "..."


def _require_id(value: object, field: str) -> str:
    """Validate an identifier and return it stripped. Raise if missing, blank or not encodable.

    The UTF-8 check matters: a lone surrogate (JSON escape "\\ud800") is a valid Python str
    but can't be written into a JSON response. Rejecting it here, before anything is saved,
    prevents "booking saved, then 500".
    """
    if value is None:
        raise InvalidInputError(f"{field} is required", field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{field} must be a non-blank string", field)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidInputError(f"{field} contains characters that are not valid Unicode", field) from None
    return value.strip()


def _parse_utc(value: object, field: str) -> datetime:
    """Parse an ISO-8601 string (or aware datetime) and convert it to UTC.

    Naive values are rejected because their moment in time is ambiguous.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise InvalidInputError(f"{field} is required", field)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            raise InvalidInputError(f"{field} is not a valid ISO-8601 timestamp", field) from None
    else:
        raise InvalidInputError(f"{field} must be an ISO-8601 string", field)

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidInputError(
            f"{field} must include a UTC offset (e.g. 'Z' or '+05:30'); naive timestamps are ambiguous",
            field,
        )
    try:
        return parsed.astimezone(timezone.utc)
    except OverflowError:
        raise InvalidInputError(f"{field} is outside the representable UTC range", field) from None


def _overlaps(start: datetime, end: datetime, other: Appointment) -> bool:
    # Half-open [start, end): strict '<' so adjacent intervals do not overlap.
    return start < other.end and other.start < end


class BookingService:
    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock: Clock = clock or _utc_now
        self._appointments: dict[str, Appointment] = {}
        # Guards check-then-insert in book() and read-modify-write in cancel().
        self._lock = threading.Lock()

    def _now(self) -> datetime:
        """Current time in UTC. A naive clock is a server misconfiguration, not bad client input."""
        now = self._clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise RuntimeError("BookingService clock must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)

    def book(self, provider_id: object, start: object, end: object) -> Appointment:
        # Request-only checks: they depend on nothing that changes, so they run before the lock.
        provider = _require_id(provider_id, "provider_id")
        start_utc = _parse_utc(start, "start")
        end_utc = _parse_utc(end, "end")
        if end_utc <= start_utc:
            raise InvalidInputError("end must be after start (duration must be positive)", "end")

        # Checks on changing state (the current time, stored appointments) and the insert are
        # one atomic step. The time check sits inside the lock so it holds when the booking is
        # committed, not when the request arrived: a request can wait here while its start passes.
        with self._lock:
            if start_utc <= self._now():
                raise InvalidInputError("start must be in the future (UTC)", "start")
            for existing in self._appointments.values():
                if (
                    existing.provider_id == provider
                    and existing.status is AppointmentStatus.ACTIVE
                    and _overlaps(start_utc, end_utc, existing)
                ):
                    raise ConflictError(
                        f"provider {_preview(provider)} already has an active appointment "
                        f"{existing.id} overlapping this time",
                        existing.id,
                    )
            appointment = Appointment(
                id=str(uuid.uuid4()),
                provider_id=provider,
                start=start_utc,
                end=end_utc,
            )
            self._appointments[appointment.id] = appointment
        return appointment  # frozen: safe to hand out

    def _find(self, appointment_id: str) -> Appointment:
        """Exact-id lookup shared by cancel() and get(). The caller holds the lock.

        The id is looked up exactly as received, never stripped, so " <id> " doesn't match <id>.
        """
        appointment = self._appointments.get(appointment_id)
        if appointment is None:
            raise NotFoundError(f"appointment {_preview(appointment_id)} not found")
        return appointment

    def cancel(self, appointment_id: object) -> Appointment:
        _require_id(appointment_id, "appointment_id")  # request-only check, before the lock
        with self._lock:
            appointment = self._find(appointment_id)
            if appointment.status is AppointmentStatus.CANCELLED:
                raise AlreadyCancelledError(f"appointment {_preview(appointment_id)} is already cancelled")
            cancelled = replace(appointment, status=AppointmentStatus.CANCELLED)
            self._appointments[appointment_id] = cancelled
        return cancelled

    # --- Read-only verification aids (no rules; see README "Read endpoints") ----------------

    def get(self, appointment_id: object) -> Appointment:
        """One appointment by its exact id (same lookup rule as cancel)."""
        _require_id(appointment_id, "appointment_id")
        with self._lock:
            return self._find(appointment_id)

    def list_for_provider(self, provider_id: object) -> list[Appointment]:
        """All of a provider's appointments (ACTIVE and CANCELLED), ordered by start.

        Providers aren't registered, so an unknown provider simply has no appointments.
        The id is stripped, matching how provider_id is stored on booking.
        """
        provider = _require_id(provider_id, "provider_id")
        with self._lock:
            appointments = [a for a in self._appointments.values() if a.provider_id == provider]
        return sorted(appointments, key=lambda a: (a.start, a.end))
