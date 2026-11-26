#include "ttt2ui/text.h"

#include <stb_truetype.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <unordered_map>

#include "ttt2_launcher_fonts.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <knownfolders.h>
#include <shlobj.h>
#endif

namespace ttt2::ui {

// ---- UTF-8 ---------------------------------------------------------------------------------------------------------

void decode_utf8(std::string_view s, std::vector<char32_t>& out, std::vector<std::uint32_t>* offsets) {
    out.clear();
    if (offsets) offsets->clear();
    const auto* p = reinterpret_cast<const unsigned char*>(s.data());
    const std::size_t n = s.size();
    std::size_t i = 0;
    while (i < n) {
        const std::size_t start = i;
        unsigned char b = p[i];
        char32_t c = 0xFFFD;
        int len = 1;
        if (b < 0x80) {
            c = b;
        } else if (b >= 0xC2 && b <= 0xDF) {
            len = 2;
        } else if (b >= 0xE0 && b <= 0xEF) {
            len = 3;
        } else if (b >= 0xF0 && b <= 0xF4) {
            len = 4;
        } else {
            len = 0;  // a stray continuation byte or an invalid lead: one U+FFFD for it
        }
        if (len >= 2) {
            if (i + len > n) {
                len = 0;
            } else {
                char32_t v = b & (len == 2 ? 0x1F : len == 3 ? 0x0F : 0x07);
                bool ok = true;
                for (int k = 1; k < len; ++k) {
                    if ((p[i + k] & 0xC0) != 0x80) {
                        ok = false;
                        break;
                    }
                    v = (v << 6) | (p[i + k] & 0x3F);
                }
                // Overlong forms, surrogates and values past U+10FFFF are invalid.
                if (ok && ((len == 3 && v < 0x800) || (len == 4 && (v < 0x10000 || v > 0x10FFFF)) ||
                           (v >= 0xD800 && v <= 0xDFFF)))
                    ok = false;
                if (ok) c = v;
                else len = 0;
            }
        }
        if (len == 0) {
            c = 0xFFFD;
            len = 1;
        }
        out.push_back(c);
        if (offsets) offsets->push_back(static_cast<std::uint32_t>(start));
        i += static_cast<std::size_t>(len);
    }
    if (offsets) offsets->push_back(static_cast<std::uint32_t>(n));
}

std::string encode_utf8(char32_t c) {
    std::string s;
    if (c < 0x80) {
        s += static_cast<char>(c);
    } else if (c < 0x800) {
        s += static_cast<char>(0xC0 | (c >> 6));
        s += static_cast<char>(0x80 | (c & 0x3F));
    } else if (c < 0x10000) {
        s += static_cast<char>(0xE0 | (c >> 12));
        s += static_cast<char>(0x80 | ((c >> 6) & 0x3F));
        s += static_cast<char>(0x80 | (c & 0x3F));
    } else {
        s += static_cast<char>(0xF0 | (c >> 18));
        s += static_cast<char>(0x80 | ((c >> 12) & 0x3F));
        s += static_cast<char>(0x80 | ((c >> 6) & 0x3F));
        s += static_cast<char>(0x80 | (c & 0x3F));
    }
    return s;
}

char32_t to_upper(char32_t c) {
    if (c >= 'a' && c <= 'z') return c - 32;
    if (c < 0x80) return c;
    if ((c >= 0xE0 && c <= 0xFE && c != 0xF7)) return c - 32;  // Latin-1
    if (c == 0xFF) return 0x178;
    if (c >= 0x100 && c <= 0x17F) {  // Latin Extended-A: pairs (mostly even = capital)
        if ((c >= 0x139 && c <= 0x148) || (c >= 0x179 && c <= 0x17E)) return (c % 2 == 0) ? c - 1 : c;
        if (c == 0x131) return 'I';
        return (c % 2 == 1) ? c - 1 : c;
    }
    if (c >= 0x3B1 && c <= 0x3C9 && c != 0x3C2) return c - 32;  // Greek
    if (c >= 0x430 && c <= 0x44F) return c - 32;                  // Cyrillic
    if (c >= 0x450 && c <= 0x45F) return c - 80;
    return c;
}

// ---- faces, atlas ----------------------------------------------------------------------------------------------

namespace {

constexpr char32_t kReplacement = 0xFFFD;
constexpr int kMaxPages = 8;

struct Face {
    std::string name;
    std::vector<unsigned char> owned;
    const unsigned char* data = nullptr;
    stbtt_fontinfo info{};
    int ascent = 0, descent = 0, gap = 0;
    bool ok = false;
};

bool init_face(Face& f, const unsigned char* data, int index) {
    f.data = data;
    const int offset = stbtt_GetFontOffsetForIndex(data, index);
    if (offset < 0 || !stbtt_InitFont(&f.info, data, offset)) return false;
    stbtt_GetFontVMetrics(&f.info, &f.ascent, &f.descent, &f.gap);
    f.ok = true;
    return true;
}

std::vector<unsigned char> read_file(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return {};
    in.seekg(0, std::ios::end);
    const auto size = static_cast<std::streamoff>(in.tellg());
    if (size <= 0 || size > (64 << 20)) return {};
    std::vector<unsigned char> data(static_cast<std::size_t>(size));
    in.seekg(0);
    in.read(reinterpret_cast<char*>(data.data()), size);
    if (!in) return {};
    return data;
}

std::filesystem::path path_from_utf8(const std::string& s) {
    return std::filesystem::path(std::u8string(s.begin(), s.end()));
}

float quantise(float px) {
    if (px < theme::kTextQuantSmallLimit)
        return std::max(1.f, std::round(px / theme::kTextQuantSmall) * theme::kTextQuantSmall);
    return std::round(px);
}

struct GlyphKey {
    int face;   // -1: our U+FFFD
    int px2;    // pixel size * 2
    int glyph;
    int outline2;  // outline width in pixels * 2 (0 = filled)
    bool operator==(const GlyphKey&) const = default;
};
struct GlyphKeyHash {
    std::size_t operator()(const GlyphKey& k) const {
        std::uint64_t h = static_cast<std::uint32_t>(k.face + 1);
        h = h * 1000003u ^ static_cast<std::uint32_t>(k.px2);
        h = h * 1000003u ^ static_cast<std::uint32_t>(k.glyph);
        h = h * 1000003u ^ static_cast<std::uint32_t>(k.outline2);
        return static_cast<std::size_t>(h);
    }
};
struct Glyph {
    int page = -1;
    int x = 0, y = 0, w = 0, h = 0;  // in the page (pixels)
    float x0 = 0, y0 = 0;            // from the pen position / baseline (pixels)
    float draw_w = 0;                // drawn width (pixels): w / oversampling
};
struct Page {
    TextureId texture = 0;
    int size = 0;
    int shelf_y = 0, shelf_h = 0, cursor_x = 0;
    std::uint64_t last_used = 0;
};

struct Placed {
    int face;  // -1: ours (U+FFFD)
    int glyph;
    float x;  // pixels from the run's start
};
struct Run {
    std::vector<Placed> glyphs;
    float width = 0;  // pixels
    float px = 0;
};

}  // namespace

struct TextEngine::Impl {
    TextureRegistry& textures;
    // Built-ins by theme::Font, then each role's Cyrillic face (theme::kCyrillicFiles), then fallbacks.
    std::vector<std::unique_ptr<Face>> faces;
    static constexpr int kRoles = static_cast<int>(theme::Font::Count);
    int builtin = 2 * kRoles;
    std::vector<std::string> extra_files;
    std::unordered_map<char32_t, int> fallback_for;
    std::unordered_map<std::string, int> face_by_file;
    std::unordered_map<GlyphKey, Glyph, GlyphKeyHash> glyphs;
    std::vector<Page> pages;
    std::uint64_t frame = 1;
    unsigned char gamma[256]{};
    std::unordered_map<std::string, Run> runs;
    std::unordered_map<std::string, std::vector<TextLine>> wraps;
    std::vector<char32_t> scratch;

