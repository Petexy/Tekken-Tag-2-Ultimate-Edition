#!/usr/bin/env python3
"""The launcher's texts: every tr("key", "English") and trn("key", n, "one", "other") in its code (C++: launcher/;
Python: the workers, tr('key', 'English') and trn(...) of launcher_texts.py), as launcher/i18n/en.txt lists them, and
whether each language's catalog (launcher/i18n/<code>.txt) fits them.

    python3 launcher/i18n/extract.py            # writes en.txt anew
    python3 launcher/i18n/extract.py --check    # fails when en.txt is not what the code says, or a catalog has a key
                                                # en.txt lacks, other placeholders than the English, or misses a
                                                # plural form of its language
    python3 launcher/i18n/extract.py --json     # every text with where it is used (for translators' work lists)

The catalogs' format: launcher/core/i18n.h. A key a catalog lacks is only counted: it shows in English.
"""
import argparse
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LANGUAGES = ('fr', 'de', 'it', 'es', 'ru', 'pl')
# CLDR's plural categories of each language (i18n.cpp plural_categories).
PLURALS = {'en': ('one', 'other'), 'de': ('one', 'other'), 'fr': ('one', 'many', 'other'),
           'it': ('one', 'many', 'other'), 'es': ('one', 'many', 'other'), 'ru': ('one', 'few', 'many', 'other'),
           'pl': ('one', 'few', 'many', 'other')}
CPP_FOLDERS = ('launcher/app', 'launcher/model', 'launcher/ui/src', 'launcher/ui/include', 'launcher/core',
               'launcher/backend')
PYTHON_FILES = ('tools/characters/launcher.py', 'launcher/windows/backend.py', 'launcher/windows/main.py',
                'launcher/windows/query.py', 'launcher/windows/self_update.py', 'launcher/windows/setup_game.py',
                'launcher/windows/build_launcher.py')
KEY = re.compile(r'^[A-Za-z0-9_.-]+$')
PLACEHOLDER = re.compile(r'(?<!\{)\{([A-Za-z0-9_]+)\}')


class Problem(Exception):
    pass


def placeholders(text):
    return set(PLACEHOLDER.findall(text.replace('{{', '')))


# ---------------------------------------------------------------- C++

ESCAPES = {'n': '\n', 't': '\t', '\\': '\\', '"': '"', "'": "'", '?': '?', '0': '\0'}


def cpp_string(source, i):
    """The literal starting at source[i] ('"'), undone, and the index after it."""
    out, i = [], i + 1
    while source[i] != '"':
        if source[i] == '\\':
            c = source[i + 1]
            if c == 'x':
                digits = re.match(r'[0-9a-fA-F]+', source[i + 2:]).group(0)
                out.append(bytes([int(digits, 16)]).decode('latin-1'))
                i += 2 + len(digits)
                continue
            out.append(ESCAPES.get(c, c))
            i += 2
            continue
        out.append(source[i])
        i += 1
    return ''.join(out), i + 1


def skip_space(source, i):
    while True:
        while i < len(source) and source[i] in ' \t\r\n':
            i += 1
        if source.startswith('//', i):
            i = source.index('\n', i)
        elif source.startswith('/*', i):
            i = source.index('*/', i) + 2
        else:
            return i


def cpp_literals(source, i):
    """Adjacent literals from source[i] ("a" "b"), joined, and the index after them; None when none is there."""
    i = skip_space(source, i)
    if i >= len(source) or source[i] != '"':
        return None, i
    parts = []
    while i < len(source) and source[i] == '"':
        text, i = cpp_string(source, i)
        parts.append(text)
        i = skip_space(source, i)
    return ''.join(parts), i


def cpp_skip_argument(source, i):
    """The index of the comma ending the argument at source[i] (brackets and literals skipped)."""
    depth = 0
    while i < len(source):
        c = source[i]
        if c == '"':
            _, i = cpp_string(source, i)
            continue
        if c == "'":
            i = source.index("'", i + 1 + (source[i + 1] == '\\')) + 1
            continue
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0:
                return i
            depth -= 1
        elif c == ',' and depth == 0:
            return i
        i += 1
    raise Problem('unterminated call')


CPP_CALL = re.compile(r'(?<![A-Za-z0-9_])(trn|tr)\s*\(')


