"""Tekken 7 / Tekken 8 -> TTT2 id maps, derived on the player's machine by aligning movesets of the games.

Requirement and property ids (and hit location codes) are ordered lists in every game, the newer games' with
insertions. Moves with the same name exist in both games (all of Heihachi's, and the generic moves every fighter has),
so for each pair of same-named moves the linked lists (cancels -> requirement lists, extra properties, begin/end
properties, hit conditions -> requirement lists and reactions) are aligned element by element and every (source
value, TTT2 value) pair is counted. Each namespace is then modelled as the heaviest strictly increasing chain of
well-supported pairs: ids on the chain map as observed, ids between two anchors with the same offset map with that
offset, strong pairs off the chain are kept as exceptions; anything else has no mapping.

Tekken 8 (tekken8_maps): Tekken 8 ships no move names, but a move's name key is CityHash32 of its name, so the
reader names the moves it can from TTT2's own (and, when given, Tekken 7's) move names; Tekken 8's are Tekken 7's
generic names and the fighter's own behind a three-letter prefix of its code (Zbr_sKAM00_). The Tekken 8 fighters
the player has (any number) are aligned with every installed TTT2 moveset ("wide": also by the stem behind each
fighter's own prefix, Zbr_sKAM00_ <-> Ju_sKAM00_, which pairs the same fighter in both games too; the rows of
matched groups; extra properties of unequal lists by frame and value). Tekken 8 numbers requirements and properties
like Tekken 7 with more insertions (its list end is 1100); the readers give commands in Tekken 7's encoding. Tekken 7
movesets, when the player has them, are optional extra evidence: Tekken 8 -> Tekken 7 maps chained with the importer's
own Tekken 7 -> TTT2 maps fill ids the direct maps leave out.

Written for this project from the files themselves (no third-party code).
"""
import bisect
import collections
import difflib
import re

from ..movesets import REACTION_MOVE_FIELDS

END_REQ = {'t7': 881, 'ttt2': 690, 't8': 1100}     # the requirement / property list end marker
GROUP, GROUP_END, LIST_END = 0x800B, 0x800C, 0x8000
# the lookups the converter trusts ('chained': through Tekken 7, Combined); extrapolated ids and gaps are not mapped
MAPPED = ('observed', 'observed-exception', 'interpolated', 'chained')
# a move name's prefix (a fighter's own: Ju_, Kz_ in TTT2 and Tekken 7, Zbr_ in Tekken 8; or a generic one: Co_,
# SE_, Tco_) and the stem behind it
PREFIX_RE = re.compile(r'^([A-Z][A-Za-z0-9]{1,2})_(.+)$')
# a move the Tekken 8 reader could not name (move_name ''): '#<index>' in the reaction evidence (convert/moveset.py
# names it alike)
UNNAMED = '#'


# ------------------------------------------------------------------------------------------------ lists
def reqs(m, i):
    if i is None:
        return []
    end = END_REQ[m.game]
    return [(r['condition'], r['param']) for _, r in m.iter_list('requirements', i, lambda r: r['condition'] == end)
            if r['condition'] != end]


def cancels(m, i, table='cancels', end=LIST_END):
    if i is None:
        return []
    return [c for _, c in m.iter_list(table, i, lambda c: c['direction'] == end)]


def xps(m, i):
    if i is None:
        return []
    return [(x['frame'], x['id'], x['value'])
            for _, x in m.iter_list('extra_move_properties', i, lambda x: x['id'] == 0 and x['frame'] == 0)]


def props(m, table, i):
    if i is None:
        return []
    end = END_REQ[m.game]
    return [(reqs(m, p['req']), p['id'], p['value']) for _, p in m.iter_list(table, i, lambda p: p['id'] == end)]


def hitconds(m, i):
    """A hit-condition list ends with the entry whose requirement list is empty."""
    if i is None:
        return []
    out, t = [], m.tables['hit_conditions']
    while i < len(t):
        rl = reqs(m, t[i]['req'])
        out.append((rl, t[i]['damage'], t[i]['reactions']))
        if not rl:
            break
        i += 1
    return out


def voices(m, i):
    if i is None:
        return []
    return [v['value'] for _, v in m.iter_list('voiceclips', i, lambda v: v['value'] == 0xFFFFFFFF)]


def target(m, mid):
    """The name of a move id's move (through the alias table for ids >= 0x8000)."""
    r = m.resolve_alias(mid)
    if r is None or r >= len(m.tables['moves']):
        return '?%#x' % mid
    return m.move_name(r)


