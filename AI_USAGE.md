# AI Prompt & Use Record

## At a glance
Claude Code was used throughout as an engineering assistant: reading the brief, design, code, tests, review and docs. A second assistant (Claude in the claude.ai chat) was used only to write a spec (details in entry 14). AI was never used inside the product. Every AI suggestion was checked against the brief, by tests, or by reproducing the problem before it was accepted and reviewed by the candidate.

The candidate's own decisions changed the result in these places:
- converting UTC offsets instead of rejecting them (entry 4)
- requiring bookings to start in the future (entry 7)
- requiring a failing test before every fix of the final review findings (entry 12)
- identifying the race in the future-only check (entry 13)
- adding the read-only GET endpoints against the AI's advice (entry 16)
- manually testing every requirement in Swagger (entry 17)

The AI's mistakes are recorded rather than hidden: a concurrency test that passed with the lock removed (entry 8), a booking saved and then answered with a 500 (entry 12), and a race in the future-only check (entry 13). So are corrections to this log: where the spec came from (entry 14), and earlier entries overtaken by later changes (entry 16).

Final state: **112 tests pass**, and **37/37 planted bugs** are each caught by a failing test (`scripts/mutation_check.py`).

**Tools:**
- Claude Code (VS Code extension), model Claude Sonnet 5.5: all work recorded in entries 1–17.
- Claude in the standard claude.ai chat: used only to write the spec in entry 6. See entry 14.

**Privacy:** prompts are quoted with personal details removed. No credentials or secrets were used.

Entries are appended with the `/log-ai-usage` skill (`.claude/skills/log-ai-usage/SKILL.md`). The log is append-only: earlier entries are not rewritten, and later entries record corrections (marked inline in *italics*).

## Summary: where judgment changed the outcome

This lists every edited or rejected item in the log. Each **#** links to the entry with the full prompt, the reasoning and the verification evidence.

