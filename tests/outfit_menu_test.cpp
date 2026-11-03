#include "title/outfit_menu.h"

#include <cstdio>
#include <cstdlib>

namespace outfit = cafe::title::outfit_menu;

void check(bool ok, const char* message) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

int main() {
    // Base/alias collisions must be rejected in either discovery order.
    for (bool reversed : {false, true}) {
        outfit::CodeOwners codes;
        codes.add(reversed ? 1 : 0, "kza");
        codes.add(reversed ? 0 : 1, "kza");
        codes.add(2, "nsc");
        check(codes.conflicts(0) && codes.conflicts(1), "reject both duplicate owners");
        check(!codes.conflicts(2), "unrelated fighter remains available");
    }

    outfit::BodySelections bodies;
    bodies.remember(0, 74, 0x10000);
    bodies.remember(1, 74, 0x10001);
    check(bodies.resolve(0, 74) == 0x10000, "first mirror outfit");
    check(bodies.resolve(1, 74) == 0x10001, "second mirror outfit stays independent");
    // Menu return bypasses the loader, then another match reuses the slot.
    check(bodies.resolve(0, 60) == 0, "menu recipe does not inherit the fighter body");
    check(bodies.resolve(0, 74) == 0, "menu transition clears the stale selection");
    bodies.remember(0, 74, 0x10002);
    check(bodies.resolve(0, 74) == 0x10002, "new match can choose another outfit");
    bodies.remember(0, 0, 0);
    check(bodies.resolve(0, 13) == 0, "native fighter clears the selection");
    check(bodies.resolve(5, 74) == 0, "out-of-range slot has no selection");
    bodies.remember(0, 0, 0x20000); // Native Paul's identity is zero, which is still a valid owner.
    bodies.remember(1, 0, 0x20001);
    check(bodies.resolve(0, 0) == 0x20000, "native Paul keeps the first mirror outfit");
    check(bodies.resolve(1, 0) == 0x20001, "native Paul's other side has an independent outfit");
    check(bodies.resolve(0, 13) == 0, "changing away from Paul clears his body");
    outfit::NativePage page{3, 10};
    check(page.pages() == 2 && page.count() == 14, "first page stays within the buffer");
    page.turn(true);
    check(page.offset() == 6 && page.visible() == 4 && page.count() == 12, "short last page keeps five custom slots");
    check(page.outfit(4) == 6 && page.outfit(7) == 9, "last page selects absolute body identities");
    check(page.outfit(8) == 10 && page.outfit(3) == 10, "custom and original slots do not inherit a body");
    page.turn(true);
    check(page.page == 0, "forward pages wrap");
    page.turn(false);
    check(page.page == 1, "previous pages wrap");
    outfit::NativePage other{3, 10};
    check(other.page == 0, "mirror players keep separate pages");
    for (size_t originals : {2u, 3u, 4u, 5u}) {
        outfit::NativePage varied{originals, 17};
        for (size_t p = 0; p < varied.pages(); ++p) {
            check(varied.count() <= 14, "every roster page fits the guest buffer");
            check(varied.count() - originals - varied.visible() == 5, "every roster page keeps five custom slots");
            for (size_t i = 0; i < varied.visible(); ++i)
                check(varied.outfit(static_cast<uint32_t>(originals + i + 1)) == varied.offset() + i,
                    "roster page preserves absolute body identity");
            varied.turn(true);
        }
        check(varied.page == 0, "different native slot counts wrap correctly");
    }
    outfit::NativePage many{3, 100};
    check(many.pages() == 17, "page layout supports future sources beyond the current catalog");
    check(outfit::native_outfit_index(3, 6, 4, 0x033E3B30) == 0, "first appended native costume");
    check(outfit::native_outfit_index(3, 6, 9, 0x033E3BDC) == 5, "sixth appended native costume");
    for (uint32_t choice : {0u, 1u, 2u, 3u, 10u, 11u, 12u, 13u, 14u})
        check(outfit::native_outfit_index(3, 6, choice, 0x033E3B30) == 6,
              "native costumes and customization never select an imported body");
    check(outfit::native_style(10, 0x033E2000, 2) == 2, "opening keeps the menu request");
    check(outfit::native_style(10, 0x033E3B30, 10) == 1, "confirmation normalizes native style");
    check(outfit::needs_reload(1, 2, false, 160, 160), "new outfit reloads a completed body");
    check(!outfit::needs_reload(1, 2, true, 160, 160), "pending body is not repeatedly invalidated");
    std::puts("Outfit namespace and lifecycle tests passed");
}
