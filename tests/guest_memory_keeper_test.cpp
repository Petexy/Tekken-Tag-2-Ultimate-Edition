// The thread that keeps the memory the GPU reads in use and on huge pages
// (keep_guest_memory_fast, runtime/src/memory.cpp) must leave the memory's
// contents alone: a range whose huge pages were split, with a page taken
// out of every 2 MiB block, is read and put back on huge pages while this
// thread keeps writing to it.
#include "cafe/runtime.h"

#include <sys/mman.h>

#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

namespace cafe {
void fatal(const char* format, ...) {
    va_list args;
    va_start(args, format);
    std::vfprintf(stderr, format, args);
    va_end(args);
    std::abort();
}
} // namespace cafe

namespace {

constexpr uint32_t kBase = 0x10000000, kSize = 16u << 20, kBlock = 2u << 20;

uint8_t value(uint32_t offset, uint32_t round) { return static_cast<uint8_t>(offset * 2654435761u >> 24) ^ static_cast<uint8_t>(round); }

// Megabytes of the range on huge pages, by the kernel's map of the process.
unsigned long huge_mb() {
    const auto begin = reinterpret_cast<unsigned long>(cafe::guest_pointer(kBase)), end = begin + kSize;
    std::FILE* maps = std::fopen("/proc/self/smaps", "r");
    if (maps == nullptr) return 0;
    char line[512];
    bool inside = false;
    unsigned long total = 0;
    while (std::fgets(line, sizeof line, maps) != nullptr) {
        unsigned long a = 0, b = 0, kb = 0;
        if (std::sscanf(line, "%lx-%lx ", &a, &b) == 2) inside = a < end && b > begin;
        else if (inside && std::sscanf(line, "AnonHugePages: %lu kB", &kb) == 1) total += kb;
    }
    std::fclose(maps);
    return total >> 10;
}

} // namespace

int main() {
    cafe::reserve_guest_memory();
    cafe::commit_guest_memory(kBase, kSize);
    uint8_t* memory = cafe::guest_pointer(kBase);
    for (uint32_t i = 0; i < kSize; ++i) memory[i] = value(i, 0);
    const unsigned long at_first = huge_mb();
    // A page out of every block: its huge page is split; the page reads as zeros.
    for (uint32_t block = 0; block < kSize; block += kBlock) {
        madvise(memory + block + 5 * 4096, 4096, MADV_DONTNEED);
        std::memset(memory + block + 5 * 4096, 0, 4096);
    }
    const unsigned long split = huge_mb();
    cafe::keep_guest_memory_fast(kBase, kSize);
    // Six seconds of the keeper's passes (a read every second, huge pages
    // every fourth), with every byte rewritten and checked meanwhile.
    const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(6);
    uint32_t round = 0;
    const auto expected = [&](uint32_t i, uint32_t r) {
        return (i % kBlock) / 4096 == 5 && r == 0 ? uint8_t{0} : value(i, r);
    };
    while (std::chrono::steady_clock::now() < until) {
        for (uint32_t i = 0; i < kSize; ++i) {
            if (memory[i] != expected(i, round)) {
                std::fprintf(stderr, "byte 0x%X changed in round %u: 0x%02X, not 0x%02X\n", i, round, memory[i], expected(i, round));
                return 1;
            }
            memory[i] = value(i, round + 1);
        }
        ++round;
    }
    std::printf("guest memory keeper: %u rounds of writes kept; on huge pages %lu MB at first, %lu after the split, %lu at the end "
                "(of %u; none where the kernel gives no huge pages)\n",
                round, at_first, split, huge_mb(), kSize >> 20);
    return 0;
}