### Candidate overrode or corrected the AI
| # | AI's position | Candidate's decision | Evidence |
|---|---|---|---|
| [4](#4-revisiting-the-utc-offset-rule) | Reject timestamps with non-UTC offsets | Checked the brief (it doesn't require this): **convert offsets to UTC** instead | `test_offset_converted_to_utc`, `test_cross_offset_overlap_conflicts` |
| [7](#7-overriding-the-ai-on-the-future-only-rule) | Leave the future-only rule out (not required by the brief) | Brief is silent on past bookings: **past date bookings cannot be made** | `test_start_in_past_rejected`, `test_start_exactly_now_rejected` |
| [12](#12-fixing-the-final-review-findings-test-first-explaining-the-planted-bugs-that-survived) | Fixes proposed as plain changes | Required **failing test first, then the fix**, and set the approach for each fix | Before/after table in entry 12 |
| [13](#13-fixing-a-race-in-the-ais-future-only-design) | Future-only check placed *before* the lock | **Race identified by the candidate** while reviewing this log, checked against DESIGN §7, and fixed test-first at the candidate's direction. The three Claude Code reviewer subagents had missed it | `test_future_check_holds_at_commit_time_not_arrival_time` failed (`'saved'`), then passed |
| [16](#16-candidate-prompted-re-review-and-api-consistency-changes) | Leave out the GET endpoints (outside the slice) | **Added both as read-only verification aids**, with their purpose explained in the README | 10 read-endpoint tests; 4 planted bugs on them, all caught |

### AI output edited after review or testing
| # | What was wrong | Found by | Fix |
|---|---|---|---|
| [5](#5-drafting-designmd-and-reviewing-it-against-the-brief) | First design over-built: store layer, GET endpoint, `cancelled_at`, CLI | AI self-review ("nothing over-engineered") | Removed; 3 source files, 2 endpoints |
| [5](#5-drafting-designmd-and-reviewing-it-against-the-brief) | Wrong JSON type / malformed JSON would bypass the error envelope; blank cancel id missing from the API table; whitespace in `provider_id` could allow a double-booking | `scope-reviewer` | Validation handler, `422` row, stripped `provider_id` |
| [8](#8-implementing-the-service-and-tests-mutation-testing) | AI's own parallel-cancel test **passed with the lock removed** | AI's planted-bug run (M5) | Delay moved between the status read and the write; caught 3/3 |
| [9](#9-independent-code-and-test-review-by-reviewer-subagents) | Insert or scan outside the lock went undetected; a scan stopping after the first appointment and returning stored objects (not copies) also went undetected | `test-coverage-reviewer` (R1–R6) | Tests strengthened; all 15 planted bugs caught |
| [12](#12-fixing-the-final-review-findings-test-first-explaining-the-planted-bugs-that-survived) | Bad `provider_id` → booking saved, then **500**; invalid UTF-8 got FastAPI's 400; padded cancel id cancelled the real booking | `invariant-reviewer`, each reproduced | `422`, nothing saved; one error format; exact-ID lookup |
| [12](#12-fixing-the-final-review-findings-test-first-explaining-the-planted-bugs-that-survived) | The production clock was never tested | `test-coverage-reviewer` (S1) | `test_default_clock_is_utc_aware` |
| [12](#12-fixing-the-final-review-findings-test-first-explaining-the-planted-bugs-that-survived) | Reviewer labelled S4 "harmless"; it can save a booking *and* return an error | AI re-analysis | `test_booking_is_all_or_nothing_even_if_clock_moves` |
| [15](#15-final-code-review-before-submission) | Mutation script counted import/collection errors as "caught"; a test used the real clock; a test accepted either outcome; unknown field names echoed in full | `/code-review` | Exit code 1 required; tests made deterministic; field names truncated |
| [16](#16-candidate-prompted-re-review-and-api-consistency-changes) | Inconsistent error formats (404/405/500); unknown fields silently ignored; ambiguous-timezone test passed for the wrong reason; no test for partly overlapping or multi-provider concurrency | Candidate's prompts (error format, unknown fields); Claude Code re-review requested by the candidate (timezone test, concurrency gaps) | One error format everywhere; `extra="forbid"`; reason asserted; 2 concurrency tests + whole-store invariant check |

### Rejected or not built
| # | Proposal | From | Why not |
|---|---|---|---|
| [2](#2-choosing-the-technical-approach) | LangChain / LangGraph / agents in the product; Azure Functions | Candidate's skill set | Out of scope; "use AI" in the brief means AI as an engineering assistant |
| [6](#6-reconciling-the-spec-with-the-ai-design) | `client_id`, `duration_minutes`, separate store class, `docs/` folder. (List/GET endpoints were also rejected here, but were **later added by the candidate as read-only verification aids**; see entry 16.) | Spec from the claude.ai chat (entry 14) | No rule uses `client_id`; `start`/`end` fits the invariant; a store with no rules; tooling paths point at the root |
| [6](#6-reconciling-the-spec-with-the-ai-design) | `pytest-cov`, `field` in error body | Spec from the claude.ai chat (entry 14) | Optional; the traceability table is stronger evidence than a coverage % |
| [10](#10-natural-language-time-input-via-an-llm-considered-left-out-and-the-readme) | LLM turning natural-language times into UTC | Candidate | Out of scope, non-deterministic, needs an API key, reintroduces zone ambiguity. Documented as a front-end concern |
| [5](#5-drafting-designmd-and-reviewing-it-against-the-brief) | Trim the candidate's prompt; rewrite entry 2 | `scope-reviewer` | Prompts are kept verbatim; the log is append-only |
| [9](#9-independent-code-and-test-review-by-reviewer-subagents) | Validate the injected clock (*later reversed in entry 16*); HTTP-level parallel-cancel test; extra cancelled-neighbour test | Reviewers | Developer contract, not user input; the lock lives in the service; already covered by M2 |
| [12](#12-fixing-the-final-review-findings-test-first-explaining-the-planted-bugs-that-survived) | A test for S3 (cancel with its own lock) | `test-coverage-reviewer` | Behaviour-equivalent: cancel only frees time, so there's no observable difference to assert |
| [15](#15-final-code-review-before-submission) | Per-provider index to avoid the O(n) scan under the lock | `/code-review` | Already a documented limitation; unnecessary complexity for an in-memory prototype |
| [16](#16-candidate-prompted-re-review-and-api-consistency-changes) | `client_id`, `duration_minutes`, a separate store class, a flat error shape, RFC 9457 `problem+json`, request IDs | Candidate review | No rule uses them / `start`+`end` fits the invariant / a store with no rules / our shape matches Microsoft's guidelines; RFC 9457 and request IDs are documented follow-ups |

---

### 1. Understanding the assessment brief
- **Date:** 2026-11-12
- **Activity type:** Requirements analysis
- **Prompt:**
  > i've attached the assessment brief before we start writing anything can you help me understand what's expected exactly? go through it point by point, including the acceptance criteria, what's in scope and out of scope, deliverables, and what they're expecting from the candidate.
- **AI response (summary):**
  - Checked the workspace and found no starter project, so the in-memory service/CLI fallback applies.
  - Broke down each acceptance criterion. Highlighted half-open `[start, end)` intervals and strict `<` as the key point for the adjacency rule.
  - Pointed out that "rejected without changing stored bookings" means validating before writing, and that tests should assert the store is unchanged.
  - Noted that the concurrency test is only conditionally required with no starter project, but recommended a lock and a focused test anyway.
  - Listed out-of-scope items and the deliverables, including a limitations section.
- **Decision:** Accepted. The interpretation was used as the basis for the plan.
- **Files / decisions affected:** Scope and acceptance-criteria mapping in `CLAUDE.md`. Half-open interval decision.
- **Verification:** Manually re-read the brief against the summary, point by point. No discrepancies found.

### 2. Choosing the technical approach
- **Date:** 2026-11-12
- **Activity type:** Design
- **Prompt:**
  > yeah there is no starter project shared, I generally use python, fastapi and am familiar with genai like llm, rag, agentic ai, langchain, langgraph, azure functions etc. so tell me what kind of technical path are we planning
- **AI response (summary):**
  - Recommended Python + a thin FastAPI layer over a framework-free `BookingService`, with an in-memory store and pytest.
  - Advised **against** using LangChain/LangGraph/RAG/agents in the product or deploying to Azure Functions, because both are out of scope. "Use AI" means AI as the engineering assistant.
  - Proposed the API (`POST /appointments`, `POST /appointments/{id}/cancel`), error codes, and HTTP status mapping.
  - Concurrency: a single `threading.Lock` around check-then-insert. Reason: FastAPI runs sync handlers in a threadpool, so the race is real. Per-provider locks were deferred as a follow-up.
  - Validation: reject naive timestamps. Recommended rejecting non-UTC offsets, with normalising to UTC as the alternative.
- **Decision:** Accepted. The strict UTC rule (reject non-UTC offsets) was adopted as the default in `CLAUDE.md` and can still be revisited.
- **Files / decisions affected:** Architecture and rules in `CLAUDE.md`; planned layout `app/`, `tests/`, `DESIGN.md`, `README.md`.
- **Verification:** Verified once the code existed (entries 8–9). 65 tests pass; the `invariant-reviewer` found no high or medium defects in the layering, lock scope or validation; lock mutations M4, M5, R1 and R2 are each caught 5 of 5 runs. The UTC rule was later changed by the candidate (entry 4).

### 3. Claude Code project tooling
- **Date:** 2026-11-12
- **Activity type:** Tooling
- **Prompt:**
  > can we add some claude code specific setup for this project to make development smoother? maybe a claude.md file with project rules and instructions and add useful skills wherever required like to run tests after any code change and pls maintain the ai usage log as they mentioned in reqs and some reviewer sub agents like you have the code review skill anyhow
- **AI response (summary):**
  - Explained that "run tests after any code change" must be a **hook** (an automatic trigger), not a skill. Added a PostToolUse hook on `Write|Edit` that runs `pytest -q` when a `.py` file changes. It returns exit code 2 on failure so the failure is fed back to the AI.
  - `CLAUDE.md` holds the invariant, rules, scope boundaries, commands, and workflow.
  - Skills: `/run-tests`, `/log-ai-usage`, `/submission-check`.
  - Read-only reviewer subagents: `invariant-reviewer`, `test-coverage-reviewer`, `scope-reviewer`, to complement the built-in `/code-review`.
  - Seeded this log with entries 1–3.
- **Decision:** Accepted.
- **Files / decisions affected:** `CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/run_tests.py`, `.claude/skills/*`, `.claude/agents/*`, `AI_USAGE.md`, `.gitignore`.
- **Verification:** Pipe-tested `.claude/hooks/run_tests.py` with synthetic hook payloads and a temporary test file (deleted afterwards):
  1. `.py` edit + passing test: exit 0, context `"1 passed in 0.01s"`
  2. `.py` edit + failing test: exit 2, pytest failure output on stderr (`1 failed in 0.32s`)
  3. `README.md` edit: exit 0, no test run
  4. `.py` edit, no `tests/` dir yet: exit 0, no-op

  `.claude/settings.json` parsed as valid JSON and the hook command resolved correctly. The new skills were detected by Claude Code straight away.

### 4. Revisiting the UTC offset rule
- **Date:** 2026-11-12
- **Activity type:** Design
- **Prompt:**
  > did the document mention we should restrict them , if not its better for us to convert
- **AI response (summary):**
  - Re-checked the brief. It says "Use UTC timestamps", "Keep time-zone handling to UTC", and "Invalid timestamps … are rejected". It does **not** say that offset timestamps are invalid. The earlier "reject non-UTC offsets" rule (entry 2) was the AI's own stricter reading, not a requirement.
  - Agreed that conversion is reasonable: accept any explicit offset, convert to UTC, and store and compare only in UTC, so time-zone handling stays limited to UTC.
  - Kept rejecting **naive** timestamps, since guessing their zone could silently misplace a booking.
  - Flagged a new test to add: a `+05:30` booking must conflict with the equivalent `Z` interval.
- **Decision:** Edited. The candidate overrode the AI's entry-2 recommendation (reject non-UTC offsets) after checking it against the brief. The AI's naive-timestamp rejection was accepted.
- **Files / decisions affected:** `CLAUDE.md` rule 3; `.claude/agents/invariant-reviewer.md`; `.claude/agents/test-coverage-reviewer.md`; `.claude/skills/submission-check/SKILL.md`; validation design for `app/service.py`.
- **Verification:** Brief re-read manually and the quoted lines confirmed. Verified by `test_offset_converted_to_utc`, `test_cross_offset_overlap_conflicts` (`-04:00` and `+05:30`) and `test_naive_timestamp_rejected`, all passing (entries 8–9). Mutation M8 (skipping UTC conversion) is caught.

### 5. Drafting DESIGN.md and reviewing it against the brief
- **Date:** 2026-11-12
- **Activity type:** Design / Documentation / Review
- **Prompt:**
  > yeah make sure nothing is overengineered and all the reqs and scope mentioned in the assessment is met
- **AI response (summary):**
  - Planned first (plan mode, approved by the candidate). The plan trimmed the earlier proposal: no separate store layer or per-provider index, no `GET` endpoint, no `cancelled_at` field, no CLI, a single global lock. Request fields are `Optional[str]` so that validation has one path.
  - Wrote `DESIGN.md`: scope, service boundary, data model, API, invariant, validation/UTC order, concurrency, assumptions, limitations, and a traceability table mapping each AC to planned tests.
  - Ran the `scope-reviewer` subagent with the full brief. It found **4 must-fix issues** and 7 nice-to-haves.
- **Decision (per review finding):**
  - **Accepted, M1.** Pydantic v2 doesn't convert numbers to strings, so `{"provider_id": 123}` or malformed JSON would get FastAPI's default `{"detail": …}` 422 instead of our envelope. Checked against Pydantic v2 behaviour. Added a `RequestValidationError` handler to the design, plus two API tests.
  - **Accepted, M2.** The cancel row was missing `422 INVALID_INPUT` for a blank id. Also documented that an empty path segment is FastAPI's own 404, so a missing id is tested at service level.
  - **Accepted, M3.** Whitespace in `provider_id` could have let the same provider double-book. Decided to store it stripped, and added a test.
  - **Accepted, M4.** The "store unchanged" check was only planned for one test. Now every rejection test deep-copies the store before and after.
  - **Accepted (nice-to-have):** named API tests per status code; out-of-range timestamp (`OverflowError`) returns `INVALID_INPUT`; exact response timestamp format; unknown ids return `NOT_FOUND`; extra fields ignored (*later reversed in entry 16*); two more limitations (unbounded memory, no read endpoint).
  - **Rejected:** trimming the skill list from the entry-2 prompt. Prompts are recorded verbatim for fidelity, and the list isn't sensitive.
  - **Rejected:** editing entry 2 to say "superseded". The log is append-only, and entry 4 already records the override.
  - **Deferred to the candidate:** a stale `app/store.py` mention in the `invariant-reviewer` description. The candidate decides on changes to agent config.
- **Files / decisions affected:** `DESIGN.md` (new); `CLAUDE.md` (architecture, rules 7–8, out-of-scope list).
- **Follow-up:** the candidate later cross-checked this design against a spec (entry 6).
- **Verification:** Every reviewer finding was checked against the brief and the doc text before it was applied. The traceability table (§10) now covers AC1–AC6, UTC handling, provider-id normalisation and every HTTP status. Confirmed in entry 9: `test-coverage-reviewer` found every planned §10 test implemented, and 65 tests pass.

### 6. Reconciling the spec with the AI design
- **Date:** 2026-11-12
- **Activity type:** Design / Review
- **Prompt:**
  > also i created a spec file for this idk if it can help or add any points

  It was followed by a spec (originally described here as "the candidate's own spec, written independently"; *corrected in entry 14: the spec came from the claude.ai chat*), which asked: *"Compare it with the approach we discussed and tell me what you'd adopt, change, or push back on, with reasons. I'll decide."*
  The spec covered: stack + pytest-cov; the half-open invariant; input fields `provider_id`, `client_id`, `start`, and `duration_minutes`; a future-only rule; `list_for_provider` plus two GET endpoints; a separate `InMemoryStore`; an injectable clock; a single lock around check and insert; a parametrized overlap test; a 50-thread concurrency test; parallel-cancel tests; and a `docs/` folder.

  The candidate then replied:
  > go with ur plan
- **AI response (summary):**
  - Most of the spec already agreed with the design: the invariant, UTC conversion, rejecting naive timestamps, soft cancel, a thin API, the lock reasoning, and the DB follow-up.
  - **Adopt:** parametrized overlap test; parallel-cancel concurrency test; ~50 threads with a Barrier; the spec's explanation of why the lock can't live in the store methods; the rule that request-only checks run before the lock and state-dependent checks inside it; limitations for buffers and provider existence; stating rejected alternatives.
  - **Change:** keep the `{"error": {"code","message"}}` envelope, because a stable code makes "clear result" testable. `pytest-cov` and `field` are optional. Keep docs in the root, because the tooling paths point there.
  - **Push back:** `client_id` (no rule uses it, and the brief doesn't mention clients); `duration_minutes` (`start`/`end` matches the invariant and avoids int/bool/float edge cases); the future-only rule (not required, and it brings a clock, extra tests and a new limitation); list/GET endpoints (outside the slice); a separate store class (just a dict with no rules).
- **Decision:** The candidate accepted the AI's recommendations as a whole. Per item:
  - **Accepted from the spec, folded into DESIGN.md:** the lock reasoning (§7), before-lock vs inside-lock checks (§7), the parametrized overlap test, ~50 threads, the parallel-cancel test (§10), and the buffers / provider-existence limitations (§9).
  - **Not adopted, with reasons recorded in DESIGN.md §9 "Alternatives considered":** `client_id`, `duration_minutes`, future-only rule + injectable clock (*later adopted, entry 7*), list/GET endpoints (*later added, entry 16*), separate store class, `docs/` folder.
  - **Optional items skipped:** `pytest-cov` and the error `field`, to keep the design lean. Can be revisited.
- **Files / decisions affected:** `DESIGN.md` §7, §8, §9, §10.
- **Verification:** Each spec item was compared against the brief text to decide whether the brief requires it. DESIGN.md was re-checked for internal consistency after the edits. The adopted tests (parametrized overlap, 50-thread booking, parallel cancel) exist and pass; mutation runs M4, M5, R1 and R2 confirm the concurrency tests detect lock bugs (entries 8–9).

### 7. Overriding the AI on the future-only rule
- **Date:** 2026-11-12
- **Activity type:** Design
- **Prompt:**
  > wait no let the user know he cannot book past dates , the doc didnt mention anything related to allowing past date bookings right
- **AI response (summary):**
  - Confirmed that the brief is silent on past bookings. "Past bookings allowed" was the AI's own assumption, not a requirement.
  - Implemented the rule in its smallest form:
    - `start > clock()` (strict), giving `422 INVALID_INPUT` with the message "start must be in the future (UTC)".
    - The check runs after UTC conversion and before the lock, since it doesn't depend on stored state (*wrong; corrected in entry 13*).
    - An optional `clock` parameter on `BookingService`; tests inject a fixed time.
    - Cancel has no time restriction.
  - Added tests for a past start, exactly now (rejected) and just after now (allowed). Replaced the "no future-only rule" limitation with "depends on the server clock".
- **Decision:** Edited. The candidate overrode the AI's entry-6 pushback (the AI had recommended leaving the future-only rule out as not required). The AI's minimal design for the rule was accepted.
- **Files / decisions affected:** `DESIGN.md` §4, §6, §7, §8, §9, §10; `CLAUDE.md` rule 4a.
- **Verification:** Brief re-read; confirmed it has no statement on past bookings. Verified by `test_start_in_past_rejected`, `test_start_exactly_now_rejected` and `test_start_just_after_now_allowed` (all pass, entry 8). Mutation M6 (allowing start == now) is caught.

### 8. Implementing the service and tests; mutation testing
- **Date:** 2026-11-12
- **Activity type:** Code generation / Test generation / Review
- **Prompt:**
  > ok

  This was approval to implement `DESIGN.md` as reviewed.
- **AI response (summary):**
  - Created `.venv` and `requirements.txt` (fastapi, uvicorn, httpx, pytest) plus `pytest.ini`.
  - `app/models.py`: dataclass, status enum, 4 domain errors with stable codes.
  - `app/service.py`: request-only checks before the lock; overlap check + insert inside one `threading.Lock`; cancel under the same lock; returns copies so callers can't mutate stored state.
  - `app/api.py`: `create_app(service)` factory, 2 routes, a `BookingError` handler, and a `RequestValidationError` handler that maps to the `INVALID_INPUT` envelope.
  - 60 tests across `test_service.py`, `test_api.py` and `test_concurrency.py`. They use a fixed clock (`NOW = 2030-01-01T08:00Z`) and never the real time. Every rejection test uses `assert_rejected_unchanged`, which deep-copies the store before and after.
- **Deviation from plan:** `CLAUDE.md` rule 4a said API tests would use far-future dates. Instead, the `create_app(service)` factory lets API tests inject a fixed-clock service. This is more deterministic and gives each test fresh state.
- **Self-review: the AI found a weakness in its own test.** The first `test_concurrent_cancel_single_winner` slowed down `dict.get`, which runs *before* the status check. The real race (read `status`, then write it) had a zero-width window, so the test **passed even with the cancel lock removed** (mutation M5 below). Fixed by injecting the delay exactly between reading `status` and writing it (`SlowStatusAppointment`).
- **Decision:** Accepted (the code), edited (the concurrency test, after the mutation run).
- **Files / decisions affected:** `app/*`, `tests/*`, `requirements.txt`, `pytest.ini`.
- **Verification:**
  - Command `.venv/Scripts/python.exe -m pytest -q` gives **`60 passed, 1 warning`**. The warning is a Starlette deprecation notice about `httpx` in `TestClient`, from a third-party library, not our code. The suite ran **10 times, 10 green** (not flaky).
  - The PostToolUse hook auto-ran the suite after each test-file write (41, 43, then 60 passed).
  - **Mutation testing:** each bug was planted in a scratch copy of `app/service.py`, then the full suite was run.

    | # | Planted bug | Result |
    |---|---|---|
    | M1 | `<` changed to `<=` in the overlap check | caught (3 failed) |
    | M2 | status filter removed (cancelled appointments still block) | caught (2 failed) |
    | M3 | provider filter removed | caught (2 failed) |
    | M4 | lock removed from `book` | caught (3 of 3 runs) |
    | M5 | lock removed from `cancel` | **survived at first**; caught 3 of 3 runs after the test fix |
    | M6 | `start == now` allowed | caught |
    | M7 | zero duration allowed | caught (2 failed) |
    | M8 | UTC conversion skipped | caught (2 failed) |
    | M9 | `provider_id` stored unstripped | caught |
  - Reviewer subagents: results and follow-up fixes are in entry 9.

### 9. Independent code and test review by reviewer subagents
- **Date:** 2026-11-12
- **Activity type:** Review
- **Prompt (to subagents, written by the AI as part of entry 8's workflow):** the `invariant-reviewer` was asked to check `app/` against DESIGN.md §4–§7. The `test-coverage-reviewer` was asked to check `tests/` against the ACs and the §10 table, to flag any test that depends on real time, and to flag any rejection test without a store-unchanged check. Both ran with fresh context and did not see the AI's reasoning.
- **AI response (summary):**
  - **`invariant-reviewer`:** no high or medium defects. It found 2 confirmed low findings (a §4 microseconds wording mismatch, and a malformed-JSON message reading `"20: JSON decode error"`) and 2 plausible low ones (a naive injected clock gives `TypeError`; Pydantic is not pinned to v2).
  - **`test-coverage-reviewer`:** every §10 test exists and none depends on real time. But its own mutation run found **6 surviving bugs**:
    - **R1:** insert placed outside the lock, which passed 9 of 9 runs and is the exact failure §7 warns about.
    - **R2:** scan outside the lock, caught in only 3 of 5 runs.
    - **R3:** scan stops after the first appointment.
    - **R4/R5:** returning the stored object instead of a copy.
    - **R6:** API dropping microseconds.

    It also found that API rejection tests didn't check the store, which breaks the project rule.
- **Decision (each finding reproduced by the AI before acting):**
  - **Accepted:** the malformed-JSON message is now "request body is not valid JSON" (reproduced first); `pydantic>=2` pinned; §4 reworded to "only if non-zero" (reproduced).
  - **Accepted:** `SlowDict.__setitem__` now sleeps before the insert lands, so R1 and R2 fail reliably.
  - **Accepted:** new or strengthened tests:
    - a conflict against a non-first stored appointment (R3)
    - a returned appointment is a copy (R4/R5)
    - an API microseconds test (R6)
    - a `+05:30` conflict case
    - a naive `end` case
    - past/now tests on the `booked` fixture
    - cancel of a past appointment is allowed
    - the full cancel response body checked
    - the first cancel asserted as 200
  - **Accepted:** the API client fixture now exposes the service, and every API rejection asserts the store is unchanged (`assert_rejected`).
  - **Rejected:** validating the injected clock. It's a developer contract (§4), not user input, and failing loudly on misuse is correct (*later reversed in entry 16*).
  - **Rejected:** an HTTP-level parallel-cancel test. The lock lives in the service, and TestClient adds no concurrency guarantee. §7 was reworded to "exactly one succeeds" at service level instead.
  - **Rejected as redundant:** a "cancelled appointment next to an active one" test. Status-filter mutation M2 is already caught.
  - **Not applicable:** "CLAUDE.md says 2099". The reviewer read a version that had already been corrected (entry 8).
- **Files / decisions affected:** `app/api.py`, `requirements.txt`, `DESIGN.md` §4/§7, `tests/test_service.py`, `tests/test_api.py`, `tests/test_concurrency.py`.
- **Verification:**
  - `.venv/Scripts/python.exe -m pytest -q` gives **`65 passed, 1 warning`**, and 10 out of 10 repeated runs were green.
  - **Mutation re-run, all 15 caught:** M1–M9 from entry 8 plus R1–R6. The lock-related ones (M4, M5, R1, R2) were each run 5 times and caught **5 of 5** every time.

### 10. Natural-language time input via an LLM (considered, left out) and the README
- **Date:** 2026-11-12
- **Activity type:** Design / Documentation
- **Prompt:**
  > also cant we use any llm here like instead of a program cant the user give time in any natural language and llm rephrases to our required format of utc timezone?

  Followed by:
  > yeah go
- **AI response (summary):**
  - Recommended **not** adding it, for five reasons:
    1. Out of scope: the brief limits the work to the booking/cancel slice and prioritises invariant correctness over features.
    2. The brief's "use AI" means AI as an engineering assistant, not AI in the product.
    3. Non-deterministic output would weaken the tests and mutation evidence.
    4. It needs an API key and sends booking data to an external service.
    5. It brings back the very ambiguity we designed out: "3pm tomorrow" doesn't say whose 3pm, and `03/04` could be March 4 or April 3.
  - Suggested documenting it instead as a front-end concern whose output the service still validates.
  - Wrote `README.md`: setup, the exact test command and expected result, run instructions with curl examples, the invariant, assumptions, and limitations (including the LLM note).
- **Decision:** Accepted. The candidate agreed to document rather than build the feature.
- **Files / decisions affected:** `README.md` (new); scope boundary (natural-language parsing belongs to a client, not the service).
- **Verification:** Started the real server (`uvicorn app.api:app`, real clock) and ran the README's examples with curl:
  - book: `201`, timestamps in `Z`
  - `+05:30` overlap: `409 CONFLICT`
  - cancel: `200 CANCELLED`
  - cancel again: `409 ALREADY_CANCELLED`
  - unknown id: `404 NOT_FOUND`
  - a 2020 start: `422` "start must be in the future (UTC)"

  Server stopped afterwards.

### 11. Final submission check and fixing the scope reviewer's six items
- **Date:** 2026-11-12
- **Activity type:** Review / Documentation
- **Prompt:** `/submission-check` (the project skill), then:
  > yeah fix these  six low-priority items
- **AI response (summary):**
  - Ran the checklist:
    - `65 passed`, and every AC traced to named tests.
    - Hygiene greps were clean: no emails, names or secrets; no naive `now()` or `utcnow()`; no `Pending` entries; no out-of-scope code.
  - Ran all three reviewer subagents in parallel.
  - **`scope-reviewer`:** nothing blocking. Six low items, all fixed after the candidate approved them:
    1. Stale `app/store.py` mention in `.claude/agents/invariant-reviewer.md`. This was deferred to the candidate in entry 5 and fixed now with their approval.
    2. DESIGN.md §10 was out of date. The header now reads "Tests", the one-minute overlap case is included, and seven tests added in entry 9 were missing from the table and are now listed.
    3. Deleted the empty stray file `learn`, after confirming it was 0 bytes. Added a README note to leave out `.venv/` and `__pycache__/` when packaging.
    4. "Every invalid input has one error shape" was too strong. It is now scoped to defined routes; unknown routes and methods keep FastAPI's 404/405 (*later unified in entry 16*).
    5. Entry 6 says the `docs/` folder and the future-only rule have reasons in DESIGN.md §9 "Alternatives considered". **Correction:** the future-only rule was later *adopted* (entry 7), so it isn't an alternative. The `docs/` reason has now been added to §9.
    6. Re-run the suite (below).
- **Decision:** Accepted (all six). The other two reviewers' findings were reported to the candidate for a decision (entry 12).
- **Files / decisions affected:** `.claude/agents/invariant-reviewer.md`, `DESIGN.md` §4/§9/§10, `CLAUDE.md` rule 7, `README.md`, `learn` (deleted).
- **Verification:** `.venv/Scripts/python.exe -m pytest -q` gives `65 passed, 1 warning`, re-run after the edits (no code or tests changed).

### 12. Fixing the final review findings, test-first; explaining the planted bugs that survived
- **Date:** 2026-11-12
- **Activity type:** Debugging / Test generation / Review
- **Prompt (candidate's numbered instructions, quoted in full):**
  > 1. validate the provider id before saving anything, so an invalid id doesn't leave a booking saved and return a 500 error. first show the test failing with the current issue (500, but booking gets saved), then show it passing after the fix (422, and nothing gets saved).
  > 2. ok can u confirm how the time is being noted then like how are u confirming whether its past booking or not
  > 3. use the standard error response format we already follow in the project show how the response looks before and after the change
  > 4. only use strip to check if the id is blank for the actual lookup use the exact id as received. add a test to show that an id with extra spaces returns 404 and the original appointment stays active
  > 5 , 6. go ahead
  > also, which 3 planted bugs did the tests miss? for each one add a test to catch it or explain why it doesn't need one because it doesn't actually change behaviour i think
- **AI response (summary):**
  - **Test-first, as instructed.** All new tests were written before any fix. The run before the fix showed `5 failed`:
    - `test_api_unencodable_provider_id_rejected_nothing_saved`: `assert (500, 1) == (422, 0)`, i.e. a 500 and one booking saved.
    - `test_api_invalid_utf8_body_422`: `assert 400 == 422`.
    - `test_api_cancel_id_with_spaces_404_original_stays_active`: `assert 200 == 404`.
    - Plus the two service-level equivalents.
  - **Fixes:**
    1. `_require_id` rejects IDs that can't be encoded as UTF-8, before anything is saved.
    2. A `StarletteHTTPException` handler maps FastAPI's undecodable-body `400` to our `422 INVALID_INPUT` envelope; 404 and 405 are left to FastAPI (*later unified in entry 16*).
    3. `cancel` strips the ID only for the blank check and looks up the exact ID.
  - **Before and after**, shown with the fixes reverted in a scratch copy:

    | Case | Before | After |
    |---|---|---|
    | #1 `provider_id` `"\ud800"` | `500 Internal Server Error`, **1 booking saved** | `422 {"error":{"code":"INVALID_INPUT","message":"provider_id contains characters that are not valid Unicode"}}`, **0 saved** |
    | #3 body bytes `{"provider_id": "\xff"}` | `400 {"detail":"There was an error parsing the body"}` | `422 {"error":{"code":"INVALID_INPUT","message":"request body is not valid JSON"}}` |
    | #4 cancel `/%20<id>%20/cancel` | `200`, original **CANCELLED** | `404 NOT_FOUND`, original **ACTIVE** |
  - **#2, how "past" is decided:**
    - `_utc_now()` returns `datetime.now(timezone.utc)`, which reads the OS clock as an aware UTC value. It is not affected by the server's local time zone.
    - The request's `start` is converted to UTC, then compared with a strict `start > now`.
    - A live demo with the real clock ran on a machine whose local time is +05:30:
      - "1 min ago" was **rejected** whether it was written in `Z` or in `+05:30`.
      - "in 1 min" was **accepted** whether it was written in `+05:30` or `-04:00`, and was stored as the same UTC instant.
    - Added `test_default_clock_is_utc_aware`, because no test had covered the production clock before.
  - **#5:** `Content-Type: application/json` requirement documented in the README and DESIGN §4.
  - **#6 hardening:** API test for each single missing field (asserts the exact "X is required" message); booking created first in the wrong-type and malformed-JSON tests; total store size asserted in the concurrency test; out-of-range `end` test.
  - **Surviving planted bugs.** The reviewer reported "22 of 25 caught" (3 missed) but described **4** survivors, so the AI re-ran all four itself:
    - **S1, naive default clock:** a real gap. Now caught by `test_default_clock_is_utc_aware`.
    - **S2, API fills a missing `end` with `start`:** a real gap (the wrong error message). Now caught by `test_api_missing_single_field_422`.
    - **S3, cancel uses its own separate lock:** **no test, because it is behaviour-equivalent.** Cancel only ever moves an appointment from ACTIVE to CANCELLED, so it can only *free* time and can never create an overlap. A booking scan running alongside a cancel sees the status as either ACTIVE (giving CONFLICT) or CANCELLED (giving success). Both outcomes are already possible with one shared lock, depending on which request takes it first. The attribute write is atomic, so there is no torn state to observe. Book-vs-book stays serialised by the booking lock, and cancel-vs-cancel by the cancel lock. With nothing observable to assert, a test would have no failing behaviour to catch. The single lock is kept anyway because it is simpler to reason about.
    - **S4, an extra "start in the future" check placed after the insert:** the AI first expected this to be harmless, but on inspection it is **not** purely equivalent. If the clock passes `start` between the two checks, a booking is saved *and* an error is returned. Added `test_booking_is_all_or_nothing_even_if_clock_moves`, which uses a clock that jumps 1 hour per read and asserts that an error never leaves a booking saved. The mutant now fails it.
- **Decision:** Accepted, as instructed: show the failing test first, keep the error format, and look up the exact ID. On S4, the AI corrected the "equivalent" label it had inherited from the reviewer.
- **Files / decisions affected:** `app/service.py`, `app/api.py`, `tests/test_service.py`, `tests/test_api.py`, `tests/test_concurrency.py`, `DESIGN.md` §4/§6/§10, `README.md`, `CLAUDE.md` rule 8.
- **Verification:**
  - Before the fix: `5 failed, 70 passed` (shown above). After the fix: **`76 passed, 1 warning`**, and 10 out of 10 repeated runs were green.
  - **Mutation run, 22 planted bugs:**
    - M1–M9, R1–R6, N1–N3 (the new fixes), S1 and S2: all caught. The lock-related ones were each run 3 times and caught 3 of 3.
    - S3: survives, behaviour-equivalent, explained above.
    - S4: survived at first; caught after the new test was added.

### 13. Fixing a race in the AI's future-only design
- **Date:** 2026-11-12
- **Activity type:** Review / Debugging
- **Origin:** the candidate noticed the issue while reviewing this log, checked it against DESIGN §7, and sent the prompt below.
- **Prompt:**
  > waitttt entry 7 says the future only check runs before the lock. doesnt that go against what we wrote in design that anything depending on changing state goes inside the lock? the current time keeps changing so a booking could pass the check then wait for the lock and get saved after its start time has already passed right
- **AI response (summary):**
  - **Confirmed the bug, and that the AI had introduced it.**
    - The spec (entry 6) said *"Anything that depends on changing state (existing appointments, the current time) is checked inside the lock."*
    - When implementing the future-only rule (entry 7), the AI placed `start > clock()` **before** the lock. It also quietly narrowed DESIGN §7 to "stored state", which dropped "current time" from the rule.
    - The flaw: a request passes the check, waits for the lock while its start passes, and is then saved with a start in the past. The window is as long as the lock wait.
    - None of the three Claude Code reviewer subagents flagged it. The `invariant-reviewer` checked placement against the AI-edited §7, so it confirmed the wrong rule.
  - **Test first:** `test_future_check_holds_at_commit_time_not_arrival_time`.
    - It holds the lock, starts a booking for 08:30 at clock 08:00, and waits until that request is queued on the lock. A `SignallingLock` event does the waiting, with no sleeps.
    - It then advances the clock to 09:00, releases the lock, and asserts the request is rejected and nothing is saved.
    - **Before the fix it failed:** `AssertionError: assert 'saved' == 'start must be in the future (UTC)'`.
  - **Fix:** moved the clock check inside the `with self._lock:` block, just before the overlap scan and insert. The check now holds at commit time. Only request-only checks (ids, parsing, UTC conversion, `end > start`) stay before the lock.
- **Decision:** Accepted. The issue was identified by the candidate; Claude Code confirmed it, wrote the test and implemented the fix. **This entry corrects entry 7**, whose "check runs after UTC conversion and before the lock" was wrong.
- **Files / decisions affected:** `app/service.py` (`book`), `tests/test_concurrency.py`, `DESIGN.md` §6/§7/§10, `CLAUDE.md` rule 4a, `README.md` (test count).
- **Verification:**
  - Before the fix: `1 failed, 76 passed`. The new test returned `'saved'`.
  - After the fix: **`77 passed, 1 warning`**, and 10 out of 10 repeated runs were green.
  - The pre-fix code serves as the mutant ("time check before the lock"), and the new test catches it.
  - `test_booking_is_all_or_nothing_even_if_clock_moves` (S4) still passes: the clock is read once, inside the lock, before the insert.

### 14. Correction: AI use outside Claude Code
- **Date:** 2026-11-12
- **Activity type:** Correction (AI use outside Claude Code)
- **What this corrects:** entry 6 described the spec as the candidate's own, "written independently". That was **inaccurate**: the spec came from Claude in the standard claude.ai chat. The log is append-only, so earlier entries keep their original text (with inline correction markers), and this entry records the correction.
- **What came from the claude.ai chat (reviewed by the candidate before use):** the spec (entry 6), and nothing else.
- **What remains the candidate's own:**
  - the UTC conversion and future-only decisions, raised by the candidate as prompts: "did the document mention we should restrict them , if not its better for us to convert" (entry 4) and "wait no let the user know he cannot book past dates , the doc didnt mention anything related to allowing past date bookings right" (entry 7)
  - the build plan and prompt sequence for this project
  - the review instructions in entry 12
  - spotting the before-lock race (entry 13)
  - reviewing and accepting or rejecting each suggestion from both assistants
  - verifying fixes against the brief and the test evidence
  - adding the read-only GET endpoints against the AI's advice (entry 16)
  - manually testing every requirement in Swagger (entry 17)
- **Prompts used in the claude.ai chat (summary):** asked for a spec for the booking feature.
- **Decision:** Correction accepted. Header and summary attribution updated.
- **Files / decisions affected:** `AI_USAGE.md` (header, summary tables, inline marker in entry 6, this entry).
- **Verification:** Based on the candidate's own statement and the claude.ai chat history. No code, tests or design changed.

### 15. Final code review before submission
- **Date:** 2026-11-13
- **Activity type:** Review
- **Prompt:**
  > okay is everything done pls do code review one last time
- **AI response (summary):**
  - Ran Claude Code's built-in `/code-review` skill at high effort over `app/`, `tests/` and `scripts/`. It uses fresh reviewers that haven't seen the AI's reasoning. The reviewer reproduced its main finding.
  - It returned **9 findings**. The AI checked each one against the code before deciding:
    1. An unknown request-field name was echoed back in full: a 5,000-character key gave a ~10,000-character response.
    2. **The mutation script counted *any* pytest failure as "caught"**, including import and collection errors (exit codes 2–5), and had no timeout. This weakened the planted-bug evidence.
    3. `test_default_clock_is_utc_aware` booked against the real clock, which breaks the project rule "tests never depend on real time".
    4. `test_booking_is_all_or_nothing_even_if_clock_moves` accepted either outcome, so a wrong rejection would pass.
    5. A stale test-helper comment said cancel "mutates status in place", but appointments are frozen.
    6. `book()` scans every stored appointment under the global lock.
    7. *Every* framework 400 was relabelled "request body is not valid JSON".
    8. The "active appointments" filter was copied in three test files.
    9. `get()` duplicated cancel's lookup logic.
- **Decision (per finding):**
  - **Accepted and fixed (1–5, 7–9):**
    - Field names are shortened before echoing.
    - The mutation script now counts only a genuine test failure (exit code 1) and reports `BROKEN`/`TIMEOUT` separately, with a 120-second timeout. A test helper (`SlowStatusAppointment`) was adjusted so the "not frozen" planted bug fails a test instead of breaking collection.
    - The real-clock part of the default-clock test was removed; it now checks only the UTC offset.
    - The clock test asserts the single expected outcome.
    - The helper comment was corrected, and the snapshot is now a plain dict copy.
    - Only FastAPI's exact body-parse 400 is relabelled; any other 400 keeps its detail as `BAD_REQUEST`.
    - One shared `active()` test helper replaces the three copies.
    - One shared `_find()` lookup in the service is used by both cancel and get.
    - New tests: `test_api_long_unknown_field_name_is_truncated`, `test_api_other_400_keeps_its_detail`.
    - New planted bugs: "unknown field name echoed in full" and "every 400 relabelled as invalid JSON".
  - **Rejected (6):** the O(n) scan is already a documented limitation (DESIGN.md §9). It's acceptable for an in-memory prototype, and a per-provider index would add complexity the brief doesn't ask for.
- **Files / decisions affected:** `app/service.py`, `app/api.py`, `tests/helpers.py`, `tests/test_service.py`, `tests/test_api.py`, `tests/test_concurrency.py`, `scripts/mutation_check.py`, `README.md`, `DESIGN.md`, `CLAUDE.md`.
- **Verification:**
  - `.venv/Scripts/python.exe -m pytest -q` gives **`112 passed`**, with no warnings and 10 out of 10 repeated runs green.
  - `scripts/mutation_check.py` with the stricter rule gives **`37/37 mutants caught by a failing test`**, with none `BROKEN` and none `TIMEOUT`.
  - (*Correction, see entry 16: these final figures were recorded after the entry 16 work was finished, so they include it. This code review itself added only the 2 tests and 2 planted bugs listed above.*)

### 16. Candidate-prompted re-review and API consistency changes
- **Date:** 2026-11-13
- **Activity type:** Review / Design / Test generation
- **Why this entry is late:** this work was done after the entry 15 code review, while the log was not being updated. It is recorded here afterwards. The entry 15 `/code-review` added only 2 tests and 2 planted bugs; the rest of the increase to **112 tests** and **37 planted bugs** came from this re-review, which the candidate started by asking Claude Code to go through the code again.
- **Prompts:**
  The first prompt, asking Claude Code to go through the code again, was not saved. The other prompts from this re-review:

  > check what industry standard api guidelines do and tell me if we should unify it

  > what happens if someone sends a field we dont know about, like status cancelled? if we just ignore it they get a 201 for something they didnt ask for

  > would read endpoints help here? not as a feature, just so someone testing can see what got booked and cancelled. i know you said its outside the slice, so tell me the tradeoff
- **AI response (summary):**
  - **Error format.** Compared the project's `{"error": {"code", "message"}}` shape with common API guidelines and found it matches the error-object style in Microsoft's REST API Guidelines. Recommended using it for *every* response, including 404/405 for unknown routes and methods and unhandled 500s, which until now still used FastAPI's defaults (entries 11 and 12). RFC 9457 `problem+json` and request IDs were suggested as follow-ups, not built.
  - **Unknown fields.** Agreed that silently ignoring them is risky: a request with `"status": "cancelled"` would get `201` and an active booking it didn't ask for. Recommended rejecting unknown fields with `422 INVALID_INPUT` (`extra="forbid"`), keeping the field-name truncation from entry 15.
  - **Read endpoints.** Repeated that they are outside the booking/cancel slice and recommended leaving them out.
  - **Re-review findings (from Claude Code, after the candidate asked it to go through the code again):**
    - The ambiguous-timezone test passed for the wrong reason (it didn't check *why* the request was rejected).
    - No concurrency test covered partly overlapping requests or requests across multiple providers.
  - **Injected clock (reverses entry 9).** The service now validates the injected clock instead of treating it as an unchecked developer contract.
- **Decision:**
  - **Accepted:** one error format for every response (404, 405, 500 included); `extra="forbid"` on request models; the ambiguous-timezone test now asserts the rejection reason; two new concurrency tests (partly overlapping requests, multiple providers) plus a whole-store invariant check; the injected-clock change above.
  - **Edited (candidate overrode the AI):** added both GET endpoints as **read-only verification aids**, not as product features. Their purpose is stated in the README. The routes are `GET /appointments/{appointment_id}` (one appointment) and `GET /providers/{provider_id}/appointments` (all of a provider's appointments).
  - **Rejected:** `client_id`, `duration_minutes` and a separate store class (same reasons as entry 6); a flat error shape (the nested shape already matches Microsoft's guidelines); RFC 9457 `problem+json` and request IDs (documented as follow-ups in DESIGN.md §9).
- **Corrections to earlier entries** (each marked inline in *italics*):
  - entry 5: "extra fields ignored" → now rejected
  - entry 6: list/GET endpoints rejected → now added as read-only aids
  - entry 9: injected clock not validated → now validated
  - entry 11: unknown routes and methods keep FastAPI's 404/405 → now use the shared error format
  - entry 12: 404 and 405 left to FastAPI → now use the shared error format
  - entry 15: final test and planted-bug counts include this entry's work
- **Files / decisions affected:** `app/api.py` (GET routes, shared error handlers, `extra="forbid"`), `app/service.py` (clock validation, `get`), `tests/test_api.py`, `tests/test_service.py`, `tests/test_concurrency.py`, `scripts/mutation_check.py` (read-endpoint planted bugs), `README.md` (purpose of the read endpoints), `DESIGN.md` §9 (RFC 9457 and request IDs as follow-ups).
- **Verification:**
  - Before this re-review: 79 tests passing (77 after entry 13, plus the 2 added in entry 15).
  - After: **`112 passed`**, 10 out of 10 repeated runs green.
  - 10 new read-endpoint tests; 4 planted bugs on the read endpoints, all caught.
  - `scripts/mutation_check.py`: **`37/37 mutants caught by a failing test`**, none `BROKEN`, none `TIMEOUT`.
  - New concurrency tests: `test_concurrent_partially_overlapping_bookings_single_winner` and `test_concurrent_bookings_for_different_providers_all_succeed`, plus a whole-store invariant check (no two active appointments for the same provider overlap).

### 17. Manual test checklist and Swagger run
- **Date:** 2026-11-13
- **Activity type:** Verification
- **Prompt:**
  > give me a checklist that covers every point in the brief with example requests i can run myself in swagger for each one tell me what response i should expect
- **AI response (summary):** a checklist mapping every acceptance criterion and scope point in the brief to example requests for Swagger, with the expected status code and body for each.
- **Decision:** Accepted. The candidate ran every case by hand, checking results against the brief rather than against the automated tests, since a manual pass can catch gaps the tests share with the code.
- **How it was run:** `uvicorn app.api:app` with the real clock, using Swagger at `/docs`. All bookings used future dates. After each rejected request, the read endpoints were used to confirm nothing was saved.
- **Results:**

  | Brief point | Case | Expected | Result |
  |---|---|---|---|
  | AC1 | Valid booking | `201`, status `ACTIVE`, timestamps in `Z` | As expected |
  | AC2 | Same provider: identical, partly overlapping (start / end), containing, contained | `409 CONFLICT`, nothing saved | As expected |
  | AC2 | Different provider, same time | `201` | As expected |
  | AC3 | Back-to-back (one ends exactly when the next starts) | `201` | As expected |
  | UTC | `+05:30` start | `201`, stored in UTC (`Z`) | As expected |
  | UTC | `+05:30` booking overlapping an equivalent `Z` booking | `409 CONFLICT` | As expected |
  | AC4 | Cancel an active booking, then rebook the same slot | `200 CANCELLED`, then `201` | As expected |
  | AC4 | Cancel an unknown id | `404 NOT_FOUND` | As expected |
  | AC4 | Cancel an already-cancelled booking | `409 ALREADY_CANCELLED` | As expected |
  | AC5 | Naive timestamp, unparseable timestamp, `end == start`, `end < start` | `422 INVALID_INPUT`, nothing saved | As expected |
  | AC5 | Missing or blank `provider_id`, missing `start` / `end` | `422 INVALID_INPUT`, nothing saved | As expected |
  | Assumption | Start in the past | `422` "start must be in the future (UTC)" | As expected |
  | Entry 16 | Unknown field, wrong JSON type | `422 INVALID_INPUT`, nothing saved | As expected |
  | Entry 16 | Read endpoints for an existing and an unknown id | `200` / `404 NOT_FOUND` | As expected |
  | Entry 16 | Unknown route / wrong method | `404` / `405` in the shared error format | As expected |

- **Files / decisions affected:** none (verification only).
- **Verification:** every case behaved as expected; no code or test changes were needed.