#include "cafe/generated.h"
#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "os/kernel.h"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <dlfcn.h>
#include <pthread.h>
#include <signal.h>
#include <ucontext.h>
#include <unistd.h>

#endif

#include <algorithm>
#include <string>
#include <vector>
#include <unordered_map>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <mutex>
#include <thread>

namespace cafe {
namespace {

thread_local PPCContext* t_current = nullptr;

void print_backtrace(const PPCContext& ctx) {
    std::fprintf(stderr, "guest backtrace (LR, then saved return addresses):\n");
    std::fprintf(stderr, "  0x%08X\n", ctx.lr);
    uint32_t frame = ctx.r[1];
    for (int depth = 0; depth < 48; ++depth) {
        if (!guest_memory_committed(frame, 8)) {
            break;
        }
        const uint32_t back = ppc::ld32(guest_base(), frame);
        if (back == 0 || back <= frame || !guest_memory_committed(back, 8)) {
            break;
        }
        std::fprintf(stderr, "  0x%08X\n", ppc::ld32(guest_base(), back + 4));
        frame = back;
    }
}

#ifdef _WIN32
LONG WINAPI windows_fault_handler(EXCEPTION_POINTERS* exception) {
    const auto code = exception->ExceptionRecord->ExceptionCode;
    const auto pc = exception->ExceptionRecord->ExceptionAddress;
    std::fprintf(stderr, "\nhost exception 0x%08lX at %p\n", code, pc);
    if ((code == EXCEPTION_ACCESS_VIOLATION || code == EXCEPTION_IN_PAGE_ERROR) &&
        exception->ExceptionRecord->NumberParameters >= 2) {
        const auto address = exception->ExceptionRecord->ExceptionInformation[1];
        const auto base = reinterpret_cast<uintptr_t>(guest_base());
        if (base && address >= base && address - base < (uint64_t{1} << 32) + 0x10000)
            std::fprintf(stderr, "guest memory fault at 0x%08llX\n",
                static_cast<unsigned long long>(address - base));
    }
    const auto module = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    std::fprintf(stderr, "host executable offset: 0x%llX\n",
        static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(pc) - module));
    if (t_current) print_guest_state(*t_current);
    std::fflush(stderr);
    return EXCEPTION_EXECUTE_HANDLER;
}
#else
void fault_handler(int signal, siginfo_t* info, void* context) {
    const auto host = reinterpret_cast<uintptr_t>(info->si_addr);
    const auto base = reinterpret_cast<uintptr_t>(guest_base());
    if (base != 0 && host >= base && host - base < (uint64_t{1} << 32) + 0x10000) {
        const uint64_t guest = host - base;
        std::fprintf(stderr, "\nguest memory fault: access to unmapped guest address 0x%08llX\n",
                     static_cast<unsigned long long>(guest));
        // Just below the stack pointer: a frame larger than the stack left.
        if (t_current != nullptr && guest < t_current->r[1] && t_current->r[1] - guest <= (4u << 20)) {
            std::fprintf(stderr, "(0x%llX bytes below the stack pointer: a stack overflow)\n",
                         static_cast<unsigned long long>(t_current->r[1] - guest));
        }
    } else {
        std::fprintf(stderr, "\nhost fault (signal %d) at %p\n", signal, info->si_addr);
    }
    // Where in the recompiled code: `addr2line -f -e <executable> <offset>`
    // names the guest function (sub_XXXXXXXX).
    const auto* uc = static_cast<const ucontext_t*>(context);
    const auto pc = static_cast<uintptr_t>(uc->uc_mcontext.gregs[REG_RIP]);
    Dl_info where{};
    if (dladdr(reinterpret_cast<void*>(pc), &where) && where.dli_fname != nullptr) {
        std::fprintf(stderr, "host code: %s+0x%llx\n", where.dli_fname,
                     static_cast<unsigned long long>(pc - reinterpret_cast<uintptr_t>(where.dli_fbase)));
    }
    if (t_current != nullptr) {
        print_guest_state(*t_current);
    }
    std::_Exit(128 + signal);
}
#endif

} // namespace

PPCContext* current_context() { return t_current; }
void set_current_context(PPCContext* ctx) { t_current = ctx; }

void print_guest_state(const PPCContext& ctx) {
    for (int i = 0; i < 32; i += 4) {
        std::fprintf(stderr, "  r%-2d %08X  r%-2d %08X  r%-2d %08X  r%-2d %08X\n", i,
                     ctx.r[i], i + 1, ctx.r[i + 1], i + 2, ctx.r[i + 2], i + 3, ctx.r[i + 3]);
    }
    std::fprintf(stderr, "  lr %08X  ctr %08X  cr %08X  xer %08X\n", ctx.lr, ctx.ctr,
                 ppc::mfcr(ctx), ppc::mfxer(ctx));
    print_backtrace(ctx);
}

