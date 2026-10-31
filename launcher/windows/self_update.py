"""The Windows launcher's own updates, as the Linux AppImage's
(launcher/core/release.cpp, launcher/app/self_update.cpp).

The release's Ultimate_Launcher-x86_64.exe (entry.cpp with the project's
files in it, make_launcher_exe.py) opens this launcher with
TTT2_LAUNCHER_EXE naming it. Only then is GitHub asked for this repository's
newest release; when that one is newer, Update downloads its .exe beside the
one that was started, checks it (its size, the SHA-256 GitHub gives, that it
is a 64-bit Windows program with its files, and that they are the version it
was released as), puts it in that one's place and opens it as this launcher
closes. Anything failing leaves the .exe as it was.

A test build's .exe (one made from a branch other than main) updates its files
instead: when its branch has newer commits on GitHub, Update downloads the
newest one's files and puts them in place of the ones the .exe unpacked
(update_files), so a fix pushed to the branch reaches testers without a new
.exe.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import contextlib
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
# The newest release as GitHub's API gives it (drafts and pre-releases are
# never it). $TTT2_LAUNCHER_RELEASES is asked instead when set (tests).
LATEST = 'https://api.github.com/repos/Petexy/Tekken-Tag-2-Ultimate-Edition/releases/latest'
# The .exe this launcher was opened from (entry.cpp sets it).
EXE_VARIABLE = 'TTT2_LAUNCHER_EXE'
# The pid of the launcher an update replaces: the new .exe waits for it to end.
REPLACES_VARIABLE = 'TTT2_LAUNCHER_AFTER'
# entry.cpp's trailer after its files: their size, count, SHA-256, magic.
TRAILER = struct.Struct('<QQ32s8s')
MAGIC = b'TTT2PAY1'
# How long between two quiet questions to GitHub, while the window stays open.
CHECK_SECONDS = 6 * 3600
# The commit the release .exe was made from (make_launcher_exe.py writes it into its files).
BUILD_COMMIT = 'launcher/windows/build-commit'
# The branch it was made from: main for a release, another for a test build.
BUILD_BRANCH = 'launcher/windows/build-branch'
# What entry.cpp unpacked last: their SHA-256, then their paths.
STAMP = 'local/launcher-files.txt'
REPOSITORY = 'Petexy/Tekken-Tag-2-Ultimate-Edition'


class UpdateError(Exception):
    """Why the launcher cannot be updated, as a sentence for the player."""


class Cancelled(Exception):
    pass


def version_of(text):
    """The version launcher/builder/CMakeLists.txt's text names (TTT2_LAUNCHER_VERSION), or ''."""
    found = re.search(r'^set\(TTT2_LAUNCHER_VERSION ([0-9.]+)\)', text, re.M)
    return found.group(1) if found else ''


@lru_cache(maxsize=None)
def version(root=ROOT):
    """This launcher's version: the Linux launcher's (one release has both)."""
    number = version_of((Path(root) / 'launcher/builder/CMakeLists.txt').read_text(encoding='utf-8'))
    if not number: raise ValueError('launcher/builder/CMakeLists.txt names no TTT2_LAUNCHER_VERSION')
    return number


def build_commit(root=ROOT):
    """The commit these files are: the release .exe's, else a Git checkout's HEAD; None when not known
    (a project ZIP)."""
    file = Path(root) / BUILD_COMMIT
    if file.is_file(): return file.read_text(encoding='utf-8').strip() or None
    git = Path(root) / '.git'
    try:
        if git.is_file():       # (a worktree: its Git folder is named there, its branches in the shared one)
            git = (Path(root) / git.read_text(encoding='utf-8').split('gitdir:', 1)[1].strip()).resolve()
        shared = (git / (git / 'commondir').read_text(encoding='utf-8').strip()).resolve() \
            if (git / 'commondir').is_file() else git
        head = (git / 'HEAD').read_text(encoding='utf-8').strip()
        if not head.startswith('ref: '): return head
        ref = head[5:]
        for folder in (git, shared):
            if (folder / ref).is_file(): return (folder / ref).read_text(encoding='utf-8').strip()
        for line in (shared / 'packed-refs').read_text(encoding='utf-8').splitlines():
            if line.endswith(' ' + ref): return line.split()[0]
    except (OSError, IndexError):
        pass
    return None


