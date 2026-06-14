#!/usr/bin/env python3
"""PRAC-01 CI gate — ruff scoped to CHANGED LINES.

Runs ruff on the changed *.py files but fails only on violations located on
lines that were ADDED or MODIFIED in this change. Pre-existing violations on
untouched lines of a touched file are ignored, so a small edit to a debt-heavy
legacy file is not blocked by that file's existing lint debt — only the new or
changed lines must be clean. (File-scoping proved too aggressive for the repo's
~670 pre-existing violations; the full-repo cleanup is a separate follow-up.)

Usage: ruff_changed_lines.py <base-ref>
Discovers the changed *.py files itself (git diff vs <base-ref>) so it doesn't
depend on the caller's shell word-splitting. Exit 0 if every changed line is
clean (or there are no Python files), else 1.
"""
import json
import os
import re
import subprocess
import sys

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _changed_py_files(base: str) -> list:
    """Repo-relative *.py files added/modified between `base` and HEAD."""
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACM", f"{base}...HEAD", "--", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def _changed_lines(base: str, path: str) -> set:
    """Line numbers added/modified in `path` between `base` and HEAD."""
    diff = subprocess.run(
        ["git", "diff", "-U0", f"{base}...HEAD", "--", path],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    lines = set()
    for row in diff.splitlines():
        match = _HUNK.match(row)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) else 1
        lines.update(range(start, start + count))
    return lines


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: ruff_changed_lines.py <base-ref>", file=sys.stderr)
        return 2
    base = sys.argv[1]
    files = _changed_py_files(base)
    if not files:
        print("No changed Python files — nothing to lint.")
        return 0
    print("Changed Python files:")
    for f in files:
        print(f"  {f}")

    proc = subprocess.run(
        ["ruff", "check", "--output-format=json", *files],
        capture_output=True,
        text=True,
    )
    try:
        violations = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode or 1

    added = {os.path.realpath(f): _changed_lines(base, f) for f in files}
    failures = [
        v
        for v in violations
        if v.get("location", {}).get("row")
        in added.get(os.path.realpath(v["filename"]), set())
    ]

    if not failures:
        print(f"Ruff: no violations on changed lines across {len(files)} file(s).")
        return 0

    print(f"Ruff: {len(failures)} violation(s) on changed lines:\n")
    for v in failures:
        loc = v["location"]
        print(f"  {v['filename']}:{loc['row']}:{loc['column']} {v['code']} {v['message']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
