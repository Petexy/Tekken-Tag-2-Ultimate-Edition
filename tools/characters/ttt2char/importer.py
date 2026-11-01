"""The importer's steps: check the inputs, convert, write the pack (import_character.py is the command line).

A fighter comes from Tekken 7 or Tekken 8 (characters.game_of); its source (source.py) gives the model, pictures and
voice from that game, and everything after it is the same for both. Its moveset is converted from the fighter's own
(Tekken 7: TKMovesets2's .tkmvst files, through the id maps two Heihachis give; Tekken 8, MOVESET_SOURCE 'tekken8':
the files the running game's own reader saved, tekken8/autodump.py, through id maps from TTT2's movesets and the
other Tekken 8 fighters saved with it), or, with MOVESET_SOURCE 'donor', the donor's TTT2 moveset stands in for it
(stand_in_moveset). A Tekken 8 fighter whose moveset cannot be had (none saved, and the game could not be run to
save it) is imported with its STAND_IN as the donor, fighting with that donor's moveset (with_stand_in).
"""
import collections
import json
import os
import struct
import time
import types

from . import InputError, pack, shared, source as sources
from .characters import CHARACTERS, GAMES, definition, game_of
from .convert import art, chains, cloth, effects as fx, face, gauge, idmaps, itemdb, model, move_overrides, movelist, \
    moveset, outfits, particles, sounds, tagsystem, tiger, voice, weapons
from .tekken7 import tkmvst
from .tekken7.autodump import FILES, unread
from .tekken7.pak import EncryptedError, Paks, pak_names
from .ttt2 import bone, motbin, title_folder
from .ttt2.archive import Archives, key_of
from .ttt2.rpx import Rpx

HEIHACHI = 8          # Tekken 7's roster id of Heihachi Mishima, the fighter both games share (for the id maps)
MOVESET_HEADER_ID = 0xF8 + 32 * 2   # a TTT2 moveset's character id fields (id-1, -(id-1), id, -id: its motion row)

TKMOVESETS_HELP = (
    'Save the movesets with TKMovesets2 (github.com/Kiloutre/TKMovesets) while Tekken 7 runs: Practice mode with '
    '%s as player 1 and Heihachi as player 2, then "Extract (all)" (any compression). The two .tkmvst files it '
    'writes to its extracted_chars folder are what --movesets needs.')


def tekken7_paks(folder):
    """The Paks of the player's Tekken 7 PC installation (the folder holding TekkenGame/)."""
    paks = os.path.join(folder or '', 'TekkenGame', 'Content', 'Paks')
    if not folder or not pak_names(paks):
        raise InputError('--tekken7 must be your own Tekken 7 PC installation, the folder holding TekkenGame/ '
                         '(Steam: Library > Tekken 7 > Manage > Browse local files); found no pak files in %s'
                         % paks)
    return paks


tekken8_folder = sources.tekken8_folder         # (there: launcher.py finds Tekken 8 without numpy)


def ttt2_folder(folder):
    """The installed Tekken Tag Tournament 2's title folder (code/, content/, meta/): `folder`, or its game/."""
    if folder and os.path.isfile(folder):
        raise InputError('--game must be the folder Tekken Tag Tournament 2 is installed in, not the file %s'
                         % os.path.basename(folder))
    title = title_folder(folder)
    if title is None:
        raise InputError('%s is no installed Tekken Tag Tournament 2 (no content/hdd in it or its game/): --game must '
                         'be the folder the game is installed in' % (folder or 'the --game folder'))
    return title


saved_movesets = tkmvst.saved_movesets          # (there: launcher.py reads them without numpy)


def find_movesets(folder, d):
    """The fighter's and Heihachi's .tkmvst files in `folder`."""
    if not folder or not os.path.isdir(folder):
        raise InputError('--movesets must be the folder with the .tkmvst files. ' + TKMOVESETS_HELP % d.NAME)
    found = saved_movesets(folder)
    missing = [who for who, i in ((d.NAME, d.TEKKEN7_ID), ('Heihachi', HEIHACHI)) if i not in found]
    if missing:
        raise InputError('%s has no Tekken 7 moveset of %s. ' % (folder, ' and '.join(missing))
                         + TKMOVESETS_HELP % d.NAME)
    return found[d.TEKKEN7_ID], found[HEIHACHI]


