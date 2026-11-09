"""Unit tests of a Tekken 8 fighter's summoned weapons and root points (convert/summons8.py, the weapon pairs of
tekken8/anim.py, retarget.descriptors / encode with pairs, weapons.append_tekken8, the moveset converter's hooks) on
made-up data (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_summons.py
"""
import collections
import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from ttt2char.convert import model, moveset, retarget as RT, summons8, weapons  # noqa: E402
from ttt2char.tekken8 import anim as T8, panm  # noqa: E402
from ttt2char.ttt2 import animation, bone  # noqa: E402
import test_retarget as TR  # noqa: E402
import test_tekken8_anim as TA  # noqa: E402

GENERIC = ((-100.0, 1000.0, 750.0), (-100.0, 1000.0, 300.0))


# ------------------------------------------------------------------------------------------------ made-up movesets
class Box:
    def __init__(self, loc, a, loc2, b):
        self.loc, self.a, self.loc2, self.b = loc, a, loc2, b


def move(boxes, key):
    """A Tekken 8 move of hit boxes [(loc, a, loc2, b)] (the first two: its summary codes) playing clip `key`."""
    hb = [Box(*x) for x in boxes] + [Box(0, (0, 0, 0), 0, (0, 0, 0))] * (2 - len(boxes))
    codes = [hb[0].loc, hb[0].loc2, hb[1].loc, hb[1].loc2]
    return dict(hitboxes=hb, hitbox=bytes(codes), key=key)


class Moveset:
    def __init__(self, moves, extra=(), end=()):
        self.tables = dict(moves=list(moves), extra_move_properties=[dict(r) for r in extra],
                           move_begin_props=[], move_end_props=[dict(r) for r in end])

    def anim_ref(self, i):
        return self.tables['moves'][i]['key'], 'com'


def definition(*weapons_):
    return types.SimpleNamespace(WEAPONS=[dict(w) for w in weapons_])


STAFF = dict(bone='staff', parent='TE_R_jnt', pair=0, summon=1)
TAIL = dict(bone='tail', parent='KOSHI_jnt', pair=3, summon=2)


class MaskRowsTest(unittest.TestCase):
    """Show and hide masks (SUMMON_MASKS): a row per bit, in a copy of the list; other lists and moves stay."""
    class Masks(Moveset):
        def iter_list(self, table, start, end):
            i = start
            while True:
                row = self.tables[table][i]
                yield i, row
                if end(row):
                    return
                i += 1

    def test_split(self):
        end = dict(id=0, frame=0, value=0, value2=0)
        extra = [dict(id=0x8001, frame=3, value=7, value2=0), end,
                 dict(id=0x83a6, frame=5, value=0b101, value2=0), dict(id=0x83a7, frame=9, value=0b10, value2=0),
                 dict(id=0x8001, frame=9, value=1, value2=0), end]
        k = self.Masks([dict(extraprops=0), dict(extraprops=2), dict(extraprops=2), dict()], extra=extra)
        d = types.SimpleNamespace(WEAPONS=[dict(summon=0), dict(summon=1)])
        stats = collections.Counter()
        summons8.split_masks(k, d, stats)
        moves = k.tables['moves']
        self.assertEqual([m.get('extraprops') for m in moves], [0, 6, 6, None])         # (one copy for both)
        rows = [(r['id'], r['frame'], r['value']) for r in k.tables['extra_move_properties'][6:]]
        self.assertEqual(rows, [(summons8.SUMMON, 5, 0), (summons8.DISMISS, 9, 1), (0x8001, 9, 1), (0, 0, 0)])
        self.assertEqual(stats['0x83a6 rows\' bits no weapon takes'], 1)                # (bit 2: no object of his)


class VarSlotsTest(unittest.TestCase):
    def test_rows(self):
        """A variable the definition names: its tests and sets become the flag slot's; other rows stay."""
        k = types.SimpleNamespace(tables=dict(requirements=[
            dict(condition=335, param=1), dict(condition=0x809b, param=1), dict(condition=336, param=1),
            dict(condition=0x809e, param=1)]))
        d = types.SimpleNamespace(TEKKEN8=dict(var_slots={3: (9, 2)}))
        stats = collections.Counter()
        summons8.vars_as_slots(k, d, stats)
        rows = k.tables['requirements']
        self.assertEqual((rows[0]['condition'], rows[0]['param'], rows[0]['param2']), (507, 9, 1))
        self.assertEqual((rows[1]['condition'], rows[1]['param'], rows[1]['param2'], rows[1]['param3']),
                         (0x815a, 9, 2, 1))
        self.assertEqual(rows[2:], [dict(condition=336, param=1), dict(condition=0x809e, param=1)])

    def test_no_slots(self):
        k = types.SimpleNamespace(tables=dict(requirements=[dict(condition=335, param=1)]))
        summons8.vars_as_slots(k, types.SimpleNamespace(), collections.Counter())
        self.assertEqual(k.tables['requirements'], [dict(condition=335, param=1)])


class Sphere(Box):
    def __init__(self, loc, a, loc2, b, radius=0):
        Box.__init__(self, loc, a, loc2, b)
        self.radius = radius


