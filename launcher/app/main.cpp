// ttt2-launcher (Golden Fist Launcher): first what needs no window (core/startup: --version, --help, the launcher it
// replaces waited for, one launcher per user), then SDL and the window (app.h).
//
//   ttt2-launcher [GAME.wua] [--screenshot FILE [--size WxH] [--scale S]] | --version | --help
//   Windows (the source ZIP's bridge, launcher/windows/build_launcher.py): [--files DIR] [--build-dir DIR]
//   [--config FILE] [--ui-smoke-test FILE]

#include "app.h"

#include "paths.h"
#include "release.h"
#include "startup.h"
#ifdef _WIN32
#include "win32.h"
#endif

#include <SDL3/SDL.h>
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <share.h>
#else
#include <sys/stat.h>
#include <unistd.h>
#endif

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <ctime>

namespace {

const char* const kUsage =
    "usage: ttt2-launcher [GAME.wua] [--screenshot FILE | --frames DIR [--at MS,...]] [--size WxH] [--scale S]\n"
    "                     [--files DIR] [--build-dir DIR] [--config FILE] [--ui-smoke-test FILE]\n"
    "       ttt2-launcher --version\n"
    "  Installs Tekken Tag Tournament 2 from your own .wua (the game program is built on this PC),\n"
    "  starts it, and adds Tekken 7's and Tekken 8's characters from your own copies of them.\n"
    "  --screenshot FILE  saves the window as a PNG once it has loaded (after the test actions of\n"
    "                     TTT2_LAUNCHER_TEST_ACTIONS), then quits (for tests; drawn offscreen)\n"
    "  --size WxH         the window's size for --screenshot (default 1280x800)\n"
    "  --scale S          the interface's scale for --screenshot\n"
    "  --frames DIR       after the last test action: frames at --at MS,MS,... (default\n"
    "                     0,50,100,200,400,700) and once settled, each checked; then quits\n"
    "  --version          prints its version (\"ttt2-launcher <ver>\")\n"
    "  --files DIR        (Windows) the launcher's files are in DIR (main.py's project), not beside it\n"
    "  --build-dir DIR    (Windows) main.py's build folder, when not DIR\\build-windows-tools\n"
    "  --config FILE      (Windows) main.py's launcher.json, when not its own\n"
    "  --ui-smoke-test FILE  draws the first frame with this PC's display, writes what it found as JSON\n"
    "                     to FILE and ends (0: drawn); TTT2_LAUNCHER_TEST_SMOKE=FILE does the same for\n"
    "                     a start as a player's (an update's reopening), with what the start found\n"
    "  Tests: TTT2_LAUNCHER_TEST_CUES=1 prints each sound cue (\"@cue <name>\"); TTT2_LAUNCHER_TEST_WINDOW=real\n"
    "  keeps a real window (a headless compositor) instead of drawing offscreen; tests sound through SDL's dummy\n"
    "  audio driver unless SDL_AUDIO_DRIVER or TTT2_LAUNCHER_TEST_AUDIO names another (e.g. disk).\n";

void wake() {
    // (A later start was handed over: the loop looks at it. Before SDL is up the event is dropped: the loop looks
    // at every start anyway.)
    if (SDL_WasInit(SDL_INIT_EVENTS)) {
        SDL_Event e{};
        e.type = SDL_EVENT_USER;
        SDL_PushEvent(&e);
    }
}

bool size_of(const char* text, int& w, int& h) {
    return text && std::sscanf(text, "%dx%d", &w, &h) == 2 && w >= 320 && h >= 240;
}

// An argument (UTF-8) as a path: wide on Windows, so that a José in it is kept.
std::filesystem::path arg_path(const std::string& a) {
#ifdef _WIN32
    return std::filesystem::path(std::u8string(a.begin(), a.end()));
#else
    return a;
#endif
}

std::string utf8(const std::filesystem::path& p) {
    const std::u8string u = p.u8string();
    return std::string(u.begin(), u.end());
}

// A variable of this process as it is now (Windows: begin() changes the process's own; the C runtime keeps a copy).
std::string environment(const char* name) {
#ifdef _WIN32
    // (Wide, as UTF-8: the A function would give the ANSI code page's letters.)
    return launcher::win32::narrow(launcher::win32::environment(launcher::win32::wide(name).c_str()));
#else
    const char* value = std::getenv(name);
    return value ? value : "";
#endif
}

// `text` as a JSON string.
std::string json_string(const std::string& text) {
    std::string out = "\"";
    for (const char c : text) {
        if (c == '"' || c == '\\') out += '\\';
        if (static_cast<unsigned char>(c) < 0x20) {
            char escape[8];
            std::snprintf(escape, sizeof escape, "\\u%04x", static_cast<unsigned>(c));
            out += escape;
        } else {
            out += c;
        }
    }
    return out + "\"";
}

// The launcher's own log: what it writes to standard error (its banner, what it started, why something failed) goes
// to a file when nobody reads it (a start from the desktop's menu or file manager, an update's reopening: no
// terminal, pipe or file was given): Linux ~/.cache/ttt2/launcher.log, Windows <files>\local\launcher.log (beside
// the program for a CMake build). Over 1 MB it is kept as launcher.old.log and begun anew.
bool stderr_is_read() {
#ifdef _WIN32
    const HANDLE h = GetStdHandle(STD_ERROR_HANDLE);
    if (!h || h == INVALID_HANDLE_VALUE) return false;
    const DWORD type = GetFileType(h);
    return type == FILE_TYPE_PIPE || type == FILE_TYPE_DISK; // (NUL and nothing: not read)
#else
    struct stat s {};
    return isatty(STDERR_FILENO) ||
           (fstat(STDERR_FILENO, &s) == 0 && (S_ISFIFO(s.st_mode) || S_ISREG(s.st_mode))); // (journal, /dev/null: no)
#endif
}

void log_to_file(const std::filesystem::path& file) {
    namespace fs = std::filesystem;
    if (stderr_is_read()) return;
    std::error_code ec;
    fs::create_directories(file.parent_path(), ec);
    if (const auto size = fs::file_size(file, ec); !ec && size > (1u << 20))
        fs::rename(file, file.parent_path() / "launcher.old.log", ec);
#ifdef _WIN32
    // (An old test build's starter, 0.4 to 0.8.0, holds launcher.log for its Python, the bridge, sharing it only for
    // reading: then launcher-ui.log beside it. Only a file that opens is reopened as standard error:
    // _wfreopen closes it first and would leave none when the file cannot be opened.)
    fs::path chosen;
    for (const fs::path& f : {file, file.parent_path() / L"launcher-ui.log"}) {
        if (FILE* probe = _wfsopen(f.c_str(), L"a", _SH_DENYNO)) {
            std::fclose(probe);
            chosen = f;
            break;
        }
    }
    if (chosen.empty() || !_wfreopen(chosen.c_str(), L"a", stderr)) return;
#else
    if (!std::freopen(file.c_str(), "a", stderr)) return;
#endif
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    const std::time_t now = std::time(nullptr);
    char when[32] = "";
    std::strftime(when, sizeof when, "%Y-%m-%d %H:%M:%S", std::localtime(&now));
    std::fprintf(stderr, "\n== %s ttt2-launcher %s\n", when, TTT2_LAUNCHER_VERSION);
}

} // namespace

