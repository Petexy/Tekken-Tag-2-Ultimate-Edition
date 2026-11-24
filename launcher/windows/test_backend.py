"""Contract tests for launcher paths and actual backend command arguments."""
import contextlib
import io
from pathlib import Path
import os
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
from backend import Settings, write_json
# T8Extraction patches ttt2char before worker() puts tools/characters on the path.
sys.path.append(str(Path(__file__).resolve().parents[2] / 'tools/characters'))

class LauncherBackend(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.build=self.root/'build'
        self.build.mkdir(); self.config=self.root/'settings.json'
        self.settings=Settings(self.build,self.config,self.root)
        self.settings.values.update(data=str(self.root/'TTT2Ultimate'),packs=str(self.root/'packs'),saves=str(self.root/'saves'),install='')
    def make_title(self,path):
        (path/'code').mkdir(parents=True); (path/'code/Tekken.rpx').touch()
        (path/'content/hdd').mkdir(parents=True); (path/'content/hdd/data000.ofs').touch()
    def test_build_tools_are_found_for_both_cmake_cache_types(self):
        compiler=self.root/'tools/llvm-mingw-20261020-ucrt-x86_64/bin/clang++.exe'
        for kind in ('FILEPATH','STRING'):
            (self.build/'CMakeCache.txt').write_text('CMAKE_CXX_COMPILER:'+kind+'='+str(compiler))
            self.assertEqual(Settings(self.build,self.config,self.root).values['tools'],str(self.root/'tools'))
    def test_paths_persist_without_changing_parent_environment(self):
        self.settings.save(); other=Settings(self.build,self.config,self.root)
        self.assertEqual(other.values,self.settings.values)
        before=dict(os.environ); env=other.environment()
        self.assertEqual(dict(os.environ),before)
        self.assertEqual(env['TTT2_CHARACTERS'],str(self.root/'packs'))
        self.assertEqual(env['TTT2_SAVE_DIR'],str(self.root/'saves'))
        self.assertEqual(env['LOCALAPPDATA'],str(self.root))
    def test_invalid_paths_do_not_replace_working_configuration(self):
        self.settings.save(); before=self.config.read_bytes()
        self.settings.values['packs']='relative/pack'
        with self.assertRaises(ValueError): self.settings.save()
        self.assertEqual(self.config.read_bytes(),before)
    def test_development_game_gets_source_argument_without_shell(self):
        exe=self.build/'ttt2-ultimate.exe';exe.touch()
        archive=self.root/'game with spaces & chars.wua';archive.touch()
        self.settings.values['source']=str(archive)
        self.assertEqual(self.settings.game_command(),[str(exe),str(archive)])
    def test_installed_game_needs_marker_and_executable(self):
        install=self.root/'installed';install.mkdir();self.settings.values['install']=str(install)
        (install/'.ttt2-install').touch()
        with self.assertRaises(ValueError):self.settings.game_command()
        (install/'TTT2 Ultimate.exe').touch()
        self.assertEqual(self.settings.game_command(),[str(install/'TTT2 Ultimate.exe')])
    def test_import_and_remove_share_the_production_entrypoint(self):
        title=self.root/'title';self.make_title(title);self.settings.values['title']=str(title)
        cmd=self.settings.import_command(['akuma','reina'])
        self.assertEqual(cmd[3:5],['akuma','reina'])
        self.assertEqual(cmd[cmd.index('--game')+1],str(title))
        self.assertEqual(cmd[cmd.index('--out')+1],str(self.root/'packs'))
        self.assertIn('--progress',cmd)
        self.assertIn('--remove',self.settings.import_command(['geese'],True))
        self.assertTrue(cmd[2].endswith('import_character.py'))
        self.assertEqual(cmd[cmd.index('--outfits')+1],'none')
        cmd=self.settings.import_command(['akuma','reina'],outfits='akuma')
        self.assertEqual(cmd[cmd.index('--outfits')+1],'akuma')
        self.assertNotIn('--outfits',self.settings.import_command(['geese'],True))
    def test_incomplete_title_and_empty_selection_are_rejected(self):
        with self.assertRaises(ValueError):self.settings.import_command(['reina'])
        with self.assertRaises(ValueError):self.settings.import_command([])
    def test_installed_title_wins_over_old_extraction(self):
        install=self.root/'installed';self.make_title(install/'game')
        (install/'.ttt2-install').touch();self.settings.values['install']=str(install)
        self.assertEqual(self.settings.title(),install/'game')
    def test_install_update_use_production_installer(self):
        exe=self.build/'ttt2-ultimate.exe';exe.touch();archive=self.root/'game.wua';archive.touch()
        folder=self.root/'destination';self.settings.values.update(source=str(archive),install=str(folder))
        self.assertEqual(self.settings.installer_command(),[str(exe),'--install',str(archive),str(folder)])
        with self.assertRaises(ValueError):self.settings.installer_command(True)
        folder.mkdir();(folder/'.ttt2-install').touch()
        self.assertEqual(self.settings.installer_command(True),[str(exe),'--update',str(folder)])

    def test_game_update_needs_an_installed_game(self):
        from backend import worker, installed_by
        with self.assertRaisesRegex(ValueError, 'Set up the game first'):
            worker(self.settings, 'upgrade', [])
        self.assertEqual(installed_by(self.settings), '')
    def test_build_needs_the_libraries_set_up_prepares(self):
        from backend import worker
        cmake=Path(self.settings.values['tools'])/'python/cmake/data/bin/cmake.exe'
        cmake.parent.mkdir(parents=True);cmake.touch()
        with self.assertRaisesRegex(ValueError, 'Use Set Up Game'):
            worker(self.settings, 'build', [])
    def test_only_release_exe_updates_itself(self):
        from backend import worker
        with mock.patch.dict(os.environ, {'TTT2_LAUNCHER_EXE': ''}), self.assertRaisesRegex(ValueError, 'release .exe'):
            worker(self.settings, 'launcher', [])
        with mock.patch.dict(os.environ, {'TTT2_LAUNCHER_EXE': ''}), self.assertRaisesRegex(ValueError, 'test build'):
            worker(self.settings, 'files', [])
    def test_files_worker_says_when_the_program_is_the_exes(self):
        # (compat review #3: the new launcher's env says its program is built into the .exe; update_files refuses
        # changes to it then.)
        from backend import worker
        import self_update
        for value, expected in (('1', True), ('', False)):
            with mock.patch.dict(os.environ, {self_update.PROGRAM_IN_EXE_VARIABLE: value}), \
                    mock.patch.object(self_update, 'running_exe', return_value='C:/x.exe'), \
                    mock.patch.object(self_update, 'test_branch', return_value='dev-test'), \
                    mock.patch.object(self_update, 'update_files') as update:
                worker(self.settings, 'files', [])
            self.assertEqual(update.call_args.kwargs, {'program_in_exe': expected})
    def test_failure_says_what_failed(self):
        from backend import failure
        ctest = ['94% tests passed, 1 tests failed out of 17', '', 'The following tests FAILED:',
                 '\t 12 - noctis_assault_test (Not Run)', '\t 13 - title_test (Failed)', 'Errors while running CTest']
        self.assertEqual(failure(ctest), 'Failed checks: noctis_assault_test (Not Run), title_test.')
        ninja = ['[377/380] Building CXX object practice.cpp.obj', 'FAILED: [code=1] practice.cpp.obj',
                 "C:/TTT2/runtime/src/title/practice.cpp:158:44: error: use of undeclared identifier 'memmem'",
                 '1 error generated.']
        self.assertEqual(failure(ninja), "Build error: C:/TTT2/runtime/src/title/practice.cpp:158:44: error: use of "
                                         "undeclared identifier 'memmem'")
        self.assertEqual(failure(['Configure failed']), '')

class InstallFolderWithAccent(unittest.TestCase):
    """A tester's: the game installed into a folder with an à, which the installer printed and recorded in the ANSI
    code page; the launcher read it as UTF-8, kept a folder with U+FFFD and offered Set Up Game again."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name); self.local=self.root/'Local'; (self.local/'TTT2Ultimate').mkdir(parents=True)
        self.game=self.root/'Desktop/Novit\u00e0/TTT2'; self.game.mkdir(parents=True)
        (self.game/'.ttt2-install').write_text('complete')
        environment=mock.patch.dict(os.environ,LOCALAPPDATA=str(self.local)); environment.start(); self.addCleanup(environment.stop)
        self.project=self.root/'launcher'; (self.project/'local').mkdir(parents=True)
    def settings(self):
        return Settings(self.project/'build',None,self.project)
    def test_installer_output_in_the_ansi_code_page(self):
        from backend import decoded, run_command
        self.assertEqual(decoded('@folder C:\\Novit\u00e0'.encode('cp1252')), '@folder C:\\Novit\u00e0')
        self.assertEqual(decoded('Novit\u00e0'.encode('utf-8')), 'Novit\u00e0')
        settings=self.settings(); settings.values['install']=''
        script='import sys; sys.stdout.buffer.write(b"@folder " + sys.argv[1].encode("cp1252") + b"\\r\\n")'
        with mock.patch('builtins.print'):
            run_command([sys.executable,'-c',script,str(self.game)],settings)
        self.assertEqual(settings.values['install'],str(self.game))
        self.assertEqual(self.settings().installed(),self.game)
    def test_record_in_the_ansi_code_page_is_read(self):
        (self.local/'TTT2Ultimate/installed').write_bytes(str(self.game).encode('cp1252')+b'\n')
        self.assertEqual(self.settings().installed(),self.game)
    def test_setting_read_wrongly_before_is_repaired(self):
        from backend import write_json
        write_json(self.project/'local/windows-launcher.json',{'install':str(self.game).replace('\u00e0','\ufffd')})
        self.assertEqual(self.settings().installed(),self.game)
        (self.local/'TTT2Ultimate/installed').write_bytes(str(self.game).encode('cp1252')+b'\n')
        self.assertEqual(self.settings().installed(),self.game)
    def test_letters_the_code_page_has_not(self):
        from backend import unreadable_letters
        self.assertEqual(unreadable_letters('C:/Novit\u00e0/Jos\u00e9'),'')
        self.assertEqual(unreadable_letters('C:/\u6e38\u620f/TTT2'),'\u620f\u6e38')

class OlderGame(unittest.TestCase):
    """Testers played packs of the 0.6.2 importer on a game an 0.5.1 launcher built (the launcher had updated itself,
    the game only says an update is ready): no summons or effects, other hit reactions. While the game is from an
    older launcher, Play and adding or updating characters wait for its Update."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name); self.build=self.root/'build-windows-tools'; self.build.mkdir()
        (self.root/'launcher/builder').mkdir(parents=True)
        (self.root/'launcher/builder/CMakeLists.txt').write_text('set(TTT2_LAUNCHER_VERSION 0.6.2)\n')
        self.settings=Settings(self.build,self.root/'settings.json',self.root)
        self.game=self.root/'game'; self.game.mkdir()
        self.settings.values.update(data=str(self.root/'TTT2Ultimate'),packs=str(self.root/'packs'),
                                    saves=str(self.root/'saves'),install=str(self.game),tools=str(self.root/'tools'))
    def built(self,files):
        (self.build/'ttt2-installed-version.txt').write_text(files+'\n',encoding='utf-8')
    def test_only_an_older_version_is_blocked(self):
        from backend import older_game
        release='0.6.2 d9258007cb1c9533303c4fb917898bec14e19873'
        self.built('0.5.1 79795183ad3a7f9fd51a4c8d2a8cd1b3fde3e6a1')
        self.assertEqual(older_game(self.settings,release),'',"no game installed (a fresh setup): nothing waits")
        (self.game/'.ttt2-install').touch()
        self.assertEqual(older_game(self.settings,release),'0.5.1')
        self.assertEqual(older_game(self.settings,'0.6.2'),'0.5.1')
        for game,why in (('0.6.2 d9258007cb1c9533303c4fb917898bec14e19873','the game is current'),
                         ('0.6.2 0123456789abcdef0123456789abcdef01234567','a test build\'s other commit'),
                         ('0.6.2','the same version'),('0.7.0','a newer version'),
                         ('0.10.0 aaaaaaa','numbers, not text'),('next','not a version')):
            self.built(game); self.assertEqual(older_game(self.settings,release),'',why)
        self.built('0.9.1'); self.assertEqual(older_game(self.settings,'0.10.0'),'0.9.1')
        (self.build/'ttt2-installed-version.txt').unlink()
        self.assertEqual(older_game(self.settings,release),'',"what built it is not known")
    def test_note(self):
        from backend import older_game_note
        note=older_game_note('0.5.1','0.6.2 d9258007cb1c9533303c4fb917898bec14e19873')
        self.assertIn('(0.5.1; this one is 0.6.2)',note)
        self.assertIn('update it to play and to add or update characters',note)
        self.assertNotIn('ttt2',note.lower())
    def test_the_game_update_ends_the_wait(self):
        # (The game card's Update: setup_game.upgrade, then what the game is from is recorded.)
        from backend import older_game, worker
        import self_update
        (self.game/'.ttt2-install').touch(); self.built('0.5.1')
        files=self_update.files_id(self.root)
        self.assertEqual(older_game(self.settings,files),'0.5.1')
        with mock.patch('setup_game.upgrade') as upgrade, mock.patch.dict(os.environ), \
             mock.patch.object(sys,'path',sys.path[:]):
            worker(self.settings,'upgrade',[])
        upgrade.assert_called_once()
        self.assertEqual((self.build/'ttt2-installed-version.txt').read_text().strip(),'0.6.2')
        self.assertEqual(older_game(self.settings,files),'')

class T8Extraction(unittest.TestCase):
    def extract(self, names, complete=True):
        from backend import worker
        from ttt2char.tekken8 import autodump as t8
        settings = mock.Mock()
        settings.root = Path(__file__).resolve().parents[2]
        settings.values = {'tools': str(settings.root / 'local/windows-tools')}
        settings.environment.return_value = {}
        settings.import_command.return_value = ['python', '-u', 'import_character.py', *names]
        game = SimpleNamespace(game='fake-game', library='fake-library')
        with mock.patch.object(t8, 'find_tekken8', return_value=game), \
             mock.patch.object(t8, 'dump') as dump, \
             mock.patch.object(t8, 'game_version', return_value='test'), \
             mock.patch.object(t8, 'saved_files', return_value=[]) as saved, \
             mock.patch.object(t8, 'whole', return_value=complete), \
             mock.patch('runpy.run_path') as run, \
             mock.patch('setup_game.ensure_importer') as tools, \
             mock.patch.object(sys, 'argv', sys.argv[:]), \
             mock.patch.object(sys, 'path', sys.path[:]):
            if complete:
                worker(settings, 'import', names)
                run.assert_called_once()
                tools.assert_called_once()
            else:
                with self.assertRaisesRegex(RuntimeError, 'Azucena extraction is incomplete'):
                    worker(settings, 'import', names)
                run.assert_not_called()
            return dump.call_args, saved.call_args_list

    def test_azucena_and_reina_are_extracted_together(self):
        call, saved = self.extract(['azucena', 'reina'])
        self.assertEqual(call.args, ([29, 28],))
        self.assertNotIn(29, call.kwargs['references'])
        self.assertNotIn(28, call.kwargs['references'])
        self.assertEqual([c.args[0] for c in saved], ['cat', 'zbr'])

    def test_incomplete_azucena_does_not_start_import(self):
        self.extract(['azucena'], complete=False)

    def test_a_failed_save_says_why(self):
        from backend import worker
        from ttt2char.tekken8 import autodump as t8
        settings = mock.Mock()
        settings.root = Path(__file__).resolve().parents[2]
        settings.values = {'tools': str(settings.root / 'local/windows-tools')}
        settings.environment.return_value = {}
        settings.import_command.return_value = ['python', '-u', 'import_character.py', 'clive']
        out = io.StringIO()
        with mock.patch.object(t8, 'find_tekken8', return_value=SimpleNamespace(game='g', library='l')), \
             mock.patch.object(t8, 'dump', side_effect=t8.DumpError('this Tekken 8 build is not known')), \
             mock.patch('runpy.run_path') as run, mock.patch('setup_game.ensure_importer'), \
             mock.patch.object(sys, 'argv', sys.argv[:]), mock.patch.object(sys, 'path', sys.path[:]), \
             contextlib.redirect_stdout(out):
            with self.assertRaises(t8.DumpError):
                worker(settings, 'import', ['clive'])
        run.assert_not_called()
        self.assertIn('@error this Tekken 8 build is not known\n', out.getvalue())

if __name__=='__main__':unittest.main()
