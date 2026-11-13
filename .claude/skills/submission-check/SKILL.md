---
name: submission-check
description: Final pre-submission audit of the appointment booking assessment. Checks every acceptance criterion and deliverable, runs the tests, and runs the reviewer subagents. Use before submitting or when asked "are we done?"
---

# Submission check

Produce a pass/fail checklist. Do not fix anything during the check; list the gaps, then ask the user which to fix.

## 1. Tests
Run `<python> -m pytest -v` (prefer `.venv/Scripts/python.exe`). Record the summary line.

## 2. Acceptance criteria
For each item, cite the test name(s) or file:line that proves it.
1. Valid booking for a provider + positive-duration interval succeeds.
2. Same-provider overlap rejected; different providers don't conflict.
3. Adjacent appointments allowed (end == next start).
4. Cancelled appointment frees its slot; cancelling a missing booking and cancelling an already-cancelled booking each return a clear, distinct result.
5. Invalid timestamps, non-positive durations, missing identifiers rejected **and the store is unchanged** (a test asserts this).
6. Tests exist for: success, same-provider overlap, adjacency, different providers, cancellation, invalid input, plus a concurrency test.
7. `AI_USAGE.md` has entries with prompt, response summary, accepted/edited/rejected, files affected, and verification evidence, and contains no `Pending` verifications.

## 3. Deliverables
- [ ] Runnable code (`app/`) + `requirements.txt`
- [ ] `DESIGN.md`: service boundary, data/API design, booking invariant, concurrency/persistence, assumptions/tradeoffs
- [ ] `README.md`: setup + run instructions, exact test command, assumptions + invariant note, limitations/follow-up risks
- [ ] `AI_USAGE.md`
- [ ] UTC assumption documented (offsets converted to UTC; naive timestamps rejected)

## 4. Reviews
Launch the `invariant-reviewer`, `test-coverage-reviewer`, and `scope-reviewer` subagents in parallel.
Summarize each one's findings, and say which ones you verified as real.

## 5. Hygiene
- Grep for secrets, emails, and personal names in all files, `AI_USAGE.md` included.
- No out-of-scope features (see CLAUDE.md).
- No naive `datetime.now()` / `datetime.utcnow()`.

Output a table: item | status (PASS / FAIL / GAP) | evidence.
