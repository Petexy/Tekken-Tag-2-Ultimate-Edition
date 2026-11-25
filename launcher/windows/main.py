"""Windows Golden Fist Launcher's Python side. With --worker one of the launcher's tasks, which it runs as a program of
its own; with --query one of its questions (query.py: one JSON answer); else (the project ZIP's Start Golden Fist
Launcher.cmd, old test builds' .exe) the native launcher built from these files and started (build_launcher.py)."""
from pathlib import Path
import argparse
import sys
import threading
import traceback

from backend import Settings, worker
import query
import self_update


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--worker', choices=('setup', 'build', 'install', 'update', 'upgrade', 'import', 'remove',
                                                 'launcher', 'files', 'shaders'))
    parser.add_argument('--cancel-file', type=Path)
    parser.add_argument('--ui-smoke-test', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--outfits', default='none')     # (an import: whose outfits, as import_character.py)
    parser.add_argument('--query', choices=query.NAMES)
    parser.add_argument('--action', choices=query.ACTIONS) # (--query check: before which task)
    parser.add_argument('fighters', nargs='*')
    args = parser.parse_args()
    settings = Settings(args.build_dir, args.config)
    if args.query: return query.main(args.query, settings, args.fighters, args.action)
    if args.worker:
        cancelled = lambda: bool(args.cancel_file and args.cancel_file.exists())
        # (The launcher's update stops only where it can: never half-way through replacing the .exe or its files.)
        if args.cancel_file and args.worker not in ('launcher', 'files'):
            def watch_cancel():
                import _thread
                while not args.cancel_file.exists():
                    threading.Event().wait(.2)
                _thread.interrupt_main()
            threading.Thread(target=watch_cancel, daemon=True).start()
        try:
            worker(settings, args.worker, args.fighters, cancelled, args.outfits)
        except KeyboardInterrupt:
            print('Cancelled. Completed extraction data is kept.', flush=True)
            return 130
        except self_update.Cancelled:
            print('Update cancelled. The launcher is as it was.', flush=True)
            return 130
        except self_update.UpdateError as error:
            print('@error ' + str(error), flush=True)
            return 1
        return 0
    import build_launcher
    return build_launcher.main(args, settings)

if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception:
        text = traceback.format_exc()
        folder = Path(__file__).resolve().parents[2] / 'local'
        folder.mkdir(exist_ok=True)
        with (folder / 'windows-launcher-errors.log').open('a', encoding='utf-8') as log: log.write(text)
        if sys.stderr: sys.stderr.write(text)
        if sys.platform == 'win32' and not sys.stderr:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, 'The launcher could not start. See local/windows-launcher-errors.log.', 'Golden Fist Launcher', 16)
        raise SystemExit(1)
