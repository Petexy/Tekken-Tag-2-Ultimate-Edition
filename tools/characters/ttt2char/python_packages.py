"""numpy and Pillow for a Python that has neither, got without pip or a package manager (SteamOS, Bazzite and other
systems whose own files cannot change, whose Python often has no pip either): the wheels PyPI publishes for this
Python, downloaded (get_python_packages.py: the launcher's Download) and unpacked into a folder of their own, which
the importer puts on its path before the system's packages (ttt2char/__init__.py).

Which files: python_packages.lock.json pins, for each Python version, each package's wheel for CPython on Linux
x86-64 (manylinux: needing a glibc no newer than its name says), with its size and SHA-256 as PyPI lists them. A file
is used only when its digest is the pinned one: what runs is what the release was made with, whatever the network or
the index serves later (as tools/windows-bootstrap.lock.json pins the Windows tools). A Python version the lock does
not have is refused, saying so; `get_python_packages.py --relock` fills the lock again from PyPI's JSON API for the
versions it names (a new Python version: add its entries, then relock).

The folder (paths.python_packages(): ~/.local/share/ttt2/python/cp313 for CPython 3.13) is made whole beside its
place and renamed into it, so an import never sees half of it; each Python version has its own (their compiled
parts are for that version only). Nothing else is changed: no pip, nothing of the system's Python.

Written for this project (no third-party code).
"""
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

from . import InputError, paths, signals

LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'python_packages.lock.json')
PACKAGES = ('numpy', 'Pillow')
MODULES = {'numpy': 'numpy', 'Pillow': 'PIL.Image'}     # (what the importer imports of each)
PYPI = 'https://pypi.org/pypi/%s/%s/json'
# the platform tags manylinux had before they named the glibc they need (PEP 600)
LEGACY = {'manylinux1': (2, 5), 'manylinux2010': (2, 12), 'manylinux2014': (2, 17)}
# what checks a folder: its packages imported before any other (the folder is the program's first argument)
CHECK = 'import sys; sys.path.insert(0, sys.argv[1]); import numpy, PIL, PIL.Image; print(numpy.__version__, ' \
        'PIL.__version__)'


def python():
    """This Python as the lock names it: '3.13'."""
    return '%d.%d' % sys.version_info[:2]


def glibc():
    """This system's glibc version, (2, 41); None without glibc (musl)."""
    try:
        found = re.match(r'glibc (\d+)\.(\d+)', os.confstr('CS_GNU_LIBC_VERSION') or '')
    except (AttributeError, ValueError, OSError):
        found = None
    return (int(found.group(1)), int(found.group(2))) if found else None


def needs_glibc(name):
    """The oldest glibc a wheel (its file name) runs on: the least of its manylinux platform tags; None for none."""
    tags = name[:-len('.whl')].split('-')[-1].split('.') if name.endswith('.whl') else []
    found = []
    for tag in tags:
        m = re.match(r'manylinux_(\d+)_(\d+)_x86_64$', tag)
        if m:
            found.append((int(m.group(1)), int(m.group(2))))
        elif tag.rsplit('_x86_64', 1)[0] in LEGACY and tag.endswith('_x86_64'):
            found.append(LEGACY[tag.rsplit('_x86_64', 1)[0]])
    return min(found) if found else None


def load(lock=LOCK):
    with open(lock, encoding='utf-8') as f:
        return json.load(f)


def wheels(lock=LOCK):
    """The lock's wheels for this Python on this system, or InputError: why there are none."""
    if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'AMD64'):
        raise InputError('the launcher gets numpy and Pillow only for Linux on x86-64 PCs')
    if sys.implementation.name != 'cpython' or 't' in getattr(sys, 'abiflags', ''):
        raise InputError('the launcher gets numpy and Pillow only for the usual CPython (this one is %s%s)'
                         % (platform.python_implementation(), ' without the GIL' if 't' in sys.abiflags else ''))
    pinned = load(lock)
    if python() not in pinned:
        raise InputError('the launcher gets numpy and Pillow for Python %s only, not %s'
                         % (', '.join(sorted(pinned, key=lambda v: tuple(map(int, v.split('.'))))), python()))
    have = glibc()
    for entry in pinned[python()]:
        need = needs_glibc(os.path.basename(entry['url']))
        if have is None or need is None or have < need:
            raise InputError('%s %s needs glibc %s or newer, and this system has %s'
                             % (entry['name'], entry['version'], '.'.join(map(str, need or (0, 0))),
                                'glibc ' + '.'.join(map(str, have)) if have else 'no glibc'))
    return pinned[python()]


def status(lock=LOCK):
    """{folder, size, error} for launcher.py status: where they go, the bytes to download, and why the launcher
    cannot get them here (None when it can)."""
    try:
        size, error = sum(e['size'] for e in wheels(lock)), None
    except (InputError, OSError, ValueError, KeyError) as e:
        size, error = 0, str(e)
    return {'folder': paths.python_packages(), 'size': size, 'error': error}


