// Controllers: the Wii U GamePad (vpad) and up to four Pro Controllers
// (padscore's KPAD, channels 0-3); their states come from the host
// (set_gamepad_state, set_pro_controller_states, fed by the window layer).
// No Wii Remotes are connected. The title reads the other controllers
// through KPAD only (its calls of WPAD's own functions are in a library of
// the title's that nothing runs).

#include "kernel.h"

#include "cafe/export.h"
#include "cafe/input.h"
#include "cafe/vfs.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

namespace cafe::os {
namespace {

std::mutex g_input_mutex;
GamepadState g_gamepad{};
TouchState g_touch{};
uint32_t g_previous_hold = 0;
std::array<std::optional<GamepadState>, kProControllers> g_pro{};

// A Pro Controller's reads. Once connected, it shows no buttons for
// kSettleReads reads, so that the title has seen it connect before it sees
// a press (a player joins with the press of + that connected the
// controller); what is pressed meanwhile is held for kHeldReads after.
constexpr int kSettleReads = 3;
struct ProReads {
    int connected = -1; // reads since it connected; -1: not connected
    uint32_t previous = 0, latched = 0;
    int latched_reads = 0;
};
std::array<ProReads, kProControllers> g_pro_reads{};

// set_input_step: reads to the next one the game sees change, buttons
// pressed meanwhile.
// It lasts a while unless set again (the mode sets it every frame; when its
// frames stop, the pad goes back to usual).
uint32_t g_step_every = 1, g_step_reads = 0, g_step_pressed = 0;
bool g_step_delivered = true;
std::chrono::steady_clock::time_point g_step_until{};
constexpr auto kStepLasts = std::chrono::milliseconds(250);

// TTT2_INPUT_SCRIPT="15:plus,20.5:a,22:down" presses each button at the given
// second after start-up, for unattended runs; "30:plus#2" presses it on the
// second controller (2-5: Pro Controllers 1-4, connected for the whole run
// once the script names them; 1 is the GamePad): for a fifth of a second and at
// least kHeldReads reads of the pad, then released for kReleasedReads reads
// before the same button is pressed again, so a press is seen even when a frame
// stalls (loading). An item "@3dbb1771" waits until the title reads the archive
// entry with that name hash (the character select screen's layout, say): the
// times after it count from then, and presses before it that have not come yet
// are dropped, so a script does not drift with loading times.
// Items that last a while: "40:touch/400/300/600/320/1.5" touches the
// GamePad's screen at 400,300 of its picture (1280 x 720, as the TV's) and
// draws a straight line to 600,320 in 1.5 s, then lifts (a tap: the same
// point twice). For the host's own input (scripted_host_input):
// "40:mouse/0.5/0.5/0.6/0.5/1" moves the mouse with its left button held
// across the window (fractions of its size), "40:rstick/1/0/0.5" holds the
// right stick, "40:hold/zr/2" holds a button.
constexpr int kHeldReads = 4;
constexpr int kReleasedReads = 4;

struct ScriptedPress {
    double at;
    uint32_t button;
    size_t segment; // the anchors before it
    int port;       // 0: the GamePad, 1-4: a Pro Controller's channel + 1
    int reads = -1; // reads of the pad while held; -1: not pressed yet
};

struct ScriptedSpan {
    enum Kind { kTouch, kMouse, kStick, kHold } kind;
    double at, seconds;
    float x0, y0, x1, y1; // kTouch: in the GamePad's picture, 1280 x 720; kMouse: of the window; kStick: x0, y0
    uint32_t button;      // kHold
    size_t segment;
};

struct Script {
    std::vector<ScriptedPress> presses;
    std::vector<ScriptedSpan> spans;
    std::vector<uint32_t> anchors;
    std::mutex mutex;
    std::vector<double> starts; // each segment's start, after start-up; < 0 while waiting
    std::vector<std::pair<uint64_t, int>> released; // port << 32 | button -> reads since its last scripted release
    std::array<bool, kProControllers> pro{};          // Pro Controllers the script uses
    std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
};

double seconds_since(std::chrono::steady_clock::time_point start) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
}

Script& load_script() {
    static Script script;
    const char* text_env = std::getenv("TTT2_INPUT_SCRIPT");
    if (text_env == nullptr) return script;
    static const std::pair<const char*, uint32_t> kNames[] = {
        {"a", vpad::kA}, {"b", vpad::kB}, {"x", vpad::kX}, {"y", vpad::kY}, {"left", vpad::kLeft},
        {"right", vpad::kRight}, {"up", vpad::kUp}, {"down", vpad::kDown}, {"zl", vpad::kZL}, {"zr", vpad::kZR},
        {"l", vpad::kL}, {"r", vpad::kR}, {"plus", vpad::kPlus}, {"minus", vpad::kMinus}, {"home", vpad::kHome},
    };
    std::string text(text_env);
    size_t pos = 0;
    while (pos < text.size()) {
        const size_t end = text.find(',', pos) == std::string::npos ? text.size() : text.find(',', pos);
        const std::string item = text.substr(pos, end - pos);
        const size_t colon = item.find(':');
        if (!item.empty() && item[0] == '@') {
            script.anchors.push_back(static_cast<uint32_t>(std::strtoul(item.c_str() + 1, nullptr, 16)));
        } else if (colon != std::string::npos) {
            std::string name = item.substr(colon + 1);
            int port = 0;
            if (const size_t hash = name.find('#'); hash != std::string::npos) {
                port = std::clamp(std::atoi(name.c_str() + hash + 1), 1, kProControllers + 1) - 1;
                name.resize(hash);
            }
            if (port > 0) script.pro[port - 1] = true;
            ScriptedSpan span{ScriptedSpan::kTouch, std::atof(item.substr(0, colon).c_str()), 0.0, 0, 0, 0, 0, 0,
                              script.anchors.size()};
            char held[16] = "";
            if (std::sscanf(name.c_str(), "touch/%f/%f/%f/%f/%lf", &span.x0, &span.y0, &span.x1, &span.y1,
                            &span.seconds) == 5) {
                script.spans.push_back(span);
            } else if (std::sscanf(name.c_str(), "mouse/%f/%f/%f/%f/%lf", &span.x0, &span.y0, &span.x1, &span.y1,
                                   &span.seconds) == 5) {
                span.kind = ScriptedSpan::kMouse;
                script.spans.push_back(span);
            } else if (std::sscanf(name.c_str(), "rstick/%f/%f/%lf", &span.x0, &span.y0, &span.seconds) == 3) {
                span.kind = ScriptedSpan::kStick;
                script.spans.push_back(span);
            } else if (std::sscanf(name.c_str(), "hold/%15[a-z]/%lf", held, &span.seconds) == 2) {
                span.kind = ScriptedSpan::kHold;
                for (const auto& [n, bit] : kNames) {
                    if (std::string(held) == n) span.button = bit;
                }
                if (span.button) script.spans.push_back(span);
            }
            for (const auto& [n, bit] : kNames) {
                if (name == n) {
                    script.presses.push_back(
                        {std::atof(item.substr(0, colon).c_str()), bit, script.anchors.size(), port});
                }
            }
        }
        pos = end + 1;
    }
    script.starts.assign(script.anchors.size() + 1, -1.0);
    script.starts[0] = 0.0;
    if (!script.anchors.empty()) {
        vfs::watch_entry_reads([&s = script](uint32_t hash) {
            std::lock_guard lock(s.mutex);
            for (size_t k = 0; k < s.anchors.size(); ++k) {
                if (s.starts[k + 1] >= 0.0) continue;
                if (s.starts[k] >= 0.0 && s.anchors[k] == hash) s.starts[k + 1] = seconds_since(s.start);
                break;
            }
        });
    }
    return script;
}

Script& script() {
    static Script& script = load_script();
    return script;
}

// The buttons the script holds on a port (0: the GamePad, 1-4: a Pro
// Controller's channel + 1), for a read of it.
uint32_t scripted_buttons(int port) {
    Script& script = cafe::os::script();
    if (script.presses.empty()) return 0;
    const double t = seconds_since(script.start);
    std::lock_guard lock(script.mutex);
    auto released_reads = [&](uint32_t button) -> int& {
        const uint64_t key = uint64_t(port) << 32 | button;
        for (auto& [b, n] : script.released) {
            if (b == key) return n;
        }
        script.released.push_back({key, kReleasedReads});
        return script.released.back().second;
    };
    uint32_t buttons = 0;
    for (ScriptedPress& p : script.presses) {
        if (p.port != port || p.reads >= kHeldReads) continue; // another pad's, or done
        const double start = script.starts[p.segment];
        const bool next_reached = p.segment + 1 < script.starts.size() && script.starts[p.segment + 1] >= 0.0;
        if (p.reads < 0) {
            if (start < 0.0 || next_reached || t < start + p.at) continue;
            if (released_reads(p.button) < kReleasedReads || (buttons & p.button)) continue; // wait for a release
            p.reads = 0;
            // TTT2_TRACE_INPUT: when each scripted press begins (seconds after start-up, as TTT2_CAPTURE_START counts)
            static const bool trace = std::getenv("TTT2_TRACE_INPUT") != nullptr;
            if (trace) std::fprintf(stderr, "ttt2: input script: %.1f (button %08X, pad %d) pressed at %.2f s\n", p.at, p.button, port, t);
        }
        buttons |= p.button;
        if (++p.reads >= kHeldReads && t < start + p.at + 0.2) p.reads = kHeldReads - 1; // hold the fifth second
        if (p.reads >= kHeldReads) released_reads(p.button) = -1;
    }
    for (auto& [b, n] : script.released) {
        if (b >> 32 == uint64_t(port) && !(buttons & uint32_t(b)) && n < kReleasedReads) ++n;
    }
    return buttons;
}

// Calls `each(span, f)` for the script's spans of `kind` going on now (f:
// how far into it, 0 to 1).
template <typename F>
void scripted_spans(ScriptedSpan::Kind kind, F each) {
    Script& script = cafe::os::script();
    if (script.spans.empty()) return;
    const double t = seconds_since(script.start);
    std::lock_guard lock(script.mutex);
    for (const ScriptedSpan& s : script.spans) {
        if (s.kind != kind) continue;
        const double start = script.starts[s.segment];
        const bool next_reached = s.segment + 1 < script.starts.size() && script.starts[s.segment + 1] >= 0.0;
        if (start < 0.0 || next_reached || t < start + s.at || t > start + s.at + s.seconds) continue;
        each(s, s.seconds > 0.0 ? static_cast<float>((t - start - s.at) / s.seconds) : 1.0f);
    }
}

// The touch the script's strokes hold now, if one does.
std::optional<TouchState> scripted_touch() {
    std::optional<TouchState> touch;
    scripted_spans(ScriptedSpan::kTouch, [&](const ScriptedSpan& s, float f) {
        touch = TouchState{true, (s.x0 + (s.x1 - s.x0) * f) / 1280.0f, (s.y0 + (s.y1 - s.y0) * f) / 720.0f};
    });
    return touch;
}

// ------------------------------------------------------------ the - chord
// See arm_select_chord. A press of - waits kChordFrames armings (the mode's
// frames, so slow frames wait longer): the mode sees a button two or three
// frames after the pad has it, and the other button may come a little after
// -. A press of - let go meanwhile still reaches the game, late, for
// kHeldReads reads.
using Clock = std::chrono::steady_clock;
constexpr uint32_t kChordFrames = 8;                         // how many armings a press of - waits for the partner
constexpr auto kChordArmed = std::chrono::milliseconds(250); // how long an arming lasts (frames may be slow)
constexpr auto kChordTaken = std::chrono::milliseconds(500); // how long a chord waits to be taken

struct SelectChord {
    enum Gate { kOpen, kWaiting, kChord } gate = kOpen;
    Clock::time_point armed_until{}, chord_at{};
    uint32_t armings = 0, pressed_armings = 0; // armings so far, and at the press of -
    bool partner = false;
    bool raw = false;     // - held, as the host has it
    bool chord = false;   // a chord not taken yet
    int late_reads = 0;
};
SelectChord g_chord;

uint32_t gate_select(uint32_t hold) {
    SelectChord& c = g_chord;
    const Clock::time_point now = Clock::now();
    const bool raw = hold & vpad::kMinus, pressed = raw && !c.raw, armed = now < c.armed_until;
    c.raw = raw;
    auto chord = [&] {
        c.gate = SelectChord::kChord;
        c.chord = true;
        c.chord_at = now;
    };
    if (pressed) {
        if (!armed) c.gate = SelectChord::kOpen;
        else if (c.partner) chord();
        else {
            c.gate = SelectChord::kWaiting;
            c.pressed_armings = c.armings;
        }
    } else if (c.gate == SelectChord::kWaiting) {
        if (armed && c.partner) {
            chord();
        } else if (!armed || c.armings - c.pressed_armings >= kChordFrames) {
            c.gate = SelectChord::kOpen;
            if (!raw) c.late_reads = kHeldReads;
        }
    }
    switch (c.gate) {
    case SelectChord::kWaiting: return hold & ~vpad::kMinus;
    case SelectChord::kChord:
        if (!raw) c.gate = SelectChord::kOpen;
        return hold & ~vpad::kMinus;
    case SelectChord::kOpen: break;
    }
    if (c.late_reads > 0) {
        --c.late_reads;
        return hold | vpad::kMinus;
    }
    return hold;
}

// ------------------------------------------------------------------- vpad
constexpr int32_t kVpadOk = 0;
constexpr int32_t kVpadNoController = -2;

GamepadState movement_state(GamepadState state) {
    // Keep DP and LS movement consistent. Resolve opposite digital
    // directions to neutral on that axis; digital input takes precedence
    // over analog drift.
    const auto digital_axis = [&](uint32_t negative, uint32_t positive, float analog) {
        const bool neg = state.buttons & negative, pos = state.buttons & positive;
        if (!neg && !pos) return std::clamp(analog, -1.0f, 1.0f);
        if (neg && pos) state.buttons &= ~(negative | positive);
        return float(pos) - float(neg);
    };
    state.left_x = digital_axis(vpad::kLeft, vpad::kRight, state.left_x);
    state.left_y = digital_axis(vpad::kDown, vpad::kUp, state.left_y);
    state.right_x = std::clamp(state.right_x, -1.0f, 1.0f);
    state.right_y = std::clamp(state.right_y, -1.0f, 1.0f);

    // Wii U reports stick directions in hold/trigger/release too. Sending
    // only axes leaves LS-mode controllers without these digital inputs.
    constexpr uint32_t directions = vpad::kStickLLeft | vpad::kStickLRight | vpad::kStickLUp | vpad::kStickLDown |
                                    vpad::kStickRLeft | vpad::kStickRRight | vpad::kStickRUp | vpad::kStickRDown;
    state.buttons &= ~directions;
    const auto stick_axis = [&](float value, uint32_t negative, uint32_t positive) {
        if (value <= -0.5f) state.buttons |= negative;
        if (value >= 0.5f) state.buttons |= positive;
    };
    stick_axis(state.left_x, vpad::kStickLLeft, vpad::kStickLRight);
    stick_axis(state.left_y, vpad::kStickLDown, vpad::kStickLUp);
    stick_axis(state.right_x, vpad::kStickRLeft, vpad::kStickRRight);
    stick_axis(state.right_y, vpad::kStickRDown, vpad::kStickRUp);
    // Combat's sub_03F52F20 matches the D-pad masks, not the VPAD stick
    // emulation flags. An LS-mode leverless therefore needs these bits too.
    stick_axis(state.left_x, vpad::kLeft, vpad::kRight);
    stick_axis(state.left_y, vpad::kDown, vpad::kUp);
    return state;
}

struct Vec2 { be<float> x, y; };
struct Vec3 { be<float> x, y, z; };
struct TouchData { be<uint16_t> x, y, touched, validity; };
struct VPADStatus {
    be<uint32_t> hold, trigger, release;
    Vec2 left_stick, right_stick;
    Vec3 acceleration;
    be<float> acc_magnitude, acc_variation;
    Vec2 acc_xy;
    Vec3 gyro, angle;
    int8_t error;
    uint8_t pad1;
    TouchData touch, touch_processed1, touch_processed2;
    uint8_t pad2[2];
    Vec3 direction[3];
    uint8_t headphone;
    uint8_t pad3[3];
    Vec3 magnet;
    uint8_t volume, battery, mic, volume_ex;
    uint8_t pad4[8];
};
static_assert(sizeof(VPADStatus) == 0xAC);

void VPADInit() {}

int32_t VPADRead(int32_t channel, VPADStatus* status, uint32_t count, be<int32_t>* error) {
    if (channel != 0 || count == 0 || status == nullptr) {
        if (error) *error = kVpadNoController;
        return 0;
    }
    std::lock_guard lock(g_input_mutex);
    std::memset(status, 0, sizeof(VPADStatus));
    GamepadState state = g_gamepad;
    state.buttons |= scripted_buttons(0);
    state = movement_state(state);
    uint32_t hold = gate_select(state.buttons);
    if (g_step_every > 1 && std::chrono::steady_clock::now() > g_step_until) g_step_every = 1;
    g_step_delivered = g_step_every <= 1 || ++g_step_reads % g_step_every == 0;
    if (!g_step_delivered) {
        g_step_pressed |= hold;
        hold = g_previous_hold;
    } else {
        hold |= g_step_pressed;
        g_step_pressed = 0;
    }
    status->hold = hold;
    status->trigger = hold & ~g_previous_hold;
    status->release = g_previous_hold & ~hold;
    g_previous_hold = hold;
    status->left_stick = {state.left_x, state.left_y};
    status->right_stick = {state.right_x, state.right_y};
    // A GamePad lying flat and still: gravity on -Z (in g), identity frame.
    status->acceleration = {0.0f, 0.0f, -1.0f};
    status->acc_magnitude = 1.0f;
    status->direction[0] = {1.0f, 0.0f, 0.0f};
    status->direction[1] = {0.0f, 1.0f, 0.0f};
    status->direction[2] = {0.0f, 0.0f, 1.0f};
    // The touch screen, calibrated as VPADGetTPCalibratedPoint gives it (the
    // GamePad's picture as 1280 x 720; the title reads no raw points).
    if (const TouchState touch = scripted_touch().value_or(g_touch); touch.touched) {
        const auto at = [](float f, int size) {
            return static_cast<uint16_t>(std::clamp(static_cast<int>(f * size), 0, size - 1));
        };
        const TouchData data{at(touch.x, 1280), at(touch.y, 720), 1, 0};
        status->touch = status->touch_processed1 = status->touch_processed2 = data;
    }
    status->battery = 0xC0;
    status->volume = 0xFF;
    status->volume_ex = 0xFF;
    if (error) *error = kVpadOk;
    return 1;
}

void VPADSetBtnRepeat(int32_t, float, float) {}
void VPADSetAccParam(int32_t, float, float) {}
int32_t VPADControlMotor(int32_t, uint32_t, uint32_t) { return 0; }
void VPADStopMotor(int32_t) {}

// Touch coordinates come in raw; calibrated output is the 1280x720 screen.
void VPADGetTPCalibratedPoint(int32_t, TouchData* out, const TouchData* in) {
    if (out && in) *out = *in;
}

// --------------------------------------------------------------- padscore
constexpr int32_t kWpadNoController = -1;

uint32_t g_wpad_alloc = 0, g_wpad_free = 0;
uint32_t g_connect_callbacks[7]{};

void WPADRegisterAllocator(uint32_t alloc, uint32_t free) {
    g_wpad_alloc = alloc;
    g_wpad_free = free;
}
void KPADInit() {}
void KPADShutdown() {}
uint32_t KPADSetConnectCallback(uint32_t channel, uint32_t callback) {
    if (channel >= 7) return 0;
    const uint32_t previous = g_connect_callbacks[channel];
    g_connect_callbacks[channel] = callback;
    return previous;
}
// KPADStatus: the Wii Remote's own part (left zero: no Wii Remote), then
// the extension's; a Pro Controller's buttons by WPAD's bits for it.
struct KPADStatus {
    be<uint32_t> hold, trigger, release;
    uint8_t remote[0x50];
    uint8_t extension; // its kind: 0x1F a Pro Controller
    int8_t error;
    uint8_t pos_valid;
    uint8_t format; // WPAD's data format: 22 a Pro Controller's
    be<uint32_t> pro_hold, pro_trigger, pro_release;
    Vec2 left_stick, right_stick;
    be<int32_t> charging, wired;
    uint8_t rest[0x6C];
};
static_assert(sizeof(KPADStatus) == 0xF0 && offsetof(KPADStatus, extension) == 0x5C &&
              offsetof(KPADStatus, pro_hold) == 0x60 && offsetof(KPADStatus, left_stick) == 0x6C);
constexpr int32_t kKpadOk = 0;
constexpr int32_t kKpadNoController = -2;
constexpr uint8_t kExtensionPro = 0x1F;
constexpr uint8_t kFormatPro = 22;

// The GamePad's buttons as a Pro Controller's (WPAD_PRO_*).
uint32_t pro_buttons(uint32_t vpad_buttons) {
    static constexpr std::pair<uint32_t, uint32_t> kBits[] = {
        {vpad::kUp, 0x0001},     {vpad::kLeft, 0x0002},   {vpad::kZR, 0x0004},     {vpad::kX, 0x0008},
        {vpad::kA, 0x0010},      {vpad::kY, 0x0020},      {vpad::kB, 0x0040},      {vpad::kZL, 0x0080},
        {vpad::kR, 0x0200},      {vpad::kPlus, 0x0400},   {vpad::kHome, 0x0800},   {vpad::kMinus, 0x1000},
        {vpad::kL, 0x2000},      {vpad::kDown, 0x4000},   {vpad::kRight, 0x8000},  {vpad::kStickR, 0x10000},
        {vpad::kStickL, 0x20000},
    };
    uint32_t pro = 0;
    for (const auto& [from, to] : kBits) {
        if (vpad_buttons & from) pro |= to;
    }
    return pro;
}

int32_t KPADReadEx(int32_t channel, KPADStatus* status, uint32_t count, be<int32_t>* error) {
    std::lock_guard lock(g_input_mutex);
    const bool valid = channel >= 0 && channel < kProControllers;
    const bool scripted = valid && script().pro[channel];
    if (!valid || !(g_pro[channel] || scripted) || status == nullptr || count == 0) {
        if (valid) g_pro_reads[channel] = {};
        if (error) *error = kKpadNoController;
        return 0;
    }
    // (Movement as on the GamePad: each player's D-pad and stick agree the same way.)
    GamepadState pad = g_pro[channel].value_or(GamepadState{});
    pad.buttons |= scripted_buttons(channel + 1);
    pad = movement_state(pad);
    ProReads& r = g_pro_reads[channel];
    uint32_t hold = pro_buttons(pad.buttons);
    const bool settled = r.connected >= kSettleReads;
    if (!settled) {
        r.latched |= hold;
        hold = 0;
        if (++r.connected == kSettleReads && r.latched) r.latched_reads = kHeldReads;
    } else if (r.latched_reads > 0) {
        hold |= r.latched;
        if (--r.latched_reads == 0) r.latched = 0;
    }
    std::memset(status, 0, sizeof(KPADStatus));
    status->extension = kExtensionPro;
    status->format = kFormatPro;
    status->pro_hold = hold;
    status->pro_trigger = hold & ~r.previous;
    status->pro_release = r.previous & ~hold;
    r.previous = hold;
    if (settled) {
        status->left_stick = {pad.left_x, pad.left_y};
        status->right_stick = {pad.right_x, pad.right_y};
    }
    status->wired = 1;
    if (error) *error = kKpadOk;
    return 1;
}

int32_t WPADProbe(int32_t, be<uint32_t>* type) {
    if (type) *type = 0xFD; // no device
    return kWpadNoController;
}
void WPADRead(int32_t, uint8_t* status) {
    if (status) std::memset(status, 0, 0x2A);
}
int32_t WPADSetDataFormat(int32_t, uint32_t) { return kWpadNoController; }
uint32_t WPADGetLatestIndexInBuf(int32_t) { return 0; }
void WPADSetAutoSamplingBuf(int32_t, uint32_t, uint32_t) {}
void WPADControlMotor(int32_t, uint32_t) {}
bool WPADIsMotorEnabled() { return true; }
int32_t WPADEnableURCC(int32_t) { return 0; }
void WPADDisconnect(int32_t) {}
int32_t WPADControlDpd(int32_t, uint32_t, uint32_t) { return kWpadNoController; }
void KPADEnableDPD(int32_t) {}
void KPADDisableDPD(int32_t) {}
void WPADClampStick(int32_t, uint32_t, uint32_t) {}
void WPADClampTrigger(int32_t, uint32_t, uint32_t) {}

} // namespace

