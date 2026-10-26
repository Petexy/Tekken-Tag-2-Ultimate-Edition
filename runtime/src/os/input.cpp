// Controllers: the Wii U GamePad (vpad) is the one input device; its state
// comes from the host (set_gamepad_state, fed by the window layer). No Wii
// Remotes or Pro Controllers are connected (padscore: KPAD/WPAD).

#include "kernel.h"

#include "cafe/export.h"
#include "cafe/input.h"
#include "cafe/vfs.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

namespace cafe::os {
namespace {

std::mutex g_input_mutex;
GamepadState g_gamepad{};
uint32_t g_previous_hold = 0;

// TTT2_INPUT_SCRIPT="15:plus,20.5:a,22:down" presses each button at the given
// second after start-up, for unattended runs: for a fifth of a second and at
// least kHeldReads reads of the pad, then released for kReleasedReads reads
// before the same button is pressed again, so a press is seen even when a frame
// stalls (loading). An item "@3dbb1771" waits until the title reads the archive
// entry with that name hash (the character select screen's layout, say): the
// times after it count from then, and presses before it that have not come yet
// are dropped, so a script does not drift with loading times.
constexpr int kHeldReads = 4;
constexpr int kReleasedReads = 4;

struct ScriptedPress {
    double at;
    uint32_t button;
    size_t segment; // the anchors before it
    int reads = -1; // reads of the pad while held; -1: not pressed yet
};

struct Script {
    std::vector<ScriptedPress> presses;
    std::vector<uint32_t> anchors;
    std::mutex mutex;
    std::vector<double> starts; // each segment's start, after start-up; < 0 while waiting
    std::vector<std::pair<uint32_t, int>> released; // button -> reads since its last scripted release
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
            const std::string name = item.substr(colon + 1);
            for (const auto& [n, bit] : kNames) {
                if (name == n) {
                    script.presses.push_back({std::atof(item.substr(0, colon).c_str()), bit, script.anchors.size()});
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

uint32_t scripted_buttons() {
    static Script& script = load_script();
    if (script.presses.empty()) return 0;
    const double t = seconds_since(script.start);
    std::lock_guard lock(script.mutex);
    auto released_reads = [&](uint32_t button) -> int& {
        for (auto& [b, n] : script.released) {
            if (b == button) return n;
        }
        script.released.push_back({button, kReleasedReads});
        return script.released.back().second;
    };
    uint32_t buttons = 0;
    for (ScriptedPress& p : script.presses) {
        if (p.reads >= kHeldReads) continue; // done
        const double start = script.starts[p.segment];
        const bool next_reached = p.segment + 1 < script.starts.size() && script.starts[p.segment + 1] >= 0.0;
        if (p.reads < 0) {
            if (start < 0.0 || next_reached || t < start + p.at) continue;
            if (released_reads(p.button) < kReleasedReads || (buttons & p.button)) continue; // wait for a release
            p.reads = 0;
        }
        buttons |= p.button;
        if (++p.reads >= kHeldReads && t < start + p.at + 0.2) p.reads = kHeldReads - 1; // hold the fifth second
        if (p.reads >= kHeldReads) released_reads(p.button) = -1;
    }
    for (auto& [b, n] : script.released) {
        if (!(buttons & b) && n < kReleasedReads) ++n;
    }
    return buttons;
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
    state.buttons |= scripted_buttons();
    state = movement_state(state);
    const uint32_t hold = gate_select(state.buttons);
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
int32_t KPADReadEx(int32_t, uint32_t, uint32_t, be<int32_t>* error) {
    if (error) *error = kWpadNoController;
    return 0;
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

void arm_select_chord(bool partner_held) {
    std::lock_guard lock(g_input_mutex);
    g_chord.armed_until = Clock::now() + kChordArmed;
    g_chord.partner = partner_held;
    ++g_chord.armings;
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
