"""Replace native TTT2 Hwoarang's combat moveset with converted, owned T8 data.

Writes three loose archive overrides, never original archives or model assets.
--out is a staging directory. Install it as characters/native/hwo after closing
the game; removing that directory restores the original Hwoarang.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from . import InputError, importer, source
from .convert import idmaps as M, moveset, native_moves, tagsystem as TS, weapons
from .tekken8 import anim, anmbin, motbin, movelist, movenames
from .ttt2 import bone, motbin as native_motbin

ROW = 6
KEYS = (0xc5b3cee7, 0xaadc2a27, 0x776053e5)


# Source names not yet recovered use validated signatures, not unchecked indices.
BOUND_FINISHERS = {
    '#1810': (0xea3bed2f, 9, 18),   # Right Flamingo u/f+3
    '#1766': (0x893d3e73, 9, 13),   # RFF b+2 (native Bound restored)
    '#1614': (0xf0792ab0, 9, 14),   # 4,4,3; RFF 2,4,3 / 4,3; RFS 2,4,3
    '#1681': (0x492986f1, 8, 14),   # WR3
    '#1813': (0x62e95622, 10, 14),  # RFF f,f+3
    '#1825': (0x0a1e027c, 7, 16),   # normal f,f+3 (separate from WR3)
    '#1878': (0x18b2635b, 9, 15),   # RFS d/f+4
    '#1596': (0xe53991ef, 9, 15),   # LFS 3,2
    '#1852': (0xc0e85d32, 10, 24),  # LFS 1+2,4
    '#1538': (0x9277ec1d, 10, 16),  # u/f+3,4,3: third hit only
    '#1529': (0xf2fdcb26, 13, 16),  # same third hit from Left Flamingo
}
BACKLASH = '#1879'


def verify_signatures(k):
    for label, expected in dict(BOUND_FINISHERS, **{BACKLASH: (0xfbc25015, 11, 12)}).items():
        index = int(label[1:])
        row = k.tables['moves'][index]
        if (row['name_key'], *k.name_lengths(index)) != expected:
            raise InputError('Hwoarang source changed; refusing an unchecked rule for ' + label)


def verify_flamingo_input_routes(k):
    # T8 cancel directions: d/f=0x8, u/f=0x200. Validate the real inputs,
    # not just signatures of a possibly misidentified attack.
    for stance, direction, button, target in ((1676, 0x200, 8, 1865),
                                              (1682, 0x200, 8, 1906), (1682, 0x8, 8, 1878),
                                              (1682, 0x200, 4, 1810)):
        found = set()
        for row in M.cancels(k, k.tables['moves'][stance]['cancel']):
            group = M.cancels(k, row['move_id'], 'group_cancels', M.GROUP_END) if row['direction'] == M.GROUP else [row]
            for candidate in group:
                if candidate['direction'] == direction and candidate['button'] & 0xffff == button:
                    found.add(candidate['move_id'])
        if found != {target}:
            raise InputError('Flamingo input route changed: stance %d direction %x -> %s' %
                             (stance, direction, sorted(found)))


def restore_native_assist_follow(c):
    """Retain native automatic TA chase in both neutral foot stances."""
    target = c.dn['DA_KamDash']
    for name in ('Hw_sKAM00_', 'Hw_sKAMR00_'):
        if name not in c.kn or c.kn[name] not in c.newidx:
            raise InputError('Hwoarang neutral stance missing: ' + name)
        native = c.d.tables['moves'][c.dn[name]]
        chase = []
        for row in TS.cancels(c.d.tables, native['cancel']):
            group = TS.chain(c.d.tables['group_cancels'], row['move_id'],
                             lambda q: q['direction'] == M.GROUP_END) if row['direction'] == M.GROUP else [row]
            chase += [dict(q) for q in group if q['direction'] == 0 and q['button'] == 0 and q['move_id'] == target]
        if len(chase) != 1:
            raise InputError('native automatic assist chase not unique: ' + name)
        move = c.T['moves'][c.newidx[c.kn[name]]]
        rows = [dict(q) for q in TS.cancels(c.T, move['cancel'])]
        present = False
        for row in rows:
            group = TS.chain(c.T['group_cancels'], row['move_id'],
                             lambda q: q['direction'] == M.GROUP_END) if row['direction'] == M.GROUP else [row]
            if any(q['direction'] == 0 and q['button'] == 0 and q['move_id'] == target for q in group):
                present = True
        if not present:
            move['cancel'] = TS.write(c.T, 'cancels', chase + rows)
            c.stats['native automatic Tag Assault chase routes restored'] += 1


def restore_native_jfsr_sparks(c):
    name = 'Hw_agerkFAST'
    native = c.d.tables['moves'][c.dn[name]]
    visual_ids = {0x8192, 0x802c, 0x803e, 0x8031}
    effects = [dict(p) for p in TS.props(c.d.tables, native['extraprops']) if p['id'] in visual_ids]
    if not any(p['id'] == 0x8031 for p in effects):
        raise InputError('native Just Frame Sky Rocket spark recipe is missing')
    move = c.T['moves'][c.newidx[c.kn[name]]]
    rows = [dict(p) for p in TS.props(c.T, move['extraprops'])
            if p['id'] not in visual_ids and not (p['id'] == moveset.EFFECT_PROP
                                                and p['value'] & 0xff == moveset.ELECTRIC_EFFECT)]
    rows += effects + [dict(frame=0, id=0, value=0)]
    move['extraprops'] = TS.write(c.T, 'extra_move_properties', rows)
    c.stats['native JFSR blue-spark recipes restored'] += 1


def filtered_conditional_props(tables, table, start):
    """Conditional properties end with id 690, unlike frame properties (id 0)."""
    if start is None:
        return None
    rows = [dict(row) for row in TS.chain(tables[table], start, lambda row: row['id'] == TS.TT_END)
            if row['id'] not in (0x8193, 0x8194, TS.TT_END)]
    return TS.write(tables, table, rows + [dict(req=0, id=TS.TT_END, value=0)]) if rows else None


def validate_conditional_props(tables):
    for move in tables['moves']:
        for table, key in (('move_begin_props', 'begin_props'), ('move_end_props', 'end_props')):
            start = move[key]
            if start is None:
                continue
            if not 0 <= start < len(tables[table]):
                raise InputError('conditional property list starts outside its table')
            terminated = False
            for row in tables[table][start:]:
                if row['id'] == TS.TT_END:
                    terminated = True
                    break
                req = row['req']
                if req is None or not 0 <= req < len(tables['requirements']):
                    raise InputError('conditional property has an invalid requirement pointer')
                if not any(r['condition'] == TS.TT_END for r in tables['requirements'][req:]):
                    raise InputError('conditional property requirements have no terminator')
            if not terminated:
                raise InputError('conditional property list has no TTT2 terminator (690)')


def restore_native_hunting_hawk_air(c):
    native = c.d.tables['moves'][c.dn['Hw_rsk02']]
    air = [hit for hit in TS.hits(c.d.tables, native['hit_condition'])
           if TS.reqs(c.d.tables, hit['req']) == [(TS.AIR, 0)]]
    if len(air) != 1:
        raise InputError('native Hunting Hawk final-hit airborne reaction is not unique')
    rx = c.add('reactions', dict(c.d.tables['reactions'][air[0]['reactions']]))
    changed = 0
    for index, move in enumerate(c.T['moves']):
        name = c.move_name(index)
        if not any(name == base or (name.startswith(base + 'T') and (not name[len(base)+1:] or name[len(base)+1:].isdigit()))
                   for base in ('Hw_#1529', 'Hw_#1538')):
            continue
        hits = [dict(hit) for hit in TS.hits(c.T, move['hit_condition'])]
        for hit in hits:
            if TS.has(c.T, hit['req'], TS.AIR) and not any(TS.has(c.T, hit['req'], flag)
                                                         for flag in (TS.BOUND, TS.BOUND_TAG)):
                hit['reactions'] = rx
                changed += 1
        move['hit_condition'] = TS.write(c.T, 'hit_conditions', hits)
    if changed < 2:
        raise InputError('both Hunting Hawk final-hit airborne routes were not restored')
    c.stats['Hunting Hawk native final-hit air reactions restored (including tag twins)'] += changed


def extend_rfs_df4_collision(c):
    """Keep the original foot sphere; extend only this move's second capsule.

    Runtime poses private item point 70 at the foot, 100 mm outward and lower.
    The original knee endpoint, active frames and hit level remain unchanged.
    """
    changed = 0
    for index, move in enumerate(c.T['moves']):
        name = c.move_name(index)
        base = 'Hw_#1878'
        if name != base and not (name.startswith(base + 'T') and
                                (not name[len(base)+1:] or name[len(base)+1:].isdigit())):
            continue
        a, b, foot, knee = move['hitbox']
        if (a, b, foot, knee) != (16, 0, 38, 15):
            raise InputError('RFS d/f+4 collision layout changed')
        move['hitbox'] = bytes((a, b, 70, knee))
        changed += 1
    if not changed:
        raise InputError('RFS d/f+4 collision move missing')
    c.stats['RFS d/f+4 private extended collision capsules'] += changed


def match_flamingo_uf4_reactions(c):
    """RFS u/f+4 takes LFS u/f+4's hit reactions, retaining its own block."""
    for label, signature in (('#1865', (0x6250d9d0, 9, 21)),
                             ('#1906', (0x26ac3cae, 9, 18))):
        index = c.kn[label]
        if (c.k.tables['moves'][index]['name_key'], *c.k.name_lengths(index)) != signature:
            raise InputError('Flamingo u/f+4 source signature changed: ' + label)
    reference = c.T['moves'][c.newidx[c.kn['#1865']]]
    templates = {tuple(TS.reqs(c.T, h['req'])): h['reactions']
                 for h in TS.hits(c.T, reference['hit_condition'])}
    changed = 0
    base = 'Hw_#1906'
    for index, move in enumerate(c.T['moves']):
        name = c.move_name(index)
        if name != base and not (name.startswith(base + 'T') and
                                (not name[len(base)+1:] or name[len(base)+1:].isdigit())):
            continue
        hits = [dict(h) for h in TS.hits(c.T, move['hit_condition'])]
        for hit in hits:
            conditions = tuple(TS.reqs(c.T, hit['req']))
            if conditions not in templates:
                raise InputError('RFS u/f+4 has an unmatched hit condition')
            own = c.T['reactions'][hit['reactions']]
            reaction = dict(c.T['reactions'][templates[conditions]])
            for key in ('block', 'crouch_block', 'pb_block'):
                reaction[key] = own[key]
            hit['reactions'] = c.add('reactions', reaction)
        move['hit_condition'] = TS.write(c.T, 'hit_conditions', hits)
        changed += 1
    if not changed:
        raise InputError('RFS u/f+4 target missing')
    c.stats['RFS u/f+4 hit reactions matched to LFS u/f+4'] += changed


