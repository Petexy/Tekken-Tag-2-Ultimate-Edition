#pragma once

// Hooks the layers above GX2 may set at start-up. Unset (null), GX2 behaves
// as the console's.

#include <cstdint>

namespace cafe::gx2 {

// GX2SetAlphaTestReg's reference (its float's bits) -> the one the draw
// takes. Null: the reference as given.
using AlphaRefHook = uint32_t (*)(uint32_t ref);
void set_alpha_ref_hook(AlphaRefHook hook);

} // namespace cafe::gx2
