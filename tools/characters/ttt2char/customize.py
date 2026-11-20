"""An added fighter's saved customizations: the file the game keeps per added fighter (the runtime's
title/customize_store.h), for developers who need a saved slot before CUSTOMIZE mode can make one.

Tekken Tag Tournament 2 saves ten customization records per fighter (0-4 the five slots of CUSTOMIZE, 5-9 the edited
default costumes) and a picture per slot. An added fighter's are in `<save folder>/customize/<code>.bin`, in the
game's layout (SIZE bytes, big-endian):
    +0       f32 1.2 (as the game's working buffer has it)
    +4       10 records of 4096 bytes
    +0xA004  12 bytes, zero
    +0xA010  11 pictures of 19,584 bytes; zero here: CUSTOMIZE mode takes a slot's picture, and the costume
             chooser shows the fighter's first costume for a slot without one
A record: +0 u8 "holds data"; +4, 21 x s32, the item in each equip slot (the `index` of an Instance of the
fighter's item database, -1 none); +568/+570/+572 u16 variants of slots 15/16/7; +576, 14 colour groups x 5
entries {u32, u32 colour number, f32} = colour registers 26..95 (groups 0 and 1 stored swapped); +3276 the slot's
number; the rest print and paint data, here as the game leaves a record without any.

A record's text is the developer switch's (`<slot>=<index>[/<variant>]`, `c<register>=<colour number>`, joined by
commas), which is also what a pack's wardrobe.txt lists per fitted outfit row.
"""
import os
import struct

SIZE = 0x3E990
RECORDS, RECORD, FIRST_RECORD, SLOTS = 10, 4096, 4, 5
PICTURES, PICTURE, FIRST_PICTURE = 11, 19584, 0xA010
EQUIP_SLOTS, FIRST_REGISTER, REGISTERS = 21, 26, 70
VARIANTS = {15: 568, 16: 570, 7: 572}
assert FIRST_PICTURE + PICTURES * PICTURE == SIZE


def empty_record():
    """A record as the game makes one that holds nothing."""
    r = bytearray(RECORD)
    r[4:568] = b'\xff' * 564                               # items, then 15 x 8 numbers: none
    r[568:574] = b'\xff' * 6                               # variants: none
    for at in range(576, 576 + 12 * REGISTERS, 12):        # colours: {0, 0 = the fighter's default, -1.0}
        struct.pack_into('>IIf', r, at, 0, 0, -1.0)
    for at in range(2320, 2320 + 4 * 36, 36):              # 4 prints: none
        struct.pack_into('>i', r, at + 4, -1)
    for at in range(2464, 2464 + 20 * 40, 40):             # 4 x 5 paint layers: none, unit scale
        struct.pack_into('>ii6f', r, at, -1, -1, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0)
    struct.pack_into('>ii', r, 3264, -1, -1)
    struct.pack_into('>ii', r, 3276, -1, -1)
    return r


def empty():
    """The file of a fighter with nothing saved."""
    body = bytearray(SIZE)
    struct.pack_into('>f', body, 0, 1.2)
    for n in range(RECORDS):
        body[FIRST_RECORD + RECORD * n:FIRST_RECORD + RECORD * (n + 1)] = empty_record()
    return body


def parse(text):
    """A record text -> ({equip slot: (index, variant or None)}, {colour register: colour number})."""
    items, colours = {}, {}
    for entry in filter(None, (e.strip() for e in text.split(','))):
        key, sep, value = entry.partition('=')
        if not sep:
            raise ValueError('not <key>=<value>: %r' % entry)
        if key.startswith('c'):
            register, colour = int(key[1:]), int(value)
            if not FIRST_REGISTER <= register < FIRST_REGISTER + REGISTERS or not 0 <= colour <= 0xFFFF:
                raise ValueError('colour register 26..95, colour number 0..65535: %r' % entry)
            colours[register] = colour
            continue
        index, sep, variant = value.partition('/')
        slot, index, variant = int(key), int(index), int(variant) if sep else None
        if not 0 <= slot < EQUIP_SLOTS or not 0 < index <= 0xFFFF:
            raise ValueError('equip slot 0..20, item index 1..65535: %r' % entry)
        if variant is not None and (slot not in VARIANTS or not 0 <= variant < 0xFFFF):
            raise ValueError('only slots 7, 15 and 16 have a variant: %r' % entry)
        items[slot] = (index, variant)
    return items, colours


