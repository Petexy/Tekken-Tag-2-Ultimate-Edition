"""A summon's large thin sheets made again as a regular grid over their UV layout (a definition's prefab model 'remesh').

A torn membrane (a wing's fringed hem) is many thousand vertices; decimated to a summon's few hundred it comes out as straight
sheets whose torn outline is gone. Laid out flat in UV, the same sheet is a region of the texture: a grid over that region
(one node every step_cm on the surface) keeps its shape, and the region itself, drawn into the colour's alpha (coverage()),
cuts the outline back out texel by texel. A sheet modelled twice, back to back (its front and its back as two layers a few
millimetres apart), keeps one layer: its material is then drawn from both sides (two_sided()). Or, `mirror`, every grid
gets a back face of its own (the same nodes, the normal turned round, wound the other way): TTT2 lights a face drawn from
behind by its front's normal, where Tekken 8's two-sided materials turn it round, so a sheet seen from behind came out dark.

Positions are the source mesh's (centimetres), areas square metres. Pieces smaller than min_area_m2 stay as they are (the
decimator takes them as before)."""
import numpy as np
from PIL import Image, ImageDraw

RASTER = 1024                   # texels across UV [0, 1] the sheets are looked up in
SUPERSAMPLE = 4                 # coverage(): its alpha drawn this many times larger, then averaged (soft edges)
LAYER_GAP_CM = 2.0              # two sheets this close (median) lie back to back: one of them is dropped
LAYER_AREA = 0.2                # ... when their surfaces differ by at most this share
LAYER_SPAN_CM = 20.0            # ... and their middles by at most this
BACK_CM = 0.05                  # mirror: a back face this far behind its front (not one point with it to the decimator)

_cover = {}                     # material name -> [(uv (n, 2), triangles (m, 3))]: the source's own layout
_two_sided = set()              # materials of which a layer was dropped


def islands(n, tris):
    """The connected piece of each of n vertices (by triangles): (n,) root ids."""
    par = np.arange(n)

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for a, b, c in tris:
        ra = find(a)
        par[find(b)] = ra
        par[find(c)] = ra
    return np.array([find(i) for i in range(n)])


def raster_ids(uv, tris, R=RASTER):
    """(R, R): the index of the triangle (of tris) covering each texel, -1 none (row = v)."""
    im = Image.new('I', (R, R), -1)
    dr = ImageDraw.Draw(im)
    for k, (a, b, c) in enumerate(tris):
        dr.polygon([(float(uv[a, 0] * R), float(uv[a, 1] * R)), (float(uv[b, 0] * R), float(uv[b, 1] * R)),
                    (float(uv[c, 0] * R), float(uv[c, 1] * R))], fill=int(k))
    return np.asarray(im, np.int64)


def coverage(name, shape):
    """The alpha (shape) of material `name` drawn where its source triangles lie in UV, or None (not remeshed)."""
    if name not in _cover:
        return None
    h, w = shape
    im = Image.new('L', (w * SUPERSAMPLE, h * SUPERSAMPLE), 0)
    dr = ImageDraw.Draw(im)
    for uv, tris in _cover[name]:
        p = uv * np.array([w * SUPERSAMPLE, h * SUPERSAMPLE])
        for a, b, c in tris:
            dr.polygon([tuple(p[a]), tuple(p[b]), tuple(p[c])], fill=255)
    a = np.asarray(im, np.float32).reshape(h, SUPERSAMPLE, w, SUPERSAMPLE).mean((1, 3)) / 255.0
    return a


def two_sided(name):
    return name in _two_sided


def _bary(q, a, b, c):
    v0, v1, v2 = b - a, c - a, q - a
    d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-18:
        return np.array([1.0, 0.0, 0.0])
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return np.array([1 - v - w, v, w])


def _layers(big, inv, T, pos, area):
    """Of each two big pieces lying back to back, the second: a set."""
    dropped = set()
    verts = {k: np.unique(T[inv == k]) for k in big}
    mid = {k: pos[verts[k]].mean(0) for k in big}
    for i, k in enumerate(big):
        if k in dropped:
            continue
        pk = pos[verts[k]]
        for k2 in big[i + 1:]:
            if k2 in dropped or abs(area[k2] - area[k]) > LAYER_AREA * area[k] or \
                    np.linalg.norm(mid[k2] - mid[k]) > LAYER_SPAN_CM:
                continue
            p2 = pos[verts[k2]]
            gap = np.sqrt(((p2[::4, None, :] - pk[None, ::2, :]) ** 2).sum(-1)).min(1)
            if np.median(gap) < LAYER_GAP_CM:
                dropped.add(k2)
    return dropped


