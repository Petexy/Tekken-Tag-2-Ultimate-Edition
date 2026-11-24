// What the launcher does first (see startup.h).

#include "startup.h"

#include "payload.h"

#ifdef _WIN32
#include "win32.h"
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <shellapi.h>
#else
#include <fstream>
#endif

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <thread>

namespace launcher::startup {

namespace {

using Clock = std::chrono::steady_clock;

void write_out(const std::string& text, bool error) {
#ifdef _WIN32
    // (A -mwindows program: the C runtime's streams may not be connected; the handles a caller gave it are.)
    HANDLE out = GetStdHandle(error ? STD_ERROR_HANDLE : STD_OUTPUT_HANDLE);
    DWORD n = 0;
    if (out && out != INVALID_HANDLE_VALUE) WriteFile(out, text.data(), static_cast<DWORD>(text.size()), &n, nullptr);
#else
    std::fputs(text.c_str(), error ? stderr : stdout);
    std::fflush(error ? stderr : stdout);
#endif
}

std::string get_environment(const char* name) {
#ifdef _WIN32
    return win32::narrow(win32::environment(win32::wide(name).c_str()));
#else
    const char* value = std::getenv(name);
    return value ? value : "";
#endif
}

void set_environment(const char* name, const std::string& value) {
#ifdef _WIN32
    SetEnvironmentVariableW(win32::wide(name).c_str(), value.empty() ? nullptr : win32::wide(value).c_str());
#else
    if (value.empty()) {
        unsetenv(name);
    } else {
        setenv(name, value.c_str(), 1);
    }
#endif
}

std::string absolute(const std::string& path) {
    std::error_code ec;
#ifdef _WIN32
    const fs::path p = fs::absolute(fs::path(win32::wide(path)), ec);
    return ec ? path : win32::narrow(p.lexically_normal().wstring());
#else
    const fs::path p = fs::absolute(fs::path(path), ec);
    return ec ? path : p.lexically_normal().string();
#endif
}

#ifdef _WIN32
fs::path own_exe() {
    std::wstring self(32768, L'\0');
    const DWORD n = GetModuleFileNameW(nullptr, self.data(), static_cast<DWORD>(self.size()));
    if (!n || n >= self.size()) throw std::runtime_error("Cannot locate Ultimate Launcher.");
    self.resize(n);
    return fs::path(self);
}
#endif

} // namespace

std::vector<std::string> arguments(int argc, char** argv) {
    std::vector<std::string> out;
#ifdef _WIN32
    (void)argc;
    (void)argv;
    int count = 0;
    if (LPWSTR* wide = CommandLineToArgvW(GetCommandLineW(), &count)) {
        for (int i = 1; i < count; ++i) out.push_back(win32::narrow(wide[i]));
        LocalFree(wide);
    }
#else
    for (int i = 1; i < argc; ++i) out.emplace_back(argv[i]);
#endif
    return out;
}

bool wait_for_exit(int64_t pid, double seconds) {
    if (pid <= 0) return true;
#ifdef _WIN32
    HANDLE process = OpenProcess(SYNCHRONIZE, FALSE, static_cast<DWORD>(pid));
    if (!process) return true;
    const bool gone = WaitForSingleObject(process, static_cast<DWORD>(seconds * 1000)) == WAIT_OBJECT_0;
    CloseHandle(process);
    return gone;
#else
    // (Its parent may never reap it: a zombie counts as gone. /proc/<pid>/stat: "pid (name) S ...".)
    const auto t0 = Clock::now();
    for (;;) {
        std::ifstream in("/proc/" + std::to_string(pid) + "/stat");
        std::string stat;
        std::getline(in, stat);
        const size_t paren = stat.rfind(')');
        if (!in || paren == std::string::npos || paren + 2 >= stat.size()) return true;
        const char state = stat[paren + 2];
        if (state == 'Z' || state == 'X') return true;
        if (std::chrono::duration<double>(Clock::now() - t0).count() >= seconds) return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
#endif
}

std::string activation_token() {
    std::string token = get_environment("XDG_ACTIVATION_TOKEN");
    return token.empty() ? get_environment("DESKTOP_STARTUP_ID") : token;
}

Start begin(const std::vector<std::string>& args, const Program& program) {
    Start start;
    start.args = args;
    const auto tell = [&](const std::string& text) {
        if (program.tell) {
            program.tell(text);
            return;
        }
        write_out(program.name + ": " + text + "\n", true);
#ifdef _WIN32
        MessageBoxW(nullptr, win32::wide(text).c_str(), L"Ultimate Launcher", MB_OK | MB_ICONINFORMATION);
#endif
    };

    // 1. Questions answered before anything else.
    for (const std::string& arg : args) {
        if (arg == "--version") {
            write_out(program.name + " " + program.version + "\n", false);
            start.exit = 0;
            return start;
        }
    }
    for (const std::string& arg : args) {
        if (arg == "--help" || arg == "-h") {
            write_out(program.usage, false);
            start.exit = 0;
            return start;
        }
    }
#ifdef _WIN32
    if (!args.empty() && args[0] == "--unpack") {
        // (Asked by a program: errors to standard error, never a window.)
        try {
            if (args.size() != 2) throw std::runtime_error("--unpack takes one folder.");
            const auto files = payload::own(own_exe());
            if (!files) throw std::runtime_error("This launcher holds no files.");
            payload::unpack(*files, fs::path(win32::wide(args[1])));
            start.exit = 0;
        } catch (const std::exception& error) {
            write_out(program.name + ": " + error.what() + "\n", true);
            start.exit = 1;
        }
        return start;
    }
#endif
    std::vector<size_t> files_args; // (positional: paths to hand over absolute)
    for (size_t i = 0; i < args.size(); ++i) {
        const std::string& arg = args[i];
        if (arg.size() < 2 || arg[0] != '-') {
            files_args.push_back(i);
            continue;
        }
        bool known = false;
        for (const auto& [name, values] : program.options) {
            if (arg != name) continue;
            known = i + values < args.size() || values == 0;
            if (known) i += static_cast<size_t>(values);
            break;
        }
        if (!known) {
            write_out(program.name + ": unknown option " + arg + "\n" + program.usage, true);
            start.exit = 2;
            return start;
        }
    }

    try {
        // 2. The launcher this one replaces ends first.
        const std::string after = get_environment("TTT2_LAUNCHER_AFTER");
        set_environment("TTT2_LAUNCHER_AFTER", "");
#ifdef _WIN32
        const double after_wait = program.after_seconds >= 0 ? program.after_seconds : 60;
#else
        const double after_wait = program.after_seconds >= 0 ? program.after_seconds : 10;
#endif
        if (!after.empty()) wait_for_exit(std::strtoll(after.c_str(), nullptr, 10), after_wait);
#ifdef _WIN32
        const fs::path exe = own_exe();
        // (Only the trailer's digest for now: the files are checked when unpacked.)
        const auto unchecked = payload::own(exe, false);
        if (unchecked) {
            DeleteFileW((exe.parent_path() / (exe.stem().wstring() + L".old.exe")).c_str()); // (what an update replaced)
            start.files_digest = unchecked->digest();
        }
#endif

        // 3. One launcher per user.
        if (program.unique) {
            InstanceOptions options;
            if (!program.instance_name.empty()) options.name = program.instance_name;
            options.message.args = args;
            for (const size_t i : files_args) options.message.args[i] = absolute(args[i]);
            options.message.token = activation_token();
            options.files = start.files_digest;
            options.after = !after.empty();
            if (program.after_seconds >= 0) options.after_seconds = program.after_seconds;
            options.wake = program.wake;
            if (!program.instance_name.empty()) options.old_bus_name.clear(); // (tests never reach a real launcher)
            InstanceClaim claim = claim_instance(options);
            switch (claim.result) {
            case InstanceClaim::Result::kPrimary:
                start.instance = std::move(claim.instance);
                break;
            case InstanceClaim::Result::kForwarded:
                if (!start.files_digest.empty() && claim.other_files != start.files_digest) {
                    tell("Another Ultimate Launcher is already running. Close it to switch to this one, then start "
                         "this one again.");
                }
                start.exit = 0;
                return start;
            case InstanceClaim::Result::kOldLauncher:
                if (!claim.error.empty()) {
                    tell("An older Ultimate Launcher is running. Close it, then start this one again.");
                    start.exit = 1;
                } else {
                    start.exit = 0;
                }
                return start;
            case InstanceClaim::Result::kFailed:
                tell(claim.error);
                start.exit = 1;
                return start;
            case InstanceClaim::Result::kAlone:
                start.note = "runs alone: " + claim.error;
                break;
            }
        }

#ifdef _WIN32
        // 4. The release .exe's files.
        if (unchecked) {
            const auto files = payload::own(exe);
            const fs::path folder = payload::files_folder();
            // (Started twice at once without the single instance (tests): one unpacks, the other finds them.)
            HANDLE lock = CreateMutexW(nullptr, FALSE, payload::kFilesMutex);
            if (lock) WaitForSingleObject(lock, INFINITE);
            try {
                payload::unpack(*files, folder);
            } catch (...) {
                if (lock) {
                    ReleaseMutex(lock);
                    CloseHandle(lock);
                }
                throw;
            }
            if (lock) {
                ReleaseMutex(lock);
                CloseHandle(lock);
            }
            start.files = folder;
            SetEnvironmentVariableW(L"TTT2_LAUNCHER_EXE", exe.c_str());
        }
        SetEnvironmentVariableW(L"TTT2_LAUNCHER_UI_PID", std::to_wstring(GetCurrentProcessId()).c_str());
#endif
    } catch (const std::exception& error) {
        start.instance.reset();
        tell(error.what());
        start.exit = 1;
    }
    return start;
}

} // namespace launcher::startup
