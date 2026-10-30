"""Contract tests for launcher paths and actual backend command arguments."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/characters'))

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
    def test_only_release_exe_updates_itself(self):
        from backend import worker
        with mock.patch.dict(os.environ, {'TTT2_LAUNCHER_EXE': ''}), self.assertRaisesRegex(ValueError, 'release .exe'):
            worker(self.settings, 'launcher', [])
        with mock.patch.dict(os.environ, {'TTT2_LAUNCHER_EXE': ''}), self.assertRaisesRegex(ValueError, 'test build'):
            worker(self.settings, 'files', [])
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

if __name__=='__main__':unittest.main()