def remesh(geo, names, step_cm, min_area_m2, one_side=True, R=RASTER, log=print, mirror=False):
    """geo (tekken8/mesh.py geometry()) with its pieces of at least min_area_m2 made again as grids, a node every step_cm;
    names: each section's material (their source layout is kept for coverage(); a material that lost a layer is drawn
    from both sides). The old vertices stay (no triangle uses them)."""
    pos = np.asarray(geo['positions'], np.float64)
    nrm = np.asarray(geo['normals'], np.float64)
    tan = np.asarray(geo['tangents'], np.float64)
    uvs = np.asarray(geo['uvs'], np.float64)
    uv = uvs[:, 0] if uvs.ndim == 3 else uvs
    J = np.asarray(geo['joints'], np.int64)
    W = np.asarray(geo['weights'], np.float64)
    secs = [np.asarray(t, np.int64).reshape(-1, 3) for t in geo['triangles']]
    for si, t in enumerate(secs):
        _cover.setdefault(names[si], []).append((uv.copy(), t.copy()))
    T = np.concatenate(secs)
    sec_of = np.concatenate([np.full(len(t), i) for i, t in enumerate(secs)])
    root = islands(len(pos), T)
    ids, inv = np.unique(root[T[:, 0]], return_inverse=True)
    a3 = np.linalg.norm(np.cross(pos[T[:, 1]] - pos[T[:, 0]], pos[T[:, 2]] - pos[T[:, 0]]), axis=1) / 2
    d1, d2 = uv[T[:, 1]] - uv[T[:, 0]], uv[T[:, 2]] - uv[T[:, 0]]
    au = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / 2
    area = np.bincount(inv, a3) / 1e4
    du = step_cm / 100.0 * np.sqrt(au.sum() / max(area.sum(), 1e-12))     # (UV units per metre, the mesh's mean)
    big = [k for k in range(len(ids)) if area[k] >= min_area_m2]
    dropped = _layers(big, inv, T, pos, area) if one_side else set()
    new = {key: [] for key in ('pos', 'nrm', 'tan', 'uv', 'J', 'W')}
    new_T, new_sec = [], []
    keep = np.ones(len(T), bool)

    def add(p, n_, t_, q, j_, w_):
        for key, x in zip(('pos', 'nrm', 'tan', 'uv', 'J', 'W'), (p, n_, t_, q, j_, w_)):
            new[key].append(x)
        return len(pos) + len(new['pos']) - 1
    for k in big:
        mine = inv == k
        keep[mine] = False
        if k in dropped:
            if not mirror:
                _two_sided.add(names[int(sec_of[mine][0])])
            continue
        tk = T[mine]
        sk = int(sec_of[mine][0])
        idr = raster_ids(uv, tk, R)
        cov = idr >= 0
        vs = np.unique(tk)
        (u0, v0), (u1, v1) = uv[vs].min(0) - du, uv[vs].max(0) + du
        nu, nv = int(np.ceil((u1 - u0) / du)) + 1, int(np.ceil((v1 - v0) / du)) + 1
        # a cell is kept when any texel of the piece lies in it (a summed table of the coverage)
        S = np.zeros((R + 1, R + 1), np.int64)
        S[1:, 1:] = cov.cumsum(0).cumsum(1)
        xs = np.clip(np.round((u0 + np.arange(nu) * du) * R).astype(int), 0, R)
        ys = np.clip(np.round((v0 + np.arange(nv) * du) * R).astype(int), 0, R)
        cells = (S[ys[1:, None], xs[None, 1:]] - S[ys[:-1, None], xs[None, 1:]] - S[ys[1:, None], xs[None, :-1]]
                 + S[ys[:-1, None], xs[None, :-1]]) > 0
        need = np.zeros((nv, nu), bool)
        need[:-1, :-1] |= cells
        need[1:, :-1] |= cells
        need[:-1, 1:] |= cells
        need[1:, 1:] |= cells
        index = -np.ones((nv, nu), np.int64)
        cy, cx = np.nonzero(cov)
        for j, i in zip(*np.nonzero(need)):
            q = np.array([u0 + i * du, v0 + j * du])
            x, y = int(q[0] * R), int(q[1] * R)
            t = idr[y, x] if 0 <= x < R and 0 <= y < R else -1
            if t < 0 and len(cx):           # (off the piece: the node moves onto its nearest texel)
                m_ = int(np.argmin((cy - q[1] * R) ** 2 + (cx - q[0] * R) ** 2))
                q = np.array([(cx[m_] + 0.5) / R, (cy[m_] + 0.5) / R])
                t = idr[cy[m_], cx[m_]]
            corners = list(tk[t])
            w = np.clip(_bary(q, *uv[corners]), 0.0, 1.0)
            w = w / max(w.sum(), 1e-9)
            n_ = w @ nrm[corners]
            n_[:3] /= max(np.linalg.norm(n_[:3]), 1e-9)
            t_ = w @ tan[corners]
            t_[:3] /= max(np.linalg.norm(t_[:3]), 1e-9)
            t_[3] = tan[corners[int(np.argmax(w))], 3]
            acc = {}
            for wc, c in zip(w, corners):
                for jj, ww in zip(J[c], W[c]):
                    if ww > 0:
                        acc[int(jj)] = acc.get(int(jj), 0.0) + wc * ww
            top = sorted(acc.items(), key=lambda x: -x[1])[:J.shape[1]]
            total = sum(x[1] for x in top) or 1.0
            jr, wr = np.zeros(J.shape[1], np.int64), np.zeros(W.shape[1])
            for m_, (jj, ww) in enumerate(top):
                jr[m_], wr[m_] = jj, ww / total
            index[j, i] = add(w @ pos[corners], n_, t_, q, jr, wr)
        for j, i in zip(*np.nonzero(cells)):
            a, b, c, d_ = index[j, i], index[j, i + 1], index[j + 1, i + 1], index[j + 1, i]
            new_T += [(a, b, c), (a, c, d_)]
            new_sec += [sk, sk]
        log('  remesh: piece %d (%s) %.3f m2: %d cells, %d nodes' % (k, names[sk], area[k], cells.sum(), need.sum()))
    if dropped:
        log('  remesh: %d pieces lying behind another left out (%s: %s)' % (
            len(dropped), 'each grid given a back face' if mirror else 'drawn from both sides',
            ', '.join(sorted({names[int(sec_of[inv == k][0])] for k in dropped}))))
    n0 = len(pos)
    P = np.r_[pos, np.reshape(new['pos'], (-1, 3))]
    N = np.r_[nrm, np.reshape(new['nrm'], (-1, nrm.shape[1]))]
    NT = np.reshape(np.array(new_T, np.int64), (-1, 3))
    if len(NT):                         # (wound as the source: its faces against their vertex normals)
        def facing(P_, N_, t):
            f = np.cross(P_[t[:, 1]] - P_[t[:, 0]], P_[t[:, 2]] - P_[t[:, 0]])
            return (f * N_[t][:, :, :3].mean(1)).sum(1)
        flip = np.sign(facing(P, N, NT)) != np.sign(facing(pos, nrm, T).mean())
        NT[flip] = NT[flip][:, [0, 2, 1]]
    if mirror and len(NT):              # (the back faces: their own nodes, normal round, the tangent frame's sign too)
        m0 = len(new['pos'])
        for key in ('tan', 'uv', 'J', 'W'):
            new[key] += new[key][:m0]
        for p_, x in zip(new['pos'][:m0], new['nrm'][:m0]):
            y = np.array(x, np.float64)
            y[:3] = -y[:3]
            new['nrm'].append(y)
            new['pos'].append(np.asarray(p_, np.float64) + BACK_CM * y[:3])
        for i_ in range(m0, 2 * m0):
            new['tan'][i_] = np.array(new['tan'][i_], np.float64)
            new['tan'][i_][3] = -new['tan'][i_][3]
        NT = np.r_[NT, NT[:, [0, 2, 1]] + m0]
        new_sec = new_sec + new_sec
        P = np.r_[pos, np.reshape(new['pos'], (-1, 3))]
        N = np.r_[nrm, np.reshape(new['nrm'], (-1, nrm.shape[1]))]
    U = np.r_[uv, np.reshape(new['uv'], (-1, 2))]
    ns = np.array(new_sec, np.int64)
    out = dict(geo)
    out['positions'] = P.astype(np.float32)
    out['normals'] = N.astype(np.asarray(geo['normals']).dtype)
    out['tangents'] = np.r_[tan, np.reshape(new['tan'], (-1, 4))].astype(np.asarray(geo['tangents']).dtype)
    out['uvs'] = (np.repeat(U[:, None, :], uvs.shape[1], 1) if uvs.ndim == 3 else U).astype(np.asarray(geo['uvs']).dtype)
    out['joints'] = np.r_[J, np.reshape(new['J'], (-1, J.shape[1]))].astype(np.asarray(geo['joints']).dtype)
    out['weights'] = np.r_[W, np.reshape(new['W'], (-1, W.shape[1]))].astype(np.asarray(geo['weights']).dtype)
    out['triangles'] = [np.r_[secs[i][keep[sec_of == i]], NT[ns == i]] for i in range(len(secs))]
    log('  remesh: %d vertices in %d pieces made again as %d (step %.0f cm)' % (
        len(np.unique(T[~keep])), len(big), len(P) - n0, step_cm))
    return out
