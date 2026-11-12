"""Skin the costume shades (a Tekken 8 definition's TEKKEN8['skin_occlusion'], off by default).

Tekken 8 shadows what a costume covers in part: an open collar's chest, the neck under the chin. TTT2 draws no shadow
on a fighter, and its light comes from above, so skin that faces up out of a collar (Clive's chest and neck) comes out
lit far brighter and more orange than his face beside it, where Tekken 8 shows them in one tone, the chest in shade.
The textures are not the cause: his chest's and face's colours match where they meet; the same skin, lit unshaded, is.

mark() measures, on the model as loaded (bind pose), how open each vertex of the named skin materials is: the share of
the directions it faces (cosine weighted) along which nothing of the named parts lies over it (depth maps along DIRECTIONS
directions, cells CELL wide; the point lifted LIFT off its surface and EPS of slack, so a surface does not hide itself).
Each vertex's colours are then scaled by (openness / open) ^ power (at most open counts) x (1 - up x how far its normal
faces up), and apply() scales a material's texels so, through its UVs. The second term is what openness alone does not
tell: TTT2's light comes from high up, so a chest facing up out of a collar is lit like the top of a nose, several times
what the neck beside it (facing forward, as open) gets; in Tekken 8 the head and hood shade it.
spec: {'materials': skin materials to darken, 'parts': the parts that shade them, 'skip': materials of those parts that
do not (lashes, brows), 'open': openness that counts as unshaded, 'power': how strongly the rest darkens, 'up': how much
skin facing straight up loses (0: nothing), 'keep': joints whose skin (with their descendants', by its skinning weight)
stays as it is: a face, which TTT2 lights as it lights every face}.

Written for this project (no third-party code).
"""
import numpy as np

DIRECTIONS = 160        # directions over the sphere (a Fibonacci spiral)
CELL = 3.0              # mm: the depth maps' cells ..
STEP = 3.0              # .. and how far apart the shading triangles are sampled
LIFT = 2.0              # mm: the shaded point lifted off its surface along its normal ..
EPS = 4.0               # .. and this much nearer still counts as nothing over it
FILL = 8                # texels: how far a map's values spread past its triangles' UVs (mips, filtering)


def _directions(n=DIRECTIONS):
    i = np.arange(n) + 0.5
    phi = np.arccos(1.0 - 2.0 * i / n)
    theta = np.pi * (1.0 + 5.0 ** 0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi), np.cos(phi), np.sin(theta) * np.sin(phi)], 1)


def _points(corners, step=STEP):
    """Points on the triangles (t, 3, 3), at most `step` apart -> (m, 3)."""
    longest = np.linalg.norm(corners[:, [1, 2, 0]] - corners, axis=2).max(1)
    rows = np.clip(np.ceil(longest / step), 1, 64).astype(np.int64)
    out = []
    for n in np.unique(rows):
        which = np.nonzero(rows == n)[0]
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
        keep = i + j <= n
        w = np.stack([n - i[keep] - j[keep], i[keep], j[keep]], 1) / float(n)
        out.append(np.einsum('tcx,mc->tmx', corners[which], w).reshape(-1, 3))
    return np.concatenate(out) if out else np.zeros((0, 3))


def openness(points, normals, cover):
    """How open each point (n, 3) with its normal (n, 3) is under the surface points `cover` (m, 3): the cosine-weighted share
    of the directions it faces along which no cover point's depth map cell lies more than EPS nearer -> (n,) in 0..1."""
    normals = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    lifted = points + normals * LIFT
    seen, total = np.zeros(len(points)), np.zeros(len(points))
    for d in _directions():
        face = np.clip(normals @ d, 0.0, None)
        if not face.any():
            continue
        up = np.array([0.0, 0.0, 1.0]) if abs(d[1]) > 0.9 else np.array([0.0, 1.0, 0.0])
        x = np.cross(up, d)
        x /= np.linalg.norm(x)
        y = np.cross(d, x)
        cx, cy = np.floor(cover @ x / CELL).astype(np.int64), np.floor(cover @ y / CELL).astype(np.int64)
        ox, oy = cx.min(), cy.min()
        w, h = int(cx.max() - ox + 1), int(cy.max() - oy + 1)
        top = np.full(w * h, -np.inf)
        np.maximum.at(top, (cy - oy) * w + (cx - ox), cover @ d)
        qx = np.floor(lifted @ x / CELL).astype(np.int64) - ox
        qy = np.floor(lifted @ y / CELL).astype(np.int64) - oy
        inside = (qx >= 0) & (qx < w) & (qy >= 0) & (qy < h)
        over = np.full(len(points), -np.inf)
        over[inside] = top[qy[inside] * w + qx[inside]]
        seen += (lifted @ d >= over - EPS) * face
        total += face
    return seen / np.maximum(total, 1e-12)


