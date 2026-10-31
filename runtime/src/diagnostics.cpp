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
    t.handle = OpenThread(THREAD_QUERY_LIMITED_INFORMATION, FALSE, GetCurrentThreadId());
    if (t.handle == nullptr) return;
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
