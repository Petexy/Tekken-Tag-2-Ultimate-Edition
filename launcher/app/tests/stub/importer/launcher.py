#!/usr/bin/env python3
"""Stub of tools/characters/launcher.py for the launcher's tests: answers from $TTT2_STUB_CASE (a golden case)."""
import json
import os
import sys


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    case_file = os.environ.get("TTT2_STUB_CASE", "")
    case = {}
    if case_file:
        with open(case_file, encoding="utf-8") as f:
            case = json.load(f)
    if what == "status" and isinstance(case.get("status_fail"), str):
        print("Traceback (most recent call last):", file=sys.stderr)
        print(case["status_fail"], file=sys.stderr)
        return 1
    answer = case.get(what)
    if answer is None:
        print(json.dumps({"error": "not in the fixture"}))
        return 1 if what == "main" else 0
    print(json.dumps(answer))
    return 0


if __name__ == "__main__":
    sys.exit(main())
