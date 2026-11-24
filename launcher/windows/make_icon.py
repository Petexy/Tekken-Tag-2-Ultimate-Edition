#!/usr/bin/env python3
"""The launcher's Windows icon: launcher/app/io.github.petexy.TekkenTag2UltimateEdition.svg drawn by rsvg-convert at
16 to 256 pixels, as one .ico (what make_launcher_exe.py puts in the release .exe, and what CMake's Windows builds of
the launcher get when they are given none: cmake/LauncherResources.cmake).

    python3 launcher/windows/make_icon.py [--rsvg-convert PROGRAM] OUTPUT.ico
"""
from pathlib import Path
import argparse
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_launcher_exe import make_icon  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('output', type=Path)
    parser.add_argument('--rsvg-convert', default=shutil.which('rsvg-convert'))
    args = parser.parse_args()
    if not args.rsvg_convert:
        sys.exit('make_icon.py: rsvg-convert is not installed (librsvg): it draws the icon')
    part = args.output.with_name(args.output.name + '.part')
    make_icon(part, args.rsvg_convert)
    part.replace(args.output)


if __name__ == '__main__':
    main()
