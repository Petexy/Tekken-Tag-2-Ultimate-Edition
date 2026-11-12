"""Unit tests of the warps (convert/moveset.py: WARP_PROP, appear_when_hit, warp_out_at_start) on made-up movesets.

    python3 -m unittest discover tools/characters/tests
"""
import collections
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import moveset  # noqa: E402


def converter(game, extra, end=(), donor_moves=3, posed=()):
    """A made-up converter: the fighter's property lists (rows of extra properties, rows of an end list), the
    donor's moves (all sharing the first property list) and its intro / win poses."""
    k = types.SimpleNamespace(tables={'extra_move_properties': [dict(frame=f, id=i, value=v) for f, i, v in extra],
                                      'move_end_props': [dict(req=0, id=i, value=v) for i, v in end]})
    props = [dict(frame=5, id=0x801f, value=3), dict(frame=0, id=0, value=0)]
    c = types.SimpleNamespace(game=game, k=k, posed=set(posed), stats=collections.Counter(),
                              d=types.SimpleNamespace(tables={'moves': [{}] * donor_moves}),
                              T={'moves': [dict(extraprops=0) for _ in range(donor_moves)],
                                 'extra_move_properties': [dict(r) for r in props]})
    c.with_props = lambda start, rows: moveset.Converter.with_props(c, start, rows)
    return c, props


class Warps(unittest.TestCase):
    def test_the_property_keeps_its_value(self):
        # Tekken 7's 0x82ae becomes TT_WARP, its value (out, flash, fade and flash frames) as it is; Tekken 8 has none
        self.assertEqual(moveset.WARP_PROP, {'t7': 0x82ae, 't8': None})
        c = types.SimpleNamespace(game='t7', stats=collections.Counter(), flag_props={}, gauge=None, opt_anims={},
                                  defn=types.SimpleNamespace(MOVESET={}))
        self.assertEqual(moveset.Converter.map_prop(c, 0x82ae), moveset.TT_WARP)
        self.assertEqual(moveset.TT_WARP, 0x823D)
        self.assertEqual(c.stats['warps (vanishing, appearing)'], 1)
        c.flag_props, c.effects, c.hit_locations = {}, None, {}
        self.assertEqual(moveset.Converter.conv_value(c, 0x82ae, 0x01012121), 0x01012121)

    def test_the_property_is_its_own(self):
        # the runtime acts on each of the importer's ids once (title/roster.cpp, sub_03AE86A0): no other constant of
        # the converter's modules may take TT_WARP's id (Clive's continued moves had 0x822A too)
        from ttt2char.convert import arcs, gauge
        for module in (moveset, arcs, gauge):
            for name, value in vars(module).items():
                if type(value) is int and value == moveset.TT_WARP and (module, name) != (moveset, 'TT_WARP'):
                    self.fail('%s.%s has TT_WARP\'s id %#x' % (module.__name__, name, value))

    def test_the_start_fades_nothing(self):
        # Tekken 7's 0x82b1 (where a warp starts, the aimed effects' aim) becomes TT_WARP with WARP_START: neither out
        # (1) nor in (0), so the runtime records the place and fades nothing (title/warp.h kStart)
        self.assertEqual(moveset.WARP_START_PROP, {'t7': 0x82b1, 't8': None})
        self.assertEqual(moveset.WARP_START >> 24, 2)
        self.assertEqual(moveset.WARP_START & 0xFFFFFF, 0)

    def test_the_donor_moves_appear(self):
        # a fighter whose moves warp: each donor move but the poses starts with WARP_APPEAR after its own rows; moves
        # sharing a list share the new one
        c, props = converter('t7', [(20, 0x82ae, 0x01010b0b), (40, 0x82ae, 0x00010a0a)], posed=[2])
        moveset.Converter.appear_when_hit(c)
        moves, table = c.T['moves'], c.T['extra_move_properties']
        self.assertEqual([m['extraprops'] for m in moves], [2, 2, 0])
        self.assertEqual(table[2:], [props[0], dict(frame=0x8001, id=moveset.TT_WARP, value=moveset.WARP_APPEAR),
                                     props[1]])
        self.assertEqual(moveset.WARP_APPEAR >> 24, 0)                     # in, at once: no fade, no flash
        self.assertEqual(c.stats["warps: shown by the donor's moves"], 2)
        # only an end list warps: the same
        c, _ = converter('t7', [], end=[(0x82ae, 0x00010505)])
        moveset.Converter.appear_when_hit(c)
        self.assertEqual(c.stats["warps: shown by the donor's moves"], 3)

    def test_moves_that_warp_out_as_they_start(self):
        # the definition's WARP_OUT moves (by Tekken 7 name) start with its warp out after their own rows; moves
        # sharing a list share the new one, the others keep theirs
        c, props = converter('t7', [(10, 0x82ae, 0x00010a0a)], donor_moves=0)
        c.T['moves'] = [dict(extraprops=0) for _ in range(3)]
        c.newidx = {7: 0, 8: 1, 9: 2}
        c.name = {7: 'Mz_rp01F_Miss', 8: 'Mz_rp01F_n', 9: 'SPMz_Combo10_Miss'}.get
        c.defn = types.SimpleNamespace(WARP_OUT=(r'^(Mz_rp01F|SPMz_Combo10)_Miss$', 0x01010505))
        moveset.Converter.warp_out_at_start(c)
        moves, table = c.T['moves'], c.T['extra_move_properties']
        self.assertEqual([m['extraprops'] for m in moves], [2, 0, 2])
        self.assertEqual(table[2:], [props[0], dict(frame=0x8001, id=moveset.TT_WARP, value=0x01010505), props[1]])
        self.assertEqual(c.stats['warps: out as a move starts (WARP_OUT)'], 2)
        # none in the definition, or a Tekken 8 fighter: nothing changes
        for game, defn in (('t7', types.SimpleNamespace()), ('t8', c.defn)):
            d, props = converter(game, [], donor_moves=0)
            d.T['moves'], d.newidx, d.name, d.defn = [dict(extraprops=0)], {7: 0}, c.name, defn
            moveset.Converter.warp_out_at_start(d)
            self.assertEqual(d.T['moves'], [dict(extraprops=0)])
            self.assertEqual(d.T['extra_move_properties'], props)

    def test_fighters_without_warps_unchanged(self):
        for game in ('t7', 't8'):
            c, props = converter(game, [(20, 0x82a7, 0)], end=[(0x8001, 1)])
            moveset.Converter.appear_when_hit(c)
            self.assertEqual([m['extraprops'] for m in c.T['moves']], [0, 0, 0])
            self.assertEqual(c.T['extra_move_properties'], props)


if __name__ == '__main__':
    unittest.main()
