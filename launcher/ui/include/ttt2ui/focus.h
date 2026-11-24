// Spatial navigation between focusable rectangles (the Tag Split mock's rules, made generic):
// - only items whose centre lies in the direction count (more than 6 points past the current centre);
// - "beam" rule: an item overlapping the current one across the move axis wins over anything outside it;
// - staircase rule: left/right skips an item above/below that does not overlap vertically, unless it is close;
// - up/down prefer staying in the same group (e.g. the crimson list vs the blue readout): crossing costs 3000;
// - explicit neighbours override all of it (handled by the caller), disabled items are focusable;
// - optional wrapping when nothing lies in the direction.
#pragma once

#include <string>
#include <vector>

#include "ttt2ui/geometry.h"

namespace ttt2::ui {

enum class Dir { Up, Down, Left, Right };

struct FocusItem {
    Rect rect;      // where it is now (points, screen)
    int group = 0;  // items of another group are reached by up/down only when nothing else is there
};

struct WrapRule {
    bool horizontal = false;  // Right past the last item goes to the first of the row, and back
    bool vertical = false;    // Down past the last goes to the top of the column, and back
};

// Index of the item to go to from `current` in `dir`, or -1 (nothing there).
int navigate(const std::vector<FocusItem>& items, int current, Dir dir, WrapRule wrap = {});
// The item nearest to `rect` (centre distance, items overlapping it first): focus lost because its item went away.
int nearest(const std::vector<FocusItem>& items, const Rect& rect);

}  // namespace ttt2::ui