void fatal(const char* format, ...) {
    std::fflush(stdout);
    std::fprintf(stderr, "\nttt2: ");
    va_list args;
    va_start(args, format);
    std::vfprintf(stderr, format, args);
    va_end(args);
    std::fprintf(stderr, "\n");
    if (t_current != nullptr) {
        print_guest_state(*t_current);
    }
    std::fflush(stderr);
    // Not exit(): other guest threads still use the objects static
    // destructors would tear down.
    std::_Exit(70);
}

// ------------------------------------------------- CPU time per thread
namespace {

struct TrackedThread {
    std::thread::id id;
    std::string name;
    uint32_t guest; // 0 for a runtime thread
#ifdef _WIN32
    HANDLE handle;
#else
    clockid_t clock;
#endif
    double used; // CPU seconds at the last report
};
std::mutex g_tracked_mutex;
std::vector<TrackedThread> g_tracked;
std::chrono::steady_clock::time_point g_last_report = std::chrono::steady_clock::now();

#ifdef _WIN32
// ------------------------------------------------------ sampling profiler
// TTT2_PROFILE_CPU=1: every millisecond each tracked thread that used CPU
// since the last look is stopped for a moment and where it is noted, with
// the functions it was called from (unwound with the executable's unwind
// tables). profile_report() names the functions the samples of the last
// seconds were in: by itself (the innermost one) and with what it called.
// Addresses are the executable's (its preferred base): llvm-symbolizer
// --obj=<exe> names them (sub_XXXXXXXX: the game's function at XXXXXXXX).
constexpr int kDepth = 12;
constexpr uint32_t kOutside = 0xFFFFFFFFu; // a function of another module (driver, system)
struct Sample {
    double time;
    uint32_t guest; // 0: a runtime thread
    uint8_t depth;
    uint32_t function[kDepth]; // the executable's function starts (RVA), innermost first
};
constexpr size_t kSamples = size_t{1} << 18;
Sample* g_samples = nullptr;
std::atomic<uint64_t> g_sample_count{0};
const bool g_profiling = [] {
    const char* e = std::getenv("TTT2_PROFILE_CPU");
    return e != nullptr && *e != '\0' && *e != '0';
}();

double steady_seconds() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

void profiler_main() {
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
    const auto exe = reinterpret_cast<DWORD64>(GetModuleHandleW(nullptr));
    std::unordered_map<HANDLE, ULONG64> cycles;
    for (;;) {
        Sleep(1);
        std::lock_guard lock(g_tracked_mutex);
        for (const TrackedThread& t : g_tracked) {
            ULONG64 c = 0;
            if (!QueryThreadCycleTime(t.handle, &c)) continue;
            ULONG64& last = cycles[t.handle];
            // Only a thread that ran for a good part of the last millisecond
            // (1M cycles: a quarter of it at 4 GHz); a thread waking from a
            // wait for a moment would fill the profile with waits.
            const bool ran = last != 0 && c - last >= 1000000;
            last = c;
            if (!ran) continue;
            // Nothing below allocates while the thread is stopped (it may hold the heap's lock).
            Sample s{};
            if (SuspendThread(t.handle) == static_cast<DWORD>(-1)) continue;
            CONTEXT ctx{};
            ctx.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER;
            if (GetThreadContext(t.handle, &ctx)) {
                for (int d = 0; d < kDepth && ctx.Rip != 0; ++d) {
                    DWORD64 image = 0;
                    PRUNTIME_FUNCTION f = RtlLookupFunctionEntry(ctx.Rip, &image, nullptr);
                    s.function[d] = (f != nullptr && image == exe) ? f->BeginAddress : kOutside;
                    s.depth = static_cast<uint8_t>(d + 1);
                    if (f == nullptr) { // a leaf without a frame: its return address on top
                        if (image != 0 || ctx.Rsp == 0) break;
                        ctx.Rip = *reinterpret_cast<const DWORD64*>(ctx.Rsp);
                        ctx.Rsp += 8;
                        continue;
                    }
                    PVOID handler_data = nullptr;
                    DWORD64 frame = 0;
                    RtlVirtualUnwind(UNW_FLAG_NHANDLER, image, ctx.Rip, f, &ctx, &handler_data, &frame, nullptr);
                }
            }
            ResumeThread(t.handle);
            if (s.depth == 0) continue;
            s.time = steady_seconds();
            s.guest = t.guest;
            const uint64_t n = g_sample_count.load(std::memory_order_relaxed);
            g_samples[n % kSamples] = s;
            g_sample_count.store(n + 1, std::memory_order_release);
        }
    }
}

uint64_t preferred_base() {
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(GetModuleHandleW(nullptr));
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(reinterpret_cast<const uint8_t*>(dos) + dos->e_lfanew);
    return nt->OptionalHeader.ImageBase;
}
#endif

// User and kernel time together; negative when it cannot be read.
double cpu_seconds(const TrackedThread& t) {
#ifdef _WIN32
    FILETIME created, exited, kernel, user;
    if (!GetThreadTimes(t.handle, &created, &exited, &kernel, &user)) return -1;
    const auto ticks = [](FILETIME f) { return (uint64_t{f.dwHighDateTime} << 32) | f.dwLowDateTime; };
    return static_cast<double>(ticks(kernel) + ticks(user)) * 1e-7;
#else
    timespec ts;
    if (clock_gettime(t.clock, &ts) != 0) return -1;
    return static_cast<double>(ts.tv_sec) + static_cast<double>(ts.tv_nsec) * 1e-9;
#endif
}

std::string guest_thread_name(const TrackedThread& t) {
    const uint32_t name = ppc::ld32(guest_base(), t.guest + os::osthread::kName);
    std::string s;
    for (uint32_t i = 0; name != 0 && i < 31 && guest_memory_committed(name + i, 1); ++i) {
        const char c = static_cast<char>(*guest_pointer(name + i));
        if (c == '\0') break;
        s += c;
    }
    if (s.empty()) s = t.name;
    return s;
}

} // namespace

