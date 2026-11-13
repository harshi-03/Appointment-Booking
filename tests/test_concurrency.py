"""Concurrency tests: the lock makes check-then-insert (book) and check-then-update (cancel) atomic.

Each test adds a short sleep between the "check" and the "act". That widens the race window so
the test reliably fails if the lock is removed or scoped too narrowly (e.g. the insert placed
after the lock is released). Without it, the GIL could make an unprotected implementation pass by
luck. Mutation-tested (see AI_USAGE.md entries 8-9).
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import timedelta
from itertools import combinations

from app.models import (
    AlreadyCancelledError,
    Appointment,
    AppointmentStatus,
    ConflictError,
    InvalidInputError,
)
from app.service import BookingService
from helpers import NOW, active, at, make_service, utc

THREADS = 50


class SlowDict(dict):
    """book(): sleeps while scanning existing appointments AND just before the insert lands.

    Both the scan and the insert must therefore sit inside the same critical section.
    """

    def values(self):
        snapshot = list(super().values())
        time.sleep(0.001)
        return snapshot

    def __setitem__(self, key, value):
        time.sleep(0.001)
        super().__setitem__(key, value)


class SlowStatusAppointment(Appointment):
    """cancel(): sleeps after `status` is read, before it is written.

    A plain subclass, not re-decorated: it inherits the dataclass fields, and it still imports
    cleanly when a planted bug removes frozen=True from Appointment. (Re-decorating it frozen would
    turn that bug into a collection error instead of a real test failure.)
    """

    def __getattribute__(self, name):
        value = object.__getattribute__(self, name)
        if name == "status":
            time.sleep(0.001)
        return value


def run_concurrently(task):
    """Run task(i) for i in 0..THREADS-1, all released at the same moment."""
    barrier = threading.Barrier(THREADS, timeout=10)

    def worker(i):
        barrier.wait()  # release all threads at the same moment
        return task(i)

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        return list(pool.map(worker, range(THREADS)))


def assert_invariant(service):
    """The booking rule itself, checked across the whole store: no provider has two ACTIVE
    appointments that overlap. Stronger than counting winners."""
    for a, b in combinations(active(service), 2):
        overlapping = a.start < b.end and b.start < a.end
        assert not (a.provider_id == b.provider_id and overlapping), f"invariant broken: {a} / {b}"


def try_book(service, provider_id, start, end):
    try:
        service.book(provider_id, start, end)
        return "ok"
    except ConflictError:
        return "conflict"


def test_concurrent_same_slot_single_winner():
    service = make_service()
    service._appointments = SlowDict()

    outcomes = run_concurrently(lambda _: try_book(service, "provider-a", at(10), at(11)))

    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == THREADS - 1
    assert len(active(service)) == 1
    assert len(service._appointments) == 1  # no stray records of any status
    assert_invariant(service)


def test_concurrent_partially_overlapping_bookings_single_winner():
    # Starts 10:00, 10:01, ... 10:49, each 60 minutes long: every pair overlaps, but none is an
    # exact duplicate, so a "reject identical slots" shortcut would not pass.
    service = make_service()
    service._appointments = SlowDict()

    def book(i):
        start = utc(10) + timedelta(minutes=i)
        return try_book(service, "provider-a", start, start + timedelta(hours=1))

    outcomes = run_concurrently(book)

    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == THREADS - 1
    assert len(service._appointments) == 1
    assert_invariant(service)


def test_concurrent_bookings_for_different_providers_all_succeed():
    # The opposite failure: a lock or check that is too aggressive and rejects valid bookings.
    service = make_service()
    service._appointments = SlowDict()

    outcomes = run_concurrently(lambda i: try_book(service, f"provider-{i}", at(10), at(11)))

    assert outcomes == ["ok"] * THREADS
    assert len(service._appointments) == THREADS
    assert_invariant(service)


class SignallingLock:
    """A lock that announces when a thread starts waiting for it, so the test needs no sleeps."""

    def __init__(self):
        self.inner = threading.Lock()
        self.waiting = threading.Event()

    def __enter__(self):
        self.waiting.set()
        self.inner.acquire()
        return self

    def __exit__(self, *exc):
        self.inner.release()


def test_future_check_holds_at_commit_time_not_arrival_time():
    # The current time is changing state, so "start > now" must be checked inside the lock.
    # Scenario: a request arrives while start is still in the future, waits for the lock while
    # another request holds it, and the clock passes its start during that wait.
    now = [NOW]  # 08:00
    service = BookingService(clock=lambda: now[0])
    service._lock = SignallingLock()
    outcome = {}

    def late_request():
        try:
            service.book("provider-a", at(8, 30), at(9, 30))
            outcome["result"] = "saved"
        except InvalidInputError as error:
            outcome["result"] = error.message

    service._lock.inner.acquire()  # another request is holding the lock
    worker = threading.Thread(target=late_request)
    worker.start()
    assert service._lock.waiting.wait(timeout=5)  # the late request is now queued on the lock
    now[0] = NOW + timedelta(hours=1)  # 09:00: its start (08:30) has passed while it waited
    service._lock.inner.release()
    worker.join(timeout=5)

    assert outcome["result"] == "start must be in the future (UTC)"
    assert service._appointments == {}  # nothing saved


def test_concurrent_cancel_single_winner():
    service = make_service()
    appointment = service.book("provider-a", at(10), at(11))
    stored = service._appointments[appointment.id]
    service._appointments[appointment.id] = SlowStatusAppointment(**asdict(stored))

    def cancel(_):
        try:
            service.cancel(appointment.id)
            return "ok"
        except AlreadyCancelledError:
            return "already"

    outcomes = run_concurrently(cancel)

    assert outcomes.count("ok") == 1
    assert outcomes.count("already") == THREADS - 1
    assert service._appointments[appointment.id].status is AppointmentStatus.CANCELLED
