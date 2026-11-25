#pragma once

// The added fighters' pictures for the launcher's Fighters screen, read at run time from their packs in the player's
// characters folder (the importer made them there from the player's own Tekken 7 / Tekken 8). Nothing of any game is
// in this repository or shipped with the launcher. Portable C++ without SDL (Linux, Windows, MinGW).
//
// A pack: a folder with a character.ini whose first line is "# <display name>, from <game> (...)" (pack.py's ini(),
// every importer since the first) and art/portrait_1p.nut: the big select portrait (convert/art.py: 356 x 612, its
// red frame and all; the fighter's face where FACE_PORTRAIT puts every fighter's).
//
// NUT ("NTP3", tools/characters/ttt2char/ttt2/nut.py): big-endian; u16 version at 4, u16 texture count at 6, the
// textures from 0x10: u32 total size, u32 palette, u32 data size, u16 header size, u16, u8, u8 mip count, u8, u8
// format (0 BC1, 1 BC2, 2 BC3), u16 width, u16 height, ...; the first mip at the texture's start + header size,
// linear (not tiled). BC1/2/3: Direct3D's block compression, little-endian blocks of 4 x 4 texels row by row.

#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace launcher::game_art {

namespace fs = std::filesystem;

struct Image {
    int w = 0, h = 0;
    std::vector<std::uint8_t> rgba;  // straight alpha, row by row
};

// The first texture of a NUT (its first mip), decoded; nullopt when it is not one this reads.
std::optional<Image> decode_nut(std::string_view data);
std::optional<Image> read_nut(const fs::path& file);

// The packs in `packs_folder`: their folder, display name (character.ini's first line) and code (its "code = ").
// Folders starting with a dot are none (a pack being made or replaced).
struct Pack {
    fs::path dir;
    std::string display, code;
};
std::vector<Pack> packs(const fs::path& packs_folder);
// "Kazumi Mishima" from a character.ini's first line, empty when it has none.
std::string ini_display_name(std::string_view first_line);

// The big select portrait (kPortraitW x kPortraitH): inside its frame (the same for every fighter) is `kInner`; the
// fighter's eyes are at kFaceX, kFaceY (art.py FACE_PORTRAIT: 0.47 and 0.17 of the picture). Pixels.
struct Crop {
    float x, y, w, h;
};
inline constexpr float kPortraitW = 356, kPortraitH = 612;
inline constexpr Crop kInner{62, 24, 246, 536};
inline constexpr float kFaceX = 167, kFaceY = 104;
fs::path portrait_file(const fs::path& pack);  // <pack>/art/portrait_1p.nut

}  // namespace launcher::game_art
