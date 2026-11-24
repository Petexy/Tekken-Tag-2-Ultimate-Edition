#include "ttt2ui/stage.h"

#include <SDL3/SDL.h>

#include <cmath>
#include <vector>

namespace ttt2::ui {

namespace c = theme::color;
using theme::kSeamTan;

namespace {
constexpr float kCos12 = 0.97814760073f, kSin12 = 0.20791169081f;
}  // namespace

SplitStage::SplitStage(TextureRegistry& textures, std::uint64_t seed) : textures_(textures), random_(seed) {
    for (int i = 0; i < theme::motion::kSpeedLines; ++i) lines_.push_back(new_line(true));
    // The halftone dot: a white disc with a soft edge, drawn many times from one texture.
    const int n = 32;
    std::vector<std::uint8_t> px(static_cast<std::size_t>(n) * n * 4);
    for (int y = 0; y < n; ++y)
        for (int x = 0; x < n; ++x) {
            const float dx = static_cast<float>(x) + .5f - n / 2.f, dy = static_cast<float>(y) + .5f - n / 2.f;
            const float a = clamp01(n / 2.f - 1 - std::sqrt(dx * dx + dy * dy) + .5f);
            std::uint8_t* p = &px[(static_cast<std::size_t>(y) * n + x) * 4];
            p[0] = p[1] = p[2] = 255;
            p[3] = static_cast<std::uint8_t>(std::lround(a * 255));
        }
    dot_ = textures_.create(n, n, std::move(px));
}

SplitStage::~SplitStage() {
    textures_.destroy(dot_);
    if (layer_) textures_.destroy(layer_);
}

SplitStage::Line SplitStage::new_line(bool initial) {
    const float side = random_.uniform() < .5f ? -1.f : 1.f;
    Line l;
    l.off = side * (6 + std::pow(random_.uniform(), 1.7f) * (theme::motion::kSpeedLineReach - 40));
    l.y = initial ? random_.uniform() * (size_.y + 200) - 100 : size_.y + random_.uniform() * 240;
    l.len = 60 + random_.uniform() * 240;
    l.speed = 260 + random_.uniform() * 700;
    l.width = random_.uniform() < .2f ? 3 : 1.2f;
    l.alpha = .08f + random_.uniform() * .22f;
    return l;
}

void SplitStage::set_target(float share, bool tall_plates, int focus_side) {
    share_ = share;
    tall_ = tall_plates;
    side_ = focus_side;
}

void SplitStage::snap() {
    c_.snap_to(share_);
    bottom_.snap_to(tall_ ? 1.f : 0.f);
    lean_.snap_to(side_ > 0 ? theme::kLean : 0.f);
    bright_red_ = side_ < 0 ? theme::motion::kBrightRed : 1;
    bright_blue_ = side_ > 0 ? theme::motion::kBrightBlue : 1;
    lock_ = lock_side_ != 0 ? 1.f : 0.f;
    if (lock_side_) lock_drawn_ = lock_side_;
}

void SplitStage::update(double, float dt, Vec2 size, bool reduced) {
    size_ = size;
    reduced_ = reduced;
    c_.target = share_;
    bottom_.target = tall_ ? 1.f : 0.f;
    lean_.target = side_ > 0 ? theme::kLean : 0.f;
    if (reduced) {
        c_.snap();
        bottom_.snap();
        lean_.snap();
    } else {
        c_.step(dt);
        bottom_.step(dt);
        lean_.step(dt);
    }
    const float k = reduced ? 1 : 1 - std::exp(-theme::motion::kBrightRate * dt);
    bright_red_ += ((side_ < 0 ? theme::motion::kBrightRed : 1) - bright_red_) * k;
    bright_blue_ += ((side_ > 0 ? theme::motion::kBrightBlue : 1) - bright_blue_) * k;
    if (lock_side_) lock_drawn_ = lock_side_;
    const float lock_to = lock_side_ != 0 ? 1.f : 0.f;
    lock_ = reduced ? lock_to : lock_ + (lock_to - lock_) * (1 - std::exp(-theme::motion::kLockRate * dt));
    if (std::fabs(lock_ - lock_to) < .005f) lock_ = lock_to;
    animating_ = lock_ != lock_to || !c_.settled(.0005f) || !bottom_.settled(.002f) || !lean_.settled(.05f) ||
                 std::fabs(bright_red_ - (side_ < 0 ? theme::motion::kBrightRed : 1)) > .005f ||
                 std::fabs(bright_blue_ - (side_ > 0 ? theme::motion::kBrightBlue : 1)) > .005f;
}

Seam SplitStage::layout_seam(float share) const {
    return {share * size_.x, (theme::kTopBand + size_.y - theme::kBottomBand) / 2, kSeamTan};
}
Seam SplitStage::seam_now() const { return layout_seam(c_.value); }

float SplitStage::plate_bottom() const {
    // (The gaps are measured from the prompt band: 688 and 740 of 800.)
    const float bottom = size_.y - theme::kBottomBand;
    return lerp(bottom - theme::kPlateBottomGap, bottom - theme::kPlateBottomGapTask, bottom_.value);
}

Rect SplitStage::crimson_area(float share) const {
    const float left = theme::kPlateSide + theme::kPlatePad;
    const Seam s = layout_seam(share);
    return {left, theme::kPlateTop + 14, std::round(s.x_at(theme::kPlateTop + 14) - theme::kSeamGap - left),
            plate_bottom() - theme::kPlateTop - 28};
}
Rect SplitStage::blue_area(float share) const {
    const Seam s = layout_seam(share);
    const float left = std::round(s.x_at(plate_bottom()) + theme::kSeamGap),
                right = size_.x - theme::kPlateSide - theme::kPlatePad;
    return {left, theme::kPlateTop + 14, right - left, plate_bottom() - theme::kPlateTop - 28};
}

bool SplitStage::ambient_running(double now) const {
    return ambient_on_ && !reduced_ && !frozen_ && now - last_input_ < theme::motion::kAmbientIdlePause;
}

double SplitStage::next_ambient_time(double now) const {
    // (Asked with the time it is now: draw() makes an ambient frame only while ambient_running(now), so a frame due
    // after the pause began would be drawn without one, and asked for again and again.)
    if (!ambient_running(now)) return 1e18;
    return last_ambient_ + 1.0 / theme::motion::kAmbientHz;
}

void SplitStage::draw_fields(Canvas& canvas, double now) {
    const float W = size_.x, H = size_.y;
    const Seam s = seam_now();
    canvas.fill_rect({0, 0, W, H}, c::kBackground);
    // The fields fill their halves completely; colour lines run parallel to the seam (gradient axis at 12 deg).
    const Vec2 n{kCos12, kSin12};
    const Vec2 at{s.x_at(s.yc), s.yc};
    const float reach = 1150 * kCos12;
    const float li = bright_red_, ri = bright_blue_;
    auto boost = [](Color col, float m) { return col.with_alpha(std::min(1.f, col.a * m)); };
    const Vec2 red_pts[4] = {{-10, -10}, {s.x_at(-10), -10}, {s.x_at(H + 10), H + 10}, {-10, H + 10}};
    Gradient red;
    red.from = at - n * reach;
    red.to = at;
    red.stops[0] = {0, c::kFieldRedFar};
    red.stops[1] = {.6f, boost(c::kFieldRedMid, li)};
    red.stops[2] = {1, boost(c::kFieldRedSeam, li)};
    red.count = 3;
    canvas.fill(red_pts, red);
    const Vec2 blue_pts[4] = {{s.x_at(-10), -10}, {W + 10, -10}, {W + 10, H + 10}, {s.x_at(H + 10), H + 10}};
    Gradient blue;
    blue.from = at;
    blue.to = at + n * reach;
    blue.stops[0] = {0, boost(c::kFieldBlueSeam, ri)};
    blue.stops[1] = {.4f, boost(c::kFieldBlueMid, ri)};
    blue.stops[2] = {1, c::kFieldBlueFar};
    blue.count = 3;
    canvas.fill(blue_pts, blue);
    // Two drifting glows (still under Reduce motion / frozen; on the ambient clock: still while it is paused).
    (void)now;
    const double t = (reduced_ || frozen_) ? 0 : ambient_time_;
    canvas.radial({W * (150.f / 1280) + static_cast<float>(std::sin(t * .13)) * 40, H * (720.f / 800)}, 600,
                  rgba(230, 20, 60, .26f * li));
    canvas.radial({W * (1150.f / 1280) + static_cast<float>(std::cos(t * .11)) * 40, H * (80.f / 800)}, 600,
                  rgba(30, 90, 240, .28f * ri));
}

void SplitStage::render_ambient(Canvas& canvas, double, float dt) {
    const float W = size_.x, H = size_.y, scale = canvas.scale();
    const int pw = static_cast<int>(std::lround(W * scale)), ph = static_cast<int>(std::lround(H * scale));
    if (!layer_ || pw != layer_w_ || ph != layer_h_) {
        if (layer_) textures_.destroy(layer_);
        layer_ = textures_.create_target(pw, ph);
        layer_w_ = pw;
        layer_h_ = ph;
    }
    const Seam s = seam_now();
    const float li = bright_red_, ri = bright_blue_, lean = lean_.value;
    // Advance the moving parts.
    if (dt > 0) {
        for (Line& l : lines_) {
            l.y -= l.speed * dt;
            if (l.y + l.len < -20) l = new_line(false);
        }
        if (random_.uniform() < dt * theme::motion::kSparkRate)
            sparks_.push_back({(random_.uniform() < .5f ? -1.f : 1.f) * 0.f, random_.uniform() * H,
                               (random_.uniform() < .5f ? -1.f : 1.f) * (30 + random_.uniform() * 90),
                               -(30 + random_.uniform() * 80), 0, .8f + random_.uniform() * 1.2f});
        for (Spark& p : sparks_) {
            p.life += dt;
            p.x += p.vx * dt;
            p.y += p.vy * dt;
        }
        std::erase_if(sparks_, [](const Spark& p) { return p.life > p.max; });
    }
    canvas.begin_target(layer_, scale);
    // Halftone along the seam: dots shrink away from it and drift down.
    const float step = theme::motion::kHalftoneStep;
    const float phase = std::fmod(static_cast<float>(ambient_time_) * theme::motion::kHalftoneSpeed, step);
    for (int side : {-1, 1}) {
        const Color col =
            side < 0 ? rgba(255, 70, 110, std::min(1.f, .15f * li)) : rgba(90, 160, 255, std::min(1.f, .15f * ri));
        int column = 0;
        for (float gx = 6; gx < theme::motion::kHalftoneReach; gx += step, ++column) {
            const float r = theme::motion::kHalftoneDot * std::pow(1 - gx / theme::motion::kHalftoneReach, 1.5f);
            if (r < .45f) continue;
            for (float gy = -step + phase + (column % 2 ? step / 2 : 0); gy < H + step; gy += step) {
                const float x = s.x_at(gy) + static_cast<float>(side) * gx;
                // (The sprite's disc fills 30 of its 32 pixels.)
                const float rr = r * 32.f / 30;
                canvas.image(dot_, {x - rr, gy - rr, rr * 2, rr * 2}, col);
            }
        }
    }
    // Speed lines parallel to the seam.
    for (const Line& l : lines_) {
        const float fade = 1 - std::min(1.f, std::fabs(l.off) / theme::motion::kSpeedLineReach);
        const Color col = l.off < 0 ? rgba(255, 130, 160, std::min(1.f, l.alpha * fade * li))
                                    : rgba(150, 200, 255, std::min(1.f, l.alpha * fade * ri));
        const float y0 = l.y, y1 = l.y + l.len;
        const Vec2 q[4] = {{s.x_at(y0) + l.off, y0}, {s.x_at(y0) + l.off + l.width, y0},
                           {s.x_at(y1) + l.off + l.width, y1}, {s.x_at(y1) + l.off, y1}};
        canvas.fill(q, col);
    }
    // Sparks off the seam.
    for (const Spark& p : sparks_) {
        const float a = 1 - p.life / p.max;
        const float x = s.x_at(p.y) + lean + p.x;
        canvas.fill_rect({x, p.y, 2, 2}, p.x < 0 ? rgba(255, 130, 160, a) : rgba(160, 205, 255, a));
    }
    // The pulse running down the seam (content area only).
    if (!reduced_) {
        const float top = theme::kTopBand, bottom = H - theme::kBottomBand;
        const float py = std::fmod(static_cast<float>(ambient_time_) * theme::motion::kPulseSpeed, H + 600) - 300;
        const float y0 = std::max(top, py - 220), y1 = std::min(py, bottom);
        if (y1 > y0) {
            const Vec2 q[4] = {{s.x_at(y0) + lean - 3, y0}, {s.x_at(y0) + lean + 3, y0}, {s.x_at(y1) + lean + 3, y1},
                               {s.x_at(y1) + lean - 3, y1}};
            canvas.fill(q, Gradient::linear({0, py - 220}, {0, py}, rgba(255, 255, 255, 0), rgba(255, 255, 255, .95f)));
        }
    }
    canvas.end_target();
    layer_seam_ = s.c + lean;
    layer_generation_ = textures_.generation();
}

void SplitStage::draw_plates(Canvas& canvas) {
    const Seam s = seam_now();
    const float y0 = theme::kPlateTop, y1 = plate_bottom(), pl = theme::kPlateSide, pr = size_.x - theme::kPlateSide;
    const float g = theme::kGutter, li = bright_red_, ri = bright_blue_;
    const Vec2 crimson[4] = {{pl, y0}, {s.x_at(y0) - g, y0}, {s.x_at(y1) - g, y1}, {pl, y1}};
    const Vec2 blue[4] = {{s.x_at(y0) + g, y0}, {pr, y0}, {pr, y1}, {s.x_at(y1) + g, y1}};
    canvas.fill(crimson, Gradient::linear({pl, 0}, {s.x_at(s.yc) - g, 0}, c::kPlateRedOuter, c::kPlateRedSeam));
    canvas.stroke(crimson, 1, c::kPlateRedStroke);
    canvas.fill(blue, Gradient::linear({s.x_at(s.yc) + g, 0}, {pr, 0}, c::kPlateBlueSeam, c::kPlateBlueOuter));
    canvas.stroke(blue, 1, c::kPlateBlueStroke);
    // A locked half's plate: darker (its content fades with it, Box::locked).
    if (lock_ > 0 && lock_drawn_ != 0)
        canvas.fill(lock_drawn_ < 0 ? crimson : blue, rgba(6, 4, 12, theme::motion::kLockVeil * lock_));
    // Seam-facing edges and the top accents fading away from the seam.
    canvas.line({s.x_at(y0) - g, y0}, {s.x_at(y1) - g, y1}, 1.6f, c::kPlateRedEdge.faded(li));
    canvas.line({s.x_at(y0) + g, y0}, {s.x_at(y1) + g, y1}, 1.6f, c::kPlateBlueEdge.faded(ri));
    canvas.fill_rect({pl, y0, s.x_at(y0) - g - pl, 3},
                     Gradient::linear({pl, 0}, {s.x_at(y0) - g, 0}, rgba(255, 42, 85, 0),
                                      rgba(255, 42, 85, std::min(1.f, .85f * li))));
    canvas.fill_rect({s.x_at(y0) + g, y0, pr - s.x_at(y0) - g, 3},
                     Gradient::linear({s.x_at(y0) + g, 0}, {pr, 0}, rgba(45, 128, 255, std::min(1.f, .9f * ri)),
                                      rgba(45, 128, 255, 0)));
}

void SplitStage::draw_seam_and_bands(Canvas& canvas) {
    const float W = size_.x, H = size_.y, top = theme::kTopBand, bottom = H - theme::kBottomBand;
    const Seam s = seam_now();
    const float lean = lean_.value;
    auto lx = [&](float y) { return s.x_at(y) + lean; };
    // The seam's line in the gutter.
    const Vec2 line[4] = {
        {lx(top) - 1.2f, top}, {lx(top) + 1.2f, top}, {lx(bottom) + 1.2f, bottom}, {lx(bottom) - 1.2f, bottom}};
    canvas.fill(line, c::kSeamLine);
    // Neutral bands; the seam continues faintly behind them; hairlines at their inner edges.
    canvas.fill_rect({0, 0, W, top}, c::kBand);
    canvas.fill_rect({0, bottom, W, H - bottom}, c::kBand);
    const Vec2 faint_top[4] = {{lx(0) - 1, 0}, {lx(0) + 1, 0}, {lx(top) + 1, top}, {lx(top) - 1, top}};
    const Vec2 faint_bottom[4] = {{lx(bottom) - 1, bottom}, {lx(bottom) + 1, bottom}, {lx(H) + 1, H}, {lx(H) - 1, H}};
    canvas.fill(faint_top, c::kSeamFaint);
    canvas.fill(faint_bottom, c::kSeamFaint);
    for (float y : {top - 1, bottom}) {
        Gradient g;
        g.from = {0, 0};
        g.to = {W, 0};
        g.stops[0] = {0, rgba(255, 42, 85, .05f)};
        g.stops[1] = {std::clamp(lx(y) / W, .05f, .95f), rgba(255, 255, 255, .4f)};
        g.stops[2] = {1, rgba(45, 128, 255, .05f)};
        g.count = 3;
        canvas.fill_rect({0, y, W, 1}, g);
    }
}

void SplitStage::draw(Canvas& canvas, double now) {
    draw_fields(canvas, now);
    // The ambient layer: made again when due (<= kAmbientHz), when the seam moved, or when the renderer lost it.
    const Seam s = seam_now();
    const bool lost = !layer_ || layer_generation_ != textures_.generation() ||
                      layer_w_ != static_cast<int>(std::lround(size_.x * canvas.scale())) ||
                      layer_h_ != static_cast<int>(std::lround(size_.y * canvas.scale()));
    const bool moved = std::fabs(s.c + lean_.value - layer_seam_) > .25f;
    const bool due = ambient_running(now) && now >= last_ambient_ + 1.0 / theme::motion::kAmbientHz;
    if (lost || moved || due) {
        float dt = 0;
        if (due) {
            dt = last_ambient_ < -1e8 ? 0 : static_cast<float>(std::min(.1, now - last_ambient_));
            ambient_time_ = now;
            last_ambient_ = now;
        } else if (lost && last_ambient_ < -1e8) {
            ambient_time_ = now;  // (first frame / frozen tests: the clock's time)
            last_ambient_ = now;
        }
        render_ambient(canvas, now, dt);
    }
    canvas.image(layer_, {0, 0, size_.x, size_.y});
    // The seam's glow under the plates.
    {
        const float top = 0, bottom = size_.y, lean = lean_.value;
        auto lx = [&](float y) { return s.x_at(y) + lean; };
        const Vec2 n{kCos12, kSin12};
        const Vec2 at{lx(s.yc), s.yc};
        const Vec2 red[4] = {{lx(top) - 120, top}, {lx(top), top}, {lx(bottom), bottom}, {lx(bottom) - 120, bottom}};
        canvas.fill(red, Gradient::linear(at - n * (120 * kCos12), at, rgba(255, 42, 85, 0),
                                          rgba(255, 42, 85, std::min(1.f, .6f * bright_red_))));
        const Vec2 blue[4] = {{lx(top), top}, {lx(top) + 120, top}, {lx(bottom) + 120, bottom}, {lx(bottom), bottom}};
        canvas.fill(
            blue, Gradient::linear(at, at + n * (120 * kCos12), rgba(45, 128, 255, std::min(1.f, .65f * bright_blue_)),
                                   rgba(45, 128, 255, 0)));
    }
    draw_plates(canvas);
    draw_seam_and_bands(canvas);
}

// ---- wipe -----------------------------------------------------------------------------------------------------------

Wipe::~Wipe() {
    for (TextureId t : frames_)
        if (t) textures_.destroy(t);
}

void Wipe::begin_frame(Canvas& canvas, Vec2 size) {
    const int w = canvas.pixel_width(), h = canvas.pixel_height();
    if (w != w_ || h != h_) {
        for (TextureId& t : frames_) {
            if (t) textures_.destroy(t);
            t = textures_.create_target(w, h);
        }
        w_ = w;
        h_ = h;
        have_old_ = false;
    }
    size_ = size;
    canvas.begin_target(frames_[current_], canvas.scale());
    drawn_ = true;
}

void Wipe::start(double now, int dir, bool reduced) {
    // Reduce motion: a cut. (A cross-fade showed both screens at once, the seam of each where it was: user
    // 2026-11-24.)
    if (reduced) {
        start_ = -1;
        reduced_ = true;
        return;
    }
    if (!drawn_) return;
    current_ ^= 1;  // the last frame stays in the other target
    have_old_ = true;
    start_ = now;
    dir_ = dir >= 0 ? 1 : -1;
    reduced_ = false;
    duration_ = theme::motion::kWipe;
}

float Wipe::progress(double now) const {
    if (start_ < 0) return 1;
    return clamp01(static_cast<float>((now - start_) / duration_));
}

Vec2 Wipe::new_offset(double now) const {
    if (!active(now) || reduced_) return {};
    const float dy = static_cast<float>(dir_) * 36 * (1 - ease::in_out_cubic(progress(now)));
    return {-dy * theme::kSeamTan, dy};
}

void Wipe::end_frame(Canvas& canvas, double now) {
    canvas.end_target();
    const float W = size_.x;
    canvas.image(frames_[current_], {0, 0, size_.x, size_.y});
    // (A lost render target leaves nothing to show: the wipe is skipped.)
    if (!active(now) || !have_old_ || !textures_.get(frames_[current_ ^ 1])) return;
    const TextureId old = frames_[current_ ^ 1];
    const float e = ease::in_out_cubic(progress(now));
    const float y0 = top_, y1 = bottom_;
    auto uv = [&](Vec2 p) { return Vec2{p.x / size_.x, p.y / size_.y}; };
    // The reveal line: parallel to the seam, crossing the window (stage x of its top at y = 0: bx).
    const float bx = dir_ > 0 ? (W + 210) + (-W - 560) * e : -160 + (W + 560) * e;
    auto line_x = [&](float y) { return bx + 75 - y * theme::kSeamTan; };
    const float shift = -static_cast<float>(dir_) * 50 * e;
    std::vector<Vec2> pts;
    if (dir_ > 0) {  // old on the left of the line
        pts = {{-W, y0}, {line_x(y0), y0}, {line_x(y1), y1}, {-W, y1}};
    } else {
        pts = {{line_x(y0), y0}, {2 * W, y0}, {2 * W, y1}, {line_x(y1), y1}};
    }
    // Clipped to the window (the reveal line keeps its slant), then each point shows the old frame where it was
    // (moved by `shift`); UVs kept inside the texture (the edge column repeated, as a GPU's clamp would). Drawn in
    // strips 24 pixels tall: SDL's software renderer drops a textured triangle whose area times its texture
    // coordinates overflows an int (a whole window's half did: "triangle area overflow").
    const auto clip = [](const std::vector<Vec2>& in, bool on_x, float at, bool keep_above) {
        std::vector<Vec2> out;
        const auto v = [on_x](Vec2 p) { return on_x ? p.x : p.y; };
        for (std::size_t i = 0; i < in.size(); ++i) {
            const Vec2 a = in[i], b = in[(i + 1) % in.size()];
            const bool ia = keep_above ? v(a) >= at : v(a) <= at, ib = keep_above ? v(b) >= at : v(b) <= at;
            if (ia) out.push_back(a);
            if (ia != ib) {
                const float t = (at - v(a)) / (v(b) - v(a));
                out.push_back({a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t});
            }
        }
        return out;
    };
    pts = clip(clip(pts, true, 0, true), true, W, false);
    const float strip = 24 / std::max(.25f, canvas.scale());
    for (float a = y0; a < y1 && pts.size() >= 3; a += strip) {
        const std::vector<Vec2> part = clip(clip(pts, false, a, true), false, std::min(y1, a + strip), false);
        if (part.size() < 3) continue;
        std::vector<Vec2> uvs;
        for (const Vec2& p : part) uvs.push_back(uv({std::clamp(p.x - shift, 0.f, W - .5f), p.y}));
        canvas.textured(old, part, uvs, rgba(255, 255, 255, 1 - e * .5f));
    }
    // The band: red fading in, a white core, blue fading out (150 points wide), over the whole height.
    const float H = size_.y;
    auto band = [&](float a, float b, const Gradient& g) {
        const Vec2 q[4] = {
            {bx + a, 0}, {bx + b, 0}, {bx + b - H * theme::kSeamTan, H}, {bx + a - H * theme::kSeamTan, H}};
        canvas.fill(q, g);
    };
    band(0, 72, Gradient::linear({bx, 0}, {bx + 72, 0}, rgba(255, 42, 85, 0), theme::color::kRed));
    band(78, 150, Gradient::linear({bx + 78, 0}, {bx + 150, 0}, theme::color::kBlue, rgba(45, 128, 255, 0)));
    const Vec2 core[4] = {
        {bx + 70, 0}, {bx + 78, 0}, {bx + 78 - H * theme::kSeamTan, H}, {bx + 70 - H * theme::kSeamTan, H}};
    canvas.glow(core, 40, rgba(255, 255, 255, .45f));
    canvas.fill(core, rgba(255, 255, 255, 1));
}

}  // namespace ttt2::ui
