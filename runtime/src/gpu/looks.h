#pragma once

// Looks the title gives one fighter's draws without changing how it draws
// them (title/warp.cpp: Noctis turning blue and dithering away in a warp).
// The title copies the colour it draws a fighter in (four floats, white as
// it is) into the constants of each of the fighter's draws; while a look
// is on, the low byte of the red, green and blue words there holds the
// look's number (a change of a few millionths: nothing to see), and the
// renderer gives those draws the look (gpu/vulkan/draw.cpp). The title's
// fighter shaders keep that colour in uniform block 8: the vertex shader's
// at byte 640, the pixel shader's at byte 160.
//
// A look is set from the title's thread and read by the renderer's after
// the title drew with it: a number is given again only after kNumbers - 1
// others, long after any draw that carried it.

#include <cstdint>

namespace cafe::gpu::looks {

// A look: how much of the fighter is drawn (an ordered dither of the
// title's pixels), how much the warp's light still shows (from its full
// sky blue, to grey while fading out and through indigo to the fighter's
// own colours while fading in), how strongly the edges light up, and flags.
constexpr uint32_t kOpacity = 0, kGlow = 8, kRim = 16; // bytes of the look, 0-255
constexpr uint32_t kAppearing = 1u << 24;              // fading in (else out)
constexpr uint32_t kHidden = 1u << 25;                 // not drawn
constexpr uint32_t kStill = 1u << 26;                  // no motion blur (it has just come from elsewhere)

constexpr uint32_t kColourBlock = 8, kVertexColourAt = 640, kPixelColourAt = 160;
constexpr uint32_t kNumbers = 256; // (0 is none)

// A number for `look` (the previous one again if its look is the same).
uint32_t number(uint32_t look, uint32_t previous);
// The look a number stands for (0: none).
uint32_t look(uint32_t number);

// The red, green and blue words (the bits of floats) with `number` marked,
// and the number marked in them, else 0.
void mark(uint32_t rgb[3], uint32_t number);
uint32_t marked(const uint32_t rgb[3]);

// Whether any look is on (the renderer looks for numbers only then).
void set_active(bool on);
bool active();

} // namespace cafe::gpu::looks
