#!/usr/bin/env python3
"""What the launcher (launcher/app) asks about adding fighters, answered as one JSON object on stdout:

    python3 tools/characters/launcher.py status [--game FOLDER] [--movesets FOLDER] [--tekken8-movesets FOLDER]
    python3 tools/characters/launcher.py owned
    python3 tools/characters/launcher.py main --commit SHA

status: what is there, quickly (nothing is started): this Python and whether it has numpy and Pillow (the import
needs them; this does not) and whether the launcher can get them for it ("packages": their folder, the bytes to
download, or the "error" why not: get_python_packages.py), the tools running Tekken 7 or Tekken 8 hidden needs (each
game's helper: "helper" Tekken 7's, "tekken8_helper" Tekken 8's) and the C compiler a Tekken 8 import builds two small
parts with ("cc"; "prebuilt" when the launcher names both built: native.py), Steam (its
folder, and "flatpak" or "snap" for a sandboxed one), Tekken 7 (found through Steam as the importer finds it, or why it
is not usable; "readable": its files are there, which what the packs share needs even when it cannot run), Tekken 8
(found through Steam's files; "build_known": whether it is the build the helper knows, so that a moveset not saved yet
can be saved, null when no fighter needs one; "run_error": why it cannot run hidden to save one), the characters
folder (as the game finds it) and every fighter the importer knows: its name, whether it is a DLC fighter (the DLC's
Steam app id), whether its pack is there ("installed"), whether that pack is
an older importer's ("outdated": the game does not load it; adding the fighter again replaces it) or a newer one's
("newer": the game does not load it either, and this importer does not replace it; the game needs updating), whether
the pack the game loads misses what importing the fighter now gives ("update": an older revision, pack.revision;
adding them again replaces it), whether its moveset is saved, how many preset outfits adding it can make
("outfits", 0 for none: import_character.py --outfits), whether the pack the game loads has them
("outfits_added") and whether what the packs share needs its game when it is made again, at every fighter added or
removed ("needs_game": its pack, an older version's, keeps no copy of its pictures and name call, and, when its game
cannot be read, the shared/ there has none of its pictures either). A Tekken 8 fighter has "game": "tekken8" too (it is
read from Tekken 8), its "moveset_saved" is whether its own Tekken 8 moveset is saved whole (any version's, in
--tekken8-movesets: the import uses it without Tekken 8 running; true for a fighter that converts none), and
"stand_in" whether the pack the game loads fights with its stand-in's moveset because its own could not be had when
it was imported (character.ini stand_in): "update" is true then once its own can be had (saved, or Tekken 8 is a
build the helper knows, so Steam running saves it); a Tekken 7 fighter's entry is as it always was. With --game:
whether that folder is an installed game the importer can read.

owned: which DLC fighters the player's Steam account owns, as Steam tells the game ({"owned": {name: true|false}}):
each game's helper runs hidden in that game's Proton prefix while Proton starts it and it asks (not the game): Tekken
7's for its DLC fighters, Tekken 8's for its own, each when that game is installed. A game that cannot be asked
leaves its fighters out, and "errors": {"tekken7"|"tekken8": "<why>"} says why. Steam must be running; when it is not
(or no game can be asked) the answer is {"error": "<why>"} at once (with "errors" when both games were asked). Steam
is never started. Only the answer goes to stdout: what runs meanwhile prints to stderr.
SIGTERM (the launcher's Cancel) ends the helper's session as its end does, and nothing is printed (exit code 143).

main: what this repository's main branch has that the build of commit SHA (the launcher's) lacks, as GitHub tells
it, so that a launcher learns of newer changes before a release brings them: {"ahead": how many commits, "head": main's
commit, "page": GitHub's page comparing them, "changes": the newest commits' titles, "fighters": the fighters main
gives a newer pack revision than this importer (pack.revision), "new": [{"name", "display"}] the fighters only main
has}, or {"error": "<why>"} (GitHub cannot be asked, or does not know the commit: a build of commits never pushed).
Only GitHub is asked ($TTT2_LAUNCHER_GITHUB instead, for tests); nothing is downloaded but the definitions that changed.

The exit code is 0 whenever the object is printed; adding and removing fighters is import_character.py's (--progress).
Needs only Python 3; works from a read-only copy (nothing is written next to it).
"""
import argparse
import contextlib
import json
import os
import platform
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ttt2char import native, pack, python_packages, signals, source   # noqa: E402  (these need no numpy)
from ttt2char.characters import CHARACTERS, definition, game_of  # noqa: E402
from ttt2char.tekken7 import autodump                          # noqa: E402
from ttt2char.tekken7.pak import pak_names                     # noqa: E402
from ttt2char.tekken7.tkmvst import saved_movesets             # noqa: E402
from ttt2char.tekken8 import autodump as dump8                 # noqa: E402
from ttt2char.ttt2 import title_folder                         # noqa: E402