    explicit Impl(TextureRegistry& t) : textures(t) {
        faces.resize(static_cast<std::size_t>(builtin));
        for (int i = 0; i < 256; ++i)
            gamma[i] = static_cast<unsigned char>(
                std::lround(255.0 * std::pow(i / 255.0, 1.0 / static_cast<double>(theme::kTextGamma))));
    }

    Face* face(int i) {
        if (i < 0 || i >= static_cast<int>(faces.size())) return nullptr;
        if (i < builtin && !faces[static_cast<std::size_t>(i)]) {
            auto f = std::make_unique<Face>();
            const char* name = i < kRoles ? theme::kFontFiles[i] : theme::kCyrillicFiles[i - kRoles];
            f->name = name ? name : "";
            if (const ttt2_fonts::File* file = name ? ttt2_fonts::find(name) : nullptr) init_face(*f, file->data, 0);
            faces[static_cast<std::size_t>(i)] = std::move(f);
        }
        Face* f = faces[static_cast<std::size_t>(i)].get();
        return f && f->ok ? f : nullptr;
    }

    int load_file(const std::string& utf8_path, int index = 0) {
        const std::string key = utf8_path + "#" + std::to_string(index);
        if (auto it = face_by_file.find(key); it != face_by_file.end()) return it->second;
        auto f = std::make_unique<Face>();
        f->name = utf8_path;
        f->owned = read_file(path_from_utf8(utf8_path));
        int result = -1;
        if (!f->owned.empty() && init_face(*f, f->owned.data(), index)) {
            faces.push_back(std::move(f));
            result = static_cast<int>(faces.size()) - 1;
        }
        face_by_file[key] = result;
        return result;
    }

