"""PostToolUse hook: run the pytest suite after Claude edits a Python file.

Reads the hook payload (JSON) from stdin. If the edited file is a .py file and a
tests/ directory exists, runs `pytest -q`. On failure, exits with code 2 and
writes the pytest output to stderr so Claude sees the failure and must address it.
On success, injects a one-line summary back into Claude's context.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}
    file_path = tool_input.get("file_path") or tool_response.get("filePath") or ""
    if not file_path.endswith(".py"):
        return 0

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    # Don't trigger on edits to this hook itself or other tooling under .claude/
    try:
        Path(file_path).resolve().relative_to(project_dir / ".claude")
        return 0
    except ValueError:
        pass

    if not (project_dir / "tests").is_dir():
        return 0

    # Prefer the project virtualenv if one exists.
    venv_python = project_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = str(venv_python) if venv_python.exists() else sys.executable

    try:
        result = subprocess.run(
            [python, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=110,
        )
    except subprocess.TimeoutExpired:
        print("pytest timed out after 110s (auto-run hook).", file=sys.stderr)
        return 2

    output = (result.stdout + result.stderr).strip()
    summary = output.splitlines()[-1] if output else "no output"

    if result.returncode == 0:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"Auto-run tests after editing {Path(file_path).name}: {summary}",
            }
        }))
        return 0

    if result.returncode == 5:  # no tests collected yet
        return 0

    tail = "\n".join(output.splitlines()[-60:])
    print(
        f"Tests FAILED after editing {Path(file_path).name}. Fix before continuing.\n\n{tail}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
