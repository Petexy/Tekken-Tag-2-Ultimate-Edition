# Playing

Everything about the game itself: which copy you need, how to start it, its controls and settings, and what the
port does differently from the Wii U game. [Golden Fist Launcher](LAUNCHER.md) sets most of this up for you;
Practice mode's additions have a page of their own: [Practice](PRACTICE.md).

## Contents

- [Your copy of the game](#your-copy-of-the-game)
- [Starting the game without the launcher](#starting-the-game-without-the-launcher)
- [Picture and frame rate](#picture-and-frame-rate)
- [Controls](#controls)
  - [Keyboard](#keyboard)
  - [Gamepads](#gamepads)
  - [Icons and menus](#icons-and-menus)
- [Local multiplayer](#local-multiplayer)
- [Input delay](#input-delay)
- [Solo Ghost Battle](#solo-ghost-battle)
- [Settings](#settings)
  - [Display settings](#display-settings)
  - [Your name and the language](#your-name-and-the-language)
  - [Environment variables](#environment-variables)

## Your copy of the game

You need **TEKKEN TAG TOURNAMENT 2 Wii U EDITION**, European release, with
update v16, as a `.wua` archive (Cemu can create one from an installed title;
the update may be merged into the game's folder or stored beside it), or as
a folder with the game's `code/`, `content/` and `meta/` and the update's
files over them.

| Property | Value |
| --- | --- |
| Product code | WUP-P-AKNP |
| Title ID | `000500001010F800` (update `0005000E1010F800`) |
| Version | 16 |
| `code/Tekken.rpx` SHA-256 | `fc0270465d384386f67804e48716e30bfbe85a5a1004e3a6bfe3ac75f9de5019` |

`cafe-recomp` refuses any other `Tekken.rpx`, and the port and its installer
refuse a game whose executable is not the one they were built from.

## Starting the game without the launcher

The launcher installs and starts the game for you. With a game program you built yourself
([Building from source](BUILDING.md)), run the game straight from its archive (or from a game folder):

```bash
build/ttt2 "/path/to/TEKKEN TAG 2 Wii U EDITION (EU).wua"
```

Or install it, as any other program is installed: choose the archive and the install folder in file dialogs, or
give them as `--install GAME FOLDER`. This copies the game (16 GB) and the
program into that folder (a folder that is not empty gets a
`Tekken Tag Tournament 2` folder inside it) and adds **Tekken Tag Tournament
2** to the application menu (`--no-launcher` leaves that out). Then start it
from the menu, or run `ttt2` without arguments; the `.wua` is no longer
needed.

```bash
build/ttt2 --install
build/ttt2 --update      # after a rebuild: copies the new program into the install
```

Saves go to `~/.local/share/ttt2/save` and compiled shaders to
`~/.cache/ttt2`. F11 toggles fullscreen while the game runs (whether it
starts fullscreen is a [setting](#display-settings)).

## Picture and frame rate

- **120 frames per second** on displays of 100 Hz and more: between each
  two frames the game renders, the port shows one more, drawn from the same
  frame with the camera, objects and character skeletons blended halfway.
  The game's logic, physics and hitboxes stay at 60 Hz. When other programs
  keep the GPU busy, frames go out without their extra frame rather than
  slowing the game down. The launcher's Settings can turn it off.
- **Higher resolutions**: up to 4x the original 720p; by default the
  smallest scale that covers your main display (2x, 2560x1440, on 1080p and
  1440p displays; 3x on 4K), or the one chosen in the launcher's Settings
  (1280x720, 1920x1080, 2560x1440, 3840x2160 or 5120x2880).
- **Even frame pacing** on 120 Hz and 240 Hz displays (with
  `VK_KHR_present_wait2`): the game's clock follows the display's
  refreshes, so every image stays on screen equally long.

## Controls

### Keyboard

| Wii U GamePad | Keyboard |
| --- | --- |
| D-pad up / left / down / right | W / A / S / D |
| Top face button (the Wii U's X) | I |
| Left face button (the Wii U's Y) | J |
| Bottom face button (the Wii U's B) | K |
| Right face button (the Wii U's A) | L |
| L / R | H / ; |
| ZL / ZR | U / O |
| + (Start) / − (Select) | Enter / Backspace |
| HOME | Home |
| Left stick up / left / down / right | ↑ / ← / ↓ / → |

The face buttons go by their place on the pad, not by their letters, which
differ between controllers (an Xbox-style pad's bottom button is its A):
I / J K L on the keyboard make the same diamond as the pad's buttons, so
with the game's own button setup J is left punch, I right punch, K left
kick and L right kick. Keys go by position, as on a US QWERTY keyboard.

These are the defaults: the launcher's **Settings** > **Keyboard**
changes them, at once, also while the game runs, and **Restore Defaults**
there brings them back. They are kept in `~/.config/ttt2/keyboard.ini`
(`$XDG_CONFIG_HOME/ttt2/`), one `input = key` per line, which can be edited
by hand too ([its format](ARCHITECTURE.md#running-the-port)); F11,
Escape and the Windows keys cannot be given to a button, and the game prints
what it read when it starts.

### Gamepads

Gamepads work through SDL by button position, as on the Wii U: the right
face button is A, the bottom one B, the top one X and the left one Y, and
fights use them that way. In menus the bottom button (B, by default K on the
keyboard) confirms and the right one goes back, except with a Nintendo
controller, which confirms with its A as on the Wii U. The icons follow the
last controller used (the keyboard counts as a neutral one).

### Icons and menus

**Controls and icons as on a computer**: menus confirm with the bottom face
button and go back with the right one, as on the other consoles (Nintendo
controllers keep the Wii U's way). Button icons follow the controller in
use: PlayStation controllers get PlayStation-style icons, any other
neutral ones that show each face button by its place on the pad. The
game's texts show the icons where they named the Wii U's buttons, and the
title screen's logo says "Ultimate Edition" where it said "Wii U
Edition", in the same brush lettering. All of it is made by the port
from the Wii U game's own files.

## Local multiplayer

In VS Battle, Team Battle and Pair Play every
keyboard or gamepad that presses Start joins as a player of its own, up
to five, and the player entry screen pictures the keyboard, PlayStation,
Xbox-style or Nintendo controller each player holds, drawn in the game's
style. Everywhere else every device plays as the one player.

For one player, the keyboard and all gamepads control the game together,
so any of them can be picked up at any time. VS Battle and Pair Play can be
chosen once two devices are connected (the keyboard and a gamepad, or two
gamepads). VS Battle, Team Battle and Pair Play start on the player entry
screen ("Press the controller's +"):
there each player presses Start (Enter on the keyboard) on their own
device, the first one joining as the Wii U's GamePad and the others as Pro
Controllers, and from then on each device plays only for its player, as
on the console. Back in the menus every device controls the game together
again.

## Input delay

**No forced input delay**: the Wii U game waits two frames (33 ms) after
reading a button before acting on it, in every mode (Cemu's "Reduce input
lag" graphic pack removes it too). The port leaves that wait out; the
launcher's Settings can put it back. Practice's own Input Delay setting
works either way.

## Solo Ghost Battle

A new Offline mode, below GHOST BATTLE: Ghost
Battle fought one on one. The player picks one fighter (no Tag or Solo
choice) and every ghost fights alone, with its own name, rank, record
and recorded play; wins, ranks and rewards count as Ghost Battle's.

## Settings

### Display settings

The launcher's **Settings** also choose how the game starts: fullscreen or
in a window, the resolution it draws at (Automatic, the default, is enough
to cover your main display), whether it shows 120 frames per second on
displays of 100 Hz and more (on by default) and whether fighters wait the
Wii U game's two frames before acting on a button (off by default). Two
more are about the short stops the first time something is shown, while
its shader is made for your graphics card (once per PC, and again after a
graphics driver update): "Shaders in the background" lets the game go on
meanwhile, so the new thing may appear a few frames late instead, and
"Prepare shaders before playing" makes Play first prepare every shader the
game has already used on this PC (it cannot know the ones it has never
shown). The first is off by default, the second on. They
are kept in `~/.config/ttt2/display.ini` (`$XDG_CONFIG_HOME/ttt2/`), which
can be edited by hand too:

```ini
fullscreen = no             # yes or no
resolution = auto           # auto, 1280x720, 1920x1080, 2560x1440, 3840x2160 or 5120x2880
interpolation = yes         # yes or no (no: 60 frames per second)
input_delay = no            # yes: two frames between a button press and the game acting on it, as on the Wii U
async_shaders = no          # yes: shaders compile in the background; new things may appear a few frames late
precompile_shaders = no     # yes: the launcher prepares the shaders seen on this PC before the game starts
```

The game reads it when it starts, so a change applies the next time. The
window opens at the chosen resolution when that fits on the desktop,
otherwise smaller (the picture is scaled to the window or the screen).
Uninstalling keeps it, as it keeps `keyboard.ini`. The [environment
variables](#environment-variables) win over it.

### Your name and the language

The name the game shows for you, in place of its own (Player in English),
and the language of the game's texts and menus are kept beside it in
`game.ini`, which the launcher's **Settings** > **Game** write; by hand:

```ini
player_name = Mira Q        # up to 16 characters; empty or missing: the game's own name
language = fr               # en, fr, de, it, es, ru or pl (any case); empty, missing or another: English
```

The game reads it when it starts too. A character it cannot show (anything
but the letters A to Z, digits, spaces and an English keyboard's punctuation)
becomes `?`, and a longer name is cut to 16 characters.

English, French, German, Italian, Spanish and Russian are the texts the European Wii U game has (in Russian, the
port translates the few it lacks, those only the Wii U version shows); Polish is the port's own translation
([how the languages work](ARCHITECTURE.md#language)).

### Environment variables

| Environment variable | Effect |
| --- | --- |
| `TTT2_SCALE=1/1.5/2/3/4` | render scale: 1280x720 times this (default from `display.ini`, else from the display) |
| `TTT2_FPS=60/120/180/240` | frames shown per second (default 120 on displays of 100 Hz and more, unless `display.ini` turns it off) |
| `TTT2_FULLSCREEN=1` | start fullscreen (another value: in a window) |
| `TTT2_INPUT_DELAY=0..15` | frames between a button press and the game acting on it (the Wii U game's own: 2; default from `display.ini`: 0) |
| `TTT2_AUDIO=0` | no sound |
| `TTT2_AUDIO_VOLUME=0..100` | volume in percent (default 100) |
| `TTT2_SAVE_DIR=<folder>` | where saves go |
| `TTT2_CONTROLLER=playstation/nintendo/xbox` | icons and menu buttons for this kind of controller, whichever is used |
| `TTT2_CHARACTERS=<folder>` | where character packs are (default `$XDG_DATA_HOME/ttt2/characters`, else `~/.local/share/ttt2/characters`) |

Debugging variables are listed in
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md#running-the-port).
