"""convert/uvmap8.py: a summon's second UV layout seen from its first, made-up meshes."""
import numpy as np

from ttt2char.convert import uvmap8


def _quad(uv0, uv1):
    """Two triangles over the corners uv0 / uv1 (4, 2) each: (uvs (4, 2, 2), tris)."""
    return np.stack([np.asarray(uv0, np.float64), np.asarray(uv1, np.float64)], 1), np.array([[0, 1, 2], [0, 2, 3]])


SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def setup_function(_):
    uvmap8._maps.clear()
    uvmap8._made.clear()


def test_one_set_is_not_kept():
    uvs, tris = _quad(SQUARE, SQUARE)
    uvmap8.register('one', uvs[:, :1], tris)
    assert not uvmap8.known('one')
    assert uvmap8.uv1_of('one', (8, 8)) is None


def test_each_texel_takes_its_point_in_the_second_layout():
    # (the second layout is the first turned half a turn: texel (u, v) lies at (1 - u, 1 - v))
    uvs, tris = _quad(SQUARE, [(1.0, 1.0), (0.0, 1.0), (0.0, 0.0), (1.0, 0.0)])
    uvmap8.register('turned', uvs, tris)
    got = uvmap8.uv1_of('turned', (16, 16))
    want = 1.0 - uvmap8.texel_uv((16, 16))
    assert got.shape == (16, 16, 2)
    assert np.allclose(got, want, atol=1e-6)


def test_texels_off_the_islands_take_their_neighbours_point_then_the_mean():
    half = [(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]
    uvs, tris = _quad(half, [(0.25, 0.25)] * 4)              # (all of it one point along the second layout)
    uvmap8.register('half', uvs, tris)
    got = uvmap8.uv1_of('half', (4, 64))
    assert np.allclose(got, 0.25)                           # (filled near the island, the mean further away)


def test_pieces_sharing_their_texels_with_points_of_their_own_give_none():
    a_uvs, tris = _quad(SQUARE, [(0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1)])
    b_uvs, _ = _quad(SQUARE, [(0.9, 0.9), (1.0, 0.9), (1.0, 1.0), (0.9, 1.0)])
    uvmap8.register('cards', np.concatenate([a_uvs, b_uvs]), np.concatenate([tris, tris + 4]))
    assert uvmap8.uv1_of('cards', (8, 8)) is None


def test_a_sheet_modelled_twice_back_to_back_keeps_its_points():
    uvs, tris = _quad(SQUARE, SQUARE)
    uvmap8.register('twice', np.concatenate([uvs, uvs]), np.concatenate([tris, tris[:, ::-1] + 4]))
    got = uvmap8.uv1_of('twice', (8, 8))
    assert got is not None and np.allclose(got, uvmap8.texel_uv((8, 8)), atol=1e-6)


def test_sample_is_bilinear_and_wraps():
    img = np.array([[[0.0], [1.0]], [[2.0], [3.0]]], np.float32)
    assert np.allclose(uvmap8.sample(img, np.array([0.25, 0.25])), 0.0)          # (a texel's middle)
    assert np.allclose(uvmap8.sample(img, np.array([0.5, 0.25])), 0.5)           # (between two along u)
    assert np.allclose(uvmap8.sample(img, np.array([1.25, 0.25])), 0.0)          # (one tile on)
    assert np.allclose(uvmap8.sample(img, np.array([0.0, 0.25])), 0.5)           # (the far texel's half across the edge)