class JointSpotsTest(unittest.TestCase):
    JOINTS = {121: ('R_Hand', 9), 131: ('ATH_R_katana', None)}
    STANDARD = {131: (0.0, 730.0, 0.0)}

    def spots(self, *boxes, every=()):
        return summons8.joint_spots(boxes, self.JOINTS, self.STANDARD, every)

    def test_plain_moves_have_none(self):
        """Body codes and the weapon's own point: the move's codes do."""
        self.assertIsNone(self.spots(Sphere(9, (0, 0, 0), 0, (0, 0, 0)),
                                     Sphere(131, (0, 730, 0), 0, (0, 0, 0))))

    def test_other_offset_follows_the_joint(self):
        got = self.spots(Sphere(131, (0, 1200, 0), 9, (0, 0, 0)), Sphere(0, (0, 0, 0), 0, (0, 0, 0)))
        self.assertEqual(got[0], (summons8.JOINT_SPOT, 'ATH_R_katana', (0.0, 1200.0, 0.0), (0.0, 0.0, 0.0)))
        self.assertEqual(got[1:], [9, 0, 0])

    def test_hand_line_near_the_joint(self):
        """Near its joint an end is the body code at the joint; the far end follows the joint (a gun's line)."""
        got = self.spots(Sphere(121, (100, 0, 0), 121, (5000, 0, 0)), Sphere(0, (0, 0, 0), 0, (0, 0, 0)))
        self.assertEqual(got[0], 9)
        self.assertEqual(got[1], (summons8.JOINT_SPOT, 'R_Hand', (5000.0, 0.0, 0.0), (0.0, 0.0, 0.0)))

    def test_short_thick_line_is_a_sphere_at_the_joint(self):
        """A flashlight's box, its round ends longer than the line; a gun's long thick line stays a line."""
        got = self.spots(Sphere(121, (0, -160, 160), 121, (0, 0, 0), 200), Sphere(0, (0, 0, 0), 0, (0, 0, 0)))
        self.assertEqual(got[0], (summons8.JOINT_SPOT, 'R_Hand', (0.0, 0.0, 0.0), (0.0, 0.0, 200.0)))
        self.assertEqual(got[1], 9)
        got = self.spots(Sphere(121, (2000, 0, 0), 121, (0, 0, 0), 150), Sphere(0, (0, 0, 0), 0, (0, 0, 0)))
        self.assertEqual(got[0], (summons8.JOINT_SPOT, 'R_Hand', (2000.0, 0.0, 0.0), (0.0, 0.0, 0.0)))

    def test_sphere_is_a_line_of_its_radius(self):
        """A grenade's sphere: its point lifted by the largest radius of that spot, to the body code."""
        grown = Sphere(121, (0, 0, 0), 121, (0, 0, 0), 800)
        got = self.spots(Sphere(121, (0, 0, 0), 121, (0, 0, 0), 400), Sphere(121, (0, 0, 0), 121, (0, 0, 0), 400),
                         every=(grown,))
        self.assertEqual(got[0], (summons8.JOINT_SPOT, 'R_Hand', (0.0, 0.0, 0.0), (0.0, 0.0, 800.0)))
        self.assertEqual(got[1], 9)
        self.assertEqual(got[2], (summons8.JOINT_SPOT, 'R_Hand', (0.0, 0.0, 0.0), (0.0, 560.0, 560.0)))
        self.assertEqual(got[3], 9)

    def test_joint_that_leaves_the_hand(self):
        """AT_JOINT: an end near the joint, a sphere's far end too, follows the joint, not the hand's body code."""
        joints = {121: ('R_Have', summons8.AT_JOINT)}
        got = summons8.joint_spots((Sphere(121, (0, -100, 0), 121, (0, 0, 0)), Sphere(0, (0, 0, 0), 0, (0, 0, 0))), joints, {})
        self.assertEqual(got[0], (summons8.JOINT_SPOT, 'R_Have', (0.0, -100.0, 0.0), (0.0, 0.0, 0.0)))
        self.assertEqual(got[1], (summons8.JOINT_SPOT, 'R_Have', (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))
        got = summons8.joint_spots((Sphere(121, (0, 0, 0), 121, (0, 0, 0), 300), Sphere(0, (0, 0, 0), 0, (0, 0, 0))), joints, {})
        self.assertEqual(got[0], (summons8.JOINT_SPOT, 'R_Have', (0.0, 0.0, 0.0), (0.0, 0.0, 300.0)))
        self.assertEqual(got[1], (summons8.JOINT_SPOT, 'R_Have', (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))

    def test_ground_origin_stays_an_offset(self):
        got = self.spots(Sphere(121, (0, 0, 0), 125, (0, 900, 900)), Sphere(0, (0, 0, 0), 0, (0, 0, 0)))
        self.assertEqual(got[1], (0.0, 900.0, 900.0))


class WideRootBoxTest(unittest.TestCase):
    def test_column_replaces_the_second_box(self):
        """Boxes 0 and 1 points on his arm with no reach, box 2 a column round the ground origin (IAI.d+2)."""
        fist = Sphere(5, (0, 0, 0), 5, (0, 0, 0))
        column = Sphere(125, (0, 1100, 0), 125, (0, 1100, 1500), 300)
        hb = (fist, Sphere(6, (0, 0, 0), 6, (0, 0, 0)), column, Sphere(0, (0, 0, 0), 0, (0, 0, 0)))
        place = lambda code: code
        self.assertIs(summons8.summary(hb, place, True, True)[1], column)
        self.assertIsNot(summons8.summary(hb, place, True, False)[1], column)


class SummonsTest(unittest.TestCase):
    def test_summon_of(self):
        self.assertEqual([summons8.summon_of(b) for b in (1, 2, 4, 8, 16)], [0, 1, 2, 3, 4])
        self.assertEqual([summons8.summon_of(b) for b in (0, 3, 32, 64, -1)], [None] * 5)

    def test_show_rows(self):
        """0x8410 bit, value2 1 / 0 -> the summon / dismiss id, value the summon number, in every property table;
        bits past the summons stay as they are (dropped later)."""
        k = Moveset([], extra=[dict(id=0x8410, value=4, value2=1), dict(id=0x8410, value=32, value2=1),
                               dict(id=0x8001, value=4, value2=1)],
                    end=[dict(id=0x8410, value=1, value2=0)])
        log = []
        summons8.prepare(k, definition(STAFF), log=log.append)
        ex, end = k.tables['extra_move_properties'], k.tables['move_end_props']
        self.assertEqual((ex[0]['id'], ex[0]['value']), (summons8.SUMMON, 2))
        self.assertEqual((ex[1]['id'], ex[1]['value']), (0x8410, 32))
        self.assertEqual((ex[2]['id'], ex[2]['value']), (0x8001, 4))
        self.assertEqual((end[0]['id'], end[0]['value']), (summons8.DISMISS, 0))
        self.assertTrue(any('left out' in line for line in log))

    def test_show_rows_need_summoned_weapons(self):
        k = Moveset([], extra=[dict(id=0x8410, value=4, value2=1)])
        summons8.prepare(k, definition(), log=lambda s: None)
        self.assertEqual(k.tables['extra_move_properties'][0]['id'], 0x8410)

    def test_the_summon_ids_become_ttt2s(self):
        """The moveset converter's overrides take the summon / dismiss ids (end properties too) to TTT2's."""
        self.assertEqual(moveset.PROP_OVERRIDE['t8'][summons8.SUMMON], moveset.TT_SUMMON)
        self.assertEqual(moveset.PROP_OVERRIDE['t8'][summons8.DISMISS], moveset.TT_DISMISS)
        self.assertEqual((moveset.HIT_POINT8[138], moveset.HIT_POINT8[139], moveset.HIT_POINT8[22]), (40, 39, 5))

    def test_roots(self):
        """Each clip of a move hitting from the ground origin: its first two distinct offsets; another move of the
        clip with other offsets is a conflict, its codes the nearest of the clip's."""
        far = ((-100.0, 1400.0, 1200.0), (-100.0, 550.0, 500.0))
        k = Moveset([move([(125, GENERIC[0], 125, GENERIC[1])], 7),
                     move([(9, (0, 0, 0), 37, (0, 0, 0))], 8),
                     move([(125, far[0], 125, far[1])], 7),
                     move([(125, (0, 1300, 280), 0, (0, 0, 0)), (125, (0, 1300, 160), 0, (0, 0, 0))], 9)])
        r = summons8.roots(k)
        self.assertEqual(dict(r), {7: list(GENERIC), 9: [(0.0, 1300.0, 280.0), (0.0, 1300.0, 160.0)]})
        self.assertEqual(r.moves, {0: 7, 2: 7, 3: 9})
        self.assertEqual(dict(r.conflicts), {7: 1})
        self.assertTrue(summons8.uses_roots(k))
        got = summons8.prepare(k, definition(), log=lambda s: None)
        self.assertEqual(got, dict(r))
        hb = [bytes(m['hitbox']) for m in k.tables['moves']]
        self.assertEqual(hb[0], bytes([0xFA, 0xFB, 0, 0]))
        self.assertEqual(hb[1], bytes([9, 37, 0, 0]))
        self.assertEqual(hb[2], bytes([0xFA, 0xFB, 0, 0]))       # (1.4 m up 1.2 m ahead -> A, 0.55 m up -> B)
        self.assertEqual(hb[3], bytes([0xFA, 0, 0xFB, 0]))

    def test_no_roots(self):
        k = Moveset([move([(9, (0, 0, 0), 37, (0, 0, 0))], 8)])
        self.assertFalse(summons8.uses_roots(k))
        self.assertEqual(summons8.prepare(k, definition(), log=lambda s: None), {})
        self.assertEqual(summons8.weapons(definition(STAFF), k), [STAFF])

    def test_root_weapons(self):
        """The root points' two hit-only weapons: under HARA_ROT1, pairs after the definition's, never summoned,
        their points the root codes at slots 2 / 3."""
        k = Moveset([move([(125, GENERIC[0], 125, GENERIC[1])], 7)])
        w = summons8.weapons(definition(STAFF, TAIL), k)
        self.assertEqual(w[:2], [STAFF, TAIL])
        self.assertEqual([(x['bone'], x['parent'], x['pair'], x['summon'], x['root']) for x in w[2:]],
                         [('root_a', 'HARA_ROT1', 4, 63, 0), ('root_b', 'HARA_ROT1', 5, 63, 1)])
        self.assertEqual(w[2]['points'], {0xFA: ('origin', 2)})
        self.assertEqual(w[3]['points'], {0xFB: ('origin', 3)})
        self.assertEqual(summons8.weapons(definition(), k)[0]['pair'], 0)
        with self.assertRaises(ValueError):
            summons8.weapons(definition(dict(STAFF, pair=19)), k)

    def test_tolerates_other_movesets(self):
        self.assertFalse(summons8.uses_roots(object()))
        self.assertEqual(summons8.prepare(object(), definition(STAFF), log=lambda s: None), {})


ZERO = (0, 0, 0)
LEAD, TOE, FOOT, KNEE, HIPS = 121, 47, 16, 140, 33     # made-up codes: a weapon's point, a toe on its foot, ...
PLACE = {LEAD: 70, TOE: 16, KNEE: 15, HIPS: 3}.get


def place(x):
    return PLACE(x, x)


def boxes(*b):
    """Hit boxes (loc, loc2[, a, b]), padded to eight with empty ones."""
    out = [Box(x[0], x[2] if len(x) > 2 else ZERO, x[1], x[3] if len(x) > 3 else ZERO) for x in b]
    return out + [Box(0, ZERO, 0, ZERO) for _ in range(8 - len(out))]


class SummaryTest(unittest.TestCase):
    """The two hit boxes a move's TTT2 summary takes (summons8.summary, prepare's place)."""

    def test_box_1_on_another_line_stays(self):
        hb = boxes((13, 0), (39, 0), (13, 12))                  # a jab: both fists' paths
        self.assertEqual(summons8.summary(hb, place), (hb[0], hb[1]))

    def test_the_same_points_with_offsets(self):
        """Box 1 on box 0's points (its offsets lost in TTT2) gives way to the first later box on another line: the
        tail's lead twice, then lead -> 1.3 m up in front of her (the ground origin), then lead -> hips."""
        up = (0.0, 1300.0, 300.0)
        hb = boxes((LEAD, 0), (LEAD, 0, (0, -200, 0), up), (LEAD, 125, (0, -200, 0), up), (LEAD, HIPS))
        self.assertEqual(summons8.summary(hb, place), (hb[0], hb[2]))
        self.assertEqual(summons8.line(hb[2], place), (70, ('origin', up)))
        self.assertEqual(summons8.summary(hb, place, roots=False), (hb[0], hb[3]))     # (no root points)

    def test_two_points_on_one_place(self):
        """A toe TTT2 places on its foot's bone: the foot's path twice -> the next box, foot -> knee."""
        hb = boxes((FOOT, 0), (TOE, 0), (FOOT, KNEE), (TOE, KNEE))
        self.assertEqual(summons8.summary(hb, place), (hb[0], hb[2]))

    def test_an_empty_box_1(self):
        hb = boxes((9, 0), (0, 0), (125, 125, (0, 200, 1500), (0, 2100, 500)))
        self.assertEqual(summons8.summary(hb, place), (hb[0], hb[2]))
        self.assertEqual(summons8.summary(hb, place, roots=False), (hb[0], hb[1]))

    def test_what_adds_nothing(self):
        """A line both ways round and one point of box 0's line are box 0's; with nothing else, box 1 stays."""
        hb = boxes((9, 8), (8, 9), (9, 9, (720, 0, 650), (-100, 0, 900)), (9, 13))
        self.assertEqual(summons8.summary(hb, place), (hb[0], hb[3]))
        hb = boxes((18, 21), (18, 21, (80, -50, 0)))
        self.assertEqual(summons8.summary(hb, place), (hb[0], hb[1]))
        hb = boxes((9, 0), (13, 0))
        self.assertIs(summons8.summary(hb, place)[1], hb[1])
        hb = boxes()
        self.assertEqual(summons8.summary(hb, place), (hb[0], hb[1]))

    def test_prepare(self):
        """prepare(place): the summary's boxes and codes, those at the ground origin its root points (the clip's
        offsets from the box chosen); a move whose box 1 stays keeps its bytes; no place: boxes 0 and 1."""
        up = (0.0, 1300.0, 300.0)
        tail = [(LEAD, ZERO, 0, ZERO), (LEAD, (0, -200, 0), 0, up), (LEAD, (0, -200, 0), 125, up),
                (LEAD, ZERO, HIPS, ZERO)]
        jab = [(13, ZERO, 0, ZERO), (39, ZERO, 0, ZERO)]
        k = Moveset([move(tail, 4), move(jab, 5), move([(125, GENERIC[0], 125, GENERIC[1])], 6)])
        log = []
        got = summons8.prepare(k, definition(), log=log.append, place=place)
        mv = k.tables['moves']
        self.assertEqual(mv[0]['hitbox'], bytes([LEAD, 0, LEAD, 0xFA]))
        self.assertIs(mv[0]['summary'][1], mv[0]['hitboxes'][2])
        self.assertEqual(got[4], [up])
        self.assertEqual(mv[1]['hitbox'], bytes([13, 0, 39, 0]))
        self.assertNotIn('summary', mv[1])
        self.assertEqual(mv[2]['hitbox'], bytes([0xFA, 0xFB, 0, 0]))
        self.assertTrue(any('later hit box' in line and line.endswith(': 1') for line in log))
        k = Moveset([move(tail[:2], 4)])
        k.tables['moves'][0]['hitboxes'] = [Box(*x) for x in tail]
        self.assertEqual(summons8.prepare(k, definition(), log=lambda s: None), {})
        self.assertEqual(k.tables['moves'][0]['hitbox'], bytes([LEAD, 0, LEAD, 0]))

    def test_clip_points_stay(self):
        """A clip's root points stay those of boxes 0 and 1 of its moves: a move whose summary took a later box at
        other offsets counts after them (a conflict, its codes the nearest)."""
        area = (0.0, 600.0, 1500.0)
        k = Moveset([move([(9, ZERO, 0, ZERO), (0, ZERO, 0, ZERO)], 3), move([(125, area, 0, ZERO)], 3)])
        k.tables['moves'][0]['hitboxes'] = [Box(*x) for x in [(9, ZERO, 0, ZERO), (0, ZERO, 0, ZERO),
                                                              (125, (0, 200, 1500), 125, (0, 2100, 500))]]
        got = summons8.prepare(k, definition(), log=lambda s: None, place=place)
        self.assertEqual(got, {3: [area]})
        self.assertEqual([m['hitbox'] for m in k.tables['moves']], [bytes([9, 0, 0xFA, 0xFA]), bytes([0xFA, 0, 0, 0])])

    def test_hit_location(self):
        """The converter's hit_location is the module's, which prepare's place uses: a weapon's point, a Tekken 8
        limb point (HIT_POINT8), the id maps', HIT_LOCATION's."""
        self.assertEqual(moveset.hit_location('t8', LEAD, {LEAD: 70}, {}), 70)
        self.assertEqual(moveset.hit_location('t8', TOE, {}, {TOE: 38}), 16)
        self.assertEqual(moveset.hit_location('t8', 21, {}, {21: 19}), 19)
        self.assertEqual(moveset.hit_location('t8', 133, {}, {}), 0)
        self.assertEqual(moveset.hit_location('t7', TOE, {}, {TOE: 38}), 38)


# ------------------------------------------------------------------------------------------------ channels
class DescriptorsTest(unittest.TestCase):
    def test_descriptors(self):
        self.assertEqual(RT.descriptors(23), tuple(animation.BODY_DESCRIPTORS))
        self.assertEqual(RT.descriptors(27), tuple(animation.BODY_DESCRIPTORS) + RT.PAIR_DESCRIPTORS * 2)
        self.assertEqual(RT.descriptors(25, animation.RAW)[:23], RT.RAW_DESCRIPTORS)
        for bad in (22, 24):
            with self.assertRaises(ValueError):
                RT.descriptors(bad)

    def test_encode_with_pairs(self):
        rng = np.random.default_rng(5)
        v = TR.smooth_values(12)
        pairs = np.zeros((12, 4, 3))
        pairs[:, 0] = rng.uniform(-300, 300, (12, 3))
        pairs[:, 1] = rng.uniform(-1, 1, (12, 3))
        pairs[:, 2] = rng.uniform(-300, 300, (12, 3))
        pairs[:, 3] = rng.uniform(-1, 1, (12, 3))
        values = np.concatenate([v, pairs], 1)
        for kind in (animation.COMPRESSED, animation.RAW):
            vals = values if kind == animation.COMPRESSED else animation.to_raw(
                list(RT.descriptors(27)), values, animation.COMPRESSED)
            a = animation.decode(RT.encode(vals, kind))
            self.assertEqual(a['values'].shape, (12, 27, 3))
            self.assertEqual(list(a['descriptors']), list(RT.descriptors(27, kind)))
            np.testing.assert_allclose(a['values'][:, 23::2], vals[:, 23::2], atol=0.5)
            got = animation.local_rotation(a['values'][:, 24::2], kind)
            want = animation.local_rotation(vals[:, 24::2], kind)
            self.assertLess(RT.angle(got, want).max(), 1e-2)
        self.assertEqual(animation.header(RT.encode(v))['nch'], 23)

    def test_shift_counts_the_pairs(self):
        v = np.concatenate([TR.smooth_values(4) * 0.1, np.zeros((4, 2, 3))], 1)
        quiet = RT.rotation_shift(v)
        v[:, 24, 0] = np.pi
        self.assertGreater(RT.rotation_shift(v), quiet)
        self.assertEqual(RT.rotation_shift(v[:, :23]), quiet)


# ------------------------------------------------------------------------------------------------ weapon pairs
def rotations(rng, n):
    return np.array([TR.random_rotation(rng) for _ in range(n)])


class PairValuesTest(unittest.TestCase):
    """pair_values against the runtime's convention: the weapon bone's world = its TTT2 parent's world x the pair."""

    def setUp(self):
        rng = np.random.default_rng(11)
        self.F = F = 5
        names = ['Drv', 'Anc', 'Joint', 'Link', 'Tip']
        self.idx = {n: i for i, n in enumerate(names)}
        self.WR = np.stack([rotations(rng, len(names)) for _ in range(F)])
        self.Wp = rng.uniform(-500, 1500, (F, len(names), 3))
        self.O = TR.random_rotation(rng)
        self.values = TR.smooth_values(F)
        self.bind = (np.array([1.0, 2.0, 3.0]), TR.random_rotation(rng))
        self.pairs = [dict(kind='joint', joint='Joint', driver='Drv', offset=self.O, anchor='Anc'),
                      dict(kind='joint', joint='Link', up='Joint'),
                      dict(kind='lead', joints=['Joint', 'Link', 'Tip'], tip=130.0, driver='Drv', offset=self.O,
                           anchor='Anc'),
                      None,
                      dict(kind='root', root=1, bind=self.bind),
                      dict(kind='still', bind=self.bind)]
        self.conv = types.SimpleNamespace(sub=types.SimpleNamespace(index=self.idx), pairs=self.pairs, scale=0.98,
                                          kind=animation.COMPRESSED)

    def local(self, out, p):
        R = animation.local_rotation(out[:, 2 * p + 1], animation.COMPRESSED)
        return R, out[:, 2 * p]

    def test_joint_and_link(self):
        out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, 1.0, None, 5)
        self.assertEqual(out.shape, (self.F, 10, 3))
        i = self.idx
        PR, Pp = self.WR[:, i['Drv']] @ self.O, self.Wp[:, i['Anc']]             # the TTT2 parent's world
        R, t = self.local(out, 0)
        self.assertLess(RT.angle(PR @ R, self.WR[:, i['Joint']]).max(), 1e-6)
        np.testing.assert_allclose(Pp + np.einsum('fij,fj->fi', PR, t), self.Wp[:, i['Joint']], atol=1e-6)
        R, t = self.local(out, 1)                                                # under the weapon before it
        self.assertLess(RT.angle(self.WR[:, i['Joint']] @ R, self.WR[:, i['Link']]).max(), 1e-6)
        np.testing.assert_allclose(self.Wp[:, i['Joint']] + np.einsum('fij,fj->fi', self.WR[:, i['Joint']], t),
                                   self.Wp[:, i['Link']], atol=1e-6)

    def test_lead(self):
        """The most forward of the joints and the tip past the last one (along its x), the parent's rotation."""
        out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, 1.0, None, 5)
        i = self.idx
        tip = self.Wp[:, i['Tip']] + 130.0 * self.WR[:, i['Tip']][:, :, 0]
        cands = np.stack([self.Wp[:, i['Joint']], self.Wp[:, i['Link']], self.Wp[:, i['Tip']], tip], 1)
        want = cands[np.arange(self.F), np.argmax(cands[:, :, 2], 1)]
        PR, Pp = self.WR[:, i['Drv']] @ self.O, self.Wp[:, i['Anc']]
        R, t = self.local(out, 2)
        np.testing.assert_allclose(Pp + np.einsum('fij,fj->fi', PR, t), want, atol=1e-6)
        self.assertLess(RT.angle(R, np.eye(3)[None]).max(), 1e-9)

    def test_gap_and_root(self):
        """A pair no weapon takes: the identity; a root point: at the ground origin's offset (the root scale and
        the size scale as the body's root), else its bind."""
        o = [(0.0, 1300.0, 280.0), (0.0, 1300.0, 160.0)]
        k = 1.07
        out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, k, o, 5)
        R, t = self.local(out, 3)
        np.testing.assert_allclose(t, 0)
        self.assertLess(RT.angle(R, np.eye(3)[None]).max(), 1e-9)
        R, t = self.local(out, 4)
        H = animation.local_rotation(self.values[:, RT.HARA_CH], animation.COMPRESSED)
        world = 0.98 * self.values[:, 1] + np.einsum('fij,fj->fi', H, t)          # HARA_ROT1 x the pair
        np.testing.assert_allclose(world, np.repeat([np.multiply(0.98 * k, o[1])], self.F, 0), atol=1e-6)
        self.assertLess(RT.angle(R, np.eye(3)[None]).max(), 1e-9)
        out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, k, None, 5)
        R, t = self.local(out, 4)
        np.testing.assert_allclose(t, np.repeat(self.bind[0][None], self.F, 0), atol=1e-9)
        self.assertLess(RT.angle(R, self.bind[1][None]).max(), 1e-6)

    def test_joint_point(self):
        """A root point following a joint: the joint's point in the fighter's frame (the source's frame turned by the
        calibration's C), each frame, plus its delta."""
        C = TR.random_rotation(np.random.default_rng(8))
        conv = types.SimpleNamespace(sub=types.SimpleNamespace(index=dict(self.idx, **{T8.TOP: self.idx['Anc']})),
                                     pairs=self.pairs, scale=0.98, kind=animation.COMPRESSED,
                                     cal=types.SimpleNamespace(C=C))
        off, delta = np.array([10.0, 20.0, 30.0]), np.array([0.0, 0.0, 200.0])
        spot = (summons8.JOINT_SPOT, 'Joint', tuple(off), tuple(delta))
        k = 1.07
        out = T8.pair_values(conv, self.WR, self.Wp, self.values, k, [spot, spot], 5)
        R, t = self.local(out, 4)
        H = animation.local_rotation(self.values[:, RT.HARA_CH], animation.COMPRESSED)
        world = 0.98 * self.values[:, 1] + np.einsum('fij,fj->fi', H, t)
        i = self.idx
        at = self.Wp[:, i['Joint']] + np.einsum('fij,j->fi', self.WR[:, i['Joint']], off) - self.Wp[:, i['Anc']]
        np.testing.assert_allclose(world, 0.98 * k * (at @ C.T + delta), atol=1e-6)
        self.assertLess(RT.angle(R, np.eye(3)[None]).max(), 1e-9)

    def test_ground(self):
        """A ground pair: the scene's origin (where Top is at the clip's frame 0); not held, where Top is each frame."""
        H = animation.local_rotation(self.values[:, RT.HARA_CH], animation.COMPRESSED)
        turn = animation.local_rotation(self.values[:, RT.TURN], animation.COMPRESSED)
        for follow in (False, True):
            conv = types.SimpleNamespace(sub=self.conv.sub, scale=0.98, kind=animation.COMPRESSED,
                                         pairs=self.pairs[:6] + [dict(kind='ground', follow=follow, bind=self.bind)])
            R, t = self.local(T8.pair_values(conv, self.WR, self.Wp, self.values, 1.0, None, 7, ground=True), 6)
            world = 0.98 * self.values[:, 1] + np.einsum('fij,fj->fi', H, t)       # HARA_ROT1 x the pair, from Top
            moved = 0.98 * np.einsum('fij,fj->fi', turn, self.values[:, 0])         # Top, from where it was at 0
            np.testing.assert_allclose(world, 0 * moved if follow else -moved, atol=1e-6)
            self.assertLess(RT.angle(H @ R, turn).max(), 1e-6)

    def test_scene_point(self):
        """A hold clip's path point: from the scene's origin (where Top was at frame 0); the scene where he is (every
        ground following him), from Top each frame."""
        F = self.F
        path = np.random.default_rng(3).uniform(-900, 900, (F, 3))
        H = animation.local_rotation(self.values[:, RT.HARA_CH], animation.COMPRESSED)
        turn = animation.local_rotation(self.values[:, RT.TURN], animation.COMPRESSED)
        moved = 0.98 * np.einsum('fij,fj->fi', turn, self.values[:, 0])
        for follows in (False, True):
            conv = types.SimpleNamespace(sub=self.conv.sub, scale=0.98, kind=animation.COMPRESSED, follows=follows,
                                         scene=lambda clip, joint: (path, np.repeat(np.eye(3)[None], F, 0)))
            t = T8.root_point(conv, self.WR, self.Wp, self.values, 1.0, ('scene', 'J', (0, 0, 0), (0, 0, 0), 0, 1))
            world = 0.98 * self.values[:, 1] + np.einsum('fij,fj->fi', H, t)
            want = np.einsum('fij,fj->fi', turn, path)
            np.testing.assert_allclose(world, want if follows else want - moved, atol=1e-6)

    def test_still(self):
        """A still pair (a hit-only weapon holding its place in the order): its bind in every frame, offsets or not."""
        for roots in (None, [(0.0, 1300.0, 280.0)]):
            out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, 1.0, roots, 6)
            R, t = self.local(out, 5)
            np.testing.assert_allclose(t, np.repeat(self.bind[0][None], self.F, 0), atol=1e-9)
            self.assertLess(RT.angle(R, self.bind[1][None]).max(), 1e-6)