MINGW = 'x86_64-w64-mingw32-gcc'


def importable(module):
    try:
        __import__(module)
        return True
    except Exception:                       # (ImportError, or whatever a broken installation raises)
        return False


def tekken7():
    """{found, path, error, readable}: Tekken 7 as the importer finds it (autodump.find_tekken7), or why it is not
    usable; readable: its pak files are there (all reading its fighters needs: what the packs share is made from them,
    whether Tekken 7 can run or not)."""
    try:
        path, error = autodump.find_tekken7().game, None
    except autodump.DumpError as e:
        error = str(e)
        try:
            path = autodump.tekken7_library()[2]
        except autodump.DumpError:
            path = None
    found = path is not None and os.path.isdir(path)
    readable = found and bool(pak_names(os.path.join(path, 'TekkenGame', 'Content', 'Paks')))
    if path is not None and not found:
        error = 'Steam lists Tekken 7 in %s, but it is not there: install it again from Steam' % path
    elif found and error is None and not readable:
        error = 'Tekken 7 has no pak files in %s: let Steam verify its files' % path
    return {'found': found, 'path': path, 'error': error, 'readable': readable}


def tekken8():
    """{found, path, error, run_error}: Tekken 8 as the importer finds it without --tekken8 (source.find_tekken8:
    through Steam's files), or why it is not usable; run_error: why it cannot run hidden to save movesets
    (tekken8/autodump.find_tekken8: Steam from Flatpak or Snap, no Proton prefix yet, ...), None when it can.
    (status adds build_known.)"""
    path = source.find_tekken8()
    if path is None:
        return {'found': False, 'path': None, 'error': 'Tekken 8 is not installed in any Steam library',
                'run_error': None}
    if not os.path.isdir(os.path.join(path, 'Polaris', 'Content', 'Paks')):
        return {'found': False, 'path': path,
                'error': 'Tekken 8 has no Polaris/Content/Paks in %s: verify its files in Steam' % path,
                'run_error': None}
    try:
        dump8.find_tekken8()
        run_error = None
    except dump8.DumpError as e:
        run_error = str(e)
    return {'found': True, 'path': path, 'error': None, 'run_error': run_error}


def steam():
    """{installed, running, path, sandbox}: the Steam Tekken 7 is installed through (else the first one installed);
    sandbox 'flatpak' or 'snap' for a Steam from Flathub or the Snap Store (Tekken 7 is not run through it yet:
    tekken7's error says so), else None."""
    path, sandbox = autodump.tekken7_steam()
    return {'installed': path is not None, 'running': autodump.steam_running(), 'path': path, 'sandbox': sandbox}