def build_branch(root=ROOT):
    """The branch the release .exe was made from; None when not known."""
    file = Path(root) / BUILD_BRANCH
    return (file.read_text(encoding='utf-8').strip() or None) if file.is_file() else None


def test_branch(root=ROOT):
    """The branch whose newer commits update these files in place (update_files): a test build's; None for a
    release (main's), a Git checkout or a project ZIP."""
    branch = build_branch(root)
    return branch if branch and branch != 'main' and (Path(root) / STAMP).is_file() else None


def files_id(root=ROOT):
    """What the game built from these files is said to be from: the version, and the commit when the .exe's
    files are (so that a test build's update of its files asks for the game to be built again)."""
    file = Path(root) / BUILD_COMMIT
    commit = file.read_text(encoding='utf-8').strip() if file.is_file() else ''
    return version(root) + (' ' + commit if commit else '')


def shown_id(text):
    """files_id() for the player: "0.4.0 (396cc69)"."""
    number, _, commit = text.partition(' ')
    return number + (' (%s)' % commit[:7] if commit else '')


def version_numbers(text):
    """A version's numbers ("0.1.0", "v0.2", "V1.10.3"); None when it is not one."""
    if text[:1] in ('v', 'V'): text = text[1:]
    parts = text.split('.')
    if not all(p.isascii() and p.isdigit() and len(p) <= 9 for p in parts): return None
    return [int(p) for p in parts]


def compare_versions(a, b):
    """Below 0, 0, above 0 as `a` is older than, the same as or newer than `b`
    (a missing number is 0); None when either is not a version."""
    x, y = version_numbers(a), version_numbers(b)
    if x is None or y is None: return None
    n = max(len(x), len(y))
    x, y = x + [0] * (n - len(x)), y + [0] * (n - len(y))
    return (x > y) - (x < y)


def newer_release(number, root=ROOT):
    """Whether a release of version `number` is newer than these files: a later version, or, for a test
    build, its own version's release (which comes after the tests)."""
    order = compare_versions(number, version(root))
    return order is not None and (order > 0 or order == 0 and test_branch(root) is not None)


@dataclass
class Release:
    version: str
    tag: str
    page: str       # its page on GitHub (what is new in it)
    asset: str      # the .exe's file name
    url: str        # where it is downloaded from
    size: int = 0
    sha256: str = ''  # lowercase hex, when GitHub gives one


@dataclass
class Answer:
    """GitHub's answer: the release with its .exe, `none` when no release is
    published, else why it cannot be updated to."""
    release: Release = None
    none: bool = False
    error: str = ''


def parse_release(text):
    try:
        root = json.loads(text)
    except ValueError as error:
        return Answer(error="GitHub's answer is not readable (%s)" % error)
    if not isinstance(root, dict):
        return Answer(error="GitHub's answer is not readable (not an object)")
    if not isinstance(root.get('tag_name'), str):
        # An error: its message says which.
        message = root.get('message') if isinstance(root.get('message'), str) else ''
        if message == 'Not Found': return Answer(none=True)
        if 'rate limit' in message.lower():
            return Answer(error='GitHub answers only so many questions from one network an hour: try again later')
        return Answer(error='GitHub answered "%s"' % message if message else "GitHub's answer names no release")
    tag = root['tag_name']
    number = tag[1:] if tag[:1] in ('v', 'V') else tag
    if version_numbers(number) is None:
        return Answer(error='the newest release, %s, is not named as a version (such as v0.2.0)' % tag)
    # Its .exe for this kind of PC: one named for x86-64, else the only one
    # named for no processor.
    named, plain = None, []
    for asset in root.get('assets') or []:
        if not isinstance(asset, dict): continue
        name = str(asset.get('name', '')).lower()
        if not name.endswith('.exe') or asset.get('state', 'uploaded') != 'uploaded' or not asset.get('browser_download_url'):
            continue
        if any(word in name for word in ('x86_64', 'x86-64', 'amd64', 'x64')):
            named = named or asset
        elif not any(word in name for word in ('aarch64', 'arm', 'i686', 'i386', 'win32')):
            plain.append(asset)
    chosen = named or (plain[0] if len(plain) == 1 else None)
    if not chosen: return Answer(error='version %s has no Windows launcher (.exe) to download' % number)
    size = chosen.get('size')
    digest = str(chosen.get('digest') or '').lower()
    return Answer(release=Release(
        version=number, tag=tag, page=str(root.get('html_url') or ''), asset=str(chosen['name']),
        url=str(chosen['browser_download_url']), size=size if isinstance(size, int) and size > 0 else 0,
        sha256=digest[7:] if digest.startswith('sha256:') and len(digest) == 7 + 64 else ''))


