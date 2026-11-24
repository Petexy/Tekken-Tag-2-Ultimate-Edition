# Third-party notices

This repository's own code is under the MIT License (`LICENSE`). Parts of the launcher are made with the works below,
under their own licenses; the files committed here keep their license texts unchanged.

## In the repository

| Work | Where | License | Upstream (pinned commit) |
|---|---|---|---|
| stb_truetype.h, stb_image_write.h (Sean Barrett) | `launcher/ui/third_party/` | public domain or MIT (the reader's choice; text at the end of each file) | https://github.com/nothings/stb (`6b5799bae8a1fe3792691ef4b72ae26434c3e799`) |
| nanosvg.h, nanosvgrast.h (Mikko Mononen) | `launcher/ui/third_party/` | zlib (text at the start of each file) | https://github.com/memononen/nanosvg (`239e102ec2c691f2902e20ace2ed36ee4a35cfe6`) |
| Barlow, Barlow Condensed (The Barlow Project Authors) | `launcher/ui/fonts/Barlow`, `launcher/ui/fonts/BarlowCondensed` | SIL Open Font License 1.1 (`OFL.txt` beside the fonts) | https://github.com/jpt/barlow (`dc2940e2e04ef4ec96c07e23e0f02aefbddd343b`) |
| JetBrains Mono (The JetBrains Mono Project Authors) | `launcher/ui/fonts/JetBrainsMono` | SIL Open Font License 1.1 (`OFL.txt` beside the fonts) | https://github.com/JetBrains/JetBrainsMono (`19371302b95d218af43299bce79ddbddd0bc364d`) |

The fonts and these libraries are built into the launcher program. File checksums: `launcher/ui/third_party/README.md`,
`launcher/ui/fonts/README.md`.

## Fetched when building

| Work | License | Pinned in | Used by |
|---|---|---|---|
| SDL 3.4.18 (Sam Lantinga and contributors) | zlib | `dependencies.launcher.lock.json` (`tools/setup_deps.py --launcher`); the Windows game's `SDL3-devel-3.4.18-mingw.zip` in `tools/setup_windows_runtime.ps1` | the launcher's release programs (built in statically); the game (the system's, or that DLL on Windows) |
| ZArchive | MIT-0 | `dependencies.lock.json` | the builder and the game |
| AMD's address library (decaf-emu/addrlib) | MIT | `dependencies.lock.json` | the game |

The game program also links the system's SDL3 (zlib), shaderc (Apache-2.0), the Vulkan loader (Apache-2.0), OpenSSL
(Apache-2.0), zstd (BSD) and zlib; see `README.md` (License).