def target_with(weapons_):
    """A TTT2 skeleton (test_retarget's) with KOSHI and the weapons' bones appended as append_tekken8 names them."""
    bon = TR.ttt2_bon()
    bon['opt'] = [0] * len(bon['names'])
    for w in weapons_:
        hw = bone.world_matrices(bon)
        world = hw[weapons.parent_index(bon, w['parent'])].copy()
        pts = [(code, slot, world[:3, 3]) for code, (where, slot) in sorted(w.get('points', {}).items())]
        bon = weapons.append_tekken8(bon, w, world, pts)[0]
    return bon


class PairSpecsTest(unittest.TestCase):
    def setUp(self):
        self.sk = types.SimpleNamespace(index={n: i for i, n in enumerate(
            ['C_Leg', 'Rot', 'R_Hand', 'ATH_staff', 'tail_01', 'tail_03', 'tail_05'])})
        self.cal = types.SimpleNamespace(drivers={'KOSHI_jnt': 'C_Leg', 'TE_R_jnt': 'R_Hand'},
                                         offsets={'KOSHI_jnt': np.eye(3), 'TE_R_jnt': np.eye(3)})
        self.weapons = [dict(bone='ATH_staff', parent='TE_R_jnt', pair=0),
                        dict(bone='tail_01', parent='KOSHI_jnt', pair=1),
                        dict(bone='tail_03', parent='tail_01', pair=2),
                        dict(bone='lead', parent='KOSHI_jnt', pair=3, lead=('tail_03', 'tail_05'), tip_cm=13),
                        dict(bone='root_b', parent='HARA_ROT1', pair=5, root=1, points={0xFB: ('origin', 3)}),
                        dict(bone='snake', parent='TE_R_jnt', pair=4, still=True, points={0x79: ('origin', 0)}),
                        dict(bone='horn', parent='TE_R_jnt', points={0x23: ('origin', 1)})]

    def test_kinds(self):
        specs = T8.pair_specs(self.sk, target_with(self.weapons), self.weapons, self.cal)
        self.assertEqual(len(specs), 6)
        self.assertEqual([s['kind'] for s in specs], ['joint', 'joint', 'joint', 'lead', 'still', 'root'])
        self.assertEqual((specs[0]['driver'], specs[0]['anchor']), ('R_Hand', 'R_Hand'))
        self.assertEqual((specs[1]['driver'], specs[1]['anchor']), ('C_Leg', 'Rot'))    # (KOSHI sits at Rot)
        self.assertEqual(specs[2]['up'], 'tail_01')
        self.assertEqual((specs[3]['joints'], specs[3]['tip']), (['tail_03', 'tail_05'], 130.0))
        self.assertEqual(specs[5]['root'], 1)
        self.assertEqual(T8.pair_joints(specs), sorted(['ATH_staff', 'C_Leg', 'R_Hand', 'Rot', 'tail_01',
                                                         'tail_03', 'tail_05']))

    def test_errors(self):
        target = target_with(self.weapons)
        with self.assertRaises(ValueError):                     # no bone for it
            T8.pair_specs(self.sk, target, self.weapons + [dict(bone='x', parent='TE_R_jnt', pair=7)], self.cal)
        bad = [dict(bone='root_a', parent='TE_R_jnt', pair=0, root=0)]
        with self.assertRaises(ValueError):                     # a root point under another bone
            T8.pair_specs(self.sk, target_with(bad), bad, self.cal)
        bad = [dict(bone='ATH_none', parent='TE_R_jnt', pair=0)]
        with self.assertRaises(ValueError):                     # no such joint
            T8.pair_specs(self.sk, target_with(bad), bad, self.cal)


