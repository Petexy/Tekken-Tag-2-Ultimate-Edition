// Plain geometry and colour types of the interface toolkit (no SDL): points are layout units ("design pixels" at
// scale 1), converted to physical pixels only when drawn (Canvas).
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace ttt2::ui {

struct Vec2 {
    float x = 0, y = 0;
    friend constexpr Vec2 operator+(Vec2 a, Vec2 b) { return {a.x + b.x, a.y + b.y}; }
    friend constexpr Vec2 operator-(Vec2 a, Vec2 b) { return {a.x - b.x, a.y - b.y}; }
    friend constexpr Vec2 operator*(Vec2 a, float s) { return {a.x * s, a.y * s}; }
    friend constexpr bool operator==(Vec2 a, Vec2 b) { return a.x == b.x && a.y == b.y; }
};

struct Insets {
    float left = 0, top = 0, right = 0, bottom = 0;
    static constexpr Insets all(float v) { return {v, v, v, v}; }
    static constexpr Insets xy(float x, float y) { return {x, y, x, y}; }
    constexpr float horizontal() const { return left + right; }
    constexpr float vertical() const { return top + bottom; }
};

struct Rect {
    float x = 0, y = 0, w = 0, h = 0;
    constexpr float right() const { return x + w; }
    constexpr float bottom() const { return y + h; }
    constexpr Vec2 center() const { return {x + w / 2, y + h / 2}; }
    constexpr bool contains(Vec2 p) const { return p.x >= x && p.y >= y && p.x < x + w && p.y < y + h; }
    constexpr bool empty() const { return w <= 0 || h <= 0; }
    constexpr Rect inset(Insets i) const { return {x + i.left, y + i.top, w - i.horizontal(), h - i.vertical()}; }
    constexpr Rect outset(float d) const { return {x - d, y - d, w + 2 * d, h + 2 * d}; }
    constexpr Rect translated(Vec2 d) const { return {x + d.x, y + d.y, w, h}; }
    Rect intersect(const Rect& o) const {
        const float x0 = std::max(x, o.x), y0 = std::max(y, o.y), x1 = std::min(right(), o.right()),
                    y1 = std::min(bottom(), o.bottom());
        return {x0, y0, std::max(0.f, x1 - x0), std::max(0.f, y1 - y0)};
    }
    bool overlaps(const Rect& o) const { return x < o.right() && o.x < right() && y < o.bottom() && o.y < bottom(); }
    friend constexpr bool operator==(const Rect& a, const Rect& b) {
        return a.x == b.x && a.y == b.y && a.w == b.w && a.h == b.h;
    }
};

// Straight (not premultiplied) RGBA, 0..1.
struct Color {
    float r = 0, g = 0, b = 0, a = 0;
    constexpr Color with_alpha(float alpha) const { return {r, g, b, alpha}; }
    constexpr Color faded(float m) const { return {r, g, b, a * m}; }
    friend constexpr bool operator==(const Color& x, const Color& y) {
        return x.r == y.r && x.g == y.g && x.b == y.b && x.a == y.a;
    }
};
constexpr Color rgb(std::uint32_t hex, float a = 1) {
    return {((hex >> 16) & 255) / 255.f, ((hex >> 8) & 255) / 255.f, (hex & 255) / 255.f, a};
}
constexpr Color rgba(int r, int g, int b, float a) { return {r / 255.f, g / 255.f, b / 255.f, a}; }
inline Color mix(Color a, Color b, float t) {
    return {a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, a.a + (b.a - a.a) * t};
}
// Brighter (m > 1) or darker, alpha kept.
inline Color brightened(Color c, float m) {
    return {std::min(1.f, c.r * m), std::min(1.f, c.g * m), std::min(1.f, c.b * m), c.a};
}

inline float lerp(float a, float b, float t) { return a + (b - a) * t; }
inline float clamp01(float v) { return std::clamp(v, 0.f, 1.f); }

}  // namespace ttt2::ui
