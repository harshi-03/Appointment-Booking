"""Service-level tests for the booking invariant, validation, UTC and cancellation (DESIGN.md §10)."""
import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone, tzinfo

import pytest

from app.models import (
    AlreadyCancelledError,
    AppointmentStatus,
    ConflictError,
    InvalidInputError,
    NotFoundError,
)
from app.service import BookingService, _utc_now
from helpers import NOW, active, assert_rejected_unchanged, at, make_service, utc


@pytest.fixture
def service():
    return make_service()


@pytest.fixture
def booked(service):
    """Service holding one ACTIVE appointment: provider-a, 10:00-11:00 UTC."""
    appointment = service.book("provider-a", at(10), at(11))
    return service, appointment


# --- AC1: successful booking ---------------------------------------------------------------

def test_book_valid_appointment(service):
    appointment = service.book("provider-a", at(10), at(11))

    assert uuid.UUID(appointment.id).version == 4
    assert appointment.provider_id == "provider-a"
    assert appointment.start == utc(10)
    assert appointment.end == utc(11)
    assert appointment.start.utcoffset() == timedelta(0)
    assert appointment.status is AppointmentStatus.ACTIVE
    assert list(service._appointments) == [appointment.id]


# --- AC2: same-provider overlap rejected; different providers OK ---------------------------

@pytest.mark.parametrize(
    "start, end",
    [
        (at(9, 30), at(10, 30)),   # partial overlap on the left
        (at(10, 30), at(11, 30)),  # partial overlap on the right
        (at(10, 15), at(10, 45)),  # new inside existing
        (at(9, 30), at(11, 30)),   # new contains existing
        (at(10), at(11)),          # identical interval
        (at(10, 59), at(12)),      # one-minute overlap at the boundary
    ],
    ids=["partial-left", "partial-right", "inside", "contains", "identical", "one-minute"],
)
def test_same_provider_overlap_rejected(booked, start, end):
    service, _ = booked
    assert_rejected_unchanged(service, ConflictError, lambda: service.book("provider-a", start, end))


def test_conflict_detected_against_non_first_appointment(service):
    # The scan must check every stored appointment, not stop at the first one.
    service.book("provider-a", at(9), at(10))
    service.book("provider-a", at(11), at(12))
    assert_rejected_unchanged(
        service, ConflictError, lambda: service.book("provider-a", at(11, 30), at(12, 30))
    )


def test_different_providers_same_slot_allowed(booked):
    service, _ = booked
    other = service.book("provider-b", at(10), at(11))
    assert other.provider_id == "provider-b"
    assert len(active(service)) == 2


# --- AC3: adjacency allowed ----------------------------------------------------------------

def test_adjacent_after_allowed(booked):
    service, _ = booked
    service.book("provider-a", at(11), at(12))  # starts exactly when existing ends
    assert len(active(service)) == 2


def test_adjacent_before_allowed(booked):
    service, _ = booked
    service.book("provider-a", at(9), at(10))  # ends exactly when existing starts
    assert len(active(service)) == 2


# --- AC4: cancellation ---------------------------------------------------------------------

def test_cancel_frees_slot(booked):
    service, original = booked

    cancelled = service.cancel(original.id)
    assert cancelled.status is AppointmentStatus.CANCELLED
    assert service._appointments[original.id].status is AppointmentStatus.CANCELLED  # soft cancel

    rebooked = service.book("provider-a", at(10), at(11))
    assert rebooked.id != original.id
    assert [a.id for a in active(service)] == [rebooked.id]


def test_cancel_past_appointment_allowed():
    # Cancel has no time restriction (DESIGN.md §8), even after the appointment started.
    now = [NOW]
    service = BookingService(clock=lambda: now[0])
    appointment = service.book("provider-a", at(10), at(11))
    now[0] = utc(12)
    assert service.cancel(appointment.id).status is AppointmentStatus.CANCELLED


