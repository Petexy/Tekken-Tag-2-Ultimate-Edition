#include "ttt2ui/window.h"

#include <stb_image_write.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "ttt2ui/icons.h"
#include "ttt2ui/theme.h"

namespace ttt2::ui {

namespace {
// The launcher's icon on its window (Wayland's toplevel icon, X11's _NET_WM_ICON, Windows' title bar and task bar):
// 256 pixels with smaller sizes beside it, so a desktop that asks for 16 or 32 gets one drawn for that size.
void set_window_icon(SDL_Window* window) {
    std::vector<std::vector<std::uint8_t>> pixels;  // (kept until the icon is set: the surfaces point into them)
    SDL_Surface* main = nullptr;
    for (const int size : {256, 128, 64, 48, 32, 24, 16}) {
        std::vector<std::uint8_t>& rgba = pixels.emplace_back(rasterise_icon(kLauncherIcon, size));
        if (rgba.empty()) break;
        SDL_Surface* s = SDL_CreateSurfaceFrom(size, size, SDL_PIXELFORMAT_RGBA32, rgba.data(), size * 4);
        if (!s) break;
        if (!main) {
            main = s;
            continue;
        }
        SDL_AddSurfaceAlternateImage(main, s);
        SDL_DestroySurface(s);  // (the main surface holds its own reference)
    }
    if (!main) return;
    SDL_SetWindowIcon(window, main);
    SDL_DestroySurface(main);
}
}  // namespace

bool running_under_gamescope() {
    auto is = [](const char* name, const char* value) {
        const char* v = std::getenv(name);
        return v && (!value || std::strcmp(v, value) == 0);
    };
    const char* desktop = std::getenv("XDG_CURRENT_DESKTOP");
    return is("SteamDeck", "1") || is("SteamOS", "1") || (desktop && std::strstr(desktop, "gamescope")) ||
           (std::getenv("GAMESCOPE_WAYLAND_DISPLAY") != nullptr);
}

float ui_scale(Vec2 pixels, float display, float user_text_scale) {
    if (display <= 0) display = 1;
    const float stage = std::min(pixels.x / display / theme::kStageWidth, pixels.y / display / theme::kStageHeight);
    const float base = display * std::clamp(stage, 1.f, 2.f);
    const float want = base * std::max(.5f, user_text_scale);
    if (user_text_scale <= 1) return want;
    // (Larger text leaves fewer points for the layout: never fewer than the Steam Deck's at 150 %, which every
    // screen is laid out for. A smaller window keeps the text that much smaller, never smaller than without it.)
    const float most = std::min(pixels.x / theme::kTextLayoutWidth, pixels.y / theme::kTextLayoutHeight);
    return std::max(base, std::min(want, most));
}

Window::~Window() {
    close_pads();
    if (renderer_) SDL_DestroyRenderer(renderer_);
    if (window_) SDL_DestroyWindow(window_);
    if (window_ || renderer_) SDL_Quit();
}

bool Window::try_open(const WindowOptions& o, const char* video, const char* render, std::string& why) {
    // (A driver of its own overrides the player's SDL_VIDEO_DRIVER / SDL_VIDEODRIVER, which a hint of normal priority
    // does not: the other driver is tried also when they named one that fails. None: as they asked.)
    if (video) SDL_SetHintWithPriority(SDL_HINT_VIDEO_DRIVER, video, SDL_HINT_OVERRIDE);
    else SDL_ResetHint(SDL_HINT_VIDEO_DRIVER);
    if (!SDL_InitSubSystem(SDL_INIT_VIDEO)) {
        why = SDL_GetError();
        return false;
    }
    gamescope_ = !o.offscreen && running_under_gamescope();
    float content = 1;
    if (!o.offscreen) {
        content = SDL_GetDisplayContentScale(SDL_GetPrimaryDisplay());
        if (content <= 0) content = 1;
    }
    int w = static_cast<int>(std::lround(o.size.x * content)), h = static_cast<int>(std::lround(o.size.y * content));
    SDL_Rect usable;
    if (!o.offscreen && SDL_GetDisplayUsableBounds(SDL_GetPrimaryDisplay(), &usable)) {
        w = std::min(w, std::max(320, usable.w - 32));
        h = std::min(h, std::max(240, usable.h - 32));
    }
    SDL_WindowFlags flags =
        SDL_WINDOW_BORDERLESS | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY | SDL_WINDOW_HIDDEN;
    if (gamescope_ || o.start_fullscreen) flags |= SDL_WINDOW_FULLSCREEN;
    window_ = SDL_CreateWindow(o.title.c_str(), w, h, flags);
    if (!window_) {
        why = SDL_GetError();
        SDL_QuitSubSystem(SDL_INIT_VIDEO);
        return false;
    }
    renderer_ = SDL_CreateRenderer(window_, render);
    if (!renderer_) {
        why = SDL_GetError();
        SDL_DestroyWindow(window_);
        window_ = nullptr;
        SDL_QuitSubSystem(SDL_INIT_VIDEO);
        return false;
    }
    SDL_SetRenderVSync(renderer_, 1);
    SDL_SetWindowMinimumSize(window_, static_cast<int>(std::lround(o.min_size.x * content)),
                             static_cast<int>(std::lround(o.min_size.y * content)));
    SDL_SetWindowHitTest(window_, hit_test, this);
    if (!o.offscreen) set_window_icon(window_);
    return true;
}

bool Window::open(const WindowOptions& o) {
    if (!o.app_id.empty()) {
        SDL_SetHint(SDL_HINT_APP_ID, o.app_id.c_str());
        SDL_SetAppMetadata(o.title.c_str(), o.version.empty() ? nullptr : o.version.c_str(), o.app_id.c_str());
    }
    SDL_SetHint(SDL_HINT_VIDEO_ALLOW_SCREENSAVER, "1");
    SDL_SetHint(SDL_HINT_AUTO_UPDATE_JOYSTICKS, "0");
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "0");
    forced_scale_ = o.forced_scale;
    std::string why, first;
    bool ok = false;
    if (o.offscreen) {
        ok = try_open(o, "offscreen", "software", why);
        first = why;
    } else {
        // The default driver (or the one the player named) and renderer; the other video driver; the software
        // renderer with each.
        ok = try_open(o, nullptr, nullptr, why);
        first = why;
#ifndef _WIN32
        const char* other = nullptr;
        if (!ok) {
            const char* named = std::getenv("SDL_VIDEO_DRIVER");
            if (!named || !*named) named = std::getenv("SDL_VIDEODRIVER"); // (SDL 2's name, which SDL 3 reads too)
            const bool wayland = named && *named ? std::strncmp(named, "wayland", 7) == 0
                                                 : std::getenv("WAYLAND_DISPLAY") != nullptr;
            other = wayland ? "x11" : "wayland";
            ok = try_open(o, other, nullptr, why);
        }
#endif
        if (!ok) ok = try_open(o, nullptr, "software", why);
#ifndef _WIN32
        if (!ok && other) ok = try_open(o, other, "software", why);
#endif
    }
    if (!ok) {
        error_ = first.empty() ? why : first;
        const std::string text = "Golden Fist Launcher cannot open its window (" + error_ +
                                 ").\n\nThe newest launcher is at " + o.releases_url +
                                 (o.no_window ? o.no_window() : std::string());
        std::fprintf(stderr, "%s\n", text.c_str());
        if (!o.offscreen && !o.quiet) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, o.title.c_str(), text.c_str(), nullptr);
        return false;
    }
    update_scale();
    return true;
}

