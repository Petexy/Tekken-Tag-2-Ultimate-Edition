#include "title/title_screen.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <span>
#include <utility>
#include <vector>

namespace cafe::title::title_screen {
namespace {

// The logo still: "TAG TOURNAMENT 2" ends at row 406 and the subtitle's
// brush lettering starts at row 412 (one stroke of its "N" curls up
// against the banner from row 392); the kanji go on behind both.
constexpr uint32_t kStill = 1280, kStillHeight = 720;
constexpr uint32_t kCurlTop = 392, kSubtitleTop = 412, kSubtitleBelow = 418;
constexpr uint32_t kFadeTop = 406, kFadeBottom = 418;

struct Mask {
    uint32_t width = 0, height = 0;
    std::vector<uint8_t> bits;
    Mask(uint32_t w, uint32_t h) : width(w), height(h), bits(size_t{w} * h, 0) {}
    uint8_t& operator()(uint32_t x, uint32_t y) { return bits[size_t{y} * width + x]; }
    uint8_t operator()(uint32_t x, uint32_t y) const { return bits[size_t{y} * width + x]; }
};

// Square neighbourhoods, a row pass then a column pass; outside counts as
// clear.
Mask spread(const Mask& m, int radius, bool erode) {
    Mask rows(m.width, m.height), out(m.width, m.height);
    const auto at = [](const Mask& s, int64_t x, int64_t y) {
        return x >= 0 && y >= 0 && x < s.width && y < s.height && s(static_cast<uint32_t>(x), static_cast<uint32_t>(y));
    };
    for (int pass = 0; pass < 2; ++pass) {
        const Mask& in = pass == 0 ? m : rows;
        Mask& to = pass == 0 ? rows : out;
        for (uint32_t y = 0; y < m.height; ++y) {
            for (uint32_t x = 0; x < m.width; ++x) {
                bool all = true, any = false;
                for (int k = -radius; k <= radius; ++k) {
                    const bool v = pass == 0 ? at(in, int64_t{x} + k, y) : at(in, x, int64_t{y} + k);
                    all = all && v;
                    any = any || v;
                }
                to(x, y) = erode ? all : any;
            }
        }
    }
    return out;
}

// Dilation by the four neighbours, `times` over.
Mask grow(Mask m, int times) {
    for (int t = 0; t < times; ++t) {
        Mask next = m;
        for (uint32_t y = 0; y < m.height; ++y) {
            for (uint32_t x = 0; x < m.width; ++x) {
                if (m(x, y)) continue;
                next(x, y) = (x > 0 && m(x - 1, y)) || (x + 1 < m.width && m(x + 1, y)) || (y > 0 && m(x, y - 1)) ||
                             (y + 1 < m.height && m(x, y + 1));
            }
        }
        m = std::move(next);
    }
    return m;
}

// The eight-connected parts of `m`, as pixel indices.
std::vector<std::vector<size_t>> parts(const Mask& m) {
    std::vector<std::vector<size_t>> out;
    Mask seen(m.width, m.height);
    std::vector<std::pair<uint32_t, uint32_t>> stack;
    for (uint32_t y = 0; y < m.height; ++y) {
        for (uint32_t x = 0; x < m.width; ++x) {
            if (!m(x, y) || seen(x, y)) continue;
            std::vector<size_t>& part = out.emplace_back();
            stack.push_back({x, y});
            seen(x, y) = 1;
            while (!stack.empty()) {
                const auto [px, py] = stack.back();
                stack.pop_back();
                part.push_back(size_t{py} * m.width + px);
                for (int dy = -1; dy <= 1; ++dy) {
                    for (int dx = -1; dx <= 1; ++dx) {
                        const int64_t nx = int64_t{px} + dx, ny = int64_t{py} + dy;
                        if (nx < 0 || ny < 0 || nx >= m.width || ny >= m.height) continue;
                        const auto ux = static_cast<uint32_t>(nx), uy = static_cast<uint32_t>(ny);
                        if (m(ux, uy) && !seen(ux, uy)) {
                            seen(ux, uy) = 1;
                            stack.push_back({ux, uy});
                        }
                    }
                }
            }
        }
    }
    return out;
}

// The parts of `m` that reach below `row`.
Mask reaching_below(const Mask& m, uint32_t row) {
    Mask out(m.width, m.height);
    for (const std::vector<size_t>& part : parts(m)) {
        if (std::none_of(part.begin(), part.end(), [&](size_t i) { return i / m.width > row; })) continue;
        for (const size_t i : part) out.bits[i] = 1;
    }
    return out;
}

// Clear pixels that the edge cannot reach through clear ones
// (four-connected) become set.
void fill_holes(Mask& m) {
    Mask outside(m.width, m.height);
    std::vector<std::pair<uint32_t, uint32_t>> stack;
    const auto visit = [&](uint32_t x, uint32_t y) {
        if (!m(x, y) && !outside(x, y)) {
            outside(x, y) = 1;
            stack.push_back({x, y});
        }
    };
    for (uint32_t x = 0; x < m.width; ++x) {
        visit(x, 0);
        visit(x, m.height - 1);
    }
    for (uint32_t y = 0; y < m.height; ++y) {
        visit(0, y);
        visit(m.width - 1, y);
    }
    while (!stack.empty()) {
        const auto [x, y] = stack.back();
        stack.pop_back();
        if (x > 0) visit(x - 1, y);
        if (x + 1 < m.width) visit(x + 1, y);
        if (y > 0) visit(x, y - 1);
        if (y + 1 < m.height) visit(x, y + 1);
    }
    for (size_t i = 0; i < m.bits.size(); ++i) m.bits[i] = !outside.bits[i];
}

// Only the holes of up to `largest` pixels filled.
void fill_small_holes(Mask& m, size_t largest) {
    Mask holes = m;
    fill_holes(holes);
    for (size_t i = 0; i < m.bits.size(); ++i) holes.bits[i] = holes.bits[i] && !m.bits[i];
    for (const std::vector<size_t>& part : parts(holes)) {
        if (part.size() > largest) continue;
        for (const size_t i : part) m.bits[i] = 1;
    }
}

// Each pixel's distance to the nearest set one (Euclidean, exact: the lower
// envelope of parabolas, Felzenszwalb and Huttenlocher's method, along rows
// then columns); huge where none is set.
std::vector<float> distance(const Mask& m) {
    constexpr double kFar = 1e20;
    const size_t w = m.width, h = m.height, longest = std::max(w, h);
    std::vector<double> d(w * h), f(longest), z(longest + 1);
    std::vector<size_t> v(longest);
    for (size_t i = 0; i < d.size(); ++i) d[i] = m.bits[i] ? 0 : kFar;
    const auto pass = [&](size_t count, size_t length, size_t step, size_t stride) {
        for (size_t c = 0; c < count; ++c) {
            double* line = d.data() + c * stride;
            for (size_t i = 0; i < length; ++i) f[i] = line[i * step];
            // Parabola v[k] is lowest from z[k] to z[k + 1]. Where two
            // meet lies within (-kFar / 2, kFar / 2), so z[0] is never
            // passed.
            size_t k = 0;
            v[0] = 0;
            z[0] = -kFar;
            z[1] = kFar;
            for (size_t q = 1; q < length; ++q) {
                const auto meet = [&](size_t p) {
                    const double qd = static_cast<double>(q), pd = static_cast<double>(p);
                    return (f[q] + qd * qd - f[p] - pd * pd) / (2 * qd - 2 * pd);
                };
                double s = meet(v[k]);
                while (s <= z[k]) s = meet(v[--k]);
                ++k;
                v[k] = q;
                z[k] = s;
                z[k + 1] = kFar;
            }
            k = 0;
            for (size_t q = 0; q < length; ++q) {
                while (z[k + 1] < static_cast<double>(q)) ++k;
                const double dq = static_cast<double>(q) - static_cast<double>(v[k]);
                line[q * step] = dq * dq + f[v[k]];
            }
        }
    };
    pass(h, w, 1, w); // rows
    pass(w, h, w, 1); // columns
    std::vector<float> out(d.size());
    for (size_t i = 0; i < d.size(); ++i) out[i] = static_cast<float>(std::sqrt(d[i]));
    return out;
}

// Dilation by a disc of radius `r`, or, eroding, what lies farther than `r`
// from a clear pixel (the edge of `m` does not count as clear).
Mask within(const Mask& m, float r, bool erode) {
    Mask from = m;
    if (erode) {
        for (uint8_t& b : from.bits) b = !b;
    }
    const std::vector<float> d = distance(from);
    Mask out(m.width, m.height);
    for (size_t i = 0; i < d.size(); ++i) out.bits[i] = erode ? d[i] > r : d[i] <= r;
    return out;
}

// Smooth noise in [-1, 1]: values on a grid of `cell` texels, interpolated.
float noise(uint32_t x, uint32_t y, uint32_t cell, uint32_t seed) {
    const auto at = [seed](uint32_t gx, uint32_t gy) {
        uint32_t h = gx * 0x9E3779B1u ^ (gy + 0x7F4A7C15u) * 0x85EBCA77u ^ seed * 0xC2B2AE3Du;
        h ^= h >> 15;
        h *= 0x2C1B3C6Du;
        h ^= h >> 12;
        h *= 0x297A2D39u;
        h ^= h >> 15;
        return static_cast<float>(h >> 8) / 8388608.0f - 1.0f;
    };
    const uint32_t gx = x / cell, gy = y / cell;
    const float fx = static_cast<float>(x % cell) / cell, fy = static_cast<float>(y % cell) / cell;
    const float top = at(gx, gy) * (1 - fx) + at(gx + 1, gy) * fx;
    const float bottom = at(gx, gy + 1) * (1 - fx) + at(gx + 1, gy + 1) * fx;
    return top * (1 - fy) + bottom * fy;
}

// ------------------------------------------------------------------ the subtitle

// The subtitle is brush lettering: black strokes ("ink") in a rough white
// edge that runs round each word as one shape (counters and gaps between
// touching letters white too), over a brushed underline. "WiiU" is large;
// EDITION's letters are 62 rows high, their ink from row 438 to 500.

// Ink, 0 (none) to 1 (black), of a width x height rectangle whose top row
// is `top` in the still.
struct Ink {
    uint32_t width = 0, height = 0;
    int top = 0;
    std::vector<float> v;
    Ink() = default;
    Ink(uint32_t w, uint32_t h, int t) : width(w), height(h), top(t), v(size_t{w} * h, 0.0f) {}
    float& operator()(uint32_t x, uint32_t y) { return v[size_t{y} * width + x]; }
    float operator()(uint32_t x, uint32_t y) const { return v[size_t{y} * width + x]; }
};

// Cut down to where it is mostly black; empty if nowhere.
Ink trim(const Ink& p) {
    uint32_t x0 = p.width, x1 = 0, y0 = p.height, y1 = 0;
    for (uint32_t y = 0; y < p.height; ++y) {
        for (uint32_t x = 0; x < p.width; ++x) {
            if (p(x, y) <= 0.5f) continue;
            x0 = std::min(x0, x);
            x1 = std::max(x1, x + 1);
            y0 = std::min(y0, y);
            y1 = std::max(y1, y + 1);
        }
    }
    if (x1 <= x0) return {};
    Ink out(x1 - x0, y1 - y0, p.top + static_cast<int>(y0));
    for (uint32_t y = 0; y < out.height; ++y) {
        for (uint32_t x = 0; x < out.width; ++x) out(x, y) = p(x0 + x, y0 + y);
    }
    return out;
}

struct Rect {
    uint32_t x0, x1, y0, y1;
};

// The still's ink in `r`, trimmed (or not).
Ink cut(const Ink& still, Rect r, bool trimmed = true) {
    Ink out(r.x1 - r.x0, r.y1 - r.y0, static_cast<int>(r.y0));
    for (uint32_t y = 0; y < out.height; ++y) {
        for (uint32_t x = 0; x < out.width; ++x) out(x, y) = still(r.x0 + x, r.y0 + y);
    }
    return trimmed ? trim(out) : out;
}

// Resized (bilinear, corners on corners) with its top at `top`.
Ink scaled(const Ink& p, uint32_t width, uint32_t height, int top) {
    Ink out(width, height, top);
    const auto source = [](uint32_t i, uint32_t from, uint32_t to) {
        return to > 1 ? static_cast<double>(i) * (from - 1) / (to - 1) : 0.0;
    };
    for (uint32_t y = 0; y < height; ++y) {
        const double sy = source(y, p.height, height);
        const auto y0 = static_cast<uint32_t>(sy);
        const uint32_t y1 = std::min(y0 + 1, p.height - 1);
        const double fy = sy - y0;
        for (uint32_t x = 0; x < width; ++x) {
            const double sx = source(x, p.width, width);
            const auto x0 = static_cast<uint32_t>(sx);
            const uint32_t x1 = std::min(x0 + 1, p.width - 1);
            const double fx = sx - x0;
            out(x, y) = static_cast<float>((p(x0, y0) * (1 - fx) + p(x1, y0) * fx) * (1 - fy) +
                                           (p(x0, y1) * (1 - fx) + p(x1, y1) * fx) * fy);
        }
    }
    return out;
}

// `p` over `into`, its left column at column `x` of `into` and its top at
// row `top` of the still.
void draw(Ink& into, const Ink& p, int x, int top) {
    for (uint32_t y = 0; y < p.height; ++y) {
        const int64_t ty = int64_t{top} - into.top + y;
        if (ty < 0 || ty >= into.height) continue;
        for (uint32_t c = 0; c < p.width; ++c) {
            const int64_t tx = int64_t{x} + c;
            if (tx < 0 || tx >= into.width) continue;
            float& v = into(static_cast<uint32_t>(tx), static_cast<uint32_t>(ty));
            v = std::max(v, p(c, y));
        }
    }
}

struct Placed {
    const Ink& ink;
    int x, top;
};

// Strokes put together into one letter.
Ink join(std::initializer_list<Placed> placed) {
    int top = INT32_MAX, bottom = INT32_MIN, right = 0;
    for (const Placed& p : placed) {
        top = std::min(top, p.top);
        bottom = std::max(bottom, p.top + static_cast<int>(p.ink.height));
        right = std::max(right, p.x + static_cast<int>(p.ink.width));
    }
    Ink out(static_cast<uint32_t>(right), static_cast<uint32_t>(bottom - top), top);
    for (const Placed& p : placed) draw(out, p.ink, p.x, p.top);
    return trim(out);
}

// Strokes cut off at the left or right column would end squarely there;
// each ends in a half ellipse instead, up to six columns deep.
void round_end(Ink& p, bool right) {
    constexpr double kDepth = 6;
    const uint32_t c = right ? p.width - 1 : 0;
    for (uint32_t y = 0; y < p.height;) {
        if (p(c, y) <= 0.5f) {
            ++y;
            continue;
        }
        uint32_t end = y;
        while (end < p.height && p(c, end) > 0.5f) ++end;
        const double half = (end - y) / 2.0, middle = (y + end - 1) / 2.0, depth = std::min(kDepth, half);
        for (uint32_t row = y; row < end; ++row) {
            const double d = (row - middle) / std::max(half, 0.5);
            const auto n = static_cast<uint32_t>(std::lround(depth * (1 - std::sqrt(std::max(0.0, 1 - d * d)))));
            for (uint32_t k = 0; k < std::min(n, p.width); ++k) p(right ? p.width - 1 - k : k, row) = 0;
        }
        y = end;
    }
}

// ULTIMATE is drawn finely, kFine subtexels to a texel each way, then
// averaged down to smooth, anti-aliased edges. Its letters, each set in a
// fine mask over its box and kMargin texels round it.
constexpr int kFine = 4, kMargin = 4;

struct Letter {
    Mask fine;
    int left = 0, top = 0; // the still's texel at fine (0, 0)
    Letter(int l, int t, int right, int bottom)
        : fine(static_cast<uint32_t>((right - l) * kFine), static_cast<uint32_t>((bottom - t) * kFine)), left(l), top(t) {}
    // Where the subtexel's centre is in the still.
    double x(uint32_t fx) const { return left + (fx + 0.5) / kFine; }
    double y(uint32_t fy) const { return top + (fy + 0.5) / kFine; }
};

Letter around(double x0, double y0, double x1, double y1) {
    return Letter(static_cast<int>(std::floor(x0)) - kMargin, static_cast<int>(std::floor(y0)) - kMargin,
                  static_cast<int>(std::ceil(x1)) + kMargin, static_cast<int>(std::ceil(y1)) + kMargin);
}

// `p` stretched over the box from (x0, y0) to (x1, y1) of the still, set
// where more black than not, then cleaned up: only its largest part, its
// small holes (flecks of white, windows onto the logo) filled and notches
// up to a texel wide closed; then widened by `bold` texels (within the
// box).
Letter stretched(const Ink& p, double x0, double y0, double x1, double y1, float bold = 0) {
    Letter out = around(x0, y0, x1, y1);
    x0 += bold;
    y0 += bold;
    x1 -= bold;
    y1 -= bold;
    const auto at = [&](int64_t x, int64_t y) {
        return x >= 0 && y >= 0 && x < p.width && y < p.height ? p(static_cast<uint32_t>(x), static_cast<uint32_t>(y))
                                                                : 0.0f;
    };
    for (uint32_t fy = 0; fy < out.fine.height; ++fy) {
        const double sy = (out.y(fy) - y0) / (y1 - y0) * p.height - 0.5;
        const auto iy = static_cast<int64_t>(std::floor(sy));
        const double ty = sy - iy;
        for (uint32_t fx = 0; fx < out.fine.width; ++fx) {
            const double sx = (out.x(fx) - x0) / (x1 - x0) * p.width - 0.5;
            const auto ix = static_cast<int64_t>(std::floor(sx));
            const double tx = sx - ix;
            const double v = (at(ix, iy) * (1 - tx) + at(ix + 1, iy) * tx) * (1 - ty) +
                             (at(ix, iy + 1) * (1 - tx) + at(ix + 1, iy + 1) * tx) * ty;
            out.fine(fx, fy) = v > 0.5;
        }
    }
    Mask& m = out.fine;
    const std::vector<std::vector<size_t>> all = parts(m);
    const auto largest = std::max_element(all.begin(), all.end(), [](const auto& a, const auto& b) { return a.size() < b.size(); });
    std::fill(m.bits.begin(), m.bits.end(), 0);
    if (largest != all.end()) {
        for (const size_t i : *largest) m.bits[i] = 1;
    }
    m = within(within(m, kFine / 2.0f, false), kFine / 2.0f, true);
    fill_small_holes(m, 20 * kFine * kFine);
    if (bold > 0) m = within(m, bold * kFine, false);
    return out;
}

struct Point {
    float x, y;
};

// Excentrian's M and A for this logo, as outlines (texels, from the
// letter's left and up from the baseline; the A's counter second).
constexpr Point kM[] = {
    {17.1f, -49.6f}, {23.8f, -49.2f}, {27.9f, -44.1f}, {30.7f, -48.0f}, {34.9f, -49.4f}, {43.2f, -49.2f}, {47.4f, -46.9f},
    {57.8f, -35.3f}, {66.1f, -23.3f}, {68.8f, -21.9f}, {69.5f, -18.4f}, {67.9f, -16.4f}, {68.1f, -12.7f}, {63.7f, -6.7f},
    {59.4f, -3.4f},  {57.7f, 0.0f},   {53.6f, 0.0f},   {51.3f, -4.3f},  {48.0f, -7.4f},  {48.0f, -9.4f},  {46.4f, -11.0f},
    {47.8f, -22.2f}, {43.4f, -31.8f}, {41.4f, -33.9f}, {40.2f, -32.6f}, {38.6f, -24.7f}, {38.6f, -19.1f}, {33.3f, -15.9f},
    {28.6f, -15.9f}, {27.7f, -16.4f}, {27.7f, -20.1f}, {25.0f, -26.5f}, {20.8f, -33.4f}, {19.0f, -34.1f}, {18.0f, -31.6f},
    {17.3f, -21.7f}, {18.0f, -15.7f}, {19.2f, -13.6f}, {17.8f, -10.6f}, {15.9f, -9.0f},  {15.7f, -7.4f},  {12.9f, -5.7f},
    {13.2f, -3.0f},  {11.3f, -1.4f},  {5.3f, -1.4f},   {2.5f, -2.3f},   {0.9f, -4.1f},   {0.0f, -7.3f},   {1.9f, -26.7f},
    {6.5f, -43.8f},  {9.0f, -48.5f},  {11.3f, -49.4f}};
constexpr Point kA[] = {
    {21.0f, -53.3f}, {22.6f, -52.8f}, {26.5f, -47.6f}, {31.2f, -46.9f}, {34.0f, -41.5f}, {43.9f, -27.4f}, {50.6f, -26.8f},
    {50.6f, -25.8f}, {47.3f, -22.6f}, {50.3f, -17.1f}, {57.5f, -7.4f},  {57.3f, -4.4f},  {55.6f, -2.5f},  {51.7f, -1.4f},
    {45.5f, -5.5f},  {40.7f, -14.1f}, {36.9f, -18.9f}, {18.5f, -13.2f}, {9.3f, -0.5f},   {7.1f, -0.2f},   {4.8f, -1.1f},
    {3.5f, -3.0f},   {1.9f, -3.7f},   {0.2f, -9.7f},   {6.0f, -14.0f},  {14.8f, -29.6f}, {18.3f, -40.4f}, {19.8f, -51.9f}};
constexpr Point kACounter[] = {{27.9f, -32.1f}, {30.7f, -28.6f}, {30.3f, -27.2f}, {25.9f, -27.5f}, {26.8f, -31.4f}};

// A letter filled from outlines (even-odd) with its left at `x` and its
// baseline at `baseline`, the edge roughened like brush ink.
Letter outlined(std::initializer_list<std::span<const Point>> rings, double x, double baseline, uint32_t seed) {
    double right = 0, high = 0;
    for (const auto& ring : rings) {
        for (const Point& p : ring) {
            right = std::max<double>(right, p.x);
            high = std::min<double>(high, p.y);
        }
    }
    Letter out = around(x, baseline + high, x + right, baseline);
    for (uint32_t fy = 0; fy < out.fine.height; ++fy) {
        const double py = out.y(fy) - baseline;
        for (uint32_t fx = 0; fx < out.fine.width; ++fx) {
            const double px = out.x(fx) - x;
            bool inside = false;
            double nearest = 1e9;
            for (const auto& ring : rings) {
                for (size_t i = 0, j = ring.size() - 1; i < ring.size(); j = i++) {
                    const Point& a = ring[j];
                    const Point& b = ring[i];
                    if ((a.y > py) != (b.y > py) && px < a.x + (py - a.y) * (b.x - a.x) / (b.y - a.y)) inside = !inside;
                    const double ex = b.x - a.x, ey = b.y - a.y;
                    const double t = std::clamp(((px - a.x) * ex + (py - a.y) * ey) / (ex * ex + ey * ey), 0.0, 1.0);
                    const double dx = px - a.x - t * ex, dy = py - a.y - t * ey;
                    nearest = std::min(nearest, dx * dx + dy * dy);
                }
            }
            const auto gx = static_cast<uint32_t>(out.left * kFine + static_cast<int>(fx));
            const auto gy = static_cast<uint32_t>(out.top * kFine + static_cast<int>(fy));
            const double rough = 0.45 * noise(gx, gy, 2 * kFine, seed) + 0.25 * noise(gx, gy, kFine - 1, seed + 1);
            nearest = std::sqrt(nearest);
            out.fine(fx, fy) = (inside ? nearest : -nearest) + rough > 0;
        }
    }
    return out;
}

// The letters of "ULTIMATE", laid out after Excentrian's design for this
// logo (boxes in texels from the word's left at `x`): U is WiiU's; L is
// EDITION's first I with its E's bottom arm; T, I and E are EDITION's; M
// and A are Excentrian's outlines. None if a stroke is missing.
std::vector<Letter> ultimate(const Ink& still, double x) {
    constexpr Rect kU{505, 606, 418, 504}, kE{638, 684, 405, 503}, kI{733, 745, 405, 503}, kT{745, 787, 405, 503};
    constexpr Rect kEBottom{657, 689, 482, 502};
    const Ink u = cut(still, kU), e = cut(still, kE), i = cut(still, kI), bottom = cut(still, kEBottom, false);
    Ink t = cut(still, kT);
    for (const Ink* p : std::initializer_list<const Ink*>{&u, &e, &i, &t}) {
        if (p->width == 0) return {};
    }
    Ink l = join({{scaled(i, 16, 53, 0), 0, 0}, {bottom, 4, 53 - static_cast<int>(bottom.height)}});
    round_end(l, true);
    l = trim(l);
    round_end(t, false);
    round_end(t, true);
    t = trim(t);
    Ink end = e;
    round_end(end, true);
    end = trim(end);

    std::vector<Letter> letters;
    letters.push_back(stretched(u, x, 445.7, x + 55.4, 502.2, 0.75f));
    letters.push_back(stretched(l, x + 55.4, 448.0, x + 90.1, 501.1));
    letters.push_back(stretched(t, x + 82.9, 450.1, x + 123.5, 501.8));
    letters.push_back(stretched(i, x + 116.6, 457.7, x + 134.6, 502.5));
    letters.push_back(outlined({kM}, x + 134.1, 502, 3));
    letters.push_back(outlined({kA, kACounter}, x + 201.6, 502, 4));
    letters.push_back(stretched(t, x + 252.6, 452.2, x + 290.5, 500.0));
    letters.push_back(stretched(end, x + 290.5, 440.8, x + 330.5, 500.7));
    return letters;
}

} // namespace

std::optional<Rgba> logo(const Rgba& wiiu) {
    if (wiiu.width != kStill || wiiu.height != kStillHeight) return std::nullopt;
    Mask bright(kStill, kStillHeight);
    for (uint32_t y = 0; y < kStillHeight; ++y) {
        for (uint32_t x = 0; x < kStill; ++x) {
            const uint8_t* p = wiiu.at(x, y);
            bright(x, y) = std::max({p[0], p[1], p[2]}) > 150;
        }
    }
    // Letters are thick, the subtitle's curling stroke thin: thin bright
    // parts below the banner's top, and all bright ones below the
    // subtitle's top, connected to what goes on below it, are the subtitle.
    const Mask thick = spread(spread(bright, 3, true), 3, false);
    const Mask thick_near = grow(thick, 2);
    Mask candidates(kStill, kStillHeight);
    for (uint32_t y = kCurlTop + 1; y < kStillHeight; ++y) {
        for (uint32_t x = 0; x < kStill; ++x) {
            candidates(x, y) = bright(x, y) && (!thick_near(x, y) || y > kSubtitleTop);
        }
    }
    const Mask bright_subtitle = reaching_below(candidates, kSubtitleBelow);
    const Mask subtitle = grow(bright_subtitle, 4);
    // The old subtitle goes, and rows below the banner fade to black (the
    // kanji tucked behind it).
    Rgba out = wiiu;
    for (uint32_t y = 0; y < kStillHeight; ++y) {
        const double keep = std::clamp((static_cast<double>(kFadeBottom) - y) / (kFadeBottom - kFadeTop), 0.0, 1.0);
        for (uint32_t x = 0; x < kStill; ++x) {
            uint8_t* p = out.at(x, y);
            const bool gone = y > kCurlTop && subtitle(x, y) && !thick(x, y);
            for (int k = 0; k < 3; ++k) p[k] = gone ? 0 : static_cast<uint8_t>(p[k] * keep + 0.5);
        }
    }

    // The old subtitle's parts: its white (bright, near grey), the shape
    // the white goes round, and in that the ink (dark) and windows onto
    // the logo behind (the rest, where wide enough to have an inside).
    std::vector<float> luma(size_t{kStill} * kStillHeight);
    Mask white(kStill, kStillHeight), dark(kStill, kStillHeight);
    for (uint32_t y = 0; y < kStillHeight; ++y) {
        for (uint32_t x = 0; x < kStill; ++x) {
            const uint8_t* p = wiiu.at(x, y);
            const int high = std::max({p[0], p[1], p[2]}), low = std::min({p[0], p[1], p[2]});
            white(x, y) = bright_subtitle(x, y) && low > 185 && high - low < 40;
            dark(x, y) = high < 70;
            luma[size_t{y} * kStill + x] = static_cast<float>(p[0] + p[1] + p[2]) / 3;
        }
    }
    Mask shape = spread(spread(white, 2, false), 2, true);
    fill_holes(shape);
    Mask between(kStill, kStillHeight), window(kStill, kStillHeight);
    for (size_t i = 0; i < shape.bits.size(); ++i) between.bits[i] = shape.bits[i] && !white.bits[i] && !dark.bits[i];
    for (const std::vector<size_t>& part : parts(between)) {
        const bool inside = std::any_of(part.begin(), part.end(), [&](size_t i) {
            const uint32_t x = i % kStill, y = static_cast<uint32_t>(i / kStill);
            if (x == 0 || y == 0 || x + 1 >= kStill || y + 1 >= kStillHeight) return false;
            for (uint32_t ny = y - 1; ny <= y + 1; ++ny) {
                for (uint32_t nx = x - 1; nx <= x + 1; ++nx) {
                    if (!between(nx, ny)) return false;
                }
            }
            return true;
        });
        if (!inside) continue;
        for (const size_t i : part) window.bits[i] = 1;
    }
    Ink ink(kStill, kStillHeight, 0);
    for (size_t i = 0; i < ink.v.size(); ++i) {
        if (shape.bits[i] && !window.bits[i]) ink.v[i] = std::clamp((0.85f - luma[i] / 255) / 0.7f, 0.0f, 1.0f);
    }
    // "ULTIMATE" (spaced as Excentrian's design has it), then a word space
    // and EDITION, the line centred where the old one was: EDITION moves
    // right.
    constexpr int kOldLeft = 327, kEditionLeft = 640, kEditionRight = 945;
    constexpr double kWord = 330.5, kSpace = 49.8;
    const double left = (kOldLeft + kEditionRight - (kWord + kSpace + kEditionRight - kEditionLeft)) / 2;
    const auto moved = static_cast<int>(std::lround(left + kWord + kSpace - kEditionLeft));
    const std::vector<Letter> letters = ultimate(ink, left);
    if (letters.empty()) return std::nullopt;

    // The old subtitle as coverage and grey: inside the shape as it is
    // (windows black: the logo behind them has faded), and the white's
    // soft outer edge. Stray specks of the logo's highlights touch it, so
    // what is kept is the shape's large solid parts and what lies close to
    // them.
    std::vector<float> cover(ink.v.size(), 0.0f), grey(ink.v.size(), 0.0f);
    const Mask edge = grow(shape, 1);
    for (size_t i = 0; i < ink.v.size(); ++i) {
        if (shape.bits[i]) {
            cover[i] = 1;
            grey[i] = window.bits[i] ? 0 : luma[i];
        } else if (edge.bits[i]) {
            cover[i] = luma[i] / 255;
            grey[i] = 255;
        }
    }
    Mask large(kStill, kStillHeight);
    for (const std::vector<size_t>& part : parts(spread(spread(shape, 2, true), 2, false))) {
        if (part.size() <= 500) continue;
        for (const size_t i : part) large.bits[i] = 1;
    }
    Mask kept = grow(large, 2);
    for (size_t i = 0; i < kept.bits.size(); ++i) kept.bits[i] = kept.bits[i] && shape.bits[i];
    kept = grow(kept, 1);

    const auto over = [&](int x, uint32_t y, float c, float v) {
        if (x < 0 || x >= static_cast<int>(kStill)) return;
        uint8_t* p = out.at(static_cast<uint32_t>(x), y);
        for (int k = 0; k < 3; ++k) p[k] = static_cast<uint8_t>(std::clamp(p[k] * (1 - c) + v * c + 0.5f, 0.0f, 255.0f));
    };

    // The underline (below the letters' white), longer by what the line
    // grew: its left part moves with ULTIMATE's start, the rest with
    // EDITION, and the stretch before `kSplit` fills the gap twice.
    constexpr int kUnderline = 504, kUnderlineLeft = 250, kUnderlineRight = 1000, kSplit = 620;
    const auto start_moved = static_cast<int>(std::lround(left - kOldLeft));
    for (int x = kUnderlineLeft + start_moved; x < kUnderlineRight + moved; ++x) {
        const int from = x - (x < kSplit + start_moved ? start_moved : moved);
        if (from < kUnderlineLeft || from >= kUnderlineRight) continue;
        for (uint32_t y = kUnderline; y < kStillHeight; ++y) {
            const size_t i = size_t{y} * kStill + static_cast<uint32_t>(from);
            if (cover[i] > 0) over(x, y, cover[i], grey[i]);
        }
    }
    // EDITION as it was, with its N's stroke curling up beside the banner.
    constexpr int kEditionFrom = 625;
    for (uint32_t y = 0; y < kUnderline; ++y) {
        for (int x = kEditionFrom; x < kUnderlineRight; ++x) {
            const size_t i = size_t{y} * kStill + static_cast<uint32_t>(x);
            if (cover[i] > 0 && kept.bits[i]) over(x + moved, y, cover[i], grey[i]);
        }
    }
    // ULTIMATE's ink with white round it, as Excentrian drew it: five
    // texels wide (give or take a brushy half) round the ink without its
    // whiskers, two at least round them, the shape's holes and gaps filled.
    int x0 = INT32_MAX, y0 = INT32_MAX, x1 = INT32_MIN, y1 = INT32_MIN;
    for (const Letter& l : letters) {
        x0 = std::min(x0, l.left);
        y0 = std::min(y0, l.top);
        x1 = std::max(x1, l.left + static_cast<int>(l.fine.width / kFine));
        y1 = std::max(y1, l.top + static_cast<int>(l.fine.height / kFine));
    }
    constexpr float kRim = 5.0f * kFine, kRimLeast = 2.0f * kFine, kWhiskers = 1.5f * kFine;
    x0 -= 4;
    y0 -= 4;
    x1 += 4;
    y1 += 4;
    // Letters stay apart, a texel of white between them: each loses what
    // comes that close to the ones before.
    Mask word(static_cast<uint32_t>((x1 - x0) * kFine), static_cast<uint32_t>((y1 - y0) * kFine));
    for (const Letter& l : letters) {
        const uint32_t ox = static_cast<uint32_t>((l.left - x0) * kFine), oy = static_cast<uint32_t>((l.top - y0) * kFine);
        Mask here(l.fine.width, l.fine.height); // the word so far where the letter goes
        for (uint32_t fy = 0; fy < l.fine.height; ++fy) {
            for (uint32_t fx = 0; fx < l.fine.width; ++fx) here(fx, fy) = word(ox + fx, oy + fy);
        }
        const std::vector<float> before = distance(here);
        for (uint32_t fy = 0; fy < l.fine.height; ++fy) {
            for (uint32_t fx = 0; fx < l.fine.width; ++fx) {
                if (l.fine(fx, fy) && before[size_t{fy} * l.fine.width + fx] > kFine) word(ox + fx, oy + fy) = 1;
            }
        }
    }
    const Mask body = within(within(word, kWhiskers, true), kWhiskers, false);
    const std::vector<float> from_body = distance(body), from_ink = distance(word);
    Mask rim(word.width, word.height);
    for (uint32_t fy = 0; fy < word.height; ++fy) {
        for (uint32_t fx = 0; fx < word.width; ++fx) {
            const size_t i = size_t{fy} * word.width + fx;
            const float reach = kRim + 0.5f * kFine * noise(fx, fy, 3 * kFine, 1);
            rim.bits[i] = from_body[i] <= reach || from_ink[i] <= kRimLeast;
        }
    }
    fill_holes(rim);
    for (int y = y0; y < y1; ++y) {
        for (int x = x0; x < x1; ++x) {
            int black = 0, covered = 0;
            for (uint32_t fy = 0; fy < kFine; ++fy) {
                for (uint32_t fx = 0; fx < kFine; ++fx) {
                    const uint32_t wx = static_cast<uint32_t>((x - x0) * kFine) + fx, wy = static_cast<uint32_t>((y - y0) * kFine) + fy;
                    black += word(wx, wy);
                    covered += rim(wx, wy) || word(wx, wy);
                }
            }
            if (covered == 0 || y < 0 || y >= static_cast<int>(kStillHeight)) continue;
            over(x, static_cast<uint32_t>(y), covered / static_cast<float>(kFine * kFine),
                 255.0f * (covered - black) / covered);
        }
    }
    return out;
}

std::optional<Rgba> copyright_line(const Rgba& line) {
    // Words: runs of columns with letters (bright texels) apart by five
    // empty ones or more.
    std::vector<std::pair<uint32_t, uint32_t>> words;
    uint32_t x = 0;
    const auto ink = [&](uint32_t column) {
        for (uint32_t y = 0; y < line.height; ++y) {
            const uint8_t* p = line.at(column, y);
            if (std::min({p[0], p[1], p[2]}) > 150 && p[3] > 128) return true;
        }
        return false;
    };
    while (x < line.width) {
        if (!ink(x)) {
            ++x;
            continue;
        }
        const uint32_t start = x;
        uint32_t end = x, gap = 0;
        while (x < line.width && gap < 5) {
            if (ink(x)) {
                gap = 0;
                end = x + 1;
            } else {
                ++gap;
            }
            ++x;
        }
        words.push_back({start, end});
    }
    // "... 2 Wii U EDITION & (C) 2012 NAMCO BANDAI Games Inc.": the seven
    // words from "&" on end the line.
    if (words.size() < 10) return std::nullopt;
    constexpr uint32_t kOutline = 3; // letters' dark edge, before their first bright column
    const uint32_t cut_from = words[words.size() - 10].first - kOutline;
    const uint32_t cut_to = words[words.size() - 7].first - kOutline;
    Rgba joined = blank(line.width - (cut_to - cut_from), line.height);
    put(joined, crop(line, 0, 0, cut_from, line.height), 0, 0);
    put(joined, crop(line, cut_to, 0, line.width - cut_to, line.height), cut_from, 0);
    // Centred as before.
    uint32_t left = joined.width, right = 0;
    for (uint32_t y = 0; y < joined.height; ++y) {
        for (uint32_t c = 0; c < joined.width; ++c) {
            if (joined.at(c, y)[3] != 0) {
                left = std::min(left, c);
                right = std::max(right, c + 1);
            }
        }
    }
    if (right <= left) return std::nullopt;
    Rgba out = blank(line.width, line.height);
    put(out, crop(joined, left, 0, right - left, joined.height), (line.width - (right - left)) / 2, 0);
    return out;
}

} // namespace cafe::title::title_screen
