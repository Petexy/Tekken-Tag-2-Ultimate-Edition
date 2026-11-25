// Text with stb_truetype: the built-in faces (theme::Font roles) plus fallback faces from the system for missing
// characters (Linux: fontconfig's fc-match; Windows: the Fonts folders), glyphs baked on demand into atlas pages
// per (face, quantised pixel size) with a coverage gamma, LRU-evicted; kerning (kern + GPOS pairs), letter
// spacing, capitals, UTF-8 with invalid bytes as U+FFFD (drawn by us: the built-in faces lack it), baselines on
// whole pixels, measuring / wrapping (cached) / ellipsis at the end or in the middle (paths), outlined glyphs
// (from a distance field) and slanted drawing. No shaping or bidi: every character is drawn on its own, left to
// right (written down in the README; such names still measure and draw without breaking the rest of a line).
#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "ttt2ui/canvas.h"
#include "ttt2ui/theme.h"

namespace ttt2::ui {

using theme::TextStyle;

// One decoded UTF-8 string: code points, invalid bytes as U+FFFD; byte offset of each code point.
void decode_utf8(std::string_view text, std::vector<char32_t>& out, std::vector<std::uint32_t>* offsets = nullptr);
std::string encode_utf8(char32_t c);
char32_t to_upper(char32_t c);

enum class Ellipsis { End, Middle };

struct TextLine {
    std::string text;
    float width = 0;  // points
};

struct TextPaint {
    Color color{1, 1, 1, 1};
    float outline = 0;  // > 0: only the outline, this many points wide (CSS -webkit-text-stroke)
    float shear = 0;    // slant: x moved by shear * (height above the baseline); e.g. theme::kSeamTan
};

class TextEngine {
public:
    // `textures` may have no renderer (measuring only).
    explicit TextEngine(TextureRegistry& textures);
    ~TextEngine();
    TextEngine(const TextEngine&) = delete;
    TextEngine& operator=(const TextEngine&) = delete;

    // Physical pixels per point; sizes are quantised at this scale (measurement matches drawing).
    void set_scale(float scale);
    float scale() const { return scale_; }
    // Look for faces on the system when no built-in one has a character (off in tests: deterministic).
    void set_system_fallback(bool on) { system_fallback_ = on; }
    // A face file to try for missing characters before the system's (tests; or a font the app ships).
    bool add_fallback_file(const std::string& path);
    // Next frame: atlas pages not used for a while may be reused.
    void begin_frame();

    // Measuring (points).
    float width(const TextStyle& style, std::string_view text);
    float line_height(const TextStyle& style) const { return style.size * style.line_height; }
    float ascent(const TextStyle& style);   // from the top of the line box to the baseline
    float cap_height(const TextStyle& style);
    std::string ellipsize(const TextStyle& style, std::string_view text, float max_width,
                          Ellipsis where = Ellipsis::End);
    // Greedy wrapping at spaces; words longer than the width break anywhere (paths). Cached.
    const std::vector<TextLine>& wrap(const TextStyle& style, std::string_view text, float max_width);
    float wrapped_height(const TextStyle& style, std::string_view text, float max_width) {
        return static_cast<float>(wrap(style, text, max_width).size()) * line_height(style);
    }

    // Drawing one line with its line box's top-left at `pos` (points); returns its width.
    float draw(Canvas& canvas, const TextStyle& style, std::string_view text, Vec2 pos, const TextPaint& how);
    float draw(Canvas& canvas, const TextStyle& style, std::string_view text, Vec2 pos, Color color) {
        return draw(canvas, style, text, pos, TextPaint{color});
    }
    // Lines wrapped to `max_width`, aligned 0 = left, .5 = centre, 1 = right; returns the height.
    float draw_wrapped(Canvas& canvas, const TextStyle& style, std::string_view text, Rect box, const TextPaint& how,
                       float align = 0);

    // Diagnostics (tests).
    std::size_t atlas_pages() const;
    std::size_t cached_glyphs() const;
    int face_count() const;
    bool has_glyph_builtin(char32_t c) const;  // any built-in face has it
    // The face used for `c` in `style` (index in face order; -1 = drawn by us / missing).
    int face_for(const TextStyle& style, char32_t c);

    struct Impl;

private:
    std::unique_ptr<Impl> impl_;
    float scale_ = 1;
    bool system_fallback_ = true;
};

}  // namespace ttt2::ui
