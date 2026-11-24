// The window and everything SDL-specific around it:
// - a borderless, resizable, high-DPI window, shown after its first frame; the interface draws its own frame: a drag
//   strip and resize edges through SDL_SetWindowHitTest, minimise / fullscreen / close buttons (the app draws them
//   and gives their rectangles), F11; under gamescope / Steam Deck it starts fullscreen and has no minimise, drag,
//   resize or fullscreen toggle (C16);
// - scale (U6): display scale x clamp(stage factor, 1, 2), so text never shrinks below its design size; smaller
//   windows get a smaller layout (reflow/scroll), DISPLAY_SCALE_CHANGED handled;
// - SDL_HINT_VIDEO_ALLOW_SCREENSAVER=1, SDL_HINT_AUTO_UPDATE_JOYSTICKS=0 (U5);
// - when the video driver, window or renderer cannot be made: the other video driver, then the software renderer,
//   then a message box with the releases link (C2);
// - gamepads: the subsystem is started when the window gets the focus and stopped when it loses it, is minimised,
//   or the game runs; polled at theme::input::kPadPollInterval only while focused (U5, F3, F11);
// - SDL events -> RawEvent for the InputRouter (Valve keyboards ignored where SDL names them);
// - screenshots (SDL_RenderReadPixels + stb_image_write).
#pragma once

#include <SDL3/SDL.h>

#include <functional>
#include <string>
#include <vector>

#include "ttt2ui/geometry.h"
#include "ttt2ui/input.h"

namespace ttt2::ui {

struct WindowOptions {
    std::string title = "Ultimate Launcher";
    std::string app_id;              // Wayland app_id / X11 class / SDL_SetAppMetadata
    std::string version;
    std::string releases_url = "https://github.com/Petexy/Tekken-Tag-2-Ultimate-Edition/releases";
    Vec2 size{1280, 800};            // points at content scale 1 (multiplied by the display's content scale)
    Vec2 min_size{960, 600};
    bool offscreen = false;          // tests / --screenshot: SDL's offscreen driver + the software renderer
    float forced_scale = 0;          // > 0: this UI scale (tests: --scale)
    bool start_fullscreen = false;
};

// SteamDeck=1, SteamOS=1, XDG_CURRENT_DESKTOP=gamescope or GAMESCOPE_WAYLAND_DISPLAY set.
bool running_under_gamescope();
// U6: the interface's scale for a window of `pixels` with display scale `display`.
float ui_scale(Vec2 pixels, float display, float user_text_scale = 1);

class Window {
public:
    Window() = default;
    ~Window();
    Window(const Window&) = delete;
    Window& operator=(const Window&) = delete;

    // SDL_Init + window + renderer with the fallbacks of C2; false (and error()) when none worked, after showing the
    // message box (not in offscreen mode).
    bool open(const WindowOptions& options);
    const std::string& error() const { return error_; }
    SDL_Window* sdl() const { return window_; }
    SDL_Renderer* renderer() const { return renderer_; }
    std::string renderer_name() const;
    std::string video_driver() const;

    // Size in physical pixels and the layout size in points at the current scale.
    Vec2 pixels() const;
    float scale() const { return scale_; }
    Vec2 points() const;
    void update_scale();
    void set_user_text_scale(float s) {
        user_scale_ = s;
        update_scale();
    }

    // The app's own frame: where the window can be dragged (points) and its caption buttons (not draggable).
    void set_drag_area(const Rect& strip, std::vector<Rect> buttons) {
        drag_ = strip;
        buttons_ = std::move(buttons);
    }
    bool gamescope() const { return gamescope_; }
    // What the frame may offer (C16).
    bool can_minimise() const { return !gamescope_; }
    bool can_toggle_fullscreen() const { return !gamescope_; }
    bool fullscreen() const;
    void set_fullscreen(bool on);
    void toggle_fullscreen() { set_fullscreen(!fullscreen()); }
    void minimise();
    void show();  // after the first frame
    bool focused() const { return focused_; }
    bool visible() const { return visible_; }

    // Events: SDL event -> raw input for the router (false when it is not input). Window events update the state
    // here (focus, visibility, scale) and return false.
    bool translate(const SDL_Event& e, RawEvent& out, double now);
    // Gamepads: start/stop with the focus (after kPadInitDelay), poll while focused. `game_running` keeps them off.
    void pads_tick(double now, bool game_running);
    double next_pad_poll() const;
    int pads_open() const { return static_cast<int>(pads_.size()); }

    // The frame as an RGBA PNG.
    bool screenshot(const std::string& path, std::string* error = nullptr);
    // The frame's pixels (RGBA32, w*h*4).
    bool read_pixels(std::vector<std::uint8_t>& rgba, int& w, int& h);

private:
    static SDL_HitTestResult SDLCALL hit_test(SDL_Window* window, const SDL_Point* area, void* data);
    bool try_open(const WindowOptions& options, const char* video, const char* render, std::string& why);
    void open_pads();
    void close_pads();
    Glyphs pad_kind(SDL_JoystickID id) const;

    SDL_Window* window_ = nullptr;
    SDL_Renderer* renderer_ = nullptr;
    std::string error_;
    float scale_ = 1, user_scale_ = 1, forced_scale_ = 0;
    Rect drag_{};
    std::vector<Rect> buttons_;
    bool gamescope_ = false, focused_ = true, visible_ = true, shown_ = false;
    bool pads_on_ = false;
    double focus_since_ = 0, last_poll_ = 0;
    struct Pad {
        SDL_JoystickID id;
        SDL_Gamepad* pad;
        Glyphs kind;
    };
    std::vector<Pad> pads_;
};

}  // namespace ttt2::ui
