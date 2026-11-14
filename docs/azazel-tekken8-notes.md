# Azazel from Tekken 8: what the port taught

The Tekken 8 import of Azazel (Tekken 8 code `got`, roster id 32, pack `aza`, slot 22). He is a Tekken 8 boss: no
command list, no bust, full-body or costume picture, a 4.2 m body and boss properties on normal buttons. These notes
record what his port needed, for later fighters.

## Giant fighters (reusable for any fighter much taller than a man)

* `character.ini camera = H` (definition `CAMERA`, mm from his feet's spheres to his top) drives
  `runtime/src/title/fight_camera.cpp`: the 2-character camera (sub_05FC085C) and focus (sub_05FB6FEC) frame him whole
  with a side margin of 0.65 H from the middle of his spheres; camera animations (sub_05FBE5B4: intros, win poses,
  move cameras) are anchored at his head (a man's head at 1.62 m mapped on his highest sphere, scaled by the body
  size) and turned to his head when they look more than 11.5 degrees away; a launched man is kept under the health
  bars (85% of the picture's height); the KO slow motion (replay camera sub_060B44E4) and the throw camera's view step
  (sub_06130C84, where its 10 m limit is applied) are contained the same way. Matches without a giant are identical
  frame for frame (camera, bodies, pushes, hits) to the runtime without the hook.
* `character.ini body = S` (definition `BODY`) drives `runtime/src/title/giant_body.cpp`: player+1652 is the Mushroom
  Battle size (it scales the model too, so never write it for an added giant). The hurt-sphere code (sub_03D6B9F4) and
  push-sphere code (sub_03D6B544) multiply radii by it; giant_body multiplies his 14 hurt and 8 push spheres by S
  after the title sized them, and takes 600 (S - 1) off a man's body gap to him (sub_03AD994C: throw requirements 3..9
  need their reach to be at least that gap). Mushroom Battle also adds 500 mm x (attacker size - victim size) to hit
  lines (sub_039C0460 in the hit test sub_039C0508): not used, his grabs connect from his own boxes.
* Throws of a fighter whose skeleton is scaled (1.8): the game places both fighters' hips at 1.8 x channel 0 across
  the floor and F x channel 1 + 60 in height, F depending on the victim (1.196 Bob, 1.192 Kuma, 1.120 Xiaoyu).
  `MOVESET 'victim_ground'` + `'throw_height'` (convert/moveset.py THROW_PAIRS8) divide the victims' floor paths by
  the scale and fit the heights, so the man is in his hand.
* Tekken 8 throws slower than the donor's grab keep their own frames (THROW_LATE8 in contact_unseen).

## Moves and data

* Tekken 8 hit boxes with radii become TTT2 points: big spheres (a 10 m wave, a 4 m disc) go through THROWN as
  projectiles (shape 2 -> cylinder); THROWN `ends_on_hit` moves a move's own-hit rows first, because TTT2 sets the
  owner's projectile-hit flag (+1152 0x200000, requirement 46) a frame after Tekken 8 sees it.
* Requirement 51 (whiff) is decided by the melee hit test at the last active frame, before a projectile hits.
* Requirements 35/36 measure the same floor distance between the fighters' origins in both games (1:1).
* A fighter without a Tekken 8 command list gets one from its converted moveset (convert/movelist_rows.py) with
  names the definition writes (`COMMANDS`).
* Beams: Tekken 8 0x8262/0x8263/0x8264 have no TTT2 counterpart; a TTT2 laser (0x8145/0x8146/0x8147) needs its .alo
  meshes copied with it (TEKKEN8 `beam_look`).
* Tekken 8 effect systems can draw wrong in TTT2 (flat opaque planes, mesh scales growing to 75, dark discs seen
  edge-on): judge every effect move whole from full-size frames and tune per definition (TEKKEN8_EFFECT_TUNE).

## Polish: pillars, tail, b+1 and 4

* His crystal pillars (1, d+3+4) were invisible for three reasons: measured effects ignored a projectile look's `at`
  position (they sat inside his body); an effect mesh with a character material (`M_EF_CH_ITM*`) read as an effect
  material turns brightness into opacity (a faint ghost: role `solid`, opaque in the body-crystal colours with baked
  light); and the runtime turns any effect spawned on the frame a projectile is thrown to that projectile's path
  (roster.cpp effect_pitch), so a straight-up projectile laid the pillar on its back in the air
  (TEKKEN8_EFFECT_TUNE `'pitched'` converts the look counter-turned).
* A Tekken 8 effect that seems to shatter at its end is usually its material's dissolve: a noise texture in one of the
  mesh's UV sets, `Edge` and `EdgeCol` for a glowing band, driven by the emitter's dynamic parameter (threshold
  1 + clip - dynamic). TTT2's effect models cannot cut (they ignore the alpha test and texture frames), so role `cut`
  bakes the cut as one copy of the mesh per frame, each with its own cut texture and one frame of alpha.
* Tail attacks hit from WEAPONS points on the tail's own spring bones (tip and middle), so they land where the drawn
  tail touches; a hit joint at the hips makes a line under the floor.
* Grabs that should take only a hit or counter hit (b+1, as Jinpachi's): move_overrides `hit_grab` gates the grab half
  on requirement 46 and gives the guard a normal block reaction.
* His 4 rows went to the All Direction Attack (a boss charge) before the mid kick his Tekken 6 4 is; dropping the
  charge's rows makes 4 that kick from Tekken 8 data alone.
