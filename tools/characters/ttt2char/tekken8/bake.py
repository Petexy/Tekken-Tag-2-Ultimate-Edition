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
    IDnn_DontColorOP (layered the same way) lerps back to D: the shader takes 0 for a value of 4 or more, else
    saturate(value) (1, 2 and 3 keep the texture's own colours: Azucena's vines; 4 is what the costumes give an ID
    with a pattern: her leggings, top and jacket);
    the pattern layer: X = lerp(X, P, P.a), P the Pattern texture (T_Alpha0_Dummy, nothing, unless a costume gives
    one), turned about the grey axis by its hue, lerped to its luma by -saturation and to white (black) by its
    brightness (the costume's Assign_PatternHue / Saturation / Brightness: Azucena's leggings' -1 makes their light
    blue side panels silver; the hue's unit, turns, is an estimate: 0 in the default costumes);
    texels no ID covers stay D
    (Saturation and the costume darkening of another constant buffer are 0 in default costumes)
  The colours per ID come from the costume (material.Materials.costume_colours), else from the material.
  Masked costume materials (a BlendMode override of Masked): alpha = OBD.R, cut at the opacity mask clip value.
  Sheer cloth (the subsurface stockings, MI_CH_ITM_SS_*: ShadingModel Subsurface): the game shows the leg through it
  where it faces the camera (towards its SSS_InSideColor) and darkens it towards the edges (SSS_OutSideColor); baked
  opaque it would be dark brown, so a flat albedo takes SHEER of the way from the cloth's colour to the leg skin's
  (SheerSkinColor, the mean of the costume's body skin: costume.py; SSS_InSideColor without one). Checked on the
  game's own 1P and 2P pictures of Reina: stockings 130-147, 107-115, 100-103 (sRGB, lit) on the thighs, 87 69 62 on
  the shin in shadow; without the pictures' lighting (~1.1 in linear, as the costume colours measure) about 136 106 96
  against 133 93 80 baked: as bright, a little warmer (the game's sheen greys it).
Skin (M_CH_skin*): tx01_BaseColor (real colours; the body parts' generic T_CH_femalebody_* textures) x TintColor
    (the compiled base-pass shader's, checked 2026-10-26 with the shader map's parameter table: the suntan / devil /
    custom tints, dirt, sweat and wrinkle colours are off in default costumes).
    On IsFace materials only (the body permutation has no scalp painting) the scalp mask (tx11_ScalpMask, face UV
    layout) paints R with ScalpColor_Eyebrow (the brows' shadow) and A with ScalpColor_Hair01; the hair's own mask
    (its BaseItem's HairScalpMask, from the costume) paints A with the hair's root colour (it stops the skin showing
    between the hair cards).
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
  Bright head hair (bright_hair: Victor Chevalier's white, drawn at HAIR_BRIGHT or above; the dark hairs baked so far,
    sRGB 40-58, are left as they are): TTT2's hair has a texture's strands painted on solid shapes, sRGB 142 139 135 for
    Lee with a spread of 11 levels and the same colour under its alpha; Tekken 8's are thin lines on nothing, its
    strands' value and depth terms running from black to white (his: spread 87, under the alpha black). Dark hair
    hides that, white hair turns to black-and-white speckle. So the drawn texels' sRGB spread comes down to HAIR_SPREAD
    round their mean, that mean comes up to HAIR_LEVEL, the undrawn texels take the colour of the drawn ones near them (fill_under: bilinear filtering
    and the box-filtered mips would darken every strand's edge), and the strands grow by HAIR_THICKEN texels a side (a thin beard's more).
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
Satin cloth (satin_cloth, satin_colour, layer_colour): a costume material with 'Use 3D Iridescent' (of Reina, Azucena,
    Miary Zo and Victor Chevalier only his suit, trousers and waistcoat: pale, half metal, near mirror-free) is bright
    in Tekken 8 by the reflections on its satin IDs (IDnn_AnisoPower near 1): his 1P suit bakes at 90 sRGB and shows 140,
    his 2P 55 and shows 85, greyer than it bakes. A 2P colour layer draws it in TTT2, and the game takes the layer's
    shade and palette colour as encoded colours and multiplies them as linear ones, 2 s^2.2 A^2.2 where colours.fit
    takes 2 s A: at s = 0.5 the layer is LAYER_GAIN darker in linear than the colour it was fitted to (in game his suit
    75 sRGB under the layer, 130 without it, the same frame). So the palette holds a satin group's colour as
    SATIN_GAIN x + SATIN_ADD in linear (the add is the neutral reflection, which is why 2P gets more), measured in
    game against Tekken 8's own pictures of both players; the material's other group, as LAYER_GAIN x, or if it is metal
    (his tie, lining, pocket square: metallic 0.84-0.95, baked 78, 73, 102, dark in Tekken 8 but for reflections) as
    SATIN_METAL_COLOUR x. The palette colour rules here: the layer's shade changes the game's result far less than the
    product suggests (his tie's shades at a third left it as bright, his suit's at x1.46 rose by 13 of 255 sRGB).

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
OVERLAY_NAMES = ('lash', 'brow', 'eyeblow')     # hair materials drawn as overlays on the face: eyelashes, eyebrows
                                                # (also spelt eyeblow: Miary Zo's MI_CH_wkz_eyeblow)
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
# bright_hair: the sRGB luma of a head hair's drawn texels from which it counts as bright, their spread (std) at most,
# their mean at least (TTT2's silver haired Lee 142; Tekken 8's pictures of Victor's hair 177), how many texels its
# strands grow by on each side at the ADI map's size, more up to _MOST while it draws under HAIR_COVER of its texture
# (his beard's strands, 7% of theirs, showed the face between them)
HAIR_BRIGHT, HAIR_SPREAD, HAIR_LEVEL = 90 / 255.0, 24 / 255.0, 170 / 255.0
HAIR_THICKEN, HAIR_THICKEN_MOST, HAIR_COVER = 1, 3, 0.25
HAIR_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)
# a cloth's shine in TTT2 (specular(); the module notes): strength, reflection, gloss at roughness 0 and its slope;
# what a satin ID's anisotropic highlight (IDnn_AnisoPower) adds to the strength; the shine texture's size at most
# (TTT2's own are 128-512)
SPECULAR, REFLECTION, GLOSS_TOP, GLOSS_SLOPE = 1.0, 0.6, 0.95, 0.3
SATIN = 0.75
SPECULAR_SIZE = 256
# satin_cloth: the AnisoPower from which an ID is satin; its palette colours in a 2P layer, and the others' (module notes)
SATIN_ID, SATIN_GAIN, SATIN_ADD, LAYER_GAIN = 0.5, 1.6, np.array((0.105, 0.106, 0.13)), 2.33
SATIN_METAL, SATIN_METAL_COLOUR = 0.7, 0.74    # satin_lift: the other group as metal from what metallic, its palette colour
ID_MAP_SIZE = 1 << 16               # an ID map is read at its top mip (Tekken 8 cooks one): a smaller mip's averaged
                                    # texels would mix IDs
DONT_COLOUR_OFF = 4.0               # IDnn_DontColorOP at or above this colours the ID after all (the shader's test)
# the costume's pattern adjustments (material.customize_colours puts them among the scalars)
PATTERN_HUE, PATTERN_SATURATION, PATTERN_BRIGHTNESS = ('Assign_PatternHue', 'Assign_PatternSaturation',
                                                       'Assign_PatternBrightness')


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


def _pattern(X, eff, textures, shape):
    """The costume shader's pattern layer over the coloured texels X (the module notes)."""
    p, pa = textures.linear(eff['textures']['Pattern'])
    if not pa.any():
        return X
    s = eff['scalars']
    p, pa = _resize(p, shape), _resize(pa, shape)[..., None]
    hue = s.get(PATTERN_HUE, 0.0)
    if hue:
        p = hue_turn(p, np.full(shape, 2 * np.pi * hue, np.float32))
    p = p - s.get(PATTERN_SATURATION, 0.0) * (_luma(p) - p)
    bright = s.get(PATTERN_BRIGHTNESS, 0.0)
    p = p + abs(bright) * (float(bright > 0) - p)
    return X + pa * (np.clip(p, 0, 1) - X)


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
                op = s.get('ID%02d_DontColorOP' % i, 0.0)
                dont[j] = 0.0 if op >= DONT_COLOUR_OFF else np.clip(op, 0, 1)
            m = mask[..., None]
            C = 1.0 + m * (palette[k] - 1.0)
            layer, dn = _kgain(C) * L * C, m * dont[k][..., None]
            if X is None:
                X, Dn = layer, dn
            else:                                # a later channel lies on top where it covers
                X = X + m * (layer - X)
                Dn = Dn + m * (dn - Dn)
        X = X + np.clip(Dn, 0, 1) * (D - X)
        if textures.exists(t.get('Pattern')):
            X = _pattern(X, eff, textures, shape)
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
    if not eff['switches'].get('IsFace'):         # (the body permutation of the shader paints no scalp: Reina's
        return np.clip(rgb, 0, 1).astype(np.float32), None      # leg skin names her face's mask)
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
        if is_bright_hair(rgb, alpha, eff):
            rgb, alpha = bright_hair(rgb, alpha, eff)
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


def _hair_clip(eff):
    return eff['overrides'].get('OpacityMaskClipValue', eff['scalars'].get('AlphaThreshold', 0.5))


def is_bright_hair(rgb, alpha, eff):
    """Whether a head hair's look (linear rgb; alpha or None) counts as bright: the mean sRGB luma of its drawn texels
    at HAIR_BRIGHT or above."""
    if alpha is None:
        return False
    drawn = alpha >= _hair_clip(eff)
    return bool(drawn.any()) and float((linear_to_srgb(rgb[drawn]) @ HAIR_LUMA).mean()) >= HAIR_BRIGHT


def fill_under(rgb, drawn):
    """Colours (H, W, 3) with the texels not `drawn` (H, W) taking the colour of the drawn ones nearest them (a pull-push
    pyramid); the drawn texels stay as they are."""
    weights, colours = [np.asarray(drawn, np.float32)], [rgb * np.asarray(drawn, np.float32)[..., None]]
    while min(weights[-1].shape) > 1:
        w, c = weights[-1], colours[-1]
        h, x = (w.shape[0] + 1) // 2, (w.shape[1] + 1) // 2
        at_y, at_x = np.arange(w.shape[0]) // 2, np.arange(w.shape[1]) // 2
        sw, sc = np.zeros((h, x), np.float32), np.zeros((h, x, 3), np.float32)
        np.add.at(sw, (at_y[:, None], at_x[None, :]), w)
        np.add.at(sc, (at_y[:, None], at_x[None, :]), c)
        weights.append(sw)
        colours.append(sc)
    out = colours[-1] / np.maximum(weights[-1], 1e-6)[..., None]
    for w, c in zip(reversed(weights[:-1]), reversed(colours[:-1])):
        up = out[np.arange(w.shape[0]) // 2][:, np.arange(w.shape[1]) // 2]
        out = np.where(w[..., None] > 0, c / np.maximum(w, 1e-6)[..., None], up)
    return np.where(np.asarray(drawn)[..., None], rgb, out).astype(np.float32)


def thicken(alpha, texels):
    """An alpha map (H, W) with what it draws grown by `texels` on each side (a square maximum filter)."""
    out = alpha
    for axis in (0, 1):
        grown = out
        for step in range(1, texels + 1):
            grown = np.maximum(grown, np.maximum(np.roll(out, step, axis), np.roll(out, -step, axis)))
        out = grown
    return out


def bright_hair(rgb, alpha, eff):
    """A bright head hair's look and alpha made solid, as TTT2's hair textures are (the module notes)."""
    drawn = alpha >= _hair_clip(eff)
    encoded = linear_to_srgb(rgb).astype(np.float32)
    luma = encoded @ HAIR_LUMA
    mean, spread = float(luma[drawn].mean()), float(luma[drawn].std())
    if spread > HAIR_SPREAD:
        encoded = encoded + ((mean - luma) * (1.0 - HAIR_SPREAD / spread))[..., None]
    encoded = encoded + max(HAIR_LEVEL - mean, 0.0)
    out = fill_under(srgb_to_linear(np.clip(encoded, 0, 1)).astype(np.float32), drawn)
    grown = thicken(alpha, HAIR_THICKEN)
    for texels in range(HAIR_THICKEN + 1, HAIR_THICKEN_MOST + 1):
        if (grown >= _hair_clip(eff)).mean() >= HAIR_COVER:
            break
        grown = thicken(alpha, texels)
    return out, grown


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


def dark_metal(rgb, eff, textures, look):
    """Baked colours (H, W, 3, linear) of a material the definition's TEKKEN8['dark_metal'] names: its grey metal (RMA_A's
    G) x look[0], its other greys x look[3]. A metal has no colour of its own in Tekken 8: all it shows is what it
    reflects, a dark room but for its highlights, where TTT2 lights its pale base colour (0.8-0.95) as a white cloth's;
    TTT2 lights his weapons' mid grey plastics far above Tekken 8's too. Coloured texels (a glowing line, a panel) stay."""
    if not textures.exists(eff['textures'].get('RMA_A')):
        return rgb
    h, w = rgb.shape[:2]
    metal = textures.image(eff['textures']['RMA_A'], max(h, w))[0][..., 1].astype(np.float32) / 255.0
    metal = _resize(metal, (h, w))[..., None]
    top = rgb.max(axis=2, keepdims=True)
    coloured = np.clip(2.0 * (top - rgb.min(axis=2, keepdims=True)) / np.maximum(top, 1e-4), 0.0, 1.0)
    factor = look[3] + (look[0] - look[3]) * metal
    return rgb * (factor + (1.0 - factor) * coloured)


def specular(eff, textures, size=SPECULAR_SIZE, dark=None):
    """A costume material's shine as TTT2's cloth materials take it (their third texture; the module notes): (H, W, 4)
    uint8 RGBA, or None without an RMA map. dark: dark_metal's look, (metal's colour, strength, reflection, others'
    colour): its metal's strength (R) and reflection (G) x these."""
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
    if dark is not None:
        out[..., 0] *= 1.0 - metal * (1.0 - dark[1])
        out[..., 1] *= dark[2]
    out[..., 3] = GLOSS_TOP - GLOSS_SLOPE * rough
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


def satin_cloth(eff, textures, shape):
    """The texels (H, W) bool of `shape` of a costume material's satin IDs, or None: not a material bright by its
    reflections (the module notes)."""
    if not (eff.get('switches') or {}).get('Use 3D Iridescent'):
        return None
    satin = id_values(eff, textures, 'AnisoPower', shape)
    return None if satin is None else satin >= SATIN_ID


def satin_lift(eff, textures, shape):
    """colours.fit's lift for a satin material of `shape`: (group: 0 satin, its colour (encoded), its texels (H, W) bool)
    -> what a 2P layer's palette holds for it (the module notes)."""
    def lift(group, rgb, texels):
        if group == 0:
            return satin_colour(rgb)
        metal = np.zeros(shape, np.float32)
        if textures.exists(eff['textures'].get('RMA_A')):
            metal = _resize(textures.image(eff['textures']['RMA_A'], max(shape))[0][..., 1].astype(np.float32) / 255.0, shape)
        return rgb * SATIN_METAL_COLOUR if metal[texels].mean() >= SATIN_METAL else layer_colour(rgb)
    return lift


def satin_colour(rgb):
    """A satin group's colour (encoded, as colours.fit has it) -> what a 2P layer's palette holds for it."""
    return np.clip(linear_to_srgb(SATIN_GAIN * srgb_to_linear(rgb) + SATIN_ADD), 0, 1)


def layer_colour(rgb):
    """The same for the other group of a satin material."""
    return np.clip(linear_to_srgb(LAYER_GAIN * srgb_to_linear(rgb)), 0, 1)


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


def classify(name, base, alpha, share=None):
    """What a Tekken 8 material becomes when the definition's MATERIALS does not say: (template kind, normal map?,
    alpha-tested?) or None (left out), from its base material `base` (a name, or the effective() dict) and its name;
    alpha: its baked alpha (None: opaque; bake_albedo gives one to masked materials only); share: its emission share
    (emission_share; None: not known), at GLOW_SHARE or more on a glowing part's base the 'glow' template's."""
    if isinstance(base, dict):
        base = base['base']
    base, n = base or '', name.lower()
    if base.startswith(LEFT_OUT_BASES) or any(x in n for x in LEFT_OUT_NAMES):
        return None                                   # calculation and cloth proxies, eye shadow, tear line
    if base.startswith(GLOW_BASES) and share is not None and share >= GLOW_SHARE:
        return ('glow', False, False)                 # a glowing summon (bake_emissive)
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


# ------------------------------------------------------------------------------------------------ glowing parts
# Summoned parts (M_CH_Extra_Parts instances: Miary Zo's staffs, tail, horn and snakes) are lit, masked materials whose
# look is an HDR emissive over a dark base, bloomed (their Tekken 8 "translucency"). The steady emissive (Transition
# 1, the shown part: its compiled base-pass pixel shader, the part's own parameters):
#     E = R(EmissiveMask) ** EmissiveMask_Power x EmissiveColor_A x EmissiveIntensity_A
#       + G(EmissiveMask) ** EmissiveMask_Power x EmissiveColor_B x EmissiveIntensity_B
#       + (1 - N.V) ** FresnelPower x Fresnel Color x Fresnel Intensity           ('Use Fresnel')
#       + FlowEmissiveMap(scrolling) x FlowEmissiveColor x FlowEmissiveIntensity   (the flowing wave)
#       + OverrideEmissiveColor x OverrideEmissiveIntensity
# The part is drawn with the definition's 'glow' template (Miary Zo's: the unlit textured core of TTT2's own light
# spears, cmn_opu_LightSpear), its colour texture the colour on screen: bake_emissive bakes E + the base colour x
# BaseTintColor x
# GLOW_AMBIENT (the scene's light on the base) with the view-dependent terms at their means (the Fresnel term's over a
# cylinder seen side-on, the wave's over its texture), then Tekken 8's tone curve on it: exposure GLOW_EXPOSURE,
# GLOW_DESATURATION of the way to its luma (Unreal's filmic curve greys bright blue), the ACES fit, gamma 2.2. Fitted
# on a Tekken 8 screenshot of her right staff (40462 staff pixels: sRGB p10 51 106 169, median 70 149 209, p90 99 199
# 240): the bake's p10 43 110 169, median 87 179 239 (13 levels off on average; without the desaturation 21). A part
# whose emission is GLOW_SHARE or more of its look (emission_share: staffs 0.97, tail centre and fur 0.84, horn 0.86)
# is drawn so (classify: 'glow'); the others keep a lit template.
GLOW_BASES = ('M_CH_Extra_Parts',)
GLOW_SHARE = 0.75
GLOW_AMBIENT = 0.5
GLOW_EXPOSURE = 0.5
GLOW_DESATURATION = 0.15
GLOW_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)      # (Rec. 709)


def uv_set(eff, slot):
    """The UV set (0 or 1) material eff samples its texture `slot` ('BaseColor', 'EmissiveMask', ...) through: its
    'Use UV1 for <slot>' switch (M_CH_Extra_Parts: Miary Zo's tail is laid out along its UV1)."""
    return 1 if (eff.get('switches') or {}).get('Use UV1 for %s' % slot) else 0


def fresnel_mean(power, samples=4096):
    """The screen mean of (1 - N.V) ** power over a cylinder seen side-on (x = sin of the normal's angle to the view,
    uniform across its width)."""
    x = (np.arange(samples) + 0.5) / samples
    return float(((1.0 - np.sqrt(1.0 - x * x)) ** power).mean())


def aces(x):
    """Narkowicz's fit of the ACES filmic curve (as convert/particles.py's lit texels)."""
    x = np.maximum(x, 0)
    return np.clip(x * (2.51 * x + 0.03) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)


def _emissive_terms(eff, textures):
    """(base term (H, W, 3), emissive E (H, W, 3)) of a glowing part, linear, at its BaseColor's size (the module
    notes); (None, None) without a colour texture."""
    t, s, sw = eff['textures'], eff['scalars'], eff.get('switches') or {}
    if not textures.exists(t.get('BaseColor')):
        return None, None
    base, _ = textures.linear(t['BaseColor'])
    shape = base.shape[:2]
    lit = base * _col(eff['vectors'].get('BaseTintColor', {'r': 1, 'g': 1, 'b': 1})) * GLOW_AMBIENT
    E = np.zeros(shape + (3,), np.float32)
    if sw.get('Use EmissiveMask', True) and textures.exists(t.get('EmissiveMask')):
        mask, _ = textures.linear(t['EmissiveMask'])
        power = float(s.get('EmissiveMask_Power', 1.0))
        if uv_set(eff, 'EmissiveMask') == uv_set(eff, 'BaseColor'):
            mask = _resize(mask, shape)
        else:                                    # (laid out otherwise: its mean)
            mask = np.broadcast_to(mask.reshape(-1, 3).mean(0), shape + (3,))
        for ch, ab in ((0, 'A'), (1, 'B')):
            colour = _col(eff['vectors'].get('EmissiveColor_' + ab, {'r': 0, 'g': 0, 'b': 0}))
            E = E + np.power(np.clip(mask[..., ch:ch + 1], 0, 1), power) * colour * float(
                s.get('EmissiveIntensity_' + ab, 0.0))
    if sw.get('Use Fresnel'):
        E = E + fresnel_mean(float(s.get('FresnelPower', 1.0))) * _col(
            eff['vectors'].get('Fresnel Color', {'r': 0, 'g': 0, 'b': 0})) * float(s.get('Fresnel Intensity', 0.0))
    flow = t.get('FlowEmissiveMap')
    if flow and textures.exists(flow) and not any(x in flow for x in ('White', 'Black')):
        wave, _ = textures.linear(flow)
        E = E + float(wave[..., 0].mean()) * _col(eff['vectors'].get('FlowEmissiveColor', {'r': 0, 'g': 0, 'b': 0})) \
            * float(s.get('FlowEmissiveIntensity', 0.0))
    E = E + _col(eff['vectors'].get('OverrideEmissiveColor', {'r': 0, 'g': 0, 'b': 0})) * float(
        s.get('OverrideEmissiveIntensity', 0.0))
    return lit.astype(np.float32), E.astype(np.float32)


def emission_share(eff, textures):
    """The share of a glowing part's steady look its emission gives (linear luminance, the base term as
    bake_emissive takes it), or None: not a glowing part's base, or nothing to bake."""
    if not (eff.get('base') or '').startswith(GLOW_BASES):
        return None
    lit, E = _emissive_terms(eff, textures)
    if lit is None:
        return None
    e, b = float((E * GLOW_LUMA).sum(-1).mean()), float((lit * GLOW_LUMA).sum(-1).mean())
    return e / (e + b) if e + b > 0 else 0.0


def glow_encode(x):
    """Linear HDR colour -> the display value (0..1) Tekken 8's tone curve gives it (the module notes)."""
    luma = (x * GLOW_LUMA).sum(-1, keepdims=True)
    return aces((x * (1 - GLOW_DESATURATION) + luma * GLOW_DESATURATION) * GLOW_EXPOSURE) ** (1 / 2.2)


def bake_emissive(eff, textures):
    """A glowing part's steady look, its colour texture -> (linear rgb whose sRGB encoding is the colour on screen,
    None) (the module notes), or (None, None) without a colour texture."""
    lit, E = _emissive_terms(eff, textures)
    if lit is None:
        return None, None
    return srgb_to_linear(glow_encode(lit + E)).astype(np.float32), None