def restore_native_rfs_b3(c):
    source = c.kn['#1894']
    if (c.k.tables['moves'][source]['name_key'], *c.k.name_lengths(source)) != (0xf6a1c76d, 9, 15):
        raise InputError('RFS b+3 source signature changed')
    native = c.d.tables['moves'][c.dn['Hw_jnblkAR']]
    original = [hit for hit in TS.hits(c.d.tables, native['hit_condition'])
                if not TS.reqs(c.d.tables, hit['req'])]
    if len(original) != 1:
        raise InputError('native RFS b+3 launch reaction is not unique')
    reaction = dict(c.d.tables['reactions'][original[0]['reactions']])
    for field in ('default', 'crouch', 'left', 'right', 'back'):
        if not c.T['moves'][reaction[field]]['airborne_start']:
            raise InputError('native RFS b+3 template is not a launcher')
    rx = c.add('reactions', reaction)
    move = c.T['moves'][c.newidx[source]]
    hits = [dict(hit) for hit in TS.hits(c.T, move['hit_condition'])]
    for hit in hits:
        if not any(TS.has(c.T, hit['req'], flag) for flag in (TS.AIR, TS.BOUND, TS.BOUND_TAG)):
            hit['reactions'] = rx
    move['hit_condition'] = TS.write(c.T, 'hit_conditions', hits)
    c.stats['RFS b+3 native TTT2 launch reaction restored'] += 1


