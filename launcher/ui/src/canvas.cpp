#include "ttt2ui/canvas.h"

#include <SDL3/SDL.h>

#include <cmath>

namespace ttt2::ui {

namespace {

float dot(Vec2 a, Vec2 b) { return a.x * b.x + a.y * b.y; }
float length(Vec2 a) { return std::sqrt(dot(a, a)); }

// Consecutive duplicates removed (they have no edge normal).
void dedupe(std::vector<Vec2>& p) {
    std::vector<Vec2> out;
    out.reserve(p.size());
    for (const Vec2& v : p)
        if (out.empty() || std::fabs(v.x - out.back().x) > 1e-4f || std::fabs(v.y - out.back().y) > 1e-4f) out.push_back(v);
    while (out.size() > 1 && std::fabs(out.front().x - out.back().x) < 1e-4f &&
           std::fabs(out.front().y - out.back().y) < 1e-4f)
        out.pop_back();
    p = std::move(out);
}

float signed_area(const std::vector<Vec2>& p) {
    float a = 0;
    for (std::size_t i = 0, n = p.size(); i < n; ++i) a += p[i].x * p[(i + 1) % n].y - p[(i + 1) % n].x * p[i].y;
    return a;
}

// The polygon moved `d` pixels outward (negative: inward) along mitred vertex normals.
std::vector<Vec2> offset_polygon(const std::vector<Vec2>& p, float d) {
    const std::size_t n = p.size();
    const float side = signed_area(p) > 0 ? 1.f : -1.f;
    auto normal = [&](Vec2 a, Vec2 b) {
        Vec2 e = b - a;
        float l = length(e);
        if (l < 1e-6f) return Vec2{0, 0};
        return Vec2{side * e.y / l, -side * e.x / l};
    };
    std::vector<Vec2> out(n);
    for (std::size_t i = 0; i < n; ++i) {
        Vec2 before = normal(p[(i + n - 1) % n], p[i]), after = normal(p[i], p[(i + 1) % n]);
        Vec2 m = before + after;
        float l = length(m);
        if (l < 1e-6f) {
            out[i] = p[i] + after * d;
            continue;
        }
        m = m * (1 / l);
        float reach = d / std::max(.25f, dot(m, before));
        out[i] = p[i] + m * reach;
    }
    return out;
}

// The part of a convex polygon where dot(p, axis) >= limit (sign = 1) or <= limit (sign = -1).
std::vector<Vec2> clip_half(const std::vector<Vec2>& p, Vec2 axis, float limit, float sign) {
    std::vector<Vec2> out;
    const std::size_t n = p.size();
    for (std::size_t i = 0; i < n; ++i) {
        Vec2 a = p[i], b = p[(i + 1) % n];
        float da = sign * (dot(a, axis) - limit), db = sign * (dot(b, axis) - limit);
        if (da >= 0) out.push_back(a);
        if ((da >= 0) != (db >= 0)) {
            float t = da / (da - db);
            out.push_back(a + (b - a) * t);
        }
    }
    return out;
}

}  // namespace

Gradient Gradient::css(const Rect& r, float degrees, std::initializer_list<GradientStop> stops) {
    // CSS: the gradient line goes through the centre at the angle (0deg = up, 90deg = right) and is as long as
    // needed for the corners to get the end colours.
    const float a = degrees * 3.14159265f / 180;
    const Vec2 dir{std::sin(a), -std::cos(a)};
    const float half = std::fabs(r.w * dir.x) / 2 + std::fabs(r.h * dir.y) / 2;
    const Vec2 c = r.center();
    Gradient g;
    g.from = c - dir * half;
    g.to = c + dir * half;
    for (const GradientStop& s : stops)
        if (g.count < 6) g.stops[g.count++] = s;
    return g;
}

Color Gradient::at(Vec2 p) const {
    if (count <= 0) return {};
    const Vec2 axis = to - from;
    const float l2 = dot(axis, axis);
    const float t = l2 > 0 ? dot(p - from, axis) / l2 : 0;
    if (t <= stops[0].at) return stops[0].color;
    for (int i = 1; i < count; ++i)
        if (t <= stops[i].at) {
            const float span = stops[i].at - stops[i - 1].at;
            return mix(stops[i - 1].color, stops[i].color, span > 0 ? (t - stops[i - 1].at) / span : 1);
        }
    return stops[count - 1].color;
}

Quad skewed(const Rect& r, float tan) {
    const float d = r.h / 2 * tan;
    return {{{r.x + d, r.y}, {r.x + r.w + d, r.y}, {r.x + r.w - d, r.y + r.h}, {r.x - d, r.y + r.h}}};
}

Canvas::Canvas(SDL_Renderer* renderer, TextureRegistry& textures) : renderer_(renderer), textures_(textures) {}
Canvas::~Canvas() = default;

void Canvas::begin(float scale, int pixel_width, int pixel_height) {
    flush();
    scale_ = scale;
    width_ = pixel_width;
    height_ = pixel_height;
    offset_ = {};
    alpha_ = 1;
    layers_.clear();
    clips_.clear();
    draw_calls_ = 0;
    if (renderer_) {
        SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_BLEND);
        SDL_SetRenderClipRect(renderer_, nullptr);
    }
}

