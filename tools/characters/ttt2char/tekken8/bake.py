"""Tekken 8 materials -> one albedo texture each (and what TTT2 template they become): the Tekken 8 counterparts of
convert/model.py's bake_albedo and classify.

Costume materials (base M_CH_ITM_id_RGBA, _ANS ...; instances MI_CH_ITM_*): the formula of the base material's own
compiled base-pass pixel shader (its Direct3D 11 shader in the game's shader library, the slice behind the base
colour output):
    a = BaseColor_A ** Degamma, b = BaseColor_B ** Degamma     (grey detail textures, sRGB -> linear first)
    D = blend(a, b, AB_BlendMode) ** Gamma                     (12, the default: Unreal's overlay keyed on a)
    L = dot(D, (0.299, 0.587, 0.114))
    ID map (B8G8R8A8, one mip; sampled nearest): channel c of R G B A holds N = SplitNumberPerChannel[c] levels; level
        k = 1..N covers v * 255 in [255 (k - 1) / N, 255 k / N] with mask (v * 255 - lo) / (hi - lo); ID 4c + k
    per channel: C = prod_k lerp(1, ID colour, mask_k) (one level at most covers a texel: id_levels);
        layer = max(1, 1 + 20 (max(C) - 0.9)) L C
    X = the R layer, then lerp(X, layer, saturate(sum_k mask_k)) for G, B, A (a later channel lies on top);
    IDnn_DontColorOP (layered the same way) lerps back to D; texels no ID covers stay D
    (the pattern layer, Saturation and the costume darkening of another constant buffer are 0 in default costumes)
  The colours per ID come from the costume (material.Materials.costume_colours), else from the material.
  Masked costume materials (a BlendMode override of Masked): alpha = OBD.R, cut at the opacity mask clip value.
  Sheer cloth (the subsurface stockings, MI_CH_ITM_SS_*: ShadingModel Subsurface): the game shows the leg through it
  where it faces the camera (towards its SSS_InSideColor) and darkens it towards the edges (SSS_OutSideColor); baked
  opaque it would be dark brown, so a flat albedo takes SHEER of the way from the cloth's colour to the leg skin's
  (SheerSkinColor, the mean of the costume's body skin: costume.py; SSS_InSideColor without one). Checked on the
  game's own 1P and 2P pictures of Reina: stockings 130-147, 107-115, 100-103 (sRGB, lit) on the thighs, 87 69 62 on
  the shin in shadow; without the pictures' lighting (~1.1 in linear, as the costume colours measure) about 136 106 96
  against 133 93 80 baked: as bright, a little warmer (the game's sheen greys it).
Skin (M_CH_skin*): tx01_BaseColor (real colours; the body parts' generic T_CH_femalebody_* textures) x TintColor.
    The scalp mask (tx11_ScalpMask, face UV layout) paints R with ScalpColor_Eyebrow (the brows' shadow) and A with
    ScalpColor_Hair01; the hair's own mask (its BaseItem's HairScalpMask, from the costume) paints A with the hair's
    root colour (it stops the skin showing between the hair cards).
Hair, eyebrows, lashes (M_Hair*): no colour texture. The base colour, from the compiled base-pass pixel shader of
    Reina's hair instance (M_Hair_Ver7; which constant is which parameter read from the code's structure):
    lerp(RootColor, TipColor, Root ** TipPower) (the Root map is 0 where a card meets the scalp, rising towards its
    tip: on Reina's 547 cards 0.01 at their highest vertex, 0.53 at their lowest), times a strand's value
    1 + RandomValueVariation (lerp(Random_Min, Random_Max, ID) - 1) and its tint, (1, 1 - RandomHueVariation,
    1 - RandomHueVariation) turned by -2 pi ID about the grey axis (ID = ADI Map.B: a random number per strand);
    alpha = saturate(ADI Map.R x OpacityIntensity), cut at the clip value (ADI Map.G, the strands' depth, offsets
    the pixels' depth; nothing else reaches the base colour).
  Head hair (hair_look; the eyebrows and lashes, TTT2 overlays, keep their colours): Tekken 8's hair shading model
    draws a strand far from its base colour (its diffuse and scattering take about the square root of it, its
    highlights are white) where TTT2's hair textures are plain albedos with the strands' shading baked in: baked
    as it is, Reina's hair was black at the crown and a flat electric blue, as if unlit. So the colour becomes TTT2's
    look of it, measured on the default hair of the 15 fighters both games have (TTT2's alpha-tested texels against
    hair_colour's, linear means: black hair, 0.003-0.03 in Tekken 8, is 0.033-0.046 in TTT2; blondes, ~0.55, are
    0.27-0.39 and much paler): grey(HAIR_GAIN (C + HAIR_LIFT) ** HAIR_POWER, HAIR_GREY) (grey(c, s): s of the way to
    its luma), and the strands are shaded by their depth as Tekken 8 shades them (lerp(TextureAO_Min, TextureAO_Max,
    ADI Map.G)) to the HAIR_STRANDS power, its mean kept (TTT2's black hair varies by ~11 sRGB levels from strand
    to strand, the plain term by half that). Reina: roots 34 34 34 -> ~55 grey, tips 79 65 252 -> ~77 74 151 (sRGB).
Eyes (M_CH_Eyes): the Sclera texture x ScleraTint with the IrisColor texture scaled to 1 / UV_Scale of the square in
    its middle (estimate). Inner mouth (M_Ch_Skin_Simple): its BaseColor as it is.
Cloth shine (specular): TTT2's cloth materials take their shine from their third texture (R = specular strength,
    G = how much of the environment map it reflects, A = gloss; TTT2's jackets: R 40-150, G only on metal and shiny
    parts, A 190-235), Tekken 8's from RMA_A (R = roughness, G = metallic, B = ambient occlusion) and, on its satin
    (the _ANS costume shader: Reina's coat and sleeves), an anisotropic highlight per ID (IDnn_AnisoPower: 0.7 on the
    coat's black and purple, 1 on its white tape, 0 on matte cloth and leather) with a Fresnel-weighted reflection of
    its own studio cube map. That satin is what lights her coat in Tekken 8: by roughness (0.70-0.75) it is as matte as
    her leather shorts (0.61-0.65), so a shine from roughness alone gave the coat ~57 of 255, no more than the
    template's average it replaced (74, the same on every cloth texel), and in game the coat showed no sheen at all
    (black parts 27 sRGB flat where Tekken 8's pictures show grey satin highlights along every fold). specular():
    R = (SPECULAR (1 - roughness) + SATIN AnisoPower) lerp(1, AO, 0.5) (the coat's satin ~150, its tape 255, leather
    ~70, matte cloth ~20-40), G = REFLECTION metallic (1 - roughness), A = GLOSS_TOP - GLOSS_SLOPE roughness. Checked in
    game (Fiji, a mirror match): the strength channel alone at 255 doubles the coat's black (27 -> 50 sRGB, the 95th
    percentile 59 -> 83) with highlights along the folds of its normal map; 0 takes her shorts' highlights away
    (95th percentile 154 -> 85).

Written for this project from the files themselves (no third-party code).
"""
import numpy as np
from PIL import Image