def restore_backlash_tailspin(c):
    from .movesets import REACTION_MOVE_FIELDS
    original = c.k.tables['moves'][c.kn[BACKLASH]]
    matches = [ri for req, _, ri in M.hitconds(c.k, original['hit_condition'])
               if (723, 0) in req and (758, 200) in req]
    if len(matches) != 1:
        raise InputError('Backlash strong aerial reaction could not be identified')
    ri = matches[0]
    reaction = dict(c.T['reactions'][c.conv_reaction(ri)])
    c.link_queued({})
    original_reaction = c.k.tables['reactions'][ri]
    clones = {}
    for field in REACTION_MOVE_FIELDS:
        source_index = original_reaction[field]
        if source_index not in (46, 47):
            continue
        target = reaction[field]
        if target not in clones:
            row = dict(c.T['moves'][target], name=c.string(c.move_name(target) + '_STRONG_NB'))
            props = [dict(p) for p in TS.props(c.T, row['extraprops']) if p['id'] not in (0x8193, 0x8194)]
            row['extraprops'] = TS.write(c.T, 'extra_move_properties', props + [dict(frame=0, id=0, value=0)])
            for table, key in (('move_begin_props', 'begin_props'), ('move_end_props', 'end_props')):
                row[key] = filtered_conditional_props(c.T, table, row[key])
            clones[target] = c.add('moves', row)
        reaction[field] = clones[target]
    if len(clones) != 2:
        raise InputError('Backlash did not retain both strong aerial victim states')
    rx = c.add('reactions', reaction)
    move = c.T['moves'][c.newidx[c.kn[BACKLASH]]]
    hits = [dict(h) for h in TS.hits(c.T, move['hit_condition'])
            if not any(TS.has(c.T, h['req'], flag) for flag in (TS.AIR, TS.BOUND, TS.BOUND_TAG))]
    damage = next(damage for req, damage, reaction in M.hitconds(c.k, original['hit_condition']) if reaction == ri)
    req = TS.write(c.T, 'requirements', [dict(condition=TS.AIR, param=0), dict(condition=TS.TT_END, param=0)])
    move['hit_condition'] = TS.write(c.T, 'hit_conditions', [dict(req=req, damage=damage, reactions=rx)] + hits)
    c.stats['Backlash strong aerial tailspin without Bound'] += 1