void track_thread_cpu(const char* name, uint32_t guest_thread) {
    TrackedThread t{std::this_thread::get_id(), name ? name : "", guest_thread, {}, 0};
    if (t.name.empty()) {
        char address[16];
        std::snprintf(address, sizeof address, "%08X", guest_thread);
        t.name = address;
    }
#ifdef _WIN32
    t.handle = OpenThread(THREAD_QUERY_LIMITED_INFORMATION | THREAD_QUERY_INFORMATION | THREAD_SUSPEND_RESUME |
                              THREAD_GET_CONTEXT,
                          FALSE, GetCurrentThreadId());
    if (t.handle == nullptr) t.handle = OpenThread(THREAD_QUERY_LIMITED_INFORMATION, FALSE, GetCurrentThreadId());
    if (t.handle == nullptr) return;
    if (g_profiling) {
        static std::once_flag started;
        std::call_once(started, [] {
            g_samples = new Sample[kSamples];
            std::thread(profiler_main).detach();
            std::fprintf(stderr, "ttt2: profile: sampling the tracked threads every millisecond (TTT2_PROFILE_CPU)\n");
        });
    }
#else
    if (pthread_getcpuclockid(pthread_self(), &t.clock) != 0) return;
#endif
    t.used = std::max(0.0, cpu_seconds(t));
    std::lock_guard lock(g_tracked_mutex);
    g_tracked.push_back(t);
}

void untrack_thread_cpu() {
    std::lock_guard lock(g_tracked_mutex);
    const auto it = std::find_if(g_tracked.begin(), g_tracked.end(),
                                 [](const TrackedThread& t) { return t.id == std::this_thread::get_id(); });
    if (it == g_tracked.end()) return;
#ifdef _WIN32
    CloseHandle(it->handle);
#endif
    g_tracked.erase(it);
}

std::string thread_cpu_report() {
    std::lock_guard lock(g_tracked_mutex);
    const auto now = std::chrono::steady_clock::now();
    const double seconds = std::max(std::chrono::duration<double>(now - g_last_report).count(), 1e-3);
    g_last_report = now;
    std::string out;
    char item[96];
    double guests = 0, busiest = -1;
    const TrackedThread* busiest_thread = nullptr;
    for (TrackedThread& t : g_tracked) {
        const double used = cpu_seconds(t);
        if (used < 0) continue;
        const double percent = (used - t.used) * 100.0 / seconds;
        t.used = used;
        if (t.guest != 0) {
            guests += percent;
            if (percent > busiest) busiest = percent, busiest_thread = &t;
            continue;
        }
        std::snprintf(item, sizeof item, "%s%s %.0f%%", out.empty() ? "" : ", ", t.name.c_str(), percent);
        out += item;
    }
    std::snprintf(item, sizeof item, "; guest threads %.0f%%", guests);
    out += item;
    if (busiest_thread != nullptr) {
        std::snprintf(item, sizeof item, ", busiest %s %.0f%%", guest_thread_name(*busiest_thread).c_str(), busiest);
        out += item;
    }
    return out;
}

