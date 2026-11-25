"""The new launcher from these files: what main.py does without --worker or --query.

The project ZIP's first start (Start Golden Fist Launcher.cmd) and the .exe of old test builds (entry.cpp, 0.4.0 to
0.8.0, after their files were updated from their branch) start `python main.py --build-dir <folder> [GAME.wua]`, which
opened the Tk window. A source ZIP has no compiled launcher, so this builds it on the PC, once, and starts it:

  1. the folders checked as Set Up Game checks them (setup_game.validate_build_paths: short, plain letters), before
     anything is downloaded;
  2. the C compiler, CMake, Ninja and SDL 3 that Set Up Game pins (tools/windows-bootstrap.lock.json) and keeps (its
     tools folder, third_party/windows): got where missing, shared with it;
  3. the launcher alone (TTT2_LAUNCHER_ONLY, PROGRAM_TARGET, SDL 3's DLL beside it) built in a short folder whose path
     has only plain letters (CMake's batch files are read in the console's code page): build_home(), one folder per
     project folder, its build tree kept for the next build;
  4. the program and its DLL copied into a folder named after the digest of everything the build reads (inputs()),
     which replaces the last good one only once it is complete (current.json); the build runs again only when that
     digest changes (a files update, a new ZIP) and one start at a time (build.lock);
  5. the program started detached, with no handles of this process, with these files (--files ROOT), the .wua and
     TTT2_LAUNCHER_EXE as it was (its Update can then replace an old test build's .exe with the newest release's).

A small Tk window shows the progress (without Tk, or without a display, the build runs without it) and, when it fails,
why, with Open log, Try again (from a clean build folder) and, when an .exe started this (TTT2_LAUNCHER_EXE), Get the
newest launcher (self_update.update + open_updated: the release .exe, which needs no build), else the releases page.

  main.py [--build-dir DIR] [--config FILE] [--check | --ui-smoke-test FILE] [GAME.wua ...]

--check: Python is ready (the .cmd's and entry.cpp's first-start check): 0, nothing built. --ui-smoke-test FILE (CI):
built without a window, then the program run with --ui-smoke-test FILE and waited for; its exit code.
"""
from dataclasses import dataclass, field
from pathlib import Path
import contextlib
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

import self_update
import setup_game

ROOT = Path(__file__).resolve().parents[2]
# The program built and started: the native launcher (launcher/app).
PROGRAM_TARGET = 'ttt2-launcher'
# What a build is made of besides the files (a change here builds again).
BUILD_FORMAT = '1'
SDL_CONFIG = 'x86_64-w64-mingw32/lib/cmake/SDL3'
BUILD_LOG = 'local/launcher-build.log'
RELEASES_PAGE = 'https://github.com/%s/releases/latest' % self_update.REPOSITORY
TITLE = 'Golden Fist Launcher'
HEADING = 'Preparing the new launcher (once)...'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


class BuildError(Exception):
    """Why the launcher could not be built or started (a sentence for the player)."""


class Stopped(Exception):
    """The window was closed during the build."""


# 1. What the build reads, and its digest.

def inputs(root=ROOT):
    """The project's files the launcher's build reads (relative, '/', sorted): its sources, CMake files, fonts, icons,
    resources, the version line (launcher/builder/CMakeLists.txt), the build's commit and branch, the pins, the game's
    display.ini code it compiles."""
    def wanted(name):
        parts = name.split('/')
        if '__pycache__' in parts or name.endswith('.pyc'): return False
        if name.startswith('launcher/builder/'): return name == 'launcher/builder/CMakeLists.txt'
        if name.startswith('launcher/windows/') and name.endswith('.py'):
            return name in ('launcher/windows/build_launcher.py', 'launcher/windows/make_icon.py',
                            'launcher/windows/make_launcher_exe.py')
        return True
    # (and the game's display.ini code, which the launcher compiles too: self_update.PROGRAM_FILES)
    names = [name for name in ('CMakeLists.txt', 'tools/windows-bootstrap.lock.json',
                               *(n for n in self_update.PROGRAM_FILES if n.startswith('runtime/')))
             if (root / name).is_file()]
    for top in ('cmake', 'launcher'):
        for folder, folders, files in os.walk(root / top):
            folders[:] = sorted(f for f in folders if f != '__pycache__')
            for file in files:
                name = (Path(folder) / file).relative_to(root).as_posix()
                if wanted(name): names.append(name)
    return sorted(names)


