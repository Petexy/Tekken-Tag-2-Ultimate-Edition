"""Restore available native swimwear presets from your installed Wii U game."""
import argparse
import sys


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    from ttt2char import InputError, pack, signals, swimsuits
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fighters', nargs='*')
    parser.add_argument('--game', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args(argv)
    signals.stop_on_signals()
    try:
        folder = pack.output_folder(args.out)
        if args.remove:
            swimsuits.remove(folder, args.fighters or [p['code'] for p in swimsuits.PROFILES])
        else:
            swimsuits.build(args.game, folder, args.fighters, log=lambda s: print(s, flush=True))
        print('@done', flush=True)
        return 0
    except (InputError, OSError, ValueError, KeyError, StopIteration) as error:
        print('@error ' + str(error), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
