"""Kunimitsu II from Tekken 7 (PC), in her default costume.

Only names, paths and rules live here; every byte of her model, textures and moveset is read from the player's own
Tekken 7 and Tekken Tag Tournament 2 files when the importer runs. Her materials are classified by the importer
(model.classify); MATERIALS lists only exceptions. TTT2 has a Kunimitsu with her Tekken 7 code knm: her pack code is kmi.
"""
NAME = 'Kunimitsu II'
SHORT_NAME = 'KUNIMITSU'
TEKKEN7_ID = 55
TEKKEN7_CODE = 'knm'
CODE = 'kmi'
SEX = 'female'

# Ordered built-in Tekken 7 preset sets for the native costume chooser.
PRESETS = (
    ('DefaultCos1P', 'Default'),
    ('DefaultCos2P', 'Default 2P'),
    ('1p_c1', '1p c1'),
    ('1p_old', '1p old'),
    ('Firefox', 'Firefox'),
    ('Firefox_silver', 'Firefox silver'),
    ('hoodie', 'Hoodie'),
    ('hoodie_c1', 'Hoodie c1'),
    ('hoodie_off', 'Hoodie off'),
)

# T7 supplies no separate slot picture for the hood-down variant.
PRESET_PREVIEWS = {'hoodie_off': 'HOODIE'}

DONOR = 'jun'                 # Jun Kazama: the 139-bone female skeleton
DONOR_ROW = 42

_ITEM = '/Game/Character/Item'
TEKKEN7 = {
    'costume': _ITEM + '/Sets/KNM/CS_KNM_DefaultCos1P',
    'costume_2p': _ITEM + '/Sets/KNM/CS_KNM_DefaultCos2P',
    'parts': [
        ('fac', _ITEM + '/Meshes/knm/Face/knm_fac/Meshes/SK_CH_knm_fac'),
        ('bdl', _ITEM + '/Meshes/knm/Lower/knm_bdl_1p/Meshes/SK_CH_knm_bdl_1p'),
        ('bdu', _ITEM + '/Meshes/knm/Upper/knm_bdu_1p/Meshes/SK_CH_knm_bdu_1p'),
        ('har', _ITEM + '/Meshes/knm/Hair/knm_har_1p/Meshes/SK_CH_knm_har_1p'),
        ('gla', _ITEM + '/Meshes/knm/Glasses/knm_gla_1p/Meshes/SK_CH_knm_gla_1p'),
    ],
    'merge_order': ['fac', 'bdl', 'bdu', 'har', 'gla'],
}

MESHES = {
    'fac': ('kmi_fac', 'ATAMA_Joint', 0),
    'bdl': ('kmi_bdl', 'KOSHI_jnt', 1),
    'bdu': ('kmi_bdu', 'MUNE2_jnt', 2),
    'har': ('kmi_har', 'ATAMA_jnt_assist', 3),
    'gla': ('kmi_gla', 'ATAMA_jnt_assist', 4),
}

MATERIALS = {}

# the material templates: Jun's (they are only shaders; the textures are hers)
TEMPLATES = {
    'skin': ('jun.nud', 'ude_A_O_OBJ', 0),
    'mouth': ('jun.nud', 'cha:kao_O_OBJ', 0),
    'eye': ('jun.nud', 'cha:kao_O_OBJ', 2),
    'overlay': ('jun.nud', 'cha:kao_O_OBJ', 7),
    'cloth': (0xD4F28D09, 'jun_upb_1p_b', 0),
    'hair': (0x5F412CA4, 'jun_hed_1p', 1),
    'colour': (0xD4F28D09, 'jun_upb_1p_b', 2),
    'colour_alpha': (0xD4F28D09, 'jun_upb_1p_b', 1),
}
TEMPLATE_TEXTURES = ['jun.nut', 0x24F8AE59, 0x277C7A37, 0xAD9B60F0, 0x900FD8C4]

_UI = '/Game/UI_Common/Texture2D/ReplaceImages'
ART = {
    'bust': (_UI + '/VS_CH_L/VS_CH_L_KNM_7FR_DEF_1', (320, 247, 115)),
    'body': (_UI + '/CS_CH_L/CS_CH_L_KNM', (564, 260, 105)),
    'name': _UI + '/CS_CH_NAME/CS_CH_NAME_KNM',
    'costume': _UI + '/CS_CH_SLOT/CS_CH_SLOT_KNM_01',
}

VOICE_PREFIX = 'kt'