# ------------------------------------------------------------------------------------------------ evidence
class Evidence:
    """pairs[(a, b)] = how often a (Tekken 7) and b (TTT2) were seen in the same place."""

    def __init__(self):
        self.pairs = collections.Counter()

    def add(self, a, b, n=1):
        self.pairs[(a, b)] += n


def _req_pair(ra, rb, ev):
    if len(ra) == len(rb):
        for (c1, _), (c2, _) in zip(ra, rb):
            ev['req'].add(c1, c2)
    else:
        ev['reqlist_unequal'].add(tuple(c for c, _ in ra), tuple(c for c, _ in rb))


def own_prefixes(movesets):
    """Each moveset's own move name prefix: its most common prefix that at most half of the movesets have (the
    others are generic: Co_, SE_, Esc_ ...) -> [prefix or None], in the order of `movesets`."""
    counts = []
    for m in movesets:
        c = collections.Counter()
        for i in range(len(m.tables['moves'])):
            g = PREFIX_RE.match(m.move_name(i))
            if g:
                c[g.group(1)] += 1
        counts.append(c)
    share = collections.Counter(p for c in counts for p in c)
    return [next((p for p, _ in c.most_common() if share[p] * 2 <= len(movesets)), None) for c in counts]


def canonical(m, prefix=None):
    """{move index: its name, with the moveset's own prefix (m.own_prefix, or `prefix`) made '@'} of the named
    moves."""
    prefix, out = prefix or getattr(m, 'own_prefix', None), {}
    for i in range(len(m.tables['moves'])):
        n = m.move_name(i)
        if not n:
            continue
        g = PREFIX_RE.match(n)
        out[i] = '@' + g.group(2) if g and g.group(1) == prefix else n
    return out


def align(a, b, ev, wide=None, reference=False):
    """Count the value pairs of the same-named moves of a (Tekken 7 / Tekken 8) and b (TTT2) into ev (key ->
    Evidence). wide (default: for Tekken 8): moves also pair by the stem behind their movesets' own prefixes
    (own_prefix attributes: own_prefixes), unnamed moves never pair, the rows of matched groups count, and extra
    property lists of unequal length pair their rows of equal frame and value ('xp.id.fv'). reference (wide only): a
    is another fighter than the one converted, b the same fighter in TTT2 (partners): a's names take b's prefix,
    and its unnamed moves give no reaction evidence (their stand-in names, '#<index>', are a's indices)."""
    if wide is None:
        wide = a.game == 't8'
    if wide:
        return _align_wide(a, b, ev, reference)
    A, B = a.tables, b.tables
    na = {a.move_name(i): i for i in range(len(A['moves']))}
    nb = {b.move_name(i): i for i in range(len(B['moves']))}

    # a row: its input and target. Directions below 0x8000 count too: a Tekken 7-only automatic row
    # `0 [806] -> sWALK_02L` in front of the neutral row `0x20 [0] -> sWALK_02L` both games have once paired with
    # TTT2's, which made 806 "always true" (convert/moveset.py REQ_FALSE)
    def sig(m):
        return lambda c: ((c['direction'], target(m, c['move_id'])) if c['direction'] < 0x8000 else
                          target(m, c['move_id']) if c['direction'] in (0x8001, 0x8002) else '', c['button'])
    sig_a, sig_b = sig(a), sig(b)
    for i, j in ((na[n], nb[n]) for n in na if n in nb):
        x, y = A['moves'][i], B['moves'][j]
        for p, q in zip(x['hitbox'], y['hitbox']):
            ev['hitbox.byte'].add(p, q)
        ca, cb = cancels(a, x['cancel']), cancels(b, y['cancel'])
        matcher = difflib.SequenceMatcher(None, [sig_a(c) for c in ca], [sig_b(c) for c in cb], autojunk=False)
        for blk in matcher.get_matching_blocks():
            for t in range(blk.size):
                _req_pair(reqs(a, ca[blk.a + t]['req']), reqs(b, cb[blk.b + t]['req']), ev)
        xa, xb = xps(a, x['extraprops']), xps(b, y['extraprops'])
        if len(xa) == len(xb):
            for p, q in zip(xa, xb):
                ev['xp.id'].add(p[1], q[1])
        else:
            ev['xplist_unequal'].add(tuple(p[1] for p in xa), tuple(q[1] for q in xb))
        for table, key in (('move_begin_props', 'begin_props'), ('move_end_props', 'end_props')):
            pa, pb = props(a, table, x[key]), props(b, table, y[key])
            if len(pa) == len(pb):
                for p, q in zip(pa, pb):
                    ev['prop.id'].add(p[1], q[1])
                    _req_pair(p[0], q[0], ev)
        ha, hb = hitconds(a, x['hit_condition']), hitconds(b, y['hit_condition'])
        if len(ha) == len(hb):
            for p, q in zip(ha, hb):
                _req_pair(p[0], q[0], ev)
                if p[2] is not None and q[2] is not None:
                    rx, ry = A['reactions'][p[2]], B['reactions'][q[2]]
                    for f in REACTION_MOVE_FIELDS:
                        ev['react.move'].add(a.move_name(rx[f]) if rx[f] < len(A['moves']) else rx[f],
                                             b.move_name(ry[f]) if ry[f] < len(B['moves']) else ry[f])


