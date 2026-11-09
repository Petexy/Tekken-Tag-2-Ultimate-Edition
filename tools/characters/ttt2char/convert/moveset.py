"""A Tekken 7 or Tekken 8 fighter's moveset -> a TTT2 moveset (motbin) and motion pack for the added fighter.

The base is the donor's moveset and motion pack: its generic moves, the tag system, the embedded MOTAs, the hand,
face and camera animations. The fighter's own moves (in its moveset but neither the donor's nor generic) are
converted and appended; the generic "hub" moves that lead into them (standing, crouching, ...) get the fighter's
cancel lists, converted, plus the donor's cancels into TTT2-only moves (tag out, ...). Neither Tekken 7 nor Tekken 8
has a tag: what TTT2's tag system needs in the converted moves themselves (the bound moves' Tag Assault twins, the
landing reactions' Tag Crash rows) is made after the donor's (tagsystem.py). Neither has a bound either: the moves
that bound are the definition's (MOVESET['bounds'], convert/move_overrides.py); screws, tornados and slams do not.

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
from . import gauge as G
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
           460: 'the opponent\'s throw-break state (set)',
           # the player's byte +0x2618 set or int +0x2610 >= 0 (case 0x14187ce81): a Tekken 8 state its battle code
           # starts (0x14190dafd: 0 and 1) and leaves (-1 and 0, also where a fighter is set up: 0x14190a83f), so
           # false outside it. Only off-chain evidence (3 rows) paired it with TTT2's 0 (true), which put rows Tekken 8
           # keeps for that state in front of their plain twins: Reina's hellsweep, 2 ~d and #1782 ~d, Azucena's
           # f,f,F+3,2 ~f into Libertador took the 0x3fff (continue) twin, #1782's 10 frames late
           798: 'a Tekken 8 state (+0x2610 / +0x2618)'},
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
# Tekken 7's screw (Tekken 8's tornado) does not exist in TTT2. Its hit-condition entries test that the combo has not
# used it yet: false here, so an air hit takes the move's next entry (its air reaction), as both games do once the
# screw is used. TTT2's bounds are the definition's moves alone (MOVESET['bounds']: Tekken 7's are the ones the Tekken
# 7 Bound Mod makes bounds). The screw counter's property resets it when the opponent lands, as TTT2's 0x8193 does
# the bound (PROP_OVERRIDE); its value SCREW_SPEND (the screw reactions') spends it and is left out, so a screw no
# longer uses up the bound. The ids are format facts as the community's moveset tools record them (README:
# Acknowledgements)
SCREW, SCREW_COUNTER, SCREW_SPEND = {'t7': 615, 't8': 724}, {'t7': 0x8255, 't8': 0x82c5}, 0
for _g in SCREW:
    REQ_FALSE[_g][SCREW[_g]] = 'screw / tornado not used yet (TTT2 has none)'
REQ_OVERRIDE = {'t7': {}, 't8': {}}                  # requirement ids mapped by the rules below, not the id maps
# Tekken 7's "opponent airborne" (TTT2's 466 through the id maps). Where TTT2 bounds, Tekken 7 often slams instead:
# [614 -> slam][614 -> air][default] in Tekken 7, [467 -> bound][466 -> air][default] in TTT2 for the same three moves
# of Heihachi's (df+1,2 among them); the reaction map makes the slam the donor's bound reaction, which TTT2 plays only
# under 467: a slam plays the donor's air hit after a bound (conv_hitconds), unless the definition makes it a bound
T7_AIR = {'t7': 614, 't8': 723}
# A slam is also told by its standing reaction (lands_at_once): airborne and falling in its first frame only, then
# down (Tekken 7's aDw_tataki). Tekken 8 has that move unnamed, which the reaction map can pair with an air hit:
# after a bound, Reina's d/f+1,2 played TTT2's air spin aDw_ym_y01L with the slam's push down
SLAM_FRAMES = (1, 1, 1)              # airborne start, end, ground fall
# Tekken 8's hit-condition walk (0x1418e94c0) matches an entry by its requirement list; in it, the airborne tests
# 723..725 with parameter 1 make the hit store parameter2 + 1 in a byte of the player's (+0x28a6: the requirement
# function's case 723, 0x14187c16f, reads no parameter). So [723 (1, 40)] tests "opponent airborne" as [723] does,
# and Tekken 8 plays the entry's air reaction (Azucena's d+2,3: #48, the float her Libertador 4,2 follows); TTT2's 466
# takes no parameter (FIT made the entry false). The pair is a side effect TTT2 has not: converted as parameter 0
AIR_SIDE_EFFECT = {'t7': set(), 't8': {723, 724, 725}}
# Requirements TTT2 tests in two rows: Tekken 8's 183 (case 0x1418766d9: the opponent's state +0x434 & 0x407 is 1 or
# 2, on its feet) is its 66 (== 2; TTT2's 63 by the id maps) or 67 (== 1; TTT2's 64, Tekken 7's 67), as TTT2's own
# on-hit follow-ups test it (Jun's Ju_nagi00_H: [458, 63, 81] and [458, 64, 81] -> Ju_nagi02_n). The id maps have no
# TTT2 id for it, so Tekken 8's on-hit follow-ups were lost: Azucena's 1,1 into Libertador, Reina's WS1 into Sentai.
# Both games' contact test 43 is another (below). A cancel row with one becomes one row per alternative
# (conv_cancel_list)
REQ_OR = {'t7': {}, 't8': {183: (63, 64)}}
# Reactions that keep their own move although the TTT2 move the reaction remap puts in their place does the same kind
# of thing to the opponent (Converter.fall: the remap of a stagger, crumple or launch into another kind is refused for
# every reaction, REST): Tekken 7's higher, longer spinning launch dw_daiten (Leroy's d/f+2,1+2, Fahkumram's and
# Kunimitsu's launchers; TTT2's sDw_UP_01_ in its place peaks 0.34 m lower and lands 10 frames sooner, too soon for
# the combos after it); the flip over dw_He_shoryuZ in the downed and wall-slumped slots (Shaheen's b+4, Negan's INT 4,
# 46 attacks of 14 Tekken 7 fighters, 13 of Azucena's: the opponent lifted off the floor again, airborne 1-30, where the
# ground hit dDw_OUC00_ took its place; TTT2 has its animation, no move); the CH stun fall sDm_naraHd_L / _R (Shaheen's
# Stealth Step 4, TTT2's Jun has it: Lars-donor fighters got the trip sDm_DownL00, which floors the opponent before the
# string's next hit). A donor that has the move keeps its own (target(): its names come first)
PRESERVE_T7_REACTIONS = {'dw_daiten', 'dw_He_shoryuZ', 'sDm_naraHd_L', 'sDm_naraHd_R'}
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
# Counted holds: Tekken 7's player variables (words that keep their values from move to move: 359 tests variable
# `param >> 16` == `param & 0xFFFF`, 0x8106 sets it, 0x8107 adds to it, value variable << 16 | amount) have no TTT2
# counterpart, and a list testing one was false. One use of them counts a move's frames: an automatic row back into
# the move whose list it is, keeping its frame (extradata 0x400), its requirements actions alone with 0x8107(variable,
# 1) among them, and a row of the same list that leaves once the variable is N. Noctis's blocked Warp-Strikes
# (Mz_rp00F_GRD, Mz_rush03C_GRD, Mz_t_slpF_RP_GRD ...: `[(359, 29 << 16 | 9)] -> Mz_rp01F_Miss`, the warp forward,
# after 9 frames in the throw's pose) and Kunimitsu II's blocked kunai (Kt_236LP_GRD -> Kt_236LP_GRD2) are such
# moves: with both rows false they never left and played the throw's pose to its end (Noctis hung in the air). In
# such a list the count is a latch's (COUNT_LATCH: the last, which no Tekken 7 row maps to; cleared as a move starts,
# where Tekken 7 sets the variable to 0 in the move before): the counting row runs its actions without leaving the
# move (tagcombo.ACTION_ONLY, move 0x8001), adding 1 every frame, and the list's tests and sets of that variable are
# the latch's
COUNT_VAR = {'t7': (359, 0x8106, 0x8107), 't8': ()}  # a player variable's test (== n), set, add
COUNT_LATCH = 3
COUNT_TTT2 = (LATCH_REQ['ttt2'] + COUNT_LATCH, LATCH_PROP['ttt2'] + 3 * COUNT_LATCH,
              LATCH_PROP['ttt2'] + 3 * COUNT_LATCH + 1)
# Tekken 8's contact test 43 (the attack connected, player +0xf5c & 0x100, and the opponent's state +0x10c & 5 == 1)
# is its 44 without 44's last condition (the opponent's bit 3 clear: case code 0x141875f87 / 0x141875fbf); the id maps
# pair 44 with TTT2's 46 (1324 rows of the generic moves) but have no row for 43, which only her own moves test (on
# contact: Inverse Deva Laser's second part #1621 -> #1622, Eisaimon's early 1RP2, the #775 chain): as Tekken 7's 43
REQ_OVERRIDE['t8'][43] = 46
# Tekken 7's contact tests. TTT2 has two (sub_0404FF30): 46 the move hit (connected, the opponent not blocking), 49 it
# was blocked (47 / 50 the same with Tag pressed: tagcombo.TAG_HIT). Tekken 7 has more, side by side in its moves: 44
# hit (the id maps: 46), 47 blocked (49), 43 either (Geese's [(43)] meter and hit sound are Akuma's [(44)] and
# [(47)] rows in one), 51 the move hit, and 45 a contact that is neither (Noctis's and Kunimitsu's warps go to their
# *_GRD versions on 47 and on 45, Geese's Jyaei to its second part on 44, 47 and 45, Akuma's meter rows on 45 have no
# hit sound). 43 and 51 have no id map row, so their lists were false: Kunimitsu's u/f+3+4,4 jump-off on contact
# (Kt_jpWK00F_RK -> Kt_jpWK00F_RK_H), Akuma's, Geese's and Eliza's on-contact rows (130 of 7 fighters), the on-hit
# versions X `[(51)] 0x401 -> X_H` TTT2 has as X `[(46)] 0x401 -> X_H` (Katarina's Ln_rk03_H, Master Raven's
# Nj_rollk00_H, Geese's My_WPF_H, Noctis's Mz_rk01F_HIT), the hit grabs `[(2), (51), (96), (66 | 67)]` (Noctis b+2,1+2,
# Lidia's Nd_1lkHIT2) and Noctis u/f+3's second kick. 51 becomes 46. 43 becomes TTT2's two, a cancel row on 46 and
# one on 49 (REQ_OR), as TTT2's own lists test them side by side for one follow-up or two (Law's Lw_runki00: [49] ->
# Lw_runki00GE before [46] -> Lw_runki00E, so 49 is no hit; Kuma's Km_spgoro, Jin's Jz_m_k20 alike); in any other
# list (a hit condition, an extra property's) 43 is 46, the hit alone. 45 fell between the anchors 44 -> 46 and
# 47 -> 49 and became 47, so those rows fired on a hit with Tag held: false, TTT2 has no third contact
REQ_OVERRIDE['t7'].update({43: 46, 51: 46})
for _g in REQ_OR:
    REQ_OR[_g][43] = (46, 49)
# Tekken 8 alike: its 51 is player +0x6fc bit 0x40 (case 0x1418763db), which the hit's registration sets
# (0x14188a72c) and a blocked one does not: the move hit, 46 (Miary Zo's u+4, 4,4 and four more strings into Baobab
# Mihira on hit, #1522 / #1572); its 49, the byte +0x67c (case 0x1418763c5) set to 1 where a hit or a block registers
# (0x1418703c9, 0x141884f45, 0x141885204), is a contact either way: 46 or 49 in a cancel list, 46 elsewhere (her
# f,f+2,2, 8LK, 6LK_8WP, 6LK_WP, 666LK on contact). Neither had an id map row
REQ_OVERRIDE['t8'].update({51: 46, 49: 46})
REQ_OR['t8'][49] = (46, 49)
REQ_FALSE['t7'][45] = 'a contact neither hit nor block'
# Throw breaks: Tekken 8's 131..134 call one test (0x1418756a0) with break kinds 1..4 (135: the kind in `param`),
# TTT2's 129..131 test kinds 1..3 (sub_0404FF30 stores 1 / 2 / 3 at +598): 1, 2 and 1+2 (Jun's Ju_Cnage01_y
# `[(131)] win 1-15 -> nuke36_n`). The id maps pair 131 / 132 with 129 / 130 but have no row for 133, which Tekken 8
# lists beside its throw-break state (`[(461), (133)]`: unequal lists give no evidence): 1+2 throws (Jun's Cnage,
# Azucena's u/f+1+2) were unbreakable
REQ_OVERRIDE['t8'][133] = 131
# Distance tests: Tekken 8's and TTT2's 3..22 and 27..34 share one routine in each game (Tekken 8 0x141875b41, TTT2
# 0x04050B28: the opponent in zone <id> within `param`), 23..26 have their own in both alike; Tekken 8's 491 / 493 are
# zones 3 / 7 with the zone's angle in param2 (0x141875bde), which TTT2's 3 / 7 take from their own table. The low
# throws test 493 (Azucena's Smell the Coffee ThrmvLOW_00 `[(493, 1600, 110)]`, TTT2's King `[(7, 1536)]`; 20 rows
# of the saved fighters): no id map had them, so those throws never caught anyone
REQ_OVERRIDE['t8'].update({491: 3, 493: 7})
# ... and the parameter of a distance test is a distance in both games' units (the Ultimate Tackle tac02xk: Tekken 8
# `(23, 1408)` and `(24 / 25 / 26, 1600)`, TTT2 `(23, 1408)` and `(24 / 25 / 26, 1536)`): FIT does not test it (TTT2
# passes 1536 alone with 24..26, so the tackle's side and back catches were left out)
DISTANCE_REQ = {'t7': set(), 't8': set(range(3, 35))}
# A cancel row that only takes its requirement list's actions has extradata 0x2800 in TTT2 (60251 rows of its own
# movesets, none 0x2c00); Tekken 8 also writes 0x2c00 (Reina 26 rows, Azucena 3). In game such a row taken on the hit
# (`auto [hit, 0x8001, sounds]`) kept every later hit row of the move from being taken: Reina's low sweeps' Sentai row
# (#1797 -> #1801) played only when moved before it, as her 0x2800 rows before Heaven's Wrath 3,4's dispatch let it
ACTION_ROW = {'t7': None, 't8': (0x2c00, 0x2800)}
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
# a property whose value is a move id (TTT2's 0x8128: the opponent goes into that move of this moveset; Jun's parry
# Ju_koushu0 puts the attacker in Ju_sabarp_y, Gigas's f+1+2 victim Cz_zutuki_y puts Gigas in his headbutt
# Cz_Head_Wall_E at a wall): the converted move's index, the property left out when the move is not converted. The
# value passed as it was, a Tekken 7 / 8 move index, so the opponent played another move of the pack (Lars's elbow
# La_sphizi there; the parries of Fahkumram, Leroy, Lidia, Noctis and Reina put the attacker in moves of the donor)
MOVE_PROP = {'t7': 0x81d4, 't8': 0x8244}
# FIT: Tekken 8's values pass the id maps as they are, in Tekken 8's own numbering where an id's meaning has one TTT2
# has not (item, face animation and move numbers, roster ids). A converted row of a Tekken 8 fighter whose value (a
# requirement's parameter) lies outside the values TTT2's own movesets pass with its TTT2 id, lowest to highest (in
# the same kind of list: idmaps.ttt2_values; an id they never pass a value with: none fits) is left out, a requirement
# making its list false (an action in a requirement list is left out, the list kept). Values the converter converts
# itself (VALUE_KIND, sounds, projectiles, move ids, characters) and the ids of the overrides (format facts) are not
# tested. Reina: 0x803d -> 0x8022 (1233 .. 3856 where TTT2 passes 0 .. 35), 0x8219 -> 0x8110 (1: TTT2 passes 0),
# 0x8084 -> 0x8056 (TTT2's movesets never use it), her own 143 -> 139 (100: TTT2 tests 17 .. 46), ...
PARRY = {'t7': {817, 823}, 't8': set()}            # parry lists: not converted
# the meter (Tekken 7's EX moves and supers): its requirement and its cost; left out with free_meter_specials, kept on
# the runtime's gauge ids for a definition with GAUGE (convert/gauge.py)
METER, METER_COST = {'t7': 629, 't8': 738}, {'t7': 0x81c2, 't8': 0x8232}
EFFECT_PROP = 0x801f                 # spawn an effect: value = body part << 8 | effect id
# Effects at a hit location: Tekken 7's 0x802e (the id maps' 0x801d: the fighter's own hit effect, item database id 0)
# and 0x803f (0x8028: the same with the hit's flash), value the location as a move's hit box numbers it. TTT2 places
# both with its hit locations' resolver (sub_03AE86A0 calls sub_03C7A600: 0..29 the body's bones, 30..77 its fixed
# points, 70..77 a held item's), which has no case for a code above 77: the effect appeared where the last one had.
# Tekken 7's weapon fighters name their weapons' points there (Noctis's sword tips 0x5f .. 0x67 on his sword hits,
# Kunimitsu II's blades 0x74 / 0x75): those take the TTT2 location their hit boxes get (hit_locations: the weapons'
# points and the definition's HIT_LOCATIONS)
EFFECT_AT = {'t7': {0x802e, 0x803f}, 't8': set()}
# Tekken 7 spawns effects with 0x8036 (the id maps find 0x801f) and, in a few moves, 0x8038 (the same value). Tekken 8
# spawns them with 0x8039 (its 0x8036, the id maps find 0x801f too, stops them as 0x8035 does: the same family of moves
# has either at the same frame) but numbers its own effects, which nothing converts (the pack has no effects of a
# Tekken 8 fighter): left out (PROP_DROP)
EFFECT8_SPAWN, EFFECT8_STOP = 0x8039, 0x8035   # ... except the ids a definition attaches (convert/effects8.py)
EFFECT8_TRAIL, EFFECT8_TRAIL_END = 0x831c, 0x831d   # a weapon's trail: a definition's TEKKEN8_TRAILS (convert/trails8.py)
PROP_OVERRIDE = {'t7': {0x8255: 0x8193, 0x8256: 0x8194, 0x8038: EFFECT_PROP}, 't8': {0x82c5: 0x8193, 0x82c6: 0x8194}}
# Moveset variables: numbers of a player's that its moves set and test (TTT2's at player +1532 + 4k, counted down each
# frame by the game). TTT2 tests variable k with 232 + k (>= param) and 261 + k (<= param) and sets it with VAR_SET[k]
# (sub_03AE86A0's table, id - 0x8058: 0x8064..0x8067 set 0..3, 0x806C (set, + 1 add, + 2 subtract) 4, 0x806F 5,
# 0x8072 6); Tekken 7 with 251 + k, 288 + k and 0x8076 + k (k < 4). The id maps anchor what TTT2's movesets use too
# (the >= tests, 289 -> 262 and 0x8077 -> 0x8065: the generic side steps' variable 1), not 290 / 0x8078 (variable 2:
# Leroy's Sugar cooldown, 210 frames after Go Sugar, 390 after a miss; his 2+3 rows test 290 <= 0) or 292 (variable
# 4: the way back in a loop of Master Raven's moves, Nj_*A*w), so those rows were false and Sugar never came out
VAR_GE, VAR_LE = 232, 261
VAR_SET = (0x8064, 0x8065, 0x8066, 0x8067, 0x806C, 0x806F, 0x8072)
VAR_PROPS = {0x8076 + k: VAR_SET[k] for k in range(4)}
REQ_OVERRIDE['t7'].update({288 + k: VAR_LE + k for k in range(5)})
REQ_OVERRIDE['t7'].update(VAR_PROPS)                 # (properties inside requirement lists)
PROP_OVERRIDE['t7'].update(VAR_PROPS)
PROP_OVERRIDE['t8'].update(LATCH_PROPS['t8'])        # the latches' properties (LATCHES), as extra properties too
# (Only variables 1..3 are counted down each frame: sub_04336854 near 0x04339A20 subtracts 1 from +1536..+1544 while
# above 0 and adds 1 to +1532; 4 and on keep their values. sub_0404FF30's tests are unsigned compares, and a property
# reaches its handler as value & 0xFFFF.) Variables 4..7 at +1548 + 4(k - 4) and 8..10 at +1564 + 4(k - 8): tests
# >= 232 + k / 243..245, <= 261 + k / 272..274, == 290 + k / 301..303; set, add, subtract 0x806C + 3(k - 4) / 0x8081
# + 3(k - 8) and the next two.
def var_ids(k):
    """TTT2's ids of moveset variable k (4..10): (>= test, <= test, == test, set, add, subtract)."""
    if 4 <= k <= 7:
        return VAR_GE + k, VAR_LE + k, 290 + k, 0x806C + 3 * (k - 4), 0x806D + 3 * (k - 4), 0x806E + 3 * (k - 4)
    if 8 <= k <= 10:
        return 235 + k, 264 + k, 293 + k, 0x8081 + 3 * (k - 8), 0x8082 + 3 * (k - 8), 0x8083 + 3 * (k - 8)
    raise ValueError('moveset variable %d has no set / subtract of its own' % k)


