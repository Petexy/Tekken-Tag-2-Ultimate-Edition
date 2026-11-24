#pragma once

// CUSTOMIZE > PAINT on a computer. The title paints only from the Wii U
// GamePad's touch screen (its pen and eraser draw where the stylus touches
// the picture, which the GamePad shows as the TV does in this mode). The
// host gives it a touch screen (host::on_touch_screen): the mouse over the
// window's picture, or a cursor a gamepad's stick moves; this says when the
// mode is open, so that clicks touch nothing elsewhere, and has the
// renderer copy the targets the strokes are drawn into back to guest
// memory meanwhile, where the title reads them to keep and save them.

namespace cafe::title {

// After the image load, before the title runs.
void prepare_paint();

} // namespace cafe::title