def _align_wide(a, b, ev, reference=False):
    """align's wide form (Tekken 8): canonical names, matched groups, extra properties by frame and value."""
    A, B = a.tables, b.tables
    ca, cb = canonical(a, getattr(b, 'own_prefix', None) if reference else None), canonical(b)
    nb = {n: j for j, n in cb.items()}

    def name(m, cn, mid):
        r = m.resolve_alias(mid)
        return '?' if r is None else cn.get(r, '#')

    def sig(m, cn):
        return lambda c: ((c['direction'], name(m, cn, c['move_id'])) if c['direction'] < 0x8000 else
                          name(m, cn, c['move_id']) if c['direction'] in (0x8001, 0x8002) else '', c['button'])
    sig_a, sig_b = sig(a, ca), sig(b, cb)

    def rows(la, lb, group):
        """Pair the rows of two cancel lists (and, in a move's list, of the groups its matched rows name)."""
        matcher = difflib.SequenceMatcher(None, [sig_a(c) for c in la], [sig_b(c) for c in lb], autojunk=False)
        for blk in matcher.get_matching_blocks():
            for t in range(blk.size):
                p, q = la[blk.a + t], lb[blk.b + t]
                _req_pair(reqs(a, p['req']), reqs(b, q['req']), ev)
                if not group and p['direction'] == GROUP and q['direction'] == GROUP:
                    rows(cancels(a, p['move_id'], 'group_cancels', GROUP_END),
                         cancels(b, q['move_id'], 'group_cancels', GROUP_END), True)
    for i, j in ((i, nb[n]) for i, n in ca.items() if n in nb):
        x, y = A['moves'][i], B['moves'][j]
        for p, q in zip(x['hitbox'], y['hitbox']):
            ev['hitbox.byte'].add(p, q)
        rows(cancels(a, x['cancel']), cancels(b, y['cancel']), False)
        xa, xb = xps(a, x['extraprops']), xps(b, y['extraprops'])
        if len(xa) == len(xb):
            for p, q in zip(xa, xb):
                ev['xp.id'].add(p[1], q[1])
        else:
            ev['xplist_unequal'].add(tuple(p[1] for p in xa), tuple(q[1] for q in xb))
            # rows of the same frame and value pair, so that rows Tekken 8 inserted do not stop the evidence
            matcher = difflib.SequenceMatcher(None, [(p[0], p[2]) for p in xa], [(q[0], q[2]) for q in xb],
                                              autojunk=False)
            for blk in matcher.get_matching_blocks():
                for t in range(blk.size):
                    ev['xp.id.fv'].add(xa[blk.a + t][1], xb[blk.b + t][1])
        for table, key in (('move_begin_props', 'begin_props'), ('move_end_props', 'end_props')):
            pa, pb = props(a, table, x[key]), props(b, table, y[key])
            if len(pa) == len(pb):
                for p, q in zip(pa, pb):
                    ev['prop.id'].add(p[1], q[1])
                    _req_pair(p[0], q[0], ev)
        ha, hb = hitconds(a, x['hit_condition']), hitconds(b, y['hit_condition'])
        if len(ha) == len(hb):
            for p, q in zip(ha, hb):
                _req_pair(p[0], q[0], ev)
                if p[2] is not None and q[2] is not None:
                    rx, ry = A['reactions'][p[2]], B['reactions'][q[2]]
                    for f in REACTION_MOVE_FIELDS:
                        if rx[f] < len(A['moves']):
                            na = a.move_name(rx[f]) or (None if reference else UNNAMED + str(rx[f]))
                            if na is not None:
                                ev['react.move'].add(na, b.move_name(ry[f]) if ry[f] < len(B['moves']) else ry[f])


