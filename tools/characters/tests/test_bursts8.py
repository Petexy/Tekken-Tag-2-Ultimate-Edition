"""convert/bursts8.py: placing a burst's sprites from a body part that moves and turns, made-up clip points."""
import math
import os
import sys
import unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from ttt2char.convert import bursts8  # noqa: E402


def _turn(degrees):
    """A level turn about y (the clip's up) as disks8 / trails8 use them: columns are the effect's axes."""
    a = math.radians(degrees)
    return np.array([[math.cos(a), 0.0, math.sin(a)], [0.0, 1.0, 0.0], [-math.sin(a), 0.0, math.cos(a)]])


def _clip(frames=6, part=13, anchor=('part', 13)):
    """A fighter walking forward 100 mm a frame while turning 10 degrees a frame; his part `part` 1 m up, 300 mm
    left."""
    at = np.array([[0.0, 1000.0, 100.0 * f] for f in range(frames)]) + np.array((300.0, 0.0, 0.0))
    parts = np.zeros((frames, 22, 3))
    parts[:, part] = at
    parts[:, 16] = parts[:, 19] = np.array([[0.0, 0.0, 100.0 * f] for f in range(frames)])
    near = at + np.array((0.0, 0.0, 50.0))
    tools = {'sword': (near, near + np.array((0.0, 1000.0, 0.0))), 'staff': (at, at + np.array((0.0, -1000.0, 0.0)))}
    return dict(at=at, levels=np.array([_turn(10.0 * f) for f in range(frames)]), parts=parts, tools=tools,
                anchor=anchor, part=part, place=None)


class _System:
    def __init__(self, user):
        self.user = user


class _Out:
    """bursts8.Bits's calls, kept."""

    def __init__(self):
        self.sprites, self.sparked = [], []

    def sprite(self, tex, place, delay, life, size, count, spread, speed, additive, alpha, lean=None, local=False,
               colour=None, grow=None):
        self.sprites.append(dict(tex=tex, place=np.asarray(place), delay=delay, life=life, size=size, local=local,
                                 grow=grow, alpha=alpha, additive=additive))

    def sparks(self, place, delay, life, size, count, spread, speed, colour=None):
        self.sparked.append(np.asarray(place))


class _Textures:
    def bake(self, key, rgba, largest=None):
        return key


class _Conv:
    textures = _Textures()


class _Bits(_Out):
    """bursts8.Bits's calls with bars, turns and growth, kept."""

    def __init__(self):
        super().__init__()
        self.bars = []

    def bar(self, tex, place, delay, life, wide, high, additive, alpha, colour=None):
        self.bars.append(dict(tex=tex, place=np.asarray(place), delay=delay, life=life, wide=wide, high=high,
                              additive=additive, alpha=alpha, turn=0.0, grow=None))

    def sprite(self, *args, **kw):
        super().sprite(*args, **kw)
        self.bars.append(self.sprites[-1])

    def turned(self, angle):
        self.bars[-1]['turn'] = angle

    def grown(self, life, factor):
        self.bars[-1]['grow'] = factor


def _standing(frames=60):
    """A fighter standing still (hips 1 m up, facing +z) for the bursts placed from the hips."""
    clip = _clip(frames=frames, part=0, anchor=('part', 0))
    clip['at'] = np.tile((0.0, 1000.0, 0.0), (frames, 1))
    clip['parts'][:, 0] = clip['at']
    clip['parts'][:, 2] = clip['at'] + (0.0, 350.0, 0.0)
    clip['parts'][:, 16] = clip['parts'][:, 19] = 0.0
    clip['levels'] = np.array([np.eye(3)] * frames)
    return clip

