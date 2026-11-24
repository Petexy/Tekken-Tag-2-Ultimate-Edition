// The GamePad's touch screen on a computer (host/touch_screen.h): where the
// window shows the picture, window points as points of the picture across
// window sizes, letterboxing and the desktop's scale, and the stick's cursor.

#include "host/touch_screen.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace {
using namespace cafe::host::touch;

int g_failures = 0;

void check(bool ok, const char* what) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", what);
        ++g_failures;
    }
}

bool near(float a, float b, float tolerance = 1e-4f) { return std::fabs(a - b) <= tolerance; }

bool same(Rect a, Rect b) { return a.x == b.x && a.y == b.y && a.w == b.w && a.h == b.h; }

void letterboxing() {
    bool one = true;
    // A 16:9 window of another size: scaled to fill it.
    check(same(letterbox(1920, 1080, 2560, 1440, &one), {0, 0, 1920, 1080}) && !one, "16:9 window, scaled");
    check(same(letterbox(3840, 2160, 1280, 720, &one), {0, 0, 3840, 2160}) && !one, "16:9 window, enlarged");
    // Wider: bars left and right. 2560x1080 (21:9) shows 1920x1080 in the middle.
    check(same(letterbox(2560, 1080, 2560, 1440), {320, 0, 1920, 1080}), "21:9 window, side bars");
    // Taller: bars above and below. 1920x1200 (16:10) shows 1920x1080 60 down.
    check(same(letterbox(1920, 1200, 1280, 720), {0, 60, 1920, 1080}), "16:10 window, bars above and below");
    // A Steam Deck's 1280x800, the picture rendered at 1280x720: 1:1 is not within 2 pixels (80 more rows).
    check(same(letterbox(1280, 800, 1280, 720, &one), {0, 40, 1280, 720}) && !one, "Steam Deck screen");
    // Within 2 pixels of the picture: 1:1, centred (a pixel cut off or left black).
    check(same(letterbox(2559, 1439, 2560, 1440, &one), {0, 0, 2560, 1440}) && one, "a pixel smaller: 1:1");
    check(same(letterbox(2562, 1442, 2560, 1440, &one), {1, 1, 2560, 1440}) && one, "two pixels larger: 1:1");
    check(same(letterbox(0, 720, 1280, 720), {}) && same(letterbox(1280, 720, 0, 0), {}), "no size, no picture");
}

void points() {
    // The window as large as the swapchain, the picture filling it: fractions of the window.
    Rect r = letterbox(1920, 1080, 2560, 1440);
    auto p = picture_point(960, 540, 1920, 1080, 1920, 1080, r);
    check(p && near(p->x, 0.5f) && near(p->y, 0.5f), "centre");
    p = picture_point(0, 0, 1920, 1080, 1920, 1080, r);
    check(p && near(p->x, 0.0f) && near(p->y, 0.0f), "top left corner");
    check(!picture_point(1920, 540, 1920, 1080, 1920, 1080, r), "the right edge is past the picture");
    p = picture_point(1919.5f, 1079.5f, 1920, 1080, 1920, 1080, r);
    check(p && p->x < 1.0f && p->y < 1.0f && p->x > 0.999f, "last pixel's centre inside");

    // Side bars (21:9): a point on a bar touches nothing; the picture's own points scale by its width.
    r = letterbox(2560, 1080, 2560, 1440);
    check(!picture_point(100, 540, 2560, 1080, 2560, 1080, r), "on the left bar");
    check(!picture_point(2500, 540, 2560, 1080, 2560, 1080, r), "on the right bar");
    p = picture_point(320 + 480, 270, 2560, 1080, 2560, 1080, r);
    check(p && near(p->x, 0.25f) && near(p->y, 0.25f), "a quarter in, past the bar");

    // Bars above and below (16:10).
    r = letterbox(1920, 1200, 1280, 720);
    check(!picture_point(960, 30, 1920, 1200, 1920, 1200, r), "on the top bar");
    p = picture_point(960, 60 + 810, 1920, 1200, 1920, 1200, r);
    check(p && near(p->x, 0.5f) && near(p->y, 0.75f), "three quarters down, below the bar");

    // The swapchain larger than the window for a moment (resizing): the window's points stretch onto it.
    r = letterbox(2560, 1440, 2560, 1440);
    p = picture_point(640, 360, 1280, 720, 2560, 1440, r);
    check(p && near(p->x, 0.5f) && near(p->y, 0.5f), "swapchain twice the window");

    // A desktop scale of 150 %: the window's pixels are its points x 1.5 (the host converts first); a
    // 1280x720 window in points is 1920x1080 pixels, the picture rendered at 2560x1440.
    r = letterbox(1920, 1080, 2560, 1440);
    p = picture_point(400 * 1.5f, 300 * 1.5f, 1920, 1080, 1920, 1080, r);
    check(p && near(p->x, 400.0f / 1280.0f) && near(p->y, 300.0f / 720.0f), "150 % desktop scale");

    // 1:1 within a pixel: the picture's point under the window's pixel.
    r = letterbox(2562, 1442, 2560, 1440);
    p = picture_point(1, 1, 2562, 1442, 2562, 1442, r);
    check(p && near(p->x, 0.0f) && near(p->y, 0.0f), "1:1 offset by a pixel");
    check(!picture_point(0.5f, 0.5f, 2562, 1442, 2562, 1442, r), "the black pixel beside a 1:1 picture");

    check(!picture_point(10, 10, 0, 0, 1920, 1080, letterbox(1920, 1080, 1280, 720)), "a window with no size");
}

