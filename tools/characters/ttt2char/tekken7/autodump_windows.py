"""Native Windows host for the existing, ownership-checked Tekken 7 importer.

The game runs on a private desktop, never switched to the user's screen.
A kill-on-close job owns only the processes this session creates. Its close
also runs at Python exit; the user's Steam or separately started games are
never terminated. Game functions and build signatures remain in t7helper.c.
"""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import msvcrt
import os
import secrets
import shutil
import subprocess
import time
import winreg

from . import autodump as common

kernel = C.WinDLL('kernel32', use_last_error=True)
user = C.WinDLL('user32', use_last_error=True)


class ProcessEntry(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('pid', W.DWORD),
                ('heap', C.c_size_t), ('module', W.DWORD), ('threads', W.DWORD),
                ('parent', W.DWORD), ('priority', W.LONG), ('flags', W.DWORD), ('exe', W.WCHAR * 260)]


class Startup(C.Structure):
    _fields_ = [('cb', W.DWORD), ('reserved', W.LPWSTR), ('desktop', W.LPWSTR), ('title', W.LPWSTR),
                ('x', W.DWORD), ('y', W.DWORD), ('width', W.DWORD), ('height', W.DWORD),
                ('chars_x', W.DWORD), ('chars_y', W.DWORD), ('fill', W.DWORD), ('flags', W.DWORD),
                ('show', W.WORD), ('reserved_size', W.WORD), ('reserved_bytes', C.c_void_p),
                ('stdin', W.HANDLE), ('stdout', W.HANDLE), ('stderr', W.HANDLE)]


class ProcessInfo(C.Structure):
    _fields_ = [('process', W.HANDLE), ('thread', W.HANDLE), ('pid', W.DWORD), ('tid', W.DWORD)]