def test_returned_appointments_cannot_change_stored_state(service):
    booked = service.book("provider-a", at(10), at(11))
    with pytest.raises(FrozenInstanceError):
        booked.status = AppointmentStatus.CANCELLED
    assert service._appointments[booked.id].status is AppointmentStatus.ACTIVE

    cancelled = service.cancel(booked.id)
    with pytest.raises(FrozenInstanceError):
        cancelled.status = AppointmentStatus.ACTIVE
    assert service._appointments[booked.id].status is AppointmentStatus.CANCELLED
    assert booked.status is AppointmentStatus.ACTIVE  # cancel stored a new object, not an edit


def test_conflict_reports_the_conflicting_appointment(booked):
    service, existing = booked
    error = assert_rejected_unchanged(
        service, ConflictError, lambda: service.book("provider-a", at(10, 30), at(11, 30))
    )
    assert error.conflicting_id == existing.id


# --- Read-only verification aids: get / list_for_provider ----------------------------------

def test_get_returns_current_state(booked):
    service, appointment = booked
    assert service.get(appointment.id) == appointment
    service.cancel(appointment.id)
    assert service.get(appointment.id).status is AppointmentStatus.CANCELLED


@pytest.mark.parametrize("bad_id", ["does-not-exist", "PADDED"], ids=["unknown", "padded"])
def test_get_unknown_or_padded_id_not_found(booked, bad_id):
    service, appointment = booked
    lookup = f" {appointment.id} " if bad_id == "PADDED" else bad_id  # exact-id rule, same as cancel
    assert_rejected_unchanged(service, NotFoundError, lambda: service.get(lookup))


def test_list_for_provider_sorted_with_cancelled_and_only_that_provider(service):
    late = service.book("provider-a", at(14), at(15))
    early = service.book("provider-a", at(9), at(10))
    middle = service.book("provider-a", at(11), at(12))
    service.book("provider-b", at(10), at(11))  # other provider: excluded
    service.cancel(middle.id)

    listed = service.list_for_provider("provider-a")

    assert [a.id for a in listed] == [early.id, middle.id, late.id]  # by start
    assert [a.status for a in listed] == [
        AppointmentStatus.ACTIVE, AppointmentStatus.CANCELLED, AppointmentStatus.ACTIVE
    ]


def test_list_for_unknown_provider_is_empty(service):
    assert service.list_for_provider("nobody") == []


def test_list_for_provider_strips_like_booking(booked):
    service, appointment = booked
    assert [a.id for a in service.list_for_provider("  provider-a ")] == [appointment.id]


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_read_methods_reject_blank_ids(service, bad):
    with pytest.raises(InvalidInputError):
        service.get(bad)
    with pytest.raises(InvalidInputError):
        service.list_for_provider(bad)


def test_cancel_missing_not_found(booked):
    service, _ = booked
    error = assert_rejected_unchanged(service, NotFoundError, lambda: service.cancel(str(uuid.uuid4())))
    assert error.code == "NOT_FOUND"


def test_cancel_twice_already_cancelled(booked):
    service, appointment = booked
    service.cancel(appointment.id)
    error = assert_rejected_unchanged(
        service, AlreadyCancelledError, lambda: service.cancel(appointment.id)
    )
    assert error.code == "ALREADY_CANCELLED"


# --- AC5: invalid input rejected without changing stored bookings --------------------------

@pytest.mark.parametrize(
    "bad", ["not-a-date", "2030-13-01T10:00:00Z", "2030-01-01T25:00:00Z", 1893484800, 12.5]
)
def test_unparseable_timestamp_rejected(booked, bad):
    service, _ = booked
    assert_rejected_unchanged(service, InvalidInputError, lambda: service.book("provider-a", bad, at(13)))
    assert_rejected_unchanged(service, InvalidInputError, lambda: service.book("provider-a", at(12), bad))


@pytest.mark.parametrize(
    "naive", ["2030-01-01T12:00:00", "2030-01-01", datetime(2030, 1, 1, 12, 0)]
)
def test_naive_timestamp_rejected(booked, naive):
    service, _ = booked
    for start, end in [(naive, at(13)), (at(11), naive)]:  # naive start, then naive end
        error = assert_rejected_unchanged(
            service, InvalidInputError, lambda: service.book("provider-a", start, end)
        )
        assert "offset" in error.message


