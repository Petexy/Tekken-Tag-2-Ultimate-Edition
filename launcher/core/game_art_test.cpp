// game_art: NUT textures and packs read from MADE-UP files written here (no game data in the repository): blocks
// whose texels are worked out by hand from Direct3D's block compression rules, the packs' character.ini first line.
// Argument: a scratch folder (the build folder).
#include "game_art.h"

#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace ga = launcher::game_art;
namespace fs = std::filesystem;

namespace {

int g_failed = 0, g_checks = 0;
void check(bool ok, const char* what, int line) {
    ++g_checks;
    if (!ok) {
        ++g_failed;
        std::printf("FAIL line %d: %s\n", line, what);
    }
}
#define CHECK(c) check((c), #c, __LINE__)

void be16(std::string& s, unsigned v) {
    s += static_cast<char>(v >> 8 & 255);
    s += static_cast<char>(v & 255);
}
void be32(std::string& s, unsigned v) {
    be16(s, v >> 16);
    be16(s, v & 0xffff);
}

// A NUT with one texture: `format`, w x h, these block bytes.
std::string nut(int format, int w, int h, const std::string& blocks) {
    std::string s = "NTP3";
    be16(s, 0x0100);
    be16(s, 1);
    s.append(8, '\0');
    const unsigned header = 0x50;
    be32(s, header + static_cast<unsigned>(blocks.size()));  // total
    be32(s, 0);                                               // palette
    be32(s, static_cast<unsigned>(blocks.size()));            // data size
    be16(s, header);
    be16(s, 0);
    s += '\0';
    s += '\1';  // one mip
    s += '\0';
    s += static_cast<char>(format);
    be16(s, static_cast<unsigned>(w));
    be16(s, static_cast<unsigned>(h));
    s.append(24, '\0');
    s += std::string("eXt\0", 4);
    be32(s, 0x20);
    be32(s, 0x10);
    be32(s, 0);
    s += "GIDX";
    be32(s, 0x10);
    be32(s, 0x1234);
    be32(s, 0);
    CHECK(s.size() == 0x10 + header);
    return s + blocks;
}

std::string bytes(std::initializer_list<int> b) {
    std::string s;
    for (int v : b) s += static_cast<char>(v);
    return s;
}

const std::uint8_t* px(const ga::Image& im, int x, int y) { return &im.rgba[static_cast<size_t>((y * im.w + x) * 4)]; }

}  // namespace