std::string Window::renderer_name() const {
    const char* n = renderer_ ? SDL_GetRendererName(renderer_) : nullptr;
    return n ? n : "";
}
std::string Window::video_driver() const {
    const char* n = SDL_GetCurrentVideoDriver();
    return n ? n : "";
}

Vec2 Window::pixels() const {
    int w = 0, h = 0;
    if (window_) SDL_GetWindowSizeInPixels(window_, &w, &h);
    return {static_cast<float>(w), static_cast<float>(h)};
}

Vec2 Window::points() const {
    const Vec2 p = pixels();
    return {p.x / scale_, p.y / scale_};
}

void Window::update_scale() {
    if (forced_scale_ > 0) {
        scale_ = forced_scale_;
        return;
    }
    float display = window_ ? SDL_GetWindowDisplayScale(window_) : 1;
    scale_ = ui_scale(pixels(), display, user_scale_);
}

bool Window::fullscreen() const { return window_ && (SDL_GetWindowFlags(window_) & SDL_WINDOW_FULLSCREEN); }
void Window::set_fullscreen(bool on) {
    if (window_ && !gamescope_) SDL_SetWindowFullscreen(window_, on);
}
void Window::minimise() {
    if (window_ && !gamescope_) SDL_MinimizeWindow(window_);
}
void Window::show() {
    if (window_ && !shown_) {
        SDL_ShowWindow(window_);
        shown_ = true;
    }
}