def test_out_of_range_timestamp_rejected(booked):
    service, _ = booked
    # Converting this to UTC underflows year 1 -> OverflowError must become INVALID_INPUT.
    assert_rejected_unchanged(
        service,
        InvalidInputError,
        lambda: service.book("provider-a", "0001-01-01T00:00:00+05:30", at(13)),
    )


def test_out_of_range_end_rejected(booked):
    service, _ = booked
    # Converting this to UTC overflows past year 9999 -> OverflowError must become INVALID_INPUT.
    assert_rejected_unchanged(
        service,
        InvalidInputError,
        lambda: service.book("provider-a", at(12), "9999-12-31T23:59:59-05:00"),
    )


def test_zero_duration_rejected(booked):
    service, _ = booked
    assert_rejected_unchanged(service, InvalidInputError, lambda: service.book("provider-a", at(12), at(12)))


def test_negative_duration_rejected(booked):
    service, _ = booked
    assert_rejected_unchanged(service, InvalidInputError, lambda: service.book("provider-a", at(13), at(12)))


@pytest.mark.parametrize("bad_provider", ["", "   ", None, 123])
def test_blank_provider_rejected(booked, bad_provider):
    service, _ = booked
    assert_rejected_unchanged(
        service, InvalidInputError, lambda: service.book(bad_provider, at(12), at(13))
    )


@pytest.mark.parametrize(
    "provider_id, start, end",
    [(None, at(12), at(13)), ("provider-a", None, at(13)), ("provider-a", at(12), None), (None, None, None)],
    ids=["no-provider", "no-start", "no-end", "nothing"],
)
def test_missing_fields_rejected(booked, provider_id, start, end):
    service, _ = booked
    error = assert_rejected_unchanged(
        service, InvalidInputError, lambda: service.book(provider_id, start, end)
    )
    assert "required" in error.message


def test_unencodable_provider_id_rejected(booked):
    service, _ = booked
    # A lone surrogate can't be encoded as UTF-8, so it could never be returned in a JSON response.
    assert_rejected_unchanged(
        service, InvalidInputError, lambda: service.book("\ud800", at(12), at(13))
    )


class _NoOffset(tzinfo):
    """A tzinfo that is present but gives no offset: still ambiguous, so still 'naive'."""

    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return None


def test_timezone_without_offset_rejected_as_naive(booked):
    service, _ = booked
    ambiguous = datetime(2030, 1, 1, 12, 0, tzinfo=_NoOffset())
    error = assert_rejected_unchanged(
        service, InvalidInputError, lambda: service.book("provider-a", ambiguous, at(13))
    )
    assert error.field == "start"
    # Check the *reason*: without the offset check, Python silently treats the value as local
    # machine time, and it could then be rejected for an unrelated reason (e.g. "in the past").
    assert "offset" in error.message


def test_naive_clock_is_a_server_error_not_bad_input():
    # A misconfigured clock must not be reported to the client as their mistake.
    service = BookingService(clock=lambda: datetime(2030, 1, 1, 8, 0))  # naive
    with pytest.raises(RuntimeError, match="timezone-aware"):
        service.book("provider-a", at(10), at(11))
    assert service._appointments == {}


@pytest.mark.parametrize(
    "provider_id, start, end, field",
    [
        ("  ", at(10), at(11), "provider_id"),
        ("provider-a", "nope", at(11), "start"),
        ("provider-a", at(10), "2030-01-01T11:00:00", "end"),
        ("provider-a", at(11), at(10), "end"),
        ("provider-a", at(7), at(9), "start"),
    ],
    ids=["blank-provider", "bad-start", "naive-end", "negative-duration", "past-start"],
)
def test_invalid_input_names_the_field(service, provider_id, start, end, field):
    error = assert_rejected_unchanged(
        service, InvalidInputError, lambda: service.book(provider_id, start, end)
    )
    assert error.field == field