def inputs_digest(root=ROOT, target=PROGRAM_TARGET):
    digest = hashlib.sha256(('%s\0%s\0' % (BUILD_FORMAT, target)).encode())
    for name in inputs(root):
        data = (root / name).read_bytes()
        digest.update(name.encode() + b'\0' + hashlib.sha256(data).digest())
    return digest.hexdigest()


# 2. Where it is built.

def build_home(environ=None):
    """%LOCALAPPDATA%\\TTT2Ultimate\\launcher-build; where that path has letters other than plain ones, %PUBLIC%'s, else
    %SystemDrive%'s (the release .exe's rule for its files folder)."""
    environ = os.environ if environ is None else environ
    data = environ.get('LOCALAPPDATA')
    if not data: raise BuildError('LOCALAPPDATA is not set.')
    drive = environ.get('SystemDrive', '')
    for base in (data, environ.get('PUBLIC', ''), drive + os.sep if drive else ''):
        if base and base.isascii(): return Path(base) / 'TTT2Ultimate' / 'launcher-build'
    return Path(data) / 'TTT2Ultimate' / 'launcher-build'


def project_folder(home, root=ROOT):
    """This project folder's own builds (a ZIP and a release .exe's files folder each have theirs)."""
    return home / hashlib.sha256(os.path.normcase(str(root)).encode('utf-8')).hexdigest()[:10]


def check_paths(settings, home):
    """Before anything is downloaded: what Set Up Game refuses (its texts), and the build folder's path."""
    setup_game.validate_build_paths(settings)
    if not str(home).isascii():
        letters = ''.join(sorted({c for c in str(home) if not c.isascii()}))
        raise BuildError('The folder the launcher is built in has letters the Windows build tools cannot read (%s): '
                         '%s. Use Golden_Fist_Launcher-x86_64.exe from the newest release instead.' % (letters, home))


# 3. The tools: Set Up Game's.

@dataclass
class Tools:
    cmake: str
    ninja: str
    c: str
    cxx: str
    sdl: str                                    # SDL 3's CMake package folder (SDL3Config.cmake)
    path: list = field(default_factory=list)    # folders put first on PATH (the compiler's)
    options: list = field(default_factory=list) # more configure options (a toolchain file: tests on Linux)

    def identity(self):
        return json.dumps([self.cmake, self.ninja, self.c, self.cxx, self.sdl, self.options])


def players_tools(settings, report, run, root=ROOT):
    """Set Up Game's compiler, CMake, Ninja and SDL 3 (what is missing downloaded, checked against the pins)."""
    lock = setup_game.manifest(settings)
    tools = setup_game.tools_folder(settings)
    downloads = root / 'local/windows-downloads'
    compiler = tools / lock['compiler']['folder'] / 'bin'
    if not (compiler / 'clang++.exe').is_file():
        report.step('Getting the C compiler (once)')
        setup_game.unzip(setup_game.download(lock['compiler'], downloads / 'llvm-mingw.zip'), tools)
    packages = tools / 'python'
    cmake = packages / 'cmake/data/bin/cmake.exe'
    ninja = packages / 'bin/ninja.exe'
    if not cmake.is_file() or not (ninja.is_file() or (packages / 'ninja/data/bin/ninja.exe').is_file()):
        report.step('Getting CMake and Ninja (once)')
        pins = [p for p in lock['packages'] if p.split('==')[0] in ('cmake', 'ninja')]
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:',
             '--upgrade', '--target', str(packages), *pins], 'Getting CMake and Ninja failed')
    if not ninja.is_file():
        ninja.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(packages / 'ninja/data/bin/ninja.exe', ninja)
    # (Where tools/setup_windows_runtime.ps1 puts it: Set Up Game then finds it there.)
    native = root / 'third_party/windows'
    sdl = native / lock['sdl']['folder'] / SDL_CONFIG
    if not (sdl / 'SDL3Config.cmake').is_file():
        report.step('Getting SDL 3 (once)')
        setup_game.unzip(setup_game.download(lock['sdl'], native / 'SDL3.zip'), native)
        if not (sdl / 'SDL3Config.cmake').is_file():
            raise BuildError('The SDL 3 download holds no %s.' % (Path(lock['sdl']['folder']) / SDL_CONFIG))
    return Tools(str(cmake), str(ninja), str(compiler / 'clang.exe'), str(compiler / 'clang++.exe'), str(sdl),
                 [str(compiler)])