def status(game=None, movesets=None, movesets8=None):
    folder = os.path.abspath(pack.default_folder())
    packs = {}                      # {code: its packs' state: 'current' (one is loaded), else 'newer' or 'outdated'}
    rank = ('outdated', 'newer', 'current')
    installed = pack.installed(folder)
    loaded = {p['code']: p for _, p in pack.loaded(installed)}
    for p in installed:
        state = 'current' if p['current'] else 'newer' if p['newer'] else 'outdated'
        if rank.index(state) >= rank.index(packs.get(p['code'], 'outdated')):
            packs[p['code']] = state
    movesets = os.path.abspath(os.path.expanduser(movesets or autodump.MOVESETS))
    movesets8 = os.path.abspath(os.path.expanduser(movesets8 or dump8.MOVESETS))
    saved = saved_movesets(movesets)
    helper = 'prebuilt' if autodump.ready_helper(autodump.CACHE) else 'mingw' if shutil.which(MINGW) else None
    helper8 = 'prebuilt' if dump8.ready_helper(dump8.CACHE) else 'mingw' if shutil.which(MINGW) else None
    cc = native.compiler() or ('prebuilt' if all(map(native.prebuilt, ('decimate', 'oodle'))) else None)
    found8 = tekken8()
    found7 = tekken7()
    readable = {'tekken7': found7['readable'], 'tekken8': found8['found']}
    copyless = {d.CODE: d for d in map(definition, CHARACTERS)
                if d.CODE in loaded and not pack.carries_source(loaded[d.CODE]['path'], d)}
    # (of those, the ones whose game cannot be read keep what the shared/ there has of them, if it has them)
    held = pack.holds(folder, [code for code, d in copyless.items() if not readable[game_of(d)]])
    build_known = None              # (whether the helper knows Tekken 8's build: its exe read once, when a pack asks)
    fighters = []
    for name in CHARACTERS:
        d = definition(name)
        tekken8_fighter = game_of(d) == 'tekken8'
        fighter = {'name': name, 'display': d.NAME.split(' (')[0],
                   'dlc': dump8.DLC.get(d.TEKKEN8_ID) if tekken8_fighter else autodump.DLC.get(d.TEKKEN7_ID),
                   'installed': d.CODE in packs, 'outdated': packs.get(d.CODE) == 'outdated',
                   'newer': packs.get(d.CODE) == 'newer',
                   'update': d.CODE in loaded and loaded[d.CODE]['revision'] < pack.revision(d),
                   'moveset_saved': tekken8_fighter or d.TEKKEN7_ID in saved,
                   'outfits': len(getattr(d, 'PRESETS', ())),
                   'outfits_added': d.CODE in loaded and loaded[d.CODE]['outfits'] > 0,
                   'needs_game': d.CODE in copyless and d.CODE not in held}
        if tekken8_fighter:
            own = getattr(d, 'MOVESET_SOURCE', None) == 'tekken8'       # (importer.converts_tekken8, without numpy)
            fighter['moveset_saved'] = not own or dump8.whole(dump8.saved_files(d.TEKKEN8_CODE, movesets8))
            if own and not fighter['moveset_saved'] and build_known is None:
                build_known = found8['found'] and dump8.known_build(found8['path'])
            fighter['stand_in'] = d.CODE in loaded and loaded[d.CODE]['stand_in'] != ''
            if fighter['stand_in'] and own and not fighter['update']:
                fighter['update'] = fighter['moveset_saved'] or build_known
            fighter['game'] = 'tekken8'
        fighters.append(fighter)
    found8['build_known'] = build_known if found8['found'] else None       # (None: no fighter needs a moveset saved)
    out = {'python': {'version': platform.python_version(), 'numpy': importable('numpy'),
                      'pillow': importable('PIL.Image'), 'packages': python_packages.status()},
           'tools': {'gamescope': shutil.which('gamescope'), 'pactl': shutil.which('pactl'), 'helper': helper,
                     'tekken8_helper': helper8, 'cc': cc},
           'steam': steam(),
           'tekken7': found7,
           'tekken8': found8,
           'packs_folder': folder,
           'movesets': {'folder': movesets, 'heihachi': autodump.HEIHACHI in saved},     # (Tekken 7's imports need his)
           'fighters': fighters}
    if game is not None:
        title = title_folder(os.path.expanduser(game))
        out['game'] = {'path': title, 'error': None if title else
                       '%s is no installed Tekken Tag Tournament 2 (no content/hdd in it or its game/)' % game}
    return out


def owned():
    """Each game's DLC fighters, as Steam tells that game, for each game installed (Tekken 8's: its Miary Zo and
    Clive). A game that cannot be asked leaves its fighters out and says why in "errors"; none answering: {"error": the
    first one's why} (with "errors" when both games were asked)."""
    answer, errors = {}, {}
    for game, module, field in (('tekken7', autodump, 'TEKKEN7_ID'), ('tekken8', dump8, 'TEKKEN8_ID')):
        dlc = {getattr(definition(name), field): name for name in CHARACTERS
               if game_of(definition(name)) == game and getattr(definition(name), field) in module.DLC}
        if not dlc or not (tekken7()['found'] if game == 'tekken7' else source.find_tekken8() is not None):
            continue
        try:
            unowned = module.unowned(list(dlc))             # (Steam not running: an error at once)
        except module.DumpError as error:
            errors[game] = str(error)
            continue
        except Exception as error:          # (building or running the helper: the launcher shows why)
            errors[game] = 'the helper failed: %s: %s' % (type(error).__name__, error)
            continue
        answer.update({name: fid not in unowned for fid, name in dlc.items()})
    if not answer and errors:
        return dict({'error': next(iter(errors.values()))}, **({'errors': errors} if len(errors) > 1 else {}))
    return dict({'owned': answer}, **({'errors': errors} if errors else {}))


REPOSITORY = 'Petexy/Tekken-Tag-2-Ultimate-Edition'
DEFINITIONS = 'tools/characters/ttt2char/characters/'


