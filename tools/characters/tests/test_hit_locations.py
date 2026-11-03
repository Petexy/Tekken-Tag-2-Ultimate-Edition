"""Unit tests of the hit locations a Tekken 7 move's hit box gets (convert/moveset.py hit_location, HIT_LOCATION's
Tekken 7 points past the limbs and in the trunk; Negan's definition), on made-up codes (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_hit_locations.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.characters import negan  # noqa: E402
from ttt2char.convert import moveset  # noqa: E402

RIGHT_FIST, LEFT_FIST, RIGHT_FOOT, LEFT_FOOT = 40, 39, 38, 37      # TTT2's points past the fists and the feet
BONES = range(1, 22)                                                # TTT2's codes of its skeleton's records


def converter(game='t7', hitbox=None, hit_locations=None):
    """A bare Converter with the id maps' hit locations (hitbox) and the definition's (hit_locations)."""
    c = moveset.Converter.__new__(moveset.Converter)
    c.game, c.hitbox, c.hit_locations = game, dict(hitbox or {}), dict(hit_locations or {})
    return c


class Tekken7Points(unittest.TestCase):
    def test_every_code_has_a_placed_point(self):
        """0x21..0x37 all become a skeleton record or a point TTT2 places past a limb (none keeps its number, which
        is another thing's point in TTT2, most of them placed nowhere for an added fighter)."""
        c = converter()
        for x in range(0x21, 0x38):
            self.assertIn(c.hit_location(x), list(BONES) + [LEFT_FOOT, RIGHT_FOOT, LEFT_FIST, RIGHT_FIST], hex(x))

    def test_sides(self):
        c = converter()
        side = {x: c.hit_location(x) for x in range(0x24, 0x38)}
        self.assertEqual({x for x, p in side.items() if p == RIGHT_FIST}, {0x24, 0x25, 0x28, 0x29, 0x33, 0x35})
        self.assertEqual({x for x, p in side.items() if p == LEFT_FIST}, {0x26, 0x27, 0x2a, 0x2b, 0x32, 0x34})
        self.assertEqual({x for x, p in side.items() if p == RIGHT_FOOT}, {0x2d, 0x2f, 0x31, 0x37})
        self.assertEqual({x for x, p in side.items() if p == LEFT_FOOT}, {0x2c, 0x2e, 0x30, 0x36})
        self.assertEqual([c.hit_location(x) for x in (0x21, 0x22, 0x23)], [3, 2, 4])      # hips, chest, neck

    def test_hit_box(self):
        """A punch to the floor's (fist, 0, fist, left foot) and a kick's (foot, knee, right foot, 0) hit boxes."""
        c = converter()
        self.assertEqual(bytes(c.hit_location(x) for x in (0x29, 0, 0x29, 0x30)), bytes((40, 0, 40, 37)))
        self.assertEqual(bytes(c.hit_location(x) for x in (0x10, 0x0f, 0x37, 0)), bytes((16, 15, 38, 0)))

    def test_definition_and_id_maps_win(self):
        """The definition's HIT_LOCATIONS and its weapons' points come first, then the id maps, then the table."""
        c = converter(hitbox={0x2e: 19, 0x25: 9}, hit_locations={0x25: 13, 0x72: 72})
        self.assertEqual([c.hit_location(x) for x in (0x25, 0x2e, 0x72, 0x29)], [13, 19, 72, RIGHT_FIST])

    def test_other_codes_and_tekken8(self):
        """Codes outside 0x21..0x37 keep their numbers (bones, TTT2's own points, weapons' codes without a point);
        Tekken 8's tables are its own (0x22, which Tekken 7's takes to the chest, is no Tekken 8 limb point)."""
        c = converter()
        self.assertEqual([c.hit_location(x) for x in (0, 9, 0x16, 0x1f, 0x63, 0x72)], [0, 9, 0x16, 0x1f, 0x63, 0x72])
        self.assertEqual([converter('t8').hit_location(x) for x in (0x22, 125)], [0x22, 70])


class Negan(unittest.TestCase):
    def test_fist_point_not_on_the_bat(self):
        """0x72 is the point past his right fist (his punches hold the bat back): not one of the bat's points, and
        no hit box of his overrides Tekken 7's (0x72, 0, 0x72, elbow)."""
        self.assertEqual(negan.HIT_LOCATIONS[0x72], RIGHT_FIST)
        self.assertNotIn(0x72, negan.WEAPONS[0]['points'])
        self.assertEqual(set(negan.WEAPONS[0]['points']), {0x6f, 0x70})
        self.assertNotIn('Na_rkrp', negan.MOVESET.get('hitboxes', {}))


if __name__ == '__main__':
    unittest.main()