class Bursts8Test(unittest.TestCase):
    def patch(self, target, name, value):
        """target.name is value until the test ends (pytest's monkeypatch.setattr)."""
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_point_on_the_part_is_the_effects_origin_at_every_frame(self):
        clip = _clip()
        at = bursts8.Placer(clip)
        for f in range(6):
            assert np.allclose(at(clip['at'][f], f), 0.0)

    def test_places_follow_the_parts_level_turn(self):
        clip = _clip()
        at = bursts8.Placer(clip)
        # (1 m ahead of the part in frame 3's level frame comes back as 1 m along the effect's z)
        ahead = clip['at'][3] + clip['levels'][3] @ np.array((0.0, 0.0, 1000.0))
        assert np.allclose(at(ahead, 3), (0.0, 0.0, 1000.0))
        assert np.allclose(at.level((0.0, 0.0, 1000.0), 3), ahead - clip['at'][3])

    def test_frames_past_the_clip_hold_its_last(self):
        clip = _clip()
        at = bursts8.Placer(clip)
        assert np.allclose(at(clip['at'][-1], 40), 0.0)
        assert np.allclose(at.part(13, -3), clip['at'][0])

    def test_tools_and_floor(self):
        clip = _clip()
        at = bursts8.Placer(clip)
        assert np.allclose(at.tool('sword', 2, 0.5), clip['at'][2] + (0.0, 500.0, 50.0))
        assert at.floor() == 0.0

    def test_which_bursts_are_the_same_in_every_move(self):
        hand = _clip(part=12, anchor=('part', 12))
        staff = _clip(part=13, anchor=('part', 120))
        foot = _clip(part=16, anchor=('part', 16))
        assert bursts8.same_anywhere(('thunder', 36), staff)
        assert not bursts8.same_anywhere(('bolts', 8), staff)           # (along the staff in this move's clip)
        assert bursts8.same_anywhere(('bolts', 8), hand)
        assert not bursts8.same_anywhere(('hand', 14), hand)            # (along the forearm)
        assert bursts8.same_anywhere(('feet', 10), foot)
        assert not bursts8.same_anywhere(('jet', 8), foot)

    def test_a_burst_goes_where_its_rows_say_else_its_own_offset(self):
        clip = _clip(part=0, anchor=('part', 0))
        clip['parts'][:, 0] = clip['at']
        at = bursts8.Placer(clip)
        hips = clip['at'][0]
        # no rows: its system's offset (cm ahead, right, up) -> mm left, up, ahead in the spawn's level frame
        d = dict(clip=clip, id=7)
        spot = bursts8._offset(d, lambda i: _System({'User.OffsetPos': [90.0, -20.0, 40.0]}), at)
        assert np.allclose(spot, hips + (200.0, 400.0, 900.0))
        # rows: (up, forward, sideways) from the bone over the hips
        clip['place'] = ((100.0, 750.0, -50.0), (0, 0, 0))
        spot = bursts8._offset(d, lambda i: _System({}), at)
        assert np.allclose(spot, hips + (-50.0, 100.0 + bursts8.disks8.BONE_ABOVE_HIPS, 750.0))

    def test_the_beams_picture_is_a_dark_core_in_a_bright_sheath_and_repeats_along_it(self):
        rgba = bursts8.beam_core_look().astype(np.float64)
        h, w = rgba.shape[:2]
        middle = rgba[:, w // 2]
        assert (middle[:, 3] > 230).all() and (middle[:, 2] > middle[:, 0]).all() and middle[:, :3].sum(1).mean() < 400
        rims = rgba[:, :w // 2, :3].sum(2).max(1)               # (the brightest across each row's one half: its sheath)
        assert (rims > 600).all()
        assert (rgba[:, 0, 3] < 0.2 * 255).all()                # (its edge: a faint glow)
        assert np.abs(rgba[0] - rgba[-1]).mean() < 12.0          # (its last row runs into its first)

    def test_a_beams_piece_is_a_standing_quad_narrowing_along_it(self):
        start, ahead, up = np.array((0.0, 1000.0, 300.0)), np.array((0.0, 0.0, 1.0)), np.array((0.0, 1.0, 0.0))
        pos, uv, tris = bursts8.beam_piece(start, ahead, up, 1000.0, 2000.0, 300.0, 100.0, along=-600.0)
        assert len(pos) == 4 and len(tris) == 2 and tris.max() == 3
        assert np.allclose(pos[:, 0], 0.0)
        assert np.allclose(np.abs(pos[:2, 1] - 1000.0), 300.0) and np.allclose(np.abs(pos[2:, 1] - 1000.0), 100.0)
        assert np.allclose(pos[:2, 2], 1300.0) and np.allclose(pos[2:, 2], 2300.0)
        assert np.allclose(uv[:, 1], [400.0 / bursts8.BEAM_TILE] * 2 + [1400.0 / bursts8.BEAM_TILE] * 2)
        assert set(uv[:, 0]) == {0.0, 1.0}

    def test_a_system_converted_whole_is_the_same_in_every_move(self):
        assert bursts8.same_anywhere(('niagara', 60), _clip(part=9, anchor=('part', 121)))
        assert not bursts8.same_anywhere(('beam', 48), _clip(part=0, anchor=('part', 0)))

    def test_the_veins_picture_is_white_on_its_lines_frosted_blue_round_them_and_soft_at_its_edges(self):
        side = 512                                              # (a made-up mask: one line up the middle)
        mask = np.zeros((side, side, 4), np.float32)
        mask[:, side // 2 - 1:side // 2 + 1, 0] = 1.0
        grain = np.full((side, side, 4), 0.1, np.float32)      # (a made-up grain: a peak every 8 texels)
        grain[::8, ::8] = 1.0
        self.patch(bursts8.disks8, '_image', lambda store, path, cache: {'mask': mask, 'grain': grain}[path])
        rgba = bursts8.veins_look(None, {'Mask2Texture': 'mask', 'BaseTexture': 'grain'}, {'BaseTexture': (1.0, 1.0)})
        n = rgba.shape[0]
        assert n == bursts8.VEINS_SIDE
        row = rgba[n // 2]
        line, near, glint, far = row[n // 2], row[n // 2 + 3], row[n // 2 + 4], row[n // 2 + 40]
        assert line[3] > 240 and min(line[:3]) > 220                      # (white, opaque)
        assert 60 < near[3] < line[3] and near[2] > near[0] + 40          # (a blue frost beside it)
        assert glint[3] > near[3] and glint[0] > near[0] + 40             # (whiter where its grain peaks)
        assert far[3] == 0
        assert rgba[0, n // 2, 3] == 0 and rgba[n - 1, n // 2, 3] == 0    # (soft at the edges)

    def test_the_wing_flash_rises_from_its_root_out_to_its_side_and_goes_with_him(self):
        self.patch(bursts8, '_veins', lambda conv, d, system_of: 'veins')
        flashes = {}
        for recipe in ('wing', 'wing_right'):
            out = _Out()
            bursts8._wing(out, _Conv(), dict(burst=(recipe, 24)), None, 24, None, None)
            flashes[recipe] = out
            frost = [s for s in out.sprites if s['tex'] == 'veins']
            veins, swept = frost[:len(bursts8.WING_SHEETS)], frost[len(bursts8.WING_SHEETS):]
            assert len(swept) == len(bursts8.WING_SWEPT)
            # (then back behind him as the wing sweeps: later, further back than up, each further out)
            assert all(s['delay'] >= bursts8.WING_SWEEP_AT and s['delay'] + s['life'] <= 24 for s in swept)
            assert all(-s['place'][2] > s['place'][1] - bursts8.WING_ROOT[1] for s in swept)
            assert [s['place'][2] for s in swept] == sorted((s['place'][2] for s in swept), reverse=True)
            assert not any(s['additive'] for s in swept)
            assert all(s['local'] for s in out.sprites)
            assert not any(s['additive'] for s in veins)  # (its frost drawn over the stage: white on a bright one too)
            assert all(s['additive'] for s in out.sprites if s['tex'] != 'veins')
            assert all(s['grow'] > 1.0 for s in veins)
            heights = [s['place'][1] for s in veins]
            assert heights == sorted(heights) and heights[-1] - heights[0] > 800.0      # (up the wing)
            assert veins[-1]['place'][2] < veins[0]['place'][2]                      # (and back)
            assert all(s['delay'] + s['life'] <= 24 for s in veins)
            assert all(s['alpha'][-1][1] == 0.0 for s in out.sprites)
        left, right = flashes['wing'].sprites, flashes['wing_right'].sprites
        for a, b in zip(left, right):                           # (the right wing's flash: the left's mirrored)
            assert np.allclose(a['place'] * (-1.0, 1.0, 1.0), b['place'])
        assert left[-1]['place'][0] > 0.0                       # (x: his left)
        assert bursts8.same_anywhere(('wing_right', 24), _clip(part=2, anchor=('weapon', 4)))

    def test_a_wing_shatters_where_its_rows_say(self):
        self.patch(bursts8, '_veins', lambda conv, d, system_of: 'veins')
        clip = _clip(part=0, anchor=('part', 0))
        clip['parts'][:, 0] = clip['at']
        clip['place'] = ((800.0, -500.0, 400.0), (0, 0, 0))
        at = bursts8.Placer(clip)
        out = _Out()
        bursts8._vanish(out, _Conv(), dict(clip=clip, source={'wing': 1}), at, 8, None, None)
        spot = np.array((400.0, 800.0 + bursts8.disks8.BONE_ABOVE_HIPS, -500.0))       # (from the hips at the spawn)
        assert np.allclose(out.sparked[0], spot)
        frost = out.sprites
        assert len(frost) == 1 and frost[0]['tex'] == 'veins' and np.allclose(frost[0]['place'], spot)
        assert max(a for _, a in frost[0]['alpha']) <= 0.5 and not frost[0]['local']         # (faint; left there)
        assert len(out.sparked) >= 3
        heights = [p[1] for p in out.sparked]
        assert heights == sorted(heights) and heights[-1] > heights[0]                  # (rising with the wing)
        out = _Out()
        bursts8._vanish(out, _Conv(), dict(clip=clip, source={}), at, 8, None, None)
        assert not out.sprites and out.sparked

    def test_a_slash_is_a_thin_white_line_in_a_blue_glow_faint_at_its_ends(self):
        rgba = bursts8.slash_look(0.0).astype(np.float64)
        h, w = rgba.shape[:2]
        middle = rgba[:, w // 2]
        full = np.flatnonzero(middle[:, 3] >= middle[:, 3].max() - 1)
        core = int(round(full.mean()))
        assert abs(core - h // 2) <= 1 and middle[core, 3] > 240 and min(middle[core, :3]) > 240     # (white, opaque)
        glow = middle[core + 8]
        assert 20 < glow[3] < middle[core, 3] and glow[2] > glow[0] + 40                              # (blue round it)
        assert middle[0, 3] == 0 and middle[-1, 3] == 0
        assert rgba[:, 2, 3].max() < 0.2 * 255 and rgba[:, -3, 3].max() < 0.2 * 255                  # (its ends)
        bent = bursts8.slash_look(0.25)
        assert np.argmax(bent[:, w // 2, 1]) > core + 4 and np.argmax(bent[:, w // 8, 1]) < core       # (bowed)

    def test_the_crescent_is_thickest_at_its_top_with_a_white_rim_and_clear_inside(self):
        rgba = bursts8.crescent_look().astype(np.float64)
        n = rgba.shape[0]
        top = rgba[:, n // 2]
        lit = np.flatnonzero(top[:, 3] > 40)
        assert lit.min() < n * 0.1                                  # (its rim near the picture's top)
        rim = top[lit.min():lit.min() + 4]
        assert rim[:, 3].max() > 200 and rim[:, :3].min(1).max() > 220       # (white)
        assert rgba[n // 2, n // 2, 3] == 0 and rgba[n - 4, n // 2, 3] == 0  # (clear inside, gone at the bottom)
        side = rgba[n // 2, :n // 2, 3]
        assert top[:, 3].sum() > 1.5 * side.sum()                   # (thinner at its sides than at its top)

    def test_ultimate_zantetsukens_flurry_is_slashes_at_every_angle_over_the_victim_ahead(self):
        clip = _standing()
        at = bursts8.Placer(clip)
        out = _Bits()
        bursts8._zan_ranbu(out, _Conv(), dict(clip=clip, id=98), at, 24, None, None)
        slashes = [b for b in out.bars if 'wide' in b]
        assert len(slashes) == bursts8.ZAN_SLASHES
        assert [b['delay'] for b in slashes[:3]] == [0, 0, 0] and max(b['delay'] for b in slashes) <= 12
        assert all(b['additive'] and b['wide'] >= 2000.0 and b['high'] < 300.0 for b in slashes)
        turns = [b['turn'] for b in slashes]
        assert max(turns) - min(turns) > 1.5 and all(abs(t) <= math.pi / 2.0 for t in turns)
        places = np.array([b['place'] for b in slashes])
        ahead, high = places[:, 2], places[:, 1] + 1000.0          # (from the hips, 1 m over the floor)
        assert np.all(np.abs(ahead - bursts8.ZAN_AHEAD) <= bursts8.ZAN_RANBU_ACROSS)
        assert np.all(np.abs(high - bursts8.ZAN_HIGH) <= 500.0) and np.allclose(places[:, 0], 0.0)
        assert out.sparked and all(b['alpha'][-1][1] == 0.0 for b in out.bars)

    def test_ultimate_zantetsukens_last_cut_is_a_long_level_line_through_the_victim(self):
        clip = _standing()
        at = bursts8.Placer(clip)
        out = _Bits()
        bursts8._zan_last(out, _Conv(), dict(clip=clip, id=96), at, 24, None, None)
        lines = [b for b in out.bars if 'wide' in b]
        assert len(lines) == 2 and all(b['turn'] == 0.0 and b['wide'] > 4000.0 and b['additive'] for b in lines)
        assert np.allclose(lines[0]['place'], (0.0, bursts8.ZAN_LAST_HIGH - 1000.0, bursts8.ZAN_AHEAD))
        ring = [s for s in out.sprites if s['grow']]
        assert len(ring) == 1 and ring[0]['grow'] > 2.0 and len(out.sparked) == 2

    def test_ultimate_zantetsukens_slash_and_sigil_round_him(self):
        clip = _standing()
        at = bursts8.Placer(clip)
        out = _Bits()
        bursts8._zan_trail(out, _Conv(), dict(clip=clip, id=99), at, 30, None, None)
        assert len(out.sprites) == 1 and out.sprites[0]['additive'] and out.sprites[0]['size'] >= 2000.0
        assert out.bars[0]['turn'] == bursts8.ZAN_TRAIL_TILT and out.sprites[0]['place'][2] > 0.0
        self.patch(bursts8.disks8, '_textures', lambda conv, system: {'Logo001': {'MaskTexture': 'sigil'}})
        self.patch(bursts8, 'sigil_look', lambda store, path: path)
        _Conv.store = None
        out = _Bits()
        bursts8._zan_sigil(out, _Conv(), dict(clip=clip, id=38), at, 60, lambda i: None, None)
        sigil = [s for s in out.sprites if s['tex'] == ('burst', 'zan', 'sigil')]
        assert len(sigil) == 1 and sigil[0]['life'] == 60 and sigil[0]['place'][2] < 0.0  # (behind him, while he waits)
        floor = [b for b in out.bars if 'wide' in b]
        assert len(floor) == 1 and np.isclose(floor[0]['place'][1], -960.0)                    # (40 mm over the floor)

    def test_updrafts_wind_leaves_a_dark_streak_behind_him_and_a_swirl_on_the_floor(self):
        self.patch(bursts8.disks8, 'feather_texture', lambda conv, system_of, source: 'feather')
        clip = _standing()
        at = bursts8.Placer(clip)
        out = _Bits()
        bursts8._updraft(out, _Conv(), dict(clip=clip, id=66, burst=('updraft', 16), source={}), at, 16, None, None)
        streaks = [b for b in out.bars if b['tex'] == ('burst', 'wind', 'streak')]
        assert [b['delay'] for b in streaks] == list(range(0, 16, 2))
        assert all(not b['additive'] and b['place'][2] < 0.0 for b in streaks)       # (dark, behind him)
        assert any(s['tex'] == 'feather' for s in out.sprites)
        out = _Bits()
        bursts8._updraft(out, _Conv(), dict(clip=clip, id=65, burst=('updraft_floor', 16), source={}), at, 16, None,
                         None)
        swirls = [b for b in out.bars if b['tex'] == ('burst', 'wind', 'swirl')]
        assert len(swirls) == 3 and all(b['grow'] > 1.0 and np.isclose(b['place'][1], -960.0) for b in swirls)
        assert all(np.isclose(b['place'][2], bursts8.UPDRAFT_SWIRL_AHEAD) for b in swirls)
        for recipe in ('updraft', 'updraft_floor', 'heat'):
            assert bursts8.same_anywhere((recipe, 16), _clip(part=0, anchor=('part', 0)))
            assert recipe in bursts8.disks8.ANY_MOVE and recipe in bursts8.disks8.ANCHORED

    def test_torgals_heat_is_one_thin_ring_growing_and_fading(self):
        out = _Bits()
        bursts8._heat(out, _Conv(), dict(id=199), None, 30, None, None)
        assert len(out.bars) == 1
        ring = out.bars[0]
        # (tall)
        assert ring['additive'] and ring['life'] == 30 and ring['grow'] > 1.0 and ring['high'] > 2.0 * ring['wide']
        assert ring['alpha'][0][1] == 0.0 and ring['alpha'][-1] == [30, 0.0]
        rgba = bursts8.thin_ring_look()
        n = rgba.shape[0]
        assert rgba[n // 2, n // 2, 3] == 0 and rgba[n // 2, int(n * 0.95) - 1, 3] > 200

    def test_the_wind_streak_is_dark_and_see_through_with_a_pale_line(self):
        rgba = bursts8.wind_streak_look().astype(np.float64)
        h, w = rgba.shape[:2]
        a = rgba[..., 3]
        assert a.max() <= 255 * 0.95 and a[:, w // 2].max() > 100
        dark = rgba[(a > 60) & (rgba[..., :3].max(-1) < 60)]
        assert len(dark) > 0.05 * h * w
        assert rgba[..., 1].max() > 150 and (rgba[..., 1] > rgba[..., 0] + 30).any()    # (its pale green line)
        assert a[:, 0].max() < 10 and a[0].max() < 10 and a[-1].max() < 10

    def test_burning_rains_pillar_is_a_streak_then_flames_up_from_the_floor_at_its_offset(self):
        self.patch(bursts8.disks8, '_flames', lambda conv, fires, name: ['f0', 'f1', 'f2', 'f3'])
        clip = _standing()
        at = bursts8.Placer(clip)
        out = _Bits()
        out.flame = lambda place, delay, *a, **k: out.sprites.append(dict(tex='flame', place=np.asarray(place),
                                                                          delay=delay))
        bursts8._column(out, _Conv(), dict(clip=clip, id=182), at, 30,
                        lambda i: _System({'User.OffsetPos': [110.0, 0.0, 0.0]}), None)
        bars = [b for b in out.bars if 'wide' in b]
        # (the white-hot streak)
        assert bars[0]['additive'] and bars[0]['delay'] == 0 and bars[0]['high'] > bursts8.COLUMN_HIGH
        flames = bars[1:]
        assert flames and all(not b['additive'] for b in flames)
        assert np.allclose([b['place'][2] for b in flames], 1100.0)                 # (its system's offset ahead)
        tops = [b['place'][1] + 1000.0 + b['high'] / 2.0 for b in flames]           # (over the floor)
        assert max(tops) > bursts8.COLUMN_HIGH * 0.9 and min(b['place'][1] + 1000.0 for b in flames) < 600.0
        assert max(b['delay'] + b['life'] for b in flames) <= 30 + bursts8.COLUMN_EVERY


if __name__ == '__main__':
    unittest.main()
