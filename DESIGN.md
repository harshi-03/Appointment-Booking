# Design: Conflict-Safe Booking & Cancellation

## 1. Purpose & scope
A small in-memory service that books appointments for providers and cancels them, guaranteeing that a
provider is never booked for overlapping active appointments. No starter project was supplied, so
this is the minimal-service fallback described in the brief.

**In scope:** booking with conflict detection, cancellation, input validation, in-memory storage,
automated tests. Two **read-only verification aids** (get one appointment; list a provider's
appointments) let reviewers observe the effects of book/cancel. They add no rules (README "Read endpoints").
**Out of scope:** frontend, authentication, notifications, recurring availability / working hours,
calendar integration, deployment, a database, non-UTC time-zone handling, rescheduling, a provider
registry, search/filtering/paging.

## 2. Service boundary
```
HTTP client ──► app/api.py (FastAPI) ──► app/service.py (BookingService) ──► in-memory dict
                thin adapter:              owns ALL rules: validation, UTC
                request → call,            normalisation, overlap invariant,
                domain error → HTTP        locking, cancellation
```
- `BookingService` has no FastAPI dependency and is tested directly.
- `api.py` contains no business rules. It forwards raw input and maps domain errors to status codes.
- State lives only in process memory, inside the service instance.

## 3. Data model
`app/models.py`
```python
class AppointmentStatus(str, Enum):  ACTIVE = "ACTIVE"; CANCELLED = "CANCELLED"

@dataclass(frozen=True)
class Appointment:
    id: str               # server-generated uuid4
    provider_id: str
    start: datetime       # tz-aware, UTC
    end: datetime         # tz-aware, UTC
    status: AppointmentStatus
```
`Appointment` is **immutable**. Objects returned to callers can't be used to change stored state, and
cancelling stores a new copy with `status=CANCELLED` (`dataclasses.replace`).
Domain errors, each with a stable `code`: `InvalidInputError` (`INVALID_INPUT`, plus the offending
`field`), `ConflictError` (`CONFLICT`), `NotFoundError` (`NOT_FOUND`), `AlreadyCancelledError` (`ALREADY_CANCELLED`).

## 4. API
**Service:** `BookingService(clock=None)`, where `clock` is an optional zero-argument callable returning an
aware UTC `datetime`. It defaults to `datetime.now(timezone.utc)`; tests inject a fixed time. A clock that
returns a naive value is a server misconfiguration. It raises `RuntimeError`, which becomes a generic `500`,
not a client error.
`book(provider_id, start, end) -> Appointment` and `cancel(appointment_id) -> Appointment`.
Both raise the domain errors above.

**HTTP:**
| Method & path | Body | Success | Errors |
|---|---|---|---|
| `POST /appointments` | `{"provider_id", "start", "end"}`, ISO-8601 strings | `201` + appointment | `422 INVALID_INPUT`, `409 CONFLICT` |
| `POST /appointments/{id}/cancel` | none | `200` + appointment (`status: CANCELLED`) | `422 INVALID_INPUT` (blank id), `404 NOT_FOUND`, `409 ALREADY_CANCELLED` |
| `GET /appointments/{id}` (read-only) | none | `200` + appointment | `422 INVALID_INPUT` (blank id), `404 NOT_FOUND` |
| `GET /providers/{provider_id}/appointments` (read-only) | none | `200` + list, ACTIVE and CANCELLED, sorted by `start`; `[]` if unknown | `422 INVALID_INPUT` (blank id) |

The read methods (`get`, `list_for_provider`) take the same lock, so they never see a half-applied
change. They apply the write side's ID rules: an exact match for appointment IDs, and stripping for provider IDs.

- **Appointment JSON:** `{"id", "provider_id", "start", "end", "status"}`, with timestamps in UTC ending in `Z`.
- **One error format for every failure:** `{"error": {"code", "message", "field"?}}`. This follows the Microsoft REST
  guidelines' shape.
  | Source | Status → `code` |
  |---|---|
  | Service rules | 422 `INVALID_INPUT` (+ `field`) · 409 `CONFLICT` (+ `conflicting_appointment_id`) · 404 `NOT_FOUND` · 409 `ALREADY_CANCELLED` |
  | Request parsing: wrong JSON type, unknown field, malformed or undecodable body | 422 `INVALID_INPUT` (`field` = the input, or `body`) |
  | Unknown route / wrong method / any other framework 400 | 404 `NOT_FOUND` / 405 `METHOD_NOT_ALLOWED` (`Allow` header kept) / 400 `BAD_REQUEST` |
  | Unexpected server fault | 500 `INTERNAL_ERROR`, generic message, no details |