def test_echoed_input_is_truncated(service):
    error = assert_rejected_unchanged(service, NotFoundError, lambda: service.cancel("x" * 5000))
    assert len(error.message) < 100


def test_cancel_uses_exact_id(booked):
    service, appointment = booked
    assert_rejected_unchanged(service, NotFoundError, lambda: service.cancel(f" {appointment.id} "))
    assert service._appointments[appointment.id].status is AppointmentStatus.ACTIVE


@pytest.mark.parametrize("bad_id", ["", "   ", None])
def test_blank_appointment_id_rejected(booked, bad_id):
    service, _ = booked
    assert_rejected_unchanged(service, InvalidInputError, lambda: service.cancel(bad_id))


# --- Provider id normalisation -------------------------------------------------------------

def test_provider_id_whitespace_normalised(booked):
    service, _ = booked
    # Same provider with surrounding whitespace must still conflict...
    assert_rejected_unchanged(
        service, ConflictError, lambda: service.book("  provider-a ", at(10, 30), at(11, 30))
    )
    # ...and is stored in stripped form.
    assert service.book("  provider-c  ", at(10), at(11)).provider_id == "provider-c"


# --- UTC handling --------------------------------------------------------------------------

def test_offset_converted_to_utc(service):
    appointment = service.book("provider-a", "2030-01-01T15:30:00+05:30", "2030-01-01T16:30:00+05:30")
    assert appointment.start == utc(10)
    assert appointment.end == utc(11)
    assert appointment.start.tzinfo == timezone.utc


def test_cross_offset_overlap_conflicts(booked):
    service, _ = booked  # 10:00-11:00Z
    # 06:30-07:30 at -04:00 is 10:30-11:30Z: same moment, different offset -> must conflict.
    assert_rejected_unchanged(
        service,
        ConflictError,
        lambda: service.book("provider-a", "2030-01-01T06:30:00-04:00", "2030-01-01T07:30:00-04:00"),
    )
    # 15:45-16:15 at +05:30 is 10:15-10:45Z -> must conflict.
    assert_rejected_unchanged(
        service,
        ConflictError,
        lambda: service.book("provider-a", "2030-01-01T15:45:00+05:30", "2030-01-01T16:15:00+05:30"),
    )
    # 16:30+05:30 is 11:00Z: adjacent across offsets -> allowed.
    service.book("provider-a", "2030-01-01T16:30:00+05:30", "2030-01-01T17:30:00+05:30")


# --- Future-only bookings (fixed clock NOW = 08:00Z) ---------------------------------------

def test_start_in_past_rejected(booked):
    service, _ = booked  # existing booking present, so "unchanged" covers more than "nothing inserted"
    error = assert_rejected_unchanged(
        service, InvalidInputError, lambda: service.book("provider-a", at(7), at(9))
    )
    assert error.message == "start must be in the future (UTC)"


def test_start_exactly_now_rejected(booked):
    service, _ = booked
    assert_rejected_unchanged(service, InvalidInputError, lambda: service.book("provider-a", at(8), at(9)))


def test_default_clock_is_utc_aware():
    # The production clock (no injection) must be the UTC-aware one. Only its *offset* is checked,
    # never its value or any booking against it, so no test depends on what time it is.
    assert BookingService()._clock is _utc_now
    assert _utc_now().utcoffset() == timedelta(0)


def test_booking_is_all_or_nothing_even_if_clock_moves():
    # The clock jumps 1h on every read. The time check must happen exactly once, before the insert:
    # the first read (08:00) is before start (08:30), so the booking must succeed and be saved.
    # A second read after the insert (09:00) would reject a booking that was already saved.
    ticks = (NOW + timedelta(hours=h) for h in range(100))
    service = BookingService(clock=lambda: next(ticks))
    appointment = service.book("provider-a", at(8, 30), at(9, 30))
    assert list(service._appointments) == [appointment.id]


def test_start_just_after_now_allowed(service):
    appointment = service.book("provider-a", "2030-01-01T08:00:00.000001Z", at(9))
    assert appointment.start == utc(8) + timedelta(microseconds=1)
