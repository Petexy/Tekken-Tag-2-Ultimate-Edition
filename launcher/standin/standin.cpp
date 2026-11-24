// launcher_standin: the new launcher's stand-in in the release packaging (make_appimage.sh --ui sdl,
// make_launcher_exe.py --cmake-target) and its tests, until launcher/app's ttt2-launcher is the SDL program. It is
// linked as that program is (ttt2_launcher_program: SDL built in, fonts, icons, Windows resources), starts as it
// starts (launcher/core/startup.h: --version, --help, --unpack, TTT2_LAUNCHER_AFTER, one launcher per user, the
// release .exe's files into the files folder), then opens a window and draws one frame with SDL:
//
//   launcher_standin [GAME.wua] [--files DIR] [--build-dir DIR] [--config FILE] [--screenshot FILE]
//                    [--ui-smoke-test FILE] | --version | --help | --unpack DIR (Windows)
//
// With TTT2_LAUNCHER_STANDIN_LOG set (tests: what an old launcher's update opened), it adds what it found to that
// file and ends after the frame: "start" (its version, the launcher it waited for and whether that one had ended,
// its arguments, the release files' folder and digest, TTT2_LAUNCHER_EXE), then "frame" (SDL's video driver and
// renderer, the colour read back) or "no-frame" (why); TTT2_LAUNCHER_STANDIN_VIDEO=offscreen draws it offscreen with the
// software renderer (Wine does not pass SDL_VIDEO_DRIVER on, and a start by an old launcher's update has no
// arguments of the test's). --screenshot FILE (as the launcher's: a test run, not the one
// launcher of the user, drawn offscreen by the software renderer) writes the frame as a PNG and ends too;
// --ui-smoke-test FILE (CI, through the source ZIP's bridge, launcher/windows/build_launcher.py) draws the frame with
// this PC's video driver, writes what it found as JSON and ends. --build-dir and --config (the bridge passes them where
// they are not the files' usual ones) are taken and only noted. Otherwise the window stays until it is closed.

