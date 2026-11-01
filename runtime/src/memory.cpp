#include "cafe/runtime.h"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <sys/mman.h>
#endif

#include <bitset>
#include <cerrno>
#include <cstring>
#include <memory>
#include <mutex>

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

} // namespace cafe
