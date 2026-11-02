"""Akuma (Street Fighter) from Tekken 7 (PC), in his default costume.

Only names, paths and rules live here; every byte of his model, textures and moveset is read from the player's own
Tekken 7 and Tekken Tag Tournament 2 files when the importer runs. His materials are classified by the importer
(model.classify); MATERIALS lists only exceptions.
"""
NAME = 'Akuma'
SHORT_NAME = 'AKUMA'
TEKKEN7_ID = 32
TEKKEN7_CODE = 'mrx'
CODE = 'mrx'
SEX = 'male'
REVISION = 3                  # his gauge (1: packs made before have his EX moves free); its full sound (2);
                              # his cancel rows' sound effects, his own back-turned kicks, Demon Flip in the air (3)

# Ordered built-in Tekken 7 preset sets for the native costume chooser.
PRESETS = (
    ('DefaultCos1P', 'Default'),
    ('DefaultCos2P', 'Default 2P'),
    ('1p_c1', '1p c1'),
    ('niou', 'Niou'),
    ('niou_silver', 'Niou silver'),
    ('yamabushi', 'Yamabushi'),
    ('yamabushi_c1', 'Yamabushi c1'),
)

DONOR = 'lar'                 # Lars Alexandersson: a slim male skeleton
DONOR_ROW = 38

_ITEM = '/Game/Character/Item'
TEKKEN7 = {
    'costume': _ITEM + '/Sets/MRX/CS_MRX_DefaultCos1P',
    'costume_2p': _ITEM + '/Sets/MRX/CS_MRX_DefaultCos2P',
    'parts': [
        ('fac', _ITEM + '/Meshes/mrx/Face/mrx_fac/Meshes/SK_CH_mrx_fac'),
        ('bdl', _ITEM + '/Meshes/mrx/Lower/mrx_bdl_1p/Meshes/SK_CH_mrx_bdl_1p'),
        ('bdu', _ITEM + '/Meshes/mrx/Upper/mrx_bdu_1p/Meshes/SK_CH_mrx_bdu_1p'),
        ('har', _ITEM + '/Meshes/mrx/Hair/mrx_har_1p/Meshes/SK_CH_mrx_har_1p'),
    ],
    'merge_order': ['fac', 'bdl', 'bdu', 'har'],
}

MESHES = {
    'fac': ('mrx_fac', 'ATAMA_Joint', 0),
    'bdl': ('mrx_bdl', 'KOSHI_jnt', 1),
    'bdu': ('mrx_bdu', 'MUNE2_jnt', 2),
    'har': ('mrx_har', 'ATAMA_jnt_assist', 3),
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
    'bust': (_UI + '/VS_CH_L/VS_CH_L_MRX_7FR_DEF', (290, 233, 75)),
    'body': (_UI + '/CS_CH_L/CS_CH_L_MRX', (570, 274, 60)),
    'name': _UI + '/CS_CH_NAME/CS_CH_NAME_MRX',
    'costume': _UI + '/CS_CH_SLOT/CS_CH_SLOT_MRX_01',
}

VOICE_PREFIX = 'mx'

# the id maps: Heihachi in both games, and his generic moves against TTT2's (Heihachi, the donor, Asuka)
ALIGN = [('heihachi', 13), ('self', 13), ('heihachi', 14), ('self', DONOR_ROW), ('heihachi', 9), ('self', 23)]
_SPECIAL_TARGETS = (
    'Ry_shinhadouken', 'Ry_EX_hadoh', 'Ry_hadohB',
    'Ry_shoryuBEX', 'Ry_shoryuB', 'Ry_shoryu',
    'Ry_hadoh', 'Ry_EXtatumaki', 'Ry_tatumakiB',
    'Ry_tatumaki', 'Ry_ShadohEX', 'Ry_ShadohB',
    'Ry_Shadoh', 'Mx_asyura', 'Mx_hyakiC',
    'Mx_hyakiD', 'Mx_asyurab', 'Mx_saving_cn',
)

# The Super Combo gauge (convert/gauge.py): two stocks of 500; his gains as Tekken 7 has them since its 2019 patch; the
# sound Tekken 7 plays as it fills up
GAUGE = dict(max=1000, stock=500, gain=(37, 75, 112, 225), hud='/Game/UI_Common/Flash/sw_ui_hud_rage/sw_ui_hud_rage',
             full_sound='SE_battle_spgauge_full')