    bool has(int i, char32_t c) {
        Face* f = face(i);
        return f && stbtt_FindGlyphIndex(&f->info, static_cast<int>(c)) != 0;
    }

    int system_face_for(char32_t c);

    // The face that draws `c` for a style whose own face is `primary` (-1: none has it).
    int pick(int primary, char32_t c, bool system) {
        if (c == kReplacement) return has(primary, c) ? primary : -1;
        if (has(primary, c)) return primary;
        // The role's Cyrillic face, then the other built-in families: Barlow (text) and JetBrains Mono (arrows,
        // symbols, box drawing).
        if (primary >= 0 && primary < kRoles && has(primary + kRoles, c)) return primary + kRoles;
        for (int alt : {static_cast<int>(theme::Font::Body), static_cast<int>(theme::Font::Mono)})
            if (alt != primary && has(alt, c)) return alt;
        for (int i = builtin; i < static_cast<int>(faces.size()); ++i)
            if (has(i, c)) return i;
        if (auto it = fallback_for.find(c); it != fallback_for.end()) return it->second;
        int found = -1;
        for (const std::string& file : extra_files) {
            int i = load_file(file);
            if (i >= 0 && has(i, c)) {
                found = i;
                break;
            }
        }
        if (found < 0 && system) found = system_face_for(c);
        fallback_for[c] = found;
        return found;
    }

    // Lay out a run (pixels) for a style at `px`.
    const Run& run(const TextStyle& style, float px, std::string_view text, bool system) {
        std::string key;
        key.reserve(text.size() + 24);
        char head[48];
        std::snprintf(head, sizeof head, "%d|%.2f|%.4f|%d|", static_cast<int>(style.font), static_cast<double>(px),
                      static_cast<double>(style.tracking), style.upper ? 1 : 0);
        key += head;
        key.append(text);
        if (auto it = runs.find(key); it != runs.end()) return it->second;
        if (runs.size() > 4096) runs.clear();
        Run r;
        r.px = px;
        decode_utf8(text, scratch);
        const int primary = static_cast<int>(style.font);
        const float tracking = style.tracking * px;
        float pen = 0;
        int prev_face = -2, prev_glyph = 0;
        for (char32_t c : scratch) {
            if (c == '\t') c = ' ';
            if (c < 0x20 || c == 0x7F || (c >= 0x80 && c < 0xA0)) continue;  // controls: nothing
            if (style.upper) c = to_upper(c);
            int fi = pick(primary, c, system);
            Placed g{fi, 0, 0};
            float advance = 0;
            if (fi >= 0) {
                Face* f = face(fi);
                const float s = stbtt_ScaleForMappingEmToPixels(&f->info, px);
                g.glyph = stbtt_FindGlyphIndex(&f->info, static_cast<int>(c));
                if (fi == prev_face)
                    pen += s * static_cast<float>(stbtt_GetGlyphKernAdvance(&f->info, prev_glyph, g.glyph));
                int adv = 0, lsb = 0;
                stbtt_GetGlyphHMetrics(&f->info, g.glyph, &adv, &lsb);
                advance = s * static_cast<float>(adv);
            } else {
                g.glyph = static_cast<int>(kReplacement);
                advance = std::round(px * .72f) + px * .1f;
            }
            if (!r.glyphs.empty()) pen += tracking;
            g.x = pen;
            pen += advance;
            r.glyphs.push_back(g);
            prev_face = fi;
            prev_glyph = g.glyph;
        }
        r.width = pen;
        return runs.emplace(std::move(key), std::move(r)).first->second;
    }