def scan_cpp(path, source, found):
    for m in CPP_CALL.finditer(source):
        line = source.count('\n', 0, m.start()) + 1
        where = '%s:%d' % (path, line)
        before = source[source.rfind('\n', 0, m.start()) + 1:m.start()]
        if before.lstrip().startswith('//') or re.search(r'\bstd::string\s+$|\bstd::string_view\s+$', before):
            continue  # (a comment, or tr()'s own declaration)
        i = m.end()
        key, i = cpp_literals(source, i)
        if key is None:
            if re.match(r'\s*std::string_view\s+key', source[i:i + 40]):
                continue  # (the declaration in i18n.h)
            raise Problem('%s: %s()\'s key is no literal' % (where, m.group(1)))
        if source[i] != ',':
            raise Problem('%s: %s("%s") has no English' % (where, m.group(1), key))
        if m.group(1) == 'tr':
            english, i = cpp_literals(source, i + 1)
            if english is None:
                raise Problem('%s: tr("%s")\'s English is no literal' % (where, key))
            add(found, key, english, None, where)
        else:
            i = cpp_skip_argument(source, i + 1)
            one, i = cpp_literals(source, i + 1)
            if one is None or source[i] != ',':
                raise Problem('%s: trn("%s")\'s one is no literal' % (where, key))
            other, i = cpp_literals(source, i + 1)
            if other is None:
                raise Problem('%s: trn("%s")\'s other is no literal' % (where, key))
            add(found, key, None, {'one': one, 'other': other}, where)


# ---------------------------------------------------------------- Python

