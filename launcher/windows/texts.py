"""tr() and trn() for the Windows launcher's Python (setup, updates, tasks): launcher/i18n/launcher_texts.py, the
launcher's catalogs in the player's language (TTT2_TEXT_LANGUAGE, set by the launcher program)."""
from pathlib import Path
import importlib.util

_spec = importlib.util.spec_from_file_location(
    'launcher_texts', Path(__file__).resolve().parent.parent / 'i18n' / 'launcher_texts.py')
_texts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_texts)
tr, trn = _texts.tr, _texts.trn
