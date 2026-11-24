"""The launcher's Windows program (make_launcher_exe.py makes the release .exe of it): it says its version, and
unpacks its files as the release unpacks them on a player's PC. Asset-free.

    test_launcher_exe.py LAUNCHER_EXE VERSION [RELEASE_EXE]

LAUNCHER_EXE is the program as built, without files (the tests append theirs); RELEASE_EXE, when given, a release
.exe made of it (make_launcher_exe.py), tested as it is: its version, its files, and a start as a player's (its
files into the files folder, the .old.exe an update left deleted, the launcher it replaces waited for, its first frame
drawn: --ui-smoke-test, offscreen under Wine, which has no display here).

On Windows the programs run themselves; elsewhere through Wine when it is there: without a display, without
winemenubuilder (no menu entries or file types of the Wine prefix in the desktop's menus). The start as a player's
writes into the files folder under LOCALAPPDATA, which Windows takes from the environment (a temporary folder here)
but Wine from its prefix: under Wine it runs only with WINEPREFIX set to a prefix of the tests' own."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from make_launcher_exe import payload
import self_update

STUB, VERSION = Path(sys.argv[1]), sys.argv[2]
RELEASE = Path(sys.argv[3]) if len(sys.argv) > 3 else None
WINE = None if os.name == 'nt' else shutil.which('wine')
# (A prefix of the tests' own, never a person's ~/.wine.)
OWN_PREFIX = bool(os.environ.get('WINEPREFIX')) and \
    Path(os.environ['WINEPREFIX']).expanduser().resolve() != (Path.home() / '.wine').resolve()


def environment(**more):
    """The programs' environment: under Wine without a display (nothing on this PC's screen) or winemenubuilder."""
    env = dict(os.environ, **more)
    if WINE:
        for name in ('DISPLAY', 'WAYLAND_DISPLAY'): env.pop(name, None)
        overrides = [part for part in env.get('WINEDLLOVERRIDES', '').split(';')
                     if part and not part.startswith('winemenubuilder')]
        env.update(WINEDEBUG='-all', WINEDLLOVERRIDES=';'.join(overrides + ['winemenubuilder.exe=d']))
    return env


def path(file):
    return subprocess.run(['winepath', '-w', str(file)], capture_output=True, text=True, check=True,
                          env=environment()).stdout.strip() if WINE else str(file)


def run_exe(exe, *args, **env):
    command = ([WINE] if WINE else []) + [str(exe), *args]
    return subprocess.run(command, capture_output=True, text=True, timeout=120, env=environment(**env))


def unpack(exe, folder):
    return run_exe(exe, '--unpack', path(folder))


@unittest.skipUnless(os.name == 'nt' or WINE, 'needs Windows or Wine')
class LauncherExe(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name); self.made = 0
        # (A program built with SDL as a DLL, as Set Up Game builds it: SDL3.dll and the like go along with it.)
        for dll in STUB.parent.glob('*.dll'): shutil.copy2(dll, self.folder / dll.name)
    def exe(self, files, damage=False):
        data = bytearray(STUB.read_bytes() + payload(files))
        if damage: data[len(STUB.read_bytes()) + 10] ^= 1
        self.made += 1
        exe = self.folder / ('launcher%d.exe' % self.made); exe.write_bytes(data)
        return exe

    def test_version_and_files(self):
        exe = self.exe({'a.txt': b'one', 'sub/dir/b.txt': b'two', 'launcher/windows/main.py': b''})
        self.assertTrue(self_update.is_launcher_exe(exe))
        result = run_exe(exe, '--version')
        self.assertEqual((result.returncode, self_update.version_in(result.stdout)), (0, VERSION))
        root = self.folder / 'root'
        self.assertEqual(unpack(exe, root).returncode, 0)
        self.assertEqual(((root / 'a.txt').read_bytes(), (root / 'sub/dir/b.txt').read_bytes()), (b'one', b'two'))
        (root / 'local/windows-tools').mkdir(parents=True); (root / 'local/windows-tools/kept').write_bytes(b'x')
        (root / 'build-windows-tools').mkdir(); (root / 'build-windows-tools/kept').write_bytes(b'x')
        # A newer launcher's files: what only the old ones had goes, nothing else.
        newer = self.exe({'a.txt': b'ONE', 'c.txt': b'three', 'launcher/windows/main.py': b''})
        self.assertEqual(unpack(newer, root).returncode, 0)
        self.assertEqual(((root / 'a.txt').read_bytes(), (root / 'c.txt').read_bytes()), (b'ONE', b'three'))
        self.assertFalse((root / 'sub/dir/b.txt').exists())
        self.assertTrue((root / 'local/windows-tools/kept').exists() and (root / 'build-windows-tools/kept').exists())
        self.assertEqual(sorted(p.name for p in root.rglob('*.part')), [])

    def test_damaged_or_unsafe_files_are_refused(self):
        root = self.folder / 'root'
        for files, damage in [({'a.txt': b'one'}, True), ({'../escape.txt': b'x'}, False),
                              ({'C:/escape.txt': b'x'}, False), ({'a\\..\\b.txt': b'x'}, False)]:
            with self.subTest(files=list(files), damage=damage):
                result = unpack(self.exe(files, damage), root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('ttt2-launcher:', result.stderr)
        self.assertFalse((self.folder / 'escape.txt').exists())
        self.assertFalse(root.exists() and any(root.rglob('*.txt')))

    # (make_launcher_exe.py packs Git's tracked files: a player's launcher folder is no Git checkout, and Set Up
    # Game runs these tests there.)
    @unittest.skipUnless((Path(__file__).resolve().parents[2] / '.git').exists() and shutil.which('git'),
                         'needs a Git checkout of the project')
    def test_project_release_exe(self):
        out = self.folder / 'Ultimate_Launcher-x86_64.exe'
        subprocess.run([sys.executable, str(Path(__file__).with_name('make_launcher_exe.py')), '--stub', str(STUB),
                        '--allow-dirty', str(out)], check=True)
        root = self.folder / 'project'
        self.assertEqual(unpack(out, root).returncode, 0)
        self.assertTrue((root / 'launcher/windows/main.py').is_file())
        self.assertIn(b'\r\n', (root / 'Start Ultimate Launcher.cmd').read_bytes())


def files_digest(exe):
    """The SHA-256 (hex) of the files in `exe` (what the stamp of their unpacking names first)."""
    return hashlib.sha256(payload(self_update.stored_files(exe))[:-self_update.TRAILER.size]).hexdigest()


@unittest.skipUnless(RELEASE, 'needs a release .exe (the third argument)')
@unittest.skipUnless(os.name == 'nt' or WINE, 'needs Windows or Wine')
class ReleaseExe(unittest.TestCase):
    """The release .exe as make_launcher_exe.py made it."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def test_what_old_launchers_check(self):
        # (self_update.py of every launcher since 0.4.0: a 64-bit Windows program with its files, of this version.)
        files = self_update.stored_files(RELEASE)
        self.assertIsNotNone(files)
        self.assertEqual(self_update.files_version(files), VERSION)
        for needed in ('launcher/windows/main.py', 'launcher/windows/self_update.py', 'Start Ultimate Launcher.cmd',
                       'launcher/windows/build-commit'):
            self.assertIn(needed, files)
        result = run_exe(RELEASE, '--version')
        self.assertEqual((result.returncode, result.stdout), (0, 'ttt2-launcher %s\n' % VERSION))

    def test_unpack(self):
        root = self.folder / 'root'
        result = unpack(RELEASE, root)
        self.assertEqual(result.returncode, 0, result.stderr)
        files = self_update.stored_files(RELEASE)
        for name, data in files.items():
            self.assertEqual((root / name).read_bytes(), data, name)
        stamp = (root / self_update.STAMP).read_text(encoding='utf-8').splitlines()
        self.assertEqual(stamp[0], files_digest(RELEASE))
        self.assertEqual(sorted(stamp[1:]), sorted(files))
        self.assertIn(b'\r\n', (root / 'Start Ultimate Launcher.cmd').read_bytes())

    @unittest.skipUnless(os.name == 'nt' or OWN_PREFIX, 'under Wine: needs WINEPREFIX, a prefix of the tests\' own')
    def test_start_as_a_player(self):
        # Where the .exe was updated: the old one beside it, renamed (self_update.replace), to be deleted.
        apps = self.folder / 'apps'
        apps.mkdir()
        exe = apps / 'Ultimate_Launcher-x86_64.exe'
        shutil.copyfile(RELEASE, exe)
        (apps / 'Ultimate_Launcher-x86_64.old.exe').write_bytes(b'MZ the old one')
        if WINE:
            said = subprocess.run([WINE, 'cmd', '/c', 'echo %LOCALAPPDATA%'], capture_output=True, text=True,
                                  env=environment()).stdout.strip().splitlines()[-1]
            local = Path(subprocess.run(['winepath', '-u', said], capture_output=True, text=True, check=True,
                                        env=environment()).stdout.strip())
            env = {}
        else:
            local = self.folder / 'local'
            local.mkdir()
            env = {'LOCALAPPDATA': str(local)}
        root = local / 'TTT2Ultimate/launcher'
        if root.exists(): shutil.rmtree(root)
        said = self.folder / 'frame.json'
        if WINE: env['TTT2_LAUNCHER_TEST_VIDEO'] = 'offscreen'
        # (A launcher that ended long ago: the start waits for it, then goes on.)
        result = run_exe(exe, '--ui-smoke-test', path(said), TTT2_LAUNCHER_AFTER='999999', **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        frame = json.loads(said.read_text(encoding='utf-8'))
        self.assertEqual(frame['program'], 'ttt2-launcher')
        self.assertEqual(frame['version'], VERSION)
        self.assertTrue(frame['frame'] and not frame['error'], frame)
        self.assertEqual((frame['after'], frame['after_ended'], frame['after_left']), ('999999', True, ''))
        self.assertEqual(frame['digest'], files_digest(RELEASE))
        # (Its manifest's activeCodePage: UTF-8 is the ANSI code page of the whole program.)
        self.assertEqual(frame.get('code_page'), 65001, frame)
        self.assertFalse((apps / 'Ultimate_Launcher-x86_64.old.exe').exists())
        self.assertEqual((root / self_update.STAMP).read_text(encoding='utf-8').splitlines()[0],
                         files_digest(RELEASE))
        self.assertEqual(self_update.version(root), VERSION)
        shutil.rmtree(local / 'TTT2Ultimate')


if __name__ == '__main__': unittest.main(argv=sys.argv[:1])