def custom_releases():
    return bool(os.environ.get('TTT2_LAUNCHER_RELEASES'))


def releases_url():
    return os.environ.get('TTT2_LAUNCHER_RELEASES') or LATEST


def user_agent():
    return 'ttt2-launcher/' + version()


def running_exe():
    """The release .exe this launcher was opened from; None otherwise (a
    project ZIP or a build: those are updated as a whole, not by this)."""
    value = os.environ.get(EXE_VARIABLE)
    return Path(value) if value and Path(value).is_absolute() and Path(value).is_file() else None


def reason(error):
    """Why a download failed, without Python's wrapping."""
    if isinstance(error, urllib.error.URLError) and not isinstance(error, urllib.error.HTTPError):
        error = error.reason
    if isinstance(error, OSError) and error.strerror: return error.strerror
    return str(error) or type(error).__name__


def sentence(text):
    text = text[:1].upper() + text[1:]
    return text if text.endswith('.') else text + '.'


def ask(url=None):
    """GitHub's answer about the newest release. OSError when it cannot be asked."""
    request = urllib.request.Request(url or releases_url(), headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': user_agent()})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return parse_release(response.read())
    except urllib.error.HTTPError as error:
        # (It says why: no release yet, or too many questions.)
        with error: body = error.read()
        if not body: raise
        return parse_release(body)


def update_file(exe):
    """Where the new .exe is downloaded to: beside the old one (one drive, so
    that it can be renamed over it)."""
    return exe.with_name(exe.stem + '.new.exe')


def old_file(exe):
    """Where the old .exe goes while the new one takes its place: a running
    .exe can be renamed but not replaced. The new one deletes it (entry.cpp)."""
    return exe.with_name(exe.stem + '.old.exe')


def cannot_replace(exe):
    """Why a new .exe cannot be put in the place of `exe` (its folder cannot
    be written to); empty when it can."""
    try:
        with tempfile.TemporaryFile(dir=exe.parent): pass
    except OSError as error:
        return reason(error)
    return ''


def stored_files(file):
    """The launcher's files in `file`, {path: bytes}, when it is a 64-bit Windows program holding them: entry.cpp's
    trailer after them (in its resource, or appended), with the SHA-256 of those files; else None. (The word alone
    is in the launcher's code too.)"""
    try:
        data = Path(file).read_bytes()
    except OSError:
        return None
    if len(data) < 64 or data[:2] != b'MZ': return None
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    if data[pe:pe + 6] != b'PE\0\0\x64\x86': return None
    at = len(data)
    while (at := data.rfind(MAGIC, 0, at)) >= TRAILER.size - len(MAGIC):
        start = at + len(MAGIC) - TRAILER.size
        size, count, digest, _ = TRAILER.unpack_from(data, start)
        if size <= start and hashlib.sha256(data[start - size:start]).digest() == digest: break
    else:
        return None
    # (As entry.cpp reads them: each one's path after its length, then its size and bytes; just those.)
    files, at = {}, start - size
    try:
        for _ in range(count):
            n, = struct.unpack_from('<I', data, at); path = data[at + 4:at + 4 + n].decode('utf-8'); at += 4 + n
            n, = struct.unpack_from('<Q', data, at); files[path] = data[at + 8:at + 8 + n]; at += 8 + n
    except (struct.error, UnicodeDecodeError):
        return None
    return files if at == start else None


def is_launcher_exe(file):
    """Whether `file` is a 64-bit Windows program holding a launcher's files (stored_files)."""
    return stored_files(file) is not None


def files_version(files):
    """The version of a launcher .exe's files (stored_files): the one its --version says, built from their
    launcher/builder/CMakeLists.txt; '' when they name none."""
    return version_of(files.get('launcher/builder/CMakeLists.txt', b'').decode('utf-8', 'replace'))


def version_in(output):
    """The version a launcher's --version names ("ttt2-launcher 0.2.0"), or ''."""
    for line in output.splitlines():
        words = line.split()
        if len(words) == 2 and words[0] == 'ttt2-launcher' and version_numbers(words[1]) is not None:
            return words[1]
    return ''


def sha256_of(file):
    with open(file, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(release, file, cancelled, say):
    request = urllib.request.Request(release.url, headers={'User-Agent': user_agent()})
    with urllib.request.urlopen(request, timeout=60) as response, open(file, 'wb') as out:
        total = release.size or int(response.headers.get('Content-Length') or 0)
        done, shown = 0, 0.0
        while chunk := response.read(1 << 16):
            if cancelled(): raise Cancelled()
            out.write(chunk)
            done += len(chunk)
            if total and (time.monotonic() - shown > 0.25 or done == total):
                say('@progress %d %d' % (done, total)); shown = time.monotonic()


def replace(update, exe):
    """`update` put in the place of `exe`; `exe` back as it was when it cannot be."""
    old = old_file(exe)
    with contextlib.suppress(FileNotFoundError): old.unlink()
    moved = exe.exists()
    if moved: os.replace(exe, old)
    try:
        os.replace(update, exe)
    except OSError:
        if moved: os.replace(old, exe)
        raise
    with contextlib.suppress(OSError): old.unlink()


def update(exe, cancelled=lambda: False, say=lambda line: print(line, flush=True)):
    """Updates `exe` to the newest release. Its version, or None when this one
    is the newest. UpdateError says why it cannot; Cancelled when cancelled."""
    current = version()
    say('@step update Looking for a newer version')
    try:
        answer = ask()
    except OSError as error:
        raise UpdateError('GitHub cannot be reached: %s.' % reason(error))
    release = answer.release
    if answer.none or (release and not newer_release(release.version)):
        say('No release is published yet.' if answer.none else 'The newest release is %s.' % release.tag)
        say('@step update The launcher is up to date: version %s is the newest.' % current)
        return None
    if not release: raise UpdateError(sentence(answer.error))
    if not custom_releases() and not release.url.startswith('https://'):
        raise UpdateError('Version %s is not offered over HTTPS.' % release.version)
    if why := cannot_replace(exe):
        raise UpdateError('Its folder, %s, cannot be written to (%s): move the launcher to a folder of yours, '
                          'then update it.' % (exe.parent, why))
    file = update_file(exe)
    try:
        with contextlib.suppress(FileNotFoundError): file.unlink()  # (one stopped half-way)
        say('@step update Downloading version ' + release.version)
        try:
            download(release, file, cancelled, say)
        except (OSError, ValueError) as error:
            raise UpdateError('Version %s cannot be downloaded: %s.' % (release.version, reason(error)))
        size = file.stat().st_size
        if release.size and size != release.size:
            raise UpdateError('The download of version %s is incomplete (%d of %d bytes).'
                              % (release.version, size, release.size))
        if release.sha256 and sha256_of(file) != release.sha256:
            raise UpdateError("The download of version %s is damaged: its SHA-256 is not GitHub's." % release.version)
        files = stored_files(file)
        if files is None:
            raise UpdateError('What was downloaded for version %s is not a Windows launcher.' % release.version)
        # It is the version it was released as (else each update would download it again), as its files say.
        # (Not by starting it, as the Linux launcher asks the new AppImage: on Windows, a program never seen
        # before is where virus scanners step in, and its start can wait on them for as long as they take, with
        # this update stuck behind it.)
        said = files_version(files)
        if not said:
            raise UpdateError('What was downloaded for version %s names no version.' % release.version)
        if compare_versions(said, release.version) != 0:
            raise UpdateError('The launcher released as version %s is version %s.' % (release.version, said))
        if cancelled(): raise Cancelled()
        try:
            replace(file, exe)
        except OSError as error:
            raise UpdateError('It cannot replace %s (%s).' % (exe, reason(error)))
    except BaseException:
        with contextlib.suppress(OSError): file.unlink()
        raise
    say('Version %s is in %s.' % (release.version, exe))
    say('@launcher-updated ' + release.version)
    return release.version


def github(path):
    """GitHub's answer about this repository (the API's /repos/<it>/<path>), as JSON. UpdateError when it cannot
    be asked, or says why not. ($TTT2_LAUNCHER_GITHUB is asked instead when set: tests.)"""
    url = (os.environ.get('TTT2_LAUNCHER_GITHUB') or 'https://api.github.com') + '/repos/' + REPOSITORY + '/' + path
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': user_agent()})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        with error: body = error.read()
        try:
            message = str(json.loads(body).get('message', ''))
        except (ValueError, AttributeError):
            message = ''
        if 'rate limit' in message.lower():
            raise UpdateError('GitHub answers only so many questions from one network an hour: try again later.')
        raise UpdateError('GitHub answered "%s".' % (message or error.code))
    except (OSError, ValueError) as error:
        raise UpdateError('GitHub cannot be reached: %s.' % reason(error))


def archive_url(commit):
    base = os.environ.get('TTT2_LAUNCHER_GITHUB')
    return base + '/archive/%s.zip' % commit if base else 'https://codeload.github.com/%s/zip/%s' % (REPOSITORY, commit)


def archive_files(data, commit):
    """{path: bytes} of GitHub's ZIP of `commit`, as make_launcher_exe.py packs a checkout's: batch files with
    Windows line ends. UpdateError when it is not this project at that commit."""
    short = commit[:7]
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UpdateError('What was downloaded for %s is not a ZIP archive.' % short)
    files, top = {}, None
    with archive:
        # (GitHub names the commit in the archive's comment.)
        if archive.comment and archive.comment.decode('ascii', 'replace').strip() != commit:
            raise UpdateError('What was downloaded for %s is another commit.' % short)
        for info in archive.infolist():
            if info.is_dir(): continue
            folder, _, path = info.filename.partition('/')
            top = top or folder
            parts = path.split('/')
            if folder != top or not path or '\\' in path or ':' in path or '..' in parts or '' in parts \
                    or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise UpdateError('What was downloaded for %s holds %s, which is not a plain file of the project.'
                                  % (short, info.filename))
            content = archive.read(info)
            # cmd.exe can miss a batch file's labels when its lines end in LF only.
            if path.lower().endswith(('.cmd', '.bat')): content = content.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            files[path] = content
    for needed in ('launcher/windows/main.py', 'launcher/windows/self_update.py', 'Start Ultimate Launcher.cmd',
                   'launcher/builder/CMakeLists.txt'):
        if needed not in files: raise UpdateError('What was downloaded for %s is not this project: it lacks %s.'
                                                  % (short, needed))
    return files


def write_file(file, data):
    """`data` in `file`, whole or not at all."""
    file.parent.mkdir(parents=True, exist_ok=True)
    part = file.with_name(file.name + '.part')
    part.write_bytes(data)
    os.replace(part, file)


def install_files(root, files):
    """`files` in place of the ones in the stamp (STAMP), as entry.cpp unpacks its own: files only those had are
    deleted, nothing else (local/, the builds, the generated code) is touched. The stamp keeps the .exe's SHA-256:
    the .exe then opens these as they are, instead of unpacking its own over them. Until all are in place it
    names no .exe's files: one stopped half-way is unpacked again from the .exe when it is next started."""
    root, stamp = Path(root), Path(root) / STAMP
    lines = stamp.read_text(encoding='utf-8').splitlines()
    digest, old = lines[0], [line for line in lines[1:] if line]
    write_file(stamp, ('updating\n' + ''.join(path + '\n' for path in sorted(set(old) | set(files)))).encode())
    for path, data in files.items():
        file = root / path
        try:
            if file.is_file() and file.read_bytes() == data: continue
        except OSError:
            pass
        write_file(file, data)
    for path in set(old) - set(files):
        if '..' in path.split('/'): continue
        with contextlib.suppress(OSError): (root / path).unlink()
    write_file(stamp, (digest + '\n' + ''.join(path + '\n' for path in sorted(files))).encode())


def update_files(root, branch, cancelled=lambda: False, say=lambda line: print(line, flush=True)):
    """Updates a test build's files (unpacked from its .exe into `root`) to the newest commit of its branch on
    GitHub. That commit, or None when these are the newest. UpdateError says why it cannot; Cancelled when
    cancelled (before anything is replaced)."""
    root = Path(root)
    current = build_commit(root)
    if not current or not (root / STAMP).is_file():
        raise UpdateError('These files were not unpacked from the launcher .exe: they cannot be updated in place.')
    say('@step update Looking for newer changes on ' + branch)
    quoted = urllib.parse.quote(branch, safe='')
    try:
        compare = github('compare/%s...%s' % (current, quoted))
    except UpdateError as error:
        if 'Not Found' not in str(error): raise
        raise UpdateError('GitHub has no branch %s with this build\'s commit (%s) any more: download the newest '
                          'release\'s launcher instead.' % (branch, current[:7]))
    ahead = compare.get('ahead_by') if isinstance(compare, dict) else None
    if not isinstance(ahead, int): raise UpdateError("GitHub's answer about %s is not readable." % branch)
    if not ahead:
        say('@step update The launcher is up to date: %s has nothing newer than %s.' % (branch, current[:7]))
        return None
    head = github('branches/' + quoted).get('commit', {}).get('sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', head): raise UpdateError("GitHub's answer names no commit of %s." % branch)
    url = archive_url(head)
    if not os.environ.get('TTT2_LAUNCHER_GITHUB') and not url.startswith('https://'):
        raise UpdateError('%s is not offered over HTTPS.' % head[:7])
    say('@step update Downloading %d change%s of %s' % (ahead, '' if ahead == 1 else 's', branch))
    file = root / 'local/launcher-update.zip'
    try:
        download(Release(version='', tag='', page='', asset='', url=url), file, cancelled, say)
        data = file.read_bytes()
    except (OSError, ValueError) as error:
        raise UpdateError('%s cannot be downloaded: %s.' % (head[:7], reason(error)))
    finally:
        with contextlib.suppress(OSError): file.unlink()
    files = archive_files(data, head)
    files[BUILD_COMMIT] = (head + '\n').encode()
    files[BUILD_BRANCH] = (branch + '\n').encode()
    if cancelled(): raise Cancelled()
    say('@step update Putting %s in place' % head[:7])
    try:
        install_files(root, files)
    except OSError as error:
        raise UpdateError('The new files cannot be put in place (%s): start the launcher again, it is as it was.'
                          % reason(error))
    say('The launcher\'s files are %s of %s.' % (head[:7], branch))
    say('@launcher-updated ' + head[:7])
    return head


def open_updated(exe):
    """The new .exe opened; it waits for this launcher to end first."""
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen([str(exe)], cwd=exe.parent, env=dict(os.environ, **{REPLACES_VARIABLE: str(os.getpid())}),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, creationflags=flags)
