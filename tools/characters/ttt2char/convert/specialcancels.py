"""Character opt-ins for special inputs (the tag combos of launchers: tagcombo.py)."""
from . import idmaps as M, tagsystem as TS

SEQ0 = 0x800D
# The fighter's game's ids these rules read in its moveset (Tekken 7's; Tekken 8's are their counterparts in the id
# maps between the two games, None where those find none: no row then matches): the meter (EX moves), the special
# buffer (346 tests it, 0x80c5 sets it), the hit / block contact tests, the hit latch, the string buffers (352; 353
# and 0x80a9), the jump's air state and arc property, the second buffer's extra gate
SOURCE_IDS = {
    't7': dict(meter=629, special=346, special_set=0x80c5, contact=(49, 50), latch=43, string=352, string2=353,
               string2_set=0x80a9, jump_air=(630, 631), jump_arc=0x822d, string2_gate=0x82ea),
    't8': dict(meter=738, special=None, special_set=0x80e4, contact=(49, 50), latch=43, string=358, string2=359,
               string2_set=0x80c8, jump_air=(739, 740), jump_arc=0x829d, string2_gate=None),
}


def apply(c):
    rules = c.defn.MOVESET
    restore_jump_specials(c)
    restore_normal_strings(c)
    restore_secondary_strings(c)
    restore_unbuffered_normal_strings(c)
    restore_hit_latched_normal_strings(c)
    for source, targets in rules.get('special_cancels', {}).items():
        if rules.get('buffered_special_cancels'):
            buffered_special(c, source, targets)
            continue
        extra_frames = rules.get('special_cancel_leniency', {}).get(source, 0)
        if not isinstance(extra_frames, int) or not 0 <= extra_frames <= 12:
            raise ValueError('special cancel leniency must be 0..12 frames')
        ids = SOURCE_IDS[c.game]
        i = c.kn[source]
        rows = M.cancels(c.k, c.k.tables['moves'][i]['cancel'])
        # T7's input-only rows store the chosen special in 0x80c5; automatic
        # contact rows test it with 346. TTT2 has no equivalent buffer.
        inputs = {}
        for row in rows:
            req = M.reqs(c.k, row['req'])
            if (ids['special'], 0) in req and SEQ0 <= row['direction'] < SEQ0 + len(c.k.tables['input_sequences']):
                for pid, value in req:
                    if pid == ids['special_set']:
                        inputs.setdefault(value, []).append(row)
        # A direct TTT2 input uses the native normal/string input mode.
        # T7's automatic special-dispatch extra retains an additional 0x800.
        direct_extra = c.extra_index.get(0x182)
        if direct_extra is None:
            direct_extra = c.add('cancel_extras', dict(value=0x182))
            c.extra_index[0x182] = direct_extra
        added, seen = [], set()
        for row in rows:
            req = M.reqs(c.k, row['req'])
            target = c.k.resolve_alias(row['move_id']) if row['direction'] != M.GROUP else None
            if target is None or c.k.move_name(target) not in targets:
                continue
            # Keep meter-dependent EX branches out of this replacement.
            if any(pid == ids['meter'] for pid, _ in req):
                continue
            codes = [v for pid, v in req if pid == ids['special'] and v != 0]
            if not any(pid in ids['contact'] for pid, _ in req):
                continue
            for code in codes:
                for inp in inputs.get(code, []):
                    for contact in (46, 47):       # native hit; 47: hit with Tag pressed too
                        key = (inp['direction'], target, contact)
                        if key in seen:
                            continue
                        seen.add(key)
                        rq = c.add('requirements', dict(condition=contact, param=0))
                        c.add('requirements', dict(condition=M.END_REQ['ttt2'], param=0))
                        seq_id = c.conv_seq(inp['direction'] - SEQ0)
                        if extra_frames:
                            # Clone: neutral inputs and other moves keep their timing.
                            key_seq = ('special_leniency', seq_id, extra_frames)
                            if key_seq not in c.cache:
                                seq = c.T['input_sequences'][seq_id]
                                c.cache[key_seq] = c.add('input_sequences', dict(
                                    seq, window=min(255, seq['window'] + extra_frames)))
                            seq_id = c.cache[key_seq]
                        added.append(dict(direction=SEQ0 + seq_id,
                                          button=inp['button'], req=rq, extradata=direct_extra,
                                          win_start=inp['win_start'], win_end=min(32767, inp['win_end'] + extra_frames),
                                          start_frame=1, move_id=c.newidx[target], option=0))
        if not added:
            raise ValueError('no special cancels found for ' + source)
        move = c.T['moves'][c.newidx[i]]
        body = list(c.T['cancels'][move['cancel']:])
        end = next(j for j, row in enumerate(body) if row['direction'] == M.LIST_END)
        move['cancel'] = len(c.T['cancels'])
        c.T['cancels'] += added + body[:end + 1]
        c.stats['special input cancels restored'] += len(added)