void set_gamepad_state(const GamepadState& state) {
    std::lock_guard lock(g_input_mutex);
    g_gamepad = state;
}

ScriptedHostInput scripted_host_input() {
    ScriptedHostInput input{};
    scripted_spans(ScriptedSpan::kMouse, [&](const ScriptedSpan& s, float f) {
        input.mouse = std::array<float, 2>{s.x0 + (s.x1 - s.x0) * f, s.y0 + (s.y1 - s.y0) * f};
    });
    scripted_spans(ScriptedSpan::kStick, [&](const ScriptedSpan& s, float) {
        input.pad.right_x = s.x0;
        input.pad.right_y = s.y0;
    });
    scripted_spans(ScriptedSpan::kHold, [&](const ScriptedSpan& s, float) { input.pad.buttons |= s.button; });
    return input;
}

void set_touch_state(const TouchState& touch) {
    std::lock_guard lock(g_input_mutex);
    g_touch = touch;
}

void set_pro_controller_states(const std::array<std::optional<GamepadState>, kProControllers>& states) {
    std::lock_guard lock(g_input_mutex);
    g_pro = states;
}

void arm_select_chord(bool partner_held) {
    std::lock_guard lock(g_input_mutex);
    g_chord.armed_until = Clock::now() + kChordArmed;
    g_chord.partner = partner_held;
    ++g_chord.armings;
}

