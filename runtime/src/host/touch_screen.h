#pragma once

// The GamePad's touch screen on a computer, its pure parts (tests/
// touch_screen_test.cpp): where the window shows the TV picture, a window
// point as a point of that picture, and the cursor a stick moves. The
// picture's points run 0 to 1 from its left and top edges, as
// os::TouchState's.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <optional>

namespace cafe::host::touch {

struct Rect {
    int32_t x = 0, y = 0, w = 0, h = 0;
};

struct Point {
    float x = 0.0f, y = 0.0f;
};

// The picture (image_w x image_h) in a swapchain of extent_w x extent_h:
// letterboxed to its aspect ratio, centred. A swapchain within 2 pixels of
// the picture shows it 1:1, centred, those pixels cut off or left black (a
// window of the render size can come out a pixel smaller at a fractional
// desktop scale; scaling by 0.999 would blur the whole picture).
inline Rect letterbox(int32_t extent_w, int32_t extent_h, int32_t image_w, int32_t image_h, bool* one_to_one = nullptr) {
    if (extent_w <= 0 || extent_h <= 0 || image_w <= 0 || image_h <= 0) return {};
    const bool same = std::abs(extent_w - image_w) <= 2 && std::abs(extent_h - image_h) <= 2;
    if (one_to_one) *one_to_one = same;
    const double scale = same ? 1.0 : std::min(double(extent_w) / image_w, double(extent_h) / image_h);
    const int32_t w = static_cast<int32_t>(image_w * scale), h = static_cast<int32_t>(image_h * scale);
    return {(extent_w - w) / 2, (extent_h - h) / 2, w, h};
}

// A point of the window (window_x, window_y in its pixels; the window
// window_w x window_h pixels) as a point of the picture shown at `rect` in
// a swapchain of extent_w x extent_h (the swapchain stretches over the
// window when their sizes differ for a moment, as while it is resized).
// Nothing outside the picture: the black bars beside it are no screen.
inline std::optional<Point> picture_point(float window_x, float window_y, float window_w, float window_h,
                                          int32_t extent_w, int32_t extent_h, Rect rect) {
    if (window_w <= 0.0f || window_h <= 0.0f || rect.w <= 0 || rect.h <= 0) return std::nullopt;
    const float ex = window_x * static_cast<float>(extent_w) / window_w;
    const float ey = window_y * static_cast<float>(extent_h) / window_h;
    const Point p{(ex - static_cast<float>(rect.x)) / static_cast<float>(rect.w),
                  (ey - static_cast<float>(rect.y)) / static_cast<float>(rect.h)};
    if (!(p.x >= 0.0f && p.x < 1.0f && p.y >= 0.0f && p.y < 1.0f)) return std::nullopt;
    return p;
}

// The cursor a stick moves over the picture (16:9): full deflection crosses
// the picture's height in kCrossing seconds, the same speed across it; the
// speed grows with the square of the deflection (fine strokes near the
// middle of the stick's travel; a long frame counts as 0.1 s at most). Up on
// the stick (positive y) is up on the picture. It stays on the picture.
constexpr float kCrossing = 1.25f;
constexpr float kAspect = 16.0f / 9.0f;
inline Point move_cursor(Point at, float stick_x, float stick_y, float seconds) {
    const float length = std::sqrt(stick_x * stick_x + stick_y * stick_y);
    if (!(length > 0.0f) || seconds <= 0.0f) return at;
    const float magnitude = std::min(length, 1.0f);
    const float step = magnitude * magnitude * std::min(seconds, 0.1f) / kCrossing; // in picture heights
    const float dx = stick_x / length * step / kAspect, dy = -stick_y / length * step;
    constexpr float kLast = 1.0f - 1.0f / 4096.0f; // inside: picture points run up to, not to, 1
    return {std::clamp(at.x + dx, 0.0f, kLast), std::clamp(at.y + dy, 0.0f, kLast)};
}

} // namespace cafe::host::touch
