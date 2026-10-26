#!/usr/bin/env python3
"""Saves Tekken 8 fighters' moveset files (what import_character.py needs from the game) without you doing anything:
Tekken 8 runs in the background, with no window and no sound, its own reader reads the fighters' files out of its
encrypted moveset archive while it sits on its start-up screens (nothing is pressed), and it is closed again. Only
fighters your Steam account owns are saved; the others are listed as skipped. Tekken 7 is not needed. What is saved
for your version of Tekken 8 already is not read again (a game update reads it again).

    python3 tools/characters/dump_tekken8.py reina
    python3 tools/characters/dump_tekken8.py reina --references kazuya,jin
    python3 tools/characters/dump_tekken8.py --motbin-only kazuya jin paul
    python3 tools/characters/dump_tekken8.py --all

Fighters are named by their names (any case, with or without spaces), their Tekken 8 codes (zbr) or roster ids (28).
--motbin-only saves only the movesets (and their protected fields' values) of the fighters named: the references the
importer's id maps take from other fighters; --references names more of those next to fighters saved whole.

Needs Steam running, Tekken 8 started once from Steam (its Proton prefix), gamescope, PulseAudio/PipeWire (pactl),
MinGW (x86_64-w64-mingw32-gcc, to build the small helper the first time) and Python 3.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(os.path.expanduser('~/.local/share'), 'ttt2', 'tekken8', 'movesets')


def roster_ids(parser, words):
    """The roster ids the words name (autodump.fighter_id), in order; an unknown one is the parser's error."""
    from ttt2char.tekken8 import autodump
    out = []
    for word in words:
        fid = autodump.fighter_id(word)
        if fid is None:
            parser.error('%r is no fighter of Tekken 8 (they are: %s)'
                         % (word, ', '.join(name for _, name in autodump.ROSTER.values())))
        out.append(fid)
    return out


def main(argv=None):
    sys.path.insert(0, HERE)
    from ttt2char import signals
    from ttt2char.tekken8 import autodump
    signals.stop_on_signals()               # (SIGTERM closes the hidden Tekken 8 as Ctrl+C does)
    parser = argparse.ArgumentParser(description='Save Tekken 8 moveset files in the background, for '
                                                 'import_character.py.')
    parser.add_argument('fighter', nargs='*', help='fighters (names, codes or roster ids); none with --all')
    parser.add_argument('--all', action='store_true', help='every fighter of Tekken 8 (the ones you own)')
    parser.add_argument('--motbin-only', action='store_true',
                        help='only their movesets and protected fields (references for the id maps)')
    parser.add_argument('--references', default='', metavar='NAMES',
                        help='more fighters (comma-separated) saved as references, next to the fighters saved whole')
    parser.add_argument('--out', default=DEFAULT_OUT, metavar='FOLDER',
                        help='where the files go (default: %(default)s)')
    parser.add_argument('--force', action='store_true', help='read the files again even when they are saved')
    args = parser.parse_args(argv)
    fighters = list(autodump.ROSTER) if args.all else roster_ids(parser, args.fighter)
    references = roster_ids(parser, [w for w in args.references.split(',') if w.strip()])
    if args.motbin_only:
        fighters, references = [], fighters + references
    if not fighters and not references:
        parser.error('name fighters, or --all')
    out = os.path.expanduser(args.out)
    try:
        saved, skipped = autodump.dump(fighters, out, references=references, force=args.force)
    except autodump.DumpError as e:
        print('error: %s' % e, file=sys.stderr)
        return 1
    print('Saved %d fighter(s) to %s.' % (len(saved), out))
    for fid, why in skipped.items():
        print('Skipped %s: %s.' % (autodump.ROSTER[fid][1] if fid in autodump.ROSTER else fid, why))
    return 0


if __name__ == '__main__':
    sys.exit(main())
