"""First-run Windows setup, using this extracted project and the player's RPX.

All downloaded tools stay private under local/. No second source checkout,
admin installation, system PATH change, game download, or Linux launcher change.
"""
from pathlib import Path
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(asset, cache):
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.is_file() and digest(cache) == asset['sha256']:
        return cache
    part = cache.with_suffix(cache.suffix + '.part')
    print('Downloading ' + asset['url'].rsplit('/', 1)[-1], flush=True)
    with urllib.request.urlopen(asset['url'], timeout=120) as response, part.open('wb') as output:
        shutil.copyfileobj(response, output, 1024 * 1024)
    if digest(part) != asset['sha256']:
        raise ValueError('Download checksum mismatch: ' + cache.name)
    part.replace(cache)
    return cache


def unzip(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as reader:
        for item in reader.infolist():
            path = (target / item.filename).resolve()
            if not path.is_relative_to(target.resolve()) or ':' in item.filename or '\\' in item.filename:
                raise ValueError('Unsafe downloaded archive path: ' + item.filename)
        reader.extractall(target)


def manifest(settings):
    return json.loads((settings.root / 'tools/windows-bootstrap.lock.json').read_text(encoding='utf-8-sig'))


def powershell(script, *args):
    return ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), *map(str,args)]


def tools_folder(settings):
    return Path(settings.values['tools'] or settings.root / 'local/windows-tools').resolve()


def ensure_compiler(settings, lock, tools):
    compiler = tools / lock['compiler']['folder'] / 'bin/clang.exe'
    if not compiler.is_file():
        print('@step tools Getting the C compiler', flush=True)
        unzip(download(lock['compiler'], settings.root / 'local/windows-downloads/llvm-mingw.zip'), tools)
    return compiler


IMPORTER_PACKAGES = ('numpy', 'Pillow')

def importer_ready(settings):
    """numpy and Pillow import, as the importer finds them (the build tools' python folder)."""
    probe = subprocess.run([sys.executable, '-c', 'import numpy, PIL.Image'], cwd=settings.root,
                           env=settings.environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return probe.returncode == 0


def ensure_importer(settings, run):
    """What adding or removing characters needs of Set Up Game's tools, got when missing: the C compiler (the
    games' helpers), numpy and Pillow. A launcher whose own folder did not set up the game has none of them, though
    the game and its characters are there (the release .exe after Set Up Game in the project ZIP)."""
    lock = manifest(settings)
    tools = tools_folder(settings)
    ensure_compiler(settings, lock, tools)
    if not importer_ready(settings):
        print('@step tools Getting numpy and Pillow', flush=True)
        pins = [p for p in lock['packages'] if p.split('==')[0] in IMPORTER_PACKAGES]
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:',
             '--upgrade', '--target', str(tools / 'python'), *pins], settings)
        importlib.invalidate_caches()           # (this process imports them next: its path had no such folder)
    os.environ.update(settings.environment())   # (TTT2_HELPER_CC: the compiler now there)


def recent_git():
    """A Git on PATH that takes safe.directory from its command line (2.38 on), which tools/setup_deps.py gives it."""
    found = shutil.which('git')
    if not found: return False
    said = subprocess.run([found, '--version'], capture_output=True, text=True,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    version = re.match(r'git version (\d+)\.(\d+)', said)
    return bool(version) and (int(version[1]), int(version[2])) >= (2, 38)


def ensure_tools(settings, run):
    lock = manifest(settings)
    tools = tools_folder(settings)
    settings.values['tools'] = str(tools); settings.save()
    downloads = settings.root / 'local/windows-downloads'
    compiler = ensure_compiler(settings, lock, tools)
    git = tools / 'git/cmd/git.exe'
    if not git.is_file() and not recent_git():
        unzip(download(lock['git'], downloads / 'mingit.zip'), tools / 'git')
    if git.is_file():
        os.environ['PATH'] = str(git.parent) + os.pathsep + os.environ.get('PATH','')
    # Existing scripts use python on PATH; prefer this launcher's portable
    # interpreter, never a Store alias or a different system Python.
    os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + str(compiler.parent) + os.pathsep + os.environ.get('PATH','')
    package_dir = tools / 'python'
    stamp = package_dir / '.ttt2-packages.json'
    if not stamp.exists() or json.loads(stamp.read_text()) != lock['packages']:
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:',
             '--upgrade', '--target', str(package_dir), *lock['packages']], settings)
        stamp.write_text(json.dumps(lock['packages']), encoding='utf-8')
    ninja = package_dir / 'ninja/data/bin/ninja.exe'
    (package_dir / 'bin').mkdir(exist_ok=True)
    if not (package_dir / 'bin/ninja.exe').is_file():
        shutil.copy2(ninja, package_dir / 'bin/ninja.exe')
    os.environ.update(settings.environment())
    sys.path.insert(0, str(package_dir))
    return tools


def verified_rpx(root, expected):
    for candidate in root.rglob('Tekken.rpx'):
        if digest(candidate) == expected: return candidate
    raise ValueError('This game source does not contain the supported European Wii U update v16 executable.')