SDL_HitTestResult SDLCALL Window::hit_test(SDL_Window* window, const SDL_Point* area, void* data) {
    auto* self = static_cast<Window*>(data);
    int w = 0, h = 0;
    SDL_GetWindowSize(window, &w, &h);
    const bool full = (SDL_GetWindowFlags(window) & SDL_WINDOW_FULLSCREEN) != 0;
    if (self->gamescope_) return SDL_HITTEST_NORMAL;
    const int edge = static_cast<int>(theme::metric::kResizeEdge);
    if (!full) {
        const bool left = area->x < edge, right = area->x >= w - edge, top = area->y < edge,
                   bottom = area->y >= h - edge;
        if (top && left) return SDL_HITTEST_RESIZE_TOPLEFT;
        if (top && right) return SDL_HITTEST_RESIZE_TOPRIGHT;
        if (bottom && left) return SDL_HITTEST_RESIZE_BOTTOMLEFT;
        if (bottom && right) return SDL_HITTEST_RESIZE_BOTTOMRIGHT;
        if (top) return SDL_HITTEST_RESIZE_TOP;
        if (bottom) return SDL_HITTEST_RESIZE_BOTTOM;
        if (left) return SDL_HITTEST_RESIZE_LEFT;
        if (right) return SDL_HITTEST_RESIZE_RIGHT;
    }
    // Window coordinates -> interface points.
    const float density = SDL_GetWindowPixelDensity(window);
    const Vec2 p{static_cast<float>(area->x) * density / self->scale_,
                 static_cast<float>(area->y) * density / self->scale_};
    for (const Rect& b : self->buttons_)
        if (b.contains(p)) return SDL_HITTEST_NORMAL;
    if (!full && self->drag_.contains(p)) return SDL_HITTEST_DRAGGABLE;
    return SDL_HITTEST_NORMAL;
}

Glyphs Window::pad_kind(SDL_JoystickID id) const {
    switch (SDL_GetGamepadTypeForID(id)) {
    case SDL_GAMEPAD_TYPE_PS3:
    case SDL_GAMEPAD_TYPE_PS4:
    case SDL_GAMEPAD_TYPE_PS5:
        return Glyphs::PlayStation;
    case SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_PRO:
    case SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_LEFT:
    case SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_RIGHT:
    case SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_PAIR:
        return Glyphs::Nintendo;
    case SDL_GAMEPAD_TYPE_XBOX360:
    case SDL_GAMEPAD_TYPE_XBOXONE:
        return Glyphs::Xbox;
    default:
        return Glyphs::Generic;
    }
}

void Window::open_pads() {
    int count = 0;
    SDL_JoystickID* ids = SDL_GetGamepads(&count);
    for (int i = 0; ids && i < count; ++i)
        if (SDL_Gamepad* g = SDL_OpenGamepad(ids[i])) pads_.push_back({ids[i], g, pad_kind(ids[i])});
    SDL_free(ids);
}

void Window::close_pads() {
    for (Pad& p : pads_) SDL_CloseGamepad(p.pad);
    pads_.clear();
}

