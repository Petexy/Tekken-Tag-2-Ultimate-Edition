"""The source ZIP's bridge to the new launcher (build_launcher.py, main.py without --worker/--query): what it builds
from, where, when again, how it starts the program, and what it says when it cannot. Synthetic files only: CMake, the
compiler and the program are stand-ins (a real build is not a unit test: see the hand-over notes)."""
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_launcher as bl  # noqa: E402
from backend import Settings  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def write(path, text='x'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def arguments(**values):
    defaults = dict(build_dir=None, config=None, check=False, ui_smoke_test=None, fighters=[])
    defaults.update(values)
    return SimpleNamespace(**defaults)


class Report:
    runner = None

    def __init__(self):
        self.steps = []

    def step(self, text):
        self.steps.append(text)

    def fraction(self, value):
        pass


class FakeRun:
    """CMake and Ninja as the bridge runs them: the configure answers the file API query, the build makes the
    program (and SDL's DLL beside it), or fails."""

    def __init__(self, fail_build=False):
        self.calls, self.fail_build, self.stopped, self.environment = [], fail_build, False, {}

    def __call__(self, argv, failure, lines=None, cwd=None):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if '-S' in argv:
            work = Path(argv[argv.index('-B') + 1])
            reply = work / '.cmake/api/v1/reply'
            write(reply / 'target-x.json', json.dumps({'artifacts': [{'path': 'launcher/program.exe'}]}))
            write(reply / 'codemodel-x.json', json.dumps({'configurations': [{'targets': [
                {'name': 'other', 'jsonFile': 'none.json'}, {'name': bl.PROGRAM_TARGET, 'jsonFile': 'target-x.json'}]}]}))
            write(reply / 'index-2.json', json.dumps({'reply': {'codemodel-v2': {'jsonFile': 'codemodel-x.json'}}}))
        elif '--build' in argv:
            if lines: lines('[1/2] Building CXX object a.obj')
            if self.fail_build: raise bl.BuildError(failure + ' (exit code 1).')
            work = Path(argv[argv.index('--build') + 1])
            write(work / 'launcher/program.exe', 'program %d' % len(self.calls))
            write(work / 'launcher/SDL3.dll', 'dll')


class Project(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'TTT2'
        for name in ('CMakeLists.txt', 'cmake/LauncherSDL.cmake', 'launcher/CMakeLists.txt', 'launcher/ui/src/ui.cpp',
                     'launcher/ui/fonts/Barlow/Barlow-Bold.ttf', 'launcher/app/icons/a.svg',
                     'launcher/windows/launcher.rc.in', 'launcher/windows/build_launcher.py',
                     'launcher/windows/backend.py', 'launcher/windows/__pycache__/backend.cpython-313.pyc',
                     'launcher/builder/kit.cpp', 'tools/characters/import_character.py', 'runtime/src/a.cpp',
                     'runtime/src/host/display_settings.cpp'):
            write(self.root / name)
        write(self.root / 'launcher/builder/CMakeLists.txt', 'set(TTT2_LAUNCHER_VERSION 0.9.0)\n')
        write(self.root / 'tools/windows-bootstrap.lock.json', '{"compiler": {}}')
        self.home = self.base / 'home'
        self.settings = Settings(root=self.root)
        self.tools = bl.Tools('cmake', 'ninja', 'clang', 'clang++', 'sdl')

    def prepare(self, run=None, **options):
        return bl.prepare(self.root, self.settings, Report(), run or FakeRun(), self.tools, home=self.home, **options)


class Inputs(Project):
    def test_inputs_are_what_the_launcher_build_reads(self):
        self.assertEqual(bl.inputs(self.root), [
            'CMakeLists.txt', 'cmake/LauncherSDL.cmake', 'launcher/CMakeLists.txt', 'launcher/app/icons/a.svg',
            'launcher/builder/CMakeLists.txt', 'launcher/ui/fonts/Barlow/Barlow-Bold.ttf', 'launcher/ui/src/ui.cpp',
            'launcher/windows/build_launcher.py', 'launcher/windows/launcher.rc.in',
            'runtime/src/host/display_settings.cpp', 'tools/windows-bootstrap.lock.json'])

    def test_digest_follows_sources_version_fonts_and_pins_only(self):
        before = bl.inputs_digest(self.root)
        write(self.root / 'launcher/windows/backend.py', 'worker change')
        write(self.root / 'tools/characters/import_character.py', 'importer change')
        self.assertEqual(bl.inputs_digest(self.root), before)
        for name, text in (('launcher/builder/CMakeLists.txt', 'set(TTT2_LAUNCHER_VERSION 0.9.1)\n'),
                           ('launcher/ui/fonts/Barlow/Barlow-Bold.ttf', 'other font'),
                           ('tools/windows-bootstrap.lock.json', '{"compiler": {"url": "new"}}'),
                           ('launcher/windows/build-commit', 'a' * 40 + '\n')):
            write(self.root / name, text)
            after = bl.inputs_digest(self.root)
            self.assertNotEqual(after, before, name)
            before = after
        self.assertNotEqual(bl.inputs_digest(self.root, 'ttt2-launcher'), bl.inputs_digest(self.root, 'other'))

    def test_the_real_tree_has_the_launcher_inputs(self):
        names = bl.inputs(REPO)
        for name in ('CMakeLists.txt', 'launcher/builder/CMakeLists.txt', 'launcher/CMakeLists.txt',
                     'launcher/ui/CMakeLists.txt', 'tools/windows-bootstrap.lock.json',
                     'runtime/src/host/display_settings.cpp', 'runtime/src/host/display_settings.h'):
            self.assertIn(name, names)
        self.assertFalse([n for n in names if n.endswith('.pyc') or n.startswith('launcher/builder/kit')])


class ProgramsPlace(unittest.TestCase):
    def test_set_up_game_and_the_texts_name_the_programs_place(self):
        # (compat review #6: CMake puts the program in <build>/launcher; the one of 0.8.0 at the top is removed.)
        self.assertIn('RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/launcher"',
                      (REPO / 'launcher/ui/CMakeLists.txt').read_text(encoding='utf-8'))
        self.assertIn('`build-windows-tools/launcher/ttt2-launcher.exe`', (REPO / 'README.md').read_text(encoding='utf-8'))
        self.assertIn('build-windows-*/launcher/ttt2-launcher.exe',
                      (REPO / 'launcher/windows/make_launcher_exe.py').read_text(encoding='utf-8'))
        script = (REPO / 'tools/build_windows_tools.ps1').read_text(encoding='utf-8')
        built = script.index('--target cafe-recomp')
        removed = script.index('Remove-Item -LiteralPath "$root/build-windows-tools/ttt2-launcher.exe"')
        self.assertGreater(removed, built)
        self.assertIn(' ttt2-launcher ', script[built:script.index('\n', built)])


class Folders(Project):
    def test_build_home_has_only_plain_letters_as_the_exe_files_folder(self):
        sep = os.sep
        self.assertEqual(bl.build_home({'LOCALAPPDATA': 'C:/Users/Ann/AppData/Local'}),
                         Path('C:/Users/Ann/AppData/Local/TTT2Ultimate/launcher-build'))
        self.assertEqual(bl.build_home({'LOCALAPPDATA': 'C:/Users/Jos\u00e9/AppData/Local', 'PUBLIC': 'C:/Users/Public'}),
                         Path('C:/Users/Public/TTT2Ultimate/launcher-build'))
        self.assertEqual(bl.build_home({'LOCALAPPDATA': 'C:/Users/Jos\u00e9/L', 'PUBLIC': 'C:/\u00d6ffentlich',
                                        'SystemDrive': 'C:'}), Path('C:' + sep) / 'TTT2Ultimate/launcher-build')
        self.assertEqual(bl.build_home({'LOCALAPPDATA': 'C:/Jos\u00e9'}), Path('C:/Jos\u00e9/TTT2Ultimate/launcher-build'))
        with self.assertRaisesRegex(bl.BuildError, 'LOCALAPPDATA'):
            bl.build_home({})

    def test_each_project_folder_builds_apart(self):
        a = bl.project_folder(self.home, Path('C:/TTT2'))
        self.assertEqual(a, bl.project_folder(self.home, Path('C:/TTT2')))
        self.assertNotEqual(a, bl.project_folder(self.home, Path('C:/Games/TTT2')))
        self.assertEqual(a.parent, self.home)

    def test_folders_checked_before_anything_is_downloaded(self):
        settings = SimpleNamespace(root=Path('C:/Users/Jos\u00e9/TTT2'), values={'tools': 'C:/TTT2/tools'})
        with mock.patch('build_launcher.players_tools', side_effect=AssertionError('downloaded')), \
             mock.patch('build_launcher.inputs_digest', return_value='0' * 64):
            with self.assertRaisesRegex(ValueError, 'plain letters, such as C:/TTT2'):
                bl.prepare(settings.root, settings, Report(), FakeRun(), home=self.home)
            settings.root = Path('D:/' + 'x' * 120)
            with self.assertRaisesRegex(ValueError, 'too long'):
                bl.prepare(settings.root, settings, Report(), FakeRun(), home=self.home)
            settings.root = Path('C:/TTT2')
            with self.assertRaisesRegex(bl.BuildError, 'built in has letters the Windows build tools cannot read'):
                bl.prepare(settings.root, settings, Report(), FakeRun(), home=Path('C:/Users/Jos\u00e9/b'))

    def test_install_paths_do_not_stop_the_launcher_build(self):
        # (Only Set Up Game gives them to the game's installer.)
        self.settings.values['install'] = 'C:/Spiele/\u0416'
        self.prepare()


class Builds(Project):
    def test_first_start_builds_then_reuses_the_build(self):
        run = FakeRun()
        program = self.prepare(run)
        folder = bl.project_folder(self.home, self.root)
        self.assertEqual(program.parent.parent, folder)
        self.assertEqual(sorted(p.name for p in program.parent.iterdir()), ['SDL3.dll', 'program.exe'])
        configure = run.calls[0]
        for option in ('-DTTT2_LAUNCHER_ONLY=ON', '-DTTT2_LAUNCHER_SDL=system', '-DSDL3_DIR=sdl',
                       '-DCMAKE_C_COMPILER=clang', '-DCMAKE_CXX_COMPILER=clang++', '-DCMAKE_MAKE_PROGRAM=ninja'):
            self.assertIn(option, configure)
        self.assertEqual(configure[configure.index('-S') + 1], str(self.root))
        self.assertTrue((folder / 'work/.cmake/api/v1/query/codemodel-v2').is_file())
        self.assertIn(bl.PROGRAM_TARGET, run.calls[1])
        again = FakeRun()
        with mock.patch('build_launcher.players_tools', side_effect=AssertionError('tools needed')):
            self.assertEqual(bl.prepare(self.root, self.settings, Report(), again, home=self.home), program)
        self.assertEqual(again.calls, [])

    def test_a_change_builds_again_and_keeps_the_one_before(self):
        first = self.prepare()
        write(self.root / 'launcher/ui/src/ui.cpp', 'changed')
        second = self.prepare()
        self.assertNotEqual(first.parent, second.parent)
        self.assertTrue(first.is_file())
        write(self.root / 'launcher/ui/src/ui.cpp', 'changed again')
        third = self.prepare()
        self.assertFalse(first.parent.exists())      # (only the one before stays)
        self.assertTrue(second.is_file() and third.is_file())

    def test_a_failed_build_keeps_the_last_good_one(self):
        first = self.prepare()
        current = (first.parent.parent / 'current.json').read_text()
        write(self.root / 'launcher/ui/src/ui.cpp', 'broken')
        with self.assertRaisesRegex(bl.BuildError, 'could not be built'):
            self.prepare(FakeRun(fail_build=True))
        self.assertEqual((first.parent.parent / 'current.json').read_text(), current)
        self.assertTrue(first.is_file())
        self.assertEqual([p.name for p in first.parent.parent.glob('part-*')], [])

    def test_try_again_starts_from_a_clean_build_folder(self):
        self.prepare()
        work = bl.project_folder(self.home, self.root) / 'work'
        write(work / 'stale.txt')
        self.prepare(clean=True)
        self.assertFalse((work / 'stale.txt').exists())

    def test_other_tools_start_a_clean_build_folder(self):
        self.prepare()
        work = bl.project_folder(self.home, self.root) / 'work'
        write(work / 'stale.txt')
        write(self.root / 'launcher/ui/src/ui.cpp', 'changed')
        self.tools = bl.Tools('cmake', 'ninja', 'clang-other', 'clang++', 'sdl')
        self.prepare()
        self.assertFalse((work / 'stale.txt').exists())

    def test_compiler_folder_goes_first_on_path(self):
        self.tools.path = ['C:/tools/llvm-mingw/bin']
        run = FakeRun()
        run.environment = {'PATH': 'C:/Windows'}
        self.prepare(run)
        self.assertEqual(run.environment['PATH'], os.pathsep.join(['C:/tools/llvm-mingw/bin', 'C:/Windows']))

    def test_one_build_at_a_time_and_the_waiting_start_takes_it(self):
        folder = bl.project_folder(self.home, self.root)
        holder = bl.BuildLock(folder)
        self.assertTrue(holder.take())
        other = bl.BuildLock(folder)
        self.assertFalse(other.take())
        other.close()
        report = Report()
        built = []

        def finish():
            time.sleep(0.6)
            built.append(bl.build(self.root, folder, bl.inputs_digest(self.root), self.tools, FakeRun(), Report()))
            holder.close()
        thread = threading.Thread(target=finish)
        thread.start()
        run = FakeRun()
        program = bl.prepare(self.root, self.settings, report, run, self.tools, home=self.home)
        thread.join()
        self.assertEqual(program, built[0])
        self.assertEqual(run.calls, [])
        self.assertIn('Another start is preparing the launcher: waiting for it', report.steps)


class Pieces(unittest.TestCase):
    def test_ninja_progress(self):
        self.assertEqual(bl.ninja_fraction('[25/100] Building CXX object x.obj'), 0.25)
        self.assertIsNone(bl.ninja_fraction('-- Configuring done'))
        self.assertIsNone(bl.ninja_fraction('[0/0] nothing'))

    def test_runner_logs_and_says_why(self):
        with tempfile.TemporaryFile('w+', encoding='utf-8') as log:
            run = bl.Runner(log)
            seen = []
            run([sys.executable, '-c', 'print("[1/2] one"); print("[2/2] two")'], 'Never', lines=seen.append)
            self.assertEqual(seen, ['[1/2] one', '[2/2] two'])
            with self.assertRaisesRegex(bl.BuildError, r'Building failed \(exit code 3\): .*broken header'):
                run([sys.executable, '-c', 'import sys; print("x.cpp: error: broken header"); sys.exit(3)'],
                    'Building failed')
            with self.assertRaisesRegex(bl.BuildError, 'cannot be started'):
                run([str(Path(tempfile.gettempdir()) / 'no-such-program-here')], 'Configure failed')
            log.seek(0)
            text = log.read()
        self.assertIn('[2/2] two', text)
        self.assertIn('broken header', text)

    def test_sdl_pin_is_set_up_games(self):
        lock = json.loads((REPO / 'tools/windows-bootstrap.lock.json').read_text(encoding='utf-8-sig'))
        script = (REPO / 'tools/setup_windows_runtime.ps1').read_text(encoding='utf-8')
        self.assertIn(lock['sdl']['url'], script)
        self.assertIn("'%s'" % lock['sdl']['sha256'], script)
        self.assertIn(lock['sdl']['folder'], script)
        self.assertTrue(lock['sdl']['url'].endswith('/%s-devel-%s-mingw.zip' % tuple(lock['sdl']['folder'].split('-'))))

    def test_program_target_is_one_the_build_has(self):
        sources = (REPO / 'launcher/app/CMakeLists.txt').read_text()
        self.assertTrue(re.search(r'add_executable\(%s\b' % re.escape(bl.PROGRAM_TARGET), sources), bl.PROGRAM_TARGET)


class Start(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.settings = Settings(root=self.root)

    def test_program_arguments(self):
        program = Path('C:/b/program.exe')
        self.assertEqual(bl.program_arguments(program, self.root, self.settings, arguments()),
                         [str(program), '--files', str(self.root)])
        game = self.root / 'game.wua'
        said = bl.program_arguments(program, self.root, self.settings,
                                    arguments(config=self.root / 'c.json', fighters=[str(game)]))
        self.assertEqual(said[3:], ['--config', str(self.root / 'c.json'), str(game)])
        other = Settings(self.root / 'build-windows-ci', None, self.root)
        said = bl.program_arguments(program, self.root, other, arguments(ui_smoke_test=self.root / 'ui.json'))
        self.assertEqual(said[3:], ['--build-dir', str(self.root / 'build-windows-ci'),
                                    '--ui-smoke-test', str(self.root / 'ui.json')])

    def test_started_detached_with_no_handles_of_this_process(self):
        process = mock.Mock()
        process.wait.side_effect = subprocess.TimeoutExpired('program', 1.5)
        environment = {'TTT2_LAUNCHER_EXE': 'C:/apps/old.exe', 'TTT2_LAUNCHER_AFTER': '12', 'PATH': 'p'}
        with mock.patch.dict(os.environ, environment, clear=True), \
             mock.patch('subprocess.Popen', return_value=process) as popen:
            self.assertEqual(bl.start(['program.exe', '--files', 'C:/TTT2'], self.root), 0)
        options = popen.call_args.kwargs
        self.assertEqual(popen.call_args.args[0], ['program.exe', '--files', 'C:/TTT2'])
        self.assertEqual((options['stdin'], options['stdout'], options['stderr']),
                         (subprocess.DEVNULL,) * 3)
        self.assertTrue(options['close_fds'])
        self.assertEqual(options['env'], {'TTT2_LAUNCHER_EXE': 'C:/apps/old.exe', 'PATH': 'p'})
        self.assertEqual(options['creationflags'], getattr(subprocess, 'DETACHED_PROCESS', 0) |
                         getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        self.assertEqual(options['cwd'], self.root)

    def test_a_program_that_stops_at_once_is_said(self):
        process = mock.Mock()
        process.wait.return_value = 2
        with mock.patch('subprocess.Popen', return_value=process):
            with self.assertRaisesRegex(bl.BuildError, 'exit code 2'):
                bl.start(['program.exe'], self.root)
        process.wait.return_value = 0   # (handed over to the launcher already running)
        with mock.patch('subprocess.Popen', return_value=process):
            self.assertEqual(bl.start(['program.exe'], self.root), 0)

    def test_a_real_program_starts(self):
        mark = self.root / 'started.txt'
        code = 'import pathlib, sys; pathlib.Path(sys.argv[1]).write_text("yes")'
        bl.start([sys.executable, '-c', code, str(mark)], self.root, wait=True)
        self.assertEqual(mark.read_text(), 'yes')


class Main(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.settings = Settings(root=self.root)

    def test_check_builds_nothing(self):
        with mock.patch('build_launcher.prepare', side_effect=AssertionError('built')):
            self.assertEqual(bl.main(arguments(check=True), self.settings, self.root), 0)

    def test_smoke_test_waits_for_the_program(self):
        with mock.patch('build_launcher.prepare', return_value=Path('C:/b/program.exe')), \
             mock.patch('build_launcher.start', return_value=0) as start:
            code = bl.main(arguments(ui_smoke_test=self.root / 'ui.json'), self.settings, self.root)
        self.assertEqual(code, 0)
        self.assertTrue(start.call_args.kwargs['wait'])
        self.assertIn('--ui-smoke-test', start.call_args.args[0])

    def test_without_a_window_a_failure_is_told(self):
        with mock.patch('build_launcher.prepare', side_effect=bl.BuildError('No compiler.')), \
             mock.patch('build_launcher.Window.open', return_value=None), \
             mock.patch('build_launcher.tell') as tell:
            self.assertEqual(bl.main(arguments(), self.settings, self.root), 1)
        self.assertEqual(tell.call_args.args, ('No compiler.', self.root / bl.BUILD_LOG))

    def test_with_a_window_the_work_runs_for_it(self):
        class FakeWindow:
            runner = None

            def __init__(self):
                self.steps = []

            def step(self, text):
                self.steps.append(text)

            def fraction(self, value):
                pass

            def run(self, job, log):
                job(self, False)
                return 0
        window = FakeWindow()
        with mock.patch('build_launcher.prepare', return_value=Path('C:/b/program.exe')), \
             mock.patch('build_launcher.start', return_value=0) as start:
            self.assertEqual(bl.main(arguments(fighters=['game.wua']), self.settings, self.root, window=window), 0)
        self.assertEqual(start.call_args.args[0][:3], [str(Path('C:/b/program.exe')), '--files', str(self.root)])
        self.assertIn('Starting the launcher', window.steps)
        self.assertTrue((self.root / bl.BUILD_LOG).is_file())

    def test_a_launcher_that_reopened_this_is_not_waited_for(self):
        with mock.patch.dict(os.environ, {'TTT2_LAUNCHER_UI_PID': '4242'}):
            bl.main(arguments(check=True), self.settings, self.root)
            self.assertNotIn('TTT2_LAUNCHER_UI_PID', os.environ)

    def test_newest_launcher_replaces_the_exe_and_opens_it(self):
        report = mock.Mock()
        with mock.patch('self_update.update', return_value='0.9.0') as update, \
             mock.patch('self_update.open_updated') as opened:
            self.assertTrue(bl.newest_launcher(Path('C:/apps/old.exe'), report))
        self.assertEqual(update.call_args.args[0], Path('C:/apps/old.exe'))
        opened.assert_called_once_with(Path('C:/apps/old.exe'))
        with mock.patch('self_update.update', return_value=None), \
             mock.patch('self_update.open_updated') as opened:
            self.assertFalse(bl.newest_launcher(Path('C:/apps/old.exe'), report))
        opened.assert_not_called()


class Routing(unittest.TestCase):
    def test_main_py_without_worker_or_query_is_the_bridge(self):
        import main
        for argv, expected in ((['main.py', '--build-dir', 'build-windows-tools'], dict(check=False, fighters=[])),
                               (['main.py', '--build-dir', 'b', '--check'], dict(check=True)),
                               (['main.py', '--build-dir', 'b', 'D:/games/game.wua'],
                                dict(fighters=['D:/games/game.wua'])),
                               (['main.py', '--config', 'c.json', '--ui-smoke-test', 'ui.json'], {})):
            with mock.patch.object(sys, 'argv', argv), \
                 mock.patch('build_launcher.main', return_value=7) as bridge:
                self.assertEqual(main.main(), 7)
            args = bridge.call_args.args[0]
            for key, value in expected.items():
                self.assertEqual(getattr(args, key), value, argv)
        with mock.patch.object(sys, 'argv', ['main.py', '--query', 'status']), \
             mock.patch('query.main', return_value=0), \
             mock.patch('build_launcher.main', side_effect=AssertionError('bridge')):
            self.assertEqual(main.main(), 0)


@unittest.skipUnless(os.name == 'nt', 'the Tk window is tried on Windows only (no window on a developer\'s desktop)')
class TkWindow(unittest.TestCase):
    """The bootstrap window itself (Windows, and Wine without a display, can make one)."""

    def setUp(self):
        self.window = bl.Window.open()
        if not self.window: self.skipTest('Tk cannot make a window here')

    def run_window(self, job, press, exe=None):
        """Runs the window; once the failure's buttons show, records them and presses `press`."""
        window, seen = self.window, []

        def watch():
            buttons = {b['text']: b for b in window.buttons.winfo_children()}
            if buttons and not window.busy:
                seen.append((sorted(buttons), window.heading['text'], window.text['text']))
                buttons[press].invoke()     # (and no more watching: the window may be gone)
            else:
                window.top.after(50, watch)
        window.top.after(50, watch)
        environment = {'TTT2_LAUNCHER_EXE': str(exe)} if exe else {}
        with mock.patch.dict(os.environ, environment), mock.patch('self_update.running_exe',
                                                                 return_value=exe):
            return window.run(job, Path('launcher-build.log')), seen

    def test_failure_shows_why_and_try_again_builds_clean(self):
        calls = []

        def job(report, clean):
            calls.append(clean)
            if not clean: raise bl.BuildError('No compiler.')
            report.step('Building the launcher')
            report.fraction(0.5)
        code, seen = self.run_window(job, 'Try again')
        self.assertEqual(code, 0)
        self.assertEqual(calls, [False, True])
        self.assertEqual(seen, [(['Close', 'Open log', 'Releases page', 'Try again'],
                                 'The new launcher could not be prepared.', 'No compiler.')])

    def test_an_exe_is_offered_the_newest_launcher(self):
        def job(report, clean):
            raise bl.BuildError('No compiler.')
        exe = Path(__file__)
        with mock.patch('build_launcher.newest_launcher', return_value=True) as newest:
            code, seen = self.run_window(job, 'Get the newest launcher', exe)
        self.assertEqual(code, 0)
        self.assertEqual(seen[0][0], ['Close', 'Get the newest launcher', 'Open log', 'Try again'])
        self.assertEqual(newest.call_args.args[0], exe)

    def test_close_after_a_failure_ends_with_an_error(self):
        def job(report, clean):
            raise bl.BuildError('No compiler.')
        code, seen = self.run_window(job, 'Close')
        self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