def native_voice_categories(vlist, tone_kind):
    """Map T8 voice categories to original TTT2 list indices, not tone numbers."""
    from .convert import voice
    kinds = {}
    shouts = [(mask, tone) for mask, tone in vlist if mask & voice.KIAI]
    damage = [(mask, tone) for mask, tone in vlist if mask & voice.DAMAGE and not mask & voice.KIAI]
    for index, (_, tone) in enumerate(shouts):
        kinds.setdefault(tone_kind(tone), []).append(0x02000000 | index)
    for index, (_, tone) in enumerate(reversed(damage)):
        kinds.setdefault(tone_kind(tone), []).append(0x03000000 | index)
    attacks = [value for values in kinds.values() for value in values if value >> 24 == 2]
    hurt = [value for values in kinds.values() for value in values if value >> 24 == 3]
    out = {}
    for category, kind in ((0, ('atk', 's')), (1, ('atk', 'm')), (2, ('atk', 'l')),
                           (3, ('dmg', 's')), (4, ('dmg', 'l'))):
        values = kinds.get(kind) or (attacks if category < 3 else hurt)
        if values:
            out[17, category] = values
    for category in (6, 8, 11):
        if hurt:
            out[17, category] = hurt
    if attacks:
        out[17, 10] = kinds.get(('atk', 's')) or attacks
    return out, len(shouts), len(damage)


