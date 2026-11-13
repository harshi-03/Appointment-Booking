---
name: run-tests
description: Run the full pytest suite for the appointment booking service and report results, mapped to acceptance criteria. Use when asked to run tests, verify a change, or capture verification evidence for AI_USAGE.md.
---

# Run tests

1. Choose the interpreter: use `.venv/Scripts/python.exe` if it exists (Windows), else `.venv/bin/python`, else `python`.
2. Run the suite verbosely so test names are visible:
   ```bash
   <python> -m pytest -v
   ```
   If `$ARGUMENTS` is given (e.g. a file or `-k` expression), pass it through instead of running everything.
3. Report:
   - Pass/fail counts and duration (last line of pytest output).
   - For any failure: the test name, the assertion, and your diagnosis of the root cause. Do not just restate the error.
   - Which acceptance criteria (1–6 in CLAUDE.md / the brief) the passing tests cover, and any criterion with **no** test.
4. If the user wants evidence for the AI usage log, paste the exact command and the pytest summary line into the relevant `AI_USAGE.md` entry under **Verification**.

Never mark a failing test as skipped or xfail to make the suite pass unless the user explicitly asks.
