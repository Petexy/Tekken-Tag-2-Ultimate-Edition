"""The new launcher's questions to the Windows backend: `main.py --query NAME` (ARCHITECTURE C8, U1, U2).

Each prints ONE JSON object on its last line of standard output, and the program ends with 0 whenever it printed one
(other lines may come before it; a reason for the log goes to standard error). The answers are facts only, never
sentences for the player: the launcher (launcher/model) words them, the same on Linux and Windows. Every answer has
"protocol": PROTOCOL; the launcher refuses another one (its files and this .exe are from different versions).

  state          what the window shows and how Play starts the game (launcher/model/facts.h, WindowsState)
  status         tools/characters/launcher.py status (with --game when installed), as the Linux launcher reads it
  owned          launcher.py owned (which DLC Steam says is owned)
  main           launcher.py main: what main (a test build: its branch) has beyond these files
  release        GitHub's newest release: {"newer": {...} | null, "none": bool, "error": raw}
  check          before a task: --action setup|build|install|update|upgrade|import|remove|shaders [names]:
                 {"problem": {"code": "" | code, "what", "letters", "path"}} (facts.h, SetupProblem)
  save-settings  the folders (a JSON object of settings keys on standard input) checked and saved:
                 {"settings": {...}} | {"problem": {"code": "data_name" | "relative", "what": key}}

Failures that are no answer: {"error": "<the reason, raw>"}. None of them imports tkinter.
"""
from pathlib import Path
import json
import os
import sys

import self_update
from backend import Settings, importer, installed_by, unreadable_letters

PROTOCOL = 1
NAMES = ('state', 'status', 'owned', 'main', 'release', 'check', 'save-settings')
FOLDERS = ('source', 'title', 'install', 'data', 'packs', 'saves', 'tools')
ACTIONS = ('setup', 'build', 'install', 'update', 'upgrade', 'import', 'remove', 'shaders')


def path_or_none(path):
    return str(path) if path else None


def play(settings):
    """How the game starts (C8): its program and arguments, folder, the variables it gets beyond the launcher's
    own (Settings.environment(): the data, characters and saves folders, LOCALAPPDATA for a data folder elsewhere)
    and its log; else why it cannot: "exe" (the installed game's program is missing), "source" (a development build
    without its Wii U source)."""
    try:
        argv = settings.game_command()
    except ValueError:
        return {'problem': 'exe' if settings.installed() else 'source'}
    own = os.environ
    env = {name: value for name, value in settings.environment().items() if own.get(name) != value}
    return {'argv': argv, 'cwd': str(Path(argv[0]).parent), 'env': env,
            'log': str(Path(settings.values['data']) / 'logs' / 'game-latest.log')}


def state(settings):
    exe = self_update.running_exe()
    data = Path(settings.values['data'])
    logs = data / 'logs'
    found = sorted(logs.glob('*.log'), key=lambda log: log.stat().st_mtime) if logs.is_dir() else []
    installed = settings.installed()
    icon = installed / 'icon.png' if installed else None
    return {'version': self_update.version(), 'files_id': self_update.files_id(), 'exe': path_or_none(exe),
            'commit': self_update.build_commit(), 'branch': self_update.test_branch() if exe else None,
            'root': str(settings.root), 'build': str(settings.build), 'config': str(settings.file),
            'settings': {key: str(settings.values.get(key) or '') for key in FOLDERS},
            'installed': path_or_none(installed), 'installed_by': installed_by(settings),
            'icon': str(icon) if icon and icon.is_file() else None,
            'logs': str(logs), 'latest_log': str(found[-1]) if found else None,
            'display_file': str(data / 'config' / 'display.ini'),
            'keyboard_file': str(data / 'config' / 'keyboard.ini'),
            'play': play(settings),
            'data_problem': '' if data.name == 'TTT2Ultimate' else 'name',
            'cannot_replace': self_update.cannot_replace(exe) if exe else ''}


def release():
    answer = self_update.ask()
    newer = answer.release if answer.release and self_update.newer_release(answer.release.version) else None
    return {'newer': None if not newer else {
                'version': newer.version, 'tag': newer.tag, 'page': newer.page, 'asset': newer.asset,
                'url': newer.url, 'size': newer.size, 'sha256': newer.sha256},
            'none': answer.none, 'error': answer.error}


