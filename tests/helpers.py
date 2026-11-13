"""Shared test helpers. Tests never depend on the real clock."""
from datetime import datetime, timezone

import pytest

from app.models import AppointmentStatus
from app.service import BookingService

NOW = datetime(2030, 1, 1, 8, 0, tzinfo=timezone.utc)


def at(hour: int, minute: int = 0) -> str:
    """ISO-8601 UTC timestamp on the fixed test day (after NOW for hour >= 8)."""
    return f"2030-01-01T{hour:02d}:{minute:02d}:00Z"


def utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2030, 1, 1, hour, minute, tzinfo=timezone.utc)


def make_service() -> BookingService:
    return BookingService(clock=lambda: NOW)


def snapshot(service: BookingService) -> dict:
    # Appointments are frozen and cancel() stores a replaced copy, so copying the dict is enough:
    # any change shows up as a different (or new/missing) value.
    return dict(service._appointments)


def active(service: BookingService) -> list:
    return [a for a in service._appointments.values() if a.status is AppointmentStatus.ACTIVE]


def assert_rejected_unchanged(service: BookingService, error: type, call):
    """Assert `call` raises `error` and leaves stored bookings exactly as they were."""
    before = snapshot(service)
    with pytest.raises(error) as excinfo:
        call()
    assert snapshot(service) == before
    return excinfo.value