# Verified against TTT2's executable: requirement 307 reads fighter+0x63c
# (0x04057000); property 0x8093 writes that same word (0x03af338c).
# This is distinct from the normal string variable (313 / 0x8096).
SPECIAL_VAR, SPECIAL_SET = 307, 0x8093
# Native 308 reads player+0x628; 0x80a5 writes it (0x03af21cc).
CONTACT_VAR, CONTACT_SET = 308, 0x80a5


def buffered_special(c, source, targets):
    """Retain T7's capture-then-contact-dispatch protocol using TTT2's word."""
    timing = c.defn.MOVESET.get('buffered_special_timing', {})
    late = timing.get('source_extra_frames', {}).get(source, timing.get('extra_frames', 0))
    motion_window = timing.get('motion_window', 0)
    if not isinstance(late, int) or not 0 <= late <= 20:
        raise ValueError('buffered special extra frames must be 0..20')
    if not isinstance(motion_window, int) or not 0 <= motion_window <= 255:
        raise ValueError('buffered special motion window must be 0..255')
    def req(values):
        start = len(c.T['requirements'])
        for a, b in values:
            c.add('requirements', dict(condition=a, param=b))
        c.add('requirements', dict(condition=M.END_REQ['ttt2'], param=0))
        return start

    def extra(value):
        if value not in c.extra_index:
            c.extra_index[value] = c.add('cancel_extras', dict(value=value))
        return c.extra_index[value]

    ids = SOURCE_IDS[c.game]
    i = c.kn[source]
    rows = M.cancels(c.k, c.k.tables['moves'][i]['cancel'])
    dispatch, codes, capture_ends = [], set(), {}
    for row in rows:
        values = M.reqs(c.k, row['req'])
        if row['direction'] != 0 or (not c.defn.MOVESET.get('free_meter_specials') and
                                    any(a == ids['meter'] for a, _ in values)):
            continue
        target = c.k.resolve_alias(row['move_id'])
        if c.k.move_name(target) not in targets:
            continue
        code = next((b for a, b in values if a == ids['special'] and b), None)
        contact = next((a for a, _ in values if a in ids['contact']), None)
        if code is None or (contact is None and source not in
                            c.defn.MOVESET.get('noncontact_special_cancels', ())):
            continue
        codes.add(code)
        capture_ends[code] = max(capture_ends.get(code, 0), min(32767, row['win_end'] + late))
        checks = [(SPECIAL_VAR, code)]
        if contact is not None:
            checks.append((CONTACT_VAR, 1))
        dispatch.append(dict(row, req=req(checks),
                             extradata=extra(0x182), move_id=c.newidx[target],
                             win_end=min(32767, row['win_end'] + late), start_frame=1, option=0))
    captures, captured = [], set()
    for row in rows:
        values = M.reqs(c.k, row['req'])
        code = next((b for a, b in values if a == ids['special_set'] and b in codes), None)
        if code is None or (ids['special'], 0) not in values:
            continue
        is_sequence = SEQ0 <= row['direction'] < SEQ0 + len(c.k.tables['input_sequences'])
        if not is_sequence and not (row['direction'] < 0x400 and row['button']):
            continue
        # These are input-only rows: native 0x2800 runs requirement actions
        # without leaving the normal. Never add a hit/block gate here.
        sequence = c.conv_seq(row['direction'] - SEQ0) if is_sequence else None
        if motion_window and is_sequence:
            key = ('buffered_motion_window', sequence, motion_window)
            if key not in c.cache:
                original = c.T['input_sequences'][sequence]
                c.cache[key] = c.add('input_sequences', dict(
                    original, window=max(original['window'], motion_window)))
            sequence = c.cache[key]
        captures.append(dict(row, direction=SEQ0 + sequence if is_sequence else row['direction'],
                             req=req([(SPECIAL_VAR, 0), (SPECIAL_SET, code)]),
                             extradata=extra(0x2800), move_id=0x8001,
                             # A few strings capture well before dispatch;
                             # allow late motions throughout the dispatch window.
                             win_end=max(min(32767, row['win_end'] + late), capture_ends[code]),
                             start_frame=1, option=0))
        captured.add(code)
    if not dispatch or captured != codes:
        raise ValueError('incomplete special buffer for ' + source)
    move = c.T['moves'][c.newidx[i]]
    body = list(c.T['cancels'][move['cancel']:])
    end = next(j for j, row in enumerate(body) if row['direction'] == M.LIST_END)
    move['cancel'] = len(c.T['cancels'])
    # Native contact tests are transient (trace: true at 15, false at 17).
    # (47 also needs Tag pressed, player+932 0x00800000: its rows only repeat the 46 ones then; kept as they are.)
    # Remember contact independently, even when motion completion comes later.
    last = max(row['win_end'] for row in dispatch)
    latch = [dict(direction=0, button=0,
                  req=req([(CONTACT_VAR, 0), (contact, 0), (CONTACT_SET, 1)]),
                  extradata=extra(0x2800), win_start=1, win_end=last,
                  start_frame=1, move_id=0x8001, option=0) for contact in (46, 47)
             if source not in c.defn.MOVESET.get('noncontact_special_cancels', ())]
    c.T['cancels'] += latch + captures + dispatch + body[:end + 1]
    # Reset at move entry, including repeated normals and the next string hit.
    # TTT2 runs end_props every frame; clearing there destroys early captures.
    # Clone the entry list rather than changing shared data.
    for field, table in [('begin_props', 'move_begin_props')]:
        original, kept = move.get(field), []
        if original is not None:
            for p in c.T[table][original:]:
                if p['id'] == M.END_REQ['ttt2']:
                    break
                kept.append(dict(p))
        move[field] = len(c.T[table])
        c.T[table] += [dict(req=req([]), id=SPECIAL_SET, value=0),
                       dict(req=req([]), id=CONTACT_SET, value=0)] + kept + [dict(req=0, id=M.END_REQ['ttt2'], value=0)]
    c.stats['special input capture rows restored'] += len(captures)
    c.stats['buffered special dispatch rows restored'] += len(dispatch)


