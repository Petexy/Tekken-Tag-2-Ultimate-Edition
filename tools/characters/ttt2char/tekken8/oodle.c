/*
 * Tekken 8's own Oodle decompressor, called natively on Linux (a shared library for ctypes; tekken8/store.py).
 *
 * Tekken 8 compresses its IoStore containers and pak files with Oodle (Kraken), which is statically linked into
 * its exe (Polaris/Binaries/Win64/Polaris-Win64-Shipping.exe, plain x64 code). Rather than reimplementing the
 * codec, this library runs the game's own OodleLZ_Decompress: Windows x64 code runs unchanged on Linux x86-64 when
 * it is called with the Microsoft calling convention and does not call into Windows itself, which the
 * decompressor does not do.
 *
 * oodle8_open(exe):
 *   - reads the exe (read-only; nothing is ever written to the game's files) and maps a private copy of its image
 *     at its preferred base (0x140000000) with MAP_FIXED_NOREPLACE; when that address is taken it maps it anywhere
 *     and applies the image's base relocations (.reloc: IMAGE_REL_BASED_DIR64 blocks), as Windows' loader would;
 *     then gives the sections their protections (code read/execute, read-only data read-only);
 *   - points the import address table at local code: memcpy/memmove/memset/memcmp get wrappers in the Microsoft
 *     calling convention, every other import a trap: the decompressor calls none of them on good data, and if it
 *     does (on corrupt data it logs through KERNEL32's OutputDebugStringA) or faults, the call ends with an error
 *     from oodle8_decompress instead of ending the Python process;
 *   - locates OodleLZ_Decompress itself (no fixed address, so a game update does not break it): Oodle names it
 *     in an error message, the ASCII string "oo2::OodleLZ_Decompress"; the code that references that string
 *     (rip-relative lea in .text) is inside it, and the function's start is the start of the .pdata entry that
 *     covers the reference (following chained unwind info back to the primary entry when the reference lies in
 *     a separated fragment of the function); every reference must lead to the same function;
 *   - sets the image's static TLS up (the TLS directory's template), should the code use thread-locals.
 * oodle8_decompress(comp, comp_size, raw, raw_size) -> raw_size on success, 0 when Oodle rejects the data, < 0
 *   (OODLE8_*) when the call could not be made or was stopped; oodle8_error() says why. Calls are serialised. For
 *   each call: a fake Windows thread block (NT_TIB StackBase/StackLimit/Self, a TLS array and an empty PEB) set as
 *   the GS base through arch_prctl(ARCH_SET_GS) (the code's stack probe __chkstk reads gs:[0x10]), the old GS base
 *   restored afterwards; handlers for SIGSEGV/SIGBUS/SIGILL/SIGFPE/SIGTRAP installed for the call and the previous
 *   ones restored after it (a fault jumps back out with siglongjmp). The arguments of OodleLZ_Decompress are
 *   (comp, compLen, raw, rawLen, fuzzSafe 1, checkCRC 0, verbosity 0, decBufBase NULL, decBufSize 0, callback
 *   NULL, callback data NULL, decoderMemory, decoderMemorySize, threadPhase 3 (all)); the decoder memory is this
 *   library's, so Oodle allocates nothing.
 *
 * Written for this project (no third-party code).
 */
#define _GNU_SOURCE
#include <asm/prctl.h>
#include <fcntl.h>
#include <pthread.h>
#include <setjmp.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif

#define OODLE8_NOT_OPEN (-1)        /* oodle8_open did not succeed */
#define OODLE8_BAD_ARGUMENTS (-2)
#define OODLE8_IMPORT (-3)          /* the game's code called a Windows function */
#define OODLE8_FAULT (-4)           /* the game's code faulted (signal) */

#define NEEDLE "oo2::OodleLZ_Decompress"     /* with its NUL: the name Oodle's own messages give the function */
#define DECODER_MEMORY (8u << 20)            /* Oodle's decoder scratch (a Kraken block needs well under 1 MiB) */
#define THUNK_SIZE 32                        /* mov rdi, index; and rsp, -16; mov rax, trap; call rax */
#define MAX_CHAIN 32                         /* chained unwind entries followed at most */
#define TEB_SIZE 0x2000
#define PEB_SIZE 0x1000
#define TLS_SLOTS 64

