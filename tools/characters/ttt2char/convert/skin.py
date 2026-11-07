"""Tekken 7 (or Tekken 8) skin -> TTT2 skin: a colour gain measured on the fighters both games have.

TTT2 draws a skin texture's colours much as they are; Tekken 7's skin shader (subsurface scattering, its lighting and
tone mapping) brightens and desaturates its own skin textures, which are darker and more orange: baked as they are,
an added fighter looks tanned beside TTT2's fighters on any stage. So the skin materials' baked colours are scaled
per channel by the gain that turns Tekken 7's baked faces into TTT2's face textures, measured on the fighters both
games have under the same code, of the fighter's sex (the games' female faces differ more than their male ones):
the median of their ratios (linear colour means) over the NEAREST of them in brightness (TTT2 evens skin out: a
dark Tekken 7 face gains more than a fair one, Marduk x3.3 and Lars x1.4 in red). A source with SKIN_NEAR_HUE (Tekken
8) takes them nearest in brightness and hue: the blue gains of its men run from 1.8 to 3.2 at one brightness, and a
fair man among the low ones comes out far more orange than TTT2 draws any (Victor Chevalier, who bakes as Lars does).

Written for this project from the files themselves (no third-party code).
"""
import numpy as np

from ..ttt2 import nud, nut
from ..ttt2.archive import key_of

# fighters with a face of their own in both games (Tekken 7: Character/Common/shader/.../skin/<code>/)
SHARED = {'female': ['ann', 'ask', 'jul', 'leo', 'lil', 'nin', 'xia', 'zaf'],
          'male': ['bob', 'bry', 'dra', 'edd', 'fen', 'gan', 'hei', 'hwo', 'jin', 'kaz', 'lar', 'law', 'lee', 'lei',
                   'mar', 'mig', 'pau', 'ste']}
FACE_MATERIAL = '/Game/Character/Common/shader/MaterialInstance/skin/%s/MI_CH_%s_skin_face'
# TTT2's women (a Tekken 8 fighter's skin is measured on the faces of TTT2 fighters Tekken 8 has, of its sex)
WOMEN = ('ali', 'ang', 'ann', 'ask', 'chr', 'jc', 'jul', 'jun', 'knm', 'leo', 'lil', 'mic', 'mih', 'nin', 'xia', 'zaf')
FACE_MESH = 'cha:kao_O_OBJ'         # TTT2's face mesh; its polygon with the most vertices is the skin
FEWEST = 3                          # pairs needed for a gain (else none: 1, 1, 1)
NEAREST = 5                         # the fighters whose faces are nearest in brightness give the gain
HUE_SPAN = 1.25                     # a fighter's skin keeps its own hue within this factor of theirs (green/red,
                                    # blue/red): Tekken 7's darker skins are far more orange than TTT2 draws any
LUMA = np.array([0.2126, 0.7152, 0.0722])


def _srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def ttt2_face(archives, code):
    """The linear mean colour of TTT2 fighter `code`'s face texture, or None."""
    if not archives.has(key_of(code + '.nud')) or not archives.has(key_of(code + '.nut')):
        return None
    model = nud.read(archives.read_name(code + '.nud'))
    polys = [p for m in model['meshes'] if m['name'] == FACE_MESH for p in m['polys']]
    if not polys:
        return None
    gidx = max(polys, key=lambda p: len(p['verts']))['materials'][0]['textures'][0]['id']
    found = [t for t in nut.read(archives.read_name(code + '.nut'))['textures'] if t['gidx'] == gidx]
    if not found:
        return None
    rgb = nut.decode(found[0])[..., :3].astype(np.float64) / 255.0
    return _srgb_to_linear(rgb).reshape(-1, 3).mean(0)


def tekken7_faces(paks, sex):
    """[(TTT2 code, Tekken 7 face material path)] of the fighters both games have, of that sex, whose face material
    the paks have."""
    paths = [(code, FACE_MATERIAL % (code, code)) for code in SHARED.get(sex, SHARED['female'])]
    return [(code, path) for code, path in paths if paks.find(path)]


