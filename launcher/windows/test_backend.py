"""Contract tests for launcher paths and actual backend command arguments."""
from pathlib import Path
import os
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
from backend import Settings, write_json

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
             mock.patch.object(sys, 'argv', sys.argv[:]), \
             mock.patch.object(sys, 'path', sys.path[:]):
            if complete:
                worker(settings, 'import', names)
                run.assert_called_once()
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