def restore_unbuffered_normal_strings(c):
    """Keep ordinary 2D-fighter strings whose only missing state is an empty T7 special buffer.

    Native special-cancel opt-ins retain their explicit timing/priority rules. Do not turn motion captures,
    meter checks or a nonempty special-buffer dispatch into unrestricted normal attacks.
    """
    explicit = c.defn.MOVESET.get('normal_string_followups', {})
    buffered = c.defn.MOVESET.get('special_cancels', {}) if c.defn.MOVESET.get('buffered_special_cancels') else {}
    ids = SOURCE_IDS[c.game]
    special, contact_tests = ids['special'], ids['contact']
    if special is None:
        return
    for name, i in c.kn.items():
        if name in explicit or name in buffered:
            continue
        index = c.newidx.get(i, getattr(c, 'dn', {}).get(name))
        if index is None:
            continue
        added, seen = [], set()
        for row in M.cancels(c.k, c.k.tables['moves'][i]['cancel']):
            if not row['button'] or row['direction'] >= M.GROUP:
                continue
            values = M.reqs(c.k, row['req'])
            if (special, 0) not in values or any(pid not in (special,) + contact_tests or value != 0
                                                 for pid, value in values):
                continue
            target = c.k.resolve_alias(row['move_id'])
            if target not in c.newidx:
                continue
            contacts = (46, 47) if any(pid in contact_tests for pid, _ in values) else (None,)
            for contact in contacts:
                key = (row['direction'], row['button'], c.newidx[target], row['win_start'], row['win_end'],
                       row['start_frame'], contact)
                if key in seen:
                    continue
                seen.add(key)
                rq = len(c.T['requirements'])
                if contact is not None:
                    c.add('requirements', dict(condition=contact, param=0))
                c.add('requirements', dict(condition=M.END_REQ['ttt2'], param=0))
                extra = c.extra_index.get(0x182)
                if extra is None:
                    extra = c.add('cancel_extras', dict(value=0x182))
                    c.extra_index[0x182] = extra
                added.append(dict(row, req=rq, extradata=extra, move_id=c.newidx[target], option=0))
        if added:
            move = c.T['moves'][index]
            body = [dict(r) for r in TS.cancels(c.T, move['cancel'])]
            move['cancel'] = len(c.T['cancels'])
            c.T['cancels'] += body[:-1] + added + body[-1:]
            c.stats['unbuffered normal string rows restored'] += len(added)