class RootConverterTest(unittest.TestCase):
    """A made-up fighter's clip with root points: 23 channels without offsets, the pairs with them; the points
    posed as the runtime poses them sit at the offsets (scaled as the body's root)."""

    def test_root_pairs(self):
        roots = [dict(bone='root_a', parent='HARA_ROT1', pair=0, root=0, summon=63, points={0xFA: ('origin', 2)}),
                 dict(bone='root_b', parent='HARA_ROT1', pair=1, root=1, summon=63, points={0xFB: ('origin', 3)})]
        bon = target_with(roots)
        fighter = TA.Fighter(TR.ttt2_bon())
        cv = T8.Converter(fighter.sk, bon, weapons=roots)
        clip = panm.Animation(fighter.clip(TR.smooth_values(10)))
        plain, info = cv.channels(clip)
        self.assertEqual((plain.shape[1], info['pairs']), (23, 0))
        out, info = cv.channels(clip, list(GENERIC))
        self.assertEqual((out.shape[1], info['pairs']), (27, 2))
        np.testing.assert_allclose(out[:, :23], plain, atol=1e-9)
        H = animation.local_rotation(out[:, RT.HARA_CH], animation.COMPRESSED)
        for r in range(2):
            world = cv.scale * out[:, 1] + np.einsum('fij,fj->fi', H, out[:, 23 + 2 * r])
            np.testing.assert_allclose(world, np.repeat([np.multiply(cv.scale * info['root_scale'], GENERIC[r])],
                                                        10, 0), atol=1e-6)
        a = animation.decode(cv.animation(fighter.clip(TR.smooth_values(10)), roots=list(GENERIC)))
        self.assertEqual(a['values'].shape[1], 27)
        self.assertEqual(cv.last_pairs, 2)

    def test_provider_roots(self):
        """Clips of root moves are converted with their offsets, even where TTT2 has the clip's original."""
        calls = []
        conv = types.SimpleNamespace(animation=lambda blob, roots=None: calls.append(roots) or b'x', pairs=[1],
                                     last_pairs=2)
        banks = types.SimpleNamespace(blob=lambda cat, key: b'clip', where=lambda cat, key: 'own')
        p = T8.Animations(banks, conv, originals={5: 0x123, 6: 0x456}, roots={5: list(GENERIC)})
        self.assertEqual(p(5, 'com'), b'x')
        self.assertEqual(p(6, 'com'), 0x456)
        self.assertEqual(p(7, 'own'), b'x')
        self.assertEqual(calls, [list(GENERIC), None])
        self.assertEqual(p.stats['body animations with weapon pairs (root points too)'], 1)