def scan_python(path, source, found):
    tree = ast.parse(source, path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else \
            node.func.attr if isinstance(node.func, ast.Attribute) else None
        if name not in ('tr', 'trn'):
            continue
        where = '%s:%d' % (path, node.lineno)
        literal = lambda n: n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None
        args = node.args
        if len(args) < (2 if name == 'tr' else 4) or literal(args[0]) is None:
            raise Problem('%s: %s() needs a literal key and English' % (where, name))
        if name == 'tr':
            if literal(args[1]) is None:
                raise Problem('%s: tr(%r)\'s English is no literal' % (where, args[0].value))
            add(found, args[0].value, args[1].value, None, where)
        else:
            if literal(args[2]) is None or literal(args[3]) is None:
                raise Problem('%s: trn(%r)\'s forms are no literals' % (where, args[0].value))
            add(found, args[0].value, None, {'one': args[2].value, 'other': args[3].value}, where)


def add(found, key, english, forms, where):
    if not KEY.match(key):
        raise Problem('%s: "%s" is no key (letters, digits, _ . -)' % (where, key))
    entry = found.get(key)
    if entry is None:
        found[key] = {'english': english, 'forms': forms, 'where': [where]}
        return
    if entry['english'] != english or entry['forms'] != forms:
        raise Problem('%s: "%s" has another English than at %s' % (where, key, entry['where'][0]))
    entry['where'].append(where)


def collect(root=ROOT):
    found = {}
    for folder in CPP_FOLDERS:
        for base, dirs, files in os.walk(os.path.join(root, folder)):
            dirs[:] = sorted(d for d in dirs if d not in ('tests', 'third_party', 'smoke', 'demo'))
            for name in sorted(files):
                if not name.endswith(('.cpp', '.h')) or name.endswith('_test.cpp') or name in ('i18n.h', 'i18n.cpp'):
                    continue
                path = os.path.join(base, name)
                with open(path, encoding='utf-8') as f:
                    scan_cpp(os.path.relpath(path, root), f.read(), found)
    for rel in PYTHON_FILES:
        path = os.path.join(root, rel)
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                scan_python(rel, f.read(), found)
    return found


# ---------------------------------------------------------------- catalogs

def escape(text):
    out = text.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')
    if out.startswith(' '):
        out = '\\s' + out[1:]
    if out.endswith(' '):
        out = out[:-1] + '\\s'
    return out


def english_catalog(found):
    lines = ['# Golden Fist Launcher: its texts in English, the source of every translation. Made from the code by',
             '# launcher/i18n/extract.py: do not edit (change the English where it is used). Format and how to add a',
             '# language: docs/LAUNCHER.md#languages.', '']
    for key in sorted(found):
        entry = found[key]
        if entry['forms']:
            for form in PLURALS['en']:
                lines.append('%s[%s] = %s' % (key, form, escape(entry['forms'][form])))
        else:
            lines.append('%s = %s' % (key, escape(entry['english'])))
    return '\n'.join(lines) + '\n'


def parse_catalog(text):
    """{key: text} and the problems (as i18n.cpp parse_catalog)."""
    texts, problems = {}, []
    for number, line in enumerate(text.split('\n'), 1):
        line = line.lstrip('\ufeff').strip(' \t\r')
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            problems.append('line %d: no "=" in it' % number)
            continue
        key, value = line.split('=', 1)
        key, value = key.rstrip(' \t'), value.lstrip(' \t')
        m = re.match(r'^([A-Za-z0-9_.-]+)(?:\[(zero|one|two|few|many|other)\])?$', key)
        if not m:
            problems.append('line %d: the key "%s" is not one' % (number, key))
            continue
        out, i = [], 0
        while i < len(value):
            c = value[i]
            if c == '\\' and i + 1 < len(value):
                e = value[i + 1]
                if e in 'nts\\':
                    out.append({'n': '\n', 't': '\t', 's': ' ', '\\': '\\'}[e])
                else:
                    problems.append('line %d: \\%s is no escape' % (number, e))
                    out.append(c + e)
                i += 2
                continue
            out.append(c)
            i += 1
        if key in texts:
            problems.append('line %d: "%s" is there twice' % (number, key))
        texts[key] = ''.join(out)
    return texts, problems


def check_catalog(code, texts, found):
    """The problems of a language's catalog against the code's texts, and how many keys it lacks."""
    problems, missing = [], 0
    forms = PLURALS[code]
    seen = set()
    for key, text in texts.items():
        base, _, form = key.partition('[')
        form = form.rstrip(']')
        entry = found.get(base)
        if entry is None:
            problems.append('%s: "%s" is no key of the launcher (en.txt has none such)' % (code, base))
            continue
        seen.add(base)
        if entry['forms'] is None:
            if form:
                problems.append('%s: "%s" is no plural text: it takes no [%s]' % (code, base, form))
                continue
            want = placeholders(entry['english'])
            if placeholders(text) != want:
                problems.append('%s: "%s" has the placeholders {%s}, the English {%s}' % (
                    code, base, ', '.join(sorted(placeholders(text))), ', '.join(sorted(want))))
        else:
            if not form:
                problems.append('%s: "%s" is a plural text: one line per form ([%s])' % (code, base, '], ['.join(forms)))
                continue
            if form not in forms:
                problems.append('%s: "%s[%s]": %s has no plural form %s' % (code, base, form, code, form))
                continue
            want = placeholders(entry['forms']['one']) | placeholders(entry['forms']['other'])
            have = placeholders(text)
            # (a form may leave {n} out: "one" is often said without the number)
            if have - want or (want - {'n'}) - have:
                problems.append('%s: "%s[%s]" has the placeholders {%s}, the English {%s}' % (
                    code, base, form, ', '.join(sorted(have)), ', '.join(sorted(want))))
    for base, entry in found.items():
        if base not in seen:
            missing += 1
        elif entry['forms'] is not None:
            for form in forms:
                if '%s[%s]' % (base, form) not in texts:
                    problems.append('%s: "%s" lacks its plural form [%s]' % (code, base, form))
    return problems, missing


def main():
    parser = argparse.ArgumentParser(description='The launcher\'s texts: en.txt from the code, catalogs checked.')
    parser.add_argument('--check', action='store_true', help='check en.txt and every catalog; write nothing')
    parser.add_argument('--json', action='store_true', help='print every text with where it is used')
    parser.add_argument('--root', default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        found = collect(args.root)
    except Problem as problem:
        sys.exit('extract.py: %s' % problem)
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=1, sort_keys=True))
        return 0
    english = english_catalog(found)
    path = os.path.join(args.root, 'launcher/i18n/en.txt')
    if not args.check:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(english)
        print('en.txt: %d keys' % len(found))
        return 0
    problems = []
    with open(path, encoding='utf-8') as f:
        if f.read() != english:
            problems.append('en.txt is not what the code says: run python3 launcher/i18n/extract.py')
    for code in LANGUAGES:
        catalog = os.path.join(args.root, 'launcher/i18n/%s.txt' % code)
        if not os.path.exists(catalog):
            problems.append('%s.txt is missing' % code)
            continue
        with open(catalog, encoding='utf-8') as f:
            texts, syntax = parse_catalog(f.read())
        problems += ['%s.txt %s' % (code, p) for p in syntax]
        wrong, missing = check_catalog(code, texts, found)
        problems += wrong
        print('%s.txt: %d of %d keys (%d shown in English)' % (code, len(found) - missing, len(found), missing))
    for p in problems:
        print('extract.py: ' + p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