#define SCN_EXECUTE 0x20000000u
#define SCN_READ 0x40000000u
#define SCN_WRITE 0x80000000u
#define UNW_FLAG_CHAININFO 4

typedef intptr_t (__attribute__((ms_abi)) *DecompressFn)(const void *, intptr_t, void *, intptr_t, int, int, int,
                                                         void *, intptr_t, void *, void *, void *, intptr_t, int);

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static DecompressFn g_fn;
static uint8_t *g_image;
static size_t g_image_size;
static uint8_t *g_thunks;
static size_t g_thunks_size;
static char **g_import_names;
static unsigned g_imports;
static uint8_t *g_decoder;
static uint64_t g_teb[TEB_SIZE / 8];
static uint64_t g_peb[PEB_SIZE / 8];
static uint64_t g_tls_array[TLS_SLOTS];
static uint8_t *g_tls_block;
static uint64_t g_function_rva;

static char g_error[512];
static sigjmp_buf g_jump;
static volatile sig_atomic_t g_in_call;
static pthread_t g_caller;
static volatile uint64_t g_trap_index;
static volatile int g_signal;
static void *volatile g_fault_address;
static volatile uint64_t g_fault_ip;
static const int g_signals[] = {SIGSEGV, SIGBUS, SIGILL, SIGFPE, SIGTRAP};
#define NSIGNALS (int)(sizeof g_signals / sizeof g_signals[0])
static struct sigaction g_old[NSIGNALS];

static void set_error(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(g_error, sizeof g_error, fmt, ap);
    va_end(ap);
}

const char *oodle8_error(void) { return g_error; }
uint64_t oodle8_function_rva(void) { return g_function_rva; }
uint64_t oodle8_image_base(void) { return (uint64_t)(uintptr_t)g_image; }

/* ------------------------------------------------------------------------------------------- imports */
__attribute__((ms_abi)) static void *w_memcpy(void *d, const void *s, size_t n) { return memcpy(d, s, n); }
__attribute__((ms_abi)) static void *w_memmove(void *d, const void *s, size_t n) { return memmove(d, s, n); }
__attribute__((ms_abi)) static void *w_memset(void *d, int c, size_t n) { return memset(d, c, n); }
__attribute__((ms_abi)) static int w_memcmp(const void *a, const void *b, size_t n) { return memcmp(a, b, n); }

/* every other import: leave the call (only ever reached inside oodle8_decompress); entered from its thunk with
   the import's number as the first (System V) argument and the stack aligned again, whatever the caller left */
__attribute__((noreturn, used)) static void trap(uint64_t index) {
    g_trap_index = index;
    siglongjmp(g_jump, 1);
}

static void on_signal(int sig, siginfo_t *info, void *context) {
    if (g_in_call && pthread_equal(pthread_self(), g_caller)) {
        g_signal = sig;
        g_fault_address = info ? info->si_addr : NULL;
        g_fault_ip = context ? (uint64_t)((ucontext_t *)context)->uc_mcontext.gregs[REG_RIP] : 0;
        siglongjmp(g_jump, 2);
    }
    /* another thread's signal during a call: give it back to the handler it had (the fault repeats under it) */
    for (int i = 0; i < NSIGNALS; i++)
        if (g_signals[i] == sig)
            sigaction(sig, &g_old[i], NULL);
}

/* ------------------------------------------------------------------------------------------- the PE image */
typedef struct {
    const uint8_t *file;
    size_t size;
    size_t nt, opt, sections;
    unsigned nsections;
    uint64_t base;
    uint32_t image_size, headers_size;
} Pe;

static int in_file(const Pe *pe, uint64_t offset, uint64_t n) { return offset <= pe->size && n <= pe->size - offset; }
static uint16_t rd16(const uint8_t *p) { uint16_t v; memcpy(&v, p, 2); return v; }
static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static uint64_t rd64(const uint8_t *p) { uint64_t v; memcpy(&v, p, 8); return v; }