# the id maps: Heihachi in both games, and her generic moves against TTT2's (Heihachi, the donor, Asuka)
ALIGN = [('heihachi', 13), ('self', 13), ('heihachi', 14), ('self', DONOR_ROW), ('heihachi', 9), ('self', 23)]
# Keep both BT 1 stance-side variants: their generic names hide Kunimitsu's
# own ktkb_s4_blp animation and BT 1,2 / BT 1,3 follow-ups; likewise her own
# BT 4 and crouching 2, d/f+3 and d/f+4 (4); her f+1+4 throw at her own
# frames (5).
REVISION = 5

MOVESET = {
    'own_moves': r'^Co_(?:R_(?:rp00L|lp00R|rk00R)|syarp00|syalkF|syarkF)$',
    # Native movement/tag groups also reference the donor's BT jab directly.
    # Only exact 1 presses should use her attack, not native 2 or 1+2 turns.
    'generic_input_replacements': {'Co_R_rp00L': 0x40000001, 'Co_R_lp00R': 0x40000001},
    # Preserve normal arm coverage; add a lower private point for both BT 1 sides.
    'hitboxes': {'Co_R_rp00L': (12, 13, 0xfe, 11),
                 'Co_R_lp00R': (12, 13, 0xfe, 11),
                 'Kt_Se_lp_LK': (0xfd, 0, 0xfd, 19)},
    'buffered_stance_transitions': {'Kt_rk00F': 'Kt_shoryu02'},
    'name': '[KUNIMITSU]',
    # bounds (convert/move_overrides.py): the moves the Tekken 7 Bound Mod makes bounds
    'bounds': dict.fromkeys(('Kt_236RP', 'Kt_3lprp_RP', 'Kt_3lrp2', 'Kt_66rk_RP', 'Kt_6lk_lprpLK', 'Kt_s_tlplp',
                             'Kt_t_slp00'), True),
    'drop_moves': r'^Kt_Direct$',
    'direct': [(r'^(ju|mk)_s', 'anim', ['kt_s%02d' % k for k in range(6)]),     # the donor's intros -> her
               (r'^ju_w', 'anim', ['kt_w%02d' % k for k in range(4)])],         # win poses
}

# Tekken 7 simulates her scarf's back flap as cloth its mesh models as a sheet a metre behind her (on a rigid bone),
# and her mask has a second copy for the moves she holds it in (on a hand attachment bone): both left out.
MATERIALS['MI_CH_knm_bdu_1p_MufflerBack'] = None
HIDE = [('gla', 'ATH_L_hand_mask_knm')]
# her fringe is modelled through the mask (its hair item has no variant for it: the one her other fox mask names has
# no scalp); Tekken 7 shows the mask over it: the hair in front of the mask's face is left out
COVERED = [('har', 'MI_CH_knm_gla_1p_Mask')]

