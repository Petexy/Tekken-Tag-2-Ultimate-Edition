// Drawing: anti-aliased convex shapes, gradients, glows, images and glyph quads as SDL_RenderGeometry batches.
// Callers give points; the canvas transforms every vertex to physical pixels itself (scale, offset), so edges get
// a feather of exactly one physical pixel at any scale. A batch is flushed when its texture changes, so drawing
// order is kept.
#pragma once

#include <cstdint>
#include <functional>

#include <initializer_list>
#include <span>
#include <vector>

#include "ttt2ui/geometry.h"
#include "ttt2ui/textures.h"

struct SDL_Renderer;

namespace ttt2::ui {

struct GradientStop {
    float at;  // 0..1 along the gradient
    Color color;
};
// A linear gradient from point `from` (stop 0) to `to` (stop 1), up to 6 stops in order.
struct Gradient {
    Vec2 from, to;
    GradientStop stops[6];
    int count = 0;
    static Gradient linear(Vec2 a, Vec2 b, Color c0, Color c1) { return {a, b, {{0, c0}, {1, c1}}, 2}; }
    static Gradient linear3(Vec2 a, Vec2 b, Color c0, float m, Color cm, Color c1) {
        return {a, b, {{0, c0}, {m, cm}, {1, c1}}, 3};
    }
    // A gradient at CSS's angle (degrees: 90 = left to right, 180 = top to bottom) over a rectangle.
    static Gradient css(const Rect& r, float degrees, std::initializer_list<GradientStop> stops);
    Color at(Vec2 p) const;
};

// The parallelogram of a box skewed like CSS skewX(-12deg) about its centre: top edge moved right by h/2*tan,
// bottom edge left (`tan` = 0 gives the rectangle).
struct Quad {
    Vec2 p[4];
};
Quad skewed(const Rect& r, float tan);
// The crimson lists' shape: the left edge upright (it lines up with the window's straight left edge), the right edge
// slanted like skewed()'s (it follows the seam).
Quad straight_left(const Rect& r, float tan);
// The blue half's mirror of it: the right edge upright (in line with the window's right edge), the left one slanted.
Quad straight_right(const Rect& r, float tan);
// A shape by kind: Rect (upright), Skewed (both sides slanted), StraightLeft / StraightRight (see above).
enum class Shape : std::uint8_t { Rect, Skewed, StraightLeft, StraightRight };
Quad shaped(const Rect& r, Shape shape, float tan);
// A point of `box`'s upright coordinates moved onto its shape (parts drawn inside a shaped box: streaks, accents).
Vec2 shaped_point(const Rect& box, Vec2 p, Shape shape, float tan);
Quad shaped_part(const Rect& box, const Rect& part, Shape shape, float tan);
// x of a skewed box's left/right edge at height y.
inline float skew_dx(const Rect& r, float y, float tan) { return (r.y + r.h / 2 - y) * tan; }

class Canvas {
public:
    Canvas(SDL_Renderer* renderer, TextureRegistry& textures);
    ~Canvas();

    // A frame (or a render target) of w x h physical pixels at `scale` pixels per point.
    void begin(float scale, int pixel_width, int pixel_height);
    void flush();
    float scale() const { return scale_; }
    int pixel_width() const { return width_; }
    int pixel_height() const { return height_; }
    SDL_Renderer* renderer() const { return renderer_; }
    TextureRegistry& textures() { return textures_; }

    // Translation (points) and opacity applied to everything drawn until the matching pop.
    void push_layer(Vec2 offset, float alpha = 1);
    void pop_layer();
    float alpha() const { return alpha_; }
    // Clipping to a rectangle (points), intersected with the current one.
    void push_clip(const Rect& r);
    void pop_clip();
    Rect clip() const;  // the current clip in points (the whole canvas when none)

