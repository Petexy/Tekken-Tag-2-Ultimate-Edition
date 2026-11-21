#include "cafe/runtime.h"
#include "memory_keeper.h"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <fcntl.h>
#include <pthread.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#endif

#include <algorithm>
#include <atomic>
#include <bitset>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iterator>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace cafe {
namespace {

constexpr uint64_t kGuestSpace = uint64_t{1} << 32;
// Accesses are computed as base + uint32 and may straddle the top by up to
// eight bytes; keep a guard so those fault instead of touching host memory.
constexpr uint64_t kGuard = 0x10000;
constexpr uint32_t kPageShift = 12;
constexpr uint64_t kPage = uint64_t{1} << kPageShift;
constexpr uint64_t kHugePage = uint64_t{2} << 20; // x86-64's transparent huge pages

uint8_t* g_base = nullptr;
std::mutex g_commit_mutex;
// One bit per guest page: committed (readable and writable) or not.
auto g_committed = std::make_unique<std::bitset<(kGuestSpace >> kPageShift)>>();

std::pair<uint64_t, uint64_t> page_span(uint32_t address, uint32_t size) {
    const uint64_t begin = address & ~(kPage - 1);
    const uint64_t end = (uint64_t{address} + size + kPage - 1) & ~(kPage - 1);
    return {begin, end};
}

} // namespace

uint8_t* guest_base() { return g_base; }

