#pragma once

// The fight camera with a giant in the fight (Tekken 8's Azazel: horns at
// 4.2 m): an added fighter whose character.ini says `camera = H` is framed
// whole, H millimetres above his lowest point (his feet), with his
// opponent. See fight_camera.cpp.

namespace cafe::title::fight_camera {

// The added fighter `slot` is `height` mm tall to the fight camera, from his
// body's lowest point (his feet's spheres) to his top (0: as TTT2 frames
// its own fighters).
void configure(int slot, float height);

} // namespace cafe::title::fight_camera
