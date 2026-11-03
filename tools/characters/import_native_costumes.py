"""Import Tekken 7 preset costumes onto their native Tag 2 fighters."""
import argparse
import sys

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    from ttt2char import InputError, native_costumes, pack, signals
    from ttt2char.native_profiles import PROFILES, profile
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('presets', nargs='*')
    parser.add_argument('--game', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--tekken7')
    parser.add_argument('--fighter', default='pau')
    parser.add_argument('--all', action='store_true', help='All presets for the selected fighter')
    parser.add_argument('--all-roster', action='store_true', help='All supported native fighters and presets')
    parser.add_argument('--remove', action='store_true')
    parser.add_argument('--cached', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    signals.stop_on_signals()
    try:
        out = pack.output_folder(args.out)
        selected = profile(args.fighter)
        if args.remove:
            if args.all_roster: raise InputError('Remove presets one fighter at a time.')
            native_costumes.remove(out, args.fighter)
            print('@done', flush=True)
            return 0
        tekken7 = args.tekken7
        if not tekken7:
            from ttt2char.tekken7 import autodump
            tekken7 = autodump.find_tekken7().game
        failed = []
        for fighter in PROFILES if args.all_roster else [selected]:
            names = fighter['presets'] if args.all or args.all_roster else args.presets
            try:
                native_costumes.build(args.game, tekken7, out, names,
                    log=lambda message: print(message, flush=True), cached=args.cached, fighter=fighter['code'])
            except (InputError, OSError, ValueError, KeyError, NotImplementedError) as error:
                if not args.all_roster: raise
                failed.append(fighter['name'] + ': ' + str(error))
                print('Skipped ' + failed[-1], flush=True)
        if failed:
            raise InputError('Some fighters were not updated; completed imports are kept. ' + '; '.join(failed))
        print('@done', flush=True)
        return 0
    except (InputError, OSError, ValueError, KeyError, NotImplementedError) as error:
        print('@error ' + str(error), flush=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())
