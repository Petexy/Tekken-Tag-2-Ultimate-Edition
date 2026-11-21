#include "host/perf.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <system_error>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <pthread.h>
#include <sched.h>
#endif

namespace cafe::host {

void tune_process_timing() {
#ifdef _WIN32
    if (const char* e = std::getenv("TTT2_TIMER_RES"); e && std::strcmp(e, "0") == 0) return;
    // timeBeginPeriod from winmm, looked up so that nothing else links it.
    bool timer = false;
    if (HMODULE winmm = LoadLibraryW(L"winmm.dll")) {
        using TimeBeginPeriod = UINT(WINAPI*)(UINT);
        if (auto begin = reinterpret_cast<TimeBeginPeriod>(reinterpret_cast<void*>(GetProcAddress(winmm, "timeBeginPeriod")))) {
            timer = begin(1) == 0; // TIMERR_NOERROR
        }
    }
    // Windows 11 may still ignore the resolution of a process it throttles
    // (an occluded or minimised window, a laptop on battery): opt out.
    // (PROCESS_POWER_THROTTLING_STATE, by value: older SDK headers lack it.)
    struct Throttling {
        ULONG version, control_mask, state_mask;
    } state{1, 0x1 | 0x4, 0}; // EXECUTION_SPEED | IGNORE_TIMER_RESOLUTION, both off
    bool unthrottled = false;
    using SetProcessInformationFn = BOOL(WINAPI*)(HANDLE, int, LPVOID, DWORD);
    if (auto set = reinterpret_cast<SetProcessInformationFn>(
            reinterpret_cast<void*>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "SetProcessInformation")))) {
        unthrottled = set(GetCurrentProcess(), 4 /* ProcessPowerThrottling */, &state, sizeof state) != 0;
    }
    std::fprintf(stderr, "ttt2: timing: 1 ms timer resolution %s, power throttling %s\n", timer ? "set" : "not available",
                 unthrottled ? "off" : "unchanged");
#endif
}

void lower_thread_priority() {
#ifdef _WIN32
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_BELOW_NORMAL);
#endif
}

uint64_t executable_stamp() {
    std::filesystem::path self;
#ifdef _WIN32
    wchar_t buffer[MAX_PATH * 2] = {};
    const DWORD n = GetModuleFileNameW(nullptr, buffer, static_cast<DWORD>(std::size(buffer)));
    if (n == 0 || n >= std::size(buffer)) return 0;
    self = buffer;
#else
    std::error_code ec;
    self = std::filesystem::read_symlink("/proc/self/exe", ec);
    if (ec) return 0;
#endif
    std::error_code ec;
    const uint64_t size = std::filesystem::file_size(self, ec);
    if (ec) return 0;
    const auto time = std::filesystem::last_write_time(self, ec);
    if (ec) return 0;
    const uint64_t ticks = static_cast<uint64_t>(time.time_since_epoch().count());
    return (size * 0x9E3779B97F4A7C15ull) ^ ticks ^ 0x7474743277726D21ull;
}

} // namespace cafe::host
