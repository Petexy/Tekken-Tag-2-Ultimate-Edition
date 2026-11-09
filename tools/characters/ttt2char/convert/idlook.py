"""A Tekken 8 costume material's IDs brought to a definition's colours (TEKKEN8['id_look']).

Tekken 8 draws some of a costume's IDs far from what its colour formula bakes (tekken8/bake.py bake_costume): a pale
shirt over a dark detail texture comes out near black, a red leather a dull brown, where its own renders show them
white and red (its lights, sheen and tone curve; TTT2's lights a texture as it is). A definition names, per material,
per ID (4 x channel + level, as the ID map's IDnn), the linear mean colour those texels take, and optionally how much of
their shading they keep: {material: {id: (r, g, b) or (r, g, b, contrast)}}. Each texel keeps its share of the ID's
mean luma raised to `contrast` (1: a plain gain per channel; 0.5: its folds and stitches half as deep), blended in by the
ID map's ramp as the colours are (a later channel on top where it covers). Other materials and IDs stay as baked.
"""
import numpy as np

from ..tekken8 import bake as bake8

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)
CORE = 0.5                  # the texels an ID's mean is taken over: its ramp at least this (not its blended edges)


def apply(rgb, eff, textures, looks):
    """rgb (H, W, 3) linear, a costume material's bake; eff its effective parameters; looks {id: (r, g, b[, contrast])}
    -> rgb with those IDs' texels at their looks' means (the module notes). Without an ID map, rgb as it is."""
    t, v = eff['textures'], eff['vectors']
    split = [int(round(v.get('SplitNumberPerChannel', {}).get(k, 0.0))) for k in 'rgba']
    if not looks or not textures.exists(t.get('ID_Map')) or not any(n > 0 for n in split):
        return rgb
    shape = rgb.shape[:2]
    idmap = bake8._resize(textures.image(t['ID_Map'], bake8.ID_MAP_SIZE)[0], shape, nearest=True)
    return _apply(rgb, idmap, split, looks)


def _apply(rgb, idmap, split, looks):
    """apply() on an ID map already at rgb's size (H, W, 4) uint8 and the material's SplitNumberPerChannel."""
    rgb = np.asarray(rgb, np.float32)
    luma = rgb @ LUMA
    levels = [bake8.id_levels(idmap[..., ch], split[ch]) if split[ch] > 0 else None for ch in range(4)]
    gain = np.ones(rgb.shape, np.float32)
    for ch in range(4):
        if levels[ch] is None:
            continue
        k, mask = levels[ch]
        layer = np.ones(rgb.shape, np.float32)
        for j in range(1, min(split[ch], bake8.IDS_PER_CHANNEL) + 1):
            look = looks.get(bake8.IDS_PER_CHANNEL * ch + j)
            if look is None:
                continue
            shown = np.where(k == j, mask, 0.0)          # (how much of a texel this ID is: later channels lie on top)
            for later in levels[ch + 1:]:
                if later is not None:
                    shown = shown * (1.0 - np.where(later[0] > 0, later[1], 0.0))
            core = shown >= CORE
            if not core.any():
                continue
            target = np.asarray(look[:3], np.float32)
            contrast = float(look[3]) if len(look) > 3 else 1.0
            mean = np.maximum(rgb[core].mean(0), 1e-6)
            mean_luma = max(float(luma[core].mean()), 1e-6)
            share = np.power(np.maximum(luma, 1e-6) / mean_luma, contrast - 1.0)[..., None]
            on = k == j
            layer[on] = ((target / mean) * share)[on]
        gain = gain + np.where(k > 0, mask, 0.0).astype(np.float32)[..., None] * (layer - gain)
    return np.clip(rgb * gain, 0, 1).astype(np.float32)
