# Appointment Booking: Conflict-Safe Booking & Cancellation

A small in-memory FastAPI service that books and cancels appointments, guaranteeing that a provider
is never double-booked. No starter project was supplied, so this is the minimal-service fallback
from the brief. There is no frontend and no database.

**Scope note:** the product is two operations, **book** and **cancel**, in three source files. Everything else here exists
to **verify** that work, not to add features:
- two read-only `GET` endpoints, so the rules can be seen working from Swagger (see "Read endpoints")
- Swagger example bodies
- a planted-bug script (`scripts/mutation_check.py`)
- the AI-assistant setup in `.claude/`

None of these adds a business rule.

| Document | Contents |
|---|---|
| [DESIGN.md](DESIGN.md) | Service boundary, data/API design, invariant, concurrency, assumptions, tradeoffs, requirements traceability |
| [AI_USAGE.md](AI_USAGE.md) | Prompts, AI responses, accepted/edited/rejected decisions, verification evidence |

## Setup
Requires Python 3.11+ (developed and tested on 3.14).

```bash
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS / Linux
.venv/bin/python -m pip install -r requirements.txt
```

## Run the tests
```bash
.venv\Scripts\python.exe -m pytest -q        # Windows
.venv/bin/python -m pytest -q                # macOS / Linux
```
Expected: `112 passed`, no warnings.

To confirm the tests actually protect the rules, run the mutation check. It plants 37 deliberate bugs one
at a time in a temporary copy (the project files are never touched) and expects every one to be caught:
```bash
.venv\Scripts\python.exe scripts\mutation_check.py   # Windows
.venv/bin/python scripts/mutation_check.py           # macOS / Linux
```
Expected: `37/37 mutants caught by a failing test` (about a minute). A bug only counts as caught when a
test actually fails; a planted bug that breaks imports or collection, or hangs, is reported separately. Use `-v` to see each test name; the names map to the
acceptance criteria in DESIGN.md §10.

| File | Covers |
|---|---|
| `tests/test_service.py` | Booking, overlap (all shapes), adjacency, providers, cancellation, invalid input, UTC conversion, future-only rule, the read methods |
| `tests/test_api.py` | HTTP status codes, the shared error format (incl. 404/405/500), unknown/wrong-type/malformed JSON, the read endpoints |
| `tests/test_concurrency.py` | 5 tests: 50 parallel bookings of one slot (exactly 1 wins), partly overlapping bookings (exactly 1 wins), different providers (all win), parallel cancels (exactly 1 wins), and a start time passing while a request waits for the lock (rejected). Each also checks that no two active appointments overlap |

## Run the API
```bash
.venv\Scripts\python.exe -m uvicorn app.api:app --reload    # Windows
.venv/bin/python -m uvicorn app.api:app --reload            # macOS / Linux
```
Interactive docs are at http://127.0.0.1:8000/docs. In **POST /appointments → Try it out**, the
**Examples** dropdown has ready-made bodies: valid, overlap, adjacent, other provider, `+05:30` offset,
naive, zero duration and past. Each is labelled with its expected status.

Requests must send `Content-Type: application/json`; without it the body isn't parsed as JSON and the
request is rejected with `422 INVALID_INPUT`. Unknown body fields are rejected too.

```bash
# Book (start/end: ISO-8601 with an offset; returned in UTC)
curl -X POST http://127.0.0.1:8000/appointments -H "Content-Type: application/json" \
     -d '{"provider_id": "provider-a", "start": "2099-01-01T10:00:00Z", "end": "2099-01-01T11:00:00Z"}'
# -> 201 {"id": "...", "provider_id": "provider-a", "start": "2099-01-01T10:00:00Z", "end": "2099-01-01T11:00:00Z", "status": "ACTIVE"}

# Overlapping booking for the same provider
# -> 409 {"error": {"code": "CONFLICT", "message": "..."}}

# Cancel
curl -X POST http://127.0.0.1:8000/appointments/<id>/cancel
# -> 200 {..., "status": "CANCELLED"}   | 404 NOT_FOUND | 409 ALREADY_CANCELLED
```

| Endpoint | Success | Errors |
|---|---|---|
| `POST /appointments` | `201` | `422 INVALID_INPUT`, `409 CONFLICT` |
| `POST /appointments/{id}/cancel` | `200` | `422 INVALID_INPUT`, `404 NOT_FOUND`, `409 ALREADY_CANCELLED` |
| `GET /appointments/{id}` *(read-only)* | `200` | `422 INVALID_INPUT` (blank id), `404 NOT_FOUND` |
| `GET /providers/{provider_id}/appointments` *(read-only)* | `200` (a list; `[]` for an unknown provider) | `422 INVALID_INPUT` (blank id) |