def redirect_native_references(tables, aliases, replacements):
    """Replace move indices, never group offsets, alias tokens or reaction indices."""
    for name in ('cancels', 'group_cancels'):
        for row in tables[name]:
            if row['direction'] not in (M.GROUP, M.LIST_END, M.GROUP_END):
                row['move_id'] = replacements.get(row['move_id'], row['move_id'])
    for row in tables['moves']:
        row['transition'] = replacements.get(row['transition'], row['transition'])
    return [replacements.get(index, index) for index in aliases]


def tornado_moves(k):
    """Source requirement 724 is the T8 Tornado condition, before remapping."""
    return {i for i, move in enumerate(k.tables['moves'])
            if any(any(condition == moveset.SCREW['t8'] for condition, _ in requirements)
                   for requirements, _, _ in M.hitconds(k, move['hit_condition']))}


class Replacement(moveset.Converter):
    def own_voice(self, value):
        bank, index = value >> 24, value & 0xffffff
        return (bank == 2 and index < self.shouts) or (bank == 3 and index < self.native_damage_count)

    def conv_voiceclips(self, start):
        # T8's 0x9986 is a mute marker, not a native Hwoarang shout number.
        values = [value for value in M.voices(self.k, start)
                  if value not in (moveset.UNSAID8, moveset.SILENT_SHOUT)
                  and (value in self.donor_clips or self.own_voice(value))]
        if not values:
            return None  # native automatic attack shouts, rather than shout 999
        return TS.write(self.T, 'voiceclips', [{'value': value} for value in values] + [{'value': 0xffffffff}])

    def _link_move(self, index, counterpart):
        super()._link_move(index, counterpart)
        name = self.name(index)
        if name in self.dn:
            self.T['moves'][self.newidx[index]]['voiceclip'] = self.d.tables['moves'][self.dn[name]]['voiceclip']
            self.stats['move-specific native voice lists restored'] += 1

    def rebuild_direct(self, donor_specific):
        # Native intros, win poses and their camera/voice choreography stay intact.
        pass

    def run(self):
        super().run()
        replacements = {old: self.newidx[self.kn[name]] for name, old in self.dn.items()
                        if name in self.kn and self.kn[name] in self.newidx
                        and name.startswith('Hw_') and name != 'Hw_Direct'}
        self.aliases = redirect_native_references(self.T, self.aliases, replacements)
        restore_native_assist_follow(self)
        self.stats['native Hwoarang moves redirected to T8'] = len(replacements)
        if self.aliases[1] == self.d.aliases[1]:
            raise InputError('Hwoarang replacement did not redirect the standing stance')
        # Old combat rows remain for native tag choreography, but must not
        # expose extra Bound attacks through legacy inputs or tag twins.
        for index, row in enumerate(self.T['moves'][:len(self.d.tables['moves'])]):
            name = self.move_name(index)
            if not name.startswith('Hw_'):
                continue
            hits = [dict(h) for h in TS.hits(self.T, row['hit_condition'])]
            if any(any(TS.has(self.T, h['req'], flag) for flag in (TS.BOUND, TS.BOUND_TAG)) for h in hits):
                hits = [h for h in hits if not any(TS.has(self.T, h['req'], flag) for flag in (TS.BOUND, TS.BOUND_TAG))]
                for hit in hits:
                    if TS.has(self.T, hit['req'], TS.AIR) and TS.same_reaction(self.T, hit['reactions'], self.bound_reaction):
                        hit['reactions'] = self.after_bound_reaction
                row['hit_condition'] = TS.write(self.T, 'hit_conditions', hits)
        restore_native_jfsr_sparks(self)
        restore_backlash_tailspin(self)
        restore_native_rfs_b3(self)
        restore_native_hunting_hawk_air(self)
        extend_rfs_df4_collision(self)
        match_flamingo_uf4_reactions(self)
        self.handoffs8()
        for n, row in enumerate(self.T['moves']):
            combined = (self.newid << 16) + n - (self.newid - 1)
            row['move_id_hi'], row['move_id_lo'] = combined >> 16 & 0xffff, combined & 0xffff
        if len(self.T['pushback_extras']) % 2:
            self.T['pushback_extras'].append({'value': 0})
        native_moves.validate_command_groups(self)
        validate_conditional_props(self.T)
        return self