    // ---- the atlas
    bool place(int w, int h, int& page_index, int& x, int& y, float scale) {
        const int size = scale > 1.5f ? 2048 : 1024;
        auto try_page = [&](Page& p) {
            if (p.cursor_x + w + 1 > p.size) {
                p.shelf_y += p.shelf_h + 1;
                p.shelf_h = 0;
                p.cursor_x = 0;
            }
            if (p.shelf_y + h + 1 > p.size || w + 1 > p.size) return false;
            x = p.cursor_x + 1;
            y = p.shelf_y + 1;
            p.cursor_x += w + 1;
            p.shelf_h = std::max(p.shelf_h, h + 1);
            return true;
        };
        if (!pages.empty() && pages.back().size == size && try_page(pages.back())) {
            page_index = static_cast<int>(pages.size()) - 1;
            return true;
        }
        // A new page, or the least recently used one (not used this frame) emptied for it.
        int reuse = -1;
        if (static_cast<int>(pages.size()) >= kMaxPages) {
            std::uint64_t oldest = frame;
            for (int i = 0; i < static_cast<int>(pages.size()); ++i)
                if (pages[static_cast<std::size_t>(i)].last_used < oldest) {
                    oldest = pages[static_cast<std::size_t>(i)].last_used;
                    reuse = i;
                }
        }
        if (reuse >= 0) {
            for (auto it = glyphs.begin(); it != glyphs.end();)
                it = it->second.page == reuse ? glyphs.erase(it) : std::next(it);
            Page& p = pages[static_cast<std::size_t>(reuse)];
            textures.destroy(p.texture);
            p = Page{};
            p.size = size;
            p.texture =
                textures.create_alpha(size, size, std::vector<std::uint8_t>(static_cast<std::size_t>(size) * size));
            // (Moved to the end so that it is the page new glyphs go into.)
            std::swap(pages[static_cast<std::size_t>(reuse)], pages.back());
            for (auto& [k, g] : glyphs)
                if (g.page == static_cast<int>(pages.size()) - 1) g.page = reuse;
        } else {
            Page p;
            p.size = size;
            p.texture =
                textures.create_alpha(size, size, std::vector<std::uint8_t>(static_cast<std::size_t>(size) * size));
            pages.push_back(p);
        }
        page_index = static_cast<int>(pages.size()) - 1;
        return try_page(pages.back());
    }

