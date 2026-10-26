"""TTT2's tag combos on the added fighter's launchers: a launcher that hit, Tag pressed during it, and the fighter
tags out at once while the partner runs in and goes on with the juggle (Kazuya's EWGF: Kz_shoryu_S -> Kz_shoryu_SChg,
the partner At_ChgInStdAuto). Tekken 7 and Tekken 8 have no tag, so their launchers have none of it.

TTT2 keeps it in the movesets, as it keeps Tag Assault (tagsystem.py):

* The launcher X has an automatic cancel `[(47), (481)]` from frame 1 to a few frames after its last active one into
  its tag exit XChg. 47 holds once the move hit and Tag was pressed during it: player+932 bit 0x00100000 (set on
  the hit, sub_03AE15D8; not on a whiff) and bit 0x00800000 (set on the Tag press, sub_03F52F20); both are
  cleared when a move starts, so a press during the startup counts once the hit lands (seen in game: EWGF's latch at
  frame 12 after a press at 9, the exit at 13; on a whiff, a press at frame 26 or no press, no exit). 481: the
  partner can come in.
* XChg has no hit; its cancels: into the waiting hub once off the point (152 -> Co_Change_Kam), at frame N the tag
  out (actions 0x824D, 0x8246 = bring the partner in with tag-in kind 22 at its place, 0x824E = swap the point), at
  frame M back to the stance (the fighter then leaves through its stance's tag group). The partner's Co_Change_Kam
  takes kind 22 into At_ChgInStdAuto, a run in from which its attacks continue the juggle (every converted pack
  keeps the donor's dispatcher row for it).
* A launcher whose hit cancels into a hit version of itself (Ju_up03 -> Ju_up03_H: the same animation, a 0x400
  extradata that keeps the frame count) has the same exit on a Tag press in that version too
  (`TAG_BUTTON [(481)]`).
* In TTT2's 58 movesets: 430 such rows on 427 moves (1 to 16 a fighter) and 59 of the hit versions'. 124 of the
  exits play X's own animation on from X's frame (extradata 0x4bc: the 0x400 keeps the frame count, so Lars's
  f,f+2 La_66RP -> La_66RPChg took over at frame 22 in game), N 8 frames (median) after the window's end, M 6 after
  N; the other 306 play animations made for them (Kazuya's amkz_shonige_change).

combo_template learns the donor's own-animation form from its X / XChg pairs (Jun 2, Lars 2); launchers picks the
fighter's moves TTT2's rule picks; add_tag_combos gives each the row and an exit that plays its own animation on.
Like tagsystem, nothing here changes a list in place: a list that changes is written anew and its move repointed.
"""
import collections
import re

from . import arcs, idmaps as M
from . import tagsystem as TS

TAG_HIT = 47                        # the move hit and Tag was pressed during it (player+932 0x00900000)
CAN_TAG = 481                       # the partner can come in
OFF_POINT = 152                     # no longer the point (player+7808 == 0 and +1004 == 0)
TAG_OUT = 0x8246                    # the action that tags the partner in (value: its place << 8 | tag-in kind)
HUB = 0x802F                        # alias slot of Co_Change_Kam, the waiting partner's hub
AIR = TS.AIR                        # (466) the opponent is airborne: an 'air' tag combo's extra requirement
ACTION_ONLY = 0x2800                # extradata of an automatic row that only runs its actions (it never leaves the move)
KEEP_FRAMES = 0x400                 # extradata bit: the next move goes on from this move's frame
STANDING_HIT = (TS.AIR, TS.BOUND, TS.BOUND_TAG)    # (an entry testing any of these is not the standing hit's)
FA_LIMIT = 35                       # TTT2: 413 of its 430 rows are on moves active before frame 35 (a slow, charged
                                    # launcher gets one in 17 of its 93 cases)
LAUNCH = 47                         # frames a launch keeps the opponent airborne: TTT2's launch reactions 47
                                    # (sDw_UP_00_) to 77 (sDw_UP_20_), its knockdowns 9 to 45 (sDw_hkr's 49 aside;
                                    # Lars's 1,2,1,1 La_Xsyou has a tag combo on a 40-frame knockdown)
