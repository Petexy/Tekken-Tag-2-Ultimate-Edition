#!/usr/bin/env python3
"""Adds a fighter from your own copy of Tekken 7 or Tekken 8 (PC) to Tekken Tag Tournament 2 (this repository's port).

Everything the fighter is made of is read from your files when you run this: your Tekken 7 installation (found
through Steam), its movesets, or your Tekken 8 installation (found through Steam, or --tekken8), and your installed
Tekken Tag Tournament 2. The result is a character pack in ~/.local/share/ttt2/characters/<code>/ (or
$XDG_DATA_HOME/ttt2/characters/), which the game loads at start-up. The pack holds Namco's assets: keep it for
yourself, never upload or share it.

    python3 tools/characters/import_character.py kazumi --game ~/Games/TekkenTag2
    python3 tools/characters/import_character.py reina --tekken8 ~/.steam/steam/steamapps/common/'TEKKEN 8' \\
        --game ~/Games/TekkenTag2
    python3 tools/characters/import_character.py --all --game ~/Games/TekkenTag2
    python3 tools/characters/import_character.py --remove kazumi --game ~/Games/TekkenTag2

A Tekken 8 fighter (Reina) needs no Tekken 7. Her moveset Tekken 8 only has while it runs: when it is not saved yet,
it is saved first (tekken8/autodump.py: Tekken 8 runs in the background, no window, no sound; Steam must be running),
with the other Tekken 8 fighters' movesets the conversion compares it with; when it cannot be (no Steam, a game
update the helper does not know yet), she is imported all the same, fighting with TTT2's own Heihachi moveset (a
warning says so, and her pack: add her again later for her own; the launcher offers it as an update). What the packs
share is made again from every added fighter's own game, so with Tekken 7 fighters added too, Tekken 7 is read for
them then (and Tekken 8 for Tekken 8 fighters when a Tekken 7 one is added): when a game the fighters added need is
gone (uninstalled since), nothing is changed and the error says which fighters need it (removing all of them at
once needs only the other game).
--all adds every Tekken 7 fighter, and the Tekken 8 ones when Tekken 8 is there (with Tekken 8 alone there, its
fighters: the Tekken 7 ones are skipped, as the Tekken 8 ones are without it).

A moveset Tekken 7 only has while it runs: the ones not saved yet are saved first (dump_tekken7.py: Tekken 7 runs in
the background, no window, no sound; Steam must be running), and so are the files Tekken 7 keeps encrypted (Geese's
and Noctis's), as the game reads them. Fighters whose DLC your account does not own are skipped.
Movesets saved from your own Tekken 7 with TKMovesets2 work too (--movesets); DLC fighters are imported only when your
Steam account owns them.

--remove deletes fighters' packs again. The packs left keep their places (their files are made for them) and what
they share is made again for them, from both games' files (not when only packs the game does not load go, which it
never held); the next fighter imported takes the first free place. A pack an older importer made (launcher.py status
"outdated") is not loaded by the game: adding its fighter again replaces it whole, in its place. A newer importer's
pack is not replaced.

--progress adds lines for the launcher (launcher/app), one each, flushed, among the others:
    @step dump <text>              saving what only the running Tekken 7 has (hidden in the background)
    @step fighter <name> <i> <n>   importing fighter i of n
    @step shared                   making what the packs share
    @added <name>                  that fighter's pack is complete
    @stand-in <name> <reason>      (a Tekken 8 fighter, after @added) it fights with its stand-in's moveset: why its
                                   own could not be saved
    @removed <name>                (--remove) that fighter's pack is gone
    @skipped <name> <reason>
    @error <text>                  why it failed (the exit code is not 0)
    @done

SIGTERM (the launcher's Cancel) and SIGHUP stop it as Ctrl+C does: Tekken 7 running hidden is closed again (a
Tekken 7 you started yourself is left alone), and the pack being written is not left half written (a fighter added
before keeps its pack as it was); the exit code is then 128 + the signal's number.

Needs Python 3 with numpy and Pillow (--remove only when what the packs left share is made again).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


class Progress:
    """The --progress lines (the launcher reads them), and the end of a run that failed."""

    def __init__(self, on):
        self.on = on
        if on and hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(line_buffering=True)    # (the log lines between them come as they are made)

    def __call__(self, *words):
        if self.on:
            print('@' + ' '.join(str(w) for w in words).replace('\n', ' '), flush=True)

    def fail(self, text):
        self('error', text)
        sys.exit('import_character: %s' % text)


def missing_packages():
    """The Python packages converting needs that this Python lacks, by their pip names."""
    missing = []
    for module in ('numpy', 'PIL'):
        try:
            __import__(module)
        except ImportError:
            missing.append({'PIL': 'Pillow'}.get(module, module))
    return missing


def needs_packages(progress):
    missing = missing_packages()
    if missing:
        progress.fail('needs the Python packages %s (e.g. pip install %s, or your distribution\'s python-numpy / '
                      'python-pillow)' % (', '.join(missing), ' '.join(missing)))


def main():
    sys.path.insert(0, HERE)
    from ttt2char import InputError, signals
    from ttt2char.characters import CHARACTERS, definition, game_of
    signals.stop_on_signals()
    parser = argparse.ArgumentParser(
        description='Add a fighter from your own Tekken 7 or Tekken 8 (PC) to Tekken Tag Tournament 2.',
        epilog='The pack holds Namco\'s assets: it is for your own use; never upload or share it.')
    parser.add_argument('fighter', nargs='*', help='who to add (one or more): %s (Tekken 8: %s)' % (
        ', '.join(f for f in CHARACTERS if game_of(definition(f)) == 'tekken7'),
        ', '.join(f for f in CHARACTERS if game_of(definition(f)) == 'tekken8')))
    parser.add_argument('--all', action='store_true', help='every fighter above that your Tekken 7 has (and your '
                        'Tekken 8, when it is there)')
    parser.add_argument('--tekken7', metavar='FOLDER',
                        help='your Tekken 7 PC installation (the folder holding TekkenGame/; default: found through Steam)')
    parser.add_argument('--tekken8', metavar='FOLDER',
                        help='your Tekken 8 PC installation (the \'TEKKEN 8\' folder holding Polaris/; default: found '
                             'through Steam)')
    parser.add_argument('--movesets', metavar='FOLDER',
                        help='the folder with the .tkmvst movesets saved from your own Tekken 7 (default: %s, filled as '
                             'needed)' % '~/.local/share/ttt2/tekken7/movesets')
    parser.add_argument('--tekken8-movesets', metavar='FOLDER',
                        help='the folder with the movesets saved from your own Tekken 8 (default: %s, filled as '
                             'needed)' % '~/.local/share/ttt2/tekken8/movesets')
    parser.add_argument('--files', metavar='FOLDER',
                        help='the folder with the files Tekken 7 keeps encrypted (Geese\'s, Noctis\'s), as the game reads '
                             'them (default: %s, filled as needed)' % '~/.local/share/ttt2/tekken7/files')
    parser.add_argument('--game', required=True, metavar='FOLDER',
                        help='your installed Tekken Tag Tournament 2 (the folder ttt2 --install made)')
    parser.add_argument('--out', metavar='FOLDER',
                        help='where character packs go (default: $TTT2_CHARACTERS, else '
                             '$XDG_DATA_HOME/ttt2/characters, else ~/.local/share/ttt2/characters)')
    parser.add_argument('--no-shared', action='store_true',
                        help='leave what the packs share (shared/) as it is: for a fighter whose pictures, 2P colours '
                             'and name call have not changed (it is made all the same for a fighter that was not in '
                             'it: new, or its pack an older importer\'s)')
    parser.add_argument('--remove', action='store_true',
                        help='remove the fighters\' packs instead (with --all: every added fighter); the packs left '
                             'keep their places and what they share is made again for them')
    parser.add_argument('--progress', action='store_true',
                        help='also print progress lines for the launcher (@step, @added, @removed, @skipped, @error, '
                             '@done)')
    args = parser.parse_args()
    progress = Progress(args.progress)
    fighters = everyone(args) if args.all else list(dict.fromkeys(f.lower() for f in args.fighter))
    if not fighters:
        parser.error('name the fighters to %s, or --all' % ('remove' if args.remove else 'add'))
    for fighter in fighters:
        try:
            definition(fighter)
        except InputError as error:
            progress.fail(str(error))
    if not args.remove:
        needs_packages(progress)
    try:
        (remove if args.remove else add)(args, fighters, progress)
    except Exception as error:              # (a bug: the launcher shows what it was; the traceback follows)
        progress('error', 'the importer failed: %s: %s' % (type(error).__name__, error))
        raise
    progress('done')


def everyone(args):
    """--all: every fighter (to add: the Tekken 8 ones only when Tekken 8 is there, given or found through Steam)."""
    from ttt2char import source
    from ttt2char.characters import CHARACTERS, definition, game_of
    if args.remove or args.tekken8 or source.find_tekken8():
        return list(CHARACTERS)
    return [f for f in CHARACTERS if game_of(definition(f)) != 'tekken8']


def add(args, fighters, progress):
    from ttt2char import InputError, importer
    from ttt2char import pack
    from ttt2char.characters import game_of
    from ttt2char.tekken7 import autodump
    from ttt2char.tekken7.pak import Paks
    tekken8_fighters = [f for f in fighters if game_of(importer.definition(f)) == 'tekken8']
    fighters = [f for f in fighters if f not in tekken8_fighters]          # (Tekken 7's first; Tekken 8's below)
    tekken7 = os.path.expanduser(args.tekken7) if args.tekken7 else None
    if fighters and tekken7 is None:
        try:
            # (its files are all the import reads; the dump finds Proton and the prefix itself, if it is needed)
            tekken7 = autodump.tekken7_library()[2]
        except autodump.DumpError as error:
            if not tekken8_fighters:                    # (only Tekken 7 fighters asked for)
                progress.fail('%s (or give --tekken7)' % error)
            # with Tekken 8 fighters asked for too (--all with only Tekken 8 there), those are added all the same
            for fighter in fighters:
                print('Skipped %s: %s (or give --tekken7)' % (fighter, error))
                progress('skipped', fighter, 'Tekken 7 is not installed')
            fighters = []
    tekken8 = os.path.expanduser(args.tekken8) if args.tekken8 else None
    if tekken8_fighters:
        try:
            tekken8 = importer.tekken8_folder(tekken8)
        except InputError as error:
            if tekken8 or not fighters:                 # (a folder given, or only Tekken 8 fighters asked for)
                progress.fail(str(error))
            # with Tekken 7 fighters asked for too (the launcher's "add all"), those are added all the same
            for fighter in tekken8_fighters:
                print('Skipped %s: %s' % (fighter, error))
                progress('skipped', fighter, 'Tekken 8 is not installed')
            tekken8_fighters = []
    movesets = os.path.expanduser(args.movesets or autodump.MOVESETS)
    files_folder = os.path.expanduser(args.files) if args.files else autodump.FILES
    game = os.path.expanduser(args.game)
    out = args.out and os.path.expanduser(args.out)
    try:
        folder = pack.output_folder(out)
    except InputError as error:
        progress.fail(str(error))
    # the fighters shared/ has no pictures of (it holds the packs the game loads): a new one, or an outdated pack's
    pack.recover(folder)
    shown = {p['code'] for _, p in pack.loaded(pack.installed(folder))}
    if not args.no_shared or any(importer.definition(f).CODE not in shown for f in fighters + tekken8_fighters):
        # what the packs share is made again after the fighters, from the game of every pack there: one that is gone
        # (Tekken 7 uninstalled since its fighters were added) fails now, before anything is saved or written, so
        # that the packs are never left with what they shared before, without the fighters added now
        tekken7, tekken8 = shared_games(folder, tekken7, tekken8, progress)
    if fighters:
        fighters = tekken7_ready(fighters, tekken7, movesets, files_folder, progress, alone=not tekken8_fighters)
    movesets8 = None
    unsaved8 = {}
    if tekken8_fighters:
        movesets8 = os.path.expanduser(args.tekken8_movesets) if args.tekken8_movesets else None
        unsaved8 = tekken8_ready(tekken8_fighters, movesets8, progress)
    fighters += tekken8_fighters
    unshared = [f for f in fighters if importer.definition(f).CODE not in shown]
    for n, fighter in enumerate(fighters):
        progress('step', 'fighter', fighter, n + 1, len(fighters))
        try:
            # what the packs share is made once, after the last fighter
            if fighter in tekken8_fighters:
                target = importer.run(fighter, None, movesets8, game, out, make_shared=False, tekken8=tekken8)
            else:
                target = importer.run(fighter, tekken7, movesets, game, out, make_shared=False, files=files_folder)
        except InputError as error:
            progress.fail(str(error))
        slot = int(pack.read_ini(os.path.join(target, 'character.ini')).get('slot', '0'))
        cell = pack.place(slot)
        rows = ('top', 'middle', 'bottom')
        where = ('a cell at the %s end of the select screen\'s %s row' % ('left' if cell['column'] < 10 else 'right',
                                                                         rows[cell['grid_row']])
                 if cell['column'] is not None else 'no cell (the select screen is full)')
        print('Done: %s has %s.' % (fighter, where))
        progress('added', fighter)
        if fighter in tekken8_fighters and pack.read_ini(os.path.join(target, 'character.ini')).get('stand_in'):
            progress('stand-in', fighter, unsaved8.get(fighter, 'its own moveset could not be saved from Tekken 8'))
    if args.no_shared and unshared:
        print('What the packs share is made again all the same: %s had no pictures, colours or name call in it.'
              % ', '.join(importer.definition(f).NAME for f in unshared))
    if not args.no_shared or unshared:
        progress('step', 'shared')
        tekken7, tekken8 = shared_games(folder, tekken7, tekken8, progress)
        try:
            importer.make_shared(tekken7, game, out, files=files_folder, tekken8=tekken8)
        except InputError as error:
            progress.fail(str(error))
    print('Start the game. The packs (in %s) hold Namco\'s assets: keep them for yourself.' % os.path.dirname(target))


def shared_games(folder, tekken7, tekken8, progress):
    """(tekken7, tekken8): the installations what the packs in `folder` share is made from, for the games of the
    fighters whose packs it is made for (the ones the game loads): the ones given, else found through Steam. Fails,
    naming the fighters that need it, when a game they need is not there (or its files are not)."""
    from ttt2char import InputError, importer, pack, source
    from ttt2char.characters import CHARACTERS, GAMES, definition, game_of
    from ttt2char.tekken7 import autodump
    known = {definition(f).CODE: definition(f) for f in CHARACTERS}
    needing = {}                        # {game: [the names of its fighters there]}
    for _, p in pack.loaded(pack.installed(folder)):
        if p['code'] in known:
            needing.setdefault(game_of(known[p['code']]), []).append(known[p['code']].NAME.split(' (')[0])
    why = None
    if 'tekken7' in needing:
        try:
            if tekken7 is None:
                tekken7 = autodump.tekken7_library()[2]
            importer.tekken7_paks(tekken7)
        except autodump.DumpError as error:
            why = 'tekken7', str(error)
        except InputError:
            why = 'tekken7', 'Tekken 7 has no pak files in %s' % tekken7
    if 'tekken8' in needing and why is None:
        try:
            tekken8 = importer.tekken8_folder(tekken8)
        except InputError as error:
            why = 'tekken8', 'Tekken 8 is not installed in any Steam library' if tekken8 is None and \
                source.find_tekken8() is None else str(error)
    if why is not None:
        game, reason = why
        names = needing[game]
        progress.fail('%s, and the %s fighters added (%s) need it: what all added fighters share is made again from '
                      'each one\'s own game when one is added. Nothing was changed: install %s again (or give --%s), '
                      'or remove %s first' % (reason, GAMES[game], ', '.join(names), GAMES[game], game,
                                              'that fighter' if len(names) == 1 else 'those fighters (all at once)'))
    return tekken7, tekken8


def tekken7_ready(fighters, tekken7, movesets, files_folder, progress, alone=True):
    """The Tekken 7 fighters that can be imported: owned (DLC fighters: as Steam tells), their movesets and
    encrypted files saved (Tekken 7 runs hidden for those not saved yet). alone: no other fighter is imported (none of
    them left fails)."""
    from ttt2char import InputError, importer
    from ttt2char.tekken7 import autodump
    from ttt2char.tekken7.pak import Paks
    # only fighters the player owns, whichever movesets are already saved (DLC fighters: as Steam tells)
    ids = [importer.definition(f).TEKKEN7_ID for f in fighters]
    if any(fid in autodump.DLC for fid in ids):
        progress('step', 'dump', 'Asking Steam which DLC you own (a helper runs in the background)')
    try:
        skipped = autodump.unowned(ids)
    except autodump.DumpError as error:
        progress.fail(str(error))
    for fighter in list(fighters):
        d = importer.definition(fighter)
        if d.TEKKEN7_ID in skipped:
            print('Skipped %s: %s.' % (d.NAME, skipped[d.TEKKEN7_ID]))
            progress('skipped', fighter, skipped[d.TEKKEN7_ID])
            fighters.remove(fighter)
    if not fighters:
        if not alone:
            return []
        progress.fail('none of the fighters asked for is owned')
    # the movesets and encrypted files not saved yet: Tekken 7 in the background, once for all of them
    try:
        paks = Paks(importer.tekken7_paks(tekken7), saved=files_folder)
    except InputError as error:
        progress.fail(str(error))
    have = importer.saved_movesets(movesets)
    needed, files = {}, {}
    for fighter in fighters:
        d = importer.definition(fighter)
        if d.TEKKEN7_ID not in have:
            needed[d.TEKKEN7_ID] = (d.TEKKEN7_CODE, d.NAME)
        entries = autodump.unsaved_files(paks, d.TEKKEN7_CODE)
        if entries:
            files[d.TEKKEN7_ID] = (d.NAME, entries)
    if importer.HEIHACHI not in have:                       # (every import needs his)
        needed[importer.HEIHACHI] = ('hei', 'Heihachi')
    if needed or files:
        print('Saving %d Tekken 7 moveset(s) and %d fighter(s)\' encrypted files first (Tekken 7 runs hidden in the '
              'background for a minute or two) ...' % (len(needed), len(files)))
        progress('step', 'dump', 'Saving what Tekken 7 has only while it runs (it runs hidden in the background for a '
                 'minute or two)')
        try:
            _, skipped = autodump.dump(needed, movesets, files=files, paks=paks)
        except autodump.DumpError as error:
            progress.fail(str(error))
        who = {fid: name for fid, (_, name) in needed.items()}
        who.update((fid, name) for fid, (name, _) in files.items())
        for fid, why in skipped.items():
            print('Skipped %s: %s.' % (who.get(fid, 'Heihachi'), why))
        have = importer.saved_movesets(movesets)
        saved = [f for f in fighters if importer.definition(f).TEKKEN7_ID in have and
                 not autodump.unsaved_files(paks, importer.definition(f).TEKKEN7_CODE)]
        for fighter in fighters:
            if fighter not in saved:
                progress('skipped', fighter, skipped.get(importer.definition(fighter).TEKKEN7_ID,
                                                         'it could not be saved from Tekken 7'))
        fighters = saved
        if importer.HEIHACHI not in have:
            progress.fail('Heihachi\'s moveset could not be saved')
        if not fighters and alone:
            progress.fail('none of the fighters asked for could be saved from Tekken 7')
    return fighters


def tekken8_ready(fighters, movesets, progress):
    """Saves the Tekken 8 fighters' movesets not saved yet for this version of the game, whole (MOVESET_SOURCE
    'tekken8'; a reference's motbin alone is none; Tekken 8 runs hidden, once for all of them, with every other
    fighter's moveset alone as references: what the id maps compare with), into `movesets` (None:
    tekken8/autodump.py's MOVESETS). Nothing is started for a build of the game the helper does not know. A fighter
    whose moveset cannot be saved is imported all the same: with a moveset saved before (another version's: a dump
    that fails leaves it), else with its stand-in (importer.run warns, and its pack says so: the launcher offers to
    update it once its own moveset can be had). -> {fighter: why its moveset was not saved now} (for --progress)."""
    from ttt2char import importer
    from ttt2char.tekken8 import autodump as dump8
    wanted = [f for f in fighters if importer.converts_tekken8(importer.definition(f))]
    if not wanted:
        return {}
    try:
        t8 = dump8.find_tekken8()
        version = dump8.game_version(t8.game, t8.library)
    except dump8.DumpError as error:
        print('Tekken 8 cannot run to save movesets (%s): the ones saved before are used' % error)
        return dict.fromkeys(wanted, str(error))
    # (a reference's motbin alone, as another Tekken 8 fighter's import saves the others, is no moveset saved)
    missing = [f for f in wanted
               if not dump8.whole(dump8.saved_files(importer.definition(f).TEKKEN8_CODE, movesets, version))]
    if not missing:
        return {}
    if not dump8.known_build(t8.game):              # (the helper would refuse it: nothing is started)
        why = dump8.UNKNOWN_BUILD % (version['build'] or 'unknown')
        print('Tekken 8 cannot run to save movesets (%s): the ones saved before are used' % why)
        return dict.fromkeys(missing, why)
    ids = [importer.definition(f).TEKKEN8_ID for f in missing]
    print('Saving %d Tekken 8 moveset(s) first (Tekken 8 runs hidden in the background for a minute) ...'
          % len(missing))
    progress('step', 'dump', 'Saving what Tekken 8 has only while it runs (it runs hidden in the background for a '
             'minute)')
    try:
        _, skipped = dump8.dump(ids, movesets, references=[fid for fid in dump8.ROSTER if fid not in ids])
    except dump8.DumpError as error:
        print('Tekken 8\'s movesets could not be saved (%s): the ones saved before are used' % error)
        return dict.fromkeys(missing, str(error))
    unsaved = {}
    for f in missing:
        d = importer.definition(f)
        if d.TEKKEN8_ID in skipped:
            print('%s\'s Tekken 8 moveset could not be saved: %s' % (d.NAME, skipped[d.TEKKEN8_ID]))
            unsaved[f] = skipped[d.TEKKEN8_ID]
    return unsaved


def remove(args, fighters, progress):
    from ttt2char import InputError, pack              # (no numpy until what the packs left share is made again)
    from ttt2char.characters import CHARACTERS, definition, game_of
    from ttt2char.tekken7 import autodump
    try:
        out = pack.output_folder(args.out and os.path.expanduser(args.out))
    except InputError as error:
        progress.fail(str(error))
    game = os.path.expanduser(args.game)
    files_folder = os.path.expanduser(args.files) if args.files else autodump.FILES
    pack.recover(out)
    packs = {}
    for p in pack.installed(out):
        packs.setdefault(p['code'], []).append(p['path'])
    current = {p['code'] for _, p in pack.loaded(pack.installed(out))}         # (shared/ holds these)
    going = []
    for fighter in fighters:
        d = definition(fighter)
        if d.CODE in packs:
            going.append(fighter)
        elif not args.all:
            print('Skipped %s: it is not added (no pack of %s in %s).' % (d.NAME, d.CODE, out))
            progress('skipped', fighter, 'it is not added')
    if not going:
        print('No pack to remove in %s.' % out)
        return
    known = {definition(f).CODE: definition(f) for f in CHARACTERS}
    gone = {definition(f).CODE for f in going}
    left = [code for code in packs if code in known and code in current and code not in gone]   # (shared/'s)
    # shared/ changes only when a fighter it holds goes (an outdated pack's never was in it), or none is left
    remake = bool(left) and bool(gone & current & set(known)) and not args.no_shared
    tekken7 = tekken8 = importer = None
    if remake:
        # what the packs left share is made again from both games' files (each fighter's own game: Tekken 7's paks,
        # not its Proton; Tekken 8's store): they must be there, and what converts them, before a pack goes
        needs_packages(progress)
        from ttt2char import importer
        games = {game_of(known[code]) for code in left}
        why = None
        try:
            if 'tekken7' in games:
                tekken7 = os.path.expanduser(args.tekken7) if args.tekken7 else autodump.tekken7_library()[2]
                importer.tekken7_paks(tekken7)
            if 'tekken8' in games:
                tekken8 = importer.tekken8_folder(args.tekken8 and os.path.expanduser(args.tekken8))
            importer.ttt2_folder(game)
        except autodump.DumpError as error:
            why = '%s (or give --tekken7)' % error
        except InputError as error:
            why = str(error)
        if why:
            progress.fail('%s; the fighters left need both games\' files for what they share, so nothing was removed'
                          % why)
    changed = False
    try:
        for fighter in going:
            for path in packs[definition(fighter).CODE]:
                changed = True
                try:
                    pack.remove(path)
                except OSError as error:
                    progress.fail('cannot remove %s: %s' % (path, error))
                print('Removed %s (%s).' % (definition(fighter).NAME, path))
            progress('removed', fighter)
        if args.no_shared or (left and not remake):
            return
        progress('step', 'shared')
        try:
            if left:
                importer.make_shared(tekken7, game, out, files=files_folder, tekken8=tekken8)
            else:
                pack.remove_shared(out)
                print('No added fighter is left: removed %s.' % os.path.join(out, pack.SHARED))
        except (InputError, OSError) as error:
            progress.fail('%s; the fighters left are without what they share until a fighter is imported again'
                          % error)
    except BaseException:
        # stopped (a failure, the launcher's Cancel) before what the packs share was made again: what it held would
        # show the removed fighters
        if changed and (remake or not left) and not args.no_shared:
            try:
                pack.remove_shared(out)
            except OSError:
                pass
        raise


if __name__ == '__main__':
    main()