def prepare_rpx(settings, run):
    source_text = settings.values['source'] or settings.values['title']
    if (not source_text or not Path(source_text).exists()) and settings.installed():
        source_text = str(settings.installed() / 'game')   # (an update: the installed game has it too)
    if not source_text or not Path(source_text).exists():
        raise ValueError('Choose your European Wii U game archive with update v16 first.')
    source = Path(source_text)
    expected = manifest(settings)['rpx_sha256']
    destination = settings.root / 'local/windows-setup/Tekken.rpx'
    # Always check the currently selected source, even after an earlier setup.
    if source.is_dir():
        selected = verified_rpx(source, expected)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(selected, destination)
    else:
        workspace = settings.root / 'local/windows-setup'
        workspace.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='analysis-', dir=workspace) as temporary:
            run([str(settings.build / 'wua_extract.exe'), 'extract-analysis', str(source), temporary], settings)
            selected = verified_rpx(Path(temporary), expected)
            part = destination.with_suffix('.part'); shutil.copy2(selected, part); part.replace(destination)
    return destination


# Conservatively bound paths before Git/CMake can leave an incomplete checkout.
# Windows long-path support is not uniform across these independently built tools.
MAX_PROJECT_PATH = 110
MAX_TOOLS_PATH = 150

def validate_setup_paths(settings):
    def windows_length(path):
        return len(str(path).encode('utf-16-le')) // 2
    if windows_length(settings.root) > MAX_PROJECT_PATH:
        raise ValueError(
            'The extracted project folder path is too long for Windows build tools. '
            'Extract a fresh copy into a short folder such as D:/TTT2 or C:/Games/TTT2 '
            '(Start Ultimate Launcher.cmd must be directly inside that folder), then start setup again. '
            'Your game archive does not need to move. Current project: ' + str(settings.root))
    tools = settings.values.get('tools') or settings.root / 'local/windows-tools'
    if windows_length(tools) > MAX_TOOLS_PATH:
        raise ValueError('The Windows tools folder path is too long. Choose a shorter tools folder '
                         'in Paths, or use a fresh project copy in D:/TTT2. Current tools: ' + str(tools))
    # The game's installer gets its source and folder in the ANSI code page: a letter it has not is lost.
    from backend import unreadable_letters
    for what, key in (('installation folder', 'install'), ('Wii U archive', 'source')):
        if letters := unreadable_letters(settings.values.get(key) or ''):
            raise ValueError('The %s path has letters the game\'s installer cannot be given on this PC (%s). Choose one '
                             'whose path has only plain letters, such as C:/Games/TTT2. Current %s: %s'
                             % (what, letters, what, settings.values[key]))
    # CMake runs some build steps through batch files it writes in UTF-8, which cmd.exe reads in the console's
    # code page (850 on an Italian Windows): a letter such as à in the path breaks them ("path not found").
    for what, path in (('project folder', settings.root), ('Windows tools folder', tools)):
        if not str(path).isascii():
            letters = ''.join(sorted({c for c in str(path) if not c.isascii()}))
            raise ValueError('The %s path has letters the Windows build tools cannot read (%s). Extract a fresh copy '
                             'into a folder whose path has only plain letters, such as C:/TTT2 (outside OneDrive), '
                             'then start setup again; or use Ultimate_Launcher-x86_64.exe, which keeps its files in '
                             'such a folder by itself. Current %s: %s' % (what, letters, what, path))


def setup(settings, run):
    # Refuse missing inputs before downloading large developer tools.
    source = settings.values['source'] or settings.values['title']
    if not source or not Path(source).exists() or not settings.values['install']:
        raise ValueError('Choose your Wii U game source and installation folder first.')
    if settings.build != settings.root / 'build-windows-tools':
        raise ValueError('First-time setup requires the project build-windows-tools folder.')
    build_game(settings, run)
    print('@step install Installing the game', flush=True)
    # The project already has its launcher entry point. Do not require writing
    # a system/desktop shortcut to finish a portable first-time setup.
    run(settings.installer_command() + ['--no-launcher'], settings)
    print('Setup complete. You can now click Play.', flush=True)


def upgrade(settings, run):
    """The installed game built again from this launcher's files and put in its place: after the
    launcher updated itself, as the Linux launcher's Update."""
    if not settings.installed(): raise ValueError('Set up the game first.')
    if settings.build != settings.root / 'build-windows-tools':
        raise ValueError('Updating the game requires the project build-windows-tools folder.')
    build_game(settings, run)
    print('@step install Updating the installed game', flush=True)
    run(settings.installer_command(True), settings)
    print('The game is updated. You can now click Play.', flush=True)


def build_game(settings, run):
    """Everything up to the built game: the tools, the libraries, the code from the player's RPX."""
    validate_setup_paths(settings)
    print('@step tools Getting the missing Windows tools ready', flush=True)
    tools = ensure_tools(settings, run)
    print('@step dependencies Preparing graphics libraries', flush=True)
    run(powershell(settings.root / 'tools/setup_windows_runtime.ps1', '-ToolsRoot', tools), settings)
    print('@step tools Building game preparation tools', flush=True)
    run(powershell(settings.root / 'tools/build_windows_tools.ps1', '-ToolsRoot', tools), settings)
    print('@step source Checking your own Wii U game', flush=True)
    rpx = prepare_rpx(settings, run)
    generated = settings.root / 'generated/ttt2-windows'
    print('@step generate Preparing game code from your own copy', flush=True)
    run([str(settings.build / 'recomp/cafe-recomp.exe'), str(rpx), str(generated)], settings)
    print('@step build Building the Windows game', flush=True)
    run(powershell(settings.root / 'tools/build_windows_runtime.ps1', '-ToolsRoot', tools,
                   '-Rpx', rpx), settings)
