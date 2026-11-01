"""Windows launcher backend; GTK/Linux code and character conversion stay shared."""
from pathlib import Path
import collections
import glob
import json
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
# The game's programs (built with llvm-mingw's libc++) print and write paths in this PC's ANSI code page: the
# installer's "@folder" line and its record of the folder (%LOCALAPPDATA%\TTT2Ultimate\installed). (cp1252 off
# Windows: tests.)
ANSI = 'mbcs' if os.name == 'nt' else 'cp1252'


def decoded(data):
    """Bytes a program wrote: UTF-8, else (an à in a path, say) the ANSI code page."""
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode(ANSI, 'replace')


def unreadable_letters(path):
    """The letters of `path` the game's programs cannot be given (they get their arguments in the ANSI code page)."""
    return ''.join(sorted({c for c in str(path) if not c.isascii() and not _ansi(c)}))


def _ansi(letter):
    try:
        letter.encode(ANSI, 'strict')
        return True
    except UnicodeEncodeError:
        return False

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix('.part')
    part.write_text(json.dumps(value, indent=2), encoding='utf-8')
    part.replace(path)

class Settings:
    def __init__(self, build=None, file=None, root=ROOT):
        self.root = Path(root).resolve()
        self.build = Path(build or self.root / 'build-windows-tools').resolve()
        local = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'TTT2Ultimate'
        self.file = Path(file or (self.root / 'local/windows-launcher.json' if (self.root / 'local').is_dir() else local / 'launcher.json'))
        data = self.root / 'local/windows-userdata/TTT2Ultimate'
        if not data.exists(): data = local
        def first(path):
            return decoded(path.read_bytes()).splitlines()[0] if path.is_file() and path.stat().st_size else ''
        tools = ''
        cache = self.build / 'CMakeCache.txt'
        if cache.exists():
            for line in cache.read_text(encoding='utf-8').splitlines():
                if line.startswith('CMAKE_CXX_COMPILER:') and '=' in line:
                    tools = str(Path(line.split('=', 1)[1]).parent.parent.parent)
        title = self.root / 'local/wua-game/0000000000000000_v0'
        saves = self.root / 'local/windows-save'
        recorded = first(local / 'installed')
        self.values = dict(source=first(self.build / 'ttt2-game.txt'), title=str(title) if title.exists() else '',
                           install=recorded, data=str(data), packs=str(data / 'characters'),
                           saves=str(saves if saves.exists() else data / 'save'), tools=tools or str(self.root / 'local/windows-tools'))
        if self.file.exists(): self.values.update(json.loads(self.file.read_text(encoding='utf-8')))
        if not self.installed(): self.values['install'] = self.found_install(recorded) or self.values['install']

    def found_install(self, recorded):
        """The install the setting misses: the installer's record of its folder, else the folder the setting names
        with the letters a launcher read wrongly (an à became U+FFFD); '' when neither is one."""
        candidates = [recorded] if recorded else []
        if '\ufffd' in self.values['install']:
            candidates += sorted(glob.glob(glob.escape(self.values['install']).replace('\ufffd', '?')))
        return next((c for c in candidates if (Path(c) / '.ttt2-install').is_file()), '')

    def save(self):
        if Path(self.values['data']).name != 'TTT2Ultimate':
            raise ValueError('The data folder must end in TTT2Ultimate so runtime settings use the same location.')
        for key in ('data', 'packs', 'saves'):
            if not Path(self.values[key]).is_absolute(): raise ValueError(key + ' must be an absolute path')
        write_json(self.file, self.values)

    def environment(self):
        env = dict(os.environ, TTT2_DATA_DIR=self.values['data'], TTT2_CHARACTERS=self.values['packs'],
                   TTT2_SAVE_DIR=self.values['saves'], PYTHONUTF8='1', PYTHONUNBUFFERED='1')
        env['PYTHONPATH'] = os.pathsep.join([str(self.root / 'local/windows-python'), str(Path(self.values['tools']) / 'python'), env.get('PYTHONPATH', '')])
        compiler = Path(self.values['tools']) / 'llvm-mingw-20261020-ucrt-x86_64/bin/clang.exe'
        if compiler.exists():
            env['TTT2_HELPER_CC'] = str(compiler)
            env['PATH'] = str(compiler.parent) + os.pathsep + env.get('PATH', '')
        data = Path(self.values['data'])
        if data.name == 'TTT2Ultimate': env['LOCALAPPDATA'] = str(data.parent)
        return env

    def installed(self):
        folder = Path(self.values['install']) if self.values['install'] else None
        return folder if folder and (folder / '.ttt2-install').is_file() else None

    def game_command(self):
        folder = self.installed()
        if folder:
            exe = folder / 'TTT2 Ultimate.exe'
            if not exe.is_file(): raise ValueError('Installed game executable is missing. Build and update it first.')
            return [str(exe)]
        exe = self.build / 'ttt2-ultimate.exe'
        game = self.values['source'] or self.values['title']
        if not exe.is_file() or not game or not Path(game).exists():
            raise ValueError('Choose your Wii U source and build the Windows game first.')
        return [str(exe), game]

    def title(self):
        installed = self.installed()
        title = installed / 'game' if installed else Path(self.values['title'])
        if not (title / 'code/Tekken.rpx').is_file() or not (title / 'content/hdd/data000.ofs').is_file():
            raise ValueError('Choose an extracted title containing code/Tekken.rpx and content/hdd/data000.ofs, '
                             'or install your .wua first.')
        return title

    def installer_command(self, update=False):
        exe = self.build / 'ttt2-ultimate.exe'
        if not exe.is_file(): raise ValueError('Build the Windows game first.')
        if update:
            folder = self.installed()
            if not folder: raise ValueError('Choose a complete installation before updating.')
            return [str(exe), '--update', str(folder)]
        source = self.values['source'] or self.values['title']
        if not source or not Path(source).exists() or not self.values['install']:
            raise ValueError('Choose the Wii U source and destination in Paths first.')
        return [str(exe), '--install', source, self.values['install']]

    def import_command(self, names, remove=False, outfits='none'):
        """outfits: whose outfits an import makes, as import_character.py --outfits takes it."""
        if not names: raise ValueError('Select one or more fighters.')
        return [sys.executable, '-u', str(self.root / 'tools/characters/import_character.py'), *names,
                '--game', str(self.title()), '--out', self.values['packs'], '--progress',
                *(['--remove'] if remove else ['--outfits', outfits])]


