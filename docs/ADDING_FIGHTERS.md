# Adding fighters

Fighters from Tekken 7 and Tekken 8 can join Tekken Tag Tournament 2's roster, made from **your own copies** of those
games. The launcher's **Fighters** screen does all of it for you ([Golden Fist Launcher](LAUNCHER.md#fighters)); this
page explains what an added fighter brings, what adding one needs, how to do it from a terminal, and which moves bound.

## Contents

- [Who can join](#who-can-join)
- [What you need](#what-you-need)
- [Adding them from a terminal](#adding-them-from-a-terminal)
- [Character packs](#character-packs)
- [What they bring, and what is left out](#what-they-bring-and-what-is-left-out)
- [Bound moves](#bound-moves)

## Who can join

The fighters of Tekken 7 that Tekken Tag Tournament 2 does not have can join
the roster beside its own (no fighter is replaced): Kazumi Mishima, Lucky
Chloe, Eliza, Claudio Serafino, Akuma, Gigas, Josie Rizal, Katarina Alves,
Master Raven, Shaheen, Fahkumram, Leroy Smith, Lidia Sobieska, Kunimitsu II,
Negan, Geese Howard and Noctis. From Tekken 8: Reina, Azucena, Miary Zo, Victor Chevalier, Clive Rosfield and
Azazel. Each gets a cell of its own on the select
screen: the free ends of the top row first, then new columns beyond the rows'
ends (19 cells), then a new top row, which appears once the 20th fighter is
added (the grid moves down a row into the space under it; 45 cells in all;
the order follows the order of import). The costume chooser
offers each one's Tekken 7 preset outfits (4 to 10 per fighter) when they are
imported with them: the launcher has an **Outfits** box for each fighter and
one for all of them (for a fighter already added, changing it offers an
**Update** that adds or removes their outfits), and the importer makes them
for everyone unless told otherwise (`--outfits none`, or the fighters' names
separated by commas).
Outfits make an import much longer; without them, a fighter has their own
costume only.

## What you need

Nothing of them is in this repository: an importer makes them from **your own
copies of both games** and writes character packs on your computer. You need:

- Tekken 7 for PC (Steam), installed and started from Steam at least once
  (the importer finds it, its Proton and its prefix through Steam), and Steam
  running: the Steam of your distribution's packages or Valve's installer
  (Steam from Flatpak or Snap is found, but not supported yet);
- the game installed with the launcher or `ttt2 --install` (the importer
  reads its folder);
- gamescope, `pactl` (PipeWire or PulseAudio), MinGW
  (`x86_64-w64-mingw32-gcc`, to build a small helper the first time) and
  Python 3 with numpy and Pillow. The launcher brings the helpers and the
  importer's C parts built, and where Python has no numpy and Pillow
  (SteamOS, Bazzite) its **Download** gets them from PyPI into
  `~/.local/share/ttt2/python/` (the wheels pinned with their SHA-256 in
  `tools/characters/ttt2char/python_packages.lock.json`; no pip, nothing of
  the system changes): `tools/characters/get_python_packages.py` does the
  same from a terminal.

For Tekken 8's fighters, Tekken 8 for PC (Steam) takes Tekken 7's place, started from Steam once in the same way;
they need neither Tekken 7 nor any of its fighters.

## Adding them from a terminal

```bash
python3 tools/characters/import_character.py --all --game /path/to/your/install
```

A fighter's moveset exists only inside the running Tekken 7, so the importer
first saves the movesets it does not have yet: Tekken 7 starts in the
background, with no window and no sound (gamescope's headless mode and a
silent audio output of its own), the game's own loader loads the fighters
while it sits on its start-up screens, and it is closed again. Nothing is
pressed and no menu is used, so your key bindings and settings do not matter.
Stopping the importer (Ctrl+C, or Cancel in the launcher) closes the hidden
Tekken 7 too and leaves no half-written pack; a Tekken 7 you start yourself
is left alone.
Only fighters your Steam account owns are imported (Steam must be running; it
tells which DLC you own): a fighter whose DLC you have not bought is skipped,
whichever movesets are already saved. Tekken 7 also keeps Geese's and
Noctis's costumes (and Noctis's voice) encrypted in its files: in the same
run the game reads those files with its own file reader, the one its loading
uses, which hands them over decoded, and they are saved to
`~/.local/share/ttt2/tekken7/files/` (about 670 MB for both) for the
importer. A file the game does not hand over plain and whole (a mod's pak
in a folder below `TekkenGame/Content/Paks` can replace it) is named in the
log, with why, and asked for again on the next import of that fighter: the
import fails only when it needs that file, saying which, and a preset outfit
that needs it is left out.
`tools/characters/dump_tekken7.py` does that step alone (the
movesets go to `~/.local/share/ttt2/tekken7/movesets/`); movesets saved with
[TKMovesets2](https://github.com/Kiloutre/TKMovesets) work too
(`--movesets FOLDER`). Tekken 8's fighters are saved the same way, from a hidden Tekken 8:
`tools/characters/dump_tekken8.py` does that step alone (the movesets go to `~/.local/share/ttt2/tekken8/movesets/`).

The fighters' names for the importer: `kazumi`, `chloe`, `eliza`, `claudio`,
`akuma`, `gigas`, `josie`, `katarina`, `master_raven`, `shaheen`,
`fahkumram`, `leroy`, `lidia`, `kunimitsu2`, `negan`, `geese`, `noctis`, and from Tekken 8 `reina`, `azucena`,
`miary_zo`, `victor`, `clive`, `azazel` (one or several; each
takes about a minute, and what they share is made once at the end).
`--remove NAME...` removes fighters again; the others keep their cells.

## Character packs

The packs
go to `~/.local/share/ttt2/characters/` (or `$XDG_DATA_HOME/ttt2/characters/`:
a folder per fighter, and `shared/`, the title's pictures, colours and name
calls the added fighters share; `$TTT2_CHARACTERS` picks another folder).
Each pack names the pack format it was made in. The game loads only packs of
its own format and skips older and newer ones (it says so on its console):
add an older pack's fighter again (the launcher offers it), and it comes back
in its own cell. A pack with no format line counts as format 1, unless it has a
`keys/` folder of its own: those are the earliest packs (made before
`shared/` existed), which must be added again.

> [!WARNING]
> **The packs hold Namco's assets: keep them to yourself and never upload or
> share them.** The importer refuses to write them inside this repository, and
> `.gitignore` keeps the games' file types out of commits.

## What they bring, and what is left out

Each has their own model with both players' colours (skin tones matched to
Tekken Tag Tournament 2's own fighters), moves, voice, command list, and their
pictures and name on the menus' screens and in fights; Kazumi's tiger appears
in the moves that summon it, long hair and tails hang and swing, coats, robes,
ribbons and headscarves swing like Lars's coat tails, their moves'
effects (Eliza's and Akuma's fireballs, auras, smoke) are Tekken 7's own,
converted to Tekken Tag Tournament 2's effect files (close, not the same:
Tekken 7's glow and some of its shading are left out), Negan swings his bat
and hits with it, Noctis summons his swords, daggers, spear and shield for the
moves that use them, Leroy's cane and Master Raven's sheathed katana are where
they carry them, and the moves that hit with a weapon (Kunimitsu II's blades
too) reach as far as the weapon. Left out for now: Rage Arts and Rage Drives,
power crush armour (those moves are there, without it), screws (a screw move
juggles as it does in Tekken 7 once the screw is used; Noctis's WS 2,2 still
screws, without using up the juggle's bound),
the weapons they take in hand only for some moves (Kunimitsu II's blades,
Master Raven's drawn sword, Leroy's folding staff, Negan's knife), the weapons
of Noctis's Rage Art, Katarina's and Leroy's sunglasses, and Gigas's back
tubes.

How the importer converts them: [ARCHITECTURE.md](ARCHITECTURE.md#added-fighters).

## Bound moves

Tekken 7 has no tag, so the importer adds what Tekken Tag Tournament 2's tag
system needs: they tag out (and have tag throws) while walking, dashing,
stepping back, crouching or crouch walking, as Tekken Tag Tournament 2's own
fighters do; press Tag during a bound move's startup (before it hits) for a
Tag Assault, and their juggles give the Tag Crash input on landing (2+Tag
with the partner in Rage). Tekken 7 has no bound either: the bound moves are
the ones the Tekken 7 Bound Mod gives each fighter (and Akuma's d/f+1+2,
Noctis's jump 1+2 and the second hit of Geese's f,d,d/f+2), and each bounds
once per juggle, as Tekken Tag Tournament 2's own do. Screws are no bounds,
and neither are Tekken 7's slams outside that list: they play the air hit
Tekken Tag Tournament 2 plays once a juggle's bound is used. Tekken 8's
fighters bound with their own lists alike (Tekken 8's tornados are no
bounds). Inputs in Tekken 7's notation (WR while rising, WS while standing
up, SS sidestep, BT back turned, FC full crouch):

| Fighter | Bound moves |
|---|---|
| Kazumi | d/b+1+2; d/f+1,2; f,F+4; 3,2; u/f+3,4,1; Fearless Warrior 3 |
| Lucky Chloe | 1,2,2; f+2,2; d/f+3,2; b+2; f+4,4; u+3+4; BT 3,3+4; Left Twist 3 |
| Eliza | f,F+4,2; b+1,2,4; b+1+2; d,d/b,b+3; EX Moon Glide 1+2 |
| Claudio | f+2,1; f+4; f+1+2,1+2; b+3,3; b+4,3,2; b+1+2; u/f+2; f,F+2,2 |
| Akuma | f+1+2; d/f+1+2; d/f+1,2; f,F+4; WS 4,4; Hyakkishu (f,d,d/f+3 or 4) 2 |
| Gigas | d+2; f+2,1,1; f+1+2; d/f+1+2; d/f+4,1+2; b+4; b+1+2; WS 4,2; 10-hit string (its 8th hit) |
| Josie | d+2; u/f+3; f,n,d,d/f+1+2; Switch Stance 1 |
| Katarina | 1,1,1; 1,1,3; 3,3,3,3,3; d+1; f+3; f+1+2; b+4,1+2; u/f+4,4; u/f+3+4; f,f,f+3; Harrier 2 |
| Master Raven | b+1; b+1+2,2; u/b+1,2; u+3,d+3,3; u/f+3+4,f+4,3; FC d/f+3+4,4; BT f+2,3; Haze 4 |
| Shaheen | 4,4; b+1; b+3; f+3+4; u/f+3 |
| Fahkumram | d+1; d+3+4; f+3+4; u/f+1; d/f+2,1; d/f+1,4,1; d/f+4,3,3; f,F+4,1 |
| Leroy | d+1+2; u/f+3+4,1+2; Hermit f+4; Hermit b+1 |
| Lidia | d+1; b+1,2; f+4,3,1; u/f+3; SS 2; Cat Foot Stance I 4; Pouncing Tiger, Stalking Wolf 4 |
| Kunimitsu II | d+1; d/f+1+2; d/f+1,2,2; f,F+4,2; d,d/f,f+2; WS 1,1; Setsunagake 1,2,3 |
| Negan | d+2; 1,2,2; b+2,2; b+1+2; d/f+3,1,2; Intimidation 2; Intimidation 2+3 |
| Geese Howard | 1,2,1; b+2; d/f+3,4,2; d,d/b,b+2,3 (and its EX version); f,d,d/f+2 (its second hit) |
| Noctis | WS 1,2; WR 1+2; d/f+4,2,2; d+4,1,1+2; b+3,1; b+1+4; u/f+2; SS 2; jump 1+2; Jump Peak 1+2 |
| Reina (Tekken 8) | d+2; f+4 (also out of a dash); d/f+1,2; 3+4; Sentai 4; Heaven's Wrath 3+4 |
| Azucena (Tekken 8) | d+1; d/f+1,4,1~2 (its last hit); Libertador 3,1; Libertador 4,2; u/f+4; u/f+3+4; f,f+4 |
| Miary Zo (Tekken 8) | d+2; d/f+1,1,2 (its last hit); b+1+2; WS 3; Morengy 1+2; Baobab 1,4 (its last hit) |
| Victor Chevalier (Tekken 8) | f+1+2; u+1+2; Perfumer 1+2; Iai 1,2,2 (its last hit) |
| Clive Rosfield (Tekken 8) | f+3; f,F+2; f+2,2,2 (its last hit); jump 1 (straight up, forward or back); Burning Rain (jump 2,2, its last hit); Staff of Judgment (f,F+1+2) |
| Azazel (Tekken 8) | 1; 3; 2,2 and f+2,1+2 (their second hits); d+1 or d/b+1; d+2; d+3; d+3,4; d+4 or d/b+4; d+4,3; d+4,3,4; d+4,3,4,3; d+1+2; d/f+1+2; u+3+4; jumping u+1, u/f+1, u/f+1+2, u+1+2, u/b+1, u/b+1+2, u+3 or u+4 |