def gain(source, archives, sex, materials, bake, own=None, log=None):
    """The per-channel gain for the skin of a fighter of `sex` whose face's mean linear colour (baked from its game)
    is `own` (None: the median over all of them). source: the fighter's (source.py: skin_faces(sex), the faces of
    fighters both games have; Tekken 7's paks as such too); materials: its game's Materials; bake: its bake_albedo
    with its textures, (effective material) -> (linear rgb, alpha). -> (gain, their face colour: the hue hue() keeps
    skin near)."""
    ratios, lumas, faces, baked = [], [], [], []
    if hasattr(source, 'skin_faces'):
        found, none = source.skin_faces(sex), source.NO_COLOURS
    else:
        found, none = tekken7_faces(source, sex), {}
    for code, path in found:
        try:
            rgb, _ = bake(materials.effective(path, none))
            theirs = ttt2_face(archives, code)
        except (KeyError, ValueError):
            continue
        if rgb is None or theirs is None:
            continue
        ours = rgb.reshape(-1, 3).mean(0)
        if (ours > 1e-3).all():
            ratios.append(theirs / ours)
            lumas.append(float(ours @ LUMA))
            faces.append(theirs)
            baked.append(ours)
    if len(ratios) < FEWEST:
        if log:
            log('  skin: too few fighters in both games to measure (%d); colours as Tekken 7 has them' % len(ratios))
        return np.ones(3), None
    ratios, faces = np.array(ratios), np.array(faces)
    if own is not None and float(own @ LUMA) > 0:
        far = np.abs(np.log(np.array(lumas)) - np.log(float(own @ LUMA)))
        if getattr(source, 'SKIN_NEAR_HUE', False) and (own > 1e-3).all():
            baked = np.array(baked)
            far = far + np.abs(np.log(baked[:, 1:] / baked[:, :1]) - np.log(own[1:] / own[:1])).sum(1)
        near = np.argsort(far)[:NEAREST]
        ratios, faces = ratios[near], faces[near]
    g = np.median(ratios, 0)
    target = np.median(faces, 0)
    if log:
        log('  skin: colour gain %.2f %.2f %.2f (from the %d fighters both games have %s)' % (
            g[0], g[1], g[2], len(ratios), 'nearest in brightness' + (' and hue' if getattr(source, 'SKIN_NEAR_HUE', False) else '')
            if own is not None else 'of that sex'))
    return g, target


def gained(rgb, g):
    """A skin texture (linear rgb) times the gain. The gain turns Tekken 7's orange skin into TTT2's paler, pinker
    skin, lifting blue most (Lidia 1.48, 2.00, 2.47): texels of other colours (the mauve painted on Lidia's lids,
    shown when they close; grey stubble) turned blue with it. So a texel takes the gain as far as it is coloured like
    skin (its red over blue against the texture's mean), the rest a grey gain lifting it as much as the skin's
    brightness."""
    g = np.asarray(g, np.float64)
    mean = rgb.reshape(-1, 3).mean(0).astype(np.float64)
    k = float((mean * g) @ LUMA / max(float(mean @ LUMA), 1e-6))

    def warmth(c):
        return (c[..., 0] - c[..., 2]) / np.maximum(c.sum(-1), 1e-6)
    w = np.clip(warmth(rgb) / max(float(warmth(mean)), 1e-3), 0, 1)[..., None]
    return np.clip(rgb * (k + w * (g - k)).astype(rgb.dtype), 0, 1)


def hue(rgb, target):
    """A skin texture (linear rgb, after the gain) with its mean's green/red and blue/red within HUE_SPAN of the
    target's (TTT2's faces): per material, as a fighter's face and its generic body textures differ."""
    if target is None:
        return rgb
    m = rgb.reshape(-1, 3).mean(0)
    if m[0] <= 1e-4:
        return rgb
    f = np.ones(3)
    for c in (1, 2):
        want = m[0] * np.clip(m[c] / m[0], target[c] / target[0] / HUE_SPAN, target[c] / target[0] * HUE_SPAN)
        f[c] = want / max(m[c], 1e-6)
    return np.clip(rgb * f.astype(rgb.dtype), 0, 1)
