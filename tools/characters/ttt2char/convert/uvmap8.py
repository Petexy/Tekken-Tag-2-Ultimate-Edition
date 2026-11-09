"""A summon's second UV layout seen from its first, for bakes of what Tekken 8 lays along the second (prefabs8.bake).

Tekken 8's summon materials read some of their textures through the mesh's second UV set (UV1): a feather's colour
along the feather, a fist's glow colour and the lines that light it. TTT2's model keeps one UV set (UV0), so a bake
samples those textures where each texel of the UV0 texture lies in UV1: the triangle that covers the texel in UV0 and
its barycentric weights there give the texel's UV1 point. A texel no triangle covers takes its nearest covered
neighbour's point (the texture's filtering and smaller mip levels read past the islands' edges), up to FILL texels away.

register() keeps a material's layouts as the prefab's model is built (before its materials are baked); uv1_of() gives
a texture's map, None for a material registered without a second set."""
import numpy as np
from PIL import Image, ImageDraw

FILL = 8                        # texels round the islands given their nearest covered neighbour's UV1 point
SHARED = 0.2                    # a layout more of whose covered texels than this lie under pieces with UV1 points APART
APART = 0.02                    # shares its texels between pieces each with a colour of its own along UV1 (feather cards
                                # on one feather's picture): no one UV1 point per texel, uv1_of gives None (bake: the mean)

_maps = {}                      # material name -> [(uv0 (n, 2), uv1 (n, 2), triangles (m, 3))]
_made = {}                      # (name, shape) -> uv1_of's map


def register(name, uvs, tris):
    """Material `name`'s triangles tris (m, 3) over vertices with UV sets uvs (n, sets, 2): kept when it has two."""
    uvs = np.asarray(uvs, np.float64)
    if uvs.ndim != 3 or uvs.shape[1] < 2:
        return
    tris = np.asarray(tris, np.int64)
    if len(tris):
        _maps.setdefault(name, []).append((uvs[:, 0], uvs[:, 1], tris))
        _made.clear()


def known(name):
    return name in _maps


def _raster(uv, tris, w, h):
    """(h, w): the triangle of tris covering each texel's middle, -1 none (row = v)."""
    im = Image.new('I', (w, h), -1)
    dr = ImageDraw.Draw(im)
    for k, (a, b, c) in enumerate(tris):
        dr.polygon([(float(uv[i, 0] * w - 0.5), float(uv[i, 1] * h - 0.5)) for i in (a, b, c)], fill=int(k))
    return np.asarray(im, np.int64)


def _fill(points, have, steps=FILL):
    """Uncovered texels take a covered 4-neighbour's point, step by step (up to `steps` texels away)."""
    points, have = points.copy(), have.copy()
    for _ in range(steps):
        if have.all():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src_have = np.roll(have, (dy, dx), (0, 1))
            take = src_have & ~have
            if take.any():
                points[take] = np.roll(points, (dy, dx), (0, 1))[take]
                have = have | take
    return points, have


def _points(layouts, h, w):
    """(points (h, w, 2), covered (h, w)): the UV1 point of each texel's middle, the last triangle drawn over it."""
    ys, xs = np.mgrid[0:h, 0:w]
    q = np.stack([(xs + 0.5) / w, (ys + 0.5) / h], -1)
    points = np.zeros((h, w, 2), np.float64)
    have = np.zeros((h, w), bool)
    for uv0, uv1, tris in layouts:
        ids = _raster(uv0, tris, w, h)
        at = ids >= 0
        t = tris[ids[at]]
        a, b, c = uv0[t[:, 0]], uv0[t[:, 1]], uv0[t[:, 2]]
        p = q[at]
        v0, v1, v2 = b - a, c - a, p - a
        d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
        d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
        den = d00 * d11 - d01 * d01
        ok = np.abs(den) > 1e-18
        den = np.where(ok, den, 1.0)
        l1 = np.where(ok, (d11 * d20 - d01 * d21) / den, 0.0)
        l2 = np.where(ok, (d00 * d21 - d01 * d20) / den, 0.0)
        l0 = 1.0 - l1 - l2
        points[at] = l0[:, None] * uv1[t[:, 0]] + l1[:, None] * uv1[t[:, 1]] + l2[:, None] * uv1[t[:, 2]]
        have |= at
    return points, have


def uv1_of(name, shape):
    """(h, w, 2): each texel's UV1 point in material `name`'s UV0 texture of `shape` (h, w), or None (not known, or
    its pieces share their texels with points of their own: SHARED). Texels no triangle reaches keep the material's
    mean UV1 point."""
    if name not in _maps:
        return None
    if (name, tuple(shape)) in _made:
        return _made[name, tuple(shape)]
    h, w = shape
    points, have = _points(_maps[name], h, w)
    # (drawn again in the other order: where pieces lie on the same texels, the other one's point; a sheet modelled
    # twice back to back has the same points, feather cards on one feather's picture each their own)
    other, _ = _points([(uv0, uv1, tris[::-1]) for uv0, uv1, tris in _maps[name][::-1]], h, w)
    apart = np.abs(points - other).max(-1) > APART
    if have.any() and float(apart[have].mean()) > SHARED:
        _made[name, tuple(shape)] = None
        return None
    mean = np.concatenate([uv1 for _, uv1, _ in _maps[name]]).mean(0)
    points, have = _fill(points, have)
    points[~have] = mean
    _made[name, tuple(shape)] = points
    return points


def sample(img, uv):
    """Bilinear samples (..., C) of image img (H, W, C) at UV points uv (..., 2) (row = v), wrapping (tiles repeat)."""
    img = np.asarray(img, np.float32)
    H, W = img.shape[:2]
    x = np.asarray(uv[..., 0], np.float64) * W - 0.5
    y = np.asarray(uv[..., 1], np.float64) * H - 0.5
    x0, y0 = np.floor(x), np.floor(y)
    fx, fy = (x - x0)[..., None].astype(np.float32), (y - y0)[..., None].astype(np.float32)
    x0, y0 = x0.astype(np.int64) % W, y0.astype(np.int64) % H
    x1, y1 = (x0 + 1) % W, (y0 + 1) % H
    top = img[y0, x0] * (1 - fx) + img[y0, x1] * fx
    bottom = img[y1, x0] * (1 - fx) + img[y1, x1] * fx
    return top * (1 - fy) + bottom * fy


def texel_uv(shape):
    """(h, w, 2): the UV0 point of each texel's middle of a texture of `shape` (row = v)."""
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w]
    return np.stack([(xs + 0.5) / w, (ys + 0.5) / h], -1)
