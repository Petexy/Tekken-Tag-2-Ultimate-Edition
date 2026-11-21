#include "cafe/runtime.h"

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
// itself. While the kernel has no memory for the reserve, the wait grows to
// 8 s; once all blocks have one, a look every four seconds (and the reserve
// goes back to the PC). Without the page map (a kernel before 6.7) the blocks
// are asked in turn, 0.1 s of calls a second, a block with its huge page
// returning at once.

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
constexpr double kBurstMs = 100, kSlowCallMs = 20, kQuietMs = 1000;

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
    const Clock::time_point begun = Clock::now();
    Clock::time_point last_read = begun, next_pass = begun, last_said = begun, short_since = begun;
    bool collapse = true;   // (false once the kernel shows it has no MADV_COLLAPSE)
    bool ever_made = false; // a block was made: the kernel has it
    bool said = false;      // the first line, how the memory stands, is out
    bool short_of = false;  // the ranges are not all on huge pages
    double wait_ms = 1000;  // after a pass that made none (no memory for them), before the next
    size_t cursor = 0;      // (no page map: the block the next pass starts at)
    uint64_t last_huge = 0; // (no page map: kilobytes on huge pages after the last pass)
    std::vector<uintptr_t> blocks;
    for (;;) {
        const double until_read = 1000 - ms_since(last_read);
        const double until_pass = std::chrono::duration<double, std::milli>(next_pass - Clock::now()).count();
        const double nap = std::clamp(collapse ? std::min(until_read, until_pass) : until_read, 1.0, 1000.0);
        std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(nap));
        std::vector<KeptRange> ranges;
        {
            std::lock_guard lock(g_kept_mutex);
            ranges = g_kept;
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
        size_t tried = 0, made = 0, failed = 0, busy = 0, unknown = 0, no_memory = 0, filled = 0;
        double longest_ms = 0, fill_ms = 0;
        // One call; false: stop the burst (the kernel had to look for memory, or has none).
        const auto make = [&](uintptr_t block) {
            const Clock::time_point call = Clock::now();
            const int result = madvise(reinterpret_cast<void*>(block), kHugePage, MADV_COLLAPSE);
            const int error = errno;
            const double call_ms = ms_since(call);
            longest_ms = std::max(longest_ms, call_ms);
            ++tried;
            if (result == 0) {
                if (known || call_ms > 0.05) ++made; // (without the page map: one that had its huge page returns at once)
            } else {
                ++failed;
                if (error == EINVAL) ++unknown;
                else if (error == ENOMEM) ++no_memory;
                else ++busy; // (pages in use just now)
            }
            return call_ms < kSlowCallMs && !(result != 0 && error == ENOMEM);
        };
        if (known && !blocks.empty() && reserve != 0) {
            // The reserve's blocks get their huge pages (up to a second).
            size_t have = 0;
            for (bool r : ready) have += r;
            for (size_t i = 0; i < kReserveBlocks && have < blocks.size() && ms_since(pass) < 1000; ++i) {
                if (ready[i]) continue;
                auto* slot = reinterpret_cast<uint8_t*>(reserve + i * kHugePage);
                *reinterpret_cast<volatile uint8_t*>(slot) = 1;
                if (madvise(slot, kHugePage, MADV_COLLAPSE) == 0) {
                    ready[i] = true;
                    ++have;
                    ++filled;
                } else if (errno == ENOMEM) {
                    ++no_memory;
                    break;
                }
            }
            fill_ms = ms_since(pass);
            // The burst: a reserve block given back, a block of the ranges made over.
            const Clock::time_point burst = Clock::now();
            for (size_t i = 0; i < kReserveBlocks && tried < blocks.size() && ms_since(burst) < kBurstMs; ++i) {
                if (!ready[i]) continue;
                madvise(reinterpret_cast<void*>(reserve + i * kHugePage), kHugePage, MADV_DONTNEED);
                ready[i] = false;
                if (!make(blocks[tried])) break;
            }
        } else if (!known) {
            // In turn, 0.1 s of calls.
            const Clock::time_point burst = Clock::now();
            for (size_t i = 0; i < all && ms_since(burst) < kBurstMs; ++i) {
                size_t index = (cursor + i) % all;
                uintptr_t block = 0;
                for (const KeptRange& r : ranges) {
                    const size_t count = (r.end - r.begin) / kHugePage;
                    if (index < count) {
                        block = r.begin + index * kHugePage;
                        break;
                    }
                    index -= count;
                }
                if (block == 0 || !make(block)) break;
            }
            if (all > 0) cursor = (cursor + tried) % all;
        }
        const double pass_ms = ms_since(pass);
        ever_made = ever_made || made > 0;
        // Every call refused as an unknown request, none ever taken: an
        // older kernel, or huge pages turned off. (One block may be refused
        // so for its own reasons.)
        if (!ever_made && tried > 0 && unknown == tried) collapse = false;
        uint64_t resident = kept_kb, huge = 0;
        bool whole = false, progress = false;
        if (known) {
            const size_t left = missing - std::min(made, missing);
            huge = kept_kb - std::min<uint64_t>(kept_kb, uint64_t{left} * (kHugePage >> 10));
            whole = left == 0;
            progress = made > 0 || filled > 0;
        } else if (made == 0 && failed == 0 && !short_of && said && !trace) {
            next_pass = Clock::now() + std::chrono::seconds(4);
            continue;
        } else {
            measure_kept(ranges, resident, huge);
            whole = huge + 4096 >= resident;
            progress = huge > last_huge + 1024;
            last_huge = huge;
        }
        if (whole && reserve != 0) {
            madvise(reinterpret_cast<void*>(reserve), kReserveBlocks * kHugePage, MADV_DONTNEED); // (back to the PC)
            std::fill(std::begin(ready), std::end(ready), false);
        }
        next_pass = Clock::now() + std::chrono::milliseconds(static_cast<int>(whole ? 4000 : progress ? kQuietMs : wait_ms));
        wait_ms = whole || progress ? 1000 : std::min(wait_ms * 2, 8000.0);
        if (trace) {
            std::fprintf(stderr,
                         "memory: read %.1f ms; %zu of %zu blocks %s; reserve %zu made in %.1f ms; %zu tried in %.1f ms (%zu made, "
                         "%zu failed: %zu busy, %zu no memory, %zu refused; longest %.1f ms); %llu of %llu MB on huge pages\n",
                         read_ms, known ? missing : all, all, known ? "missing" : "(no page map)", filled, fill_ms, tried,
                         pass_ms - fill_ms, made, failed, busy, no_memory, unknown, longest_ms, mb(huge), mb(resident));
        }
        // Said: how the memory stands at the start; when huge pages go
        // missing, and every ten seconds while they are; when it is whole.
        const bool was_short = said ? short_of : known ? missing > 0 : !whole;
        if ((!was_short && !whole) || (!said && was_short)) {
            const uint64_t short_kb =
                !said && known ? std::min<uint64_t>(kept_kb, uint64_t{missing} * (kHugePage >> 10)) : resident - huge;
            std::fprintf(stderr,
                         "ttt2: memory: %llu of the %llu MB the GPU reads are not on huge pages (the PC is short of free "
                         "memory?): the game may stutter until they are; putting them back\n",
                         mb(short_kb), mb(resident));
            short_since = last_said = pass;
        } else if (!whole && ms_since(last_said) >= 10000) {
            std::fprintf(stderr, "ttt2: memory: %llu of the %llu MB the GPU reads are still not on huge pages%s\n",
                         mb(resident - huge), mb(resident),
                         collapse ? (progress ? "" : " (the PC has no free memory for them now)") : " (this kernel cannot put them back)");
            last_said = Clock::now();
        }
        if (whole && was_short) {
            std::fprintf(stderr, "ttt2: memory: the %llu MB the GPU reads are on huge pages again (after %.0f s)\n", mb(resident),
                         ms_since(short_since) / 1000);
        } else if (whole && !said) {
            std::fprintf(stderr, "ttt2: memory: the %llu MB the GPU reads are on huge pages\n", mb(resident));
        }
        said = true;
        short_of = !whole;
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
    static bool started = false;
    if (!started) std::thread(keeper_main).detach();
    started = true;
#endif
}

} // namespace cafe