MOVESET = {
    # bounds (convert/move_overrides.py): the moves the Tekken 7 Bound Mod makes bounds, and d/f+1+2 (Mx_3lrp)
    'bounds': dict.fromkeys(('Mx_3lprp2', 'Mx_66rk', 'Mx_6lrp', 'Mx_6lrp2', 'Mx_hyaki_gouB', 'Mx_kkt2',
                             'Mx_3lrp'), True),
    'recovery_trim': {'Mx_3rplp': 4},
    'startup_trim': {'Mx_3lrp': 4, 'Mx_66rk': 4},
    'name': '[AKUMA]',
    # Keep Akuma's own WS2, crouching punches and back-turned attacks rather than donor equivalents.
    'own_moves': (
        r'^Mx_6lrk_zanku_EX$|'
        '(?:^Co_(s_trp00|t_slp00(?:y2?)?|t_srp00|t_slk00|syarp03|syalp00(?:y)?|syarp00)$)|^(?:Co_R_clp00R|'
        'Co_R_clk00L|Co_R_crk00R|Co_R_lk00L|Co_R_rk00R|'
        'Co_R_crp00L|Co_R_lp00R|Co_R_rp00L|Co_s_tlp00|Co_s_trp00|Co_syalp00|Co_syarp00|Co_syarp03|Co_t_slk00|'
        'Co_t_slp00|Co_t_srp00|Mx_4lp00|Mx_6lrk|Mx_asyura|Mx_asyurab|Mx_hyakiC|Mx_hyakiD|Mx_lp00|Mx_lplp|'
        'Mx_rp00|Mx_sDASHB_sv|Mx_sDASHF_sv|Mx_sSTEPB_sv|Mx_s_tlk00|Mx_saving|Mx_saving_cn|Mx_syalk00|'
        'Ry_6lrk_EXtatumaki|Ry_EX_hadoh|Ry_EXtatumaki|Ry_Shadoh|Ry_ShadohB|Ry_ShadohB2|Ry_ShadohEX|Ry_hadoh|'
        'Ry_hadohB|Ry_shinhadouken|Ry_shoryu|Ry_shoryu3|Ry_shoryuB|Ry_shoryuB2|Ry_shoryuBEX|Ry_shoryuB_tmk|'
        'Ry_shoryu_tmk|Ry_tatumaki|Ry_tatumakiB)$'
    ),
    # Native routes, including EX/super and Focus cancels. Keep special
    # sources restricted to the targets present in T7 rather than granting
    # every normal's targets to every special.
    'special_cancels': {name: _SPECIAL_TARGETS for name in (
        'Mx_lp00', 'Mx_lplp', 'Mx_4lp00',
        'Mx_rp00', 'Co_R_rp00L', 'Co_R_lp00R',
        'Co_syalp00', 'Co_syarp03', 'Co_syarp00',
        'Co_R_crp00L', 'Co_R_clp00R', 'Mx_syalk00',
        'Co_t_slp00', 'Co_t_srp00', 'Co_t_slk00',
        'Co_s_tlp00', 'Co_s_trp00', 'Mx_s_tlk00',
    )} | {
        'Mx_6lrk': ('Mx_6lrk_zanku_EX', 'Ry_6lrk_EXtatumaki'),
        'Ry_hadohB': ('Mx_saving_cn',),
        'Ry_hadoh': ('Mx_saving_cn',),
        'Ry_Shadoh': ('Mx_saving_cn',),
        'Ry_ShadohB': ('Mx_saving_cn',),
        'Ry_ShadohB2': ('Mx_saving_cn',),
        'Ry_shoryu_tmk': ('Mx_saving_cn',),
        'Ry_shoryu': ('Mx_saving_cn',),
        'Ry_shoryu3': ('Mx_saving_cn',),
        'Ry_shoryuB_tmk': ('Mx_saving_cn',),
        'Ry_shoryuB': ('Mx_saving_cn',),
        'Ry_shoryuB2': ('Mx_saving_cn',),
    },
    'noncontact_special_cancels': ('Ry_hadohB', 'Ry_hadoh', 'Ry_Shadoh', 'Ry_ShadohB', 'Ry_ShadohB2'),
    # Preserve T7's early motion capture and contact-time dispatch.
    'buffered_special_cancels': True,
    'buffered_special_timing': {
        'extra_frames': 8,
        'source_extra_frames': {'Co_s_trp00': 12, 'Mx_s_tlk00': 12, 'Co_t_slk00': 12, 'Mx_syalk00': 12},  # WS+2
        'motion_window': 24,
    },
    'normal_string_followups': {
        'Mx_lp00': ('Mx_lplp', 'Mx_lprp00'),
        'Co_t_slp00': ('Co_syarp03',),
        'Co_syalp00': ('Co_syarp03',),
    },
    'drop_moves': r'^Mx_Direct$',
    'direct': [(r'^(la|mk)_s', 'anim', ['mx_s%02d' % k for k in range(6)]),     # the donor's intros -> his
               (r'^la_w', 'anim', ['mx_w%02d' % k for k in range(2)])],         # win poses
}