    const Glyph* bake(const GlyphKey& key, float scale) {
        if (auto it = glyphs.find(key); it != glyphs.end()) {
            if (it->second.page >= 0) pages[static_cast<std::size_t>(it->second.page)].last_used = frame;
            return &it->second;
        }
        const float px = static_cast<float>(key.px2) / 2;
        std::vector<std::uint8_t> bitmap;
        Glyph g;
        int w = 0, h = 0;
        if (key.face < 0) {
            // U+FFFD as a diamond with a question mark cut out of it (the built-in faces have no U+FFFD).
            const int d = std::max(4, static_cast<int>(std::lround(px * .72f)));
            w = h = d;
            bitmap.assign(static_cast<std::size_t>(d) * d, 0);
            const float r = static_cast<float>(d) / 2;
            for (int y = 0; y < d; ++y)
                for (int x = 0; x < d; ++x) {
                    float dist =
                        std::fabs(static_cast<float>(x) + .5f - r) + std::fabs(static_cast<float>(y) + .5f - r);
                    bitmap[static_cast<std::size_t>(y) * d + x] =
                        static_cast<std::uint8_t>(std::lround(255 * clamp01(r - dist + .5f)));
                }
            if (Face* f = face(static_cast<int>(theme::Font::BodyBold))) {
                const float s = stbtt_ScaleForMappingEmToPixels(&f->info, px * .62f);
                int qx0, qy0, qx1, qy1;
                stbtt_GetCodepointBitmapBox(&f->info, '?', s, s, &qx0, &qy0, &qx1, &qy1);
                const int qw = qx1 - qx0, qh = qy1 - qy0;
                if (qw > 0 && qh > 0 && qw <= d && qh <= d) {
                    std::vector<std::uint8_t> q(static_cast<std::size_t>(qw) * qh);
                    stbtt_MakeCodepointBitmap(&f->info, q.data(), qw, qh, qw, s, s, '?');
                    const int ox = (d - qw) / 2, oy = (d - qh) / 2;
                    for (int y = 0; y < qh; ++y)
                        for (int x = 0; x < qw; ++x) {
                            auto& v = bitmap[static_cast<std::size_t>(y + oy) * d + x + ox];
                            v = static_cast<std::uint8_t>(std::max(0, v - q[static_cast<std::size_t>(y) * qw + x]));
                        }
                }
            }
            g.x0 = std::round(px * .05f);
            g.y0 = -std::round(px * .7f);
            g.draw_w = static_cast<float>(w);
        } else {
            Face* f = face(key.face);
            const float s = stbtt_ScaleForMappingEmToPixels(&f->info, px);
            if (key.outline2 > 0) {
                const float width = static_cast<float>(key.outline2) / 2;
                const int pad = static_cast<int>(std::ceil(width)) + 2;
                int xoff = 0, yoff = 0;
                unsigned char* sdf = stbtt_GetGlyphSDF(&f->info, s, key.glyph, pad, 128,
                                                       128.f / static_cast<float>(pad), &w, &h, &xoff, &yoff);
                if (sdf) {
                    bitmap.resize(static_cast<std::size_t>(w) * h);
                    for (std::size_t i = 0; i < bitmap.size(); ++i) {
                        const float dist = (static_cast<float>(sdf[i]) - 128) * static_cast<float>(pad) / 128;
                        bitmap[i] = static_cast<std::uint8_t>(
                            std::lround(255 * clamp01(width / 2 + .5f - std::fabs(dist))));
                    }
                    stbtt_FreeSDF(sdf, nullptr);
                }
                g.x0 = static_cast<float>(xoff);
                g.y0 = static_cast<float>(yoff);
                g.draw_w = static_cast<float>(w);
            } else {
                const int ox = px <= theme::kTextOversampleLimit ? 2 : 1;
                int x0, y0, x1, y1;
                stbtt_GetGlyphBitmapBoxSubpixel(&f->info, key.glyph, s * static_cast<float>(ox), s, 0, 0, &x0, &y0, &x1,
                                                &y1);
                w = x1 - x0 + (ox - 1);
                h = y1 - y0;
                if (w > 0 && h > 0) {
                    bitmap.assign(static_cast<std::size_t>(w) * h, 0);
                    float sub_x = 0, sub_y = 0;
                    stbtt_MakeGlyphBitmapSubpixelPrefilter(&f->info, bitmap.data(), w, h, w, s * static_cast<float>(ox),
                                                           s, 0, 0, ox, 1, &sub_x, &sub_y, key.glyph);
                    g.x0 = static_cast<float>(x0) / static_cast<float>(ox) + sub_x;
                    g.y0 = static_cast<float>(y0);
                    g.draw_w = static_cast<float>(w) / static_cast<float>(ox);
                }
            }
        }
        if (w <= 0 || h <= 0 || bitmap.empty()) {
            g.page = -1;  // (a space)
            return &glyphs.emplace(key, g).first->second;
        }
        for (auto& v : bitmap) v = gamma[v];
        int page = -1, x = 0, y = 0;
        if (!place(w, h, page, x, y, scale)) {
            g.page = -1;
            return &glyphs.emplace(key, g).first->second;
        }
        textures.update_alpha(pages[static_cast<std::size_t>(page)].texture, x, y, w, h, bitmap.data(), w);
        pages[static_cast<std::size_t>(page)].last_used = frame;
        g.page = page;
        g.x = x;
        g.y = y;
        g.w = w;
        g.h = h;
        return &glyphs.emplace(key, g).first->second;
    }
};

// ---- system fallback faces -------------------------------------------------------------------------------------

int TextEngine::Impl::system_face_for(char32_t c) {
#ifdef _WIN32
    static std::vector<std::string> candidates;
    static bool listed = false;
    auto to_utf8 = [](const std::wstring& w) {
        int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, nullptr, 0, nullptr, nullptr);
        std::string s(n > 0 ? static_cast<std::size_t>(n - 1) : 0, '\0');
        if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, s.data(), n, nullptr, nullptr);
        return s;
    };
    if (!listed) {
        listed = true;
        std::vector<std::wstring> dirs;
        PWSTR fonts = nullptr;
        if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_Fonts, 0, nullptr, &fonts)) && fonts) dirs.emplace_back(fonts);
        if (fonts) CoTaskMemFree(fonts);
        wchar_t local[MAX_PATH];
        DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH);
        if (n > 0 && n < MAX_PATH) dirs.push_back(std::wstring(local) + L"\\Microsoft\\Windows\\Fonts");
        static const wchar_t* kPreferred[] = {L"segoeui.ttf", L"seguisym.ttf", L"YuGothR.ttc", L"msgothic.ttc",
                                             L"msyh.ttc",    L"malgun.ttf",   L"Nirmala.ttf", L"simsun.ttc",
                                             L"tahoma.ttf",  L"arial.ttf",    L"ebrima.ttf",  L"gadugi.ttf"};
        for (const std::wstring& d : dirs) {
            for (const wchar_t* name : kPreferred) {
                std::error_code ec;
                std::filesystem::path p = std::filesystem::path(d) / name;
                if (std::filesystem::is_regular_file(p, ec)) candidates.push_back(to_utf8(p.wstring()));
            }
        }
        // Per-user fonts (installed without admin rights) after the known ones.
        if (dirs.size() > 1) {
            std::error_code ec;
            for (const auto& e : std::filesystem::directory_iterator(dirs.back(), ec)) {
                std::wstring ext = e.path().extension().wstring();
                for (auto& ch : ext) ch = static_cast<wchar_t>(towlower(ch));
                if (ext == L".ttf" || ext == L".ttc" || ext == L".otf")
                    candidates.push_back(to_utf8(e.path().wstring()));
            }
        }
    }
    for (const std::string& file : candidates) {
        int i = load_file(file);
        if (i >= 0 && has(i, c)) return i;
    }
    return -1;
