#!/usr/bin/env python3
"""Fetch the pinned sources the build needs into third_party/."""

import argparse
import functools
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


@functools.lru_cache(maxsize=None)
def git_for_windows():
    """Whether the Git on PATH is Git for Windows (MinGit too: "git version 2.56.0.windows.1"), whose cURL has the
    Windows TLS backend; another (MSYS2's, Cygwin's) has OpenSSL only and would stop at http.sslBackend=schannel."""
    try:
        said = subprocess.run(["git", "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True).stdout
    except OSError:
        return False
    return ".windows." in said


def git(directory, *args, capture=False, check=True):
    # These folders are this script's own downloads. Git refuses a repository whose owner is not the current user
    # ("dubious ownership"), and on Windows that is every folder on an exFAT or FAT32 drive, which records no owner,
    # or on a drive from another PC; only the command line or the user's own Git settings can allow it.
    options = ["-c", "safe.directory=*"]
    if os.name == "nt":
        options += ["-c", "core.longpaths=true"]
        # HTTPS trusts what Windows trusts (its certificate store, as curl.exe for the SDL download): Git's own
        # bundle setting can point at a file that is gone, e.g. one a former Git for Windows left in the user's or
        # the PC-wide Git settings, and then every download fails ("error adding trust anchors from file").
        if git_for_windows():
            options += ["-c", "http.sslBackend=schannel", "-c", "http.schannelUseSSLCAInfo=false"]
    # (stderr is not captured: what Git says goes into the setup log)
    return subprocess.run(["git", *options, "-C", str(directory), *args], check=check,
                          stdout=subprocess.PIPE if capture else None, text=True)


def unfinished(directory):
    """A download an earlier setup left before its first checkout (no network, or Git refused or was missing): nothing
    in the folder but .git, or nothing at all."""
    return [entry.name for entry in directory.iterdir()] in ([], [".git"])


def repair_missing_windows_files(directory):
    # A failed long-path checkout can still leave HEAD at the pinned commit.
    # Restore only missing tracked dependency files, preserving modified files.
    if os.name != 'nt':
        return
    missing = git(directory, 'ls-files', '--deleted', '-z', capture=True).stdout.split('\0')
    missing = [name for name in missing if name]
    for start in range(0, len(missing), 32):
        git(directory, 'restore', '--source=HEAD', '--worktree', '--', *missing[start:start + 32])
    if missing:
        print('%s: restored %d missing dependency files' % (directory, len(missing)))


def main():
    dependencies = json.loads((ROOT / "dependencies.lock.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="Default: all of dependencies.lock.json")
    parser.add_argument("--windows", action="store_true", help="Include native Windows build dependencies")
    parser.add_argument("--launcher", action="store_true",
                        help="Include the launcher's own (SDL 3's source, built into its release programs); "
                             "a player's game setup does not need them")
    args = parser.parse_args()
    for wanted, lock in ((args.windows, "dependencies.windows.lock.json"),
                         (args.launcher, "dependencies.launcher.lock.json")):
        if wanted:
            dependencies.update(json.loads((ROOT / lock).read_text()))
    selected = args.names or list(dependencies)
    for name in selected:
        if name not in dependencies:
            parser.error(f"Unknown dependency: {name}")
    for name in selected:
        dependency = dependencies[name]
        directory = ROOT / "third_party" / name
        if not directory.exists() or unfinished(directory):
            directory.mkdir(parents=True, exist_ok=True)
            git(directory, "init", "--quiet")
            git(directory, "fetch", "--depth", "1", dependency["url"], dependency["revision"])
            git(directory, "checkout", "--detach", "FETCH_HEAD")
        actual = git(directory, "rev-parse", "--verify", "--quiet", "HEAD", capture=True, check=False).stdout.strip()
        if actual != dependency["revision"]:
            parser.exit(1, f"Refusing to change existing {directory}: expected {dependency['revision']}, "
                           f"got {actual or 'no checkout'}. Delete that folder and start again.\n")
        repair_missing_windows_files(directory)
        print(f"{name}: {actual}")


if __name__ == "__main__":
    main()
