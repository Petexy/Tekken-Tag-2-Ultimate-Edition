#pragma once

// Practice: frame data and combat information, a panel for each side at the
// bottom of the screen (title/framedata.cpp).

#include <cstdint>
#include <string>
#include <vector>

namespace cafe::title::framedata {

// The fighters' frame of a Practice round has run (not while the pause menu
// is open): `fighters` are the two sides' fighters in play.
void fighters_frame(uint8_t* base, const uint32_t fighters[2]);
// The position reset: the session's totals start over.
void reset();
// The ULTIMATE SETTINGS submenu's settings, as on (1) or off (0): the
// frame data panels at all, 1P's, 2P's, the fighters coloured by frame
// advantage, the hitboxes, the camera from above; and the slow motion: 0
// off, 1 half speed, 2 a quarter.
enum Setting { kPanels, kPanel1P, kPanel2P, kAdvantageColours, kHitboxes, kTopCamera, kSlowMotion, kSettings };
uint32_t setting(Setting s);
void set_setting(Setting s, uint32_t value);
// The right edge of the input history's column (on the left) while it
// shows, else 0.
float history_right();
// The line the panels stand on (on the TV image), above the title's hints
// and DAMAGE INFO 2's bars (title/gauge.cpp's gauges keep above it too).
constexpr float kPanelsBottom = 634;
// A message of the port's own in a box at the top of the screen, in the title's fonts, for `seconds`: for what the
// title has no message of its own for (a customization save the disk refused). From a guest thread, in any mode
// (Practice's panels, which share the layer, replace it).
void notice(const std::vector<std::string>& lines, double seconds);

} // namespace cafe::title::framedata
