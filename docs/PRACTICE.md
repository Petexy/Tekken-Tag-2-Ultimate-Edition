# Practice

The port adds Tekken 8's training tools to Practice mode: frame data, input history, a position reset, plus 3D
hitboxes, a view from above and slow motion. This page explains each one and where to switch it on. For everything
else about playing, see [Playing](PLAYING.md).

## Contents

- [At a glance](#at-a-glance)
- [Position reset](#position-reset)
- [ULTIMATE SETTINGS](#ultimate-settings)
- [Frame data panels](#frame-data-panels)
- [Command history](#command-history)

## At a glance

- **Position reset in Practice**, as in Tekken 8: 3 and − (Select) pressed
  together put both fighters back where the stage put them; a hint at the
  bottom right of the screen says so, in the look of the game's own.
- **Frame data in Practice**, as in Tekken 8: a panel for each player at the
  bottom of the screen shows the damage of their hits and combos, the hit
  level, startup and active frames of their last attack, frame advantage
  after a hit or block, counter hits, punishes and wall hits, posture and
  distance. The pause menu's ULTIMATE SETTINGS submenu (in place of TOUCH
  SELECT) sets them up, and can colour the fighters by frame advantage after
  a hit or block (blue ahead, red behind).
- **Hitboxes and a view from above in Practice**: the fighters' bodies as
  the game tests hits against them, in 3D, and their attacks' hit lines,
  with the parts an attack reaches lit red; a window shows the fight from
  above as well, to see what a sidestep avoids; slow motion at half or a
  quarter speed.
- **Input history in Practice**, as in Tekken 8: COMMAND HISTORY (on from
  the start of each Practice session) shows the player's inputs in a column
  on the left, newest on top, each with the frames it was held, in place of
  the game's bar along the bottom.

## Position reset

In Practice, 3 (left kick: by default K, or a gamepad's bottom button) and
− (Select: Backspace) pressed together, in either order, put both fighters
back where the stage put them, standing, as Tekken 8's position reset does;
the pause menu's POSITION SETTINGS apply as at the start of training. 3 is
whichever button the game's Controller Setup gives left kick. − alone still
reaches the game, a few frames later than before.

## ULTIMATE SETTINGS

Practice's pause menu has ULTIMATE SETTINGS where the Wii U had TOUCH
SELECT (the GamePad's touch-screen moves, which a computer has no use for,
and which stopped the game with an added fighter): a submenu like the
game's own, to show or hide the frame data panels (FRAME DATA) and each
player's (1P PANEL, 2P PANEL), all on to begin with, and, off to begin
with:
- ADV. COLORS: as in Tekken 8, from a hit or block until both fighters can
  act again, the fighter ahead in frames turns blue and the one behind red.
- HITBOXES: each fighter's body as the game sees it when it tests a hit,
  the 14 spheres it puts on the fighter's bones every frame, drawn in 3D
  (1P's cyan, 2P's yellow, through the fighters), and the lines an attack
  tests against them on its active frames (red, in front of everything,
  fading over a third of a second). A sphere an attack's line crosses turns
  red: that is what the hit reached. Added fighters show theirs the same
  way.
- TOP CAMERA: a window between the panels shows the fight from straight
  above, the game itself rendered a second time from there, while the main
  camera stays as it is: the fighters' line across it, 1P's end on the
  left, high enough for both. With HITBOXES on they show in it too, so
  whether an attack's line reaches across a sidestep shows directly. It
  costs a second rendering of each frame while it is on; only what the
  game's own camera could see is drawn in it.
- SLOW MOTION: OFF, 1/2 or 1/4 speed, as in Smash Bros.' training mode:
  the fight steps its frames at that rate (the same picture shown in
  between), and every button pressed meanwhile still counts. The pause
  menu keeps its speed.

## Frame data panels

The frame data panels show, for each player: **Total Damage** dealt since
the round started (or the last position reset), the best combo's damage, the
last attack's hit level (High, Mid, Low, S.Low), the last hit's damage with
the game's multiplier (as its own DAMAGE display: 120% for a solo fighter,
more on a counter hit) and how much of it is recoverable, and whether it was
a counter hit, a punish (a hit during the recovery of the opponent's
attack) or hit the opponent into a wall, as the game's own COUNTER, PUNISH
and WALL HIT texts say, for the whole combo; then the attack's startup
and active frames, the frame advantage after the last hit or block, as it
lands (green for the side ahead, red for the side behind; "KND" when the
hit knocked the opponent down), the posture and the distance between the
fighters in metres. Total Damage and the best combo start over on the
position reset. They move up above the game's DAMAGE INFO 2 bars when those
are on, and are not shown in the pause menu. 2P's panel has a red tint.

## Command history

COMMAND HISTORY (in the pause menu's ADVANCED SETTINGS → HUD Information)
shows the player's inputs as Tekken 8's Practice does: a column on the left
side of the screen, the newest input on top, each row a direction (as the
fighter faces) and the buttons held, drawn with the game's own icons, and
the number of frames it was held. It replaces the game's command history
bar along the bottom.

How the panels are made: [ARCHITECTURE.md](ARCHITECTURE.md#practice-frame-data).