# ------------------------------------------------------------------------------------------------ id maps
def anchors(ev, keys, lo, hi):
    """Evidence of several keys merged, Tekken 7 ids in [lo, hi): a -> (best b, its count, total, top 3)."""
    c = collections.defaultdict(collections.Counter)
    for k in keys:
        for (a, b), n in ev[k].pairs.items():
            if isinstance(a, int) and isinstance(b, int) and lo <= a < hi:
                c[a][b] += n
    out = {}
    for a, cc in c.items():
        (b, n), tot = cc.most_common(1)[0], sum(cc.values())
        out[a] = (b, n, tot, dict(cc.most_common(3)))
    return out


def chain(anc):
    """Heaviest chain increasing in both ids over the pairs that have at least 60 % of their id's evidence."""
    items = sorted((a, b, n) for a, (b, n, tot, alt) in anc.items() if n / tot >= 0.6)
    if not items:
        return []
    W, P = [0] * len(items), [-1] * len(items)
    for i, (a, b, n) in enumerate(items):
        W[i] = n
        for j in range(i):
            if items[j][1] < b and W[j] + n > W[i] and (b - items[j][1]) <= (a - items[j][0]) + 400:
                W[i] = W[j] + n
                P[i] = j
    i = max(range(len(items)), key=lambda k: W[k])
    best = []
    while i >= 0:
        best.append(items[i])
        i = P[i]
    return best[::-1]


class IdMap:
    def __init__(self, anc):
        self.anc = anc
        self.chain = chain(anc)
        self.ca = [a for a, b, n in self.chain]
        on_chain = set(self.ca)
        # strong pairs off the chain (renumbered ids) are kept as exceptions
        self.exc = {a: (b, n, tot) for a, (b, n, tot, alt) in anc.items()
                    if a not in on_chain and n >= 2 and n / tot >= 0.9}
        self.left_out = set()           # exceptions this map does not answer for (Tekken 8: distrust, outvoted)

    def lookup(self, x):
        """-> (TTT2 id or None, how it was found)"""
        if x in self.left_out:
            return None, 'left out'
        if x in self.anc and x in set(self.ca):
            return self.anc[x][0], 'observed'
        if x in self.exc:
            return self.exc[x][0], 'observed-exception'
        k = bisect.bisect_left(self.ca, x)
        if k == 0:
            a2, b2, _ = self.chain[0]
            return (x + b2 - a2 if x + b2 - a2 >= 0 else None), 'extrapolated-below'
        if k == len(self.ca):
            a1, b1, _ = self.chain[-1]
            return x + b1 - a1, 'extrapolated-above'
        a1, b1, _ = self.chain[k - 1]
        a2, b2, _ = self.chain[k]
        if b1 - a1 == b2 - a2:
            return x + b1 - a1, 'interpolated'
        return None, 'gap'


def build_maps(ev, game='t7', target='ttt2'):
    """(requirement map, property map) of `game`'s ids to `target`'s from the evidence; lists of unequal length are
    aligned in a second pass on the ids the first pass maps."""
    req = IdMap(anchors(ev, ['req'], 0, 0x8000))
    prop = IdMap(anchors(ev, ['req', 'xp.id', 'prop.id'], 0x8000, 0x10000))

    def known(x):
        b, how = (req if x < 0x8000 else prop).lookup(x)
        return b if how in ('observed', 'observed-exception', 'interpolated') else ('?', x)
    for key in ('reqlist_unequal', 'xplist_unequal'):
        for (xs, ys), n in ev[key].pairs.items():
            matcher = difflib.SequenceMatcher(None, [known(x) for x in xs], list(ys), autojunk=False)
            for op, i1, i2, j1, j2 in matcher.get_opcodes():
                if op == 'replace' and i2 - i1 == j2 - j1:
                    for x, y in zip(xs[i1:i2], ys[j1:j2]):
                        ev['refined'].add(x, y, n)
    req = IdMap(anchors(ev, ['req', 'refined'], 0, 0x8000))
    # (the wide alignment's extra properties paired by frame and value: Tekken 8)
    prop = IdMap(anchors(ev, ['req', 'xp.id', 'prop.id', 'refined'] + (['xp.id.fv'] if 'xp.id.fv' in ev else []),
                         0x8000, 0x10000))
    req.exc[END_REQ[game]] = (END_REQ[target], 0, 0)
    return req, prop