MOVE_FIELDS = TS.VALUE_FIELDS + ('transition',)
SAME, HIGH, OR = 'same', 'high half', 'or'
HIGH_HALF = TS.HIGH_HALF
START = 0x8001                      # property frame: the move's start
SCENARIO = 'SP'                     # name prefix of the scenario (story) moves
# the launchers TTT2 leaves out (of its fighters' launchers that pass `launchers`: 308 of 563 others have a tag combo):
GENERIC = 'Co_'                     # the generic moves every moveset shares: 2 of 188 (but tagged_stems')
FIGHTER = re.compile(r'^([A-Z][a-z0-9])_(.+)$')                     # a fighter's own move: prefix, stem
STEM_SHARE = 2                      # a stem is a tag-combo one when 1 / STEM_SHARE or more of its launchers have one
TEN_HIT = re.compile(r'10c|10h|10C|10A_|vw10|c20')                  # the 10-hit combos' hits: 6 of 28 (Jun's c20E)
JUMP = re.compile(r'(^|_)s?jp|jpR|jp[lr]')                           # jump attacks: 13 of 278
ARC_IDS = (arcs.ARC, arcs.BAKED, arcs.AIR_MARK)    # the port's 2D arcs (an air move's exit flies on)


def plain(f):
    return f < TS.FRAME_FLAGS


def automatic(c):
    return c['direction'] == 0 and c['button'] == 0


def is_exit(tables, aliases, move):
    rows = TS.cancels(tables, move['cancel']) if move['cancel'] is not None else []
    hub = any(c['direction'] < M.LIST_END and c['move_id'] == HUB and TS.reqs(tables, c['req']) == [(OFF_POINT, 0)]
              for c in rows)
    return hub and any(c['direction'] < M.LIST_END and TS.has(tables, c['req'], TAG_OUT) for c in rows)


def tag_rows(tables, aliases, x):
    """Move x's tag-combo rows: [(row, 'hit' (the automatic [(47), (481)] row) or 'press' (a hit version's Tag press
    row), exit move index)]."""
    out = []
    moves = tables['moves']
    for c in TS.cancels(tables, x['cancel']) if x['cancel'] is not None else []:
        if c['direction'] >= M.LIST_END:
            continue
        ids = [a for a, _ in TS.reqs(tables, c['req'])]
        if automatic(c) and TAG_HIT in ids and CAN_TAG in ids:
            kind = 'hit'
        elif c['direction'] == 0 and c['button'] == TS.TAG_BUTTON and ids == [CAN_TAG]:
            kind = 'press'
        else:
            continue
        j = TS.resolve(aliases, c['move_id'])
        if j < len(moves) and is_exit(tables, aliases, moves[j]):
            out.append((c, kind, j))
    return out


# ------------------------------------------------------------------------------------------------ learning
def learn(votes, x, e):
    """Counts, per move field, the rules that give the exit e its value from the launcher x: x's (SAME), x's high half
    (HIGH), x's with bits set (OR, the bits), the value itself."""
    for f in MOVE_FIELDS:
        v = votes[f]
        a, b = x[f], e[f]
        v[('value', b)] += 1
        v[SAME] += a == b
        if isinstance(a, int) and isinstance(b, int):
            v[HIGH] += b == a & HIGH_HALF
            if b & a == a and b != a:
                v[(OR, b & ~a)] += 1
    v = votes['voiceclip']
    v[SAME if x['voiceclip'] == e['voiceclip'] else ('value', e['voiceclip'])] += 1


def rule_of(v):
    """The rule most of the exits follow: SAME before HIGH before OR before a value, where they tie."""
    rank = {SAME: 0, HIGH: 1}
    return max(v, key=lambda r: (v[r], -rank.get(r, 2 if isinstance(r, tuple) and r[0] == OR else 3)))


