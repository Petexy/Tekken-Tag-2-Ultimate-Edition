// The Tag Split stage behind every screen: two coloured fields split by a 12-degree seam, a dark plate in each half
// whose seam-facing edge keeps a fixed gutter from the seam, neutral top and bottom bands, and the ambient layer
// (halftone along the seam, speed lines, sparks, a pulse down the seam). The seam is one spring value (the split C)
// that every part follows; it leans toward the half that holds the focus.
//
// The ambient layer never counts as animation (U9): it is drawn at most theme::motion::kAmbientHz times a second
// into a cached render target, pauses after kAmbientIdlePause seconds without input, stops while the window is
// unfocused / occluded / minimised, and is still under Reduce motion. Tests freeze it (fixed clock, seeded random).
#pragma once

#include "ttt2ui/anim.h"
#include "ttt2ui/canvas.h"
#include "ttt2ui/ui.h"

namespace ttt2::ui {

class SplitStage {
public:
    explicit SplitStage(TextureRegistry& textures, std::uint64_t seed = 1);
    ~SplitStage();

    // Where the seam should go: `share` of the width (theme::split::*), tall plates (a task fills the screen),
    // which half has the focus (-1 crimson, 0 none, 1 blue).
    void set_target(float share, bool tall_plates, int focus_side);
    // A drill-in lock (FEEDBACK F4): that half's plate darkens (eased) while its content is locked (Box::locked);
    // -1 crimson, 1 blue, 0 none.
    void set_locked(int side) { lock_side_ = side; }
    void snap();
    // Advance (dt seconds), for a window of `size` points.
    void update(double now, float dt, Vec2 size, bool reduced_motion);
    bool animating() const { return animating_; }

    // The seam a screen is laid out for (its target split, no lean) and the one drawn now (springing).
    Seam layout_seam(float share) const;
    Seam seam_now() const;
    // The split as it is now (springing toward the target): lay the screen out for THIS every frame (with
    // crimson_area/blue_area(share_now())), so nothing ever crosses the seam drawn while it moves.
    float share_now() const { return c_.value; }
    float plate_top() const { return theme::kPlateTop; }
    float plate_bottom() const;
    float content_top() const { return theme::kTopBand; }
    float content_bottom() const { return size_.y - theme::kBottomBand; }
    // The rectangles content of each half may use (between the plate's outer edge and the window's middle; the
    // seam fit narrows them per row).
    Rect crimson_area(float share) const;
    Rect blue_area(float share) const;

    // Ambient motion: on while the window is focused and visible, the user was active recently, and motion is
    // not reduced. `frozen`: tests (drawn once at the clock's time, never moves).
    void set_ambient(bool focused_and_visible) { ambient_on_ = focused_and_visible; }
    void set_frozen(bool frozen) { frozen_ = frozen; }
    void note_input(double now) { last_input_ = now; }
    // The time the loop must wake for the next ambient frame, as it is `now` (infinity when none is due).
    double next_ambient_time(double now) const;
    // Whether ambient motion runs now (on, not reduced, not frozen, input in the last kAmbientIdlePause seconds):
    // decorative loops elsewhere (PaintContext::loop) move only while it does.
    bool ambient_running(double now) const;

    void draw(Canvas& canvas, double now);

private:
    void draw_fields(Canvas& canvas, double now);
    void draw_plates(Canvas& canvas);
    void draw_seam_and_bands(Canvas& canvas);
    void render_ambient(Canvas& canvas, double now, float dt);

    TextureRegistry& textures_;
    Random random_;
    Vec2 size_{theme::kStageWidth, theme::kStageHeight};
    float share_ = theme::split::kHome;
    bool tall_ = false;
    int side_ = 0;
    Spring c_{theme::split::kHome, theme::motion::kSeam};  // as a share of the width
    Spring bottom_{0, theme::motion::kPlateBottom};       // 0 = normal plates, 1 = tall
    Spring lean_{0, theme::motion::kLean};
    float bright_red_ = 1, bright_blue_ = 1;
    int lock_side_ = 0, lock_drawn_ = 0;  // (the side the veil is on: it fades out where it was)
    float lock_ = 0;
    bool reduced_ = false, animating_ = false;
    bool ambient_on_ = true, frozen_ = false;
    double last_input_ = 0, last_ambient_ = -1e9, ambient_time_ = 0;
    // ambient state
    struct Line {
        float off, y, len, speed, width, alpha;
    };
    std::vector<Line> lines_;
    struct Spark {
        float x, y, vx, vy, life, max;
    };
    std::vector<Spark> sparks_;
    TextureId layer_ = 0, dot_ = 0;
    int layer_w_ = 0, layer_h_ = 0;
    unsigned layer_generation_ = ~0u;
    float layer_seam_ = -1;
    Line new_line(bool initial);
};

// The diagonal wipe between screens: every frame is drawn into a render target; a switch keeps the last frame
// and, for theme::motion::kWipe seconds, draws it (textured geometry) over the part of the content area the new
// screen has not reached yet, behind a red-white-blue band parallel to the seam. Reduce motion: a short cross-fade.
class Wipe {
public:
    explicit Wipe(TextureRegistry& textures) : textures_(textures) {}
    ~Wipe();
    // Draw the frame into the current target (call before anything is drawn) ...
    void begin_frame(Canvas& canvas, Vec2 size);
    // ... then put it on the screen, with the old frame over the part not wiped yet.
    void end_frame(Canvas& canvas, double now);
    // A switch: `dir` 1 = the new screen comes from the right (a later tab), -1 from the left.
    void start(double now, int dir, bool reduced);
    bool active(double now) const { return start_ >= 0 && now < start_ + duration_; }
    // Where the new content is drawn during the wipe: it slides in ALONG the seam (parallel to it), so its distance
    // from the seam never changes and nothing enters the gutter.
    Vec2 new_offset(double now) const;
    // The content area wiped (stage points); the bands outside stay live.
    void set_area(float top, float bottom) {
        top_ = top;
        bottom_ = bottom;
    }

private:
    float progress(double now) const;
    TextureRegistry& textures_;
    TextureId frames_[2] = {0, 0};
    int current_ = 0;
    int w_ = 0, h_ = 0;
    Vec2 size_{};
    double start_ = -1;
    float duration_ = theme::motion::kWipe;
    int dir_ = 1;
    bool reduced_ = false, have_old_ = false, drawn_ = false;
    float top_ = theme::kTopBand, bottom_ = theme::kStageHeight - theme::kBottomBand;
};

}  // namespace ttt2::ui