void Window::pads_tick(double now, bool game_running) {
    game_running_ = game_running;
    const bool want = focused_ && visible_ && !game_running && now - focus_since_ >= theme::input::kPadInitDelay;
    if (want && !pads_on_ && !pads_failed_) {
        if (SDL_InitSubSystem(SDL_INIT_GAMEPAD)) {
            pads_on_ = true;
            open_pads();
        } else {
            pads_failed_ = true;  // (tried again when the focus comes back)
        }
    } else if (!want && pads_on_) {
        close_pads();
        SDL_QuitSubSystem(SDL_INIT_GAMEPAD);
        pads_on_ = false;
    }
    if (pads_on_ && now >= next_pad_poll()) {
        SDL_UpdateJoysticks();
        last_poll_ = now;
    }
}

double Window::next_pad_poll() const {
    if (pads_on_) return last_poll_ + (pads_.empty() ? .5 : theme::input::kPadPollInterval);
    // (When they are opened: not while the game runs, nor after they could not be.)
    if (focused_ && visible_ && !game_running_ && !pads_failed_) return focus_since_ + theme::input::kPadInitDelay;
    return 1e18;
}

bool Window::translate(const SDL_Event& e, RawEvent& out, double now) {
    out = RawEvent{};
    out.time = now;
    const float density = window_ ? SDL_GetWindowPixelDensity(window_) : 1;
    auto to_points = [&](float x, float y) { return Vec2{x * density / scale_, y * density / scale_}; };
    switch (e.type) {
    case SDL_EVENT_WINDOW_FOCUS_GAINED:
        // (The first one usually comes after the start, which already counted as focused: the pads stay open.)
        if (!focused_) focus_since_ = now;
        focused_ = true;
        pads_failed_ = false;
        return false;
    case SDL_EVENT_WINDOW_FOCUS_LOST:
        focused_ = false;
        return false;
    case SDL_EVENT_WINDOW_MINIMIZED:
    case SDL_EVENT_WINDOW_HIDDEN:
    case SDL_EVENT_WINDOW_OCCLUDED:
        visible_ = false;
        return false;
    case SDL_EVENT_WINDOW_RESTORED:
    case SDL_EVENT_WINDOW_SHOWN:
    case SDL_EVENT_WINDOW_EXPOSED:
    case SDL_EVENT_WINDOW_MAXIMIZED:
        visible_ = true;
        return false;
    case SDL_EVENT_WINDOW_DISPLAY_SCALE_CHANGED:
    case SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED:
    case SDL_EVENT_WINDOW_RESIZED:
        update_scale();
        return false;
    case SDL_EVENT_KEY_DOWN:
    case SDL_EVENT_KEY_UP: {
        out.kind = e.type == SDL_EVENT_KEY_DOWN ? RawEvent::KeyDown : RawEvent::KeyUp;
        out.device = Device::Keyboard;
        out.device_id = e.key.which;
        out.code = e.key.scancode;
        out.os_repeat = e.key.repeat;
        out.shift = (e.key.mod & SDL_KMOD_SHIFT) != 0;
        out.ctrl = (e.key.mod & SDL_KMOD_CTRL) != 0;
        out.alt = (e.key.mod & SDL_KMOD_ALT) != 0;
        out.gui = (e.key.mod & SDL_KMOD_GUI) != 0;
        // Keys typed by a Steam Controller / Deck in desktop mode (where SDL knows the keyboard's name: X11,
        // Windows raw input). Elsewhere the router's same-press rule catches them.
        if (const char* name = e.key.which ? SDL_GetKeyboardNameForID(e.key.which) : nullptr)
            out.filtered = std::strstr(name, "Steam Controller") || std::strstr(name, "Steam Deck") ||
                           std::strstr(name, "Valve Software");
        return true;
    }
    case SDL_EVENT_GAMEPAD_ADDED:
        if (pads_on_ && !std::any_of(pads_.begin(), pads_.end(), [&](const Pad& p) { return p.id == e.gdevice.which; }))
            if (SDL_Gamepad* g = SDL_OpenGamepad(e.gdevice.which))
                pads_.push_back({e.gdevice.which, g, pad_kind(e.gdevice.which)});
        return false;
    case SDL_EVENT_GAMEPAD_REMOVED:
        for (auto it = pads_.begin(); it != pads_.end(); ++it)
            if (it->id == e.gdevice.which) {
                SDL_CloseGamepad(it->pad);
                pads_.erase(it);
                break;
            }
        return false;
    case SDL_EVENT_GAMEPAD_BUTTON_DOWN:
    case SDL_EVENT_GAMEPAD_BUTTON_UP:
        out.kind = e.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN ? RawEvent::ButtonDown : RawEvent::ButtonUp;
        out.device = Device::Gamepad;
        out.device_id = e.gbutton.which;
        out.code = e.gbutton.button;
        out.pad_kind = pad_kind(e.gbutton.which);
        return true;
    case SDL_EVENT_GAMEPAD_AXIS_MOTION:
        out.kind = RawEvent::AxisMotion;
        out.device = Device::Gamepad;
        out.device_id = e.gaxis.which;
        out.code = e.gaxis.axis;
        out.value = std::clamp(static_cast<float>(e.gaxis.value) / 32767.f, -1.f, 1.f);
        out.pad_kind = pad_kind(e.gaxis.which);
        return true;
    case SDL_EVENT_MOUSE_MOTION:
        out.kind = RawEvent::MouseMove;
        out.device = Device::Mouse;
        out.pos = to_points(e.motion.x, e.motion.y);
        out.delta = to_points(e.motion.xrel, e.motion.yrel);
        return true;
    case SDL_EVENT_MOUSE_BUTTON_DOWN:
    case SDL_EVENT_MOUSE_BUTTON_UP:
        out.kind = e.type == SDL_EVENT_MOUSE_BUTTON_DOWN ? RawEvent::MouseDown : RawEvent::MouseUp;
        out.device = Device::Mouse;
        out.code = e.button.button;
        out.pos = to_points(e.button.x, e.button.y);
        return true;
    case SDL_EVENT_MOUSE_WHEEL:
        out.kind = RawEvent::Wheel;
        out.device = Device::Mouse;
        // (As the system has it: SDL's value already follows natural scrolling, which `direction` only reports.)
        out.value = e.wheel.y;
        return true;
    case SDL_EVENT_WINDOW_MOUSE_LEAVE:
        out.kind = RawEvent::MouseMove;
        out.device = Device::Mouse;
        out.pos = {-1e6f, -1e6f};
        return true;
    default:
        return false;
    }
}