def combo_template(tables, aliases, window):
    """The donor's own-animation tag combo, learnt from its X / XChg pairs whose XChg plays X's animation (the most
    common form of each part): X's row (requirements, extradata, option, window start, start frame), a hit version's
    Tag press row (requirements of the donor's, any exit's), XChg's rows (the hub row, the tag-out row at N, the stance
    row at M, the end row), N's frames after the window's end and M's after N (the low median), XChg's hit list, the
    properties it adds and the ids of X's it carries at its start, the rule of every other move field; the window ends
    `window` frames after X's last active one. Raises ValueError if the donor has none."""
    moves = tables['moves']
    pairs, presses = [], []
    for i, x in enumerate(moves):
        for c, kind, j in tag_rows(tables, aliases, x):
            if kind == 'press':
                presses.append(c)
            elif moves[j]['anim'] == x['anim']:
                pairs.append((x, moves[j], c))
    if not pairs:
        raise ValueError('the donor has no tag combo that plays its launcher on (a launcher with a [(47), (481)] '
                         'cancel into a tag exit with the launcher\'s animation): pick another donor')
    votes = collections.defaultdict(collections.Counter)
    after, gap = [], []
    starts = collections.Counter()
    for x, e, c in pairs:
        votes['row'][(c['req'], c['extradata'], c['option'], c['win_start'], c['start_frame'])] += 1
        votes['no hit'][e['hit_condition']] += 1
        rows = [r for r in TS.cancels(tables, e['cancel'])]
        hub = [r for r in rows if r['direction'] < M.LIST_END and r['move_id'] == HUB]
        out = [r for r in rows if r['direction'] < M.LIST_END and TS.has(tables, r['req'], TAG_OUT)]
        back = [r for r in rows if r['direction'] < M.LIST_END and r not in hub and r not in out]
        votes['hub'][tuple((r['req'], r['extradata'], r['option'], r['win_start'], r['win_end'], r['start_frame'])
                           for r in hub)] += 1
        votes['out'][tuple((r['req'], r['extradata'], r['option'], r['move_id']) for r in out)] += 1
        votes['back'][tuple((r['req'], r['extradata'], r['option']) for r in back)] += 1
        end = rows[-1]
        votes['end'][(end['req'], end['extradata'], end['option'], end['win_start'], end['win_end'],
                      end['start_frame'])] += 1
        if out and back:
            after.append(out[0]['win_start'] - c['win_end'])
            gap.append(back[-1]['win_start'] - out[0]['win_start'])
        own = [(p['frame'], p['id'], p['value']) for p in TS.props(tables, x['extraprops'])]
        mine = [(p['frame'], p['id'], p['value']) for p in TS.props(tables, e['extraprops'])]
        ids = {pid: v for _, pid, v in own}
        votes['adds'][tuple(p for p in mine if p[0] == START and ids.get(p[1]) != p[2])] += 1
        starts.update(pid for f, pid, v in mine if f == START and ids.get(pid) == v)
        learn(votes, x, e)
    tpl = {key: TS.majority(votes[key], 'tag combo ' + key) for key in ('row', 'no hit', 'hub', 'out', 'back', 'end',
                                                                      'adds')}
    # a hit version's press row: the donor's own (any exit's; Jun's are all into made animations) with X's extradata
    pv = collections.Counter(c['req'] for c in presses)
    tpl['press'] = pv.most_common(1)[0][0] if pv else None
    tpl['after'] = max(1, sorted(after)[(len(after) - 1) // 2]) if after else 1
    tpl['gap'] = max(1, sorted(gap)[(len(gap) - 1) // 2]) if gap else 1
    tpl['window'] = window
    tpl['start ids'] = {pid for pid, n in starts.items() if n * 2 >= len(pairs)}
    tpl['fields'] = {f: rule_of(votes[f]) for f in MOVE_FIELDS + ('voiceclip',)}
    tpl['pairs'] = len(pairs)
    return tpl


def ewgf_window(tables, name_of):
    """Frames after its last active one that TTT2's EWGF (Heihachi's He_shoryu_S, the user's reference: Kazuya's is
    the same) takes the tag combo in: 8 (frames 1-20, last active 12)."""
    moves = tables['moves']
    for i, x in enumerate(moves):
        if name_of(i) == 'He_shoryu_S':
            for c in TS.cancels(tables, x['cancel']):
                ids = [a for a, _ in TS.reqs(tables, c['req'])]
                if automatic(c) and TAG_HIT in ids and CAN_TAG in ids:
                    return c['win_end'] - x['last_active']
    raise ValueError('no EWGF tag combo (He_shoryu_S) in the moveset given')


# ------------------------------------------------------------------------------------------------ picking
def air_time(tables, aliases, x):
    """How long x's hit on a standing opponent keeps it airborne: its first hit entry that tests no air or bound
    state, that reaction's front hit move, its airborne frames (0: none)."""
    if x['hit_condition'] is None:
        return 0
    for h in TS.hits(tables, x['hit_condition']):
        if any(c in STANDING_HIT for c, _ in TS.reqs(tables, h['req'])):
            continue
        if h['reactions'] is None:
            return 0
        j = TS.resolve(aliases, tables['reactions'][h['reactions']]['default'])
        if j >= len(tables['moves']):
            return 0
        v = tables['moves'][j]
        return v['airborne_end'] - v['airborne_start'] if v['airborne_start'] > 0 else 0
    return 0


def is_bound(tables, x):
    return x['hit_condition'] is not None and any(TS.has(tables, h['req'], TS.BOUND)
                                                  for h in TS.hits(tables, x['hit_condition']))


def launchers(tables, aliases, own, launch=LAUNCH):
    """The moves of `own` (the fighter's own moves' indices: not the generic moves TTT2 shares, as TTT2 gives 2 of its
    250 generic launchers one) TTT2's rule gives a tag combo: an attack active from frame 2 to frame FA_LIMIT - 1 whose
    hit on a standing opponent keeps it airborne `launch` frames or longer (air_time), with no bound (TTT2 gives no
    move both: a bound has Tag Assault) and no tag combo yet. On TTT2's own movesets this rule picks 689 moves, 327 of
    them (47 %) with TTT2's row, and 87 % of TTT2's 374 rows on fighter moves (the rest: string twins, jump kicks,
    alternate versions, the Mishimas' crouch dash 1: tighten leaves most of them out)."""
    return [i for i in own if launches(tables, aliases, tables['moves'][i], launch)
            and not tag_rows(tables, aliases, tables['moves'][i])]


def launches(tables, aliases, x, launch=LAUNCH):
    """Whether move x is a launcher by launchers' test (whatever tag combo it has)."""
    return x['hit_condition'] is not None and 2 <= x['first_active'] <= x['last_active'] and \
        x['first_active'] < FA_LIMIT and not is_bound(tables, x) and air_time(tables, aliases, x) >= launch


def combo_stems(movesets, aliases_of=lambda m: m.aliases):
    """{stem: (launching, tagged)}: per stem of TTT2's fighters' own moves (the name less its fighter prefix: Ju_s_trp00
    -> s_trp00), how many of the movesets have such a move that launches (the launchers test) and how many of those
    give it a tag combo."""
    launching, tagged = collections.defaultdict(set), collections.defaultdict(set)
    for k, m in enumerate(movesets):
        t, al = m.tables, aliases_of(m)
        for i, x in enumerate(t['moves']):
            f = FIGHTER.match(m.move_name(i))
            if not f or f.group(1) + '_' == GENERIC or not launches(t, al, x):
                continue
            launching[f.group(2)].add(k)
            if any(kind == 'hit' for _, kind, _ in tag_rows(t, al, x)):
                tagged[f.group(2)].add(k)
    return {s: (len(v), len(tagged[s])) for s, v in launching.items()}


def tagged_stems(tag_states):
    """The stems (combo_stems) of TTT2's own fighters' launchers that half or more of them (two at least) give a tag
    combo, from the movesets tagsystem.TagStates was made of (cached on it; none without them). TTT2 names some
    launchers generically (Co_*) that the converted fighters have as their own (Tekken 7 named Akuma's WS+2
    Co_s_trp00): such a move keeps its tag combo when its stem is one of these (s_trp00, WS+2: 5 of TTT2's 5
    launching ones; s_tlk00: 5 of 6; d/f+2, t_srpF: 0 of 17, no; jump kicks jprk00F: 1 of 14, no)."""
    if tag_states is None or not getattr(tag_states, 'movesets', None):
        return set()
    if getattr(tag_states, '_tag_stems', None) is None:
        tag_states._tag_stems = {s for s, (n, t) in combo_stems(tag_states.movesets).items()
                                 if n >= 2 and t * STEM_SHARE >= n}
    return tag_states._tag_stems


def left_out(name, donor_tagged=(), stems=()):
    """The classes of launcher TTT2 gives no tag combo that the move name is in: 'generic' (unless the donor's own
    moveset gives that very move one, or TTT2's fighters their own moves of its stem: tagged_stems), '10 hit',
    'jump'."""
    out = set()
    if name.startswith(GENERIC) and name not in donor_tagged and name[len(GENERIC):] not in stems:
        out.add('generic')
    if TEN_HIT.search(name):
        out.add('10 hit')
    if JUMP.search(name):
        out.add('jump')
    return out


def tighten(tables, picks, name_of, donor_tagged=(), stems=()):
    """launchers' picks less the classes TTT2 leaves out (left_out) and less twins: of the picks playing one animation
    only the first (TTT2: 49 of 152 first ones of such groups have a tag combo, 27 of 188 later ones). Where nothing
    is left, the best of the picks: not a jump attack or a 10-hit combo's, the earliest active (then the first).
    With these, the rule picks 473 moves on TTT2's own movesets: 61 % of them with TTT2's row, 77 % of TTT2's rows
    (8 a fighter, at most 18; TTT2's own: about 6, at most 16)."""
    kept = [i for i in picks if not left_out(name_of(i), donor_tagged, stems)]
    seen, out = set(), []
    for i in sorted(kept):
        a = tables['moves'][i]['anim']
        if a not in seen:
            seen.add(a)
            out.append(i)
    if not out and picks:
        out = [min(picks, key=lambda i: (bool(left_out(name_of(i), donor_tagged, stems) - {'generic'}),
                                         tables['moves'][i]['first_active'], i))]
    return out


def reachable(tables, aliases):
    """The moves a fighter can get into: from its alias slots (stance, landings, ...) through every cancel (of its
    lists and groups) and transition. (A converted list keeps no row that can never be taken: Tekken 8's Heat moves
    that only Heat leads to are left out.)"""
    moves = tables['moves']
    seen, todo = set(), [TS.resolve(aliases, 0x8000 + s_) for s_ in range(len(aliases))]
    while todo:
        i = todo.pop()
        if i is None or i >= len(moves) or i in seen:
            continue
        seen.add(i)
        x = moves[i]
        if x['transition'] is not None:
            todo.append(TS.resolve(aliases, x['transition']))
        for c in TS.cancels(tables, x['cancel']) if x['cancel'] is not None else []:
            if c['direction'] == M.GROUP:
                todo += [TS.resolve(aliases, g['move_id'])
                         for g in TS.chain(tables['group_cancels'], c['move_id'], lambda g: g['direction'] == M.GROUP_END)
                         if g['direction'] != M.GROUP_END]
            elif c['direction'] < M.LIST_END:
                todo.append(TS.resolve(aliases, c['move_id']))
    return seen


def hit_versions(tables, aliases, x):
    """The moves x's hit cancels into that play x's animation on (a 0x400 extradata): its hit versions."""
    out = []
    for c in TS.cancels(tables, x['cancel']):
        if not automatic(c) or c['direction'] >= M.LIST_END or not TS.has(tables, c['req'], 46):
            continue
        if c['extradata'] is None or not tables['cancel_extras'][c['extradata']]['value'] & KEEP_FRAMES:
            continue
        j = TS.resolve(aliases, c['move_id'])
        if j < len(tables['moves']) and tables['moves'][j]['anim'] == x['anim'] and j not in out:
            out.append(j)
    return out


# ------------------------------------------------------------------------------------------------ making
def exit_move(x, tpl):
    """A copy of launcher row x with the fields the donor's exits take from it, or not."""
    out = dict(x)
    for f, rule in tpl['fields'].items():
        if rule == SAME:
            continue
        if rule == HIGH:
            out[f] = x[f] & HIGH_HALF
        elif rule[0] == OR:
            out[f] = x[f] | rule[1]
        else:
            out[f] = rule[1]
    return out


def insert(tables, move, row, action_extra):
    """move's cancel list written anew with `row` after its leading automatic rows that only run actions (TTT2's
    tag combo rows come right after them in 378 of its 430 lists: the on-hit sounds still play when the row is taken);
    action_extra: the extradata indices of such rows."""
    rows = [dict(c) for c in TS.cancels(tables, move['cancel'])]
    k = 0
    while k < len(rows) - 1 and automatic(rows[k]) and rows[k]['extradata'] in action_extra:
        k += 1
    move['cancel'] = TS.write(tables, 'cancels', rows[:k] + [row] + rows[k:])


def requirements(tables, start, extra):
    """A new requirement list: the one at `start` with `extra` rows before its end."""
    rows = [dict(condition=c, param=p) for c, p in TS.reqs(tables, start) + list(extra)]
    return TS.write(tables, 'requirements', rows + [dict(condition=TS.TT_END, param=0)])


def add_tag_combos(tables, tpl, picks, aliases, name_of, string, air=()):
    """Every move of `picks` (move indices) gets TTT2's tag combo after `tpl` (combo_template): its row (taken from
    frame 1 to `window` frames after its last active one, before the end of the move) into a new exit XChg that plays
    its animation on, tags the partner in `after` frames after the row's window and goes back to the stance `gap`
    frames later (before the move would end). Its hit versions (hit_versions) get the press row into the same exit.
    air: the picks whose rows also need the opponent airborne (466). name_of(i): move i's name; string(s): the name's
    string offset. -> [(X, XChg, [hit versions])]"""
    moves = tables['moves']
    taken = {name_of(i) for i in range(len(moves))}
    action = {k for k, e in enumerate(tables['cancel_extras']) if e['value'] == ACTION_ONLY}

    def name(s):
        n, k = s, 1
        while n in taken:
            k += 1
            n = '%s%d' % (s, k)
        taken.add(n)
        return string(n)
    made = []
    for i in picks:
        x = moves[i]
        if x['cancel'] is None:
            continue
        rows = TS.cancels(tables, x['cancel'])
        last = rows[-1]['win_start'] if rows[-1]['direction'] == M.LIST_END and plain(rows[-1]['win_start']) else None
        la = x['last_active']
        we = la + tpl['window']
        n_out = we + tpl['after']
        m_back = n_out + tpl['gap']
        if last is not None and last > la:
            # a short recovery: the window, the tag out and the stance all before the move's end
            m_back = min(m_back, last)
            n_out = min(n_out, m_back - 1)
            we = min(we, n_out - 1)
        if we < max(1, la) or n_out <= we or m_back <= n_out:
            continue
        req, extra, option, ws, sf = tpl['row']
        if i in air:
            req = requirements(tables, req, [(AIR, 0)])
        e_i = len(moves)
        row = dict(direction=0, button=0, req=req, extradata=extra, win_start=ws, win_end=we, start_frame=sf,
                   move_id=e_i, option=option)
        e = exit_move(x, tpl)
        e['name'] = name(name_of(i) + 'Chg')
        e['hit_condition'] = tpl['no hit']
        back_to = x['transition']
        out = [dict(direction=0, button=0, req=rq, extradata=ex, option=op, win_start=a, win_end=b, start_frame=s,
                    move_id=HUB) for rq, ex, op, a, b, s in tpl['hub']]
        out += [dict(direction=0, button=0, req=rq, extradata=ex, option=op, win_start=n_out, win_end=n_out,
                     start_frame=n_out, move_id=mid) for rq, ex, op, mid in tpl['out']]
        out += [dict(direction=0, button=0, req=rq, extradata=ex, option=op, win_start=m_back, win_end=m_back,
                     start_frame=m_back, move_id=back_to) for rq, ex, op in tpl['back']]
        rq, ex, op, a, b, s = tpl['end']
        out.append(dict(direction=M.LIST_END, button=0, req=rq, extradata=ex, option=op, win_start=a, win_end=b,
                        start_frame=s, move_id=0))
        e['cancel'] = TS.write(tables, 'cancels', out)
        # X's property rows themselves (the converter renumbers effects in them after run()): the ones after its
        # last active frame (TTT2's own-animation exits keep 50 of 63 of those, 25 of 98 before, 19 of 176 of the
        # start's) and its 2D arc rows, the start ones the donor's exits carry (animation blend channels), then the
        # ones they add
        own = TS.props(tables, x['extraprops'])
        keep = [p for p in own if (plain(p['frame']) and p['frame'] > la) or p['id'] in ARC_IDS]
        starts = [dict(p, frame=START) for p in own if p['id'] in tpl['start ids']]
        adds = [dict(frame=f, id=pid, value=v) for f, pid, v in tpl['adds']]
        e['extraprops'] = TS.write(tables, 'extra_move_properties', starts + keep + adds + [dict(frame=0, id=0, value=0)])
        moves.append(e)
        insert(tables, x, row, action)
        versions = []
        for j in hit_versions(tables, aliases, x):
            if j in picks or tag_rows(tables, aliases, moves[j]):
                continue
            press = tpl['press'] if tpl['press'] is not None else requirements(tables, None, [(CAN_TAG, 0)])
            if i in air:
                press = requirements(tables, press, [(AIR, 0)])
            insert(tables, moves[j], dict(row, button=TS.TAG_BUTTON, req=press), action)
            versions.append(j)
        made.append((i, e_i, versions))
    return made


# ------------------------------------------------------------------------------------------------ the converter's step
def apply(c):
    """moveset.Converter.run's step, after Tag Assault: the fighter's launchers (launchers over its own moves, the
    converter's K class, that it can get into; tighten) plus or minus the definition's MOVESET['tag_combos'] ({move name: True (add), False (leave
    out), 'air' (add; its rows also need the opponent airborne)}) get TTT2's tag combo, learnt from the donor, the
    window from TTT2's EWGF (c.h2: TTT2's Heihachi). -> [(X, XChg, [hit versions])]"""
    d = c.d
    rules = c.defn.MOVESET.get('tag_combos', {})
    # (not its scenario moves, SP*: none of TTT2's 33 such launchers has a tag combo)
    live = reachable(c.T, c.aliases)
    own = sorted(i for i in set(c.newidx.values()) if i in live and not c.move_name(i).startswith(SCENARIO))
    donor_tagged = {d.move_name(i) for i, x in enumerate(d.tables['moves'])
                    if any(kind == 'hit' for _, kind, _ in tag_rows(d.tables, d.aliases, x))}
    picks = tighten(c.T, launchers(c.T, c.aliases, own), c.move_name, donor_tagged,
                    tagged_stems(getattr(c, 'tag_states', None)))
    for name, how in rules.items():
        if name not in c.kn or c.kn[name] not in c.newidx:
            raise ValueError('tag combo for a move the fighter does not have (or that is not converted): ' + name)
        i = c.newidx[c.kn[name]]
        if how is False:
            picks = [j for j in picks if j != i]
        elif how is True or how == 'air':
            if i not in picks:
                picks.append(i)
        else:
            raise ValueError('a tag combo rule is True, False or \'air\': %s %r' % (name, how))
    air = {c.newidx[c.kn[n]] for n, how in rules.items() if how == 'air'}
    tpl = combo_template(d.tables, d.aliases, ewgf_window(c.h2.tables, c.h2.move_name))
    made = add_tag_combos(c.T, tpl, sorted(picks), c.aliases, c.move_name, c.string, air)
    c.stats['Tag combos: launchers given a tag exit playing their own animation'] += len(made)
    c.stats['Tag combos: hit versions given the Tag press row'] += sum(len(v) for _, _, v in made)
    c.tag_combos = [c.move_name(i) for i, _, _ in made]
    return made