# 4. The build.

class Runner:
    """Runs the build's programs: no console window, output into the log (UTF-8) and line by line to `lines`."""

    def __init__(self, log, environment=None):
        self.log, self.environment, self.process, self.stopped = log, environment, None, False

    def __call__(self, argv, failure, lines=None, cwd=None):
        if self.stopped: raise Stopped()
        self.log.write('> ' + subprocess.list2cmdline([str(a) for a in argv]) + '\n')
        self.log.flush()
        tail = []
        try:
            self.process = subprocess.Popen([str(a) for a in argv], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, cwd=cwd, env=self.environment,
                                            creationflags=NO_WINDOW)
        except OSError as error:
            raise BuildError('%s: %s cannot be started (%s).'
                             % (failure, Path(argv[0]).name, self_update.reason(error)))
        with self.process.stdout as output:
            for raw in output:
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                self.log.write(line + '\n')
                self.log.flush()
                tail = (tail + [line])[-3:]
                if lines: lines(line)
        code = self.process.wait()
        if self.stopped: raise Stopped()
        if code:
            last = ' '.join(t.strip() for t in tail if t.strip())
            raise BuildError('%s (exit code %d)%s' % (failure, code, ': ' + last[-300:] if last else '.'))

    def stop(self):
        """The running program ended with its children (the compiler's), from another thread."""
        self.stopped = True
        process = self.process
        if process and process.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
            else:
                process.kill()


NINJA_STEP = re.compile(r'^\[(\d+)/(\d+)\]')


def ninja_fraction(line):
    """How far Ninja is, from its "[12/345] ..." lines; None for other lines."""
    if found := NINJA_STEP.match(line):
        done, total = int(found[1]), int(found[2])
        return done / total if total else None
    return None


def program_file(work, target):
    """The target's program in the build tree, as CMake's file API says (the reply to the codemodel query)."""
    reply = work / '.cmake/api/v1/reply'
    indexes = sorted(reply.glob('index-*.json'))
    if not indexes: raise BuildError('CMake did not say what it builds (no file API reply in %s).' % reply)
    index = json.loads(indexes[-1].read_text(encoding='utf-8'))
    model = json.loads((reply / index['reply']['codemodel-v2']['jsonFile']).read_text(encoding='utf-8'))
    for entry in model['configurations'][0]['targets']:
        if entry['name'] == target:
            details = json.loads((reply / entry['jsonFile']).read_text(encoding='utf-8'))
            return work / details['artifacts'][0]['path']
    raise BuildError('These files have no launcher program %s to build.' % target)


