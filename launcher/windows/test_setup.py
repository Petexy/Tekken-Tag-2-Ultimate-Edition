"""First-run setup regressions; all fixtures are synthetic and asset-free."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
from backend import Settings
from setup_game import download, unzip, verified_rpx, setup, validate_setup_paths, ensure_importer, importer_ready

class FirstRun(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_checked_download_and_corrupt_cache_repair(self):
        source=self.root/'source';source.write_bytes(b'verified runtime')
        asset=dict(url=source.as_uri(),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        out=self.root/'cache/runtime';out.parent.mkdir();out.write_bytes(b'interrupted')
        self.assertEqual(download(asset,out).read_bytes(),source.read_bytes())
        with mock.patch('urllib.request.urlopen',side_effect=AssertionError('cache should be reused')):
            self.assertEqual(download(asset,out),out)
    def test_hash_failure_never_replaces_cached_file(self):
        source=self.root/'source';source.write_bytes(b'bad bytes')
        out=self.root/'cache';out.write_bytes(b'previous')
        with self.assertRaisesRegex(ValueError,'checksum'):
            download(dict(url=source.as_uri(),sha256='0'*64),out)
        self.assertEqual(out.read_bytes(),b'previous')
    def test_downloaded_zip_cannot_escape_tools_folder(self):
        archive=self.root/'test.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape.exe',b'bad')
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            unzip(archive,self.root/'tools')
        self.assertFalse((self.root/'escape.exe').exists())
    def test_valid_tool_zip_extracts(self):
        archive=self.root/'test.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('bin/tool.exe',b'fake')
        unzip(archive,self.root/'tools')
        self.assertEqual((self.root/'tools/bin/tool.exe').read_bytes(),b'fake')
    def test_only_matching_game_revision_is_selected(self):
        wrong=self.root/'base/code/Tekken.rpx';wrong.parent.mkdir(parents=True);wrong.write_bytes(b'base')
        right=self.root/'update/code/Tekken.rpx';right.parent.mkdir(parents=True);right.write_bytes(b'update')
        expected=hashlib.sha256(b'update').hexdigest()
        self.assertEqual(verified_rpx(self.root,expected),right)
        with self.assertRaisesRegex(ValueError,'v16'):verified_rpx(self.root,'0'*64)
    def test_git_too_old_for_setting_safe_directory_is_not_used(self):
        from setup_game import recent_git
        for said,usable in (('git version 2.37.3.windows.1\n',False),('git version 2.38.0\n',True),
                            ('git version 2.56.0.windows.4\n',True),('',False)):
            with mock.patch('shutil.which',return_value='git.exe'), \
                 mock.patch('subprocess.run',return_value=mock.Mock(stdout=said)):
                self.assertEqual(recent_git(),usable,said)
        with mock.patch('shutil.which',return_value=None):self.assertFalse(recent_git())
    def test_missing_inputs_stop_before_downloading_tools(self):
        settings=Settings(self.root/'build-windows-tools',self.root/'config.json',self.root)
        settings.values.update(source='',title='',install='')
        with mock.patch('setup_game.ensure_tools') as tools:
            with self.assertRaises(ValueError):setup(settings,mock.Mock())
            tools.assert_not_called()

class ImporterTools(unittest.TestCase):
    """A launcher folder that did not set up the game (the release .exe after the project ZIP's setup): the game and
    its characters are there, the compiler, numpy and Pillow are not; adding or removing one gets them."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);(self.root/'tools').mkdir()
        lock=Path(__file__).resolve().parents[2]/'tools/windows-bootstrap.lock.json'
        (self.root/'tools/windows-bootstrap.lock.json').write_bytes(lock.read_bytes())
        self.settings=Settings(self.root/'build-windows-tools',self.root/'config.json',self.root)
        self.settings.values['tools']=str(self.root/'local/windows-tools')
        self.environment=mock.patch.dict('os.environ');self.environment.start();self.addCleanup(self.environment.stop)
    def module(self,name,text):
        path=self.root/'local/windows-tools/python'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    def test_probe_reads_the_build_tools_python_folder(self):
        self.module('numpy/__init__.py','raise ImportError("broken")');self.module('PIL/__init__.py','');self.module('PIL/Image.py','')
        self.assertFalse(importer_ready(self.settings))
        self.module('numpy/__init__.py','')
        self.assertTrue(importer_ready(self.settings))
    def test_missing_ones_are_got(self):
        run=mock.Mock()
        with mock.patch('setup_game.download',return_value=self.root/'llvm-mingw.zip') as download, \
             mock.patch('setup_game.unzip') as unzip, mock.patch('setup_game.importer_ready',return_value=False), \
             mock.patch('builtins.print'):
            ensure_importer(self.settings,run)
        self.assertTrue(download.call_args.args[1].name=='llvm-mingw.zip')
        self.assertEqual(unzip.call_args.args[1],self.root/'local/windows-tools')
        command=run.call_args.args[0]
        self.assertEqual(command[1:4],['-m','pip','install'])
        self.assertEqual(command[command.index('--target')+1],str(self.root/'local/windows-tools/python'))
        self.assertEqual(sorted(p.split('==')[0] for p in command[command.index('--target')+2:]),['Pillow','numpy'])
    def test_nothing_is_got_when_there(self):
        clang=self.root/'local/windows-tools/llvm-mingw-20261020-ucrt-x86_64/bin/clang.exe'
        clang.parent.mkdir(parents=True);clang.touch()
        run=mock.Mock()
        with mock.patch('setup_game.download') as download, mock.patch('setup_game.importer_ready',return_value=True):
            ensure_importer(self.settings,run)
        download.assert_not_called();run.assert_not_called()
        import os;self.assertEqual(os.environ['TTT2_HELPER_CC'],str(clang))

class PathPreflight(unittest.TestCase):
    def settings(self, root='D:/TTT2', tools='D:/TTT2/local/windows-tools'):
        from types import SimpleNamespace
        return SimpleNamespace(root=root, values={'tools':tools})
    def test_short_project_and_tools_are_accepted(self):
        validate_setup_paths(self.settings())
    def test_reported_nested_project_is_rejected_with_user_instructions(self):
        root='D:/Nuova cartella/' + 'Tekken-Tag-2-Ultimate-Edition-codex-native-windows-t7-reina(1)/' + 'Tekken-Tag-2-Ultimate-Edition-codex-native-windows-t7-reina'
        with self.assertRaisesRegex(ValueError, 'D:/TTT2'):
            validate_setup_paths(self.settings(root))
    def test_custom_tools_path_is_checked_separately(self):
        with self.assertRaisesRegex(ValueError,'tools folder path'):
            validate_setup_paths(self.settings(tools='D:/'+'x'*160))
    def test_letters_cmd_cannot_read_are_rejected(self):
        # (A tester's: CMake's batch files lost the à, "path not found".)
        root='C:/Users/Player/Desktop/Novit\u00e0/Tekken-Tag-2-Ultimate-Edition-dev-0-4-0'
        with self.assertRaisesRegex(ValueError, 'project folder path has letters .*\\(\u00e0\\).*C:/TTT2'):
            validate_setup_paths(self.settings(root, tools='C:/TTT2/local/windows-tools'))
        with self.assertRaisesRegex(ValueError, 'Windows tools folder path has letters'):
            validate_setup_paths(self.settings(tools='C:/Users/Jos\u00e9/tools'))
    def test_install_folder_the_installer_cannot_be_given(self):
        settings=self.settings(); settings.values.update(install='C:/\u6e38\u620f', source='C:/TTT2.wua')
        with self.assertRaisesRegex(ValueError, 'installation folder path has letters'):
            validate_setup_paths(settings)
        settings.values['install']='C:/Users/Player/Desktop/Novit\u00e0/TTT2'
        validate_setup_paths(settings)
    def test_windows_utf16_length_is_used(self):
        with self.assertRaisesRegex(ValueError,'project folder path'):
            validate_setup_paths(self.settings(root='D:/'+'\U0001f600'*55))

class DependencyCheckout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        path=Path(__file__).resolve().parents[2]/'tools/setup_deps.py'
        spec=importlib.util.spec_from_file_location('dependency_setup_tested',path)
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
    def test_windows_git_gets_process_local_longpath_option(self):
        with mock.patch.object(self.module.os,'name','nt'), mock.patch.object(self.module.subprocess,'run') as run:
            self.module.git('dependency','status')
            self.assertEqual(run.call_args.args[0][:7],['git','-c','safe.directory=*','-c','core.longpaths=true','-C','dependency'])
    def test_only_missing_files_are_restored(self):
        from types import SimpleNamespace
        with mock.patch.object(self.module.os,'name','nt'), mock.patch.object(self.module,'git',return_value=SimpleNamespace(stdout='source/missing header.h\0')) as git:
            self.module.repair_missing_windows_files('dependency')
            self.assertEqual(git.call_args_list[1].args,('dependency','restore','--source=HEAD','--worktree','--','source/missing header.h'))
    def test_linux_checkout_behavior_is_unchanged(self):
        with mock.patch.object(self.module.os,'name','posix'), mock.patch.object(self.module,'git') as git:
            self.module.repair_missing_windows_files('dependency')
            git.assert_not_called()
    # tools/setup_deps.py where Git calls every folder someone else's (an exFAT or FAT32 drive, a drive from another
    # PC), after setups that stopped there: the library folders they left (only .git; empty) are downloaded again.
    def test_unfinished_download_on_a_drive_git_calls_foreign(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        def git(folder,*args):
            return subprocess.run(['git','-c','user.name=test','-c','user.email=test@example.com','-c','commit.gpgsign=false',
                                   '-C',str(folder),*args],check=True,capture_output=True,text=True).stdout.strip()
        source=root/'source';source.mkdir();git(source,'init','-q');(source/'file').write_text('pinned')
        git(source,'add','file');git(source,'commit','-q','-m','pinned')
        project=root/'project';(project/'tools').mkdir(parents=True)
        shutil.copy2(Path(__file__).resolve().parents[2]/'tools/setup_deps.py',project/'tools')
        pinned=dict(url=str(source),revision=git(source,'rev-parse','HEAD'))
        (project/'dependencies.lock.json').write_text(json.dumps({'Library':pinned,'Empty':pinned}))
        left=project/'third_party/Library';left.mkdir(parents=True);git(left,'init','-q')
        (project/'third_party/Empty').mkdir()
        result=subprocess.run([sys.executable,str(project/'tools/setup_deps.py')],capture_output=True,text=True,
                              env=dict(os.environ,GIT_TEST_ASSUME_DIFFERENT_OWNER='1'))
        self.assertEqual(result.returncode,0,result.stderr)
        for name in ('Library','Empty'):self.assertEqual((project/'third_party'/name/'file').read_text(),'pinned')

if __name__=='__main__':unittest.main()
