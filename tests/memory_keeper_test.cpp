// The rule of the thread that keeps the memory the GPU reads on huge pages
// (runtime/src/memory_keeper.h), played through with made-up kernel answers:
// pinned blocks are left alone after three passes and the passes slow down;
// blocks made keep the passes a second apart; each kind of failure is told
// once; a block seen on a huge page gets a fresh start.
#include "memory_keeper.h"

#include <cstdio>
#include <functional>
#include <set>
#include <vector>

using cafe::keeper::Answer;
using cafe::keeper::Plan;
namespace keeper = cafe::keeper;

namespace {

int failures = 0;
#define CHECK(x)                                                                                                       \
    do {                                                                                                               \
        if (!(x)) {                                                                                                    \
            std::fprintf(stderr, "%s:%d: failed: %s\n", __FILE__, __LINE__, #x);                                       \
            ++failures;                                                                                                \
        }                                                                                                              \
    } while (0)

constexpr uintptr_t kBlock = 2u << 20;
uintptr_t block(int n) { return 0x10000000u + static_cast<uintptr_t>(n) * kBlock; }

// A pass as memory.cpp makes it with the page map: the reserve holds up to 32
// blocks and is filled for the blocks asked with one; a block asked with one
// needs a reserve block (none left: the block waits for the next pass).
struct Pass {
    size_t asked = 0, with_reserve = 0, filled = 0;
    double delay = 0;
    unsigned news = 0;
};
struct Kernel {
    std::set<uintptr_t> missing;
    std::function<Answer(uintptr_t)> answer; // what a call on a missing block gets
    size_t reserve_room = 32;                // reserve blocks the kernel can fill a pass
};
Pass pass(Plan& plan, Kernel& kernel) {
    Pass out;
    const std::vector<uintptr_t> missing(kernel.missing.begin(), kernel.missing.end());
    const std::vector<uintptr_t> to_try = plan.begin(missing);
    size_t want = 0;
    for (uintptr_t b : to_try) want += plan.reserve_for(b);
    size_t ready = std::min({want, size_t{32}, kernel.reserve_room});
    out.filled = ready;
    if (ready < want && kernel.reserve_room < 32) plan.reserve_short();
    for (uintptr_t b : to_try) {
        if (plan.reserve_for(b)) {
            if (ready == 0) continue;
            --ready;
            ++out.with_reserve;
        }
        ++out.asked;
        const Answer a = kernel.answer(b);
        if (a == Answer::made) kernel.missing.erase(b);
        if (!plan.answer(b, a, 1.0)) break;
    }
    out.delay = plan.end();
    out.news = plan.news();
    return out;
}

// Passes over the given (simulated) seconds: totals.
struct Run {
    size_t passes = 0, asked = 0, with_reserve = 0, filled = 0;
    unsigned told = 0;
    int lines = 0;
    double longest_delay = 0;
};
Run run(Plan& plan, Kernel& kernel, double seconds) {
    Run out;
    for (double t = 0; t < seconds * 1000;) {
        const Pass p = pass(plan, kernel);
        ++out.passes;
        out.asked += p.asked;
        out.with_reserve += p.with_reserve;
        out.filled += p.filled;
        for (unsigned k = p.news; k != 0; k &= k - 1) ++out.lines;
        out.told |= p.news;
        out.longest_delay = std::max(out.longest_delay, p.delay);
        t += p.delay;
    }
    return out;
}

void pinned_blocks_are_left_alone() {
    // Three blocks a driver pinned (the checker's probe): every call busy.
    Plan plan;
    Kernel kernel{{block(0), block(1), block(2)}, [](uintptr_t) { return Answer::busy; }};
    Pass p = pass(plan, kernel);
    CHECK(p.asked == 3 && p.with_reserve == 3 && p.delay == 1000 && p.news == 0);
    p = pass(plan, kernel); // turned down before: asked without the reserve
    CHECK(p.asked == 3 && p.with_reserve == 0 && p.filled == 0 && p.delay == 2000 && p.news == 0);
    p = pass(plan, kernel); // the third time: left alone, nothing left to ask
    CHECK(p.asked == 3 && p.news == keeper::kBusy && plan.settled() && !plan.whole() && p.delay == Plan::kCalmMs);
    CHECK(plan.left() == 3 && plan.left(keeper::kBusy) == 3 && plan.left(keeper::kRefused) == 0);
    p = pass(plan, kernel);
    CHECK(p.asked == 0 && p.filled == 0 && p.news == 0 && plan.settled() && p.delay == Plan::kCalmMs);
    // A minute of it: nine calls in all, the reserve filled once, one line.
    Plan minute;
    Kernel again{{block(0), block(1), block(2)}, [](uintptr_t) { return Answer::busy; }};
    const Run r = run(minute, again, 60);
    CHECK(r.asked == 9 && r.with_reserve == 3 && r.filled == 3 && r.lines == 1 && r.told == keeper::kBusy);
    CHECK(r.longest_delay <= Plan::kLongestMs && r.passes <= 20);
}

void many_pinned_blocks_go_without_the_reserve() {
    // 400 pinned blocks (a driver that pins all it imports, on a PC short of
    // memory at the start): the reserve is filled once, for the first pass.
    Plan plan;
    Kernel kernel;
    for (int i = 0; i < 400; ++i) kernel.missing.insert(block(i));
    kernel.answer = [](uintptr_t) { return Answer::busy; };
    Pass p = pass(plan, kernel);
    CHECK(p.asked == 32 && p.with_reserve == 32 && !plan.with_reserve());
    p = pass(plan, kernel);
    CHECK(p.asked == 400 && p.with_reserve == 0 && p.filled == 0);
    const Run r = run(plan, kernel, 60);
    CHECK(plan.left() == 400 && plan.settled() && r.filled == 0 && r.lines == 1);
    CHECK(r.asked == 400 + 368); // the third call on the first 32 and the second on the rest, then the third on the rest
}

void blocks_made_keep_the_passes_quick() {
    // The good path: memory pressure took 100 blocks; 32 a pass come back.
    Plan plan;
    Kernel kernel;
    for (int i = 0; i < 100; ++i) kernel.missing.insert(block(i));
    kernel.answer = [](uintptr_t) { return Answer::made; };
    double t = 0;
    int passes = 0;
    while (!kernel.missing.empty()) {
        const Pass p = pass(plan, kernel);
        CHECK(p.with_reserve == p.asked && p.news == 0);
        t += p.delay;
        ++passes;
    }
    CHECK(passes == 4 && plan.whole() && t == 3 * Plan::kQuietMs + Plan::kCalmMs);
    // More taken later: a pass puts them back at once.
    for (int i = 10; i < 15; ++i) kernel.missing.insert(block(i));
    const Pass p = pass(plan, kernel);
    CHECK(p.asked == 5 && p.with_reserve == 5 && plan.whole() && p.delay == Plan::kCalmMs);
}

void no_memory_backs_off_and_is_told_once() {
    Plan plan;
    Kernel kernel;
    for (int i = 0; i < 100; ++i) kernel.missing.insert(block(i));
    int calls = 0;
    kernel.answer = [&](uintptr_t) { return ++calls <= 20 ? Answer::made : Answer::no_memory; };
    Pass p = pass(plan, kernel);
    CHECK(p.asked == 21 && p.delay == Plan::kQuietMs && p.news == 0); // 20 made, then no memory: the burst ends
    kernel.reserve_room = 0;                                            // the reserve cannot be filled any more
    const double waits[] = {1000, 2000, 4000, 8000, 8000};
    for (int i = 0; i < 5; ++i) {
        p = pass(plan, kernel);
        CHECK(p.asked == 0 && p.delay == waits[i] && p.news == (i == 0 ? unsigned{keeper::kNoMemory} : 0u));
    }
    kernel.reserve_room = 32; // memory again: back to a second
    kernel.answer = [](uintptr_t) { return Answer::made; };
    p = pass(plan, kernel);
    CHECK(p.asked == 32 && p.delay == Plan::kQuietMs && p.news == 0 && plan.left() == 0);
}

void the_memory_limit_is_no_strike() {
    Plan plan;
    Kernel kernel{{block(0), block(1)}, [](uintptr_t) { return Answer::limit; }};
    for (int i = 0; i < 6; ++i) {
        const Pass p = pass(plan, kernel);
        CHECK(p.asked == 1 && p.news == (i == 0 ? unsigned{keeper::kLimit} : 0u)); // the first call ends the burst
    }
    CHECK(plan.left() == 0 && !plan.settled());
}

void a_busy_block_gets_a_fresh_start() {
    Plan plan;
    int busy_left = 2;
    Kernel kernel{{block(7)}, [&](uintptr_t) { return busy_left-- > 0 ? Answer::busy : Answer::made; }};
    pass(plan, kernel);
    pass(plan, kernel);
    Pass p = pass(plan, kernel); // made on the third try: no strike stays
    CHECK(p.asked == 1 && plan.whole() && plan.left() == 0 && p.news == 0);
    // Left alone, then seen on a huge page (khugepaged made it): forgotten, asked again when it loses it.
    Kernel pinned{{block(3)}, [](uintptr_t) { return Answer::busy; }};
    for (int i = 0; i < 3; ++i) pass(plan, pinned);
    CHECK(plan.left_alone(block(3)) && plan.settled());
    pinned.missing.clear();
    p = pass(plan, pinned);
    CHECK(!plan.left_alone(block(3)) && plan.whole());
    pinned.missing.insert(block(3));
    pinned.answer = [](uintptr_t) { return Answer::made; };
    p = pass(plan, pinned);
    CHECK(p.asked == 1 && p.with_reserve == 1 && plan.whole());
}

void the_rest_put_back_beside_blocks_left_alone() {
    // Two pinned blocks and ten that come back: settled, a look every four seconds.
    Plan plan;
    Kernel kernel;
    for (int i = 0; i < 12; ++i) kernel.missing.insert(block(i));
    kernel.answer = [](uintptr_t b) { return b == block(4) || b == block(9) ? Answer::busy : Answer::made; };
    Pass p = pass(plan, kernel);
    CHECK(p.asked == 12 && p.delay == Plan::kQuietMs && !plan.settled());
    pass(plan, kernel);
    p = pass(plan, kernel);
    CHECK(plan.settled() && p.news == keeper::kBusy && plan.left() == 2 && p.delay == Plan::kCalmMs);
    // Memory pressure takes three more: put back in one pass, still settled.
    for (int i = 20; i < 23; ++i) kernel.missing.insert(block(i));
    p = pass(plan, kernel);
    CHECK(p.asked == 3 && p.with_reserve == 3 && plan.settled() && p.delay == Plan::kCalmMs && p.news == 0);
}

void refused_blocks_are_left_alone_too() {
    Plan plan;
    Kernel kernel{{block(1)}, [](uintptr_t) { return Answer::refused; }};
    for (int i = 0; i < 3; ++i) pass(plan, kernel);
    CHECK(plan.left(keeper::kRefused) == 1 && plan.settled() && plan.news() == keeper::kRefused);
}

void slow_calls_end_the_burst() {
    Plan plan;
    plan.begin({block(0), block(1), block(2)});
    CHECK(plan.answer(block(0), Answer::made, 3.0));
    CHECK(!plan.answer(block(1), Answer::made, Plan::kSlowCallMs + 1));
    CHECK(plan.end() == Plan::kQuietMs && !plan.whole() && plan.made() == 2);
}

void without_the_page_map() {
    // Blocks asked in turn: strikes still count, the caller says whole/progress.
    Plan plan;
    for (int i = 0; i < 3; ++i) {
        plan.begin_blind();
        CHECK(!plan.left_alone(block(5)));
        plan.answer(block(5), Answer::busy, 0.01);
        plan.answer(block(6), Answer::had, 0.01);
        const double delay = plan.end(false, false);
        CHECK(delay == (i == 0 ? 1000 : i == 1 ? 2000 : 4000) && !plan.settled());
    }
    CHECK(plan.left_alone(block(5)) && plan.news() == keeper::kBusy);
    plan.begin_blind();
    plan.answer(block(6), Answer::made, 2.0);
    CHECK(plan.end(false, true) == Plan::kQuietMs);
    plan.begin_blind();
    CHECK(plan.end(true, false) == Plan::kCalmMs && plan.whole());
}

} // namespace

int main() {
    pinned_blocks_are_left_alone();
    many_pinned_blocks_go_without_the_reserve();
    blocks_made_keep_the_passes_quick();
    no_memory_backs_off_and_is_told_once();
    the_memory_limit_is_no_strike();
    a_busy_block_gets_a_fresh_start();
    the_rest_put_back_beside_blocks_left_alone();
    refused_blocks_are_left_alone_too();
    slow_calls_end_the_burst();
    without_the_page_map();
    if (failures == 0) std::printf("memory keeper rule: all cases hold\n");
    return failures == 0 ? 0 : 1;
}