def merge(texts):
    """Several record texts as one (a base, an upper row, a lower row ...): later ones win."""
    items, colours = {}, {}
    for text in texts:
        more_items, more_colours = parse(text)
        items.update(more_items)
        colours.update(more_colours)
    return items, colours


def colour_offset(register):
    group, entry = divmod(register - FIRST_REGISTER, 5)
    return 576 + 60 * {0: 1, 1: 0}.get(group, group) + 12 * entry


def record(items, colours, number):
    """The record of customization slot `number` wearing `items` in `colours` (what parse returns)."""
    r = empty_record()
    r[0] = 1
    for slot, (index, variant) in items.items():
        struct.pack_into('>i', r, 4 + 4 * slot, index)
        if variant is not None:
            struct.pack_into('>H', r, VARIANTS[slot], variant)
    for register, colour in colours.items():
        struct.pack_into('>I', r, colour_offset(register) + 4, colour)
    struct.pack_into('>i', r, 3276, number)
    return r


def filled(body, number):
    return body[FIRST_RECORD + RECORD * number] != 0


def items_of(body, number):
    """{equip slot: index} of a filled record."""
    at = FIRST_RECORD + RECORD * number + 4
    return {slot: index for slot, index in enumerate(struct.unpack_from('>21i', body, at)) if index > 0}


def path(save, code):
    if not code or not all(c.isascii() and (c.isalnum() or c == '_') for c in code):
        raise ValueError('not a pack code: %r' % code)
    return os.path.join(save, 'customize', code + '.bin')


def load(save, code):
    """The fighter's file, or an empty one if there is none (a file of another size is not one of these)."""
    try:
        with open(path(save, code), 'rb') as f:
            body = bytearray(f.read())
    except FileNotFoundError:
        return empty()
    if len(body) != SIZE:
        raise ValueError('%s is not a customization file (%d bytes)' % (path(save, code), len(body)))
    return body


def store(save, code, body):
    """Writes the file whole or not at all (a temporary file, then a rename)."""
    assert len(body) == SIZE
    out = path(save, code)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + '.tmp', 'wb') as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())
    os.replace(out + '.tmp', out)
    return out


def set_slot(body, number, texts):
    if not 0 <= number < SLOTS:
        raise ValueError('customization slots are 0..4')
    items, colours = merge(texts)
    if not items:
        raise ValueError('a record without items')
    body[FIRST_RECORD + RECORD * number:FIRST_RECORD + RECORD * (number + 1)] = record(items, colours, number)
    body[FIRST_PICTURE + PICTURE * number:FIRST_PICTURE + PICTURE * (number + 1)] = bytes(PICTURE)


def clear_slot(body, number):
    if not 0 <= number < SLOTS:
        raise ValueError('customization slots are 0..4')
    body[FIRST_RECORD + RECORD * number:FIRST_RECORD + RECORD * (number + 1)] = empty_record()
    body[FIRST_PICTURE + PICTURE * number:FIRST_PICTURE + PICTURE * (number + 1)] = bytes(PICTURE)


def wardrobe_rows(pack):
    """{label: record text} of a pack's wardrobe.txt (the outfit rows the importer fitted for the fighter)."""
    rows = {}
    with open(os.path.join(pack, 'wardrobe.txt'), encoding='utf-8') as f:
        for line in f:
            label, sep, text = line.partition(':')
            if sep and text.strip():
                rows[label.strip()] = text.strip()
    return rows