# her blades (weapons.py), posed by her animations' extra pairs. Her weapon mesh holds eight items, which her moves
# show and hide by number (Tekken 7's 0x8300 n .. 0x8301 n: moveset.SUMMON_PROPS): 0 the short sword (ATH_L_weapon001,
# pair 0: 1,1,1 and the other strings ending in a slash, d, d/f, f + 1 + 2, her Rage Drive and Rage Art) and 1 the
# kunai (ATH_L_weapon002, pair 1: her two kunai throws, until it flies) in her left hand; 3 her kunai in her right
# fist (ATH_R_weapon001, pair 3), 2 the sheathed sword she holds in that hand in an intro (ATH_R_weapon_spear, pair 5,
# its sword ATH_R_weapon_spear_top in it); 7 the sheath at her hips (ATH_R_weapon002, pair 4) with 6 the sword and 5
# the knife in it (ATH_R_weapon002_top, _hilp: carried in the sheath, they go where it goes). 3, 6 and 7 are out
# before any move takes them out (moveset.default_summons): her stance holds the kunai in her right fist (her hand
# shapes: HANDS) and the sheath with the sword at her hips. The points they hit with (Tekken 7 hit locations) are
# Tekken 7's own, on the sword and the kunai in her fist, written whether they are shown or not.
_WEAPONS = _ITEM + '/Meshes/knm/extra/knm_exp_1p/Meshes/SK_CH_knm_exp_1p'
WEAPONS = [
    {'mesh': _WEAPONS, 'draw': True, 'bone': 'ATH_L_weapon001', 'parent': 'TE_L_jnt', 'pair': 0, 'summon': 0,
     'points': {0x74: 'ATH_L_weapon001_top', 0x76: 'ATH_L_weapon001_top', 0x77: 'ATH_L_weapon001_hilp'}},
    {'mesh': _WEAPONS, 'draw': True, 'bone': 'ATH_R_weapon001', 'parent': 'TE_R_jnt', 'pair': 3, 'summon': 3,
     'points': {0x75: 'ATH_R_weapon001_top'}},
    {'mesh': _WEAPONS, 'draw': True, 'bone': 'ATH_L_weapon002', 'parent': 'TE_L_jnt', 'pair': 1, 'summon': 1},
]
# Tekken 7 starts a round with only the kunai in her fist and the sheath with the sword out (one intro ends with the
# sword drawn): her stance and the move her intros and win poses end in start so (moveset.dismiss_at_start)
WEAPON_DISMISS = r'^Kt_(sKAM00_|KAM)$'
# her fingers are TTT2 Kunimitsu's (row 44; moveset.HAND_PROPS): its hand shapes, whose default right hand is the
# fist round her kunai Tekken 7 shows (the donor's are Jun's open hands), and its stance's open left hand (Tekken 7
# kept her stance animation and its hand property)
HANDS = 44
# her Piercing Kunai Throw (d, d/f, f + 1) and the kunai ending her low-high kicks: Tekken 7 flies the kunai by those
# pairs, which TTT2 cannot follow at range; a TTT2 projectile instead (convert/moveset.py thrown_rows), flying as the
# kunai does: from 1.2 m ahead of her hips at its first active frame, 1.1 m up, 460 mm a frame for 13 frames
# The kunai is seen flying with it: her kunai (its triangles in her weapon mesh, tip forward: it has no point bone of
# its own, and in the bind it points as the sword beside it does), with the speed line Tekken 7 trails behind it (her
# effect 40); the kunai drawn in her hand goes as the projectile is spawned (moveset.thrown_rows)
_KUNAI = {'mesh': _WEAPONS, 'bone': 'ATH_L_weapon002', 'tip': 'ATH_L_weapon001_top'}
THROWN = {'Kt_236LP': dict(frame=15, forward=1200, up=350, speed=460, frames=13, radius=150, height=250,
                           item=_KUNAI, trail=40),
          'Kt_2lkrk_LP': dict(frame=26, forward=1200, up=350, speed=470, frames=13, radius=150, height=250,
                              item=_KUNAI, trail=40)}

# Slots 1 and 2 are unused by her converted attacks (the old kunai tip/hilt
# were replaced by projectiles). Later invisible points take those slots;
# the left sword's slot 0 and right sword's slot 3 keep their original reach.
# Offsets are in the parent bone's local frame, in mm, calibrated at impact:
# BT 1: 350 mm below its hand at frame 15; BT 1,3: 100 mm ahead of
# the knee at frame 22 (93 mm at frame 23). Models/animation stay unchanged.
WEAPONS += [
    {'bone': 'L_Hand', 'parent': 'TE_L_jnt', 'pair': None,
     'points': {0xfe: ({'parent_local_offset': (87.579403, -313.689518, 128.174626)}, 1)}},
    {'bone': 'L_Leg', 'parent': 'HIZA_L_jnt', 'pair': None,
     'points': {0xfd: ({'parent_local_offset': (-46.328674, -88.211068, -8.512432)}, 2)}},
]
# her sheathed blades (after the points above, which keep their numbers): the sheath at her hips and the sword and
# the knife in it, the sheathed sword in her right hand and its sword
WEAPONS += [
    {'mesh': _WEAPONS, 'draw': True, 'bone': 'ATH_R_weapon002', 'parent': 'KOSHI_jnt', 'pair': 4, 'summon': 7},
    {'mesh': _WEAPONS, 'draw': True, 'bone': 'ATH_R_weapon002_hilp', 'parent': 'ATH_R_weapon002', 'pair': None,
     'summon': 5},
    {'mesh': _WEAPONS, 'draw': True, 'bone': 'ATH_R_weapon002_top', 'parent': 'ATH_R_weapon002', 'pair': None,
     'summon': 6},
    {'mesh': _WEAPONS, 'draw': True, 'bone': 'ATH_R_weapon_spear', 'parent': 'TE_R_jnt', 'pair': 5, 'summon': 2},
    {'mesh': _WEAPONS, 'draw': True, 'bone': 'ATH_R_weapon_spear_top', 'parent': 'ATH_R_weapon_spear', 'pair': None},
]
