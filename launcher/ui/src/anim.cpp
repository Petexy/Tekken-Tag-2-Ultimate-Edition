#include "ttt2ui/anim.h"

#include <SDL3/SDL_timer.h>

#include <cmath>

namespace ttt2::ui {

double SystemClock::now() const { return static_cast<double>(SDL_GetTicksNS()) / 1e9; }

void Spring::step(float dt) {
    if (dt <= 0) return;
    // (Long gaps - a window that was hidden - are not replayed: the spring arrives.)
    if (dt > .25f) {
        snap();
        return;
    }
    const float k = spec.stiffness, c = 2 * std::sqrt(k) * spec.ratio;
    int n = static_cast<int>(std::ceil(dt / theme::motion::kSpringStep));
    const float h = dt / static_cast<float>(n);
    while (n--) {
        // Semi-implicit Euler (velocity first): stable for these stiffnesses at 240 Hz.
        const float a = -k * (value - target) - c * velocity;
        velocity += a * h;
        value += velocity * h;
    }
    if (settled()) snap();
}

bool Spring::settled(float eps) const { return std::fabs(value - target) < eps && std::fabs(velocity) < eps * 10; }

namespace ease {

float cubic_bezier(float x1, float y1, float x2, float y2, float t) {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    // x(s) = t solved for s with Newton steps then bisection; y(s) is the answer.
    auto bx = [&](float s) { return 3 * (1 - s) * (1 - s) * s * x1 + 3 * (1 - s) * s * s * x2 + s * s * s; };
    auto by = [&](float s) { return 3 * (1 - s) * (1 - s) * s * y1 + 3 * (1 - s) * s * s * y2 + s * s * s; };
    auto dx = [&](float s) {
        return 3 * (1 - s) * (1 - s) * x1 + 6 * (1 - s) * s * (x2 - x1) + 3 * s * s * (1 - x2);
    };
    float s = t;
    for (int i = 0; i < 8; ++i) {
        const float e = bx(s) - t, d = dx(s);
        if (std::fabs(e) < 1e-5f) return by(s);
        if (std::fabs(d) < 1e-6f) break;
        s -= e / d;
    }
    float lo = 0, hi = 1;
    s = t;
    for (int i = 0; i < 30; ++i) {
        const float x = bx(s);
        if (std::fabs(x - t) < 1e-5f) break;
        (x < t ? lo : hi) = s;
        s = (lo + hi) / 2;
    }
    return by(s);
}

float in_out_cubic(float t) {
    t = clamp01(t);
    return t < .5f ? 4 * t * t * t : 1 - std::pow(-2 * t + 2, 3.f) / 2;
}
float in_cubic(float t) {
    t = clamp01(t);
    return t * t * t;
}
float out_cubic(float t) {
    t = clamp01(t);
    return 1 - std::pow(1 - t, 3.f);
}

}  // namespace ease

float Tween::at(double now) const {
    if (start < 0 || duration <= 0) return 1;
    if (now <= start) return 0;
    const float t = clamp01(static_cast<float>((now - start) / duration));
    return curve ? curve(t) : t;
}

}  // namespace ttt2::ui
