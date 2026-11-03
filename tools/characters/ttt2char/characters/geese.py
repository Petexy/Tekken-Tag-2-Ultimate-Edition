"""Geese Howard (Fatal Fury) from Tekken 7 (PC), in his default costume.

Only names, paths and rules live here; every byte of his model, textures and moveset is read from the player's own
Tekken 7 and Tekken Tag Tournament 2 files when the importer runs. Tekken 7 keeps his costume encrypted: the
importer reads it as the running game reads it (dump_tekken7.py saves it). His materials are classified by the
importer (model.classify); MATERIALS lists only exceptions.
"""
NAME = 'Geese Howard'
SHORT_NAME = 'GEESE'
TEKKEN7_ID = 43
TEKKEN7_CODE = 'mry'
CODE = 'mry'
SEX = 'male'
REVISION = 2                  # his gauge and MAX mode (packs made before have his EX moves and supers free);
                              # his cancel rows' sound effects, his own back-turned 3 and 4 (2)

# Ordered built-in Tekken 7 preset sets for the native costume chooser.
PRESETS = (
    ('DefaultCos1P', 'Default'),
    ('DefaultCos2P', 'Default 2P'),
    ('1p_c1', '1p c1'),
    ('houou', 'Houou'),
    ('houou_c1', 'Houou c1'),
    ('houou_silver', 'Houou silver'),
    ('suit_gilet', 'Suit gilet'),
)

DONOR = 'lar'                 # Lars Alexandersson: a slim male skeleton
DONOR_ROW = 38

_ITEM = '/Game/Character/Item'
TEKKEN7 = {
    'costume': _ITEM + '/Sets/MRY/CS_MRY_DefaultCos1P',
    'costume_2p': _ITEM + '/Sets/MRY/CS_MRY_DefaultCos2P',
    'parts': [
        ('fac', _ITEM + '/Meshes/mry/Face/mry_fac/Meshes/SK_CH_mry_fac'),
        ('bdl', _ITEM + '/Meshes/mry/Lower/mry_bdl_1p/Meshes/SK_CH_mry_bdl_1p'),
        ('bdu', _ITEM + '/Meshes/mry/Upper/mry_bdu_1p/Meshes/SK_CH_mry_bdu_1p'),
        ('har', _ITEM + '/Meshes/mry/Hair/mry_har_1p/Meshes/SK_CH_mry_har_1p'),
    ],
    'merge_order': ['fac', 'bdl', 'bdu', 'har'],
}

MESHES = {
    'fac': ('mry_fac', 'ATAMA_Joint', 0),
    'bdl': ('mry_bdl', 'KOSHI_jnt', 1),
    'bdu': ('mry_bdu', 'MUNE2_jnt', 2),
    'har': ('mry_har', 'ATAMA_jnt_assist', 3),
}

MATERIALS = {}

# the material templates: Jun's (they are only shaders; the textures are his)
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
    'bust': (_UI + '/VS_CH_L/VS_CH_L_MRY_7FR_DEF', (342, 225, 155)),
    'body': (_UI + '/CS_CH_L/CS_CH_L_MRY', (582, 276, 125)),
    'name': _UI + '/CS_CH_NAME/CS_CH_NAME_MRY',
    'costume': _UI + '/CS_CH_SLOT/CS_CH_SLOT_MRY_01',
}

VOICE_PREFIX = 'my'

