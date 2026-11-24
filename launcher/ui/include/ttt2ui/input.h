// Input: keyboard, mouse and gamepad events become ACTIONS (move, accept, back, tabs, sections, pages, ...), with
// the arbitration the review asked for (U4, U5, U7, U8; REVIEW_ui F4/F15):
// - the same action from another device within theme::input::kSamePress counts once (Steam Controller in desktop
//   mode types Enter/arrows while SDL also sees the pad; Steam's virtual pad beside the physical one);
// - Accept and Back never repeat; held moves repeat after a delay at a rate (own timers, OS repeats ignored);
// - keyboards named like Valve's are ignored where SDL gives names (X11, Windows raw input);
// - key capture: raw keys go to the capturer instead; the keyboard is ignored for a while after a pad started it,
//   key-ups of keys held before it started are dropped, and any pad button or a click cancels it;
// - the prompt glyph set follows the last device used (or is forced).
// The router is SDL-free (tests feed RawEvent); Window::translate (window.h) turns SDL events into RawEvents.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "ttt2ui/geometry.h"

namespace ttt2::ui {

enum class Device : std::uint8_t { None, Keyboard, Mouse, Gamepad };

enum class Action : std::uint8_t {
    None,
    Up,
    Down,
    Left,
    Right,
    Accept,
    Back,
    TabPrev,
    TabNext,
    SectionPrev,
    SectionNext,
    PageUp,
    PageDown,
    Home,
    End,
    FocusNext,  // Tab
    FocusPrev,  // Shift+Tab
    Context1,   // X / F
    Context2,   // Y / R
    Menu,       // Start
    Fullscreen, // F11
    Count
};
const char* action_name(Action a);

// The prompt glyphs to show.
enum class Glyphs : std::uint8_t { Keyboard, Xbox, PlayStation, Nintendo, Generic };

// Gamepad buttons by position (SDL_GamepadButton values) and kinds of pads.
namespace pad {
enum Button : int {
    South = 0, East = 1, West = 2, North = 3, Back = 4, Guide = 5, Start = 6, LeftStick = 7, RightStick = 8,
    LeftShoulder = 9, RightShoulder = 10, DpadUp = 11, DpadDown = 12, DpadLeft = 13, DpadRight = 14,
    // Triggers as buttons (from their axes past the dead zone):
    LeftTrigger = 100, RightTrigger = 101
};
enum Axis : int { LeftX = 0, LeftY = 1 };
}  // namespace pad

struct RawEvent {
    enum Kind : std::uint8_t { KeyDown, KeyUp, ButtonDown, ButtonUp, AxisMotion, MouseMove, MouseDown, MouseUp, Wheel };
    Kind kind = KeyDown;
    Device device = Device::Keyboard;
    std::uint32_t device_id = 0;
    double time = 0;          // seconds (the router's clock)
    int code = 0;             // keys: SDL scancode (= USB HID usage); pad: button / axis; mouse: button
    bool os_repeat = false;   // keyboard auto-repeat (ignored: the router repeats itself)
    bool shift = false, ctrl = false, alt = false, gui = false;
    float value = 0;          // axis -1..1; wheel notches (+ = up)
    Vec2 pos{};               // mouse position (points)
    Vec2 delta{};             // mouse motion (points)
    Glyphs pad_kind = Glyphs::Generic;  // gamepad events: what kind of pad it is
    bool filtered = false;    // the SDL side found a Valve keyboard: dropped
};

struct ActionEvent {
    Action action = Action::None;
    Device device = Device::None;
    std::uint32_t device_id = 0;
    double press_time = 0;  // when the press that made it began (a modal ignores presses older than itself)
    bool repeat = false;
};

struct CaptureEvent {
    enum Kind : std::uint8_t { Key, KeyUp, CancelByPad, CancelByMouse };
    Kind kind = Key;
    int scancode = 0;
    bool shift = false, ctrl = false, alt = false, gui = false;
    double time = 0;
};

// The mouse as the interface sees it this frame.
struct MouseState {
    Vec2 pos{-1, -1};
    bool moved = false;          // real motion that may move the focus (not right after pad/keyboard navigation)
    bool down = false;           // button 1 held
    bool pressed = false;        // went down this frame
    bool released = false;       // went up this frame
    float wheel = 0;             // notches this frame (+ = up)
    bool inside = false;
};

class InputRouter {
public:
    // The pad kind decides the confirm button: Nintendo pads accept with East (their "A") and go back with South.
    void feed(const RawEvent& e);
    // Repeats of held moves due by `now`.
    void tick(double now);
    std::vector<ActionEvent> take_actions();
    std::vector<CaptureEvent> take_capture();
    MouseState take_mouse();  // (clears the per-frame parts)

    // Key capture (Settings > Keyboard): started by which device; until end_capture no actions come.
    void begin_capture(Device started_by, double now);
    void end_capture();
    bool capturing() const { return capturing_; }

    // The glyph set: from the last device used, or forced (Settings, TTT2_CONTROLLER).
    Glyphs glyphs() const { return forced_ ? forced_glyphs_ : last_glyphs_; }
    void force_glyphs(bool on, Glyphs g = Glyphs::Keyboard) {
        forced_ = on;
        forced_glyphs_ = g;
    }
    Device last_device() const { return last_device_; }
    // Navigation from pad/keyboard happened at `time` (mouse motion is ignored for a while after).
    double last_nav_time() const { return last_nav_; }
    // Nothing should repeat or stay held (window lost focus).
    void release_all();
    // Something is held that will repeat (the loop must keep ticking).
    bool holding() const;
    // Whatever the next frame takes from it: actions, capture events, the mouse's motion, presses or wheel.
    bool pending() const {
        return !actions_.empty() || !capture_.empty() || mouse_.moved || mouse_.pressed || mouse_.released ||
               mouse_.wheel != 0;
    }
    double next_repeat_time() const;

private:
    struct Held {
        Action action = Action::None;
        Device device = Device::None;
        std::uint32_t device_id = 0;
        int code = 0;
        double press_time = 0, next = 0;
        bool active = false;
    };
    void press(Action a, Device d, std::uint32_t id, int code, double t);
    void release(Device d, std::uint32_t id, int code, double t);
    Action key_action(const RawEvent& e) const;
    Action pad_action(int button, Glyphs kind) const;
    void emit(Action a, Device d, std::uint32_t id, double press_time, bool repeat);

    std::vector<ActionEvent> actions_;
    std::vector<CaptureEvent> capture_;
    std::vector<Held> held_;
    struct Last {
        Device device = Device::None;
        std::uint32_t device_id = 0;
        double time = -1;
    } last_[static_cast<int>(Action::Count)];
    // Stick directions per pad (with hysteresis) and trigger states.
    struct PadAxes {
        std::uint32_t id = 0;
        float x = 0, y = 0;
        int dir = -1;  // pad button of the stick's current direction, -1 none
        bool lt = false, rt = false;
    };
    std::vector<PadAxes> axes_;
    MouseState mouse_;
    bool capturing_ = false;
    Device capture_device_ = Device::None;
    double capture_start_ = 0;
    std::vector<int> keys_down_before_capture_;
    std::vector<int> keys_down_;
    Glyphs last_glyphs_ = Glyphs::Keyboard, forced_glyphs_ = Glyphs::Keyboard;
    bool forced_ = false;
    Device last_device_ = Device::None;
    double last_nav_ = -1e9;
    Vec2 mouse_travel_{};
};

}  // namespace ttt2::ui
