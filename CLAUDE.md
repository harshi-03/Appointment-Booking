# Appointment Booking: Conflict-Safe Booking & Cancellation

Bounded assessment project. Implements **only** the booking-conflict and cancellation slice of a
scheduling service. No starter project was supplied, so this is the minimal in-memory service fallback.

## Stack
- Python 3.11+, FastAPI (thin HTTP layer), Pydantic v2, pytest, httpx2 (TestClient transport).
- `scripts/mutation_check.py` plants 37 bugs in a temp copy; it must report 37/37 caught by a failing test. Add a mutant
  when you add a rule.
- In-memory store. No database, no frontend.

## Architecture (keep these boundaries)
```
app/api.py      FastAPI routes: forward raw input to the service, map domain errors -> HTTP. No business logic.
app/service.py  BookingService: holds the in-memory dict[id, Appointment]; validation, UTC
                normalisation, overlap invariant, locking, cancel. ALL rules live here.
app/models.py   Appointment, AppointmentStatus, domain errors.
tests/          test_service.py, test_api.py, test_concurrency.py
```
`DESIGN.md` is the source of truth for API shape and behaviour. Keep it minimal: no separate store
layer, no CLI, no extra fields. The two GET endpoints are read-only verification aids: they must
never gain rules, filters, paging or write side effects.

## The booking invariant (never break this)
For any provider, no two ACTIVE appointments overlap.
- Intervals are half-open `[start, end)`.
- Overlap: `new.start < existing.end and existing.start < new.end` (strict `<`).
- Adjacent appointments (one ends exactly when the next starts) are allowed.
- CANCELLED appointments are ignored by the overlap check.
- Different providers never conflict.

## Non-negotiable rules
1. **Validate before any write.** A rejected request must leave the store unchanged.
2. **Check-then-insert happens under the service lock** (`threading.Lock`). Cancel also takes the lock.
3. **UTC internally.** Timestamps must be timezone-aware ISO-8601. Any explicit offset (`Z`, `+00:00`,
   `+05:30`, …) is accepted and **converted to UTC** before validation, comparison, and storage. API
   responses return UTC (`Z`). **Naive timestamps (no offset) are rejected** because their zone is
   ambiguous. Unparseable strings are rejected. Never call `datetime.now()` without `timezone.utc`.
4. `end > start`, otherwise reject as non-positive duration.
4a. **Future-only:** `start > clock()` (strict), checked **inside the lock** because time is changing state, otherwise `INVALID_INPUT` with the message "start must be in
    the future (UTC)". `BookingService(clock=...)` is injectable; tests always pass a fixed clock and must
    never depend on the real time. API tests build the app with `create_app(make_service())` so they
    get the same fixed clock and fresh state. Cancel has no time restriction.
5. `provider_id` must be a non-empty string after stripping whitespace. `appointment_id` must be present.
6. Error results use stable codes: `INVALID_INPUT`, `CONFLICT`, `NOT_FOUND`, `ALREADY_CANCELLED`.
   HTTP mapping: 201 created, 200 cancelled, 422 invalid, 409 conflict/already-cancelled, 404 not found.
7. The service validates on its own. Request model fields are `Optional[str]`. A
   `RequestValidationError` handler maps FastAPI's own rejections (wrong JSON types, malformed JSON) to
   the same `422 INVALID_INPUT` envelope. Unknown routes/methods (404/405) and unexpected faults
   (500, generic message) use the same envelope too. Unknown body fields are rejected (`extra="forbid"`).
   `Appointment` is frozen: never mutate it, store a `replace(...)` copy.
8. `provider_id` is stored and compared **stripped**, and must be encodable as UTF-8. Cancel looks up the
   appointment id **exactly as received**; strip is used only for the blank check.

## Out of scope (do NOT add)
Frontend, auth, notifications, recurring availability/working hours, calendar integration, deployment,
Docker, a real database, time zones other than UTC, rescheduling, search/paging/provider registry,
and any LLM/LangChain/agent features inside the product.
If something seems necessary but is out of scope, write it in the README limitations instead.

## Commands
```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows (use .venv/bin/python on POSIX)
.venv/Scripts/python.exe -m pytest -q                         # run tests
.venv/Scripts/python.exe -m uvicorn app.api:app --reload      # run the API
```

## Workflow for Claude
- **Tests run automatically** after every edit to a `.py` file (PostToolUse hook in
  `.claude/settings.json`). If the hook reports failures, fix them before doing anything else.
- **Write tests alongside code.** Every acceptance criterion (1–6) must map to at least one test.
- **Before declaring a feature done**, run the reviewer subagents: `invariant-reviewer`,
  `test-coverage-reviewer`, and `scope-reviewer` (or the built-in `/code-review`).
  Treat their findings as input to verify, not as truth.
- **Keep the AI usage log current.** After each meaningful AI-assisted activity (design decision,
  generated code, generated tests, review finding, rejected suggestion), append an entry to
  `AI_USAGE.md` with the `/log-ai-usage` skill. Record rejections and edits honestly. That is the
  most valuable part of the log.
- Before submission, run `/submission-check`.

## Privacy
Never put credentials, secrets, emails, or personal names in prompts, code, or `AI_USAGE.md`.
Use generic provider IDs in tests (`provider-a`, `provider-b`).

## Deliverables (all in repo root)
`README.md` (setup, run, test commands, assumptions + invariant, limitations), `DESIGN.md`,
`AI_USAGE.md`, `app/`, `tests/`, `requirements.txt`.
