#include "ttt2ui/widgets.h"

#include <SDL3/SDL_clipboard.h>

#include <algorithm>
#include <cmath>
#include <functional>

namespace ttt2::ui {

namespace c = theme::color;
namespace m = theme::metric;
namespace tx = theme::text;
using theme::kSeamTan;

namespace {

constexpr float kPi = 3.14159265f;

bool zero(const Insets& i) { return i.left == 0 && i.top == 0 && i.right == 0 && i.bottom == 0; }

Box with_height(Box b, float h) {
    if (b.h.mode == Size::Fit) b.h = Size::fixed(h);
    return b;
}

float centred_y(TextEngine& text, const TextStyle& st, const Rect& r) { return r.y + (r.h - text.line_height(st)) / 2; }

struct ToneColors {
    Color fill, border, text;
};
ToneColors tone_colors(Tone t) {
    switch (t) {
    case Tone::Ok: return {rgba(63, 231, 161, .14f), rgba(63, 231, 161, .6f), c::kOk};
    case Tone::Warn: return {rgba(255, 200, 67, .14f), rgba(255, 200, 67, .6f), c::kWarn};
    case Tone::Bad: return {rgba(255, 93, 113, .16f), rgba(255, 93, 113, .65f), c::kBad};
    case Tone::Blue: return {rgba(45, 128, 255, .2f), rgba(98, 212, 255, .6f), c::kCyan};
    case Tone::Red: return {rgba(255, 42, 85, .2f), rgba(255, 120, 150, .6f), c::kRedLabel};
    case Tone::Dim: return {rgba(255, 255, 255, .04f), rgba(255, 255, 255, .16f), rgb(0x9aa2b6)};
    default: return {rgba(255, 255, 255, .08f), rgba(255, 255, 255, .22f), rgb(0xe4e8f1)};
    }
}
Color tone_text(Tone t, Color neutral) { return t == Tone::Neutral ? neutral : tone_colors(t).text; }

// Point p of a box's unskewed space moved like CSS skewX(-12deg) about the box's centre.
Vec2 sk(const Rect& r, Vec2 p, float tan = kSeamTan) { return {p.x + (r.y + r.h / 2 - p.y) * tan, p.y}; }
Quad sk_rect(const Rect& box, const Rect& part, float tan = kSeamTan) {
    return {{sk(box, {part.x, part.y}, tan), sk(box, {part.right(), part.y}, tan),
             sk(box, {part.right(), part.bottom()}, tan), sk(box, {part.x, part.bottom()}, tan)}};
}

// The look's row surface: rest fill, the focused gradient faded in by `f`.
// (Crimson lists: Shape::StraightLeft, their left edges in line with the window's.)
void row_surface(Canvas& cv, const Rect& r, float f, Color rest_fill, Color rest_border, Color focus_a, Color focus_b,
                 Color focus_border, Shape shape = Shape::StraightLeft) {
    const Quad q = shaped(r, shape, kSeamTan);
    cv.fill(q, rest_fill);
    if (f > 0) cv.fill(q, Gradient::css(r, 100, {{0, focus_a.faded(f)}, {1, focus_b.faded(f)}}));
    cv.stroke(q, 1, mix(rest_border, focus_border, f));
}

void draw_arrow(Canvas& cv, Vec2 c, float w, float h, int dir, Color col) {
    // A filled triangle pointing left (dir -1) or right (1), w x h.
    const Vec2 tip{c.x + dir * w / 2, c.y}, a{c.x - dir * w / 2, c.y - h / 2}, b{c.x - dir * w / 2, c.y + h / 2};
    const Vec2 pts[3] = {a, tip, b};
    cv.fill(pts, col);
}

float hash01(std::string_view s) {
    std::uint32_t h = 2166136261u;
    for (char ch : s) h = (h ^ static_cast<std::uint8_t>(ch)) * 16777619u;
    return static_cast<float>(h & 0xffffff);
}

}  // namespace

// ---- primitives -----------------------------------------------------------------------------------------------------

void surface(Canvas& canvas, const Rect& r, Color fill, Color border, float tan) {
    const Quad q = skewed(r, tan);
    canvas.fill(q, fill);
    if (border.a > 0) canvas.stroke(q, 1, border);
}
void surface(Canvas& canvas, const Rect& r, const Gradient& fill, Color border, float tan) {
    const Quad q = skewed(r, tan);
    canvas.fill(q, fill);
    if (border.a > 0) canvas.stroke(q, 1, border);
}

void dashed(Canvas& canvas, const Quad& q, float width, float dash, float gap, Color color) {
    for (int i = 0; i < 4; ++i) {
        const Vec2 a = q.p[i], b = q.p[(i + 1) % 4];
        const Vec2 d = b - a;
        const float len = std::sqrt(d.x * d.x + d.y * d.y);
        if (len <= 0) continue;
        const Vec2 u = d * (1 / len);
        // Inside the edge (the polygon's winding: clockwise on screen).
        const Vec2 n{-u.y * width / 2, u.x * width / 2};
        for (float t = 0; t < len; t += dash + gap) {
            const float t1 = std::min(len, t + dash);
            canvas.line(a + u * t + n, a + u * t1 + n, width, color);
        }
    }
}

namespace {
std::vector<Vec2> round_points(const Rect& r, float rt, float rb) {
    std::vector<Vec2> p;
    rt = std::min({rt, r.w / 2, r.h / 2});
    rb = std::min({rb, r.w / 2, r.h / 2});
    auto arc = [&](Vec2 c, float rad, float a0) {
        if (rad <= 0) {
            p.push_back(c);
            return;
        }
        for (int i = 0; i <= 5; ++i) {
            const float a = a0 + static_cast<float>(i) * (kPi / 2) / 5;
            p.push_back({c.x + std::cos(a) * rad, c.y + std::sin(a) * rad});
        }
    };
    arc({r.x + rt, r.y + rt}, rt, kPi);
    arc({r.right() - rt, r.y + rt}, rt, -kPi / 2);
    arc({r.right() - rb, r.bottom() - rb}, rb, 0);
    arc({r.x + rb, r.bottom() - rb}, rb, kPi / 2);
    return p;
}
}  // namespace

void rounded_rect(Canvas& canvas, const Rect& r, float radius, Color color) {
    rounded_rect(canvas, r, radius, radius, color);
}
void rounded_rect(Canvas& canvas, const Rect& r, float top_radius, float bottom_radius, Color color) {
    const auto p = round_points(r, top_radius, bottom_radius);
    canvas.fill(p, color);
}

void chroma_text(Canvas& canvas, TextEngine& text, const TextStyle& style, std::string_view s, Vec2 pos, float split,
                 float alpha) {
    text.draw(canvas, style, s, {pos.x - split, pos.y - split / 4}, rgba(255, 42, 85, .92f * alpha));
    text.draw(canvas, style, s, {pos.x + split, pos.y + split / 4}, rgba(45, 128, 255, .95f * alpha));
    text.draw(canvas, style, s, pos, rgba(255, 255, 255, alpha));
}

void icon(Canvas& canvas, Icons& icons, const std::string& name, const Rect& box, Color color) {
    if (name.empty()) return;
    const bool line = name.rfind("stroke:", 0) == 0;
    icons.draw(canvas, name, box, color, line ? IconMode::Mask : IconMode::Colour);
}

void paint_focus_highlight(Canvas& cv, const Rect& r, Shape shape, float alpha, double now) {
    if (alpha <= 0 || r.empty()) return;
    const float tan = kSeamTan;
    const Quad q = shaped(r, shape, tan);
    cv.glow(q, 30, rgba(45, 128, 255, .22f * alpha));
    cv.glow(q, 14, rgba(255, 255, 255, .3f * alpha));
    cv.stroke(shaped(r.outset(1), shape, tan), 1, rgba(0, 0, 0, .45f * alpha));
    cv.stroke(q, 2, rgba(255, 255, 255, alpha));
    // A faint inner light and a sheen passing now and then.
    cv.stroke(shaped(r.outset(-2), shape, tan), 3, rgba(255, 255, 255, .07f * alpha));
    const float period = 2.6f, t = static_cast<float>(std::fmod(now, static_cast<double>(period))) / period;
    if (t < .6f) {
        const float x = r.x - 80 + t / .6f * 1400;
        const float x0 = std::max(r.x + 2, x), x1 = std::min(r.right() - 2, x + 60);
        if (x1 > x0) {
            const Rect band{x0, r.y + 2, x1 - x0, r.h - 4};
            const Quad bq = shaped_part(r, band, shape, tan);
            cv.fill(bq, Gradient::linear3({x, 0}, {x + 60, 0}, rgba(255, 255, 255, 0), .5f,
                                          rgba(255, 255, 255, .16f * alpha), rgba(255, 255, 255, 0)));
        }
    }
    // Corner accents: red top-left, blue bottom-right (5 points thick, 20 long), skewed with the frame.
    const Color red = c::kRed.faded(alpha), blue = c::kBlue.faded(alpha);
    auto bar = [&](const Rect& part, Color col) {
        const Quad pq = shaped_part(r, part, shape, tan);
        cv.glow(pq, 5, col.faded(.5f));
        cv.fill(pq, col);
    };
    bar({r.x - 8, r.y - 8, 20, 5}, red);
    bar({r.x - 8, r.y - 3, 5, 15}, red);
    bar({r.right() - 12, r.bottom() + 3, 20, 5}, blue);
    bar({r.right() + 3, r.bottom() - 12, 5, 15}, blue);
}

// ---- prompt glyphs --------------------------------------------------------------------------------------------------

namespace {
enum class GlyphShape { Key, Circle, Shoulder, Dpad, Svg };
struct GlyphPart {
    GlyphShape shape;
    std::string label;  // key / letter / shoulder text; svg path; dpad arms "lr"
    Color color{};
    int ps = -1;        // PlayStation symbol 0 cross, 1 circle, 2 square, 3 triangle
};

std::vector<GlyphPart> glyph_parts(Glyphs g, Prompt p) {
    using P = Prompt;
    if (p == P::Tabs || p == P::Sections) {
        auto a = glyph_parts(g, p == P::Tabs ? P::TabPrev : P::SectionPrev);
        const auto b = glyph_parts(g, p == P::Tabs ? P::TabNext : P::SectionNext);
        a.insert(a.end(), b.begin(), b.end());
        return a;
    }
    if (g == Glyphs::Keyboard) {
        switch (p) {
        case P::Accept: return {{GlyphShape::Key, "Enter"}};
        case P::Back: return {{GlyphShape::Key, "Esc"}};
        case P::Context1: return {{GlyphShape::Key, "F"}};
        case P::Context2: return {{GlyphShape::Key, "R"}};
        case P::TabPrev: return {{GlyphShape::Key, "Q"}};
        case P::TabNext: return {{GlyphShape::Key, "E"}};
        case P::SectionPrev: return {{GlyphShape::Key, "Z"}};
        case P::SectionNext: return {{GlyphShape::Key, "C"}};
        case P::Menu: return {{GlyphShape::Key, "Esc"}};
        case P::Move: return {{GlyphShape::Key, "WASD"}};
        case P::Change: return {{GlyphShape::Key, "\x01L"}, {GlyphShape::Key, "\x01R"}};
        case P::AnyKey: return {{GlyphShape::Key, "Any key"}};
        default: break;
        }
    }
    const int face = p == P::Accept ? 0 : p == P::Back ? 1 : p == P::Context1 ? 2 : p == P::Context2 ? 3 : -1;
    if (g == Glyphs::Generic) {
        static const char* kFace[] = {"icons/ttt2-input-face_bottom.svg", "icons/ttt2-input-face_right.svg",
                                      "icons/ttt2-input-face_left.svg", "icons/ttt2-input-face_top.svg"};
        if (face >= 0) return {{GlyphShape::Svg, kFace[face]}};
        switch (p) {
        case P::TabPrev: return {{GlyphShape::Svg, "icons/ttt2-input-l.svg"}};
        case P::TabNext: return {{GlyphShape::Svg, "icons/ttt2-input-r.svg"}};
        case P::SectionPrev: return {{GlyphShape::Svg, "icons/ttt2-input-zl.svg"}};
        case P::SectionNext: return {{GlyphShape::Svg, "icons/ttt2-input-zr.svg"}};
        case P::Menu: return {{GlyphShape::Svg, "icons/ttt2-input-plus.svg"}};
        default: break;
        }
    }
    if (face >= 0) {
        if (g == Glyphs::PlayStation) {
            static const Color kPs[] = {c::kPsCross, c::kPsCircle, c::kPsSquare, c::kPsTriangle};
            GlyphPart part{GlyphShape::Circle, "", kPs[face], face};
            return {part};
        }
        if (g == Glyphs::Nintendo) {
            // (Nintendo pads confirm with the right button, labelled A.)
            static const char* kN[] = {"A", "B", "Y", "X"};
            return {{GlyphShape::Circle, kN[face], rgb(0x9aa3b8)}};
        }
        static const char* kX[] = {"A", "B", "X", "Y"};
        static const Color kXc[] = {c::kXboxA, c::kXboxB, c::kXboxX, c::kXboxY};
        return {{GlyphShape::Circle, kX[face], kXc[face]}};
    }
    const bool ps = g == Glyphs::PlayStation, nin = g == Glyphs::Nintendo;
    switch (p) {
    case P::TabPrev: return {{GlyphShape::Shoulder, ps ? "L1" : nin ? "L" : "LB"}};
    case P::TabNext: return {{GlyphShape::Shoulder, ps ? "R1" : nin ? "R" : "RB"}};
    case P::SectionPrev: return {{GlyphShape::Shoulder, ps ? "L2" : nin ? "ZL" : "LT"}};
    case P::SectionNext: return {{GlyphShape::Shoulder, ps ? "R2" : nin ? "ZR" : "RT"}};
    case P::Menu: return {{GlyphShape::Shoulder, ps ? "OPTIONS" : nin ? "+" : "MENU"}};
    case P::Move: return {{GlyphShape::Dpad, "udlr"}};
    case P::Change: return {{GlyphShape::Dpad, "lr"}};
    case P::AnyKey: return {{GlyphShape::Shoulder, "ANY"}};
    default: return {{GlyphShape::Shoulder, "?"}};
    }
}

constexpr theme::TextStyle kShoulderText{theme::Font::BodyBold, 11, .02f, false, 1};
constexpr theme::TextStyle kPadLetter{theme::Font::BodyBold, 13, 0, false, 1};

float part_width(TextEngine& text, const GlyphPart& part) {
    switch (part.shape) {
    case GlyphShape::Key:
        if (part.label[0] == '\x01') return 22;
        return std::max(22.f, text.width(tx::kGlyphKey, part.label) + 12);
    case GlyphShape::Shoulder: return std::max(22.f, text.width(kShoulderText, part.label) + 12 + 3);
    default: return 24;
    }
}

float draw_part(Canvas& cv, TextEngine& text, Icons& icons, const GlyphPart& part, float x, float cy, float alpha) {
    const float w = part_width(text, part);
    switch (part.shape) {
    case GlyphShape::Key: draw_keycap(cv, text, part.label, x, cy, alpha); break;
    case GlyphShape::Circle: {
        const Vec2 ctr{x + 12, cy};
        cv.circle(ctr, 12, c::kPadGlyphBase.faded(alpha));
        cv.ring(ctr, 11.25f, 1.5f, part.color.faded(alpha));
        if (part.ps >= 0) {
            const Color col = part.color.faded(alpha);
            const float s = 1;  // 12-unit symbol drawn 12 points wide
            const Vec2 o{ctr.x - 6 * s, cy - 6 * s};
            auto P = [&](float px, float py) { return Vec2{o.x + px * s, o.y + py * s}; };
            switch (part.ps) {
            case 0: cv.line(P(2, 2), P(10, 10), 2.2f, col), cv.line(P(10, 2), P(2, 10), 2.2f, col); break;
            case 1: cv.ring(P(6, 6), 4.3f, 2.2f, col); break;
            case 2:
                cv.line(P(2, 2), P(10, 2), 2.2f, col), cv.line(P(10, 2), P(10, 10), 2.2f, col);
                cv.line(P(10, 10), P(2, 10), 2.2f, col), cv.line(P(2, 10), P(2, 2), 2.2f, col);
                break;
            default:
                cv.line(P(6, 1.6f), P(10.8f, 9.9f), 2.2f, col), cv.line(P(10.8f, 9.9f), P(1.2f, 9.9f), 2.2f, col);
                cv.line(P(1.2f, 9.9f), P(6, 1.6f), 2.2f, col);
                break;
            }
        } else {
            const float tw = text.width(kPadLetter, part.label);
            text.draw(cv, kPadLetter, part.label, {ctr.x - tw / 2, cy - text.line_height(kPadLetter) / 2},
                      part.color.faded(alpha));
        }
        break;
    }
    case GlyphShape::Shoulder: {
        const Rect r{x, cy - 11, w, 22};
        rounded_rect(cv, r, 7, 4, rgb(0x8d96ab, alpha));
        rounded_rect(cv, r.outset(-1.5f), 5.5f, 2.5f, c::kPadGlyphBase.faded(alpha));
        const float tw = text.width(kShoulderText, part.label);
        text.draw(cv, kShoulderText, part.label, {x + (w - tw) / 2, cy - text.line_height(kShoulderText) / 2},
                  rgb(0xe8ecf4, alpha));
        break;
    }
    case GlyphShape::Dpad: {
        const float s = 1;
        const Vec2 o{x, cy - 12};
        auto R = [&](float rx, float ry, float rw, float rh) {
            return Rect{o.x + rx * s, o.y + ry * s, rw * s, rh * s};
        };
        const Color edge = rgb(0x8d96ab, alpha), base = c::kPadGlyphBase.faded(alpha), lit = rgb(0xe8ecf4, alpha);
        cv.fill_rect(R(8.8f, 2.3f, 6.4f, 19.4f), edge);
        cv.fill_rect(R(2.3f, 8.8f, 19.4f, 6.4f), edge);
        cv.fill_rect(R(9.5f, 3, 5, 18), base);
        cv.fill_rect(R(3, 9.5f, 18, 5), base);
        for (char arm : part.label) {
            if (arm == 'u') cv.fill_rect(R(9.5f, 3, 5, 6), lit);
            if (arm == 'd') cv.fill_rect(R(9.5f, 15, 5, 6), lit);
            if (arm == 'l') cv.fill_rect(R(3, 9.5f, 6, 5), lit);
            if (arm == 'r') cv.fill_rect(R(15, 9.5f, 6, 5), lit);
        }
        break;
    }
    case GlyphShape::Svg: icons.draw(cv, part.label, {x, cy - 12, 24, 24}, rgba(255, 255, 255, alpha)); break;
    }
    return w;
}
}  // namespace

float draw_keycap(Canvas& cv, TextEngine& text, std::string_view label, float left, float cy, float alpha) {
    const bool arrow = !label.empty() && label[0] == '\x01';
    const float w = arrow ? 22 : std::max(22.f, text.width(tx::kGlyphKey, label) + 12);
    const Rect r{left, cy - 11, w, 22};
    rounded_rect(cv, r.translated({0, 2}), 4, c::kKeycapShadow.faded(alpha));
    rounded_rect(cv, r, 4, c::kKeycap.faded(alpha));
    if (arrow) {
        const int dir = label[1] == 'L' ? -1 : label[1] == 'R' ? 1 : 0;
        const Color col = c::kKeycapText.faded(alpha);
        const Vec2 ctr = r.center();
        cv.line({ctr.x - 4.5f, ctr.y}, {ctr.x + 4.5f, ctr.y}, 1.6f, col);
        draw_arrow(cv, {ctr.x + dir * 3.5f, ctr.y}, 4, 7, dir, col);
    } else {
        const float tw = text.width(tx::kGlyphKey, label);
        text.draw(cv, tx::kGlyphKey, label, {left + (w - tw) / 2, cy - text.line_height(tx::kGlyphKey) / 2},
                  c::kKeycapText.faded(alpha));
    }
    return w;
}

float prompt_width(TextEngine& text, Glyphs glyphs, Prompt p) {
    const auto parts = glyph_parts(glyphs, p);
    float w = 0;
    for (std::size_t i = 0; i < parts.size(); ++i) w += part_width(text, parts[i]) + (i ? 3 : 0);
    return w;
}

float draw_prompt(Canvas& canvas, TextEngine& text, Icons& icons, Glyphs glyphs, Prompt p, float left, float cy,
                  float alpha) {
    const auto parts = glyph_parts(glyphs, p);
    float x = left;
    for (std::size_t i = 0; i < parts.size(); ++i) {
        if (i) x += 3;
        x += draw_part(canvas, text, icons, parts[i], x, cy, alpha);
    }
    return x - left;
}

void prompt(Ui& ui, const std::string& id, Prompt p, const Box& box) {
    TextEngine& te = ui.text();
    const Glyphs g = ui.glyphs();
    ui.leaf(
        id, box, [&te, g, p](float) { return Vec2{prompt_width(te, g, p), 24}; },
        [p](PaintContext& ctx) {
            draw_prompt(ctx.canvas, ctx.text, ctx.icons, ctx.glyphs, p, ctx.rect.x, ctx.rect.y + ctx.rect.h / 2, .9f);
        });
}

// ---- text -----------------------------------------------------------------------------------------------------------

void text(Ui& ui, const std::string& id, const TextSpec& spec0, const Box& box) {
    TextEngine& te = ui.text();
    // (In a mirrored half: right-aligned, wrapped lines too.)
    const bool right = ui.mirrored();
    TextSpec spec = spec0;
    if (right && spec.wrap && spec.align == 0) spec.align = 1;
    ui.leaf(
        id, box,
        [&te, spec](float max_w) -> Vec2 {
            if (spec.wrap) {
                const float natural = te.width(spec.style, spec.text);
                const float w = std::min(max_w, natural);
                return {w, te.wrapped_height(spec.style, spec.text, std::max(1.f, max_w))};
            }
            return {te.width(spec.style, spec.text) + spec.chroma * 2, te.line_height(spec.style)};
        },
        [spec, right](PaintContext& ctx) {
            const Rect r = ctx.rect;
            if (spec.wrap) {
                ctx.text.draw_wrapped(ctx.canvas, spec.style, spec.text, r, TextPaint{spec.color, spec.outline},
                                      spec.align);
                return;
            }
            TextStyle st = spec.style;
            if (spec.drop && ctx.text.width(st, spec.text) + spec.chroma * 2 > r.w + .5f) return;
            if (spec.autofit_min > 0)
                while (st.size > spec.autofit_min && ctx.text.width(st, spec.text) + spec.chroma * 2 > r.w + .5f)
                    st.size = std::max(spec.autofit_min, st.size - 3);
            const std::string shown = ctx.text.width(st, spec.text) + spec.chroma * 2 > r.w + .5f
                                          ? ctx.text.ellipsize(st, spec.text, r.w - spec.chroma * 2, spec.ellipsis)
                                          : spec.text;
            const float x = right ? r.right() - spec.chroma - ctx.text.width(st, shown) : r.x + spec.chroma;
            const Vec2 pos{x, r.y + (r.h - ctx.text.line_height(st)) / 2};
            if (spec.chroma > 0) chroma_text(ctx.canvas, ctx.text, st, shown, pos, spec.chroma);
            else ctx.text.draw(ctx.canvas, st, shown, pos, TextPaint{spec.color, spec.outline});
        });
}

void runs(Ui& ui, const std::string& id, const TextStyle& style, std::vector<Run> rs, const Box& box) {
    TextEngine& te = ui.text();
    ui.leaf(
        id, box,
        [&te, style, rs](float) {
            float w = 0;
            for (const Run& r : rs) w += te.width(style, r.text);
            return Vec2{w, te.line_height(style)};
        },
        [style, rs, right = ui.mirrored()](PaintContext& ctx) {
            float x = ctx.rect.x;
            if (right) {
                float w = 0;
                for (const Run& r : rs) w += ctx.text.width(style, r.text);
                x = ctx.rect.right() - w;
            }
            for (const Run& r : rs) x += ctx.text.draw(ctx.canvas, style, r.text, {x, ctx.rect.y}, r.color);
        });
}

void section_label(Ui& ui, const std::string& id, const std::string& label, Half half, const std::string& right,
                   const Box& box) {
    Box b = with_height(box, 20);
    if (zero(b.margin)) b.margin.bottom = 12;
    const Color col = half == Half::Blue ? c::kBlueLabel : c::kRedLabel;
    TextEngine& te = ui.text();
    ui.leaf(
        id, b,
        [&te, label, right](float) {
            return Vec2{
                32 + te.width(tx::kLabel, label) + 30 + (right.empty() ? 0 : 10 + te.width(tx::kLabelEm, right)), 20};
        },
        [label, right, col, mirrored = ui.mirrored()](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            const float cy = r.y + r.h / 2;
            if (mirrored) {
                // (Mirrored: the hairline from the left, the label, the bar at the right end; `right` first.)
                const Rect bar{r.right() - 22, cy - 2, 22, 4};
                cv.glow(skewed(bar, kSeamTan), 8, col.faded(.5f));
                cv.fill(skewed(bar, kSeamTan), col);
                const float w = ctx.text.width(tx::kLabel, label);
                const float x = r.right() - 32 - w;
                ctx.text.draw(cv, tx::kLabel, label, {x, centred_y(ctx.text, tx::kLabel, r)}, col);
                const float rw = right.empty() ? 0 : ctx.text.width(tx::kLabelEm, right);
                if (!right.empty())
                    ctx.text.draw(cv, tx::kLabelEm, right, {r.x, centred_y(ctx.text, tx::kLabelEm, r)}, rgb(0xe9edf5));
                const float l0 = r.x + (right.empty() ? 0 : rw + 10), l1 = x - 10;
                if (l1 > l0)
                    cv.fill_rect({l0, cy - .5f, l1 - l0, 1},
                                 Gradient::linear({l0, 0}, {l1, 0}, col.faded(0), col.faded(.35f)));
                return;
            }
            const Rect bar{r.x, cy - 2, 22, 4};
            cv.glow(skewed(bar, kSeamTan), 8, col.faded(.5f));
            cv.fill(skewed(bar, kSeamTan), col);
            const float x = r.x + 32;
            const float w = ctx.text.draw(cv, tx::kLabel, label, {x, centred_y(ctx.text, tx::kLabel, r)}, col);
            const float rw = right.empty() ? 0 : ctx.text.width(tx::kLabelEm, right);
            const float l0 = x + w + 10, l1 = r.right() - (right.empty() ? 0 : rw + 10);
            if (l1 > l0)
                cv.fill_rect({l0, cy - .5f, l1 - l0, 1},
                             Gradient::linear({l0, 0}, {l1, 0}, col.faded(.35f), col.faded(0)));
            if (!right.empty())
                ctx.text.draw(cv, tx::kLabelEm, right, {r.right() - rw, centred_y(ctx.text, tx::kLabelEm, r)},
                              rgb(0xe9edf5));
        });
}

void facts(Ui& ui, const std::string& id, std::span<const Fact> fs, const Box& box) {
    std::vector<Fact> list(fs.begin(), fs.end());
    TextEngine& te = ui.text();
    constexpr float kGapX = 18, kGapY = 7;
    auto key_w = [&te, list]() {
        float w = 0;
        for (const Fact& f : list) w = std::max(w, te.width(tx::kFactKey, f.key));
        return w;
    };
    auto value_style = [](const Fact& f) { return f.mono ? tx::kFactValue : tx::kFactValueUi; };
    auto row_h = [&te, value_style](const Fact& f, float vw) {
        const TextStyle vs = value_style(f);
        float h = te.line_height(vs);
        if (f.value.size() == 1) h = te.wrapped_height(vs, f.value[0].text, std::max(1.f, vw));
        return std::max(te.line_height(tx::kFactKey), h);
    };
    ui.leaf(
        id, box,
        [&te, list, key_w, value_style, row_h](float max_w) {
            const float kw = key_w();
            float vw = 0;
            for (const Fact& f : list) {
                float w = 0;
                for (const Run& r : f.value) w += te.width(value_style(f), r.text);
                vw = std::max(vw, w);
            }
            const float w = std::min(max_w, kw + kGapX + vw);
            float h = 0;
            for (const Fact& f : list) h += row_h(f, w - kw - kGapX);
            h += kGapY * static_cast<float>(std::max<std::size_t>(1, list.size()) - 1);
            return Vec2{w, h};
        },
        [list, key_w, value_style, row_h, mirrored = ui.mirrored()](PaintContext& ctx) {
            if (mirrored) {
                // The mirrored table: values right-aligned at the right edge, keys right-aligned before the widest
                // value (both columns' straight edges face right).
                float vmax = 0;
                for (const Fact& f : list) {
                    float w = 0;
                    for (const Run& r : f.value) w += ctx.text.width(value_style(f), r.text);
                    vmax = std::max(vmax, w);
                }
                const float kw = key_w(), vw = std::min(vmax, ctx.rect.w - kw - kGapX);
                const float kx1 = ctx.rect.right() - vw - kGapX;
                float y = ctx.rect.y;
                for (const Fact& f : list) {
                    const float h = row_h(f, vw);
                    ctx.text.draw(ctx.canvas, tx::kFactKey, f.key, {kx1 - ctx.text.width(tx::kFactKey, f.key), y},
                                  c::kBlueFaint);
                    const TextStyle vs = value_style(f);
                    const float dy = (ctx.text.line_height(tx::kFactKey) - ctx.text.line_height(vs)) / 2;
                    if (f.value.size() == 1) {
                        ctx.text.draw_wrapped(ctx.canvas, vs, f.value[0].text,
                                              {ctx.rect.right() - vw, y + dy, vw, h}, TextPaint{f.value[0].color}, 1);
                    } else {
                        float w = 0;
                        for (const Run& r : f.value) w += ctx.text.width(vs, r.text);
                        float x = ctx.rect.right() - w;
                        for (const Run& r : f.value) x += ctx.text.draw(ctx.canvas, vs, r.text, {x, y + dy}, r.color);
                    }
                    y += h + kGapY;
                }
                return;
            }
            const float kw = key_w(), vx = ctx.rect.x + kw + kGapX, vw = ctx.rect.right() - vx;
            float y = ctx.rect.y;
            for (const Fact& f : list) {
                const float h = row_h(f, vw);
                ctx.text.draw(ctx.canvas, tx::kFactKey, f.key, {ctx.rect.x, y}, c::kBlueFaint);
                const TextStyle vs = value_style(f);
                // (Keys and values share a line height of 18: their first lines sit on the same line box.)
                const float dy = (ctx.text.line_height(tx::kFactKey) - ctx.text.line_height(vs)) / 2;
                if (f.value.size() == 1)
                    ctx.text.draw_wrapped(ctx.canvas, vs, f.value[0].text, {vx, y + dy, vw, h},
                                          TextPaint{f.value[0].color});
                else {
                    float x = vx;
                    for (const Run& r : f.value) x += ctx.text.draw(ctx.canvas, vs, r.text, {x, y + dy}, r.color);
                }
                y += h + kGapY;
            }
        });
}

void note(Ui& ui, const std::string& id, Tone tone, const std::string& s, const Box& box,
          const std::string& icon_name) {
    const Color text_col = tone == Tone::Bad ? rgb(0xffd0d7) : tone == Tone::Blue ? rgb(0xcfe2ff) : rgb(0xf6e6bd);
    const Color icon_col = tone == Tone::Bad ? c::kBad : tone == Tone::Blue ? c::kCyan : c::kWarn;
    const std::string ic = !icon_name.empty() ? icon_name : tone == Tone::Blue ? "stroke:info:2.2" : "stroke:warn:2.2";
    TextEngine& te = ui.text();
    ui.leaf(
        id, box,
        [&te, s](float max_w) {
            const float w = std::min(max_w, 26 + te.width(tx::kWarn, s));
            return Vec2{w, std::max(18.f, te.wrapped_height(tx::kWarn, s, std::max(1.f, w - 26)))};
        },
        [s, text_col, icon_col, ic, mirrored = ui.mirrored()](PaintContext& ctx) {
            if (mirrored) {  // (the icon at the right end, the words right-aligned before it)
                icon(ctx.canvas, ctx.icons, ic, {ctx.rect.right() - 16, ctx.rect.y + 1, 16, 16}, icon_col);
                ctx.text.draw_wrapped(ctx.canvas, tx::kWarn, s, {ctx.rect.x, ctx.rect.y, ctx.rect.w - 26, ctx.rect.h},
                                      TextPaint{text_col}, 1);
                return;
            }
            icon(ctx.canvas, ctx.icons, ic, {ctx.rect.x, ctx.rect.y + 1, 16, 16}, icon_col);
            ctx.text.draw_wrapped(ctx.canvas, tx::kWarn, s, {ctx.rect.x + 26, ctx.rect.y, ctx.rect.w - 26, ctx.rect.h},
                                  TextPaint{text_col});
        });
}

void watermark(Canvas& canvas, TextEngine& text, const std::string& word, Vec2 bottom_right) {
    const float w = text.width(tx::kWatermark, word);
    text.draw(canvas, tx::kWatermark, word, {bottom_right.x - w, bottom_right.y - text.line_height(tx::kWatermark)},
              TextPaint{rgba(255, 255, 255, .035f), 2});
}

// ---- top band -------------------------------------------------------------------------------------------------------

void brand(Ui& ui, const std::string& id, const std::string& line1, const std::string& line2, const Box& box) {
    Box b = with_height(box, 34);
    // (Its words go when the top band is short of room: shrink_order 1, down to the mark.)
    if (b.w.mode == Size::Fit && b.min_w == 0) b.min_w = 44;
    if (b.shrink_order == 0) b.shrink_order = 1;
    static constexpr theme::TextStyle kSecond{theme::Font::DisplayBoldItalic, 14, .24f, true, 1.05f};
    ui.leaf(id, b, [](float) { return Vec2{196, 34}; }, [line1, line2](PaintContext& ctx) {
        Canvas& cv = ctx.canvas;
        const float x = ctx.rect.x, cy = ctx.rect.y + ctx.rect.h / 2;
        const Rect red{x + 2, cy - 15, 20, 30}, blue{x + 19, cy - 15, 20, 30};
        cv.fill(skewed(red, kSeamTan), Gradient::linear({0, red.y}, {0, red.bottom()}, rgb(0xff4d72), rgb(0xc40f39)));
        cv.fill(skewed(blue, kSeamTan),
                Gradient::linear({0, blue.y}, {0, blue.bottom()}, rgb(0x4b98ff, .92f), rgb(0x1650d6, .92f)));
        if (ctx.rect.w < 52 + std::max(ctx.text.width(tx::kBrand, line1), ctx.text.width(kSecond, line2))) return;
        const float lh = ctx.text.line_height(tx::kBrand);
        ctx.text.draw(cv, tx::kBrand, line1, {x + 52, cy - lh}, rgb(0xe6e9f2));
        ctx.text.draw(cv, kSecond, line2, {x + 52, cy}, c::kDim);
    });
}

void tab_bar(Ui& ui, const std::string& id, std::span<const Tab> tabs, int active, const Box& box) {
    Box b = box;
    b.layout = Layout::Row;
    b.align = Align::Center;
    b.gap = 2;
    if (b.h.mode == Size::Fit) b.h = Size::fixed(theme::kTopBand);
    std::string active_id =
        active >= 0 && active < static_cast<int>(tabs.size()) ? tabs[static_cast<std::size_t>(active)].id : "";
    Ui* u = &ui;
    auto underline = [u, active_id](PaintContext& ctx) {
        if (active_id.empty() || !u->has(active_id)) return;
        const Rect t = u->rect(active_id);
        NodeState& s = ctx.state;
        Spring x{s.user[0], theme::motion::kTabBar}, w{s.user[2], theme::motion::kTabBar};
        x.velocity = s.user[1];
        w.velocity = s.user[3];
        x.target = t.x + 12;
        w.target = t.w - 24;
        if (!s.user_set || ctx.reduced) {
            x.snap();
            w.snap();
            s.user_set = true;
        } else {
            x.step(ctx.dt);
            w.step(ctx.dt);
        }
        s.user[0] = x.value, s.user[1] = x.velocity, s.user[2] = w.value, s.user[3] = w.velocity;
        if (!x.settled(.2f) || !w.settled(.2f)) ctx.animate();
        const Rect bar{x.value, ctx.rect.bottom() - 12 - 5, w.value, 5};
        const Quad q = skewed(bar, kSeamTan);
        ctx.canvas.glow(q, 14, rgba(255, 42, 85, .35f));
        ctx.canvas.glow(q, 18, rgba(45, 128, 255, .25f));
        ctx.canvas.fill(q, Gradient::linear({bar.x, 0}, {bar.right(), 0}, c::kRed, c::kBlue));
    };
    auto g = ui.open(id, b, {}, nullptr, underline);
    prompt(ui, id + "/prev", Prompt::TabPrev, Box{.margin = {8, 0, 8, 0}});
    TextEngine& te = ui.text();
    for (std::size_t i = 0; i < tabs.size(); ++i) {
        const Tab t = tabs[i];
        const bool on = static_cast<int>(i) == active;
        Focus f;
        f.nav = false;
        Box tb;
        tb.h = Size::fixed(theme::kTopBand);
        ui.leaf(
            t.id, tb, [&te, t](float) { return Vec2{te.width(tx::kTab, t.label) + 34, theme::kTopBand}; },
            [t, on](PaintContext& ctx) {
                Canvas& cv = ctx.canvas;
                const Rect r = ctx.rect;
                const Vec2 pos{r.x + 17, centred_y(ctx.text, tx::kTab, r)};
                if (on) {
                    ctx.text.draw(cv, tx::kTab, t.label, {pos.x - 2, pos.y}, rgba(255, 42, 85, .7f));
                    ctx.text.draw(cv, tx::kTab, t.label, {pos.x + 2, pos.y}, rgba(45, 128, 255, .7f));
                    ctx.text.draw(cv, tx::kTab, t.label, pos, rgb(0xffffff));
                } else {
                    ctx.text.draw(cv, tx::kTab, t.label, pos, mix(c::kTabIdle, c::kTabHover, ctx.hover_t));
                }
                if (!t.badge.empty()) {
                    const float bw = ctx.text.width(tx::kTabBadge, t.badge) + 14;
                    const Rect br{r.right() + 2 - bw, r.y + 16, bw, 18};
                    ctx.canvas.fill(skewed(br, kSeamTan), c::kWarn);
                    ctx.text.draw(cv, tx::kTabBadge, t.badge, {br.x + 7, centred_y(ctx.text, tx::kTabBadge, br)},
                                  rgb(0x160f00));
                }
            },
            &f);
    }
    prompt(ui, id + "/next", Prompt::TabNext, Box{.margin = {8, 0, 8, 0}});
}

void icon_button(Ui& ui, const std::string& id, const IconButtonSpec& spec, const Box& box) {
    Box b = with_height(box, 34);
    TextEngine& te = ui.text();
    Focus f;
    f.nav = spec.nav;
    f.pad = 4;
    // (Short of room: the label goes, the icon stays: shrink_order 2.)
    if (!spec.icon.empty() && !spec.label.empty() && b.w.mode == Size::Fit && b.min_w == 0) {
        b.min_w = 28 + 17;
        if (b.shrink_order == 0) b.shrink_order = 2;
    }
    ui.leaf(
        id, b,
        [&te, spec](float) {
            return Vec2{
                28 + (spec.icon.empty() ? 0 : 17) +
                    (spec.label.empty() ? 0 : (spec.icon.empty() ? 0 : 8) + te.width(tx::kIconButton, spec.label)),
                34};
        },
        [spec](PaintContext& ctx) {
            const Rect r = ctx.rect;
            const float hv = std::max(ctx.hover_t, ctx.focus_t);
            const Color border = spec.on ? rgba(98, 212, 255, .5f) : rgba(255, 255, 255, .16f);
            surface(ctx.canvas, r, mix(rgba(255, 255, 255, .05f), rgba(255, 255, 255, .12f), hv), border);
            const Color col = spec.on ? c::kCyan : mix(c::kTabHover, rgb(0xffffff), hv);
            const bool label =
                !spec.label.empty() &&
                (spec.icon.empty() || r.w >= 28 + 17 + 8 + ctx.text.width(tx::kIconButton, spec.label) - .5f);
            float x = label ? r.x + 14 : r.x + (r.w - 17) / 2;
            if (!spec.icon.empty()) {
                icon(ctx.canvas, ctx.icons, spec.icon, {x, r.y + (r.h - 17) / 2, 17, 17}, col);
                x += 17 + 8;
            }
            if (label)
                ctx.text.draw(ctx.canvas, tx::kIconButton, spec.label, {x, centred_y(ctx.text, tx::kIconButton, r)},
                              col);
        },
        &f);
}

void caption_buttons(Ui& ui, const std::string& id, bool minimise, bool fullscreen_toggle, bool is_fullscreen,
                     bool close, const Box& box) {
    // Like Windows' own caption buttons: no gaps, no frames, flush with the window's top and right edges (give the
    // group the band's full height: they sit at its top); hovered: a light wash, the close button Windows' red.
    Box b = box;
    b.layout = Layout::Row;
    b.gap = 0;
    b.align = Align::Start;
    auto g = ui.open(id, b);
    auto one = [&](const std::string& part, const std::string& ic, bool danger) {
        Focus f;
        f.nav = false;
        f.skewed = false;
        f.pad = 0;
        Box bb;
        bb.w = Size::fixed(m::kCaptionButtonWidth);
        bb.h = Size::fixed(m::kCaptionButtonHeight);
        ui.leaf(id + "/" + part, bb, {}, [ic, danger](PaintContext& ctx) {
            const float hv = std::max(ctx.hover_t, ctx.focus_t);
            if (hv > .001f)
                ctx.canvas.fill_rect(ctx.rect, danger ? rgba(196, 43, 28, hv) : rgba(255, 255, 255, .1f * hv));
            const float g = m::kCaptionGlyph;
            const Vec2 cc = ctx.rect.center();
            icon(ctx.canvas, ctx.icons, ic, {cc.x - g / 2, cc.y - g / 2, g, g},
                 mix(rgba(230, 234, 242, .82f), rgb(0xffffff), hv));
        }, &f);
    };
    if (minimise) one("min", "stroke:minimise", false);
    if (fullscreen_toggle) one("full", is_fullscreen ? "stroke:windowed" : "stroke:fullscreen", false);
    if (close) one("close", "stroke:close", true);
}

void hint_bar(Ui& ui, const std::string& id, std::span<const Hint> hints, const Box& box) {
    Box b = box;
    b.layout = Layout::Row;
    b.gap = 22;
    b.align = Align::Center;
    auto g = ui.open(id, b);
    TextEngine& te = ui.text();
    const Glyphs gl = ui.glyphs();
    for (std::size_t i = 0; i < hints.size(); ++i) {
        const Hint h = hints[i];
        ui.leaf(
            id + "/" + std::to_string(i), Box{},
            [&te, h, gl](float) { return Vec2{prompt_width(te, gl, h.prompt) + 8 + te.width(tx::kHint, h.label), 24}; },
            [h](PaintContext& ctx) {
                const float cy = ctx.rect.y + ctx.rect.h / 2;
                const float w = draw_prompt(ctx.canvas, ctx.text, ctx.icons, ctx.glyphs, h.prompt, ctx.rect.x, cy);
                ctx.text.draw(ctx.canvas, tx::kHint, h.label,
                              {ctx.rect.x + w + 8, centred_y(ctx.text, tx::kHint, ctx.rect)}, rgb(0xd9dee9));
            });
    }
}

// ---- crimson lists --------------------------------------------------------------------------------------------------

void slab(Ui& ui, const std::string& id, const SlabSpec& spec, Focus focus, const Box& box) {
    focus.straight_left = true;
    Box b = with_height(box, m::kSlabHeight);
    if (zero(b.margin)) b.margin = {0, 0, 0, 18};  // (its left edge in line with the rows under it)
    focus.pad = 8;
    focus.disabled = focus.disabled || spec.disabled;
    ui.leaf(
        id, b, [](float) { return Vec2{300, m::kSlabHeight}; },
        [spec](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const float f = ctx.focus_t;
            Rect r = ctx.rect;
            // Focused: 2 % taller (its upright left edge stays in line with the rows) and brighter, its glow breathing.
            const float s = 1 + .02f * f;
            r = {r.x, r.center().y - r.h * s / 2, r.w, r.h * s};
            const Quad q = straight_left(r, kSeamTan);
            const bool dis = spec.disabled;
            const float breathe = ctx.reduced ? 0 : .5f + .5f * std::sin(static_cast<float>(ctx.now) * 2 * kPi / 1.6f);
            if (!dis) {
                Rect low = r;
                low.y += 12;
                low.h -= 8;
                cv.glow(straight_left(low, kSeamTan), 26 + 8 * f * breathe, rgba(255, 42, 85, .42f + .2f * f * breathe));
            }
            const float bright = 1 + .08f * f;
            auto col = [&](Color cc) {
                if (dis) {
                    const float g = (cc.r * .3f + cc.g * .59f + cc.b * .11f);
                    cc =
                        mix(rgba(static_cast<int>(g * 255), static_cast<int>(g * 255), static_cast<int>(g * 255), cc.a),
                            cc, .35f);
                    return brightened(cc, .72f);
                }
                return brightened(cc, bright);
            };
            cv.fill(q, Gradient::css(r, 100, {{0, col(c::kSlabA)}, {.45f, col(c::kSlabB)}, {1, col(c::kSlabC)}}));
            // Streaks and a sheen running through it (still under Reduce motion).
            if (!dis && !ctx.reduced) {
                const float t = static_cast<float>(ctx.now);
                static constexpr float kL[6][4] = {{16, 180, 1.1f, 0}, {32, 120, .8f, .3f}, {50, 240, 1.3f, .6f},
                                                   {68, 160, .9f, .1f}, {84, 200, 1.2f, .45f}, {98, 110, .7f, .8f}};
                for (const auto& l : kL) {
                    const float ph = std::fmod(t / l[2] + l[3], 1.f);
                    const float x0 = 620 - ph * 940, x1 = x0 + l[1];
                    const float a = std::max(0.f, x0), b2 = std::min(r.w, x1);
                    if (b2 <= a) continue;
                    const Rect part{r.x + a, r.y + l[0] * s, b2 - a, 2};
                    cv.fill(shaped_part(r, part, Shape::StraightLeft, kSeamTan), Gradient::linear({r.x + x0, 0}, {r.x + x1, 0}, rgba(255, 255, 255, 0),
                                                               rgba(255, 255, 255, .55f)));
                }
                const float ph = std::fmod(t, 3.4f) / 3.4f;
                if (ph < .55f) {
                    const float e = ease::cubic_bezier(.5f, 0, .2f, 1, ph / .55f);
                    const float x0 = -180 + e * 900, x1 = x0 + 140;
                    const float a = std::max(0.f, x0), b2 = std::min(r.w, x1);
                    if (b2 > a)
                        cv.fill(shaped_part(r, {r.x + a, r.y, b2 - a, r.h}, Shape::StraightLeft, kSeamTan),
                                Gradient::linear3({r.x + x0, 0}, {r.x + x1, 0}, rgba(255, 255, 255, 0), .5f,
                                                  rgba(255, 255, 255, .4f), rgba(255, 255, 255, 0)));
                }
                ctx.animate();
            }
            // Inner light along the top, shade along the bottom.
            cv.line(q.p[0] + Vec2{0, .5f}, q.p[1] + Vec2{0, .5f}, 1, rgba(255, 255, 255, .45f));
            cv.fill(shaped_part(r, {r.x, r.bottom() - 3, r.w, 3}, Shape::StraightLeft, kSeamTan), rgba(0, 0, 0, .25f));
            // Content (upright): the word, two small lines, the Accept glyph when focused.
            const TextStyle big =
                spec.mid ? TextStyle{tx::kSlabBig.font, 78, tx::kSlabBig.tracking, true, 1} : tx::kSlabBig;
            const float bx = r.x + 40;
            const float by = r.y + (r.h - ctx.text.line_height(big)) / 2;
            ctx.text.draw(cv, big, spec.big, {bx, by + 4}, rgba(0, 0, 0, .22f));
            const float bw = ctx.text.draw(cv, big, spec.big, {bx, by}, rgb(0xffffff));
            const float lh = ctx.text.line_height(tx::kSlabSmall);
            const float sx = bx + bw + 18, sy = r.y + r.h / 2 - lh - 2;
            ctx.text.draw(cv, tx::kSlabSmall, spec.line1, {sx, sy}, rgba(255, 255, 255, .9f));
            ctx.text.draw(cv, tx::kSlabSmall, spec.line2, {sx, sy + lh + 4}, rgba(255, 255, 255, .9f));
            if (f > .01f) {
                const float pw = prompt_width(ctx.text, ctx.glyphs, Prompt::Accept);
                draw_prompt(cv, ctx.text, ctx.icons, ctx.glyphs, Prompt::Accept, r.right() - 30 - pw, r.y + r.h / 2, f);
            }
        },
        &focus);
}

void menu_row(Ui& ui, const std::string& id, const MenuRowSpec& spec, Focus focus, const Box& box) {
    focus.straight_left = true;
    const bool tall = !spec.caption.empty();
    Box b = with_height(box, tall ? 72 : spec.compact ? 50 : m::kMenuRowHeight);
    focus.disabled = focus.disabled || spec.disabled;
    TextEngine& te = ui.text();
    ui.leaf(
        id, b,
        [&te, spec, tall](float) {
            return Vec2{
                26 + 36 + 16 + te.width(tx::kMenuTitle, spec.title) + 16 + te.width(tx::kMenuValue, spec.value) + 40,
                tall ? 72.f : m::kMenuRowHeight};
        },
        [spec, tall](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            const float f = ctx.focus_t;
            if (spec.disabled) cv.push_layer({}, .42f);
            row_surface(cv, r, f, c::kRowFill, c::kRowStrokeRed, c::kRowFocusA, c::kRowFocusB, c::kRowFocusStroke);
            float x = r.x + (spec.compact ? 24 : 26);
            const float cy = r.y + r.h / 2;
            if (spec.check >= 0) {
                const Rect cb{x, cy - 10, 20, 20};
                const Quad cq = skewed(cb, kSeamTan);
                if (spec.check == 1) {
                    cv.fill(cq, rgb(0xffffff));
                    icon(cv, ctx.icons, "stroke:check:3.4", cb.outset(-3.5f), rgb(0x07080d));
                } else {
                    if (spec.check == 2) cv.fill(cq, rgba(255, 255, 255, .2f));
                    cv.stroke(cq, 2, rgba(255, 255, 255, .75f));
                    if (spec.check == 2) cv.fill_rect({cb.center().x - 5, cb.center().y - 1.5f, 10, 3}, rgb(0xffffff));
                }
                x += 20 + 14;
            } else if (spec.number > 0) {
                constexpr TextStyle kNum{theme::Font::DisplayBlackItalic, 40, 0, false, 1};
                const std::string n = std::to_string(spec.number);
                ctx.text.draw(cv, kNum, n, {x, cy - 20}, TextPaint{spec.ok ? c::kOk : rgba(255, 200, 212, .6f), 1.4f});
                x += 26 + 16;
            } else if (!spec.icon.empty()) {
                const Rect ib{x, cy - 18, 36, 36};
                surface(cv, ib, spec.danger ? rgba(255, 93, 113, .1f) : rgba(255, 42, 85, .16f),
                        spec.danger ? rgba(255, 93, 113, .5f) : rgba(255, 120, 150, .42f));
                icon(cv, ctx.icons, spec.icon, {ib.x + 8.5f, ib.y + 8.5f, 19, 19}, rgb(0xffd0da));
                x += 36 + 16;
            }
            constexpr TextStyle kChev = tx::kChevron;
            const float chev_w = ctx.text.width(kChev, "›");
            const float chev_x = r.right() - 22 - chev_w + 4 * f;
            ctx.text.draw(cv, kChev, "›", {chev_x, centred_y(ctx.text, kChev, r)},
                          mix(rgba(255, 255, 255, .3f), rgb(0xffffff), f));
            float right = r.right() - 22 - chev_w - 16;
            if (!spec.value.empty()) {
                const Color vc = spec.value_tone == Tone::Neutral ? mix(c::kRedDim, rgb(0xffe3e9), f)
                                                                  : tone_text(spec.value_tone, c::kRedDim);
                const float vw = ctx.text.width(tx::kMenuValue, spec.value);
                ctx.text.draw(cv, tx::kMenuValue, spec.value, {right - vw, centred_y(ctx.text, tx::kMenuValue, r)}, vc);
                right -= vw + 16;
            }
            const Color title_col = spec.danger ? rgb(0xffd3da) : c::kText;
            if (tall) {
                constexpr TextStyle kCap{theme::Font::DisplayBoldItalic, 12.5f, .2f, true, 1};
                const TextStyle ts = spec.mono_title ? TextStyle{theme::Font::Mono, 15, 0, false, 1.1f}
                                                     : TextStyle{tx::kMenuTitle.font, 21, .05f, true, 1};
                const float h = ctx.text.line_height(kCap) + 5 + ctx.text.line_height(ts);
                const float y = cy - h / 2;
                ctx.text.draw(cv, kCap, spec.caption, {x, y}, mix(c::kRedDim, rgb(0xffe3e9), f));
                ctx.text.draw(
                    cv, ts,
                    ctx.text.ellipsize(ts, spec.title, right - x, spec.mono_title ? Ellipsis::Middle : Ellipsis::End),
                    {x, y + ctx.text.line_height(kCap) + 5}, title_col);
            } else {
                const TextStyle ts = spec.compact ? TextStyle{tx::kMenuTitle.font, 19, .06f, true, 1} : tx::kMenuTitle;
                ctx.text.draw(cv, ts, ctx.text.ellipsize(ts, spec.title, right - x), {x, centred_y(ctx.text, ts, r)},
                              title_col);
            }
            if (spec.disabled) cv.pop_layer();
        },
        &focus);
}

void fighter_tile(Ui& ui, const std::string& id, const TileSpec& spec, Focus focus) {
    Box b;
    b.w = Size::fixed(m::kTileWidth);
    b.h = Size::fixed(m::kTileHeight);
    focus.pad = 5;
    ui.leaf(
        id, b, {},
        [spec](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            const float f = ctx.focus_t;
            const Quad q = skewed(r, kSeamTan);
            const TileState st = spec.state;
            const bool none = st == TileState::None, notowned = st == TileState::NotOwned,
                       checking = st == TileState::Checking;
            const bool pic = spec.portrait != 0 && !none && !notowned;
            // Body.
            if (pic) {
                // The fighter, over a dark ground, its lower part darkened for the name; lit up when focused.
                cv.fill(q, rgba(10, 6, 10, .92f));
                // (The slanted sides show the picture beyond the rectangle, at its scale.)
                const Rect u = spec.portrait_uv;
                const float d = r.h / 2 * kSeamTan, du = u.w * d / r.w;
                cv.picture(spec.portrait, {r.x - d, r.y, r.w + 2 * d, r.h}, {u.x - du, u.y, u.w + 2 * du, u.h},
                           std::span<const Vec2>(q.p, 4), [](Vec2) { return 1.f; },
                           rgba(255, 255, 255, .86f + .14f * f), 2);
                cv.fill(q, Gradient::css(r, 180, {{0, rgba(0, 0, 0, 0)}, {.5f, rgba(0, 0, 0, 0)},
                                                  {.78f, rgba(8, 2, 6, .55f)}, {1, rgba(8, 2, 6, .9f)}}));
            } else if (none) cv.fill(q, rgba(20, 8, 12, .72f));
            else if (notowned) cv.fill(q, rgba(14, 8, 10, .82f));
            else if (checking) cv.fill(q, rgba(20, 10, 14, .72f));
            else {
                Color top = rgba(255, 42, 85, .42f), mid = rgba(60, 6, 20, .85f), low = rgba(10, 6, 10, .92f);
                if (spec.tone == TileTone::Orange)
                    top = rgba(255, 110, 60, .42f), mid = rgba(70, 16, 8, .85f), low = rgba(12, 6, 6, .92f);
                if (spec.tone == TileTone::Pink)
                    top = rgba(255, 42, 140, .36f), mid = rgba(70, 8, 46, .82f), low = rgba(10, 6, 14, .92f);
                const float lift = 1 + .4f * f;
                cv.fill(q,
                        Gradient::css(
                            r, 170,
                            {{0, brightened(top, lift)}, {.62f, brightened(mid, lift)}, {1, brightened(low, lift)}}));
                // Halftone dots in the upper corner.
                for (float y = r.y + 3; y < r.y + r.h * .55f; y += 6)
                    for (float x = r.x - 10; x < r.right() + 10; x += 6) {
                        const Vec2 p = sk(r, {x, y});
                        const float t = (y - r.y) / (r.h * .55f) + (r.right() - x) / r.w * .2f;
                        const float a = .16f * (1 - t);
                        if (a <= .01f || x < r.x + 2 || x > r.right() - 2) continue;
                        cv.fill_rect({p.x - .6f, p.y - .6f, 1.2f, 1.2f}, rgba(255, 255, 255, a));
                    }
            }
            if (notowned) {
                // Diagonal stripes.
                cv.push_clip(r.outset(0));
                for (float d = -r.h; d < r.w + r.h; d += 12) {
                    const Vec2 a = sk(r, {r.x + d, r.y}), b2 = sk(r, {r.x + d - r.h, r.bottom()});
                    cv.line(a, b2, 4, rgba(255, 255, 255, .04f));
                }
                cv.pop_clip();
            }
            // The top accent.
            if (!notowned) {
                const Quad top = sk_rect(r, {r.x, r.y, r.w, 3});
                if (spec.tone == TileTone::Pink && !none)
                    cv.fill(top, Gradient::linear({r.x, 0}, {r.right(), 0}, c::kRed, rgb(0xff4fc0)));
                else cv.fill(top, (spec.tone == TileTone::Orange ? rgb(0xff7a3c) : c::kRed).faded(none ? .5f : 1));
            }
            // Border.
            const Color border = notowned    ? rgba(255, 255, 255, .1f)
                                 : none      ? rgba(255, 200, 212, .34f)
                                 : spec.busy ? c::kCyan
                                 : checking  ? rgba(255, 255, 255, .18f)
                                             : rgba(255, 255, 255, .14f);
            if (none && !spec.busy) dashed(cv, q, 1, 4, 3, mix(border, rgb(0xffffff), f));
            else cv.stroke(q, 1, mix(border, rgb(0xffffff), f));
            if (checking && !ctx.reduced) {
                const float ph = std::fmod(static_cast<float>(ctx.now) / 1.3f, 1.f);
                const float x0 = r.x + r.w * (1.5f - 3 * ph) - r.w * .4f;
                const float a = std::max(r.x, x0), b2 = std::min(r.right(), x0 + r.w * .8f);
                if (b2 > a)
                    cv.fill(sk_rect(r, {a, r.y, b2 - a, r.h}),
                            Gradient::linear3({x0, 0}, {x0 + r.w * .8f, 0}, rgba(98, 212, 255, 0), .5f,
                                              rgba(98, 212, 255, .25f), rgba(98, 212, 255, 0)));
                ctx.animate();
            }
            // Code and name.
            const Color code_col = notowned   ? rgb(0x7d6a70)
                                   : checking ? rgb(0xa8949a)
                                   : none     ? rgb(0xecd5db)
                                              : rgb(0xffffff);
            if (!pic) {
                TextStyle code = tx::kTileCode;
                code.size *= 1 + .14f * f;
                const float cw = ctx.text.width(code, spec.code);
                ctx.text.draw(cv, code, spec.code,
                              {r.center().x - cw / 2, r.y + 19 - (code.size - tx::kTileCode.size) / 2}, code_col);
            }
            const std::string name = ctx.text.ellipsize(tx::kTileName, spec.name, r.w + 12);
            const float nw = ctx.text.width(tx::kTileName, name);
            ctx.text.draw(cv, tx::kTileName, name,
                          {r.center().x - nw / 2, r.bottom() - 10 - ctx.text.line_height(tx::kTileName)},
                          notowned ? rgb(0x7d6a70) : rgb(0xecd9de));
            // Corner badge.
            Color bc = rgb(0xecd5db);
            std::string ic = "stroke:dots:3";
            switch (st) {
            case TileState::Added: bc = c::kOk, ic = "stroke:check:3"; break;
            case TileState::Update: bc = c::kWarn, ic = "stroke:up:3"; break;
            case TileState::None: bc = rgb(0xecd5db), ic = "stroke:plus:3"; break;
            case TileState::NotOwned: bc = rgb(0x8d7a80), ic = "stroke:ban:3"; break;
            case TileState::Newer: bc = c::kCyan, ic = "stroke:diamond:3"; break;
            case TileState::Checking: bc = c::kCyan, ic = "stroke:dots:3"; break;
            }
            const Rect br{r.right() + 3 - 22, r.y - 5, 22, 22};
            const Quad bq = skewed(br, kSeamTan);
            cv.fill(bq, rgb(0x120a0d));
            cv.stroke(bq, 1.5f, bc);
            icon(cv, ctx.icons, ic, {br.x + 5, br.y + 5, 12, 12}, bc);
            if (!spec.tag.empty()) {
                const float tw = ctx.text.width(tx::kTileTag, spec.tag) + 8;
                const Rect tr{r.x + 4, r.y - 4, tw, 14};
                cv.fill(skewed(tr, kSeamTan), rgb(0xf1e4e8));
                ctx.text.draw(cv, tx::kTileTag, spec.tag, {tr.x + 4, centred_y(ctx.text, tx::kTileTag, tr)},
                              rgb(0x0b0d14));
            }
        },
        &focus);
}

void group_header(Ui& ui, const std::string& id, const GroupHeaderSpec& spec, const Box& box) {
    // A wrapping row: short of room, the buttons go to a line of their own, on the right.
    Box b = box;
    b.layout = Layout::Row;
    b.wrap = true;
    b.align = Align::Center;
    b.justify = Align::End;
    b.gap = 12;
    b.line_gap = 6;
    b.min_h = 30;
    auto g = ui.open(id, b);
    TextSpec title{spec.title, tx::kGroupTitle, c::kText};
    text(ui, id + "/title", title);
    TextEngine& te = ui.text();
    const std::string count = spec.count, sub = spec.sub;
    const Color sub_col = tone_text(spec.sub_tone, c::kRedFaint);
    ui.leaf(
        id + "/count", Box{},
        [&te, count, sub](float) {
            return Vec2{std::max(te.width(tx::kGroupCount, count), te.width(tx::kGroupCount, sub)),
                        te.line_height(tx::kGroupCount) * (sub.empty() ? 1 : 2) + (sub.empty() ? 0 : 3)};
        },
        [count, sub, sub_col](PaintContext& ctx) {
            ctx.text.draw(ctx.canvas, tx::kGroupCount, count, {ctx.rect.x, ctx.rect.y}, c::kRedDim);
            if (!sub.empty())
                ctx.text.draw(ctx.canvas, tx::kGroupCount, sub,
                              {ctx.rect.x, ctx.rect.y + ctx.text.line_height(tx::kGroupCount) + 3}, sub_col);
        });
    ui.leaf(id + "/space", Box{.w = Size::grow(), .h = Size::fixed(1)}, {}, {});
    {
        auto bg = ui.open(id + "/buttons", Box{.layout = Layout::Row, .gap = 8});
        for (const HeaderButton& hb : spec.buttons) {
            ButtonSpec bs;
            bs.label = hb.label;
            bs.size = ButtonSize::Tiny;
            bs.disabled = hb.disabled;
            bs.half = Half::Crimson;
            Focus f;
            f.group = spec.focus_group;
            button(ui, hb.id, bs, f);
        }
    }
}

void setting_row(Ui& ui, const std::string& id, const SettingRowSpec& spec, Focus focus, const Box& box) {
    focus.straight_left = true;
    const bool two = !spec.detail.empty();
    Box b = with_height(box, two ? 52 : m::kSettingRowHeight);
    TextEngine& te = ui.text();
    const float vw = spec.chevron ? 0 : std::max(m::kValueBoxMin, te.width(tx::kSettingValue, spec.value) + 24);
    focus.disabled = focus.disabled || spec.disabled;
    if (!spec.chevron) {
        focus.adjust = true;
        // Clicks on the arrows: right arrow 22..38 points from the right edge, left one after the value box.
        focus.zones[0] = {22 - 6, 38 + 5, 1};
        focus.zones[1] = {38 + 10 + vw + 10 - 5, 38 + 10 + vw + 10 + 16 + 6, -1};
        focus.zone_count = 2;
    }
    ui.leaf(
        id, b,
        [&te, spec, vw](float) {
            return Vec2{26 + te.width(tx::kSettingTitle, spec.title) + 18 + 16 + 10 + vw + 10 + 16 + 22,
                        m::kSettingRowHeight};
        },
        [spec, vw, two](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            const float f = ctx.focus_t;
            NodeState& s = ctx.state;
            // A new value slides in from the side it came from; its arrow kicks.
            const float h = hash01(spec.value);
            if (!s.user_set) {
                s.user[0] = h;
                s.user[1] = -1e6f;
                s.user_set = true;
            } else if (s.user[0] != h) {
                s.user[0] = h;
                s.user[1] = static_cast<float>(ctx.now);
                s.user[2] = static_cast<float>(spec.slide);
            }
            const float age = static_cast<float>(ctx.now) - s.user[1];
            const float slide = ctx.reduced || age >= .2f ? 0 : (1 - ease::out_expo_like(age / .2f)) * 24 * s.user[2];
            const float kick = ctx.reduced || age >= .25f ? 0 : 1 - age / .25f;
            if (slide != 0 || kick > 0) ctx.animate();
            if (spec.disabled) cv.push_layer({}, .42f);
            row_surface(cv, r, f, c::kRowFill, rgba(255, 120, 150, .2f), rgba(255, 42, 85, .58f),
                        rgba(150, 10, 40, .4f), c::kRowFocusStroke);
            const float cy = r.y + r.h / 2;
            float right = r.right() - 22;
            if (spec.chevron) {
                constexpr TextStyle kChev{theme::Font::DisplayBlackItalic, 26, 0, false, 1};
                const float cw = ctx.text.width(kChev, "›");
                ctx.text.draw(cv, kChev, "›", {right - cw, centred_y(ctx.text, kChev, r)},
                              mix(rgba(255, 255, 255, .3f), rgb(0xffffff), f));
                right -= cw + 18;
                if (!spec.value.empty()) {
                    const Color vc = spec.value_on ? c::kWarn : c::kRedFaint;
                    const float w = ctx.text.width(tx::kMenuValue, spec.value);
                    ctx.text.draw(cv, tx::kMenuValue, spec.value, {right - w, centred_y(ctx.text, tx::kMenuValue, r)},
                                  vc);
                    right -= w + 18;
                }
            } else {
                const Color arrow = mix(rgba(255, 255, 255, .3f), rgb(0xffffff), f);
                const int kdir = static_cast<int>(s.user[2]);
                auto arrow_col = [&](int d) { return kdir == d ? mix(arrow, c::kCyan, kick) : arrow; };
                auto arrow_scale = [&](int d) { return kdir == d ? 1 + .6f * kick : 1.f; };
                draw_arrow(cv, {right - 8, cy}, 8 * arrow_scale(1), 12 * arrow_scale(1), 1, arrow_col(1));
                right -= 16 + 10;
                const Rect vb{right - vw, cy - m::kValueBoxHeight / 2, vw, m::kValueBoxHeight};
                if (spec.value_on)
                    surface(cv, vb, Gradient::css(vb, 100, {{0, rgb(0x3b8cff)}, {1, rgb(0x1452d6)}}),
                            rgba(160, 205, 255, .8f));
                else
                    surface(cv, vb, rgba(2, 3, 8, .7f), rgba(255, 255, 255, .22f));
                cv.push_clip(vb);
                const float tw = ctx.text.width(tx::kSettingValue, spec.value);
                ctx.text.draw(cv, tx::kSettingValue, spec.value,
                              {vb.center().x - tw / 2 + slide, centred_y(ctx.text, tx::kSettingValue, vb)},
                              rgba(255, 255, 255, 1 - std::fabs(slide) / 30));
                cv.pop_clip();
                right -= vw + 10;
                draw_arrow(cv, {right - 8, cy}, 8 * arrow_scale(-1), 12 * arrow_scale(-1), -1, arrow_col(-1));
                right -= 16 + 18;
            }
            const float x = r.x + 26;
            if (two) {
                constexpr TextStyle kCode{theme::Font::Mono, 12.5f, 0, false, 1};
                const float hh = ctx.text.line_height(tx::kSettingTitle) + 6 + ctx.text.line_height(kCode);
                const float y = cy - hh / 2;
                ctx.text.draw(cv, tx::kSettingTitle, ctx.text.ellipsize(tx::kSettingTitle, spec.title, right - x),
                              {x, y}, c::kText);
                ctx.text.draw(cv, kCode, ctx.text.ellipsize(kCode, spec.detail, right - x, Ellipsis::Middle),
                              {x, y + ctx.text.line_height(tx::kSettingTitle) + 6}, mix(c::kRedDim, rgb(0xffe3e9), f));
            } else {
                ctx.text.draw(cv, tx::kSettingTitle, ctx.text.ellipsize(tx::kSettingTitle, spec.title, right - x),
                              {x, centred_y(ctx.text, tx::kSettingTitle, r)}, c::kText);
            }
            if (spec.disabled) cv.pop_layer();
        },
        &focus);
}

void section_tabs(Ui& ui, const std::string& id, std::span<const Section> sections, int active, const Box& box,
                  int focus_group) {
    Box b = box;
    b.layout = Layout::Row;
    b.align = Align::Center;
    b.gap = 8;
    if (zero(b.margin)) b.margin.bottom = 16;
    auto g = ui.open(id, b);
    const bool one = sections.size() < 2;
    if (!one) prompt(ui, id + "/prev", Prompt::SectionPrev);
    TextEngine& te = ui.text();
    for (std::size_t i = 0; i < sections.size(); ++i) {
        const Section s = sections[i];
        const bool on = static_cast<int>(i) == active;
        Focus f;
        f.disabled = s.disabled;
        f.group = focus_group;
        ui.leaf(
            s.id, Box{.h = Size::fixed(m::kSectionHeight)},
            [&te, s](float) { return Vec2{40 + te.width(tx::kSection, s.label), m::kSectionHeight}; },
            [s, on](PaintContext& ctx) {
                const Rect r = ctx.rect;
                const float fo = ctx.focus_t;
                if (s.disabled) ctx.canvas.push_layer({}, .42f);
                if (on) {
                    const Color a = mix(rgb(0xff2a55), rgb(0xff5a7d), fo), b2 = mix(rgb(0xa80d33), rgb(0xc8103a), fo);
                    surface(ctx.canvas, r, Gradient::css(r, 100, {{0, a}, {1, b2}}),
                            mix(rgba(255, 170, 185, .8f), rgb(0xffffff), fo));
                } else {
                    surface(ctx.canvas, r, rgba(255, 255, 255, .04f),
                            mix(rgba(255, 120, 150, .22f), rgb(0xffffff), fo));
                }
                ctx.text.draw(ctx.canvas, tx::kSection, s.label, {r.x + 20, centred_y(ctx.text, tx::kSection, r)},
                              on ? rgb(0xffffff) : rgb(0xd8b9c1));
                if (s.disabled) ctx.canvas.pop_layer();
            },
            &f);
    }
    if (!one) prompt(ui, id + "/next", Prompt::SectionNext);
}

void key_row(Ui& ui, const std::string& id, const KeyRowSpec& spec, Focus focus, const Box& box) {
    focus.straight_left = true;
    Box b = with_height(box, m::kKeyRowHeight);
    if (zero(b.margin)) b.margin.bottom = 5;
    TextEngine& te = ui.text();
    ui.leaf(
        id, b,
        [&te, spec](float) {
            return Vec2{14 + 22 + 10 + te.width(tx::kKeyName, spec.name) + 10 +
                            std::max(44.f, te.width(tx::kKeyCap, spec.key) + 18) + 12,
                        m::kKeyRowHeight};
        },
        [spec](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            const float f = ctx.focus_t;
            float flash = 0;
            if (spec.flash_until > ctx.now && !ctx.reduced) {
                const float left = static_cast<float>(spec.flash_until - ctx.now);
                flash = std::fmod(left, .5f) / .5f;
                ctx.animate();
            }
            row_surface(cv, r, f, brightened(rgba(255, 255, 255, .04f), 1 + flash), rgba(255, 120, 150, .16f),
                        rgba(255, 42, 85, .56f), rgba(150, 10, 40, .38f), c::kRowFocusStroke);
            const float cy = r.y + r.h / 2;
            icon(cv, ctx.icons, spec.icon, {r.x + 14, cy - 11, 22, 22}, mix(rgb(0xe8c9d0), rgb(0xffffff), f));
            const float kw = std::max(44.f, ctx.text.width(tx::kKeyCap, spec.key) + 18);
            const Rect kc{r.right() - 12 - kw, cy - 13, kw, 26};
            const float x = r.x + 14 + 22 + 10;
            ctx.text.draw(cv, tx::kKeyName, ctx.text.ellipsize(tx::kKeyName, spec.name, kc.x - 10 - x),
                          {x, centred_y(ctx.text, tx::kKeyName, r)}, c::kText);
            Color text_col = rgb(0xffffff);
            if (spec.capturing) {
                const float pulse = ctx.reduced ? 0 : .5f + .5f * std::sin(static_cast<float>(ctx.now) * 2 * kPi / .8f);
                surface(cv, kc,
                        Gradient::css(kc, 100, {{0, brightened(c::kWarn, 1 + .25f * pulse)}, {1, rgb(0xff9a2e)}}),
                        rgb(0xffffff));
                text_col = rgb(0x1a1000);
                if (!ctx.reduced) ctx.animate();
            } else if (f > .5f) {
                surface(cv, kc, Gradient::linear({0, kc.y}, {0, kc.bottom()}, rgb(0xffffff), rgb(0xd9dde8)),
                        spec.swapped ? c::kWarn : rgba(255, 255, 255, .28f));
                text_col = rgb(0x0a0c12);
            } else {
                surface(cv, kc, Gradient::linear({0, kc.y}, {0, kc.bottom()}, rgb(0x2a3042), rgb(0x171b27)),
                        spec.swapped ? c::kWarn : rgba(255, 255, 255, .28f));
            }
            const float tw = ctx.text.width(tx::kKeyCap, spec.key);
            ctx.text.draw(cv, tx::kKeyCap, spec.key, {kc.center().x - tw / 2, centred_y(ctx.text, tx::kKeyCap, kc)},
                          text_col);
        },
        &focus);
}

void step_row(Ui& ui, const std::string& id, const StepRowSpec& spec, const Box& box) {
    Box b = with_height(box, m::kStepRowHeight);
    if (zero(b.margin)) b.margin.bottom = 8;
    ui.leaf(id, b, [](float) { return Vec2{20 + 24 + 14 + 118 + 14 + 30 + 14 + 96 + 20, m::kStepRowHeight}; },
            [spec](PaintContext& ctx) {
                Canvas& cv = ctx.canvas;
                const Rect r = ctx.rect;
                const StepState st = spec.state;
                const Quad q = straight_left(r, kSeamTan);
                Color name_col = c::kRedDim, icon_col = c::kRedFaint, count_col = c::kRedFaint;
                switch (st) {
                case StepState::Current:
                    cv.fill(q, Gradient::css(r, 100, {{0, rgba(255, 42, 85, .42f)}, {1, rgba(120, 10, 40, .3f)}}));
                    if (!ctx.reduced) {
                        // Moving stripes.
                        const float off = std::fmod(static_cast<float>(ctx.now) * 45, 20.f);
                        cv.push_clip(r);
                        for (float x = r.x - r.h - 20 - off; x < r.right() + r.h; x += 20) {
                            const Vec2 a = sk(r, {x + 10, r.y}), b2 = sk(r, {x + 10 - r.h * .47f, r.bottom()});
                            cv.line(a, b2, 10 * .9f, rgba(255, 255, 255, .07f));
                        }
                        cv.pop_clip();
                        ctx.animate();
                    }
                    cv.stroke(q, 1, rgba(255, 210, 220, .85f));
                    name_col = icon_col = rgb(0xffffff);
                    count_col = rgb(0xffe0e7);
                    break;
                case StepState::Done:
                    cv.fill(q, rgba(255, 255, 255, .035f));
                    cv.stroke(q, 1, rgba(63, 231, 161, .4f));
                    name_col = icon_col = c::kOk;
                    break;
                case StepState::Failed:
                    cv.fill(q, rgba(255, 42, 85, .2f));
                    cv.stroke(q, 1, c::kBad);
                    name_col = icon_col = c::kBad;
                    break;
                default:
                    cv.fill(q, rgba(255, 255, 255, .035f));
                    cv.stroke(q, 1, rgba(255, 120, 150, .18f));
                    break;
                }
                const float cy = r.y + r.h / 2;
                const Rect ib{r.x + 20, cy - 12, 24, 24};
                if (st == StepState::Done) icon(cv, ctx.icons, "stroke:check:3.2", ib.outset(-4), icon_col);
                else if (st == StepState::Failed) icon(cv, ctx.icons, "stroke:cross:3.2", ib.outset(-4), icon_col);
                else {
                    constexpr TextStyle kNum{theme::Font::DisplayBlackItalic, 18, 0, false, 1};
                    const std::string n = std::to_string(spec.number);
                    const float w = ctx.text.width(kNum, n);
                    ctx.text.draw(cv, kNum, n, {ib.center().x - w / 2, centred_y(ctx.text, kNum, ib)}, icon_col);
                }
                const float nx = ib.right() + 14;
                ctx.text.draw(cv, tx::kStepName, ctx.text.ellipsize(tx::kStepName, spec.name, 118),
                              {nx, centred_y(ctx.text, tx::kStepName, r)}, name_col);
                const float bx = nx + 118 + 14, bw = std::max(30.f, r.right() - 20 - 96 - 14 - bx);
                const Rect bar{bx, cy - 3, bw, 6};
                cv.fill(skewed(bar, kSeamTan), rgba(255, 255, 255, .08f));
                const float fr = std::clamp(st == StepState::Done ? 1 : spec.fraction, 0.f, 1.f);
                if (fr > 0) {
                    const Quad fq = sk_rect(bar, {bar.x, bar.y, bar.w * fr, bar.h});
                    if (st == StepState::Done) cv.fill(fq, c::kOk);
                    else cv.fill(fq, Gradient::linear({bar.x, 0}, {bar.x + bar.w * fr, 0}, c::kRed, rgb(0xff8aa2)));
                }
                constexpr TextStyle kCount = tx::kStepCount;
                const float cw = ctx.text.width(kCount, spec.count);
                ctx.text.draw(cv, kCount, spec.count, {r.right() - 20 - cw, centred_y(ctx.text, kCount, r)}, count_col);
            });
}

void file_row(Ui& ui, const std::string& id, const FileRowSpec& spec, Focus focus, const Box& box) {
    focus.straight_left = true;
    Box b = with_height(box, m::kFileRowHeight);
    TextEngine& te = ui.text();
    ui.leaf(
        id, b,
        [&te, spec](float) {
            return Vec2{
                16 + 18 + 12 + te.width(tx::kFileName, spec.name) + 12 + te.width(tx::kFileMeta, spec.meta) + 16,
                m::kFileRowHeight};
        },
        [spec](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            const float f = ctx.focus_t;
            row_surface(cv, r, f, rgba(255, 255, 255, .04f), rgba(255, 120, 150, .16f), rgba(255, 42, 85, .58f),
                        rgba(150, 10, 40, .4f), c::kRowFocusStroke);
            const float cy = r.y + r.h / 2;
            icon(cv, ctx.icons, spec.icon, {r.x + 16, cy - 9, 18, 18}, spec.tone == Tone::Ok ? c::kOk : rgb(0xffc1cd));
            const float mw = ctx.text.width(tx::kFileMeta, spec.meta);
            ctx.text.draw(cv, tx::kFileMeta, spec.meta, {r.right() - 16 - mw, centred_y(ctx.text, tx::kFileMeta, r)},
                          c::kRedDim);
            const float x = r.x + 16 + 18 + 12, room = r.right() - 16 - mw - 12 - x;
            const Color nc = spec.tone == Tone::Ok ? rgb(0xeafff5) : spec.tone == Tone::Dim ? rgb(0xcdb3ba) : c::kText;
            ctx.text.draw(cv, tx::kFileName, ctx.text.ellipsize(tx::kFileName, spec.name, room, Ellipsis::Middle),
                          {x, centred_y(ctx.text, tx::kFileName, r)}, nc);
        },
        &focus);
}

// ---- blue readout ---------------------------------------------------------------------------------------------------

void progress_bar(Ui& ui, const std::string& id, float fraction, Tone tone, const Box& box) {
    Box b = with_height(box, m::kProgressHeight);
    if (zero(b.margin)) b.margin = {0, 6, 0, 12};
    ui.leaf(id, b, [](float) { return Vec2{200, m::kProgressHeight}; }, [fraction, tone](PaintContext& ctx) {
        Canvas& cv = ctx.canvas;
        const Rect r = ctx.rect;
        NodeState& s = ctx.state;
        const bool pulse = fraction < 0;
        const float target = std::clamp(fraction, 0.f, 1.f);
        if (!s.user_set || ctx.reduced) {
            s.user[0] = target;
            s.user_set = true;
        } else {
            s.user[0] += (target - s.user[0]) * (1 - std::exp(-theme::motion::kProgressSmooth * ctx.dt));
            if (std::fabs(s.user[0] - target) < .0005f) s.user[0] = target;
            else ctx.animate();
        }
        const Quad back = skewed(r, kSeamTan);
        cv.fill(back, rgba(2, 4, 12, .85f));
        Color a = rgb(0x1450d0), mid = rgb(0x2d80ff), z = rgb(0x62d4ff);
        if (tone == Tone::Ok) a = rgb(0x1c9b6a), mid = rgb(0x2cc086), z = rgb(0x3fe7a1);
        if (tone == Tone::Bad) a = rgb(0x5e0a1f), mid = rgb(0xa8183a), z = rgb(0xff2a55);
        float x0 = 0, x1 = s.user[0];
        if (pulse) {
            const float t = ctx.reduced ? .5f : .5f - .5f * std::cos(static_cast<float>(ctx.now) * kPi / 1.1f);
            x0 = (-0.4f + 3.1f * t) * .3f;
            x1 = x0 + .3f;
            if (!ctx.reduced) ctx.animate();
        }
        x0 = std::clamp(x0, 0.f, 1.f), x1 = std::clamp(x1, 0.f, 1.f);
        if (x1 > x0) {
            const Rect fill{r.x + r.w * x0, r.y + 1, r.w * (x1 - x0), r.h - 2};
            const Quad fq = sk_rect(r, fill);
            cv.fill(fq, Gradient::linear3({r.x, 0}, {r.x + r.w * std::max(x1, .05f), 0}, a, .55f, mid, z));
            cv.line(fq.p[0] + Vec2{0, .5f}, fq.p[1] + Vec2{0, .5f}, 1, rgba(255, 255, 255, .4f));
            for (float x = fill.x + 22; x < fill.right(); x += 24) {
                const Quad st = sk_rect(r, {x, fill.y, std::min(2.f, fill.right() - x), fill.h});
                cv.fill(st, rgba(0, 0, 0, .18f));
            }
            if (!pulse && x1 < 1) {
                const float ex = sk(r, {r.x + r.w * x1, r.y + r.h / 2}).x;
                const Rect edge{ex - 2, r.y - 4, 4, r.h + 8};
                cv.glow(skewed(edge, 0), 14, c::kCyan.faded(.6f));
                cv.fill_rect(edge, rgb(0xffffff));
            }
        }
        cv.stroke(back, 1, rgba(160, 200, 255, .28f));
    });
}

void pill(Ui& ui, const std::string& id, const std::string& label, Tone tone, bool dot, const Box& box) {
    Box b = with_height(box, m::kPillHeight);
    b.hug = true;  // (a tag: as wide as its word, also in a stretching column)
    TextEngine& te = ui.text();
    ui.leaf(
        id, b,
        [&te, label, dot](float) { return Vec2{26 + (dot ? 13 : 0) + te.width(tx::kPill, label), m::kPillHeight}; },
        [label, tone, dot](PaintContext& ctx) {
            const ToneColors tc = tone_colors(tone);
            surface(ctx.canvas, ctx.rect, tc.fill, tc.border);
            float x = ctx.rect.x + 13;
            if (dot) {
                const float blink = ctx.reduced ? 1 : .625f + .375f * std::cos(static_cast<float>(ctx.now) * 2 * kPi);
                const Vec2 ctr{x + 3.5f, ctx.rect.y + ctx.rect.h / 2};
                ctx.canvas.radial(ctr, 9, tc.text.faded(.5f * blink));
                ctx.canvas.circle(ctr, 3.5f, tc.text.faded(blink));
                if (!ctx.reduced) ctx.animate();
                x += 13;
            }
            ctx.text.draw(ctx.canvas, tx::kPill, label, {x, centred_y(ctx.text, tx::kPill, ctx.rect)}, tc.text);
        });
}

void chips(Ui& ui, const std::string& id, std::span<const std::string> options, int current, const Box& box) {
    Box b = box;
    b.layout = Layout::Row;
    b.wrap = true;
    b.gap = 6;
    b.line_gap = 6;
    if (zero(b.margin)) b.margin = {0, 10, 0, 4};
    auto g = ui.open(id, b);
    TextEngine& te = ui.text();
    for (std::size_t i = 0; i < options.size(); ++i) {
        const std::string o = options[i];
        const bool on = static_cast<int>(i) == current;
        ui.leaf(id + "/" + std::to_string(i), Box{.h = Size::fixed(m::kChipHeight)},
                [&te, o](float) { return Vec2{24 + te.width(tx::kChip, o), m::kChipHeight}; },
                [o, on](PaintContext& ctx) {
                    const Rect r = ctx.rect;
                    if (on)
                        surface(ctx.canvas, r, Gradient::css(r, 100, {{0, rgb(0x3b8cff)}, {1, rgb(0x1452d6)}}),
                                rgba(160, 205, 255, .8f));
                    else surface(ctx.canvas, r, rgba(255, 255, 255, .04f), rgba(255, 255, 255, .14f));
                    ctx.text.draw(ctx.canvas, tx::kChip, o, {r.x + 12, centred_y(ctx.text, tx::kChip, r)},
                                  on ? rgb(0xffffff) : c::kBlueFaint);
                });
    }
}

void describe_panel(Ui& ui, const std::string& id, const std::string& title, const std::string& body, const Box& box) {
    TextEngine& te = ui.text();
    Box b = box;
    if (zero(b.margin)) b.margin.top = 4;
    ui.leaf(
        id, b,
        [&te, title, body](float max_w) {
            const float w =
                std::min(max_w, 46 + std::max(te.width(tx::kExplainTitle, title), te.width(tx::kExplainText, body)));
            return Vec2{w, 11 + te.line_height(tx::kExplainTitle) + 5 +
                               te.wrapped_height(tx::kExplainText, body, std::max(1.f, w - 46)) + 12};
        },
        [title, body, mirrored = ui.mirrored()](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            if (mirrored) {  // (the accent on the right, the words right-aligned)
                surface(cv, r, Gradient::css(r, 260, {{0, rgba(45, 128, 255, .16f)}, {1, rgba(8, 14, 34, .5f)}}),
                        rgba(140, 190, 255, .3f));
                const Rect accent{r.right() - 8, r.y + 8, 4, r.h - 16};
                const Quad aq = sk_rect(r, accent);
                cv.glow(aq, 8, c::kCyan.faded(.5f));
                cv.fill(aq, c::kCyan);
                ctx.text.draw(cv, tx::kExplainTitle, title,
                              {r.right() - 26 - ctx.text.width(tx::kExplainTitle, title), r.y + 11}, c::kCyan);
                const float y = r.y + 11 + ctx.text.line_height(tx::kExplainTitle) + 5;
                ctx.text.draw_wrapped(cv, tx::kExplainText, body, {r.x + 20, y, r.w - 46, r.bottom() - y},
                                      TextPaint{rgb(0xdbe6f8)}, 1);
                return;
            }
            surface(cv, r, Gradient::css(r, 100, {{0, rgba(45, 128, 255, .16f)}, {1, rgba(8, 14, 34, .5f)}}),
                    rgba(140, 190, 255, .3f));
            const Rect accent{r.x + 4, r.y + 8, 4, r.h - 16};
            const Quad aq = sk_rect(r, accent);
            cv.glow(aq, 8, c::kCyan.faded(.5f));
            cv.fill(aq, c::kCyan);
            ctx.text.draw(cv, tx::kExplainTitle, title, {r.x + 26, r.y + 11}, c::kCyan);
            const float y = r.y + 11 + ctx.text.line_height(tx::kExplainTitle) + 5;
            ctx.text.draw_wrapped(cv, tx::kExplainText, body, {r.x + 26, y, r.w - 46, r.bottom() - y},
                                  TextPaint{rgb(0xdbe6f8)});
        });
}

void button(Ui& ui, const std::string& id, const ButtonSpec& spec, Focus focus, const Box& box) {
    const float h = spec.size == ButtonSize::Tiny    ? m::kButtonTinyHeight
                    : spec.size == ButtonSize::Small ? m::kButtonSmallHeight
                                                     : m::kButtonHeight;
    const float pad = spec.size == ButtonSize::Tiny ? 13 : spec.size == ButtonSize::Small ? 20 : 26;
    const float gap = spec.size == ButtonSize::Tiny ? 6 : 10;
    const TextStyle st = spec.size == ButtonSize::Tiny    ? tx::kButtonTiny
                         : spec.size == ButtonSize::Small ? tx::kButtonSmall
                                                          : tx::kButton;
    Box b = with_height(box, h);
    if (ui.mirrored()) b.hug = true;  // (blue: as wide as its label, at the right end - not a full-width bar)
    focus.disabled = focus.disabled || spec.disabled;
    TextEngine& te = ui.text();
    const Glyphs g = ui.glyphs();
    ui.leaf(
        id, b,
        [&te, spec, h, pad, gap, st, g](float) {
            float w = pad * 2 + te.width(st, spec.label);
            if (spec.prompt) w += prompt_width(te, g, *spec.prompt) + gap;
            if (spec.check) w += 20 + gap;
            return Vec2{w, h};
        },
        [spec, pad, gap, st](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            const float f = ctx.focus_t;
            if (spec.disabled) cv.push_layer({}, f > .5f ? .7f : .42f);
            Gradient fill;
            Color border;
            Color text_col = rgb(0xffffff);
            auto grad = [&](Color a, Color b2) { return Gradient::css(r, 100, {{0, a}, {1, b2}}); };
            switch (spec.kind) {
            case ButtonKind::Primary:
                fill = grad(mix(rgb(0xff3d66), rgb(0xff5a7d), f), mix(rgb(0xc8103a), rgb(0xe0163f), f));
                border = mix(rgba(255, 150, 170, .65f), rgb(0xffffff), f);
                break;
            case ButtonKind::Blue:
                fill = grad(mix(rgb(0x3b8cff), rgb(0x5aa0ff), f), mix(rgb(0x1452d6), rgb(0x2364f0), f));
                border = mix(rgba(150, 195, 255, .65f), rgb(0xffffff), f);
                break;
            case ButtonKind::Danger:
                fill = grad(mix(rgba(255, 42, 85, .14f), rgb(0xff3d66), f),
                            mix(rgba(255, 42, 85, .14f), rgb(0xb80f37), f));
                border = mix(rgba(255, 93, 113, .7f), rgb(0xffffff), f);
                text_col = mix(rgb(0xffd3da), rgb(0xffffff), f);
                break;
            default: {
                const bool blue = spec.half == Half::Blue;
                const Color fa = blue ? rgba(45, 128, 255, .5f) : rgba(255, 42, 85, .5f),
                            fb = blue ? rgba(20, 82, 214, .4f) : rgba(160, 12, 45, .4f);
                fill = grad(mix(rgba(8, 10, 18, .55f), fa, f), mix(rgba(8, 10, 18, .55f), fb, f));
                border = mix(rgba(255, 255, 255, .26f), rgb(0xffffff), f);
                break;
            }
            }
            surface(cv, r, fill, border);
            float w = ctx.text.width(st, spec.label);
            if (spec.prompt) w += prompt_width(ctx.text, ctx.glyphs, *spec.prompt) + gap;
            if (spec.check) w += 20 + gap;
            float x = r.center().x - w / 2;
            const float cy = r.y + r.h / 2;
            if (spec.check) {
                const Rect cb{x, cy - 10, 20, 20};
                const Quad cq = skewed(cb, kSeamTan);
                if (*spec.check) {
                    cv.fill(cq, rgb(0xffffff));
                    icon(cv, ctx.icons, "stroke:check:3.4", cb.outset(-3.5f), rgb(0x07080d));
                } else {
                    cv.stroke(cq, 2, rgba(255, 255, 255, .75f));
                }
                x += 20 + gap;
            }
            if (spec.prompt) x += draw_prompt(cv, ctx.text, ctx.icons, ctx.glyphs, *spec.prompt, x, cy) + gap;
            ctx.text.draw(cv, st, spec.label, {x, centred_y(ctx.text, st, r)}, text_col);
            (void)pad;
            if (spec.disabled) cv.pop_layer();
        },
        &focus);
}

// ---- readout --------------------------------------------------------------------------------------------------------

void Readout::show(const std::string& key, int dy, double now) {
    if (key == key_) return;
    old_ = key_;
    key_ = key;
    dy_ = dy;
    changed_ = old_.empty() ? -1e9 : now;
}

bool Readout::animating(double now) const {
    return now - changed_ < std::max(theme::motion::kReadoutIn, theme::motion::kReadoutOut);
}

void Readout::build(Ui& ui, const std::string& id, const Box& box,
                    const std::function<void(const std::string&)>& content) {
    Box b = box;
    b.layout = Layout::Stack;
    b.align = Align::Stretch;
    auto g = ui.open(id, b);
    const double now = ui.now();
    const float age = static_cast<float>(now - changed_);
    const bool reduced = ui.reduced();
    if (!reduced && !old_.empty() && age < theme::motion::kReadoutOut) {
        const float t = ease::in_cubic(age / theme::motion::kReadoutOut);
        Box ob;
        ob.inert = true;
        ob.opacity = 1 - t;
        // (Up or down ALONG the seam, and away from it: never into the gutter.)
        const float oy = -static_cast<float>(dy_) * theme::motion::kReadoutDy * t;
        ob.shift = {theme::motion::kReadoutOutDx * t - oy * kSeamTan, oy};
        auto og = ui.open(id + "/old", ob);
        ui.push_prefix("old:");
        content(old_);
        ui.pop_prefix();
    }
    Box nb;
    if (!reduced && age < theme::motion::kReadoutIn) {
        const float e = ease::out_expo_like(std::max(0.f, age) / theme::motion::kReadoutIn);
        nb.opacity = e;
        // (In from the half's straight outer edge, moving along the seam: never into the gutter.)
        const float ny = static_cast<float>(dy_) * theme::motion::kReadoutDy * (1 - e);
        nb.shift = {theme::motion::kReadoutDx * (1 - e) - ny * kSeamTan, ny};
    }
    auto ng = ui.open(id + "/cur", nb);
    content(key_);
}

// ---- dialog band ----------------------------------------------------------------------------------------------------

BandLayout band_layout(Vec2 size, float top, float height, float share) {
    BandLayout l;
    l.band = {0, top, size.x, height};
    const Seam seam{share * size.x, (theme::kTopBand + size.y - theme::kBottomBand) / 2, kSeamTan};
    const float y0 = top + 8 + 12, y1 = top + height - 8;  // (content: 20 points into the band, as the mock)
    const float left = theme::kPlateSide + theme::kPlatePad;
    l.crimson.seam = seam;
    l.crimson.margin = {left, y0, 0, 0};
    l.crimson.w = Size::fixed(std::round(seam.x_at(y0) - theme::kSeamGap - left));
    l.crimson.h = Size::fixed(y1 - y0 - 14);
    const float bx = std::round(seam.x_at(y1) + theme::kSeamGap);
    l.blue.seam = seam;
    l.blue.mirror = true;  // (FEEDBACK F2: right-aligned)
    l.blue.margin = {bx, y0, 0, 0};
    l.blue.w = Size::fixed(size.x - theme::kPlateSide - theme::kPlatePad - bx);
    l.blue.h = Size::fixed(y1 - y0 - 14);
    return l;
}

Ui::Guard dialog_band(Ui& ui, const std::string& id, const BandLayout& layout) {
    Box b;
    b.layout = Layout::Stack;
    b.align = Align::Start;
    b.w = Size::fixed(ui.frame().size.x);
    b.h = Size::fixed(ui.frame().size.y);
    const Rect band = layout.band;
    const Vec2 size = ui.frame().size;
    auto paint = [band, size](PaintContext& ctx) {
        Canvas& cv = ctx.canvas;
        const float fade = ctx.reduced ? 1 : clamp01(ctx.appear / theme::motion::kScrimFade);
        const float grow = ctx.reduced ? 1 : ease::out_expo_like(clamp01(ctx.appear / theme::motion::kBand));
        if (fade < 1 || grow < 1) ctx.animate();
        cv.fill_rect({0, 0, size.x, size.y}, c::kScrim.faded(fade));
        // The band grows from its middle (scaleY .2 -> 1).
        const float hh = band.h * (.2f + .8f * grow);
        const Rect bb{band.x, band.center().y - hh / 2, band.w, hh};
        cv.push_layer({}, grow);
        cv.fill_rect(bb, rgb(0x07080e, .97f));
        const Seam seam{theme::split::kDialog * size.x, (theme::kTopBand + size.y - theme::kBottomBand) / 2, kSeamTan};
        const float y0 = bb.y + 8, y1 = bb.bottom() - 8, pl = theme::kPlateSide, pr = size.x - theme::kPlateSide;
        const Vec2 cp[4] = {
            {pl, y0}, {seam.x_at(y0) - theme::kGutter, y0}, {seam.x_at(y1) - theme::kGutter, y1}, {pl, y1}};
        const Vec2 bp[4] = {
            {seam.x_at(y0) + theme::kGutter, y0}, {pr, y0}, {pr, y1}, {seam.x_at(y1) + theme::kGutter, y1}};
        cv.fill(cp, Gradient::linear({pl, 0}, {seam.x_at(y0), 0}, rgb(0x3a0714, .9f), rgb(0x6e0c28, .8f)));
        cv.stroke(cp, 1.2f, rgba(255, 110, 140, .55f));
        cv.fill(bp, Gradient::linear({seam.x_at(y1), 0}, {pr, 0}, rgb(0x0c2a78, .8f), rgb(0x06143c, .9f)));
        cv.stroke(bp, 1.2f, rgba(120, 175, 255, .55f));
        const Vec2 s0{seam.x_at(bb.y), bb.y}, s1{seam.x_at(bb.bottom()), bb.bottom()};
        cv.line(s0 - Vec2{8, 0}, s1 - Vec2{8, 0}, 16, rgba(255, 42, 85, .5f));
        cv.line(s0 + Vec2{8, 0}, s1 + Vec2{8, 0}, 16, rgba(45, 128, 255, .5f));
        cv.line(s0, s1, 2.4f, rgb(0xffffff));
        for (float y : {bb.y, bb.bottom() - 3}) {
            Gradient g;
            g.from = {0, 0};
            g.to = {size.x, 0};
            g.stops[0] = {0, c::kRed};
            g.stops[1] = {.5f, rgba(255, 255, 255, .4f)};
            g.stops[2] = {1, c::kBlue};
            g.count = 3;
            cv.fill_rect({0, y, size.x, 3}, g);
        }
        cv.pop_layer();
    };
    return ui.modal(id, b, paint);
}

// ---- log view -------------------------------------------------------------------------------------------------------

void LogView::append(std::string text, LogKind kind) {
    lines_.push_back({std::move(text), kind});
    rows_.push_back(-1);
    if (lines_.size() > limit_) {
        if (rows_.front() > 0) total_rows_ -= static_cast<std::size_t>(rows_.front());
        lines_.pop_front();
        rows_.pop_front();
    }
    ++serial_;
}

void LogView::clear() {
    lines_.clear();
    rows_.clear();
    total_rows_ = 0;
    ++serial_;
}

std::string LogView::text() const {
    std::string out;
    for (const LogLine& l : lines_) {
        out += l.text;
        out += '\n';
    }
    return out;
}

void LogView::rewrap(TextEngine& text, float width) {
    if (width != width_ || text.scale() != scale_) {
        width_ = width;
        scale_ = text.scale();
        std::fill(rows_.begin(), rows_.end(), -1);
        total_rows_ = 0;
    }
    for (std::size_t i = 0; i < lines_.size(); ++i)
        if (rows_[i] < 0) {
            // (Measured, not kept: TextEngine's wrap cache holds only recent texts.)
            rows_[i] = std::max<int>(1, static_cast<int>(text.wrap(tx::kLog, lines_[i].text, width).size()));
            total_rows_ += static_cast<std::size_t>(rows_[i]);
        }
}

float LogView::height(TextEngine& text, float width) {
    rewrap(text, width);
    return static_cast<float>(total_rows_) * text.line_height(tx::kLog);
}

void LogView::paint(PaintContext& ctx, const Rect& content, float view_top, float view_bottom) {
    rewrap(ctx.text, content.w);
    const float lh = ctx.text.line_height(tx::kLog);
    float y = content.y;
    for (std::size_t i = 0; i < lines_.size(); ++i) {
        const float h = static_cast<float>(rows_[i]) * lh;
        if (y + h >= view_top && y <= view_bottom) {
            const LogLine& l = lines_[i];
            const Color col = l.kind == LogKind::Command ? c::kCyan : l.kind == LogKind::Error ? rgb(0xff8a99)
                              : l.kind == LogKind::Status ? rgb(0xffffff) : rgb(0xb3bccd);
            ctx.text.draw_wrapped(ctx.canvas, tx::kLog, l.text, {content.x, y, content.w, h}, TextPaint{col});
        }
        y += h;
        if (y > view_bottom) break;
    }
}

void log_view(Ui& ui, const std::string& id, LogView& log, const Box& box) {
    Box b = box;
    b.scroll = true;
    b.pad = {19, 9, 16, 9};
    // Follow the end: shown first at its end, and when it was scrolled to the end, it stays there as lines come.
    const std::string full = ui.prefix() + id;
    const NodeState* s = ui.state(full);
    if (!s || !s->user_set) ui.scroll_to_end(full, true);
    else if (s->scroll.target >= s->content_h - s->view_h - 2) ui.scroll_to_end(full);
    Focus f;
    f.skewed = false;
    f.pad = 4;
    auto bg = [](PaintContext& ctx) {
        ctx.canvas.fill_rect(ctx.rect, rgba(1, 3, 10, .92f));
        ctx.canvas.stroke(Quad{{{ctx.rect.x, ctx.rect.y},
                                {ctx.rect.right(), ctx.rect.y},
                                {ctx.rect.right(), ctx.rect.bottom()},
                                {ctx.rect.x, ctx.rect.bottom()}}},
                          1, rgba(160, 200, 255, .18f));
        ctx.canvas.fill_rect({ctx.rect.x, ctx.rect.y, 3, ctx.rect.h}, c::kBlue);
    };
    auto g = ui.open(id, b, bg, &f);
    if (NodeState* st = ui.state(full)) st->user_set = true;
    TextEngine& te = ui.text();
    LogView* lv = &log;
    ui.leaf(id + "/lines", Box{}, [&te, lv](float max_w) { return Vec2{max_w, lv->height(te, max_w)}; },
            [lv](PaintContext& ctx) {
                const Rect clip = ctx.canvas.clip();
                lv->paint(ctx, ctx.rect, clip.y, clip.bottom());
            });
}

// ---- dialog parts --------------------------------------------------------------------------------------------------

void option_row(Ui& ui, const std::string& id, const OptionRowSpec& spec, Focus focus, const Box& box) {
    focus.straight_left = true;
    // .opt: min 44 high, padding 8 18 8 20, check box 20, gap 14, text 600 14.5/1.25.
    static constexpr TextStyle kText{theme::Font::BodySemiBold, 14.5f, 0, false, 1.25f};
    static constexpr float kLeft = 20 + 20 + 14, kRight = 18;
    TextEngine& te = ui.text();
    focus.disabled = focus.disabled || spec.disabled;
    Box b = box;
    if (zero(b.margin)) b.margin = {0, 0, 0, 8};
    ui.leaf(
        id, b,
        [&te, spec](float max_w) {
            const float room = std::max(1.f, max_w - kLeft - kRight);
            return Vec2{std::min(max_w, kLeft + te.width(kText, spec.text) + kRight),
                        std::max(44.f, te.wrapped_height(kText, spec.text, room) + 16)};
        },
        [spec](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            const float f = ctx.focus_t;
            if (spec.disabled) cv.push_layer({}, .42f);
            row_surface(cv, r, f, rgba(255, 255, 255, .04f), rgba(255, 120, 150, .22f), rgba(255, 42, 85, .5f),
                        rgba(150, 10, 40, .36f), rgba(255, 200, 212, .95f));
            const Rect cb{r.x + 20, r.y + r.h / 2 - 10, 20, 20};
            const Quad cq = skewed(cb, kSeamTan);
            if (spec.on) {
                cv.fill(cq, c::kRed);
                icon(cv, ctx.icons, "stroke:check:3.4", cb.outset(-3.5f), rgb(0xffffff));
            } else {
                cv.stroke(cq, 2, rgba(255, 255, 255, .75f));
            }
            const float x = r.x + kLeft, room = std::max(1.f, r.right() - kRight - x);
            const float h = ctx.text.wrapped_height(kText, spec.text, room);
            ctx.text.draw_wrapped(cv, kText, spec.text, {x, r.y + (r.h - h) / 2, room, h}, TextPaint{c::kText});
            if (spec.disabled) cv.pop_layer();
        },
        &focus);
}

namespace {
// Words of "what happens" parts, each with its font, laid out in lines of `width`.
struct WhatWord {
    std::string text;
    bool mono;
    bool space_before;
    float width;
};
constexpr TextStyle kWhatText{theme::Font::Body, 14, 0, false, 1.4f};
constexpr TextStyle kWhatMono{theme::Font::Mono, 13, 0, false, 1.4f};
constexpr TextStyle kWhatKey{theme::Font::DisplayExtraBoldItalic, 13, .14f, true, 1};
constexpr float kWhatKeyWidth = 62, kWhatGap = 12, kWhatLineGap = 9;

std::vector<WhatWord> what_words(TextEngine& te, const WhatLine& line) {
    std::vector<WhatWord> out;
    bool space = false;
    for (const WhatPart& p : line.parts) {
        std::size_t i = 0;
        if (!p.text.empty() && p.text.front() == ' ') space = true;
        while (i < p.text.size()) {
            const std::size_t j = p.text.find(' ', i);
            const std::string w = p.text.substr(i, j == std::string::npos ? std::string::npos : j - i);
            if (!w.empty()) {
                out.push_back({w, p.mono, space && !out.empty(), te.width(p.mono ? kWhatMono : kWhatText, w)});
                space = false;
            }
            if (j == std::string::npos) break;
            space = true;
            i = j + 1;
        }
    }
    return out;
}
// Positions (x, line) of each word; a word wider than the line is cut where it no longer fits (paths).
struct Placed {
    std::string text;
    bool mono;
    float x;
    int line;
};
std::vector<Placed> what_layout(TextEngine& te, const std::vector<WhatWord>& words, float width, int& lines) {
    std::vector<Placed> out;
    float x = 0;
    int line = 0;
    const float space = te.width(kWhatText, " ");
    for (const WhatWord& w : words) {
        const float gap = w.space_before && x > 0 ? space : 0;
        if (x > 0 && x + gap + w.width > width + .5f) {
            ++line;
            x = 0;
        }
        const TextStyle& st = w.mono ? kWhatMono : kWhatText;
        if (w.width <= width + .5f) {
            out.push_back({w.text, w.mono, x + (x > 0 ? gap : 0), line});
            x += (x > 0 ? gap : 0) + w.width;
            continue;
        }
        // (Too long for any line: break it by characters.)
        std::vector<char32_t> cps;
        decode_utf8(w.text, cps);
        std::string piece;
        for (char32_t cp : cps) {
            const std::string next = piece + encode_utf8(cp);
            if (!piece.empty() && x + te.width(st, next) > width + .5f) {
                out.push_back({piece, w.mono, x, line});
                ++line;
                x = 0;
                piece = encode_utf8(cp);
            } else {
                piece = next;
            }
        }
        if (!piece.empty()) {
            out.push_back({piece, w.mono, x, line});
            x += te.width(st, piece);
        }
    }
    lines = line + 1;
    return out;
}
}  // namespace

void what_list(Ui& ui, const std::string& id, std::span<const WhatLine> lines, const Box& box) {
    TextEngine& te = ui.text();
    std::vector<WhatLine> copy(lines.begin(), lines.end());
    ui.leaf(
        id, box,
        [&te, copy](float max_w) {
            const float room = std::max(40.f, max_w - kWhatKeyWidth - kWhatGap);
            const float lh = te.line_height(kWhatText);
            float h = 0, w = 0;
            for (std::size_t i = 0; i < copy.size(); ++i) {
                int n = 1;
                const auto words = what_words(te, copy[i]);
                float natural = 0;
                for (const WhatWord& word : words) natural += word.width + (word.space_before ? 4 : 0);
                what_layout(te, words, room, n);
                h += n * lh + (i ? kWhatLineGap : 0);
                w = std::max(w, kWhatKeyWidth + kWhatGap + natural);
            }
            return Vec2{std::min(max_w, w), h};
        },
        [copy, mirrored = ui.mirrored()](PaintContext& ctx) {
            const Rect r = ctx.rect;
            const float room = std::max(40.f, r.w - kWhatKeyWidth - kWhatGap);
            const float lh = ctx.text.line_height(kWhatText);
            float y = r.y;
            for (const WhatLine& l : copy) {
                const Color kc = l.tone == WhatTone::Removed ? rgb(0xff9aa8)
                                 : l.tone == WhatTone::Kept  ? c::kOk
                                                             : c::kBlueFaint;
                // (Mirrored: the keys in a column at the right edge, each line of words right-aligned before it.)
                const float kx = mirrored ? r.right() - ctx.text.width(kWhatKey, l.key) : r.x;
                ctx.text.draw(ctx.canvas, kWhatKey, l.key, {kx, y + (19 - ctx.text.line_height(kWhatKey)) / 2}, kc);
                int n = 1;
                const auto placed = what_layout(ctx.text, what_words(ctx.text, l), room, n);
                std::vector<float> line_end(static_cast<std::size_t>(n), 0);
                for (const Placed& p : placed)
                    line_end[static_cast<std::size_t>(p.line)] =
                        std::max(line_end[static_cast<std::size_t>(p.line)],
                                 p.x + ctx.text.width(p.mono ? kWhatMono : kWhatText, p.text));
                for (const Placed& p : placed) {
                    const TextStyle& st = p.mono ? kWhatMono : kWhatText;
                    // (Mono words sit on the same baseline as the text around them.)
                    const float dy = p.mono ? ctx.text.ascent(kWhatText) - ctx.text.ascent(kWhatMono) : 0;
                    const float x = mirrored ? r.x + room - line_end[static_cast<std::size_t>(p.line)] + p.x
                                             : r.x + kWhatKeyWidth + kWhatGap + p.x;
                    ctx.text.draw(ctx.canvas, st, p.text, {x, y + p.line * lh + dy},
                                  p.mono ? rgb(0xffffff) : rgb(0xd6e2f5));
                }
                y += n * lh + kWhatLineGap;
            }
        });
}

bool copy_text(const std::string& text) { return SDL_SetClipboardText(text.c_str()); }

}  // namespace ttt2::ui
