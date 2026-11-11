#include "gpu/looks.h"

#include <array>
#include <atomic>

namespace cafe::gpu::looks {
namespace {

std::array<std::atomic<uint32_t>, kNumbers> g_looks{};
uint32_t g_next = 1; // (the title's thread)
std::atomic<bool> g_active{false};

// The marks: the number, and the number with two patterns, in the words'
// low bytes; a float from 1/16 to 16 (the colour's range) each.
constexpr uint32_t kGreen = 0x5A, kBlue = 0xA5;
bool plausible(uint32_t bits) {
    const uint32_t exponent = bits >> 23 & 0xFF;
    return !(bits >> 31) && exponent >= 127 - 4 && exponent <= 127 + 4;
}

} // namespace

uint32_t number(uint32_t look, uint32_t previous) {
    if (previous != 0 && previous < kNumbers && g_looks[previous].load(std::memory_order_relaxed) == look) {
        return previous;
    }
    const uint32_t n = g_next;
    g_next = g_next + 1 < kNumbers ? g_next + 1 : 1;
    g_looks[n].store(look, std::memory_order_release);
    return n;
}

uint32_t look(uint32_t number) {
    return number && number < kNumbers ? g_looks[number].load(std::memory_order_acquire) : 0;
}

void mark(uint32_t rgb[3], uint32_t number) {
    rgb[0] = (rgb[0] & ~0xFFu) | number;
    rgb[1] = (rgb[1] & ~0xFFu) | (number ^ kGreen);
    rgb[2] = (rgb[2] & ~0xFFu) | (number ^ kBlue);
}

uint32_t marked(const uint32_t rgb[3]) {
    const uint32_t n = rgb[0] & 0xFF;
    if (n == 0 || (rgb[1] & 0xFF) != (n ^ kGreen) || (rgb[2] & 0xFF) != (n ^ kBlue)) return 0;
    return plausible(rgb[0]) && plausible(rgb[1]) && plausible(rgb[2]) ? n : 0;
}

void set_active(bool on) { g_active.store(on, std::memory_order_release); }
bool active() { return g_active.load(std::memory_order_acquire); }

} // namespace cafe::gpu::looks
