# Golden Fist Launcher

Golden Fist Launcher (called Ultimate Launcher up to 0.8.0) installs, updates and starts Tekken Tag Tournament 2 and
adds fighters to it, in one window, on Linux and on Windows. This page describes its screens, what it needs on your PC,
how it updates itself, and the Windows launcher's own parts. How to build it yourself: [Building from
source](BUILDING.md#building-the-launcher).

## Contents

- [The three screens](#the-three-screens)
- [On Linux](#on-linux)
  - [Home](#home)
  - [Settings](#settings)
  - [Fighters](#fighters)
  - [What it needs](#what-it-needs)
  - [The AppImage](#the-appimage)
  - [Updates](#updates)
- [On Windows](#on-windows)
  - [Starting from a release](#starting-from-a-release)
  - [Updates on Windows](#updates-on-windows)
  - [Test builds](#test-builds)
  - [Starting from a downloaded project ZIP](#starting-from-a-downloaded-project-zip)
  - [The first setup](#the-first-setup)
  - [The launcher Set Up Game builds](#the-launcher-set-up-game-builds)
  - [Windows' own parts](#windows-own-parts)
  - [Folders and logs](#folders-and-logs)
- [Languages](#languages)
- [Known limits](#known-limits)

## The three screens

`ttt2-launcher` (**Golden Fist Launcher**) does the installing and
the adding of fighters in a window, without a terminal, with the keyboard, the
mouse or a controller, on three screens: **Home**, **Fighters** and **Settings**.

Nothing of the game is in the launcher: the game program is built on your PC
by the launcher's kit (`build/launcher/kit`: `ttt2-build`, `cafe-recomp` and
the runtime) with your C++ compiler, in a few minutes.

## On Linux

### Home

**Install** on Home takes your `.wua` and a folder (chosen in the launcher's own
file browser, or the system's picker), checks the PC, builds the game program for it from
the archive and installs the game with its menu entry, as `ttt2 --install`
does; then Home has **Play** and **Uninstall** (saves and added characters are kept unless you
tick them; of a save folder you chose with `TTT2_SAVE_DIR`, only the game's
own saves go). While anything can be updated, the big button is **UPDATE** in Play's
place: it brings the launcher (the AppImage), the game program (when the launcher's version differs from
the program's) and the added fighters up to date, one after another; Play stays below it, unless
the game is of an older version than the launcher. While the game runs, however it was started, Play, UPDATE and
Uninstall wait for it to end. What the game writes when Play starts it goes
to `~/.cache/ttt2/game.log` (of its last start); when it stops with an error,
its last lines are shown on Home: attach that file to a report.

### Settings

**Settings** has
the name the game shows for you in place of Player (typed on the keyboard, or with a controller on keys the
launcher shows), the language the game shows its texts and menus in (English, French, German, Italian, Spanish or
Russian: those the European Wii U game has; or Polish, the port's own translation), whether the game starts fullscreen, the resolution it draws at, its 120
frames per second, whether fighters wait the Wii U version's two frames
before acting on a button, whether its shaders are compiled in the background and prepared before it starts,
its keyboard keys ([Playing](PLAYING.md#keyboard)), and the launcher's own language ([Languages](#languages)), sounds,
motion, button prompts and text size.
Where the game keeps these settings: [Settings](PLAYING.md#settings).

### Fighters

**Fighters** shows where Steam has Tekken 7 and Tekken 8, or why one cannot be used, and a group for each game's
fighters (the installed game's first), with **Add** per fighter and **Add All**; each game's DLC fighters are in a
group of their own, with those your Steam account owns and **Add All Owned**. Above the groups, one **Add All Owned**
adds every fighter that can be added now from both games: their own and the DLC fighters your account owns. Tekken
8's fighters are added without Tekken 7 or any of its fighters. **Remove** takes one out again. A
Tekken 8 fighter whose moves could not be saved from Tekken 8 (a game update its helper does not know yet, or
nothing to run it hidden) is added with Heihachi's moves, says so and why, and is offered as an update once
their own can be saved. What all added fighters share is made from each one's own game, so while one game is
uninstalled its fighters stay in the game but no other can be added: the launcher says so, and offers to
remove that game's fighters all at once. What adding a fighter does and needs: [Adding fighters](ADDING_FIGHTERS.md).

### What it needs

Building the game program needs Clang (or
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

### The AppImage

The launcher in the AppImage has SDL 3 built in and needs nothing of the system but
glibc 2.39 and GCC 14's libstdc++ or newer (Ubuntu 24.04, Debian 13, Fedora
40 and newer releases, and rolling distributions), on any x86-64 processor;
it opens the display's and sound's libraries when it starts. The
game program it builds needs SDL 3.2 or newer from the system, which
Ubuntu 24.04 does not have yet. How the AppImage is made: [Building from source](BUILDING.md#the-appimage).

### Updates

The AppImage updates itself. When it starts, and when its window is back in
front after six hours, it asks GitHub for this repository's newest release; when
that is newer, a notice on Home says so, with **What's New** (the release's
page), and Home's **UPDATE** gets it before the game program and the fighters
(before the game is installed, the notice's own **Update** does). It downloads
the new AppImage (with curl or wget), checks it, puts it in place of the
AppImage you started and opens it; a new one that ends before it shows its
window is replaced by the old one again. Each launcher checks that a new one is the release's version before it
replaces anything ([Releases](BUILDING.md#releases)).

Both launchers also know what `main` has that their build lacks, before a
release brings it: each knows the commit it was built from (Git's, when it is
built; the Windows `.exe` keeps it in its files) and asks GitHub
what `main` has beyond it (`tools/characters/launcher.py main`). Fighters `main`
gives a newer pack show **Newer on main**; it
comes with the next release. (No notice counts `main`'s changes: a
release's own pull request is merged after its build.) A build of commits never
pushed shows nothing.

## On Windows

The Windows launcher is the same program as the Linux one ([On Linux](#on-linux)), with the same
three screens: **Home** (Play, or UPDATE while the launcher, the game program or
an added fighter can be updated), **Fighters** (the characters as the shared
importer finds them: Tekken 7, Tekken 8 and Steam; Add, Update and Remove per
fighter, Add All, the DLC with what Steam says you own) and **Settings**
(the name the game shows for you, the language of its texts, fullscreen, resolution, 120 fps, input delay, shaders,
and the keyboard's keys chosen by pressing them, as the Linux launcher writes keyboard.ini). A task shows
its progress and Cancel at the bottom of the window, an update on Home.

### Starting from a release

For Windows 10/11, x64:

1. Download `Golden_Fist_Launcher-x86_64.exe` from the newest release and put it
   in a folder of yours (not Program Files: it replaces itself when it updates).
2. Double-click it. The first start unpacks the launcher's files into
   `%LOCALAPPDATA%\TTT2Ultimate\launcher` and gets its private Python ready
   in the launcher's window (**Getting the launcher ready**); later starts open
   the launcher at once. (When that
   path has letters beyond plain ASCII, as a user name such as José gives it,
   the files go to `%PUBLIC%\TTT2Ultimate\launcher` instead: see
   [the project ZIP's start](#starting-from-a-downloaded-project-zip) for why such letters break a build.)
3. Continue with **Set Up** as in [step 3 of the project ZIP's start](#starting-from-a-downloaded-project-zip). The tools, the build
   and the generated code stay in that folder too (plan its 30 GB on that drive).

The `.exe` is not code-signed, so Windows Defender may flag a new release by guess: see
[The Windows launcher](BUILDING.md#the-windows-launcher).

### Updates on Windows

The release launcher updates itself. With a newer release known, a notice on
**Home** says so, with **What's New** (the release's page), and Home's big
button is **UPDATE**: it updates the launcher, which then goes on with the game
program, built again on this PC with the new version's changes, and with your
added fighters. (Before the game is set up, the notice's own **Update** updates
the launcher alone.) The launcher's part downloads the new `.exe` beside the one
you started, checks it (its size, GitHub's SHA-256, that it is a 64-bit Windows
launcher and its files are of that version), puts it in that one's place and
opens it: it unpacks its files over the old ones, keeping everything else there.
Anything failing, or Cancel, leaves the `.exe` as it was. Fighters `main` gives
a newer pack show **Newer on main**, as in the Linux launcher ([Updates](#updates)).

When Set Up Game or UPDATE fails, the launcher names the checks that failed or
the build's first error; **More** on Home opens the whole log (**Open Latest
Log**).

### Test builds

A test build (an `.exe` made on a branch other than `main`, for testers) follows
its branch instead: when the branch has newer commits, the notice says so with
**Update**, which downloads the newest commit's files from GitHub, puts them in
place of the ones the `.exe` unpacked and opens the launcher again: a fix pushed
to the branch reaches testers without a new `.exe`. Changes to the launcher's
own program need a new test build; Update then says so and changes nothing. A
game built from older files then gets **UPDATE** on Home. One stopped half-way
is unpacked again from the `.exe` when it is next started.

### Starting from a downloaded project ZIP

For Windows 10/11, x64, without the release `.exe`:

1. Download this branch as a ZIP and **Extract All** into a writable folder
   whose path has only plain letters and is short, such as `C:\TTT2`: not in
   OneDrive (30 GB would be synced). The first start and Set Up Game refuse
   a path with letters such as à: CMake runs some build steps through batch
   files it writes in UTF-8, which `cmd.exe` reads in the console's code
   page, so such a letter turns into others and the step finds no folder.
2. Double-click **Start Golden Fist Launcher.cmd** in that folder. The first start
   downloads and verifies a private Python runtime, then builds the launcher
   from the folder's files, once (a few minutes; a small window shows how far
   it is): with the C compiler, CMake, Ninja and SDL 3 that Set Up Game uses
   (SHA-256 or version pinned, downloaded where missing into `local\` and
   `third_party\windows\` as Set Up Game does, and shared with it), in
   `%LOCALAPPDATA%\TTT2Ultimate\launcher-build`. Later
   starts open the launcher at once; it is built again only when its files
   change. When it cannot be built, that window says why, with **Open log**
   (`local\launcher-build.log`) and **Try again**; the release's
   `Golden_Fist_Launcher-x86_64.exe` needs no build. No Python installation,
   Git installation, terminal commands or second project download are needed.
3. Choose **Set Up** on Home, then your own European Wii U Tekken Tag Tournament 2 `.wua` containing
   update v16 and an installation folder in the launcher's file browser (Windows'
   own pickers are one button away there), and confirm with **Set Up Game**.
4. Leave setup running while it downloads missing tools, prepares libraries,
   checks your game executable, builds and installs the Windows game.
5. Choose **Play** when setup completes. To add fighters, open Steam, close Tekken 7 and Tekken 8,
   open **Fighters**, and choose a fighter and **Add**, or **Add All**. Tekken 8's
   fighters require Tekken 8.

### The first setup

The first setup needs internet, a Vulkan-capable graphics driver, an x86-64-v3
CPU and substantial free disk space for the tools, generated build and game.
It can take a while; keep the extracted project folder for future updates.
Downloads are private to ignored `local/` folders. Python, LLVM-MinGW and MinGit
archives are SHA-256 pinned; Python packages are version pinned. Existing
project files are reused; the game and its assets are never downloaded.
Setup logs remain under the selected data folder. The game archive is kept.

### The launcher Set Up Game builds

Set Up Game also builds the launcher there: `build-windows-tools/launcher/ttt2-launcher.exe`
(SDL3.dll beside it), from the same sources as the release `.exe` and the program
the ZIP's first start makes (those are built with other compilers and C++ libraries:
the release `.exe` with MinGW-w64's GCC, Set Up Game and the ZIP with LLVM-MinGW).
The launcher of releases up to 0.8.0 that an older Set Up Game left at
`build-windows-tools/ttt2-launcher.exe` is removed by the next Set Up Game. The ZIP startup path obtains a private Python automatically (its Tk
draws only the first start's progress window); developer launches can also use an
installed Python 3 (`python launcher/windows/main.py` builds and starts the
launcher as the ZIP's first start does). Setup obtains numpy and Pillow. Set
`TTT2_PYTHON` to a Python executable to override automatic discovery.

### Windows' own parts

Windows'
own parts stay: Set Up, **More** on Home (Build / Rebuild, Install from Wii U
Source, Update Installed Game, Set Up Again…, the logs) and **Folders** in
Settings. It calls the existing Windows
build scripts, native installer, and shared character importer, and needs nothing
beyond the private Python it gets itself. Set Up Game prepares the build tools automatically from the extracted project.
Keep the project folder for rebuilds. The compiled launcher executable can also
be opened from its build folder after setup.

### Folders and logs

It detects the existing development archive, extracted title, fighter packs,
saves, and CMake toolchain. To change them, use **Settings** > **Folders**
(**Browse…** or **Default** for each), then **Save Folders**.
Development configuration is saved in ignored `local/windows-launcher.json`;
other layouts use `%LOCALAPPDATA%/TTT2Ultimate/launcher.json`. The data folder must
end in `TTT2Ultimate` so runtime settings and launcher settings use the same place.
Explicit fighter/save paths are passed to both the game and importer. Packs
marked **Update ready** still load: this compares revisions from the shared
importer and never automatically rebuilds anything.

Task/game logs are saved under the selected data folder's `logs/` directory;
the launcher's own messages are in `local/launcher.log` of its files' folder (the
release's in `%LOCALAPPDATA%`, the project ZIP's), or beside the executable when
it was not started with one. The window does not close while a task runs.
Import cancellation requests cleanup and
keeps completed extraction data. Only the release `.exe` updates itself (a
project ZIP is updated as a whole); the Linux uninstall is not part of the
Windows launcher.

## Languages

The launcher shows its texts in English, French, German, Italian, Spanish, Russian or Polish: **Settings > Launcher >
Language**, each named in its own language. **System** (the default) is your system's language when the launcher has
it, else English (Linux: `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`, in that order; Windows: the display language).
It changes at once and is kept in `launcher.ini` (`language=`, beside `display.ini`). The game's own language is the
other setting, Settings > Game > Language. What the launcher writes to its logs and to a terminal stays English, and
so do messages the system or another program gives it (a folder that cannot be read, a compiler's error), names, and
key names such as Enter and Esc.

Every text has a key and its English, which is the source: the English is in the code where the text is used, as
`tr("home.play", "Play")` or, for a text that changes with a number, `trn("fighters.added", n, "{n} fighter added",
"{n} fighters added")`. The Python programs the launcher starts (the Windows setup and updates, the importer's
progress lines) do the same with `launcher/i18n/launcher_texts.py`, in the language the launcher passes them
(`TTT2_TEXT_LANGUAGE`). `launcher/i18n/en.txt` lists every key with its English; it is made from the code:

```sh
python3 launcher/i18n/extract.py            # en.txt anew, after a text was added or changed
python3 launcher/i18n/extract.py --check    # what the tests run: en.txt is current, every catalog fits it
python3 launcher/i18n/extract.py --json     # every text with where it is used
```

Each other language is a catalog, `launcher/i18n/<code>.txt` (UTF-8), built into the launcher:

```
# comments and blank lines
home.play = Spielen
fighters.added[one] = {n} Kämpfer hinzugefügt
fighters.added[other] = {n} Kämpfer hinzugefügt
```

One text per line: its key, `=`, the text. `{name}` is a value the launcher puts in (a number, a name, a folder),
by name and in any order the sentence needs; `{{` and `}}` are braces; `\n` is a new line, `\\` a backslash and
`\s` a space at a text's start or end. A text that changes with a number has one line per plural form the
language has, as CLDR counts them: English and German `one` and `other`; French, Italian and Spanish `one`, `many`
and `other`; Russian and Polish `one`, `few`, `many` and `other` (`one` is also 21, 31 ... in Russian, so it says
`{n}` too). A key a catalog lacks shows in English. The check fails on a key `en.txt` does not have, on other
placeholders than the English, on a plural text without each of the language's forms, and on a line it cannot read.

To try a catalog without building: `TTT2_LAUNCHER_I18N_DIR=<folder with code.txt files>` makes the launcher read the
catalogs there instead of its own, and `TTT2_LAUNCHER_LANGUAGE=<code>` starts it in that language without changing
Settings. `TTT2_LAUNCHER_LANGUAGE=qps` is the test language: every English text marked with brackets, its letters
accented and a third longer, to see on the screen a text that does not go through the catalog (it shows plain) or
does not fit.

To add a language: its code and own name in `kLanguages` (`launcher/core/i18n.h`; the game's languages are in
`runtime/src/host/game_settings.h`), its plural rules in `plural_category()` (`launcher/core/i18n.cpp`),
`launcher_texts.py` and `extract.py`'s `PLURALS` and `LANGUAGES`, an empty `launcher/i18n/<code>.txt` in
`TTT2_LAUNCHER_CATALOGS` (`launcher/core/CMakeLists.txt`: the catalogs built in), and the letters it needs in the
fonts: Barlow has Latin letters, Fira Sans Cyrillic ([fonts](../launcher/ui/fonts/README.md)); a script neither has
needs a font of its own beside them.

## Known limits

The launcher draws text without shaping or bidirectional ordering: every character is drawn on its own, left to
right. Names in scripts that need either (Arabic, Hebrew, Devanagari ...), such as a folder's, still measure and
draw without breaking the rest of a line, but not as those scripts are written.