#else
    // fontconfig's best match for the character (a face is accepted only when stb_truetype can read it and it has
    // the character: e.g. CFF2 variable fonts are not).
    char command[96];
    std::snprintf(command, sizeof command, "fc-match -f '%%{file}\\n%%{index}' ':charset=%x' 2>/dev/null",
                  static_cast<unsigned>(c));
    FILE* pipe = popen(command, "r");
    if (!pipe) return -1;
    std::string out;
    char buffer[512];
    std::size_t n;
    while ((n = std::fread(buffer, 1, sizeof buffer, pipe)) > 0) out.append(buffer, n);
    pclose(pipe);
    const std::size_t nl = out.find('\n');
    const std::string file = out.substr(0, nl);
    int index = nl == std::string::npos ? 0 : std::atoi(out.c_str() + nl + 1);
    if (file.empty()) return -1;
    int i = load_file(file, index);
    return i >= 0 && has(i, c) ? i : -1;
#endif
}

// ---- the engine ------------------------------------------------------------------------------------------------

TextEngine::TextEngine(TextureRegistry& textures) : impl_(std::make_unique<Impl>(textures)) {}
TextEngine::~TextEngine() = default;

void TextEngine::set_scale(float scale) {
    if (scale > 0 && scale != scale_) {
        scale_ = scale;
        impl_->wraps.clear();
    }
}