def stand_in(d):
    """Whether fighter d fights with its donor's moveset for now (MOVESET_SOURCE 'donor'), not its own converted."""
    return getattr(d, 'MOVESET_SOURCE', None) == 'donor'


def converts_tekken8(d):
    """Whether fighter d's own Tekken 8 moveset is converted (MOVESET_SOURCE 'tekken8')."""
    return game_of(d) == 'tekken8' and getattr(d, 'MOVESET_SOURCE', None) == 'tekken8'


def with_stand_in(d):
    """Fighter d as it is imported when its own Tekken 8 moveset cannot be had: its STAND_IN (a TTT2 fighter's code
    and motion row) is the donor of everything (skeleton, face joints, voice list, item database, the runtime's
    donor: the face animations set the face joints' absolute positions, so the skeleton is the moveset owner's), and
    it fights with that donor's moveset (MOVESET_SOURCE 'donor'). WITHOUT_OWN_MOVESET marks its pack (character.ini
    stand_in): the launcher offers to update it once its own moveset can be had."""
    donor, row = d.STAND_IN
    fields = {k: v for k, v in vars(d).items() if not k.startswith('__')}
    fields.update(DONOR=donor, DONOR_ROW=row, MOVESET_SOURCE='donor', WITHOUT_OWN_MOVESET=True)
    return types.SimpleNamespace(**fields)


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def tekken8_moveset(d, folder):
    """Fighter d's own Tekken 8 moveset as tekken8/autodump.py saved it in `folder` (None: its MOVESETS), read: ((the
    moveset (tekken8.motbin.read), its files (autodump.saved_files), the other fighters saved there [(code, motbin
    path, fields path)]), None), or (None, why it cannot be had). A moveset saved from an older version of the game
    is taken as it is (import_character.py saves it again first when it can)."""
    from .tekken8 import autodump as dump8, motbin as motbin8
    folder = folder or dump8.MOVESETS
    files = dump8.saved_files(d.TEKKEN8_CODE, folder)
    if not dump8.whole(files):                  # (a reference's motbin alone, saved with another fighter, is none)
        return None, 'its Tekken 8 moveset is not saved in %s' % folder
    try:
        k = motbin8.read(_read(files['motbin']), _read(files['fields']), d.TEKKEN8_CODE)
    except (OSError, InputError) as error:
        return None, 'its Tekken 8 moveset in %s cannot be read (%s)' % (folder, error)
    references = []
    for code in dump8.saved_codes(folder):
        other = dump8.saved_files(code, folder) if code != d.TEKKEN8_CODE else None
        if other is not None:
            references.append((code, other['motbin'], other['fields']))
    return (k, files, references), None


def run(name, tekken7, movesets, game, out=None, log=print, make_shared=True, files=FILES, tekken8=None, outfits=True):
    """Imports fighter `name`; returns the pack's folder. movesets: the folder of the fighter's saved movesets
    (Tekken 7: the .tkmvst files; Tekken 8: tekken8/autodump.py's, None: its MOVESETS). make_shared: also remake what
    the packs share (shared/; an import of several fighters makes it once, after the last). files: the folder of the
    files Tekken 7 keeps encrypted, as the game reads them (tekken7/autodump.py saves them). tekken8: the Tekken 8
    installation (a Tekken 8 fighter's, else for shared/ when a Tekken 8 fighter's pack is installed; None: found
    through Steam). outfits: also build the definition's preset outfits (PRESETS: a complete body each, most of an
    import's time); without them the pack has the default costume only."""
    try:
        return _run(name, tekken7, movesets, game, out, log, make_shared, files, tekken8, outfits)
    except EncryptedError as error:
        raise _not_saved(error.args[0], name)


def _not_saved(path, name=None):
    """The InputError of a file Tekken 7 keeps encrypted that is not saved (pak.py's EncryptedError), for fighter
    `name` (None: one of the added fighters): why, when the game did not read it in this run (autodump's unread)."""
    if path in unread:
        return InputError('%s needs %s, which Tekken 7 did not read: %s. Let Steam verify Tekken 7\'s files (and '
                          'move a mod\'s paks out of its Paks folder), then try again'
                          % (definition(name).NAME if name else 'An added fighter', path, unread[path]))
    return InputError('Tekken 7 keeps %s encrypted and it has not been saved from the running game yet: run '
                      'dump_tekken7.py %s (or import_character.py, which runs it) with Steam running'
                      % (path, name or 'for that fighter'))