static int launcher_main(int argc, char** argv) {
    namespace st = launcher::startup;
    const std::vector<std::string> args = st::arguments(argc, argv);
    // (TTT2_LAUNCHER_TEST_SMOKE: a start as a player's, which an old launcher's update may have opened with its own
    // test actions in the environment: those are not this start's.)
    const char* actions = environment("TTT2_LAUNCHER_TEST_SMOKE").empty() ? std::getenv("TTT2_LAUNCHER_TEST_ACTIONS")
                                                                          : nullptr;
    bool screenshot = false, smoke_arg = false;
    for (const std::string& a : args) {
        screenshot = screenshot || a == "--screenshot" || a == "--frames";
        smoke_arg = smoke_arg || a == "--ui-smoke-test";
    }
    const std::string after = environment("TTT2_LAUNCHER_AFTER"); // (begin() waits for it and removes it)
    st::Program program;
    program.version = TTT2_LAUNCHER_VERSION;
    program.usage = kUsage;
    program.options = {{"--screenshot", 1}, {"--size", 1}, {"--scale", 1}, {"--frames", 1}, {"--at", 1},
                       {"--files", 1},      {"--build-dir", 1}, {"--config", 1}, {"--ui-smoke-test", 1}};
    program.unique = !screenshot && !smoke_arg && !(actions && *actions);
    // (Tests that start it as a player does, side by side (tests/idle.sh): a name of their own, so they never reach a
    // real launcher nor each other.)
    program.instance_name = environment("TTT2_LAUNCHER_TEST_INSTANCE");
    program.wake = wake;
#ifndef _WIN32
    // (Before any window: the player is told in a message box too, as when no window can open, not only on standard
    // error, which a start from the desktop's menu shows nowhere. Tests' starts only write it.)
    program.tell = [quiet = !environment("TTT2_LAUNCHER_TEST_SMOKE").empty()](const std::string& text) {
        std::fprintf(stderr, "ttt2-launcher: %s\n", text.c_str());
        if (!quiet) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "Golden Fist Launcher", text.c_str(), nullptr);
    };