bool TextEngine::add_fallback_file(const std::string& path) {
    if (impl_->load_file(path) < 0) return false;
    impl_->extra_files.push_back(path);
    impl_->fallback_for.clear();
    return true;
}

void TextEngine::begin_frame() {
    ++impl_->frame;
    if (impl_->wraps.size() > 2048) impl_->wraps.clear();
}

float TextEngine::width(const TextStyle& style, std::string_view text) {
    const float px = quantise(style.size * scale_);
    return impl_->run(style, px, text, system_fallback_).width / scale_;
}

float TextEngine::ascent(const TextStyle& style) {
    Face* f = impl_->face(static_cast<int>(style.font));
    const float px = quantise(style.size * scale_);
    if (!f) return style.size * .8f;
    const float s = stbtt_ScaleForMappingEmToPixels(&f->info, px);
    const float asc = s * static_cast<float>(f->ascent), desc = -s * static_cast<float>(f->descent);
    const float lh = style.size * style.line_height * scale_;
    return std::round((lh - (asc + desc)) / 2 + asc) / scale_;
}

float TextEngine::cap_height(const TextStyle& style) {
    Face* f = impl_->face(static_cast<int>(style.font));
    if (!f) return style.size * .7f;
    int x0, y0, x1, y1;
    if (!stbtt_GetCodepointBox(&f->info, 'H', &x0, &y0, &x1, &y1)) return style.size * .7f;
    return stbtt_ScaleForMappingEmToPixels(&f->info, style.size) * static_cast<float>(y1);
}

std::string TextEngine::ellipsize(const TextStyle& style, std::string_view text, float max_width, Ellipsis where) {
    if (width(style, text) <= max_width + .01f) return std::string(text);
    std::vector<char32_t> cps;
    std::vector<std::uint32_t> offsets;
    decode_utf8(text, cps, &offsets);
    const std::string dots = "\xE2\x80\xA6";
    auto make = [&](int keep) {
        if (where == Ellipsis::End) {
            std::string s(text.substr(0, offsets[static_cast<std::size_t>(keep)]));
            while (!s.empty() && s.back() == ' ') s.pop_back();
            return s + dots;
        }
        // The middle: a little more of the end is kept (a path's file name).
        const int tail = keep - keep * 2 / 5, head = keep - tail;
        const std::size_t n = cps.size();
        return std::string(text.substr(0, offsets[static_cast<std::size_t>(head)])) + dots +
               std::string(text.substr(offsets[n - static_cast<std::size_t>(tail)]));
    };
    int lo = 0, hi = static_cast<int>(cps.size()) - 1;
    while (lo < hi) {
        int mid = (lo + hi + 1) / 2;
        if (width(style, make(mid)) <= max_width + .01f) lo = mid;
        else hi = mid - 1;
    }
    return make(lo);
}

