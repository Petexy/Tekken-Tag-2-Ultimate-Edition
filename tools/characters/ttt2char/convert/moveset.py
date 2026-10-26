"""A Tekken 7 or Tekken 8 fighter's moveset -> a TTT2 moveset (motbin) and motion pack for the added fighter.

The base is the donor's moveset and motion pack: its generic moves, the tag system, the embedded MOTAs, the hand,
face and camera animations. The fighter's own moves (in its moveset but neither the donor's nor generic) are
converted and appended; the generic "hub" moves that lead into them (standing, crouching, ...) get the fighter's
cancel lists, converted, plus the donor's cancels into TTT2-only moves (tag out, ...). Neither Tekken 7 nor Tekken 8
has a tag: what TTT2's tag system needs in the converted moves themselves (the bound moves' Tag Assault twins, the
landing reactions' Tag Crash rows, the bound test of the air slams) is made after the donor's (tagsystem.py).

Converting a move: requirement and property ids through the derived id maps (idmaps.py), hit location codes
likewise, the bitfield bit-reversed (TTT2 bit 31 - i = Tekken 7 bit i), move ids by name, animations by reference:
0x8000 | i when the animation is in TTT2's common motions (data004), 0x4000 | i when the donor's pack has it,
otherwise it is appended (byte-swapped) to the pack's body MOTA. Whatever cannot be mapped is dropped with the
cancel, hit-condition entry or property that holds it, and counted; nothing is guessed.

The source moveset's game (its `game`: 't7' TKMovesets2's .tkmvst, tekken7/tkmvst.py; 't8' a Tekken 8 motbin as the
Tekken 8 reader gives it: Tekken 7's field names and command encoding, Tekken 8's requirement and property ids, its
60 alias slots) picks the rules below: each id they name is a table {'t7': ..., 't8': ...}, Tekken 8's the Tekken 7
id's counterpart (the id maps between the two games: Tekken 8 inserted ids, 217 -> 220, 0x81bd -> 0x822d). A Tekken
8 fighter needs no Tekken 7: its moves are classified by name and by the bank of their animations (classify8), its
own animations come from an animation provider (ANIMATIONS), and the ids Tekken 8 alone has follow REQ_T8ONLY.

Written for this project from the files themselves (no third-party code).
"""
import collections
import copy
import hashlib
import re
import struct

import numpy as np

from ..movesets import REACTION_MOVE_FIELDS, TABLE_ORDER, TTT2
from ..ttt2 import animation, motbin, motion
from . import arcs
from . import idmaps as M
from . import tagsystem, tagcombo, specialcancels, move_overrides, retarget

T7_END, TT_END = M.END_REQ['t7'], M.END_REQ['ttt2']
SEQ0 = 0x800D                       # a cancel direction from here on names an input sequence
# A move the Tekken 8 reader could not name (its move_name is '') is '#<index>' here (the converter's `name`, idmaps'
# reaction evidence) and '<own prefix>_#<index>' in the TTT2 moveset (Zbr_#1523)
UNNAMED = M.UNNAMED

# ------------------------------------------------------------------------------------------------ rules
# The requirement ids that are always false in TTT2 (the mode or system does not exist there)
REQ_FALSE = {
    't7': {157: 'rage', 636: 'assist button', 811: 'basic combo', 558: 'story battle', 559: 'story battle no.',
           560: 'customization', 563: 'game mode', 634: 'treasure battle', 765: 'arcade cutscene',
           830: 'power crush absorption', 809: 'assist combo value', 810: 'assist combo', 807: 'assist combo',
           806: 'Tekken 7-only state (CPU or mode)'},
    # Tekken 7's 157, 765, 806 (and 634, 636: between anchors of the same offset) in Tekken 8's numbering; then
    # Tekken 8's own whose parameter is in its own numbering, which the other Tekken 8 fighters' evidence pairs with a
    # TTT2 id all the same (REQ_T8ONLY's notes)
    't8': {159: 'rage', 745: 'assist button', 743: 'treasure battle', 977: 'arcade cutscene',
           1018: 'Tekken 7-only state (CPU or mode)', 442: 'Heat variables',
           1036: 'the opponent\'s move (a Tekken 8 move number)', 1065: 'the opponent\'s move (a Tekken 8 move number)',
           # (Tekken 7's 830: the player's byte +0xf64 > 0; Kugai Dachi / Demon Bolt -> their absorbing twins)
           1049: 'power crush absorption',
           # the opponent's throw-break state +0x1c08 set (461: clear; REQ_T8ONLY)
           460: 'the opponent\'s throw-break state (set)'},
}
# 806 must be false for a player: Tekken 7's generic moves gate a 120-frame lock on it at frame 2 of every side step
# ([806][0x8077 120][352][0x80a6 1]: moveset variable 1 = 120, which TTT2's down-tap side step needs at 0, its
# requirement 262; down taps crouched for 2 s after any side step) and an end of every side walk at frame 32. The
# alignment once paired it with TTT2's requirement 0 (true): its row `[806] -> sWALK_02L` sat where TTT2 has the
# neutral row `0x20 [0] -> sWALK_02L` (idmaps.align now compares directions).
# Tekken 8-only requirements (Heat, game modes, new systems: no Tekken 7 or TTT2 counterpart, so no id map has them;
# in Reina's generic moves they occur only in rows Tekken 7 lacks) as a TTT2 fighter meets them: id -> (field, value,
# what it tests). The test reads a state TTT2 never has, so it always finds `value` there: a row whose `field` is
# that value (field 'always': any row; 'param_lo': param & 0xFFFF) is true and left out of its list, any other makes
# the list false. Tekken 8's requirement function (0x141875910; body 0x141875952: switch (id - 2) over a table of
# 1092 cases at 0x14187e728, unknown ids false; r14 the player, r13 the opponent, the row at [rbp + 0x110]) reads:
#   476  the player's variable `param` (1-based, of 20 at +0x580) == param2. The moveset writes them (0x8152: value
#        the variable, value2 what; Reina's Heat Burst sets 16 to 1..3 and branches on it). The first four are TTT2's
#        latches (LATCHES); the others a Tekken 8 property TTT2 has not: always 0, so her normal rows (throws from
#        #1501 test 476(16, 0)) stay
#   439  the opponent's variable param >> 16 (of 50 at +0x16d4) == param & 0xFFFF: always 0 alike
#   453  the buttons `param` held (bit 1 LP .. 0x40 as input bits 0x200 << k at +0x28b0): the row's own buttons again
#        (1+2 with 453(3), 1+3 with 453(5), ...)
#   667  game mode 4 on (param 1) / off (0) (the mode object, 0x1418a9f00(mode, 4)); 801 the same for mode 14
#   1028 Heat: the protected gauge at +0x2490 is > 0 (or -1) and activation is not locked (param 1) / empty (0)
# Left false: 452 the Heat activation lock alone (only in Heat Burst rows) and 668 / 802 a value of game mode 4 / 14
# (no id map has them), 442 the Heat variables (4 at +0x24a0) == param2 and 1036 / 1065 the opponent's move is the
# move `param` (a Tekken 8 move number, 14295 ...; TTT2's 647 / 665 test TTT2's: 491 ...): REQ_FALSE, as the other
# Tekken 8 fighters' evidence pairs them with TTT2's 46, 647 and 665. The rest TTT2 tests alike, their ids mapped and
# their parameters TTT2's numbers too: 661 a random chance of param per mille (TTT2's 409: 900, 300, ...), 662 / 652 /
# 653 a frame counter modulo param (410 / 400 / 401), 1035 and 1078..1083 the kind of the opponent's attack (646 and
# 678..683: 9, 13, 16, 19, ...).
#   461  the opponent's byte +0x1c08 == 0 (460: != 0, REQ_FALSE), only in her throws' break rows: `[(461), (131 | 132)]
#        win 1-15 -> Esc_*_n` (the opponent pressed 1 / 2: TTT2's 129 / 130), `[(460), ...] win 1-10` the shorter
#        window of that state. TTT2's own throws break as the first, `[(130)] win 1-15 -> Esc_FRnage00_n` (Jun): the
#        state is never set there, so her throws were unbreakable with both rows false
REQ_T8ONLY = {476: ('param2', 0, 'player variable'), 439: ('param_lo', 0, 'opponent variable'),
              453: ('always', None, 'buttons held'), 667: ('param', 0, 'game mode 4'),
              801: ('param', 0, 'game mode 14'), 1028: ('param', 0, 'Heat'),
              461: ('always', None, 'the opponent\'s throw-break state clear')}
# "player / opponent is character <roster id>" requirements; the first two of each game are the owner's. Tekken 8's
# 224 is the owner's too (TTT2's 206, by the id maps: "the player's motion row is <param>", Jun's moves test 206(42)
# where Reina's test 224(28)), its parameter a Tekken 8 roster id (8 Kazuya, 34 Lidia, ...): folded at conversion
OWNER_IS, OWNER_IS_NOT = {'t7': {217}, 't8': {220, 224}}, {'t7': {218}, 't8': {221}}
CHAR_IS, CHAR_IS_NOT = {'t7': {217, 219, 223}, 't8': {220, 222, 226}}, {'t7': {218}, 't8': {221}}
# Tekken 7's screw state does not exist in TTT2: its requirement and properties become TTT2's bound. The alignment
# has no evidence for these ids; the pairs are format facts as the community's moveset tools record them (README:
# Acknowledgements)
SCREW = {'t7': 615, 't8': 724}
BOUND = 467
REQ_OVERRIDE = {g: {SCREW[g]: BOUND} for g in SCREW}
# Tekken 7's "opponent airborne" (TTT2's 466 through the id maps). Where TTT2 bounds, Tekken 7 often slams instead:
# [614 -> slam][614 -> air][default] in Tekken 7, [467 -> bound][466 -> air][default] in TTT2 for the same three moves
# of Heihachi's (df+1,2 among them); the reaction map makes the slam the donor's bound reaction, so such an entry gets
# TTT2's 467 test too (convert/tagsystem.py gated_slam)
T7_AIR = {'t7': 614, 't8': 723}
# Direction tests: TTT2's requirement function (sub_0404FF30) has four sets of four, front first, back last, at 81..96
# (*(r24), *(r24 + 4), the quadrant of an angle (sub_05C5D9B4), the hit's direction *(r20)) and 97 (TTT2 only);
# Tekken 7 has the same four sets at 84..99 (100 = TTT2's 98), Tekken 8 too (its ids up to 131 are Tekken 7's). The
# alignment anchors only 87 -> 84 and 100 -> 98, so 88..99 fell between them and every list using one became false:
# Negan's Face Grinder (f+2,2 on a hit from the front: 96) never grabbed, and 32 hit-confirm follow-ups and hit-grabs
# of 11 fighters were lost alike.
for _g in REQ_OVERRIDE:
    REQ_OVERRIDE[_g].update({c: c - 3 for c in range(88, 100)})