#include "startup.h"

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include "stb_image_write.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <unistd.h>
#endif

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace {

const char kUsage[] = "usage: ttt2-launcher [GAME.wua] [--files DIR] [--build-dir DIR] [--config FILE] | --version\n"
                      "(launcher_standin: the new launcher's stand-in in its packaging and tests)\n";

std::string environment(const char* name) {
#ifdef _WIN32
    // (The process's own variables, which begin() changes; the C runtime keeps a copy of those it started with.)
    char value[4096];
    const DWORD n = GetEnvironmentVariableA(name, value, sizeof value);
    return n > 0 && n < sizeof value ? std::string(value, n) : "";
#else
    const char* value = std::getenv(name);
    return value ? value : "";
#endif
}

long long own_pid() {
#ifdef _WIN32
    return static_cast<long long>(GetCurrentProcessId());
#else
    return static_cast<long long>(getpid());
#endif
}

// One line added to TTT2_LAUNCHER_STANDIN_LOG ("" none). Values are quoted by replacing spaces and newlines.
void note(const std::string& log, const std::string& line) {
    if (log.empty()) return;
    std::FILE* file = std::fopen(log.c_str(), "ab");
    if (!file) return;
    std::fprintf(file, "%s\n", line.c_str());
    std::fclose(file);
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

std::string word(std::string text) {
    if (text.empty()) return "-";
    for (char& c : text)
        if (c == ' ' || c == '\n' || c == '\r' || c == '\t') c = '_';
    return text;
}

// The frame: the Tag Split halves (crimson left, blue right) and nothing else; the colour of a pixel on each side read
// back. Returns "" or why there is no frame.
std::string draw(bool stay, const std::string& screenshot, std::string* said) {
    SDL_SetMainReady();
    SDL_SetAppMetadata("Ultimate Launcher", TTT2_LAUNCHER_VERSION, TTT2_LAUNCHER_APP_ID);
    SDL_SetHint(SDL_HINT_VIDEO_ALLOW_SCREENSAVER, "1");
    if (!screenshot.empty() || environment("TTT2_LAUNCHER_STANDIN_VIDEO") == "offscreen") {
        SDL_SetHint(SDL_HINT_VIDEO_DRIVER, "offscreen");
        SDL_SetHint(SDL_HINT_RENDER_DRIVER, "software");
    }
    if (!SDL_Init(SDL_INIT_VIDEO)) return std::string("SDL cannot start: ") + SDL_GetError();
    // (As the launcher's window does: SDL's renderer for this PC, else the software one.)
    SDL_Window* window = nullptr;
    SDL_Renderer* renderer = nullptr;
    std::string why;
    for (const char* driver : {static_cast<const char*>(nullptr), "software"}) {
        window = SDL_CreateWindow("Ultimate Launcher", 640, 400, SDL_WINDOW_RESIZABLE);
        renderer = window ? SDL_CreateRenderer(window, driver) : nullptr;
        if (renderer) break;
        why += std::string(why.empty() ? "" : "; ") + (window ? "no renderer: " : "no window: ") + SDL_GetError();
        if (window) SDL_DestroyWindow(window);
        window = nullptr;
    }
    if (!renderer) {
        SDL_Quit();
        return why;
    }
    auto paint = [&] {
        int w = 0, h = 0;
        SDL_GetCurrentRenderOutputSize(renderer, &w, &h);
        SDL_SetRenderDrawColor(renderer, 0x8f, 0x10, 0x1c, 255);
        SDL_RenderClear(renderer);
        SDL_SetRenderDrawColor(renderer, 0x10, 0x3a, 0x8c, 255);
        const SDL_FRect blue{static_cast<float>(w) / 2, 0, static_cast<float>(w) / 2, static_cast<float>(h)};
        SDL_RenderFillRect(renderer, &blue);
    };
    paint();
    std::string colours;
    for (const int x : {40, 600}) {
        const SDL_Rect at{x, 200, 1, 1};
        SDL_Surface* pixel = SDL_RenderReadPixels(renderer, &at);
        Uint8 r = 0, g = 0, b = 0, a = 0;
        if (pixel) SDL_ReadSurfacePixel(pixel, 0, 0, &r, &g, &b, &a);
        SDL_DestroySurface(pixel);
        char text[32];
        std::snprintf(text, sizeof text, "%s%02x%02x%02x", colours.empty() ? "" : ",", r, g, b);
        colours += text;
    }
    std::string failed;
    if (!screenshot.empty()) {
        SDL_Surface* read = SDL_RenderReadPixels(renderer, nullptr);
        SDL_Surface* image = read ? SDL_ConvertSurface(read, SDL_PIXELFORMAT_RGBA32) : nullptr;
        if (!image)
            failed = std::string("cannot read the frame: ") + SDL_GetError();
        else if (!stbi_write_png(screenshot.c_str(), image->w, image->h, 4, image->pixels, image->pitch))
            failed = "cannot write " + screenshot;
        SDL_DestroySurface(image);
        SDL_DestroySurface(read);
    }
    SDL_RenderPresent(renderer);
    const char* video = SDL_GetCurrentVideoDriver();
    const char* name = SDL_GetRendererName(renderer);
    *said = std::string("video=") + word(video ? video : "") + " renderer=" + word(name ? name : "") +
            " colours=" + colours;
    while (stay) {
        SDL_Event event;
        if (!SDL_WaitEvent(&event)) break;
        if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) break;
        if (event.type == SDL_EVENT_WINDOW_EXPOSED || event.type == SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED) {
            paint();
            SDL_RenderPresent(renderer);
        }
    }
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return failed;
}

int run(const std::vector<std::string>& args) {
    const std::string log = environment("TTT2_LAUNCHER_STANDIN_LOG");
    const std::string after = environment("TTT2_LAUNCHER_AFTER"); // (begin() removes it)
    launcher::startup::Program program;
    program.version = TTT2_LAUNCHER_VERSION;
    program.usage = kUsage;
    program.options = {{"--files", 1}, {"--screenshot", 1}, {"--build-dir", 1}, {"--config", 1},
                       {"--ui-smoke-test", 1}};
    std::string screenshot, smoke;
    for (size_t i = 0; i + 1 < args.size(); ++i) {
        if (args[i] == "--screenshot") screenshot = args[i + 1];
        if (args[i] == "--ui-smoke-test") smoke = args[i + 1];
    }
    program.unique = screenshot.empty() && smoke.empty();
    launcher::startup::Start start = launcher::startup::begin(args, program);
    if (start.exit >= 0) return start.exit;

    std::string line = "start version=" TTT2_LAUNCHER_VERSION " pid=" + std::to_string(own_pid());
    line += " after=" + word(after);
    if (!after.empty())
        line += std::string(" after_ended=") +
                (launcher::startup::wait_for_exit(std::strtoll(after.c_str(), nullptr, 10), 0) ? "yes" : "no");
    line += " after_left=" + word(environment("TTT2_LAUNCHER_AFTER"));
    std::string joined;
    for (const std::string& arg : start.args) joined += (joined.empty() ? "" : "|") + arg;
    line += " args=" + word(joined);
    line += " files=" + word(start.files.string());
    line += " digest=" + word(start.files_digest);
    line += " exe=" + word(environment("TTT2_LAUNCHER_EXE"));
    line += " unique=" + std::string(start.instance ? "yes" : "no");
    if (!start.note.empty()) line += " note=" + word(start.note);
    note(log, line);

    std::string said;
    const std::string why = draw(log.empty() && screenshot.empty() && smoke.empty(), screenshot, &said);
    note(log, why.empty() ? "frame " + said : "no-frame " + word(why));
    if (!smoke.empty()) {
        std::string json = "{\"program\": \"launcher_standin\", \"version\": " + json_string(TTT2_LAUNCHER_VERSION);
        json += ", \"args\": [";
        for (size_t i = 0; i < start.args.size(); ++i) json += (i ? ", " : "") + json_string(start.args[i]);
        json += "], \"frame\": " + json_string(why.empty() ? said : "") + ", \"error\": " + json_string(why) + "}\n";
        std::FILE* file = std::fopen(smoke.c_str(), "wb");
        if (!file || std::fputs(json.c_str(), file) < 0) {
            if (file) std::fclose(file);
            std::fprintf(stderr, "ttt2-launcher: cannot write %s\n", smoke.c_str());
            return 1;
        }
        std::fclose(file);
    }
    if (!why.empty()) {
        std::fprintf(stderr, "ttt2-launcher: %s\n", why.c_str());
        return 1;
    }
    return 0;
}

} // namespace

#ifdef _WIN32
int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) { return run(launcher::startup::arguments(0, nullptr)); }
#else
int main(int argc, char** argv) { return run(launcher::startup::arguments(argc, argv)); }
#endif