def mark(k, spec, log=print):
    """Model dict k (bind pose, its prims sharing one pos/nrm/uv) -> {material: {'tris', 'uv', 'ao' (each vertex's
    openness), 'scale' (its colours' scale)}} for the materials spec['materials'] (the module notes)."""
    prims = k['prims']
    shade = [p for p in prims if p['part'] in spec['parts'] and p['material'] not in set(spec.get('skip', ()))]
    skins = [p for p in prims if p['material'] in set(spec['materials'])]
    if not shade or not skins:
        return {}
    pos, nrm = prims[0]['pos'].astype(np.float64), prims[0]['nrm'].astype(np.float64)
    uv = np.asarray(prims[0]['uv'], np.float64)
    uv = uv if uv.ndim == 2 else uv[:, 0]
    cover = _points(pos[np.concatenate([p['tris'] for p in shade])])
    if not len(cover):
        return {}
    used = np.unique(np.concatenate([p['tris'].reshape(-1) for p in skins]))
    ao = np.ones(len(pos), np.float32)
    ao[used] = openness(pos[used], nrm[used], cover)
    scale = np.power(np.clip(ao / max(float(spec.get('open', 0.9)), 1e-6), 0.0, 1.0), float(spec.get('power', 1.0)))
    if spec.get('up'):
        upward = nrm[:, 1] / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
        scale = scale * (1.0 - float(spec['up']) * np.clip(upward, 0.0, 1.0))
    if spec.get('keep'):
        kept = _kept(k, spec['keep'])
        scale += (1.0 - scale) * kept
    out = {}
    for name in spec['materials']:
        tris = [p['tris'] for p in skins if p['material'] == name]
        if tris:
            tris = np.concatenate(tris)
            out[name] = dict(tris=tris, uv=uv, ao=ao, scale=scale.astype(np.float32))
            v = np.unique(tris)
            log('  skin occlusion: %s %d vertices, openness mean %.2f (10%% under %.2f), colours x %.2f on average' % (
                name, len(v), float(ao[v].mean()), float(np.percentile(ao[v], 10)), float(scale[v].mean())))
    return out


def _kept(k, roots):
    """Each vertex's skinning weight on the joints `roots` and their descendants (k['bones'] names, parents) -> (n,)."""
    names, parents = list(k['bones']['names']), list(k['bones']['parents'])
    keep = {i for i, n in enumerate(names) if n in set(roots)}
    grown = True
    while grown:
        more = {i for i, p in enumerate(parents) if p in keep and i not in keep}
        keep |= more
        grown = bool(more)
    s0 = k['prims'][0]
    joints, weights = np.asarray(s0['joints']), np.asarray(s0['weights'], np.float64)
    return np.clip((weights * np.isin(joints, sorted(keep))).sum(1), 0.0, 1.0).astype(np.float32)


def scale_map(entry, shape, key='scale'):
    """A per-vertex value of a mark() entry (its colours' scale, or 'ao') through its UVs at a texture's (h, w) -> (h, w)
    float32; texels no triangle holds take the nearest held one's within FILL texels, the rest 1."""
    h, w = shape
    total, count = np.zeros((h, w), np.float64), np.zeros((h, w), np.float64)
    ao, uv = entry[key], entry['uv']
    for tri in entry['tris']:
        q = uv[tri]
        q = q - np.floor(q.min(0))                   # (a triangle kept whole across a tile's edge)
        px, py = q[:, 0] * w - 0.5, q[:, 1] * h - 0.5
        x0, x1 = int(np.floor(px.min())), int(np.ceil(px.max()))
        y0, y1 = int(np.floor(py.min())), int(np.ceil(py.max()))
        den = (py[1] - py[2]) * (px[0] - px[2]) + (px[2] - px[1]) * (py[0] - py[2])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        l0 = ((py[1] - py[2]) * (gx - px[2]) + (px[2] - px[1]) * (gy - py[2])) / den
        l1 = ((py[2] - py[0]) * (gx - px[2]) + (px[0] - px[2]) * (gy - py[2])) / den
        l2 = 1.0 - l0 - l1
        m = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not m.any():
            continue
        v = l0[m] * ao[tri[0]] + l1[m] * ao[tri[1]] + l2[m] * ao[tri[2]]
        ys, xs = gy[m] % h, gx[m] % w
        np.add.at(total, (ys, xs), v)
        np.add.at(count, (ys, xs), 1.0)
    held = count > 0
    value = np.where(held, total / np.maximum(count, 1.0), 1.0)
    for _ in range(FILL):
        if held.all():
            break
        s, n = np.zeros((h, w)), np.zeros((h, w))
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s += np.roll(np.where(held, value, 0.0), (dy, dx), (0, 1))
            n += np.roll(held, (dy, dx), (0, 1))
        grow = ~held & (n > 0)
        value[grow] = s[grow] / n[grow]
        held = held | grow
    return value.astype(np.float32)


def apply(rgb, entry):
    """A skin material's colours (H, W, 3, linear) scaled as mark() found its surface shaded (the module notes)."""
    scale = scale_map(entry, rgb.shape[:2])
    return (np.asarray(rgb, np.float32) * scale[..., None]).astype(np.float32)