class Chained:
    """Two maps one after the other (Tekken 8 -> Tekken 7, then Tekken 7 -> TTT2): an id both map is 'chained'."""

    def __init__(self, first, second):
        self.first, self.second = first, second

    def lookup(self, x):
        y, how = self.first.lookup(x)
        if how not in MAPPED or y is None:
            return None, how
        z, how = self.second.lookup(y)
        return (z, 'chained') if how in MAPPED and z is not None else (None, how)


class Combined:
    """A map with fallbacks: the first map's answer where it maps the id, else the first fallback's that does."""

    def __init__(self, first, *fallbacks):
        self.maps = (first,) + fallbacks

    def lookup(self, x):
        first = None
        for m in self.maps:
            b, how = m.lookup(x)
            if how in MAPPED and b is not None:
                return b, how
            first = first or (b, how)
        return first


def reaction_remap(ev):
    """Tekken 7 move name -> the TTT2 move most often in the same reaction slot (where the names differ)."""
    c = collections.defaultdict(collections.Counter)
    for (x, y), n in ev['react.move'].pairs.items():
        if isinstance(x, str) and isinstance(y, str) and x != y:
            c[x][y] += n
    return {x: cc.most_common(1)[0][0] for x, cc in c.items()}


def hitbox_remap(ev, min_count=2):
    """Hit location codes (a move's four hitbox bytes) that Tekken 7 numbers differently: the heaviest chain over
    the observed (Tekken 7, TTT2) code pairs (0, no location, left out) that increases in the Tekken 7 code and
    never decreases in the TTT2 code (Tekken 7 has more locations: several may become one). Codes on the chain map
    to their partner; the others stay as they are. -> {code: TTT2 code} of the codes that change."""
    items = sorted((a, b, n) for (a, b), n in ev['hitbox.byte'].pairs.items() if a and b and n >= min_count)
    if not items:
        return {}
    W, P = [0] * len(items), [-1] * len(items)
    for i, (a, b, n) in enumerate(items):
        W[i] = n
        for j in range(i):
            if items[j][0] < a and items[j][1] <= b and W[j] + n > W[i]:
                W[i] = W[j] + n
                P[i] = j
    i = max(range(len(items)), key=lambda k: W[k])
    out = {}
    while i >= 0:
        a, b, _ = items[i]
        if a != b:
            out[a] = b
        i = P[i]
    return out


def ttt2_usage(movesets):
    """Requirement and property ids that some TTT2 moveset uses: {'req': set, 'prop': set, 'values': ttt2_values}."""
    use = {'req': set(), 'prop': set()}
    for m in movesets:
        for r in m.tables['requirements']:
            use['req' if r['condition'] < 0x8000 else 'prop'].add(r['condition'])
        for t in ('extra_move_properties', 'move_begin_props', 'move_end_props'):
            for x in m.tables[t]:
                use['prop' if x['id'] >= 0x8000 else 'req'].add(x['id'])
    use['values'] = ttt2_values(movesets)
    return use


def ttt2_values(movesets):
    """What TTT2's movesets pass with each id: {'req': {condition: {param}} of the requirement lists (the properties
    in them too), 'prop': {id: {value}} of the extra, begin and end property lists}."""
    out = {'req': collections.defaultdict(set), 'prop': collections.defaultdict(set)}
    for m in movesets:
        for r in m.tables['requirements']:
            out['req'][r['condition']].add(r['param'])
        for t in ('extra_move_properties', 'move_begin_props', 'move_end_props'):
            for x in m.tables[t]:
                out['prop'][x['id']].add(x['value'])
    return {kind: dict(v) for kind, v in out.items()}


# ------------------------------------------------------------------------------------------------ Tekken 8
# A gap id of a Tekken 8 map whose best partner has at least NEAR_SHARE of its evidence (NEAR_MIN observations at
# least) and keeps the chain increasing maps to it: Reina's 152 / 153 -> TTT2's 148 / 149 (55 %: Tekken 8 tests the
# sides where TTT2 tests 146 / 147 as often) and 293 -> 262 (51 %), the three such ids, all three what the route
# through Tekken 7 gives
NEAR_SHARE, NEAR_MIN = 0.5, 20


