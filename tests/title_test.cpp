// The title's file formats and the pictures made from them, on synthetic
// data (no game files needed): archive scrambling, packing and rebuilding,
// texture decoding, the font's glyph table and icon sets, the text banks'
// button names, our Russian and Polish texts and Polish subtitles, the
// copyright line without "Wii U Edition", a still without the logo's
// subtitle getting none, and the Offline menu's SOLO GHOST BATTLE row.

#include "title/archive.h"
#include "title/draw.h"
#include "title/font.h"
#include "title/image.h"
#include "title/language.h"
#include "title/menudata.h"
#include "title/pictures.h"
#include "title/subtitles.h"
#include "title/text.h"
#include "title/title_screen.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

using namespace cafe::title;
using namespace std::string_literals;

namespace {

int g_failures = 0;

void check(bool ok, const std::string& what) {
    if (!ok) {
        std::printf("FAIL %s\n", what.c_str());
        ++g_failures;
    }
}

void put_be32(std::vector<uint8_t>& v, uint32_t x) {
    for (int s = 24; s >= 0; s -= 8) v.push_back(static_cast<uint8_t>(x >> s));
}
uint32_t be32(const uint8_t* p) { return uint32_t{p[0]} << 24 | uint32_t{p[1]} << 16 | uint32_t{p[2]} << 8 | p[3]; }

std::vector<uint8_t> bytes(const std::string& s) { return {s.begin(), s.end()}; }

// ------------------------------------------------------------------ archives

void test_scramble() {
    // The stream: four words seeded x = x * 0xBDE95 + 0x8EF345 from the hash,
    // XORed big-endian over each 16-byte block, each word then stepping
    // w = w * 1531 + 5011.
    const uint32_t hash = 0x12345678;
    std::vector<uint8_t> data(37, 0);
    archive::scramble(data.data(), data.size(), hash);
    uint32_t state[4], x = hash;
    for (uint32_t& s : state) s = x = x * 0xBDE95u + 0x8EF345u;
    std::vector<uint8_t> expected;
    while (expected.size() < data.size()) {
        for (uint32_t& s : state) {
            put_be32(expected, s);
            s = s * 1531u + 5011u;
        }
    }
    expected.resize(data.size());
    check(data == expected, "scramble: the keystream");
    archive::scramble(data.data(), data.size(), hash);
    check(data == std::vector<uint8_t>(37, 0), "scramble: twice is nothing");
}

struct Archive {
    std::vector<uint8_t> ofs, bin;
};

std::vector<uint8_t> chunk(const char* tag, const std::vector<uint8_t>& payload) {
    std::vector<uint8_t> c;
    put_be32(c, static_cast<uint32_t>(8 + payload.size()));
    c.insert(c.end(), tag, tag + 4);
    c.insert(c.end(), payload.begin(), payload.end());
    return c;
}

// An archive of entries as stored, laid out as the title's are.
Archive make_archive(const std::vector<std::pair<uint32_t, std::vector<uint8_t>>>& entries) {
    std::vector<uint8_t> names, offsets, payload;
    for (const auto& [hash, stored] : entries) {
        put_be32(names, hash);
        put_be32(names, 0);
        put_be32(offsets, static_cast<uint32_t>(payload.size()) | (stored.size() % 16));
        payload.insert(payload.end(), stored.begin(), stored.end());
        payload.resize((payload.size() + 15) & ~size_t{15});
    }
    put_be32(offsets, static_cast<uint32_t>(payload.size()));
    Archive a;
    for (const auto& c : {chunk("ftyp", bytes("nrfo....")), chunk("head", std::vector<uint8_t>(20)), chunk("ofsi", names),
                          chunk("ofsd", offsets)}) {
        a.ofs.insert(a.ofs.end(), c.begin(), c.end());
    }
    a.bin.assign(archive::kPayload - 8, 0);
    put_be32(a.bin, static_cast<uint32_t>(8 + payload.size()));
    a.bin.insert(a.bin.end(), {'i', 'm', 'g', 'e'});
    a.bin.insert(a.bin.end(), payload.begin(), payload.end());
    return a;
}

std::vector<uint8_t> contents_of(const Archive& a, uint32_t hash) {
    const auto index = archive::parse_index(a.ofs);
    const archive::Entry* e = index ? index->find(hash) : nullptr;
    if (!e || archive::kPayload + e->offset + e->size > a.bin.size()) return {};
    std::vector<uint8_t> stored(a.bin.begin() + static_cast<ptrdiff_t>(archive::kPayload + e->offset),
                                a.bin.begin() + static_cast<ptrdiff_t>(archive::kPayload + e->offset + e->size));
    return archive::unpack(stored, hash).value_or(std::vector<uint8_t>{});
}

void test_archive() {
    const uint8_t flags[8] = {0x30, 0x14, 0, 0, 0, 0, 0, 0};
    std::vector<uint8_t> big(5000);
    for (size_t i = 0; i < big.size(); ++i) big[i] = static_cast<uint8_t>(i * 7 % 251);
    std::vector<uint8_t> raw = bytes("not compressed, 37 bytes long......."), raw_stored = raw;
    archive::scramble(raw_stored.data(), raw_stored.size(), 0xBBBB);
    const std::vector<uint8_t> small = bytes("sixteen bytes!!!");
    const Archive a = make_archive({{0xAAAA, archive::pack(big, 0xAAAA, flags)},
                                    {0xBBBB, raw_stored},
                                    {0xCCCC, archive::pack(small, 0xCCCC, flags)}});
    check(contents_of(a, 0xAAAA) == big, "archive: a compressed entry");
    check(contents_of(a, 0xBBBB) == raw, "archive: an entry stored as it is");
    check(contents_of(a, 0xCCCC) == small, "archive: the last entry");

    const auto index = archive::parse_index(a.ofs);
    const archive::Entry* e = index->find(0xAAAA);
    std::vector<uint8_t> start(a.bin.begin() + archive::kPayload, a.bin.begin() + archive::kPayload + 64);
    const auto first = archive::peek(start, 0xAAAA, 8);
    check(first == std::vector<uint8_t>(big.begin(), big.begin() + 8), "archive: peeking into a compressed entry");
    uint8_t got[8];
    archive::stored_flags(std::vector<uint8_t>(a.bin.begin() + archive::kPayload, a.bin.begin() + archive::kPayload + 16),
                          0xAAAA, got);
    check(std::memcmp(got, flags, 8) == 0 && e->offset == 0, "archive: an entry's NRCZ flags");

    // The middle entry replaced by a longer one, and one added.
    std::vector<uint8_t> longer(300, 'x'), added = bytes("an entry the archive did not hold");
    // (the added one made when it is read, stored uncompressed)
    auto made = std::make_shared<archive::Source>();
    made->size = archive::stored_size(added.size());
    made->make = [&]() -> std::optional<std::vector<uint8_t>> { return archive::store(added, 0xDDDD, flags); };
    const auto rebuilt = archive::rebuild(
        a.ofs, std::vector<uint8_t>(a.bin.begin(), a.bin.begin() + archive::kPayload),
        {{0xBBBB, std::make_shared<const archive::Source>(archive::held(archive::pack(longer, 0xBBBB, flags)))},
         {0xDDDD, made}});
    check(rebuilt.has_value(), "rebuild: an archive with a replaced and an added entry");
    if (!rebuilt) return;
    Archive b;
    b.ofs = rebuilt->ofs;
    b.bin.resize(rebuilt->bin_size);
    for (const archive::Piece& p : rebuilt->bin) {
        if (!p.entry) {
            std::memcpy(&b.bin[p.at], &a.bin[p.source], p.size);
            continue;
        }
        const auto data = p.entry->data ? *p.entry->data : p.entry->make().value_or(std::vector<uint8_t>{});
        check(data.size() == p.entry->size && p.size - data.size() < 16, "rebuild: an entry is as long as it says");
        std::memcpy(&b.bin[p.at], data.data(), std::min<size_t>(data.size(), p.size)); // (the padding stays zero)
    }
    check(contents_of(b, 0xAAAA) == big && contents_of(b, 0xBBBB) == longer && contents_of(b, 0xCCCC) == small &&
              contents_of(b, 0xDDDD) == added,
          "rebuild: every entry read back");
    // An entry stored uncompressed: as long as its contents' size says, read back like a compressed one.
    for (const size_t n : {size_t{0}, size_t{1}, size_t{65535}, size_t{65536}, size_t{200000}}) {
        std::vector<uint8_t> contents(n);
        for (size_t i = 0; i < n; ++i) contents[i] = static_cast<uint8_t>(i * 13 % 239);
        const std::vector<uint8_t> stored = archive::store(contents, 0x1234, flags);
        uint8_t stored_flags[8];
        archive::stored_flags(stored, 0x1234, stored_flags);
        check(stored.size() == archive::stored_size(n), "store: an uncompressed entry is as long as foretold");
        check(std::memcmp(stored_flags, flags, 8) == 0, "store: an uncompressed entry's NRCZ flags");
        if (n != 0) check(archive::unpack(stored, 0x1234) == contents, "store: an uncompressed entry read back");
    }
    const auto rebuilt_index = archive::parse_index(b.ofs);
    check(rebuilt_index && rebuilt_index->entries.size() == 4 && rebuilt_index->entries.back().hash == 0xDDDD,
          "rebuild: the added entry is the last");
    check(b.ofs.size() == a.ofs.size() + 12 && std::equal(a.ofs.begin(), a.ofs.begin() + 8 + 8 + 8 + 20, b.ofs.begin()),
          "rebuild: the index's other chunks kept");
    check(be32(&b.bin[archive::kPayload - 8]) == b.bin.size() - archive::kPayload + 8, "rebuild: the payload's size");
}

// ------------------------------------------------------------------ textures

void test_bc() {
    // BC1: red and blue endpoints, texel 0 index 0, texel 1 index 1, texel 2
    // index 2 (2/3 red), texel 3 index 3 (1/3 red).
    const uint8_t bc1[8] = {0x00, 0xF8, 0x1F, 0x00, 0b11100100, 0, 0, 0};
    const Rgba a = decode_bc(1, bc1, 4, 4);
    check(a.at(0, 0)[0] == 255 && a.at(0, 0)[2] == 0, "BC1: the first endpoint");
    check(a.at(1, 0)[0] == 0 && a.at(1, 0)[2] == 255, "BC1: the second endpoint");
    check(a.at(2, 0)[0] == 170 && a.at(3, 0)[0] == 85, "BC1: the colours between");
    // BC3: alpha endpoints 255 and 0, texel 0 index 0, texel 1 index 1.
    uint8_t bc3[16] = {255, 0, 0b00001000, 0, 0, 0, 0, 0};
    std::memcpy(bc3 + 8, bc1, 8);
    const Rgba b = decode_bc(3, bc3, 4, 4);
    check(b.at(0, 0)[3] == 255 && b.at(1, 0)[3] == 0, "BC3: alpha");
}

// ------------------------------------------------------------------ fonts

// A glyph table, little-endian like the main font's or big-endian like
// the plain font's.
std::vector<uint8_t> make_nfh(std::vector<std::pair<uint16_t, font::Glyph>> glyphs, bool big_endian = false) {
    std::sort(glyphs.begin(), glyphs.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    std::vector<uint8_t> nfh(0x450, 0);
    std::memcpy(nfh.data(), "NFH", 4);
    const auto put32 = [&](size_t at, uint32_t v) {
        for (int i = 0; i < 4; ++i) nfh[at + i] = static_cast<uint8_t>(v >> (big_endian ? 24 - 8 * i : 8 * i));
    };
    put32(4, 24); // pixels
    put32(8, static_cast<uint32_t>(glyphs.size()));
    const auto put16 = [&](uint8_t* p, uint32_t v) {
        p[big_endian ? 0 : 1] = static_cast<uint8_t>(v >> 8);
        p[big_endian ? 1 : 0] = static_cast<uint8_t>(v);
    };
    for (const auto& [code, g] : glyphs) {
        uint8_t r[32] = {};
        put16(r + 4, g.x);
        put16(r + 6, g.y);
        put16(r + 12, g.width * 64); // the advance
        r[20] = static_cast<uint8_t>(g.width);
        r[21] = static_cast<uint8_t>(g.height);
        r[22] = static_cast<uint8_t>(code >> 8);
        r[23] = static_cast<uint8_t>(code);
        nfh.insert(nfh.end(), r, r + 32);
    }
    return nfh;
}

bool same_box(const Rgba& a, const Rgba& b, const font::Glyph& g) {
    for (uint32_t y = g.y; y < g.y + g.height; ++y) {
        if (std::memcmp(a.at(g.x, y), b.at(g.x, y), g.width * 4) != 0) return false;
    }
    return true;
}

void test_font() {
    const std::vector<std::pair<uint16_t, font::Glyph>> table = {
        {0xE024, {0, 0, 22, 22}},  {0xE01C, {24, 0, 22, 22}}, {0xE036, {48, 0, 22, 22}},
        {0x2282, {0, 24, 36, 17}}, {'L', {40, 24, 10, 14}},   {'1', {52, 24, 10, 14}}};
    const auto glyphs = font::parse(make_nfh(table));
    check(glyphs && glyphs->size() == table.size() && glyphs->at(0x2282).width == 36 && glyphs->at('1').x == 52,
          "font: the glyph table");
    if (!glyphs) return;
    font::Font f{*glyphs, blank(96, 64)};
    for (uint32_t y = 0; y < 22; ++y) { // the lit-dot picture: a white square
        for (uint32_t x = 30; x < 40; ++x) std::memset(f.texture.at(x, y), 255, 4);
    }
    for (uint32_t y = 0; y < 64; ++y) f.texture.at(90, y)[1] = 77; // outside every box
    const Rgba neutral = font::neutral_icons(f);
    const font::Glyph source = glyphs->at(0xE01C);
    check(same_box(neutral, f.texture, source), "neutral icons: the dot pictures stay");
    bool copied = true;
    for (uint32_t y = 0; y < 22; ++y) copied = copied && std::memcmp(neutral.at(0, y), f.texture.at(24, y), 22 * 4) == 0;
    check(copied, "neutral icons: the right button shows the right dot lit");
    check(neutral.at(90, 10)[1] == 77, "neutral icons: the rest of the texture stays");
    const Rgba playstation = font::playstation_icons(f);
    check(!same_box(playstation, f.texture, glyphs->at(0xE024)) && !same_box(playstation, f.texture, glyphs->at(0x2282)),
          "PlayStation icons: drawn in the face button's and L1's boxes");
    check(playstation.at(90, 10)[1] == 77, "PlayStation icons: the rest of the texture stays");
}

void test_glyph_tables() {
    for (const bool big_endian : {false, true}) {
        const std::string kind = big_endian ? " (big-endian)" : " (little-endian)";
        auto nfh = make_nfh({{'A', {0, 0, 20, 24}}, {0xA3, {30, 0, 22, 25}}, {0xE024, {60, 0, 22, 22}}}, big_endian);
        const auto glyphs = font::parse(nfh);
        check(glyphs && glyphs->size() == 3 && glyphs->at(0xA3).x == 30 && glyphs->at(0xA3).height == 25,
              "font: a glyph table" + kind);
        const auto record = [&](uint16_t code) {
            for (size_t at = 0x450; at + 32 <= nfh.size(); at += 32) {
                const uint8_t* r = &nfh[at + 4];
                if ((r[18] << 8 | r[19]) == code) return std::vector<uint8_t>(r, r + 20);
            }
            return std::vector<uint8_t>{};
        };
        check(font::copy_glyph(nfh, 0xA3, 0xE024), "font: copying a glyph" + kind);
        const auto copied = font::parse(nfh);
        const auto a3 = record(0xA3), e024 = record(0xE024);
        check(copied && copied->at(0xA3).x == 60 && copied->at(0xA3).width == 22 &&
                  std::equal(a3.begin(), a3.begin() + 18, e024.begin()) && a3[18] == 0x00 && a3[19] == 0xA3,
              "font: a copied glyph has the other's box and placement, and its code point" + kind);
        check(font::set_glyph(nfh, 'A', {100, 50, 21, 21}, {0, 19, 22}), "font: setting a glyph" + kind);
        const auto set = font::parse(nfh);
        const auto a = record('A');
        const auto at16 = [&](size_t i) { return big_endian ? a[i] << 8 | a[i + 1] : a[i] | a[i + 1] << 8; };
        check(set && set->at('A').x == 100 && set->at('A').y == 50 && set->at('A').width == 21 && at16(6) == 19 * 64 &&
                  at16(8) == 22 * 64,
              "font: a set glyph's box and placement" + kind);
        check(!font::copy_glyph(nfh, 0xB3, 'A') && !font::set_glyph(nfh, 0xB3, {}, {}),
              "font: a glyph the table lacks" + kind);
    }
    auto unsorted = make_nfh({{'A', {0, 0, 1, 1}}, {'B', {0, 0, 1, 1}}});
    std::swap_ranges(unsorted.begin() + 0x450, unsorted.begin() + 0x470, unsorted.begin() + 0x470);
    check(!font::parse(unsorted), "font: a table out of code point order is not read");
}

void test_draw() {
    draw::Canvas c(20, 20);
    c.fill(draw::Shape::circle(20, 20, {10, 10}, 6), draw::Colour::rgb(0xFFFFFF));
    const Rgba r = c.result();
    double area = 0;
    for (uint32_t y = 0; y < 20; ++y) {
        for (uint32_t x = 0; x < 20; ++x) area += r.at(x, y)[3] / 255.0;
    }
    check(std::abs(area - 3.14159 * 36) < 2.0, "draw: a circle's area");
}

void test_distance() {
    std::vector<uint8_t> set(7 * 5, 0);
    set[2 * 7 + 1] = 1;
    const std::vector<float> d = distance(set, 7, 5);
    check(d[2 * 7 + 1] == 0 && d[2 * 7 + 4] == 3 && std::abs(d[0] - std::sqrt(5.0f)) < 1e-6f &&
              std::abs(d[4 * 7 + 6] - std::sqrt(29.0f)) < 1e-5f,
          "distance: exact Euclidean distances to the set pixel");
    check(distance(std::vector<uint8_t>(4, 0), 2, 2)[3] > 1e9f, "distance: huge where nothing is set");
}

void test_pictures() {
    for (int k = 0; k < 3; ++k) {
        const Rgba white = pictures::white(static_cast<pictures::Device>(k));
        size_t opaque = 0;
        bool edges_clear = true;
        for (uint32_t y = 0; y < white.height; ++y) {
            for (uint32_t x = 0; x < white.width; ++x) {
                const uint8_t* p = white.at(x, y);
                if (p[3] == 255) ++opaque;
                // Room round it for the glow.
                if ((x < 8 || y < 8 || x >= white.width - 8 || y >= white.height - 8) && p[3] != 0) edges_clear = false;
            }
        }
        const std::string name = "pictures " + std::to_string(k) + ": ";
        check(white.width == pictures::kWidth && white.height == pictures::kHeight && opaque > 15000 && edges_clear,
              name + "the device, with room for its glow");
        const Rgba red = pictures::lit(white, pictures::kRedGlow, pictures::kRedTint);
        // Along the middle row from the left: the glow outside, the tint inside.
        const uint32_t y = white.height / 2;
        uint32_t edge = 0;
        while (edge < white.width && white.at(edge, y)[3] < 128) ++edge;
        // (The pixel next to the edge is part outline.)
        check(edge >= 17 && red.at(edge - 2, y)[0] > 240 && red.at(edge - 2, y)[1] < 10 && red.at(edge - 2, y)[3] > 150 &&
                  red.at(edge - 17, y)[3] == 0,
              name + "a red glow outside, gone some 14 pixels out");
        check(red.at(edge + 3, y)[1] < white.at(edge + 3, y)[1], name + "tinted red inside the edge");
        bool deep_same = true;
        for (uint32_t x = 0; x < white.width; ++x) {
            bool deep = true;
            for (int dy = -28; dy <= 28 && deep; ++dy) {
                for (int dx = -28; dx <= 28 && deep; ++dx) {
                    const int px = int(x) + dx, py = int(y) + dy;
                    deep = px >= 0 && py >= 0 && px < int(white.width) && py < int(white.height) &&
                           white.at(uint32_t(px), uint32_t(py))[3] >= 128;
                }
            }
            if (deep && std::memcmp(red.at(x, y), white.at(x, y), 4) != 0) deep_same = false;
        }
        check(deep_same, name + "deep inside, as it was");
        const Rgba small = pictures::small(white);
        size_t shadow = 0;
        for (uint32_t sy = 0; sy < small.height; ++sy) {
            for (uint32_t sx = 0; sx < small.width; ++sx) {
                const uint8_t* p = small.at(sx, sy);
                if (p[3] > 20 && p[0] < 10 && p[1] < 10 && p[2] < 10) ++shadow;
            }
        }
        check(small.width == pictures::kSmallWidth && small.height == pictures::kSmallHeight && shadow > 150,
              name + "small, on its shadow");
    }
}

// ------------------------------------------------------------------ text banks

struct Record {
    std::string key, text, english;
};

size_t pad(size_t bytes, size_t zeros) { return (bytes + zeros + 3) & ~size_t{3}; }

std::vector<uint8_t> make_bank(const std::vector<Record>& records, bool bad_count = false) {
    std::vector<uint8_t> bank(0x30, 0);
    std::memcpy(bank.data(), "NTXB", 4);
    for (const Record& r : records) {
        std::vector<uint8_t> key(r.key.begin(), r.key.end());
        key.resize(pad(key.size(), 1), 0);
        bank.insert(bank.end(), key.begin(), key.end());
        size_t count = 0;
        for (const char c : r.text) count += (c & 0xC0) != 0x80;
        if (bad_count) ++count;
        bank.insert(bank.end(), {0xAB, 0xCD, static_cast<uint8_t>(count >> 8), static_cast<uint8_t>(count)});
        for (const std::string* s : {&r.text, &r.english}) {
            std::vector<uint8_t> t(s->begin(), s->end());
            t.resize(pad(t.size(), 2), 0);
            bank.insert(bank.end(), t.begin(), t.end());
        }
    }
    return bank;
}

// The bank's texts and their lengths, in order; a shortened text keeps its
// space (zero bytes up to the next part).
std::vector<std::pair<std::string, size_t>> texts(const std::vector<uint8_t>& bank) {
    std::vector<std::pair<std::string, size_t>> out;
    size_t at = 0x30;
    const auto skip_zeros = [&] {
        while (at < bank.size() && bank[at] == 0) ++at;
    };
    while (at < bank.size()) {
        const std::string key(reinterpret_cast<const char*>(&bank[at]));
        at += pad(key.size(), 1);
        const size_t count = size_t{bank[at + 2]} << 8 | bank[at + 3];
        at += 4;
        const std::string text(reinterpret_cast<const char*>(&bank[at]));
        at += text.size();
        skip_zeros();
        const std::string english(reinterpret_cast<const char*>(&bank[at]));
        at += english.size();
        skip_zeros();
        out.push_back({text, count});
    }
    return out;
}

void test_text() {
    const std::string start = "\xEF\xBC\xBC", select = "\xC2\xB3", a = "\xC2\xA3", b = "\xC2\xA5", x = "\xC2\xA2",
                      y = "\xC2\xAA", pad_icon = "\xC2\xBB";
    auto bank = make_bank({
        {"common_4", "PRESS THE + BUTTON", "PRESS THE + BUTTON"},
        {"practice_987", "Press the - Button and B Button to set.", "Press the - Button and B Button "},
        {"common_9", "A DATA Button is no button.", "A DATA Button is no button."},
        {"common_10", "Appuyer sur le bouton Annuler.", "Press Cancel."},
        {"Manu_1692", "Attack using the A, B, X, and Y Buttons.", "Attack using the A, B, X, and Y"},
        {"common_479", "Press left on the +Control Pad.", "Press left on the +Control Pad."},
        {"common_12", "Drücke den X-Knopf.", "Press the X Button."},
    });
    const int changed = text::show_button_icons(bank);
    const auto t = texts(bank);
    check(changed == 5, "text: five texts name buttons");
    check(t.size() == 7, "text: the records still parse");
    if (t.size() != 7) return;
    check(t[0].first == "PRESS " + start + " BUTTON" && t[0].second == 14, "text: the prompt to press Start");
    check(t[1].first == "Press the " + select + " and " + b + " to set.", "text: the - and B buttons");
    check(t[2].first == "A DATA Button is no button.", "text: only whole button names");
    check(t[3].first == "Appuyer sur le bouton Annuler.", "text: not a word starting with a button's letter");
    check(t[4].first == "Attack using the " + a + ", " + b + ", " + x + ", and " + y + ".", "text: a list of buttons");
    check(t[5].first == "Press left on the " + pad_icon + ".", "text: the +Control Pad");
    check(t[6].first == "Drücke den " + x + ".", "text: German");
    auto wrong = make_bank({{"common_4", "PRESS THE + BUTTON", "PRESS THE + BUTTON"}}, true);
    check(text::show_button_icons(wrong) == 0, "text: a record whose length does not match is left alone");

    // Russian: the PlayStation 3's and Xbox 360's names (START, SELECT, BACK) and our translations' (made-up texts)
    auto russian = make_bank({
        {"common_193", "Жмите кнопку START дважды.", "Push plus twice."},
        {"common_1319", "Нажать START и ждать.", "Push plus, wait."},
        {"Manu_635", "Держите кнопку BACK, чтобы закрыть.", "Hold minus to close."},
        {"common_1307", "НАЖАТЬ START", "PUSH"},
        {"common_1380", "Только не кнопку PS.", "Leave HOME be."},
        {"common_2", "РЕЖИМ START", "MODE"},
        {"practice_1", "Жмите кнопку - и кнопку B, затем крестовину.", "Minus, B, then the pad."},
        {"Manu_1", "Бейте кнопками A, B, X и Y.", "Hit with all four."},
    });
    check(text::show_button_icons(russian) == 6, "text: six Russian texts name buttons");
    const auto r = texts(russian);
    check(r.size() == 8 && r[0].first == "Жмите " + start + " дважды." && r[0].second == 15, "text: Russian START");
    check(r.size() == 8 && r[1].first == "Нажать " + start + " и ждать.", "text: Russian press START");
    check(r.size() == 8 && r[2].first == "Держите " + select + ", чтобы закрыть.", "text: Russian BACK");
    check(r.size() == 8 && r[3].first == "НАЖАТЬ " + start, "text: the Russian prompt");
    check(r.size() == 8 && r[4].first == "Только не кнопку PS." && r[5].first == "РЕЖИМ START",
          "text: no other START or PS");
    check(r.size() == 8 && r[6].first == "Жмите " + select + " и " + b + ", затем " + pad_icon + ".",
          "text: our Russian names of the - and B buttons and the +Control Pad");
    check(r.size() == 8 && r[7].first == "Бейте " + a + ", " + b + ", " + x + " и " + y + ".",
          "text: our Russian list of buttons");

    std::set<char32_t> used;
    text::code_points(make_bank({{"common_5", "Drücke \xE2\x94\xBC!", "Press the pad!"}}), used);
    check(used == std::set<char32_t>{U'D', U'r', U'\u00FC', U'c', U'k', U'e', U' ', U'\u253C', U'!'},
          "text: the code points texts use (not the English originals')");
}

// A text bank as the title's are (text.cpp's read_index): table 1 by
// number, tables 2 and 3 (the English originals' and keys' hashes) by hash,
// the records after them (read back: with their headers' hash and length).
struct Numbered {
    uint32_t number;
    std::string key, text, english;
    uint16_t header_hash = 0;
    size_t count = 0;
};

uint32_t get32(const std::vector<uint8_t>& b, size_t at) {
    return uint32_t{b[at]} << 24 | uint32_t{b[at + 1]} << 16 | uint32_t{b[at + 2]} << 8 | b[at + 3];
}

void put32(std::vector<uint8_t>& b, size_t at, uint32_t v) {
    for (int k = 0; k < 4; ++k) b[at + k] = static_cast<uint8_t>(v >> (24 - 8 * k));
}

uint32_t hash_of(const std::string& s) {
    uint32_t h = 2166136261u;
    for (const char c : s) h = (h ^ static_cast<uint8_t>(c)) * 16777619u;
    return h;
}

size_t to16(size_t v) { return (v + 15) & ~size_t{15}; }

std::vector<uint8_t> make_indexed(uint8_t language, std::vector<Numbered> records) {
    std::stable_sort(records.begin(), records.end(), [](const auto& a, const auto& b) { return a.number < b.number; });
    const size_t n = records.size();
    std::vector<std::pair<uint32_t, size_t>> tables[2];
    std::vector<uint8_t> area(4, 0);
    std::vector<uint32_t> at(n), english(n), key(n);
    for (size_t i = 0; i < n; ++i) {
        const Numbered& r = records[i];
        at[i] = static_cast<uint32_t>(area.size());
        const size_t count = language::characters(r.text);
        area.insert(area.end(), {0x12, 0x34, static_cast<uint8_t>(count >> 8), static_cast<uint8_t>(count)});
        for (const std::string* t : {&r.text, &r.english, &r.key}) {
            if (t == &r.english) english[i] = static_cast<uint32_t>(area.size());
            if (t == &r.key) key[i] = static_cast<uint32_t>(area.size());
            std::vector<uint8_t> bytes(t->begin(), t->end());
            bytes.resize(pad(bytes.size(), t == &r.key ? 1 : 2), 0);
            area.insert(area.end(), bytes.begin(), bytes.end());
        }
        tables[0].push_back({(hash_of(r.english) & 0xFFFF0000) | static_cast<uint32_t>(r.english.size()), i});
        if (!r.key.empty()) tables[1].push_back({hash_of(r.key), i});
    }
    put32(area, 0, static_cast<uint32_t>(area.size() + 4));
    for (auto& t : tables) {
        std::stable_sort(t.begin(), t.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    }
    const size_t t2 = to16(0x30 + 4 + 16 * n), t3 = to16(t2 + 4 + 8 * tables[0].size()),
                 rec = to16(t3 + 4 + 8 * tables[1].size());
    std::vector<uint8_t> bank(to16(rec + area.size() + 4 + 1), 0xFF);
    std::memcpy(bank.data(), "NTXB", 4);
    put32(bank, 4, 0x00020000u | uint32_t{language} << 8);
    put32(bank, 8, static_cast<uint32_t>(bank.size()));
    put32(bank, 12, 0x30);
    put32(bank, 16, 0x30);
    put32(bank, 20, static_cast<uint32_t>(t2));
    put32(bank, 24, static_cast<uint32_t>(t3));
    put32(bank, 28, static_cast<uint32_t>(rec));
    put32(bank, 0x30, static_cast<uint32_t>(n));
    for (size_t i = 0; i < n; ++i) {
        put32(bank, 0x34 + 16 * i, at[i]);
        put32(bank, 0x38 + 16 * i, english[i]);
        put32(bank, 0x3C + 16 * i, key[i]);
        put32(bank, 0x40 + 16 * i, records[i].number << 16 | 0x12);
    }
    for (int k = 0; k < 2; ++k) {
        const size_t t = k == 0 ? t2 : t3;
        put32(bank, t, static_cast<uint32_t>(tables[k].size()));
        for (size_t j = 0; j < tables[k].size(); ++j) {
            put32(bank, t + 4 + 8 * j, tables[k][j].first);
            put32(bank, t + 8 + 8 * j, static_cast<uint32_t>(4 + 16 * tables[k][j].second));
        }
    }
    std::copy(area.begin(), area.end(), bank.begin() + static_cast<ptrdiff_t>(rec));
    return bank;
}

// The bank's records through its index, in table 1's order; empty if the
// index is not one the title can read (tables in order, each record found
// once by its text and, with a key, once by its key; the size its header's).
std::vector<Numbered> indexed(const std::vector<uint8_t>& bank) {
    if (bank.size() < 0x30 || get32(bank, 8) != bank.size()) return {};
    const size_t rec = get32(bank, 28), n = get32(bank, 0x30);
    std::vector<Numbered> out;
    const auto string = [&](size_t at) { return std::string(reinterpret_cast<const char*>(&bank[rec + at])); };
    size_t keyed = 0;
    for (size_t i = 0; i < n; ++i) {
        const size_t e = 0x34 + 16 * i;
        const size_t header = rec + get32(bank, e);
        out.push_back({get32(bank, e + 12) >> 16, string(get32(bank, e + 8)), string(get32(bank, e) + 4),
                       string(get32(bank, e + 4)), static_cast<uint16_t>(bank[header] | bank[header + 1] << 8),
                       size_t{bank[header + 2]} << 8 | bank[header + 3]});
        keyed += !out.back().key.empty();
        if (i > 0 && out[i].number < out[i - 1].number) return {};
    }
    for (int k = 0; k < 2; ++k) {
        const size_t t = get32(bank, k == 0 ? 20 : 24), entries = get32(bank, t);
        if (entries != (k == 0 ? n : keyed)) return {};
        std::set<size_t> seen;
        for (size_t j = 0; j < entries; ++j) {
            const uint32_t hash = get32(bank, t + 4 + 8 * j), entry = get32(bank, t + 8 + 8 * j);
            const size_t i = (entry - 4) / 16;
            if ((entry - 4) % 16 != 0 || i >= n || !seen.insert(i).second) return {};
            const Numbered& r = out[i];
            const uint32_t want =
                k == 0 ? (hash_of(r.english) & 0xFFFF0000) | static_cast<uint32_t>(r.english.size()) : hash_of(r.key);
            if (hash != want || (j > 0 && (get32(bank, t - 4 + 8 * j) & 0xFFFF0000) > (hash & 0xFFFF0000))) return {};
        }
    }
    return out;
}

// A part's banks, Japanese (1) to Russian (10): texts 1, 2, 3 and 5, and one
// without a number (found by its key). English's 3 is its 1 again, its 2
// "ENGLISH", its 5 "FIVE" or, in a part whose Russian has none of its own
// (a stand-in record), "ENGLISH ONLY"; Russian has text 1 or all.
enum class Russian { kStandIn, kSome, kAll };
std::vector<std::vector<uint8_t>> part(Russian russian) {
    std::vector<std::vector<uint8_t>> banks;
    for (uint8_t l = 1; l <= text::kBankRussian; ++l) {
        const std::string own = "TEXT " + std::to_string(l);
        std::vector<Numbered> records = {{1, "practice_1", own, "TEXT"},
                                         {2, "practice_2", "TWO " + own, "TWO"},
                                         {3, "practice_3", "THREE " + own, "THREE"},
                                         {5, "practice_5", "FIVE " + own, "FIVE"},
                                         {0xFFFF, "practice_9_2", "BY KEY " + own, "BY KEY"}};
        if (l == text::kBankEnglish) {
            records[1].text = "ENGLISH";
            records[2].text = own;
            records[3].text = russian == Russian::kStandIn ? "ENGLISH ONLY" : "FIVE";
        }
        if (l == text::kBankRussian && russian == Russian::kStandIn) records = {{0xFFFF, "", " ", "@_@"}};
        if (l == text::kBankRussian && russian == Russian::kSome) records.resize(1);
        banks.push_back(make_indexed(l, records));
    }
    return banks;
}

std::vector<std::vector<uint8_t>> three_parts() {
    std::vector<std::vector<uint8_t>> banks;
    for (const Russian r : {Russian::kStandIn, Russian::kSome, Russian::kAll}) {
        auto more = part(r);
        banks.insert(banks.end(), more.begin(), more.end());
    }
    return banks;
}

std::vector<std::vector<uint8_t>*> pointers_to(std::vector<std::vector<uint8_t>>& banks) {
    std::vector<std::vector<uint8_t>*> out;
    for (auto& b : banks) out.push_back(&b);
    return out;
}

void test_missing_texts() {
    std::vector<std::vector<uint8_t>> banks = three_parts();
    check(indexed(banks[1]).size() == 5 && indexed(banks[9]).size() == 1, "text: the test's banks read");
    const std::vector<std::vector<uint8_t>> before = banks;
    check(text::bank_language(banks[9]) == text::kBankRussian && text::bank_language(banks[1]) == text::kBankEnglish,
          "text: a bank's language");
    const text::Filled filled = text::fill_missing_texts(pointers_to(banks), {});
    check(filled.banks == (std::vector<size_t>{9, 19}) && filled.kept_english.empty(),
          "text: the Russian banks lacking texts, only");
    // English's texts by number; in Russian where Russian has the same English text (TEXT 2: twice TEXT 10, once
    // THREE TEXT 10) in any part, the header that text's; the keys English's
    const auto stand_in = indexed(banks[9]), some = indexed(banks[19]);
    check(banks[9][6] == text::kBankRussian && stand_in.size() == 5 && stand_in[0].text == "TEXT 10" &&
              stand_in[0].key == "practice_1" && stand_in[1].text == "TWO TEXT 10" && stand_in[2].text == "TEXT 10" &&
              stand_in[2].key == "practice_3" && stand_in[3].text == "ENGLISH ONLY" && stand_in[3].english == "FIVE" &&
              stand_in[4].number == 0xFFFF && stand_in[4].key.empty(),
          "text: a Russian bank without texts gets English's, in Russian where another has them, its stand-in kept");
    check(stand_in.size() == 5 && stand_in[0].header_hash == text::text_hash("TEXT 10") && stand_in[0].count == 7 &&
              stand_in[3].header_hash == 0x3412 && stand_in[3].count == 12,
          "text: a Russian text's header is its own, an English record's as it was");
    check(some.size() == 4 && some[0].text == "TEXT 10" && some[1].number == 2 && some[1].text == "TWO TEXT 10" &&
              some[2].text == "TEXT 10" && some[3].text == "FIVE TEXT 10" && some[3].key == "practice_5",
          "text: a Russian bank keeps its texts and gets those of the numbers it lacks");
    bool others = true;
    for (size_t i = 0; i < banks.size(); ++i) {
        if (i != 9 && i != 19) others = others && banks[i] == before[i];
    }
    check(others, "text: the other banks stay");

    // our translations (by key) before the game's texts; one whose markup is not its English text's stays English
    std::vector<std::vector<uint8_t>> with_ours = three_parts();
    const text::Translation ours[] = {{"practice_2", "ДВА"}, {"practice_3", "ТРИ"}, {"practice_5", "ПЯТЬ\nШЕСТЬ"}};
    const text::Filled filled_ours = text::fill_missing_texts(pointers_to(with_ours), ours);
    const auto ours_stand_in = indexed(with_ours[9]), ours_some = indexed(with_ours[19]);
    check(filled_ours.banks == (std::vector<size_t>{9, 19}) &&
              filled_ours.kept_english == (std::vector<std::string>{"practice_5", "practice_5"}),
          "text: our translations, those whose markup differs named");
    check(ours_stand_in.size() == 5 && ours_stand_in[0].text == "TEXT 10" && ours_stand_in[1].text == "ДВА" &&
              ours_stand_in[1].english == "TWO" && ours_stand_in[1].key == "practice_2" &&
              ours_stand_in[1].header_hash == 0x0738 && ours_stand_in[1].count == 3 &&
              ours_stand_in[2].text == "ТРИ" && ours_stand_in[3].text == "ENGLISH ONLY",
          "text: our translation with its own header, before the game's text; English where its markup differs");
    check(ours_some.size() == 4 && ours_some[0].text == "TEXT 10" && ours_some[1].text == "ДВА" &&
              ours_some[2].text == "ТРИ" && ours_some[3].text == "FIVE" && ours_some[3].english == "FIVE",
          "text: our translations only for the numbers Russian lacks; English, not the game's text, for one left out");

    // our texts' references: expanded from the Russian banks as they were, then markup checked; one naming a
    // record no Russian bank has leaves English (named)
    std::vector<std::vector<uint8_t>> with_references = three_parts();
    with_references[29] = make_indexed(text::kBankRussian, {{1, "practice_1", "TEXT 10", "TEXT"},
                                                            {2, "practice_2", "ДВА\nСЛОВА", "TWO"},
                                                            {3, "practice_3", "ЛЕВЫЙ", "THREE"},
                                                            {5, "practice_5", " жёлтый ", "FIVE"},
                                                            {0xFFFF, "practice_9_2", "BY KEY", "BY KEY"}});
    const text::Translation referring[] = {{"practice_1", "{practice_4}"},
                                           {"practice_2", "\xE2\x96\xA0{practice_3:capital}"},
                                           {"practice_3", "{practice_5:upper}!"},
                                           {"practice_5", "{practice_2}"}};
    const text::Filled filled_refs = text::fill_missing_texts(pointers_to(with_references), referring);
    const auto refs_stand_in = indexed(with_references[9]), refs_some = indexed(with_references[19]);
    check(filled_refs.banks == (std::vector<size_t>{9, 19}) &&
              filled_refs.unresolved == (std::vector<std::string>{"practice_1"}) &&
              filled_refs.kept_english == (std::vector<std::string>{"practice_5", "practice_5"}),
          "text: references to records the banks lack, and those whose expanded markup differs, named");
    const std::string left = "\xE2\x96\xA0Левый"; // (■ and the record's text, a capital first letter only)
    check(refs_stand_in.size() == 5 && refs_stand_in[0].text == "TEXT 2" && refs_stand_in[0].key == "practice_1" &&
              refs_stand_in[1].text == left && refs_stand_in[1].header_hash == text::text_hash(left) &&
              refs_stand_in[1].count == 6 && refs_stand_in[2].text == "ЖЁЛТЫЙ!" &&
              refs_stand_in[3].text == "ENGLISH ONLY" && refs_some.size() == 4 && refs_some[1].text == left &&
              refs_some[2].text == "ЖЁЛТЫЙ!" && refs_some[3].text == "FIVE",
          "text: references expanded from the player's Russian records; English where one is missing or its markup "
          "differs");

    auto shuffled = part(Russian::kStandIn);
    std::swap(shuffled[2], shuffled[3]);
    check(text::fill_missing_texts(pointers_to(shuffled), {}).banks.empty(),
          "text: banks not in the languages' order stay");
    auto broken = part(Russian::kSome);
    put32(broken[9], 0x30, 1000); // table 1 runs past the bank
    check(text::fill_missing_texts(pointers_to(broken), {}).banks.empty(), "text: a bank whose index does not read stays");
}

// The markup a translation keeps, and the records' header hash (made-up texts).
void test_markup() {
    check(text::text_hash("") == 0 && text::text_hash("Q") == 0x51 && text::text_hash("Mug") == 0xB6C7 &&
              text::text_hash("Кот") == 0xD68B && text::text_hash("Ящик\nпуст") == 0x064B,
          "text: the header's hash of a text");
    const std::string code = "\xEF\xBF\xB4\xE8\x80\x81"; // U+FFF4 and its argument U+8001
    const std::string icon = "\xEE\x81\xA4";                // U+E064, a private-use icon
    check(text::markup("Mug " + code + "of\ntea " + icon + "!") == U"\uFFF4\u8001\n\uE064",
          "text: markup: a code with its argument, a line break, an icon, in order");
    check(text::markup("Press the X Button, then \xE2\x98\x86.") == U"\u00A2\u2606" &&
              text::markup("Жмите кнопку X, затем \xE2\x98\x86.") == text::markup("Press the X Button, then \xE2\x98\x86.") &&
              text::markup("Жмите \xE2\x98\x86, затем кнопку X.") != text::markup("Press the X Button, then \xE2\x98\x86."),
          "text: markup: button names as their icons, input symbols, in order");
    check(text::markup("Plain words [in brackets].") == U"", "text: markup: none in plain words");
    // a colour (U+FFF2) has two arguments, U+FFFF none: a translation must keep both halves
    const std::string colour = "\xEF\xBF\xB2\xEF\xBF\xBF\xEF\xBC\xA0"; // U+FFF2 U+FFFF U+FF20
    const std::string original = "Hat " + colour + "yellow" + code;
    check(text::markup(original) == U"\uFFF2\uFFFF\uFF20\uFFF4\u8001" &&
              text::markup("Шляпа " + colour + "жёлтая" + code) == text::markup(original),
          "text: markup: a colour with both its halves");
    check(text::markup("Шляпа \xEF\xBF\xB2\xEF\xBF\xBF" "жёлтая" + code) != text::markup(original) &&
              text::markup("Шляпа \xEF\xBF\xB2\xEF\xBF\xBF\xEF\xBF\xBF" "жёлтая" + code) != text::markup(original) &&
              text::markup("Шляпа \xEF\xBF\xB2\xEF\xBF\xBF\xEF\xBC\xA1" "жёлтая" + code) != text::markup(original),
          "text: markup: a colour's second half dropped or changed differs");
    check(text::markup("Hat " + colour) != text::markup("Шляпа \xEF\xBF\xB2\xEF\xBF\xBF") &&
              text::markup("Шляпа \xEF\xBF\xB2\xEF\xBF\xBF") == U"\uFFF2\uFFFF",
          "text: markup: a text ending after a colour's first half differs");
    check(text::markup("Mug\xEF\xBF\xBF" "a\n") == U"\uFFFF\n", "text: markup: U+FFFF takes no argument");

    // references to the player's Russian records: as they are (spaces at the ends dropped), in capitals, with
    // a capital first letter only; nothing when one is not well formed or names a record there is none of
    const std::map<std::string_view, std::string_view> records = {
        {"common_7", " Ёжик в тумане "}, {"Manu_12", "СТАРАЯ ЛАМПА"}, {"online_3", "Стул"}, {"common_8", "  "}};
    const auto record = [&](std::string_view key) -> std::optional<std::string_view> {
        const auto found = records.find(key);
        return found == records.end() ? std::nullopt : std::optional(found->second);
    };
    check(text::with_references("\xE2\x96\xA0{common_7}", record) == "\xE2\x96\xA0Ёжик в тумане" &&
              text::with_references(code + " {online_3:upper} " + code, record) == code + " СТУЛ " + code &&
              text::with_references("{Manu_12:capital} / {common_7:upper}", record) == "Старая лампа / ЁЖИК В ТУМАНЕ" &&
              text::with_references(code + "{common_7:capital}", record) == code + "Ёжик в тумане" &&
              text::with_references("Без ссылок.", record) == "Без ссылок.",
          "text: references expanded, in their case forms");
    check(!text::with_references("{common_9}", record) && !text::with_references("{common_8}", record) &&
              !text::with_references("{common_7", record) && !text::with_references("common_7}", record) &&
              !text::with_references("a} {common_7}", record) && !text::with_references("{common_7:bold}", record) &&
              !text::with_references("{common 7}", record) && !text::with_references("{}", record),
          "text: a reference to a record there is none of, an empty one, or one not well formed: nothing");

    // our Russian table: keys of a part's records, each once, texts without the icons' code points, references
    // well formed
    std::set<std::string_view> keys;
    bool well_formed = !text::russian_texts().empty();
    const auto any_record = [](std::string_view) -> std::optional<std::string_view> { return "Слово"; };
    for (const text::Translation& t : text::russian_texts()) {
        const size_t underscore = t.key.find('_');
        well_formed = well_formed && underscore != std::string_view::npos && underscore > 0 && !t.text.empty() &&
                      keys.insert(t.key).second && text::with_references(t.text, any_record).has_value();
        for (const char32_t c : {text::kRightButton, text::kBottomButton, text::kTopButton, text::kLeftButton,
                                 text::kStartButton, text::kSelectButton, text::kPad}) {
            std::string utf8;
            if (c < 0x800) utf8 = {static_cast<char>(0xC0 | (c >> 6)), static_cast<char>(0x80 | (c & 0x3F))};
            else utf8 = {static_cast<char>(0xE0 | (c >> 12)), static_cast<char>(0x80 | ((c >> 6) & 0x3F)),
                         static_cast<char>(0x80 | (c & 0x3F))};
            well_formed = well_formed && t.text.find(utf8) == std::string_view::npos;
        }
    }
    check(well_formed,
          "text: our Russian texts by key, each once, none with an icon's code point, references well formed");
}


// The code points of UTF-8 text.
std::u32string code_points(std::string_view utf8) {
    std::u32string out;
    for (size_t i = 0; i < utf8.size();) {
        const auto b = static_cast<unsigned char>(utf8[i]);
        const size_t n = b < 0x80 ? 1 : b < 0xE0 ? 2 : b < 0xF0 ? 3 : 4;
        char32_t c = n == 1 ? b : b & (0x3F >> (n - 1));
        for (size_t k = 1; k < n && i + k < utf8.size(); ++k) c = c << 6 | (static_cast<unsigned char>(utf8[i + k]) & 0x3F);
        out += c;
        i += n;
    }
    return out;
}

// Table 1's word of a bank's record i (number << 16, line count << 4, low bits).
uint32_t word_of(const std::vector<uint8_t>& bank, size_t i) { return get32(bank, 0x40 + 16 * i); }

// Polish over the English banks (made-up texts): by key, else by the same English text, else English; markup
// checked with the line breaks aside, table 1's line count the new text's.
void test_polish_texts() {
    std::vector<std::vector<uint8_t>> banks = three_parts();
    const std::vector<std::vector<uint8_t>> before = banks;
    const text::Translation ours[] = {{"practice_1", "Pierwsze\nsłowo"},       // (its English: one line)
                                      {"practice_2", "Wciśnij przycisk A."},   // (its English names no button)
                                      {"practice_5", "PIĘĆ"},
                                      {"practice_9_2", "Według klucza"}};
    const text::Filled filled = text::put_polish(pointers_to(banks), ours);
    check(filled.banks == (std::vector<size_t>{1, 11, 21}) &&
              filled.kept_english == (std::vector<std::string>{"practice_2", "practice_2", "practice_2"}),
          "polish: the English banks only, those whose markup differs named");
    const auto english = indexed(banks[1]);
    check(english.size() == 5 && english[0].text == "Pierwsze\nsłowo" && english[0].english == "TEXT" &&
              english[0].key == "practice_1" && english[1].text == "ENGLISH" && english[2].text == "Pierwsze\nsłowo" &&
              english[2].key == "practice_3" && english[3].text == "PIĘĆ" && english[4].text == "Według klucza" &&
              english[4].number == 0xFFFF,
          "polish: ours by key, by another key's same English text, English where the markup differs");
    check(english.size() == 5 && english[0].header_hash == text::text_hash("Pierwsze\nsłowo") &&
              english[0].count == 14 && english[3].count == 4 && english[1].header_hash == 0x3412,
          "polish: a Polish record's header its text's, an English one's as it was");
    check(word_of(banks[1], 0) == (1u << 16 | 0x22) && word_of(banks[1], 1) == (2u << 16 | 0x12) &&
              word_of(banks[1], 3) == (5u << 16 | 0x12) && word_of(before[1], 0) == (1u << 16 | 0x12),
          "polish: table 1 counts the lines of the new text");
    bool others = true;
    for (size_t i = 0; i < banks.size(); ++i) {
        if (i != 1 && i != 11 && i != 21) others = others && banks[i] == before[i];
    }
    check(others && indexed(banks[11]).size() == 5 && indexed(banks[11])[3].text == "PIĘĆ",
          "polish: the other languages' banks stay; every part's English bank gets it");
    std::vector<std::vector<uint8_t>> untouched = three_parts();
    check(text::put_polish(pointers_to(untouched), {}).banks.empty() && untouched == before,
          "polish: no texts, no change");
    // a pin (no text): that record stays English, takes no other key's text of its English text and gives none
    const auto english_before = indexed(before[1]);
    std::vector<std::vector<uint8_t>> pinned = three_parts(), pin_first = three_parts();
    const text::Translation later_pinned[] = {{"practice_1", "Pierwsze"}, {"practice_3", ""}};
    const text::Translation first_pinned[] = {{"practice_1", ""}, {"practice_3", "Trzecie"}};
    text::put_polish(pointers_to(pinned), later_pinned);
    text::put_polish(pointers_to(pin_first), first_pinned);
    const auto a = indexed(pinned[1]), b = indexed(pin_first[1]);
    check(english_before.size() == 5 && english_before[0].text == english_before[2].text && a.size() == 5 &&
              a[0].text == "Pierwsze" && a[2].text == english_before[2].text && b.size() == 5 &&
              b[0].text == english_before[0].text && b[2].text == "Trzecie",
          "polish: a pinned record stays English, the other of its English text takes its own");

    // Polish button names are the buttons' icons, as the English ones are
    check(text::markup("Wciśnij przycisk A, potem krzyżakiem wybierz.") ==
                  text::markup("Press the A Button, then choose with the +Control Pad.") &&
              text::markup("Przytrzymaj przycisk +.") == text::markup("Hold the + Button.") &&
              text::markup("Użyj przycisków A, B, X i Y.") == text::markup("Use the A, B, X, and Y Buttons.") &&
              text::markup("Przycisku Aby") == U"" && text::markup("krzyżaki") == U"",
          "polish: button names as icons, whole words only");
    std::vector<uint8_t> named = make_bank({{"common_1", "Wciśnij przycisk B lub krzyżak.", "Press"}});
    check(text::show_button_icons(named) == 1 && texts(named)[0].first == "Wciśnij ¥ lub ».",
          "polish: their icons in a bank");

    // the table: keys of a part's records, each once, Polish texts (or none: a pin) without the icons' code points
    // (the carriers, the plain font's boxes, ideographs) nor typographic quotes, dashes, ellipses or braces, but as a
    // control code's argument
    std::set<std::string_view> keys;
    bool well_formed = true;
    for (const text::Translation& t : text::polish_texts()) {
        const size_t underscore = t.key.find('_');
        well_formed = well_formed && underscore != std::string_view::npos && underscore > 0 && keys.insert(t.key).second;
        size_t arguments = 0;
        for (const char32_t c : code_points(t.text)) {
            if (arguments > 0) {
                --arguments;
                continue;
            }
            if (c >= 0xFFF0 && c <= 0xFFFE) arguments = c == 0xFFF2 ? 2 : 1;
            const bool icon = c == text::kRightButton || c == text::kBottomButton || c == text::kTopButton ||
                              c == text::kLeftButton || c == text::kStartButton || c == text::kSelectButton ||
                              c == text::kPad || c == 0x00DE || c == 0x0152 || c == 0x0158 || c == 0x00DD ||
                              (c >= 0x3400 && c < 0xE000);
            const bool typographic = c == U'\u00AB' || c == U'\u201E' || c == U'\u201D' || c == U'\u201C' ||
                                     c == U'\u2018' || c == U'\u2019' || c == U'\u2026' || c == U'\u2013' ||
                                     c == U'\u2014';
            well_formed = well_formed && !icon && !typographic && c != U'{' && c != U'}';
        }
    }
    check(well_formed, "polish: our Polish texts by key, each once, none with an icon's code point");
}

// A timed subtitle line (show and hide frames as code points below U+0800, then the words).
std::string timed(const std::string& words, char32_t show, char32_t hide) {
    const auto utf8 = [](char32_t c) {
        return c < 0x80 ? std::string(1, static_cast<char>(c))
                        : std::string{static_cast<char>(0xC0 | (c >> 6)), static_cast<char>(0x80 | (c & 0x3F))};
    };
    return "\xEF\xBF\xBB" + utf8(show) + "\xEF\xBF\xBC" + utf8(hide) + "\xEF\xBF\xB5\x01" + words +
           "\xEF\xBF\xBB\x01\xEF\xBF\xBC\xEF\xBF\xBF";
}

// A table (a u32 count, then {offset, size} pairs) of `parts`, each 16-aligned after it; one of `use` per entry
// (shared parts share their bytes).
std::vector<uint8_t> table_of(const std::vector<std::vector<uint8_t>>& parts, const std::vector<size_t>& use) {
    std::vector<uint8_t> out(4 + 8 * use.size(), 0);
    put32(out, 0, static_cast<uint32_t>(use.size()));
    out.resize(to16(out.size()), 0);
    std::vector<size_t> at;
    for (const auto& p : parts) {
        at.push_back(out.size());
        out.insert(out.end(), p.begin(), p.end());
        out.resize(to16(out.size()), 0);
    }
    for (size_t i = 0; i < use.size(); ++i) {
        put32(out, 4 + 8 * i, static_cast<uint32_t>(at[use[i]]));
        put32(out, 8 + 8 * i, static_cast<uint32_t>(parts[use[i]].size()));
    }
    return out;
}

// The parts of a table (table_of's inverse).
std::vector<std::vector<uint8_t>> parts_of(const std::vector<uint8_t>& t) {
    std::vector<std::vector<uint8_t>> out;
    for (size_t i = 0, n = get32(t, 0); i < n; ++i) {
        const size_t at = get32(t, 4 + 8 * i), size = get32(t, 8 + 8 * i);
        out.emplace_back(t.begin() + static_cast<ptrdiff_t>(at), t.begin() + static_cast<ptrdiff_t>(at + size));
    }
    return out;
}

// A line's container: a bank per entry (16), the title's own way (each its own, " " from 10 on) or an added
// fighter's (English, French and maybe Polish of its own, the others English's).
std::vector<uint8_t> line_container(const std::vector<std::string>& english, bool added, const std::string& polish) {
    std::vector<std::vector<uint8_t>> banks;
    std::vector<size_t> use;
    const auto bank = [](uint8_t entry, const std::vector<std::string>& lines) {
        std::vector<Numbered> records;
        for (size_t k = 0; k < lines.size(); ++k) records.push_back({static_cast<uint32_t>(k), "", lines[k], ""});
        return make_indexed(static_cast<uint8_t>(entry + 1), records);
    };
    if (!added) {
        for (uint8_t e = 0; e < 16; ++e) {
            banks.push_back(bank(e, e == 1 ? english : e >= 10 ? std::vector<std::string>{" "}
                                                               : std::vector<std::string>{timed("Autre", 'A', 'Z')}));
            use.push_back(e);
        }
        return table_of(banks, use);
    }
    banks = {bank(1, english), bank(3, {timed("Ligne", 'A', 'Z')})};
    if (!polish.empty()) banks.push_back(bank(subtitles::kPolishEntry, {timed(polish, 'B', 'Y')}));
    for (size_t e = 0; e < 16; ++e) use.push_back(e == 3 ? 1 : e == subtitles::kPolishEntry && !polish.empty() ? 2 : 0);
    return table_of(banks, use);
}

void test_subtitles() {
    const std::vector<std::vector<uint8_t>> lines = {
        line_container({timed("Hello there", '@', 0x90)}, false, ""),                         // 0: the title's
        {0xFF, 0xFF, 0xFF, 0xFF},                                                             // 1: empty
        line_container({timed("Morning", '@', 'p')}, true, "Dzień dobry"),                    // 2: added, Polish
        line_container({timed("Evening", '@', 'p')}, true, ""),                               // 3: added, no Polish
        line_container({timed("First", 'A', 'B'), timed("then second", 'C', 0xC0)}, false, ""), // 4: two texts
        line_container({timed("Not ours", 'A', 'B')}, false, ""),                             // 5: none of ours
    };
    const std::vector<uint8_t> file = table_of(lines, {0, 1, 2, 3, 4, 5});
    const subtitles::Line ours[] = {{"0", "Cześć"}, {"4.1", "a potem drugi"}, {"9", "Nikt"}};
    const auto polish = subtitles::in_polish(file, ours);
    check(polish && polish->ours == 2 && polish->added == 1, "subtitles: ours in two lines, an added fighter's own");
    if (!polish) return;
    const auto entries = parts_of(polish->file);
    const auto bank_of = [](const std::vector<uint8_t>& container, size_t entry) { return parts_of(container)[entry]; };
    const auto text_of = [&](size_t line, size_t entry, size_t k) {
        const auto records = indexed(bank_of(entries[line], entry));
        return k < records.size() ? records[k].text : std::string("?");
    };
    check(entries.size() == 6 && text_of(0, 1, 0) == timed("Cześć", '@', 0x90) &&
              indexed(bank_of(entries[0], 1))[0].header_hash == text::text_hash(timed("Cześć", '@', 0x90)),
          "subtitles: the title's line in our Polish, with its English timing");
    bool kept = entries.size() == 6;
    for (size_t e = 0; kept && e < 16; ++e) kept = e == 1 || bank_of(entries[0], e) == bank_of(lines[0], e);
    check(kept && entries[1] == lines[1] && entries[3] == lines[3] && entries[5] == lines[5],
          "subtitles: the line's other languages, an empty line, an added fighter's without Polish, lines without "
          "ours stay");
    check(text_of(2, 1, 0) == timed("Dzień dobry", 'B', 'Y') && text_of(2, 3, 0) == timed("Ligne", 'A', 'Z'),
          "subtitles: an added fighter's own Polish (entry 10) shown for English");
    check(text_of(4, 1, 0) == timed("First", 'A', 'B') && text_of(4, 1, 1) == timed("a potem drugi", 'C', 0xC0),
          "subtitles: a line's second text by its key");
    std::vector<uint8_t> broken = file;
    put32(broken, 8 + 8 * 2, 1u << 30); // an entry past the file's end
    check(!subtitles::in_polish(broken, ours) && !subtitles::in_polish({1, 2}, ours),
          "subtitles: a file not as described: nothing");
    const auto only_added = subtitles::in_polish(file, {});
    check(only_added && only_added->ours == 0 && only_added->added == 1 && parts_of(only_added->file)[0] == lines[0],
          "subtitles: without ours, only the added fighters' own");

    // the Fight Lab story's file: a movie's lines in one bank, English's empty where its picture has the words
    const std::vector<std::vector<uint8_t>> movies = {
        line_container({timed("", 'A', 'B'), timed("Spoken", 'C', 'D'), timed("Not ours", 'E', 'F')}, false, ""),
        line_container({timed("Later", 'G', 'H')}, false, "")};
    const subtitles::Line story[] = {{"0", "NAPIS"}, {"0.1", "Mówione"}, {"1", "Potem"}};
    const auto in_polish = subtitles::in_polish(table_of(movies, {0, 1}), story);
    const auto movie = [&](size_t m, size_t k) {
        const auto records = in_polish ? indexed(parts_of(parts_of(in_polish->file)[m])[1]) : std::vector<Numbered>{};
        return k < records.size() ? records[k].text : std::string("?");
    };
    check(in_polish && in_polish->ours == 2 && movie(0, 0) == timed("NAPIS", 'A', 'B') &&
              movie(0, 1) == timed("Mówione", 'C', 'D') && movie(0, 2) == timed("Not ours", 'E', 'F') &&
              movie(1, 0) == timed("Potem", 'G', 'H'),
          "subtitles: the story's lines in ours, the empty ones (captions) too, with the English timing");
    // the tables: "N" / "N.k" keys, each once, a line of words (no control codes, no typographic quotes)
    bool well_formed = true;
    for (const auto table : {subtitles::polish_lines(), subtitles::story_lines()}) {
        std::set<std::string_view> keys;
        for (const subtitles::Line& l : table) {
            const bool key = !l.key.empty() && std::all_of(l.key.begin(), l.key.end(), [](char c) {
                return (c >= '0' && c <= '9') || c == '.';
            });
            well_formed = well_formed && key && keys.insert(l.key).second && !l.text.empty();
            for (const char32_t c : code_points(l.text)) {
                well_formed = well_formed && c >= 0x20 && c < 0xE000 && c != U'\u00AB' && c != U'\u201E' &&
                              c != U'\u201D' && c != U'\u2026' && c != U'\u2013';
            }
        }
    }
    check(well_formed && !subtitles::story_lines().empty(), "subtitles: our tables' keys and lines well formed");
}

void test_language() {
    const language::Text t = {"English", "Fran\xC3\xA7" "ais", nullptr, "", "Espa\xC3\xB1ol", "\xD0\xA0\xD1\x83\xD1\x81"};
    check(language::in(t, language::kEnglish) == "English" && language::in(t, language::kFrench) == "Français" &&
              language::in(t, language::kSpanish) == "Español" && language::in(t, language::kRussian) == "Рус",
          "language: a text in each language");
    check(language::in(t, language::kGerman) == "English" && language::in(t, language::kItalian) == "English" &&
              language::in(t, language::kPlaces) == "English",
          "language: English where one has none");
    const language::Text polish = {"Player", nullptr, nullptr, nullptr, nullptr, nullptr, "Gracz"};
    check(language::in(polish, language::kPolish) == "Gracz" && language::in(t, language::kPolish) == "English" &&
              language::place_of("pl") == language::kPolish,
          "language: Polish, the port's own, in its place");
    check(language::place_of("ru") == language::kRussian && language::place_of("de") == language::kGerman &&
              language::place_of("en") == language::kEnglish && language::place_of("ja") == language::kPlaces &&
              language::place_of("") == language::kPlaces,
          "language: the places of the launcher's codes");
    check(language::place() == language::kEnglish && language::in_current(t) == "English", "language: English until set");
    language::set(cafe::host::game::kLanguages[language::kFrench]);
    check(language::place() == language::kFrench && language::current().code == "fr" &&
              language::in_current(t) == "Français",
          "language: the language set");
    language::set(cafe::host::game::Language{"xx", "None", 99});
    check(language::place() == language::kEnglish, "language: one the game does not have is English");
    check(language::characters("Рус ok") == 6 && language::characters("") == 0, "language: characters of UTF-8");
}

// ------------------------------------------------------------------ the copyright line

void test_copyright_line() {
    // 14 words of white letters with a dark edge, two letters each.
    Rgba line = blank(700, 32);
    std::vector<uint32_t> starts;
    uint32_t x = 30;
    for (int word = 0; word < 14; ++word) {
        starts.push_back(x);
        for (int letter = 0; letter < 2; ++letter) {
            for (uint32_t yy = 8; yy < 24; ++yy) {
                for (uint32_t xx = x - 2; xx < x + 10; ++xx) {
                    uint8_t* p = line.at(xx, yy);
                    if (p[3] == 0) p[3] = 200; // the edge
                }
                for (uint32_t xx = x; xx < x + 8; ++xx) std::memset(line.at(xx, yy), 255, 4);
            }
            x += 10;
        }
        x += 12;
    }
    const auto out = title_screen::copyright_line(line);
    check(out && out->width == 700 && out->height == 32, "copyright line: made");
    if (!out) return;
    // Words left: 11 (the three before the last seven gone); centred.
    uint32_t left = 700, right = 0, runs = 0;
    bool inside = false;
    uint32_t gap = 0;
    for (uint32_t c = 0; c < 700; ++c) {
        const bool ink = out->at(c, 16)[0] == 255 && out->at(c, 16)[3] == 255;
        if (out->at(c, 16)[3] != 0) {
            left = std::min(left, c);
            right = c + 1;
        }
        if (ink) {
            if (!inside && gap >= 5) ++runs;
            if (!inside && runs == 0) runs = 1;
            inside = true;
            gap = 0;
        } else {
            inside = false;
            ++gap;
        }
    }
    check(runs == 11, "copyright line: three words fewer (" + std::to_string(runs) + ")");
    check(std::abs(static_cast<int>(left) - static_cast<int>(700 - right)) <= 1, "copyright line: centred");
    check(!title_screen::copyright_line(blank(700, 32)), "copyright line: none for a line without the words");
}

// ------------------------------------------------------------------ the logo

void test_logo() {
    // Only the Wii U still has the strokes the new subtitle is made from.
    check(!title_screen::logo(blank(1280, 720)), "logo: none for a still without the subtitle");
    check(!title_screen::logo(blank(640, 360)), "logo: none for another size");
}

// A menus' file (BX01) shaped like the title's Offline menu: name tables,
// a frame with the menu (its OnLoad script's two icon arrays, eight rows
// with an OnEnter script each), eight descriptions and eight values.
struct Bx {
    std::vector<uint8_t> d;
    void text(const std::string& t) {
        put_be32(d, static_cast<uint32_t>(t.size()));
        d.insert(d.end(), t.begin(), t.end());
        d.resize(d.size() + (-t.size() & 3));
    }
    // An element with its attributes (number, text) and `children` children to follow.
    void element(uint32_t tag, const std::string& t, std::vector<std::pair<uint32_t, std::string>> attributes,
                 uint32_t children) {
        put_be32(d, tag);
        text(t);
        put_be32(d, static_cast<uint32_t>(attributes.size()));
        for (const auto& [id, value] : attributes) {
            put_be32(d, id);
            text(value + '\0');
        }
        put_be32(d, children);
    }
    void table(std::vector<std::pair<uint32_t, std::string>> names) {
        put_be32(d, static_cast<uint32_t>(names.size()));
        std::string pool;
        for (const auto& [id, name] : names) {
            put_be32(d, static_cast<uint32_t>(pool.size()));
            put_be32(d, static_cast<uint32_t>(name.size() + 1));
            put_be32(d, id);
            pool += name + '\0';
        }
        d.insert(d.end(), pool.begin(), pool.end());
    }
};

std::string icon_script(bool size_field = true) {
    std::string code = "\x30\x00\x00\x02\x42\x01\x02"s;
    for (char v = 1; v <= 8; ++v) code += "\x02\x02\x00"s + v + "\x43\x01\x02"s;
    code += "\x4a\x00\x00\x03\x00\x00\x01"s;
    for (int i = 0; i < 8; ++i) code += "\x02\x02\x00\x09\x43\x01\x02"s;
    code += "\x4a\x00\x00\x04\x00\x00\x01"s;
    std::vector<uint8_t> s = {'x', 't', 'a', 'l', 1, 0, 0, 0};
    put_be32(s, static_cast<uint32_t>(code.size()));
    s.insert(s.end(), code.begin(), code.end());
    std::vector<uint8_t> tail(80, 0);
    if (size_field) tail[69] = static_cast<uint8_t>(code.size() - 1);
    s.insert(s.end(), tail.begin(), tail.end());
    return std::string(s.begin(), s.end());
}

// (`menu_last`: the menu after the statics, as a file laid out otherwise could have it)
std::vector<uint8_t> offline_menu(bool size_field = true, bool menu_last = false) {
    enum : uint32_t { kMenuData = 0, kFrame = 1, kMenu = 2, kItem = 3, kStatic = 4, kOnLoad = 100, kOnEnter = 104 };
    enum : uint32_t { kName = 0, kText = 4, kTextId = 5 };
    Bx b;
    b.d = {'B', 'X', '0', '1', 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1};
    b.element(kMenuData, "", {}, 1);
    b.element(kFrame, "", {{kName, "FrameMode002-01"}}, 17);
    const auto menu = [&] {
        b.element(kMenu, "", {{kName, "MenuMode002-01"}}, 9);
        b.element(kOnLoad, icon_script(size_field), {}, 0);
        const char* rows[] = {"ARCADE BATTLE", "GHOST BATTLE", "VS BATTLE", "TEAM BATTLE", "TIME ATTACK", "SURVIVAL", "PRACTICE", "PAIR PLAY"};
        for (int i = 0; i < 8; ++i) {
            b.element(kItem, "", {{kName, "MenuItemMode002-0" + std::to_string(i + 1)}, {kText, rows[i]}, {kTextId, "4," + std::to_string(26 + i)}}, 1);
            b.element(kOnEnter, "xtal ghost " + std::to_string(i), {}, 0);
        }
    };
    if (!menu_last) menu();
    for (int i = 0; i < 8; ++i)
        b.element(kStatic, "", {{kName, "StaticMode002-0" + std::to_string(i + 1)}, {kText, "description " + std::to_string(i + 1)}, {kTextId, "4," + std::to_string(34 + i)}}, 0);
    for (int i = 0; i < 8; ++i) b.element(kStatic, "", {{kName, "StaticValueMode002-0" + std::to_string(i + 1)}, {kText, ""}}, 0);
    if (menu_last) menu();
    const uint32_t tags = static_cast<uint32_t>(b.d.size());
    b.table({{kMenuData, "menudata"}, {kFrame, "frame"}, {kMenu, "menu"}, {kItem, "menuitemtext"}, {kStatic, "statictext"},
             {kOnLoad, "OnLoad"}, {kOnEnter, "OnEnter"}});
    const uint32_t attributes = static_cast<uint32_t>(b.d.size());
    b.table({{kName, "name"}, {kText, "text"}, {kTextId, "textid"}});
    for (int i = 0; i < 4; ++i) {
        b.d[8 + i] = static_cast<uint8_t>(tags >> (24 - 8 * i));
        b.d[12 + i] = static_cast<uint8_t>(attributes >> (24 - 8 * i));
    }
    return b.d;
}

void test_menudata() {
    const std::vector<uint8_t> file = offline_menu();
    const auto out = menudata::add_solo_ghost_row(file);
    check(out.has_value(), "menudata: the Offline menu gets its row");
    if (!out) return;
    const std::string_view o(reinterpret_cast<const char*>(out->data()), out->size());
    const auto at = [&](std::string_view s) { return o.find(s); };
    check(at("MenuItemMode002-02") < at("MenuItemMode002-09") && at("MenuItemMode002-09") < at("MenuItemMode002-03") &&
              at("MenuItemMode002-09") < at("SOLO GHOST BATTLE") && at("SOLO GHOST BATTLE") < o.find("xtal ghost 1", at("MenuItemMode002-09")),
          "menudata: the row is GHOST BATTLE's, below it, with its own label");
    check(o.find("4,27", at("MenuItemMode002-09")) > at("MenuItemMode002-03"), "menudata: the row's label is its own text");
    check(at("StaticMode002-02") < at("description 2") && at("description 2") < at("StaticMode002-03") &&
              at("StaticMode002-03") < at("one-on-one") && at("one-on-one") < at("StaticMode002-04") &&
              at("StaticMode002-04") < at("description 3") && at("StaticMode002-09") < at("description 8") &&
              at("StaticValueMode002-09") != std::string_view::npos,
          "menudata: the descriptions and values follow the rows' places");
    const std::string grown = [] {
        std::string s = icon_script();
        const uint32_t size = be32(reinterpret_cast<const uint8_t*>(&s[8]));
        std::string code = s.substr(12, size);
        const std::string ghost = "\x02\x02\x00\x02\x43\x01\x02"s, large = "\x02\x02\x00\x09\x43\x01\x02"s;
        code.insert(code.find(large) + 2 * 7, large);
        code.insert(code.find(ghost) + 7, ghost);
        std::string t = s.substr(12 + size);
        t[69] = static_cast<char>(size + 14 - 1);
        std::string h = s.substr(0, 12);
        h[11] = static_cast<char>(size + 14);
        return h + code + t;
    }();
    check(o.find(grown) != std::string_view::npos, "menudata: the icon arrays get the row's icons");
    check(be32(&(*out)[8]) == out->size() - (file.size() - be32(&file[8])) &&
              std::equal(file.begin() + be32(&file[8]), file.end(), out->begin() + be32(&(*out)[8])),
          "menudata: the name tables follow");
    check(!menudata::add_solo_ghost_row(*out), "menudata: no second row");
    check(!menudata::add_solo_ghost_row(offline_menu(false)), "menudata: a script not as expected leaves the menu");
    std::vector<uint8_t> cut(file.begin(), file.begin() + file.size() / 2);
    check(!menudata::add_solo_ghost_row(cut), "menudata: a cut file");
    std::vector<uint8_t> long_text = file;
    const size_t script = std::string_view(reinterpret_cast<const char*>(file.data()), file.size()).find("xtal ghost 3");
    long_text[script - 4] = 0x7F; // the script's length, past the file's end
    check(!menudata::add_solo_ghost_row(long_text), "menudata: a text longer than the file");
    const auto german = menudata::add_solo_ghost_row(file, language::kGerman);
    const auto russian = menudata::add_solo_ghost_row(file, language::kRussian);
    const auto has = [](const std::optional<std::vector<uint8_t>>& f, std::string_view s) {
        return f && std::string_view(reinterpret_cast<const char*>(f->data()), f->size()).find(s) != std::string_view::npos;
    };
    check(has(german, "SOLO-GEISTERKAMPF") && has(german, "ein Geist nach dem anderen") && !has(german, "SOLO GHOST BATTLE"),
          "menudata: the row in German");
    check(has(russian, "СОЛО-БОЙ С ПРИЗРАКАМИ") && has(russian, "один за другим"), "menudata: the row in Russian");
    const auto last = menudata::add_solo_ghost_row(offline_menu(true, true));
    check(last && std::string_view(reinterpret_cast<const char*>(last->data()), last->size()).find("MenuItemMode002-09") !=
                      std::string_view::npos,
          "menudata: the menu after the statics");
}

} // namespace

int main() {
    test_scramble();
    test_archive();
    test_bc();
    test_font();
    test_glyph_tables();
    test_draw();
    test_distance();
    test_pictures();
    test_text();
    test_missing_texts();
    test_markup();
    test_polish_texts();
    test_subtitles();
    test_language();
    test_copyright_line();
    test_logo();
    test_menudata();
    if (g_failures == 0) std::printf("title_test: all passed\n");
    return g_failures == 0 ? 0 : 1;
}
