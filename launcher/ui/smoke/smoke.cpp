// launcher_smoke: one frame of the new launcher's interface made the way the launcher makes its frames, as a check
// that it is built and linked right (SDL 3, the fonts and icons built into it, stb_truetype, nanosvg,
// stb_image_write) on Linux and Windows. Not something players start.
//
//   launcher_smoke [--size WxH]                    a borderless window (drag it by its top strip; Esc, F11, X)
//   launcher_smoke --screenshot FILE [--size WxH]  the frame drawn offscreen by the software renderer, checked
//                                                  (text, icon and shapes where they belong, anti-aliased edges)
//                                                  and written as a PNG; exit 3 when a check fails
//   launcher_smoke --version                       "launcher_smoke <version>", before anything of SDL
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#endif

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>  // (SDL_MAIN_HANDLED: only for SDL_SetMainReady)
#include <nanosvg.h>
#include <nanosvgrast.h>
#include <stb_image_write.h>
#include <stb_truetype.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

#include "ttt2_launcher_fonts.h"
#include "ttt2_launcher_icons.h"

namespace {

constexpr int kDesignWidth = 1280, kDesignHeight = 800;
constexpr float kStrip = 40;     // the drag strip's height
constexpr float kCloseWidth = 52;
constexpr float kEdge = 6;       // where the window is resized

void say(std::string_view text, bool error = false) {
#ifdef _WIN32
    // (A Windows GUI program: its standard handles are what its starter gave it, or none.)
    HANDLE out = GetStdHandle(error ? STD_ERROR_HANDLE : STD_OUTPUT_HANDLE);
    DWORD written = 0;
    if (out && out != INVALID_HANDLE_VALUE) WriteFile(out, text.data(), static_cast<DWORD>(text.size()), &written, nullptr);
#else
    std::fwrite(text.data(), 1, text.size(), error ? stderr : stdout);
    std::fflush(error ? stderr : stdout);
#endif
}

struct Color { float r, g, b, a; };
constexpr Color rgb(unsigned hex, float a = 1) {
    return {((hex >> 16) & 255) / 255.f, ((hex >> 8) & 255) / 255.f, (hex & 255) / 255.f, a};
}
constexpr Color kBackground = rgb(0x0d0f16), kBlueSide = rgb(0x0b1d44), kCrimson = rgb(0xd0202a),
                kStripColor = rgb(0x161a26), kWhite = rgb(0xffffff), kFaint = rgb(0x8b93a8);

struct Point { float x, y; };

// Shapes as SDL_RenderGeometry triangles, in physical pixels, with a one-pixel feather ring for anti-aliasing.
class Shapes {
public:
    void convex(const std::vector<Point>& points, Color inner_color, Color outer_color) {
        const std::size_t n = points.size();
        float area = 0;
        for (std::size_t i = 0; i < n; ++i)
            area += points[i].x * points[(i + 1) % n].y - points[(i + 1) % n].x * points[i].y;
        const float side = area > 0 ? 1.f : -1.f;  // which way is out
        const int base = static_cast<int>(vertices_.size());
        auto normal = [&](Point a, Point b) {
            float dx = b.x - a.x, dy = b.y - a.y, length = std::sqrt(dx * dx + dy * dy);
            return Point{side * dy / length, -side * dx / length};
        };
        for (std::size_t i = 0; i < n; ++i) {
            Point p = points[i], before = normal(points[(i + n - 1) % n], p), after = normal(p, points[(i + 1) % n]);
            Point miter{before.x + after.x, before.y + after.y};
            float length = std::sqrt(miter.x * miter.x + miter.y * miter.y);
            miter = {miter.x / length, miter.y / length};
            float reach = 0.5f / std::max(0.2f, miter.x * before.x + miter.y * before.y);
            add({p.x - miter.x * reach, p.y - miter.y * reach}, inner_color);
            add({p.x + miter.x * reach, p.y + miter.y * reach}, {outer_color.r, outer_color.g, outer_color.b, 0});
        }
        for (std::size_t i = 1; i + 1 < n; ++i) triangle(base, base + 2 * static_cast<int>(i), base + 2 * static_cast<int>(i + 1));
        for (std::size_t i = 0; i < n; ++i) {
            int a = base + 2 * static_cast<int>(i), b = base + 2 * static_cast<int>((i + 1) % n);
            triangle(a, a + 1, b + 1);
            triangle(a, b + 1, b);
        }
    }
    void convex(const std::vector<Point>& points, Color color) { convex(points, color, color); }
    void draw(SDL_Renderer* renderer) {
        if (!indices_.empty())
            SDL_RenderGeometry(renderer, nullptr, vertices_.data(), static_cast<int>(vertices_.size()), indices_.data(),
                               static_cast<int>(indices_.size()));
        vertices_.clear();
        indices_.clear();
    }

private:
    void add(Point p, Color c) { vertices_.push_back({{p.x, p.y}, {c.r, c.g, c.b, c.a}, {0, 0}}); }
    void triangle(int a, int b, int c) { indices_.insert(indices_.end(), {a, b, c}); }
    std::vector<SDL_Vertex> vertices_;
    std::vector<int> indices_;
};

// Text: one face at one pixel size, its printable ASCII packed into an atlas with 2x horizontal oversampling.
struct Face {
    const unsigned char* data = nullptr;
    stbtt_fontinfo info{};
    float pixels = 0, scale = 0, ascent = 0;
    stbtt_packedchar chars[95]{};
};

class Text {
public:
    bool build(SDL_Renderer* renderer, float density) {
        static const struct { const char* file; float size; } kFaces[] = {
            {"BarlowCondensed/BarlowCondensed-ExtraBoldItalic.ttf", 76},  // 0: the big title
            {"BarlowCondensed/BarlowCondensed-ExtraBoldItalic.ttf", 19},  // 1: the strip's title
            {"BarlowCondensed/BarlowCondensed-BlackItalic.ttf", 30},      // 2: the blue side's heading
            {"Barlow/Barlow-Medium.ttf", 15},                             // 3: body text
            {"JetBrainsMono/JetBrainsMono-Regular.ttf", 14},              // 4: paths, versions
        };
        faces_.clear();
        int width = 1024, height = 1024;
        if (density > 1.5f) width = height = 2048;
        std::vector<unsigned char> coverage(static_cast<std::size_t>(width) * height);
        stbtt_pack_context pack;
        if (!stbtt_PackBegin(&pack, coverage.data(), width, height, 0, 1, nullptr)) return fail("cannot pack glyphs");
        stbtt_PackSetOversampling(&pack, 2, 1);
        for (const auto& wanted : kFaces) {
            const ttt2_fonts::File* file = ttt2_fonts::find(wanted.file);
            if (!file) return fail(std::string("no font ") + wanted.file);
            Face face;
            face.data = file->data;
            if (!stbtt_InitFont(&face.info, face.data, stbtt_GetFontOffsetForIndex(face.data, 0)))
                return fail(std::string("cannot read ") + wanted.file);
            face.pixels = wanted.size * density;
            face.scale = stbtt_ScaleForMappingEmToPixels(&face.info, face.pixels);
            int ascent, descent, gap;
            stbtt_GetFontVMetrics(&face.info, &ascent, &descent, &gap);
            face.ascent = ascent * face.scale;
            if (!stbtt_PackFontRange(&pack, face.data, 0, STBTT_POINT_SIZE(face.pixels), 32, 95, face.chars))
                return fail(std::string("the atlas is too small for ") + wanted.file);
            faces_.push_back(face);
        }
        stbtt_PackEnd(&pack);
        std::vector<unsigned char> rgba(coverage.size() * 4);
        for (std::size_t i = 0; i < coverage.size(); ++i) {
            rgba[i * 4] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = 255;
            rgba[i * 4 + 3] = coverage[i];
        }
        if (texture_) SDL_DestroyTexture(texture_);
        texture_ = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, width, height);
        if (!texture_ || !SDL_UpdateTexture(texture_, nullptr, rgba.data(), width * 4)) return fail(SDL_GetError());
        SDL_SetTextureBlendMode(texture_, SDL_BLENDMODE_BLEND);
        SDL_SetTextureScaleMode(texture_, SDL_SCALEMODE_LINEAR);
        width_ = width;
        height_ = height;
        return true;
    }
    // Text in face `which`, its top-left at (x, y) (physical pixels); its width.
    float add(int which, std::string_view text, float x, float y, Color color, float tracking = 0) {
        const Face& face = faces_[static_cast<std::size_t>(which)];
        const float start = x, baseline = std::round(y + face.ascent);
        int previous = 0;
        for (unsigned char c : text) {
            int code = c >= 32 && c < 127 ? c : '?';
            if (previous) x += face.scale * stbtt_GetCodepointKernAdvance(&face.info, previous, code);
            stbtt_aligned_quad q;
            float pen_y = baseline;
            stbtt_GetPackedQuad(face.chars, width_, height_, code - 32, &x, &pen_y, &q, 0);
            const int base = static_cast<int>(vertices_.size());
            const SDL_FColor fc{color.r, color.g, color.b, color.a};
            vertices_.push_back({{q.x0, q.y0}, fc, {q.s0, q.t0}});
            vertices_.push_back({{q.x1, q.y0}, fc, {q.s1, q.t0}});
            vertices_.push_back({{q.x1, q.y1}, fc, {q.s1, q.t1}});
            vertices_.push_back({{q.x0, q.y1}, fc, {q.s0, q.t1}});
            indices_.insert(indices_.end(), {base, base + 1, base + 2, base, base + 2, base + 3});
            x += tracking;
            previous = code;
        }
        return x - start;
    }
    void draw(SDL_Renderer* renderer) {
        if (!indices_.empty())
            SDL_RenderGeometry(renderer, texture_, vertices_.data(), static_cast<int>(vertices_.size()),
                               indices_.data(), static_cast<int>(indices_.size()));
        vertices_.clear();
        indices_.clear();
    }
    // (Before its renderer goes.)
    void release() {
        if (texture_) SDL_DestroyTexture(texture_);
        texture_ = nullptr;
    }
    std::string error;

private:
    bool fail(std::string why) {
        error = std::move(why);
        return false;
    }
    std::vector<Face> faces_;
    SDL_Texture* texture_ = nullptr;
    int width_ = 0, height_ = 0;
    std::vector<SDL_Vertex> vertices_;
    std::vector<int> indices_;
};

