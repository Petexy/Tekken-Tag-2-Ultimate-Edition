#include "ttt2ui/input.h"

#include <algorithm>
#include <cmath>
#include <utility>

#include "ttt2ui/theme.h"

namespace ttt2::ui {

namespace {
// SDL scancodes (= USB HID usages) the router knows.
enum Key : int {
    kA = 4, kC = 6, kD = 7, kE = 8, kF = 9, kQ = 20, kR = 21, kS = 22, kW = 26, kZ = 29, kReturn = 40, kEscape = 41,
    kBackspace = 42, kTab = 43, kSpace = 44, kF11 = 68, kHome = 74, kPageUp = 75, kEnd = 77, kPageDown = 78,
    kRight = 79, kLeft = 80, kDown = 81, kUp = 82, kKeypadEnter = 88
};
constexpr int kStickBase = 200;  // stick directions as pseudo buttons 200..203 (beside the real D-pad)

bool is_move(Action a) { return a == Action::Up || a == Action::Down || a == Action::Left || a == Action::Right; }
bool repeats(Action a) { return is_move(a) || a == Action::PageUp || a == Action::PageDown; }
}  // namespace

const char* action_name(Action a) {
    static const char* kNames[] = {"none",   "up",      "down",     "left",         "right",        "accept",
                                   "back",   "tab-prev", "tab-next", "section-prev", "section-next", "page-up",
                                   "page-down", "home",  "end",     "focus-next",   "focus-prev",   "context1",
                                   "context2", "menu",   "fullscreen"};
    static_assert(sizeof kNames / sizeof kNames[0] == static_cast<int>(Action::Count));
    return kNames[static_cast<int>(a)];
}

Action InputRouter::key_action(const RawEvent& e) const {
    if (e.code == kTab) {
        if (e.ctrl) return e.shift ? Action::TabPrev : Action::TabNext;
        return e.shift ? Action::FocusPrev : Action::FocusNext;
    }
    if (e.alt && e.code == kLeft) return Action::Back;  // (as the GTK launcher's Settings page)
    if (e.ctrl || e.alt || e.gui) return Action::None;  // shortcuts of other programs, AltGr chords
    switch (e.code) {
    case kUp: case kW: return Action::Up;
    case kDown: case kS: return Action::Down;
    case kLeft: case kA: return Action::Left;
    case kRight: case kD: return Action::Right;
    case kReturn: case kSpace: case kKeypadEnter: return Action::Accept;
    case kEscape: case kBackspace: return Action::Back;
    case kQ: return Action::TabPrev;
    case kE: return Action::TabNext;
    case kZ: return Action::SectionPrev;
    case kC: return Action::SectionNext;
    case kPageUp: return Action::PageUp;
    case kPageDown: return Action::PageDown;
    case kHome: return Action::Home;
    case kEnd: return Action::End;
    case kF: return Action::Context1;
    case kR: return Action::Context2;
    case kF11: return Action::Fullscreen;
    default: return Action::None;
    }
}

Action InputRouter::pad_action(int button, Glyphs kind) const {
    const bool nintendo = kind == Glyphs::Nintendo;  // (the game's rule: Nintendo pads keep the Wii U's way)
    switch (button) {
    case pad::South: return nintendo ? Action::Back : Action::Accept;
    case pad::East: return nintendo ? Action::Accept : Action::Back;
    case pad::West: return Action::Context1;
    case pad::North: return Action::Context2;
    case pad::LeftShoulder: return Action::TabPrev;
    case pad::RightShoulder: return Action::TabNext;
    case pad::LeftTrigger: return Action::SectionPrev;
    case pad::RightTrigger: return Action::SectionNext;
    case pad::Start: return Action::Menu;
    case pad::DpadUp: case kStickBase + 0: return Action::Up;
    case pad::DpadDown: case kStickBase + 1: return Action::Down;
    case pad::DpadLeft: case kStickBase + 2: return Action::Left;
    case pad::DpadRight: case kStickBase + 3: return Action::Right;
    default: return Action::None;
    }
}

void InputRouter::emit(Action a, Device d, std::uint32_t id, double press_time, bool repeat) {
    actions_.push_back({a, d, id, press_time, repeat});
}

bool InputRouter::same_press(Action a, Device d, std::uint32_t id, double t) const {
    if (a == Action::None) return false;
    const Last& l = last_[static_cast<int>(a)];
    return l.time >= 0 && t - l.time < theme::input::kSamePress && (l.device != d || l.device_id != id);
}

void InputRouter::press(Action a, Device d, std::uint32_t id, int code, double t) {
    if (a == Action::None) return;
    if (same_press(a, d, id, t)) return;
    Last& l = last_[static_cast<int>(a)];
    l = {d, id, t};
    last_nav_ = t;
    mouse_travel_ = {};
    emit(a, d, id, t, false);
    if (repeats(a)) {
        const double delay = d == Device::Gamepad ? theme::input::kPadRepeatDelay : theme::input::kKeyRepeatDelay;
        held_.push_back({a, d, id, code, t, t + delay, true});
    }
}

void InputRouter::release(Device d, std::uint32_t id, int code, double) {
    held_.erase(std::remove_if(held_.begin(), held_.end(),
                               [&](const Held& h) { return h.device == d && h.device_id == id && h.code == code; }),
                held_.end());
}

void InputRouter::feed(const RawEvent& e) {
    if (e.filtered) return;
    switch (e.kind) {
    case RawEvent::KeyDown: {
        if (e.os_repeat) return;
        if (std::find(keys_down_.begin(), keys_down_.end(), e.code) == keys_down_.end()) keys_down_.push_back(e.code);
        last_device_ = Device::Keyboard;
        last_glyphs_ = Glyphs::Keyboard;
        if (capturing_) {
            if (capture_device_ == Device::Gamepad && e.time - capture_start_ < theme::input::kCaptureKeyboardIgnore) {
                // (Ignored: its key-up is not a capture either.)
                keys_down_before_capture_.push_back(e.code);
                return;
            }
            capture_.push_back({CaptureEvent::Key, e.code, e.shift, e.ctrl, e.alt, e.gui, e.time});
            return;
        }
        press(key_action(e), Device::Keyboard, e.device_id, e.code, e.time);
        return;
    }
    case RawEvent::KeyUp: {
        keys_down_.erase(std::remove(keys_down_.begin(), keys_down_.end(), e.code), keys_down_.end());
        if (capturing_) {
            auto it = std::find(keys_down_before_capture_.begin(), keys_down_before_capture_.end(), e.code);
            if (it != keys_down_before_capture_.end()) {
                keys_down_before_capture_.erase(it);  // (its key-down came before the capture)
                return;
            }
            capture_.push_back({CaptureEvent::KeyUp, e.code, e.shift, e.ctrl, e.alt, e.gui, e.time});
            return;
        }
        release(Device::Keyboard, e.device_id, e.code, e.time);
        return;
    }
    case RawEvent::ButtonDown:
        last_device_ = Device::Gamepad;
        last_glyphs_ = e.pad_kind;
        if (capturing_) {
            // The other order of the same press (U4): a Steam Controller's A is an Enter Steam types AND its pad's
            // A; the Enter, arriving first, started choosing a key; the pad's report of that same press (pads are
            // read at the poll: it arrives later) is not B, it changes nothing. By arrival time, as press() does.
            if (same_press(pad_action(e.code, e.pad_kind), Device::Gamepad, e.device_id, e.time)) return;
            capture_.push_back({CaptureEvent::CancelByPad, 0, false, false, false, false, e.time});
            return;
        }
        press(pad_action(e.code, e.pad_kind), Device::Gamepad, e.device_id, e.code, e.time);
        return;
    case RawEvent::ButtonUp:
        release(Device::Gamepad, e.device_id, e.code, e.time);
        return;
    case RawEvent::AxisMotion: {
        auto it = std::find_if(axes_.begin(), axes_.end(), [&](const PadAxes& a) { return a.id == e.device_id; });
        if (it == axes_.end()) {
            axes_.push_back({});
            it = axes_.end() - 1;
            it->id = e.device_id;
        }
        PadAxes& p = *it;
        if (e.code == 4 || e.code == 5) {  // triggers (SDL_GAMEPAD_AXIS_LEFT_TRIGGER / RIGHT_TRIGGER), 0..1
            bool& state = e.code == 4 ? p.lt : p.rt;
            const int button = e.code == 4 ? pad::LeftTrigger : pad::RightTrigger;
            if (!state && e.value > theme::input::kStickPress) {
                state = true;
                RawEvent b = e;
                b.kind = RawEvent::ButtonDown;
                b.code = button;
                feed(b);
            } else if (state && e.value < theme::input::kStickRelease) {
                state = false;
                release(Device::Gamepad, e.device_id, button, e.time);
            }
            return;
        }
        if (e.code == pad::LeftX) p.x = e.value;
        else if (e.code == pad::LeftY) p.y = e.value;
        else return;
        // Dead zone with hysteresis: a direction is pressed past kStickPress on its axis, released under
        // kStickRelease.
        if (p.dir >= 0) {
            const float v = (p.dir == kStickBase + 0 || p.dir == kStickBase + 1) ? std::fabs(p.y) : std::fabs(p.x);
            if (v >= theme::input::kStickRelease) return;
            release(Device::Gamepad, e.device_id, p.dir, e.time);
            p.dir = -1;
        }
        const float ax = std::fabs(p.x), ay = std::fabs(p.y);
        int dir = -1;
        if (ay >= ax && ay > theme::input::kStickPress) dir = kStickBase + (p.y < 0 ? 0 : 1);
        else if (ax > ay && ax > theme::input::kStickPress) dir = kStickBase + (p.x < 0 ? 2 : 3);
        if (dir < 0) return;
        p.dir = dir;
        last_device_ = Device::Gamepad;
        last_glyphs_ = e.pad_kind;
        if (capturing_) return;
        press(pad_action(dir, e.pad_kind), Device::Gamepad, e.device_id, dir, e.time);
        return;
    }
    case RawEvent::MouseMove:
        mouse_.pos = e.pos;
        mouse_.inside = true;
        mouse_travel_ = mouse_travel_ + Vec2{std::fabs(e.delta.x), std::fabs(e.delta.y)};
        if (e.time - last_nav_ >= theme::input::kMouseAfterNav &&
            mouse_travel_.x + mouse_travel_.y >= theme::input::kMouseHoverSlop) {
            mouse_.moved = true;
            last_device_ = Device::Mouse;
        }
        return;
    case RawEvent::MouseDown:
        mouse_.pos = e.pos;
        last_device_ = Device::Mouse;
        if (capturing_) {
            capture_.push_back({CaptureEvent::CancelByMouse, 0, false, false, false, false, e.time});
            return;
        }
        if (e.code == 1) {
            mouse_.down = true;
            mouse_.pressed = true;
        }
        return;
    case RawEvent::MouseUp:
        mouse_.pos = e.pos;
        if (e.code == 1) {
            mouse_.down = false;
            mouse_.released = true;
        }
        return;
    case RawEvent::Wheel:
        mouse_.wheel += e.value;
        return;
    }
}

void InputRouter::tick(double now) {
    for (Held& h : held_) {
        while (h.next <= now) {
            // One device repeats an action at a time (the one pressed first): two devices holding the same
            // direction (a Steam Controller typing arrows) must not move twice as fast.
            const bool other_first = std::any_of(held_.begin(), held_.end(), [&](const Held& o) {
                return &o != &h && o.action == h.action && (o.device != h.device || o.device_id != h.device_id) &&
                       o.press_time < h.press_time;
            });
            if (!other_first && !capturing_) emit(h.action, h.device, h.device_id, h.press_time, true);
            h.next += h.device == Device::Gamepad ? theme::input::kPadRepeatRate : theme::input::kKeyRepeatRate;
            last_nav_ = h.next;
        }
    }
}

std::vector<ActionEvent> InputRouter::take_actions() { return std::exchange(actions_, {}); }
std::vector<CaptureEvent> InputRouter::take_capture() { return std::exchange(capture_, {}); }

MouseState InputRouter::take_mouse() {
    MouseState m = mouse_;
    mouse_.moved = mouse_.pressed = mouse_.released = false;
    mouse_.wheel = 0;
    if (m.moved) mouse_travel_ = {};
    return m;
}

void InputRouter::begin_capture(Device started_by, double now) {
    capturing_ = true;
    capture_device_ = started_by;
    capture_start_ = now;
    keys_down_before_capture_ = keys_down_;
    held_.clear();
    capture_.clear();
}

void InputRouter::end_capture() {
    capturing_ = false;
    capture_.clear();
}

void InputRouter::release_all() {
    held_.clear();
    keys_down_.clear();
    for (PadAxes& p : axes_) p = PadAxes{p.id};
    mouse_.down = false;
}

bool InputRouter::holding() const { return !held_.empty(); }

double InputRouter::next_repeat_time() const {
    double t = 1e18;
    for (const Held& h : held_) t = std::min(t, h.next);
    return t;
}

}  // namespace ttt2::ui