def near_anchors(m):
    """Add the well-supported pairs of gap ids to IdMap m's exceptions (NEAR_SHARE) -> how many."""
    added = 0
    if not m.chain:
        return added
    for x, (b, n, tot, _) in sorted(m.anc.items()):
        if m.lookup(x)[1] in MAPPED or n < NEAR_MIN or n < NEAR_SHARE * tot:
            continue
        k = bisect.bisect_left(m.ca, x)
        lo = m.chain[k - 1][1] if k else -1
        hi = m.chain[k][1] if k < len(m.chain) else float('inf')
        if lo < b < hi:
            m.exc[x] = (b, n, tot)
            added += 1
    return added


# Other Tekken 8 fighters' movesets (references: the player's saved ones) give same-fighter evidence: a fighter TTT2
# has too keeps its old names in Tekken 8 (Jun's Ju_sKAM00_, Kazuya's Kz_), so its moves pair with its TTT2
# moveset's own moves, rows the generic moves never show. A reference's partners are the TTT2 movesets sharing at
# least PARTNER_MIN of its names that are not generic (a name more than GENERIC_SHARE of TTT2's movesets have is
# generic): Tekken 8 Jun has 230 in TTT2 Jun's moveset (and 169 in Unknown's, who fights with Jun's moves), Kazuya
# 259, the 25 fighters both games have 144 to 696; newcomers (Reina, Azucena, Victor) and those TTT2 lacks (Claudio,
# Shaheen, Leroy) 100 at most. Reina's maps with those 25 references: 321 of the 620 ids her moveset uses (253
# alone; 18 of the new ones checked against the route through Tekken 7 agree with it, 1 differs), 73.6 % of her own
# moves' cancel rows kept (63.9 %); aligning the references with every TTT2 moveset gives the same in 15 times the
# time.
GENERIC_SHARE, PARTNER_MIN = 0.25, 120


def _names(m):
    return set(m.move_name(i) for i in range(len(m.tables['moves'])) if m.move_name(i))


def partners(m, ttt2, names=None):
    """The TTT2 movesets (of `ttt2`; names: their _names, when known) that are the fighter of moveset m (by its
    names: PARTNER_MIN)."""
    names = names or [_names(t) for t in ttt2]
    share = collections.Counter(n for s in names for n in s)
    own = {n for n in _names(m) if share[n] <= GENERIC_SHARE * len(ttt2)}
    return [t for t, s in zip(ttt2, names) if len(own & s) >= PARTNER_MIN]


def _copy(ev):
    out = collections.defaultdict(Evidence)
    for key, e in ev.items():
        out[key].pairs.update(e.pairs)
    return out


def _maps8(ev):
    req, prop = build_maps(ev, 't8')
    near_anchors(req)
    near_anchors(prop)
    return req, prop


# An exception (an off-chain pair) rests on few rows and nothing around it. Tekken 8's ids keep values in Tekken 8's
# own numbering where their meaning has one TTT2 has not, so an exception of a Tekken 8 map is kept only when at
# least FIT_SHARE of the fighters' rows with that id pass a value TTT2's own movesets pass with its TTT2 id (in any
# list): Reina's 0x8049 -> 0x801d (71 .. 5054 where TTT2 passes 0 .. 60; through Tekken 7 it is 0x8031, whose values
# do not fit either), 0x83be -> 0x8001 (65536: TTT2 passes 0), 0x83ce -> 0x8138 (70, 80: TTT2 0, 1), 0x8376 ->
# 0x825d, 0x82a6 -> 0x82d5, 0x833b -> 0x8194, 0x8281 -> 0x82f9 (a sound property, value 1) and the requirements 442
# (Heat variables 1 .. 3 as TTT2's 46, which tests 0) and 352 -> 49 lose theirs (`distrust`). And an exception of the
# fighters' own evidence yields to the references' map where their evidence (which holds the fighters' too) pairs the
# id with another TTT2 id and maps it so (`outvoted`): Reina's 130 -> 46 (8 rows of hers) is 128 there (92 of 154
# rows; 130 sits between 128 -> 126 and 131 -> 129, and Tekken 7's 130 is TTT2's 128 too).
FIT_SHARE = 0.5


