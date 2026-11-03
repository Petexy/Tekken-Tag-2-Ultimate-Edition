#pragma once

#include <algorithm>
#include <cstdint>

namespace cafe::title::damage {

// T7 PC: sub_1407166FA selects Geese (43), then sub_1406FBE60
// indexes this curve with the attacking side's existing combo-hit counter.
// Index 0 is the opener; index 1 is also full damage. This is an extra
// grounded rule, not the native airborne/wall/throw damage calculation.
constexpr uint32_t geese_ground_percent(uint32_t prior_hits) {
    constexpr uint32_t curve[] = {100, 100, 80, 70, 60, 50, 40, 30, 20, 10};
    return curve[std::min(prior_hits, 9u)];
}

constexpr bool ground_hit(uint32_t flags, uint32_t stance) {
    // EU v16 sub_03AE1704: high bit takes the non-standard damage path;
    // bit 21 takes airborne scaling; stances 18/19 take downed scaling.
    return !(flags & (0x80000000u | 0x00200000u)) && stance != 18 && stance != 19;
}

// A hit-grab's flat throw damage continues its initiating hit's scaling, only
// for the same attacker, for every deal of that throw (a throw can deal twice).
// A new collision on the defender invalidates it.
struct HitGrabContinuation {
    uint32_t owner = 0, percent = 100;
    void clear() { owner = 0; percent = 100; }
    void remember(uint32_t attacker, uint32_t scale) { owner = attacker; percent = scale; }
    uint32_t of(uint32_t attacker) const { return owner && owner == attacker ? percent : 0; }
};

constexpr int32_t scale_hit(int32_t points, uint32_t percent) {
    // As in T7's damage calculation: truncate, with a one-point minimum
    // for a positive hit. Preserve zero damage and non-damage values.
    return points > 0 ? std::max<int32_t>(1, int64_t{points} * percent / 100) : points;
}

} // namespace cafe::title::damage
