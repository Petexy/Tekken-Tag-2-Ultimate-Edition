#!/usr/bin/env python3
"""Developer tool (not for players): write a saved customization slot of an ADDED fighter, so that the costume
chooser has a slot to pick before CUSTOMIZE mode can make one.

    customize_slot.py SAVE CODE                      list the fighter's slots
    customize_slot.py SAVE CODE SLOT TEXT...         slot 0..4 wears the record text(s), later ones winning
    customize_slot.py SAVE CODE SLOT --pack PACK ROW... [TEXT...]
                                                     the same from rows of PACK/wardrobe.txt (by label, or by a
                                                     part of it that names one row), over TEXTs given before them
    customize_slot.py SAVE CODE SLOT --clear         empty the slot

SAVE is the game's save folder (the one holding 80000001/; TTT2_SAVE_DIR of a test run): the file is
SAVE/customize/CODE.bin and nothing else is touched. Use a copy of a save, never the player's own. A record text is
`<equip slot>=<item index>[/<variant>],c<colour register>=<colour number>...`; a record replaces the fighter's
default items, so name those too (for a fighter whose donor is Jun: 0=5,17=333,18=338 and the garments).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ttt2char import customize  # noqa: E402


def row_text(rows, name):
    if name in rows:
        return rows[name]
    hits = [label for label in rows if name in label]
    if len(hits) != 1:
        raise ValueError('%r names %d rows of wardrobe.txt%s' % (name, len(hits), ': ' + ', '.join(hits) if hits else ''))
    return rows[hits[0]]


def main(argv):
    if len(argv) < 2 or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 2
    save, code, rest = argv[0], argv[1], argv[2:]
    if not os.path.isdir(save):
        print('no such save folder: %s' % save)
        return 1
    body = customize.load(save, code)
    if not rest:
        for n in range(customize.SLOTS):
            items = customize.items_of(body, n) if customize.filled(body, n) else None
            print('slot %d: %s' % (n, 'empty' if items is None else ','.join('%d=%d' % kv for kv in sorted(items.items()))))
        return 0
    number, rest = int(rest[0]), rest[1:]
    if rest == ['--clear']:
        customize.clear_slot(body, number)
    else:
        texts, rows = [], None
        while rest:
            word = rest.pop(0)
            if word == '--pack':
                rows = customize.wardrobe_rows(rest.pop(0))
            elif '=' in word:
                texts.append(word)
            elif rows is None:
                raise ValueError('%r: a row needs --pack PACK before it' % word)
            else:
                texts.append(row_text(rows, word))
        customize.set_slot(body, number, texts)
    print(customize.store(save, code, body))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, OSError) as error:
        print('customize_slot: %s' % error)
        sys.exit(1)
