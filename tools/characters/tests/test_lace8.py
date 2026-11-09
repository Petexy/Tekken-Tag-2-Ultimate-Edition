"""convert/lace8.py: a sheet of many pieces drawn as a picture on a low grid, on made-up data (two combs, mirror images,
with a strip lying over each)."""
import numpy as np
import pytest

from ttt2char.convert import lace8

TEETH = [(100 + 200 * i, 220 + 200 * i) for i in range(5)]     # (x from, x to) mm: five teeth, 80 mm gaps
GOAL = 400


@pytest.fixture(autouse=True)
def _no_cards_left():
    """(lace8 keeps the cards a test makes by material name: cleared after it, so that another module's made-up
    material of the same name is not drawn as lace)"""
    yield
    lace8._cards.clear()


def _quad(x0, x1, y0, y1, z, uv0, uv1):
    """4 points of a quad in the plane z (normal +z) with its UV box, wound about +z."""
    pos = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
    uv = [(uv0[0], uv0[1]), (uv1[0], uv0[1]), (uv1[0], uv1[1]), (uv0[0], uv1[1])]
    return pos, uv, [(0, 1, 2), (0, 2, 3)]


def _wing():
    """One comb: teeth down from a spine (y 400..500), x 100..1100, its UV its place; a strip 20 mm in front of it
    (y 200..220) with its own corner of the UV layout. -> pos, uv, tris."""
    quads = [(x0, x1, 0, 400, 0.0, ((x0 - 100) / 1000.0, 0.0), ((x1 - 100) / 1000.0, 0.8)) for x0, x1 in TEETH]
    quads.append((100, 1100, 400, 500, 0.0, (0.0, 0.8), (0.9, 1.0)))
    quads.append((100, 1100, 200, 220, 20.0, (0.92, 0.92), (0.98, 0.98)))
    pos, uv, tris = [], [], []
    for q in quads:
        p, u, t = _quad(*q)
        tris += [(a + len(pos), b + len(pos), c + len(pos)) for a, b, c in t]
        pos += p
        uv += u
    return np.array(pos, np.float64), np.array(uv, np.float64), np.array(tris, np.int64)


def _streams(wound=1):
    """Both combs as a prefab's streams: the right the left mirrored (x -> -x), kept bones 0 (root) 1 (tip) for the
    left, 2 3 for the right; wound -1: the triangles the other way round about their normals."""
    pos, uv, tris = _wing()
    pos[:, 0] += 50.0
    mirrored = pos * [-1, 1, 1]
    P = np.concatenate([pos, mirrored])
    T = np.concatenate([tris, tris[:, [0, 2, 1]] + len(pos)])
    if wound < 0:
        T = T[:, [0, 2, 1]]
    n = len(P)
    nrm = np.tile([0.0, 0.0, 1.0], (n, 1))
    tip = np.clip((np.abs(P[:, 0]) - 150.0) / 1000.0, 0, 1)
    joints = np.zeros((n, 8), np.int64)
    weights = np.zeros((n, 8))
    joints[:, 0] = np.where(P[:, 0] > 0, 0, 2)
    joints[:, 1] = joints[:, 0] + 1
    weights[:, 0], weights[:, 1] = 1 - tip, tip
    tan = np.tile([1.0, 0.0, 0.0, 1.0], (n, 1))
    return dict(part='w', material='made_up_wing', tris=T, pos=P, nrm=nrm, tan=tan, uv=np.concatenate([uv, uv]),
                joints=joints, weights=weights)


def _cards(wound=1):
    lines = []
    out = lace8.cards([_streams(wound)], [-1, 0, -1, 2], GOAL, {'texture': (256, 128)}, log=lines.append)
    return out, lines


def test_a_lace_model_fits_its_vertices_and_the_mirror_image_shares_the_picture():
    (p,), lines = _cards()
    assert len(p['pos']) <= GOAL
    assert set(np.unique(p['tris'])) == set(range(len(p['pos'])))
    assert any('the picture of group 1 (its mirror image)' in x for x in lines)
    assert (p['uv'] >= 0).all() and (p['uv'] <= 1).all()
    left, right = p['pos'][:, 0] > 0, p['pos'][:, 0] < 0
    assert np.allclose(np.sort(p['uv'][left], 0), np.sort(p['uv'][right], 0))


@pytest.mark.parametrize('wound', [1, -1])
def test_every_face_winds_about_its_normal_as_the_source_did(wound):
    (p,), _ = _cards(wound)
    a, b, c = (p['pos'][p['tris'][:, k]] for k in range(3))
    turn = (np.cross(b - a, c - a) * p['nrm'][p['tris'][:, 0]]).sum(1)
    assert ((turn * wound) > 0).all()
    front = p['nrm'][:, 2] > 0
    assert 0 < front.sum() < len(front)              # (a front face and a back face each)