LUMA = np.array([0.299, 0.587, 0.114], np.float32)      # the costume shader's luma weights
COSTUME_BASES = ('M_CH_ITM_id_RGBA',)          # the costume shader family (_ANS, ... variants share the formula)
HAIR_BASES = ('M_Hair',)                        # M_Hair_Ver7: hair, eyebrows and lashes
SKIN_BASES = ('M_CH_skin', 'M_Ch_skin')         # M_CH_skin_V3 (face; arm/body/hand skins are its instances)
# not drawn in TTT2: the invisible calculation mesh, the cloth simulation proxy, the eye shadow and tear line films
LEFT_OUT_BASES = ('M_CalculationMesh', 'M_Eye_Blur_AO', 'M_Add_Tear', 'M_CH_sim_mesh_material')
LEFT_OUT_NAMES = ('tear', 'tealine', 'cal_mesh', 'sim_mesh', 'eye_ao')
OVERLAY_NAMES = ('eyebrow', 'eyelash', 'lash', 'brow')     # hair materials drawn as overlays on the face
AB_OVERLAY = 12                     # AB_BlendMode default: Unreal's overlay
IDS_PER_CHANNEL = 4                 # IDs an ID map channel holds at most (16 per material)
NO_ID_COLOUR = {'r': 0.5, 'g': 0.5, 'b': 0.5}     # IDnn_Color's default in the base materials
SHADING_SUBSURFACE = 2              # EMaterialShadingModel MSM_Subsurface (the sheer stockings)
SHEER = 0.4                         # how far a sheer cloth's flat colour goes towards the skin under it
SHEER_COLOUR = 'SheerSkinColor'     # (the vector parameter costume.py gives sheer cloth: the leg skin's colour)
HOLES = 0.02                        # a masked cloth with more than this share cut away has holes (as model.HOLES)
IRIS_EDGE = 0.08                    # soft limbus edge (share of the iris radius)
EYE_SIZE = 256                      # eyes are small in TTT2 (its own have 128-256)
# TTT2's look of a Tekken 8 hair colour C (linear): grey(HAIR_GAIN (C + HAIR_LIFT) ** HAIR_POWER, HAIR_GREY) (the
# module notes); the strands' shading by depth to the HAIR_STRANDS power (as much as TTT2's own hair textures have)
HAIR_GAIN, HAIR_LIFT, HAIR_POWER, HAIR_GREY = 0.48, 0.035, 0.85, 0.34
HAIR_STRANDS = 2.5
# a cloth's shine in TTT2 (specular(); the module notes): strength, reflection, gloss at roughness 0 and its slope;
# what a satin ID's anisotropic highlight (IDnn_AnisoPower) adds to the strength; the shine texture's size at most
# (TTT2's own are 128-512)
SPECULAR, REFLECTION, GLOSS_TOP, GLOSS_SLOPE = 1.0, 0.6, 0.95, 0.3
SATIN = 0.75
SPECULAR_SIZE = 256
ID_MAP_SIZE = 1 << 16               # an ID map is read at its top mip (Tekken 8 cooks one): a smaller mip's averaged
                                    # texels would mix IDs


