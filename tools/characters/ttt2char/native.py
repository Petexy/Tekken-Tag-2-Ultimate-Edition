"""C helpers shipped as source in ttt2char, compiled on the player's PC when first needed.

Some steps call code that has to run natively (Tekken 8's own Oodle decompressor, tekken8/oodle.c) or would be too
slow in Python (the mesh decimator, convert/decimate.c). They are shipped as C source and built with the system's C
compiler (Clang first on Windows; gcc, cc, clang on Linux, then $CC) into the cache:
$XDG_CACHE_HOME/ttt2/native/<name>.so (.dll on Windows; ~/.cache when
XDG_CACHE_HOME is not set). A build is redone when it is missing, older than its source or was made with other
compiler options (its .cmd file records them); it is written under a temporary name and renamed into place, so two
importers starting at once do not see half a file.
$TTT2_NATIVE_<NAME> (the name in capitals) can name a prebuilt file to use instead (a packaged launcher may ship
them).

Written for this project (no third-party code).
"""
import os
import shutil
import subprocess
import tempfile

from . import InputError

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))       # ttt2char/: sources are below it
CACHE = os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'ttt2', 'native')
COMPILERS = ('clang', 'gcc', 'cc') if os.name == 'nt' else ('gcc', 'cc', 'clang')
FLAGS = ('-O2', '-std=gnu11', '-Wall')      # every build; a kind's and the caller's flags follow
KINDS = {'shared': ('.dll', ('-shared',)) if os.name == 'nt' else ('.so', ('-shared', '-fPIC')),
         'executable': ('.exe' if os.name == 'nt' else '', ())}
OUTPUT_TAIL = 2000                          # characters of the compiler's output an error message quotes


def compiler():
    """The C compiler to build with (a path), or None."""
    for name in COMPILERS:
        path = shutil.which(name)
        if path:
            return path
    cc = os.environ.get('CC')
    if cc:
        return shutil.which(cc) or (cc if os.path.isfile(cc) else None)
    return None


def _source_path(source):
    return source if os.path.isabs(source) else os.path.join(PACKAGE_DIR, source)


def output_path(name, kind='shared', cache=None):
    """Where build() puts `name`'s build."""
    return os.path.join(cache or CACHE, name + KINDS[kind][0])


def _command(cc, src, out, kind, flags, libs):
    return [cc] + list(FLAGS) + list(KINDS[kind][1]) + list(flags) + ['-o', out, src] + list(libs)


def _stamp(cmd, out):
    """A build's options without its paths (they change between temporary and final names)."""
    return ' '.join(c for c in cmd[1:] if c != out)


def build(name, source, kind='shared', flags=(), libs=(), cache=None, dependencies=()):
    """The path of a built `source` (a C file; relative paths are below ttt2char/), building it when needed.

    kind: 'shared' (a library for ctypes) or 'executable'; flags: extra compiler options (e.g. '-O3'); libs: linker
    arguments after the source (e.g. '-lm'); dependencies: additional source headers to check for changes.
    $TTT2_NATIVE_<NAME> names a prebuilt file to use instead."""
    if kind not in KINDS:
        raise ValueError('unknown native build kind %r' % kind)
    prebuilt = os.environ.get('TTT2_NATIVE_' + name.upper())
    if prebuilt:
        if not os.path.isfile(prebuilt):
            raise InputError('$TTT2_NATIVE_%s names %s, which does not exist: unset it to build %s here' %
                             (name.upper(), prebuilt, name))
        return prebuilt
    src = _source_path(source)
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    out = output_path(name, kind, cache)
    stamp_file = out + '.cmd'
    cc = compiler()
    wanted = _stamp(_command(cc or 'cc', src, out, kind, flags, libs), out)
    newest = max(os.path.getmtime(p) for p in [src] + [_source_path(p) for p in dependencies])
    if os.path.isfile(out) and os.path.getmtime(out) >= newest:
        try:
            with open(stamp_file) as f:
                if f.read() == wanted:
                    return out
        except OSError:
            pass
    if cc is None:
        raise InputError('Building the %s helper needs a C compiler, and none was found (gcc, cc or clang): install '
                         'gcc (Arch: pacman -S gcc; Debian/Ubuntu: apt install gcc; Fedora: dnf install gcc) and try '
                         'again' % name)
    folder = os.path.dirname(out)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.%s.' % name, suffix=KINDS[kind][0], dir=folder)
    os.close(fd)
    try:
        cmd = _command(cc, src, tmp, kind, flags, libs)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            text = (r.stderr or r.stdout or '').strip()
            raise InputError('Building the %s helper with %s failed (the C library headers may be missing: Debian/'
                             'Ubuntu: apt install build-essential):\n%s' % (name, cc, text[-OUTPUT_TAIL:]))
        os.chmod(tmp, 0o755)
        os.replace(tmp, out)
        with open(stamp_file, 'w') as f:
            f.write(wanted)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return out