def problem(code='', what='', letters='', path=''):
    return {'problem': {'code': code, 'what': what, 'letters': letters, 'path': str(path)}}


def check(settings, action, names):
    """What Window.start refused before a task, as a fact (the same checks: setup_game.validate_setup_paths and
    setup()'s first ones, Settings.import_command, Settings.installer_command). The game running and an older game
    are the launcher's to see (state)."""
    from setup_game import MAX_PROJECT_PATH, MAX_TOOLS_PATH
    values = settings.values
    if action == 'setup':
        tools = values.get('tools') or settings.root / 'local/windows-tools'
        length = lambda path: len(str(path).encode('utf-16-le')) // 2
        if length(settings.root) > MAX_PROJECT_PATH: return problem('project_length', path=settings.root)
        if length(tools) > MAX_TOOLS_PATH: return problem('tools_length', path=tools)
        for what, key in (('install', 'install'), ('source', 'source')):
            if letters := unreadable_letters(values.get(key) or ''):
                return problem('installer_letters', what, letters, values[key])
        for what, path in (('project', settings.root), ('tools', tools)):
            if not str(path).isascii():
                return problem('tools_letters', what, ''.join(sorted({c for c in str(path) if not c.isascii()})), path)
        source = values['source'] or values['title']
        if not source or not Path(source).exists() or not values['install']: return problem('inputs')
        if settings.build != settings.root / 'build-windows-tools': return problem('tools_folder')
    elif action in ('import', 'remove'):
        if not names: return problem('no_fighters')
        try:
            settings.title()
        except ValueError:
            return problem('title')
    elif action in ('install', 'update'):
        if not (settings.build / 'ttt2-ultimate.exe').is_file(): return problem('no_build')
        if action == 'update':
            if not settings.installed(): return problem('no_install')
        else:
            source = values['source'] or values['title']
            if not source or not Path(source).exists() or not values['install']: return problem('no_paths')
    return problem()


def save_settings(settings, text):
    given = json.loads(text) if text.strip() else {}
    if not isinstance(given, dict): raise ValueError('save-settings takes a JSON object')
    for key in FOLDERS:
        if key in given: settings.values[key] = str(given[key] or '')
    if Path(settings.values['data']).name != 'TTT2Ultimate': return problem('data_name', 'data')
    for key in ('data', 'packs', 'saves'):
        if not Path(settings.values[key]).is_absolute(): return problem('relative', key)
    settings.save()
    return {'settings': {key: str(settings.values.get(key) or '') for key in FOLDERS}}


def answer(name, settings, arguments=(), action=None, stdin=None):
    """NAME's answer as a dict, with the protocol; {"error"} when it has none."""
    try:
        if name == 'state': result = state(settings)
        elif name == 'status': result = importer(settings, 'status', timeout=300)
        elif name == 'owned': result = importer(settings, 'owned', timeout=300)
        elif name == 'main':
            commit = self_update.build_commit()
            if not commit: raise ValueError('these files are no known commit')
            branch = self_update.test_branch() if self_update.running_exe() else None
            result = importer(settings, 'main', '--commit', commit, *(('--branch', branch) if branch else ()),
                              timeout=120)
        elif name == 'release': result = release()
        elif name == 'check':
            if action not in ACTIONS: raise ValueError('check takes --action ' + '|'.join(ACTIONS))
            result = check(settings, action, list(arguments))
        elif name == 'save-settings': result = save_settings(settings, (stdin or sys.stdin).read())
        else: raise ValueError('no query ' + name)
        if not isinstance(result, dict): raise ValueError('the answer is no JSON object')
    except Exception as error:  # (said, never a traceback: the launcher logs it)
        result = {'error': self_update.reason(error) if isinstance(error, OSError) else str(error) or type(error).__name__}
    return dict(result, protocol=PROTOCOL)


def main(name, settings, arguments=(), action=None):
    # (ASCII with \u escapes: standard output's code page cannot lose a letter of a path.)
    print(json.dumps(answer(name, settings, arguments, action)), flush=True)
    return 0