def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _col(v):
    return np.array([v['r'], v['g'], v['b']], np.float32)


def _resize(a, shape, nearest=False):
    """(H, W[, C]) float array -> shape (h, w), bilinear (nearest for ID maps)."""
    if a.shape[:2] == tuple(shape):
        return a
    if nearest:
        yy = np.arange(shape[0]) * a.shape[0] // shape[0]
        xx = np.arange(shape[1]) * a.shape[1] // shape[1]
        return a[yy][:, xx]
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32)).resize((shape[1], shape[0]), Image.BILINEAR))
    return np.stack([_resize(a[..., c], shape) for c in range(a.shape[-1])], -1)


def _kgain(c):
    m = np.maximum(np.maximum(c[..., 0:1], c[..., 1:2]), c[..., 2:3])
    return np.maximum(1.0, 1.0 + 20.0 * (m - 0.9))


def _luma(c):
    return c[..., 0:1] * LUMA[0] + c[..., 1:2] * LUMA[1] + c[..., 2:3] * LUMA[2]


def ab_blend(a, b, mode):
    """The costume shader's BaseColor_A / BaseColor_B blend (gamma-space values): 1 multiply, 2 add, 11 k(B) A B,
    16 luma(A) k(B) B, 12 (and the others) Unreal's overlay keyed on A."""
    if mode == 1:
        return a * b
    if mode == 2:
        return a + b
    if mode == 11:
        return _kgain(b) * a * b
    if mode == 16:
        return _luma(a) * _kgain(b) * b
    return np.where(a >= 0.5, 1 - 2 * (1 - a) * (1 - b), 2 * a * b)