**Every** error, including an unknown route (`404 NOT_FOUND`), a wrong method (`405 METHOD_NOT_ALLOWED`)
and unexpected faults (`500 INTERNAL_ERROR`, generic message), uses one format:
`{"error": {"code": "...", "message": "...", "field": "..."}}`. `field` is included when a specific input was
wrong, and a `409 CONFLICT` also carries `conflicting_appointment_id`, the booking that's in the way.

### Read endpoints: why they exist
The brief scopes this work to **booking and cancellation**, and the two `GET` endpoints don't extend that
scope. They are **read-only verification aids**. They add no business rules, change nothing, and take the same lock as
`book`/`cancel`, so what they return is always a consistent snapshot. They exist so that a reviewer can
**see** the effect of every booking rule from Swagger or curl, without trusting the tests alone:

| To verify… | Do this |
|---|---|
| A rejected request saved nothing (AC5) | List the provider before and after: the list is unchanged |
| Cancel is a soft status change and frees the slot (AC4) | `GET` the appointment after cancelling: `status` is `CANCELLED`, the record still exists; then rebook the slot |
| No overlaps for a provider (AC2, AC3) | List the provider: appointments come back sorted by `start`, so overlaps and back-to-back slots are easy to see |
| Times are stored in UTC | Book with `+05:30`, then `GET` it: `start` ends in `Z` |

Deliberate limits:
- There's no "list all providers" endpoint, because providers aren't registered entities here.
- There's no search, filtering or paging.
- Lookups use the same rules as the write side. `GET /appointments/{id}` matches the ID exactly, like cancel.
  The provider list strips whitespace, like booking.

## Booking invariant
> **For any provider, no two ACTIVE appointments overlap in time.**

- Intervals are half-open `[start, end)`. Two intervals overlap iff `a.start < b.end and b.start < a.end`.
- **Adjacent** appointments (one ends exactly when the next starts) are allowed.
- **Cancelled** appointments don't block time, so their slot can be rebooked.
- **Different providers** never conflict.
- The overlap check and the insert run under one lock, so concurrent requests can't both win the same slot.

## Assumptions
- **UTC:** all times are stored, compared and returned in UTC. Inputs must carry an offset; any offset
  (e.g. `+05:30`) is converted to UTC. Naive timestamps (no offset) are rejected as ambiguous.
- **Future-only:** `start` must be strictly after the current UTC time. Cancelling has no time restriction.
- **Validation:** `end > start` (positive duration). `provider_id` must be non-blank and valid Unicode, and is
  stored with surrounding whitespace removed. Cancel IDs are matched exactly as sent, with no trimming. Every
  rejected request leaves stored bookings unchanged.
- **IDs:** appointment IDs are server-generated UUID4. `provider_id` is an opaque string; providers aren't pre-registered.
- **Cancellation** is a soft status change (`CANCELLED`). The record is kept and cancelling can't be undone.

## Limitations & follow-up risks
- **In-memory and single-process.** Data is lost on restart. The lock only protects one process, so running
  several workers or instances would break the invariant. A database version needs a DB-level guarantee,
  e.g. a PostgreSQL exclusion constraint on `tstzrange(start, end, '[)')` for ACTIVE rows, or
  `SELECT … FOR UPDATE` in a transaction.
- **One global lock** serialises all providers. Per-provider locks would scale better.
- **O(n) overlap scan.** Cancelled records are kept forever, so memory grows without bound.
- **The future-only rule depends on the server clock.** No idempotency keys: a retried `POST` may get `CONFLICT` against its own booking.
- **Not implemented (by scope):** rescheduling, buffers between appointments, provider registry or
  existence checks, search/paging on the read endpoints, auth.
- **Natural-language times** were considered and left out of the service. A front end (e.g. an
  LLM-based assistant) could convert phrases like "tomorrow 3pm" to ISO-8601 UTC before calling this
  API. The service would still validate its output, so the booking rule never depends on the LLM's
  interpretation.

## Project layout
```
app/models.py      Appointment, status, domain errors
app/service.py     BookingService: all rules (validation, UTC, invariant, lock)
app/api.py         Thin FastAPI adapter
tests/             test_service.py, test_api.py, test_concurrency.py, helpers.py
scripts/           mutation_check.py (37 planted bugs, run on a temporary copy)
CLAUDE.md, .claude/   AI-assistant project setup (rules, test-on-edit hook, review agents); see AI_USAGE.md
```
`.venv/`, `__pycache__/` and `.pytest_cache/` are in `.gitignore`, so they are not committed.