bool Window::read_pixels(std::vector<std::uint8_t>& rgba, int& w, int& h) {
    if (!renderer_) return false;
    SDL_Surface* read = SDL_RenderReadPixels(renderer_, nullptr);
    SDL_Surface* image = read ? SDL_ConvertSurface(read, SDL_PIXELFORMAT_RGBA32) : nullptr;
    SDL_DestroySurface(read);
    if (!image) return false;
    w = image->w;
    h = image->h;
    rgba.resize(static_cast<std::size_t>(w) * h * 4);
    for (int y = 0; y < h; ++y)
        std::memcpy(&rgba[static_cast<std::size_t>(y) * w * 4],
                    static_cast<const std::uint8_t*>(image->pixels) + static_cast<std::size_t>(y) * image->pitch,
                    static_cast<std::size_t>(w) * 4);
    SDL_DestroySurface(image);
    return true;
}

bool Window::screenshot(const std::string& path, std::string* error) {
    std::vector<std::uint8_t> rgba;
    int w = 0, h = 0;
    if (!read_pixels(rgba, w, h)) {
        if (error) *error = SDL_GetError();
        return false;
    }
    // (The frame is opaque: alpha is whatever blending left there.)
    for (std::size_t i = 3; i < rgba.size(); i += 4) rgba[i] = 255;
    if (!stbi_write_png(path.c_str(), w, h, 4, rgba.data(), w * 4)) {
        if (error) *error = "cannot write " + path;
        return false;
    }
    return true;
}

}  // namespace ttt2::ui
