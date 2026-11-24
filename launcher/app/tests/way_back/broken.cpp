// A new launcher version that passes the update's checks and then breaks (tests/way_back/way_back.sh, C2's way
// back): --version says TTT2_BROKEN_VERSION; opened, it ends by SIGSEGV before any frame (TTT2_BROKEN=crash), or
// runs the launcher TTT2_BROKEN_LAUNCHER as this AppImage where no window can open (TTT2_BROKEN=window).
// way_back.sh gives it an AppImage's header (bytes 8 to 10: "AI", 2).

#include <signal.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <string>

int main(int argc, char** argv) {
    if (argc > 1 && std::string(argv[1]) == "--version") {
        const char* version = std::getenv("TTT2_BROKEN_VERSION");
        std::printf("ttt2-launcher %s\n", version ? version : "0.0.0");
        return 0;
    }
    const char* how = std::getenv("TTT2_BROKEN");
    const char* launcher = std::getenv("TTT2_BROKEN_LAUNCHER");
    if (how && std::string(how) == "window" && launcher) {
        char self[4096];
        const ssize_t n = ::readlink("/proc/self/exe", self, sizeof self - 1);
        if (n <= 0) return 3;
        self[n] = '\0';
        const std::string program = launcher;
        ::setenv("APPIMAGE", self, 1);
        ::setenv("APPDIR", program.substr(0, program.rfind('/')).c_str(), 1);
        // (No display to open a window on: no X11, a Wayland that is not there.)
        ::unsetenv("DISPLAY");
        ::unsetenv("TTT2_LAUNCHER_TEST_VIDEO");
        ::unsetenv("TTT2_LAUNCHER_TEST_ACTIONS");
        ::setenv("WAYLAND_DISPLAY", "no-such-wayland", 1);
        ::setenv("SDL_VIDEO_DRIVER", "wayland", 1);
        ::execl(launcher, launcher, static_cast<char*>(nullptr));
        return 4;
    }
    // (As the launcher does: the one it replaces ends first, TTT2_LAUNCHER_AFTER.)
    if (const char* after = std::getenv("TTT2_LAUNCHER_AFTER"); after && *after) {
        for (int i = 0; i < 300 && ::kill(std::atoi(after), 0) == 0; ++i) ::usleep(100000);
    }
    std::fprintf(stderr, "broken: crashing before any frame\n");
    std::fflush(stderr);
    ::raise(SIGSEGV);
    return 5;
}