def id_levels(channel, n):
    """One ID map channel (H, W) uint8 holding n levels -> (level (H, W) int: 1..IDS_PER_CHANNEL, 0 = none, mask (H,
    W) float32): the shader's ramp, level k covering v in [255 (k - 1) / n, 255 k / n] with mask (v - lo) / (hi - lo)
    (a texel on a boundary takes the lower level at 1, the same as the shader's product of both); v = 0 none."""
    m = channel.astype(np.int32) * int(n)
    k = (m + 254) // 255
    mask = ((m - 255 * (k - 1)) / np.float32(255)).astype(np.float32)
    none = (k == 0) | (k > IDS_PER_CHANNEL)
    k[none], mask[none] = 0, 0.0
    return k, mask


def _texture(textures, path, grey=False):
    rgb, a = textures.linear(path)
    if grey:
        rgb = np.repeat((rgb * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True), 3, -1)
    return rgb, a


# ------------------------------------------------------------------------------------------------ families
def bake_costume(eff, textures):
    """A costume material (M_CH_ITM_id_RGBA*) -> (linear rgb, alpha or None); the module notes give the formula."""
    t, v, s = eff['textures'], eff['vectors'], eff['scalars']
    a, _ = textures.linear(t['BaseColor_A'])
    shape = a.shape[:2]
    gam, degam = np.float32(s.get('Gamma', 2.2)), np.float32(s.get('Degamma', 0.4545))
    a = np.power(np.clip(a, 0, None), degam)
    if textures.exists(t.get('BaseColor_B')):
        b, _ = textures.linear(t['BaseColor_B'])
        a = ab_blend(a, np.power(np.clip(_resize(b, shape), 0, None), degam), int(round(s.get('AB_BlendMode',
                                                                                              AB_OVERLAY))))
    D = np.power(np.clip(a, 0, None), gam).astype(np.float32)
    split = [int(round(v.get('SplitNumberPerChannel', {}).get(k, 0.0))) for k in 'rgba']
    out = D
    if textures.exists(t.get('ID_Map')) and any(n > 0 for n in split):
        idmap = _resize(textures.image(t['ID_Map'], ID_MAP_SIZE)[0], shape, nearest=True)
        L = _luma(D)
        X = Dn = None
        for ch in range(4):
            if split[ch] <= 0:
                if X is None:                    # (no R IDs: the R layer is the untinted one)
                    ones = np.ones(shape + (3,), np.float32)
                    X, Dn = _kgain(ones) * L * ones, np.zeros(shape + (1,), np.float32)
                continue
            k, mask = id_levels(idmap[..., ch], split[ch])
            palette, dont = np.ones((IDS_PER_CHANNEL + 1, 3), np.float32), np.zeros(IDS_PER_CHANNEL + 1, np.float32)
            for j in range(1, min(split[ch], IDS_PER_CHANNEL) + 1):
                i = IDS_PER_CHANNEL * ch + j
                palette[j] = _col(v.get('ID%02d_Color' % i, NO_ID_COLOUR))
                dont[j] = np.clip(s.get('ID%02d_DontColorOP' % i, 0.0), 0, 1)
            m = mask[..., None]
            C = 1.0 + m * (palette[k] - 1.0)
            layer, dn = _kgain(C) * L * C, m * dont[k][..., None]
            if X is None:
                X, Dn = layer, dn
            else:                                # a later channel lies on top where it covers
                X = X + m * (layer - X)
                Dn = Dn + m * (dn - Dn)
        X = X + np.clip(Dn, 0, 1) * (D - X)
        anyid = (idmap.astype(np.int32).sum(-1, keepdims=True) > 0).astype(np.float32)
        out = D + anyid * (X - D)
    out = np.clip(out, 0, 1)
    sheer = v.get(SHEER_COLOUR, v.get('SSS_InSideColor'))
    if eff['overrides'].get('ShadingModel') == SHADING_SUBSURFACE and sheer is not None:
        out = out + SHEER * (_col(sheer) - out)
    alpha = None
    if 'AlphaThreshold' in s and textures.exists(t.get('OBD')):
        obd, _ = textures.linear(t['OBD'])
        alpha = _resize(obd[..., 0], shape)
    return out.astype(np.float32), alpha


