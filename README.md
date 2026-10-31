# Tekken Tag 2 Ultimate Edition

<img width="1593" height="888" alt="image" src="https://github.com/user-attachments/assets/3bd58409-1442-4ce7-b9a6-8f036f38f4f8" />


An unofficial native Linux port of **Tekken Tag Tournament 2 Wii U Edition**,
made by static recompilation: the game's PowerPC code is translated to C++
ahead of time and runs as native x86-64 code on a reimplementation of the
Wii U's system libraries. There is no CPU emulation; the game's GPU commands
and shaders are translated to Vulkan as it runs.

> [!IMPORTANT]
> **No game files are included.** This repository holds only original tools
> and runtime code; you need your own copy of the game
> ([see below](#the-game)). The C++ generated from the game, programs built
> from it, an install folder, and captures or dumps made with the debugging
> options all contain the game's code or assets: do not share or upload
> them, and do not attach them to issues.
>
> This project is not affiliated with or endorsed by Bandai Namco
> Entertainment or Nintendo. TEKKEN, Tekken Tag Tournament and Wii U are
> trademarks of their respective owners.

## Features

- **Plays natively**: intro, menus, character select, arcade mode and versus
  matches, with sound and saves. Arcade mode has been played through by
  hand.
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
- **Controls and icons as on a computer**: menus confirm with the bottom face
  button and go back with the right one, as on the other consoles (Nintendo
  controllers keep the Wii U's way). Button icons follow the controller in
  use: PlayStation controllers get PlayStation-style icons, any other
  neutral ones that show each face button by its place on the pad. The
  game's texts show the icons where they named the Wii U's buttons, and the
  title screen's logo says "Ultimate Edition" where it said "Wii U
  Edition", in the same brush lettering. All of it is made by the port
  from the Wii U game's own files.
- **Local multiplayer**: in VS Battle, Team Battle and Pair Play every
  keyboard or gamepad that presses Start joins as a player of its own, up
  to five, and the player entry screen pictures the keyboard, PlayStation,
  Xbox-style or Nintendo controller each player holds, drawn in the game's
  style. Everywhere else every device plays as the one player.
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
- **No forced input delay**: the Wii U game waits two frames (33 ms) after
  reading a button before acting on it, in every mode (Cemu's "Reduce input
  lag" graphic pack removes it too). The port leaves that wait out; the
  launcher's Settings can put it back. Practice's own Input Delay setting
  works either way.
- **Installs like any other program**: `ttt2 --install` copies the game into
  a folder you choose and adds it to the application menu.
- **Made to be modified**: every function of the game is a C++ function that
  can be replaced ([see below](#changing-the-game)).

## Status

Playable from boot through arcade mode. Not done yet: the Wii U GamePad's
screen and speaker, online play, the software keyboard and error viewer
screens, and audio effects the game does not seem to use. Only the European
version with update 16 is supported (other versions have different code).
Tested on Linux with an AMD GPU (RADV) under KDE Plasma (Wayland). Design
notes, measurements and milestones are in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## The game

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

## Requirements

- Linux on x86-64 with AVX2 and FMA (x86-64-v3: Intel Haswell, AMD Excavator
  or newer).
- A Vulkan 1.3 GPU and driver with `VK_EXT_external_memory_host` and push
  descriptors (current AMD, Intel and NVIDIA drivers).
- To build: Git, CMake 3.20+, Ninja, Clang (or GCC 15+), Python 3, and the
  development files of SDL 3.2 or newer, shaderc, the Vulkan loader, Vulkan
  headers recent enough to define `VK_KHR_present_wait2` (mid-2025 or
  newer), OpenSSL 3, zstd and zlib; for the launcher also GTK 4.10 or newer
  (without it the launcher is left out) and MinGW (optional: the Tekken 7
  and Tekken 8 helpers are then built in).

On Arch Linux:

```bash
sudo pacman -S --needed base-devel git cmake ninja clang python zstd zlib openssl vulkan-headers vulkan-icd-loader sdl3 shaderc gtk4 mingw-w64-gcc
```

Other distributions package the same libraries under similar names; older
releases such as Ubuntu 24.04 and Debian 12 ship SDL and Vulkan headers that
are too old.

## Building

```bash
git clone https://github.com/Petexy/Tekken-Tag-2-Ultimate-Edition.git && cd Tekken-Tag-2-Ultimate-Edition
python3 tools/setup_deps.py                      # ZArchive and AMD's addrlib, at pinned revisions

cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build build --target wua_extract cafe-recomp

# The game's executables and metadata (about 70 MB per title folder) into local/wua
build/wua_extract extract-analysis "/path/to/TEKKEN TAG 2 Wii U EDITION (EU).wua" local/wua
# The v16 executable's code as C++ in generated/ttt2 (in the update's
# folder, or in the game's when the update is merged into it)
build/recomp/cafe-recomp local/wua/*_v16/code/Tekken.rpx generated/ttt2

cmake -B build -DTTT2_GENERATED_DIR="$PWD/generated/ttt2"
cmake --build build --target ttt2
```

Recompiling takes a few seconds; compiling the generated code takes a few
minutes. `local/`, `generated/`, `third_party/` and `build*/` are ignored by
Git, so nothing derived from the game ends up in a commit; keep captures and
dumps from the debugging options under `local/` too.

## The launcher

### Windows launcher

**Starting from a release (Windows 10/11, x64):**

1. Download `Ultimate_Launcher-x86_64.exe` from the newest release and put it
   in a folder of yours (not Program Files: it replaces itself when it updates).
2. Double-click it. The first start unpacks the launcher's files into
   `%LOCALAPPDATA%\TTT2Ultimate\launcher` and gets its private Python ready
   in a console window; later starts open the launcher at once. (When that
   path has letters beyond plain ASCII, as a user name such as José gives it,
   the files go to `%PUBLIC%\TTT2Ultimate\launcher` instead: see below.)
3. Continue with **Set Up Game** as in step 3 below. The tools, the build
   and the generated code stay in that folder too (plan its 30 GB on that drive).

The release launcher updates itself. When it starts (and when its window is
back in front after six hours) it asks GitHub for this repository's newest
release; when that is newer, a notice at the top of the window says so, with
**What's New** (the release's page) and **Update**, and the button at the
top right says **Update to** its version (that button also looks for an update
any time). Update downloads the new `.exe` beside the one you started, checks
it (its size, GitHub's SHA-256, that it is a 64-bit Windows launcher and says
it is that version), puts it in that one's place and opens it: it unpacks its
files over the old ones, keeping everything else there. Anything failing, or
Cancel, leaves the `.exe` as it was. A game an older version built gets
**Update** beside Play, which builds it again on this PC with the new version's
changes. The launcher also says when `main` has newer changes than its release,
as the Linux launcher does (below).

A test build (an `.exe` made on a branch other than `main`, for testers) follows
its branch instead: when the branch has newer commits, the notice says so with
**Update**, which downloads the newest commit's files from GitHub, puts them in
place of the ones the `.exe` unpacked and opens the launcher again: a fix pushed
to the branch reaches testers without a new `.exe`. A game built from older
files then gets **Update** beside Play. One stopped half-way is unpacked again
from the `.exe` when it is next started.

When Set Up Game or Update fails, the task panel names the checks that failed or
the build's first error; **Open Log** there opens the whole log.

**Starting from a downloaded project ZIP (Windows 10/11, x64):**

1. Download this branch as a ZIP and **Extract All** into a writable folder
   whose path has only plain letters and is short, such as `C:\TTT2`: not in
   OneDrive (30 GB would be synced). Set Up Game refuses a path with letters
   such as à: CMake runs some build steps through batch files it writes in
   UTF-8, which `cmd.exe` reads in the console's code page, so such a letter
   turns into others and the step finds no folder.
2. Double-click **Start Ultimate Launcher.cmd** in that folder. The first start
   downloads and verifies a private Python/Tk runtime. No Python installation,
   Git installation, terminal commands or second project download are needed.
3. Click **Set Up Game**, select your own European Wii U TTT2 `.wua` containing
   update v16, and choose an installation folder.
4. Leave setup running while it downloads missing tools, prepares libraries,
   checks your game executable, builds and installs the Windows game.
5. Click **Play** when setup completes. To add fighters, open Steam, close T7/T8,
   select fighters and use **Import / Update selected**. Reina requires Tekken 8.

The first setup needs internet, a Vulkan-capable graphics driver, an x86-64-v3
CPU and substantial free disk space for the tools, generated build and game.
It can take a while; keep the extracted project folder for future updates.
Downloads are private to ignored `local/` folders. Python, LLVM-MinGW and MinGit
archives are SHA-256 pinned; Python packages are version pinned. Existing
project files are reused; the game and its assets are never downloaded.
Setup logs remain under the selected data folder. The game archive is kept.


The Windows build also produces `build-windows-tools/ttt2-launcher.exe`.
This opens a separate Windows interface; the GTK launcher and Linux build/import
paths are unchanged. The ZIP startup path obtains private Python/Tk automatically; developer launches
can also use an installed Python 3 with Tcl/Tk. Setup obtains numpy and Pillow. Set `TTT2_PYTHON`
to a Python executable to override automatic discovery.

The Windows interface looks and behaves as the Linux launcher: one page with the
game (Play, Settings, Update when the launcher's version is newer than the game's)
and its characters as the shared importer finds them (Tekken 7, Tekken 8 and Steam;
Add, Update and Remove per fighter, Add All, the DLC with what Steam says you own),
a Settings page (fullscreen, resolution, 120 fps, input delay, and the keyboard's
keys chosen by pressing them, as the Linux launcher writes keyboard.ini), and the
task panel below with its progress, Cancel and Details. Windows' own parts stay:
Set Up Game, the More menu (Build / Rebuild, Install from Wii U Source, Update
Installed Game, the logs) and the Folders in Settings. It calls the existing Windows
build scripts, native installer, and shared character importer, and needs nothing
beyond the Python with Tk it gets itself. Set Up Game prepares the build tools automatically from the extracted project.
Keep the project folder for rebuilds. The compiled launcher executable can also
be opened from its build folder after setup.

It detects the existing development archive, extracted title, fighter packs,
saves, and CMake toolchain. Use **Paths**, then **Save paths**, to change them.
Development configuration is saved in ignored `local/windows-launcher.json`;
other layouts use `%LOCALAPPDATA%/TTT2Ultimate/launcher.json`. The data folder must
end in `TTT2Ultimate` so runtime settings and launcher settings use the same place.
Explicit fighter/save paths are passed to both the game and importer. Packs
marked **Update available** still load: this compares revisions from the shared
importer and never automatically rebuilds anything.

Task/game logs are saved under the selected data folder's `logs/` directory;
startup errors are saved beside the executable in `launcher.log` (the release
`.exe`'s in `local/launcher.log` of its folder in `%LOCALAPPDATA%`). Build/install
tasks finish before the window closes. Import cancellation requests cleanup and
keeps completed extraction data. Only the release `.exe` updates itself (a
project ZIP is updated as a whole); this frontend does not implement the GTK
key-capture screen or the Linux uninstall interface.


`ttt2-launcher` (**Ultimate Launcher**) does the installing and
the adding of fighters in a window, without a terminal. **Install…** asks for
your `.wua` and a folder, checks the PC, builds the game program for it from
the archive and installs the game with its menu entry, as `ttt2 --install`
does; then **Play**, **Update** (when the launcher's version differs from
the program's) and **Uninstall…** (saves and added characters are kept unless you
tick them; of a save folder you chose with `TTT2_SAVE_DIR`, only the game's
own saves go). While the game runs, however it was started, Play, Update and
Uninstall wait for it to end. The gear next to Play opens its **Settings**:
whether the game starts fullscreen, the resolution it draws at, its 120
frames per second, whether fighters wait the Wii U version's two frames
before acting on a button, and its keyboard keys ([Playing](#playing)). Its
Characters section shows where Steam has Tekken 7 and Tekken 8, or why one cannot be used, and a part for each game's
fighters (the installed game's first), with **Add** per fighter: Tekken 7's with **Add All** and its DLC
fighters in a list that opens, with those your Steam account owns and **Add
All Owned**; Tekken 8's (Reina, Azucena) without Tekken 7 or any of its fighters. **Remove** takes one out again. A
Tekken 8 fighter whose moves could not be saved from Tekken 8 (a game update its helper does not know yet, or
nothing to run it hidden) is added with Heihachi's moves, says so and why, and is offered as an update once
their own can be saved. What all added fighters share is made from each one's own game, so while one game is
uninstalled its fighters stay in the game but no other can be added: the launcher says so, and offers to
remove that game's fighters all at once.

```bash
cmake --build build --target ttt2-launcher ttt2_kit
build/launcher/ttt2-launcher
```

Nothing of the game is in the launcher: the game program is built on your PC
by the launcher's kit (`build/launcher/kit`: `ttt2-build`, `cafe-recomp` and
the runtime) with your C++ compiler, in a few minutes. It needs Clang (or
GCC 15+) and the SDL 3, shaderc, Vulkan, OpenSSL 3, zstd and zlib libraries
(not their development files); the launcher checks the processor, the
compiler and free space first and shows the command that installs what is
missing. On image-based systems, whose package manager cannot add to the
system (SteamOS, Fedora Atomic and Bazzite, openSUSE MicroOS and Aeon,
NixOS), it says instead that the compiler and the importer's tools must come
from a toolbox or distrobox container, or from the system's own way of
adding software. `build/launcher/kit/bin/ttt2-build install GAME FOLDER`
does the same in a terminal; `ttt2-build check` alone only checks that this
PC can build the game program (the compiler, the libraries, and that the
program links with them and starts).

To make an AppImage of the launcher (the launcher, its kit and the character
importer; nothing of the game):

```bash
launcher/appimage/make_appimage.sh Ultimate_Launcher-x86_64.AppImage build-appimage
```

It builds in a folder of its own (here `build-appimage`; Git ignores it and
the AppImage), needs LLD and `mksquashfs`,
and downloads the AppImage runtime once (`--runtime-cache DIR` says where).
The AppImage uses the system's GTK 4 (4.10 or newer) and needs glibc 2.38
and GCC 13's libstdc++ or newer (Ubuntu 24.04, Debian 13, Fedora 39 and
newer releases, and rolling distributions), on any x86-64 processor. The
game program it builds needs SDL 3.2 or newer from the system, which
Ubuntu 24.04 does not have yet.

The AppImage updates itself. When it starts it asks GitHub for this
repository's newest release; when that is newer, a notice at the top of the
window says so, with **What's New** (the release's page) and **Update**,
and the button left of Check Again is highlighted (that button also looks
for an update any time). Update downloads the new AppImage (with curl or
wget), checks it, puts it in place of the AppImage you started and opens it. A release is tagged `v<version>` (`v0.1.1`) with
the AppImage and the Windows launcher attached, both built with that version as `TTT2_LAUNCHER_VERSION` in
`launcher/builder/CMakeLists.txt`: before it replaces anything each launcher
checks that the new one says it is that version (`ttt2-launcher --version`).

Both launchers also say when `main` has changes their build lacks, before a
release brings them: each knows the commit it was built from (Git's, when it is
built; the Windows `.exe` keeps it in its files) and asks GitHub, with the release,
what `main` has beyond it (`tools/characters/launcher.py main`). The notice then
says how many changes and the newest one, with **What's New** (GitHub's
comparison); fighters `main` gives a newer pack show **Newer on main**, and
fighters only `main` has are named. All of it comes with the next release. A
build of commits never pushed shows nothing.

The Windows launcher of a release is made on Linux too, from a commit:

```bash
python3 launcher/windows/make_launcher_exe.py Ultimate_Launcher-x86_64.exe
```

It is `launcher/windows/entry.cpp` compiled with MinGW-w64
(`x86_64-w64-mingw32-g++` and its `windres`; `--cxx` names another), with the
project's tracked files (nothing of the game) as a resource of the program, and
its icon and version details (the icon needs `rsvg-convert`). `--stub` takes a
launcher CMake built for Windows instead and appends the files to it (tests).
Made on a branch other than `main`, it is a test build, which updates its files
from that branch (above); a release is made on `main`.
The files are a resource rather than data after the program because virus
scanners' guesses take that for a dropper's payload less often; the `.exe` is
not code-signed, so Windows Defender may still flag a new build by guess
(`…!ml`): report it to Microsoft as a false positive. Attach it to the release
as it is named here: each launcher takes its own file from a release
(`.AppImage`, `.exe`).

## Playing

Run the game straight from its archive (or from a game folder):

```bash
build/ttt2 "/path/to/TEKKEN TAG 2 Wii U EDITION (EU).wua"
```

Or install it: choose the archive and the install folder in file dialogs, or
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
starts fullscreen is a setting, below).

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

These are the defaults: the launcher's **Settings** (the gear next to Play)
change them, at once, also while the game runs, and **Restore Defaults**
there brings them back. They are kept in `~/.config/ttt2/keyboard.ini`
(`$XDG_CONFIG_HOME/ttt2/`), one `input = key` per line, which can be edited
by hand too ([its format](docs/ARCHITECTURE.md#running-the-port)); F11,
Escape and the Windows keys cannot be given to a button, and the game prints
what it read when it starts.

Gamepads work through SDL by button position, as on the Wii U: the right
face button is A, the bottom one B, the top one X and the left one Y, and
fights use them that way. In menus the bottom button (B, by default K on the
keyboard) confirms and the right one goes back, except with a Nintendo
controller, which confirms with its A as on the Wii U. The icons follow the
last controller used (the keyboard counts as a neutral one).

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

In Practice, 3 (left kick: by default K, or a gamepad's bottom button) and
− (Select: Backspace) pressed together, in either order, put both fighters
back where the stage put them, standing, as Tekken 8's position reset does;
the pause menu's POSITION SETTINGS apply as at the start of training. 3 is
whichever button the game's Controller Setup gives left kick. − alone still
reaches the game, a few frames later than before.

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

2P's panel has a red tint.

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
are on, and are not shown in the pause menu.

COMMAND HISTORY (in the pause menu's ADVANCED SETTINGS → HUD Information)
shows the player's inputs as Tekken 8's Practice does: a column on the left
side of the screen, the newest input on top, each row a direction (as the
fighter faces) and the buttons held, drawn with the game's own icons, and
the number of frames it was held. It replaces the game's command history
bar along the bottom.

The launcher's **Settings** also choose how the game starts: fullscreen or
in a window, the resolution it draws at (Automatic, the default, is enough
to cover your main display), whether it shows 120 frames per second on
displays of 100 Hz and more (on by default) and whether fighters wait the
Wii U game's two frames before acting on a button (off by default). They
are kept in `~/.config/ttt2/display.ini` (`$XDG_CONFIG_HOME/ttt2/`), which
can be edited by hand too:

```ini
fullscreen = no             # yes or no
resolution = auto           # auto, 1280x720, 1920x1080, 2560x1440, 3840x2160 or 5120x2880
interpolation = yes         # yes or no (no: 60 frames per second)
input_delay = no            # yes: two frames between a button press and the game acting on it, as on the Wii U
```

The game reads it when it starts, so a change applies the next time. The
window opens at the chosen resolution when that fits on the desktop,
otherwise smaller (the picture is scaled to the window or the screen).
Uninstalling keeps it, as it keeps `keyboard.ini`. The environment
variables below win over it.

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
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#running-the-port).

## Adding fighters

The fighters of Tekken 7 that Tekken Tag Tournament 2 does not have can join
the roster beside its own (no fighter is replaced): Kazumi Mishima, Lucky
Chloe, Eliza, Claudio Serafino, Akuma, Gigas, Josie Rizal, Katarina Alves,
Master Raven, Shaheen, Fahkumram, Leroy Smith, Lidia Sobieska, Kunimitsu II,
Negan, Geese Howard and Noctis. Each gets a cell of its own on the select
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
  Python 3 with numpy and Pillow.

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
(`--movesets FOLDER`).

The fighters' names for the importer: `kazumi`, `chloe`, `eliza`, `claudio`,
`akuma`, `gigas`, `josie`, `katarina`, `master_raven`, `shaheen`,
`fahkumram`, `leroy`, `lidia`, `kunimitsu2`, `negan`, `geese`, `noctis` (one or several; each
takes about a minute, and what they share is made once at the end). The packs
go to `~/.local/share/ttt2/characters/` (or `$XDG_DATA_HOME/ttt2/characters/`:
a folder per fighter, and `shared/`, the title's pictures, colours and name
calls the added fighters share; `$TTT2_CHARACTERS` picks another folder).
`--remove NAME...` removes fighters again; the others keep their cells.
Each pack names the pack format it was made in. The game loads only packs of
its own format and skips older and newer ones (it says so on its console):
add an older pack's fighter again (the launcher offers it), and it comes back
in its own cell. A pack with no format line counts as format 1, unless it has a
`keys/` folder of its own: those are the earliest packs (made before
`shared/` existed), which must be added again.
**The packs hold Namco's assets: keep them to yourself and never upload or
share them.** The importer refuses to write them inside this repository, and
`.gitignore` keeps the games' file types out of commits.

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

### Bound moves

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

## How it works

- `recomp/`: `cafe-recomp` loads the RPX, finds all 205,200 function entry
  points and writes the 79,564 reachable ones as C++ functions (`--all`
  writes every one). Guest calls are C++ calls; indirect calls go through an
  address table.
- `runtime/src/os/`: the Cafe OS libraries the game imports (threads,
  synchronisation, memory, file system, saves, input, sound mixing), written
  natively.
- `runtime/src/gx2/` and `runtime/src/gpu/`: GX2 writes real GPU command
  buffers, which a command processor executes; the Vulkan renderer
  (`runtime/src/gpu/vulkan/`) translates the GPU's shaders to SPIR-V
  (`runtime/src/latte/`), interpolates frames and paces presentation.
- `runtime/src/title/`: what this game shows differently on a computer: the
  menu buttons, the icon sets, texts and the title screen, made at start-up
  from the game's archives (their format is described in
  [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#presentation-on-a-computer)),
  and the added fighters from their character packs.
- `tools/characters/`: the importer that makes a character pack from the
  player's own Tekken 7 and Tekken Tag Tournament 2
  ([`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#added-fighters)).
- `tests/`: a memory-model test, tests of reading split archives and of the
  game's file formats and the icons and texts made from them, and
  differential tests that run every instruction form the game uses against
  Dolphin's PowerPC interpreter.

### Changing the game

A generated function `sub_<address>` can be replaced by defining it in a
`.cpp` file added to the `ttt2` target (`target_sources(ttt2 PRIVATE ...)` in
`CMakeLists.txt`); every call, direct or through a function pointer, then
reaches the replacement, and `sub_<address>_orig` is still the original:

```cpp
#include "cafe/ppc_ops.h"

PPC_FUNC(sub_0123ABCD_orig);
PPC_FUNC(sub_0123ABCD) {
    // ... before
    sub_0123ABCD_orig(ctx, base);
    // ... after
}
```

## Tests

```bash
cmake --build build      # also builds the tests
ctest --test-dir build
```

runs `memory_model_test`, `wua_layers_test`, `title_test` and, with Python 3,
numpy and Pillow, `character_import_test` (the importer's formats). The
differential tests (`semantics_test`, `control_flow_test`) also need `fmt`,
the game's `Tekken.rpx` (by default
`local/wua/000500001010f800_v16/code/Tekken.rpx`; otherwise configure with
`-DTTT2_RPX=<path>`), and a partial checkout of Dolphin:

```bash
git clone --filter=blob:none --no-checkout https://github.com/dolphin-emu/dolphin.git third_party/ref/dolphin
git -C third_party/ref/dolphin sparse-checkout set --no-cone \
  /Source/Core/Core/PowerPC/Interpreter/ /Source/Core/Core/PowerPC/Gekko.h \
  /Source/Core/Core/PowerPC/PowerPC.h '/Source/Core/Core/PowerPC/ConditionRegister.*' \
  /Source/Core/Common/BitField.h /Source/Core/Common/BitUtils.h /Source/Core/Common/CommonTypes.h \
  '/Source/Core/Common/FloatUtils.*' /Source/Core/Common/Inline.h /Source/Core/Common/Swap.h
git -C third_party/ref/dolphin checkout 771fb154059c5812d6a715a23226249cc42877a2
cmake -B build && cmake --build build && ctest --test-dir build
```

They build Dolphin's interpreter (GPL-2.0 or later) into the test programs;
nothing of Dolphin is stored in this repository.

## License

This repository's code is under the [MIT License](LICENSE). It does not cover
the game, or anything generated from it.

Fetched by `tools/setup_deps.py`, under their own licenses:
[ZArchive](https://github.com/Exzap/ZArchive) (MIT-0) and AMD's address
library ([decaf-emu/addrlib](https://github.com/decaf-emu/addrlib), MIT,
built into the `ttt2` program). The port also links SDL3 (zlib), shaderc
(Apache-2.0), the Vulkan loader (Apache-2.0), OpenSSL (Apache-2.0), zstd
(BSD) and zlib.

## Acknowledgements

- [Cemu](https://github.com/cemu-project/Cemu) and
  [decaf-emu](https://github.com/decaf-emu/decaf-emu), whose reverse
  engineering of the Wii U's system libraries and GPU documented much of the
  behaviour reimplemented here (structure layouts, register values, formats,
  GX2's surface layout rules). This repository's code is its own.
- [Dolphin](https://github.com/dolphin-emu/dolphin), whose hardware-tested
  PowerPC interpreter is the reference the instruction tests compare
  against, and whose hardware research measured the processor's estimate
  tables.
- [XenonRecomp](https://github.com/hedge-dev/XenonRecomp) and
  [N64Recomp](https://github.com/N64Recomp/N64Recomp), for showing how far
  function-level static recompilation can go.
- [TKMovesets2](https://github.com/Kiloutre/TKMovesets) and
  [TekkenMovesetExtractor](https://github.com/Kiloutre/TekkenMovesetExtractor),
  whose research documented the Tekken 7 and TTT2 moveset layouts, their
  animations and what their requirement and property ids mean, which the
  character importer builds on (its movesets are in TKMovesets2's .tkmvst
  layout, which it can also read); the Tekken 7 Bound Mod, whose choice of
  bound moves the added Tekken 7 fighters have;
  [UE Viewer](https://github.com/gildor2/UEViewer) and
  [CUE4Parse](https://github.com/FabianFG/CUE4Parse), for Tekken 7's Unreal
  Engine 4.14 packages. The importer's code is its own.
- [Excentrian](https://github.com/Excentrian), who designed the title
  screen's "ULTIMATE EDITION" subtitle
  ([#9](https://github.com/Petexy/Tekken-Tag-2-Ultimate-Edition/issues/9)):
  the port letters it after that design, its M and A from Excentrian's
  outlines.
