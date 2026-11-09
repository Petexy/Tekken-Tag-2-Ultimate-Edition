"""convert/prefabs8.py's small rules, on made-up data."""
import collections
import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from ttt2char import pack  # noqa: E402
from ttt2char.convert import prefabs8, summons8  # noqa: E402


def _moveset(extras):
    return types.SimpleNamespace(tables={'cancel_extras': [{'value': v} for v in extras]})


def _joint_locals(worlds):
    from ttt2char.convert import snakes8
    import numpy as np
    return snakes8.ttt2_locals(worlds, [-1, 0], [1], np.eye(3))

class Tekken8PrefabsTest(unittest.TestCase):
    def test_a_cancel_enters_at_its_start_frame_only_if_it_keeps_the_frames(self):
        k = _moveset([0x214, 0x402])
        assert prefabs8._start_of(k, {'extradata': 0, 'start_frame': 27}) == 1
        assert prefabs8._start_of(k, {'extradata': 1, 'start_frame': 27}) == 27
        assert prefabs8._start_of(k, {'extradata': None, 'start_frame': 27}) == 1

    def test_a_row_the_entry_has_passed_fires_as_the_move_is_entered(self):
        assert prefabs8._on_entry(5, 12) == prefabs8.AT_START
        assert prefabs8._on_entry(12, 12) == 12
        assert prefabs8._on_entry(28, 12) == 28
        assert prefabs8._on_entry(prefabs8.AT_START, 12) == prefabs8.AT_START

    def test_only_a_weapon_asking_for_channels_gets_them(self):
        weapons = [{'bone': 'a', 'number': 591, 'channels': 8}, {'bone': 'b', 'number': 592}, {'bone': 'c', 'pair': 0}]
        ini = [(-209, 0, [], 62, 7), (-208, 0, [], 13, 7), (0, 9, [], 0, 6)]
        assert prefabs8.with_channels(weapons, ini) == [(-209, 0, [], 62, 7, 8), (-208, 0, [], 13, 7), (0, 9, [], 0, 6)]

    def test_a_ground_not_held_follows_the_body(self):
        # (his body's creatures: posed from the clip each frame, not held where the move began)
        weapons = [{'bone': 'g', 'number': 591, 'channels': 8, 'ground': True},
                   {'bone': 'gb', 'number': 590, 'channels': 8, 'ground': True, 'held': False}]
        ini = [(-210, 0, [], 62, 0), (-209, 0, [], 62, 7)]
        assert prefabs8.with_channels(weapons, ini) == [(-210, 0, [], 62, 0, 8), (-209, 0, [], 62, 7, 8, 1)]

    def test_the_ground_is_anchored_in_the_world(self):
        weapons = [{'bone': 'g', 'number': 591, 'channels': 8, 'ground': True}, {'bone': 'b', 'number': 592}]
        ini = [(-209, 0, [], 62, 7), (-208, 0, [], 13, 7)]
        assert prefabs8.with_channels(weapons, ini) == [(-209, 0, [], 62, 7, 8, 1), (-208, 0, [], 13, 7)]
        d = types.SimpleNamespace(NAME='X', CODE='xxx', DONOR='lar', SEX='male', GAME='tekken8')
        text = pack.character_ini(d, 21, weapons=prefabs8.with_channels(weapons, ini))
        assert 'weapons = -209:0::62:7:8:1 -208:0::13:7' in text

    def test_root_points_follow_the_held_ground_and_only_with_one(self):
        roots = [{'bone': 'root_a', 'pair': 9, 'root': 0, 'summon': 63},
                 {'bone': 'root_b', 'pair': 10, 'root': 1, 'summon': 63}]
        ground = [{'bone': 'g', 'number': 591, 'channels': 8, 'ground': True}]
        ini = [(-209, 0, [], 62, 7), (9, 0, [(1, 2)], 63, 0), (10, 0, [(2, 3)], 63, 0)]
        made = prefabs8.with_channels(ground + roots, ini)
        assert made == [(-209, 0, [], 62, 7, 8, 1), (9, 0, [(1, 2)], 63, 0, None, 2), (10, 0, [(2, 3)], 63, 0, None, 2)]
        d = types.SimpleNamespace(NAME='X', CODE='xxx', DONOR='lar', SEX='male', GAME='tekken8')
        assert 'weapons = -209:0::62:7:8:1 9:0:1>2:63:0::2 10:0:2>3:63:0::2' in pack.character_ini(d, 21, weapons=made)
        assert prefabs8.with_channels(roots, ini[1:]) == ini[1:]          # (no ground: as before)

    def test_the_channels_field_of_a_weapons_line(self):
        d = types.SimpleNamespace(NAME='X', CODE='xxx', DONOR='lar', SEX='male', GAME='tekken8')
        text = pack.character_ini(d, 21, weapons=[(-209, 0, [], 62, 0, 8), (-208, 0, [], 13, 7), (1, 9, [], None)])
        line = next(x for x in text.splitlines() if x.startswith('weapons = '))
        assert line == 'weapons = -209:0::62:0:8 -208:0::13:7 1:9:'

    def test_a_root_point_takes_no_pair_a_ground_bone_has_as_channels(self):
        class D:
            WEAPONS = [{'bone': 'blade', 'pair': 1, 'summon': 0},
                       {'bone': 'ground', 'parent': 'root', 'number': 590, 'channels': 2, 'ground': True}]

        def box(y):
            return types.SimpleNamespace(loc=summons8.ROOT_CODE, loc2=summons8.ROOT_CODE, radius=0.0, a=(0.0, y, 0.0),
                                         b=(0.0, y, 300.0), first=1, last=1)
        k = types.SimpleNamespace(tables={'moves': [{'hitboxes': (box(900.0), box(1100.0)), 'first_active': 1,
                                                     'last_active': 1}]})
        out = summons8.weapons(D, k)
        roots = [w for w in out if w.get('root') is not None]
        assert [w['pair'] for w in roots] == [3, 4]

    def test_a_named_move_gets_a_body_clip_row_after_its_own(self):
        end = {'id': 0, 'frame': 0, 'value': 0}
        moves = [{'extraprops': 0}, {'extraprops': None}]
        rows = [{'id': 0x8683, 'frame': 0x8001, 'value': 1}, dict(end)]

        class K:
            tables = {'moves': moves, 'extra_move_properties': rows}

            def move_name(self, i):
                return ''

            def iter_list(self, table, start, stop):
                n = start
                while True:
                    yield n, self.tables[table][n]
                    if stop(self.tables[table][n]):
                        return
                    n += 1
        stats = collections.Counter()
        prefabs8._named_body_clips(K(), {'body_clip_moves': {'#1': 7}}, stats)
        assert moves[0]['extraprops'] == 0
        assert [r['value'] for r in prefabs8._extras(K(), 1)] == [7]
        assert prefabs8._extras(K(), 1)[0]['frame'] == 0x8001
        assert stats["moves showing a body rig's clip the definition names"] == 1

    def test_a_summons_shine_reads_its_own_map_and_without_one_there_is_none(self):
        import numpy as np
        class Textures:
            def __init__(self, known):
                self.known = known

            def exists(self, path):
                return path in self.known

            def image(self, path, size):
                return np.full((size, size, 4), 128, np.uint8), None
        d = types.SimpleNamespace(PREFABS={'models': []})
        eff = {'textures': {'RMA': 'made/up'}, 'switches': {}, 'scalars': {}, 'vectors': {}}
        got = prefabs8.shine(d, eff, Textures({'made/up'}))
        assert got.shape == (prefabs8.SHINE_SIZE, prefabs8.SHINE_SIZE, 4) and got[..., 0].max() > 0
        flat = prefabs8.shine(d, {'textures': {}}, Textures(()))
        assert flat[..., :3].max() == 0

    def test_a_glow_gain_brightens_that_summons_glow_through_the_tone_curve_and_leaves_the_rest_as_it_was(self):
        import numpy as np
        from ttt2char.tekken8 import bake as bake8

        class Textures:
            def exists(self, path):
                return path in ('made/base', 'made/mask', 'made/ramp')

            def linear(self, path, size):
                img = np.full((size, size, 3), 0.2, np.float32)
                if path == 'made/ramp':                  # (a glow colour ramp: dark red to orange across the texture)
                    img[...] = np.array([0.4, 0.05, 0.0], np.float32)
                    img[:, size // 2:] = np.array([0.8, 0.4, 0.1], np.float32)
                return img, None
        eff = {'base': 'made_up_base', 'textures': {'Basecolor': 'made/base', 'EmissiveMask': 'made/mask',
                                                    'EmissiveMaskColor': 'made/ramp'},
               'switches': {'Use EmissiveMask': True, 'Use EmissiveMaskColor': True}, 'vectors': {},
               'scalars': {'BaseEmissive_Intensity': 1.0, 'AddEmisive_Intensity': 1.0}}
        d = types.SimpleNamespace(PREFABS={'models': [], 'bases': ('made_up_base',), 'texture_size': 8,
                                           'glowing': {'made_up_wing': 0.0, 'made_up_other': 0.0},
                                           'glow_gain': {'made_up_wing': 8.0}})
        other, _ = prefabs8.bake(d, eff, Textures(), 'made_up_other')
        wing, _ = prefabs8.bake(d, eff, Textures(), 'made_up_wing')
        flow = prefabs8._flow(eff['scalars'], eff['switches'], lambda slot: None)
        E = np.array([0.4, 0.05, 0.0]) * 0.2 * (flow + 1.0)
        assert np.allclose(other[0, 0], bake8.aces(E * bake8.GLOW_EXPOSURE), atol=1e-5)
        assert np.allclose(wing[0, 0], bake8.aces(E * bake8.GLOW_EXPOSURE * 8.0), atol=1e-5)
        assert (wing >= other).all() and (wing[..., 0] > other[..., 0]).all()
        assert (wing[:, 4:].mean((0, 1)) > wing[:, :4].mean((0, 1)))[:2].all()     # the ramp kept
        del d.PREFABS['glow_gain']
        assert np.allclose(prefabs8.bake(d, eff, Textures(), 'made_up_wing')[0], other)

    def test_a_summon_its_template_draws_doubled_is_baked_at_half_its_colour_and_keeps_its_cover(self):
        import numpy as np

        class Textures:
            def exists(self, path):
                return path == 'made/base'

            def linear(self, path, size):
                return np.full((size, size, 3), 0.6, np.float32), None
        eff = {'base': 'made_up_base', 'textures': {'Basecolor': 'made/base'}, 'switches': {}, 'vectors': {},
               'scalars': {}}
        d = types.SimpleNamespace(PREFABS={'models': [], 'bases': ('made_up_base',), 'texture_size': 8,
                                           'see_through': {'made_up_veil': 0.5, 'made_up_cloak': 0.5},
                                           'drawn_doubled': ('made_up_veil',)})
        veil, veil_cover = prefabs8.bake(d, eff, Textures(), 'made_up_veil')
        cloak, cloak_cover = prefabs8.bake(d, eff, Textures(), 'made_up_cloak')
        assert np.allclose(cloak, 0.6) and np.allclose(veil, 0.3)
        assert np.allclose(veil_cover, 0.5) and np.allclose(cloak_cover, 0.5)

    def test_a_prefab_held_in_a_joint_hangs_at_that_joint_in_its_frame(self):
        import numpy as np
        rig = prefabs8.HandRig.__new__(prefabs8.HandRig)
        rig.name, rig._clips, rig.keep_sk = 'held', {}, [1]
        rig.skeleton = {'parents': [-1, 0]}
        worlds = np.repeat(np.eye(4)[None, None], 2, 0).repeat(2, 1)
        worlds[:, 1, :3, 3] = (1.0, 2.0, 3.0)
        rig._world_of = lambda kind, clip: worlds
        rig.O = np.eye(3)
        got = rig.locals_of('k', 0, None)
        assert np.allclose(got, _joint_locals(worlds))
        assert rig.place() is None
        d = types.SimpleNamespace(PREFABS={'models': [{'name': 'held', 'weapon': 'pf_held'}]})
        rigs = prefabs8.rigs
        prefabs8.rigs = lambda store, d_, log=print: [rig]
        try:
            out = prefabs8.placed(None, d, [{'bone': 'pf_held', 'parent': 'TE_L_jnt'}])
        finally:
            prefabs8.rigs = rigs
        assert 'place' not in out[0]

    def test_a_veined_summon_glows_on_its_metal_and_its_membranes_are_lit(self):
        import numpy as np
        side = 8

        class Textures:
            def exists(self, path):
                return path in ('base', 'rma', 'mask')

            def linear(self, path, size):
                return np.full((side, side, 3), 0.1 if path == 'base' else 0.5, np.float32), None

            def image(self, path, size):         # (RMA: rough everywhere, metal on the left half only)
                im = np.zeros((side, side, 4), np.uint8)
                im[..., 0] = 255
                im[:, :side // 2, 1] = 255
                return im, None
        eff = {'textures': {'Basecolor': 'base', 'RMA': 'rma', 'EmissiveMask': 'mask'},
               'switches': {'Use EmissiveMask': True},
               'vectors': {'BaseEmissive_Color': {'r': 0.0, 'g': 1.0, 'b': 1.0}},
               'scalars': {'BaseEmissive_Intensity': 1.0, 'AddEmisive_Intensity': 1.0}}
        plain = types.SimpleNamespace(PREFABS={'models': [], 'metal_lit': ('made_up',)})
        veined = types.SimpleNamespace(PREFABS={'models': [], 'metal_lit': ('made_up',),
                                                'veins': {'made_up': (3.0, 2.0)}})
        before, _ = prefabs8.bake(plain, eff, Textures(), 'made_up')
        after, _ = prefabs8.bake(veined, eff, Textures(), 'made_up')
        metal, membrane = (slice(None), slice(0, side // 2)), (slice(None), slice(side // 2, None))
        assert np.allclose(after[membrane], 0.3)                    # no glow, its colour lit 3 times
        assert before[membrane][..., 1].min() > 0.1                 # (glowing all over before)
        assert after[metal][..., 1].min() > before[metal][..., 1].min()
        framed = types.SimpleNamespace(PREFABS={'models': [], 'metal_lit': ('made_up',),
                                                'veins': {'made_up': (3.0, 2.0, 0.0, 0.5)}})
        dimmed, _ = prefabs8.bake(framed, eff, Textures(), 'made_up')
        assert np.allclose(dimmed[membrane], 0.3)                   # (a frame gain: the metal's own colour only)
        assert np.allclose(dimmed[metal] - after[metal], -0.05, atol=1e-6)

    def test_veins_take_gains_by_channel_and_a_sharper_frame_share(self):
        import numpy as np
        side = 12

        class Textures:
            def exists(self, path):
                return path in ('base', 'rma', 'mask')

            def linear(self, path, size):
                return np.full((side, side, 3), 0.1 if path == 'base' else 0.5, np.float32), None

            def image(self, path, size):  # (RMA: no metal on the left third, half in the middle, all on the right)
                im = np.zeros((side, side, 4), np.uint8)
                im[..., 0] = 255
                im[:, side // 3:2 * side // 3, 1] = 128
                im[:, 2 * side // 3:, 1] = 255
                return im, None
        eff = {'textures': {'Basecolor': 'base', 'RMA': 'rma', 'EmissiveMask': 'mask'},
               'switches': {'Use EmissiveMask': True},
               'vectors': {'BaseEmissive_Color': {'r': 0.0, 'g': 1.0, 'b': 1.0}},
               'scalars': {'BaseEmissive_Intensity': 1.0, 'AddEmisive_Intensity': 1.0}}

        def baked(veins):
            d = types.SimpleNamespace(PREFABS={'models': [], 'metal_lit': ('made_up',), 'veins': {'made_up': veins}})
            return prefabs8.bake(d, eff, Textures(), 'made_up')[0]
        none, half = (slice(None), slice(0, side // 3)), (slice(None), slice(side // 3, 2 * side // 3))
        soft = baked(((1.0, 2.0, 3.0), 2.0, 0.0, (0.5, 0.5, 0.5)))
        sharp = baked(((1.0, 2.0, 3.0), 2.0, 0.0, (0.5, 0.5, 0.5), (0.25, 0.5)))
        assert np.allclose(soft[none][..., :3], (0.1, 0.2, 0.3))    # the membranes lit by channel
        assert np.allclose(sharp[none], soft[none])
        # half metal: half membrane and half frame colour before, all frame with the frame share from 0.25 to 0.5 (its
        # glow on the raw metal share in both)
        share = 128 / 255
        expected = 0.1 * (1.0 - share) * (0.5 - np.array([1.0, 2.0, 3.0]))
        assert np.allclose(sharp[half][..., :3] - soft[half][..., :3], expected, atol=1e-4)

    def test_a_dissolving_lace_model_s_root_weapon_dissolves_the_others_are_not_scaled(self):
        d = types.SimpleNamespace(
            PREFABS={'models': [{'name': 'a', 'weapon': 'pf_a', 'lace': {'dissolve': True}},
                                {'name': 'b', 'weapon': 'pf_b', 'lace': {}}, {'name': 'c', 'weapon': 'pf_c'}]},
            WEAPONS=[{'bone': 'pf_a', 'number': 598, 'prefab': True}, {'bone': 'pf_b', 'number': 597, 'prefab': True},
                     {'bone': 'pf_c', 'number': 596, 'prefab': True}])
        ini = [(-202, 2, [], 6, 7), (-203, 2, [], 7, 7), (-204, 2, [], 8, 7, 3), (0, 9, [], 0, 6)]
        assert prefabs8.with_fades(d, ini) == [(-202, 2, [], 6, 7 | prefabs8.RAMP_DISSOLVE), (-203, 2, [], 7, 0),
                                               (-204, 2, [], 8, 0, 3), (0, 9, [], 0, 6)]

    def test_a_dissolving_summon_s_fade_takes_the_share_its_lace_names(self):
        assert prefabs8.dissolve_frames(10, 0.25) == 3        # (2.5 up)
        assert prefabs8.dissolve_frames(25, 0.25) == 6
        assert prefabs8.dissolve_frames(4, 0.25) == 2         # (never under 2: 0 or 1 is no fade at all)
        assert prefabs8.dissolve_frames(20, 1.0) == 20 and prefabs8.dissolve_frames(20, 3.0) == 20

    def test_a_seen_colour_keeps_the_detail_around_that_colour(self):
        import numpy as np
        rgb = np.zeros((2, 2, 3), np.float32)
        rgb[0, 0] = (0.8, 0.2, 0.1)
        rgb[1, 1] = (0.4, 0.1, 0.05)
        got = prefabs8.seen_colour(rgb, (0.1, 0.2, 0.3))
        assert np.allclose(got.reshape(-1, 3).mean(0), (0.1, 0.2, 0.3), atol=1e-5)
        assert got[0, 0, 2] > got[1, 1, 2] > got[0, 1, 2] == 0

    def test_a_see_through_summon_covers_that_share_of_what_is_behind_it_times_its_own_cut_outs(self):
        import numpy as np

        class Textures:
            def exists(self, path):
                return path in ('made/base', 'made/obd')

            def linear(self, path, size):
                img = np.full((size, size, 3), 0.5, np.float32)
                if path == 'made/obd':
                    img[:, : size // 2] = 0.0            # (its left half cut out)
                return img, None
        eff = {'base': 'made_up_base', 'textures': {'Basecolor': 'made/base', 'OBD': 'made/obd'}, 'switches': {},
               'vectors': {}, 'scalars': {}}
        d = types.SimpleNamespace(PREFABS={'models': [], 'bases': ('made_up_base',), 'texture_size': 8,
                                           'see_through': {'made_up_veil': 0.6}})
        _, solid = prefabs8.bake(d, eff, Textures(), 'made_up_other')
        _, veil = prefabs8.bake(d, eff, Textures(), 'made_up_veil')
        assert np.allclose(veil, solid * 0.6)
        assert veil[:, :4].max() == 0 and np.allclose(veil[:, 4:], 0.3)
        eff['textures'].pop('OBD')
        _, whole = prefabs8.bake(d, eff, Textures(), 'made_up_veil')
        assert whole.shape == (8, 8) and np.allclose(whole, 0.6)

    def test_two_thick_boxes_on_one_line_hit_along_one_line_from_the_nearest_end_to_the_farthest(self):
        # (d/b+2,1's ice spikes: a clip has two root points, so the four ends would fall to two)
        def box(z):
            return types.SimpleNamespace(loc=summons8.ROOT_CODE, loc2=summons8.ROOT_CODE, radius=260.0,
                                         a=(0.0, 1300.0, z), b=(0.0, 500.0, z))
        mv = {'hitboxes': [box(1000.0), box(1750.0)]}
        stats = collections.Counter()
        prefabs8.thick_roots(types.SimpleNamespace(tables={'moves': [mv]}), stats)
        near, far = (0.0, 900.0, 740.0), (0.0, 900.0, 2010.0)
        assert mv['spots'] == [near, far, near, far]
        assert mv['hitbox'] == bytes([summons8.ROOT_CODE] * 4)
        mv = {'hitboxes': [box(1000.0), types.SimpleNamespace(loc=13, loc2=12, radius=0.0, a=(0, 0, 0), b=(0, 0, 0))]}
        prefabs8.thick_roots(types.SimpleNamespace(tables={'moves': [mv]}), stats)
        assert mv['spots'] == [near, (0.0, 900.0, 1260.0), 13, 12]                 # (one: as before)


class SceneCutsTest(unittest.TestCase):
    """prefabs8.scene_cuts: a throw's one-frame jump of the attacker (a camera cut) taken back, the victim thrown that
    much further, on made-up paths."""
    F, CUT, PUSH = 12, 8, 3

    def setUp(self):
        z = np.zeros((self.F, 3))
        self.attacker = z.copy()
        self.attacker[:, 2] = -50.0 * np.arange(self.F)               # (backing off ..)
        self.attacker[self.CUT:, 2] -= 2000.0                          # (.. and 2 m back in one frame)
        self.attacker[:, 1] = 900.0
        self.victim = z.copy()
        self.victim[:, 2] = [0, -10, -20, -30, -10, 50, 150, 250, 300, 300, 290, 280]   # (pushed from frame 3)
        self.paths = {'A': self.attacker, 'V': self.victim, 'S': z}
        names = ['Okm_throw', 'Okm_thrown', '']
        self.k = types.SimpleNamespace(tables={'moves': [{}, {}, {}]}, move_name=lambda i: names[i],
                                       anim_ref=lambda i: ('AVS'[i], 0))

    def cuts(self, spec):
        return prefabs8.scene_cuts(self.k, types.SimpleNamespace(PREFABS={'scene_cuts': spec}),
                                   lambda key: self.paths[key], log=lambda *a: None)

    def test_the_attacker_has_no_jump_and_the_victim_ends_as_far_from_him_as_before(self):
        out = self.cuts({'Okm_throw': (self.CUT, 'Okm_thrown', self.PUSH)})
        A, V = self.attacker + out['A'], self.victim + out['V']
        steps = np.linalg.norm(np.diff(A, axis=0), axis=1)
        np.testing.assert_allclose(steps, 50.0)                       # (backing off all through)
        np.testing.assert_allclose(out['A'][:self.CUT], 0.0)
        np.testing.assert_allclose(V[self.CUT:] - A[self.CUT:], self.victim[self.CUT:] - self.attacker[self.CUT:])
        np.testing.assert_allclose(out['V'][:self.PUSH + 1], 0.0)    # (as he was until his push)
        assert (np.diff(out['V'][:, 2]) >= 0).all() and out['V'][self.CUT, 2] == 2000.0
        assert (out['V'][:, :2] == 0).all()                            # (along the jump only, never up)

    def test_a_named_move_without_a_jump_or_a_push_is_refused(self):
        with self.assertRaises(ValueError):
            self.cuts({'Okm_throw': (self.CUT - 2, 'Okm_thrown', self.PUSH)})
        with self.assertRaises(ValueError):
            self.cuts({'Okm_throw': (self.CUT, 'Okm_thrown', 9)})          # (a push after the cut)
        self.paths['V'] = -self.victim
        with self.assertRaises(ValueError):
            self.cuts({'Okm_throw': (self.CUT, 'Okm_thrown', self.PUSH)})  # (pushed towards him)
        with self.assertRaises(ValueError):
            self.cuts({'Okm_throw': (self.CUT, 'Okm_nobody', self.PUSH)})

    def test_a_fighter_without_cuts_has_none(self):
        assert prefabs8.scene_cuts(self.k, types.SimpleNamespace(PREFABS={}), None) == {}
        assert prefabs8.scene_cuts(self.k, types.SimpleNamespace(), None) == {}


if __name__ == '__main__':
    unittest.main()
