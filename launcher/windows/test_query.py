"""The new launcher's questions (query.py, main.py --query): facts only, one JSON answer with the protocol, no
window. Asset-free; runs on any OS."""
from pathlib import Path
from unittest import mock
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

import query
import self_update
from backend import Settings

HERE = Path(__file__).resolve().parent


class Query(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.build = self.root / 'build-windows-tools'; self.build.mkdir()
        self.config = self.root / 'local/windows-launcher.json'
        self.data = self.root / 'appdata/TTT2Ultimate'
        environment = mock.patch.dict(os.environ, LOCALAPPDATA=str(self.root / 'appdata')); environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop('TTT2_LAUNCHER_EXE', None)
        self.settings = self.fresh()
        self.settings.values.update(data=str(self.data), packs=str(self.data / 'characters'),
                                    saves=str(self.data / 'save'), install='', source='', title='')

    def fresh(self):
        return Settings(self.build, self.config, self.root)

    def installed(self, program=True):
        folder = self.root / 'Games/TTT2'; folder.mkdir(parents=True, exist_ok=True)
        (folder / '.ttt2-install').touch()
        if program: (folder / 'TTT2 Ultimate.exe').touch()
        self.settings.values['install'] = str(folder)
        return folder

    def ask(self, name, *arguments, action=None, stdin=None):
        result = query.answer(name, self.settings, arguments, action, io.StringIO(stdin or ''))
        self.assertEqual(result.pop('protocol'), query.PROTOCOL)
        return result

    # ---- state

    def test_state_says_how_the_game_starts(self):
        folder = self.installed()
        (self.build / 'ttt2-installed-version.txt').write_text('0.7.1 ' + 'a' * 40, encoding='utf-8')
        state = self.ask('state')
        self.assertEqual(state['play']['argv'], [str(folder / 'TTT2 Ultimate.exe')])
        self.assertEqual(state['play']['cwd'], str(folder))
        self.assertEqual(state['play']['log'], str(self.data / 'logs/game-latest.log'))
        # Only what differs from the launcher's own environment: the game's folders, LOCALAPPDATA for the data.
        env = state['play']['env']
        self.assertEqual((env['TTT2_DATA_DIR'], env['TTT2_CHARACTERS'], env['TTT2_SAVE_DIR']),
                         (str(self.data), str(self.data / 'characters'), str(self.data / 'save')))
        self.assertNotIn('LOCALAPPDATA', env)   # (the data folder is LOCALAPPDATA's already)
        self.assertNotIn('HOME', env)
        self.settings.values['data'] = str(self.root / 'elsewhere/TTT2Ultimate')
        self.assertEqual(self.ask('state')['play']['env']['LOCALAPPDATA'], str(self.root / 'elsewhere'))
        self.assertEqual((state['installed'], state['installed_by']), (str(folder), '0.7.1 ' + 'a' * 40))
        self.assertEqual((state['root'], state['build'], state['config']),
                         (str(self.root), str(self.build), str(self.config)))
        self.assertEqual(state['settings']['install'], str(folder))
        self.assertEqual(sorted(state['settings']), sorted(query.FOLDERS))
        # Each folder's default (the new launcher's Settings > Folders > Default): what Settings found before
        # launcher.json changed it.
        self.assertEqual(sorted(state['defaults']), sorted(query.FOLDERS))
        self.assertEqual(state['defaults']['tools'], self.fresh().defaults['tools'])
        self.assertEqual((state['version'], state['files_id']), (self_update.version(), self_update.files_id()))
        self.assertEqual((state['display_file'], state['keyboard_file']),
                         (str(self.data / 'config/display.ini'), str(self.data / 'config/keyboard.ini')))
        self.assertEqual((state['data_problem'], state['cannot_replace'], state['exe'], state['branch']),
                         ('', '', None, None))
        self.assertIsNone(state['icon']); self.assertIsNone(state['latest_log'])

    def test_state_says_why_the_game_cannot_start(self):
        self.assertEqual(self.ask('state')['play'], {'problem': 'source'})
        self.installed(program=False)
        self.assertEqual(self.ask('state')['play'], {'problem': 'exe'})
        self.settings.values['data'] = str(self.root / 'Other')
        self.assertEqual(self.ask('state')['data_problem'], 'name')

    def test_state_names_the_newest_log_icon_and_exe(self):
        folder = self.installed()
        (folder / 'icon.png').touch()
        logs = self.data / 'logs'; logs.mkdir(parents=True)
        for i, name in enumerate(('import-1.log', 'setup-2.log', 'notes.txt')):
            (logs / name).touch(); os.utime(logs / name, (1000 + i, 1000 + i))
        exe = self.root / 'Ultimate_Launcher-x86_64.exe'; exe.touch()
        with mock.patch.dict(os.environ, TTT2_LAUNCHER_EXE=str(exe)):
            state = self.ask('state')
        self.assertEqual((state['icon'], state['latest_log'], state['logs'], state['exe']),
                         (str(folder / 'icon.png'), str(logs / 'setup-2.log'), str(logs), str(exe)))
        self.assertEqual(state['cannot_replace'], '')

    def test_state_through_main_without_tkinter(self):
        """main.py --query: its last line is the answer, and it never loads Tk (a query has no window)."""
        output = io.StringIO()
        argv = ['main.py', '--build-dir', str(self.build), '--config', str(self.config), '--query', 'state']
        sys.modules.pop('main', None)
        import main
        with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
            self.assertEqual(main.main(), 0)
        answer = json.loads(output.getvalue().strip().splitlines()[-1])
        self.assertEqual((answer['protocol'], answer['build']), (query.PROTOCOL, str(self.build)))
        self.assertNotIn('tkinter', sys.modules)
        self.assertTrue(output.getvalue().isascii())  # (letters beyond ASCII as \\u escapes)

    def test_paths_beyond_ascii_survive(self):
        self.settings.values['install'] = str(self.root / 'José/TTT2')
        line = io.StringIO()
        with contextlib.redirect_stdout(line):
            query.main('state', self.settings)
        self.assertTrue(line.getvalue().isascii())
        self.assertEqual(json.loads(line.getvalue())['settings']['install'], str(self.root / 'José/TTT2'))

    # ---- check

    def test_check_setup(self):
        self.assertEqual(self.ask('check', action='setup')['problem']['code'], 'inputs')
        archive = self.root / 'game.wua'; archive.touch()
        self.settings.values.update(source=str(archive), install=str(self.root / 'Games/TTT2'))
        self.assertEqual(self.ask('check', action='setup'), query.problem())
        self.settings.values['install'] = str(self.root / 'Gry/łódź')   # (not in the code page)
        problem = self.ask('check', action='setup')['problem']
        self.assertEqual((problem['code'], problem['what'], problem['letters']), ('installer_letters', 'install',
                                                                                  'łź'))
        self.settings.values['install'] = str(self.root / 'Games/TTT2')
        self.settings.values['tools'] = str(self.root / 'strànge tools')
        problem = self.ask('check', action='setup')['problem']
        self.assertEqual((problem['code'], problem['what'], problem['letters'], problem['path']),
                         ('tools_letters', 'tools', 'à', str(self.root / 'strànge tools')))
        self.settings.values['tools'] = str(self.root / ('t' * 200))
        self.assertEqual(self.ask('check', action='setup')['problem']['code'], 'tools_length')
        self.settings.values['tools'] = ''
        self.settings.build = self.root / 'other-build'
        self.assertEqual(self.ask('check', action='setup')['problem']['code'], 'tools_folder')

    def test_check_tasks(self):
        self.assertEqual(self.ask('check', action='import')['problem']['code'], 'no_fighters')
        self.assertEqual(self.ask('check', 'kazumi', action='import')['problem']['code'], 'title')
        title = self.root / 'title'
        (title / 'code').mkdir(parents=True); (title / 'code/Tekken.rpx').touch()
        (title / 'content/hdd').mkdir(parents=True); (title / 'content/hdd/data000.ofs').touch()
        self.settings.values['title'] = str(title)
        self.assertEqual(self.ask('check', 'kazumi', action='remove'), query.problem())
        self.assertEqual(self.ask('check', action='install')['problem']['code'], 'no_build')
        (self.build / 'ttt2-ultimate.exe').touch()
        self.assertEqual(self.ask('check', action='update')['problem']['code'], 'no_install')
        self.settings.values['title'] = ''
        self.assertEqual(self.ask('check', action='install')['problem']['code'], 'no_paths')
        self.installed()
        self.assertEqual(self.ask('check', action='update'), query.problem())
        for action in ('build', 'upgrade', 'shaders'):
            self.assertEqual(self.ask('check', action=action), query.problem())
        self.assertIn('check takes --action', self.ask('check', action='play')['error'])

    # ---- save-settings

    def test_save_settings(self):
        answer = self.ask('save-settings', stdin=json.dumps({'packs': str(self.root / 'my packs'), 'other': 'x'}))
        self.assertEqual(answer['settings']['packs'], str(self.root / 'my packs'))
        self.assertEqual(self.fresh().values['packs'], str(self.root / 'my packs'))
        self.assertNotIn('other', json.loads(self.config.read_text(encoding='utf-8')))
        before = self.config.read_bytes()
        self.assertEqual(self.ask('save-settings', stdin='{"data": "%s"}' % (self.root / 'Other').as_posix()),
                         query.problem('data_name', 'data'))
        self.settings = self.fresh()
        self.assertEqual(self.ask('save-settings', stdin='{"saves": "relative/saves"}'),
                         query.problem('relative', 'saves'))
        self.assertEqual(self.config.read_bytes(), before)
        self.assertIn('error', self.ask('save-settings', stdin='[1, 2]'))
        self.assertIn('error', self.ask('save-settings', stdin='{not json'))

    # ---- the importer's and GitHub's answers

    def test_importer_answers_get_the_protocol(self):
        with mock.patch.object(query, 'importer', return_value={'fighters': [], 'games': {}}) as importer:
            self.assertEqual(self.ask('status'), {'fighters': [], 'games': {}})
            self.assertEqual(self.ask('owned'), {'fighters': [], 'games': {}})
        self.assertEqual([c.args[1] for c in importer.call_args_list], ['status', 'owned'])
        with mock.patch.object(query, 'importer', side_effect=RuntimeError('Steam is not running')):
            self.assertEqual(self.ask('owned'), {'error': 'Steam is not running'})
        with mock.patch.object(self_update, 'build_commit', return_value=None):
            self.assertIn('error', self.ask('main'))
        with mock.patch.object(self_update, 'build_commit', return_value='c' * 40), \
                mock.patch.object(query, 'importer', return_value={'commits': 3}) as importer:
            self.assertEqual(self.ask('main'), {'commits': 3})
        self.assertEqual(importer.call_args.args[1:], ('main', '--commit', 'c' * 40))

    def test_release(self):
        newer = self_update.Release('99.0.0', 'v99.0.0', 'https://page', 'Ultimate_Launcher-x86_64.exe',
                                    'https://file', 123, 'ab' * 32)
        with mock.patch.object(self_update, 'ask', return_value=self_update.Answer(release=newer)):
            answer = self.ask('release')
        self.assertEqual(answer['newer'], dict(version='99.0.0', tag='v99.0.0', page='https://page',
                                               asset='Ultimate_Launcher-x86_64.exe', url='https://file', size=123,
                                               sha256='ab' * 32))
        same = self_update.Release(self_update.version(), 'v', 'p', 'a', 'u')
        with mock.patch.object(self_update, 'ask', return_value=self_update.Answer(release=same)):
            self.assertEqual(self.ask('release'), {'newer': None, 'none': False, 'error': ''})
        with mock.patch.object(self_update, 'ask', return_value=self_update.Answer(none=True)):
            self.assertEqual(self.ask('release')['none'], True)
        with mock.patch.object(self_update, 'ask', side_effect=OSError(110, 'Connection timed out')):
            self.assertEqual(self.ask('release'), {'error': 'Connection timed out'})

    def test_hidden_program_answers_on_its_last_line(self):
        """As the launcher runs it: a program of its own, the answer on the last line of its output, 0."""
        result = subprocess.run([sys.executable, str(HERE / 'main.py'), '--build-dir', str(self.build), '--config',
                                 str(self.config), '--query', 'check', '--action', 'import'],
                                capture_output=True, text=True, timeout=120, env=dict(os.environ, PYTHONUTF8='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]),
                         dict(query.problem('no_fighters'), protocol=query.PROTOCOL))


if __name__ == '__main__': unittest.main()