def make_shared(tekken7, game, out=None, log=print, files=FILES, tekken8=None):
    """Remakes what the packs in `out` share (shared/) for the packs there now, from the games' files (each fighter's
    own game, and TTT2): after imports with make_shared=False, or after packs were removed. tekken7 / tekken8: the
    installations (needed when a fighter of that game is installed). -> shared.build's [(slot, definition, pack
    folder)]."""
    game = ttt2_folder(game)
    out = pack.output_folder(out)
    step = _steps(log)
    needed = sorted({game_of(d) for d in _installed(out)})
    if 'tekken7' in needed:
        tekken7_paks(tekken7)                   # (said before anything is read)
    step('reading %s and Tekken Tag Tournament 2 (%s)' % (
        ' and '.join('%s (%s)' % (GAMES[g], tekken7 if g == 'tekken7' else tekken8 or 'found through Steam')
                     for g in needed) or 'no other game', game))
    try:
        return _shared(sources.Sources(tekken7, tekken8, files), _archives(game), _rpx(game), out, log, step)
    except EncryptedError as error:
        raise _not_saved(error.args[0])


def _installed(out):
    """The definitions of the fighters whose packs in `out` shared/ is made for (shared.fighters_of)."""
    return [d for _, d, _ in shared.fighters_of(out, _known())]


def _known():
    known = {}
    for name in CHARACTERS:
        other = definition(name)
        known[other.CODE] = other
    return known


def _steps(log):
    """step(text): logs the text after the seconds from now."""
    start = time.time()
    return lambda text: log('%5.1f s  %s' % (time.time() - start, text))


def _paks(paks_dir, files):
    try:
        return Paks(paks_dir, saved=files)
    except (OSError, ValueError, struct.error) as error:
        raise InputError('cannot read the pak files in %s (%s): let Steam verify Tekken 7\'s files' % (paks_dir, error))


def _archives(game):
    try:
        return Archives(game)
    except (OSError, ValueError, struct.error) as error:
        raise InputError('cannot read the archives in %s (%s): install Tekken Tag Tournament 2 again' % (game, error))


def _rpx(game):
    try:
        return Rpx.of_game(game)
    except (OSError, ValueError) as error:
        raise InputError('cannot read the game\'s executable in %s (%s): install Tekken Tag Tournament 2 again'
                         % (game, error))


def _shared(source_of, archives, rpx, out, log, step):
    """source_of(d): fighter d's source (source.Sources)."""
    step('what the added fighters share: their pictures in the title\'s screens, colours and name calls')
    together = shared.build(source_of, archives, rpx, out, _known(), log=lambda s: log('         ' + s))
    if together:
        step('wrote %s for %s' % (os.path.join(out, pack.SHARED), ', '.join('%s (place %d)' % (f[1].NAME, f[0])
                                                                           for f in together)))
    else:
        step('no added fighter left: %s is gone' % os.path.join(out, pack.SHARED))
    return together


def spring_file(archives, d, bon, cloth_springs):
    """The spring entries (.mop) of a body's extra bones (bon: its .bon), on the donor's: the tiger's, the hanging
    chains', the cloth's (cloth_springs: model.convert's) and the weapons' still ones. -> bytes, or None without any."""
    skel = bone.read(bon)
    donor_mop = archives.read_name(d.DONOR + '.mop') if archives.has(key_of(d.DONOR + '.mop')) else None
    mop = None
    if getattr(d, 'TIGER', None):
        mop = tiger.spring_file(archives.read_name(d.DONOR + '.mop'),
                                archives.read_name(tiger.SPRING_TEMPLATE[0] + '.mop'),
                                sum(1 for n in skel['opt'] if tiger.OPT_FIRST <= n < weapons.OPT_FIRST))
    swinging = [n for n in skel['opt'] if chains.OPT_FIRST <= n < cloth.OPT_FIRST]
    if swinging:
        template = archives.read_name(chains.SPRING_TEMPLATE[0] + '.mop')
        mop = chains.spring_file(mop or donor_mop or chains.empty_spring_file(template), template, swinging)
    if cloth_springs:                             # cloth: Lars's coat tails' entries, leg capsules, pairs and links
        template = cloth.template(archives)
        mop = cloth.spring_file(mop or donor_mop or chains.empty_spring_file(template), template, cloth_springs)
    still = [n for n in skel['opt'] if n >= weapons.OPT_FIRST]
    if still:                                     # weapons: still extra bones (Devil Jin's wing entry, flag 8)
        template = archives.read_name(tiger.SPRING_TEMPLATE[0] + '.mop')
        mop = chains.spring_file(mop or donor_mop or chains.empty_spring_file(template), template, still,
                                 template=tiger.SPRING_TEMPLATE[1], links=False)
    return mop