int main(int argc, char** argv) {
    const fs::path scratch = fs::path(argc > 1 ? argv[1] : ".") / "game_art_test";
    std::error_code ec;
    fs::remove_all(scratch, ec);
    fs::create_directories(scratch);

    // BC1, c0 = pure red (0xF800) > c1 = pure blue (0x001F): texel 0 index 0 (red), texel 1 index 1 (blue),
    // texel 2 index 2 ((2 red + blue) / 3), texel 3 index 3 ((red + 2 blue) / 3), the rest red.
    {
        const auto im = ga::decode_nut(nut(0, 4, 4, bytes({0x00, 0xF8, 0x1F, 0x00, 0b11100100, 0, 0, 0})));
        CHECK(im && im->w == 4 && im->h == 4);
        if (im) {
            CHECK(px(*im, 0, 0)[0] == 255 && px(*im, 0, 0)[2] == 0 && px(*im, 0, 0)[3] == 255);
            CHECK(px(*im, 1, 0)[0] == 0 && px(*im, 1, 0)[2] == 255);
            CHECK(px(*im, 2, 0)[0] == 170 && px(*im, 2, 0)[2] == 85);
            CHECK(px(*im, 3, 0)[0] == 85 && px(*im, 3, 0)[2] == 170);
            CHECK(px(*im, 3, 3)[0] == 255 && px(*im, 3, 3)[1] == 0);
        }
    }
    // BC1 three-colour mode (c0 <= c1): index 3 is transparent.
    {
        const auto im = ga::decode_nut(nut(0, 4, 4, bytes({0x1F, 0x00, 0x00, 0xF8, 0b11, 0, 0, 0})));
        CHECK(im && px(*im, 0, 0)[3] == 0 && px(*im, 1, 0)[3] == 255 && px(*im, 1, 0)[2] == 255);
    }
    // BC3 on a 6 x 5 texture (2 x 2 blocks, cropped): alpha a0 = 255 > a1 = 0, texel 0 index 0 (255), texel 1
    // index 1 (0), texel 2 index 2 ((6 * 255 + 0) / 7 = 219); the colour block white everywhere (c0 = c1 = 0xFFFF,
    // four colours). The other blocks: alpha a0 = 0 <= a1 = 0 (index 7 = 255), colour black.
    {
        const std::string white = bytes({0xFF, 0xFF, 0xFF, 0xFF, 0, 0, 0, 0});
        const std::string black = bytes({0, 0, 0, 0, 0, 0, 0, 0});
        // indices 0, 1, 2 for texels 0..2 (3 bits each: 000 001 010 -> bits 0..8 = 0b010001000), the rest 0
        const std::string a1 = bytes({255, 0, 0b10001000, 0, 0, 0, 0, 0});
        const std::string a7 = bytes({0, 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF});
        const auto im = ga::decode_nut(nut(2, 6, 5, a1 + white + a7 + black + a7 + black + a7 + black));
        CHECK(im && im->w == 6 && im->h == 5 && im->rgba.size() == 6 * 5 * 4);
        if (im) {
            CHECK(px(*im, 0, 0)[0] == 255 && px(*im, 0, 0)[3] == 255);
            CHECK(px(*im, 1, 0)[3] == 0);
            CHECK(px(*im, 2, 0)[3] == 219);
            CHECK(px(*im, 4, 0)[0] == 0 && px(*im, 4, 0)[3] == 255);
            CHECK(px(*im, 5, 4)[0] == 0 && px(*im, 5, 4)[3] == 255);
        }
    }
    // Not a texture this reads: wrong magic, a plain format, data cut short.
    CHECK(!ga::decode_nut("NTP4" + std::string(0x80, '\0')));
    CHECK(!ga::decode_nut(nut(14, 4, 4, std::string(64, '\0'))));
    CHECK(!ga::decode_nut(nut(2, 8, 8, std::string(16, '\0'))));
    CHECK(!ga::read_nut(scratch / "missing.nut"));

    // The packs by their character.ini's first line.
    CHECK(ga::ini_display_name("# Kazumi Mishima, from Tekken 7 (made on this machine from the player's own copy)") ==
          "Kazumi Mishima");
    CHECK(ga::ini_display_name("# Reina, from Tekken 8 (x)\r") == "Reina");
    CHECK(ga::ini_display_name("format = 1").empty());
    CHECK(ga::ini_display_name("# , from Tekken 7").empty());
    const auto pack = [&](const std::string& dir, const std::string& first) {
        fs::create_directories(scratch / "packs" / dir / "art");
        std::ofstream(scratch / "packs" / dir / "character.ini") << first << "\nformat = 1\ncode = " << dir << "\n";
    };
    pack("abc", "# Made Up, from Tekken 7 (made on this machine from the player's own copy)");
    pack("def", "# Someone Else, from Tekken 8 (made on this machine from the player's own copy)");
    pack(".abc-new", "# Made Up, from Tekken 7 (being made)");
    pack("ghi", "format = 1");  // (its code line follows: "code = ghi")
    fs::create_directories(scratch / "packs" / "shared" / "keys");
    std::ofstream(scratch / "packs" / "abc" / "art" / "portrait_1p.nut", std::ios::binary)
        << nut(0, 4, 4, bytes({0x00, 0xF8, 0x1F, 0x00, 0, 0, 0, 0}));
    const auto packs = ga::packs(scratch / "packs");
    // (sorted by folder: abc, def, ghi; ghi has a code but no display name; the dot folder is none)
    CHECK(packs.size() == 3);
    if (packs.size() == 3) {
        CHECK(packs[0].dir.filename() == "abc" && packs[0].display == "Made Up" && packs[0].code == "abc");
        CHECK(packs[1].display == "Someone Else" && packs[1].code == "def");
        CHECK(packs[2].display.empty() && packs[2].code == "ghi");
        const auto im = ga::read_nut(ga::portrait_file(packs[0].dir));
        CHECK(im && im->w == 4 && px(*im, 2, 2)[0] == 255);
    }
    CHECK(ga::packs(scratch / "nowhere").empty());

    std::printf("%d checks, %d failed\n", g_checks, g_failed);
    fs::remove_all(scratch, ec);
    return g_failed ? 1 : 0;
}