// An SVG of the launcher's (built in) drawn by nanosvg at `size` physical pixels, as a texture.
SDL_Texture* icon_texture(SDL_Renderer* renderer, const char* path, int size, std::string& error) {
    const ttt2_icons::File* file = ttt2_icons::find(path);
    if (!file) {
        error = std::string("no icon ") + path;
        return nullptr;
    }
    std::string text(reinterpret_cast<const char*>(file->data), file->size);  // (nsvgParse writes into it)
    NSVGimage* image = nsvgParse(text.data(), "px", 96);
    if (!image || image->width <= 0) {
        if (image) nsvgDelete(image);
        error = std::string("cannot read ") + path;
        return nullptr;
    }
    NSVGrasterizer* rasterizer = nsvgCreateRasterizer();
    std::vector<unsigned char> pixels(static_cast<std::size_t>(size) * size * 4);
    nsvgRasterize(rasterizer, image, 0, 0, size / std::max(image->width, image->height), pixels.data(), size, size,
                  size * 4);
    nsvgDeleteRasterizer(rasterizer);
    nsvgDelete(image);
    SDL_Texture* texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, size, size);
    if (!texture || !SDL_UpdateTexture(texture, nullptr, pixels.data(), size * 4)) {
        error = SDL_GetError();
        return nullptr;
    }
    SDL_SetTextureBlendMode(texture, SDL_BLENDMODE_BLEND);
    return texture;
}

