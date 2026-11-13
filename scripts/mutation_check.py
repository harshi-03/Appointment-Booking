"""Mutation check: plant one deliberate bug at a time and confirm the test suite catches it.

Each mutant is a small source edit (e.g. `<` -> `<=` in the overlap check) applied to a
temporary COPY of app/ and tests/; the project files are never modified. A mutant that
"survives" (all tests still pass) means a rule is not actually protected by the tests.

Usage, from the project root:
    .venv\\Scripts\\python.exe scripts\\mutation_check.py        (Windows)
    .venv/bin/python scripts/mutation_check.py                  (macOS / Linux)
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S, A, M = "app/service.py", "app/api.py", "app/models.py"
FUTURE_CHECK = '            if start_utc <= self._now():\n                raise InvalidInputError("start must be in the future (UTC)", "start")\n'

# (name, file, [(find, replace), ...]) -- each `find` must occur exactly once.
MUTANTS = [
    # --- booking invariant ---
    ("overlap uses <= (breaks adjacency)", S, [("return start < other.end and other.start < end", "return start <= other.end and other.start <= end")]),
    ("cancelled appointments still block", S, [("and existing.status is AppointmentStatus.ACTIVE", "and True")]),
    ("providers conflict with each other", S, [("existing.provider_id == provider", "True")]),
    ("scan stops after the first appointment", S, [("            appointment = Appointment(", "                break\n            appointment = Appointment(")]),
    ("cancel result not stored", S, [("            self._appointments[appointment_id] = cancelled", "            pass")]),
    ("appointments mutable (not frozen)", M, [("@dataclass(frozen=True)\nclass Appointment:", "@dataclass\nclass Appointment:")]),
    ("overlap check only rejects exact duplicates", S, [("and _overlaps(start_utc, end_utc, existing)", "and existing.start == start_utc")]),
    # --- locking / time ---
    ("no lock in book()", S, [("        with self._lock:\n" + FUTURE_CHECK, "        if True:\n" + FUTURE_CHECK)]),
    ("no lock in cancel()", S, [("        with self._lock:\n            appointment = self._find(appointment_id)", "        if True:\n            appointment = self._find(appointment_id)")]),
    ("insert outside the lock", S, [("            self._appointments[appointment.id] = appointment\n        return appointment", "        self._appointments[appointment.id] = appointment\n        return appointment")]),
    ("overlap scan outside the lock", S, [
        ("        with self._lock:\n" + FUTURE_CHECK, "        existing_all = list(self._appointments.values())\n        with self._lock:\n" + FUTURE_CHECK),
        ("            for existing in self._appointments.values():", "            for existing in existing_all:")]),
    ("future check before the lock", S, [("        with self._lock:\n" + FUTURE_CHECK, FUTURE_CHECK.replace("            ", "        ", 1).replace("                raise", "            raise") + "        with self._lock:\n")]),
    ("future check allows start == now", S, [("if start_utc <= self._now():", "if start_utc < self._now():")]),
    ("extra time check after insert", S, [("            self._appointments[appointment.id] = appointment\n", "            self._appointments[appointment.id] = appointment\n            if start_utc <= self._now():\n                raise InvalidInputError('late')\n")]),
    ("default clock is naive", S, [("return datetime.now(timezone.utc)", "return datetime.now()")]),
    ("naive clock not detected", S, [("        if not isinstance(now, datetime) or now.utcoffset() is None:\n            raise RuntimeError", "        if False:\n            raise RuntimeError")]),
    # --- validation ---
    ("zero duration allowed", S, [("if end_utc <= start_utc:", "if end_utc < start_utc:")]),
    ("no UTC conversion", S, [("return parsed.astimezone(timezone.utc)", "return parsed")]),
    ("tz without offset accepted", S, [("if parsed.tzinfo is None or parsed.utcoffset() is None:", "if parsed.tzinfo is None:")]),
    ("provider stored unstripped", S, [("    return value.strip()", "    return value")]),
    ("un-encodable id accepted", S, [('        value.encode("utf-8")\n    except UnicodeEncodeError:', '        pass\n    except UnicodeEncodeError:')]),
    ("cancel/get look up a stripped id", S, [("        appointment = self._appointments.get(appointment_id)", "        appointment = self._appointments.get(appointment_id.strip())")]),
    ("raw input echoed in full", S, [("{_preview(appointment_id)} not found", "{appointment_id} not found")]),
    ("unknown field name echoed in full", A, [("field = _preview(location[-1]) if location", "field = location[-1] if location")]),
    # --- read-only verification aids ---
    ("list not sorted by start", S, [("return sorted(appointments, key=lambda a: (a.start, a.end))", "return appointments")]),
    ("list includes other providers", S, [("if a.provider_id == provider]", "if True]")]),
    ("list ignores provider normalisation", S, [('        provider = _require_id(provider_id, "provider_id")\n        with self._lock:\n            appointments', '        _require_id(provider_id, "provider_id")\n        provider = provider_id\n        with self._lock:\n            appointments')]),
    # --- API contract ---
    ("conflicting id not exposed", A, [('conflicting_appointment_id=getattr(exc, "conflicting_id", None),', "conflicting_appointment_id=None,")]),
    ("API fills a missing end", A, [("booking.book(request.provider_id, request.start, request.end)", "booking.book(request.provider_id, request.start, request.end or request.start)")]),
    ("API drops microseconds", A, [("return value.isoformat().replace", "return value.replace(microsecond=0).isoformat().replace")]),
    ("unknown fields ignored", A, [('model_config = ConfigDict(extra="forbid")', 'model_config = ConfigDict(extra="ignore")')]),
    ("error field not exposed", A, [('            getattr(exc, "field", None),\n', "            None,\n")]),
    ("undecodable body gives FastAPI 400", A, [("        if exc.status_code == 400 and exc.detail == _BODY_PARSE_ERROR:", "        if False:")]),
    ("every 400 relabelled as invalid JSON", A, [("        if exc.status_code == 400 and exc.detail == _BODY_PARSE_ERROR:", "        if exc.status_code == 400:")]),
    ("404/405 use FastAPI default body", A, [('        return _error(exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))', '        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})')]),
    ("405 loses its Allow header", A, [('str(exc.detail), headers=getattr(exc, "headers", None))', "str(exc.detail), headers=None)")]),
    ("no generic 500 handler", A, [("@app.exception_handler(Exception)", "@app.exception_handler(KeyError)")]),
]
# Deliberately not listed: giving cancel() its own separate lock. Cancel can only turn ACTIVE
# into CANCELLED (it frees time, never creates an overlap), so the behaviour is unchanged.


TIMEOUT_SECONDS = 120


def run_mutant(name: str, rel: str, edits: list) -> str:
    """Return CAUGHT (a test failed), SURVIVED (all passed), BROKEN (the mutant didn't import or
    collect, so no test actually ran against it) or TIMEOUT (e.g. a deadlock)."""
    work = Path(tempfile.mkdtemp(prefix="mutant-"))
    try:
        for item in ("app", "tests"):
            shutil.copytree(ROOT / item, work / item, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / "pytest.ini", work)
        target = work / rel
        text = target.read_text(encoding="utf-8")
        for find, replace in edits:
            if text.count(find) != 1:
                raise SystemExit(f"pattern for '{name}' not found exactly once: {find!r}")
            text = text.replace(find, replace)
        target.write_text(text, encoding="utf-8")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
                cwd=work, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT"
        # pytest exit codes: 0 = all passed, 1 = tests failed, 2-5 = interrupted/usage/collection
        # problems. Only a real test failure counts as catching the bug.
        return {0: "SURVIVED", 1: "CAUGHT"}.get(result.returncode, "BROKEN")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    not_caught = []
    for name, rel, edits in MUTANTS:
        outcome = run_mutant(name, rel, edits)
        print(f"{outcome:8} | {name}")
        if outcome != "CAUGHT":
            not_caught.append(name)
    print(f"\n{len(MUTANTS) - len(not_caught)}/{len(MUTANTS)} mutants caught by a failing test")
    sys.exit(1 if not_caught else 0)