# Latches: per-move variables a move's own cancel rows set and test (a button pressed early, played out at a later
# frame: hellsweep, 2 is d/f+4 then `2 [(358, 0), (0x80c5, 1)]` in frames 1-15 and `[(358, 1), (359, 0)] -> d/f+4,2`
# at frame 21; once-only rows `[(latch, 0), (set latch, 1), ...]`). Both games have them, as format facts of their
# requirement and property functions: TTT2 four at player+500..512, tested by 313..316 (== param; sub_0404FF30's cases
# read +288 +212..224), set / added to / subtracted from by 0x8096 + 3k / +1 / +2 (sub_03AE86A0's table: id - 0x8058,
# handlers at 0x03AF105C..); Tekken 8 twenty at +0x580 (Reina's ids: 358..361 test the first four, == param; 476 any
# one, `param` 1-based, == param2; 0x80c5 + 3k / +1 / +2 set / add / subtract the first four, 0x8152..0x8154 any one
# (value the variable, value2 the amount): cases 0x14187b0c4.., handlers 0x141897fd4.. (table id - 0x8001 at
# 0x1418a3f20)). Tekken 8's first four are TTT2's four (each cleared as a move starts: in game, Furin Kazan's #1615
# sets latch 2 to 2 and goes on to #1616 on it, which starts with 0); the others have no TTT2 counterpart (476 and
# REQ_T8ONLY then: never set, so 0). The id maps had found 358 -> 313 alone (and paired 360 with it as well): 359's
# rows were false, so hellsweep, 2 never came out
LATCHES = 4
LATCH_REQ = {'t8': 358, 'ttt2': 313}                 # the first latch's test (== param)
LATCH_PROP = {'t8': 0x80c5, 'ttt2': 0x8096}          # the first latch's set, add, subtract
LATCH_ANY_REQ, LATCH_ANY_PROP = {'t8': 476}, {'t8': 0x8152}      # (variable, value) forms: test; set, add, subtract
REQ_OVERRIDE['t8'].update({LATCH_REQ['t8'] + k: LATCH_REQ['ttt2'] + k for k in range(LATCHES)})
LATCH_PROPS = {'t8': {LATCH_PROP['t8'] + j: LATCH_PROP['ttt2'] + j for j in range(3 * LATCHES)}}
REQ_OVERRIDE['t8'].update(LATCH_PROPS['t8'])         # (properties inside requirement lists)
# Tekken 8's contact test 43 (the attack connected, player +0xf5c & 0x100, and the opponent's state +0x10c & 5 == 1)
# is its 44 without 44's last condition (the opponent's bit 3 clear: case code 0x141875f87 / 0x141875fbf); the id maps
# pair 44 with TTT2's 46 (1324 rows of the generic moves) but have no row for 43, which only her own moves test (on
# contact: Inverse Deva Laser's second part #1621 -> #1622, Eisaimon's early 1RP2, the #775 chain): TTT2's 46 too
REQ_OVERRIDE['t8'][43] = 46
# The donor's cancels into TTT2-only generic moves (merge_donor_extras: a generic move name Tekken 7 has not; the tag
# system's) go into the fighter's hub moves. Tekken 8 renamed or reworked many generic moves Tekken 7 and TTT2 share
# (jump attacks Co_jplp00F -> its own Zbr_9LP, the crouching d/f+3 Co_syalkF, the throws ThrmvLB2_00, the Ki charge
# Ju_SUPER_0, running attacks Co_R_rk00R) and, with no Tekken 7 names to tell, those count as TTT2-only too: the
# donor's rows came first in her stance and played the donor's moves for her own u/f+1, d/f+3, 1+2+3+4 and b+1+3
# (Tatenashi became a throw). So for a Tekken 8 fighter a donor row whose input her own converted list already answers
# (the same buttons, each of its directions among her rows' of those buttons) is left out; Tag and the other inputs
# Tekken 8 has not stay
OWN_INPUT = {'t7': False, 't8': True}
ALL_DIRECTIONS = 0x3FE                                # d/b .. u/f (a cancel's direction 0: any)
# A property inside a requirement list is an action TTT2's evaluator takes as true (sub_0404FF30 at 0x0404FFA0: an id
# with 0x8000 set returns 1), never a condition: one that has no TTT2 counterpart is left out of the list, not the
# list made false (effects, sounds, camera zooms, stop motion; 1145 cancels of the 15 fighters) - except these, which
# keep a state the list's other conditions may depend on
REQ_PROP_KEEP = {'t7': {0x8107}, 't8': set()}
# a requirement whose parameter is a move id (the list is false when that move is not converted)
MOVE_PARAM = {'t7': 0x81dc, 't8': 0x824c}
# FIT: Tekken 8's values pass the id maps as they are, in Tekken 8's own numbering where an id's meaning has one TTT2
# has not (item, face animation and move numbers, roster ids). A converted row of a Tekken 8 fighter whose value (a
# requirement's parameter) lies outside the values TTT2's own movesets pass with its TTT2 id, lowest to highest (in
# the same kind of list: idmaps.ttt2_values; an id they never pass a value with: none fits) is left out, a requirement
# making its list false (an action in a requirement list is left out, the list kept). Values the converter converts
# itself (VALUE_KIND, sounds, projectiles, move ids, characters) and the ids of the overrides (format facts) are not
# tested. Reina: 0x803d -> 0x8022 (1233 .. 3856 where TTT2 passes 0 .. 35), 0x8219 -> 0x8110 (1: TTT2 passes 0),
# 0x8084 -> 0x8056 (TTT2's movesets never use it), her own 143 -> 139 (100: TTT2 tests 17 .. 46), ...
PARRY = {'t7': {817, 823}, 't8': set()}            # parry lists: not converted
# the meter (Tekken 7's EX moves and supers): its requirement and its cost; left out with free_meter_specials
METER, METER_COST = {'t7': 629, 't8': 738}, {'t7': 0x81c2, 't8': 0x8232}
EFFECT_PROP = 0x801f                 # spawn an effect: value = body part << 8 | effect id
# Tekken 7 spawns effects with 0x8036 (the id maps find 0x801f) and, in a few moves, 0x8038 (the same value). Tekken 8
# spawns them with 0x8039 (its 0x8036, the id maps find 0x801f too) but numbers its own effects, which nothing converts
# (the pack has no effects of a Tekken 8 fighter): left out (PROP_DROP)
PROP_OVERRIDE = {'t7': {0x8255: 0x8193, 0x8256: 0x8194, 0x8038: EFFECT_PROP}, 't8': {0x82c5: 0x8193, 0x82c6: 0x8194}}
PROP_OVERRIDE['t8'].update(LATCH_PROPS['t8'])        # the latches' properties (LATCHES), as extra properties too
# Electrics (the Mishimas' Electric Wind God Fist and its like). TTT2's own (Kazuya's Kz_shoryu_S; Heihachi's, Jin's
# and Devil Jin's alike) carry: 0x8192 = 1 from the start (ELECTRIC_PROP: player +928 bit 0x2000, the electric spark
# of sub_03AE2254), the common spark sound at frame 2 (0x82f9 0x0100002b: se_Btl_Battle's RES_BANK_SPK_L01, the same
# for every fighter), the hit's sounds as actions of the first cancel row's requirement list (0x82f9 0x01000018
# RES_BANK_PCH_LT02 and 0x07000010, which Tekken 8 splits alike: req_value), and the fighter's own lightning: its
# unique effect (item database id 0, kaz/alo/eff_koyuu00) on the striking arm's shoulder (0x801d 7: bone 7, KATA_R)
# 5 frames before the hit (Kazuya, Jin, Devil Jin: frame 6 of 11). Tekken 8 marks its electrics the same way (0x82c4
# = 1, beside 0x82c5 / 0x82c6 = TTT2's 0x8193 / 0x8194; Reina's EWGF and Electric Wind God Step 4 and their Heat
# versions, Kazuya's EWGF) with the same sounds, but draws its lightning with its own effects, which nothing
# converts: a Tekken 8 electric that strikes (an active frame, a hit point on a limb) spawns Kazuya's lightning
# instead (effect id ELECTRIC_EFFECT, which the importer gives the pack: a copy of his TTT2 file ELECTRIC_LOOK and its
# texture) at the root of the limb it hits with (ELECTRIC_ROOT, from the hit box's first point), ELECTRIC_LEAD frames
# before its first active frame. Tekken 7's electrics keep their own effects (converted by particles.py).
ELECTRIC_MARK = {'t7': None, 't8': 0x82c4}
ELECTRIC_PROP = 0x8192
PROP_OVERRIDE['t8'][ELECTRIC_MARK['t8']] = ELECTRIC_PROP
ELECTRIC_EFFECT = 99                 # an id neither the donors' databases (0..10, 100) nor Tekken 7's effects use
ELECTRIC_LOOK = 'kaz/alo/eff_koyuu00.alo'
ELECTRIC_LEAD = 5
# a hit point's limb (TTT2's skeleton records, as hit locations 0..21 and effect parts number them) -> the limb's root:
# hand / forearm -> shoulder (KATA_R 7, KATA_L 11), foot / knee / toe -> thigh (MOMO_R 14, MOMO_L 17)
ELECTRIC_ROOT = {8: 7, 9: 7, 12: 11, 13: 11, 15: 14, 16: 14, 20: 14, 18: 17, 19: 17, 21: 17}
# properties left out (presentation or mechanics TTT2 has not, or values not converted yet)
PROP_DROP = {
    't7': {0x828f: 'tiger animation', 0x828e: 'projectile index', 0x81bd: 'power crush',
           0x81be: 'rage art fx', 0x801b: 'rage drive vfx', 0x8233: 'rage drive bg', 0x8234: 'rage drive bg',
           0x8272: 'spend rage', 0x828b: 'game speed', 0x828c: 'slow motion', 0x828d: 'slow motion immunity',
           0x829d: 'HUD', 0x829f: 'subtitles', 0x8243: 'subtitles', 0x82bf: 'assist vfx',
           0x8414: 'assist combo value', 0x842e: 'hand animation (Tekken 7 hand codec not converted)',
           0x842f: 'hand animation', 0x8435: 'camera/item animation id', 0x8049: 'item id', 0x8343: 'attach item',
           0x8344: 'detach item'},
    't8': {0x82ff: 'tiger animation', 0x82fe: 'projectile index', 0x822d: 'power crush',
           0x822e: 'rage art fx', 0x801b: 'rage drive vfx', 0x82a3: 'rage drive bg', 0x82a4: 'rage drive bg',
           0x82e2: 'spend rage', 0x82fb: 'game speed', 0x82fc: 'slow motion', 0x82fd: 'slow motion immunity',
           0x830d: 'HUD', 0x830f: 'subtitles', 0x82b3: 'subtitles', 0x832f: 'assist vfx',
           0x855c: 'assist combo value', 0x8610: 'hand animation (Tekken 8 hand animations not converted)',
           0x8611: 'hand animation', 0x8688: 'camera/item animation id', 0x804c: 'item id', 0x848b: 'attach item',
           0x848c: 'detach item', 0x8039: 'effect (Tekken 8 effects are not converted)',
           # (the id maps' TTT2 0x82d5..0x82d7: high byte an animation of the motion pack's face container, the
           # donor's, 54 of Jun's; Tekken 8's numbers go to 69 and are its own: the donor's moves keep their faces,
           # hers play none, as with the hands)
           0x860a: 'face animation (Tekken 8 face animations not converted)', 0x860b: 'face animation',
           0x860c: 'face animation'},
}
SOUND_PROPS = {'t7': {0x84c4, 0x84c6}, 't8': {0x87f0, 0x87f1, 0x87f2}}   # value = bank << 24 | n: kept only where
# the donor uses the same value, or a voice of the fighter's own banks (convert/voice.py): shout n (bank 2) and damage
# voice n (bank 3), numbered alike in both games (their SE_KIAI_n / SE_YARARE_n test moves): shouts up to the fighter's
# count (the donor's and the ones voice.py appends; `shouts`), damage voices up to the last number TTT2 has. Tekken 8
# splits the value: the bank in `value`, n in `value3` (`value2` 0, or 100 with bank 17): the sounds of the moves Reina
# and Tekken 7 Heihachi share are (bank, n) alike in banks 1, 2, 6, 7, 9 and 10; Tekken 8's banks 15 and 17 (where
# Tekken 7 plays bank 7, or a voice of bank 2 / 3) are its own, so the donor never has them. Its moves play their voice
# with bank 16 (n: a sound id of the fighter's) and 17 (n: a kind, value2 the chance): VOICE8_BANKS, converted to the
# TTT2 voice that plays the same line (voices8: tekken8/voice.py's move_voices), else left out
SPLIT_SOUND = {'t7': False, 't8': True}
OWN_VOICE = {2: 0xE, 3: 0xA}
VOICE8_BANKS = (16, 17)
# Tekken 8 says some lines against one fighter (requirement 505: the opponent is <roster id>; 506 is not): Reina's
# Other_013 .. 018 against Heihachi (35) in moves whose other line (Attack_Line_004, ...) everyone else hears. TTT2's
# property rows have no conditions: the other line is said always, the one against the fighter left out
VERSUS8 = (505, 506)
# The opponent's voice (0x87f2: a thrown or parried opponent's cry) plays through the opponent's own voice list: of
# the kinds Tekken 8's moves give it (3 and 4 damage, 11 surprise: bank 17), TTT2's damage voice 0, as TTT2's own
# throws play the opponent's (Jun's 0x82fb 0x03000000 where Reina's 0x87f2 plays 17 / 3); its other voices left out
OPPONENT_VOICE8 = (0x87f2, {3: 0x03000000, 4: 0x03000000, 11: 0x03000000})
# A voice of a kind (bank 17) Tekken 8 says by chance (value2, percent: her jabs' short shout 40 %, most of her
# attacks' 60 to 100 %): said always from CHANCE8 on (TTT2's rows have no conditions), else left out (TTT2's own jabs
# say nothing: a shout on every jab would be the most of her voice)
CHANCE8 = 50
# A move's voice clip list (said as it starts): TTT2 marks a move that says nothing there with shout 999 (2 << 24 |
# 999, past every shout count: nothing plays); a move whose list says no shout at all gets a random short or medium
# one from the title on about half of its starts (an attack's: sub_077549A8). Tekken 8 says its moves' voices with
# sound properties (VOICE8_BANKS), and its voice clip lists hold only its own mark of saying nothing, shout 0x9986
# (2 << 24 | 0x9986: 345 of Reina's moves, every attack of hers; 3 << 24 | 0x9986 on 25 more, which TTT2 has no use
# for): the mark becomes TTT2's (left out, her attacks shouted at random besides the lines of their own)
UNSAID8, SILENT_SHOUT = 0x02009986, 0x020003E7
# A win quote: TTT2's win poses play a tone of the fighter's se_Dwi bank with this property (value | tone); Tekken 7
# plays its win quote by the pose's name. The donor's poses stay, with the animation of the quote at their tone.
WIN_QUOTE_PROP, WIN_QUOTE_VALUE = 0x82F9, 0x0E003000
# Tekken 7's tiger (or any other summoned model) plays an animation of its own: 0x828f = the animation's index. TTT2
# plays an animation of a fighter's extra (OPT) bones from part 3 of its motion pack with 0x82de = 0x4000 + its
# index there (0x82df does the same in win poses only, 0x82e0 under another condition: Devil Jin's wings); the added
# fighter's tiger is such a set of bones (convert/tiger.py), so 0x828f becomes 0x82de where the converter knows the
# tiger animation's index (opt_anims), else it is left out.
TIGER_PROP = {'t7': 0x828f, 't8': None}
OPT_ANIM_PROP, OPT_ANIM_BASE = 0x82de, 0x4000
VALUE_KIND = {'t7': {0x8331: 'reaction', 0x8332: 'reaction', 0x843c: 'throwcam', 0x843d: 'throwcam',
                     0x820b: 'projectile'},
              't8': {0x8478: 'reaction', 0x8479: 'reaction', 0x868f: 'throwcam', 0x8690: 'throwcam',
                     0x827b: 'projectile'}}
# Projectiles (Kazumi's tiger). Tekken 7 spawns one with five properties on the same frame: limb 0x820c, offsets
# 0x820d/0x820e/0x820f, then 0x820b = the projectile's index. TTT2 has the same set at 0x8169 (limb; resets the
# offsets), 0x816a/0x816b/0x816c (offset = the value as a signed 16-bit number) and 0x8168 (spawn projectile
# <value>): handlers in its property interpreter (sub_03AE86A0), used in the same order by its balloon and cloche
# items. The alignment has no evidence for these ids (no Heihachi move spawns a projectile). Tekken 8's are 0x827b..f
# (the Tekken 8 reader gives its projectile rows in Tekken 7's form, `raw`).
TT_PROJ_SPAWN, TT_PROJ_LIMB, TT_PROJ_OFFSETS = 0x8168, 0x8169, (0x816a, 0x816b, 0x816c)
PROJ_SPAWN, PROJ_BONE = {'t7': 0x820b, 't8': 0x827b}, {'t7': 0x820c, 't8': 0x827c}
PROJ_PROPS = {g: dict([(PROJ_SPAWN[g], TT_PROJ_SPAWN), (PROJ_BONE[g], TT_PROJ_LIMB)] +
                      list(zip(range(PROJ_BONE[g] + 1, PROJ_BONE[g] + 4), TT_PROJ_OFFSETS))) for g in PROJ_SPAWN}
