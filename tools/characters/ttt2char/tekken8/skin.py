"""Tekken 8 faces for convert/skin.py's colour gain: the fighters Tekken 8 and TTT2 both have, with a face of their
own in both (no masks, robots or bears), by sex.

skin.gain measures how TTT2 draws skin against how a source game's skin bakes: per fighter in both games, TTT2's face
texture (its model's cha:kao_O_OBJ) over the source's baked face material, the median over the fighters nearest in
brightness to the added one. Tekken 8's face material is Character/Item/model/unique/<code>/face/<code>_fac/materials/
MI_CH_<code>_face_skin (base M_CH_skin_V3; its arm, body and hand skins are instances of it). Tekken 8 names its
fighters by animal codes (the names from the game's own name pictures, UI/.../T_UI_HUD_Character_Name_<code>).

Written for this project from the files themselves (no third-party code).
"""
FACE_MATERIAL = '/Game/Character/Item/model/unique/%s/face/%s_fac/materials/MI_CH_%s_face_skin'
# Tekken 8 code -> (TTT2 code, sex); left out: King, Armor King, Kunimitsu (masks), Jack-8 (a robot), Devil Jin
# (markings; Tekken 7's list leaves him out too), Alisa (TTT2's model has no cha:kao_O_OBJ face), Kuma and Panda
# (bears), and the fighters TTT2 does not have
FIGHTERS = {
    'aml': ('jun', 'female'), 'der': ('ask', 'female'), 'hms': ('lil', 'female'), 'kal': ('nin', 'female'),
    'kgr': ('ann', 'female'), 'rat': ('xia', 'female'), 'crw': ('zaf', 'female'), 'ghp': ('leo', 'female'),
    'ant': ('jin', 'male'), 'bbn': ('rav', 'male'), 'bee': ('hei', 'male'), 'bsn': ('ste', 'male'),
    'cht': ('bry', 'male'), 'dog': ('edd', 'male'), 'grf': ('pau', 'male'), 'grl': ('kaz', 'male'),
    'klw': ('fen', 'male'), 'kmd': ('dra', 'male'), 'lzd': ('lar', 'male'), 'pig': ('law', 'male'),
    'snk': ('hwo', 'male'), 'usi': ('bob', 'male'), 'wlf': ('lee', 'male'),
}


def face_material(code):
    """A Tekken 8 fighter's face skin material (object path)."""
    return FACE_MATERIAL % (code, code, code) + '.MI_CH_%s_face_skin' % code


def reference_faces(sex=None, store=None):
    """[(TTT2 code, Tekken 8 face material path)] of the fighters both games have (of `sex` when given; those whose
    material the installation has when a store is given), in a fixed order."""
    out = []
    for code in sorted(FIGHTERS, key=lambda c: (FIGHTERS[c][1], FIGHTERS[c][0])):
        ttt2, s = FIGHTERS[code]
        if sex is not None and s != sex:
            continue
        path = face_material(code)
        if store is not None and not store.exists(path):
            continue
        out.append((ttt2, path))
    return out
