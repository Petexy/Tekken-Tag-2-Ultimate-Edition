# Building from source

Players don't need any of this: [Golden Fist Launcher](LAUNCHER.md) builds the game program on their PC by itself.
This page is for working on the project: what a build needs, how to build the game program and the launcher, how
the release programs are made, and how to run the tests.

## Contents

- [Requirements](#requirements)
- [Building the game program](#building-the-game-program)
- [Building the launcher](#building-the-launcher)
- [The AppImage](#the-appimage)
- [The Windows launcher](#the-windows-launcher)
- [Releases](#releases)
- [Tests](#tests)

## Requirements

- Linux on x86-64 with AVX2 and FMA (x86-64-v3: Intel Haswell, AMD Excavator
  or newer).
- A Vulkan 1.3 GPU and driver with `VK_EXT_external_memory_host` and push
  descriptors (current AMD, Intel and NVIDIA drivers).
- To build: Git, CMake 3.20+, Ninja, Clang (or GCC 15+), Python 3, and the
  development files of SDL 3.2 or newer, shaderc, the Vulkan loader, Vulkan
  headers recent enough to define `VK_KHR_present_wait2` (mid-2025 or
  newer), OpenSSL 3, zstd and zlib; for the launcher MinGW too (optional: the
  Tekken 7 and Tekken 8 helpers are then built in). The launcher draws its own
  window with SDL 3, without GTK.
- For the launcher's release programs (the AppImage, the Windows `.exe`):
  SDL 3's own source at its pinned revision, built into them
  (`python3 tools/setup_deps.py --launcher`), with the development files of
  what SDL can use on a player's PC (X11, Wayland, libdecor, PipeWire,
  PulseAudio, ALSA, udev, D-Bus: opened when the launcher starts, never
  linked), LLD and `mksquashfs` for the AppImage, and MinGW-w64 for the
  `.exe`.

On Arch Linux:

```bash
sudo pacman -S --needed base-devel git cmake ninja clang python zstd zlib openssl vulkan-headers vulkan-icd-loader sdl3 shaderc mingw-w64-gcc
# and for the launcher's release programs (openssl-3: the OpenSSL the players' systems have, for the AppImage's kit)
sudo pacman -S --needed lld squashfs-tools openssl-3 libx11 libxext libxrandr libxcursor libxfixes libxi libxss libxtst libxkbcommon wayland wayland-protocols libdecor libpulse pipewire alsa-lib systemd-libs dbus mesa
```

Other distributions package the same libraries under similar names; older
releases such as Ubuntu 24.04 and Debian 12 ship SDL and Vulkan headers that
are too old.

## Building the game program

You need your own copy of the game: [which one](PLAYING.md#your-copy-of-the-game).

```bash
git clone https://github.com/Petexy/Golden-Fist-Launcher.git && cd Golden-Fist-Launcher
python3 tools/setup_deps.py                      # ZArchive and AMD's addrlib, at pinned revisions
# (python3 tools/setup_deps.py --launcher: SDL 3's source too, for the launcher's release programs only)

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

How to run and install the program you built: [Playing](PLAYING.md#starting-the-game-without-the-launcher).

## Building the launcher

```bash
cmake --build build --target ttt2-launcher ttt2_kit
build/launcher/ttt2-launcher
```

What the launcher does and what it needs on a player's PC: [Golden Fist Launcher](LAUNCHER.md).

## The AppImage

To make an AppImage of the launcher (the launcher, its kit and the character
importer; nothing of the game):

```bash
python3 tools/setup_deps.py --launcher           # SDL 3's source, built into the launcher
launcher/appimage/make_appimage.sh Golden_Fist_Launcher-x86_64.AppImage build-appimage
```

It builds in a folder of its own (here `build-appimage`; Git ignores it and
the AppImage), needs LLD and `mksquashfs`,
and downloads the AppImage runtime once (`--runtime-cache DIR` says where).
What the AppImage needs on a player's PC: [The AppImage](LAUNCHER.md#the-appimage).

## The Windows launcher

The Windows launcher of a release is made on Linux too, from a commit:

```bash
python3 launcher/windows/make_launcher_exe.py Golden_Fist_Launcher-x86_64.exe
```

It is the launcher's own program cross-built for Windows by CMake with
MinGW-w64 (`cmake/toolchain-mingw64.cmake`; it needs CMake, Ninja and SDL 3's
source: `python3 tools/setup_deps.py --launcher`), SDL 3 built in, with the
project's tracked files (nothing of the game; the README's pictures in
`docs/images/` stay out) as a resource of the program, and
its icon and version details (the icon needs `rsvg-convert`); the same commit
makes the same bytes. `--cxx COMPILER` makes the Python launcher's `.exe` of
0.4.0 to 0.8.0 instead (`launcher/windows/entry.cpp`), and `--stub` appends the
files to a launcher CMake built for Windows already (tests).
Made on a branch other than `main`, it is a test build, which updates its files
from that branch ([test builds](LAUNCHER.md#test-builds)); a release is made on `main`.
The files are a resource rather than data after the program because virus
scanners' guesses take that for a dropper's payload less often; the `.exe` is
not code-signed, so Windows Defender may still flag a new build by guess
(`…!ml`): report it to Microsoft as a false positive. Attach it to the release
as it is named here: each launcher takes its own file from a release
(`.AppImage`, `.exe`).

## Releases

A release is tagged `v<version>` (`v0.1.1`) with
the AppImage and the Windows launcher attached, both built with that version as `TTT2_LAUNCHER_VERSION` in
`launcher/builder/CMakeLists.txt`: before it replaces anything each launcher
checks that the new one is that version (the AppImage by its `--version`, the
`.exe` by the files in it). How the launchers update themselves: [Updates](LAUNCHER.md#updates).

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
