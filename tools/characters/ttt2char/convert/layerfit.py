"""A 2P colour layer fitted texel by texel (a definition's TEKKEN8['layer_blend']) and its values carried into its holes
(TEKKEN8['layer_bleed']).

colours.fit puts each texel of a layer in one of two groups, its colour a shade of that group's. A worn cloth's small pale
specks, between the two groups' colours (a red mantle's pale grey-pink wear, its lining ochre), go to the group nearer in
both players' colours together, and 2P draws them in the other group's colour: pale yellow flecks over the red. Here each
texel takes its own blend of the two groups (the mask's B, which the game blends the two palette colours by) and its own
shade, both fitted to both players' colours; a texel either player's colour misses by more than max_error is left out.

A layer's shade and B are 0 where it is left out; brought to the texture's size (and halved to fit the budget) the texels
round its holes mix that black in, and draw dark rims. bleed() carries the nearest values in first.
"""
import numpy as np

from . import colours

BLENDS = 33                     # fit(): the blends tried for each texel (B = 0, 1/32 .. 1)
BLEED_PASSES = 16               # bleed(): how far (texels) the values go into a hole


def _shades(x, p):
    """The least-squares shade (colour = 2 * shade * p) of each row of x (n, 6) for the colour p (6,), clipped."""
    return np.clip((x * p).sum(1) / max(2.0 * (p * p).sum(), 1e-6), 0.0, 1.0)


def fit(c1, c2, palette, max_error=colours.MAX_ERROR, lift=None):
    """colours.fit's result (alpha, shade, b, groups) with each texel's b its own blend of the two groups (0..1).
    c1, c2 (H, W, 3) in 0..1; palette.place(rgb) -> its palette position; lift(group, colour, texels) as colours.fit's.
    None when nothing changes."""
    changed = np.abs(c1 - c2).max(-1) > colours.CHANGED
    if changed.mean() < 0.002:
        return None
    blends = np.linspace(0.0, 1.0, BLENDS)
    for _ in range(colours.PASSES):
        x = np.concatenate([c1[changed], c2[changed]], 1)
        lab = colours._kmeans2(x) if len(x) > 16 else np.zeros(len(x), np.int64)
        q = [x[lab == k].mean(0) if (lab == k).any() else x.mean(0) for k in range(2)]
        best, shade, b = np.full(len(x), np.inf), np.zeros(len(x)), np.zeros(len(x))
        for v in blends:
            p = np.clip(q[0] * (1.0 - v) + q[1] * v, 0.0, 1.0)
            s = _shades(x, p)
            e = ((np.clip(2.0 * s[:, None] * p, 0.0, 1.0) - x) ** 2).sum(1)
            better = e < best
            best[better], shade[better], b[better] = e[better], s[better], v
        p = q[0][None] * (1.0 - b[:, None]) + q[1][None] * b[:, None]
        missed = (np.abs(np.clip(2.0 * shade[:, None] * p, 0.0, 1.0) - x) > max_error).any(1)
        if not missed.any():
            break
        kept = changed.copy()
        kept[changed] = ~missed
        if kept.mean() < 0.002:
            return None
        changed, shade, b, lab = kept, shade[~missed], b[~missed], lab[~missed]
    means = [(np.clip(g[:3], 0, 1), np.clip(g[3:], 0, 1)) for g in q]
    if lift is not None:
        where = [np.zeros(changed.shape, bool) for _ in means]
        for k, texels in enumerate(where):
            texels[changed] = lab == k
        means = [(lift(k, m[0], where[k]), lift(k, m[1], where[k])) for k, m in enumerate(means)]
    groups = [(palette.place(m[0]), m[0], palette.place(m[1]), m[1]) for m in means]
    out_shade = np.zeros(changed.shape)
    out_shade[changed] = shade
    out_b = np.zeros(changed.shape)
    out_b[changed] = b
    return dict(alpha=changed.astype(np.float64), shade=out_shade, b=out_b, groups=groups)


def bleed(inside, values, passes=BLEED_PASSES):
    """values (H, W) with the texels outside `inside` (H, W) bool given their filled neighbours' mean, ring by ring
    (passes rings); the rest keep theirs."""
    x = np.array(values, np.float64)
    filled = np.array(inside, bool)
    h, w = filled.shape
    for _ in range(passes):
        if filled.all() or not filled.any():
            break
        total, count = np.zeros((h, w)), np.zeros((h, w))
        f = filled.astype(np.float64)
        xf = x * f
        for dst, src in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                         ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                         ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                         ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
            total[dst] += xf[src]
            count[dst] += f[src]
        new = ~filled & (count > 0)
        x[new] = total[new] / count[new]
        filled |= new
    return x
