#include "cafe/runtime.h"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <pthread.h>
#include <sys/mman.h>
#endif

#include <atomic>
#include <bitset>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
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
// title fell under 60 frames a second. The memory starts on huge pages, but
// a PC short of free memory takes them away again: the GPU's reads do not
// count as use, so the kernel sees idle memory, splits the huge pages to
// swap them out, and the next submission reads them back as small ones.
// So the ranges are read here once a second, a byte of every page (they stay
// in use, and what was swapped out comes back on this thread, not on the
// presentation thread), and every few seconds the blocks that lost their
// huge page get one again (MADV_COLLAPSE, Linux 6.1; nothing to do for a
// block that has one).

#ifndef _WIN32
namespace {

#ifndef MADV_COLLAPSE
#define MADV_COLLAPSE 25
#endif

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

void keeper_main() {
    pthread_setname_np(pthread_self(), "memory");
    static const bool trace = std::getenv("TTT2_TRACE_MEMORY") != nullptr;
    bool collapse = true;     // (false once the kernel says it has no MADV_COLLAPSE)
    bool short_of = false;    // told that the ranges are not on huge pages
    size_t cursor = 0;        // the block the next collapse pass starts at
    for (uint32_t second = 1;; ++second) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
        std::vector<KeptRange> ranges;
        {
            std::lock_guard lock(g_kept_mutex);
            ranges = g_kept;
        }
        const auto started = std::chrono::steady_clock::now();
        const auto elapsed_ms = [&] {
            return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
        };
        uint32_t sum = 0;
        for (const KeptRange& r : ranges) {
            for (uintptr_t page = r.begin; page < r.end; page += kPage) sum += *reinterpret_cast<const volatile uint8_t*>(page);
        }
        g_kept_sum.fetch_add(sum, std::memory_order_relaxed);
        const double read_ms = elapsed_ms();
        if (!collapse || second % 4 != 0) continue;
        // The blocks in turn; a pass stops once it has taken 10 ms (a block
        // with a huge page costs a microsecond; making one, a 2 MiB copy
        // and maybe the kernel's search for free memory).
        size_t blocks = 0;
        for (const KeptRange& r : ranges) blocks += (r.end - r.begin) / kHugePage;
        size_t visited = 0, failed = 0;
        for (; visited < blocks && elapsed_ms() - read_ms < 10.0; ++visited) {
            size_t index = (cursor + visited) % blocks;
            for (const KeptRange& r : ranges) {
                const size_t count = (r.end - r.begin) / kHugePage;
                if (index >= count) {
                    index -= count;
                    continue;
                }
                if (madvise(reinterpret_cast<void*>(r.begin + index * kHugePage), kHugePage, MADV_COLLAPSE) != 0) {
                    if (errno == EINVAL) collapse = false; // an older kernel, or huge pages turned off
                    ++failed;
                }
                break;
            }
            if (!collapse) break;
        }
        cursor = blocks ? (cursor + visited) % blocks : 0;
        const double pass_ms = elapsed_ms() - read_ms;
        // A pass that had work to do: say once how the memory stands, and again when it is whole.
        if (pass_ms < 3.0 && !short_of && !trace) continue;
        uint64_t resident = 0, huge = 0;
        measure_kept(ranges, resident, huge);
        const bool whole = huge + 4096 >= resident;
        if (trace) {
            std::fprintf(stderr, "memory: read %.1f ms; %zu of %zu blocks in %.1f ms (%zu failed); %llu of %llu MB on huge pages\n",
                         read_ms, visited, blocks, pass_ms, failed, static_cast<unsigned long long>(huge >> 10),
                         static_cast<unsigned long long>(resident >> 10));
        }
        if (!whole && !short_of) {
            std::fprintf(stderr,
                         "ttt2: memory: %llu of the %llu MB the GPU reads are not on huge pages (the PC is short of free "
                         "memory?); putting them back\n",
                         static_cast<unsigned long long>((resident - huge) >> 10), static_cast<unsigned long long>(resident >> 10));
        } else if (whole && short_of) {
            std::fprintf(stderr, "ttt2: memory: the memory the GPU reads is on huge pages again\n");
        }
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