def build(root, folder, digest, tools, run, report, target=PROGRAM_TARGET, clean=False):
    """The program built in folder/work and put with its DLL in folder/b-<digest>; that folder, now current."""
    work = folder / 'work'
    identity = work / 'ttt2-tools.json'
    if clean or (identity.is_file() and identity.read_text(encoding='utf-8') != tools.identity()):
        shutil.rmtree(work, ignore_errors=True)
    query = work / '.cmake/api/v1/query/codemodel-v2'
    query.parent.mkdir(parents=True, exist_ok=True)
    query.touch()
    identity.write_text(tools.identity(), encoding='utf-8')
    report.step('Building the launcher')
    run([tools.cmake, '-S', root, '-B', work, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DTTT2_LAUNCHER_ONLY=ON',
         '-DTTT2_LAUNCHER_SDL=system', '-DSDL3_DIR=' + tools.sdl, '-DCMAKE_MAKE_PROGRAM=' + tools.ninja,
         '-DCMAKE_C_COMPILER=' + tools.c, '-DCMAKE_CXX_COMPILER=' + tools.cxx, *tools.options],
        'CMake could not configure the launcher')
    program = program_file(work, target)
    run([tools.cmake, '--build', work, '--target', target, '--parallel', str(os.cpu_count() or 2)],
        'The launcher could not be built', lines=lambda line: report.fraction(ninja_fraction(line)))
    if not program.is_file(): raise BuildError('The build made no %s.' % program.name)
    # (Complete first, then current: the last good one stays until this one is.)
    final = folder / ('b-' + digest[:16])
    part = folder / ('part-%d' % os.getpid())
    shutil.rmtree(part, ignore_errors=True)
    part.mkdir(parents=True)
    shutil.copy2(program, part / program.name)
    for dll in program.parent.glob('*.dll'):
        shutil.copy2(dll, part / dll.name)
    if final.exists(): shutil.rmtree(final)
    part.replace(final)
    previous = current(folder)
    write_current(folder, {'digest': digest, 'folder': final.name, 'program': program.name})
    # (Older builds go; the one before stays, and any still running cannot be deleted yet: next time.)
    keep = {final.name, previous['folder'] if previous else ''}
    for old in folder.glob('b-*'):
        if old.name not in keep: shutil.rmtree(old, ignore_errors=True)
    for old in folder.glob('part-*'):
        if old != part: shutil.rmtree(old, ignore_errors=True)
    return final / program.name


def current(folder):
    """The last good build: {digest, folder, program}, or None."""
    try:
        answer = json.loads((folder / 'current.json').read_text(encoding='utf-8'))
        return answer if (folder / answer['folder'] / answer['program']).is_file() else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_current(folder, value):
    part = folder / 'current.json.part'
    part.write_text(json.dumps(value), encoding='utf-8')
    part.replace(folder / 'current.json')