# ------------------------------------------------------------------------------------------------ skeleton
class GroundPairTest(unittest.TestCase):
    """The scene's ground pair (prefabs8.py): following him, where his Top is each frame; in a held clip (a definition's
    held_moves: a throw's scene), where the move began, his travel taken back, as a ground that is not followed."""

    def setUp(self):
        self.F = 5
        self.values = TR.smooth_values(self.F)
        self.values[:, 0] = np.linspace(0.0, -4400.0, self.F)[:, None] * np.array([0.1, 0.0, 1.0])  # Top: 4.4 m back

    def world(self, follow, ground):
        conv = types.SimpleNamespace(sub=types.SimpleNamespace(index={}), pairs=[dict(kind='ground', follow=follow)],
                                     scale=0.98, kind=animation.COMPRESSED, follows=follow)
        out = T8.pair_values(conv, None, None, self.values, 1.0, None, 1, None, ground)
        H = animation.local_rotation(self.values[:, RT.HARA_CH], animation.COMPRESSED)
        return 0.98 * self.values[:, 1] + np.einsum('fij,fj->fi', H, out[:, 0])     # HARA_ROT1 x the pair

    def test_following_ground_is_at_his_top(self):
        np.testing.assert_allclose(self.world(True, True), 0, atol=1e-6)

    def test_held_clip_takes_his_travel_back(self):
        turn = animation.local_rotation(self.values[:, RT.TURN], animation.COMPRESSED)
        want = -0.98 * np.einsum('fij,fj->fi', turn, self.values[:, 0])
        np.testing.assert_allclose(self.world(True, T8.HELD), want, atol=1e-6)
        np.testing.assert_allclose(self.world(False, True), want, atol=1e-6)
        self.assertGreater(np.linalg.norm(want[-1]), 4000)

    def test_animations_pass_held_for_its_clips(self):
        seen = {}

        def animation_(blob, **extra):
            seen[blob] = extra.get('ground')
            return b''
        banks = types.SimpleNamespace(blob=lambda kind, key: key, where=lambda kind, key: 'own')
        cache = T8.Animations(banks, types.SimpleNamespace(animation=animation_), ground={1, 2}, held={2})
        cache(1), cache(2), cache(3)
        self.assertEqual(seen, {1: True, 2: T8.HELD, 3: None})


