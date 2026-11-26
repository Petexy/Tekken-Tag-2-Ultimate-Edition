"""tr() and trn() for what the launcher shows of the importer (its progress lines, launcher.py's answers):
launcher/i18n/launcher_texts.py, the launcher's catalogs in the player's language (TTT2_TEXT_LANGUAGE, set by the
launcher program), found in the source tree or installed beside the importer (share/ttt2/i18n). Without it (the
importer copied alone) the texts are English."""
import importlib.util
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    for folder in (os.path.join(_HERE, '..', '..', '..', 'launcher', 'i18n'), os.path.join(_HERE, '..', '..', 'i18n')):
        path = os.path.join(folder, 'launcher_texts.py')
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location('launcher_texts', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    return None


_texts = _load()


def _fill(text, values):
    return re.sub(r'\{([A-Za-z0-9_]+)\}', lambda m: str(values.get(m.group(1), m.group(0))), text)


def tr(key, english, **values):
    return _texts.tr(key, english, **values) if _texts else _fill(english, values)


def trn(key, n, one, other, **values):
    return _texts.trn(key, n, one, other, **values) if _texts else _fill(one if n == 1 else other, dict(values, n=n))