void reserve_guest_memory() {
    if (g_base != nullptr) {
        return;
    }
#ifdef _WIN32
    void* p = VirtualAlloc(nullptr, kGuestSpace + kGuard, MEM_RESERVE, PAGE_NOACCESS);
    if (p == nullptr) {
        fatal("cannot reserve guest memory: Windows error %lu", GetLastError());
    }
#else
    // At a 2 MiB boundary, with transparent huge pages asked for: the
    // recompiled code reads and writes guest memory all over, and the GPU
    // imports it (VK_EXT_external_memory_host), which amdgpu walks page by
    // page at each submission. With 4 KiB pages the "gpu" thread spent 44 %
    // of a core in the kernel during a fight, with 2 MiB ones 7 %; the
    // processor's TLB misses halved. Without the advice the kernel gives
    // them only when it is set to "always" and has whole 2 MiB blocks free
    // (soon after a boot), not with "madvise" (SteamOS); with it, it makes
    // them (the "defrag" setting's default compacts memory for them).
    void* p = mmap(nullptr, kGuestSpace + kGuard + kHugePage, PROT_NONE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (p == MAP_FAILED) {
        fatal("cannot reserve 4 GiB of address space for guest memory: %s",
              std::strerror(errno));
    }
    const auto start = reinterpret_cast<uintptr_t>(p);
    const uintptr_t aligned = (start + kHugePage - 1) & ~(kHugePage - 1);
    if (aligned > start) munmap(p, aligned - start);
    munmap(reinterpret_cast<void*>(aligned + kGuestSpace + kGuard), start + kHugePage - aligned);
    p = reinterpret_cast<void*>(aligned);
    madvise(p, kGuestSpace, MADV_HUGEPAGE); // (refused by a kernel without them: 4 KiB pages then)
#endif
    g_base = static_cast<uint8_t*>(p);
}

void commit_guest_memory(uint32_t address, uint32_t size) {
    if (size == 0) {
        return;
    }
    const auto [begin, end] = page_span(address, size);
    if (end > kGuestSpace) {
        fatal("guest commit 0x%08X+0x%X runs past 4 GiB", address, size);
    }
    std::lock_guard lock(g_commit_mutex);
#ifdef _WIN32
    if (VirtualAlloc(g_base + begin, end - begin, MEM_COMMIT, PAGE_READWRITE) == nullptr) {
        fatal("cannot commit guest memory 0x%08X+0x%X: Windows error %lu",
              address, size, GetLastError());
    }
#else
    if (mprotect(g_base + begin, end - begin, PROT_READ | PROT_WRITE) != 0) {
        fatal("cannot commit guest memory 0x%08X+0x%X: %s", address, size,
              std::strerror(errno));
    }
#endif
    for (uint64_t page = begin; page < end; page += kPage) {
        g_committed->set(page >> kPageShift);
    }
}

bool guest_memory_committed(uint32_t address, uint32_t size) {
    const auto [begin, end] = page_span(address, size == 0 ? 1 : size);
    if (end > kGuestSpace) {
        return false;
    }
    for (uint64_t page = begin; page < end; page += kPage) {
        if (!g_committed->test(page >> kPageShift)) {
            return false;
        }
    }
    return true;
}

// ------------------------------------------------- memory the GPU reads
//
// The driver walks the imported guest memory at every submission (see
// reserve_guest_memory), and the presentation thread submits at every
// refresh of the display: on 4 KiB pages that walk took the thread from 13 %
// to 63 % of a core at 240 Hz, the frames' extra images were dropped and the
// title fell under 60 frames a second. The memory starts on huge pages when
// the PC has whole 2 MiB blocks free, and a PC short of free memory takes
// them away again: the GPU's reads do not count as use, so the kernel sees
// idle memory, splits the huge pages to swap them out, and the next
// submission reads them back as small ones.
// So the ranges are read here once a second, a byte of every page (they stay
// in use, and what was swapped out comes back on this thread, not on the
// presentation thread), and the blocks without a huge page get one
// (MADV_COLLAPSE, Linux 6.1). The kernel's page map says which blocks those
// are (PAGEMAP_SCAN, Linux 6.7).
// Making a block over moves its memory under the GPU's mapping: the driver
// waits for the GPU, and every submission that overlaps the change starts
// again and maps the whole range anew. On a PC short of memory the kernel
// also has to compact memory for each block (20-150 ms), so blocks made one
// after another kept the submissions starting over: the game ran at 3-10
// frames/s while it caught up, at 5-6 while the kernel had no memory to give
// and the calls went on, and once stopped (its GPU wait timed out).
// So the slow part happens away from that mapping: blocks of a reserve of
// this thread's own get their huge pages first (the kernel's compaction),
// then each is given back right before a block of the ranges is made over,
// which then takes a millisecond. A burst makes up to 64 MB within 0.1 s, so
// the mapping changes once for all of them; then the game has a second to
// itself. While the kernel makes none, or says it has no memory for them, the
// wait grows to 8 s: each such answer cost a round of compaction and reclaim
// that takes the coldest pages of the PC, the game's own among them. Once all
// blocks have one, a look every four seconds (and the reserve goes back to
// the PC). A block the kernel keeps turning down is left alone, and looked at
// again now and then: a driver that pins the memory it imports makes every
// call on it fail as busy, for as long as the game runs (the rule:
// memory_keeper.h). Without
// the page map (a kernel before 6.7) the blocks are asked in turn, 0.1 s of
// calls a second, a block with its huge page returning at once.

#ifndef _WIN32
namespace {

#ifndef MADV_COLLAPSE
#define MADV_COLLAPSE 25
#endif

// PAGEMAP_SCAN as <linux/fs.h> declares it (Linux 6.7), here for older headers.
struct PageRegion {
    uint64_t start, end, categories;
};
struct PageScan {
    uint64_t size, flags, start, end, walk_end, vec, vec_len, max_pages, category_inverted, category_mask, category_anyof_mask,
        return_mask;
};
static_assert(sizeof(PageScan) == 96);
constexpr unsigned long kPagemapScan = _IOWR('f', 16, PageScan);
constexpr uint64_t kPageIsHuge = 1 << 6;

struct KeptRange {
    uintptr_t begin, end; // host addresses, whole huge pages
};
std::mutex g_kept_mutex;
std::vector<KeptRange> g_kept;
std::chrono::steady_clock::time_point g_kept_added; // (when the last range came)
std::atomic<uint32_t> g_kept_sum{0}; // (what the reads add up to: they must not be optimised away)

// Resident and huge-page kilobytes of the kept ranges, from the kernel's map of the process.
void measure_kept(const std::vector<KeptRange>& ranges, uint64_t& resident, uint64_t& huge) {
    resident = huge = 0;
    std::FILE* maps = std::fopen("/proc/self/smaps", "r");
    if (maps == nullptr) return;
    char line[512];
    bool inside = false;
    while (std::fgets(line, sizeof line, maps) != nullptr) {
        unsigned long begin = 0, end = 0, kb = 0;
        if (std::sscanf(line, "%lx-%lx ", &begin, &end) == 2 && std::strchr(line, ':') > std::strchr(line, ' ')) {
            inside = false;
            for (const KeptRange& r : ranges) inside = inside || (begin < r.end && end > r.begin);
        } else if (inside && std::sscanf(line, "Rss: %lu kB", &kb) == 1) {
            resident += kb;
        } else if (inside && std::sscanf(line, "AnonHugePages: %lu kB", &kb) == 1) {
            huge += kb;
        }
    }
    std::fclose(maps);
}

// The blocks of the ranges that are not on a huge page, from the kernel's page
// map (pagemap: /proc/self/pagemap); false when the kernel cannot say.
bool find_missing(int pagemap, const std::vector<KeptRange>& ranges, std::vector<uintptr_t>& missing) {
    missing.clear();
    PageRegion regions[64];
    for (const KeptRange& r : ranges) {
        for (uintptr_t from = r.begin; from < r.end;) {
            PageScan scan{};
            scan.size = sizeof scan;
            scan.start = from;
            scan.end = r.end;
            scan.vec = reinterpret_cast<uintptr_t>(regions);
            scan.vec_len = std::size(regions);
            scan.category_inverted = scan.category_mask = scan.return_mask = kPageIsHuge; // (the pages without one)
            const int found = ioctl(pagemap, kPagemapScan, &scan);
            if (found < 0) return false;
            for (int i = 0; i < found; ++i) {
                for (uintptr_t block = regions[i].start & ~(kHugePage - 1); block < regions[i].end; block += kHugePage) {
                    if (missing.empty() || missing.back() < block) missing.push_back(block);
                }
            }
            if (scan.walk_end <= from) break;
            from = scan.walk_end;
        }
    }
    return true;
}

// The reserve: 64 MB of this thread's own, its blocks made huge pages away
// from the GPU's mapping and given back one by one in a burst.
constexpr size_t kReserveBlocks = 32;
constexpr double kBurstMs = 100;
// The ranges come one after another (MEM2's, then MEM1's): the first pass
// waits until none has come for this long, so it sees them all.
constexpr double kSettleMs = 500;

std::string mb_text(uint64_t kb) { return std::to_string(kb >> 10); }

void keeper_main() {
    pthread_setname_np(pthread_self(), "memory");
    static const bool trace = std::getenv("TTT2_TRACE_MEMORY") != nullptr;
    using Clock = std::chrono::steady_clock;
    const auto ms_since = [](Clock::time_point then) {
        return std::chrono::duration<double, std::milli>(Clock::now() - then).count();
    };
    const auto mb = [](uint64_t kb) { return static_cast<unsigned long long>(kb >> 10); };
    int pagemap = open("/proc/self/pagemap", O_RDONLY | O_CLOEXEC);
    uintptr_t reserve = 0;
    bool ready[kReserveBlocks] = {}; // (a reserve block on a huge page)
    if (void* r = mmap(nullptr, (kReserveBlocks + 1) * kHugePage, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE,
                       -1, 0);
        r != MAP_FAILED) {
        reserve = (reinterpret_cast<uintptr_t>(r) + kHugePage - 1) & ~(kHugePage - 1);
        madvise(reinterpret_cast<void*>(reserve), kReserveBlocks * kHugePage, MADV_HUGEPAGE);
    }
    const auto give_back_reserve = [&] {
        if (reserve == 0) return;
        madvise(reinterpret_cast<void*>(reserve), kReserveBlocks * kHugePage, MADV_DONTNEED); // (back to the PC)
        std::fill(std::begin(ready), std::end(ready), false);
    };
    const Clock::time_point begun = Clock::now();
    Clock::time_point last_read = begun, next_pass = begun, last_said = begun, short_since = begun;
    keeper::Plan plan;
    bool collapse = true;    // (false once the kernel shows it has no MADV_COLLAPSE)
    bool ever_made = false;  // a block was made: the kernel has it
    bool said = false;       // the first line, how the memory stands, is out
    bool short_of = false;   // blocks to put back (not on huge pages, not left alone)
    size_t made_since = 0;   // blocks made since the last line
    int lines = 0;           // lines said (at most kMostLines)
    constexpr int kMostLines = 40;
    size_t cursor = 0;       // (no page map: the block the next pass starts at)
    uint64_t last_huge = 0;  // (no page map: kilobytes on huge pages after the last pass)
    std::vector<uintptr_t> blocks;
    const auto say = [&](const std::string& text) {
        if (lines > kMostLines) return;
        std::fprintf(stderr, "ttt2: memory: %s\n", ++lines > kMostLines ? "(no more memory lines this session)" : text.c_str());
    };
    for (;;) {
        const double until_read = 1000 - ms_since(last_read);
        const double until_pass = std::chrono::duration<double, std::milli>(next_pass - Clock::now()).count();
        const double nap = std::clamp(collapse ? std::min(until_read, until_pass) : until_read, 1.0, 1000.0);
        std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(nap));
        std::vector<KeptRange> ranges;
        Clock::time_point added;
        {
            std::lock_guard lock(g_kept_mutex);
            ranges = g_kept;
            added = g_kept_added;
        }
        double read_ms = 0;
        if (ms_since(last_read) >= 990) {
            last_read = Clock::now();
            uint32_t sum = 0;
            for (const KeptRange& r : ranges) {
                for (uintptr_t page = r.begin; page < r.end; page += kPage) sum += *reinterpret_cast<const volatile uint8_t*>(page);
            }
            g_kept_sum.fetch_add(sum, std::memory_order_relaxed);
            read_ms = ms_since(last_read);
        }
        if (!collapse || Clock::now() < next_pass) continue;
        if (ms_since(added) < kSettleMs) {
            next_pass = added + std::chrono::milliseconds(static_cast<int>(kSettleMs));
            continue;
        }
        const Clock::time_point pass = Clock::now();
        uint64_t kept_kb = 0;
        size_t all = 0;
        for (const KeptRange& r : ranges) {
            kept_kb += (r.end - r.begin) >> 10;
            all += (r.end - r.begin) / kHugePage;
        }
        const bool known = pagemap >= 0 && find_missing(pagemap, ranges, blocks);
        if (!known && pagemap >= 0) {
            close(pagemap); // (a kernel before 6.7)
            pagemap = -1;
        }
        const size_t missing = known ? blocks.size() : 0;
        size_t filled = 0;
        double longest_ms = 0, fill_ms = 0;
        // One call; false: stop the burst (the kernel had to look for memory, or has none).
        const auto make = [&](uintptr_t block) {
            const Clock::time_point call = Clock::now();
            const int result = madvise(reinterpret_cast<void*>(block), kHugePage, MADV_COLLAPSE);
            const int error = errno;
            const double call_ms = ms_since(call);
            longest_ms = std::max(longest_ms, call_ms);
            using keeper::Answer;
            const Answer answer = result == 0 ? (known || call_ms > 0.05 ? Answer::made : Answer::had) // (blind: one that had its huge page returns at once)
                                  : error == ENOMEM ? Answer::no_memory
                                  : error == EBUSY  ? Answer::limit
                                  : error == EAGAIN ? Answer::busy
                                                    : Answer::refused;
            return plan.answer(block, answer, call_ms);
        };
        if (known) {
            const std::vector<uintptr_t>& to_try = plan.begin(blocks, ms_since(begun));
            // The reserve's blocks get their huge pages (up to a second), as many as the blocks asked with one.
            const auto want = static_cast<size_t>(
                std::count_if(to_try.begin(), to_try.end(), [&](uintptr_t b) { return plan.reserve_for(b); }));
            if (reserve != 0 && want > 0) {
                size_t have = 0;
                for (bool r : ready) have += r;
                for (size_t i = 0; i < kReserveBlocks && have < want && ms_since(pass) < 1000; ++i) {
                    if (ready[i]) continue;
                    auto* slot = reinterpret_cast<uint8_t*>(reserve + i * kHugePage);
                    *reinterpret_cast<volatile uint8_t*>(slot) = 1;
                    if (madvise(slot, kHugePage, MADV_COLLAPSE) == 0) {
                        ready[i] = true;
                        ++have;
                        ++filled;
                    } else if (errno == ENOMEM) {
                        plan.reserve_short();
                        break;
                    }
                }
            }
            fill_ms = ms_since(pass);
            // The burst: a reserve block given back, a block of the ranges made over.
            const Clock::time_point burst = Clock::now();
            size_t slot = 0;
            for (size_t n = 0; n < to_try.size() && ms_since(burst) < kBurstMs; ++n) {
                if (reserve != 0 && plan.reserve_for(to_try[n])) {
                    while (slot < kReserveBlocks && !ready[slot]) ++slot;
                    if (slot == kReserveBlocks) continue; // (the reserve is used up: this block next pass)
                    madvise(reinterpret_cast<void*>(reserve + slot * kHugePage), kHugePage, MADV_DONTNEED);
                    ready[slot] = false;
                }
                if (!make(to_try[n])) break;
            }
        } else {
            // In turn, 0.1 s of calls, the blocks left alone skipped.
            plan.begin_blind(ms_since(begun));
            const Clock::time_point burst = Clock::now();
            size_t visited = 0;
            while (visited < all && ms_since(burst) < kBurstMs) {
                size_t index = (cursor + visited++) % all;
                uintptr_t block = 0;
                for (const KeptRange& r : ranges) {
                    const size_t count = (r.end - r.begin) / kHugePage;
                    if (index < count) {
                        block = r.begin + index * kHugePage;
                        break;
                    }
                    index -= count;
                }
                if (block == 0) break;
                if (plan.left_alone(block)) continue;
                if (!make(block)) break;
            }
            if (all > 0) cursor = (cursor + visited) % all;
        }
        const double pass_ms = ms_since(pass);
        ever_made = ever_made || plan.made() > 0;
        // Every call refused as an unknown request, none ever taken: an
        // older kernel, or huge pages turned off. (One block may be refused
        // so for its own reasons.)
        if (!ever_made && plan.tried() > 0 && plan.refused() == plan.tried()) collapse = false;
        uint64_t resident = kept_kb, huge = 0;
        double delay = 0;
        if (known) {
            delay = plan.end();
            const size_t left = missing - std::min(plan.made(), missing);
            huge = kept_kb - std::min<uint64_t>(kept_kb, uint64_t{left} * (kHugePage >> 10));
        } else if (plan.made() == 0 && plan.busy() + plan.refused() + plan.no_memory() + plan.limit() == 0 && !short_of && said &&
                   !trace) {
            delay = plan.end(true, false); // (every block asked had its huge page: the process's map is not read)
            huge = resident;
        } else {
            measure_kept(ranges, resident, huge);
            const bool progress = huge > last_huge + 1024;
            last_huge = huge;
            delay = plan.end(huge + 4096 >= resident, progress);
        }
        const bool whole = plan.whole(), settled = plan.settled();
        if (whole || settled) give_back_reserve();
        next_pass = Clock::now() + std::chrono::milliseconds(static_cast<int>(delay));
        made_since += plan.made();
        if (trace) {
            std::fprintf(stderr,
                         "memory: read %.1f ms; %zu of %zu blocks %s, %zu left alone (%zu looked at again%s); reserve %zu made in "
                         "%.1f ms; %zu tried in %.1f ms (%zu made, %zu busy, %zu over the limit, %zu no memory, %zu refused; "
                         "longest %.1f ms); %llu of %llu MB on huge pages; next pass in %.0f ms%s, %s the reserve\n",
                         read_ms, known ? missing : all, all, known ? "missing" : "(no page map)", plan.left(), plan.looked_at(),
                         plan.fresh_start() ? ", fresh start" : "", filled, fill_ms, plan.tried(), pass_ms - fill_ms, plan.made(),
                         plan.busy(), plan.limit(), plan.no_memory(), plan.refused(), longest_ms, mb(huge), mb(resident), delay,
                         plan.strained() ? " (strained)" : "", plan.with_reserve() ? "with" : "without");
        }
        // Said: how the memory stands at the start; when huge pages go
        // missing, every ten seconds while more come back, and when they are
        // back; each kind of failure once. A few blocks a pass puts back at
        // once are not worth a line (two are missing at most starts, the PC
        // not short of anything).
        const uint64_t alone_kb = uint64_t{plan.left()} * (kHugePage >> 10);
        const bool short_now = !whole && !settled;
        const std::string of_all = " of the " + mb_text(resident) + " MB the GPU reads";
        if (short_now && (!said || !short_of)) {
            const uint64_t short_kb =
                !said && known ? std::min<uint64_t>(kept_kb, uint64_t{missing} * (kHugePage >> 10)) : resident - huge;
            // Why, from this pass's answers: calls all turned down as busy (and
            // the kernel not short), pages held in place; blocks left alone let
            // go; otherwise the PC had no whole 2 MiB blocks to give.
            const bool held = plan.made() == 0 && plan.busy() > 0 && plan.no_memory() == 0 && plan.limit() == 0;
            const char* why = plan.fresh_start() ? " (pages held in place before were let go)"
                              : held             ? " (pages held in place by the graphics driver?)"
                                                 : " (the PC is short of free memory?)";
            say(mb_text(short_kb) + of_all + " are not on huge pages" + why +
                ": the game may stutter until they are; putting them back");
            short_since = last_said = pass;
            made_since = 0;
        } else if (short_now && made_since > 0 && ms_since(last_said) >= 10000) {
            say(mb_text(resident - huge) + of_all + " are still not on huge pages");
            last_said = Clock::now();
            made_since = 0;
        }
        const unsigned news = plan.news();
        if (news & keeper::kNoMemory) say("the PC has no free memory for huge pages now: asking again less often (up to every 8 s)");
        if (news & keeper::kLimit) say("the game's memory limit (cgroup) leaves no room for huge pages: asking again less often");
        if (news & keeper::kBusy) {
            say("blocks the GPU reads that the kernel keeps turning down as busy (pages held in place by the graphics driver?) "
                "are left on small pages (" +
                mb_text(uint64_t{plan.left(keeper::kBusy)} * (kHugePage >> 10)) + " MB so far)");
        }
        if (news & keeper::kRefused) {
            say("blocks the GPU reads that the kernel keeps refusing huge pages are left on small pages (" +
                mb_text(uint64_t{plan.left(keeper::kRefused)} * (kHugePage >> 10)) + " MB so far)");
        }
        if (!short_now && said && short_of) {
            const std::string after = " (after " + std::to_string(static_cast<long>(ms_since(short_since) / 1000 + 0.5)) + " s)";
            say(whole ? "the " + mb_text(resident) + " MB the GPU reads are on huge pages again" + after
                      : "done putting them back" + after + ": " + mb_text(huge) + of_all + " are on huge pages, the other " +
                            mb_text(alone_kb) + " MB stay on small pages");
        } else if (whole && !said) {
            say("the " + mb_text(resident) + " MB the GPU reads are on huge pages");
        }
        if (!collapse) say("this kernel cannot put the memory the GPU reads back on huge pages (Linux 6.1 can)");
        said = true;
        short_of = short_now;
    }
}

} // namespace
#endif

void keep_guest_memory_fast(uint32_t address, uint32_t size) {
#ifdef _WIN32
    (void)address;
    (void)size;
#else
    // TTT2_KEEP_MEMORY=0: as before (to compare).
    if (const char* setting = std::getenv("TTT2_KEEP_MEMORY"); setting != nullptr && std::strcmp(setting, "0") == 0) return;
    const auto base = reinterpret_cast<uintptr_t>(g_base);
    const uintptr_t begin = (base + address + kHugePage - 1) & ~(kHugePage - 1);
    const uintptr_t end = (base + address + size) & ~(kHugePage - 1);
    if (end <= begin) return;
    std::lock_guard lock(g_kept_mutex);
    g_kept.push_back({begin, end});
    g_kept_added = std::chrono::steady_clock::now();
    static bool started = false;
    if (!started) std::thread(keeper_main).detach();
    started = true;
#endif
}

} // namespace cafe
