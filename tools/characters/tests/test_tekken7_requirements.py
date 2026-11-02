"""Unit tests of the requirement and property rules of a Tekken 7 fighter's conversion (convert/moveset.py): the contact
tests 43 / 45 / 51 (43's cancel rows), the moveset variables (Tekken 7's 288 + k and 0x8076 + k), the definition's
state flags (MOVESET['state_flags']) and the opponent's move (MOVE_PROP), on made-up tables.

    python3 -m pytest -q tools/characters/tests/test_tekken7_requirements.py
"""
import collections
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_cancels import row  # noqa: E402
from test_tekken8_convert import Map, converted  # noqa: E402
from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.convert import moveset  # noqa: E402
from ttt2char.movesets import Moveset  # noqa: E402

STARBURST = {'starburst': {'variable': 5, 'prop': 0x81bf, 'equals': 351}}
CANE = {'cane': {'variable': 6, 'prop': 0x82eb, 'clear': 641, 'set': 642}}


class Source7(Moveset):
    """A made-up Tekken 7 moveset: moves by name, requirement rows (end T7_END)."""
    game = 't7'

    def __init__(self, names=()):
        self.names = list(names)
        self.aliases = [0] * 56
        self.tables = collections.defaultdict(list)
        self.tables['moves'] = [dict(anim=i) for i in range(len(self.names))]

    def move_name(self, i):
        return self.names[i]

    def req(self, *rows):
        """A requirement list of (condition, param) -> its index."""
        start = len(self.tables['requirements'])
        for c, p in rows + ((moveset.T7_END, 0),):
            self.tables['requirements'].append(dict(condition=c, param=p))
        return start


class Defn:
    def __init__(self, **options):
        self.MOVESET = dict(name='[TEST]', **options)


def converter(k, req=None, prop=None, **options):
    """A bare Converter of Tekken 7 moveset k (its run() parts not needed by the tests left out); req / prop: its id
    maps' pairs."""
    c = moveset.Converter.__new__(moveset.Converter)
    c.k, c.game, c.end, c.prefix = k, 't7', moveset.T7_END, None
    c.req_map, c.prop_map = Map(req or {}), Map(prop or {})
    c.usage = {'req': set((req or {}).values()), 'prop': set((prop or {}).values())}
    c.T = {'requirements': []}
    c.cache, c.stats, c.unmapped = {}, collections.Counter(), collections.Counter()
    c.defn, c.k_id, c.newid = Defn(**options), 8, 70
    c.flag_reqs, c.flag_props = moveset.state_flags(c.defn.MOVESET)
    c.opt_anims, c.alloc_ok, c.newidx = {}, 0, {}
    return c


class Requirements(unittest.TestCase):
    def setUp(self):
        self.k = Source7()
        # the id maps' pairs as Tekken 7's fighters have them: 45 between 44 -> 46 and 47 -> 49
        self.c = converter(self.k, req={0: 0, 2: 2, 44: 46, 45: 47, 47: 49, 251: 232, 289: 262},
                           prop={0x8077: 0x8065, 0x81d4: 0x8128})

    def conv(self, *rows):
        start, ok = self.c.conv_reqs(self.k.req(*rows))
        return converted(self.c, start) if ok else None

    def test_contact(self):
        """43 (hit or block) outside a cancel row and 51 (the move hit) are TTT2's 46; 45 (neither) is false, not 47
        (hit + Tag)."""
        self.assertEqual(self.conv((43, 0)), [(46, 0)])
        self.assertEqual(self.conv((2, 0), (51, 0), (96, 0)), [(2, 0), (46, 0), (93, 0)])     # a hit grab
        self.assertEqual(self.conv((51, 0)), [(46, 0)])
        self.assertEqual(self.conv((44, 0)), [(46, 0)])
        self.assertEqual(self.conv((47, 0)), [(49, 0)])
        self.assertIsNone(self.conv((45, 0)))

    def test_contact_cancel_rows(self):
        """A cancel row on 43 is two, on 46 and on 49 (REQ_OR: TTT2's hit and block tests, as its own lists have them
        side by side), in the row's place; 44 stays one row."""
        self.c.T.update(cancels=[], cancel_extras=[])
        self.c.extra_index, self.c.target = {}, lambda m, input_target=False: m
        self.k.tables['cancels'] = [row(0, 0, 1, self.k.req((43, 0))), row(0, 0, 2, self.k.req((44, 0))),
                                    row(M.LIST_END, 0)]
        out = self.c.conv_cancel_list(0)[:-1]
        self.assertEqual([(r['move_id'], converted(self.c, r['req'])) for r in out],
                         [(1, [(46, 0)]), (1, [(49, 0)]), (2, [(46, 0)])])
        self.assertEqual(self.c.stats['cancels made one row per alternative (REQ_OR)'], 1)

    def test_variables(self):
        """Tekken 7's <= tests 288 + k are TTT2's 261 + k, its sets 0x8076 + k (k < 4) TTT2's 0x8064 + k."""
        self.assertEqual(self.conv((290, 0)), [(263, 0)])                  # Leroy's 2+3: Sugar's cooldown over
        self.assertEqual(self.conv((292, 0)), [(265, 0)])
        self.assertEqual(self.conv((289, 0), (251, 1)), [(262, 0), (232, 1)])
        self.assertEqual(self.c.map_prop(0x8078), 0x8066)                  # Go Sugar sets the cooldown
        self.assertEqual(self.c.map_prop(0x8077), 0x8065)
        self.assertEqual(self.conv((0x8078, 210)), [(0x8066, 210)])

    def test_unknown_state_stays_false(self):
        self.assertIsNone(self.conv((351, 0)))
        self.assertIsNone(self.conv((641, 0)))