# the id maps: Heihachi in both games, and his generic moves against TTT2's (Heihachi, the donor, Asuka)
ALIGN = [('heihachi', 13), ('self', 13), ('heihachi', 14), ('self', DONOR_ROW), ('heihachi', 9), ('self', 23)]
# All sources below were audited against Geese's exported T7 capture/dispatch rows.
# EX commands retain their distinct two-button inputs; normal commands stay available.
_SPECIALS = (
    'My_EX_SPReppuu',
    'My_EX_Reppuu',
    'My_Reppuu',
    'My_RS00',
    'My_EX_FudohPAB',
    'My_FudohP',
    'My_CCL_DASH',
    'My_623EX',
    'My_623A',
    'My_623B',
    'My_ReppuuB',
    'My_FudohPB',
    'My_EX_Jyaei',
    'My_Jyaei_C',
    'My_Jyaei_D',
    'My_HItataki',
    'My_lk00F',
)
_NORMAL_CANCELS = (
    'My_lp00',
    'My_rp00',
    'Co_R_rp00L',
    'Co_R_lp00R',
    'My_syalp00',
    'Co_R_crp00L',
    'Co_R_clp00R',
    'My_syalk00_LP',
    'My_syark00',
    'Co_R_clk00L',
    'Co_R_crk00R',
    'My_t_slp00',
    'My_t_slk_LP',
    'My_t_srk00',
    'My_s_tlp00',
    'My_HItataki',
)
_SUPER_CANCELS_ON_CONTACT = (
    'My_FudohP',
    'My_FudohP_LP',
    'My_FudohP_LK',
    'My_FudohP_RK',
    'My_EX_FudohPAB_LP',
    'My_EX_FudohPAB_LK',
    'My_EX_FudohPAB_RK',
    'My_Jyaei_C2',
    'My_Jyaei_D3',
    'My_EX_Jyaei03',
)
_SUPER_CANCELS_WITHOUT_CONTACT = (
    'My_Reppuu',
    'My_ReppuuB2',
    'My_EX_Reppuu2',
)
# his power gauge (convert/gauge.py): three stocks of 500, his own gains (Tekken 7 sets them for him), the MAX mode
# (activation 500: his EX moves while its timer runs) and its HUD
GAUGE = dict(max=1500, stock=500, gain=(21, 85, 63, 255),
             hud='/Game/UI_Common/Flash/sw_ui_hud_rage_mry/sw_ui_hud_rage_mry')

MOVESET = {
    'own_moves': r'^(My_.*|Co_R_(rp00L|lp00R|lk00L|rk00R|crp00L|clp00R|clk00L|crk00R))$',
    # MAX mode's activation (1+2+3) also tests Tekken 7's variable 9 == 0, which none of his moves sets
    'true_requirements': ((360, 9 << 16),),
    'buffered_special_cancels': True,
    'strict_special_cancel_gates': True,
    'buffered_normal_followups': True,
    'buffered_special_timing': {'extra_frames': 8, 'motion_window': 24},
    'noncontact_special_cancels': _SUPER_CANCELS_WITHOUT_CONTACT,
    'special_cancels': {
        **{name: _SPECIALS for name in _NORMAL_CANCELS},
        **{name: ('My_CCL_DASH',) for name in ('My_rp02F', 'My_lk00F', 'My_4lplk', 'My_lkrp00B',)},
        'My_WPF': ('My_WPF_EX_ShippuF', 'My_WPF_ShippuF_A', 'My_WPF_ShippuF_B'),
        **{name: ('My_EX_SPReppuu', 'My_RS00')
           for name in _SUPER_CANCELS_ON_CONTACT + _SUPER_CANCELS_WITHOUT_CONTACT},
    },
    'name': '[GEESE]',
    # bounds (convert/move_overrides.py): the moves the Tekken 7 Bound Mod makes bounds, and CD+2 (Hishou Nichirin
    # Zan) on its second hit
    'bounds': dict.fromkeys(('My_EX_FudohPAB_LK', 'My_FudohP_LK', 'My_lprplp03', 'My_rp00B', 'My_t_slkF2_RP',
                             'My_623B2'), True),
    # f+1+2 airborne pickup: native float plus earlier neutral recovery.
    'air_reactions': {'My_WPF': (40, 'J8_jprk00')},
    'recovery_trim': {'My_WPF': 8},
    'drop_moves': r'^My_Direct$',
    'direct': [(r'^(la|mk)_s', 'anim', ['my_s%02d' % k for k in range(7)]),     # the donor's intros -> his
               (r'^la_w', 'anim', ['my_w%02d' % k for k in range(3)])],         # win poses
}
