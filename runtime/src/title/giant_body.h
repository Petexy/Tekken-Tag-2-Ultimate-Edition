#pragma once

// A giant's body in the fight (Tekken 8's Azazel, kept at his own size: his
// skeleton 1.8 times a man's): an added fighter whose character.ini says
// `body = S` is S times as big as a man to the fight's bodies too, as
// Mushroom Battle makes a grown fighter, his model left as it is. See
// giant_body.cpp.

#include <cstdint>

namespace cafe::title::giant_body {

// The added fighter `slot` has a body `scale` times a man's (1: as TTT2
// sizes its own fighters).
void configure(int slot, float scale);

// A fighter's body scale (1 for anybody without one).
float scale_of(uint32_t player);

// After the title sized a fighter's 14 hurt spheres (sub_03D6B9F4) or its 8
// push spheres (sub_03D6B544): a giant's grow with him.
void hurt_spheres_sized(uint8_t* base, uint32_t player);
void push_spheres_sized(uint8_t* base, uint32_t player);

} // namespace cafe::title::giant_body