def stand_in_moveset(donor, row, name):
    """The donor's moveset (a TTT2 motbin, data006) as the added fighter's own while it has none (MOVESET_SOURCE
    'donor'): its header's character id fields made its motion row `row` and its name `name`, as
    moveset.Converter.write makes them; its aliases, tables and embedded motions are the donor's as they are."""
    m = motbin.read(donor)
    hdr, strings, blob, slots = motbin.split(m)
    hdr = bytearray(hdr)
    struct.pack_into('>4H', hdr, MOVESET_HEADER_ID, row - 1, (-(row - 1)) & 0xFFFF, row, (-row) & 0xFFFF)
    strings = bytearray(strings)
    while strings and strings[-1] == 0:          # (its alignment), then the name after the donor's strings
        strings.pop()
    strings.append(0)
    name_off = len(strings)
    strings += name.encode('latin1') + b'\0'
    old = struct.unpack_from('>4I', hdr, 8)
    return motbin.build(hdr, bytes(strings), m.tables, blob, slots, name_offsets=(name_off,) + old[1:])


def _source(d, tekken7, tekken8, files):
    """The game folder fighter d is read from (checked) and how to open its source."""
    if game_of(d) == 'tekken8':
        folder = tekken8_folder(tekken8)
        return folder, lambda: sources.open_tekken8(folder)
    paks_dir = tekken7_paks(tekken7)
    return tekken7, lambda: sources.Tekken7Source(_paks(paks_dir, files))


