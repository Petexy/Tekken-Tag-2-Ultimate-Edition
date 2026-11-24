# Single-header libraries in the launcher's interface

Copied unmodified from their upstream repositories (each keeps its own license
text: at the end of the stb headers, at the start of the nanosvg ones). They are
compiled once, in `third_party.c` (`ttt2_launcher_vendor`), with warnings off.

| File | Upstream | Commit | License | SHA-256 |
|---|---|---|---|---|
| `stb_truetype.h` (v1.28) | https://github.com/nothings/stb | `6b5799bae8a1fe3792691ef4b72ae26434c3e799` | public domain or MIT | `428cfe93520f2aed5e413a220b0db5bba5b17e2ebe5a64e4a8efa9eeeb67ec5f` |
| `stb_image_write.h` (v1.19) | https://github.com/nothings/stb | `6b5799bae8a1fe3792691ef4b72ae26434c3e799` | public domain or MIT | `5d89edc8bffd848f3e138b2a1dbec67aadbed591894bde16ade7c83dc233af9b` |
| `nanosvg.h` | https://github.com/memononen/nanosvg (`src/`) | `239e102ec2c691f2902e20ace2ed36ee4a35cfe6` | zlib | `e34fd5d084be106cea972d19ce5d27fd96d17ba89f8d06bdceee058420c8b2b0` |
| `nanosvgrast.h` | https://github.com/memononen/nanosvg (`src/`) | `239e102ec2c691f2902e20ace2ed36ee4a35cfe6` | zlib | `79a9c5f4db19debf9f3a648a1589e96d92854f245a5cb4f3d823f263785234d8` |

To update one: copy the file from a newer commit, then change its commit and
SHA-256 (`sha256sum`) here and in `THIRD_PARTY_NOTICES.md` at the repository's root.
