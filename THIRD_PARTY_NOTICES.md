# Third-party notices

This repository's own code is under the MIT License (`LICENSE`). Parts of the launcher and of the game program are made
with the works below, under their own licenses; the files committed here keep their license texts unchanged. The
license texts of what is built into the release programs are in `licenses/` and beside the fonts, as their authors
wrote them. `Golden_Fist_Launcher-x86_64.exe` carries all files of this repository; the AppImage has this file,
`LICENSE` and those texts in `usr/share/licenses/ttt2-launcher/`, at the same paths (`--appimage-extract` unpacks it).

## In the repository

| Work | Where | License | Upstream (pinned commit) |
|---|---|---|---|
| stb_truetype.h, stb_image_write.h (Sean Barrett) | `launcher/ui/third_party/` | public domain or MIT (the reader's choice; text at the end of each file and in `licenses/stb.txt`) | https://github.com/nothings/stb (`6b5799bae8a1fe3792691ef4b72ae26434c3e799`) |
| nanosvg.h, nanosvgrast.h (Mikko Mononen) | `launcher/ui/third_party/` | zlib (text at the start of each file and in `licenses/nanosvg.txt`) | https://github.com/memononen/nanosvg (`239e102ec2c691f2902e20ace2ed36ee4a35cfe6`) |
| Barlow, Barlow Condensed (The Barlow Project Authors) | `launcher/ui/fonts/Barlow`, `launcher/ui/fonts/BarlowCondensed` | SIL Open Font License 1.1 (`OFL.txt` beside the fonts) | https://github.com/jpt/barlow (`dc2940e2e04ef4ec96c07e23e0f02aefbddd343b`) |
| JetBrains Mono (The JetBrains Mono Project Authors) | `launcher/ui/fonts/JetBrainsMono` | SIL Open Font License 1.1 (`OFL.txt` beside the fonts) | https://github.com/JetBrains/JetBrainsMono (`19371302b95d218af43299bce79ddbddd0bc364d`) |

The fonts and these libraries are built into the launcher program. File checksums: `launcher/ui/third_party/README.md`,
`launcher/ui/fonts/README.md`.

## SDL 3 in the release programs

The launcher in the AppImage and `Golden_Fist_Launcher-x86_64.exe` have SDL 3.4.18 built in
(`dependencies.launcher.lock.json`). SDL (Sam Lantinga and contributors) is under the zlib license
(`licenses/SDL/LICENSE.txt`); so are most parts others wrote for it, under their own names in its source files
(Valve's controller code, Gareth McCaughan's qsort, Andreas Schiffler's SDL_rotate.c and more). These parts of it have
licenses of their own:

| Part of SDL | License | Text | In |
|---|---|---|---|
| yuv2rgb (Adrien Descamps) | BSD 3-Clause | `licenses/SDL/yuv2rgb.txt` | both |
| HIDAPI (Alan Ott, Signal 11 Software; the libusb/hidapi team) | the original HIDAPI license (one of the three its user chooses from) | `licenses/SDL/hidapi.txt` | both |
| stb_image.h (Sean Barrett) | public domain or MIT (the reader's choice) | `licenses/stb.txt` | both |
| miniz.h (Rich Geldreich); the bsearch, strtok, CRC, MurmurHash, date and half-float code; the debug text font | public domain or CC0 | none needed | both |
| imKStoUCS.c (Jamey Sharp, Josh Triplett, Red Hat, Oracle) | MIT | `licenses/SDL/imKStoUCS.txt` | the AppImage |
| edid-parse.c (Red Hat) | MIT | `licenses/SDL/edid.txt` | the AppImage |
| xsettings-client.c (Red Hat, Igalia) | permission notice (HPND) | `licenses/SDL/xsettings-client.txt` | the AppImage |
| xdg-user-dirs' lookup functions in the Unix SDL_sysfilesystem.c (Red Hat) | MIT | `licenses/SDL/xdg-user-dirs.txt` | the AppImage |
| code made from the Wayland protocol files (their authors) | MIT (text-input: HPND) | `licenses/SDL/wayland-protocols.txt` (each file's own notice; pointer-gestures has none) | the AppImage |

## Also in the AppImage

| Work | Where | License | Text |
|---|---|---|---|
| ZArchive (Exzap) | the kit: the builder, and the game program built with it | MIT-0 (its sha_256.c, from amosnier/sha-2: Unlicense or 0BSD) | `licenses/ZArchive.txt` |
| AMD's address library (Advanced Micro Devices; decaf-emu/addrlib) | the kit: the game program built with it | MIT | `licenses/addrlib.txt` |
| MinGW-w64's runtime | the kit's `t7helper.exe` and `t8helper.exe` | its own and others it lists | `licenses/mingw-w64/COPYING.MinGW-w64-runtime.txt` |
| AppImage type 2 runtime (probonopd), built from commit `fedfad51acc2860b2916a1eef32ba4a500ff31ef` (the runtime names it) | the AppImage's first part (`runtime_sha256` in `launcher/appimage/make_appimage.sh`) | MIT | `licenses/appimage-runtime/type2-runtime.txt` |
| libfuse 3.15.0, changed by the runtime's `patches/libfuse/mount.c.diff` | in that runtime | LGPL 2.1 | `licenses/appimage-runtime/libfuse-LGPL2.txt` |
| squashfuse 0.5.2 (Dave Vasilevsky, Phillip Lougher) | in that runtime | BSD 2-Clause | `licenses/appimage-runtime/squashfuse.txt` |
| zstd 1.5.6 (Meta Platforms) | in that runtime | BSD 3-Clause (or GPL 2) | `licenses/appimage-runtime/zstd.txt` |
| zlib 1.3.2 (Jean-loup Gailly and Mark Adler) | in that runtime | zlib | `licenses/appimage-runtime/zlib.txt` |
| mimalloc (Microsoft, Daan Leijen) | in that runtime | MIT | `licenses/appimage-runtime/mimalloc.txt` |
| musl (Rich Felker and contributors) | in that runtime | MIT | `licenses/appimage-runtime/musl.txt` |

The runtime is used as its project publishes it. Its source, the libfuse patch and the scripts that build it with these
libraries (zstd, zlib, mimalloc and musl are Alpine Linux 3.21's):
https://github.com/AppImage/type2-runtime/tree/fedfad51acc2860b2916a1eef32ba4a500ff31ef

## Also in Golden_Fist_Launcher-x86_64.exe

| Work | License | Text |
|---|---|---|
| MinGW-w64's runtime | its own and others it lists | `licenses/mingw-w64/COPYING.MinGW-w64-runtime.txt` |
| winpthreads (the mingw-w64 project, Lockless) | MIT, parts BSD 3-Clause | `licenses/mingw-w64/winpthreads.txt` |
| GCC's libstdc++ and libgcc | GPL 3 with the GCC Runtime Library Exception 3.1 | https://www.gnu.org/licenses/gcc-exception-3.1.html |

## Fetched when building

| Work | License | Pinned in | Used by |
|---|---|---|---|
| SDL 3.4.18 (Sam Lantinga and contributors) | zlib | `dependencies.launcher.lock.json` (`tools/setup_deps.py --launcher`) | the launcher's release programs (built in) |
| SDL 3.4.18's `SDL3.dll` | zlib | `tools/windows-bootstrap.lock.json`, `tools/setup_windows_runtime.ps1` (`SDL3-devel-3.4.18-mingw.zip`) | the game on Windows, and the launcher a Windows setup builds (the DLL beside them) |
| ZArchive | MIT-0 | `dependencies.lock.json` | the builder, the game and `wua_extract` |
| AMD's address library (decaf-emu/addrlib) | MIT | `dependencies.lock.json` | the game |
| Vulkan-Headers | Apache-2.0 or MIT | `dependencies.windows.lock.json` | the game on Windows |
| shaderc, with SPIRV-Tools (both Apache-2.0), glslang (BSD 3-Clause and others, its `LICENSE.txt`) and SPIRV-Headers (MIT) | as named | `dependencies.windows.lock.json` | the game on Windows (`libshaderc_shared.dll`) |
| zlib 1.3.1, zstd 1.5.7 | zlib; BSD 3-Clause | `CMakeLists.txt` | the game and its tools on Windows |
| llvm-mingw's libc++ and libunwind (Apache-2.0 with the LLVM exception) and winpthreads (MIT, parts BSD 3-Clause) | as named | `tools/windows-bootstrap.lock.json` | the programs built on a Windows PC (built in, or as DLLs beside the game) |

On Linux the game program and the kit's programs also link the system's SDL3 (zlib), shaderc (Apache-2.0), the Vulkan
loader (Apache-2.0), OpenSSL (Apache-2.0), zstd (BSD) and zlib; see `README.md` (License).