def _run(name, tekken7, movesets, game, out, log, make_shared, files, tekken8, make_outfits):
    d = definition(name)
    folder, open_source = _source(d, tekken7, tekken8, files)
    saved8 = None
    if converts_tekken8(d):             # (decided before the model: the donor's skeleton is the base of hers)
        saved8, why = tekken8_moveset(d, movesets)
        if saved8 is None:
            log('WARNING: %s\'s own moveset cannot be had: %s (import_character.py saves it while Steam runs). %s '
                'is imported with %s\'s TTT2 moveset instead (and that fighter\'s skeleton and voice list).'
                % (d.NAME, why, d.NAME, art.NAME_TEXTS.get(d.STAND_IN[0], d.STAND_IN[0]).title()))
            d = with_stand_in(d)
    own, heihachi = find_movesets(movesets, d) if game_of(d) == 'tekken7' and not stand_in(d) else (None, None)
    game = ttt2_folder(game)
    out = pack.output_folder(out)
    step = _steps(log)

    step('reading %s (%s) and Tekken Tag Tournament 2 (%s)' % (GAMES[game_of(d)], folder, game))
    source = open_source()
    archives = _archives(game)
    if not archives.has(key_of(d.DONOR + '.xml')):
        raise InputError('%s has no %s files: is it the Wii U game\'s folder?' % (game, d.DONOR))

    slot = pack.choose_slot(out, d.CODE)
    if slot is None:
        raise InputError('the game has room for %d added fighters and %s holds them already: delete one\'s folder '
                         'first' % (pack.MAX_FIGHTERS, out))
    pack.target_of(out, d)          # (where the pack goes can take it: checked before the minute converting takes)
    place = pack.place(slot)
    rpx = _rpx(game)
    if any(p['code'] == d.CODE and not p['current'] for p in pack.installed(out)):
        step('%s\'s pack in %s was made by an older importer: it is replaced whole (place %d kept)'
             % (d.NAME, out, slot))

    step('model: %s (place %d)' % (d.NAME, slot))
    own_moveset = tkmvst.read(own) if own is not None else None
    standing = cloth.standing(own_moveset) if own_moveset is not None and game_of(d) == 'tekken7' else None
    nud, nut, bon, palettes, cloth_springs = model.convert(source, archives, d, slot,
                                                           log=lambda s: log('         ' + s.strip()),
                                                           standing=standing)
    donor_xml = archives.read_name(d.DONOR + '.xml')
    effect_files, _, _ = fx.copy_files(archives, d.DONOR, itemdb.effect_names(donor_xml), {},
                                       log=lambda s: log('         ' + s))
    part3, opt_anims = None, {}
    if getattr(d, 'TIGER', None):
        step('tiger: its animations and its bones\' spring entries')
        part3, opt_anims = tiger.animations(source.paks, d, bone.read(bon), log=lambda s: log('         ' + s.strip()))
    mop = spring_file(archives, d, bon, cloth_springs)

    step('pictures: %s\'s %s pictures for the loading and VS screens and the costume chooser' % (d.NAME, source.NAME))
    pictures = art.pack_files(source, archives, rpx, d, slot, log=lambda s: log('         ' + s))

    step('voice: %s\'s %s voice in %s\'s sound banks' % (d.NAME, source.NAME, d.DONOR))
    effects = None
    if own_moveset is not None and game_of(d) == 'tekken7' and gauge.of(d):
        effects = sounds.Effects(source.paks, d.TEKKEN7_CODE, own_moveset, idmaps.xps,
                                 lambda name: not sounds.LEFT_OUT.search(name),
                                 extra=[s for s in (gauge.full_sound(d),) if s])
        effects.base = sounds.item_count(rpx, d.DONOR)
    try:
        clips = source.clips(d)
        if saved8 is not None:              # (Tekken 8: the lines her own moves say, shouts after hers)
            clips.add_lines(saved8[0])
        vlist = voice.voice_list(rpx, d.DONOR)
        banks, lines, wins, voice_extra, sound_extra = voice.build(
            clips, {w: archives.raw(key_of('%s_%s.nus3bank' % (w, d.DONOR))) for w in ('se_Chr', 'se_Dwi', 'rm_Dst',
                                                                                     'rm_Dwi')}, d.CODE, vlist, slot,
            effects.clips if effects else ())
    except KeyError as error:
        raise InputError('%s has no %s voice files (%s): is it the Wii U game\'s folder?' % (game, d.DONOR, error))
    merged, chr_tones = voice.merge(banks.pop('se_Chr_%s.nus3bank' % d.CODE), banks.pop('se_Dwi_%s.nus3bank' % d.CODE))
    banks['se_Chr_%s.nus3bank' % d.CODE] = merged
    lines.append('se_Chr_%s: with se_Dwi_%s\'s tones after its %d (one bank in a match), %d KB'
                 % (d.CODE, d.CODE, chr_tones, len(merged) // 1024))
    if effects:
        lines.append('sound effects (its moves\' and projectiles\' item sounds %d on): %s'
                     % (effects.base, ', '.join(effects.names)))
    for line in lines:
        log('         ' + line)

    if stand_in(d):
        step('moveset: %s\'s moveset and motions stand in for %s\'s (motion row %d; the command list is %s\'s)'
             % (d.DONOR, d.NAME, place['row'], d.DONOR))
        moves = stand_in_moveset(archives.entry('data006', d.DONOR_ROW), place['row'], d.MOVESET['name'])
        motions = archives.entry('data005', d.DONOR_ROW)
        xml = itemdb.body_only(donor_xml)
        effect_files = fx.still_named(effect_files, itemdb.effect_files_named(xml))
        mvl = None
        if not archives.has(key_of(d.DONOR + '.mvl')):
            log('         WARNING: the game has no %s.mvl: no command list in Practice' % d.DONOR)
    elif saved8 is not None:
        moves, motions, xml, effect_files, mvl = _converted_tekken8_moveset(source, archives, d, place, saved8,
                                                                            donor_xml, effect_files, wins, vlist,
                                                                            voice_extra, bon, log, step,
                                                                            clips.move_voices(voice.voice_values(
                                                                                clips, vlist)))
    else:
        moves, motions, xml, effect_files, mvl = _converted_moveset(source.paks, archives, d, slot, place, own_moveset,
                                                                    heihachi, donor_xml, effect_files, wins, vlist,
                                                                    voice_extra, opt_anims, part3, bon, log, step,
                                                                    effects)

    lids = face.tekken7_lids(tkmvst.face_animations(own_moveset)) if own_moveset is not None else None
    moves, motions, changed, lid_scales = face.retarget(moves, motions, bone.read(bon),
                                                        bone.read(archives.read_name(d.DONOR + '.bon')), lids)
    if changed:
        log('         face animations moved with its face joints: %d%s' % (changed, ''.join(
            ', %s turned x%.2f' % (name.replace('_Joint', ''), sc) for name, sc in sorted(lid_scales.items()))))

    contents = {'.xml': xml, '.nud': nud, '.nut': nut, '.bon': bon, '.moveset': moves, '.motion': motions}
    contents.update(banks)
    contents.update(pictures)
    if gauge.of(d):
        step('gauge: %s\'s gauge and its HUD from %s' % (d.NAME, source.NAME))
        contents.update(gauge.hud_files(source.paks, d, log=lambda s: log('         ' + s)))
    contents.update(effect_files)
    if mvl is not None:
        contents['.mvl'] = mvl
    if mop is not None:
        contents['.mop'] = mop
    if palettes:
        contents['colours.json'] = json.dumps({str(nn): v for nn, v in sorted(palettes.items())}).encode('utf-8')
    outfit_codes = []
    if make_outfits and getattr(d, 'PRESETS', ()):          # (outfits: the module that makes them)
        step('preset outfits: complete bodies for the in-game costume chooser')
        contents.update(outfits.build(source.paks, archives, rpx, d, slot, xml,
                                   lambda bon, cloth_springs: spring_file(archives, d, bon, cloth_springs),
                                   (nud, nut, bon, mop), standing=standing,
                                   log=lambda s: log('         ' + s.strip()), reference_bon=bon))
        outfit_codes = [c for c in outfits.codes(d) if c + '.nud' in contents]     # (but presets left out)
    gauge_sound = effects.number(gauge.full_sound(d)) if effects and gauge.full_sound(d) else None
    target = pack.write(out, d, contents, slot, chr_tones=chr_tones, voice_extra=voice_extra, sound_extra=sound_extra,
                        gauge_sound=gauge_sound,
                        weapons=weapons.of_skeleton(bone.read(bon), getattr(d, 'WEAPONS', ())), outfits=outfit_codes)
    step('wrote %s' % target)

    if make_shared:
        _shared(sources.Sources(tekken7, tekken8, files, opened=[source]), archives, rpx, out, log, step)
    return target


def _converted_moveset(paks, archives, d, slot, place, k, heihachi, donor_xml, effect_files, wins, vlist, voice_extra,
                       opt_anims, part3, bon, log, step, effects=None):
    """The fighter's own Tekken 7 moveset converted (k: its tkmvst.read), with its effects and command list ->
    (moveset bytes, motion pack bytes, item database, effect files, command list or None)."""
    step('moveset: the id maps from Heihachi in both games')
    h7 = tkmvst.read(heihachi)
    evidence = collections.defaultdict(idmaps.Evidence)
    for who, row in d.ALIGN:
        idmaps.align(k if who == 'self' else h7, motbin.read(archives.entry('data006', row)), evidence)
    req, prop = idmaps.build_maps(evidence)
    maps = (req, prop, idmaps.reaction_remap(evidence), idmaps.hitbox_remap(evidence))
    ttt2_movesets = [motbin.read(archives.entry('data006', row)) for row in range(58)]
    usage = idmaps.ttt2_usage(ttt2_movesets)
    tag_states = tagsystem.TagStates(ttt2_movesets)     # movement states: tag out (walking back, ...)
    del ttt2_movesets

    step('moveset: converting')
    c = moveset.Converter(k, h7, motbin.read(archives.entry('data006', d.DONOR_ROW)),
                          archives.entry('data005', d.DONOR_ROW), motbin.read(archives.entry('data006', 13)),
                          archives.entry('data004', 0), maps, usage, place['row'], d)
    _options(c, archives, d, wins, vlist, voice_extra, tag_states, bon)
    c.opt_anims, c.part3 = opt_anims, part3
    c.effects = effects
    c.run()
    copies = c.split_effects(particles.emitting_frames(paks, d.TEKKEN7_CODE, c.effect_ids),
                             set(c.projectile_effects) | set(itemdb.effect_ids(donor_xml)))
    moves, motions = c.write()
    for line in c.summary():
        log('         ' + line)

    step('effects: the Tekken 7 effects %s\'s moves spawn' % d.NAME)
    own_files, own_effects = particles.convert_fighter(
        paks, archives, d.TEKKEN7_CODE, c.effect_ids | {particles.HIT_EFFECT},
        model.GIDX_BASE + model.SLOT_GIDX * slot + particles.FIRST_ID, c.projectile_effects,
        log=lambda s: log('         ' + s), copies=copies)
    xml = itemdb.body_only(donor_xml, {i: [(name, None) for name in names] for i, names in own_effects.items()})
    effect_files = fx.still_named(effect_files, itemdb.effect_files_named(xml))    # the donor's not replaced
    effect_files.update(own_files)

    mvl = None
    if k.movelist[:4] == b'MVLT':
        step('command list')
        mvl = movelist.convert(k.movelist, log=lambda s: log('         ' + s),
                               bounds=move_overrides.command_bounds(c))     # the definition's bounds' icons
    return moves, motions, xml, effect_files, mvl


def _options(c, archives, d, wins, vlist, voice_extra, tag_states, bon):
    """What moveset.Converter c takes from the import besides the movesets (both games): the definition's gameplay
    options' reference movesets, the win quotes' tones, the shouts' count, the movement states, the hit locations."""
    if d.MOVESET.get('electric_tag_exit'):
        c.electric_pack = archives.entry('data005', 13)
    c.air_reaction_references = {spec[0]: motbin.read(archives.entry('data006', spec[0]))
        for spec in d.MOVESET.get('air_reactions', {}).values() if isinstance(spec, tuple)}
    if 'air_reaction_reference' in d.MOVESET:
        c.air_reaction_reference = motbin.read(archives.entry('data006', d.MOVESET['air_reaction_reference']))
    if d.MOVESET.get('stance_reference'):
        c.stance_reference = motbin.read(archives.entry('data006', d.MOVESET['stance_reference'][0]))
    c.win_tones = wins
    c.shouts = sum(1 for mask, _ in vlist if mask & voice.KIAI) + len(voice_extra)
    c.tag_states = tag_states
    c.hit_locations = dict(getattr(d, 'HIT_LOCATIONS', {}))     # Tekken 7 hit locations TTT2 numbers otherwise
    c.hit_locations.update(weapons.points_of(bone.read(bon)['names']))         # ... and its weapons' points


def _converted_tekken8_moveset(source, archives, d, place, saved, donor_xml, effect_files, wins, vlist, voice_extra,
                               bon, log, step, voices8=None):
    """The fighter's own Tekken 8 moveset converted (saved: tekken8_moveset's), with its command list -> (moveset
    bytes, motion pack bytes, item database, effect files, command list or None). Its moves are named from TTT2's
    movesets, the id maps come from those and the other Tekken 8 fighters saved with it (their moves named alike),
    its body animations are retargeted onto the skeleton the model step built (bon), TTT2's own where an older
    shared clip was made from one. Tekken 8's effects are not converted: the donor's stay (as with a stand-in).
    voices8: the TTT2 voice of each of its moves' Tekken 8 voices (tekken8/voice.py's move_voices on the banks the
    voice step built)."""
    from .tekken8 import anim, anmbin, motbin as motbin8, movelist as movelist8, movenames, voice as voice8
    k, files, references = saved

    def sub(s):
        log('         ' + s)
    step('moveset: %s\'s move names from TTT2\'s movesets' % d.NAME)
    ttt2_movesets = movenames.ttt2_movesets(archives)
    movenames.name_known(k, [n.encode('ascii') for n in d.MOVESET.get('move_name_seeds', ())])
    movenames.name_moves(k, ttt2_movesets, log=sub)
    dictionary = movenames.harvest(ttt2_movesets)[0]
    others = []
    for code, motbin_path, fields_path in references:
        try:
            other = motbin8.read(_read(motbin_path), _read(fields_path), code)
        except (OSError, InputError) as error:
            sub('the saved moveset of %s is left out: %s' % (code, error))
            continue
        movenames.name_known(other, dictionary)
        others.append(other)

    step('moveset: the id maps from TTT2\'s movesets and %d other Tekken 8 fighters\'' % len(others))
    req, prop, reactions, hitboxes, _ = idmaps.tekken8_maps([k], ttt2_movesets, references=others)
    fighters = ttt2_movesets[:58]                       # (the fighters' motion rows, as for Tekken 7)
    usage = idmaps.ttt2_usage(fighters)
    tag_states = tagsystem.TagStates(fighters)         # movement states: tag out (walking back, ...)

    step('moveset: converting (%s\'s animations onto the skeleton built for the model)' % d.NAME)
    own_bank, common_bank = anmbin.Bank(files['anmbin']), anmbin.Bank(files['common'])
    try:
        k.attach_banks(motbin8.read_bank(files['anmbin']), motbin8.read_bank(files['common']))
        banks = anmbin.Banks(own_bank, common_bank, k.character_id)
        common = archives.entry('data004', 0)
        animations = anim.Animations(banks, anim.Converter(anim.load_skeleton(source.store, d.TEKKEN8_CODE),
                                                           bone.read(bon)),
                                     anim.originals(k, banks, ttt2_movesets, common,
                                                    lambda row: archives.entry('data005', row), d.DONOR_ROW))
        c = moveset.Converter(k, None, ttt2_movesets[d.DONOR_ROW], archives.entry('data005', d.DONOR_ROW),
                              ttt2_movesets[13], common, (req, prop, reactions, hitboxes), usage, place['row'], d)
        c.animations = animations
        # (the win poses play the quote of their tone: the fighter's lines are its win moves', zbr_w01's
        # Play_zbr_win_01)
        _options(c, archives, d, {voice8.pose_move(n) or n: tone for n, tone in wins.items()}, vlist, voice_extra,
                 tag_states, bon)
        c.voices8 = voices8 or {}           # her moves' Tekken 8 voices -> the TTT2 voices of the same lines
        c.run()
        moves, motions = c.write()
    finally:
        own_bank.close()
        common_bank.close()
    for line in c.summary():
        sub(line)
    for key, n in sorted(animations.stats.items()):
        sub('%s: %d' % (key, n))
    sub('body animations converted in %.1f s' % animations.seconds)
    if c.projectile_effects:
        sub('WARNING: %d projectile looks are not converted (Tekken 8 effects): those projectiles fly unseen'
            % len(c.projectile_effects))
    electric = None
    if c.electric_moves:                # Tekken 8 electrics: Kazuya's lightning, a copy of his TTT2 effect file
        effect_files, electric, _ = fx.copy_files(archives, d.DONOR, itemdb.effect_names(donor_xml),
                                                  {moveset.ELECTRIC_EFFECT: [(moveset.ELECTRIC_LOOK, None)]})
        sub('electrics with Kazuya\'s lightning (%s, effect id %d): %s'
            % (moveset.ELECTRIC_LOOK, moveset.ELECTRIC_EFFECT, ', '.join(c.electric_moves)))
        if not electric:
            sub('WARNING: the game has no %s: the electrics show no lightning' % moveset.ELECTRIC_LOOK)
    xml = itemdb.body_only(donor_xml, electric)
    effect_files = fx.still_named(effect_files, itemdb.effect_files_named(xml))

    step('command list')
    mvl = None
    entries = {key: (hit, d.MOVESET['bounds'][name])
               for key, (name, hit) in d.MOVESET.get('bound_entries', {}).items()}
    try:
        mvl = movelist8.convert(_read(files['mvl']), source.store, log=sub,
                                bounds=move_overrides.command_bounds(c), bound_entries=entries)     # the definition's bounds' icons
    except (OSError, ValueError, KeyError, IndexError, struct.error) as error:
        sub('WARNING: the command list could not be converted (%s): Practice shows %s\'s' % (error, d.DONOR))
    if mvl is None:
        sub('no command list of %s\'s own: Practice shows %s\'s' % (d.NAME, d.DONOR))
    return moves, motions, xml, effect_files, mvl