# A projectile's look: Tekken 7 draws a missile actor (the character blueprint's missile of the row's field 2) that
# flies with the projectile; TTT2's projectile rows name an effect of a common table, not the fighter's. So the
# spawning move also spawns, right after the projectile, an effect of the fighter's (an id from PROJECTILE_EFFECTS on)
# with the missile's particles, which the runtime keeps where that projectile is until it is gone (roster.cpp's level
# effects): one id per (missile, life).
PROJECTILE_EFFECTS = 230
THROWING_HAND = 13                   # body part TE_L: where a thrown weapon's look is before its projectile moves
EFFECT_PARTS = 21                    # body parts TTT2 places effects on (its skeleton's first records); others: 0
TTT2_EFFECT_PARTS = {27}             # ... and the parts above them TTT2's own moves use (asa, kaz, knm, cbt)
# Hit locations the id maps leave out (no TTT2 code pairs with them often enough) that have no position in TTT2 (its
# hit test places codes 0..77; facts: a move's hit box is two pairs of points, (point, 0) a single one): Tekken 8's
# 125, the held item's point of its item moves ((125, 125), TTT2's item moves (70, 9): 70), and 133 / 134, the second
# point of a kick's pair after a foot or knee (Reina's f,f,f+4 (47, 134), 1,2,3 (18, 134), 6WP_9RK (16, 133)), where
# TTT2's same moves have 0 most often (18 of the 48 pairs of 134; 133 has none): 0, the foot or knee alone
HIT_LOCATION = {'t7': {}, 't8': {125: 70, 133: 0, 134: 0}}
# Throw damage: the thrown fighter plays the thrower's victim move (`.._n`), which deals the damage. Tekken 7 sets an
# amount (0x821b, value = points; frame 0x8001 = from the start) and deals a percentage of it at a frame (0x821c, and
# 0x821d alike); TTT2 deals points at the frame (0x8058, 0x8059): the same victim moves of Heihachi in both games
# (e.g. He_OTOKO3n: 0x821b 30, 0x821d 100% at 2, 0x821c 100% at 44 -> 0x8059 30 at 2, 0x8058 30 at 44). A deal of
# 0% is what is left of the amount (He_hp2_n2: 35, 42% at 64, 0% at 76 -> 15 at 64, 20 at 76). Tekken 8 deals with
# 0x828c and two more ids the alignment pairs with Tekken 7's 0x821c.
# Summoned weapons (Noctis's): Tekken 7 shows weapon n from 0x82a7 (value n) and puts it away with 0x82a8 (n, or 16:
# all), its appearing and vanishing particles spawned with 0x82af (n << 16 | effect id). TTT2 has neither: the runtime
# shows the weapons (roster.cpp, weapons) from 0x822E / 0x822F, ids its property interpreter ignores and no TTT2
# moveset uses; the particles become the fighter's effects at the weapon's hand (the definition's weapon 'part').
TT_SUMMON, TT_DISMISS = 0x822E, 0x822F
SUMMON_PROPS = {'t7': {0x82a7: TT_SUMMON, 0x82a8: TT_DISMISS}, 't8': {0x8317: TT_SUMMON, 0x8318: TT_DISMISS}}
SUMMON_EFFECT = {'t7': 0x82af, 't8': 0x831f}
# A thrown weapon that hits stays where it hit (Noctis's Warp-Strike: Tekken 7 dismisses the sword as it hits, with
# particles of its mesh lingering there, which convert/particles.py leaves out): the move a hit leads to (the
# definition's WEAPON_HOLD, by Tekken 7 name) starts with this property (another id TTT2 ignores and no moveset uses),
# and the runtime keeps the thrown weapons there, drawn though dismissed, until the warp takes them back (roster.cpp,
# weapons)
WEAPON_HOLD_PROP = 0x822B
EFFECT_STEP = 6                      # frames: effect ends closer than this share a copy (split_effects)
EFFECT_SPARE = range(229, 160, -1)   # ids for the copies: above Tekken 7's (100..160), below the projectiles' (230)
DAMAGE_AMOUNT = {'t7': 0x821b, 't8': 0x828b}
DAMAGE_DEAL = {'t7': {0x821c: 0x8058, 0x821d: 0x8059}, 't8': {0x828c: 0x8058, 0x838a: 0x8058, 0x838f: 0x8058,
                                                              0x828d: 0x8059}}
# Tekken 7's 2D arcs (convert/arcs.py; Tekken 8 has no 2D fighter, and its 0x8226 / 0x8227 are other properties)
ARCS = {'t7': (arcs.ARC, arcs.AIR_MOVE), 't8': (None, None)}
# A projectile row, Tekken 7 (42 x u32) -> TTT2 (34 x u32): (TTT2 field, Tekken 7 field, count). TTT2's fields as
# its projectile code reads them: 0 effect, 1 delay, 2 forward speed, 3 upward speed, 4 hits it can deal, 5 frames
# it lives, 6 shape (0 sphere, 1 cylinder), 7 radius, 8 height, 9 hit level, 14 sound at spawn, 16 sound on hit,
# 18 sound when it runs out, 19 hit conditions, 20 cancels (both table indices, 0 = none), 21 hits the owner's
# team, 22 hits the other team, 23..33 a hit effect (on when 23 != 0 and 26 > 0). Tekken 7's are the same with
# five more fields after the effect and 64-bit links (hit conditions at 24, cancels at 26).
PROJ_FIELDS = [(1, 6, 3), (4, 9, 15), (21, 28, 13)]
# A weapon Tekken 7 throws by animation (Kunimitsu II's kunai: the hand's extra pairs carry it up to 7 m out, its hit
# locations ride on it) misses in TTT2 at range: the lever multiplies any difference between the hand TTT2 poses and
# the one the animation was made for (TTT2's hit test has no range limit: sub_03ADBD10 -> sub_039C006C is geometry
# only). Such a move (the definition's THROWN) throws a TTT2 projectile instead: a cylinder flying straight ahead,
# spawned at the frame from the hips (limb 0) with the offsets (forward, up), with the move's own hit condition and hit
# level (the low half), hitting the other team once; the move keeps its animation and loses its hit boxes.
THROWN_SOUND = 0x07000010           # the hit sound TTT2's projectile rows use (Kazumi's tiger strikes)
PROJ_SOUNDS = (14, 16, 18)
PROJ_EFFECT = 0                 # Tekken 7's effect ids mean nothing in TTT2: none
# Animations. Tekken 7's are found by their bytes: one TTT2 already has (its common motions, the donor's pack) is
# referenced, any other appended (byte-swapped). Tekken 8's are PANM (tekken8/panm.py) and come from an animation
# provider (the converter's `animations`, by default the moveset's ttt2_animation): called with a move's anim_ref
# (key, bank) -> one TTT2 animation (bytes, big-endian: what motion.extend_mota appends), an animation id TTT2 already
# has (0x8000 | i common, 0x4000 | i the donor's pack), or None (none: the move keeps the donor stance's). A move
# whose animation key a 'G' move of the fighter has too (the same generic animation) plays the donor's animation of
# that move.
ANIM_COMMON, ANIM_PACK = 0x8000, 0x4000
# the fighter's own moves that are not converted: Rage Arts / Drives, story, customisation, cinematics
DROP_MOVES = r'RageArts|_EX\d?$|^b7_|^vra_|_7CS$|^Story|^FACE'
# Tekken 7 generic moves (also Heihachi's, not in TTT2) converted when a reaction needs them, except these
DROP_T_RE = re.compile(r'Balcony|_RA$|RAtk|RageArt|^vra_|_7CS$|^SE_|^FACE|Story|^b7_')
ANIM_KEY_BYTES = 256                 # animations are matched by a hash of their first bytes


def rev32(v):
    return int('{:032b}'.format(v)[::-1], 2)


def classify(k, h7, donor):
    """Per move of the Tekken 7 fighter: 'G' generic (the donor has it), 'T' Tekken 7 generic (Tekken 7 Heihachi
    has it), 'K' the fighter's own."""
    g = set(donor.move_name(i) for i in range(len(donor.tables['moves'])))
    t = set(h7.move_name(i) for i in range(len(h7.tables['moves'])))
    return ['G' if n in g else ('T' if n in t else 'K') for n in (k.move_name(i) for i in range(len(k.tables['moves'])))]


def own_prefix(k):
    """The fighter's own move name prefix ('Zbr' for Tekken 8's zbr: Zbr_sKAM00_), or None."""
    p = getattr(k, 'own_prefix', None)
    if p is None and getattr(k, 'code', None):
        p = k.code[:1].upper() + k.code[1:].lower()
    return p


def classify8(k, donor):
    """Per move of a Tekken 8 fighter (no Tekken 7 needed): 'G' the donor has its name, 'T' a generic name (not the
    fighter's own prefix) the donor lacks, 'K' the fighter's own (its own prefix, in lower case too: its intros and
    win poses, zbr_s00, zbr_w01; or unnamed with an animation of its own bank), 'N' unnamed with an animation of the
    common bank (a Tekken 8 generic move TTT2 has no name for: it is converted only when one of the fighter's own
    moves or a reaction needs it, Converter.target)."""
    g = set(donor.move_name(i) for i in range(len(donor.tables['moves'])))
    own = (own_prefix(k) or '\0') + '_'
    out = []
    for i in range(len(k.tables['moves'])):
        n = k.move_name(i)
        if not n or n.startswith(UNNAMED):
            out.append('K' if k.anim_ref(i)[1] == 'own' else 'N')
        else:
            out.append('K' if n.startswith((own, own.lower())) else 'G' if n in g else 'T')
    return out


def generic_animations(k, cls, donor_anim):
    """{Tekken 8 animation key: the donor's animation} of the common-bank clips the 'G' moves of Tekken 8 fighter k
    play (cls: classify8's; donor_anim(i): the donor's animation of 'G' move i), the first such move's. A 'G' move
    playing one of the fighter's own clips borrows it (Reina's sWALK_00BMv plays her stance): the donor's animation
    of that move would replace her own clip in her own moves, so those clips are left out."""
    out = {}
    for i, c in enumerate(cls):
        key, bank = k.anim_ref(i) if c == 'G' else (None, None)
        if key is not None and bank == 'com':
            out.setdefault(key, donor_anim(i))
    return out


def _anim_key(buf):
    return hashlib.sha1(buf[:ANIM_KEY_BYTES]).hexdigest()


def anim_index(sources):
    """sources: [(tag, data, MOTA offset)] -> {key: [(tag, index)]}"""
    idx = collections.defaultdict(list)
    for tag, d, o in sources:
        for i, a in enumerate(motion.mota_offsets(d, o)[1]):
            idx[_anim_key(d[o + a:o + a + ANIM_KEY_BYTES])].append((tag, i))
    return idx


