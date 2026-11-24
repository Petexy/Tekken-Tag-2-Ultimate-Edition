#include "game_art.h"

#include <algorithm>
#include <array>
#include <fstream>
#include <system_error>

namespace launcher::game_art {

namespace {

std::uint32_t be32(std::string_view d, std::size_t at) {
    return static_cast<std::uint32_t>(static_cast<unsigned char>(d[at])) << 24 |
           static_cast<std::uint32_t>(static_cast<unsigned char>(d[at + 1])) << 16 |
           static_cast<std::uint32_t>(static_cast<unsigned char>(d[at + 2])) << 8 |
           static_cast<std::uint32_t>(static_cast<unsigned char>(d[at + 3]));
}
std::uint16_t be16(std::string_view d, std::size_t at) {
    return static_cast<std::uint16_t>(static_cast<unsigned char>(d[at]) << 8 | static_cast<unsigned char>(d[at + 1]));
}
std::uint16_t le16(const unsigned char* p) { return static_cast<std::uint16_t>(p[0] | p[1] << 8); }
std::uint32_t le32(const unsigned char* p) {
    return static_cast<std::uint32_t>(p[0]) | static_cast<std::uint32_t>(p[1]) << 8 |
           static_cast<std::uint32_t>(p[2]) << 16 | static_cast<std::uint32_t>(p[3]) << 24;
}

using Texel = std::array<std::uint8_t, 4>;

std::array<std::uint8_t, 3> rgb565(std::uint16_t c) {
    const unsigned r = c >> 11 & 31, g = c >> 5 & 63, b = c & 31;
    return {static_cast<std::uint8_t>(r << 3 | r >> 2), static_cast<std::uint8_t>(g << 2 | g >> 4),
            static_cast<std::uint8_t>(b << 3 | b >> 2)};
}

// A BC1 colour block's 16 texels; `four`: always the four-colour palette (BC2/BC3's colour block).
void colour_block(const unsigned char* p, bool four, Texel out[16]) {
    const std::uint16_t c0 = le16(p), c1 = le16(p + 2);
    const auto a = rgb565(c0), b = rgb565(c1);
    Texel pal[4];
    pal[0] = {a[0], a[1], a[2], 255};
    pal[1] = {b[0], b[1], b[2], 255};
    if (four || c0 > c1) {
        for (int k = 0; k < 3; ++k) {
            pal[2][k] = static_cast<std::uint8_t>((2 * a[k] + b[k] + 1) / 3);
            pal[3][k] = static_cast<std::uint8_t>((a[k] + 2 * b[k] + 1) / 3);
        }
        pal[2][3] = pal[3][3] = 255;
    } else {
        for (int k = 0; k < 3; ++k) pal[2][k] = static_cast<std::uint8_t>((a[k] + b[k]) / 2);
        pal[2][3] = 255;
        pal[3] = {0, 0, 0, 0};
    }
    const std::uint32_t bits = le32(p + 4);
    for (int i = 0; i < 16; ++i) out[i] = pal[bits >> (2 * i) & 3];
}

// A BC4 block's 16 values (BC3's alpha).
void value_block(const unsigned char* p, std::uint8_t out[16]) {
    const unsigned a0 = p[0], a1 = p[1];
    unsigned v[8] = {a0, a1};
    if (a0 > a1) {
        for (unsigned k = 1; k < 7; ++k) v[k + 1] = ((7 - k) * a0 + k * a1 + 3) / 7;
    } else {
        for (unsigned k = 1; k < 5; ++k) v[k + 1] = ((5 - k) * a0 + k * a1 + 2) / 5;
        v[6] = 0;
        v[7] = 255;
    }
    std::uint64_t bits = 0;
    for (int k = 0; k < 6; ++k) bits |= static_cast<std::uint64_t>(p[2 + k]) << (8 * k);
    for (int i = 0; i < 16; ++i) out[i] = static_cast<std::uint8_t>(v[bits >> (3 * i) & 7]);
}

}  // namespace

std::optional<Image> decode_nut(std::string_view d) {
    if (d.size() < 0x10 + 0x30 || d.substr(0, 4) != "NTP3" || be16(d, 6) == 0) return std::nullopt;
    const std::size_t p = 0x10;
    const std::uint32_t data_size = be32(d, p + 8);
    const std::uint16_t header = be16(d, p + 12);
    const int format = static_cast<unsigned char>(d[p + 0x13]);
    const int w = be16(d, p + 0x14), h = be16(d, p + 0x16);
    const int block = format == 0 ? 8 : (format == 1 || format == 2) ? 16 : 0;
    if (!block || w <= 0 || h <= 0 || w > 4096 || h > 4096) return std::nullopt;
    const std::size_t bw = (static_cast<std::size_t>(w) + 3) / 4, bh = (static_cast<std::size_t>(h) + 3) / 4;
    const std::size_t need = bw * bh * static_cast<std::size_t>(block);
    if (data_size < need || p + header + need > d.size()) return std::nullopt;
    const auto* src = reinterpret_cast<const unsigned char*>(d.data() + p + header);
    Image img;
    img.w = w;
    img.h = h;
    img.rgba.assign(static_cast<std::size_t>(w) * static_cast<std::size_t>(h) * 4, 0);
    Texel t[16];
    std::uint8_t alpha[16];
    for (std::size_t by = 0; by < bh; ++by)
        for (std::size_t bx = 0; bx < bw; ++bx) {
            const unsigned char* b = src + (by * bw + bx) * static_cast<std::size_t>(block);
            if (format == 0) colour_block(b, false, t);
            else {
                colour_block(b + 8, true, t);
                if (format == 1)
                    for (int i = 0; i < 16; ++i) t[i][3] = static_cast<std::uint8_t>((b[i / 2] >> (4 * (i & 1)) & 15) * 17);
                else {
                    value_block(b, alpha);
                    for (int i = 0; i < 16; ++i) t[i][3] = alpha[i];
                }
            }
            for (int i = 0; i < 16; ++i) {
                const std::size_t x = bx * 4 + static_cast<std::size_t>(i % 4), y = by * 4 + static_cast<std::size_t>(i / 4);
                if (x >= static_cast<std::size_t>(w) || y >= static_cast<std::size_t>(h)) continue;
                std::copy(t[i].begin(), t[i].end(), img.rgba.begin() + static_cast<std::ptrdiff_t>((y * static_cast<std::size_t>(w) + x) * 4));
            }
        }
    return img;
}

std::optional<Image> read_nut(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    if (!in) return std::nullopt;
    in.seekg(0, std::ios::end);
    const std::streamoff size = in.tellg();
    if (size <= 0 || size > (64 << 20)) return std::nullopt;
    in.seekg(0);
    std::string data(static_cast<std::size_t>(size), '\0');
    if (!in.read(data.data(), size)) return std::nullopt;
    return decode_nut(data);
}

std::string ini_display_name(std::string_view line) {
    if (!line.empty() && line.back() == '\r') line.remove_suffix(1);
    if (!line.starts_with("# ")) return {};
    line.remove_prefix(2);
    const std::size_t from = line.rfind(", from ");
    return from == std::string_view::npos || from == 0 ? std::string() : std::string(line.substr(0, from));
}

std::vector<Pack> packs(const fs::path& folder) {
    std::vector<Pack> out;
    std::error_code ec;
    fs::directory_iterator it(folder, ec), end;
    for (; !ec && it != end; it.increment(ec)) {
        const fs::path dir = it->path();
        const std::string name = dir.filename().string();
        if (name.empty() || name[0] == '.' || !it->is_directory(ec)) continue;
        std::ifstream ini(dir / "character.ini");
        std::string line;
        if (!ini || !std::getline(ini, line)) continue;
        Pack p{dir, ini_display_name(line), {}};
        do {
            std::string_view v = line;
            if (!v.empty() && v.back() == '\r') v.remove_suffix(1);
            if (!v.starts_with("code")) continue;
            v.remove_prefix(4);
            while (!v.empty() && v.front() == ' ') v.remove_prefix(1);
            if (v.empty() || v.front() != '=') continue;
            v.remove_prefix(1);
            while (!v.empty() && v.front() == ' ') v.remove_prefix(1);
            while (!v.empty() && v.back() == ' ') v.remove_suffix(1);
            p.code = std::string(v);
            break;
        } while (std::getline(ini, line));
        if (!p.display.empty() || !p.code.empty()) out.push_back(std::move(p));
    }
    std::sort(out.begin(), out.end(), [](const Pack& a, const Pack& b) { return a.dir < b.dir; });
    return out;
}

fs::path portrait_file(const fs::path& pack) { return pack / "art" / "portrait_1p.nut"; }

}  // namespace launcher::game_art
