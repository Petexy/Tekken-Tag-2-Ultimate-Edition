#include "title/win_pose.h"

#include <cstdio>
#include <cstdlib>
#include <map>
#include <utility>
#include <vector>

namespace win_pose = cafe::title::win_pose;

void check(bool ok, const char* message) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

int main() {
    // The parts of the short team win, by the names a moveset keeps from its donor (made-up codes).
    check(win_pose::is_part("ab_wem_1") && win_pose::is_part("ab_wes_2") && win_pose::is_part("xy_wem_3"), "parts");
    check(!win_pose::is_part("ab_wnm_1") && !win_pose::is_part("ab_srm") && !win_pose::is_part("Ab_sKAM00_") &&
              !win_pose::is_part(""),
          "other moves are not");

    // Made-up players 100 (the winner) and 200 (its partner), moves 1.. .
    std::map<uint32_t, uint32_t> move = {{100, 1}, {200, 5}};
    std::vector<std::pair<uint32_t, uint32_t>> given;
    const auto move_of = [&](uint32_t player) { return move[player]; };
    const auto give = [&](uint32_t receiver, uint32_t value) { given.emplace_back(receiver, value); };
    win_pose::Handovers h;
    check(h.empty(), "nothing held at first");
    h.hold(100, 1, 200, 1);
    h.hold(100, 1, 200, 1); // (a property runs once per pass)
    h.deliver(move_of, give);
    check(given.empty() && !h.empty(), "held while the sender's part goes on");
    move[100] = 2; // the winner's pose is over: it waits
    h.deliver(move_of, give);
    check(given.size() == 1 && given[0] == std::make_pair(200u, 1u) && h.empty(), "given once the part is over");
    h.deliver(move_of, give);
    check(given.size() == 1, "and only once");
    // The partner's part hands back the same way; both can be held at a time.
    move[200] = 6;
    h.hold(200, 6, 100, 1);
    h.hold(100, 2, 200, 7);
    move[200] = 7;
    h.deliver(move_of, give);
    check(given.size() == 2 && given[1] == std::make_pair(100u, 1u) && !h.empty(), "one given, the other still held");
    // A scene cut short owes nothing to the next fight.
    h.clear();
    move[100] = 3;
    h.deliver(move_of, give);
    check(given.size() == 2 && h.empty(), "cleared");

    std::puts("win_pose_test: ok");
    return 0;
}
