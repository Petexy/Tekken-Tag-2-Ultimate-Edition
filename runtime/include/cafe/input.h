#pragma once

// Host-side controller states, set by the window/input layer and read by the
// game: the GamePad's through VPADRead, the Pro Controllers' through KPAD.

#include <array>
#include <cstdint>
#include <optional>

namespace cafe::os {

// VPAD button bits, as the game sees them.
namespace vpad {
constexpr uint32_t kA = 0x8000, kB = 0x4000, kX = 0x2000, kY = 0x1000;
constexpr uint32_t kLeft = 0x0800, kRight = 0x0400, kUp = 0x0200, kDown = 0x0100;
constexpr uint32_t kZL = 0x0080, kZR = 0x0040, kL = 0x0020, kR = 0x0010;
constexpr uint32_t kPlus = 0x0008, kMinus = 0x0004, kHome = 0x0002;
constexpr uint32_t kStickR = 0x00020000, kStickL = 0x00040000;
// VPAD_STICK_*_EMULATION_*: direction flags alongside the analog axes.
// https://github.com/devkitPro/wut/blob/master/include/vpad/input.h
constexpr uint32_t kStickLLeft = 0x40000000, kStickLRight = 0x20000000;
constexpr uint32_t kStickLUp = 0x10000000, kStickLDown = 0x08000000;
constexpr uint32_t kStickRLeft = 0x04000000, kStickRRight = 0x02000000;
constexpr uint32_t kStickRUp = 0x01000000, kStickRDown = 0x00800000;
} // namespace vpad

struct GamepadState {
    uint32_t buttons;
    float left_x, left_y;   // -1..1, up positive
    float right_x, right_y;
};

void set_gamepad_state(const GamepadState& state);

// The GamePad's touch screen: touched or not, and where, as a point of the
// GamePad's picture (0 to 1 from its left edge, 0 to 1 from its top edge).
// The host sets it (host/window.cpp: the mouse over the window's picture,
// or the cursor a gamepad's stick moves); TTT2_INPUT_SCRIPT's touch items
// stand in for it while they last.
struct TouchState {
    bool touched = false;
    float x = 0.0f, y = 0.0f;
};
void set_touch_state(const TouchState& touch);

// TTT2_INPUT_SCRIPT's items for the host's own input, to test it end to
// end: the mouse with its left button held at a point of the window
// (fractions of its size), and a pad's buttons and right stick held. The
// host takes them as it takes the keyboard's and the mouse's.
struct ScriptedHostInput {
    GamepadState pad{};
    std::optional<std::array<float, 2>> mouse;
};
ScriptedHostInput scripted_host_input();

// The Pro Controllers on KPAD's channels 0-3 (buttons by the GamePad's bits);
// a channel without a state has none connected.
constexpr int kProControllers = 4;
void set_pro_controller_states(const std::array<std::optional<GamepadState>, kProControllers>& states);

// - (Select) pressed together with another button, for a mode that gives the
// chord a meaning of its own (title/practice.cpp: Practice's position reset).
// The mode arms it on every frame the chord can happen, saying whether the
// other button is held. While armed, a press of - waits eight of those frames
// before the game sees it; if the other button is held by then, the press is
// the chord's and the game never sees it. take_select_chord() is true once
// for each chord.
void arm_select_chord(bool partner_held);
bool take_select_chord();

// Stepped input, for a game that runs its frame every `every` reads of the
// pad only (title/practice.cpp: Practice's slow motion): the game sees the
// pad change on every `every`-th read, with whatever was pressed since
// (a press made and let go in between counts as held for that read); the
// reads in between show it as it was. 1: every read, as usual.
// input_step_delivered() says whether the last read was one that changed.
void set_input_step(uint32_t every);
bool input_step_delivered();

} // namespace cafe::os