static int parse_pe(Pe *pe) {
    if (!in_file(pe, 0, 0x40) || memcmp(pe->file, "MZ", 2))
        return set_error("not a Windows program (no MZ header)"), -1;
    pe->nt = rd32(pe->file + 0x3c);
    if (!in_file(pe, pe->nt, 24 + 240) || memcmp(pe->file + pe->nt, "PE\0\0", 4))
        return set_error("not a Windows program (no PE header)"), -1;
    if (rd16(pe->file + pe->nt + 4) != 0x8664)
        return set_error("not an x64 program"), -1;
    pe->nsections = rd16(pe->file + pe->nt + 6);
    pe->opt = pe->nt + 24;
    if (rd16(pe->file + pe->opt) != 0x20b)
        return set_error("not a 64-bit PE image"), -1;
    pe->sections = pe->opt + rd16(pe->file + pe->nt + 20);
    if (!in_file(pe, pe->sections, 40ull * pe->nsections))
        return set_error("truncated section table"), -1;
    pe->base = rd64(pe->file + pe->opt + 24);
    pe->image_size = rd32(pe->file + pe->opt + 56);
    pe->headers_size = rd32(pe->file + pe->opt + 60);
    if (!pe->image_size || pe->headers_size > pe->image_size || !in_file(pe, 0, pe->headers_size))
        return set_error("bad image size"), -1;
    return 0;
}

static void directory(const Pe *pe, unsigned i, uint32_t *rva, uint32_t *size) {
    uint32_t n = rd32(pe->file + pe->opt + 108);
    *rva = *size = 0;
    if (i < n) {
        *rva = rd32(pe->file + pe->opt + 112 + 8 * i);
        *size = rd32(pe->file + pe->opt + 112 + 8 * i + 4);
    }
}

/* image range check: [rva, rva + n) inside the mapped image */
static int in_image(uint64_t rva, uint64_t n) { return rva <= g_image_size && n <= g_image_size - rva; }

static int file_to_rva(const Pe *pe, uint64_t offset, uint32_t *rva) {
    for (unsigned i = 0; i < pe->nsections; i++) {
        const uint8_t *s = pe->file + pe->sections + 40 * i;
        uint32_t vsize = rd32(s + 8), va = rd32(s + 12), rsize = rd32(s + 16), raw = rd32(s + 20);
        uint32_t n = rsize < vsize ? rsize : vsize;
        if (offset >= raw && offset < (uint64_t)raw + n) {
            *rva = (uint32_t)(va + (offset - raw));
            return 0;
        }
    }
    return -1;
}