void Canvas::push_layer(Vec2 offset, float alpha) {
    layers_.push_back({offset_, alpha_});
    offset_ = offset_ + offset;
    alpha_ *= alpha;
}
void Canvas::pop_layer() {
    if (layers_.empty()) return;
    offset_ = layers_.back().offset;
    alpha_ = layers_.back().alpha;
    layers_.pop_back();
}

void Canvas::push_clip(const Rect& r) {
    const Vec2 a = to_pixels({r.x, r.y}), b = to_pixels({r.right(), r.bottom()});
    Rect px{std::floor(a.x), std::floor(a.y), 0, 0};
    px.w = std::ceil(b.x) - px.x;
    px.h = std::ceil(b.y) - px.y;
    if (!clips_.empty()) px = px.intersect(clips_.back());
    clips_.push_back(px);
    flush();
    apply_clip();
}
void Canvas::pop_clip() {
    if (clips_.empty()) return;
    flush();
    clips_.pop_back();
    apply_clip();
}
Rect Canvas::clip() const {
    Rect px = clips_.empty() ? Rect{0, 0, static_cast<float>(width_), static_cast<float>(height_)} : clips_.back();
    return {px.x / scale_ - offset_.x, px.y / scale_ - offset_.y, px.w / scale_, px.h / scale_};
}
void Canvas::apply_clip() {
    if (!renderer_) return;
    if (clips_.empty()) {
        SDL_SetRenderClipRect(renderer_, nullptr);
        return;
    }
    const Rect& c = clips_.back();
    SDL_Rect r{static_cast<int>(c.x), static_cast<int>(c.y), std::max(0, static_cast<int>(c.w)),
               std::max(0, static_cast<int>(c.h))};
    SDL_SetRenderClipRect(renderer_, &r);
}

void Canvas::use(TextureId texture) {
    if (texture != batch_texture_) {
        flush();
        batch_texture_ = texture;
    }
}

void Canvas::add_vertex(Vec2 px, Color c, Vec2 uv) {
    xy_.push_back(px.x);
    xy_.push_back(px.y);
    rgba_.push_back(c.r);
    rgba_.push_back(c.g);
    rgba_.push_back(c.b);
    rgba_.push_back(c.a * alpha_);
    uv_.push_back(uv.x);
    uv_.push_back(uv.y);
}
void Canvas::tri(int a, int b, int c) { indices_.insert(indices_.end(), {a, b, c}); }

void Canvas::flush() {
    if (!indices_.empty() && renderer_) {
        SDL_Texture* texture = batch_texture_ ? textures_.get(batch_texture_) : nullptr;
        if (!batch_texture_ || texture) {
            SDL_RenderGeometryRaw(renderer_, texture, xy_.data(), 2 * sizeof(float),
                                  reinterpret_cast<const SDL_FColor*>(rgba_.data()), 4 * sizeof(float), uv_.data(),
                                  2 * sizeof(float), static_cast<int>(xy_.size() / 2), indices_.data(),
                                  static_cast<int>(indices_.size()), sizeof(int));
            ++draw_calls_;
        }
    }
    xy_.clear();
    uv_.clear();
    rgba_.clear();
    indices_.clear();
}