void set_input_step(uint32_t every) {
    std::lock_guard lock(g_input_mutex);
    g_step_until = std::chrono::steady_clock::now() + kStepLasts;
    if (every == g_step_every) return;
    g_step_every = std::max(every, 1u);
    g_step_reads = 0;
    if (g_step_every == 1) g_step_delivered = true;
}

bool input_step_delivered() {
    std::lock_guard lock(g_input_mutex);
    return g_step_delivered;
}

bool take_select_chord() {
    std::lock_guard lock(g_input_mutex);
    const bool chord = g_chord.chord && Clock::now() - g_chord.chord_at < kChordTaken;
    g_chord.chord = false;
    return chord;
}

CAFE_EXPORT(vpad, VPADInit, VPADInit);
CAFE_EXPORT(vpad, VPADRead, VPADRead);
CAFE_EXPORT(vpad, VPADSetBtnRepeat, VPADSetBtnRepeat);
CAFE_EXPORT(vpad, VPADSetAccParam, VPADSetAccParam);
CAFE_EXPORT(vpad, VPADControlMotor, VPADControlMotor);
CAFE_EXPORT(vpad, VPADStopMotor, VPADStopMotor);
CAFE_EXPORT(vpad, VPADGetTPCalibratedPoint, VPADGetTPCalibratedPoint);