static int map_image(const Pe *pe) {
    size_t size = (pe->image_size + 0xfffu) & ~(size_t)0xfff;
    uint8_t *img = mmap((void *)(uintptr_t)pe->base, size, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (img == MAP_FAILED)                 /* the preferred address is taken: anywhere, relocated below */
        img = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (img == MAP_FAILED)
        return set_error("cannot map %zu bytes for the game's code", size), -1;
    g_image = img;
    g_image_size = size;
    memcpy(img, pe->file, pe->headers_size);
    for (unsigned i = 0; i < pe->nsections; i++) {
        const uint8_t *s = pe->file + pe->sections + 40 * i;
        uint32_t vsize = rd32(s + 8), va = rd32(s + 12), rsize = rd32(s + 16), raw = rd32(s + 20);
        uint32_t n = rsize < vsize ? rsize : vsize;
        if (!n)
            continue;
        if (!in_file(pe, raw, n) || !in_image(va, n))
            return set_error("section %u lies outside the file or image", i), -1;
        memcpy(img + va, pe->file + raw, n);
    }
    return 0;
}

static int relocate(const Pe *pe) {
    int64_t delta = (int64_t)((uint64_t)(uintptr_t)g_image - pe->base);
    if (!delta)
        return 0;
    uint32_t rva, size;
    directory(pe, 5, &rva, &size);
    if (!rva || !size)
        return set_error("the image cannot move (no relocations) and its address is taken"), -1;
    if (!in_image(rva, size))
        return set_error("relocations outside the image"), -1;
    for (uint32_t at = 0; at + 8 <= size;) {
        uint32_t page = rd32(g_image + rva + at), block = rd32(g_image + rva + at + 4);
        if (block < 8 || block > size - at)
            return set_error("bad relocation block at %#x", rva + at), -1;
        for (uint32_t k = 8; k + 2 <= block; k += 2) {
            uint16_t e = rd16(g_image + rva + at + k);
            uint32_t target = page + (e & 0xfff);
            switch (e >> 12) {
            case 0:                         /* padding */
                break;
            case 10:                        /* DIR64 */
                if (!in_image(target, 8))
                    return set_error("relocation outside the image"), -1;
                {
                    uint64_t v = rd64(g_image + target) + (uint64_t)delta;
                    memcpy(g_image + target, &v, 8);
                }
                break;
            case 3:                         /* HIGHLOW */
                if (!in_image(target, 4))
                    return set_error("relocation outside the image"), -1;
                {
                    uint32_t v = rd32(g_image + target) + (uint32_t)delta;
                    memcpy(g_image + target, &v, 4);
                }
                break;
            default:
                return set_error("relocation type %u is not supported", e >> 12), -1;
            }
        }
        at += block;
    }
    return 0;
}

static const char *c_string(uint64_t rva) {
    if (!in_image(rva, 1))
        return NULL;
    const char *s = (const char *)g_image + rva;
    return memchr(s, 0, g_image_size - rva) ? s : NULL;
}

static int bind_imports(const Pe *pe) {
    uint32_t rva, size;
    directory(pe, 1, &rva, &size);
    if (!rva)
        return 0;
    unsigned count = 0;
    for (uint32_t d = rva; in_image(d, 20) && rd32(g_image + d + 12); d += 20) {
        uint32_t lookup = rd32(g_image + d) ? rd32(g_image + d) : rd32(g_image + d + 16);
        for (uint32_t t = lookup; in_image(t, 8) && rd64(g_image + t); t += 8)
            count++;
    }
    g_thunks_size = ((size_t)count * THUNK_SIZE + 0xfff) & ~(size_t)0xfff;
    if (!g_thunks_size)
        g_thunks_size = 0x1000;
    g_thunks = mmap(NULL, g_thunks_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    g_import_names = calloc(count + 1, sizeof *g_import_names);
    if (g_thunks == MAP_FAILED || !g_import_names)
        return g_thunks = NULL, set_error("out of memory"), -1;
    unsigned n = 0;
    for (uint32_t d = rva; in_image(d, 20) && rd32(g_image + d + 12); d += 20) {
        const char *dll = c_string(rd32(g_image + d + 12));
        uint32_t lookup = rd32(g_image + d) ? rd32(g_image + d) : rd32(g_image + d + 16);
        uint32_t iat = rd32(g_image + d + 16);
        for (uint32_t t = lookup; in_image(t, 8) && rd64(g_image + t) && n < count; t += 8, iat += 8, n++) {
            uint64_t entry = rd64(g_image + t);
            char name[160];
            const char *fn = NULL;
            if (entry >> 63)
                snprintf(name, sizeof name, "%s!#%u", dll ? dll : "?", (unsigned)(entry & 0xffff));
            else {
                fn = c_string((uint32_t)entry + 2);
                snprintf(name, sizeof name, "%s!%s", dll ? dll : "?", fn ? fn : "?");
            }
            g_import_names[n] = strdup(name);
            void *target = NULL;
            if (fn && !strcmp(fn, "memcpy"))
                target = (void *)w_memcpy;
            else if (fn && !strcmp(fn, "memmove"))
                target = (void *)w_memmove;
            else if (fn && !strcmp(fn, "memset"))
                target = (void *)w_memset;
            else if (fn && !strcmp(fn, "memcmp"))
                target = (void *)w_memcmp;
            if (!target) {
                uint8_t *th = g_thunks + (size_t)THUNK_SIZE * n;
                uint64_t index = n, to = (uint64_t)(uintptr_t)trap;
                th[0] = 0x48; th[1] = 0xbf; memcpy(th + 2, &index, 8);      /* mov rdi, index */
                th[10] = 0x48; th[11] = 0x83; th[12] = 0xe4; th[13] = 0xf0; /* and rsp, -16 */
                th[14] = 0x48; th[15] = 0xb8; memcpy(th + 16, &to, 8);      /* mov rax, trap */
                th[24] = 0xff; th[25] = 0xd0;                               /* call rax (never returns) */
                target = th;
            }
            if (!in_image(iat, 8))
                return set_error("import table outside the image"), -1;
            uint64_t v = (uint64_t)(uintptr_t)target;
            memcpy(g_image + iat, &v, 8);
        }
    }
    g_imports = n;
    if (mprotect(g_thunks, g_thunks_size, PROT_READ | PROT_EXEC))
        return set_error("cannot protect the import thunks"), -1;
    return 0;
}

static int setup_tls(const Pe *pe) {
    uint32_t rva, size;
    directory(pe, 9, &rva, &size);
    if (!rva || !in_image(rva, 40))
        return 0;
    uint64_t base = (uint64_t)(uintptr_t)g_image;
    uint64_t start = rd64(g_image + rva), end = rd64(g_image + rva + 8), index = rd64(g_image + rva + 16);
    uint32_t zero_fill = rd32(g_image + rva + 32);
    if (end < start || start < base || !in_image(start - base, end - start))
        return set_error("bad TLS directory"), -1;
    size_t n = (size_t)(end - start) + zero_fill;
    g_tls_block = calloc(1, n + 16);
    if (!g_tls_block)
        return set_error("out of memory"), -1;
    memcpy(g_tls_block, g_image + (start - base), (size_t)(end - start));
    if (index >= base && in_image(index - base, 4)) {
        uint32_t zero = 0;                  /* _tls_index = 0: slot 0 of the TLS array */
        memcpy(g_image + (index - base), &zero, 4);
    }
    g_tls_array[0] = (uint64_t)(uintptr_t)g_tls_block;
    return 0;
}

static int protect_sections(const Pe *pe) {
    if (mprotect(g_image, (pe->headers_size + 0xfffu) & ~0xfffu, PROT_READ))
        return set_error("cannot protect the image headers"), -1;
    for (unsigned i = 0; i < pe->nsections; i++) {
        const uint8_t *s = pe->file + pe->sections + 40 * i;
        uint32_t vsize = rd32(s + 8), va = rd32(s + 12), flags = rd32(s + 36);
        uint32_t lo = va & ~0xfffu, hi = (va + vsize + 0xfffu) & ~0xfffu;
        if (!vsize || !in_image(lo, hi - lo))
            continue;
        int prot = (flags & SCN_READ ? PROT_READ : 0) | (flags & SCN_WRITE ? PROT_WRITE : 0) |
                   (flags & SCN_EXECUTE ? PROT_EXEC : 0);
        if (mprotect(g_image + lo, hi - lo, prot))
            return set_error("cannot protect section %u", i), -1;
    }
    return 0;
}

/* ------------------------------------------------------------------------------------------- finding the function */
/* the code section: the one named .text, else the first executable one */
static int code_section(const Pe *pe, uint32_t *va, uint32_t *n) {
    int pick = -1;
    for (unsigned i = 0; i < pe->nsections && pick < 0; i++)
        if (!memcmp(pe->file + pe->sections + 40 * i, ".text\0", 6))
            pick = (int)i;
    for (unsigned i = 0; i < pe->nsections && pick < 0; i++)
        if (rd32(pe->file + pe->sections + 40 * i + 36) & SCN_EXECUTE)
            pick = (int)i;
    if (pick < 0)
        return -1;
    *va = rd32(pe->file + pe->sections + 40 * pick + 12);
    *n = rd32(pe->file + pe->sections + 40 * pick + 8);
    return 0;
}

/* the primary function start of the .pdata entry covering rva, or 0 */
static uint32_t primary_function(const Pe *pe, uint32_t rva) {
    uint32_t prva, psize;
    directory(pe, 3, &prva, &psize);
    if (!prva || !in_image(prva, psize))
        return 0;
    const uint8_t *table = g_image + prva;
    uint32_t count = psize / 12;
    for (int depth = 0; depth < MAX_CHAIN; depth++) {
        uint32_t lo = 0, hi = count;                    /* entries are sorted by BeginAddress */
        while (lo < hi) {
            uint32_t mid = lo + (hi - lo) / 2;
            if (rd32(table + 12 * mid) <= rva)
                lo = mid + 1;
            else
                hi = mid;
        }
        if (!lo)
            return 0;
        const uint8_t *e = table + 12 * (lo - 1);
        uint32_t begin = rd32(e), end = rd32(e + 4), unwind = rd32(e + 8);
        if (rva < begin || rva >= end || !in_image(unwind, 4))
            return 0;
        uint8_t flags = g_image[unwind] >> 3, codes = g_image[unwind + 2];
        if (!(flags & UNW_FLAG_CHAININFO))
            return begin;
        uint32_t chained = unwind + 4 + 2 * ((codes + 1u) & ~1u);
        if (!in_image(chained, 12))
            return 0;
        rva = rd32(g_image + chained);                  /* the parent entry's BeginAddress */
    }
    return 0;
}

static int locate(const Pe *pe) {
    const uint8_t *hit = memmem(pe->file, pe->size, NEEDLE, sizeof NEEDLE);
    if (!hit)
        return set_error("the program has no Oodle decompressor (\"%s\" not found): is it Tekken 8's?", NEEDLE), -1;
    if (memmem(hit + 1, pe->size - (size_t)(hit + 1 - pe->file), NEEDLE, sizeof NEEDLE))
        return set_error("\"%s\" is in the program twice", NEEDLE), -1;
    uint32_t target;
    if (file_to_rva(pe, (uint64_t)(hit - pe->file), &target))
        return set_error("\"%s\" lies outside the sections", NEEDLE), -1;
    uint32_t tva, tn;
    if (code_section(pe, &tva, &tn) || !in_image(tva, tn))
        return set_error("no .text section"), -1;
    uint32_t found = 0;
    const uint8_t *code = g_image + tva;
    for (uint32_t i = 0; i + 7 <= tn; i++) {
        /* lea r64, [rip + disp32]: REX.W (0x48-0x4f), 0x8d, ModRM with mod 00 and r/m 101 */
        if ((code[i] & 0xf8) != 0x48 || code[i + 1] != 0x8d || (code[i + 2] & 0xc7) != 0x05)
            continue;
        int32_t disp = (int32_t)rd32(code + i + 3);
        if ((int64_t)tva + i + 7 + disp != (int64_t)target)
            continue;
        uint32_t f = primary_function(pe, tva + i);
        if (!f)
            return set_error("the reference at %#x is not inside a known function", tva + i), -1;
        if (found && f != found)
            return set_error("\"%s\" is referenced by more than one function (%#x, %#x)", NEEDLE, found, f), -1;
        found = f;
    }
    if (!found)
        return set_error("nothing references \"%s\"", NEEDLE), -1;
    g_function_rva = found;
    g_fn = (DecompressFn)(void *)(g_image + found);
    return 0;
}

/* ------------------------------------------------------------------------------------------- API */
static void unmap_all(void) {
    if (g_image)
        munmap(g_image, g_image_size);
    if (g_thunks)
        munmap(g_thunks, g_thunks_size);
    if (g_import_names) {
        for (unsigned i = 0; i < g_imports; i++)
            free(g_import_names[i]);
        free(g_import_names);
    }
    free(g_tls_block);
    g_image = g_thunks = g_tls_block = NULL;
    g_import_names = NULL;
    g_imports = 0;
    g_fn = NULL;
}

int oodle8_open(const char *exe, char *error, int error_size) {
    int rc = -1;
    pthread_mutex_lock(&g_lock);
    if (g_fn) {                             /* one image per process; any Tekken 8 exe's Oodle reads the same data */
        pthread_mutex_unlock(&g_lock);
        return 0;
    }
    g_error[0] = 0;
    int fd = open(exe, O_RDONLY | O_CLOEXEC);
    struct stat st;
    void *file = MAP_FAILED;
    if (fd < 0)
        set_error("cannot open %s", exe);
    else if (fstat(fd, &st) || st.st_size < 0x400)
        set_error("%s is not a program", exe);
    else if ((file = mmap(NULL, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0)) == MAP_FAILED)
        set_error("cannot read %s", exe);
    else {
        Pe pe = {.file = file, .size = (size_t)st.st_size};
        if (!parse_pe(&pe) && !map_image(&pe) && !relocate(&pe) && !bind_imports(&pe) && !setup_tls(&pe) &&
            !locate(&pe) && !protect_sections(&pe)) {
            if (!g_decoder)
                g_decoder = mmap(NULL, DECODER_MEMORY, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (g_decoder == MAP_FAILED) {
                g_decoder = NULL;
                set_error("out of memory");
            } else
                rc = 0;
        }
        if (rc)
            unmap_all();
    }
    if (file != MAP_FAILED)
        munmap(file, (size_t)st.st_size);
    if (fd >= 0)
        close(fd);
    if (rc && error && error_size > 0)
        snprintf(error, (size_t)error_size, "%s", g_error);
    pthread_mutex_unlock(&g_lock);
    return rc;
}

static void stack_bounds(uint64_t sp, uint64_t *base, uint64_t *limit) {
    pthread_attr_t attr;
    void *addr;
    size_t size;
    *base = sp + 0x10000;
    *limit = sp - (1u << 20);
    if (!pthread_getattr_np(pthread_self(), &attr)) {
        if (!pthread_attr_getstack(&attr, &addr, &size) && (uint64_t)(uintptr_t)addr < sp &&
            sp < (uint64_t)(uintptr_t)addr + size) {
            *limit = (uint64_t)(uintptr_t)addr + 0x2000;        /* above the guard page */
            *base = (uint64_t)(uintptr_t)addr + size;
        }
        pthread_attr_destroy(&attr);
    }
}

intptr_t oodle8_decompress(const void *comp, intptr_t comp_size, void *raw, intptr_t raw_size) {
    if (!comp || !raw || comp_size <= 0 || raw_size <= 0)
        return set_error("bad arguments"), OODLE8_BAD_ARGUMENTS;
    pthread_mutex_lock(&g_lock);
    if (!g_fn) {
        pthread_mutex_unlock(&g_lock);
        return set_error("oodle8_open has not succeeded"), OODLE8_NOT_OPEN;
    }
    uint64_t sp = (uint64_t)(uintptr_t)__builtin_frame_address(0), base, limit, old_gs = 0;
    stack_bounds(sp, &base, &limit);
    memset(g_teb, 0, sizeof g_teb);
    g_teb[0x08 / 8] = base;                                 /* NT_TIB StackBase */
    g_teb[0x10 / 8] = limit;                                /* NT_TIB StackLimit (__chkstk probes below it) */
    g_teb[0x30 / 8] = (uint64_t)(uintptr_t)g_teb;           /* NT_TIB Self */
    g_teb[0x58 / 8] = (uint64_t)(uintptr_t)g_tls_array;     /* ThreadLocalStoragePointer */
    g_teb[0x60 / 8] = (uint64_t)(uintptr_t)g_peb;           /* ProcessEnvironmentBlock */

    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_signal;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigemptyset(&sa.sa_mask);
    for (int i = 0; i < NSIGNALS; i++)
        sigaction(g_signals[i], &sa, &g_old[i]);
    syscall(SYS_arch_prctl, ARCH_GET_GS, &old_gs);

    volatile intptr_t got = 0;
    g_caller = pthread_self();
    g_trap_index = 0;
    g_signal = 0;
    int how = sigsetjmp(g_jump, 1);
    if (how == 0) {
        g_in_call = 1;
        syscall(SYS_arch_prctl, ARCH_SET_GS, (uint64_t)(uintptr_t)g_teb);
        got = g_fn(comp, comp_size, raw, raw_size, 1, 0, 0, NULL, 0, NULL, NULL, g_decoder, DECODER_MEMORY, 3);
    }
    g_in_call = 0;
    syscall(SYS_arch_prctl, ARCH_SET_GS, old_gs);
    for (int i = 0; i < NSIGNALS; i++)
        sigaction(g_signals[i], &g_old[i], NULL);
    if (how == 1) {
        uint64_t i = g_trap_index;
        set_error("the game's decompressor called %s, which is not available here",
                  i < g_imports && g_import_names[i] ? g_import_names[i] : "a Windows function");
        got = OODLE8_IMPORT;
    } else if (how == 2) {
        uint64_t ip = g_fault_ip, img = (uint64_t)(uintptr_t)g_image;
        set_error("the game's decompressor stopped with signal %d (address %p, code at image offset %#llx)",
                  g_signal, g_fault_address,
                  (unsigned long long)(ip >= img && ip < img + g_image_size ? ip - img : ip));
        got = OODLE8_FAULT;
    } else if (got != raw_size)
        set_error("Oodle decoded %lld of %lld bytes", (long long)got, (long long)raw_size);
    pthread_mutex_unlock(&g_lock);
    return got;
}