class AppendTest(unittest.TestCase):
    def test_append_tekken8(self):
        bon = TR.ttt2_bon()
        bon['opt'] = [0] * len(bon['names'])
        world = np.eye(4)
        world[:3, :3] = TR.random_rotation(np.random.default_rng(3))
        world[:3, 3] = (100.0, 900.0, 50.0)
        tip = np.array([100.0, 900.0, 330.0])
        skel, index, number, used = weapons.append_tekken8(bon, dict(bone='horn', parent='MUNE2_jnt', summon=3),
                                                           world, [(0x23, 1, tip)])
        self.assertEqual((number, used), (weapons.STILL_FIRST, [weapons.POINT_FIRST]))
        self.assertEqual(skel['names'][-2:], ['cha:OPT820_horn', 'cha:OPT850_hit23_1'])
        hw = bone.world_matrices(skel)
        np.testing.assert_allclose(hw[index], world, atol=1e-3)
        np.testing.assert_allclose(hw[-1][:3, 3], tip, atol=1e-3)
        self.assertEqual(weapons.points_of(skel['names']), {0x23: 71})
        with self.assertRaises(ValueError):
            weapons.append_tekken8(bon, dict(bone='x', parent='MUNE2_jnt'), world, [(0x23, 4, tip)])
        w = [dict(bone='staff', mesh='a', points={1: ('tip', 0)}), dict(bone='staff2', mesh='a'),
             dict(bone='tail', mesh='b', points={2: ('origin', 1), 3: ('origin', 2)}), dict(bone='root')]
        self.assertEqual(model.weapon_parts(w), [('wpn0', 'a'), ('wpn1', 'b')])
        self.assertEqual(model.weapon_bones(w), 1 + 1 + 1 + 1 + 2 + 1)