def test_the_grid_is_skinned_by_the_bones_under_it():
    (p,), _ = _cards()
    x = p['pos'][:, 0]
    top = p['joints'][np.arange(len(x)), np.argmax(p['weights'], 1)]
    assert (top[x > 950] == 1).all() and (top[(x > 0) & (x < 300)] == 0).all()
    assert (top[x < -950] == 3).all() and (top[(x < 0) & (x > -300)] == 2).all()


def test_the_picture_has_the_gaps_as_holes_and_the_front_piece_s_colour():
    (p,), _ = _cards()
    card = lace8.card('made_up_wing')
    bake = np.zeros((64, 64, 3), np.float32)
    bake[..., 0] = 1.0                                  # (the combs red, the strip's corner blue)
    bake[58:63, 58:63] = (0.0, 0.0, 1.0)
    rgb, alpha = card.texture(bake)
    assert rgb.shape == (128, 256, 3) and alpha.shape == (128, 256)
    # the picture's place of a point: the UV of the grid is an affine map of the left comb's points
    left = p['pos'][:, 0] > 0
    A = np.c_[p['pos'][left], np.ones(left.sum())]
    M = np.linalg.lstsq(A, p['uv'][left], rcond=None)[0]

    def at(x, y, z=0.0):
        u, v = np.array([x, y, z, 1.0]) @ M
        return int(v * 128), int(u * 256)
    across = [alpha[at(x, 100.0)] for x in np.arange(150.0, 1150.0, 5.0)]
    runs = sum(1 for i in range(1, len(across)) if across[i] >= 0.5 > across[i - 1]) + (across[0] >= 0.5)
    assert runs == len(TEETH)                           # the teeth, the gaps between them holes
    assert alpha[at(160.0 + 50, 450.0)] == 1.0          # the spine
    assert rgb[at(600.0, 210.0, 20.0)][2] > 0.9         # the strip lies in front of the teeth: its colour shows
    assert rgb[at(210.0, 100.0)][0] > 0.9
    shine = card.resample(np.full((8, 8, 4), 200, np.uint8))
    assert shine.dtype == np.uint8 and shine.shape[1] == 2 * shine.shape[0]


def test_a_model_of_two_materials_is_refused():
    s = _streams()
    with pytest.raises(ValueError):
        lace8.cards([s, dict(s, material='other')], [-1, 0, -1, 2], GOAL, {}, log=lambda *a: None)


def test_a_dissolving_picture_orders_its_covered_texels_above_the_reference_and_its_holes_below():
    (p,) = lace8.cards([_streams()], [-1, 0, -1, 2], GOAL, {'texture': (256, 128), 'kind': 'glow', 'dissolve': True},
                       log=lambda *a: None)
    card = lace8.card('made_up_wing')
    assert card.kind == 'glow'
    _, alpha = card.texture(np.ones((64, 64, 3), np.float32))
    lo = lace8.DISSOLVE_REF / 255.0
    covered = alpha >= lo
    assert covered.any() and (alpha[~covered] < lo).all()
    shares = np.sort((alpha[covered] - lo) / (1.0 - lo))
    assert np.allclose(shares, np.linspace(0.0, 1.0, len(shares)), atol=1e-6)    # (even: a fade's share shows that share)
    # a fade's share s shows the texels at or above lo + (1 - lo)(1 - s): the half that forms first lies nearer the root
    # (the spine's end at x 150, between the combs) than the half that forms last
    left = p['pos'][:, 0] > 0
    M = np.linalg.lstsq(np.c_[p['pos'][left], np.ones(left.sum())], p['uv'][left], rcond=None)[0]
    to_xy = np.linalg.inv(M[:2])                        # (the comb's plane z = 0: uv = (x, y) M[:2] + M[3])
    rows, cols = np.nonzero(covered)
    xy = (np.stack([(cols + 0.5) / 256, (rows + 0.5) / 128], 1) - M[3]) @ to_xy
    first = alpha[rows, cols] >= lo + (1.0 - lo) * 0.5
    assert xy[first, 0].mean() < xy[~first, 0].mean() - 100.0
    plain = lace8.cards([_streams()], [-1, 0, -1, 2], GOAL, {'texture': (256, 128)}, log=lambda *a: None)
    assert lace8.card('made_up_wing').order is None and lace8.card('made_up_wing').kind is None


def test_both_faces_keep_their_own_normals():
    (p,), _ = _cards()
    a, b, c = (p['pos'][p['tris'][:, k]] for k in range(3))
    face = np.cross(b - a, c - a)
    face /= np.linalg.norm(face, axis=1, keepdims=True)
    assert np.abs((face * p['nrm'][p['tris'][:, 0]]).sum(1)).min() > 0.99   # (no lean: the faces' own normals)


def test_a_converted_alpha_cutoff_stays_off_the_dissolve_reference():
    from ttt2char.convert import model
    assert model.clear_of_dissolve(lace8.DISSOLVE_REF) != lace8.DISSOLVE_REF
    assert abs(model.clear_of_dissolve(lace8.DISSOLVE_REF) - lace8.DISSOLVE_REF) == 1
    assert all(model.clear_of_dissolve(r) == r for r in range(256) if r != lace8.DISSOLVE_REF)