class BasicLimits(C.Structure):
    _fields_ = [('process_time', C.c_int64), ('job_time', C.c_int64), ('flags', W.DWORD),
                ('min_working', C.c_size_t), ('max_working', C.c_size_t), ('active', W.DWORD),
                ('affinity', C.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]


class ExtendedLimits(C.Structure):
    _fields_ = [('basic', BasicLimits), ('io', C.c_uint64 * 6), ('process_memory', C.c_size_t),
                ('job_memory', C.c_size_t), ('peak_process', C.c_size_t), ('peak_job', C.c_size_t)]


def api(dll, name, result, *args):
    function = getattr(dll, name)
    function.restype, function.argtypes = result, args
    return function


close_handle = api(kernel, 'CloseHandle', W.BOOL, W.HANDLE)
snapshot = api(kernel, 'CreateToolhelp32Snapshot', W.HANDLE, W.DWORD, W.DWORD)
process_first = api(kernel, 'Process32FirstW', W.BOOL, W.HANDLE, C.POINTER(ProcessEntry))
process_next = api(kernel, 'Process32NextW', W.BOOL, W.HANDLE, C.POINTER(ProcessEntry))
create_job = api(kernel, 'CreateJobObjectW', W.HANDLE, C.c_void_p, W.LPCWSTR)
set_job = api(kernel, 'SetInformationJobObject', W.BOOL, W.HANDLE, C.c_int, C.c_void_p, W.DWORD)
assign_job = api(kernel, 'AssignProcessToJobObject', W.BOOL, W.HANDLE, W.HANDLE)
create_mutex = api(kernel, 'CreateMutexW', W.HANDLE, C.c_void_p, W.BOOL, W.LPCWSTR)
release_mutex = api(kernel, 'ReleaseMutex', W.BOOL, W.HANDLE)
wait = api(kernel, 'WaitForSingleObject', W.DWORD, W.HANDLE, W.DWORD)
terminate = api(kernel, 'TerminateProcess', W.BOOL, W.HANDLE, W.UINT)
exit_code = api(kernel, 'GetExitCodeProcess', W.BOOL, W.HANDLE, C.POINTER(W.DWORD))
resume = api(kernel, 'ResumeThread', W.DWORD, W.HANDLE)
create_process = api(kernel, 'CreateProcessW', W.BOOL, W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p,
                     W.BOOL, W.DWORD, C.c_void_p, W.LPCWSTR, C.POINTER(Startup), C.POINTER(ProcessInfo))
create_desktop = api(user, 'CreateDesktopW', W.HANDLE, W.LPCWSTR, W.LPCWSTR, C.c_void_p, W.DWORD, W.DWORD, C.c_void_p)
close_desktop = api(user, 'CloseDesktop', W.BOOL, W.HANDLE)


def checked(value, what):
    if not value:
        raise common.DumpError('%s: %s' % (what, C.WinError(C.get_last_error())))
    return value


def processes():
    handle = snapshot(2, 0)
    if handle == C.c_void_p(-1).value:
        checked(False, 'cannot list Windows processes')
    try:
        entry = ProcessEntry()
        entry.dwSize = C.sizeof(entry)
        more = process_first(handle, C.byref(entry))
        while more:
            yield entry.pid, entry.exe
            more = process_next(handle, C.byref(entry))
    finally:
        close_handle(handle)


def steam_running():
    return any(name.lower() == 'steam.exe' for _, name in processes())


def steams():
    paths = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            paths.append(winreg.QueryValueEx(key, 'SteamPath')[0])
    except OSError:
        pass
    paths.append(os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Steam'))
    return [(p, None) for p in dict.fromkeys(os.path.normpath(p) for p in paths) if os.path.isdir(p)]


def find_tekken7():
    steam, _, _, game = common._tekken7_library()
    if not os.path.isfile(os.path.join(game, 'TekkenGame', 'Binaries', 'Win64', 'TekkenGame-Win64-Shipping.exe')):
        raise common.DumpError('Tekken 7 Windows shipping executable is missing; verify its files in Steam')
    return common.Tekken7(steam, game, game, 'Windows')


def tekken7_running(t7):
    return any(name.lower() in ('tekkengame-win64-shipping.exe', 'tekken 7.exe') for _, name in processes())


def build_helper(cache):
    ready = common.ready_helper(cache)
    if ready:
        return ready
    compiler = shutil.which('clang') or shutil.which('gcc')
    if not compiler:
        raise common.DumpError('the Windows helper requires MSYS2 CLANG64 clang in PATH')
    os.makedirs(cache, exist_ok=True)
    exe = os.path.join(cache, 't7helper.exe')
    subprocess.run([compiler, '-O2', '-mwindows', '-o', exe, os.path.normpath(common.HELPER_SOURCE), '-lws2_32'], check=True)
    return exe


class Session:
    @property
    def common(self):
        return common

    def game_running(self, game):
        return tekken7_running(game)

    game_exe = 'TekkenGame/Binaries/Win64/TekkenGame-Win64-Shipping.exe'
    mutex_prefix = 'Local\\TTT2Tekken7-'

    def __init__(self, t7, helper_exe, run, with_game):
        common = self.common
        self.t7, self.run, self.closed = t7, run, False
        self.helper = self.mutex = self.job = self.desktop = None
        self.locked = False
        self.children, self.game = [], None
        common._open.append(self)
        try:
            os.makedirs(run, exist_ok=True)
            name = hashlib.sha256(os.path.normcase(os.path.realpath(t7.game)).encode()).hexdigest()[:24]
            self.mutex = checked(create_mutex(None, False, self.mutex_prefix + name), 'cannot create importer mutex')
            if wait(self.mutex, 300000) not in (0, 0x80):
                raise common.DumpError(common.BUSY)
            self.locked = True
            if self.game_running(t7):
                raise common.DumpError(common.RUNNING)
            self.job = checked(create_job(None, None), 'cannot create import process job')
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            checked(set_job(self.job, 9, C.byref(limits), C.sizeof(limits)), 'cannot set import cleanup')
            self.desktop_name = None
            if with_game:
                self.desktop_name = 'TTT2Import-' + secrets.token_hex(10)
                self.desktop = checked(create_desktop(self.desktop_name, None, None, 0, 0x1ff, None), 'cannot create hidden desktop')
                binary = os.path.join(t7.game, self.game_exe)
                self.game = self._spawn([binary, '-windowed', '-ResX=1280', '-ResY=720', '-nosound', '-NoSplash'],
                                        'game.log', self.desktop_name)
            self.port, self.secret = common._free_port(), secrets.token_hex(16)
            self._spawn([helper_exe, 'serve', str(self.port), self.secret], 'helper.log', self.desktop_name)
        except BaseException:
            self.close()
            raise

    def _spawn(self, command, log_name, desktop):
        common = self.common
        env = dict(os.environ, SteamAppId=str(common.APP_ID), SteamGameId=str(common.APP_ID))
        environment = C.create_unicode_buffer('\0'.join('%s=%s' % item for item in sorted(env.items())) + '\0\0')
        line = C.create_unicode_buffer(subprocess.list2cmdline(command))
        startup = Startup()
        startup.cb, startup.desktop = C.sizeof(startup), desktop
        startup.flags = 0x101  # STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW (SW_HIDE)
        info = ProcessInfo()
        with open(os.path.join(self.run, log_name), 'wb') as log, open(os.devnull, 'rb') as stdin:
            for file in (log, stdin):
                os.set_inheritable(file.fileno(), True)
            startup.stdin = msvcrt.get_osfhandle(stdin.fileno())
            startup.stdout = startup.stderr = msvcrt.get_osfhandle(log.fileno())
            checked(create_process(command[0], line, None, None, True, 0x08000404, environment,
                                   self.t7.game, C.byref(startup), C.byref(info)), 'cannot start ' + command[0])
        try:
            if not assign_job(self.job, info.process):
                terminate(info.process, 1)
                checked(False, 'cannot attach import process cleanup')
            self.children.append(info.process)
            checked(resume(info.thread) != 0xffffffff, 'cannot resume import process')
            return info
        finally:
            close_handle(info.thread)

    def wait_game(self, timeout=240):
        if self.game and wait(self.game.process, 500) == 0x102:
            return self.game.pid
        raise common.DumpError('The game stopped while starting; see ' + os.path.join(self.run, 'game.log'))

    def connect(self):
        common = self.common
        self.helper = common.Helper(self.port, self.secret)
        if self.game:
            self.helper.target_pid = self.game.pid
        return self.helper

    def close(self):
        common = self.common
        if self.closed:
            return
        self.closed = True
        with common.signals.deferred():
            try:
                if self.helper:
                    self.helper.quit()
            finally:
                if self.job:
                    close_handle(self.job)
                    self.job = None
                for process in self.children:
                    wait(process, 5000)
                    close_handle(process)
                if self.desktop:
                    close_desktop(self.desktop)
                if self.locked:
                    release_mutex(self.mutex)
                if self.mutex:
                    close_handle(self.mutex)
                if self in common._open:
                    common._open.remove(self)


def owned_dlc(t7, helper_exe, run):
    session = Session(t7, helper_exe, run, False)
    try:
        helper = session.connect()
        return {app: owned for app, owned, _ in helper.dlc(os.path.join(t7.game, common.STEAMWORKS))}
    finally:
        session.close()