struct Frame {
    SDL_Window* window = nullptr;
    SDL_Renderer* renderer = nullptr;
    Text text;
    SDL_Texture* icon = nullptr;
    float density = 0;
    std::string error;

    bool prepare() {
        float now = SDL_GetWindowPixelDensity(window);
        if (now <= 0) now = 1;
        if (now == density && icon) return true;
        density = now;
        if (!text.build(renderer, density)) {
            error = text.error;
            return false;
        }
        if (icon) SDL_DestroyTexture(icon);
        icon = icon_texture(renderer, "icons/ttt2-input-face_bottom.svg", static_cast<int>(std::lround(168 * density)),
                            error);
        return icon != nullptr;
    }

    // The frame: design units (1280x800 at density 1) times the density.
    void draw() {
        int w = 0, h = 0;
        SDL_GetWindowSizeInPixels(window, &w, &h);
        const float s = density, W = static_cast<float>(w), H = static_cast<float>(h);
        Shapes shapes;
        SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
        SDL_SetRenderDrawColorFloat(renderer, kBackground.r, kBackground.g, kBackground.b, 1);
        SDL_RenderClear(renderer);
        // The blue side, past a slanted seam (Tag Split: the list on the left, the focused item on the right).
        const float seam = W * 0.58f;
        shapes.convex({{seam, kStrip * s}, {W + 2, kStrip * s}, {W + 2, H + 2}, {seam - 120 * s, H + 2}}, kBlueSide);
        shapes.convex({{seam - 3 * s, kStrip * s}, {seam + 3 * s, kStrip * s}, {seam - 117 * s, H + 2},
                       {seam - 123 * s, H + 2}}, kCrimson);
        // The drag strip, its close button's cross.
        shapes.convex({{0, 0}, {W, 0}, {W, kStrip * s}, {0, kStrip * s}}, kStripColor);
        const float cx = W - kCloseWidth * s / 2, cy = kStrip * s / 2, r = 7 * s, t = 1.1f * s;
        shapes.convex({{cx - r - t, cy - r + t}, {cx - r + t, cy - r - t}, {cx + r + t, cy + r - t},
                       {cx + r - t, cy + r + t}}, kFaint);
        shapes.convex({{cx + r - t, cy - r - t}, {cx + r + t, cy - r + t}, {cx - r + t, cy + r + t},
                       {cx - r - t, cy + r - t}}, kFaint);
        // A menu item's parallelogram, and a thinner one beside it.
        shapes.convex({{64 * s, 300 * s}, {504 * s, 300 * s}, {464 * s, 400 * s}, {24 * s, 400 * s}}, kCrimson);
        shapes.convex({{528 * s, 300 * s}, {556 * s, 300 * s}, {516 * s, 400 * s}, {488 * s, 400 * s}},
                      rgb(0xff4136, 0.85f));
        shapes.draw(renderer);

        text.add(1, "ULTIMATE LAUNCHER", 16 * s, 10 * s, kWhite, 1.5f * s);
        text.add(0, "TAG SPLIT SMOKE", 64 * s, 118 * s, kWhite);
        text.add(3, "Barlow Condensed ExtraBold Italic, drawn from an stb_truetype atlas.", 66 * s, 222 * s, kFaint);
        text.add(0, "PLAY", 92 * s, 307 * s, kWhite);
        char line[160];
        const int version = SDL_GetVersion();
        const char* renderer_name = SDL_GetRendererName(renderer);
        std::snprintf(line, sizeof line, "launcher_smoke %s - SDL %d.%d.%d, %s renderer", TTT2_LAUNCHER_VERSION,
                      SDL_VERSIONNUM_MAJOR(version), SDL_VERSIONNUM_MINOR(version), SDL_VERSIONNUM_MICRO(version),
                      renderer_name ? renderer_name : "no");
        text.add(4, line, 66 * s, 440 * s, kFaint);
        text.add(2, "FACE BUTTON", (seam / s + 40) * s, 92 * s, kWhite);
        text.draw(renderer);

        SDL_FRect where{(seam / s + 60) * s, 150 * s, 168 * s, 168 * s};
        SDL_RenderTexture(renderer, icon, nullptr, &where);
    }
};

