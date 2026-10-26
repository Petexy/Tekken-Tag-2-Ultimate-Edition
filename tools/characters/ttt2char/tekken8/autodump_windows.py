"""Native Windows Tekken 8 sessions, sharing the Tekken 7 process isolation."""
import os
import shutil
import subprocess

from ..tekken7 import autodump_windows as host
from . import autodump as common


def find_tekken8():
    steam, _, library, game = common._tekken8_library()
    if not os.path.isfile(os.path.join(game, common.EXE)):
        raise common.DumpError('Tekken 8 Windows shipping executable is missing; verify its files in Steam')
    return common.Tekken8(steam, library, game, game, 'Windows')


def tekken8_running(t8):
    return any(name.lower() in ('polaris-win64-shipping.exe', 'tekken 8.exe') for _, name in host.processes())


def build_helper(cache):
    ready = common.ready_helper(cache)
    if ready:
        return ready
    compiler = shutil.which('clang') or shutil.which('gcc')
    if not compiler:
        raise common.DumpError('the Windows helper requires MSYS2 CLANG64 clang in PATH')
    os.makedirs(cache, exist_ok=True)
    exe = os.path.join(cache, 't8helper.exe')
    subprocess.run([compiler, '-O2', '-mwindows', '-o', exe, os.path.normpath(common.HELPER_SOURCE), '-lws2_32'],
                   check=True)
    return exe


class Session(host.Session):
    game_exe = common.EXE
    mutex_prefix = 'Local\\TTT2Tekken8-'

    @property
    def common(self):
        return common

    def game_running(self, game):
        return tekken8_running(game)


def owned_dlc(t8, helper_exe, run):
    session = Session(t8, helper_exe, run, False)
    try:
        helper = session.connect()
        return {app: owned for app, owned, _ in helper.dlc(os.path.join(t8.game, common.STEAMWORKS))}
    finally:
        session.close()