- **Request fields** are optional strings, and unknown fields are rejected (`extra="forbid"`). The service does all
  real validation. Echoed client input is shortened to 40 characters.
- **Appointment IDs are matched exactly** (no trimming): any unknown ID gives `NOT_FOUND`, and `" <id> "` doesn't
  match `<id>`.

## 5. Booking invariant
> For any provider, no two **ACTIVE** appointments overlap in time.

- Intervals are half-open: `[start, end)`.
- Two intervals overlap iff `a.start < b.end and b.start < a.end` (strict `<`).
- So **adjacent** appointments (`a.end == b.start`) do not overlap and are allowed.
- **CANCELLED** appointments are ignored by the check, so a cancelled slot can be rebooked.
- Only appointments with the **same `provider_id`** are compared. Different providers never conflict.

## 6. Validation & UTC
`book` runs these steps in order:
1. `provider_id` must be a non-empty string after stripping whitespace, and encodable as UTF-8 (a lone
   surrogate such as JSON `"\ud800"` could never be written back in a response), otherwise `INVALID_INPUT`. It is
   **stored and compared in stripped form**, so `"provider-a "` and `"provider-a"` are the same provider
   and can't double-book each other.
2. Parse `start` and `end` as ISO-8601 (`Z` accepted). Unparseable or missing gives `INVALID_INPUT`.
3. **No offset (naive) gives `INVALID_INPUT`.** The zone is ambiguous, and guessing could misplace a booking.
4. **Any explicit offset is converted to UTC** (e.g. `10:00+05:30` becomes `04:30Z`). Everything after
   this step works on UTC values. A value that can't be represented in UTC (e.g. `0001-01-01T00:00+05:30`,
   which raises `OverflowError`) gives `INVALID_INPUT`, not a 500.
5. `end > start`, otherwise `INVALID_INPUT` (non-positive duration).
6. Acquire the lock. Inside it, **future-only:** `start > clock()` (strict), otherwise `INVALID_INPUT`
   with the message `"start must be in the future (UTC)"`. A start exactly equal to now is rejected.
   The clock is read **inside the lock**, at commit time, not when the request arrived. A request can
   wait for the lock while its start passes, and it must not then be saved.
7. Still inside the lock: check for overlap against the provider's ACTIVE appointments (`CONFLICT` if any),
   insert, and release the lock.

`cancel` rejects a missing or blank id with `INVALID_INPUT` (whitespace is stripped only for that check), then
under the lock looks up the id exactly as received and returns
`NOT_FOUND` or `ALREADY_CANCELLED`, or sets `status = CANCELLED`.

Every rejection happens **before any write**, so a rejected request leaves stored bookings unchanged.

## 7. Concurrency & persistence
- **Persistence:** a `dict[str, Appointment]` on the service instance. One instance is created at app
  startup and shared by all requests.
- **Concurrency:** FastAPI runs sync (`def`) handlers in a threadpool, so two requests for the same slot
  can interleave between "check" and "insert". One `threading.Lock` in `BookingService` wraps the
  conflict check **and** the insert as a single critical section. It also wraps the read-modify-write in
  `cancel`.
- **Why the lock is in the service, not around individual storage operations:** locking "find overlaps"
  and "insert" separately would release the lock between them. Two requests could both see "no
  conflict" and both insert. The whole check-then-act sequence must be atomic.
- **What runs where:** checks that depend only on the request (ID present, parsing, UTC
  conversion, `end > start`) run *before* the lock. Anything that depends on **changing state** runs
  *inside* it. That covers the current time (`start > now`) as well as stored appointments (overlaps,
  current status).
- **Tests (5, at the service level, where the lock lives):** ~50 threads released together by a
  `threading.Barrier` (1) book the same slot, (2) book partly overlapping slots, (3) book the same slot for
  different providers, or (4) cancel the same appointment. Exactly one wins in (1), (2) and (4); all succeed in
  (3). (5) A request waits for the lock while its start time passes and must be rejected, not saved. After
  each, a whole-store check confirms that no two ACTIVE appointments of a provider overlap. The tests inject
  short sleeps inside the critical section, so a missing or too-narrow lock fails reliably.
- A single global lock was chosen over per-provider locks because it is obviously correct, and contention
  is irrelevant at this scale.

## 8. Assumptions
- All timestamps are stored, compared and returned in UTC. Offset inputs are converted; naive inputs are rejected.
- **Bookings must start in the future** (`start > now`, UTC). The brief is silent on this, so it was chosen as
  realistic behaviour. Only `start` is checked; an appointment whose start is in the future may still
  be in progress later. There is no maximum duration and no booking-horizon limit.