    // Shapes (convex polygons, either winding).
    void fill(std::span<const Vec2> points, Color color);
    void fill(std::span<const Vec2> points, const Gradient& gradient);
    void fill(const Quad& q, Color color) { fill(std::span<const Vec2>(q.p, 4), color); }
    void fill(const Quad& q, const Gradient& g) { fill(std::span<const Vec2>(q.p, 4), g); }
    void fill_rect(const Rect& r, Color color);
    void fill_rect(const Rect& r, const Gradient& g);
    // A border `width` points wide inside the shape's edge.
    void stroke(std::span<const Vec2> points, float width, Color color);
    void stroke(const Quad& q, float width, Color color) { stroke(std::span<const Vec2>(q.p, 4), width, color); }
    // A soft glow outside the shape, fading to nothing `radius` points away.
    void glow(std::span<const Vec2> points, float radius, Color color);
    void glow(const Quad& q, float radius, Color color) { glow(std::span<const Vec2>(q.p, 4), radius, color); }
    void line(Vec2 a, Vec2 b, float width, Color color);
    void line(Vec2 a, Vec2 b, float width, Color ca, Color cb);
    void circle(Vec2 center, float radius, Color color);
    void ring(Vec2 center, float radius, float width, Color color);
    // A radial light: `color` at the centre fading out at `radius`.
    void radial(Vec2 center, float radius, Color color);

    // Images: the whole texture (or `uv` part of it, 0..1) into `dst`, multiplied by `tint`.
    void image(TextureId texture, const Rect& dst, Color tint = {1, 1, 1, 1}, const Rect& uv = {0, 0, 1, 1});
    // A texture through a convex polygon with texture coordinates per point (the wipe).
    void textured(TextureId texture, std::span<const Vec2> points, std::span<const Vec2> uvs,
                  Color tint = {1, 1, 1, 1});
    // A picture: the texture's `uv` part laid over `dst`, cut to the convex polygon `shape` (either winding), its
    // opacity at each point alpha(p) (exact at the corners of a grid of `cells` x `cells` over `dst`, linear
    // between): soft edges and fades (the added fighters' portraits).
    void picture(TextureId texture, const Rect& dst, const Rect& uv, std::span<const Vec2> shape,
                 const std::function<float(Vec2)>& alpha, Color tint = {1, 1, 1, 1}, int cells = 8);
    // One glyph quad in PHYSICAL pixels (text engine), with x shifted by `shear` * (baseline - y) for slanted text.
    void glyph_quad(TextureId texture, float x0, float y0, float x1, float y1, float u0, float v0, float u1, float v1,
                    Color color, float shear = 0, float baseline = 0);

    // Render targets: draw into `target` (cleared) until end_target.
    void begin_target(TextureId target, float scale);
    void end_target();

    // Points <-> physical pixels with the current layers.
    Vec2 to_pixels(Vec2 p) const { return {(p.x + offset_.x) * scale_, (p.y + offset_.y) * scale_}; }
    float pixel() const { return 1 / scale_; }  // one physical pixel in points

    std::size_t draw_calls() const { return draw_calls_; }

private:
    void use(TextureId texture);
    void add_vertex(Vec2 px, Color c, Vec2 uv = {});
    void tri(int a, int b, int c);
    // A convex polygon in pixels, AA'd: fill by `shade` (per vertex), feather ring alpha 0 outside.
    template <class Shade> void fill_px(std::vector<Vec2>& px, Shade&& shade, bool interior = true);
    void apply_clip();

    SDL_Renderer* renderer_;
    TextureRegistry& textures_;
    float scale_ = 1;
    int width_ = 0, height_ = 0;
    Vec2 offset_{};
    float alpha_ = 1;
    struct Layer {
        Vec2 offset;
        float alpha;
    };
    std::vector<Layer> layers_;
    std::vector<Rect> clips_;  // in pixels
    struct TargetState {
        TextureId target;
        float scale;
        int w, h;
        std::vector<Rect> clips;
    };
    std::vector<TargetState> targets_;
    TextureId batch_texture_ = 0;
    std::vector<float> xy_, uv_;
    std::vector<float> rgba_;
    std::vector<int> indices_;
    std::size_t draw_calls_ = 0;
};

}  // namespace ttt2::ui
