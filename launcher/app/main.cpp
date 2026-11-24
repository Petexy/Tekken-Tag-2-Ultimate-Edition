// ttt2-launcher (Ultimate Launcher): first what needs no window (core/startup: --version, --help, the launcher it
// replaces waited for, one launcher per user), then SDL and the window (app.h).
//
//   ttt2-launcher [GAME.wua] [--screenshot FILE [--size WxH] [--scale S]] | --version | --help

#include "app.h"

#include "paths.h"
#include "startup.h"

#include <SDL3/SDL.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>

namespace {

const char* const kUsage =
    "usage: ttt2-launcher [GAME.wua] [--screenshot FILE | --frames DIR [--at MS,...]] [--size WxH] [--scale S]\n"
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
    "  Tests: TTT2_LAUNCHER_TEST_CUES=1 prints each sound cue (\"@cue <name>\"); TTT2_LAUNCHER_TEST_WINDOW=real\n"
    "  keeps a real window (a headless compositor) instead of drawing offscreen.\n";

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

} // namespace

int main(int argc, char** argv) {
    namespace st = launcher::startup;
    const std::vector<std::string> args = st::arguments(argc, argv);
    const char* actions = std::getenv("TTT2_LAUNCHER_TEST_ACTIONS");
    bool screenshot = false;
    for (const std::string& a : args) screenshot = screenshot || a == "--screenshot" || a == "--frames";
    st::Program program;
    program.version = TTT2_LAUNCHER_VERSION;
    program.usage = kUsage;
    program.options = {{"--screenshot", 1}, {"--size", 1}, {"--scale", 1}, {"--frames", 1}, {"--at", 1}};
    program.unique = !screenshot && !(actions && *actions);
    program.wake = wake;
    st::Start start = st::begin(args, program);
    if (start.exit >= 0) return start.exit;

    launcher::app::Options o;
    o.instance = std::move(start.instance);
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
            o.frames = start.args[++i];
        } else if (a == "--at" && more) {
            const std::string list = start.args[++i];
            for (size_t at = 0; at < list.size();) {
                const size_t comma = list.find(',', at);
                o.frames_at.push_back(std::atoi(list.substr(at, comma - at).c_str()));
                if (comma == std::string::npos) break;
                at = comma + 1;
            }
        } else if (!a.empty() && a[0] != '-') {
            o.game = launcher::normal(a);
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
    if (const char* c = std::getenv("TTT2_LAUNCHER_TEST_CUES"); c && *c && std::string(c) != "0") o.trace_cues = true;
    if (const char* w = std::getenv("TTT2_LAUNCHER_TEST_WINDOW"); w && std::string(w) == "real") o.real_window = true;
    if (const char* shots = std::getenv("TTT2_LAUNCHER_TEST_SHOTS"); shots && *shots) {
        o.shots = shots;
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