class NaniteOverrideTest(unittest.TestCase):
    """tekken8/uprops.py reads a material instance's NaniteOverrideMaterial (Miary Zo's horn): 28 bytes."""

    def test_read(self):
        import struct
        import test_tekken8_uprops as TU
        from ttt2char.tekken8 import reflect, uprops
        data = TU.name('/Game/Test/Item') + TU.name('Item') + struct.pack('<i', 0) + struct.pack('<Ii', 1, 0) + b'\x7f'
        k = TU.package(data)
        at = k.exports[0].offset
        v, end = uprops.read_struct(k, reflect.Schema(TU.SCHEMA), 'MaterialOverrideNanite', at, at + len(data))
        self.assertEqual(end - at, 28)
        self.assertEqual(v, {'OverrideMaterialRef': '/Game/Test/Item.Item', 'bEnableOverride': True,
                             'OverrideMaterial': None})
        empty = TU.name('None') + TU.name('None') + struct.pack('<iIi', 0, 0, 0)
        k = TU.package(empty)
        at = k.exports[0].offset
        v, end = uprops.read_struct(k, reflect.Schema(TU.SCHEMA), 'MaterialOverrideNanite', at)
        self.assertEqual((v['OverrideMaterialRef'], v['bEnableOverride'], end - at), (None, False, 28))


