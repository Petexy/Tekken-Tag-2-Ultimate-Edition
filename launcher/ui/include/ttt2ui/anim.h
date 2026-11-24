// Time and motion: an injectable clock (tests use a fixed one), a seeded random source, springs and eased tweens.
#pragma once

#include <cstdint>

#include "ttt2ui/geometry.h"
#include "ttt2ui/theme.h"

namespace ttt2::ui {

// Seconds since some start. The real one reads SDL's tick counter; tests and screenshots use ManualClock.
class Clock {
public:
    virtual ~Clock() = default;
    virtual double now() const = 0;
};
class SystemClock final : public Clock {
public:
    double now() const override;
};
class ManualClock final : public Clock {
public:
    explicit ManualClock(double start = 0) : t_(start) {}
    double now() const override { return t_; }
    void advance(double seconds) { t_ += seconds; }
    void set(double t) { t_ = t; }

private:
    double t_;
};

// xorshift64*: the same numbers for the same seed on every platform (ambient particles in tests).
class Random {
public:
    explicit Random(std::uint64_t seed = 0x9e3779b97f4a7c15ull) : s_(seed ? seed : 1) {}
    std::uint64_t next() {
        s_ ^= s_ >> 12;
        s_ ^= s_ << 25;
        s_ ^= s_ >> 27;
        return s_ * 0x2545f4914f6cdd1dull;
    }
    float uniform() { return static_cast<float>(next() >> 40) / static_cast<float>(1ull << 24); }  // [0, 1)
    float range(float a, float b) { return a + (b - a) * uniform(); }

private:
    std::uint64_t s_;
};

// A damped spring toward a target, integrated in fixed sub-steps (the same result at any frame rate).
struct Spring {
    float value = 0, velocity = 0, target = 0;
    theme::SpringSpec spec{300, 1};

    Spring() = default;
    Spring(float v, theme::SpringSpec s) : value(v), target(v), spec(s) {}
    void step(float dt);
    void snap() {
        value = target;
        velocity = 0;
    }
    void snap_to(float v) {
        target = v;
        snap();
    }
    // At rest: within eps of the target and (nearly) not moving.
    bool settled(float eps = .01f) const;
    // Settle checks for springs whose value is a pixel-ish quantity vs a 0..1 quantity use different eps.
};

// Four springs that move a rectangle (the focus highlight).
struct RectSpring {
    Spring x, y, w, h;
    explicit RectSpring(theme::SpringSpec s = theme::motion::kFocus) : x(0, s), y(0, s), w(0, s), h(0, s) {}
    void set_target(const Rect& r) {
        x.target = r.x;
        y.target = r.y;
        w.target = r.w;
        h.target = r.h;
    }
    void snap_to(const Rect& r) {
        x.snap_to(r.x);
        y.snap_to(r.y);
        w.snap_to(r.w);
        h.snap_to(r.h);
    }
    void step(float dt) {
        x.step(dt);
        y.step(dt);
        w.step(dt);
        h.step(dt);
    }
    void kick(float vx) { x.velocity += vx; }
    bool settled(float eps = .05f) const { return x.settled(eps) && y.settled(eps) && w.settled(eps) && h.settled(eps); }
    Rect value() const { return {x.value, y.value, w.value, h.value}; }
    void set_spec(theme::SpringSpec s) { x.spec = y.spec = w.spec = h.spec = s; }
};

// Easing curves on t in [0, 1].
namespace ease {
float cubic_bezier(float x1, float y1, float x2, float y2, float t);  // like CSS cubic-bezier()
inline float out_expo_like(float t) { return cubic_bezier(.16f, 1, .3f, 1, t); }  // the mock's entry curve
float in_out_cubic(float t);
float in_cubic(float t);
float out_cubic(float t);
}  // namespace ease

// A timed value from 0 to 1 that started at `start` (seconds) and lasts `duration`, with a curve.
struct Tween {
    double start = -1;
    float duration = 0;
    float (*curve)(float) = nullptr;
    void begin(double now, float seconds, float (*c)(float) = nullptr) {
        start = now;
        duration = seconds;
        curve = c;
    }
    bool active(double now) const { return start >= 0 && now < start + duration; }
    bool started() const { return start >= 0; }
    float at(double now) const;  // 0 before it starts, 1 after it ends (or when never begun)
};

}  // namespace ttt2::ui