class Converter:
    # (a Tekken 7 source unless __init__ finds another game)
    game, end, prefix = 't7', T7_END, None
    linking = 0                         # > 0 while the links of the fighter's own (or converted) moves are made
    _fit = None                         # FIT's ranges: {'req' / 'prop': {TTT2 id: (lowest, highest)}}, when needed

    def __init__(self, k, h7, donor, donor_pack, h2, common_motions, maps, usage, newid, d):
        """k: the fighter's moveset (Tekken 7: tkmvst.read; Tekken 8: tekken8.motbin.read, its moves named),
        h7: Tekken 7 Heihachi's (Tekken 7 only; None for Tekken 8); donor: the donor's motbin (motbin.read) and its
        motion pack; h2: TTT2 Heihachi's motbin; common_motions: data004's common MOTA; maps: (requirement map,
        property map, reaction remap, hitbox remap) of k's ids (idmaps.build_maps, tekken8_maps); usage:
        idmaps.ttt2_usage; newid: the new fighter's motion row; d: the character definition."""
        self.k, self.h7, self.d, self.h2 = k, h7, donor, h2
        self.game = getattr(k, 'game', 't7')
        if self.game not in REQ_FALSE:
            raise ValueError('no conversion rules for movesets of game %r' % self.game)
        self.end = M.END_REQ[self.game]
        self.donor_pack = donor_pack
        self.common_motions = common_motions
        self.newid = newid
        self.k_id = k.character_id
        self.defn = d
        self.req_map, self.prop_map, self.react_remap, self.hitbox = maps
        self.hit_locations = {}         # Tekken 7 hit location -> TTT2's, before the id maps' (weapons.py)
        self.summons = {w['summon']: w for w in getattr(d, 'WEAPONS', []) if w.get('summon') is not None}
        self.posed = set()              # the donor's intro and win pose moves playing the fighter's animations
        self.usage = usage
        self.stats = collections.Counter()
        self.unmapped = collections.Counter()
        self.T = copy.deepcopy(donor.tables)
        self.strings = bytearray(donor.raw[motbin.BASE:motbin.BASE + donor.table_info['reactions'][0]])
        while self.strings and self.strings[-1] == 0:      # trailing alignment
            self.strings.pop()
        self.strings.append(0)
        self.str_off = {}
        self.dn = {donor.move_name(i): i for i in range(len(donor.tables['moves']))}
        self.kn = {self.name(i): i for i in range(len(k.tables['moves']))}
        self.cls = classify(k, h7, donor) if self.game == 't7' else classify8(k, donor)
        self.prefix = own_prefix(k) if self.game == 't8' else None
        # Some character-specific attacks reuse a generic move name in T7.
        # Let a definition retain those attacks instead of losing their input.
        own_moves = d.MOVESET.get('own_moves')
        if own_moves:
            for i in range(len(self.cls)):
                if re.search(own_moves, k.move_name(i)):
                    self.cls[i] = 'K'
        self.effect_ids = set()                                    # the Tekken 7 effect ids the moves spawn
        self.effect_rows = []              # (property row, Tekken 7 effect id, frames left of its move or None)
        self.projectile_effects = {}                               # effect id -> its projectile (projectile_look)
        self.electric_moves = []           # the (Tekken 8) electrics given Kazuya's lightning (electric_rows)
        self.thrown = getattr(d, 'THROWN', {})                    # move name -> its projectile (thrown_rows)
        # Tekken 7 plays some moves' animations as deltas on another's ("_sabun": Akuma's forward and back jumps
        # over his neutral jump); TTT2 has no such layers and plays them as poses (on the floor). Such a move
        # stays the fighter's own (his 2D-style jumps are not Tekken's) and plays the whole animation it is a
        # delta of (the name without _f/_b_sabun), or, when it starts a 2D arc, the delta made absolute
        # (bake_arcs); without one, it becomes the donor's move of its name without the fighter's prefix.
        anims = {k.anim_name(i): k.tables['moves'][i]['anim'] for i in range(len(k.tables['moves']))}
        self.delta_move, self.delta_anim = {}, {}
        for i in range(len(k.tables['moves'])):
            a = k.anim_name(i)
            if '_sabun' not in a.lower() or self.cls[i] != 'K':
                continue
            generic = re.sub(r'^[A-Z][a-z0-9]_', '', k.move_name(i))
            whole = re.sub(r'_[fb]_sabun', '', a, flags=re.I)
            if whole in anims:
                self.delta_anim[k.tables['moves'][i]['anim']] = anims[whole]
            elif generic in self.dn:
                self.delta_move[i] = self.dn[generic]
        t7names = set(self.kn) | (set(h7.move_name(i) for i in range(len(h7.tables['moves']))) if h7 else set())
        h2names = set(h2.move_name(i) for i in range(len(h2.tables['moves'])))
        self.ttt2_only_generic = {n for n in self.dn if n in h2names and n not in t7names}
        self.cache = {}
        self.donor_sound = collections.defaultdict(set)
        for t in ('extra_move_properties', 'move_begin_props', 'move_end_props'):
            for x in donor.tables[t]:
                self.donor_sound[x['id']].add(x['value'])
        self.donor_clips = {v['value'] for v in donor.tables['voiceclips']} - {0xFFFFFFFF}
        self.known_sounds = set(self.donor_clips)
        for pid in (0x82f9, 0x82fb):                 # player / opponent sound
            self.known_sounds |= self.donor_sound[pid]
        self.voice = True               # the fighter has its own voice banks (convert/voice.py)
        self.shouts = OWN_VOICE[2] + 1  # its shouts' count (the importer sets it from voice.build)
        self.voices8 = {}               # Tekken 8: {(bank, n): [TTT2 voices]} of its moves' voices (the importer's)
        self.voice_turns = collections.Counter()      # (a kind's voices are taken in turn)
        self.tag_states = None          # TTT2's movement (tag-out) states by move name (tagsystem.TagStates)
        self._reachable = self.donor_states = None
        self.opt_anims = {}             # Tekken 7 tiger animation index -> its index in motion pack part 3
        self.part3 = None               # the motion pack's part 3 (animations of extra bones), else the donor's
        # animations already in TTT2: the common motions and the donor's own pack (Tekken 7, by their bytes); a
        # Tekken 8 fighter's from the animation provider (ANIMATIONS), its generic ones the donor's
        o0 = motion.pack_items(donor_pack)[0][0]
        self.anim_src = {}
        if self.game == 't7':
            idx = anim_index([('common', common_motions, 0), ('donor', donor_pack, o0)])
            self.anim_src = {off: idx.get(_anim_key(motion.swap_animation(k.animbuf[off:off + k.anim_size[off]], '<')),
                                          []) for off in k.anim_offsets}
        self.animations = getattr(k, 'ttt2_animation', None)
        self.generic_anim = {}          # Tekken 8 animation key -> the donor's animation of a 'G' move playing it
        if self.game == 't8':
            self.generic_anim = generic_animations(
                k, self.cls, lambda i: donor.tables['moves'][self.dn[k.move_name(i)]]['anim'])
        self.pack0_count = len(motion.mota_offsets(donor_pack, o0)[1])
        self.new_anims, self.anim_id = [], {}
        self.converted8 = set()         # positions in new_anims of converted Tekken 8 clips (handoffs8)
        self.seq_index = {}
        T = self.T
        for i, s in enumerate(T['input_sequences']):
            key = (s['window'], tuple((x['direction'], x['button'])
                                      for x in T['inputs'][s['inputs']:s['inputs'] + s['amount']]))
            self.seq_index.setdefault(key, i)
        self.extra_index = {}
        for j, e in enumerate(T['cancel_extras']):
            self.extra_index.setdefault(e['value'], j)
        dropped = DROP_MOVES.replace(r'|_EX\d?$', '') if d.MOVESET.get('free_meter_specials') else DROP_MOVES
        self.drop_moves = re.compile('|'.join([dropped] + ([d.MOVESET['drop_moves']] if d.MOVESET.get('drop_moves')
                                                          else [])))
        self.ground_arcs = {}           # Tekken 7 move -> (frame, value) of its 0x8226 to bake (convert/arcs.py)

    # --- helpers ----------------------------------------------------------------------------------------
    def string(self, s):
        if s not in self.str_off:
            self.str_off[s] = len(self.strings)
            self.strings += s.encode('latin1') + b'\0'
        return self.str_off[s]

    def add(self, table, row):
        self.T[table].append(row)
        return len(self.T[table]) - 1

    def move_name(self, i):
        """The name of move i of the new moveset."""
        off = self.T['moves'][i]['name']
        return self.strings[off:self.strings.index(b'\0', off)].decode('latin1')

    # --- ids --------------------------------------------------------------------------------------------
    def map_req(self, c):
        """A requirement id of the fighter's game (or a property id inside a requirement list) -> TTT2's, or None."""
        g = self.game
        if c == self.end:
            return TT_END
        if c in REQ_OVERRIDE[g]:
            return REQ_OVERRIDE[g][c]
        if c in REQ_FALSE[g]:
            return None
        b, how = (self.req_map if c < 0x8000 else self.prop_map).lookup(c)
        if how in M.MAPPED and b is not None:
            if b in self.usage['req' if b < 0x8000 else 'prop']:
                return b
            self.stats['requirement id no TTT2 moveset uses -> false'] += 1
            return None
        self.unmapped[('req' if c < 0x8000 else 'req-prop', c)] += 1
        return None

    def map_prop(self, p):
        g = self.game
        # T7's meter delta (negative on EX/super entry); free-meter opt-ins
        # must not remap it onto an unrelated native property.
        if p == METER_COST[g] and self.defn.MOVESET.get('free_meter_specials'):
            return None
        if p == TIGER_PROP[g] and self.opt_anims:
            return OPT_ANIM_PROP
        if p in PROP_OVERRIDE[g]:
            return PROP_OVERRIDE[g][p]
        if p in PROJ_PROPS[g]:
            return PROJ_PROPS[g][p]
        if p in PROP_DROP[g]:
            self.stats['property dropped: ' + PROP_DROP[g][p]] += 1
            return None
        b, how = self.prop_map.lookup(p)
        if how in M.MAPPED and b is not None:
            return b
        self.unmapped[('prop', p)] += 1
        return None

    def guarded(self, c):
        """The values of the fighter's id c pass the id maps as they are, so FIT tests them (a Tekken 8 fighter's)."""
        g = self.game
        return g == 't8' and not (c in VALUE_KIND[g] or c in SOUND_PROPS[g] or c in PROJ_PROPS[g] or
                                  c in PROP_OVERRIDE[g] or c in REQ_OVERRIDE[g] or c == MOVE_PARAM[g] or
                                  c in CHAR_IS[g] or c in CHAR_IS_NOT[g])

    def fits(self, kind, b, v):
        """Value v fits TTT2 id b in a list of `kind` ('req' a requirement list, 'prop' a property list): TTT2's
        movesets pass values from lowest to highest with it and v lies there (FIT). True when the usage the converter
        was given has no values (idmaps.ttt2_usage's)."""
        values = self.usage.get('values') if isinstance(self.usage, dict) else None
        if values is None:
            return True
        if self._fit is None:
            self._fit = {k: {x: (min(vs), max(vs)) for x, vs in t.items() if vs} for k, t in values.items()}
        lo, hi = self._fit[kind].get(b, (1, 0))
        return lo <= v <= hi

    def name(self, i):
        """The fighter's move i's name (an unnamed Tekken 8 move's: UNNAMED + its index)."""
        n = self.k.move_name(i)
        return n if n or self.game == 't7' else UNNAMED + str(i)

    def ttt2_name(self, i):
        """The name the fighter's move i has in the new moveset (an unnamed one's with the fighter's prefix)."""
        n = self.name(i)
        return '%s_%s' % (self.prefix, n) if n.startswith(UNNAMED) and self.game == 't8' else n

    def state_label(self, i):
        """Move i's name as TTT2's tag system reads it (tagsystem.state_name): a Tekken 8 fighter's own prefix
        (three letters, Zbr_sWALKF) left out."""
        n = self.name(i)
        if self.prefix and n.startswith(self.prefix + '_'):
            return n[len(self.prefix) + 1:]
        return n

    def shared_input_target(self, mid):
        """A shared T7 gameplay move the donor cannot provide, reached by an input or follow-up."""
        if mid is None or not 0 <= mid < len(self.cls) or self.cls[mid] != 'T':
            return False
        name = self.name(mid)
        return (name not in self.dn and not DROP_T_RE.search(name) and not re.search(DROP_MOVES, name)
                and not name.startswith(('Co_I', 'Wi_I', 'Mt_I')))

    def target(self, mid, input_target=False):
        """A Tekken 7 move id (or alias slot) -> the new moveset's move id, or None."""
        if mid is None:
            return None
        if mid >= 0x8000:
            return mid if mid < 0x8000 + 56 else None     # alias slots mean the same in both games
        if mid >= len(self.k.tables['moves']):
            return None
        if mid in self.newidx:
            return self.newidx[mid]
        if mid in self.delta_move:
            self.stats['moves with a delta animation -> the donor\'s generic move'] += 1
            return self.delta_move[mid]
        n = self.name(mid)
        if n in self.dn:
            return self.dn[n]
        r = self.react_remap.get(n)
        if r and r in self.dn:
            self.stats['target remapped (Tekken 7-only move -> the TTT2 move in its place)'] += 1
            return self.dn[r]
        # Shared attacks (FC jabs/kicks, jump attacks, throw follow-ups) can be absent from the donor too.
        # Import them when a retained input/follow-up reaches them, not only when a reaction needs them.
        if self.cls[mid] == 'T' and not DROP_T_RE.search(n) and (
                self.alloc_ok or self.is_state(mid) or (input_target and self.shared_input_target(mid))):
            idx = len(self.T['moves'])
            self.newidx[mid] = idx
            self.T['moves'].append(self.conv_move(mid))
            self.queue.append(mid)
            reason = 'needed by reactions' if self.alloc_ok else 'input targets' if input_target else 'movement states'
            self.stats['Tekken 7 generic moves converted (%s)' % reason] += 1
            return idx
        # a Tekken 8 generic move TTT2 has no name for: when the fighter's own moves (or a reaction) lead into it
        if self.cls[mid] == 'N' and (self.alloc_ok or self.linking):
            idx = len(self.T['moves'])
            self.newidx[mid] = idx
            self.T['moves'].append(self.conv_move(mid))
            self.queue.append(mid)
            reason = 'needed by reactions' if self.alloc_ok else 'needed by the fighter\'s own moves'
            self.stats['Tekken 8 unnamed generic moves converted (%s)' % reason] += 1
            return idx
        return None

    def reachable(self):
        """The Tekken 7 moves a fighter gets into without a button: from its alias slots (stance, landings, ...)
        through cancels on directions alone and transitions."""
        if self._reachable is None:
            k = self.k
            nm = len(k.tables['moves'])
            seen, todo = set(), [k.resolve_alias(0x8000 + s_) for s_ in range(56)]
            groups = {}
            while todo:
                i = todo.pop()
                if i is None or i >= nm or i in seen:
                    continue
                seen.add(i)
                mv = k.tables['moves'][i]
                todo.append(k.resolve_alias(mv['transition']))
                for c in M.cancels(k, mv['cancel']):
                    if c['direction'] == M.GROUP:
                        if c['move_id'] not in groups:
                            groups[c['move_id']] = [x for x in M.cancels(k, c['move_id'], 'group_cancels', M.GROUP_END)
                                                    if x['direction'] != M.GROUP_END]
                        rows = groups[c['move_id']]
                    else:
                        rows = [c] if c['direction'] != M.LIST_END else []
                    todo += [k.resolve_alias(x['move_id']) for x in rows if x['button'] == 0]
            self._reachable = seen
        return self._reachable

    def is_state(self, i):
        """Tekken 7 move i is a movement state TTT2 lets a fighter tag out of (by TTT2's own movesets' move names,
        tagsystem.TagStates) that the fighter gets into without a button."""
        return self.tag_states is not None and self.tag_states(self.state_label(i)) and i in self.reachable()

    def state_counterpart(self, i):
        """The donor's move whose TTT2-only rows (tag out, tag throws, ...) the fighter's movement state i gets: its
        tag-out move of the same state_name, else its stance (every one of the donor's tag-out states has the same)."""
        if not self.is_state(i):
            return None
        if self.donor_states is None:
            self.donor_states = {}
            for j in sorted(tagsystem.tag_out_moves(self.d)):
                self.donor_states.setdefault(tagsystem.state_name(self.d.move_name(j)), j)
        return self.donor_states.get(tagsystem.state_name(self.state_label(i)), self.d.resolve_alias(0x8001))

    # --- lists ------------------------------------------------------------------------------------------
    def req_rows(self, i):
        """[(condition, param, row)] of the fighter's requirement list at i (its end row left out)."""
        if i is None:
            return []
        return [(r['condition'], r['param'], r) for _, r in
                self.k.iter_list('requirements', i, lambda r: r['condition'] == self.end) if r['condition'] != self.end]

    def latch_row(self, c, row):
        """A requirement row naming a latch by (variable, value) (LATCH_ANY_REQ / LATCH_ANY_PROP: Tekken 8's 476 and
        0x8152..0x8154) -> TTT2's row for it ({'condition', 'param'}), or None (another id, or a variable TTT2 has
        not)."""
        g = self.game
        k = row.get('param', 0) - 1
        if not 0 <= k < LATCHES or 'param2' not in row:
            return None
        if c == LATCH_ANY_REQ.get(g):
            return {'condition': LATCH_REQ['ttt2'] + k, 'param': row['param2']}
        base = LATCH_ANY_PROP.get(g)
        if base is not None and base <= c < base + 3:
            return {'condition': LATCH_PROP['ttt2'] + 3 * k + c - base, 'param': row['param2']}
        return None

    def conv_reqs(self, i):
        """A Tekken 7 requirement list -> (the new list's index, ok); ok False: the list can never be true."""
        if i is None:
            return None, True
        key = ('req', i)
        if key in self.cache:
            return self.cache[key]
        g = self.game
        rows, res = [], None
        for c, p, row in self.req_rows(i):
            if c in (METER[g], METER_COST[g]) and self.defn.MOVESET.get('free_meter_specials'):
                self.stats['meter requirements/costs removed (opt-in)'] += 1
                continue
            # These checks refer to the owner of this moveset, known at conversion time. Native requirement
            # 200 interprets parameters 69..83 as character-family selectors, not equality with our virtual row.
            # Folding only the owner's checks avoids breaking SS attacks when an import takes one of those rows.
            # Opponent checks (219/223) must still be evaluated at run time.
            if c in OWNER_IS[g] or c in OWNER_IS_NOT[g]:
                matches = p == self.k_id
                if matches == (c in OWNER_IS[g]):
                    self.stats['owner character requirements folded true'] += 1
                    continue
                self.stats['owner character requirements folded false'] += 1
                res = (None, False)
                break
            if c in CHAR_IS[g] or c in CHAR_IS_NOT[g]:
                if p == self.k_id:
                    p = self.newid
                elif c in CHAR_IS_NOT[g]:         # "is not <another character>": true
                    self.stats['character requirement "is not X" dropped (true)'] += 1
                    continue
                else:                             # "is <another character>": false
                    self.stats['character requirement "is X" -> false'] += 1
                    res = (None, False)
                    break
            latch = self.latch_row(c, row)
            if latch is not None:                 # one of the latches TTT2 has too, in its (variable, value) form
                self.stats['latch tests and actions (variable, value) -> TTT2\'s latches'] += 1
                rows.append(latch)
                continue
            if g == 't8' and c in REQ_T8ONLY:     # a state TTT2 never has (REQ_T8ONLY)
                field, value, what = REQ_T8ONLY[c]
                if field == 'always' or (row['param'] & 0xFFFF if field == 'param_lo' else row[field]) == value:
                    self.stats['Tekken 8-only requirements true (left out): ' + what] += 1
                    continue
                self.stats['Tekken 8-only requirements -> false: ' + what] += 1
                res = (None, False)
                break
            c2 = self.map_req(c)
            if c >= 0x8000 and c not in (self.end, MOVE_PARAM[g]) and c not in REQ_PROP_KEEP[g]:
                v = self.req_value(row)           # (a Tekken 8 sound: its split value, req_value)
                p2 = self.conv_value(c, v) if c2 is not None and v is not None else None
                if p2 is None:                    # an action TTT2 cannot take: left out, the list kept
                    self.stats['property left out of a requirement list'] += 1
                    continue
                if self.guarded(c) and not self.fits('req', c2, p2):      # a value TTT2 never passes (FIT)
                    self.stats['property left out of a requirement list: a value TTT2 never passes'] += 1
                    continue
                rows.append({'condition': c2, 'param': p2})
                continue
            if c2 is None:
                res = (None, False)
                break
            if c == MOVE_PARAM[g]:                # the parameter is a move id
                t = self.target(p)
                if t is None:
                    res = (None, False)
                    break
                p = t
            elif c in PARRY[g]:                   # parry lists: not converted
                self.stats['parry requirement -> false'] += 1
                res = (None, False)
                break
            elif self.guarded(c) and not self.fits('req', c2, p):         # a parameter TTT2 never passes (FIT)
                self.stats['requirement with a parameter TTT2 never passes -> false'] += 1
                res = (None, False)
                break
            rows.append({'condition': c2, 'param': p})
        if res is None:
            rows.append({'condition': TT_END, 'param': 0})
            start = len(self.T['requirements'])
            self.T['requirements'] += rows
            res = (start, True)
        self.cache[key] = res
        return res

    def conv_cancel_list(self, i, table='cancels', end=M.LIST_END):
        """The converted rows of the Tekken 7 cancel list at i (its end row included)."""
        out = []
        nseq = len(self.k.tables['input_sequences'])
        for c in M.cancels(self.k, i, table, end):
            d = dict(direction=c['direction'], button=c['button'], req=None, extradata=None,
                     win_start=c['win_start'], win_end=c['win_end'], start_frame=c['start_frame'],
                     move_id=c['move_id'], option=0)
            if c['direction'] in (M.LIST_END, M.GROUP_END):
                d['req'], _ = self.conv_reqs(c['req'])
                d['extradata'] = self.extradata(c['extradata'])
                if c['direction'] == M.LIST_END:
                    d['move_id'] = self.target(c['move_id'], input_target=True) or 0
                out.append(d)
                break
            d['req'], ok = self.conv_reqs(c['req'])
            if not ok:
                self.stats['cancel dropped: requirement'] += 1
                continue
            if c['direction'] == M.GROUP:
                d['move_id'] = self.conv_group(c['move_id'])
            else:
                if SEQ0 <= c['direction'] < SEQ0 + nseq:
                    d['direction'] = SEQ0 + self.conv_seq(c['direction'] - SEQ0)
                t = self.target(c['move_id'], input_target=True)
                if t is None:
                    self.stats['cancel dropped: target not converted'] += 1
                    continue
                d['move_id'] = t
            d['extradata'] = self.extradata(c['extradata'])
            out.append(d)
            self.stats['cancels converted'] += 1
        return out

    def conv_group(self, gi):
        key = ('group', gi)
        if key in self.cache:
            return self.cache[key]
        self.cache[key] = None
        rows = self.conv_cancel_list(gi, 'group_cancels', M.GROUP_END)
        start = len(self.T['group_cancels'])
        self.T['group_cancels'] += rows
        self.cache[key] = start
        return start

    def conv_seq(self, si):
        key = ('seq', si)
        if key in self.cache:
            return self.cache[key]
        s = self.k.tables['input_sequences'][si]
        rows = [(x['direction'], x['button']) for x in self.k.tables['inputs'][s['inputs']:s['inputs'] + s['amount']]]
        k2 = (min(s['window'], 255), tuple(rows))
        if k2 in self.seq_index:
            idx = self.seq_index[k2]
        else:
            start = len(self.T['inputs'])
            for dr, bt in rows:
                self.T['inputs'].append(dict(direction=dr, button=bt))
            idx = self.add('input_sequences', dict(s_00=0, window=k2[0], amount=len(rows), inputs=start))
            self.seq_index[k2] = idx
        self.cache[key] = idx
        return idx

    def extradata(self, i):
        if i is None:
            return None
        v = self.k.tables['cancel_extras'][i]['value'] & ~0x84000     # Tekken 7-only bits (0x84080 -> 128)
        if v not in self.extra_index:
            self.extra_index[v] = self.add('cancel_extras', {'value': v})
        return self.extra_index[v]

    def conv_value(self, t7id, v):
        """A property's value (of the fighter's property id t7id) -> TTT2's, or None (not converted)."""
        g = self.game
        if t7id == TIGER_PROP[g]:
            return OPT_ANIM_BASE + self.opt_anims[v] if v in self.opt_anims else None
        kind = VALUE_KIND[g].get(t7id)
        if kind == 'throwcam':
            return self.conv_throwcam(v)
        if kind == 'reaction':
            return self.conv_reaction(v)
        if kind == 'projectile':
            return self.conv_projectile(v)
        if g == 't8' and t7id in SOUND_PROPS[g] and v >> 24 in VOICE8_BANKS:
            if t7id == OPPONENT_VOICE8[0]:
                return OPPONENT_VOICE8[1].get(v & 0xFFFFFF) if v >> 24 == VOICE8_BANKS[1] else None
            return self.voice8(v)
        if t7id in SOUND_PROPS[g] and v not in self.donor_sound[self.prop_map.lookup(t7id)[0]] and \
                not self.own_voice(v):
            return None
        return v

    def voice8(self, v):
        """A Tekken 8 voice (bank << 24 | n, VOICE8_BANKS) -> the TTT2 voice that plays its line (voices8; a kind's
        in turn), or None."""
        voices = self.voices8.get((v >> 24, v & 0xFFFFFF))
        if not voices:
            return None
        turn = self.voice_turns[v]
        self.voice_turns[v] += 1
        return voices[turn % len(voices)]

    def prop_value(self, row):
        """A property row's value as Tekken 7 has it (Tekken 8's sounds: bank << 24 | n, SPLIT_SOUND)."""
        if SPLIT_SOUND[self.game] and row['id'] in SOUND_PROPS[self.game]:
            return (row['value'] & 0xFF) << 24 | (row['value3'] & 0xFFFFFF)
        return row['value']

    def req_value(self, row):
        """A requirement row's parameter as the converter takes it: a Tekken 8 sound action in a requirement list
        splits its value as a property row does (SPLIT_SOUND: the bank in `param`, n in `param3`; the hits' sounds of
        its moves, the electrics' lightning punch among them): bank << 24 | n, or None for a voice of a kind said by a
        chance below CHANCE8 (left out, as in property rows)."""
        if not (SPLIT_SOUND[self.game] and row['condition'] in SOUND_PROPS[self.game]):
            return row['param']
        if row['param'] & 0xFF == VOICE8_BANKS[1] and row.get('param2', 0) < CHANCE8:
            return None
        return (row['param'] & 0xFF) << 24 | (row.get('param3', 0) & 0xFFFFFF)

    def electric_rows(self, move):
        """Kazuya's lightning for Tekken 8 electric move `move` (ELECTRIC_MARK) when it strikes with a limb: [its
        effect row] (ELECTRIC_EFFECT at the limb's root, ELECTRIC_LEAD frames before the first active frame), else
        []. The move is noted in electric_moves (the importer gives the pack the effect)."""
        if move is None:
            return []
        mv = self.k.tables['moves'][move]
        root = ELECTRIC_ROOT.get(self.hit_location(mv['hitbox'][0]))
        if not mv['hitlevel'] or not mv['first_active'] or root is None:
            return []
        self.electric_moves.append(self.name(move))
        self.stats['electrics given Kazuya\'s lightning'] += 1
        return [dict(frame=max(1, mv['first_active'] - ELECTRIC_LEAD), id=EFFECT_PROP,
                     value=root << 8 | ELECTRIC_EFFECT)]

    def voice_req(self, row):
        """A Tekken 8 property row's requirement list; for a voice said against one fighter only (VERSUS8) or by
        a chance below CHANCE8 False (the row left out), for its line against any other None (said always: TTT2's rows
        have no conditions)."""
        if row['id'] not in SOUND_PROPS[self.game] or row['value'] & 0xFF not in VOICE8_BANKS:
            return row['req']
        if row['value'] & 0xFF == VOICE8_BANKS[1] and row['value2'] < CHANCE8:
            return False
        if row['req']:
            tests = M.reqs(self.k, row['req'])
            if len(tests) == 1 and tests[0][0] in VERSUS8:
                return False if tests[0][0] == VERSUS8[0] else None
        return row['req']

    def xp_rows(self, i):
        """The extra property list at i: [(frame, id, value, requirement list or None)] (Tekken 7's rows have no
        requirement list; Tekken 8's each have one, [0] for always)."""
        if self.game == 't7':
            return [(f, idv, v, None) for f, idv, v in M.xps(self.k, i)]
        if i is None:
            return []
        return [(x['frame'], x['id'], self.prop_value(x), self.voice_req(x)) for _, x in
                self.k.iter_list('extra_move_properties', i, lambda x: x['id'] == 0 and x['frame'] == 0)
                if self.voice_req(x) is not False]

    def always(self, r):
        """The converted requirement list at r tests nothing (only TTT2's requirement 0, true)."""
        t = self.T['requirements']
        while r is not None and r < len(t) and t[r]['condition'] != TT_END:
            if t[r]['condition'] != 0:
                return False
            r += 1
        return True

    def own_voice(self, v):
        if v >> 24 == 2:
            return self.voice and (v & 0xFFFFFF) < self.shouts
        return self.voice and (v & 0xFFFFFF) <= OWN_VOICE.get(v >> 24, -1)

    def conv_voiceclips(self, i):
        """A Tekken 7 voice clip list -> the new list's index (its own voices kept), or None. Tekken 8's mark of
        saying nothing (UNSAID8) is TTT2's (SILENT_SHOUT)."""
        vals = M.voices(self.k, i)
        silent = set()
        if self.game == 't8':
            vals = [SILENT_SHOUT if v == UNSAID8 else v for v in vals]
            silent.add(SILENT_SHOUT)
            self.stats['voice clips saying nothing (TTT2\'s shout 999)'] += vals.count(SILENT_SHOUT)
        vals = [v for v in vals if self.own_voice(v) or v in self.donor_clips or v in silent]
        if not vals:
            return None
        start = len(self.T['voiceclips'])
        self.T['voiceclips'] += [{'value': v} for v in vals] + [{'value': 0xFFFFFFFF}]
        return start

    def hit_location(self, x):
        """A Tekken 7 hit location code (a byte of a move's hitbox) -> TTT2's: a weapon's point (its bone's number)
        or the definition's HIT_LOCATIONS, else the id maps', else HIT_LOCATION's."""
        return self.hit_locations.get(x, self.hitbox.get(x, HIT_LOCATION[self.game].get(x, x)))

    def conv_xps(self, i, move=None, extra=()):
        if i is None and not extra:
            return None
        g = self.game
        rows = []
        t7 = self.xp_rows(i)
        air = any(idv == ARCS[g][1] for _, idv, _, _ in t7)     # a 2D air move (convert/arcs.py)
        amounts = sorted((0 if f >= 0x8000 else f, v) for f, idv, v, _ in t7 if idv == DAMAGE_AMOUNT[g])
        dealt = collections.Counter()                       # points dealt so far (amount's frame, property)
        for f, idv, v, req in t7:
            if idv == 0 and f == 0:
                break
            if req is not None:                             # Tekken 8: the row's own requirement list
                r, ok = self.conv_reqs(req)
                if not ok:
                    self.stats['property dropped: requirement'] += 1
                    continue
                if not self.always(r):                      # (TTT2's rows have none)
                    self.stats['property dropped: a condition TTT2 cannot attach'] += 1
                    continue
            if idv in ARCS[g]:                              # 2D arcs (convert/arcs.py)
                rows += [r for r in self.arc_rows(move, air, f, idv, v) if r not in rows]
                continue
            if idv == DAMAGE_AMOUNT[g]:
                continue
            if idv in SUMMON_PROPS[g] or idv == SUMMON_EFFECT[g]:  # summoned weapons
                rows += self.summon_rows([(f, idv, v)], move)
                continue
            if idv in DAMAGE_DEAL[g]:                       # throw damage: points of the amount set before
                at = 0 if f >= 0x8000 else f
                since, amount = next(((g, a) for g, a in reversed(amounts) if g <= at),
                                     amounts[0] if amounts else (0, 0))
                # 0 percent deals what is left of the amount (Heihachi's He_hp2_n2: 35, 42% then 0 -> 15, 20)
                points = int(round(amount * v / 100.0)) if v else max(0, amount - dealt[since, idv])
                dealt[since, idv] += points
                if points:
                    rows.append(dict(frame=f, id=DAMAGE_DEAL[g][idv], value=points))
                    self.stats['throw damage dealt'] += 1
                continue
            p = self.map_prop(idv) if idv >= 0x8000 else self.map_req(idv)
            if p is None:
                continue
            v2 = self.conv_value(idv, v)
            if v2 is None:
                self.stats['property dropped: value (sound bank / index)'] += 1
                continue
            if self.guarded(idv) and not self.fits('prop', p, v2):      # a value TTT2 never passes (FIT)
                self.stats['property dropped: a value TTT2 never passes'] += 1
                continue
            if p == EFFECT_PROP:
                self.effect_ids.add(v2 & 0xFF)
                if (v2 >> 8) > EFFECT_PARTS and (v2 >> 8) not in TTT2_EFFECT_PARTS:
                    v2 &= 0xFF                         # a part TTT2 has not: the base
            rows.append(dict(frame=f, id=p, value=v2))
            if p == EFFECT_PROP:
                self.effect_rows.append((rows[-1], v2 & 0xFF, self.frames_left(move, f)))
            if idv == PROJ_SPAWN[g]:
                look = self.projectile_look(v, {i: x for h, i, x, _ in t7 if h == f})
                if look is not None:
                    rows.append(dict(frame=f, id=EFFECT_PROP, value=look))
        if ELECTRIC_MARK[g] is not None and any(r['id'] == ELECTRIC_PROP and r['value'] == 1 for r in rows):
            rows += self.electric_rows(move)                # a Tekken 8 electric: Kazuya's lightning
        rows += extra
        if not rows:
            return None
        rows.append(dict(frame=0, id=0, value=0))
        start = len(self.T['extra_move_properties'])
        self.T['extra_move_properties'] += rows
        return start

    def summon_rows(self, t7, move=None):
        """The rows of Tekken 7 properties [(frame, id, value)] that summon weapons and their particles (SUMMON_PROPS,
        SUMMON_EFFECT), for a fighter whose definition has summoned weapons."""
        rows = []
        for f, idv, v in t7:
            if not self.summons:
                break
            if idv in SUMMON_PROPS[self.game]:
                rows.append(dict(frame=f, id=SUMMON_PROPS[self.game][idv], value=v))
                self.stats['weapon summons'] += 1
            elif idv == SUMMON_EFFECT[self.game] and (v >> 16) in self.summons and self.summons[v >> 16].get('part'):
                eid = v & 0xFFFF
                rows.append(dict(frame=f, id=EFFECT_PROP, value=self.summons[v >> 16]['part'] << 8 | eid))
                self.effect_ids.add(eid)
                self.effect_rows.append((rows[-1], eid, self.frames_left(move, f)))
        return rows

    def dismiss_when_hit(self):
        """Tekken 7 puts a summoned weapon away when the fighter is hit (its game, not the moveset, does) and in its
        stance; the added fighter is hit into, falls and gets up through the donor's generic moves, and gets up into the
        donor's stance (La_KAM), so each of the donor's moves dismisses all summons as it starts (the fighter's own
        moves never go through them with a weapon out: Noctis's only into a KO), but the intro and win poses that play
        the fighter's animations (they summon their own)."""
        if not self.summons:
            return
        made = {}
        for i in range(len(self.d.tables['moves'])):
            if i in self.posed:
                continue
            row = self.T['moves'][i]
            start = row['extraprops']
            if start not in made:
                made[start] = self.with_props(start, [dict(frame=0x8001, id=TT_DISMISS, value=16)])
            row['extraprops'] = made[start]
            self.stats['weapon summons: dismissed by the donor\'s moves'] += 1

    def hold_thrown(self):
        """The definition's WEAPON_HOLD moves (a pattern of Tekken 7 move names: those a thrown weapon's hit leads
        to) hold the thrown weapons where they are (WEAPON_HOLD_PROP)."""
        pattern = getattr(self.defn, 'WEAPON_HOLD', None)
        if not pattern or not self.summons:
            return
        made = {}
        for t7, i in sorted(self.newidx.items()):
            if not re.search(pattern, self.name(t7)):
                continue
            row = self.T['moves'][i]
            start = row['extraprops']
            if start not in made:
                made[start] = self.with_props(start, [dict(frame=0x8001, id=WEAPON_HOLD_PROP, value=0)])
            row['extraprops'] = made[start]
            self.stats['weapon summons: thrown weapons held after a hit'] += 1

    def with_props(self, start, extra):
        """A new property list: the one at `start` (None: none) with rows `extra` after it -> its index."""
        rows = []
        table = self.T['extra_move_properties']
        while start is not None and start < len(table) and not (table[start]['id'] == 0 and table[start]['frame'] == 0):
            rows.append(dict(table[start]))
            start += 1
        out = len(table)
        table += rows + list(extra) + [dict(frame=0, id=0, value=0)]
        return out

    def frames_left(self, move, f):
        """The frames of Tekken 7 move `move` left from frame f (0x8001 = the start), or None (not known)."""
        length = self.k.tables['moves'][move]['anim_len'] if move is not None else 0
        return max(1, length - (0 if f >= 0x8000 else f)) if length else None

    def split_effects(self, emitting, used):
        """Tekken 7 stops the effect a move spawns when the move ends; an effect stops by itself in TTT2. An
        effect that emits longer (`emitting`: {id: frames it emits for, None when only at its start}) than a move
        spawning it lasts gets a copy that stops with that move: one copy a different end (rounded to EFFECT_STEP
        frames) under a spare id (EFFECT_SPARE, none of `used`), the move's rows naming it; the longest end keeps the
        id; when the spare ids run out, the longest end. -> {effect id: (Tekken 7 id, frames it emits for or None)}
        (also the ids in effect_ids)."""
        ends = collections.defaultdict(lambda: collections.defaultdict(list))
        for row, effect, left in self.effect_rows:
            full = emitting.get(effect)
            end = full if full is None or left is None else min(full, -(-left // EFFECT_STEP) * EFFECT_STEP)
            ends[effect][end].append(row)
        spare = [i for i in EFFECT_SPARE if i not in used and i not in self.effect_ids]
        out = {}
        for effect, by_end in sorted(ends.items()):
            order = sorted(by_end, key=lambda e: float('inf') if e is None else e, reverse=True)
            out[effect] = (effect, order[0])
            for end in order[1:]:
                if not spare:
                    self.stats['effect copies: no spare id (the longest end)'] += 1
                    continue
                copy_id = spare.pop(0)
                out[copy_id] = (effect, end)
                self.effect_ids.add(copy_id)
                for row in by_end[end]:
                    row['value'] = (row['value'] & ~0xFF) | copy_id
                self.stats['effect copies ending with their moves'] += 1
        return out

    def arc_rows(self, move, air, f, idv, v):
        """The TTT2 rows of a Tekken 7 2D-arc property (convert/arcs.py) of move `move`."""
        if idv == arcs.AIR_MOVE:
            self.stats['2D arcs: air moves'] += 1
            return [dict(frame=arcs.AIR_MARK_FRAME, id=arcs.AIR_MARK, value=0)]
        v &= 0xFFFFFFFF
        if move is not None and arcs.is_ground_arc(air, f):
            if move in self.ground_arcs:
                self.stats['2D arcs: second ground arc of a move dropped'] += 1
                return []
            self.ground_arcs[move] = (f, v)
            return [dict(frame=arcs.BAKED_FRAME, id=arcs.BAKED, value=(v & 0xFFFFFF00) | (f & 0xFF))]
        self.stats['2D arcs: started in the air'] += 1
        return [dict(frame=f, id=arcs.ARC, value=v)]

    def bake_arcs(self):
        """The moves that start a 2D arc on the ground play their animation with the arc in the hips height,
        extended to the landing (convert/arcs.py)."""
        k = self.k
        whole = {k.anim_name(i): k.tables['moves'][i]['anim'] for i in range(len(k.tables['moves']))
                 if '_sabun' not in k.anim_name(i).lower()}
        baked = {}
        for i, (f0, value) in sorted(self.ground_arcs.items()):
            if i not in self.newidx:
                continue
            row, mv = self.T['moves'][self.newidx[i]], k.tables['moves'][i]
            a, g, _ = arcs.params(value)
            hold = mv['ground_fall'] or mv['airborne_end']
            off, name = mv['anim'], k.anim_name(i)
            key = (off, f0, a, g, hold)
            if key not in baked:
                dec = arcs.decode_t7(k, off)
                frames = dec['frames']
                if '_sabun' in name.lower() and arcs.whole_name(name) in whole:
                    dec, _, _ = arcs.absolute_sabun(dec, arcs.decode_t7(k, whole[arcs.whole_name(name)]))
                    self.stats['2D arcs: delta animations made absolute'] += 1
                desc, values, ext = arcs.bake(dec, f0, a, g, hold)
                baked[key] = (0x4000 | (self.pack0_count + len(self.new_anims)), ext, frames)
                self.new_anims.append(arcs.encode(desc, values))
                self.stats['2D arcs: animations baked'] += 1
            row['anim'], ext, frames = baked[key]
            self.stats['2D arcs: ground moves'] += 1
            if not ext:
                continue
            for f in ('airborne_end', 'ground_fall'):
                if row[f] and row[f] >= hold:
                    row[f] += ext
            if row['cancel'] is None:
                continue
            # the landing: the cancels from the animation's end on, in a copy of the list (lists are shared)
            cl, j = [], row['cancel']
            while j < len(self.T['cancels']):
                cl.append(dict(self.T['cancels'][j]))
                if cl[-1]['direction'] == M.LIST_END:
                    break
                j += 1
            for c in cl:
                if c['direction'] not in (M.LIST_END, M.GROUP_END) and c['win_start'] >= frames \
                        and c['win_end'] < 32767:
                    c['win_start'] += ext
                    c['win_end'] += ext
                    c['start_frame'] += ext
            row['cancel'] = len(self.T['cancels'])
            self.T['cancels'] += cl

    def conv_props(self, table, i):
        if i is None:
            return None
        rows = []
        for _, p in self.k.iter_list(table, i, lambda p: p['id'] == self.end):
            if p['id'] == self.end:
                break
            pid = self.map_prop(p['id']) if p['id'] >= 0x8000 else self.map_req(p['id'])
            if pid is None:
                continue
            r, ok = self.conv_reqs(p['req'])
            if not ok:
                self.stats['property dropped: requirement'] += 1
                continue
            v2 = self.conv_value(p['id'], self.prop_value(p))
            if v2 is None:
                self.stats['property dropped: value (sound bank / index)'] += 1
                continue
            if self.guarded(p['id']) and not self.fits('prop', pid, v2):    # a value TTT2 never passes (FIT)
                self.stats['property dropped: a value TTT2 never passes'] += 1
                continue
            rows.append(dict(req=r if r is not None else 0, id=pid, value=v2))
        if not rows:
            return None
        rows.append(dict(req=0, id=TT_END, value=0))
        start = len(self.T[table])
        self.T[table] += rows
        return start

    def conv_throwcam(self, ti):
        key = ('tc', ti)
        if key not in self.cache:
            t = self.k.tables['throw_cameras'][ti]
            cd = self.add('camera_data', dict(self.k.tables['camera_data'][t['camera_data']]))
            self.cache[key] = self.add('throw_cameras', dict(side=t['side'] & 0xFFFFFFFF, camera_data=cd))
        return self.cache[key]

    def conv_pushback(self, pi):
        if pi is None:
            return None
        key = ('pb', pi)
        if key not in self.cache:
            p = self.k.tables['pushbacks'][pi]
            ex = None
            if p['extradata'] is not None:
                ex = len(self.T['pushback_extras'])
                for q in range(p['loops']):
                    self.T['pushback_extras'].append(dict(self.k.tables['pushback_extras'][p['extradata'] + q]))
            self.cache[key] = self.add('pushbacks', dict(duration=p['duration'], displacement=p['displacement'],
                                                         loops=p['loops'], extradata=ex))
        return self.cache[key]

    def conv_reaction(self, ri):
        key = ('react', ri)
        if key in self.cache:
            return self.cache[key]
        r = self.k.tables['reactions'][ri]
        row = {}
        self.alloc_ok += 1
        for nm, off, fmt, link in TTT2['reactions'][1]:
            if link == 'pushbacks':
                row[nm] = self.conv_pushback(r[nm])
            elif link == 'move':
                t = self.target(r[nm])
                if t is None:
                    self.stats['reaction slot -> fallback'] += 1
                    n = self.name(r[nm]) if r[nm] < len(self.k.tables['moves']) else r[nm]
                    t = self.similar(n) if isinstance(n, str) else None
                    if t is None:
                        t = self.slot_default[nm]
                row[nm] = t
            else:
                row[nm] = r[nm]
        self.alloc_ok -= 1
        idx = self.add('reactions', row)
        self.cache[key] = idx
        return idx

    def similar(self, n):
        """The donor move whose name shares the longest prefix (7 characters at least) with n."""
        best, bl = None, 6
        for dn_, j in self.dn.items():
            l = 0
            for a, b in zip(n, dn_):
                if a != b:
                    break
                l += 1
            if l > bl or (l == bl and best is not None and len(dn_) < len(self.d.move_name(best))):
                best, bl = j, l
        return best

    def conv_projectile(self, pi):
        """A Tekken 7 projectile index -> the new moveset's projectile index (the row appended), or None."""
        t = self.k.tables['projectiles']
        if not 0 < pi < len(t):
            return None
        key = ('proj', pi)
        if key in self.cache:
            return self.cache[key]
        self.cache[key] = None                    # a cancel that respawns this projectile: not converted
        p = t[pi]
        v = struct.unpack('<42I', p['raw'])
        out = [0] * 34
        out[0] = PROJ_EFFECT
        for to, fr, n in PROJ_FIELDS:
            out[to:to + n] = v[fr:fr + n]
        for f in PROJ_SOUNDS:
            if out[f] and out[f] not in self.known_sounds and not self.own_voice(out[f]):
                out[f] = 0
                self.stats['projectile sound dropped'] += 1
        n0 = len(self.T['hit_conditions'])
        hc = self.conv_hitconds(p['hit_condition'])
        out[19] = hc if hc is not None and len(self.T['hit_conditions']) > n0 else 0
        out[20] = self.conv_proj_cancels(p['cancel'])
        idx = self.add('projectiles', {'raw': struct.pack('>34I', *out)})
        self.cache[key] = idx
        self.stats['projectiles converted'] += 1
        return idx

    def projectile_look(self, pi, props):
        """The effect showing Tekken 7 projectile `pi` spawned with `props` ({property: value} of its frame) ->
        the 0x801f value (part << 8 | effect id), or None (no room for more ids). The look is the projectile's
        missile's particle system; the runtime keeps it where the projectile is (convert/particles.py projectile)."""
        t = self.k.tables['projectiles']
        if not 0 < pi < len(t):
            return None
        v = struct.unpack('<42I', t[pi]['raw'])
        bone = props.get(PROJ_BONE[self.game], 0)
        spec = dict(missile=v[2], life=v[10])
        for eid, known in self.projectile_effects.items():
            if known == spec:
                break
        else:
            eid = PROJECTILE_EFFECTS + len(self.projectile_effects)
            if eid > 0xFF:
                return None
            self.projectile_effects[eid] = spec
        self.stats['projectiles shown by an effect'] += 1
        return (bone if bone <= EFFECT_PARTS else 0) << 8 | eid

    def thrown_rows(self, i, row):
        """A move of the definition's THROWN: its projectile (a row appended) and the properties spawning it; the
        move's hit boxes go. -> the properties, or []."""
        spec = self.thrown.get(self.name(i))
        if spec is None or row['hit_condition'] is None:
            return []
        out = [0] * 34
        out[2], out[4], out[5] = spec['speed'], 1, spec['frames']           # forward speed, one hit, life
        out[6], out[7], out[8] = 1, spec['radius'], spec['height']          # a cylinder
        out[9] = row['hitlevel'] & 0xFFFF
        out[16], out[19], out[22] = THROWN_SOUND, row['hit_condition'], 1   # hit sound, hit condition, the other team
        out[23], out[24] = 2 * spec['radius'], spec['height']
        idx = self.add('projectiles', {'raw': struct.pack('>34I', *out)})
        row['hitbox'], row['first_active'], row['last_active'] = bytes(4), 0, 0
        self.stats['weapons thrown as projectiles'] += 1
        f = spec['frame']
        look = []
        if spec.get('item'):                  # the weapon flying with it (convert/particles.py thrown)
            seen = dict(item=spec['item'], trail=spec.get('trail'), life=spec['frames'])
            eid = next((e for e, known in self.projectile_effects.items() if known == seen), None)
            if eid is None and PROJECTILE_EFFECTS + len(self.projectile_effects) <= 0xFF:
                eid = PROJECTILE_EFFECTS + len(self.projectile_effects)
                self.projectile_effects[eid] = seen
            if eid is not None:
                look = [dict(frame=f, id=EFFECT_PROP, value=THROWING_HAND << 8 | eid)]   # (there until it flies)
        return [dict(frame=f, id=TT_PROJ_LIMB, value=0),
                dict(frame=f, id=TT_PROJ_OFFSETS[0], value=spec['forward'] & 0xFFFF),
                dict(frame=f, id=TT_PROJ_OFFSETS[1], value=spec['up'] & 0xFFFF),
                dict(frame=f, id=TT_PROJ_OFFSETS[2], value=spec.get('side', 0) & 0xFFFF),
                dict(frame=f, id=TT_PROJ_SPAWN, value=idx)] + look     # (the look rides the projectile)

    def conv_proj_cancels(self, i):
        """A projectile's cancel list -> its new index, 0 if nothing but the end row is left. TTT2 runs it every
        frame of the projectile's life: a row whose window and requirements hold applies its properties (the
        requirement list's ids >= 0x8000) to the owner; with option 0x40 the projectile turns into projectile
        move_id."""
        if i is None:
            return 0
        rows = []
        for c in M.cancels(self.k, i):
            end = c['direction'] == M.LIST_END
            r, ok = self.conv_reqs(c['req'])
            if not ok and not end:
                self.stats['projectile cancel dropped: requirement'] += 1
                continue
            m = 0
            if not end and c['option'] & 0x40:
                m = self.conv_projectile(c['move_id'])
                if m is None:
                    self.stats['projectile cancel dropped: target'] += 1
                    continue
            rows.append(dict(direction=c['direction'], button=c['button'], req=r,
                             extradata=self.extradata(c['extradata']), win_start=c['win_start'],
                             win_end=c['win_end'], start_frame=c['start_frame'], move_id=m,
                             option=c['option'] & 0x40))
            if end:
                break
        if len(rows) < 2:
            return 0
        start = len(self.T['cancels'])
        self.T['cancels'] += rows
        return start

    def conv_hitconds(self, i):
        if i is None:
            return None
        out = []
        t = self.k.tables['hit_conditions']
        j = i
        while j < len(t):
            h = t[j]
            last = not M.reqs(self.k, h['req'])
            r, ok = self.conv_reqs(h['req'])
            if ok:
                rl = [c for c, p in M.reqs(self.k, h['req'])]
                if SCREW[self.game] in rl:                      # screw -> the donor's bound reactions
                    rx = self.bound_reaction
                else:
                    rx = self.conv_reaction(h['reactions']) if h['reactions'] is not None else None
                entry = dict(req=r, damage=h['damage'], reactions=rx)
                air = T7_AIR[self.game]
                if rl == [air] and tagsystem.same_reaction(self.T, rx, self.bound_reaction):     # an air slam
                    alone = j + 1 >= len(t) or [c for c, p in M.reqs(self.k, t[j + 1]['req'])] != [air]
                    out += tagsystem.gated_slam(self.T, entry, out, self.bound_req, self.bound_reaction,
                                                self.after_bound_reaction, alone)
                    self.stats['Tekken 7 air slams -> bounds (467)'] += 1
                else:
                    out.append(entry)
            else:
                self.stats['hit condition entry dropped'] += 1
            if last:
                break
            j += 1
        start = len(self.T['hit_conditions'])
        self.T['hit_conditions'] += out
        return start

    def anim(self, off):
        off = self.delta_anim.get(off, off)
        if off not in self.anim_id:
            hits = self.anim_src.get(off, [])
            com = [h for h in hits if h[0] == 'common']
            own = [h for h in hits if h[0] == 'donor']
            if com:
                aid = 0x8000 | com[0][1]
                self.stats['animations: common'] += 1
            elif own:
                aid = 0x4000 | own[0][1]
                self.stats['animations: in the donor pack'] += 1
            else:
                aid = 0x4000 | (self.pack0_count + len(self.new_anims))
                self.new_anims.append(motion.swap_animation(self.k.animbuf[off:off + self.k.anim_size[off]], '<'))
                self.stats['animations: new'] += 1
            self.anim_id[off] = aid
        return self.anim_id[off]

    def anim8(self, i):
        """The TTT2 animation id of Tekken 8 move i (ANIMATIONS): a 'G' move's of the same key, else the provider's
        (appended when it gives bytes), else the donor stance's."""
        ref = tuple(self.k.anim_ref(i))
        if ref not in self.anim_id:
            if ref[0] in self.generic_anim:
                aid = self.generic_anim[ref[0]]
                self.stats['animations: the donor\'s (a generic move\'s)'] += 1
            else:
                if self.animations is None:
                    raise ValueError('a Tekken 8 moveset needs an animation provider (Converter.animations)')
                got = self.animations(ref) if ref[1] is not None else None
                if isinstance(got, int):
                    aid = got
                    self.stats['animations: TTT2\'s'] += 1
                elif got is not None:
                    aid = ANIM_PACK | (self.pack0_count + len(self.new_anims))
                    if ref[0] not in getattr(self.animations, 'originals', ()):   # a converted clip, not TTT2's
                        vars(self).setdefault('converted8', set()).add(len(self.new_anims))     # (handoffs8)
                    self.new_anims.append(bytes(got))
                    self.stats['animations: new'] += 1
                else:
                    aid = self.d.tables['moves'][self.d.resolve_alias(0x8001)]['anim']
                    self.stats['animations: none (the donor stance\'s)'] += 1
            self.anim_id[ref] = aid
        return self.anim_id[ref]

    def move_anim(self, i):
        """The TTT2 animation id of the fighter's move i."""
        return self.anim(self.k.tables['moves'][i]['anim']) if self.game == 't7' else self.anim8(i)

    def animation_bytes(self, aid):
        """(buffer, endian, offset) of a TTT2 animation id: the common motions', the donor pack's or a new one."""
        if aid & ANIM_COMMON:
            e, offs = motion.mota_offsets(self.common_motions, 0)
            return self.common_motions, e, offs[aid & 0x3FFF]
        o0 = motion.pack_items(self.donor_pack)[0][0]
        e, offs = motion.mota_offsets(self.donor_pack, o0)
        n = aid & 0x3FFF
        if n < len(offs):
            return self.donor_pack, e, o0 + offs[n]
        return self.new_anims[n - len(offs)], '>', 0

    # --- moves ------------------------------------------------------------------------------------------
    def conv_move(self, i):
        mv = self.k.tables['moves'][i]
        return dict(name=self.string(self.ttt2_name(i)), anim_name=self.string(self.k.anim_name(i)),
                    anim=self.move_anim(i), vuln=mv['vuln'], hitlevel=mv['hitlevel'], cancel=None, cancel2=0,
                    c2_int=0, cancel3=0, c3_int=0, cancel4=0, c4_int=0, transition=0, m_56=mv['m_56'],
                    move_id_hi=0, move_id_lo=0, hit_condition=None, anim_len=0,
                    airborne_start=mv['airborne_start'], airborne_end=mv['airborne_end'],
                    ground_fall=mv['ground_fall'], voiceclip=None, extraprops=None, begin_props=None,
                    end_props=None, bitfield=rev32(mv['bitfield']) & ~(1 << 30),   # Tekken 7 bit 1: no TTT2 meaning
                    hitbox=bytes(self.hit_location(x) for x in mv['hitbox']), first_active=mv['first_active'],
                    last_active=mv['last_active'], m_a8=mv['m_a8'], distance=mv['distance'])

    def cancel_list(self, i):
        key = ('cl', i)
        if key not in self.cache:
            cl = self.conv_cancel_list(i)
            self.cache[key] = len(self.T['cancels'])
            self.T['cancels'] += cl
        return self.cache[key]

    def run(self):
        k, d = self.k, self.d
        self.alloc_ok = 0
        self.queue = []
        # per reaction slot, the donor's most common move (fallback); the donor's bound reactions (requirement 467)
        self.slot_default = {f: collections.Counter(r[f] for r in d.tables['reactions']).most_common(1)[0][0]
                             for f in REACTION_MOVE_FIELDS}
        bc = collections.Counter(h['reactions'] for h in d.tables['hit_conditions']
                                 if h['reactions'] is not None and any(c == 467 for c, p in M.reqs(d, h['req'])))
        self.bound_reaction = bc.most_common(1)[0][0]
        # ... their requirement list and what an air hit plays after them (the Tekken 7 air slams: conv_hitconds)
        self.bound_req, self.after_bound_reaction = tagsystem.bound_shape(d.tables)
        nd = len(d.tables['moves'])
        keep = [i for i, c in enumerate(self.cls) if c == 'K' and not self.drop_moves.search(self.name(i))
                and i not in self.delta_move]
        self.stats['own moves'] = sum(1 for c in self.cls if c == 'K')
        self.stats['own moves converted'] = len(keep)
        self.newidx = {i: nd + n for n, i in enumerate(keep)}
        self.T['moves'] += [self.conv_move(i) for i in keep]
        # alias slots: the donor's, except where it names a donor-specific move (the round start, its stance):
        # there the Tekken 7 fighter's slot, converted. Such a pair are counterparts: the converted move also gets
        # the donor move's cancels into TTT2-only moves (tag out from standing, ...)
        donor_specific = {n for n in self.dn if n not in self.kn and n not in self.ttt2_only_generic}
        self.aliases = list(d.aliases)
        counterpart = {}
        for s_ in range(56):
            if d.move_name(d.aliases[s_]) in donor_specific and k.aliases[s_] in self.newidx:
                self.aliases[s_] = self.newidx[k.aliases[s_]]
                counterpart.setdefault(k.aliases[s_], d.aliases[s_])
        # the round-start move (alias slot 0): Tekken 7's does not convert (its mode checks land on TTT2 ids that
        # need guards: one crashes in practice), so the donor's list is kept with its own targets replaced
        self.rebuild_direct(donor_specific)
        # second pass: the links (every new index is known now)
        for i in keep:
            self.link_move(i, counterpart)
        self.link_queued(counterpart)
        self.rebuild_hubs()
        self.own_transitions()
        self.link_queued(counterpart)          # Tekken 7 generic movement states the last two reached
        self.bake_arcs()
        move_overrides.apply(self)
        specialcancels.apply(self)
        self.dismiss_when_hit()
        self.hold_thrown()
        # TTT2's tag system on the converted moves (convert/tagsystem.py; the slams were gated while linking): the
        # Tag Crash rows of the landing reactions, then the Tag Assault twins of the bound moves
        self.stats['Tag Crash: moves given the landing tag rows'] += tagsystem.add_landing_rows(
            self.T, tagsystem.landing_template(d.tables, d.aliases), nd, self.aliases)
        made = tagsystem.add_tag_assault(self.T, tagsystem.assault_template(d.tables, d.aliases), nd, self.move_name,
                                         self.string)
        self.stats['Tag Assault: bound moves given a tag twin and its exit'] += len(made)
        # ... its idle variants of the stance get the stance's list (tag out, ...), and its launchers tag combos
        # (convert/tagcombo.py)
        idle = tagsystem.share_stance(self.T, self.aliases, nd)
        if idle:
            self.stats['idle variants given their stance\'s list (tag out, ...)'] += idle
        tagcombo.apply(self)
        if self.game == 't8':
            self.handoffs8()
        # every move belongs to the new motion row
        for n, row in enumerate(self.T['moves']):
            combined = (self.newid << 16) + n - (self.newid - 1)
            row['move_id_hi'] = combined >> 16 & 0xFFFF
            row['move_id_lo'] = combined & 0xFFFF
        if len(self.T['pushback_extras']) % 2:
            self.T['pushback_extras'].append({'value': 0})
        return self

    def link_queued(self, counterpart):
        """Link the Tekken 7 generic moves target() converted on the way (their links may convert more)."""
        self.alloc_ok += 1
        while self.queue:
            self.link_move(self.queue.pop(0), counterpart)
        self.alloc_ok -= 1

    def link_move(self, i, counterpart):
        self.linking += 1
        try:
            self._link_move(i, counterpart)
        finally:
            self.linking -= 1

    def _link_move(self, i, counterpart):
        k, d = self.k, self.d
        mv = k.tables['moves'][i]
        row = self.T['moves'][self.newidx[i]]
        # the fighter's own walks, dashes, crouch starts ... (Ka_sWALKB, sWALK_00B) are counterparts of the donor's
        # (Tekken 7 has no tag: without the donor's rows, no tag out while walking back or crouching)
        cp = counterpart[i] if i in counterpart else self.state_counterpart(i)
        if cp is not None:
            if i not in counterpart:
                self.stats['own movement states given the donor\'s tag rows'] += 1
            cl = self.merge_donor_extras(self.conv_cancel_list(mv['cancel']),
                                         M.cancels(d, d.tables['moves'][cp]['cancel']))
            row['cancel'] = len(self.T['cancels'])
            self.T['cancels'] += cl
        else:
            row['cancel'] = self.cancel_list(mv['cancel'])
        t = self.target(mv['transition'], input_target=True)
        if t is None:
            self.stats['transition -> the standing alias 0x8001'] += 1
            t = 0x8001
        row['transition'] = t
        row['hit_condition'] = self.conv_hitconds(mv['hit_condition'])
        row['extraprops'] = self.conv_xps(mv['extraprops'], i, self.thrown_rows(i, row))
        row['begin_props'] = self.conv_props('move_begin_props', mv['begin_props'])
        row['end_props'] = self.conv_props('move_end_props', mv['end_props'])
        if M.voices(k, mv['voiceclip']):
            row['voiceclip'] = self.conv_voiceclips(mv['voiceclip'])
            self.stats['voice clips kept' if row['voiceclip'] is not None else 'voice clips dropped'] += 1

    def rebuild_hubs(self):
        """Generic moves that lead into the fighter's own moves get its cancel lists plus the donor's cancels into
        TTT2-only moves."""
        k, d = self.k, self.d
        nd = len(d.tables['moves'])
        donor_specific = {n for n in self.dn if n not in self.kn and n not in self.ttt2_only_generic}
        for i, c in enumerate(self.cls):
            if c != 'G':
                continue
            mv = k.tables['moves'][i]
            kc = M.cancels(k, mv['cancel'])
            dj = self.dn[k.move_name(i)]
            dc = M.cancels(d, d.tables['moves'][dj]['cancel'])
            k_hub = any(x['direction'] < 0x8000 and (x['move_id'] in self.newidx or
                        self.shared_input_target(x['move_id'])) for x in kc) or \
                any(x['direction'] == M.GROUP for x in kc)
            d_spec = any(x['direction'] < 0x8000 and x['move_id'] < nd and d.move_name(x['move_id']) in donor_specific
                         for x in dc) or any(x['direction'] == M.GROUP for x in dc)
            if not k_hub and not d_spec:
                continue
            # a TTT2-only hub (the partner's tag-in dispatcher: Tekken 7 has no tag, its list is one row TTT2 never
            # takes) keeps the donor's list, without its rows into donor-specific moves
            cl = None if k_hub else tagsystem.kept_hub(
                dc, lambda m: m < nd and d.move_name(m) in self.ttt2_only_generic,
                lambda m: m < nd and d.move_name(m) in donor_specific)
            if cl is not None:
                self.stats['hub moves keeping the donor\'s list (tag system)'] += 1
            else:
                cl = self.merge_donor_extras(self.conv_cancel_list(mv['cancel']), dc)
            self.T['moves'][dj]['cancel'] = len(self.T['cancels'])
            self.T['cancels'] += cl
            self.stats['hub moves rebuilt'] += 1

    def own_transitions(self):
        """Generic moves keep the donor's move row, its transition too: where that ends in the donor's own movement
        state (st2cr_00B -> Ju_cWALKB, cr2st_00F -> Ju_sWALKF: the donor's walk, its list with the donor's attacks),
        the fighter's Tekken 7 transition when that is a movement state (Kz_cWALKB, Ka_sWALKF)."""
        k, d = self.k, self.d
        nd = len(d.tables['moves'])
        donor_specific = {n for n in self.dn if n not in self.kn and n not in self.ttt2_only_generic}
        for i, c in enumerate(self.cls):
            if c != 'G':
                continue
            row = self.T['moves'][self.dn[k.move_name(i)]]
            now = row['transition']
            if now >= 0x8000:                   # an alias slot: the new moveset's (the stance is the fighter's)
                now = self.aliases[now - 0x8000] if now < 0x8000 + 56 else None
            if now is None or now >= nd or d.move_name(now) not in donor_specific:
                continue
            t7 = k.resolve_alias(k.tables['moves'][i]['transition'])
            if t7 is None or t7 >= len(k.tables['moves']) or not self.is_state(t7):
                continue
            t = self.target(k.tables['moves'][i]['transition'])
            if t is not None and t != row['transition']:
                row['transition'] = t
                self.stats['generic moves going on to the fighter\'s movement state, not the donor\'s'] += 1

    def answered_by(self, cl):
        """OWN_INPUT[game]: a test whether a donor cancel's input (a button, with directions or a special command) is
        one the fighter's converted list cl (its groups too) already answers: the same buttons, and every direction of
        the donor's row among the fighter's rows of those buttons (0: all of them), whatever their conditions (an
        earlier row of a button takes the press first: the donor's u/f+2 [214] in front of her u/f+1+2 played the
        donor's jump punch for it; the donor's item moves, which the fighter answers with her own item rows, need an
        item an added fighter cannot wear). Otherwise (or for another game) always False."""
        if not OWN_INPUT[self.game]:
            return lambda y: False
        dirs, specials = collections.defaultdict(int), set()
        for x in cl:
            rows = [x]
            if x['direction'] == M.GROUP:
                rows, j, t = [], x['move_id'], self.T['group_cancels']
                while j < len(t) and t[j]['direction'] != M.GROUP_END:
                    rows.append(t[j])
                    j += 1
            for y in rows:
                if y['direction'] in (M.LIST_END, M.GROUP_END, M.GROUP) or not y['button']:
                    continue
                if y['direction'] < 0x8000:
                    dirs[y['button']] |= (y['direction'] & ALL_DIRECTIONS) or ALL_DIRECTIONS
                else:
                    specials.add((y['direction'], y['button']))

        def answered(y):
            if not y['button'] or y['direction'] in (M.LIST_END, M.GROUP_END, M.GROUP):
                return False
            if y['direction'] >= 0x8000:
                return (y['direction'], y['button']) in specials
            want = (y['direction'] & ALL_DIRECTIONS) or ALL_DIRECTIONS
            return want & ~dirs.get(y['button'], 0) == 0
        return answered

    def merge_donor_extras(self, cl, dc):
        """Insert the donor's cancels into TTT2-only generic moves (the tag system, ...) at their aligned place:
        after the converted cancel that matches the nearest preceding donor cancel (same target name and input). A
        Tekken 8 fighter's: only those whose input its own list does not answer (OWN_INPUT)."""
        d = self.d

        def sig_new(x):
            m = x['move_id']
            return (x['direction'], x['button'],
                    d.move_name(m) if m < len(self.T['moves']) and m < len(d.tables['moves']) else m)
        pos = {}
        for p, x in enumerate(cl[:-1]):
            pos.setdefault(sig_new(x), p)
        inserts = collections.defaultdict(list)      # converted position -> donor rows after it (-1: in front)
        anchor = -1

        def tto(m):
            return m < len(d.tables['moves']) and d.move_name(m) in self.ttt2_only_generic
        answered = self.answered_by(cl)
        for x in dc:
            if x['direction'] == M.LIST_END:
                break
            m = x['move_id']
            if x['direction'] == M.GROUP:
                g = [y for y in M.cancels(d, m, 'group_cancels', M.GROUP_END) if y['direction'] != M.GROUP_END]
                gt = [y for y in g if tto(y['move_id'])]
                if g and len(gt) * 2 >= len(g):          # a TTT2-only group (tag out from standing, ...): kept
                    kept = [n for n, y in enumerate(g) if not answered(y)]
                    if len(kept) == len(g):
                        inserts[anchor].append(dict(x))
                    elif kept:                           # (OWN_INPUT: without the rows the fighter answers)
                        key = ('own input group', m, tuple(kept))
                        if key not in self.cache:
                            self.cache[key] = len(self.T['group_cancels'])
                            self.T['group_cancels'] += [dict(g[n]) for n in kept] + \
                                [dict(self.T['group_cancels'][m + len(g)])]
                        y = dict(x)
                        y['move_id'] = self.cache[key]
                        inserts[anchor].append(y)
                    if len(kept) < len(g):
                        self.stats['donor rows the fighter answers itself, left out (OWN_INPUT)'] += len(g) - len(kept)
                    continue
                for y in gt:                             # TTT2-only members of a shared group: as plain cancels
                    if answered(y):
                        self.stats['donor rows the fighter answers itself, left out (OWN_INPUT)'] += 1
                        continue
                    y = dict(y)
                    y['option'] = 0
                    inserts[anchor].append(y)
            elif (x['direction'] == 16 and x['button'] == 0 and m < len(d.tables['moves'])
                  and d.move_name(m) in {'Co_AOzen', 'Co_AOkou', 'Co_UTokiF', 'Co_UTokiB'}):
                # T7 replaced the grounded back-roll routes with *tk7 recovery
                # moves. Those targets have no TTT2 counterpart and are dropped.
                # Keep each native orientation-gated back route, without duplicating
                # routes already converted. Retain native priority via the anchor.
                if not any(sig_new(y) == sig_new(x)
                           and tagsystem.reqs(self.T, y['req']) == M.reqs(d, x['req'])
                           for y in cl[:-1]):
                    inserts[anchor].append(dict(x))
                    self.stats['native grounded back-roll routes restored'] += 1
                else:
                    anchor = pos.get(sig_new(x), anchor)
            elif tto(m):
                if answered(x):
                    self.stats['donor rows the fighter answers itself, left out (OWN_INPUT)'] += 1
                    continue
                y = dict(x)
                y['option'] = 0
                inserts[anchor].append(y)
                continue
            s = (x['direction'], x['button'],
                 d.move_name(m) if (x['direction'] != M.GROUP and m < len(d.tables['moves'])) else m)
            if s in pos:
                anchor = pos[s]
        out = list(inserts[-1])
        for p, x in enumerate(cl[:-1]):
            out.append(x)
            out += inserts[p]
        out.append(cl[-1])
        return out

    def rebuild_direct(self, donor_specific):
        """The round-start list (alias slot 0) keeps the donor's targets except its own moves (MOVESET['direct']):
        its stance becomes the fighter's; its intros and win poses stay (their camera animations end the intro and
        the win screen; their sound properties play the fighter's own lines, which sit at the same tones of its
        banks) and play the fighter's animations instead."""
        d = self.d
        dj = d.aliases[0]
        turn = collections.Counter()
        by_tone = {tone: name for name, tone in self.win_tones.items()}

        def quote_tone(j):
            for f, idv, v in M.xps(d, d.tables['moves'][j]['extraprops']):
                if idv == WIN_QUOTE_PROP and v & 0xFFFFF000 == WIN_QUOTE_VALUE:
                    return v & 0xFFF
            return None

        def sub(j):
            name = d.move_name(j)
            for pat, how, theirs in self.defn.MOVESET.get('direct', ()):
                if not re.search(pat, name):
                    continue
                own = [n for n in theirs if self.kn.get(n) in self.newidx]
                if not own:
                    break
                if how == 'move':
                    return self.newidx[self.kn[own[0]]]
                pick = by_tone.get(quote_tone(j))
                if pick not in own:
                    pick = own[turn[pat] % len(own)]
                    turn[pat] += 1
                self.pose_sequence(j, self.kn[pick])
                return j
            return 0x8001                                # the standing alias
        out = []
        for x in M.cancels(d, d.tables['moves'][dj]['cancel']):
            y = dict(x)
            m = x['move_id']
            if x['direction'] < 0x8000 and m < len(d.tables['moves']) and d.move_name(m) in donor_specific:
                y['move_id'] = sub(m)
            out.append(y)
        self.T['moves'][dj]['cancel'] = len(self.T['cancels'])
        self.T['cancels'] += out

    def pose_sequence(self, j, t7):
        """The donor's intro or win pose `j` and the moves it goes on to (TTT2 plays a pose in parts: a round win
        is `1ko`, a wait (`co_dummy`), then `2ko`; a match win the winner's part, then one with the partner): the
        first part with an animation plays the fighter's (Tekken 7 move `t7`), later parts with the donor's own
        animations (its `2ko`, poses made for a certain partner) hold that pose's last frame as long as they
        lasted, so the scene's timing stays the donor's; waits and the common pair poses stay."""
        d = self.d
        prefix = d.move_name(j).split('_')[0].lower()            # the donor's (ju, la) or a shared one (mk)
        family = re.compile(r'^%s_' % re.escape(prefix), re.I)
        order, seen = [j], {j}
        for m in order:
            for x in M.cancels(d, d.tables['moves'][m]['cancel']):
                t = x['move_id']
                if t < len(d.tables['moves']) and t not in seen and family.match(d.move_name(t)):
                    seen.add(t)
                    order.append(t)
        posed = False
        self.posed.update(order)
        for m in order:
            name = d.anim_name(m)
            row = self.T['moves'][m]
            if name.startswith('co_dummy'):
                continue
            if not posed:
                row['anim'] = self.move_anim(t7)
                row['anim_name'] = self.string(self.k.anim_name(t7))
                posed = True
                self.stats['donor round-start moves with her animation'] += 1
                summons = self.summon_rows(M.xps(self.k, self.k.tables['moves'][t7]['extraprops']), t7)
                if summons:                              # the weapons its pose holds (Noctis's sword)
                    row['extraprops'] = self.with_props(row['extraprops'], summons)
            elif not name.startswith('co_') or re.search(r'_%s\(' % re.escape(prefix), name):
                frames = self.donor_anim_frames(d.tables['moves'][m]['anim'])
                if frames:
                    row['anim'] = self.hold(t7, frames)
                    self.stats['donor pose parts holding her pose'] += 1

    def handoffs8(self):
        """Tekken 8: a converted clip keeps HARA_ROT1 upright, TTT2's lying (and other) moves hold the body's
        orientation there; the game's pre-blend into a move's transition keeps HARA_ROT1, so the thrown opponent sat
        up over the last 15 frames of each of Reina's throws and dropped back at the next move (retarget.PREBLEND).
        Each converted clip whose move hands off (its transition) to a move whose frame 0 holds HARA_ROT1 more than
        retarget.HANDOFF_NEEDED degrees elsewhere gets its tail re-split for that move (retarget.handoff: the same
        world pose); a clip handing off to several such moves gets a copy per target."""
        rows = self.T['moves']

        def target(mid):
            r = self.aliases[mid - 0x8000] if mid >= 0x8000 and mid - 0x8000 < len(self.aliases) else mid
            return rows[r] if r is not None and r < len(rows) else None
        users = collections.defaultdict(list)            # new_anims position -> [(row, the next move's animation)]
        for row in rows:
            aid = row['anim']
            if aid & ANIM_COMMON or not aid & ANIM_PACK:
                continue
            n = (aid & 0x3FFF) - self.pack0_count
            nxt = target(row['transition'])
            if n in getattr(self, 'converted8', ()) and nxt is not None and nxt is not row:
                users[n].append((row, nxt['anim']))
        firsts = {}

        def first(aid):
            if aid not in firsts:
                buf, e, off = self.animation_bytes(aid)
                firsts[aid] = (animation.decode_frame(buf, 0, e, off), animation.header(buf, e, off)['type'])
            return firsts[aid]
        for n, lst in sorted(users.items()):
            clip = animation.decode(self.new_anims[n], '>')
            v, kind = clip['values'].astype(np.float64), clip['type']
            if v.shape[1] != len(animation.BODY_DESCRIPTORS) or len(v) < 2:
                continue
            fixes = {}
            for _, b in lst:
                if b not in fixes:
                    nv, nk = first(b)
                    fixes[b] = None
                    if len(nv) >= len(animation.BODY_DESCRIPTORS) and \
                            retarget.handoff_mismatch(v, kind, nv, nk) > retarget.HANDOFF_NEEDED:
                        fixes[b] = retarget.encode(retarget.handoff(v, kind, nv[:len(v[0])], nk), kind)
            for b, data in sorted((b, d) for b, d in fixes.items() if d is not None):
                if all(c == b for _, c in lst):
                    self.new_anims[n] = data
                    self.stats['hand-offs: converted clips re-split for the next move\'s HARA_ROT1'] += 1
                    continue
                aid = ANIM_PACK | (self.pack0_count + len(self.new_anims))
                self.new_anims.append(data)
                for row, c in lst:
                    if c == b:
                        row['anim'] = aid
                self.stats['hand-offs: re-split copies of converted clips (one per next move)'] += 1

    def donor_anim_frames(self, aid):
        """The frame count of a donor pack animation (0x4000 | index), else None."""
        if not aid & 0x4000 or aid & 0x8000:
            return None
        o0 = motion.pack_items(self.donor_pack)[0][0]
        e, offs = motion.mota_offsets(self.donor_pack, o0)
        idx = aid & 0x3FFF
        if idx >= len(offs):
            return None
        return animation.header(self.donor_pack, e, o0 + offs[idx])['frames']

    def hold(self, move, frames):
        """A new animation: the last frame of the fighter's move `move`'s animation held for `frames` frames, in
        place (no ground displacement, no turn: the move before ends with them)."""
        if self.game == 't7':
            off = self.k.tables['moves'][move]['anim']
            key, buf, endian = ('hold', off, frames), self.k.animbuf, '<'
        else:
            buf, endian, off = self.animation_bytes(self.move_anim(move))
            key = ('hold', tuple(self.k.anim_ref(move)), frames)
        if key not in self.anim_id:
            a = animation.decode(buf, endian, off)
            last = animation.to_raw(a['descriptors'], a['values'][-1:], a['type'])[0]
            values = np.repeat(last[None], frames, 0)
            values[:, 0] = 0.0                       # ground displacement
            values[:, 2] = 0.0                       # turn
            self.anim_id[key] = 0x4000 | (self.pack0_count + len(self.new_anims))
            self.new_anims.append(animation.encode_raw(a['descriptors'], values))
        return self.anim_id[key]

    # --- output -----------------------------------------------------------------------------------------
    def write(self):
        """-> (motbin bytes, motion pack bytes)"""
        hdr, strings, blob, slots = motbin.split(self.d)
        hdr = bytearray(hdr)
        nid = self.newid
        struct.pack_into('>4H', hdr, 0xF8 + 32 * 2, nid - 1, (-(nid - 1)) & 0xFFFF, nid, (-nid) & 0xFFFF)
        struct.pack_into('>56H', hdr, 0x18, *self.aliases)
        struct.pack_into('>56H', hdr, 0x88, *self.aliases)
        name_off = self.string(self.defn.MOVESET['name'])
        old = struct.unpack_from('>4I', hdr, 8)
        mb = motbin.build(hdr, bytes(self.strings), self.T, blob, slots, name_offsets=(name_off,) + old[1:])
        pk = self.donor_pack
        items = [pk[o:o + s] for o, s in motion.pack_items(pk)]
        items[0] = motion.extend_mota(items[0], self.new_anims)
        if self.part3 is not None:
            items[3] = motion.replace_mota(items[3], self.part3)
        return mb, motion.build_pack(items)

    def summary(self):
        lines = ['tables: ' + ', '.join('%s %d' % (t, len(self.T[t])) for t in TABLE_ORDER),
                 'new animations: %d (%d bytes)' % (len(self.new_anims), sum(len(a) for a in self.new_anims))]
        lines += ['%s: %d' % kv for kv in sorted(self.stats.items())]
        if self.unmapped:
            lines.append('ids without a TTT2 counterpart (dropped where used): %d' % len(self.unmapped))
        return lines
