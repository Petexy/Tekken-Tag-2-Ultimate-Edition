"""Unit tests of ttt2char.convert.arcs (Tekken 7's 2D arcs) on made-up animations (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_arcs.py
"""
import collections
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import arcs, moveset  # noqa: E402
from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.movesets import Moveset  # noqa: E402
from ttt2char.ttt2 import animation  # noqa: E402


def made_up(frames, typ=animation.RAW, hips=1000.0, seed=1):
    """A decoded animation: 23 body channels with TTT2's descriptors, random rotations, hips at `hips`."""
    rng = np.random.default_rng(seed)
    desc = [11, 11, 5, 7, 7, 7, 11, 7, 7, 7, 7, 6, 7, 7, 7, 6, 7, 7, 6, 7, 7, 6, 7]
    v = rng.uniform(-1.0, 1.0, (frames, len(desc), 3)).astype(np.float32)
    v[:, 1, 1] = hips
    return dict(type=typ, frames=frames, descriptors=desc, values=v)


class Arcs(unittest.TestCase):
    def test_params(self):
        self.assertEqual(arcs.params(0x82466400), (130, 7.0, 100))
        self.assertEqual(arcs.params(0x6E3C6400), (110, 6.0, 100))
        self.assertEqual(arcs.params(0x00960000), (0, 15.0, 0))

    def test_height_is_ttt2_physics(self):
        # TTT2's physics (sub_04336854): vy -= g, then y += vy, once a frame, from vy = a
        a, g, y, vy = 130.0, 7.0, 0.0, 130.0
        for n in range(1, 40):
            vy -= g
            y += vy
            self.assertAlmostEqual(arcs.height(n, a, g), y, places=3)

    def test_touchdown(self):
        self.assertEqual(arcs.touchdown(130, 7.0), 37)     # Akuma: 20 A / B = 37.1 frames
        self.assertEqual(arcs.touchdown(110, 6.0), 36)     # Eliza
        self.assertGreater(arcs.height(arcs.touchdown(110, 6.0) - 1, 110, 6.0), 0)
        self.assertLessEqual(arcs.height(arcs.touchdown(110, 6.0), 110, 6.0), 0)

    def test_ground_or_air(self):
        self.assertTrue(arcs.is_ground_arc(False, 9))
        self.assertFalse(arcs.is_ground_arc(True, 10))       # an air move's own arc (dive kick)
        self.assertFalse(arcs.is_ground_arc(False, 0x8009))  # on the second counter: kept for the runtime

    def test_bake_raw(self):
        dec = made_up(44)
        f0, a, g, hold = 9, 130, 7.0, 43
        desc, out, ext = arcs.bake(dec, f0, a, g, hold)
        self.assertEqual(ext, f0 + arcs.touchdown(a, g) - hold)
        self.assertEqual(out.shape[0], 44 + ext)
        self.assertEqual(desc, dec['descriptors'])
        # before the arc: unchanged; the held frame repeats; the arc is in the hips height only
        np.testing.assert_array_equal(out[:f0], dec['values'][:f0])
        for f in range(hold, hold + ext + 1):
            np.testing.assert_array_equal(np.delete(out[f], 1, 0), np.delete(dec['values'][hold], 1, 0))
        for f in range(f0, out.shape[0]):
            self.assertAlmostEqual(float(out[f, 1, 1]), 1000.0 + max(0.0, arcs.height(f - f0, a, g)), places=2)
        self.assertAlmostEqual(float(out[f0 + arcs.touchdown(a, g), 1, 1]), 1000.0, places=3)

    def test_bake_compressed_keeps_the_pose(self):
        dec = made_up(20, animation.COMPRESSED)
        desc, out, _ = arcs.bake(dec, 5, 30, 6.0, 19)
        for c, d in enumerate(dec['descriptors']):
            if animation.is_rotation(d):
                self.assertEqual(desc[c], 7)
                want = animation.local_rotation(dec['values'][:5, c], animation.COMPRESSED)
                got = animation.local_rotation(out[:5, c], animation.RAW)
                np.testing.assert_allclose(got, want, atol=1e-5)
        raw = arcs.encode(desc, out)
        back = animation.decode(raw, '>')
        self.assertEqual(back['type'], animation.RAW)
        np.testing.assert_array_equal(back['values'], out)

    def test_absolute_sabun(self):
        whole = made_up(44, hips=1271.0)
        whole['values'][:5, 1, 1] = 750.0                    # take-off and landing frames lower
        delta = made_up(40, hips=0.0, seed=2)
        delta['values'][:5, 1, 1] = 700.0                    # absolute take-off frames
        delta['values'][5:38, 1, 1] = np.linspace(-180, 180, 33)
        delta['values'][38:, 1, 1] = 1000.0                  # absolute landing frames
        out, base, n = arcs.absolute_sabun(delta, whole)
        self.assertEqual(base, 1271.0)
        self.assertEqual(n, 33)
        np.testing.assert_allclose(out['values'][5:38, 1, 1], 1271.0 + np.linspace(-180, 180, 33), rtol=1e-6)
        np.testing.assert_array_equal(out['values'][:5, 1, 1], 700.0)
        np.testing.assert_array_equal(out['values'][38:, 1, 1], 1000.0)

    def test_relative_hips(self):
        # Akuma's Demon Flip: absolute take-off frames, then relative hips from the arc's frame (5) on
        flip = made_up(40, hips=0.0)
        flip['values'][:5, 1, 1] = [754, 754, 781, 898, 898]
        flip['values'][5:24, 1, 1] = np.linspace(11, -7, 19)
        self.assertTrue(arcs.relative_hips(flip, 5))
        self.assertFalse(arcs.relative_hips(flip, 4))           # still absolute there
        held = made_up(44)                                       # a jump holding its flat airborne pose
        self.assertFalse(arcs.relative_hips(held, 9))
        self.assertFalse(arcs.relative_hips(held, 0))
        self.assertFalse(arcs.relative_hips(held, 44))
        whole = made_up(44, hips=1271.0)
        out, base, n = arcs.absolute_sabun(flip, whole)          # made absolute as the "_sabun" jumps are
        self.assertEqual((base, n), (1271.0, 35))
        np.testing.assert_array_equal(out['values'][:5, 1, 1], [754, 754, 781, 898, 898])
        np.testing.assert_allclose(out['values'][5:24, 1, 1], 1271.0 + np.linspace(11, -7, 19), rtol=1e-6)

    def test_landing_bit(self):
        # Hyakkigozan (0: a 2D air move, ground_fall 14) lands into its slide (1) one frame later; the slide gets
        # TTT2's bit 31. Not: the stance (2, an alias slot), a move a ground move (3) cancels into too (4), the
        # landing of a baked ground arc (5 -> 6: its fighter stays on the floor)
        def move(cancel, props=None, fall=0, air=0):
            return dict(cancel=cancel, extraprops=props, ground_fall=fall, airborne_start=air, transition=0x8000,
                        bitfield=0)

        def cancel(to, win=(15, 15), direction=0):
            return dict(direction=direction, move_id=to, win_start=win[0], win_end=win[1])
        k = Moveset()
        k.game, k.aliases = 't7', [2]
        k.tables = {
            'moves': [move(0, 0, 14, 1), move(None), move(None), move(3), move(None), move(5, 2, 20), move(None)],
            'cancels': [cancel(1), cancel(4), cancel(2, (0, 0), M.LIST_END), cancel(4, (1, 32767)),
                        cancel(2, (0, 0), M.LIST_END), cancel(6, (21, 21)), cancel(2, (0, 0), M.LIST_END)],
            'group_cancels': [], 'reactions': [],
            'extra_move_properties': [dict(frame=0x8001, id=arcs.AIR_MOVE, value=0), dict(frame=0, id=0, value=0),
                                      dict(frame=5, id=arcs.ARC, value=0x82466400), dict(frame=0, id=0, value=0)]}
        c = moveset.Converter.__new__(moveset.Converter)
        c.k, c.game, c.stats = k, 't7', collections.Counter()
        c.newidx = {i: 100 + i for i in range(7)}
        c.T = {'moves': [None] * 100 + [dict(bitfield=0x20) for _ in range(7)]}
        c.arc_landings()
        self.assertEqual([r['bitfield'] for r in c.T['moves'][100:]], [0x20, 0x80000020] + [0x20] * 5)
        self.assertEqual(c.stats['2D arcs: landing moves given the landing bit'], 1)

    def test_tekken8_s_arc_ids_convert_as_tekken7_s(self):
        # (Clive's jumps: 0x8296 = (110, 60, 100) at frame 9; his air moves: 0x8297 at 0x8001, a dive's 0x8296 in the air)
        c = moveset.Converter.__new__(moveset.Converter)
        c.game, c.stats, c.ground_arcs = 't8', collections.Counter(), {}
        self.assertEqual(moveset.ARCS['t8'], (arcs.ARC8, arcs.AIR_MOVE8))
        self.assertEqual(c.arc_rows(7, False, 9, arcs.ARC8, 0x6E3C6400),
                         [dict(frame=arcs.BAKED_FRAME, id=arcs.BAKED, value=0x6E3C6409)])
        self.assertEqual(c.ground_arcs, {7: (9, 0x6E3C6400)})
        self.assertEqual(c.arc_rows(8, True, 0x8001, arcs.AIR_MOVE8, 0),
                         [dict(frame=arcs.AIR_MARK_FRAME, id=arcs.AIR_MARK, value=0)])
        self.assertEqual(c.arc_rows(8, True, 14, arcs.ARC8, 0x00500000), [dict(frame=14, id=arcs.ARC, value=0x00500000)])
        self.assertEqual(c.ground_arcs, {7: (9, 0x6E3C6400)})

    def test_an_air_move_flies_on_from_its_entry_and_restarts_its_arc(self):
        # entered at jump frame 17 of an arc (110, 6.0) from frame 9: frame 1 is the arc's frame 9 (720 mm)
        n0, a, g = 8, 110, 6.0
        fly = arcs.fly(arcs.height(n0, a, g), a - g * n0, g, {})
        self.assertEqual(fly[1][0], arcs.height(9, a, g))
        self.assertEqual(len(fly) - 1, arcs.touchdown(a, g) - n0)
        self.assertEqual(fly[-1], (0.0, 0.0, g))
        # its own arc at frame 3 (A 0, g 8.0): the vertical speed starts again from there
        fly = arcs.fly(1000.0, 50.0, 6.0, {3: (0, 8.0)})
        self.assertEqual(fly[3], (1000.0 + 44 + 38 + 32, 0, 8.0))
        self.assertEqual(fly[4][0], fly[3][0] - 8.0)

    def test_an_air_move_is_held_on_its_ground_fall_or_cut_to_it(self):
        dec = made_up(6)
        dec['values'][:, 1, 1] += 10 * np.arange(6)
        # lands at frame 7, ground_fall 4: frame 4 held 3 frames more
        desc, v, shift = arcs.bake_air(dec, [100.0] * 7 + [0.0], 4)
        self.assertEqual(shift, 3)
        self.assertEqual(v.shape[0], 9)
        self.assertTrue((v[4:8, 0] == dec['values'][4, 0]).all())
        self.assertEqual(v[6, 1, 1], dec['values'][4, 1, 1] + 100)
        self.assertEqual(v[8, 1, 1], dec['values'][5, 1, 1])
        self.assertEqual([arcs.moved(f, 4, shift) for f in (3, 4, 5)], [3, 4, 8])
        self.assertEqual(arcs.moved(4, 4, shift, held=True), 7)
        # lands at frame 2, ground_fall 4: frames 2 and 3 left out, the touchdown shows frame 4
        desc, v, shift = arcs.bake_air(dec, [100.0, 100.0, 0.0], 4)
        self.assertEqual(shift, -2)
        self.assertEqual(v.shape[0], 4)
        self.assertTrue((v[2] == dec['values'][4]).all())
        self.assertEqual([arcs.moved(f, 4, shift) for f in (1, 2, 3, 4, 5)], [1, 2, 2, 2, 3])

    def test_tekken8_s_ways_into_an_air_move_lead_to_copies_baked_from_their_starts(self):
        # a jump (arc 110, 6.0 from frame 9) into an air move at frames 17 and 26 (its group list); the air move (its
        # own arc at frame 3: A 0, g 8.0; ground_fall 8) lands into move 2 at frame 9
        c = moveset.Converter.__new__(moveset.Converter)
        c.game, c.stats, c.aliases, c.pack0_count = 't8', collections.Counter(), [], 0
        clip = made_up(10)
        c.new_anims = [arcs.encode(clip['descriptors'], clip['values'])]
        c.animation_bytes = lambda aid: (c.new_anims[aid & 0x3FFF], '>', 0)

        def cancel(move, a, b, st, direction=0):
            return dict(direction=direction, button=0, req=None, extradata=None, move_id=move, win_start=a,
                        win_end=b, start_frame=st)

        def move(props, cancels, gf=0):
            return dict(anim=0x4000, extraprops=props, cancel=cancels, ground_fall=gf, airborne_end=gf and gf + 1,
                        first_active=gf and 5, last_active=gf and 6, bitfield=0x80000060 if gf else 0)
        end = dict(frame=0, id=0, value=0)
        c.T = dict(moves=[move(0, 0), move(2, 3, gf=8), move(None, None)],
                   extra_move_properties=[dict(frame=arcs.BAKED_FRAME, id=arcs.BAKED, value=0x6E3C6409), end,
                                          dict(frame=arcs.AIR_MARK_FRAME, id=arcs.AIR_MARK, value=0),
                                          dict(frame=3, id=arcs.ARC, value=0x00500000),
                                          dict(frame=9, id=0x801F, value=1), end],
                   cancels=[cancel(1, 1, 8, 17), cancel(0, 0, 0, 0, M.GROUP), cancel(0, 0, 0, 0, M.LIST_END),
                            cancel(2, 9, 9, 9), cancel(0, 0, 0, 0, M.LIST_END)],
                   group_cancels=[cancel(1, 18, 26, 26), cancel(0, 0, 0, 0, M.GROUP_END)])
        c.bake_air8()
        rows, C, G, P = c.T['moves'], c.T['cancels'], c.T['group_cancels'], c.T['extra_move_properties']
        self.assertEqual(len(rows), 5)
        jump = C[rows[0]['cancel']:]
        self.assertEqual(jump[0]['move_id'], 3)
        self.assertEqual(G[jump[1]['move_id']]['move_id'], 4)
        self.assertEqual((C[0]['move_id'], G[0]['move_id']), (1, 1))          # (the lists are copied)
        # entered at the arc's frame 8: 664 mm, 62 mm/frame up; 814 mm at its own arc, which lands it at frame 17
        early = rows[3]
        self.assertEqual(early['ground_fall'], 17)
        self.assertEqual((early['first_active'], early['last_active']), (5, 6))
        self.assertEqual((early['bitfield'], rows[1]['bitfield']), (0x80000020, 0x80000060))
        v = animation.decode(c.new_anims[early['anim'] & 0x3FFF])['values']
        self.assertAlmostEqual(float(v[3, 1, 1]), float(clip['values'][3, 1, 1]) + 814, 2)
        self.assertAlmostEqual(float(v[17, 1, 1]), float(clip['values'][8, 1, 1]), 2)
        self.assertEqual([(x['win_start'], x['start_frame']) for x in C[early['cancel']:early['cancel'] + 1]], [(18, 18)])
        ps = P[early['extraprops']:early['extraprops'] + 2]
        self.assertEqual([(x['frame'], x['id']) for x in ps], [(18, 0x801F), (0, 0)])
        self.assertEqual(rows[1]['extraprops'], 2)                          # (the air move itself stays flown)

    def test_a_flight_brought_down_lands_on_its_frame_from_where_it_was(self):
        flight = arcs.fly(1274.0, 50.0, 10.0, {0: (40, 1.0), 20: (10, 20.0)})
        self.assertEqual(len(flight) - 1, 34)
        down = arcs.land_by(flight, 28)
        self.assertEqual(len(down) - 1, 28)
        self.assertEqual(down[-1], (0.0, 0.0, 20.0))
        self.assertAlmostEqual(down[0][0], 1274.0)
        self.assertTrue(all(y > 0 for y, _, _ in down[:-1]))
        self.assertAlmostEqual(down[26][0], flight[26][0] - flight[28][0] * 26 / 28)

    def test_tekken8_s_air_move_a_ground_move_goes_on_with_lands_by_its_ground_fall(self):
        # as above, move 2 (the air move's landing at frame 9) going on with its clip (TT_CONTINUE): the copy entered
        # at the jump's frame 17 (which flew to frame 17) is on the floor at its ground_fall, 8
        c = moveset.Converter.__new__(moveset.Converter)
        c.game, c.stats, c.aliases, c.pack0_count = 't8', collections.Counter(), [], 0
        clip = made_up(10)
        c.new_anims = [arcs.encode(clip['descriptors'], clip['values'])]
        c.animation_bytes = lambda aid: (c.new_anims[aid & 0x3FFF], '>', 0)

        def cancel(move, a, b, st, direction=0):
            return dict(direction=direction, button=0, req=None, extradata=None, move_id=move, win_start=a,
                        win_end=b, start_frame=st)

        def move(props, cancels, gf=0):
            return dict(anim=0x4000, extraprops=props, cancel=cancels, ground_fall=gf, airborne_end=gf and gf + 1,
                        first_active=gf and 5, last_active=gf and 6, bitfield=0)
        end = dict(frame=0, id=0, value=0)
        c.T = dict(moves=[move(0, 0), move(2, 2, gf=8), move(6, None)],
                   extra_move_properties=[dict(frame=arcs.BAKED_FRAME, id=arcs.BAKED, value=0x6E3C6409), end,
                                          dict(frame=arcs.AIR_MARK_FRAME, id=arcs.AIR_MARK, value=0),
                                          dict(frame=3, id=arcs.ARC, value=0x00500000), end, end,
                                          dict(frame=arcs.BAKED_FRAME, id=moveset.TT_CONTINUE, value=10), end],
                   cancels=[cancel(1, 1, 8, 17), cancel(0, 0, 0, 0, M.LIST_END),
                            cancel(2, 9, 9, 9), cancel(0, 0, 0, 0, M.LIST_END)],
                   group_cancels=[])
        c.bake_air8()
        rows, C = c.T['moves'], c.T['cancels']
        copy = rows[3]
        self.assertEqual(copy['ground_fall'], 8)
        self.assertEqual([(x['win_start'], x['start_frame']) for x in C[copy['cancel']:copy['cancel'] + 1]], [(9, 9)])
        v = animation.decode(c.new_anims[copy['anim'] & 0x3FFF])['values']
        # 814 mm at frame 3, 694 at 8 (where it flew): less 3/8 of 694
        self.assertAlmostEqual(float(v[3, 1, 1]), float(clip['values'][3, 1, 1]) + 814 - 694 * 3 / 8, 2)
        self.assertAlmostEqual(float(v[8, 1, 1]), float(clip['values'][8, 1, 1]), 2)
        self.assertEqual(c.stats['2D arcs: air moves brought down where a ground move goes on with their clip '
                                 '(Tekken 8)'], 1)

if __name__ == '__main__':
    unittest.main()