// Where the window is dragged and resized from (window coordinates: logical points).
SDL_HitTestResult SDLCALL hit_test(SDL_Window* window, const SDL_Point* area, void*) {
    int w = 0, h = 0;
    SDL_GetWindowSize(window, &w, &h);
    const bool fullscreen = (SDL_GetWindowFlags(window) & SDL_WINDOW_FULLSCREEN) != 0;
    if (!fullscreen) {
        const bool left = area->x < kEdge, right = area->x >= w - kEdge, top = area->y < kEdge,
                   bottom = area->y >= h - kEdge;
        if (top && left) return SDL_HITTEST_RESIZE_TOPLEFT;
        if (top && right) return SDL_HITTEST_RESIZE_TOPRIGHT;
        if (bottom && left) return SDL_HITTEST_RESIZE_BOTTOMLEFT;
        if (bottom && right) return SDL_HITTEST_RESIZE_BOTTOMRIGHT;
        if (top) return SDL_HITTEST_RESIZE_TOP;
        if (bottom) return SDL_HITTEST_RESIZE_BOTTOM;
        if (left) return SDL_HITTEST_RESIZE_LEFT;
        if (right) return SDL_HITTEST_RESIZE_RIGHT;
    }
    if (area->y < kStrip && area->x < w - kCloseWidth) return SDL_HITTEST_DRAGGABLE;
    return SDL_HITTEST_NORMAL;
}