void profile_report(double seconds, const char* label) {
#ifdef _WIN32
    if (!g_profiling || g_samples == nullptr) return;
    const double now = steady_seconds();
    const uint64_t count = g_sample_count.load(std::memory_order_acquire);
    std::unordered_map<uint32_t, uint32_t> self, inclusive, threads;
    uint32_t total = 0;
    for (uint64_t i = count; i > 0 && count - i < kSamples; --i) {
        const Sample& s = g_samples[(i - 1) % kSamples];
        if (now - s.time > seconds) break;
        ++total;
        ++self[s.function[0]];
        ++threads[s.guest];
        uint32_t seen[kDepth];
        int distinct = 0;
        for (int d = 0; d < s.depth; ++d) {
            const uint32_t f = s.function[d];
            if (std::find(seen, seen + distinct, f) != seen + distinct) continue;
            seen[distinct++] = f;
            ++inclusive[f];
        }
    }
    if (total == 0) return;
    const uint64_t base = 0x140000000ull; // (the linker's default base: llvm-symbolizer --obj=<exe> takes these)
    (void)preferred_base;
    const auto sorted = [](const std::unordered_map<uint32_t, uint32_t>& m) {
        std::vector<std::pair<uint32_t, uint32_t>> v(m.begin(), m.end());
        std::sort(v.begin(), v.end(), [](const auto& a, const auto& b) { return a.second > b.second; });
        return v;
    };
    const auto top = [&](const std::unordered_map<uint32_t, uint32_t>& m, size_t n, const char* what) {
        const auto v = sorted(m);
        std::string out;
        char item[64];
        for (size_t i = 0; i < v.size() && i < n; ++i) {
            if (v[i].first == kOutside) std::snprintf(item, sizeof item, " other-module:%u%%", v[i].second * 100 / total);
            else std::snprintf(item, sizeof item, " 0x%llx:%u%%", static_cast<unsigned long long>(base + v[i].first),
                               v[i].second * 100 / total);
            out += item;
        }
        std::fprintf(stderr, "ttt2: profile: %s %s:%s\n", label, what, out.c_str());
    };
    std::fprintf(stderr, "ttt2: profile: %s: %u samples in %.0f ms\n", label, total, seconds * 1000.0);
    {
        const auto v = sorted(threads);
        std::string out;
        char item[64];
        for (size_t i = 0; i < v.size() && i < 6; ++i) {
            std::snprintf(item, sizeof item, " %08X:%u%%", v[i].first, v[i].second * 100 / total);
            out += item;
        }
        std::fprintf(stderr, "ttt2: profile: %s threads (guest OSThread; 00000000: the runtime's):%s\n", label, out.c_str());
    }
    top(self, 12, "self");
    top(inclusive, 25, "inclusive");
#else
    (void)seconds;
    (void)label;
#endif
}

void install_fault_handler() {
#ifdef _WIN32
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    SetUnhandledExceptionFilter(windows_fault_handler);
#else
    static char alternate_stack[64 * 1024];
    stack_t stack{};
    stack.ss_sp = alternate_stack;
    stack.ss_size = sizeof alternate_stack;
    sigaltstack(&stack, nullptr);
    struct sigaction action{};
    action.sa_sigaction = fault_handler;
    action.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigaction(SIGSEGV, &action, nullptr);
    sigaction(SIGBUS, &action, nullptr);
#endif
}

} // namespace cafe

// ------------------------------------------------- hooks for generated code
extern "C" {

void cafe_ppc_trap(cafe::PPCContext& ctx, uint32_t address) {
    cafe::set_current_context(&ctx);
    cafe::fatal("guest trap instruction at 0x%08X (an assertion in game code)", address);
}

void cafe_ppc_illegal(cafe::PPCContext& ctx, uint32_t address, uint32_t word,
                      const char* reason) {
    cafe::set_current_context(&ctx);
    cafe::fatal("cannot execute instruction 0x%08X at 0x%08X: %s", word, address, reason);
}

void cafe_ppc_null_call(cafe::PPCContext& ctx, uint32_t address) {
    cafe::set_current_context(&ctx);
    cafe::fatal("call through an unresolved weak symbol (address 0) at 0x%08X", address);
}

void cafe_ppc_bad_return(cafe::PPCContext& ctx, uint32_t expected) {
    cafe::set_current_context(&ctx);
    cafe::fatal("a guest call returned with LR=0x%08X instead of its return address "
                "0x%08X: the callee returned somewhere other than its caller "
                "(longjmp-style control flow the port does not model yet)",
                ctx.lr, expected);
}

// The Espresso time base runs at a quarter of the 248.625 MHz bus clock.
uint64_t cafe_ppc_timebase(void) {
    static const auto start = std::chrono::steady_clock::now();
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                        std::chrono::steady_clock::now() - start)
                        .count();
    constexpr uint64_t kHz = 62156250;
    const auto t = static_cast<uint64_t>(ns);
    return (t / 1000000000u) * kHz + (t % 1000000000u) * kHz / 1000000000u;
}

void cafe_unimplemented_import(cafe::PPCContext& ctx, const char* module, const char* name) {
    cafe::set_current_context(&ctx);
    cafe::fatal("the game called %s:%s, which the runtime does not implement yet", module,
                name);
}

} // extern "C"
