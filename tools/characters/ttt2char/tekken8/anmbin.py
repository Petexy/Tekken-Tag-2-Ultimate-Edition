"""Tekken 8's animation banks (.anmbin): a fighter's own bank (<code>.anmbin) and the shared one (com.anmbin), as
the game's own file reader hands them over (the dump of tekken8's helper; they live in the encrypted moveset archive,
which the importer never opens).

Header (little-endian, 0x98 bytes):
    +0x00  u32 end of the index (the first blob's offset)
    +0x04  6 x u32 entry counts, one per category
    +0x1C  6 x u32 key list counts (a fighter's bank: key list 0 has one key per move of its moveset; the shared
           bank has none)
    +0x34  u32 0
    +0x38  6 x u64 entry list offsets
    +0x68  6 x u64 key list offsets (u32 keys)
Entry (0x38 bytes): u32 key, u32 0, u64 blob offset (0: this bank does not hold it), u64 offset of an external path
(0 in every entry seen), 8 x u32 fighter mask (bit f % 32 of word f // 32: fighter f may use it; Reina is 28).
A blob is a 'PANM' animation (panm.py); its size runs up to the next blob (or the end of the file). Keys are
unique per category within a bank; a fighter's entry without a blob is served by the shared bank's entry of the
same category and key, whose mask has the fighter's bit (all of Reina's 1227 such entries resolve so; 6 body keys
are in neither bank).
Categories: 0 body, 1 hands (finger joints), 2 face, 3 props (wings, items), 4 camera, 5 unused.
A move's body animation: key list 0 [the move's anim index, its field +0x50] (Reina's: one per move), a key of
category 0. Its hand animations: properties 0x8610 / 0x8611 (one hand each), value = an index into key list 1, a
key of category 1 (19 finger joints of one hand; Reina's moves use 190 of them).

Written for this project from the files themselves (no third-party code).
"""
import mmap
import os
import struct

from .. import InputError

BODY, HANDS, FACE, PROPS, CAMERA = 0, 1, 2, 3, 4
CATEGORIES = 6
HEADER_SIZE = 0x98
ENTRY_SIZE = 0x38
MASK_WORDS = 8                              # a 256-bit fighter mask
SHARED = 'com'                              # the shared bank's name (com.anmbin)


class Entry:
    __slots__ = ('category', 'index', 'key', 'blob', 'path', 'mask', 'size')

    def __repr__(self):
        return '<Entry cat %d #%d key %08x blob %#x size %d>' % (self.category, self.index, self.key, self.blob,
                                                                 self.size)

    def serves(self, fighter):
        """The fighter may use this entry (its bit in the mask)."""
        return bool((self.mask[fighter // 32] >> (fighter % 32)) & 1)


class Bank:
    """One .anmbin: `source` is a file path (mapped, not read) or bytes. .entries {(category, key): Entry},
    .keys(category) [keys in entry order], .key_lists [6 lists of u32 keys], .blob(category, key)."""

    def __init__(self, source, name=None):
        if isinstance(source, (str, os.PathLike)):
            self.name = name or os.path.basename(os.fspath(source))
            try:
                self._file = open(source, 'rb')
                self.data = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
            except (OSError, ValueError) as e:
                raise InputError('the animation bank %s cannot be read (%s): dump the fighter again' % (source, e))
        else:
            self.name, self._file, self.data = name or 'anmbin', None, source
        d = self.data
        if len(d) < HEADER_SIZE:
            raise InputError('%s is not a Tekken 8 animation bank (too short): dump the fighter again' % self.name)
        self.index_end, = struct.unpack_from('<I', d, 0)
        self.counts = struct.unpack_from('<6I', d, 4)
        key_counts = struct.unpack_from('<6I', d, 0x1C)
        lists = struct.unpack_from('<6Q', d, 0x38)
        key_lists = struct.unpack_from('<6Q', d, 0x68)
        for c in range(CATEGORIES):
            if lists[c] + ENTRY_SIZE * self.counts[c] > self.index_end or \
                    key_lists[c] + 4 * key_counts[c] > self.index_end or self.index_end > len(d):
                raise InputError('%s is not a Tekken 8 animation bank (its index does not fit): dump the fighter '
                                 'again' % self.name)
        self.entries, self._order = {}, [[] for _ in range(CATEGORIES)]
        starts = []
        for c in range(CATEGORIES):
            for j in range(self.counts[c]):
                o = lists[c] + ENTRY_SIZE * j
                e = Entry()
                e.category, e.index = c, j
                e.key, _, e.blob, e.path = struct.unpack_from('<IIQQ', d, o)
                e.mask = struct.unpack_from('<%dI' % MASK_WORDS, d, o + 0x18)
                e.size = 0
                if e.blob and not self.index_end <= e.blob < len(d):
                    raise InputError('%s: animation %08x lies outside the file: dump the fighter again' % (
                        self.name, e.key))
                self.entries[(c, e.key)] = e
                self._order[c].append(e.key)
                if e.blob:
                    starts.append(e.blob)
        ends = sorted(set(starts)) + [len(d)]
        following = dict(zip(ends[:-1], ends[1:]))
        for e in self.entries.values():
            if e.blob:
                e.size = following[e.blob] - e.blob
        self.key_lists = [list(struct.unpack_from('<%dI' % key_counts[c], d, key_lists[c]))
                          for c in range(CATEGORIES)]

    def close(self):
        if self._file is not None:
            self.data.close()
            self._file.close()
            self._file = None

    def keys(self, category):
        return list(self._order[category])

    def entry(self, category, key):
        return self.entries.get((category, key))

    def blob(self, category, key):
        """The animation's bytes, or None when this bank does not hold it."""
        e = self.entries.get((category, key))
        if e is None or not e.blob:
            return None
        return bytes(self.data[e.blob:e.blob + e.size])


class Banks:
    """A fighter's banks: its own, then the shared one (an entry there only if its mask has the fighter's bit)."""

    def __init__(self, own, shared, fighter):
        self.own, self.shared, self.fighter = own, shared, int(fighter)

    def where(self, category, key):
        """'own', 'com' (the shared bank) or None: which bank holds the fighter's animation."""
        e = self.own.entry(category, key)
        if e is not None and e.blob:
            return 'own'
        e = self.shared.entry(category, key) if self.shared is not None else None
        if e is not None and e.blob and e.serves(self.fighter):
            return SHARED
        return None

    def blob(self, category, key):
        w = self.where(category, key)
        if w is None:
            return None
        return (self.own if w == 'own' else self.shared).blob(category, key)

    def anim_key(self, index):
        """The body animation key of a move's anim index (its field +0x50 without the flag bits 0xC000; key list
        0)."""
        keys = self.own.key_lists[BODY]
        if not 0 <= index < len(keys):
            raise IndexError('anim index %d: the bank has keys for %d' % (index, len(keys)))
        return keys[index]

    def move_keys(self):
        """[(key, bank)] of the distinct body animations the fighter's moves use, in first-use order."""
        out = []
        for k in dict.fromkeys(self.own.key_lists[BODY]):
            out.append((k, self.where(BODY, k)))
        return out


def open_banks(folder, code, fighter):
    """Banks of fighter `code` (number `fighter`) from a folder holding <code>.anmbin and com.anmbin."""
    paths = [os.path.join(folder, '%s.anmbin' % n) for n in (code, SHARED)]
    for p in paths:
        if not os.path.isfile(p):
            raise InputError('%s is missing: dump the fighter from Tekken 8 first' % p)
    return Banks(Bank(paths[0]), Bank(paths[1]), fighter)