// The screenshot's checks: what each part of the frame must have put there (design coordinates at density 1).
int check(const SDL_Surface* image) {
    auto pixel = [&](int x, int y) {
        const auto* row = static_cast<const unsigned char*>(image->pixels) + static_cast<std::size_t>(y) * image->pitch;
        return row + x * 4;
    };
    auto count = [&](int x0, int y0, int x1, int y1, auto&& wanted) {
        int n = 0;
        for (int y = std::max(0, y0); y < std::min(image->h, y1); ++y)
            for (int x = std::max(0, x0); x < std::min(image->w, x1); ++x) n += wanted(pixel(x, y)) ? 1 : 0;
        return n;
    };
    auto near = [](const unsigned char* p, Color c, int tolerance) {
        return std::abs(p[0] - static_cast<int>(std::lround(c.r * 255))) <= tolerance &&
               std::abs(p[1] - static_cast<int>(std::lround(c.g * 255))) <= tolerance &&
               std::abs(p[2] - static_cast<int>(std::lround(c.b * 255))) <= tolerance;
    };
    auto white = [](const unsigned char* p) { return p[0] > 200 && p[1] > 200 && p[2] > 200; };
    struct Check { const char* what; int found, needed; };
    const float seam = image->w * 0.58f;
    const int icon_x = static_cast<int>(seam + 60);
    const Check checks[] = {
        {"title text (white pixels)", count(64, 118, 760, 210, white), 4000},
        {"strip text (white pixels)", count(10, 4, 260, 38, white), 150},
        {"icon's red button", count(icon_x, 150, icon_x + 168, 318,
                                    [](const unsigned char* p) { return p[0] > 170 && p[1] < 120 && p[2] < 110; }),
         400},
        {"icon's light buttons", count(icon_x, 150, icon_x + 168, 318,
                                       [](const unsigned char* p) {
                                           return p[0] > 170 && p[1] > 170 && p[2] > 170;
                                       }),
         400},
        {"parallelogram fill", count(120, 330, 400, 370, [&](const unsigned char* p) { return near(p, kCrimson, 2); }),
         6000},
        // Its slanted edges: pixels between the background's colour and the fill's (one per row and edge at least).
        {"anti-aliased edges",
         count(20, 302, 70, 398, [&](const unsigned char* p) {
             return !near(p, kCrimson, 6) && !near(p, kBackground, 6) && p[0] > 20 && p[0] < 200;
         }),
         80},
    };
    int failed = 0;
    for (const Check& c : checks) {
        char line[200];
        std::snprintf(line, sizeof line, "%s %s: %d (at least %d)\n", c.found >= c.needed ? "ok  " : "FAIL", c.what,
                      c.found, c.needed);
        say(line, c.found < c.needed);
        failed += c.found < c.needed;
    }
    return failed;
}

int usage(bool error) {
    say("usage: launcher_smoke [--screenshot FILE] [--size WxH] | --version\n", error);
    return error ? 2 : 0;
}