const std::vector<TextLine>& TextEngine::wrap(const TextStyle& style, std::string_view text, float max_width) {
    char head[64];
    std::snprintf(head, sizeof head, "%d|%.2f|%.4f|%d|%.1f|%.3f|", static_cast<int>(style.font),
                  static_cast<double>(style.size), static_cast<double>(style.tracking), style.upper ? 1 : 0,
                  static_cast<double>(max_width), static_cast<double>(scale_));
    std::string key = head;
    key.append(text);
    if (auto it = impl_->wraps.find(key); it != impl_->wraps.end()) return it->second;
    std::vector<TextLine> lines;
    auto push = [&](std::string s) {
        float w = width(style, s);
        lines.push_back({std::move(s), w});
    };
    std::size_t para_start = 0;
    while (para_start <= text.size()) {
        std::size_t para_end = text.find('\n', para_start);
        if (para_end == std::string_view::npos) para_end = text.size();
        std::string_view para = text.substr(para_start, para_end - para_start);
        std::string line;
        std::size_t i = 0;
        bool any = false;
        while (i <= para.size()) {
            std::size_t j = para.find(' ', i);
            if (j == std::string_view::npos) j = para.size();
            std::string word(para.substr(i, j - i));
            std::string candidate = line.empty() ? word : line + " " + word;
            if (width(style, candidate) <= max_width + .01f || (line.empty() && word.empty())) {
                line = std::move(candidate);
            } else {
                if (!line.empty()) {
                    push(std::move(line));
                    line.clear();
                    any = true;
                }
                // A word wider than the line breaks anywhere.
                while (width(style, word) > max_width + .01f) {
                    std::vector<char32_t> cps;
                    std::vector<std::uint32_t> offsets;
                    decode_utf8(word, cps, &offsets);
                    int lo = 1, hi = static_cast<int>(cps.size()) - 1;
                    while (lo < hi) {
                        int mid = (lo + hi + 1) / 2;
                        if (width(style, word.substr(0, offsets[static_cast<std::size_t>(mid)])) <= max_width + .01f)
                            lo = mid;
                        else hi = mid - 1;
                    }
                    if (cps.size() <= 1) break;
                    push(word.substr(0, offsets[static_cast<std::size_t>(lo)]));
                    any = true;
                    word = word.substr(offsets[static_cast<std::size_t>(lo)]);
                }
                line = word;
            }
            i = j + 1;
        }
        if (!line.empty() || !any) push(std::move(line));
        para_start = para_end + 1;
        if (para_end == text.size()) break;
    }
    return impl_->wraps.emplace(std::move(key), std::move(lines)).first->second;
}

float TextEngine::draw(Canvas& canvas, const TextStyle& style, std::string_view text, Vec2 pos, const TextPaint& how) {
    const float px = quantise(style.size * scale_);
    const Run& r = impl_->run(style, px, text, system_fallback_);
    if (r.glyphs.empty()) return r.width / scale_;
    const Vec2 origin = canvas.to_pixels(pos);
    const float baseline = std::round(origin.y + ascent(style) * scale_);
    const int outline2 = how.outline > 0 ? std::max(1, static_cast<int>(std::lround(how.outline * scale_ * 2))) : 0;
    const int px2 = static_cast<int>(std::lround(px * 2));
    const bool snap_x = px > theme::kTextOversampleLimit || outline2 > 0;
    for (const Placed& p : r.glyphs) {
        const Glyph* g = impl_->bake({p.face, px2, p.glyph, outline2}, scale_);
        if (!g || g->page < 0) continue;
        const Page& page = impl_->pages[static_cast<std::size_t>(g->page)];
        float x0 = origin.x + p.x + g->x0;
        if (snap_x) x0 = std::round(x0);
        const float y0 = baseline + g->y0, inv = 1.f / static_cast<float>(page.size);
        canvas.glyph_quad(page.texture, x0, y0, x0 + g->draw_w, y0 + static_cast<float>(g->h),
                          static_cast<float>(g->x) * inv, static_cast<float>(g->y) * inv,
                          static_cast<float>(g->x + g->w) * inv, static_cast<float>(g->y + g->h) * inv, how.color,
                          how.shear, baseline);
    }
    return r.width / scale_;
}

float TextEngine::draw_wrapped(Canvas& canvas, const TextStyle& style, std::string_view text, Rect box,
                               const TextPaint& how, float align) {
    const auto& lines = wrap(style, text, box.w);
    float y = box.y;
    for (const TextLine& l : lines) {
        draw(canvas, style, l.text, {box.x + (box.w - l.width) * align, y}, how);
        y += line_height(style);
    }
    return y - box.y;
}

std::size_t TextEngine::atlas_pages() const { return impl_->pages.size(); }
std::size_t TextEngine::cached_glyphs() const { return impl_->glyphs.size(); }
int TextEngine::face_count() const { return static_cast<int>(impl_->faces.size()); }
bool TextEngine::has_glyph_builtin(char32_t c) const {
    for (int i = 0; i < impl_->builtin; ++i)
        if (impl_->has(i, c)) return true;
    return false;
}
int TextEngine::face_for(const TextStyle& style, char32_t c) {
    return impl_->pick(static_cast<int>(style.font), style.upper ? to_upper(c) : c, system_fallback_);
}

}  // namespace ttt2::ui