def convert(game, saved, tekken8=None, log=print):
    saved = Path(saved)
    definition = SimpleNamespace(CODE='hwo', NAME='Hwoarang', DONOR='hwo', DONOR_ROW=ROW,
                                 TEKKEN8_CODE='snk', TEKKEN8_ID=4,
                                 MOVESET={'name': '[HWOARANG]',
                                          'drop_moves': r'^Hw_Direct$|^hw_[sw]'})
    loaded, why = importer.tekken8_moveset(definition, str(saved))
    if loaded is None:
        raise InputError('Hwoarang T8 extraction is incomplete: ' + why)
    k, files, references = loaded
    archives = importer._archives(str(game))
    native = movenames.ttt2_movesets(archives)
    donor = native[ROW]
    if donor.name(donor.name_offsets[0]) != '[HWOARANG]':
        raise InputError('expected EU v16 Hwoarang at native motion row 6')
    rpx = importer._rpx(str(game))
    keys = tuple(rpx.u32(0x105a51c4 + ROW*12 + i*4) for i in range(3))
    if keys != KEYS:
        raise InputError('native Hwoarang archive keys do not match EU v16')
    log('Recovering Hwoarang move names and native conversion maps...')
    movenames.name_moves(k, native, log=log)
    # T8 keeps Hwoarang's legacy Hw_ prefix, not the PC asset code Snk_.
    k.own_prefix = 'Hw'
    dictionary = movenames.harvest(native)[0]
    refs = []
    for code, path, fields in references:
        other = motbin.read(Path(path).read_bytes(), Path(fields).read_bytes(), code)
        movenames.name_known(other, dictionary)
        refs.append(other)
    req, prop, reactions, hitboxes, _ = M.tekken8_maps([k], native, references=refs)
    verify_signatures(k)
    verify_flamingo_input_routes(k)
    tornados = tornado_moves(k)
    definition.MOVESET['bounds'] = {moveset.UNNAMED + str(i) if not k.move_name(i) else k.move_name(i): False
                                    for i in tornados}
    definition.MOVESET['bounds'][BACKLASH] = False
    definition.MOVESET['bounds'].update({label: True for label in BOUND_FINISHERS})
    definition.MOVESET['bounds']['Hw_s_tlk'] = True
    log('User Bound rules enabled; every other source Tornado remains non-Bound.')
    target_bones = bone.read(archives.read_name('hwo.bon'))
    own, common = anmbin.Bank(files['anmbin']), anmbin.Bank(files['common'])
    t8 = source.open_tekken8(tekken8)
    try:
        k.attach_banks(motbin.read_bank(files['anmbin']), motbin.read_bank(files['common']))
        banks = anmbin.Banks(own, common, k.character_id)
        common_motions = archives.entry('data004', 0)
        animation_provider = anim.Animations(
            banks, anim.Converter(anim.load_skeleton(t8.store, 'snk'), target_bones),
            anim.originals(k, banks, native, common_motions,
                           lambda row: archives.entry('data005', row), ROW))
        c = Replacement(k, None, donor, archives.entry('data005', ROW), native[13], common_motions,
                        (req, prop, reactions, hitboxes), M.ttt2_usage(native[:58]), ROW, definition)
        c.animations = animation_provider
        from .convert import voice
        from .ttt2.archive import key_of
        from .ttt2.nus3bank import Bank
        vlist = voice.voice_list(rpx, 'hwo')
        native_bank = Bank(archives.raw(key_of('se_Chr_hwo.nus3bank')))
        c.voices8, c.shouts, c.native_damage_count = native_voice_categories(
            vlist, lambda tone: voice.tone_kind(native_bank.name(tone)))
        if not c.shouts or not c.native_damage_count:
            raise InputError('native Hwoarang voice slots are missing')
        c.voice = True
        log('Native voice slots: %d shouts, %d damage calls; original audio banks retained.' %
            (c.shouts, c.native_damage_count))
        c.win_tones = {}
        c.tag_states = TS.TagStates(native[:58])
        c.hit_locations = weapons.points_of(target_bones['names'])
        log('Converting T8 attacks, stances and animations onto native Hwoarang...')
        c.run()
        if c.stats.get("animations: none (the donor stance's)", 0):
            raise InputError('a Hwoarang source animation is missing; refusing a partial replacement')
        selected_bounds = {c.kn[name] for name, enabled in definition.MOVESET['bounds'].items() if enabled}
        for i in tornados - selected_bounds:
            if i in c.newidx:
                move = c.T['moves'][c.newidx[i]]
                if any(TS.has(c.T, hit['req'], TS.BOUND) for hit in TS.hits(c.T, move['hit_condition'])):
                    raise InputError('a T8 Tornado retained Bound: ' + c.name(i))
        mb, pk = c.write()
        check = native_motbin.read(mb)
        if check.aliases != c.aliases or len(check.tables['moves']) != len(c.T['moves']):
            raise InputError('Hwoarang serialization failed validation')
        from .convert import move_overrides
        command_data = Path(files['mvl']).read_bytes()
        entries, _, _ = movelist.read(command_data)
        no_tornado_icons = {entry['keys'][0]: (0, False) for entry in entries if entry['icons'] & 0xff00}
        # Stable text keys identify commands even when the demo walker cannot
        # simulate dash inputs or stance changes. The displayed hit is explicit.
        texts = movelist.texts(t8.store, {key for entry in entries for key in entry['keys'] if key}, log)
        command_bounds = {
            'During Right Flamingo \ue007\ue018': 1,
            'During Right Stance \ue003\ue016': 1,
            '\ue01c\ue01c\ue018': 3,
            '\ue007\ue018 on hit or block \ue01c\ue018': 3,
            'During Left Flamingo \ue007\ue018 on hit or block \ue01c\ue018': 3,
            'While rising \ue018': 1,
            'During Right Stance \ue016\ue01c\ue018': 3,
            'During Right Stance \ue01c\ue018': 2,
            'During Right Flamingo \ue002\ue01c': 1,
            'During Left Flamingo \ue018\ue016': 2,
            'During Left Flamingo \ue017\ue01c': 2,
            '\ue004\ue004\ue00c\ue018': 1,
        }
        for entry in entries:
            # _strings already performs the game's glyph substitution.
            try:
                command = movelist._strings(entry, texts)[4]
            except (KeyError, ValueError, movelist.LeftOut):
                continue
            if command in command_bounds:
                no_tornado_icons[entry['keys'][0]] = (command_bounds[command], True)

        commands = movelist.convert(command_data, t8.store, log=log,
                                    bounds=move_overrides.command_bounds(c), bound_entries=no_tornado_icons,
                                    texts_by_language=texts)
        if commands is None:
            raise InputError('Hwoarang command list conversion failed')
        for line in c.summary():
            log(line)
        log('Native Bound move rules retained: ' + ', '.join(sorted(name for name, enabled in definition.MOVESET['bounds'].items() if enabled)))
        return dict(zip(KEYS, (pk, mb, commands)))
    finally:
        own.close()
        common.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', required=True, type=Path)
    parser.add_argument('--saved', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--tekken8')
    args = parser.parse_args()
    files = convert(args.game, args.saved, args.tekken8, log=lambda s: print(s, flush=True))
    keys = args.out / 'keys'
    keys.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for key, data in files.items():
        path = keys / ('%08x.bin' % key)
        part = path.with_suffix('.part')
        part.write_bytes(data)
        part.replace(path)
        hashes[path.name] = hashlib.sha256(data).hexdigest()
    (args.out / 'patch.json').write_text(json.dumps({'code': 'hwo', 'revision': 12, 'files': hashes}, indent=2)+'\n')
    print('Native Hwoarang T8 replacement built in ' + str(args.out), flush=True)


if __name__ == '__main__':
    main()