def source_values(movesets):
    """{id: Counter of values} of Tekken 8 movesets: the requirement lists' params by condition, the property lists'
    values by id (both in one table: a property passes its value in either)."""
    out = collections.defaultdict(collections.Counter)
    for m in movesets:
        for r in m.tables['requirements']:
            out[r['condition']][r['param']] += 1
        for t in ('extra_move_properties', 'move_begin_props', 'move_end_props'):
            for x in m.tables[t]:
                out[x['id']][x['value']] += 1
    return out


def distrust(m, mine, theirs, game='t8'):
    """Leave out the exceptions of IdMap m whose rows' values do not fit (FIT_SHARE; mine: source_values of the
    fighters, theirs: ttt2_values): m no longer maps them (no interpolation in their place) -> the ids left out."""
    out = []
    for x, (b, n, tot) in list(m.exc.items()):
        rows = mine.get(x)
        if x == END_REQ[game] or not rows or x in m.left_out:
            continue
        values = theirs['req'].get(b, set()) | theirs['prop'].get(b, set())
        if sum(c for v, c in rows.items() if v in values) < FIT_SHARE * sum(rows.values()):
            m.left_out.add(x)
            out.append(x)
    return out


def outvoted(own, wide):
    """Leave out the exceptions of IdMap own (the fighters' evidence) that IdMap wide (theirs and the references')
    maps to the id its own evidence pairs them with most: own no longer maps them, so Combined(own, wide) takes wide's
    -> the ids left out."""
    out = []
    for x, (b, n, tot) in list(own.exc.items()):
        anc = wide.anc.get(x)
        if anc is None or anc[0] == b or x in own.left_out:
            continue
        b2, how = wide.lookup(x)
        if how in MAPPED and b2 == anc[0]:
            own.left_out.add(x)
            out.append(x)
    return out


def tekken8_maps(fighters, ttt2, tekken7=None, references=()):
    """Tekken 8 -> TTT2 maps from the player's own files. fighters: Tekken 8 movesets (any number; their moves named
    where the reader could), ttt2: TTT2's movesets (all of them), tekken7: None, or optional extra evidence
    (Tekken 7 movesets, (requirement map, property map) of Tekken 7 -> TTT2, the importer's own: build_maps),
    references: other Tekken 8 fighters' movesets (named), each aligned with its partners only -> (requirement map,
    property map, reaction remap, hitbox remap, evidence). The references' evidence fills what the fighters' own
    leaves out (ids it does not map, reaction moves it has not seen): with it, 13 of the ids Reina's own evidence
    maps (as the route through Tekken 7 does too) would lose their mapping or change; it decides the hit locations
    (her attacks' hit boxes are few; with the references' 46 -> 37 and 47 -> 38 as through Tekken 7). Exceptions
    whose values do not fit TTT2's are left out, and so are the fighters' own the references' evidence outvotes
    (FIT_SHARE). With Tekken 7, an id the direct maps leave out maps through Tekken 7 (Tekken 8 -> Tekken 7 from the
    same alignment, then Tekken 7 -> TTT2)."""
    movesets7, maps7 = tekken7 if tekken7 else ([], None)
    every = list(fighters) + list(ttt2) + list(movesets7)
    for m, p in zip(every, own_prefixes(every)):
        if getattr(m, 'own_prefix', None) is None:
            m.own_prefix = p
    ev = collections.defaultdict(Evidence)
    for a in fighters:
        for b in ttt2:
            align(a, b, ev, wide=True)
    if references:
        wider = _copy(ev)
        names = [_names(t) for t in ttt2]
        for a in references:
            for b in partners(a, ttt2, names):
                align(a, b, wider, wide=True, reference=True)
    req, prop = _maps8(ev)
    mine, theirs = source_values(fighters), ttt2_values(ttt2)
    for m in (req, prop):
        distrust(m, mine, theirs)
    reactions = reaction_remap(ev)
    if references:
        req2, prop2 = _maps8(wider)
        for own, wide in ((req, req2), (prop, prop2)):
            distrust(wide, mine, theirs)
            outvoted(own, wide)
        req, prop = Combined(req, req2), Combined(prop, prop2)
        reactions = dict(reaction_remap(wider), **reactions)
        ev = wider
    if movesets7:
        ev7 = collections.defaultdict(Evidence)
        for a in fighters:
            for b in movesets7:
                align(a, b, ev7, wide=True)
        req7, prop7 = build_maps(ev7, 't8', 't7')
        req, prop = Combined(req, Chained(req7, maps7[0])), Combined(prop, Chained(prop7, maps7[1]))
    return req, prop, reactions, hitbox_remap(ev), ev