CAFE_EXPORT(padscore, WPADRegisterAllocator, WPADRegisterAllocator);
CAFE_EXPORT(padscore, KPADInit, KPADInit);
CAFE_EXPORT(padscore, KPADShutdown, KPADShutdown);
CAFE_EXPORT(padscore, KPADSetConnectCallback, KPADSetConnectCallback);
CAFE_EXPORT(padscore, KPADReadEx, KPADReadEx);
CAFE_EXPORT(padscore, WPADProbe, WPADProbe);
CAFE_EXPORT(padscore, WPADRead, WPADRead);
CAFE_EXPORT(padscore, WPADSetDataFormat, WPADSetDataFormat);
CAFE_EXPORT(padscore, WPADGetLatestIndexInBuf, WPADGetLatestIndexInBuf);
CAFE_EXPORT(padscore, WPADSetAutoSamplingBuf, WPADSetAutoSamplingBuf);
CAFE_EXPORT(padscore, WPADControlMotor, WPADControlMotor);
CAFE_EXPORT(padscore, WPADIsMotorEnabled, WPADIsMotorEnabled);
CAFE_EXPORT(padscore, WPADEnableURCC, WPADEnableURCC);
CAFE_EXPORT(padscore, WPADDisconnect, WPADDisconnect);
CAFE_EXPORT(padscore, WPADControlDpd, WPADControlDpd);
CAFE_EXPORT(padscore, KPADEnableDPD, KPADEnableDPD);
CAFE_EXPORT(padscore, KPADDisableDPD, KPADDisableDPD);
CAFE_EXPORT(padscore, WPADClampStick, WPADClampStick);
CAFE_EXPORT(padscore, WPADClampTrigger, WPADClampTrigger);

} // namespace cafe::os
