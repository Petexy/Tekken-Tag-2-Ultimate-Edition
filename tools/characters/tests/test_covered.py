"""convert/covered.py: surfaces under a costume's own plates, on made-up boxes."""
import numpy as np

from ttt2char.convert import covered


def box(lo, hi):
    """A closed box's corners (t, 3, 3), its faces wound outwards."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = np.array([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                  (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], np.float64)
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)]
    return v[np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))])]


def test_a_box_inside_a_box_is_hidden_and_the_outer_one_shows():
    inner, outer = box((-20, -20, -20), (20, 20, 20)), box((-21, -21, -21), (21, 21, 21))
    corners = np.concatenate([inner, outer])
    out = covered.hidden(corners, np.ones(len(corners)))
    assert out[:12].all()
    assert not out[12:].any()


def test_a_plate_hides_only_what_it_covers():
    shell = box((-50, -50, -50), (50, 50, 50))
    plate = box((-30, -30, 50.5), (30, 30, 52))
    corners = np.concatenate([shell, plate])
    out = covered.hidden(corners, np.ones(len(corners)))
    assert not out[:12].any()                    # (the shell shows round the plate)
    little = box((-30, -30, 44), (30, 30, 48))   # a piece just under the face of the shell, inside: hidden
    corners = np.concatenate([shell, little])
    assert covered.hidden(corners, np.ones(len(corners)))[12:].all()


def test_a_slope_does_not_hide_itself():
    a = np.array([[(0, 0, 0), (100, 0, 60), (0, 100, 0)], [(100, 0, 60), (100, 100, 60), (0, 100, 0)]], np.float64)
    assert not covered.hidden(a, np.ones(2)).any()


def _model(corners, uv):
    n = len(corners) * 3
    pos = corners.reshape(-1, 3).astype(np.float32)
    v0, v1 = pos[1::3] - pos[0::3], pos[2::3] - pos[0::3]
    nrm = np.repeat(np.cross(v0, v1), 3, axis=0)
    prim = dict(pos=pos, nrm=nrm, uv=uv, joints=np.zeros((n, 1), np.int64), weights=np.ones((n, 1), np.float32),
                tris=np.arange(n).reshape(-1, 3), part='body', material='m')
    return dict(prims=[prim])


def _bend(n):
    """A test pose moving everything alike: the same as the bind pose."""
    return [np.eye(4)[None]]


def test_mark_gives_what_stays_hidden():
    corners = np.concatenate([box((-20, -20, -20), (20, 20, 20)), box((-21, -21, -21), (21, 21, 21))])
    k = _model(corners, np.zeros((len(corners) * 3, 2)))
    out, maps = covered.mark(k, dict(parts=('body',)), _bend(1), lambda name: np.ones((4, 4), np.float32), log=lambda *_: None)
    assert out['free'][:36].all() and not out['free'][36:].any()
    assert maps['m'].any()
    assert len(out['prims'][0]['tris']) == 24     # (nothing cut yet)


def test_moving_pieces_stay():
    corners = np.concatenate([box((-20, -20, -20), (20, 20, 20)), box((-21, -21, -21), (21, 21, 21))])
    k = _model(corners, np.zeros((len(corners) * 3, 2)))
    k['prims'][0]['material'] = 'cape'
    out, maps = covered.mark(k, dict(parts=('body',), moving=('cape',)), _bend(1), lambda name: np.ones((4, 4), np.float32),
                             log=lambda *_: None)
    assert out is k and maps == {}


def test_black_goes_even_if_bending_shows_it():
    # (hidden in the bind pose; the test pose moves the inner box out)
    inner, outer = box((-20, -20, -20), (20, 20, 20)), box((-21, -21, -21), (21, 21, 21))
    corners = np.concatenate([inner, outer])
    n = len(corners) * 3
    k = _model(corners, np.zeros((n, 2)))
    joints = np.zeros((n, 1), np.int64)
    joints[:36] = 1
    k['prims'][0]['joints'] = joints
    pose = np.stack([np.eye(4), np.eye(4)])
    pose[1, :3, 3] = (300, 0, 0)
    light = np.ones((4, 4), np.float32)
    kept, _ = covered.mark(k, dict(parts=('body',)), [pose], lambda name: light, log=lambda *_: None)
    assert not kept['free'].any()
    gone, _ = covered.mark(k, dict(parts=('body',)), [pose], lambda name: light * 0, log=lambda *_: None)
    assert gone['free'][:36].all() and not gone['free'][36:].any()


def test_trim_takes_triangles_with_all_corners_free():
    tris = np.array([[0, 1, 2], [1, 2, 3], [3, 4, 5]])
    pos, nrm = np.zeros((6, 3), np.float32), np.tile(np.array((0.0, 0.0, 1.0), np.float32), (6, 1))
    out = dict(prims=[dict(tris=tris, part='body', pos=pos, nrm=nrm)], source=np.array([10, 11, 12, 13, 14, 15]), free=None)
    free = np.zeros(16, bool)
    free[[10, 11, 12, 13]] = True                 # (the first two triangles' corners)
    done = covered.trim(out, free)
    assert done['prims'][0]['tris'].tolist() == [[3, 4, 5]]
    assert 'free' not in done
    assert done['prims'][0]['pos'][3, 2] == -covered.SINK and done['prims'][0]['pos'][4, 2] == 0   # (a free vertex left: down)


def test_paint_takes_the_black_only_from_what_no_one_sees():
    rgb = np.full((8, 8, 3), 0.5, np.float32)
    rgb[2, 2] = 0.0                              # hidden and black: painted
    rgb[5, 5] = 0.0                              # shown and black: kept
    rgb[6, 2] = 0.3                              # hidden, not dark: kept
    shown = np.ones((8, 8), bool)
    shown[2, 2] = shown[6, 2] = False
    out = covered.paint(rgb, shown)
    assert out[2, 2, 0] == 0.5 and out[5, 5, 0] == 0.0 and out[6, 2, 0] == np.float32(0.3)
    assert rgb[2, 2, 0] == 0.0


def test_trim_sinks_what_the_bind_pose_does_not_show():
    tris = np.array([[0, 1, 2], [3, 4, 5]])
    pos = np.zeros((6, 3), np.float32)
    nrm = np.zeros((6, 4), np.float32)
    nrm[:, 2] = 1.0
    out = dict(prims=[dict(tris=tris, part='body', pos=pos, nrm=nrm)], source=np.arange(6), free=None)
    free, under = np.zeros(6, bool), np.zeros(6, bool)
    under[[0, 1, 2]] = True
    done = covered.trim(out, free, under)
    assert (done['prims'][0]['pos'][:3, 2] == -covered.UNDER).all() and (done['prims'][0]['pos'][3:, 2] == 0).all()
