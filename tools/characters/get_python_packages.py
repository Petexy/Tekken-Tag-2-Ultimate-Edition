#!/usr/bin/env python3
"""numpy and Pillow for this Python, without pip or a package manager (the launcher's Download beside "Missing: numpy
and Pillow for Python"): the wheels python_packages.lock.json pins for this Python version, downloaded from PyPI,
checked against their SHA-256 and unpacked into a folder of their own that the importer finds by itself
(~/.local/share/ttt2/python/cp313 for Python 3.13; see ttt2char/python_packages.py):

    python3 tools/characters/get_python_packages.py [--progress]
    python3 tools/characters/get_python_packages.py --relock      (maintainers: the lock filled again from PyPI)

When this Python has both already (its own, or got before), nothing is downloaded. --progress adds lines for the
launcher: @step download|unpack|check <text>, @progress <bytes> <of bytes>, @error <text>, @done. SIGTERM (the
launcher's Cancel) stops it and nothing is changed. Needs only Python 3 (with its ssl module).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    sys.path.insert(0, HERE)
    from ttt2char import InputError, signals, python_packages
    signals.stop_on_signals()
    parser = argparse.ArgumentParser(description='Get numpy and Pillow for this Python into a folder of their own.')
    parser.add_argument('--progress', action='store_true', help='progress lines for the launcher')
    parser.add_argument('--relock', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()

    def progress(*words):
        if args.progress:
            print('@' + ' '.join(str(w) for w in words).replace('\n', ' '), flush=True)

    try:
        if args.relock:
            python_packages.relock()
            return
        missing = [name for name, module in python_packages.MODULES.items() if not importable(module)]
        if not missing:
            print('This Python (%s) has numpy and Pillow already: nothing to get.' % sys.executable)
        else:
            python_packages.get(progress=progress)
    except (InputError, OSError) as error:          # (OSError: their folder cannot be written, say)
        progress('error', error)
        sys.exit('get_python_packages: %s' % error)
    progress('done')


def importable(module):
    try:
        __import__(module)
        return True
    except Exception:                       # (ImportError, or whatever a broken installation raises)
        return False


if __name__ == '__main__':
    main()
