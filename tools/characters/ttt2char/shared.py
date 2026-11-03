"""The title entries the added fighters share (`<characters folder>/shared/keys/`), made for every current pack.

Each added fighter changes some of the title's own entries: the 2D layouts (its labels beside Paul's, its select
grid cell), the big portraits' container, the fights' HUD pictures, the costume palettes and colour grid (its
player 2 colours) and the select screen's announcer bank (its name call). Packs made one by one would each carry a
copy and the last would win, so these are made here for all installed packs together, each fighter in its place
(pack.place): after an import, from each pack's `colours.json` (its player 2 colours) and each fighter's pictures
and name call, which come from its own game (Tekken 7 or Tekken 8): from the copy its import saved in its pack
(`source/`: source_files), else from that game again (source.py). A pack made before packs had that copy, whose
game is gone, keeps what the shared/ there has of it (its pictures, its name call: art.keep, voice.kept_name_call),
so that one game uninstalled never stops the other game's fighters being added, updated or removed. Only current
packs (pack.PACK_FORMAT) are in it: the port loads no other, and these are the only copies of the title's entries
it reads (never a pack's own `keys/`).
"""
import io
import json
import os
import shutil
import types
import wave

import numpy as np
from PIL import Image

from . import InputError, pack, signals
from .characters import GAMES, game_of
from .convert import art, colours, voice
from .ttt2.archive import key_of
from .ttt2.nus3bank import wave as wave_file

NAME_CALL = 'name_call.wav'     # a pack's copy of its name call, in source/


def fighters_of(folder, definitions, leaving=()):
    """[(slot, definition, pack folder)] of the packs the port loads (pack.loaded: current ones, one of each code)
    whose fighter the importer knows, by place, but those of codes `leaving` (packs about to be removed: as if they
    were gone). An older importer's pack gets no pictures here, and its place stays its own (pack.placed counts every
    pack) for when its fighter is imported again."""
    out = []
    for k, p in pack.loaded([p for p in pack.installed(folder) if p['code'] not in leaving]):
        d = definitions.get(p['code'])
        if d is not None:
            out.append((k, d, p['path']))
    return out


def source_files(source, d, clips):
    """What fighter d's pack keeps of its game for shared/ (its source/): the pictures shared/ is made from
    (pack.source_pictures: PNG) and its name call (16-bit WAVE, if its game has one), as its source (source.py)
    and its clips give them -> {file name in the pack: bytes}."""
    files = {}
    for path in pack.source_pictures(d):
        out = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(source.picture(path), np.uint8), 'RGBA').save(out, 'PNG')
        files['%s/%s' % (pack.SOURCE, pack.source_name(path))] = out.getvalue()
    clip = clips.kinds.get(('name', None))
    if clip:
        _, rate, a = clip[0]
        files['%s/%s' % (pack.SOURCE, NAME_CALL)] = wave_file(list(a), rate)
    return files


class PackSource:
    """Fighter d's pictures and name call from its pack's source/ (source_files), as its game gave them: what
    art.Sources and name_calls ask a source (source.py) for."""

    def __init__(self, folder, d):
        self.folder, self.game = os.path.join(folder, pack.SOURCE), game_of(d)

    def picture(self, path):
        with Image.open(os.path.join(self.folder, pack.source_name(path))) as img:
            return np.asarray(img.convert('RGBA'), np.uint8)

    def clips(self, d):
        """Its clips as far as shared/ needs them: kinds holding its name call, when it has one."""
        kinds = {}
        path = os.path.join(self.folder, NAME_CALL)
        if os.path.isfile(path):
            with wave.open(path, 'rb') as f:
                channels, rate = f.getnchannels(), f.getframerate()
                a = np.frombuffer(f.readframes(f.getnframes()), '<i2').reshape(-1, channels).T.astype(np.int16)
            kinds[('name', None)] = [('name', rate, a)]
        return types.SimpleNamespace(kinds=kinds)


def palettes(archives, fighters):
    """The colour grid and both palettes with every fighter's player 2 colours: {file name: bytes}, or {}."""
    texts = [archives.read(k).decode('utf-8') for k in (colours.KEY_1P, colours.KEY_2P)]
    grid = colours.Palette(archives.read(colours.KEY_GRID), texts)
    placed = False
    for slot, d, folder in fighters:
        path = os.path.join(folder, 'colours.json')
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            mine = {int(nn): v for nn, v in json.load(f).items()}
        entries = [{}, {}]
        for nn, (rgb1, rgb2) in sorted(mine.items()):
            entries[0][nn] = grid.place(rgb1)
            entries[1][nn] = grid.place(rgb2)
        for which in (0, 1):
            texts[which] = colours.palette_xml(texts[which], pack.place(slot)['id'], entries[which])
        placed = True
    if not placed:
        return {}
    return {'keys/%08x.bin' % colours.KEY_GRID: grid.grid_bytes(),
            'keys/%08x.bin' % colours.KEY_1P: texts[0].encode('utf-8'),
            'keys/%08x.bin' % colours.KEY_2P: texts[1].encode('utf-8')}