# Tekken 8's flag slots (FLAG8): ten per player (+0xde4, 8 bytes {lifetime, value}). 507 (param the slot, param2 a
# value) tests slot.value == param2 (case 0x14187b150); 0x815a (value the slot, value2 the lifetime, value3 the value)
# sets both (handler 0x1418980c0), as an action of a cancel row's requirement list, an extra property or a begin / end
# property. The lifetime counts moves, the setting one included: as a move starts it goes down by one, and at 0 the
# slot is clear (Miary Zo's: b+2's 3 sets slot 0 for 1 move, and b+2 tests it at frame 13 for b+2,3; f+1+2's 1+2
# sets it for 2 moves, f+1+2 and its automatic second hit, which tests it for the third; the 10-hit combo's 5th hit
# sets slot 1 for 2 moves, the 6th tests it for the 7th; 26 of 31 Tekken 8 fighters' movesets have them). The id maps
# paired 507 with TTT2's 0 (true; FIT kept (507, 0, x) as it, left the other slots false) and had no row for 0x815a:
# b+2 always went on to b+2,3, f+1+2 played all five hits unpressed, and the 7th hit and f+1+2,1+2,3+4's ender never
# came out. TTT2 has no such slots: a slot the fighter both sets (value 0 or 1 only) and tests is a moveset variable no
# TTT2 moveset of the donor's uses (FLAG8_VARS in turn: 7, which no TTT2 moveset uses, 6 and 5, which only Tekken 7
# definitions' state_flags take, then 10 and 4) holding the lifetime left: a set is (set, lifetime if value else 0),
# a test of value 1 (>= 1), of value 0 (<= 0), of another value false; every cancel list converted from the fighter's
# starts with one action row per variable (window 1-1, no input: tagcombo.ACTION_ONLY) that takes one off a variable
# above 0 as the move starts. A slot without a variable is never set: its sets are left out, its value-0 tests true.
# Tekken 8 also tests slots in extra properties' requirement lists (state values 0x81fa -> TTT2's 0x80f8 as the move
# starts: Reina's d/f+1,2 on hit, Miary Zo's string enders, her Heat Tromba's weapon); TTT2's extra properties have no
# conditions, so such a property (and a set as an extra or begin property) is an action row of the move's list at its
# frame (1 for the start), after the countdown rows
FLAG8_REQ = {'t7': None, 't8': 507}
FLAG8_PROP = {'t7': None, 't8': 0x815a}
FLAG8_VARS = (7, 6, 5, 10, 4)
# Wall tests: Tekken 8's 194..201 (cases 0x141879ebd..0x14187a0ff) call 0x1419672b0(player, out, param as the
# distance, 360.1 degrees, the facing +0x17e * 2pi / 65536 plus 0 / 0 / pi / pi / pi/2 / pi/2 / -pi/2 / -pi/2, 1, 0):
# a wall within `param` in front, behind, to the side +pi/2, to the side -pi/2; the even ids true when there is one,
# the odd ids when there is none. TTT2's 174..181 (sub_0404D868(player, axis, frame, param >> 8, param & 0xFF)) are
# the same test on the same rotation (rows (cos, 0, -sin) and (sin, 0, cos) in both; sinf / cosf told by their value
# at 0), front, back, local +x (forward turned by +pi/2), -x, even = a wall (along the facing or the screen),
# odd = none along the facing, the low byte the largest angle between the wall and the way (|cos|, 90: any wall; its
# tag system's runs out use them: Co_runchng 640080 = 2500 << 8 | 80). No id map has them: Miary Zo's Mikisaka Malaky
# (b+3+4, u+3+4, d+3+4: 196 / 198 / 200 (950 / 1250)) never went on to Tromba at a wall
WALL8 = {'t7': {}, 't8': {194 + n: 174 + n for n in range(8)}}
WALL_ANGLE = 90
# "The move hit" kept to the move's end: TTT2's 46 holds on the hit's frame only. Each frame sub_039C8D64 clears the
# four players' hit bits (+1152 & 0x00300000: sub_03ADB680 -> sub_03ADB5E4) before the hit pass (sub_03ADCBA8 ->
# sub_03ADBD10 sets 0x00200000, 46's, on the attacker as a hit registers), and TTT2's own rows test 46 / 47 / 49 / 51
# inside the active frames only (none of 2239 starts after the last). Tekken 8's 51 (+0x6fc & 0x40, set by the hit)
# and 49 (+0x67c, hit or block) keep their value: Miary Zo's u+4 (active 16-17) goes on to Baobab Mihira at frame 17
# when it hit, and so do u/b+4 and the strings' enders (frames 19 .. 30), f,f+2's 2 and four more follow-ups on contact.
# In game, with 51 as 46, u+4 hit on frame 16 and never went on. A cancel list testing them (HIT_HELD, the hit
# alternative of REQ_OR) gets a latch none of its rows and moves use (the last first; latches are cleared as a move
# starts): its first row, an action on the hit's frame, sets it to 1 [(46), (set latch, 1)], and the tests are the
# latch's (== 1). In a group list (shared by moves) and in other lists they stay 46
HIT_HELD = {'t7': (), 't8': (51, 49)}
HIT_NOW = 46                                         # TTT2: the move's attack hit on this frame
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
# Automatic evades (Tekken 8: Azucena's Libertador ducks a high attack, #1649, and hops a low one, #1637; dog's, okm's,
# lon's and bbn's alike). Tekken 8 sets them with properties (its interpreter's cases 0x14189dfa2..0x14189e006):
# 0x8606 = the evade's frames (player +0x19bc, counted down every frame, cleared as a move starts; 0x7fff: the rest of
# the move) and per slot (value2: two of 32 bytes at +0x19d0) 0x8607 the evade move, 0x83ea the hit-level class it
# takes (1 high, 2 mid, 3 low, any other value any attack), 0x83eb a direction test (her angle to the attacker below
# 60 .. 180 degrees for 1..7) and 0x83ec (the evaded hit's effects left out). When an attack of the class connects
# (the attacker's hit registration: 0x1418703b5, 0x141884ee0 ... -> 0x141904f70), the hit is voided and her move
# becomes the slot's (0x14196aab0, extradata 0x80); a hit of another class ends the evade. TTT2 does that with
# cancel rows, its parries: no input, requirement 678 / 679 / 680 (the opponent's high / mid / low attack by its hit
# level, 0x512 0x806 / 0x217 0x31f 0x707 / 0x10f 0x41f: Tekken 8's classes, the two facing each other within 60
# degrees) or 682 / 683 / 684 (the opponent's back turned), parameter the attacking limb (sub_0404D5C0: 0 any, but
# an attack with hit location 64, a kiss, a laser or mist, which only 64 takes). Lei's Crane stance (5tsu_P) parries
# lows so: such rows first in its list, 1-32767. So a converted move with an evade gets, first in its list, a row per
# slot, test and limb over the evade's frames into the slot's move (evade_rows); TTT2 has no other direction tests.
# In game (Azucena in Libertador, Jun attacking): jabs and low kicks turn into the duck / the hop on their active
# frame and miss, the hop's kick hits back, a mid hits her, as in Tekken 8
EVADE = {'t7': None, 't8': {'frames': 0x8606, 'move': 0x8607, 'class': 0x83ea, 'direction': 0x83eb, 'mark': 0x83ec}}
EVADE_TESTS = {1: (678, 682), 2: (679, 683), 3: (680, 684)}      # Tekken 8 class -> TTT2's tests (faced, back turned)
EVADE_LIMBS = (0, 64)
EVADE_EXTRA = 0x80
EVADE_FOREVER = 0x7FFF
# properties left out (presentation or mechanics TTT2 has not, or values not converted yet)
PROP_DROP = {
    't7': {0x828f: 'tiger animation', 0x828e: 'projectile index', 0x81bd: 'power crush',
           0x81be: 'rage art fx', 0x801b: 'rage drive vfx', 0x8233: 'rage drive bg', 0x8234: 'rage drive bg',
           0x8272: 'spend rage', 0x828b: 'game speed', 0x828c: 'slow motion', 0x828d: 'slow motion immunity',
           0x829d: 'HUD', 0x829f: 'subtitles', 0x8243: 'subtitles', 0x82bf: 'assist vfx',
           0x8414: 'assist combo value', 0x842e: 'hand animation (none of the HANDS row\'s: HAND_PROPS)',
           0x842f: 'hand animation (none of the HANDS row\'s: HAND_PROPS)', 0x8435: 'camera/item animation id',
           0x8049: 'item id', 0x8343: 'attach item', 0x8344: 'detach item'},
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
PLAYER_SOUND8 = 0x87f0
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
TIGER_PROP = {'t7': 0x828f, 't8': 0x83aa}  # (Tekken 8's: Miary Zo's snakes' clip k, convert/snakes8.py)
OPT_ANIM_PROP, OPT_ANIM_BASE = 0x82de, 0x4000
# A fighter's own state Tekken 7's game keeps for it, which TTT2 has not (unmapped, its tests made their lists false):
# Claudio's Starburst (351 == param; 0x81bf 1 / 0 gives it / uses it up) and Leroy's cane (641 not used yet, 642 used;
# 0x82eb uses it). The definition's MOVESET['state_flags'] {name: {'variable': k, 'prop': id, 'equals': id | 'clear':
# id, 'set': id}} keeps it in moveset variable k (VAR_SET), one no TTT2 moveset uses (5, 6): on is FLAG_ON (frames,
# as the game counts it down), a test of it on VAR_GE + k >= 1, off VAR_LE + k <= 0. No round start clears it that
# is known: it lasts until a move uses it up
FLAG_ON = 0x7FFFFFFF
# (Tekken 8's 0x8258 is Tekken 7's 0x81e8, TTT2's 0x813b: the pushback a wall hit's rows give, an index of the
# fighter's pushbacks. Tekken 8's wall pair 4 / 6 is TTT2's 0 / 1; as it was, the index named the pack's 4, a 1.3 m
# push that at the wall moved the attacker away: Azucena's ws4,1,3)
VALUE_KIND = {'t7': {0x81e8: 'pushback', 0x8331: 'reaction', 0x8332: 'reaction', 0x843c: 'throwcam', 0x843d: 'throwcam',
                     0x820b: 'projectile'},
              't8': {0x8258: 'pushback', 0x8478: 'reaction', 0x8479: 'reaction', 0x868f: 'throwcam',
                     0x8690: 'throwcam', 0x827b: 'projectile'}}
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
# TTT2's same moves have 0 most often (18 of the 48 pairs of 134; 133 has none): 0, the foot or knee alone.
# Tekken 7's points past the end of a limb and in the trunk (0x21..0x37) TTT2 numbers otherwise. The id maps pair
# only 0x2e / 0x2f (-> 37 / 38); kept as they were, the others named TTT2's points of other things (0x25, a right
# fist's, as 37 the left foot's; 41..60 a thrown item's, Yoshimitsu's sword's, other fighters' parts), most of them
# placed nowhere for an added fighter (its hit test read (0, -10000, 0) or (0, 0, 0): Leroy's d/b+2 on a downed
# opponent, (0x29, 0, 0x29, 0x30), hit nothing). By the points they pair with (a line to the elbow or the shoulder,
# the knee or the thigh) and by TTT2's own moves of the fighters Tekken 8 has too (which numbers them as Tekken 7):
# the right fist's 0x24 0x25 0x28 0x29 0x33 0x35 and the left's 0x26 0x27 0x2a 0x2b 0x32 0x34 -> TTT2's points past
# the fists (40 / 39), the right foot's 0x2d 0x2f 0x31 0x37 and the left's 0x2c 0x2e 0x30 0x36 -> past the feet
# (38 / 37). 0x21..0x23 pair with every limb's end, the hips and each other: points of the trunk, 0x21 -> the hips
# (as some of TTT2's same moves have it, and its item moves' (70, 3)), 0x22 the chest, 0x23 the neck (Kuma's)
T7_BODY_POINTS = {**dict.fromkeys((0x24, 0x25, 0x28, 0x29, 0x33, 0x35), 40),
                  **dict.fromkeys((0x26, 0x27, 0x2a, 0x2b, 0x32, 0x34), 39),
                  **dict.fromkeys((0x2d, 0x2f, 0x31, 0x37), 38), **dict.fromkeys((0x2c, 0x2e, 0x30, 0x36), 37),
                  0x21: 3, 0x22: 2, 0x23: 4}
HIT_LOCATION = {'t7': T7_BODY_POINTS, 't8': {125: 70, 133: 0, 134: 0}}
# Tekken 8's limb points: a fist's, foot's or knee's front beside the limb's bone (Reina's jab (13, 0)(43, 12), her 2
# (9, 0)(36, 8), Azucena's f+4 (16, 0)(55, 14), her f+3 (19, 19)(46, 141)). Their numbers are TTT2 points an added
# fighter's hit test has no place for (in game, the hit test's slots for Reina: 41..44 at (0, -10000, 0) as no item
# writes them, 36..38 by her feet: 36 ahead of them 0.1 to 0.2 m under the floor, 37 0.15 m above 36, 38 behind her;
# 53..55 no TTT2 move uses, > 77 none), and the id maps' chain cannot take them (several to one bone, below their
# numbers) or takes them to those points (44 -> 36, 46 -> 37, 47 -> 38): her jab's capsule ran from the elbow to 10 m
# under the stage, Azucena's f+3 and f+4,4,3 hit nothing (and her 2,1,2 and d/f+4,1 reached a pushed opponent only
# with that capsule). Each becomes, before the id maps, the point of its limb TTT2's same moves pair it with (the
# alignment's evidence with the saved Tekken 8 fighters: 37 hand_R x101, 41 x33, 39 hand_L x39, 43 x21, 46 foot_L
# x95, 47 foot_R x69, 54 x5, 55 x12, 140 knee_R, 141 knee_L, 33 the hips x11, 52 elbow_L): a fist's the fist point
# TTT2 keeps 0.1 m ahead of the hand (40 right, 39 left; in game they follow her hands), which keeps Tekken 8's reach
HIT_POINT8 = {**dict.fromkeys((36, 37, 40, 41, 51, 53), 40), **dict.fromkeys((38, 39, 42, 43, 50), 39),
              **dict.fromkeys((45, 47, 49, 55), 16), **dict.fromkeys((44, 46, 48, 54), 19),
              140: 15, 141: 18, 33: 3, 52: 12}
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
# Negan's moves show and hide the items of his weapon mesh with 0x82c4 n / 0x82c5 n instead (0 the bat in his left
# hand, 1 the knife, 2 the bat in his right hand; no other fighter uses these ids): the same summons. Kunimitsu II's
# with 0x8300 n / 0x8301 n (only her moveset has them): 0 the short sword in her left hand, 1 the kunai in it, 2 the
# sheathed sword in her right hand (intros), 3 her kunai in her right fist, 5 and 6 the knife and the sword in the
# sheath at her hips, 7 that sheath; a sword move shows 0 and hides 6 as she draws, and the other way round as she
# sheathes it. Some items are out before any move shows them (her kunai, her sheath): Tekken 7 starts a round with
# them out and its moves end so; default_summons finds them, and summon_reset takes them out again where the summons
# are put away (her stance, the donor's moves).
TT_SUMMON, TT_DISMISS = 0x822E, 0x822F
TT_DISMISS_ALL = 16
# The fingers: a hand shows a frame of the moveset's hand shapes (ttt2/motbin.py HAND_SHAPES: TTT2 0x82d6 left,
# 0x82d7 right, 0x82d9 both back to their defaults; Tekken 7's own shape properties map to them), or a hand
# animation (Tekken 7's 0x842e / 0x842f, TTT2's 0x82db left / 0x82dc right, value HAND_OWN | n: animation n of the
# motion pack's hands container, ttt2/motion.py), until a move gives it another. The shapes are the moveset's own
# (the donor's: Jun's hands are open where Kunimitsu II's are fists), and the two games' hand animations are
# numbered and made apart; but a fighter TTT2 has keeps its hands: the definition's HANDS names that TTT2 motion row,
# whose hand shapes the fighter's moveset takes (Kunimitsu II's right fist round her kunai, Tekken 7's default right
# hand: her stance gives only her left hand an animation), and a Tekken 7 hand value the fighter's moves share with
# that row's moves of the same name becomes that row's animation, copied into the pack's hands container (or the
# donor's own of the same bytes: Converter.hand_map; Kunimitsu II's stance's open left hand). The other values are
# left out (PROP_DROP).
HAND_PROPS = {'t7': {0x842e: 0x82db, 0x842f: 0x82dc}, 't8': {}}
HAND_OWN = 0x4000
# ... and a Tekken 8 fighter (Converter.hands8, tekken8/anim.py) has
# its own: 0x8610 left and 0x8611 right name a hand clip, until a move gives that hand another, also on the generic
# moves it shares with the donor (hands8_generic); the hand shapes a hand goes back to take its stance's first frame,
# so the donor's open hand never shows and a move's return to the stance meets the stance's clip (TTT2's own moves,
# which Tekken 8 does not have, keep theirs).
HANDS8 = {0x8610: 0x82db, 0x8611: 0x82dc}
HAND_ROWS = frozenset((0x82d6, 0x82d7, 0x82d9, 0x82db, 0x82dc))     # (TTT2's, all of them)
HAND_SHAPE_LEFT, HAND_SHAPE_RIGHT = 1, 2                            # the frames of the hand shapes a hand goes back to
HAND_SHAPES_OPEN = (3, 24)          # (both hands', when hit and down, and running: the donor's open hands)
SUMMON_PROPS = {'t7': {0x82a7: TT_SUMMON, 0x82a8: TT_DISMISS, 0x82c4: TT_SUMMON, 0x82c5: TT_DISMISS,
                       0x8300: TT_SUMMON, 0x8301: TT_DISMISS},
                't8': {0x8317: TT_SUMMON, 0x8318: TT_DISMISS}}
SUMMON_EFFECT = {'t7': 0x82af, 't8': 0x831f}
# --- Tekken 8 summons and hit points (convert/summons8.py) ---------------------------------------------------------
# its show / hide rows become the summon ids above before the converter runs (summons8.prepare), so its end properties
# (hide as the move ends) map too; its limb points TTT2 has no place for get TTT2's (summons8.HIT_POINTS)
from .summons8 import HIT_POINTS as _HIT_POINTS8  # noqa: E402
PROP_OVERRIDE['t8'].update(SUMMON_PROPS['t8'])
HIT_POINT8.update(_HIT_POINTS8)
# --------------------------------------------------------------------------------------------------------------------
# A thrown weapon that hits stays where it hit (Noctis's Warp-Strike: Tekken 7 dismisses the sword as it hits, with
# particles of its mesh lingering there, which convert/particles.py leaves out): the move a hit leads to (the
# definition's WEAPON_HOLD, by Tekken 7 name) starts with this property (another id TTT2 ignores and no moveset uses),
# and the runtime keeps the thrown weapons there, drawn though dismissed, until the warp takes them back (roster.cpp,
# weapons)
WEAPON_HOLD_PROP = 0x822B
EFFECT_STEP = 6                      # frames: effect ends closer than this share a copy (split_effects)
EFFECT_SPARE = range(229, 160, -1)   # ids for the copies: above Tekken 7's (100..160), below the projectiles' (230)
TRAIL_SPARE = range(100, 230)        # ids for a Tekken 8 fighter's trails (convert/trails8.py): above its own ids
DAMAGE_AMOUNT = {'t7': 0x821b, 't8': 0x828b}
DAMAGE_DEAL = {'t7': {0x821c: 0x8058, 0x821d: 0x8059}, 't8': {0x828c: 0x8058, 0x838a: 0x8058, 0x838f: 0x8058,
                                                              0x828d: 0x8059}}
# Floor breaks. TTT2 breaks a stage's breakable floor when a row 0x8138 of the victim's move fires (sub_03AE6B6C; then
# every player above the hole falls, the victim by the row's value: 0 a hit's fall, 1 a thrown one, 10 points): its
# throws have the row some 20 frames after the victim lands (He_FRnage_y lands at 81 and breaks at 100, Jack's pile_y
# 139 and 160), its bound reactions 20 frames in. Tekken 7's 0x81e4 is the same row (the id maps carry it over).
# Tekken 8 marks the victim's move for its whole length instead (FLOOR_BREAK8 at frame 0x8001) with a strength, and
# the moment by a ground-impact row (FLOOR_IMPACT8) where the body hits the floor (He_FRnage_y's at 81): 80 (a few 90,
# 100) on throws, attack throws and Heat slams, all of them ending with the victim down; 70 (a few 50) on spikes and
# staggers that end on its feet, below a floor's strength. Its values are no TTT2 values (the id maps leave it out:
# idmaps.distrust), and a row at the move's start would break the floor as the throw begins. So a move with a row of
# at least FLOOR_BREAK8_MIN gets TTT2's row (value 1) FLOOR_BREAK_WAIT frames after its impact, else (a hit's
# reaction, below) after its landing row (LANDING, where TTT2's throws have theirs: the same frame in both games), else
# after the frame its animation's hips first come down below LYING_HIPS from STANDING_HIPS or above; a Tekken 8 row
# with a frame of its own (100 at 80 on Jack's hataki_y, TTT2's frame) keeps it; one past the animation's end (it
# would never fire) sits on its last frame. A move with no such moment gets none, nor does a weaker one
# (Converter.floor_break_rows).
# The impact rows are where Tekken 7 had its floor break: its air slam aDw_tataki and bound dwup_hei_xe break at 18 /
# 20, Tekken 8's same moves have an impact there instead and no mark (those reactions become the donor's dwup_hei_x*,
# which break the floor at 20 already). A throw (THROW_LEVEL) breaks the floor where its victim's move has the
# impact, marked or not: King's Jaguar Bombs (Kg_AirRRbom_y, Kg_AirRollbom_y), his Neck Breaker (Kg_kinstn_y) and
# Reina's SSH CH 3 attack throw (Zbr_6WP_LK_y) have no mark, and are floor breaks in Tekken 8; the 12 with a TTT2 move
# of the same name (Kg_kinstn_y, Fu_houounage_y, I_GJ_B_y, ...) break the floor in TTT2 too. A marked throw victim
# without an impact is a toss that breaks balconies, not floors (Reina's u/f+1+2 He_hp2_y and d,d/b,b,f+2
# Zbr_2146RP_y, Miary Zo's u/f+1+2; the 12 with a TTT2 move of the same name, He_hp2_y, Kz_hp2_y, ..., do not break
# the floor in TTT2 either): no row. A hit's reaction breaks by its mark only (a Heat slam's); one with an impact and no
# mark is a spike on a standing opponent (Reina's d+2 on counter hit): no row.
FLOOR_BREAK = 0x8138
FLOOR_BREAK8 = {'t7': None, 't8': 0x83ce}
FLOOR_BREAK8_MIN = 80
FLOOR_IMPACT8 = 0x8379
LANDING = 0x800e
FLOOR_BREAK_WAIT = 20                # TTT2's own throws: 19 .. 26 frames after the landing
LYING_HIPS, STANDING_HIPS = 350.0, 600.0     # mm (an animation's hips height: channel 1 y)
PLAIN_FRAME = 0x4000                 # Tekken 8 row frames from here on are no plain frame of the move (0x8001: all)
THROW_LEVEL = 0xA00                  # a throw's hit level (its low half), in both games
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
# A reaction move the donor has no move of its own for takes the TTT2 move the evidence puts in its place
# (idmaps.reaction_remap). That evidence can be a move whose effect changed between the games, counted once per
# reaction slot (Azucena's Libertador 1 staggers in Tekken 8, sDm_KAOLee, 8 of the 28+ pairs said TTT2's knock-down
# sDw_KAO00_; her 2,1,2 and d/f+4,1 launch, dw_He_shoryu, had become the crumple sDm_KAKCca; Tekken 7's CH trip
# sDw_utuharai_r, airborne for a combo, the sweep knock-down sDm_Fjn00C: Master Raven's d/b+4, Katarina's FC d/f+4),
# or another fighter's move where TTT2 has the reaction in other movesets only (Tekken 7's trip sDm_DownL00 is Lars's:
# Jun-donor fighters got a standing leg stagger, Lidia's Cat Foot Stance II 4,4, or a sweep from behind, Katarina's
# d/f+3,3; the crumples dm_hara_07L / R and sDm_LBdowCE, TTT2's too, the spins sDm_PNGL0_ / R0_ and ym_y01L). So a
# reaction does not take a TTT2 move that does another kind of thing to the opponent (Converter.fall, by REST: where
# its transitions come to rest and whether one of them, the reaction itself first, is airborne): keep it on its feet,
# fell it without leaving the ground (a crumple), or put it in the air (a launch, a trip); the source's own reaction is
# converted instead (its class T or N move, its animation). Air, down and wall reactions keep TTT2's where they are the
# same kind (TTT2's bounds and Tag Crash need them; a Tekken 7 slam takes the donor's bound reaction, T7_AIR).
REST = (('stand', re.compile(r'sKAM00_$')), ('crouch', re.compile(r'^cKAM')), ('down', re.compile(r'^d(w|Dw)')))
REST_STEPS = 12                   # transitions followed at most
ANIM_KEY_BYTES = 256                 # animations are matched by a hash of their first bytes


def state_flags(moveset):
    """A definition's MOVESET['state_flags'] -> ({test id: (variable, 'equals' | 'clear' | 'set')}, {property id:
    variable})."""
    tests, props = {}, {}
    for flag in moveset.get('state_flags', {}).values():
        props[flag['prop']] = flag['variable']
        tests.update({flag[kind]: (flag['variable'], kind) for kind in ('equals', 'clear', 'set') if kind in flag})
    return tests, props


class ParamAsValue:
    """A requirement row (an action) seen as the property row it was made of: its 'value' is the row's 'param'."""

    def __init__(self, row):
        self.row = row

    def __getitem__(self, key):
        return self.row['param' if key == 'value' else key]

    def __setitem__(self, key, v):
        self.row['param' if key == 'value' else key] = v


def rev32(v):
    return int('{:032b}'.format(v)[::-1], 2)


def hit_location(game, x, hit_locations, hitbox):
    """A hit location code of `game` (a byte of a move's hitbox) -> TTT2's: a weapon's point (its bone's number) or
    the definition's HIT_LOCATIONS (hit_locations), else a Tekken 8 limb point's (HIT_POINT8), else the id maps'
    (hitbox), else HIT_LOCATION's."""
    if x not in hit_locations and game == 't8' and x in HIT_POINT8:
        return HIT_POINT8[x]
    return hit_locations.get(x, hitbox.get(x, HIT_LOCATION[game].get(x, x)))


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


# A move's tests of its own contact: TTT2's throw connected from a side (requirements 3 .. 9, sub_0404FF30: this
# player's hit from the front, back, left, right ..., the bodies within param mm) and the hit and block latches
# (move_overrides.CONTACT)
OWN_CONTACT = frozenset(range(3, 10)) | {46, 49}


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


def drop_moves(d):
    """The pattern of the names of definition d's own moves the converter leaves out: DROP_MOVES (its EX moves kept
    with a gauge or free_meter_specials) and the definition's drop_moves."""
    dropped = DROP_MOVES.replace(r'|_EX\d?$', '') if d.MOVESET.get('free_meter_specials') or G.of(d) else DROP_MOVES
    return re.compile('|'.join([dropped] + ([d.MOVESET['drop_moves']] if d.MOVESET.get('drop_moves') else [])))


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


def count_groups(T):
    """Each group row (0x800B) given its group's length in start_frame; -> the rows changed. TTT2 goes through that
    many rows of the group, never looking for its 0x800C end (every cancel reader, 0x039943C4 and on: `lwz 24(row)`
    the count), and each of its own 40532 group rows holds its group's length. The source's was copied, so a group
    left shorter (rows dropped or merged) read on into the next groups: a Tekken 8 fighter's walks and runs took
    118 of other lists' rows (a jump attack from any frame)."""
    groups, changed = T['group_cancels'], 0
    for row in T['cancels']:
        if row['direction'] == M.GROUP:
            n = 0
            while groups[row['move_id'] + n]['direction'] != M.GROUP_END:
                n += 1
            if row['start_frame'] != n:
                row['start_frame'] = n
                changed += 1
    return changed


class Converter:
    # (a Tekken 7 source unless __init__ finds another game)
    game, end, prefix = 't7', T7_END, None
    linking = 0                         # > 0 while the links of the fighter's own (or converted) moves are made
    gauge = None                        # the definition's GAUGE (convert/gauge.py), set by __init__
    effects = None                      # its sound effects (convert/sounds.Effects; the importer's), or None
    effects8 = {}                       # Tekken 8 effect id -> its body part, or {summon: part} (convert/effects8.py)
    true_reqs = frozenset()             # (requirement, parameter) pairs true by the definition, set by __init__
    # reactions of the fighter's that keep their own move where the reaction evidence puts another of the same kind in
    # their place (MOVESET['own_reactions']: source names, '#<index>' for unnamed Tekken 8 moves; target()), by __init__
    own_reactions = frozenset()
    flag_reqs, flag_props = {}, {}      # the definition's state flags (FLAG_ON): test id -> (variable, kind), property
                                        # id -> variable, set by __init__
    counted = frozenset()               # the counted holds' variables of the cancel list being converted (COUNT_VAR)
    flag8 = {}                          # Tekken 8 flag slot -> its TTT2 moveset variable (FLAG8), set by __init__
    flag8_count = None                  # the flag variables' countdown requirement lists (flag8_block)
    hit_latch = None                    # the latch keeping "the move hit" in the cancel list being converted (HIT_HELD)
    _prop_latches = None                # {cancel list: latches its moves' properties use} (hit_latch_of)
    _hit_sets = None                    # {latch: the requirement list [(46), (set latch, 1)]} (hit_row)
    _fit = None                         # FIT's ranges: {'req' / 'prop': {TTT2 id: (lowest, highest)}}, when needed
    hands_reference = None              # the definition's HANDS row: (its motbin, its motion pack), by the importer
    hands8 = None                       # tekken8.anim.HandClips of a Tekken 8 fighter, by the importer
    _hands = None                       # hand_map's map
    _throw_victims = None               # throw_victims' set

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
        self.shown = []                 # the summons out by default (default_summons, by run)
        self.hand_anims = []            # animations added to the pack's hands container (hand_map)
        self._hand8_numbers = self._hand8_longest = None            # (hand8)
        self.posed_hands = {}           # donor pose part -> (Tekken 8 move, holding its last frame) (pose_sequence)
        self.hand8_shapes = {}          # hand shapes frame -> its values (hands8_generic)
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
        self.own_reactions = frozenset(d.MOVESET.get('own_reactions', ()))
        self.effect_ids = set()                                   # the Tekken 7 effect ids the moves spawn
        self.effect_rows = []              # (property row, Tekken 7 effect id, frames left of its move or None)
        self.effects8_stopped = set()      # the Tekken 8 effect ids a move's list stops (effect8_rows)
        self.trail_sampler = None          # a definition's TEKKEN8_TRAILS: convert/trails8.Sampler
        self.trail_rows = []               # (property row, what shares its effect, trail) (trail8_rows)
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
        self.gauge = G.of(d)            # Tekken 7's gauge kept (convert/gauge.py): its EX moves too
        # (requirement, parameter) pairs the definition knows true for the fighter (Geese's MAX activation tests
        # Tekken 7's variable 9, which nothing he does sets)
        self.true_reqs = set(d.MOVESET.get('true_requirements', ()))
        self.flag_reqs, self.flag_props = state_flags(d.MOVESET)
        self.flag8 = self.flag8_slots()
        self.flag8_moves = collections.defaultdict(list)   # Tekken 8 move -> [(frame, gate list, TTT2 rows)] (FLAG8)
        self.drop_moves = drop_moves(d)
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
        if self.gauge and c in G.REQS[g]:
            return G.REQS[g][c]
        if self.gauge and c in G.PROPS[g]:         # (an action in a requirement list)
            return G.PROPS[g][c]
        if c in self.flag_props:                   # (an action in a requirement list: a state flag set or cleared)
            return VAR_SET[self.flag_props[c]]
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
        if self.gauge and p in G.PROPS[g]:
            return G.PROPS[g][p]
        if p == TIGER_PROP[g] and self.opt_anims:
            return OPT_ANIM_PROP
        if p in self.flag_props:
            return VAR_SET[self.flag_props[p]]
        if p in PROP_OVERRIDE[g]:
            return PROP_OVERRIDE[g][p]
        if p in PROJ_PROPS[g]:
            return PROJ_PROPS[g][p]
        if EVADE[g] is not None and p in EVADE[g].values():        # (made into cancel rows: evade_rows)
            self.stats['evade properties (cancel rows instead)'] += 1
            return None
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
        if c == TIGER_PROP[g] and self.opt_anims:       # (its own part-3 animations: conv_value)
            return False
        return g == 't8' and not (c in VALUE_KIND[g] or c in SOUND_PROPS[g] or c in PROJ_PROPS[g] or
                                  c in PROP_OVERRIDE[g] or c in REQ_OVERRIDE[g] or c in REQ_OR[g] or
                                  c in (MOVE_PARAM[g], MOVE_PROP[g]) or c in CHAR_IS[g] or c in CHAR_IS_NOT[g] or
                                  c in DISTANCE_REQ[g])

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

    def target(self, mid, input_target=False, reaction=False):
        """A Tekken 7 move id (or alias slot) -> the new moveset's move id, or None. reaction: mid is a reaction slot's
        move (conv_reaction): a Tekken 8 one the remap would turn into TTT2's empty move 0 (motOrigin: the move TTT2's
        reaction slots that cannot happen hold: the victim stood free at once) or into a guard or stagger that frees
        the opponent on another frame (other_stun: a 28-frame guard, sGrd_SmTR28, became sGrd_mM00's 19 frames and
        left the attacker 9 frames more minus on block) is converted itself instead, as a refused remap is."""
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
        r = self.react_remap.get(n) if n not in PRESERVE_T7_REACTIONS and n not in self.own_reactions else None
        if r and r in self.dn and self.other_fall(mid, self.dn[r]):
            self.stats['reaction remap refused (the TTT2 move does another thing: stagger, crumple, launch)'] += 1
        elif r and r in self.dn and reaction and self.game == 't8' and self.convertible8(mid, n) and (
                self.dn[r] == 0 or self.other_stun(mid, self.dn[r])):
            why = 'TTT2 has no move there, motOrigin' if self.dn[r] == 0 else 'a guard or stagger of another length'
            self.stats['reaction remap refused (%s: Tekken 8\'s own kept)' % why] += 1
        elif r and r in self.dn:
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

    @staticmethod
    def rest(m, i, name):
        """How move i of moveset m (name: its names) ends: (REST kind, whether a move on the way is airborne: the move
        itself too, a launch named as a down state such as dw_He_shoryu), or None when its transitions reach none of
        REST's within REST_STEPS."""
        air, seen = False, set()
        for _ in range(REST_STEPS):
            if i is None or i in seen or not 0 <= i < len(m.tables['moves']):
                return None
            seen.add(i)
            mv = m.tables['moves'][i]
            air = air or mv['airborne_start'] > 0
            for kind, pattern in REST:
                if pattern.search(name(i)):
                    return kind, air
            t = mv['transition']
            i = m.resolve_alias(t) if t >= 0x8000 else t
        return None

    @staticmethod
    def fall(r):
        """What a reaction does to the opponent by its rest() r: 'air' (it leaves the ground: a launch, a trip),
        'down' (it comes to rest down without: a crumple), 'feet' (it stays standing or crouching: a stagger)."""
        return 'air' if r[1] else 'down' if r[0] == 'down' else 'feet'

    def other_fall(self, mid, j):
        """The source's reaction mid and the donor's move j do different things to the opponent (fall(); unknown counts
        as the same): a stagger where TTT2's fells or launches (Eliza's sDm_KAOLee, Negan's sDm_snap35), a launch or a
        trip where TTT2's stays on the ground (Azucena's BT 4,3 dw_He_shoryu -> the crumple sDm_KAKCca, Lidia's trip
        sDm_DownL00 -> the leg stagger sDm_ASI00R), a crumple where TTT2's stands or launches (Azucena's BT 1+2 CH #386
        -> a stagger; Negan's d/b+1+2 CH sDm_nkdoBxC -> the flip ym_y01L; her u/f+3 #1514, whose animation sinks to the
        floor, -> the pop-up sDw_KAO00_)."""
        a, b = self.rest(self.k, mid, self.name), self.rest(self.d, j, self.d.move_name)
        return a is not None and b is not None and self.fall(a) != self.fall(b)

    @staticmethod
    def end_frame(m, i):
        """The frame move i of moveset m frees its player from (its cancel list's end row: Wavu's recovery, a
        reaction's stun), or None."""
        ends = [c['start_frame'] for c in M.cancels(m, m.tables['moves'][i]['cancel']) if c['direction'] == M.LIST_END]
        return ends[0] if ends else None

    def other_stun(self, mid, j):
        """The source's reaction mid and the donor's move j both leave the opponent on its feet (fall(): a guard, a
        stagger; unknown counts as not) and free it on other frames (end_frame): the attacker's advantage would change
        by the difference (Tekken 8's guards run 20 to 42 frames, TTT2's generic sGrd_mM00 and sGrd_hM00 19). A copy of
        TTT2's move given Tekken 8's end frame would not do: its animations last 30 frames, fewer than Tekken 8's
        longest guards and staggers (32 to 42).
        Launches and crumples are left to other_fall: their end rows are air or floor time, not a stun."""
        a, b = self.rest(self.k, mid, self.name), self.rest(self.d, j, self.d.move_name)
        if a is None or b is None or self.fall(a) != 'feet' or self.fall(b) != 'feet':
            return False
        fa, fb = self.end_frame(self.k, mid), self.end_frame(self.d, j)
        return fa is not None and fb is not None and fa != fb

    def convertible8(self, mid, n):
        """Tekken 8 move mid (name n) is one target() converts as a reaction ('T' not dropped, 'N'): a remap refused
        for it then gives Tekken 8's own move, not none."""
        return (self.cls[mid] == 'T' and not DROP_T_RE.search(n)) or self.cls[mid] == 'N'

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

    # --- Tekken 8's flag slots (FLAG8) ------------------------------------------------------------------
    def flag8_slots(self):
        """{Tekken 8 flag slot: TTT2 moveset variable} for the slots the fighter both sets (with value 0 or 1 only)
        and tests, one variable each in FLAG8_VARS order while one is free: not a state_flags one of the definition's,
        and none whose ids the donor's moveset has or the fighter's ids map to (the id maps, the overrides)."""
        g = self.game
        if FLAG8_REQ.get(g) is None:
            return {}
        k, d = self.k, self.d
        tested, values, ids = set(), collections.defaultdict(set), set()
        for r in k.tables['requirements']:
            ids.add(r['condition'])
            if r['condition'] == FLAG8_REQ[g]:
                tested.add(r['param'])
            elif r['condition'] == FLAG8_PROP[g]:
                values[r['param']].add(r.get('param3', 0))
        for t in ('extra_move_properties', 'move_begin_props', 'move_end_props'):
            for x in k.tables[t]:
                ids.add(x['id'])
                if x['id'] == FLAG8_PROP[g]:
                    values[x['value']].add(x.get('value3', 0))
        why = {v: 'a state flag of the definition' for v in FLAG8_VARS
               if v in set(self.flag_props.values()) | {v for v, _ in self.flag_reqs.values()}}
        donor = {r['condition'] for r in d.tables['requirements']}
        for t in ('extra_move_properties', 'move_begin_props', 'move_end_props'):
            donor |= {x['id'] for x in d.tables[t]}
        mapped = {}
        for c in sorted(ids - {FLAG8_REQ[g], FLAG8_PROP[g]}):
            b, how = (self.req_map if c < 0x8000 else self.prop_map).lookup(c)
            for x in (REQ_OVERRIDE[g].get(c), PROP_OVERRIDE[g].get(c), b if how in M.MAPPED else None):
                mapped.setdefault(x, c)
        for v in FLAG8_VARS:
            if v not in why and donor & set(var_ids(v)):
                why[v] = 'the donor\'s moveset uses it'
            elif v not in why and mapped.keys() & set(var_ids(v)):
                why[v] = 'the fighter\'s %d maps to its id' % mapped[min(mapped.keys() & set(var_ids(v)))]
        for v, reason in sorted(why.items()):
            self.stats['Tekken 8 flag slots: moveset variable %d not taken (%s)' % (v, reason)] += 1
        free = [v for v in FLAG8_VARS if v not in why]
        out = {}
        for s in sorted(tested & set(values)):
            if not values[s] <= {0, 1}:
                self.stats['Tekken 8 flag slots set to values TTT2 cannot keep (left never set)'] += 1
            elif not free:
                self.stats['Tekken 8 flag slots without a free moveset variable (left never set)'] += 1
            else:
                out[s] = free.pop(0)
                self.stats['Tekken 8 flag slot %d -> moveset variable %d' % (s, out[s])] += 1
        return out

    def flag8_test(self, slot, value):
        """A test of flag slot `slot`'s value: TTT2's row for it, None (true: left out) or False."""
        k = self.flag8.get(slot)
        if k is None:
            self.stats['Tekken 8 flag slot tests of a slot never set (value 0 true, others false)'] += 1
            return None if value == 0 else False
        self.stats['Tekken 8 flag slot tests -> moveset variables'] += 1
        ge, le = var_ids(k)[:2]
        return {'condition': le, 'param': 0} if value == 0 else {'condition': ge, 'param': 1} if value == 1 else False

    def flag8_set(self, slot, life, value):
        """A set of flag slot `slot` (its lifetime in moves, its value): TTT2's row for it ({'condition', 'param'}, as
        an action in a requirement list), or None (left out)."""
        k = self.flag8.get(slot)
        if k is None:
            self.stats['Tekken 8 flag slot sets of a slot without a variable (left out)'] += 1
            return None
        self.stats['Tekken 8 flag slot sets -> moveset variables'] += 1
        return {'condition': var_ids(k)[3], 'param': (life if value else 0) & 0xFFFF}

    def flag8_gated(self, i):
        """Tekken 8 requirement list i tests a flag slot kept in a variable."""
        return bool(self.flag8) and any(c == FLAG8_REQ[self.game] and p in self.flag8 for c, p, _ in self.req_rows(i))

    def flag8_block(self):
        """The rows every cancel list converted from the fighter's starts with: per flag variable, an action row as the
        move starts (window 1-1, no input) taking 1 off it while it is above 0 (the unsigned tests: below 0 it is
        huge)."""
        if not self.flag8:
            return []
        if self.flag8_count is None:
            self.flag8_count = []
            for k in sorted(set(self.flag8.values())):
                ge, sub = var_ids(k)[0], var_ids(k)[5]
                self.flag8_count.append(tagsystem.write(self.T, 'requirements', [
                    {'condition': ge, 'param': 1}, {'condition': sub, 'param': 1}, {'condition': TT_END, 'param': 0}]))
        return [self.action_row(r, 1) for r in self.flag8_count]

    def action_row(self, req, frame):
        """A cancel row that only runs requirement list req's actions, at the move's frame `frame`."""
        if tagcombo.ACTION_ONLY not in self.extra_index:
            self.extra_index[tagcombo.ACTION_ONLY] = self.add('cancel_extras', {'value': tagcombo.ACTION_ONLY})
        return dict(direction=0, button=0, req=req, extradata=self.extra_index[tagcombo.ACTION_ONLY],
                    win_start=frame, win_end=frame, start_frame=frame, move_id=0x8001, option=0)

    def flag8_rows(self):
        """The fighter's moves whose extra (or begin) properties set a flag slot or test one (flag8_moves) get them as
        action rows of their cancel list (a copy), after its countdown rows: per property frame and list, the list's
        tests, then the properties as its actions."""
        made = {}
        for t8, held in sorted(self.flag8_moves.items()):
            if t8 not in self.newidx:
                continue
            move = self.T['moves'][self.newidx[t8]]
            rows = []
            for frame, gate, props in held:
                if not props:
                    continue
                tests = [{'condition': c, 'param': p} for c, p in tagsystem.reqs(self.T, gate)] if gate is not None else []
                acts = [{'condition': p['id'], 'param': p['value']} for p in props]
                for p, a in zip(props, acts):           # (an effect's row: split_effects names its copy later)
                    for n, (row, effect, left) in enumerate(self.effect_rows):
                        if row is p:
                            self.effect_rows[n] = (ParamAsValue(a), effect, left)
                req = tagsystem.write(self.T, 'requirements', tests + acts + [{'condition': TT_END, 'param': 0}])
                rows.append(self.action_row(req, 1 if frame >= 0x8000 or frame < 1 else min(frame, 32767)))
                self.stats['Tekken 8 flag slots: property rows as action rows'] += len(props)
            if not rows:
                continue
            cl = [dict(c) for c in tagsystem.cancels(self.T, move['cancel'])]
            count = set(self.flag8_count or ())
            at = max((n + 1 for n, c in enumerate(cl) if c['req'] in count and c['move_id'] == 0x8001), default=0)
            key = (move['cancel'], tuple(tuple(sorted(r.items())) for r in rows))
            if key not in made:
                made[key] = tagsystem.write(self.T, 'cancels', cl[:at] + rows + cl[at:])
            move['cancel'] = made[key]
            self.stats['Tekken 8 flag slots: moves given action rows'] += 1

    # --- "the move hit" kept to the move's end (HIT_HELD) ----------------------------------------------------
    def latches_in(self, rows):
        """The latches (0 .. LATCHES - 1) Tekken 8 requirement or property rows [(id, value, ...)] name."""
        g, out = self.game, set()
        for c, p, *_ in rows:
            if LATCH_REQ[g] <= c < LATCH_REQ[g] + LATCHES:
                out.add(c - LATCH_REQ[g])
            elif LATCH_PROP[g] <= c < LATCH_PROP[g] + 3 * LATCHES:
                out.add((c - LATCH_PROP[g]) // 3)
            elif c == LATCH_ANY_REQ[g] or 0 <= c - LATCH_ANY_PROP[g] < 3:
                out.add(p - 1)
        return out

    def hit_latch_of(self, i):
        """The latch keeping "the move hit" in the Tekken 8 cancel list at i (HIT_HELD): None when none of its rows
        tests a HIT_HELD id, or when its rows, its groups' and the properties of the moves with this list name all four
        latches (the last free one otherwise)."""
        g = self.game
        if not HIT_HELD[g] or i is None:
            return None
        rows = M.cancels(self.k, i)
        if not any(c in HIT_HELD[g] for x in rows for c, _, _ in self.req_rows(x['req'])):
            return None
        used = set()
        for x in rows:
            used |= self.latches_in(self.req_rows(x['req']))
            if x['direction'] == M.GROUP:
                for y in M.cancels(self.k, x['move_id'], 'group_cancels', M.GROUP_END):
                    used |= self.latches_in(self.req_rows(y['req']))
        if self._prop_latches is None:
            self._prop_latches = collections.defaultdict(set)
            for mv in self.k.tables['moves']:
                props = [(idv, v) for _, idv, v, _ in self.xp_rows(mv.get('extraprops'))]
                for key, t in (('begin_props', 'move_begin_props'), ('end_props', 'move_end_props')):
                    if mv.get(key) is not None:
                        for _, p in self.k.iter_list(t, mv[key], lambda p: p['id'] == self.end):
                            if p['id'] == self.end:
                                break
                            props.append((p['id'], p['value']))
                self._prop_latches[mv.get('cancel')] |= self.latches_in(props)
        used |= self._prop_latches.get(i, set())
        free = [k for k in reversed(range(LATCHES)) if k not in used]
        if not free:
            self.stats['Tekken 8 "the move hit": cancel lists with every latch taken (46 kept)'] += 1
            return None
        return free[0]

    def hit_row(self, k):
        """The action row first in a cancel list keeping "the move hit" in latch k (HIT_HELD): on the hit's frame (46)
        it sets the latch to 1."""
        if self._hit_sets is None:
            self._hit_sets = {}
        if k not in self._hit_sets:
            self._hit_sets[k] = tagsystem.write(self.T, 'requirements', [
                {'condition': HIT_NOW, 'param': 0}, {'condition': LATCH_PROP['ttt2'] + 3 * k, 'param': 1},
                {'condition': TT_END, 'param': 0}])
        return dict(self.action_row(self._hit_sets[k], 1), win_end=32767)

    def conv_reqs(self, i, overrides=None):
        """A Tekken 7 requirement list -> (the new list's index, ok); ok False: the list can never be true."""
        if i is None:
            return None, True
        g = self.game
        key = ('req', i, tuple(sorted(overrides.items()))) if overrides else ('req', i)
        counted = self.counted and self.counted & {p >> 16 for c, p, _ in self.req_rows(i) if c in COUNT_VAR[g]}
        if counted:                               # (the list names a counted hold's variable: converted for it)
            key += ('counted',) + tuple(sorted(counted))
        held = self.hit_latch is not None and any(c in HIT_HELD[g] for c, _, _ in self.req_rows(i))
        if held:                                  # (it tests "the move hit": the cancel list's latch, HIT_HELD)
            key += ('hit', self.hit_latch)
        if key in self.cache:
            return self.cache[key]
        rows, res = [], None
        for c, p, row in self.req_rows(i):
            if (c, p) in self.true_reqs:
                self.stats['requirements true by the definition'] += 1
                continue
            if counted and c in COUNT_VAR[g] and p >> 16 in counted:     # a counted hold's variable: the latch's
                rows.append({'condition': COUNT_TTT2[COUNT_VAR[g].index(c)], 'param': p & 0xFFFF})
                self.stats['counted holds: tests and actions of their variable -> latch %d' % (COUNT_LATCH + 1)] += 1
                continue
            if g == 't7' and c == 176 and p == 0 and self.defn.MOVESET.get('free_max_mode'):
                self.stats['MAX mode requirements removed (opt-in)'] += 1
                continue
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
            if c == FLAG8_REQ[g]:                 # a test of a Tekken 8 flag slot (FLAG8)
                test = self.flag8_test(p, row.get('param2', 0))
                if test is False:
                    res = (None, False)
                    break
                if test is not None:
                    rows.append(test)
                continue
            if c == FLAG8_PROP[g]:                # a flag slot's set, as an action (FLAG8)
                act = self.flag8_set(p, row.get('param2', 0), row.get('param3', 0))
                if act is not None:
                    rows.append(act)
                continue
            if c in WALL8[g]:                     # a wall test (WALL8): the distance in TTT2's high bits
                if not 0 <= p < 1 << 24:
                    res = (None, False)
                    break
                rows.append({'condition': WALL8[g][c], 'param': p << 8 | WALL_ANGLE})
                self.stats['wall tests (Tekken 8 194..201 -> TTT2 174..181)'] += 1
                continue
            if c in self.flag_reqs:               # a test of a state flag (state_flags): on or off
                k, kind = self.flag_reqs[c]
                on = p != 0 if kind == 'equals' else kind == 'set'
                rows.append({'condition': VAR_GE + k, 'param': 1} if on else {'condition': VAR_LE + k, 'param': 0})
                self.stats['state flag tests -> moveset variables'] += 1
                continue
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
            c2 = overrides[c] if overrides and c in overrides else self.map_req(c)
            if held and c in HIT_HELD[g] and c2 == HIT_NOW:     # "the move hit": the latch (HIT_HELD)
                rows.append({'condition': LATCH_REQ['ttt2'] + self.hit_latch, 'param': 1})
                self.stats['Tekken 8 "the move hit" tests -> the latch set on the hit\'s frame'] += 1
                continue
            if c in AIR_SIDE_EFFECT[g] and p == 1 and c2 is not None:     # (1, n): the hit's side effect, no test
                self.stats['Tekken 8 airborne tests: the hit\'s side effect (1, n) left out'] += 1
                p = 0
            if c >= 0x8000 and c not in (self.end, MOVE_PARAM[g]) and c not in REQ_PROP_KEEP[g]:
                v = self.req_value(row)           # (a Tekken 8 sound: its split value, req_value)
                if v is not None and self.own_effect(c, v) != c:
                    c2 = self.map_req(self.own_effect(c, v))
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
        counting = self.counting_rows(i) if table == 'cancels' else {}
        outer, self.counted = self.counted, frozenset(counting.values())     # (a group is converted without them)
        hit = self.hit_latch_of(i) if table == 'cancels' else None
        outer_hit, self.hit_latch = self.hit_latch, hit                       # (a group's stay 46: HIT_HELD)
        for n, c in enumerate(M.cancels(self.k, i, table, end)):
            d = dict(direction=c['direction'], button=c['button'], req=None, extradata=None,
                     win_start=c['win_start'], win_end=c['win_end'], start_frame=c['start_frame'],
                     move_id=c['move_id'], option=0)
            if n in counting:                     # a counted hold's count: its actions every frame (COUNT_VAR)
                d['req'], ok = self.conv_reqs(c['req'])
                if not ok:
                    self.stats['cancel dropped: requirement'] += 1
                    continue
                if tagcombo.ACTION_ONLY not in self.extra_index:
                    self.extra_index[tagcombo.ACTION_ONLY] = self.add('cancel_extras', {'value': tagcombo.ACTION_ONLY})
                out.append(dict(d, extradata=self.extra_index[tagcombo.ACTION_ONLY], move_id=0x8001))
                self.stats['counted holds'] += 1
                continue
            if c['direction'] in (M.LIST_END, M.GROUP_END):
                d['req'], _ = self.conv_reqs(c['req'])
                d['extradata'] = self.extradata(c['extradata'])
                if c['direction'] == M.LIST_END:
                    d['move_id'] = self.target(c['move_id'], input_target=True) or 0
                out.append(d)
                break
            reqs = [r for r, ok in (self.conv_reqs(c['req'], o) for o in self.or_variants(c['req'])) if ok]
            if not reqs:
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
            if len(reqs) > 1:
                self.stats['cancels made one row per alternative (REQ_OR)'] += 1
            for r in reqs:
                out.append(dict(d, req=r))
                self.stats['cancels converted'] += 1
        self.counted, self.hit_latch = outer, outer_hit
        if hit is not None and any((LATCH_REQ['ttt2'] + hit, 1) in tagsystem.reqs(self.T, r['req'])
                                   for r in out if r['req'] is not None):
            out = [self.hit_row(hit)] + out         # "the move hit" set on the hit's frame (HIT_HELD)
            self.stats['Tekken 8 "the move hit": cancel lists keeping it in a latch'] += 1
        if table == 'cancels' and self.flag8:      # the flag slots' countdown as the move starts (FLAG8)
            out = self.flag8_block() + out
        return out

    def or_variants(self, i):
        """The overrides requirement list i converts with: one {id: TTT2 id} per combination of its REQ_OR ids'
        alternatives, [None] when it has none."""
        ids = dict.fromkeys(c for c, _, _ in self.req_rows(i) if c in REQ_OR[self.game])
        out = [{}]
        for c in ids:
            out = [{**o, c: a} for o in out for a in REQ_OR[self.game][c]]
        return out if ids else [None]

    def counting_rows(self, i):
        """The rows of the Tekken 7 cancel list at i that count a hold's frames (COUNT_VAR): {row number: its
        variable} of the automatic rows back into the move whose list it is, keeping its frame, whose requirements are
        actions alone with an add of 1 to a variable a row of the list tests among them."""
        if not COUNT_VAR[self.game]:
            return {}
        test, _, add = COUNT_VAR[self.game]
        rows = M.cancels(self.k, i)
        tested = {p >> 16 for c in rows for r, p, _ in self.req_rows(c['req']) if r == test}
        if not tested:
            return {}
        moves, extras = self.k.tables['moves'], self.k.tables['cancel_extras']
        found = {}
        for n, c in enumerate(rows):
            if c['direction'] or c['button'] or c['move_id'] >= len(moves) or moves[c['move_id']]['cancel'] != i or \
                    c['extradata'] is None or not extras[c['extradata']]['value'] & tagcombo.KEEP_FRAMES:
                continue
            reqs = self.req_rows(c['req'])
            adds = [p >> 16 for r, p, _ in reqs if r == add and p & 0xFFFF == 1 and p >> 16 in tested]
            if len(adds) == 1 and all(r >= 0x8000 for r, _, _ in reqs):
                found[n] = adds[0]
        return found

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
        if ACTION_ROW[self.game] and v == ACTION_ROW[self.game][0]:
            v = ACTION_ROW[self.game][1]
        if v not in self.extra_index:
            self.extra_index[v] = self.add('cancel_extras', {'value': v})
        return self.extra_index[v]

    def conv_value(self, t7id, v):
        """A property's value (of the fighter's property id t7id) -> TTT2's, or None (not converted)."""
        g = self.game
        if t7id in self.flag_props:
            return FLAG_ON if v else 0
        if t7id == TIGER_PROP[g] and self.opt_anims:
            return OPT_ANIM_BASE + self.opt_anims[v] if v in self.opt_anims else None
        if t7id == SCREW_COUNTER[g] and v == SCREW_SPEND:
            return None
        if t7id == MOVE_PROP[g]:              # (a state the opponent plays, as a reaction slot's move)
            self.alloc_ok += 1
            t = self.target(v)
            self.alloc_ok -= 1
            self.stats['opponent move properties: ' + ('move converted' if t is not None else
                                                       'move not converted (left out)')] += 1
            return t
        if t7id in EFFECT_AT[g] and v in self.hit_locations:          # an effect at a weapon's point (EFFECT_AT)
            self.stats['effects at a weapon\'s point (its hit boxes\' location)'] += 1
            return self.hit_locations[v]
        kind = VALUE_KIND[g].get(t7id)
        if kind == 'pushback':
            return self.conv_pushback(v)
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
        if t7id in SOUND_PROPS[g] and self.effects is not None and self.effects.move_value(v) is not None:
            self.stats['sound effects (item sounds of its own)'] += 1
            return self.effects.move_value(v)
        if t7id in SOUND_PROPS[g] and v not in self.donor_sound[self.prop_map.lookup(t7id)[0]] and \
                not self.own_voice(v):
            return None
        return v

    def own_effect(self, c, v):
        """Tekken 8's sound id c with value v (bank << 24 | n), as the id its row needs: an effect of the attacker's
        played at the opponent's body (0x87f2) is the player's in TTT2, whose opponent sound would take the item sound
        from the opponent's list (tekken8/sounds.py)."""
        if self.game == 't8' and c == OPPONENT_VOICE8[0] and self.effects is not None and \
                self.effects.move_value(v) is not None:
            return PLAYER_SOUND8
        return c

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
        """A property row's value as Tekken 7 has it (Tekken 8's sounds: bank << 24 | n, SPLIT_SOUND; a flag slot's set:
        slot | lifetime << 8 | value << 24, FLAG8)."""
        if SPLIT_SOUND[self.game] and row['id'] in SOUND_PROPS[self.game]:
            return (row['value'] & 0xFF) << 24 | (row['value3'] & 0xFFFFFF)
        if row['id'] == FLAG8_PROP[self.game]:
            return row['value'] & 0xFF | (row.get('value2', 0) & 0xFFFF) << 8 | min(row.get('value3', 0), 0xFF) << 24
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

    def floor_break_rows(self, breaks, xp, move):
        """TTT2's floor break of Tekken 8 move `move` (FLOOR_BREAK8): breaks, its rows' (frame, strength), none for a
        move without; xp, all its extra property rows [(frame, id, value, requirement list)] -> [the row] or []. A
        throw's victim breaks the floor by its impact row, marked or not, and without one not at all."""
        if move in self.throw_victims():
            if not any(idv == FLOOR_IMPACT8 and f < PLAIN_FRAME for f, idv, _, _ in xp):
                if breaks:
                    self.stats['floor breaks left out: a throw without an impact (a toss: balcony breaks)'] += 1
                return []
            if not breaks:
                breaks = [(0x8001, FLOOR_BREAK8_MIN)]
                self.stats['floor breaks of throws marked by their impact only'] += 1
        elif not breaks:
            return []
        if max(v for _, v in breaks) < FLOOR_BREAK8_MIN:
            self.stats['floor breaks left out: weaker than a floor (spikes, staggers)'] += 1
            return []
        own = [f for f, v in breaks if f < PLAIN_FRAME and v >= FLOOR_BREAK8_MIN]
        anchors = [(sorted(f for f, idv, _, _ in xp if idv == a and f < PLAIN_FRAME), how)
                   for a, how in ((FLOOR_IMPACT8, 'its impact'), (LANDING, 'its landing'))]
        if own:
            frame, how = min(own), 'their own frame'
        else:
            frame, how = next(((at[0] + FLOOR_BREAK_WAIT, how) for at, how in anchors if at), (None, None))
            if frame is None:
                down = self.landing_frame(move)
                if down is None:
                    self.stats['floor breaks left out: no moment the victim lands'] += 1
                    return []
                frame, how = down + FLOOR_BREAK_WAIT, 'its animation\'s landing'
        last = self.anim_frames(move)
        if last and frame >= last:
            frame = last - 1
        self.stats['floor breaks (after %s)' % how] += 1
        return [dict(frame=max(1, frame), id=FLOOR_BREAK, value=1)]

    def throw_victims(self):
        """The Tekken 8 moves a throw (THROW_LEVEL) puts its victim in: the moves of its hit conditions' reactions."""
        if self._throw_victims is None:
            k, moves = self.k, self.k.tables['moves']
            self._throw_victims = {r[f] for mv in moves if mv.get('hitlevel', 0) & 0xFFFF == THROW_LEVEL
                                   for _, _, rx in M.hitconds(k, mv.get('hit_condition')) if rx is not None
                                   for r in (k.tables['reactions'][rx],) for f in REACTION_MOVE_FIELDS
                                   if f != 'standing' and r[f] is not None and r[f] < len(moves)}
        return self._throw_victims

    def landing_frame(self, move):
        """The first frame Tekken 8 move `move`'s TTT2 animation has its hips below LYING_HIPS after they were at
        STANDING_HIPS or above (the victim of a throw hits the floor), else None."""
        if move is None:
            return None
        buf, e, off = self.animation_bytes(self.move_anim(move))
        hips = animation.decode(buf, e, off)['values'][:, 1, 1]
        up = False
        for f, y in enumerate(hips):
            up = up or y >= STANDING_HIPS
            if up and y < LYING_HIPS:
                return f
        return None

    def anim_frames(self, move):
        """The frame count of Tekken 8 move `move`'s TTT2 animation, else None."""
        if move is None:
            return None
        buf, e, off = self.animation_bytes(self.move_anim(move))
        return animation.header(buf, e, off)['frames']

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
        """A Tekken 7 hit location code (a byte of a move's hitbox) -> TTT2's (hit_location)."""
        return hit_location(self.game, x, self.hit_locations, self.hitbox)

    def conv_xps(self, i, move=None, extra=(), only=None):
        """Move `move`'s extra property list i (with rows `extra` after it) -> the new list's index, or None.
        `only`: rows [(frame, id, value, None)] converted in place of list i's, their TTT2 rows returned (FLAG8: the
        properties whose requirement list tests a flag slot)."""
        if i is None and not extra and only is None:
            return None
        g = self.game
        rows = []
        t7 = self.xp_rows(i) if only is None else only
        air = any(idv == ARCS[g][1] for _, idv, _, _ in t7)     # a 2D air move (convert/arcs.py)
        amounts = sorted((0 if f >= 0x8000 else f, v) for f, idv, v, _ in t7 if idv == DAMAGE_AMOUNT[g])
        dealt = collections.Counter()                       # points dealt so far (amount's frame, property)
        breaks = []                                         # Tekken 8's floor breaks (floor_break_rows)
        for f, idv, v, req in t7:
            if idv == 0 and f == 0:
                break
            if req is not None:                             # Tekken 8: the row's own requirement list
                r, ok = self.conv_reqs(req)
                if not ok:
                    self.stats['property dropped: requirement'] += 1
                    continue
                if not self.always(r):                      # (TTT2's rows have none)
                    if move is not None and self.flag8_gated(req):      # a flag slot's test: action rows (FLAG8)
                        self.flag8_moves[move].append((f, r, self.conv_xps(None, move, only=[(f, idv, v, None)])))
                        continue
                    self.stats['property dropped: a condition TTT2 cannot attach'] += 1
                    continue
            if idv == FLAG8_PROP[g]:                        # a flag slot's set: an action row at its frame (FLAG8)
                act = self.flag8_set(v & 0xFF, v >> 8 & 0xFFFF, v >> 24)
                if act is not None and (only is not None or move is not None):
                    prop = dict(frame=f, id=act['condition'], value=act['param'])
                    if only is not None:
                        rows.append(prop)
                    else:
                        self.flag8_moves[move].append((f, None, [prop]))
                continue
            if idv in ARCS[g]:                              # 2D arcs (convert/arcs.py)
                rows += [r for r in self.arc_rows(move, air, f, idv, v) if r not in rows]
                continue
            if idv == DAMAGE_AMOUNT[g]:
                continue
            if idv == FLOOR_BREAK8[g]:
                breaks.append((f, v))
                continue
            if idv in SUMMON_PROPS[g] or idv == SUMMON_EFFECT[g]:  # summoned weapons
                rows += self.summon_rows([(f, idv, v)], move)
                continue
            if g == 't8' and self.hands8 is not None and idv in HANDS8:    # the fighter's own hand clip
                n = self.hand8(v)
                if n is not None:
                    rows.append(dict(frame=f, id=HANDS8[idv], value=n))
                    self.stats['hand animations (Tekken 8\'s)'] += 1
                continue
            if (idv, v) in self.hand_map():                 # a hand animation the HANDS row has
                rows.append(dict(frame=f, id=HAND_PROPS[g][idv], value=self.hand_map()[idv, v]))
                self.stats['hand animations (the HANDS row\'s)'] += 1
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
            if g == 't8' and v & 0xFF in self.effects8 and idv in (EFFECT8_SPAWN, EFFECT8_STOP):    # (effects8.py)
                self.effect8_rows(rows, t7, f, idv, v, move)
                continue
            if g == 't8' and idv == EFFECT8_TRAIL and self.trail_sampler is not None:              # (trails8.py)
                self.trail8_rows(rows, t7, f, v, move)
                continue
            stop = G.stop_frames(t7, idv, v, g) if self.gauge else None
            if stop:                                        # a super's time stop (convert/gauge.py)
                rows.append(dict(frame=f, id=G.STOP, value=stop))
                self.stats['time stops'] += 1
                continue
            p = self.map_prop(self.own_effect(idv, v)) if idv >= 0x8000 else self.map_req(idv)
            if p is None:
                continue
            v2 = self.conv_value(idv, v)
            if v2 is None:
                self.stats['property dropped: value (sound bank / index / screw spent)'] += 1
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
        if only is not None:
            return rows
        if ELECTRIC_MARK[g] is not None and any(r['id'] == ELECTRIC_PROP and r['value'] == 1 for r in rows):
            rows += self.electric_rows(move)                # a Tekken 8 electric: Kazuya's lightning
        if breaks or FLOOR_BREAK8[g] is not None and move is not None:
            rows += self.floor_break_rows(breaks, t7, move)
        rows += extra
        if not rows:
            return None
        rows.append(dict(frame=0, id=0, value=0))
        start = len(self.T['extra_move_properties'])
        self.T['extra_move_properties'] += rows
        return start

    # --- Tekken 8 effects (convert/effects8.py) ---------------------------------------------------------------------
    def effect8_rows(self, rows, t7, f, idv, v, move):
        """A Tekken 8 effect row (EFFECT8_SPAWN, EFFECT8_STOP; value part << 8 | id) of an effect id the definition
        attaches to a body part (effects8 {id: part, or {summon: part}: at the part of the summon the list shows or
        hides, the first listed when it does neither}): a spawn becomes TTT2's (EFFECT_PROP, at that part), noted
        with the frames until the same list stops it (EFFECT8_STOP, the same id, or that summon's dismissal; else
        the move's frames left), which split_effects makes the end of its copy; a stop has no TTT2 row (TTT2's
        effects stop by themselves; effects8_stopped notes the id: it loops until stopped)."""
        if idv == EFFECT8_STOP:
            self.effects8_stopped.add(v & 0xFF)
            self.stats['Tekken 8 effect stops (their copies end there)'] += 1
            return
        eid, part = v & 0xFF, self.effects8[v & 0xFF]
        at = lambda g: 0 if g >= 0x8000 else g
        start = at(f)
        ends = [at(g) for g, i, x, _ in t7 if i == EFFECT8_STOP and x & 0xFF == eid]
        if isinstance(part, dict):                          # a summon's effect: at its part, ending with it
            moves = SUMMON_PROPS[self.game]
            n = next((x for g, i, x, _ in t7 if moves.get(i) in (TT_SUMMON, TT_DISMISS) and x in part),
                     next(iter(part)))
            ends += [at(g) for g, i, x, _ in t7 if moves.get(i) == TT_DISMISS and x == n]
            part = part[n]
            self.stats['Tekken 8 effects at the part of the summon shown (%d)' % n] += 1
        stop = min((g for g in ends if g > start), default=None)
        rows.append(dict(frame=f, id=EFFECT_PROP, value=part << 8 | eid))
        self.effect_ids.add(eid)
        self.effect_rows.append((rows[-1], eid, stop - start if stop is not None else self.frames_left(move, f)))
        self.stats['Tekken 8 effects (the definition\'s, at its body parts)'] += 1

    def trail8_rows(self, rows, t7, f, v, move):
        """A Tekken 8 weapon trail (EFFECT8_TRAIL; value parts << 24 | frames << 16 | tail << 8 | kind): an effect at the
        hips (part 0) that draws the blade's way baked from move's clip (convert/trails8.py), to the first
        EFFECT8_TRAIL_END of the list after it or its frames. Its id comes with assign_trails."""
        at = lambda g: 0 if g >= 0x8000 else g
        start = at(f)
        frames = min([at(g) - start for g, i, _, _ in t7 if i == EFFECT8_TRAIL_END and at(g) > start] + [v >> 16 & 0xFF])
        trail = self.trail_sampler(move, start, frames, v)
        if trail is None:
            self.stats['Tekken 8 trails left out (no clip or weapon)'] += 1
            return
        rows.append(dict(frame=f, id=EFFECT_PROP, value=0))
        self.trail_rows.append((rows[-1], (self.k.anim_ref(move)[0], start, frames, v), trail))
        self.stats['Tekken 8 trails'] += 1

    def assign_trails(self, used):
        """The ids of the trails trail8_rows met: one for each clip, start, length and value, none of `used` or
        effect_ids; the rows name them -> {id: trail}."""
        spare = iter([i for i in TRAIL_SPARE if i not in used and i not in self.effect_ids])
        ids, out = {}, {}
        for row, key, trail in self.trail_rows:
            if key not in ids:
                ids[key] = next(spare)
                out[ids[key]] = trail
            row['value'] = ids[key]
        self.effect_ids |= set(out)
        return out

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

    def default_summons(self):
        """The definition's summons out before any move takes them out (Kunimitsu II's kunai in her right fist, the
        sheath with her sword at her hips), sorted: by the fighter's moves that both take a summon out and put it away,
        whichever they do first (putting it away: it was out), most of them; a move doing only one of the two (the
        clean-up after a throw, a win pose putting her kunai away) tells nothing."""
        ids = SUMMON_PROPS[self.game]
        votes = collections.defaultdict(collections.Counter)
        for mv in self.k.tables['moves'] if self.summons else ():
            ops = collections.defaultdict(list)
            for f, idv, v, _ in self.xp_rows(mv.get('extraprops')):
                if idv == 0 and f == 0:
                    break
                v &= 0xFF                                     # (Tekken 8's fade frames above: summons8.fade_value)
                if idv in ids and v in self.summons:
                    ops[v].append((0 if f >= 0x8000 else f, ids[idv] == TT_SUMMON))
            for n, rows in ops.items():
                rows.sort(key=lambda r: r[0])
                if len({out for _, out in rows}) == 2:
                    votes[n][not rows[0][1]] += 1
        return sorted(n for n, c in votes.items() if c[True] > c[False])

    def summon_reset(self):
        """The rows that start a move with the summons as a round starts: all put away, then those out by default
        (default_summons) taken out again."""
        return [dict(frame=0x8001, id=TT_DISMISS, value=TT_DISMISS_ALL)] + \
            [dict(frame=0x8001, id=TT_SUMMON, value=n) for n in self.shown]

    def hand_map(self):
        """{(Tekken 7 hand property, value): TTT2 value} of the hand animations the definition's HANDS row has
        (HAND_PROPS; hands_reference): per value the fighter's moves give a hand, the value most of that row's moves of
        the same name give the hand (one of its pack's own animations); the animation is the donor pack's of the same
        bytes, else one added to it (hand_anims, numbered after the donor's)."""
        if self._hands is not None:
            return self._hands
        self._hands = {}
        props = HAND_PROPS[self.game]
        if self.hands_reference is None or not props:
            return self._hands
        t, pack = self.hands_reference
        o, n = motion.pack_items(pack)[1]
        theirs = motion.hand_animations(pack[o:o + n])
        o, n = motion.pack_items(self.donor_pack)[1]
        donor = motion.hand_animations(self.donor_pack[o:o + n])
        number = {}
        for i, a in reversed(list(enumerate(donor))):
            number[a] = i
        names = {t.move_name(j): j for j in range(len(t.tables['moves']))}
        votes = collections.defaultdict(collections.Counter)
        for i, mv in enumerate(self.k.tables['moves']):
            j = names.get(self.k.move_name(i))
            if j is None:
                continue
            given = {idv: v for f, idv, v in M.xps(t, t.tables['moves'][j]['extraprops']) if idv in props.values()}
            for f, idv, v, _ in self.xp_rows(mv.get('extraprops')):
                ttt2 = given.get(props.get(idv))
                if ttt2 is not None and ttt2 & HAND_OWN and (ttt2 & ~HAND_OWN) < len(theirs):
                    votes[idv, v][ttt2] += 1
        for key, c in sorted(votes.items()):
            a = theirs[c.most_common(1)[0][0] & ~HAND_OWN]
            if a not in number:
                number[a] = len(donor) + len(self.hand_anims)
                self.hand_anims.append(a)
            self._hands[key] = HAND_OWN | number[a]
        return self._hands

    def hand8_number(self, a):
        """The pack's value (HAND_OWN | n) of hand animation `a`, added to hand_anims when new."""
        if self._hand8_numbers is None:
            o, n = motion.pack_items(self.donor_pack)[1]
            self._hand8_numbers = {}
            self._hand8_donor = len(motion.hand_animations(self.donor_pack[o:o + n]))
        if a not in self._hand8_numbers:
            self._hand8_numbers[a] = HAND_OWN | (self._hand8_donor + len(self.hand_anims))
            self.hand_anims.append(a)
        return self._hand8_numbers[a]

    def hand8(self, value):
        """The pack's value of Tekken 8's hand clip `value`, as long as the longest move it starts (None: no clip)."""
        if self._hand8_longest is None:
            self._hand8_longest = collections.Counter()
            for i, mv in enumerate(self.k.tables['moves']):
                values = [v for _, idv, v, _ in self.xp_rows(mv.get('extraprops')) if idv in HANDS8]
                frames = self.hands8.body_frames(self.k.anim_ref(i)[0]) if values else 0
                for v in values:
                    self._hand8_longest[v] = max(self._hand8_longest[v], frames)
        a = self.hands8.animation(value, self._hand8_longest[value])
        return None if a is None else self.hand8_number(a)

    def hands8_rows(self, t8):
        """The TTT2 rows of Tekken 8 move t8's hand properties."""
        return [dict(frame=f, id=HANDS8[idv], value=n) for f, idv, n in
                ((f, idv, self.hand8(v)) for f, idv, v, _ in self.xp_rows(self.k.tables['moves'][t8]['extraprops'])
                 if idv in HANDS8) if n is not None]

    def hands8_hold_rows(self, t8):
        """Rows that hold the last frame of the hand clips Tekken 8 move t8 starts."""
        out = []
        for f, idv, v, _ in self.xp_rows(self.k.tables['moves'][t8]['extraprops']):
            a = self.hands8.hold(v) if idv in HANDS8 else None
            if a is not None:
                out.append(dict(frame=0x8001, id=HANDS8[idv], value=self.hand8_number(a)))
        return out

    def hands8_generic(self):
        """The donor's moves the fighter has by name, and its intros and win poses (pose_sequence), play Tekken 8's
        hand properties in place of the donor's; those Tekken 8 does not have keep theirs. The hand shapes a hand goes
        back to (write) are its stance's first frames."""
        if self.hands8 is None:
            return
        made = {}
        for i in range(len(self.d.tables['moves'])):
            row = self.T['moves'][i]
            if i in self.posed_hands:
                t8, holding = self.posed_hands[i]
                rows = self.hands8_hold_rows(t8) if holding else self.hands8_rows(t8)
            else:
                t8 = self.kn.get(self.d.move_name(i))
                if t8 is None:
                    continue
                rows = self.hands8_rows(t8)
            key = (row['extraprops'], tuple(sorted(tuple(sorted(r.items())) for r in rows)))
            if key not in made:
                made[key] = self.with_props(row['extraprops'], rows, drop=HAND_ROWS)
            row['extraprops'] = made[key]
            self.stats['hands: donor moves with Tekken 8\'s hand properties'] += 1
        stance = self.kn.get('%s_sKAM00_' % self.prefix)
        for f, idv, v, _ in self.xp_rows(self.k.tables['moves'][stance]['extraprops']) if stance is not None else ():
            values = self.hands8.values(v) if idv in HANDS8 else None
            if values is not None:
                self.hand8_shapes[HAND_SHAPE_LEFT if idv == 0x8610 else HAND_SHAPE_RIGHT] = values[0].tolist()
        if HAND_SHAPE_RIGHT in self.hand8_shapes:        # (Tekken 8 has no row there: its hands stay as they were)
            for frame in HAND_SHAPES_OPEN:
                self.hand8_shapes[frame] = self.hand8_shapes[HAND_SHAPE_RIGHT]

    def dismiss_when_hit(self):
        """Tekken 7 puts a summoned weapon away when the fighter is hit (its game, not the moveset, does) and in its
        stance; the added fighter is hit into, falls and gets up through the donor's generic moves, and gets up into the
        donor's stance (La_KAM), so each of the donor's moves starts with the summons as a round starts (summon_reset:
        all put away, those out by default out again; the fighter's own moves never go through them with a weapon
        out: Noctis's only into a KO), but the intro and win poses that play the fighter's animations (they summon
        their own)."""
        if not self.summons:
            return
        made = {}
        for i in range(len(self.d.tables['moves'])):
            if i in self.posed:
                continue
            row = self.T['moves'][i]
            start = row['extraprops']
            if start not in made:
                made[start] = self.with_props(start, self.summon_reset())
            row['extraprops'] = made[start]
            self.stats['weapon summons: dismissed by the donor\'s moves'] += 1

    def dismiss_at_start(self):
        """Tekken 7 puts a fighter's weapons away as a round starts (its game, not the moveset: Kunimitsu II's intros
        end with her sword drawn, and the fight starts with only her kunai out); TTT2 does not. So the definition's
        WEAPON_DISMISS moves (a pattern of Tekken 7 move names: her stance, which a round starts in and her moves end
        in, and the move her intros and win poses end in) start with the summons as a round starts (summon_reset)."""
        pattern = getattr(self.defn, 'WEAPON_DISMISS', None)
        if not pattern or not self.summons:
            return
        made = {}
        for t7, i in sorted(self.newidx.items()):
            if not re.search(pattern, self.name(t7)):
                continue
            row = self.T['moves'][i]
            start = row['extraprops']
            if start not in made:
                made[start] = self.with_props(start, self.summon_reset())
            row['extraprops'] = made[start]
            self.stats['weapon summons: dismissed as a move starts (WEAPON_DISMISS)'] += 1

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

    def evades(self, i):
        """Move i's automatic evades (EVADE): [(first frame, last frame, [(Tekken 8 class, Tekken 8 evade move)] by
        slot)]: each row setting its frames (always rows: TTT2's cannot have conditions) opens one, to its frames' end
        or the next such row, with the slots as the move sets them up to its frame (a slot with move 0 is none, as in
        Tekken 8; it keeps a slot's class from an earlier move: a slot the move gives no class takes any attack, as a
        fresh player's)."""
        ids = EVADE[self.game]
        start = self.k.tables['moves'][i]['extraprops']
        if ids is None or start is None:
            return []
        rows = []
        for _, x in self.k.iter_list('extra_move_properties', start, lambda x: x['id'] == 0 and x['frame'] == 0):
            if x['id'] == 0 and x['frame'] == 0:
                break
            if x['id'] in ids.values():
                r, ok = self.conv_reqs(x['req'])
                if ok and self.always(r):
                    rows.append((1 if x['frame'] >= 0x8000 else max(1, x['frame']), x['id'], x['value'], x['value2']))
        rows.sort(key=lambda x: x[0])
        opens = [(f, v) for f, idv, v, _ in rows if idv == ids['frames']]
        out = []
        for n, (f, frames) in enumerate(opens):
            last = f + frames - 1 if frames < EVADE_FOREVER else 32767
            if n + 1 < len(opens):
                last = min(last, opens[n + 1][0] - 1)
            slots = {}
            for g, idv, v, s in rows:
                if g <= f and idv in (ids['move'], ids['class']):
                    slots.setdefault(s, {})[idv] = v
            got = [(slots[s].get(ids['class'], 0), slots[s][ids['move']]) for s in sorted(slots)
                   if slots[s].get(ids['move'])]
            if frames > 0 and last >= f and got:
                out.append((f, min(last, 32767), got))
        return out

    def evade_rows(self):
        """The converted moves with Tekken 8 evades get, first in a copy of their cancel list, TTT2's rows for them
        (EVADE): per evade, slot, TTT2 test (EVADE_TESTS, all three for any class) and limb (EVADE_LIMBS), no input,
        over the evade's frames into the slot's move."""
        if EVADE[self.game] is None:
            return
        reqs, made = {}, {}
        for t8, i in sorted(self.newidx.items()):
            rows = []
            for first, last, slots in self.evades(t8):
                for cls, mid in slots:
                    to = self.target(mid)
                    if to is None:
                        self.stats['evades left out: the evade move is not converted'] += 1
                        continue
                    for test in EVADE_TESTS.get(cls, sum(EVADE_TESTS.values(), ())):
                        for limb in EVADE_LIMBS:
                            if EVADE_EXTRA not in self.extra_index:
                                self.extra_index[EVADE_EXTRA] = self.add('cancel_extras', {'value': EVADE_EXTRA})
                            if (test, limb) not in reqs:
                                reqs[test, limb] = len(self.T['requirements'])
                                self.T['requirements'] += [{'condition': test, 'param': limb},
                                                           {'condition': TT_END, 'param': 0}]
                            rows.append(dict(direction=0, button=0, req=reqs[test, limb],
                                             extradata=self.extra_index[EVADE_EXTRA], win_start=first, win_end=last,
                                             start_frame=first, move_id=to, option=0))
            move = self.T['moves'][i]
            if not rows or move['cancel'] is None:
                continue
            key = (move['cancel'], tuple(tuple(sorted(r.items())) for r in rows))
            if key not in made:
                made[key] = tagsystem.write(self.T, 'cancels',
                                            rows + [dict(c) for c in tagsystem.cancels(self.T, move['cancel'])])
            move['cancel'] = made[key]
            self.stats['moves given automatic evades (Tekken 8: cancel rows)'] += 1
            self.stats['automatic evade rows'] += len(rows)

    def with_props(self, start, extra, drop=()):
        """A new property list: the one at `start` (None: none) without its rows of the ids `drop`, with rows `extra`
        after it -> its index."""
        rows = []
        table = self.T['extra_move_properties']
        while start is not None and start < len(table) and not (table[start]['id'] == 0 and table[start]['frame'] == 0):
            if table[start]['id'] not in drop:
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
        # the neutral jump (the whole of the fighter's "_sabun" jumps): the air height of other relative animations
        jump = next((whole[arcs.whole_name(n)] for n in map(k.anim_name, range(len(k.tables['moves'])))
                     if '_sabun' in n.lower() and arcs.whole_name(n) in whole), None)
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
                elif jump is not None and arcs.relative_hips(dec, f0):
                    dec, _, _ = arcs.absolute_sabun(dec, arcs.decode_t7(k, jump))
                    self.stats['2D arcs: relative animations made absolute'] += 1
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

    def arc_landings(self):
        """A ground move that only 2D air moves land into (their cancel one frame after their ground_fall; every
        other way in counts: cancel lists' rows, group lists, transitions, reactions, alias slots) gets TTT2's bit
        31, Tekken 7's bit 0, which its other landings (sJUMP_*_chak) have and Akuma's Hyakkigozan slide lacks. TTT2
        starts a move without it from a squat when the fighter comes down from the air (the runtime flies those
        moves at the player's own height): the slide's first frame had his hips at half height and his feet 110 mm
        under the floor, the landings with the bit cleared sank to 200 mm for three frames."""
        arc, air_move = ARCS[self.game]
        if air_move is None:
            return
        k = self.k
        moves = k.tables['moves']
        air = set()                                       # the 2D air moves (arc_rows: not baked)
        for i, mv in enumerate(moves):
            p = [(f, idv) for f, idv, _ in M.xps(k, mv['extraprops'])]
            flies = any(idv == air_move for _, idv in p)
            if flies or any(idv == arc and not arcs.is_ground_arc(flies, f) for f, idv in p):
                air.add(i)

        def target(mid):
            return None if mid is None else k.resolve_alias(mid) if mid >= 0x8000 else mid
        ways = collections.defaultdict(set)               # Tekken 7 move -> per way in: a 2D air move's landing?
        for i, mv in enumerate(moves):
            for _, c in k.iter_list('cancels', mv['cancel'], lambda c: c['direction'] == M.LIST_END):
                if c['direction'] != M.GROUP:
                    ways[target(c['move_id'])].add(i in air and c['direction'] == 0 and
                                                   0 < mv['ground_fall'] < c['win_start'] == c['win_end'])
        for t in [target(c['move_id']) for c in k.tables['group_cancels']] + \
                [target(mv['transition']) for mv in moves] + list(k.aliases) + \
                [target(r[f]) for r in k.tables['reactions'] for f in REACTION_MOVE_FIELDS]:
            ways[t].add(False)
        for t, landing in ways.items():
            if landing == {True} and t in self.newidx and not moves[t]['airborne_start']:
                row = self.T['moves'][self.newidx[t]]
                if not row['bitfield'] & 1 << 31:
                    row['bitfield'] |= 1 << 31
                    self.stats['2D arcs: landing moves given the landing bit'] += 1

    def conv_props(self, table, i):
        if i is None:
            return None
        rows = []
        for _, p in self.k.iter_list(table, i, lambda p: p['id'] == self.end):
            if p['id'] == self.end:
                break
            if p['id'] == FLAG8_PROP[self.game]:      # a flag slot's set (FLAG8; an end property clears one)
                v = self.prop_value(p)
                act = self.flag8_set(v & 0xFF, v >> 8 & 0xFFFF, v >> 24)
                r, ok = self.conv_reqs(p['req'])
                if act is not None and ok:
                    rows.append(dict(req=r if r is not None else 0, id=act['condition'], value=act['param']))
                continue
            pid = self.map_prop(self.own_effect(p['id'], self.prop_value(p))) if p['id'] >= 0x8000 else self.map_req(p['id'])
            if pid is None:
                continue
            r, ok = self.conv_reqs(p['req'])
            if not ok:
                self.stats['property dropped: requirement'] += 1
                continue
            v2 = self.conv_value(p['id'], self.prop_value(p))
            if v2 is None:
                self.stats['property dropped: value (sound bank / index / screw spent)'] += 1
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
                t = self.target(r[nm], reaction=True)
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
        if self.gauge and out[4]:                           # its hits on one fighter (convert/gauge.py)
            out[4] = G.projectile_hits(self.k, pi, self.game, M.cancels, M.reqs)
        for f in PROJ_SOUNDS:
            if out[f] and out[f] not in self.known_sounds and not self.own_voice(out[f]):
                out[f] = 0
                self.stats['projectile sound dropped'] += 1
        if self.effects is not None and self.effects.hit_value(v[2]) is not None:   # its missile's hit sound
            out[16] = self.effects.hit_value(v[2])
            self.stats['projectile hit sounds (item sounds of its own)'] += 1
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
        move's hit boxes go. A summoned weapon of the thrown item's bone (Kunimitsu II's kunai, drawn in her hand from
        the move's summon on) is dismissed as the projectile is spawned: the projectile's look flies it from there
        (the hand's copy would follow the pairs Tekken 7 flies it by, up to 7 m out). -> the properties, or []."""
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
            look += [dict(frame=f, id=TT_DISMISS, value=n) for n, w in sorted(self.summons.items())
                     if (w.get('mesh'), w.get('bone')) == (spec['item']['mesh'], spec['item']['bone'])]
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

    def lands_at_once(self, ri):
        """The fighter's reaction list ri is a slam's: its standing reaction is airborne and falls in its first frame
        only (SLAM_FRAMES) and goes on into a down move."""
        moves, reactions = self.k.tables.get('moves', []), self.k.tables.get('reactions', [])
        if ri is None or ri >= len(reactions):
            return False
        mid = self.k.resolve_alias(reactions[ri]['default'])
        if mid is None or mid >= len(moves):
            return False
        mv = moves[mid]
        if (mv['airborne_start'], mv['airborne_end'], mv['ground_fall']) != SLAM_FRAMES:
            return False
        nxt = self.k.resolve_alias(mv['transition'])
        return nxt is not None and nxt < len(moves) and REST[2][1].search(self.name(nxt)) is not None

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
                rx = self.conv_reaction(h['reactions']) if h['reactions'] is not None else None
                entry = dict(req=r, damage=h['damage'], reactions=rx)
                air = T7_AIR[self.game]
                if rl == [air] and (tagsystem.same_reaction(self.T, rx, self.bound_reaction) or
                                    self.lands_at_once(h['reactions'])):                        # an air slam
                    # what TTT2's bound moves play on an air hit once the bound is used: the air entry after it, or
                    # the donor's (Negan's, Geese's, Noctis's slams have none)
                    if j + 1 >= len(t) or [c for c, p in M.reqs(self.k, t[j + 1]['req'])] != [air]:
                        out.append(dict(entry, reactions=self.after_bound_reaction))
                    self.stats['air slams -> the air hit after a bound'] += 1
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
        self.shown = sorted(getattr(self.defn, 'REST_SUMMONS', ())) or self.default_summons()
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
        self.arc_landings()
        self.stats['grounded Screw launches preserve Bound'] += len(
            tagsystem.preserve_grounded_screw_bound(self.T, self.move_name))
        self.stats['native running collision exits restored'] += tagsystem.restore_running_contacts(
            self.T, self.move_name, d.tables, d.move_name)
        move_overrides.apply(self)
        specialcancels.apply(self)
        self.hands8_generic()
        self.dismiss_when_hit()
        self.dismiss_at_start()
        self.hold_thrown()
        # TTT2's tag system on the converted moves (convert/tagsystem.py; the slams were gated while linking): the
        # Tag Crash rows of the landing reactions, then the Tag Assault twins of the bound moves
        self.stats['Tag Crash: moves given the landing tag rows'] += tagsystem.add_landing_rows(
            self.T, tagsystem.landing_template(d.tables, d.aliases), nd, self.aliases)
        made = tagsystem.add_tag_assault(self.T, tagsystem.assault_template(d.tables, d.aliases), nd, self.move_name,
                                         self.string, self.defn.MOVESET.get('tag_assault_finish_hit', ()))
        routes = {self.newidx[self.kn[parent]]: {self.newidx[self.kn[target]] for target in targets}
                  for parent, targets in self.defn.MOVESET.get('tag_assault_strings', {}).items()}
        self.stats['Tag Assault: string tag inputs restored'] += tagsystem.add_tag_assault_strings(self.T, made, routes)
        self.stats['Tag Assault: tag rows on the move before a continued bound move'] += \
            tagsystem.add_tag_assault_continuations(self.T, made, nd)
        self.stats['Tag Assault: bound moves given a tag twin and its exit'] += len(made)
        # ... and the partner coming in for one attacks with its own move, not the donor's: the definition's
        # MOVESET['tag_assault_entry'] (a move name), else its d/f+1
        entry = self.defn.MOVESET.get('tag_assault_entry')
        if entry is None:
            entry = tagsystem.stance_input(self.T, self.aliases, nd, tagsystem.DF, tagsystem.PRESS_1)
        elif entry in self.kn and self.kn[entry] in self.newidx:
            entry = self.newidx[self.kn[entry]]
        else:
            raise ValueError('Tag Assault entry move the fighter does not have (or that is not converted): ' + entry)
        self.stats['Tag Assault: the incoming partner\'s entry attack rows (its own move)'] += \
            tagsystem.set_assault_entry(self.T, self.move_name, entry)
        # ... its idle variants of the stance get the stance's list (tag out, ...), and its launchers tag combos
        # (convert/tagcombo.py)
        idle = tagsystem.share_stance(self.T, self.aliases, nd)
        if idle:
            self.stats['idle variants given their stance\'s list (tag out, ...)'] += idle
        tagcombo.apply(self)
        # Tekken 8's automatic evades: cancel rows first in their moves' lists (EVADE)
        self.evade_rows()
        if self.game == 't8':
            self.handoffs8()
        self.flag8_rows()                   # Tekken 8's flag slots: the properties that set or test them (FLAG8)
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
                row = self.T['moves'][dj]
                if self.contact_unseen(cl, row, mv):
                    row['first_active'], row['last_active'] = mv['first_active'], mv['last_active']
                    self.stats['hub moves taking the fighter\'s active frames (its contact tests)'] += 1
            self.T['moves'][dj]['cancel'] = len(self.T['cancels'])
            self.T['cancels'] += cl
            self.stats['hub moves rebuilt'] += 1

    def contact_unseen(self, cl, row, mv):
        """Whether converted cancel list cl has a row testing the move's own contact (OWN_CONTACT) whose frames end
        before the donor's row is active, though not before the fighter's move (mv) is: a generic move keeps the
        donor's row, its frames too, but takes the fighter's list, timed to the fighter's frames. A generic throw
        whose donor row is active later than the fighter's own frames grabs after its own test, and the throw never
        happens (Tekken 7 and Tekken 8 alike: Josie's f,F+3+4, Thrmv_B2_01, Jun's grab at 14, her rows into the
        throws at 12; Gigas's Overkill and Kunimitsu's f+1+4, the donor's at 12, theirs at 11). The donor's row then
        takes the fighter's frames (rebuild_hubs), as the game the fighter comes from has them."""
        if not mv['first_active'] or (mv['first_active'], mv['last_active']) == (row['first_active'],
                                                                                 row['last_active']):
            return False
        for x in cl:
            if x['direction'] in (M.LIST_END, M.GROUP, M.GROUP_END):
                continue
            if any(c in OWN_CONTACT for c, _ in tagsystem.reqs(self.T, x['req'])) and \
                    mv['first_active'] <= x['win_end'] < row['first_active']:
                return True
        return False

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
                if self.shown:                           # (from the summons a round starts with: summon_reset)
                    summons = self.summon_reset() + summons
                if summons:                              # the weapons its pose holds (Noctis's sword)
                    row['extraprops'] = self.with_props(row['extraprops'], summons)
                self.posed_hands[m] = (t7, False)
            elif not name.startswith('co_') or re.search(r'_%s\(' % re.escape(prefix), name):
                frames = self.donor_anim_frames(d.tables['moves'][m]['anim'])
                if frames:
                    row['anim'] = self.hold(t7, frames)
                    self.stats['donor pose parts holding her pose'] += 1
                    self.posed_hands[m] = (t7, True)

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
            if v.shape[1] < len(animation.BODY_DESCRIPTORS) or len(v) < 2:     # (weapon pairs after: summons8)
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
        self.stats['group rows given their converted group\'s length'] += count_groups(self.T)
        hdr, strings, blob, slots = motbin.split(self.d)
        if self.hands_reference is not None:             # the HANDS row's hand shapes
            blob, slots = motbin.with_slot(blob, slots, motbin.HAND_SHAPES,
                                           motbin.slot_bytes(self.hands_reference[0], motbin.HAND_SHAPES))
        if getattr(self, 'hand8_shapes', None):          # (hands8_generic)
            blob, slots = motbin.with_slot(blob, slots, motbin.HAND_SHAPES, motion.with_hand_frames(
                motbin.slot_bytes(self.d, motbin.HAND_SHAPES), self.hand8_shapes))
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
        if self.hand_anims:                              # (hand_map)
            items[1] = motion.extend_hands(items[1], self.hand_anims)
        if self.part3 is not None:
            items[3] = motion.replace_mota(items[3], self.part3)
        return mb, motion.build_pack(items)

    def summary(self):
        lines = ['tables: ' + ', '.join('%s %d' % (t, len(self.T[t])) for t in TABLE_ORDER),
                 'new animations: %d (%d bytes)' % (len(self.new_anims), sum(len(a) for a in self.new_anims))]
        if self.hands_reference is not None:
            lines.append('hand shapes: the HANDS row\'s')
        if self.hand_anims:
            lines.append('hand animations added: %d (%d bytes)' % (
                len(self.hand_anims), sum(len(a) for a in self.hand_anims)))
        if self.shown:
            lines.append('summons out by default (default_summons): %s' % ', '.join(map(str, self.shown)))
        lines += ['%s: %d' % kv for kv in sorted(self.stats.items())]
        if self.unmapped:
            lines.append('ids without a TTT2 counterpart (dropped where used): %d' % len(self.unmapped))
        return lines