def _download(entry, target, done, total, progress):
    """One wheel into `target`, its size and digest checked -> the bytes done after it."""
    name = os.path.basename(entry['url'])
    digest = hashlib.sha256()
    shown = 0.0
    request = urllib.request.Request(entry['url'], headers={'User-Agent': 'ttt2-launcher'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(target, 'wb') as out:
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if time.monotonic() - shown > 0.2:
                    shown = time.monotonic()
                    progress('progress', done, total)
    except OSError as e:
        raise InputError('cannot download %s from PyPI (%s): check the internet connection and try again'
                         % (name, getattr(e, 'reason', None) or e))
    if os.path.getsize(target) != entry['size'] or digest.hexdigest() != entry['sha256']:
        raise InputError('%s from PyPI is not the file the launcher expects (its size or SHA-256 differs): nothing '
                         'was changed; try again later' % name)
    progress('progress', done, total)
    return done


def _unpack(wheel, folder):
    """A wheel's files into `folder` as pip puts them in site-packages (a .data folder's purelib and platlib too;
    its scripts and headers are not needed), refusing any path that leads out of it or is a link."""
    with zipfile.ZipFile(wheel) as z:
        for info in z.infolist():
            parts = info.filename.split('/')
            mode = info.external_attr >> 16
            if info.filename.startswith('/') or '\\' in info.filename or '..' in parts or stat.S_ISLNK(mode):
                raise InputError('%s holds a file it must not (%s)' % (os.path.basename(wheel), info.filename))
            if parts[0].endswith('.data'):
                if len(parts) < 3 or parts[1] not in ('purelib', 'platlib'):
                    continue
                parts = parts[2:]
            if info.is_dir() or not parts[-1]:
                continue
            path = os.path.join(folder, *parts)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with z.open(info) as src, open(path, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            if mode & 0o111:
                os.chmod(path, 0o755)


def get(folder=None, lock=LOCK, log=print, progress=lambda *words: None):
    """Downloads this Python's pinned numpy and Pillow, checks them, and puts them in `folder` (default:
    paths.python_packages()), replacing what was there -> {name: version} as they import."""
    entries = wheels(lock)
    folder = os.path.abspath(folder or paths.python_packages())
    parent = os.path.dirname(folder)
    os.makedirs(parent, exist_ok=True)
    total = sum(e['size'] for e in entries)
    names = ' and '.join('%s %s' % (e['name'], e['version']) for e in entries)
    log('%s for Python %s: %.1f MB from PyPI (pypi.org), into %s' % (names, python(), total / 1e6, folder))
    work = tempfile.mkdtemp(prefix='.get-', dir=parent)
    try:
        progress('step', 'download', 'Downloading ' + names)
        done = 0
        for e in entries:
            log('Downloading %s' % e['url'])
            done = _download(e, os.path.join(work, os.path.basename(e['url'])), done, total, progress)
        progress('step', 'unpack', 'Unpacking them')
        packages = os.path.join(work, 'packages')
        for e in entries:
            _unpack(os.path.join(work, os.path.basename(e['url'])), packages)
        progress('step', 'check', 'Checking that they work')
        checked = subprocess.run([sys.executable, '-c', CHECK, packages], capture_output=True, text=True)
        if checked.returncode != 0:
            raise InputError('numpy and Pillow do not work with this Python after all: %s'
                             % ((checked.stderr or checked.stdout).strip().splitlines() or ['?'])[-1])
        versions = dict(zip(('numpy', 'Pillow'), checked.stdout.split()))
        with open(os.path.join(packages, '.ttt2-packages.json'), 'w', encoding='utf-8') as f:
            json.dump({'python': python(), 'wheels': entries}, f, indent=1)
        with signals.deferred():            # (never without a folder in place once one was there)
            old = None
            if os.path.lexists(folder):
                old = os.path.join(work, 'old')
                os.rename(folder, old)
            os.rename(packages, folder)
        log('numpy %s and Pillow %s work: they are in %s' % (versions.get('numpy', '?'), versions.get('Pillow', '?'),
                                                              folder))
        return versions
    finally:
        shutil.rmtree(work, ignore_errors=True)


def relock(lock=LOCK, log=print):
    """The lock filled again from PyPI's JSON API: for each Python version in it and each of its packages' versions,
    the cpXY wheel for manylinux x86-64 that needs the oldest glibc (its url, size and sha256)."""
    pinned = load(lock)
    for version, entries in pinned.items():
        tag = 'cp' + version.replace('.', '')
        for e in entries:
            with urllib.request.urlopen(PYPI % (e['name'], e['version']), timeout=60) as response:
                files = json.load(response)['urls']
            found = []
            for f in files:
                parts = f['filename'][:-len('.whl')].split('-') if f['filename'].endswith('.whl') else []
                if len(parts) >= 5 and parts[-3] == tag and parts[-2] == tag and needs_glibc(f['filename']):
                    found.append((needs_glibc(f['filename']), f))
            if not found:
                raise InputError('PyPI has no %s %s wheel for %s on manylinux x86-64' % (e['name'], e['version'], tag))
            f = min(found, key=lambda x: x[0])[1]
            e.update(url=f['url'], size=f['size'], sha256=f['digests']['sha256'])
            log('Python %s: %s' % (version, f['filename']))
    with open(lock + '.part', 'w', encoding='utf-8') as out:
        out.write('{\n' + ',\n'.join('  %s: [\n%s\n  ]' % (json.dumps(v), ',\n'.join('    ' + json.dumps(e)
                                                                                     for e in entries))
                                     for v, entries in pinned.items()) + '\n}\n')
    os.replace(lock + '.part', lock)