def bake_skin(eff, textures, grey=False):
    """Skin (M_CH_skin*): colour texture x TintColor, the scalp painted."""
    t, v = eff['textures'], eff['vectors']
    rgb, _ = _texture(textures, t['tx01_BaseColor'], grey)
    tint = v.get('TintColor')
    if tint is not None:
        rgb = rgb * _col(tint)
    shape = rgb.shape[:2]
    for key, paints in (('tx11_ScalpMask', ((0, 'ScalpColor_Eyebrow'), (3, 'ScalpColor_Hair01'))),
                        ('HairScalpMask', ((3, 'ScalpColor_Hair01'),))):
        if not textures.exists(t.get(key)):
            continue
        img = textures.image(t[key])[0]
        for channel, colour in paints:
            if colour in v and img[..., channel].any():
                m = _resize(img[..., channel].astype(np.float32) / 255.0, shape)[..., None]
                rgb = rgb + m * (_col(v[colour]) - rgb)
    return np.clip(rgb, 0, 1).astype(np.float32), None


def hue_turn(rgb, angle):
    """Colours (..., 3) turned by `angle` (radians, (...)) about the grey axis (the hair shader's hue variation)."""
    grey = rgb.mean(-1, keepdims=True)
    d = rgb - grey
    turned = np.stack([d[..., 2] - d[..., 1], d[..., 0] - d[..., 2], d[..., 1] - d[..., 0]], -1) / np.sqrt(3.0)
    return grey + d * np.cos(angle)[..., None] + turned * np.sin(angle)[..., None]


def hair_colour(eff, textures):
    """A hair material's (M_Hair*) base colour as Tekken 8's shader makes it: (linear rgb, alpha or None, the ADI map
    (H, W, 4) uint8 or None), at the ADI map's size; the module notes give the formula."""
    t, v, s = eff['textures'], eff['vectors'], eff['scalars']
    root, tip = _col(v.get('RootColor', {'r': 0, 'g': 0, 'b': 0})), _col(v.get('TipColor', v.get('RootColor', {
        'r': 0, 'g': 0, 'b': 0})))
    adi = textures.image(t['ADI Map'])[0] if textures.exists(t.get('ADI Map')) else None
    if textures.exists(t.get('Root')):
        r = textures.image(t['Root'])[0][..., 0].astype(np.float32) / 255.0
    else:
        r = np.ones(adi.shape[:2] if adi is not None else (32, 32), np.float32)
    if adi is not None:
        r = _resize(r, adi.shape[:2])
    f = np.power(np.clip(r, 0, 1), max(s.get('TipPower', 1.0), 1e-3))[..., None]
    rgb = root + f * (tip - root)
    alpha = None
    if adi is not None:
        alpha = np.clip(adi[..., 0].astype(np.float32) / 255.0 * s.get('OpacityIntensity', 1.0), 0, 1)
        strand = adi[..., 2].astype(np.float32) / 255.0          # (the strands' IDs: a random number each)
        value = 1.0 + s.get('RandomValueVariation', 0.0) * (s.get('Random_Min', 1.0) + strand * (
            s.get('Random_Max', 1.0) - s.get('Random_Min', 1.0)) - 1.0)
        hue = s.get('RandomHueVariation', 0.0)
        tint = hue_turn(np.broadcast_to(np.array([1.0, 1.0 - hue, 1.0 - hue], np.float32), strand.shape + (3,)),
                        -2 * np.pi * strand)
        rgb = tint * rgb * value[..., None]
    return np.clip(rgb, 0, 1).astype(np.float32), alpha, adi