def name_calls(source_of, archives, fighters, log=None, earlier=None, kept=()):
    """The select screen's announcer bank with every fighter's name call: {file name: bytes}, or {}. source_of(d):
    fighter d's source (source.py: its clips); a fighter of codes `kept` has its name call as earlier(file name),
    the bank an earlier build made, has it."""
    name = 'keys/%08x.bin' % key_of(voice.SELECT_BANK)
    bank = archives.raw(key_of(voice.SELECT_BANK))
    changed = False
    for slot, d, folder in fighters:
        if d.CODE in kept:
            before = earlier(name)
            made = voice.kept_name_call(before, bank, d.DONOR, d.CODE) if before else None
        else:
            made = voice.name_call(source_of(d).clips(d), bank, d.DONOR, d.CODE)
        if made is not None:
            bank, changed = made, True
        elif log:
            log('no name call of %s on the select screen' % d.NAME)
    return {name: bank} if changed else {}


def own_sources(fighters, source_of):
    """({code: source}, kept) of fighters [(slot, definition, pack folder)]: the source of each one's pictures and
    name call, its pack's copy (PackSource), else its game's (source_of(d)); kept [(slot, definition)]: those whose
    game cannot be read (InputError), which keep what the shared/ there has of them."""
    sources, kept = {}, []
    for slot, d, path in fighters:
        if pack.carries_source(path, d):
            sources[d.CODE] = PackSource(path, d)
            continue
        try:
            sources[d.CODE] = source_of(d)
        except InputError:
            kept.append((slot, d))
    return sources, kept


def build(source_of, archives, rpx, folder, definitions, log=None, leaving=()):
    """Writes <folder>/shared/ for the installed packs (but those of codes `leaving`); definitions: {code:
    definition}; source_of(d): fighter d's source (source.Sources: a Tekken 7 and a Tekken 8 fighter are read from
    their own games) for a pack without its copy (source/). A fighter whose game cannot be read (InputError) keeps
    what the shared/ there has of it; InputError when that has none. The select grid gets its new top row only while
    a fighter's place is past the title's grid's room (pack.needs_new_row; grid.ini `grid = rows` tells the port).
    -> the fighters it has."""
    fighters = fighters_of(folder, definitions, leaving)
    target = os.path.join(folder, pack.SHARED)
    part, old = target + '.part', target + '.old'
    if not os.path.lexists(target) and os.path.isdir(old):
        os.replace(old, target)             # (an earlier build stopped between its renames: what it replaced)
    sources, kept = own_sources(fighters, source_of)

    def own(d):
        return sources[d.CODE] if d.CODE in sources else art.Blank()
    earlier = _reader(target)
    files = {}
    if fighters:
        new_row = pack.needs_new_row(slot for slot, _, _ in fighters)
        files.update(art.shared_files(own, archives, rpx, [(slot, d) for slot, d, _ in fighters], log=log,
                                      new_row=new_row))
        try:
            art.keep(files, earlier, kept, archives)
        except art.Lost as lost:
            d, what = lost.args
            raise InputError('%s comes from %s, which cannot be read, and neither %s\'s pack (made by an older '
                             'version) nor %s has the pictures and name call made from it (%s: %s): install %s '
                             'again, or remove %s' % (d.NAME, GAMES[game_of(d)], d.NAME, target, d.NAME, what,
                                                      GAMES[game_of(d)], d.NAME))
        if kept and log:
            log('as %s has them (their game cannot be read): %s' % (target, ', '.join(d.NAME for _, d in kept)))
        if new_row:
            files['grid.ini'] = b'grid = rows\n'
        files.update(palettes(archives, fighters))
        files.update(name_calls(own, archives, fighters, log=log, earlier=earlier, kept={d.CODE for _, d in kept}))
    # (A link put there goes, not what it leads to: shared/ is made anew each time, here.)
    for path in (part, old):
        pack.delete_path(path)
    try:
        for name, data in files.items():
            path = os.path.join(part, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
    except BaseException:
        # (stopped, or the disk is full: the shared/ there stays, and nothing half written is left beside it)
        shutil.rmtree(part, ignore_errors=True)
        raise
    try:
        with signals.deferred():            # (the old one goes and the new one comes, a signal or not)
            if os.path.lexists(target):
                os.replace(target, old)
            if files:
                os.replace(part, target)
    finally:
        try:
            pack.delete_path(old)
        except OSError:
            pass                            # (deleted at the next build)
    return fighters


def _reader(target):
    """earlier(file name) -> the bytes of that file of shared/ `target` as it is now, or None."""
    def earlier(name):
        path = os.path.join(target, name)
        if not os.path.isfile(path):
            return None
        with open(path, 'rb') as f:
            return f.read()
    return earlier