def restore_hit_latched_normal_strings(c):
    """Retain the one-frame hit-confirmed normal follow-up (Akuma f,f+2,1).

    T7 latches the hit with 0x80a9 at frame 15 and tests 353 at frame 16. Use the verified native contact word,
    reset on entry, rather than dropping the test or requiring the hit condition still to be live a frame later.
    """
    ids = SOURCE_IDS[c.game]
    for name, i in c.kn.items():
        if i not in c.newidx:
            continue
        original = M.cancels(c.k, c.k.tables['moves'][i]['cancel'])
        captures = [r for r in original if r['direction'] == 0 and r['button'] == 0
                    and M.reqs(c.k, r['req']) == [(ids['latch'], 0), (ids['string2_set'], 1)]]
        dispatch = [r for r in original if r['button'] and r['direction'] < M.GROUP
                    and M.reqs(c.k, r['req']) == [(ids['string2'], 1)]
                    and c.k.resolve_alias(r['move_id']) in c.newidx]
        if not captures or not dispatch:
            continue

        def extra(value):
            if value not in c.extra_index:
                c.extra_index[value] = c.add('cancel_extras', dict(value=value))
            return c.extra_index[value]

        def req(values):
            return TS.write(c.T, 'requirements', [dict(condition=a, param=b) for a, b in values]
                            + [dict(condition=M.END_REQ['ttt2'], param=0)])

        latch = []
        for row in captures:
            # T7's 43 is absent from the derived map. The native hit predicate is 46 (TTT2's on-hit rows: X -[46]->
            # X_H, the on-hit sounds); 47 holds only once Tag was pressed too (player+932 0x00800000, tagcombo.py),
            # so with it the follow-up came out only with Tag held.
            latch.append(dict(row, req=req([(46, 0), (CONTACT_SET, 1)]),
                              extradata=extra(0x2800), move_id=0x8001, option=0))
        added = [dict(row, req=req([(CONTACT_VAR, 1)]), extradata=extra(0x182), option=0,
                      move_id=c.newidx[c.k.resolve_alias(row['move_id'])]) for row in dispatch]
        move = c.T['moves'][c.newidx[i]]
        body = [dict(row) for row in TS.cancels(c.T, move['cancel'])]
        move['cancel'] = TS.write(c.T, 'cancels', latch + body[:-1] + added + body[-1:])
        original_entry, entry = move.get('begin_props'), []
        if original_entry is not None:
            for p in c.T['move_begin_props'][original_entry:]:
                if p['id'] == M.END_REQ['ttt2']:
                    break
                entry.append(dict(p))
        move['begin_props'] = TS.write(c.T, 'move_begin_props',
            [dict(req=req([]), id=CONTACT_SET, value=0)] + entry
            + [dict(req=0, id=M.END_REQ['ttt2'], value=0)])
        c.stats['hit-latched normal string rows restored'] += len(added)


def restore_normal_strings(c):
    """Restore normal follow-ups gated by T7's unmapped special buffer."""
    special = SOURCE_IDS[c.game]['special']
    for source, targets in c.defn.MOVESET.get('normal_string_followups', {}).items():
        original = M.cancels(c.k, c.k.tables['moves'][c.kn[source]]['cancel'])
        added, found = [], set()
        extra = c.extra_index.get(0x182)
        if extra is None:
            extra = c.add('cancel_extras', dict(value=0x182))
            c.extra_index[0x182] = extra
        for row in original:
            if not row['button'] or row['direction'] == M.GROUP:
                continue
            target = c.k.resolve_alias(row['move_id'])
            name = c.k.move_name(target)
            if name not in targets or M.reqs(c.k, row['req']) != [(special, 0)]:
                continue
            first = min(r['win_start'] for r in original
                        if r['button'] == row['button'] and M.reqs(c.k, r['req']) == [(special, 0)])
            rq = c.add('requirements', dict(condition=SPECIAL_VAR, param=0))
            c.add('requirements', dict(condition=M.END_REQ['ttt2'], param=0))
            added.append(dict(row, req=rq, extradata=extra, move_id=c.newidx[target],
                              win_start=first, option=0))
            found.add(name)
        if found != set(targets):
            raise ValueError('missing normal follow-up: ' + source)
        move = c.T['moves'][c.newidx[c.kn[source]]]
        body = list(c.T['cancels'][move['cancel']:])
        end = next(i for i, row in enumerate(body) if row['direction'] == M.LIST_END)
        move['cancel'] = len(c.T['cancels'])
        c.T['cancels'] += added + body[:end + 1]
        c.stats['normal string follow-ups restored'] += len(added)