def bake_hair(eff, textures):
    """Hair, eyebrows, lashes (M_Hair*): Tekken 8's root-to-tip colour with its strands' variation (hair_colour);
    head hair (not the eyebrows and lashes, drawn as overlays) as TTT2's hair textures look (hair_look). Alpha from
    the ADI map's red."""
    rgb, alpha, adi = hair_colour(eff, textures)
    if adi is not None and not any(x in eff['name'].lower() for x in OVERLAY_NAMES):
        rgb = hair_look(rgb, adi, alpha, eff)
    return rgb, alpha


def hair_look(rgb, adi, alpha, eff):
    """Tekken 8 head hair's base colour (hair_colour) -> a TTT2 hair texture's colours: the measured TTT2 look of a
    hair colour, then the strands' shading from the ADI map's green (their depth), its mean kept."""
    s = eff['scalars']
    out = HAIR_GAIN * np.power(rgb + HAIR_LIFT, HAIR_POWER)
    out = out + HAIR_GREY * (_luma(out) - out)
    lo, hi = s.get('TextureAO_Min', 1.0), s.get('TextureAO_Max', 1.0)
    shade = np.power(lo + adi[..., 1].astype(np.float32) / 255.0 * (hi - lo), HAIR_STRANDS)
    clip = eff['overrides'].get('OpacityMaskClipValue', s.get('AlphaThreshold', 0.5))
    drawn = alpha >= clip if alpha is not None else np.ones(shade.shape, bool)
    if drawn.any() and shade[drawn].mean() > 0:
        out = out * (shade / shade[drawn].mean())[..., None]
    return np.clip(out, 0, 1).astype(np.float32)


def bake_eye(eff, textures, size=EYE_SIZE):
    """Eye (M_CH_Eyes): the sclera with the iris scaled to 1 / UV_Scale in the middle (estimate)."""
    t, v, s = eff['textures'], eff['vectors'], eff['scalars']
    sc, _ = textures.linear(t['Sclera'], size)
    sc = sc * (_col(v['ScleraTint']) if 'ScleraTint' in v else 1.0)
    if not textures.exists(t.get('IrisColor')):
        return np.clip(sc, 0, 1).astype(np.float32), None
    iris, _ = textures.linear(t['IrisColor'], size)
    h, w = sc.shape[:2]
    d = max(2, int(round(w / max(s.get('UV_Scale', 3.0), 1.0))))
    iris = _resize(iris, (d, d))
    yy, xx = np.mgrid[0:d, 0:d]
    r = np.hypot(xx - (d - 1) / 2.0, yy - (d - 1) / 2.0) / (d / 2.0)
    a = np.clip((1.0 - r) / IRIS_EDGE, 0, 1)[..., None]
    y0, x0 = (h - d) // 2, (w - d) // 2
    sc = sc.copy()
    sc[y0:y0 + d, x0:x0 + d] = sc[y0:y0 + d, x0:x0 + d] * (1 - a) + iris * a
    return np.clip(sc, 0, 1).astype(np.float32), None


def id_values(eff, textures, name, shape):
    """Per texel, the scalar IDnn_<name> of the ID covering it (layered as the colours are: a later channel on top
    where its ramp covers; 0 where no ID does) -> (H, W) float32 of `shape`, or None without an ID map."""
    t, v, s = eff['textures'], eff['vectors'], eff['scalars']
    split = [int(round(v.get('SplitNumberPerChannel', {}).get(k, 0.0))) for k in 'rgba']
    if not textures.exists(t.get('ID_Map')) or not any(n > 0 for n in split):
        return None
    idmap = _resize(textures.image(t['ID_Map'], ID_MAP_SIZE)[0], shape, nearest=True)
    out = np.zeros(shape, np.float32)
    for ch in range(4):
        if split[ch] <= 0:
            continue
        k, mask = id_levels(idmap[..., ch], split[ch])
        values = np.zeros(IDS_PER_CHANNEL + 1, np.float32)
        for j in range(1, min(split[ch], IDS_PER_CHANNEL) + 1):
            values[j] = s.get('ID%02d_%s' % (IDS_PER_CHANNEL * ch + j, name), 0.0)
        out = out + mask * (values[k] - out)
    return out