template <class Shade> void Canvas::fill_px(std::vector<Vec2>& px, Shade&& shade, bool interior) {
    dedupe(px);
    if (px.size() < 3) return;
    use(0);
    const std::vector<Vec2> inner = offset_polygon(px, -.5f), outer = offset_polygon(px, .5f);
    const int n = static_cast<int>(px.size());
    if (interior) {
        const int base = static_cast<int>(xy_.size() / 2);
        for (const Vec2& v : inner) add_vertex(v, shade(v));
        for (int i = 1; i + 1 < n; ++i) tri(base, base + i, base + i + 1);
    }
    const int ring = static_cast<int>(xy_.size() / 2);
    for (int i = 0; i < n; ++i) {
        add_vertex(inner[i], shade(inner[i]));
        Color c = shade(outer[i]);
        c.a = 0;
        add_vertex(outer[i], c);
    }
    for (int i = 0; i < n; ++i) {
        int a = ring + 2 * i, b = ring + 2 * ((i + 1) % n);
        tri(a, a + 1, b + 1);
        tri(a, b + 1, b);
    }
}

void Canvas::fill(std::span<const Vec2> points, Color color) {
    if (color.a <= 0) return;
    std::vector<Vec2> px;
    px.reserve(points.size());
    for (const Vec2& p : points) px.push_back(to_pixels(p));
    fill_px(px, [&](Vec2) { return color; });
}

void Canvas::fill(std::span<const Vec2> points, const Gradient& gradient) {
    if (gradient.count <= 0) return;
    if (gradient.count == 1) return fill(points, gradient.stops[0].color);
    Gradient g = gradient;
    g.from = to_pixels(g.from);
    g.to = to_pixels(g.to);
    std::vector<Vec2> px;
    px.reserve(points.size());
    for (const Vec2& p : points) px.push_back(to_pixels(p));
    auto shade = [&](Vec2 p) { return g.at(p); };
    // The feather ring only, then the inside split at each stop into slabs with exact colours at their edges.
    fill_px(px, shade, false);
    dedupe(px);
    if (px.size() < 3) return;
    std::vector<Vec2> inner = offset_polygon(px, -.5f);
    const Vec2 axis = g.to - g.from;
    const float l2 = dot(axis, axis);
    if (l2 <= 0) return;
    auto t_at = [&](float t) { return dot(g.from + axis * t, axis); };
    std::vector<float> cuts;
    for (int i = 0; i < g.count; ++i) cuts.push_back(t_at(g.stops[i].at));
    for (std::size_t s = 0; s <= cuts.size(); ++s) {
        std::vector<Vec2> slab = inner;
        if (s > 0) slab = clip_half(slab, axis, cuts[s - 1], 1);
        if (s < cuts.size() && slab.size() >= 3) slab = clip_half(slab, axis, cuts[s], -1);
        if (slab.size() < 3) continue;
        const int base = static_cast<int>(xy_.size() / 2);
        for (const Vec2& v : slab) add_vertex(v, g.at(v));
        for (int i = 1; i + 1 < static_cast<int>(slab.size()); ++i) tri(base, base + i, base + i + 1);
    }
}

void Canvas::fill_rect(const Rect& r, Color color) {
    const Vec2 p[4] = {{r.x, r.y}, {r.right(), r.y}, {r.right(), r.bottom()}, {r.x, r.bottom()}};
    fill(p, color);
}
void Canvas::fill_rect(const Rect& r, const Gradient& g) {
    const Vec2 p[4] = {{r.x, r.y}, {r.right(), r.y}, {r.right(), r.bottom()}, {r.x, r.bottom()}};
    fill(p, g);
}