def failure(lines):
    """What a failed command's last lines say went wrong, for the task panel: the checks ctest names as failed,
    else the build's first error; '' when they say neither."""
    for i, line in enumerate(lines):
        if line.startswith('The following tests FAILED:'):
            failed = []
            for listed in lines[i + 1:]:
                found = re.match(r'\s*\d+ - (\S+) \((.+)\)\s*$', listed)
                if not found: break
                failed.append(found.group(1) + ('' if found.group(2) == 'Failed' else ' (%s)' % found.group(2)))
            if failed: return 'Failed check%s: %s.' % ('' if len(failed) == 1 else 's', ', '.join(failed))
    for line in lines:
        if ': error: ' in line or ': fatal error: ' in line:
            text = line.strip()
            return 'Build error: ' + (text if len(text) <= 300 else text[:297] + '...')
    return ''


def run_command(command, settings):
    print('Starting:', subprocess.list2cmdline(command), flush=True)
    last = collections.deque(maxlen=400)
    with subprocess.Popen(command, cwd=settings.root, env=settings.environment(), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
        try:
            for data in process.stdout:
                line = decoded(data).rstrip('\r\n')
                print(line, flush=True)
                last.append(line)
                if line.startswith('@folder '):
                    settings.values['install'] = line[8:].strip(); settings.save()
            result = process.wait()
        except BaseException:
            process.terminate(); process.wait(); raise
    if result:
        # (Said in the task panel too: what a tester sends when it is all that is seen.)
        if why := failure(list(last)): print('@error ' + why, flush=True)
        raise RuntimeError('Task exited with code %d; see the log above.' % result)


def built_by(settings):
    """The launcher version whose files built the game in the build folder, with a test build's commit
    (self_update.files_id; '' when unknown)."""
    file = settings.build / 'ttt2-launcher-version.txt'
    return file.read_text(encoding='utf-8').strip() if file.is_file() else ''


def installed_by(settings):
    """The launcher version whose files built the installed game, as built_by ('' when unknown)."""
    file = settings.build / 'ttt2-installed-version.txt'
    return file.read_text(encoding='utf-8').strip() if file.is_file() and settings.installed() else ''


def importer(settings, *args, timeout=None):
    """The character importer's answer for the launcher (tools/characters/launcher.py), as for the
    Linux launcher: status (what is there) or owned (which DLC Steam says is owned)."""
    command = [sys.executable, '-u', str(settings.root / 'tools/characters/launcher.py'), *args]
    if args[0] == 'status' and settings.installed(): command += ['--game', str(settings.installed())]
    result = subprocess.run(command, cwd=settings.root, env=settings.environment(), capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        return json.loads(result.stdout)
    except ValueError:
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        raise RuntimeError(lines[-1] if lines else 'the importer ended with code %d' % result.returncode)


def worker(settings, action, names, cancelled=lambda: False, outfits='none'):
    os.environ.update(settings.environment())
    sys.path[:0] = [str(settings.root / 'local/windows-python'), str(settings.root / 'tools/characters'), str(Path(settings.values['tools']) / 'python')]
    if action == 'setup':
        from setup_game import setup
        setup(settings, run_command)
    elif action == 'upgrade':
        from setup_game import upgrade
        upgrade(settings, run_command)
    elif action == 'build':
        tools = Path(settings.values['tools'])
        if not (tools / 'python/cmake/data/bin/cmake.exe').is_file():
            raise ValueError('Select the Windows build tools folder in Paths first.')
        # (the last of the libraries Set Up Game prepares before building: missing when no setup got that far)
        if not (settings.root / 'build-windows-shaderc/libshaderc/libshaderc_shared.dll').is_file():
            raise ValueError('The libraries the game is built with are not ready; Set Up Game prepares them. '
                             'Use Set Up Game: it carries on from where an earlier one stopped.')
        run_command(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                     str(settings.root / 'tools/build_windows_runtime.ps1'), '-ToolsRoot', str(tools)], settings)
    elif action == 'launcher':
        import self_update
        exe = self_update.running_exe()
        if not exe: raise ValueError('Only the release .exe updates itself, and this launcher was not opened from one.')
        self_update.update(exe, cancelled)
    elif action == 'files':
        import self_update
        branch = self_update.test_branch(settings.root)
        if not self_update.running_exe() or not branch:
            raise ValueError('Only a test build\'s .exe updates its files from its branch, and this launcher is not one.')
        self_update.update_files(settings.root, branch, cancelled)
    elif action in ('install', 'update'):
        run_command(settings.installer_command(action == 'update'), settings)
    elif action in ('import', 'remove'):
        from setup_game import ensure_importer
        ensure_importer(settings, run_command)
        command = settings.import_command(names, action == 'remove', outfits)
        if action == 'import':
            from ttt2char.characters import definition, game_of
            selected = [definition(name) for name in names]
            t8_fighters = [d for d in selected if game_of(d) == 'tekken8']
            if t8_fighters:
                from ttt2char.tekken8 import autodump as t8
                game = t8.find_tekken8()
                ids = [d.TEKKEN8_ID for d in t8_fighters]
                t8.dump(ids, references=[fid for fid in t8.ROSTER if fid not in ids])
                version = t8.game_version(game.game, game.library)
                for d in t8_fighters:
                    if not t8.whole(t8.saved_files(d.TEKKEN8_CODE, t8.MOVESETS, version)):
                        raise RuntimeError(d.NAME + ' extraction is incomplete; existing packs were not changed.')
        import runpy
        sys.argv = command[2:]
        runpy.run_path(command[2], run_name='__main__')
    else: raise ValueError('Unknown task: ' + action)
    import self_update
    if action in ('setup', 'build', 'upgrade'):
        (settings.build / 'ttt2-launcher-version.txt').write_text(self_update.files_id(settings.root) + '\n',
                                                                 encoding='utf-8')
    if action in ('setup', 'install', 'update', 'upgrade') and built_by(settings):
        (settings.build / 'ttt2-installed-version.txt').write_text(built_by(settings) + '\n', encoding='utf-8')