class BuildLock:
    """One build per project folder at a time (two quick starts): a lock on folder/build.lock, held while open."""

    def __init__(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        self.file = open(folder / 'build.lock', 'a+b')

    def take(self):
        """True when taken; False when another start holds it."""
        try:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def wait(self, waiting, stopped=lambda: False, seconds=3600):
        """Takes it, waiting for the other start (`waiting` said once); BuildError after `seconds`."""
        said = False
        deadline = time.monotonic() + seconds
        while not self.take():
            if stopped(): raise Stopped()
            if not said: waiting(); said = True
            if time.monotonic() > deadline:
                raise BuildError('Another start has been preparing the launcher for too long: start it again.')
            time.sleep(0.5)

    def close(self):
        self.file.close()   # (releases the lock)


# 5. The start.

def program_arguments(program, root, settings, args):
    """The program's command line: these files, a build folder and settings file of their own only where they are
    not these files' usual ones, the smoke test, the .wua files (absolute)."""
    argv = [str(program), '--files', str(root)]
    if Path(settings.build) != (root / 'build-windows-tools').resolve():
        argv += ['--build-dir', str(settings.build)]
    if args.config:
        argv += ['--config', str(Path(args.config).resolve())]
    if args.ui_smoke_test:
        argv += ['--ui-smoke-test', str(Path(args.ui_smoke_test).resolve())]
    return argv + [str(Path(f).resolve()) for f in args.fighters]


def start(argv, root, wait=False):
    """Detached, with no handle of this process (an old .exe's log stays free for its next start); the environment
    as it is (TTT2_LAUNCHER_EXE), but for TTT2_LAUNCHER_AFTER. With `wait`, its exit code."""
    environment = dict(os.environ)
    environment.pop(self_update.REPLACES_VARIABLE, None)
    flags = 0 if wait else (getattr(subprocess, 'DETACHED_PROCESS', 0) |
                            getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    try:
        process = subprocess.Popen(argv, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                                   creationflags=flags, start_new_session=not wait and os.name != 'nt')
    except OSError as error:
        raise BuildError('The launcher cannot be started (%s).' % self_update.reason(error))
    if wait: return process.wait()
    # (A start that ends at once with an error, an argument it does not know: said, not lost.)
    with contextlib.suppress(subprocess.TimeoutExpired):
        code = process.wait(1.5)
        if code: raise BuildError('The launcher stopped at once (exit code %d).' % code)
    return 0




# The bridge.

FAILURES = (BuildError, ValueError, OSError, self_update.UpdateError)


def prepare(root, settings, report, run, tools=None, clean=False, home=None):
    """The program for these files: the last good build when nothing it reads changed, else a new one."""
    home = home or build_home()
    folder = project_folder(home, root)
    report.step('Checking the folders')
    check_paths(settings, home)
    digest = inputs_digest(root)
    found = current(folder)
    if found and found['digest'] == digest and not clean:
        return folder / found['folder'] / found['program']
    lock = BuildLock(folder)
    try:
        lock.wait(lambda: report.step('Another start is preparing the launcher: waiting for it'),
                  lambda: run.stopped)
        found = current(folder)     # (that start may have built it)
        if found and found['digest'] == digest and not clean:
            return folder / found['folder'] / found['program']
        tools = tools or players_tools(settings, report, run, root)
        if tools.path:  # (the compiler's folder first, as build_windows_tools.ps1 has it: its programs, its DLLs)
            run.environment['PATH'] = os.pathsep.join(tools.path + [run.environment.get('PATH', '')])
        return build(root, folder, digest, tools, run, report, clean=clean)
    finally:
        lock.close()


def main(args, settings, root=ROOT, tools=None, home=None, window=None):
    """main.py without --worker or --query; its exit code."""
    os.environ.pop(self_update.UI_PID_VARIABLE, None)   # (a launcher that reopened this one has ended)
    if args.check:
        print('Windows Golden Fist Launcher: Python and the launcher build available', flush=True)
        return 0
    log_path = root / BUILD_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):  # (the builds before the last few go)
        if log_path.stat().st_size > 4 << 20: log_path.replace(log_path.with_suffix('.old.log'))

    def program(report, clean):
        with log_path.open('a', encoding='utf-8') as log:
            log.write('\n== %s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), root))
            run = Runner(log, dict(os.environ))
            report.runner = run
            found = prepare(root, settings, report, run, tools, clean, home)
            log.write('program %s\n' % found)
            return found

    if args.ui_smoke_test:
        try:
            found = program(Quiet(), False)
        except FAILURES as error:
            print('The new launcher could not be prepared: %s (%s)' % (error, log_path), file=sys.stderr, flush=True)
            return 1
        code = start(program_arguments(found, root, settings, args), root, wait=True)
        print('The launcher ended with exit code %d.' % code, flush=True)
        return code

    def job(report, clean):
        found = program(report, clean)
        report.step('Starting the launcher')
        start(program_arguments(found, root, settings, args), root)

    window = window or Window.open()
    if window: return window.run(job, log_path)
    try:
        job(Quiet(), False)
        return 0
    except FAILURES as error:
        tell(str(error), log_path)
        return 1


def newest_launcher(exe, report):
    """The newest release's .exe in place of `exe` (the .exe that started this), opened: it needs no build. False when
    `exe` is that release already."""
    def say(line):
        if line.startswith('@step update '): report.step(line[len('@step update '):])
    if not self_update.update(exe, say=say): return False
    self_update.open_updated(exe)
    return True


def tell(text, log_path):
    """A failure without a window: standard error, and on Windows a message box."""
    message = 'The new launcher could not be prepared: %s\n\nDetails: %s' % (text, log_path)
    print(message, file=sys.stderr, flush=True)
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)


class Quiet:
    """Progress without a window: lines in the log the .exe keeps (local/launcher.log)."""
    runner = None

    def step(self, text):
        print('@step launcher ' + text, flush=True)

    def fraction(self, value):
        pass


class Window:
    """The only Tk left: the heading, the step, a progress bar; on a failure the reason with Open log, Try again, Get
    the newest launcher (an .exe started this) or the releases page, and Close. The work runs in a thread of its own;
    the window takes its news from a queue."""

    @staticmethod
    def open():
        """A window, or None where Tk cannot show one (no Tk, no display)."""
        try:
            import tkinter
            from tkinter import ttk
            top = tkinter.Tk()
        except Exception:
            return None
        return Window(top, ttk)

    def __init__(self, top, ttk):
        self.top, self.ttk, self.events, self.runner = top, ttk, queue.Queue(), None
        self.code, self.busy, self.task = 0, False, None
        top.title(TITLE)
        top.resizable(False, False)
        frame = ttk.Frame(top, padding=18)
        frame.pack(fill='both', expand=True)
        self.heading = ttk.Label(frame, text=HEADING, font=('Segoe UI', 12, 'bold'))
        self.heading.pack(anchor='w')
        self.text = ttk.Label(frame, text='', wraplength=460, justify='left')
        self.text.pack(anchor='w', fill='x', pady=(8, 10))
        self.bar = ttk.Progressbar(frame, length=460, mode='indeterminate', maximum=1000)
        self.bar.pack(fill='x')
        self.buttons = ttk.Frame(frame)
        self.buttons.pack(anchor='e', pady=(14, 0))
        top.protocol('WM_DELETE_WINDOW', self.close)

    # (From the work's thread.)
    def step(self, text):
        self.events.put(('step', text))

    def fraction(self, value):
        if value is not None: self.events.put(('fraction', value))

    def run(self, job, log_path):
        self.job, self.log_path = job, log_path
        self.begin(lambda: self.job(self, False))
        self.polling = self.top.after(100, self.poll)
        self.top.mainloop()
        return self.code

    def begin(self, task):
        for button in self.buttons.winfo_children(): button.destroy()
        self.heading['text'] = HEADING
        self.text['text'] = ''
        self.bar.configure(mode='indeterminate', value=0)
        self.bar.pack(fill='x')
        self.bar.start(12)
        self.busy = True

        def work():
            try:
                self.events.put(('done', task()))
            except Stopped:
                self.events.put(('closed', None))
            except FAILURES as error:
                self.events.put(('failed', str(error)))
            except Exception as error:  # (said, not lost in a thread)
                self.events.put(('failed', 'Unexpected error: %s: %s' % (type(error).__name__, error)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'step':
                self.text['text'] = value
            elif kind == 'fraction':
                if str(self.bar['mode']) != 'determinate':
                    self.bar.stop()
                    self.bar.configure(mode='determinate')
                self.bar['value'] = int(value * 1000)
            elif kind == 'done' and value is False:
                self.failed('This launcher is the newest release already.')
            elif kind in ('done', 'closed'):
                self.code = 0 if kind == 'done' else 1
                self.finish()
                return
            elif kind == 'failed':
                self.failed(value)
        self.polling = self.top.after(100, self.poll)

    def failed(self, reason):
        self.busy, self.code = False, 1
        self.bar.stop()
        self.bar.pack_forget()
        self.heading['text'] = 'The new launcher could not be prepared.'
        self.text['text'] = reason
        ttk = self.ttk
        exe = self_update.running_exe()
        for text, action in (('Open log', self.open_log), ('Try again', self.again),
                             ('Get the newest launcher', self.newest) if exe else ('Releases page', self.releases),
                             ('Close', self.close)):
            ttk.Button(self.buttons, text=text, command=action).pack(side='left', padx=(6, 0))

    def open_log(self):
        if os.name == 'nt': os.startfile(self.log_path)
        else:
            import webbrowser
            webbrowser.open(self.log_path.as_uri())

    def releases(self):
        import webbrowser
        webbrowser.open(RELEASES_PAGE)

    def again(self):
        self.begin(lambda: self.job(self, True))

    def newest(self):
        exe = self_update.running_exe()
        self.begin(lambda: newest_launcher(exe, self))

    def close(self):
        if self.busy:
            self.code = 1
            if self.runner: self.runner.stop()
        self.finish()

    def finish(self):
        # (Nothing of this window may run after it: Tcl's timers outlive it, in the thread's next window too.)
        with contextlib.suppress(Exception):
            self.bar.stop()
            self.top.after_cancel(self.polling)
        self.top.destroy()