def specular(eff, textures, size=SPECULAR_SIZE):
    """A costume material's shine as TTT2's cloth materials take it (their third texture; the module notes): (H, W, 4)
    uint8 RGBA, or None without an RMA map."""
    t = eff['textures']
    if not textures.exists(t.get('RMA_A')):
        return None
    rma = textures.image(t['RMA_A'], size)[0][..., :3].astype(np.float32) / 255.0
    rough, metal, ao = rma[..., 0], rma[..., 1], rma[..., 2]
    satin = id_values(eff, textures, 'AnisoPower', rough.shape)
    satin = np.zeros_like(rough) if satin is None else np.clip(satin, 0, 1)
    out = np.zeros(rma.shape[:2] + (4,), np.float32)
    out[..., 0] = (SPECULAR * (1.0 - rough) + SATIN * satin) * (0.5 + 0.5 * ao)
    out[..., 1] = REFLECTION * metal * (1.0 - rough)
    out[..., 3] = GLOSS_TOP - GLOSS_SLOPE * rough
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


# ------------------------------------------------------------------------------------------------ the API
def bake_albedo(eff, textures, grey=False):
    """Linear albedo (H, W, 3) and alpha (H, W) or None of a material with its parameters in effect
    (material.Materials.effective; textures: material.Textures), or (None, None) when it has no colour to bake.
    grey: a colour texture taken by its brightness alone (costume colours give the hue anyway)."""
    base, t = eff['base'] or '', eff['textures']
    if base.startswith(COSTUME_BASES) and textures.exists(t.get('BaseColor_A')):
        return bake_costume(eff, textures)
    if base.startswith(HAIR_BASES):
        return bake_hair(eff, textures)
    if base == 'M_CH_Eyes' and textures.exists(t.get('Sclera')):
        return bake_eye(eff, textures)
    if base.startswith(SKIN_BASES) and textures.exists(t.get('tx01_BaseColor')):
        return bake_skin(eff, textures, grey)
    for slot in ('BaseColor', 'tx01_BaseColor', 'BaseColor_A', 'Diffuse', 'Color'):
        if textures.exists(t.get(slot)):
            rgb, a = _texture(textures, t[slot], grey)
            return rgb, None
    return None, None


def classify(name, base, alpha):
    """What a Tekken 8 material becomes when the definition's MATERIALS does not say: (template kind, normal map?,
    alpha-tested?) or None (left out), from its base material `base` (a name, or the effective() dict) and its name;
    alpha: its baked alpha (None: opaque; bake_albedo gives one to masked materials only)."""
    if isinstance(base, dict):
        base = base['base']
    base, n = base or '', name.lower()
    if base.startswith(LEFT_OUT_BASES) or any(x in n for x in LEFT_OUT_NAMES):
        return None                                   # calculation and cloth proxies, eye shadow, tear line
    if base == 'M_CH_Eyes' or n.endswith(('_eye_l', '_eye_r', '_eyes', '_eye')):
        return ('eye', False, False)
    if 'teeth' in n:
        return ('mouth', False, False)
    if 'mouth' in n or 'tongue' in n:
        return ('mouth', True, False)
    if base.startswith(SKIN_BASES) or '_skin' in n:
        return ('skin', True, False)
    if base.startswith(HAIR_BASES):
        return ('overlay', False, True) if any(x in n for x in OVERLAY_NAMES) else ('hair', False, True)
    holes = alpha is not None and float((alpha < 0.5).mean()) > HOLES
    return ('cloth', True, holes)
