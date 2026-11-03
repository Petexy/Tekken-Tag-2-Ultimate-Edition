#include "title/damage_scaling.h"
#include <array>
#include <cstdio>
#include <cstdlib>
using namespace cafe::title::damage;
void check(bool ok) { if (!ok) std::abort(); }
int main() {
    // Values recovered from the local T7 executable's actual jump table.
    constexpr std::array<unsigned, 12> t7 = {100,100,80,70,60,50,40,30,20,10,10,10};
    for (unsigned i = 0; i < t7.size(); ++i) check(geese_ground_percent(i) == t7[i]);
    check(geese_ground_percent(0xffffffffu) == 10);
    check(ground_hit(0, 0));
    check(!ground_hit(0x80000000u, 0)); // blocked/non-standard damage
    check(!ground_hit(0x00200000u, 0)); // native airborne path
    check(!ground_hit(0, 18) && !ground_hit(0, 19)); // native downed paths
    check(ground_hit(0x100, 0)); // unrelated hit flags preserved
    check(scale_hit(20,100) == 20); // full standalone damage
    check(scale_hit(17,80) == 13); // integer truncation
    check(scale_hit(1,10) == 1); // minimum positive hit
    check(scale_hit(0,10) == 0 && scale_hit(-4,10) == -4);
    // First six grounded damage values read directly from the supplied clip.
    const int original[] = {20,16,17,16,13,27};
    int sum = 0;
    for (unsigned i=0; i<6; ++i) sum += scale_hit(original[i], geese_ground_percent(i));
    check(sum == 80); // 20 + 16 + 13 + 11 + 7 + 13; formerly 109
    HitGrabContinuation warp;
    check(warp.of(0x1000) == 0); // no initiating hit: ordinary throw stays native
    warp.remember(0x1000, 45);
    check(scale_hit(25, warp.of(0x1000)) == 11);
    check(scale_hit(10, warp.of(0x1000)) == 4); // the same throw's second deal
    warp.remember(0x1000, 60);
    check(warp.of(0x2000) == 0); // another attacker/partner cannot inherit it
    warp.remember(0x1000, 50);
    warp.clear(); // intervening hit or grounded initiation
    check(warp.of(0x1000) == 0);
    std::puts("Grounded scaling and hit-grab continuation: PASS");
}
