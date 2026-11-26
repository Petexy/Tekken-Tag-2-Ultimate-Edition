"""The launcher's texts in the player's language, for the Python programs it starts (the Windows setup and updates,
the importer's progress lines, launcher.py's answers): the same catalogs as the launcher program
(launcher/i18n/<code>.txt, format in launcher/core/i18n.h), the same keys, plural forms and English fallback.

    from launcher_texts import tr, trn
    print('@step tools ' + tr('worker.getting_compiler', 'Getting the C compiler'), flush=True)
    tr('worker.saved', 'Saved {name}', name='Kazumi')
    trn('worker.changes', count, '{n} change of {branch}', '{n} changes of {branch}', branch='main')

The language is TTT2_TEXT_LANGUAGE's, which the launcher sets for every program it starts (a code of LANGUAGES or
"qps", the pseudo language); none or another: English. The catalogs are found beside this file (the source tree,
the Windows release's files, the AppImage's share/ttt2/i18n), or in TTT2_LAUNCHER_I18N_DIR when it is set (a
translator's files). One that cannot be read leaves its texts in English. Only what a player reads goes through
here: logs and command-line output stay English. extract.py lists these texts in en.txt with the C++ ones (it reads
the files of its PYTHON_FILES).
"""
import os
import re

LANGUAGES = ('en', 'fr', 'de', 'it', 'es', 'ru', 'pl')
PSEUDO = 'qps'
FORMS = ('zero', 'one', 'two', 'few', 'many', 'other')
_KEY = re.compile(r'^[A-Za-z0-9_.-]+$')
_PLACEHOLDER = re.compile(r'\{\{|\}\}|\{([A-Za-z0-9_]+)\}')
_ACCENTS = dict(zip('aeiouc' 'nszyAEIOUCNSZY', 'áéíöüçñšžýÅÉÎÖÜÇÑŠŽÝ'))
_catalogs = {}


def language():
    """The code of the launcher's language now: TTT2_TEXT_LANGUAGE's when it is one of LANGUAGES or PSEUDO, else
    "en"."""
    code = os.environ.get('TTT2_TEXT_LANGUAGE', '').strip().lower()
    return code if code in LANGUAGES or code == PSEUDO else 'en'


def plural_category(code, n):
    """CLDR's plural category of the whole number n in a language (i18n.cpp plural_category)."""
    a = abs(int(n))
    ten, hundred = a % 10, a % 100
    if code == 'fr':
        return 'one' if a in (0, 1) else 'many' if a and a % 1000000 == 0 else 'other'
    if code in ('it', 'es'):
        return 'one' if a == 1 else 'many' if a and a % 1000000 == 0 else 'other'
    if code in ('ru', 'pl'):
        if (ten == 1 and hundred != 11) if code == 'ru' else a == 1:
            return 'one'
        if 2 <= ten <= 4 and not 12 <= hundred <= 14:
            return 'few'
        return 'many'
    return 'one' if a == 1 else 'other'


def parse_catalog(text):
    """A catalog's texts (key or key[form] -> text, escapes undone) and its errors ("line N: ..."), as
    i18n.cpp parse_catalog reads it."""
    texts, errors = {}, []
    if text.startswith('﻿'):
        text = text[1:]
    for number, line in enumerate(text.split('\n'), 1):
        line = line.rstrip('\r \t').lstrip(' \t')
        if not line or line.startswith('#'):
            continue
        where = 'line %d: ' % number
        if '=' not in line:
            errors.append(where + "no '=' in it")
            continue
        key, value = line.split('=', 1)
        key, value = key.rstrip(' \t'), value.lstrip(' \t')
        base, form = key, None
        if '[' in key and key.endswith(']'):
            base, form = key[:key.index('[')], key[key.index('[') + 1:-1]
        if not _KEY.match(base) or (form is not None and form not in FORMS) or ('[' in key and form is None):
            errors.append(where + 'the key "%s" is not one' % key)
            continue
        out, i = [], 0
        while i < len(value):
            c = value[i]
            if c != '\\' or i + 1 == len(value):
                if c == '\\':
                    errors.append(where + 'a lone \\ at the end')
                out.append(c)
                i += 1
                continue
            e = value[i + 1]
            if e in 'nts\\':
                out.append({'n': '\n', 't': '\t', 's': ' ', '\\': '\\'}[e])
            else:
                errors.append(where + '\\%s is no escape (\\n, \\t, \\s or \\\\)' % e)
                out.append('\\' + e)
            i += 2
        if key in texts:
            errors.append(where + '"%s" is there twice' % key)
            continue
        texts[key] = ''.join(out)
    return texts, errors


def _folders():
    here = os.path.dirname(os.path.abspath(__file__))
    folders = [os.environ['TTT2_LAUNCHER_I18N_DIR']] if os.environ.get('TTT2_LAUNCHER_I18N_DIR') else []
    return folders + [here]


def catalog(code):
    """The texts of a language's catalog ({} for English, the pseudo language, or one that cannot be read)."""
    if code in ('en', PSEUDO) or code not in LANGUAGES:
        return {}
    if code not in _catalogs:
        texts = {}
        for folder in _folders():
            try:
                with open(os.path.join(folder, code + '.txt'), encoding='utf-8') as f:
                    texts = parse_catalog(f.read())[0]
                break
            except (OSError, UnicodeDecodeError):
                continue
        _catalogs[code] = texts
    return _catalogs[code]


def fill(text, values):
    """text with its {name}s filled ({name} without a value stays; {{ and }} are { and })."""
    def one(m):
        if m.group(0) in ('{{', '}}'):
            return m.group(0)[0]
        name = m.group(1)
        return str(values[name]) if name in values else m.group(0)
    return _PLACEHOLDER.sub(one, text)


def pseudo(english):
    """The pseudo language's form of an English text (i18n.cpp pseudo): marked, accented, a third longer."""
    if not english:
        return ''
    out, letters, i = ['['], 0, 0
    while i < len(english):
        m = re.match(r'\{[A-Za-z0-9_]+\}', english[i:])
        if m:
            out.append(m.group(0))
            i += len(m.group(0))
            continue
        c = english[i]
        letters += c.isascii() and c.isalpha()
        out.append(_ACCENTS.get(c, c))
        i += 1
    return ''.join(out) + ' ' + '~' * max(1, (letters + 2) // 3) + ']'


def tr(key, english, **values):
    """The text of key in the launcher's language (english when its catalog lacks it), its {name}s filled."""
    code = language()
    if code == PSEUDO:
        return fill(pseudo(english), values)
    return fill(catalog(code).get(key, english), values)


def trn(key, n, one, other, **values):
    """A text that changes with n: its plural form in the launcher's language (English: one for 1, else other);
    {n} is n."""
    values = dict(values, n=n)
    english = one if n == 1 else other
    code = language()
    if code == PSEUDO:
        return fill(pseudo(english), values)
    texts = catalog(code)
    text = texts.get('%s[%s]' % (key, plural_category(code, n))) or texts.get(key + '[other]') or english
    return fill(text, values)
