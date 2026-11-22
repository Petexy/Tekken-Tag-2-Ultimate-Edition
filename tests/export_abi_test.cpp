// Arguments of exported Cafe OS functions (cafe/export.h): r3..r10, then the
// caller's parameter area on the stack from r1 + 8. GX2InitBlendControlReg
// takes nine words, so its alpha combine comes from the stack; read from r11
// instead, the eraser of CUSTOMIZE > PAINT added alpha instead of taking it
// away and painted black.

#include "cafe/export.h"

#include <cstdio>
#include <cstring>
#include <vector>

namespace {

// A small guest address space: the test's stack lives in it.
alignas(64) uint8_t g_memory[0x10000];

int g_failures = 0;

void check(bool ok, const char* what) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", what);
        ++g_failures;
    }
}

void store32(uint32_t address, uint32_t value) {
    *reinterpret_cast<cafe::be<uint32_t>*>(g_memory + address) = value;
}

constexpr uint32_t kStack = 0x8000;

cafe::PPCContext make_context() {
    cafe::PPCContext ctx;
    std::memset(&ctx, 0, sizeof ctx);
    for (int i = 0; i < 32; ++i) ctx.r[i] = 0xDEAD0000u + i; // what a register past r10 holds is not an argument
    ctx.r[1] = kStack;
    return ctx;
}

std::vector<uint32_t> g_seen;

void nine(uint32_t a, uint32_t b, uint32_t c, uint32_t d, uint32_t e, uint32_t f, uint32_t g, uint32_t h,
          uint32_t i) {
    g_seen = {a, b, c, d, e, f, g, h, i};
}

// GX2InitBlendControlReg's shape: a pointer, then eight values, the last on the stack.
struct Reg {
    cafe::be<uint32_t> value;
};
void blend_like(Reg* reg, uint32_t target, uint32_t color_src, uint32_t color_dst, uint32_t color_combine,
                bool separate, uint32_t alpha_src, uint32_t alpha_dst, uint32_t alpha_combine) {
    g_seen = {cafe::guest_address(reg), target, color_src, color_dst, color_combine, separate, alpha_src,
              alpha_dst, alpha_combine};
}

void fourteen(uint32_t a, bool b, bool c, uint32_t d, bool e, bool f, uint32_t g, uint32_t h, uint32_t i,
              uint32_t j, uint32_t k, uint32_t l, uint32_t m, uint32_t n) {
    g_seen = {a, b, c, d, e, f, g, h, i, j, k, l, m, n};
}

// A 64-bit value that no longer fits in a register pair goes 8-aligned on the stack, and the next word after it.
void wide_late(uint32_t a, uint32_t b, uint32_t c, uint32_t d, uint32_t e, uint32_t f, uint32_t g, uint64_t h,
               uint32_t i) {
    g_seen = {a, b, c, d, e, f, g, static_cast<uint32_t>(h >> 32), static_cast<uint32_t>(h), i};
}

// Floating point arguments use f1.. and leave the integer order alone.
uint32_t mixed(uint32_t a, float x, uint32_t b, uint32_t c, uint32_t d, uint32_t e, uint32_t f, uint32_t g,
               uint32_t h, double y, uint32_t i) {
    g_seen = {a, b, c, d, e, f, g, h, i, static_cast<uint32_t>(x), static_cast<uint32_t>(y)};
    return a + i;
}

void register_arguments() {
    cafe::PPCContext ctx = make_context();
    for (int i = 0; i < 8; ++i) ctx.r[3 + i] = 10 + i;
    store32(kStack + 8, 18);
    cafe::abi::invoke<nine>(ctx);
    check(g_seen == std::vector<uint32_t>{10, 11, 12, 13, 14, 15, 16, 17, 18}, "nine words: the ninth from r1 + 8");
}

void blend_control() {
    cafe::PPCContext ctx = make_context();
    // GX2InitBlendControlReg(reg, 0, SRC_ALPHA, ONE, ADD, true, SRC_ALPHA, ONE, DST_MINUS_SRC), as the eraser makes it.
    const uint32_t args[] = {0x100, 0, 4, 1, 0, 1, 4, 1};
    for (int i = 0; i < 8; ++i) ctx.r[3 + i] = args[i];
    store32(kStack + 8, 4);
    cafe::abi::invoke<blend_like>(ctx);
    check(g_seen.size() == 9 && g_seen[0] == 0x100 && g_seen[8] == 4, "blend control: alpha combine DST_MINUS_SRC");
    check(ctx.r[1] == kStack, "the stack pointer is left alone");
}

void depth_stencil() {
    cafe::PPCContext ctx = make_context();
    for (int i = 0; i < 8; ++i) ctx.r[3 + i] = i + 1;
    for (uint32_t i = 0; i < 6; ++i) store32(kStack + 8 + 4 * i, 100 + i);
    cafe::abi::invoke<fourteen>(ctx);
    check(g_seen == std::vector<uint32_t>{1, 1, 1, 4, 1, 1, 7, 8, 100, 101, 102, 103, 104, 105},
          "fourteen words: six from the stack in order");
}

void wide_value() {
    cafe::PPCContext ctx = make_context();
    for (int i = 0; i < 8; ++i) ctx.r[3 + i] = 20 + i; // r10 is skipped: no pair left for the 64-bit value
    store32(kStack + 8, 0x01234567);
    store32(kStack + 12, 0x89ABCDEF);
    store32(kStack + 16, 30);
    cafe::abi::invoke<wide_late>(ctx);
    check(g_seen == std::vector<uint32_t>{20, 21, 22, 23, 24, 25, 26, 0x01234567, 0x89ABCDEF, 30},
          "a 64-bit value past r9:r10 on the stack, then the next word");
}

void floats_between() {
    cafe::PPCContext ctx = make_context();
    for (int i = 0; i < 8; ++i) ctx.r[3 + i] = 40 + i;
    ctx.f[1].ps0 = 3.0;
    ctx.f[2].ps0 = 5.0;
    store32(kStack + 8, 48);
    cafe::abi::invoke<mixed>(ctx);
    check(g_seen == std::vector<uint32_t>{40, 41, 42, 43, 44, 45, 46, 47, 48, 3, 5}, "floats in f1, f2; words in order");
    check(ctx.r[3] == 88, "the result in r3");
}

} // namespace

uint8_t* cafe::guest_base() { return g_memory; }

int main() {
    register_arguments();
    blend_control();
    depth_stencil();
    wide_value();
    floats_between();
    if (g_failures != 0) return 1;
    std::printf("export_abi_test: ok\n");
    return 0;
}