void Canvas::stroke(std::span<const Vec2> points, float width, Color color) {
    if (color.a <= 0 || width <= 0) return;
    std::vector<Vec2> px;
    for (const Vec2& p : points) px.push_back(to_pixels(p));
    dedupe(px);
    if (px.size() < 3) return;
    use(0);
    const float w = width * scale_, hw = std::max(w / 2, .5f), a = color.a * std::min(1.f, w), c = -w / 2;
    const float offsets[4] = {c + hw + .5f, c + hw - .5f, c - hw + .5f, c - hw - .5f};
    const float alphas[4] = {0, a, a, 0};
    std::vector<Vec2> rings[4];
    for (int k = 0; k < 4; ++k) rings[k] = offset_polygon(px, offsets[k]);
    const int n = static_cast<int>(px.size());
    const int base = static_cast<int>(xy_.size() / 2);
    for (int k = 0; k < 4; ++k)
        for (int i = 0; i < n; ++i) add_vertex(rings[k][i], color.with_alpha(alphas[k]));
    for (int k = 0; k < 3; ++k)
        for (int i = 0; i < n; ++i) {
            int a0 = base + k * n + i, a1 = base + k * n + (i + 1) % n, b0 = a0 + n, b1 = a1 + n;
            tri(a0, b0, b1);
            tri(a0, b1, a1);
        }
}

void Canvas::glow(std::span<const Vec2> points, float radius, Color color) {
    if (color.a <= 0 || radius <= 0) return;
    std::vector<Vec2> px;
    for (const Vec2& p : points) px.push_back(to_pixels(p));
    dedupe(px);
    if (px.size() < 3) return;
    use(0);
    const float r = radius * scale_;
    const float offsets[4] = {0, r * .3f, r * .62f, r};
    const float alphas[4] = {color.a, color.a * .42f, color.a * .12f, 0};
    const int n = static_cast<int>(px.size());
    const int base = static_cast<int>(xy_.size() / 2);
    for (int k = 0; k < 4; ++k) {
        std::vector<Vec2> ring = offset_polygon(px, offsets[k]);
        for (int i = 0; i < n; ++i) add_vertex(ring[i], color.with_alpha(alphas[k]));
    }
    for (int k = 0; k < 3; ++k)
        for (int i = 0; i < n; ++i) {
            int a0 = base + k * n + i, a1 = base + k * n + (i + 1) % n, b0 = a0 + n, b1 = a1 + n;
            tri(a0, b0, b1);
            tri(a0, b1, a1);
        }
}

void Canvas::line(Vec2 a, Vec2 b, float width, Color color) { line(a, b, width, color, color); }
void Canvas::line(Vec2 a, Vec2 b, float width, Color ca, Color cb) {
    Vec2 d = b - a;
    float l = length(d);
    if (l < 1e-6f) return;
    Vec2 n{-d.y / l * width / 2, d.x / l * width / 2};
    const Vec2 p[4] = {a + n, b + n, b - n, a - n};
    if (ca == cb) fill(p, ca);
    else fill(p, Gradient::linear(a, b, ca, cb));
}

namespace {
int segments_for(float radius_px) { return std::clamp(static_cast<int>(radius_px * .9f), 12, 96); }
}  // namespace

void Canvas::circle(Vec2 center, float radius, Color color) {
    const int n = segments_for(radius * scale_);
    std::vector<Vec2> p(n);
    for (int i = 0; i < n; ++i) {
        float a = 6.2831853f * static_cast<float>(i) / static_cast<float>(n);
        p[i] = {center.x + radius * std::cos(a), center.y + radius * std::sin(a)};
    }
    fill(p, color);
}

void Canvas::ring(Vec2 center, float radius, float width, Color color) {
    const int n = segments_for(radius * scale_);
    std::vector<Vec2> p(n);
    for (int i = 0; i < n; ++i) {
        float a = 6.2831853f * static_cast<float>(i) / static_cast<float>(n);
        p[i] = {center.x + radius * std::cos(a), center.y + radius * std::sin(a)};
    }
    stroke(p, width, color);
}

