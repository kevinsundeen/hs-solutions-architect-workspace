#!/usr/bin/env python3
"""
test-on-edit.py — PostToolUse hook: run the _meta/scripts unit tests after Claude
edits a Python file under _meta/scripts/, and hand any failure back to Claude.

Reads hook JSON on stdin. Silent (exit 0) for any other file, or when the suite
passes. On failure, exits 2 with the tail of the test output on stderr, which
Claude Code feeds back to the model so it fixes the break before moving on.

The suite needs Python 3.11+ (tomllib, `X | None`); macOS /usr/bin/python3 is 3.9,
so this picks the first interpreter on the list that is new enough.

Stdlib only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
TESTS = SCRIPTS / "tests"
CANDIDATES = [sys.executable, "python3", "python3.13", "python3.12", "python3.11", "python3"]


def pick_python() -> str | None:
    for c in CANDIDATES:
        exe = c if Path(c).is_absolute() else shutil.which(c)
        if not exe or not Path(exe).exists():
            continue
        try:
            out = subprocess.run([exe, "-c", "import sys; print(sys.version_info >= (3, 11))"],
                                 capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.stdout.strip() == "True":
            return exe
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".py"):
        return 0
    try:
        Path(path).resolve().relative_to(SCRIPTS)
    except ValueError:
        return 0
    py = pick_python()
    if not py or not TESTS.is_dir():
        return 0
    try:
        res = subprocess.run([py, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                             cwd=SCRIPTS, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print("test-on-edit: _meta/scripts tests timed out after 60s.", file=sys.stderr)
        return 2
    if res.returncode == 0:
        return 0
    tail = "\n".join((res.stderr or res.stdout).strip().splitlines()[-40:])
    print(f"_meta/scripts tests FAILED after editing {Path(path).name}. Fix before continuing:\n{tail}",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
