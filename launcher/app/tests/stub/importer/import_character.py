#!/usr/bin/env python3
"""Stub of tools/characters/import_character.py for the launcher's tests: the progress lines only."""
import os
import sys
import time


def main():
    args = sys.argv[1:]
    remove = bool(args) and args[0] == "--remove"
    names = [a for a in (args[1:] if remove else args) if not a.startswith("--")]
    names = names[: next((i for i, a in enumerate(names) if "/" in a), len(names))]
    for i, name in enumerate(names):
        print("@step fighter %s %d %d" % (name, i + 1, len(names)), flush=True)
        time.sleep(float(os.environ.get("TTT2_STUB_STEP_SECONDS", "0.05")))
    print("@step shared", flush=True)
    for name in names:
        print("@%s %s" % ("removed" if remove else "added", name), flush=True)
    print("@done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