- Cancelling is allowed regardless of time, including for appointments that have already started.
- Appointment IDs are server-generated uuid4 strings. `provider_id` is an opaque caller-supplied string;
  providers are not pre-registered.
- Cancellation is a status change, not a delete. The record remains, and cancelling is not reversible.
- Re-booking an identical slot after cancellation creates a new appointment with a new ID.

## 9. Tradeoffs & limitations
| Limitation | Impact | Follow-up |
|---|---|---|
| In-memory only | Data is lost on restart | Persist in a DB |
| Lock is per-process | Running several uvicorn workers or instances would break the invariant | DB-level guarantee, e.g. a Postgres `EXCLUDE USING gist (provider_id WITH =, tstzrange(start,end,'[)') WITH &&) WHERE status='ACTIVE'` |
| Global lock | Serialises all providers | Per-provider locks if contention matters |
| O(n) overlap scan | Fine at prototype scale | Index by provider / interval tree |
| No idempotency keys | A retried `POST` after a timeout may hit `CONFLICT` against its own booking | `Idempotency-Key` header |
| Cancelled records kept forever | Memory grows without bound | Archive or purge once persistence exists |
| Future-only rule uses the server clock | Clock skew could accept or reject bookings near "now" | Use a trusted time source if it matters |
| No buffers between appointments | Back-to-back bookings are always allowed | Optional per-provider buffer |
| No provider existence check | Any non-blank `provider_id` is accepted | Validate against a provider registry |
| Errors carry no request/trace ID; custom envelope rather than RFC 9457 `problem+json` | Harder to correlate a client's error with server logs | Add a request-ID middleware; adopt RFC 9457 if clients expect it |

**Alternatives considered and rejected:**
- **`duration_minutes` instead of `end`.** Rejected because `start`/`end` maps directly onto the `[start, end)`
  rule and avoids int/float/bool parsing edge cases.
- **A required `client_id`.** Rejected because no rule uses it, and the brief's "identifiers" are covered by
  the provider and appointment IDs.
- **A separate store class.** Rejected because it would be a dict with no rules, and it invites locking
  at the wrong level.
- **List/GET endpoints as product features.** Not built as features. They were first left out as
  outside the booking-and-cancel slice, then added in a limited form as **read-only verification aids**:
  no search, paging or provider listing, and no new rules.
- **Per-provider locks.** Rejected as unnecessary at this scale.
- **A `docs/` folder for DESIGN/AI_USAGE.** Rejected: the docs stay in the repo root, where the README,
  `CLAUDE.md` and the review tooling already point.

## 10. Requirements traceability
Every rejection test snapshots the store before the call and asserts it is unchanged afterwards (AC5).
`scripts/mutation_check.py` plants 37 deliberate bugs, one at a time, in a temporary copy, and requires a test to
genuinely fail for each one: **37/37 caught**. Run `pytest -v` for the full list of test names.

| Requirement | Design | Representative tests (file) |
|---|---|---|
| AC1 valid booking | §4, §6 | `test_book_valid_appointment`, `test_api_book_201` (service, api) |
| AC2 overlap rejected; different providers OK | §5 | `test_same_provider_overlap_rejected` (6 shapes), `test_different_providers_same_slot_allowed` (service) |
| AC3 adjacency allowed | §5 | `test_adjacent_after_allowed`, `test_adjacent_before_allowed` (service) |
| AC4 cancel frees slot; clear results | §4, §5 | `test_cancel_frees_slot`, `test_cancel_missing_not_found`, `test_cancel_twice_already_cancelled` (service, api) |
| AC5 invalid input rejected, store unchanged | §6 | `test_unparseable_timestamp_rejected`, `test_naive_timestamp_rejected`, `test_zero_duration_rejected`, `test_blank_provider_rejected`, `test_missing_fields_rejected`, … (service, api) |
| UTC handling and future-only rule | §6, §8 | `test_offset_converted_to_utc`, `test_cross_offset_overlap_conflicts`, `test_start_in_past_rejected` (service) |
| AC6 concurrency | §7 | 5 tests: same slot (50 threads), partial overlaps, different providers, parallel cancel, time passing while waiting for the lock (concurrency) |
| Error format, read-only endpoints | §4 | `test_api_*` status/code tests, `test_get_*`, `test_list_*` (api, service) |
| AC7 AI use recorded | n/a | `AI_USAGE.md` |