int run(const std::vector<std::string>& args) {
    // (First of all, and without SDL: what an update asks a new launcher before it switches to it.)
    if (!args.empty() && args[0] == "--version") {
        say("launcher_smoke " TTT2_LAUNCHER_VERSION "\n");
        return 0;
    }
    std::string screenshot;
    int width = kDesignWidth, height = kDesignHeight;
    for (std::size_t i = 0; i < args.size(); ++i) {
        if (args[i] == "-h" || args[i] == "--help") return usage(false);
        if (args[i] == "--screenshot" && i + 1 < args.size()) {
            screenshot = args[++i];
        } else if (args[i] == "--size" && i + 1 < args.size()) {
            if (std::sscanf(args[++i].c_str(), "%dx%d", &width, &height) != 2 || width < 320 || height < 240)
                return usage(true);
        } else {
            say("launcher_smoke: unknown option " + args[i] + "\n", true);
            return usage(true);
        }
    }

    SDL_SetMainReady();
    SDL_SetAppMetadata("Ultimate Launcher smoke test", TTT2_LAUNCHER_VERSION, TTT2_LAUNCHER_APP_ID ".Smoke");
    SDL_SetHint(SDL_HINT_VIDEO_ALLOW_SCREENSAVER, "1");
    if (!screenshot.empty()) {
        // Tests: no screen, no GPU.
        SDL_SetHint(SDL_HINT_VIDEO_DRIVER, "offscreen");
        SDL_SetHint(SDL_HINT_RENDER_DRIVER, "software");
    }
    if (!SDL_Init(SDL_INIT_VIDEO)) {
        say(std::string("launcher_smoke: SDL cannot start: ") + SDL_GetError() + "\n", true);
        return 1;
    }
    Frame frame;
    SDL_WindowFlags flags = SDL_WINDOW_BORDERLESS | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY |
                            SDL_WINDOW_HIDDEN;
    frame.window = SDL_CreateWindow("Ultimate Launcher", width, height, flags);
    if (frame.window) frame.renderer = SDL_CreateRenderer(frame.window, screenshot.empty() ? nullptr : "software");
    if (!frame.window || !frame.renderer) {
        say(std::string("launcher_smoke: no window: ") + SDL_GetError() + "\n", true);
        SDL_Quit();
        return 1;
    }
    SDL_SetRenderVSync(frame.renderer, 1);
    SDL_SetWindowMinimumSize(frame.window, 960, 600);
    SDL_SetWindowHitTest(frame.window, hit_test, nullptr);
    int result = 0;
    if (!frame.prepare()) {
        say("launcher_smoke: " + frame.error + "\n", true);
        result = 1;
    } else if (!screenshot.empty()) {
        frame.draw();
        SDL_Surface* read = SDL_RenderReadPixels(frame.renderer, nullptr);
        SDL_Surface* image = read ? SDL_ConvertSurface(read, SDL_PIXELFORMAT_RGBA32) : nullptr;
        if (!image) {
            say(std::string("launcher_smoke: cannot read the frame: ") + SDL_GetError() + "\n", true);
            result = 1;
        } else {
            if (check(image)) result = 3;
            if (!stbi_write_png(screenshot.c_str(), image->w, image->h, 4, image->pixels, image->pitch)) {
                say("launcher_smoke: cannot write " + screenshot + "\n", true);
                result = 1;
            }
        }
        SDL_DestroySurface(image);
        SDL_DestroySurface(read);
    } else {
        bool shown = false, running = true, dirty = true;
        while (running) {
            if (dirty) {
                if (!frame.prepare()) {
                    say("launcher_smoke: " + frame.error + "\n", true);
                    result = 1;
                    break;
                }
                frame.draw();
                SDL_RenderPresent(frame.renderer);
                dirty = false;
                if (!shown) SDL_ShowWindow(frame.window);  // (after its first frame: never an empty window)
                shown = true;
            }
            SDL_Event event;
            if (!SDL_WaitEventTimeout(&event, 1000)) continue;
            switch (event.type) {
            case SDL_EVENT_QUIT:
            case SDL_EVENT_WINDOW_CLOSE_REQUESTED:
                running = false;
                break;
            case SDL_EVENT_KEY_DOWN:
                if (event.key.key == SDLK_ESCAPE) running = false;
                if (event.key.key == SDLK_F11)
                    SDL_SetWindowFullscreen(frame.window,
                                            (SDL_GetWindowFlags(frame.window) & SDL_WINDOW_FULLSCREEN) == 0);
                break;
            case SDL_EVENT_MOUSE_BUTTON_UP: {
                int w = 0, h = 0;
                SDL_GetWindowSize(frame.window, &w, &h);
                if (event.button.y < kStrip && event.button.x >= w - kCloseWidth) running = false;
                break;
            }
            case SDL_EVENT_WINDOW_EXPOSED:
            case SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED:
            case SDL_EVENT_WINDOW_DISPLAY_SCALE_CHANGED:
                dirty = true;
                break;
            default:
                break;
            }
        }
    }
    if (frame.icon) SDL_DestroyTexture(frame.icon);
    frame.text.release();
    SDL_DestroyRenderer(frame.renderer);
    SDL_DestroyWindow(frame.window);
    SDL_Quit();
    return result;
}

}  // namespace

#ifdef _WIN32
int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    int argc = 0;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    std::vector<std::string> args;
    for (int i = 1; argv && i < argc; ++i) {
        int n = WideCharToMultiByte(CP_UTF8, 0, argv[i], -1, nullptr, 0, nullptr, nullptr);
        std::string arg(n > 0 ? static_cast<std::size_t>(n - 1) : 0, '\0');
        if (n > 1) WideCharToMultiByte(CP_UTF8, 0, argv[i], -1, arg.data(), n, nullptr, nullptr);
        args.push_back(std::move(arg));
    }
    if (argv) LocalFree(argv);
    return run(args);
}
#else
int main(int argc, char** argv) {
    return run(std::vector<std::string>(argv + 1, argv + argc));
}
#endif
