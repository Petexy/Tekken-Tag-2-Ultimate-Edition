#pragma once

// One launcher per user (ARCHITECTURE section 4, C12): the first start
// claims a name; a second start hands its arguments and activation token to
// it and exits, and the first one raises its window (and pre-selects the .wua
// it was given).
//
// Linux: an abstract unix socket "\0<name>.<uid>" (released by the kernel when
// the launcher ends, however it ends); each side checks the other's uid
// (SO_PEERCRED), so another user's program can neither pose as the launcher
// nor send it arguments. Before that an old GTK launcher (GApplication, the
// same app id on the session bus) is looked for through libdbus-1 when the
// system has it (dlopen: nothing is linked; SDL itself uses that library for
// the screensaver and input methods): it is asked to Activate (or Open the
// .wua) and this start ends.
//
// Windows: the mutex "Local\<name>" (this session) and the named pipe
// "\\.\pipe\<name>-<session>"; the second start allows the first one to take
// the foreground (AllowSetForegroundWindow), as only the program the player
// just started may.
//
// The message is a few lines: "arg <text>" each, "token <t>", "end"; the
// first answers "ok <pid> <files>" (its pid, the digest of the files it runs
// from: payload.h).

#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace launcher {

// What a second start handed over.
struct Forwarded {
    std::vector<std::string> args; // its arguments (paths made absolute by startup.h)
    std::string token;             // Wayland/X11 activation token ("" none): for raising the window
    bool operator==(const Forwarded&) const = default;
};

struct InstanceOptions {
#ifdef _WIN32
    std::string name = "TTT2UltimateLauncherWindow";
#else
    std::string name = "io.github.petexy.TekkenTag2UltimateEdition";
#endif
    Forwarded message;  // what this start hands over when one runs already
    std::string files;  // the digest of the files this one runs from (answered to a second start), "" none
    // TTT2_LAUNCHER_AFTER: this start replaces a launcher, so it never hands over (it would hand over to the one it
    // replaces, or to whatever took its place): it tries again until `after_seconds` and then fails.
    bool after = false;
    double after_seconds = 10;
    // Linux: an old GTK launcher's bus name ("" none: not looked for) and object path.
    std::string old_bus_name = "io.github.petexy.TekkenTag2UltimateEdition";
    std::string old_object_path = "/io/github/petexy/TekkenTag2UltimateEdition";
    std::function<void()> wake; // called on the listening thread when a second start arrived (the app's event)
};

class SingleInstance;

struct InstanceClaim {
    enum class Result {
        kPrimary,     // this is the launcher: `instance` hears of later starts
        kForwarded,   // one runs already and was handed the message: exit 0
        kOldLauncher, // Linux: an old GTK launcher runs and was asked to show itself: exit 0
        kAlone,       // could not claim nor hand over (another user's program has the name, no socket): run anyway
        kFailed       // with `after`: the name stayed taken; `error` says so
    };
    Result result = Result::kAlone;
    std::unique_ptr<SingleInstance> instance; // kPrimary
    int64_t other_pid = 0;                    // kForwarded: the running launcher
    std::string other_files;                  // kForwarded: the digest of its files ("" none)
    std::string error;                        // kAlone / kFailed: why (for the log)
};

// Claims being this user's launcher, else hands `options.message` over. Call once, early (before any window).
InstanceClaim claim_instance(const InstanceOptions& options);

class SingleInstance {
public:
    ~SingleInstance(); // stops listening; the name is released
    SingleInstance(const SingleInstance&) = delete;
    SingleInstance& operator=(const SingleInstance&) = delete;

    // The starts handed over since the last call (UI thread).
    std::vector<Forwarded> take();

    struct Os;
    struct Shared {
        std::mutex mutex;
        std::vector<Forwarded> arrived;
        std::function<void()> wake;
        std::string files;
    };

private:
    friend InstanceClaim claim_instance(const InstanceOptions&);
    SingleInstance();
    std::shared_ptr<Shared> shared_;
    std::unique_ptr<Os> os_;
};

// The message's lines (both sides; tests).
std::string encode_forwarded(const Forwarded& message);
// Parses complete lines up to "end"; false while incomplete or when malformed.
bool decode_forwarded(const std::string& text, Forwarded* message);

} // namespace launcher