def github(path):
    """A file of the repository as GitHub gives it: the API's /repos/... answers, raw files (raw/<commit>/<path>)."""
    base = os.environ.get('TTT2_LAUNCHER_GITHUB')
    if path.startswith('raw/'):
        url = (base + '/' if base else 'https://raw.githubusercontent.com/' + REPOSITORY + '/') + path[4:]
    else:
        url = (base or 'https://api.github.com') + '/repos/' + REPOSITORY + '/' + path
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'ttt2-launcher'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as error:
        with error: body = error.read().decode('utf-8', 'replace')
        try:
            message = json.loads(body).get('message', '')
        except ValueError:
            message = ''
        if 'rate limit' in message.lower():
            raise LookupError('GitHub answers only so many questions from one network an hour: try again later')
        raise LookupError(message or 'GitHub answered %d' % error.code)


def revision_in(text):
    found = re.search(r'^REVISION\s*=\s*(\d+)', text, re.M)
    return int(found.group(1)) if found else 0


def main_news(commit, branch='main'):
    try:
        try:
            compare = json.loads(github('compare/%s...%s' % (urllib.parse.quote(commit), urllib.parse.quote(branch))))
        except LookupError as error:
            if str(error) != 'Not Found': raise
            raise LookupError('GitHub does not know commit %s: this launcher was built from changes never pushed'
                              % commit)
        ahead, commits = int(compare.get('ahead_by', 0)), compare.get('commits') or []
        out = {'ahead': ahead, 'head': commits[-1]['sha'] if commits else commit, 'page': compare.get('html_url', ''),
               'changes': [c['commit']['message'].split('\n')[0] for c in reversed(commits)][:5],
               'fighters': [], 'new': []}
        if not ahead: return out
        files = {f['filename']: f.get('status', '') for f in compare.get('files') or []}
        main = lambda path: github('raw/%s/%s' % (out['head'], path))
        # A fighter's pack revision on main: pack.py's REVISION there, and its definition's there.
        shared = revision_in(main('tools/characters/ttt2char/pack.py')) if 'tools/characters/ttt2char/pack.py' in files \
            else pack.REVISION
        for name in CHARACTERS:
            d = definition(name)
            path = DEFINITIONS + os.path.basename(d.__file__)
            if files.get(path) == 'removed': continue
            own = revision_in(main(path)) if path in files else vars(d).get('REVISION', 0)
            if shared + own > pack.revision(d): out['fighters'].append(name)
        if DEFINITIONS + '__init__.py' in files:
            roster = re.search(r'^CHARACTERS\s*=\s*\(([^)]*)\)', main(DEFINITIONS + '__init__.py'), re.M)
            for name in re.findall(r"'(\w+)'", roster.group(1) if roster else ''):
                if name in CHARACTERS: continue
                shown = re.search(r'^NAME\s*=\s*[\'"](.+?)[\'"]', main(DEFINITIONS + name + '.py'), re.M)
                out['new'].append({'name': name, 'display': shown.group(1).split(' (')[0] if shown else name})
        return out
    except LookupError as error:
        return {'error': str(error)}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {'error': 'GitHub cannot be asked: %s' % (getattr(error, 'reason', None) or error)}


def main():
    parser = argparse.ArgumentParser(description='Answer the launcher\'s questions about adding fighters, as JSON.')
    commands = parser.add_subparsers(dest='command', required=True)
    asked = commands.add_parser('status', help='what is there (fast; nothing is started)')
    asked.add_argument('--game', metavar='FOLDER', help='an installed game folder to check')
    asked.add_argument('--movesets', metavar='FOLDER',
                       help='the saved movesets\' folder (default: %s)' % '~/.local/share/ttt2/tekken7/movesets')
    asked.add_argument('--tekken8-movesets', metavar='FOLDER',
                       help='the saved Tekken 8 movesets\' folder (default: %s)'
                            % '~/.local/share/ttt2/tekken8/movesets')
    commands.add_parser('owned', help='which DLC fighters the Steam account owns (Steam must be running)')
    asked = commands.add_parser('main', help='what the main branch has that the build of a commit lacks (GitHub)')
    asked.add_argument('--commit', required=True, help='the launcher\'s build commit')
    asked.add_argument('--branch', default='main', help=argparse.SUPPRESS)
    args = parser.parse_args()
    signals.stop_on_signals()               # (owned: the launcher's Cancel ends the hidden helper too)
    # (What runs meanwhile prints to stderr: the launchers read stdout whole as the answer, and the hidden helpers'
    # sessions print where their logs are.)
    with contextlib.redirect_stdout(sys.stderr):
        answer = (status(args.game, args.movesets, args.tekken8_movesets) if args.command == 'status' else
                  main_news(args.commit, args.branch) if args.command == 'main' else owned())
    print(json.dumps(answer), flush=True)


if __name__ == '__main__':
    main()
