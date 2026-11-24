#pragma once

// Pictures drawn over the title's image, not by the title: rectangles of
// an RGBA atlas (or plain colour), tinted top to bottom, in the TV image's
// coordinates (1280 x 720, whatever the render size). The renderer draws
// them over every image it shows, extra frames too, after the title's
// frame; nothing reaches guest memory. Set from any thread
// (title/framedata.cpp: Practice's frame data panels).

#include <cstdint>
#include <memory>
#include <vector>

namespace cafe::gpu::overlay {

constexpr float kWidth = 1280, kHeight = 720;

struct Quad {
    float x0 = 0, y0 = 0, x1 = 0, y1 = 0; // in the TV image's pixels
    float u0 = 0, v0 = 0, u1 = 0, v1 = 0; // in the atlas, 0 to 1
    uint32_t top = 0, bottom = 0;         // colours, 0xRRGGBBAA, multiplying the atlas
    uint32_t add = 0;                     // 0xRRGGBB added after (a Flash colour transform's); its
                                          // alpha 0xFF: blended additively (a Flash "add" blend)
};

struct Atlas {
    uint32_t width = 0, height = 0;
    std::vector<uint8_t> pixels; // RGBA, rows top first
};

// Solids in the title's world (millimetres), drawn under the quads as the
// title's camera sees them, shaded: capsules round the segment a-b (a
// sphere: both ends the same). The others show only their surfaces nearest
// the camera; those in front show through everything.
struct Solid {
    float a[3] = {}, b[3] = {};
    float radius = 0;
    uint32_t colour = 0; // 0xRRGGBBAA
    bool in_front = false;
};

struct Scene {
    float view_projection[16] = {}; // the title's: clip = (x, y, z, 1) x M, row-major, clip y up
    std::vector<Solid> solids;
};

// A window onto the scene from another camera: the title's frame rendered
// again with its camera's matrix (`from`, as the title holds it) replaced
// by `to`, the part `crop` of that image (in the TV image's pixels) shown
// at `rect`, over the quads; the scene's solids drawn in it too, through
// `view_projection` (the one `to` and the crop make).
struct Window {
    float from[16] = {}, to[16] = {}, view_projection[16] = {};
    float rect[4] = {}, crop[4] = {};
};

// The atlas the quads sample (set once; a new one replaces it).
void set_atlas(std::shared_ptr<const Atlas> atlas);
// The quads (and solids, and window) drawn for the next `seconds` (unless
// shown again); none hides the overlay.
void show(std::vector<Quad> quads, double seconds, std::shared_ptr<const Scene> scene = nullptr,
          std::shared_ptr<const Window> window = nullptr);

// The HUD layer: quads of their own atlas, drawn under the others (and
// apart from them: title/gauge.cpp's gauges of added fighters, in any
// mode, while Practice's panels come and go).
void set_hud_atlas(std::shared_ptr<const Atlas> atlas);
void show_hud(std::vector<Quad> quads, double seconds);

// The pointer layer: quads of their own atlas, drawn over everything else
// (title/paint.cpp's cursor for the GamePad's touch screen).
void set_pointer_atlas(std::shared_ptr<const Atlas> atlas);
void show_pointer(std::vector<Quad> quads, double seconds);

// For the renderer.
struct State {
    std::shared_ptr<const Atlas> atlas;
    std::shared_ptr<const std::vector<Quad>> quads; // null: nothing to draw
    std::shared_ptr<const Scene> scene;             // null: no solids
    std::shared_ptr<const Window> window;           // null: none
    std::shared_ptr<const Atlas> hud_atlas;
    std::shared_ptr<const std::vector<Quad>> hud_quads; // null: nothing to draw
    std::shared_ptr<const Atlas> pointer_atlas;
    std::shared_ptr<const std::vector<Quad>> pointer_quads; // null: nothing to draw
};
State current(); // the quads, solids and window only while they are to be drawn
// The windows shown lately, newest first: the frame the renderer renders
// again may be one or two older than the newest, its camera matrix theirs.
std::vector<std::shared_ptr<const Window>> recent_windows();
// Counts the windows shown: the renderer draws the window's view again only
// for a new one (not for frames the fighters' frame did not run in, such as
// the pause menu's first, which takes its picture of the scene).
uint64_t window_generation();

} // namespace cafe::gpu::overlay