void Canvas::radial(Vec2 center, float radius, Color color) {
    if (color.a <= 0 || radius <= 0) return;
    use(0);
    const Vec2 c = to_pixels(center);
    const float r = radius * scale_;
    const int n = 48;
    const float ts[4] = {0, .35f, .7f, 1}, as[4] = {1, .55f, .18f, 0};
    const int base = static_cast<int>(xy_.size() / 2);
    add_vertex(c, color);
    for (int k = 1; k < 4; ++k)
        for (int i = 0; i < n; ++i) {
            float a = 6.2831853f * static_cast<float>(i) / n;
            add_vertex({c.x + r * ts[k] * std::cos(a), c.y + r * ts[k] * std::sin(a)}, color.with_alpha(color.a * as[k]));
        }
    for (int i = 0; i < n; ++i) tri(base, base + 1 + i, base + 1 + (i + 1) % n);
    for (int k = 1; k < 3; ++k)
        for (int i = 0; i < n; ++i) {
            int a0 = base + 1 + (k - 1) * n + i, a1 = base + 1 + (k - 1) * n + (i + 1) % n, b0 = a0 + n, b1 = a1 + n;
            tri(a0, b0, b1);
            tri(a0, b1, a1);
        }
}

void Canvas::image(TextureId texture, const Rect& dst, Color tint, const Rect& uv) {
    if (!texture) return;
    use(texture);
    const Vec2 a = to_pixels({dst.x, dst.y}), b = to_pixels({dst.right(), dst.bottom()});
    const int base = static_cast<int>(xy_.size() / 2);
    add_vertex({a.x, a.y}, tint, {uv.x, uv.y});
    add_vertex({b.x, a.y}, tint, {uv.x + uv.w, uv.y});
    add_vertex({b.x, b.y}, tint, {uv.x + uv.w, uv.y + uv.h});
    add_vertex({a.x, b.y}, tint, {uv.x, uv.y + uv.h});
    tri(base, base + 1, base + 2);
    tri(base, base + 2, base + 3);
}

void Canvas::textured(TextureId texture, std::span<const Vec2> points, std::span<const Vec2> uvs, Color tint) {
    if (!texture || points.size() < 3 || uvs.size() < points.size()) return;
    use(texture);
    const int base = static_cast<int>(xy_.size() / 2);
    for (std::size_t i = 0; i < points.size(); ++i) add_vertex(to_pixels(points[i]), tint, uvs[i]);
    for (int i = 1; i + 1 < static_cast<int>(points.size()); ++i) tri(base, base + i, base + i + 1);
}

void Canvas::glyph_quad(TextureId texture, float x0, float y0, float x1, float y1, float u0, float v0, float u1,
                        float v1, Color color, float shear, float baseline) {
    use(texture);
    const int base = static_cast<int>(xy_.size() / 2);
    const float s0 = shear * (baseline - y0), s1 = shear * (baseline - y1);
    add_vertex({x0 + s0, y0}, color, {u0, v0});
    add_vertex({x1 + s0, y0}, color, {u1, v0});
    add_vertex({x1 + s1, y1}, color, {u1, v1});
    add_vertex({x0 + s1, y1}, color, {u0, v1});
    tri(base, base + 1, base + 2);
    tri(base, base + 2, base + 3);
}

void Canvas::begin_target(TextureId target, float scale) {
    flush();
    targets_.push_back({target, scale_, width_, height_, clips_});
    SDL_Texture* t = textures_.get(target);
    int w = 0, h = 0;
    textures_.size(target, w, h);
    if (renderer_ && t) {
        SDL_SetRenderTarget(renderer_, t);
        SDL_SetTextureBlendMode(t, SDL_BLENDMODE_BLEND_PREMULTIPLIED);
        SDL_SetRenderClipRect(renderer_, nullptr);
        SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_NONE);
        SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 0);
        SDL_RenderClear(renderer_);
        SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_BLEND);
    }
    scale_ = scale;
    width_ = w;
    height_ = h;
    clips_.clear();
}

void Canvas::end_target() {
    flush();
    if (targets_.empty()) return;
    TargetState s = targets_.back();
    targets_.pop_back();
    if (renderer_) {
        SDL_Texture* previous = nullptr;
        if (!targets_.empty()) previous = textures_.get(targets_.back().target);
        SDL_SetRenderTarget(renderer_, previous);
    }
    scale_ = s.scale;
    width_ = s.w;
    height_ = s.h;
    clips_ = s.clips;
    apply_clip();
}

}  // namespace ttt2::ui