#endif
    st::Start start = st::begin(args, program);
    if (start.exit >= 0) return start.exit;

    launcher::app::Options o;
    o.instance = std::move(start.instance);
    o.files = start.files;
#ifndef _WIN32
    // (Set when an update's new version never drew and this one was put back; not for the programs it starts.)
    o.rolled_back = environment(launcher::kRolledBackVariable);
    unsetenv(launcher::kRolledBackVariable);
#endif
    // (Home's UPDATE goes on in this one after the launcher's part, kContinueVariable: never for the programs it
    // starts, and never on a start put back after the new version failed: the update stops there.)
    o.go_on_update = environment(launcher::kContinueVariable) == "update" && o.rolled_back.empty();
#ifdef _WIN32
    SetEnvironmentVariableW(L"TTT2_LAUNCHER_CONTINUE", nullptr);
#else
    unsetenv(launcher::kContinueVariable);
#endif
    // (For --ui-smoke-test / TTT2_LAUNCHER_TEST_SMOKE's answer: what this start found, as the release tests read it.)
    {
        std::string facts = "\"pid\": " + std::to_string(
#ifdef _WIN32
                                               static_cast<long long>(GetCurrentProcessId())
#else
                                               static_cast<long long>(getpid())
#endif
                                                   );
        facts += ", \"after\": " + json_string(after);
        if (!after.empty())
            facts += std::string(", \"after_ended\": ") +
                     (st::wait_for_exit(std::strtoll(after.c_str(), nullptr, 10), 0) ? "true" : "false");
        facts += ", \"after_left\": " + json_string(environment("TTT2_LAUNCHER_AFTER"));
        facts += ", \"rolled_back\": " + json_string(o.rolled_back);
        facts += std::string(", \"go_on_update\": ") + (o.go_on_update ? "true" : "false");
        facts += ", \"continue_left\": " + json_string(environment(launcher::kContinueVariable));
        facts += ", \"args\": [";
        for (size_t i = 0; i < start.args.size(); ++i) facts += (i ? ", " : "") + json_string(start.args[i]);
        facts += "], \"files\": " + json_string(utf8(start.files));
        facts += ", \"digest\": " + json_string(start.files_digest);
        facts += ", \"exe\": " + json_string(environment("TTT2_LAUNCHER_EXE"));
        facts += std::string(", \"unique\": ") + (o.instance ? "true" : "false");
        facts += ", \"note\": " + json_string(start.note);
#ifdef _WIN32
        // (65001 = UTF-8, the manifest's activeCodePage: narrow paths and texts in UTF-8 on Windows 10 1903 and later.)
        facts += ", \"code_page\": " + std::to_string(GetACP());
#endif
        o.smoke_start = facts;
    }
    for (size_t i = 0; i < start.args.size(); ++i) {
        const std::string& a = start.args[i];
        const bool more = i + 1 < start.args.size();
        if (a == "--screenshot" && more) {
            o.screenshot = start.args[++i];
        } else if (a == "--size" && more) {
            if (!size_of(start.args[++i].c_str(), o.width, o.height)) {
                std::fprintf(stderr, "ttt2-launcher: --size is WxH, at least 320x240\n%s", kUsage);
                return 2;
            }
        } else if (a == "--scale" && more) {
            o.scale = static_cast<float>(std::atof(start.args[++i].c_str()));
        } else if (a == "--frames" && more) {
            o.frames = arg_path(start.args[++i]);
        } else if (a == "--files" && more) {
            o.windows.files = launcher::normal(arg_path(start.args[++i]));
        } else if (a == "--build-dir" && more) {
            o.windows.build = launcher::normal(arg_path(start.args[++i]));
        } else if (a == "--config" && more) {
            o.windows.config = launcher::normal(arg_path(start.args[++i]));
        } else if (a == "--ui-smoke-test" && more) {
            o.smoke = arg_path(start.args[++i]);
        } else if (a == "--at" && more) {
            const std::string list = start.args[++i];
            for (size_t at = 0; at < list.size();) {
                const size_t comma = list.find(',', at);
                o.frames_at.push_back(std::atoi(list.substr(at, comma - at).c_str()));
                if (comma == std::string::npos) break;
                at = comma + 1;
            }
        } else if (!a.empty() && a[0] != '-') {
            o.game = launcher::normal(arg_path(a));
        }
    }
    if (actions && *actions) {
        std::string error;
        auto parsed = launcher::parse_test_actions(actions, &error);
        if (!parsed) {
            std::fprintf(stderr, "@test actions failed %s\n", error.c_str());
            return 2;
        }
        o.tests = std::move(*parsed);
    }
    if (!o.frames.empty()) {
        if (o.frames_at.empty()) o.frames_at = {0, 50, 100, 200, 400, 700};
        std::sort(o.frames_at.begin(), o.frames_at.end());
        std::error_code ec;
        std::filesystem::create_directories(o.frames, ec);
    }
    o.testing = !o.screenshot.empty() || !o.frames.empty() || (actions && *actions);
    if (!o.testing) {
#ifdef _WIN32
        const std::filesystem::path files = !start.files.empty() ? start.files : o.windows.files;
        log_to_file(!files.empty() ? files / "local" / "launcher.log"
                                   : launcher::app::program_file().parent_path() / "launcher.log");
#else
        log_to_file(launcher::Places::from_environment().cache / "ttt2" / "launcher.log");
#endif
    }
    if (const char* c = std::getenv("TTT2_LAUNCHER_TEST_CUES"); c && *c && std::string(c) != "0") o.trace_cues = true;
    if (const char* w = std::getenv("TTT2_LAUNCHER_TEST_WINDOW"); w && std::string(w) == "real") o.real_window = true;
    // (A start as a player's, e.g. an old launcher's update reopening this one: its first frame told, then the end.
    // TTT2_LAUNCHER_TEST_VIDEO=offscreen: drawn offscreen, for Wine without a display.)
    if (const std::string s = environment("TTT2_LAUNCHER_TEST_SMOKE"); o.smoke.empty() && !s.empty()) o.smoke = arg_path(s);
    o.offscreen = environment("TTT2_LAUNCHER_TEST_VIDEO") == "offscreen";
    if (const std::string shots = environment("TTT2_LAUNCHER_TEST_SHOTS"); !shots.empty()) {
        o.shots = arg_path(shots);
        std::error_code ec;
        std::filesystem::create_directories(o.shots, ec);
    }
    if (o.width == 0) size_of(std::getenv("TTT2_LAUNCHER_TEST_SIZE"), o.width, o.height);
    if (o.scale == 0) {
        if (const char* s = std::getenv("TTT2_LAUNCHER_TEST_SCALE")) o.scale = static_cast<float>(std::atof(s));
    }
    if (!start.note.empty()) std::fprintf(stderr, "ttt2-launcher: %s\n", start.note.c_str());
    launcher::app::App app(std::move(o));
    return app.run();
}

#ifdef _WIN32
// (A GUI program: no console. Its arguments are read from the wide command line by startup.)
int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) { return launcher_main(0, nullptr); }
#else
int main(int argc, char** argv) { return launcher_main(argc, argv); }
#endif