class PartVerticesTest(unittest.TestCase):
    """model.tekken8_model: a part with TEKKEN8['part_vertices'] is decimated alone first, then kept as it is; the
    model's 'source' still numbers the vertices as loaded."""

    def test_small_part_first(self):
        from unittest import mock
        import test_source as TS
        from ttt2char.convert import decimate, skeleton
        src = mock.Mock(game='tekken8')
        src.costume.return_value = {'parts': [('bdf', 'b')], 'merge_order': ['bdf'], 'colours': 'c'}
        src.load_model.return_value = TS.small_model([('bdf', 'b'), ('wpn0', 'w')])
        calls = []

        def reduce(k, target, weights, log, poses=None, classes=None):
            calls.append((target, dict(weights)))
            if len(calls) < 3:                  # (the part's triangle loses a corner each pass: 2, then 1 left)
                left = [[3, 4, 4]] if len(calls) == 1 else [[3, 3, 3]]
                prims = [dict(p, tris=np.array(left)) if p['part'] == 'wpn0' else p for p in k['prims']]
                return dict(k, prims=prims, source=np.array([5, 0, 1, 2, 3] if len(calls) == 1 else [0, 1, 2, 4]))
            return dict(k, source=np.array([1, 3]))
        d = types.SimpleNamespace(TEKKEN8={'costume': '1p', 'part_vertices': {'wpn0': 1}})
        with mock.patch.object(decimate, 'decimate', side_effect=reduce), \
                mock.patch.object(decimate, 'vertex_target', return_value=4), \
                mock.patch.object(skeleton, 'repose', side_effect=lambda k, donor, log: k):
            k, worn, _, _ = model.tekken8_model(src, d, {}, log=lambda s: None, weapons=[{'mesh': 'w', 'bone': 'x'}])
        self.assertEqual(worn, [('bdf', 'b'), ('wpn0', 'w')])
        self.assertEqual(calls, [(6 - 2, {'bdf': 0.0, 'wpn0': 1.0}), (5 - 1, {'bdf': 0.0, 'wpn0': 1.0}),
                                 (4, {'bdf': 1.0, 'wpn0': 0.0})])
        self.assertEqual(k['source'].tolist(), [0, 3])


if __name__ == '__main__':
    unittest.main()
