#!/usr/bin/env python3
"""answers.py OUT ROOT CASE GOLDEN: the stub python's answers (stub_tools.cpp) for a run of the Windows launcher
under Wine (run_wine.sh): OUT/<query>.json as main.py --query prints them (launcher/windows/query.py), with the
files folder ROOT as Windows names it (Z:\\...). CASE: setup (nothing installed, no folders chosen) | installed |
protocol (an answer of another launcher version's files). GOLDEN: a golden case (launcher/model/tests/golden/*/
case.json) for status and owned."""
import json
import sys
from pathlib import Path

PROTOCOL = 1


def write(out, name, answer, protocol=PROTOCOL):
    (out / (name + '.json')).write_text('Some line a module printed first\n' +
                                        json.dumps(dict(answer, protocol=protocol)) + '\n', encoding='utf-8')


def main(out, root, case, golden):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob('*.json'): old.unlink()
    w = lambda *parts: '\\'.join((root,) + parts)
    data = w('appdata', 'TTT2Ultimate')
    installed = case != 'setup'
    game = w('Games', 'Tekken Tag Tournament 2') if installed else ''
    folders = {'source': w('Downloads', 'Tekken Tag Tournament 2 [EUR] (update 16).wua') if installed else '',
               'title': '', 'install': game, 'data': data, 'packs': data + '\\characters', 'saves': data + '\\save',
               'tools': w('local', 'windows-tools')}
    defaults = dict(folders, source='', install=w('Games', 'Tekken Tag Tournament 2'))
    state = {'version': '0.9.0', 'files_id': '0.9.0', 'exe': None, 'commit': 'e82a93f677fe8fc2f5e43ff095ab6a956a5b3406',
             'branch': None, 'root': root, 'build': w('build-windows-tools'), 'config': w('local', 'windows-launcher.json'),
             'settings': folders, 'defaults': defaults, 'installed': game or None,
             'installed_by': '0.9.0 e82a93f677fe8fc2f5e43ff095ab6a956a5b3406' if installed else '',
             'icon': None, 'logs': data + '\\logs', 'latest_log': None,
             'display_file': data + '\\config\\display.ini', 'keyboard_file': data + '\\config\\keyboard.ini',
             'play': {'argv': [game + '\\TTT2 Ultimate.exe'], 'cwd': game, 'env': {}, 'log': data + '\\logs\\game-latest.log'}
             if installed else {'problem': 'source'},
             'data_problem': '', 'cannot_replace': ''}
    write(out, 'state', state, protocol=2 if case == 'protocol' else PROTOCOL)
    fixture = json.loads(Path(golden).read_text(encoding='utf-8'))
    if fixture.get('status'): write(out, 'status', fixture['status'])
    if fixture.get('owned'): write(out, 'owned', fixture['owned'])
    write(out, 'release', {'newer': None, 'none': True, 'error': ''})
    write(out, 'check', {'problem': {'code': '', 'what': '', 'letters': '', 'path': ''}})
    write(out, 'save-settings', {'settings': folders})
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:5]))