def restore_secondary_strings(c):
    """Restore opted-in follow-ups using T7's second string buffer (353/0x80a9).

    These inputs are direct in TTT2. Timing and native cancel mode come from
    the original capture/dispatch pair; no new route is invented.
    """
    ids = SOURCE_IDS[c.game]
    first, second, second_set = ids['string'], ids['string2'], ids['string2_set']
    for source, targets in c.defn.MOVESET.get('secondary_string_followups', {}).items():
        original = M.cancels(c.k, c.k.tables['moves'][c.kn[source]]['cancel'])
        captures = {}
        for row in original:
            values = M.reqs(c.k, row['req'])
            code = next((b for a, b in values if a == second_set and b), None)
            if row['button'] and (second, 0) in values and code is not None:
                captures.setdefault(code, []).append(row)
        added, found, seen = [], set(), set()
        empty = c.add('requirements', dict(condition=M.END_REQ['ttt2'], param=0))
        for row in original:
            target = c.k.resolve_alias(row['move_id'])
            if target is None or c.k.move_name(target) not in targets:
                continue
            code = next((b for a, b in M.reqs(c.k, row['req']) if a == second and b), None)
            branches = [M.reqs(c.k, r['req']) for r in original
                        if c.k.resolve_alias(r['move_id']) == target and
                        (second, code) in M.reqs(c.k, r['req'])]
            allowed = {(first, 0), (first, 1), (second, code), (ids['string2_gate'], 0)}
            if (not all(set(branch) <= allowed for branch in branches) or
                    {b for branch in branches for a, b in branch if a == first} != {0, 1}):
                raise ValueError('unsupported secondary string gates: ' + source)
            for inp in captures.get(code, ()):
                key = (target, inp['direction'], inp['button'])
                if key in seen:
                    continue
                seen.add(key)
                # The original branches cover the hit-buffer's 0 and 1 cases.
                # A single direct input supports both, without a missing buffer.
                added.append(dict(row, direction=inp['direction'], button=inp['button'],
                                  req=empty, extradata=c.extradata(row['extradata']),
                                  move_id=c.newidx[target], win_start=inp['win_start'],
                                  win_end=inp['win_end'], option=0))
                found.add(c.k.move_name(target))
        if found != set(targets):
            raise ValueError('missing secondary string follow-up: ' + source)
        move = c.T['moves'][c.newidx[c.kn[source]]]
        body = TS.cancels(c.T, move['cancel'])
        move['cancel'] = TS.write(c.T, 'cancels', added + [dict(r) for r in body])
        c.stats['secondary string follow-ups restored'] += len(added)


def restore_jump_specials(c):
    """Restore opted-in air specials from baked jumps, using their native air window.

    T7 630/631 and action 0x822d refer to its physics. The port carries the
    jump in a baked animation and continues it through the runtime air markers.
    These routes are limited to the original jump's airborne frames instead.
    """
    targets = c.defn.MOVESET.get('jump_special_inputs', ())
    if not targets:
        return
    ids = SOURCE_IDS[c.game]
    for name, index in c.kn.items():
        if not name.startswith('Vp_sJUMP') or index not in c.newidx:
            continue
        original = c.k.tables['moves'][index]
        move = c.T['moves'][c.newidx[index]]
        added, seen = [], set()
        for row in M.cancels(c.k, original['cancel']):
            target = c.k.resolve_alias(row['move_id'])
            if target is None or c.k.move_name(target) not in targets:
                continue
            values = M.reqs(c.k, row['req'])
            if not any(a in ids['jump_air'] for a, _ in values):
                raise ValueError('missing T7 air gate: ' + name)
            if any(a not in (ids['meter'],) + ids['jump_air'] + (ids['jump_arc'],) for a, _ in values):
                raise ValueError('unsupported jump special gate: ' + name)
            if any(a == ids['meter'] for a, _ in values) and not c.defn.MOVESET.get('free_meter_specials'):
                continue
            if not SEQ0 <= row['direction'] < SEQ0 + len(c.k.tables['input_sequences']):
                raise ValueError('missing jump special input sequence: ' + name)
            # Original order prefers EX for 3+4; rising/falling branches share
            # inputs. Keep one route per command, rather than overlapping it.
            key = row['direction'], row['button']
            if key in seen:
                continue
            seen.add(key)
            empty = c.add('requirements', dict(condition=M.END_REQ['ttt2'], param=0))
            delta = move['airborne_end'] - original['airborne_end']
            start = max(row['win_start'], move['airborne_start'])
            end = min(row['win_end'] + delta, move['airborne_end'] - 1)
            if start > end:
                raise ValueError('empty jump special air window: ' + name)
            added.append(dict(row, direction=SEQ0 + c.conv_seq(row['direction'] - SEQ0),
                              req=empty, extradata=c.extradata(row['extradata']),
                              move_id=c.newidx[target], win_start=start, win_end=end, option=0))
        if added:
            rows = [dict(r) for r in TS.cancels(c.T, move['cancel'])]
            move['cancel'] = TS.write(c.T, 'cancels', added + rows)
            c.stats['jump special inputs restored'] += len(added)