void cursor() {
    const Point centre{0.5f, 0.5f};
    // Still: no stick, or no time.
    Point c = move_cursor(centre, 0.0f, 0.0f, 0.5f);
    check(near(c.x, 0.5f) && near(c.y, 0.5f), "no deflection, no move");
    c = move_cursor(centre, 1.0f, 0.0f, 0.0f);
    check(near(c.x, 0.5f), "no time, no move");
    // Full deflection up for 0.1 s: a tenth of kCrossing's picture heights, upwards.
    c = move_cursor(centre, 0.0f, 1.0f, 0.1f);
    check(near(c.y, 0.5f - 0.1f / kCrossing) && near(c.x, 0.5f), "up moves up");
    // Across: the same speed in pixels, so a smaller share of the wider picture.
    c = move_cursor(centre, 1.0f, 0.0f, 0.1f);
    check(near(c.x, 0.5f + 0.1f / kCrossing / kAspect) && near(c.y, 0.5f), "right moves right, as fast in pixels");
    // Half deflection: a quarter of the speed (fine strokes).
    c = move_cursor(centre, 0.0f, -0.5f, 0.1f);
    check(near(c.y, 0.5f + 0.25f * 0.1f / kCrossing), "half deflection, a quarter of the speed");
    // Diagonal at full deflection: no faster than straight.
    c = move_cursor(centre, 1.0f, 1.0f, 0.1f);
    const float dx = (c.x - 0.5f) * kAspect, dy = 0.5f - c.y;
    check(near(std::sqrt(dx * dx + dy * dy), 0.1f / kCrossing), "diagonal as fast as straight");
    // A long stall counts as a tenth of a second at most.
    c = move_cursor(centre, 0.0f, 1.0f, 3.0f);
    check(near(c.y, 0.5f - 0.1f / kCrossing), "a stall moves no further than 0.1 s");
    // It stays on the picture, inside its last point.
    c = centre;
    for (int i = 0; i < 100; ++i) c = move_cursor(c, -1.0f, 1.0f, 0.1f);
    check(near(c.x, 0.0f) && near(c.y, 0.0f), "stops at the top left corner");
    for (int i = 0; i < 100; ++i) c = move_cursor(c, 1.0f, -1.0f, 0.1f);
    check(c.x < 1.0f && c.y < 1.0f && c.x > 0.999f && c.y > 0.999f, "stops inside the bottom right corner");
    // Deflections beyond the stick's range count as full.
    c = move_cursor(centre, 0.0f, 3.0f, 0.1f);
    check(near(c.y, 0.5f - 0.1f / kCrossing), "clamped deflection");
}

} // namespace

int main() {
    letterboxing();
    points();
    cursor();
    if (g_failures) return EXIT_FAILURE;
    std::printf("touch screen: ok\n");
    return EXIT_SUCCESS;
}
