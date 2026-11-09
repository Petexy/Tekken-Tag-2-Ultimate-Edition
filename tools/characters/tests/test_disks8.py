"""convert/disks8.py: a blade's circle, made-up points."""
import math

import numpy as np

from ttt2char.convert import disks8


def _way(radius, centre, degrees):
    return np.array([[centre[0] + radius * math.cos(math.radians(a)), centre[1] + radius * math.sin(math.radians(a)), centre[2]]
                     for a in degrees])


def test_circle_finds_centre_radius_and_turning_sense():
    got = disks8.circle(_way(1200.0, (10.0, 900.0, -40.0), range(0, 120, 15)))
    centre, normal, radius = got
    assert np.allclose(centre, (10.0, 900.0, -40.0), atol=1e-3)
    assert abs(radius - 1200.0) < 1e-3
    assert np.allclose(normal, (0.0, 0.0, 1.0), atol=1e-6)      # counter-clockwise in x, y


def test_circle_turns_the_normal_with_the_way():
    assert np.allclose(disks8.circle(_way(800.0, (0.0, 0.0, 0.0), range(120, 0, -15)))[1], (0.0, 0.0, -1.0), atol=1e-6)


def test_a_thrust_has_no_circle():
    tips = np.array([[0.0, 1000.0, z] for z in range(0, 800, 100)], np.float64)
    assert disks8.circle(tips) is None


def test_turns_flat_without_turns():
    assert np.allclose(disks8.turns(0.0, 0.0, 0.0), np.eye(3))


def test_turns_apply_the_sideways_turn_first():
    assert np.allclose(disks8.turns(0.0, 90.0, 0.0)[:, 1], (0.0, 0.0, 1.0))         # tips towards the front
    assert np.allclose(disks8.turns(90.0, 0.0, 0.0)[:, 1], (-1.0, 0.0, 0.0))        # tips over to one side
    assert np.allclose(disks8.turns(90.0, 90.0, 0.0)[:, 1], (0.0, 0.0, 1.0))        # the first turn's front stays on the last's axis


class _Pieces:
    """Two rigid pieces of a vertex animation (made up): UV1 u picks the column, a marker vertex at v 1."""
    positions = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [5.0, 0.0, 0.0], [6.0, 0.0, 0.0], [9.0, 9.0, 9.0]])
    uvs = np.array([[[0.0, 0.0], [0.25, 0.25]], [[0.0, 0.0], [0.25, 0.25]], [[0.0, 0.0], [0.75, 0.25]], [[0.0, 0.0], [0.75, 0.25]],
                    [[0.0, 0.0], [0.75, 1.0]]])


def _vat(moves, turn_z=0.0):
    """(positions, rotations) textures over frames 0, 1: piece 0 stays, piece 1 moves by `moves` and turns about z."""
    pos = np.zeros((2, 2, 4), np.float32)
    pos[:, 0, :3] = (0.5, 0.0, 0.0)
    pos[:, 1, :3] = (5.5, 0.0, 0.0)
    pos[1, 1, :3] += moves
    rot = np.zeros((2, 2, 4), np.float32)
    rot[1, 1, 2] = math.sin(turn_z / 2.0)
    return pos, rot


def test_ice_frame_zero_is_the_mesh_as_stored_without_the_markers():
    p, kept = disks8.ice_frame(_Pieces, *_vat((0.0, 3.0, 0.0)), 0)
    assert np.allclose(p, _Pieces.positions)
    assert kept.tolist() == [True, True, True, True, False]


def test_ice_frame_moves_and_turns_each_piece_about_its_pivot():
    p, _ = disks8.ice_frame(_Pieces, *_vat((0.0, 3.0, 0.0), math.pi), 1)
    assert np.allclose(p[:2], _Pieces.positions[:2], atol=1e-5)                 # (piece 0 stays)
    assert np.allclose(p[2], (6.0, 3.0, 0.0), atol=1e-3)                       # (piece 1 half a turn about its pivot, then moved)
    assert np.allclose(p[3], (5.0, 3.0, 0.0), atol=1e-3)


def _flat(value):
    """A made-up texture: every texel `value` (a mask's worst case: the band full of it)."""
    return np.full((64, 64, 4), value, np.float32)


def test_a_fire_band_is_bright_lines_over_a_faint_smoke_the_fighter_seen_through(monkeypatch):
    monkeypatch.setattr(disks8, '_image', lambda store, path, cache: _flat({'streaks': 1.0, 'flame': 0.8}.get(path, 0.6)))
    tex = {k: k for k in ('streaks', 'wedge', 'flame', 'flame2', 'cells')}
    rgba = disks8.fire_look(None, tex, along=256, across=128).astype(np.float64)
    lum = rgba[..., :3].max(-1)
    dark = rgba[..., 3][lum < 0.35 * 255]
    assert dark.size and dark.max() < 0.5 * 255                # (its smoke a faint haze: no opaque dark band)
    line = rgba[:, int(disks8.FIRE_LINE_AT * 128)]
    hot = line[line[:, 3] > 200]
    assert len(hot) and hot[:, 0].min() > 230 and (hot[:, 1] > 150).all()      # (a bright orange-white line)


def test_the_ink_wheel_is_see_through(monkeypatch):
    monkeypatch.setattr(disks8, '_image', lambda store, path, cache: _flat({'lightning': 0.0, 'wedge': 0.0}.get(path, 1.0)))
    tex = {k: k for k in ('streaks', 'wedge', 'cells', 'noise', 'lightning', 'marble')}
    thin = disks8.ink_look(None, tex, along=256, across=128, density=disks8.INK_DENSITY, water=disks8.INK_WATER)
    body = thin[:, :100]                                            # (inside its far rim's line)
    ink = body[..., 3][body[..., :3].max(-1) < 0.4 * 255]
    assert ink.size and ink.max() <= 0.6 * 255
    thick = disks8.ink_look(None, tex, along=256, across=128)[:, :100]      # (the old ink: 0.88)
    assert thick[..., 3].max() > 0.8 * 255


def test_heatwaves_column_is_see_through_and_still_leans_at_its_end():
    copies = disks8.swing_copies(27)
    assert len(copies) == disks8.SWING_STEPS * len(disks8.SWING_LAYERS)
    for (ramp, _, _, alpha), copy in zip(disks8.SWING_LAYERS * disks8.SWING_STEPS, copies):
        assert copy[3] == ramp and max(a for _, a in copy[6]) <= alpha <= 0.6
    leans = [c[5] for c in copies]
    assert leans[0] == disks8.SWING_LEAN[0] and leans[-1] == disks8.SWING_LEAN[1] > 0.0