class StateFlags(unittest.TestCase):
    def conv(self, c, *rows):
        start, ok = c.conv_reqs(c.k.req(*rows))
        return converted(c, start) if ok else None

    def test_equals(self):
        """Starburst: 351 == 1 on (variable 5 >= 1), == 0 off (<= 0); 0x81bf 1 / 0 sets it on / off."""
        c = converter(Source7(), req={0: 0}, state_flags=STARBURST)
        self.assertEqual(self.conv(c, (351, 1)), [(237, 1)])
        self.assertEqual(self.conv(c, (351, 0), (0x81bf, 1)), [(266, 0), (0x806F, moveset.FLAG_ON)])
        self.assertEqual(self.conv(c, (351, 1), (0x81bf, 0)), [(237, 1), (0x806F, 0)])
        self.assertEqual(c.map_prop(0x81bf), 0x806F)
        self.assertEqual(c.conv_value(0x81bf, 1), moveset.FLAG_ON)
        self.assertEqual(c.conv_value(0x81bf, 0), 0)
        self.assertEqual(c.stats['state flag tests -> moveset variables'], 3)

    def test_clear_and_set(self):
        """The cane: 641 not used yet (variable 6 <= 0), 642 used (>= 1); 0x82eb uses it up."""
        c = converter(Source7(), state_flags=CANE)
        self.assertEqual(self.conv(c, (641, 0)), [(267, 0)])
        self.assertEqual(self.conv(c, (642, 0)), [(238, 1)])
        self.assertEqual(c.map_prop(0x82eb), 0x8072)
        self.assertEqual(c.conv_value(0x82eb, 1), moveset.FLAG_ON)

    def test_definition(self):
        self.assertEqual(moveset.state_flags({'state_flags': {**STARBURST, **CANE}}),
                         ({351: (5, 'equals'), 641: (6, 'clear'), 642: (6, 'set')}, {0x81bf: 5, 0x82eb: 6}))
        self.assertEqual(moveset.state_flags({}), ({}, {}))


class OpponentMove(unittest.TestCase):
    def test_move_id_converted(self):
        """0x81d4's value is a move of the moveset: the converted move's index, left out when not converted."""
        k = Source7(['Cz_zutuki_y', 'Cz_Head_Wall_E'])
        c = converter(k, req={0: 0}, prop={0x81d4: 0x8128})
        c.newidx = {1: 2349}
        self.assertEqual(c.conv_value(0x81d4, 1), 2349)
        self.assertIsNone(c.conv_value(0x81d4, 5))                         # (no such move)
        self.assertEqual(c.alloc_ok, 0)
        start, ok = c.conv_reqs(k.req((0x81d4, 1)))
        self.assertEqual(converted(c, start), [(0x8128, 2349)])
        start, ok = c.conv_reqs(k.req((0, 0), (0x81d4, 5)))
        self.assertEqual(converted(c, start), [(0, 0)])                    # the action left out, the list kept
        self.assertEqual(c.stats['opponent move properties: move converted'], 2)

    def test_not_fit_tested(self):
        c = converter(Source7())
        c.game = 't8'
        self.assertFalse(c.guarded(moveset.MOVE_PROP['t8']))


if __name__ == '__main__':
    unittest.main()
