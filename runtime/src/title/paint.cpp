// CUSTOMIZE > PAINT without a Wii U GamePad (title/paint.h).

#include "title/paint.h"

#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "gpu/gpu.h"
#include "gpu/overlay.h"
#include "host/window.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <optional>

namespace cafe::title {
namespace {

// The customize manager: **0x107A71EC (the Xtal natives' object). Its
// realtime paint object (manager + 0x6A7D8: getRealtimePaintStatus
// sub_023101B4 -> sub_02A9CDCC -> sub_0250373C; begin/endRealtimePaint
// sub_02503A78 / sub_02503AB8) holds the mode's state at +60: 0 none, 1 not
// painting (CUSTOMIZE's menus), 4 PAINT's first dialog, 5 the paint screen,
// 8 a moment as the camera tool is left (the paint position is taken), 7
// the thumbnail shot and its questions after B, then 1 again. At +68 the
// toolbar's row: 0 pen, 1 eraser, 2 history, 3 camera (PAINT POSITION, where
// a touch paints nothing and the right stick turns the camera).
constexpr uint32_t kCustomize = 0x107A71EC;
constexpr uint32_t kPaintObject = 0x6A7D8;
constexpr uint32_t kState = 60, kTool = 68;
constexpr uint32_t kPaintScreen = 5, kPositionTaken = 8, kCameraTool = 3;
// The strokes are drawn on the GPU into 256 x 256 RGBA8 targets (256 KiB),
// which the title reads with the CPU to keep them on the model and save
// them: they must reach guest memory while the mode is open (from PAINT's
// first question to the thumbnail shot), or the strokes vanish when the
// paint screen closes.
constexpr uint32_t kPaintTileBytes = 256 * 256 * 4;

std::optional<uint32_t> load(uint32_t address) {
    if (address == 0 || !guest_memory_committed(address, 4)) return std::nullopt;
    return ppc::ld32(guest_base(), address);
}

const auto g_start = std::chrono::steady_clock::now(); // (TTT2_TRACE_PAINT's times)

// The realtime paint object, if there is one.
std::optional<uint32_t> paint_object() {
    const std::optional<uint32_t> holder = load(kCustomize);
    const std::optional<uint32_t> manager = holder ? load(*holder) : std::nullopt;
    const std::optional<uint32_t> paint = manager && *manager ? load(*manager + kPaintObject) : std::nullopt;
    if (!paint || *paint == 0) return std::nullopt;
    return paint;
}

// ------------------------------------------------------------ the cursor

// The stick's cursor: a ring with a dark edge and a dot (a filled disc while
// it touches), drawn over the picture, its centre the point it touches.
constexpr int kSprite = 64;    // pixels of each of the atlas's two pictures
constexpr float kCursor = 40;  // its size on the picture (1280 x 720)

std::shared_ptr<const gpu::overlay::Atlas> cursor_atlas() {
    auto atlas = std::make_shared<gpu::overlay::Atlas>();
    atlas->width = kSprite * 2;
    atlas->height = kSprite;
    atlas->pixels.assign(size_t{atlas->width} * atlas->height * 4, 0);
    const float c = kSprite / 2.0f;
    const auto coverage = [](float d, float inner, float outer) { // of the band inner..outer at distance d
        return std::clamp(std::min(d - inner, outer - d) + 0.5f, 0.0f, 1.0f);
    };
    for (int sprite = 0; sprite < 2; ++sprite) {
        for (int y = 0; y < kSprite; ++y) {
            for (int x = 0; x < kSprite; ++x) {
                const float d = std::hypot(x + 0.5f - c, y + 0.5f - c);
                const float edge = coverage(d, 17.0f, 29.0f);                      // dark edge of the ring
                const float ring = coverage(d, 20.0f, 26.0f);                      // the ring
                const float dot = sprite ? coverage(d, -1.0f, 14.0f) : coverage(d, -1.0f, 3.0f);
                const float dot_edge = sprite ? coverage(d, -1.0f, 16.0f) : coverage(d, -1.0f, 5.0f);
                const float light = std::max(ring, dot), alpha = std::max({edge * 0.6f, dot_edge * 0.6f, light});
                const float r = sprite ? 0.35f : 1.0f, g = sprite ? 0.9f : 1.0f; // touching: cyan
                uint8_t* px = &atlas->pixels[(size_t{static_cast<size_t>(y)} * atlas->width + sprite * kSprite + x) * 4];
                const float shade = alpha > 0.0f ? light / alpha : 0.0f;
                px[0] = static_cast<uint8_t>(255.0f * r * shade);
                px[1] = static_cast<uint8_t>(255.0f * g * shade);
                px[2] = static_cast<uint8_t>(255.0f * shade);
                px[3] = static_cast<uint8_t>(255.0f * alpha);
            }
        }
    }
    return atlas;
}

void draw_cursor() {
    static bool drawn = false;
    const std::optional<host::TouchCursor> cursor = host::touch_cursor();
    if (!cursor) {
        if (drawn) gpu::overlay::show_pointer({}, 0.0);
        drawn = false;
        return;
    }
    if (!drawn) {
        static const bool atlas_set = [] {
            gpu::overlay::set_pointer_atlas(cursor_atlas());
            return true;
        }();
        (void)atlas_set;
    }
    drawn = true;
    const float x = cursor->x * gpu::overlay::kWidth, y = cursor->y * gpu::overlay::kHeight, h = kCursor / 2;
    const float u0 = cursor->touching ? 0.5f : 0.0f;
    gpu::overlay::show_pointer({{x - h, y - h, x + h, y + h, u0, 0.0f, u0 + 0.5f, 1.0f, 0xFFFFFFFF, 0xFFFFFFFF}}, 0.25);
}

// On the window's thread.
host::TouchScreen touch_screen() {
    const std::optional<uint32_t> paint = paint_object();
    const std::optional<uint32_t> state = paint ? load(*paint + kState) : std::nullopt;
    const std::optional<uint32_t> tool = paint ? load(*paint + kTool) : std::nullopt;
    // TTT2_TRACE_PAINT=1: the state and the tool as they change, with the
    // seconds since start-up (as TTT2_CAPTURE_START counts).
    static const bool trace = std::getenv("TTT2_TRACE_PAINT") != nullptr;
    static std::optional<uint32_t> traced_state, traced_tool;
    if (trace && (state != traced_state || tool != traced_tool)) {
        const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_start).count();
        std::fprintf(stderr, "ttt2: paint: %.2f s: state %d, tool %d\n", t, state ? static_cast<int>(*state) : -1,
                     tool ? static_cast<int>(*tool) : -1);
        traced_state = state;
        traced_tool = tool;
    }
    draw_cursor();
    const bool open = state && *state > 1; // 0 none, 1 CUSTOMIZE's menus
    static bool reading = false;
    if (open != reading) gpu::set_cpu_read_targets(open ? kPaintTileBytes : 0);
    reading = open;
    if (state != kPaintScreen && state != kPositionTaken) return host::TouchScreen::kOff;
    return tool == kCameraTool ? host::TouchScreen::kMouse : host::TouchScreen::kCursor;
}

} // namespace

void prepare_paint() { host::on_touch_screen(touch_screen); }

} // namespace cafe::title
