#pragma once

// The AppImage's own update (Linux; launcher/app/self_update.cpp): the
// newest release asked from GitHub, its AppImage downloaded beside this one
// (progress from the file's size), checked (size, SHA-256, an AppImage, made
// executable, its --version within 60 s), put in this one's place and opened.
// Each step is a program run through the task runner's Starter; the files are
// looked at through UpdateFiles (the real ones, or a test's).

#include "task.h"

#include <optional>
#include <string>

namespace launcher::model {

struct UpdateFiles {
    virtual ~UpdateFiles() = default;
    virtual std::string cannot_replace(const fs::path& appimage) = 0;
    virtual std::optional<Downloader> find_downloader() = 0;
    virtual std::optional<uint64_t> size(const fs::path& file) = 0;
    virtual std::string sha256(const fs::path& file) = 0; // lowercase hex, empty when it cannot be read
    virtual bool is_appimage(const fs::path& file) = 0;
    virtual std::string make_executable(const fs::path& file, const fs::path& appimage) = 0;
    virtual std::string replace(const fs::path& file, const fs::path& appimage) = 0;
    virtual void remove(const fs::path& file) = 0;
    virtual Distro distro() = 0;
    // C2: `appimage` kept as previous_file() until the new one drew its first frame. Why not, or empty.
    virtual std::string keep_previous(const fs::path& appimage) = 0;
};

// The core's (sha256 is the app's: GLib/ZArchive's).
struct RealUpdateFiles : UpdateFiles {
    std::string cannot_replace(const fs::path& appimage) override { return launcher::cannot_replace(appimage); }
    std::optional<Downloader> find_downloader() override { return launcher::find_downloader(); }
    std::optional<uint64_t> size(const fs::path& file) override;
    bool is_appimage(const fs::path& file) override { return launcher::is_appimage(file); }
    std::string make_executable(const fs::path& file, const fs::path& appimage) override {
        return launcher::make_executable(file, appimage);
    }
    std::string replace(const fs::path& file, const fs::path& appimage) override {
        return replace_appimage(file, appimage);
    }
    void remove(const fs::path& file) override;
    Distro distro() override { return this_distro(); }
    std::string keep_previous(const fs::path& appimage) override { return launcher::keep_previous(appimage); }
};

// Errors as a sentence: the first letter in capitals and a period.
std::string full_sentence(std::string text);
// curl's or wget's last line without its name and code ("curl: (6) Could not resolve host: x" -> "Could not ...").
std::string last_error(std::string text);

class SelfUpdate {
public:
    static constexpr double kVersionSeconds = 60, kWatchSeconds = 0.25;

    struct Config {
        std::optional<fs::path> appimage; // the AppImage this launcher runs from (none: not one)
        std::string version;              // this launcher's ("0.8.0")
        std::string releases = kLatestRelease;
        bool custom_releases = false; // TTT2_LAUNCHER_RELEASES (tests): plain http allowed
        std::string user_agent;       // "ttt2-launcher/0.8.0"
        int pid = 0;                  // this launcher's: the new one waits for it to end
    };

    SelfUpdate(TaskRunner& runner, Starter& starter, UpdateFiles& files, Config config)
        : runner_(runner), starter_(starter), files_(files), config_(std::move(config)) {}

    // Update (header bar, notice): refused (title, why) when it cannot start; nullopt when it started. `go_on`:
    // Home's UPDATE has more to do, which the new version does once opened (kContinueVariable).
    struct Refusal {
        std::string title, why;
    };
    std::optional<Refusal> start(double now, bool go_on = false);
    void tick(double now);
    bool running() const { return state_ != State::kIdle; }

    // GitHub's answer, also from the quiet check (check_command); the model keeps `newer`.
    std::function<void(const ReleaseAnswer&)> on_release;
    // After the update: the new AppImage was opened (this launcher quits once the panel says so).
    bool opened() const { return opened_; }
    // The quiet check's command (start + every 6 h), none without a downloader.
    std::optional<Command> check_command();

private:
    enum class State { kIdle, kAsking, kDownloading, kChecking };
    void run(Command command, bool log_out, std::function<void(int, const std::string&, const std::string&)> then);
    void answered(int code, const std::string& out, const std::string& err);
    void download(double now);
    void downloaded(int code, const std::string& err);
    void started(int code, const std::string& out);
    void failed(const std::string& title, const std::string& why, bool cancelled = false);

    TaskRunner& runner_;
    Starter& starter_;
    UpdateFiles& files_;
    Config config_;
    State state_ = State::kIdle;
    Downloader downloader_;
    Release release_;
    fs::path file_;
    double now_ = 0, watch_at_ = -1, deadline_ = -1;
    bool timed_out_ = false, opened_ = false, go_on_ = false;
    int serial_ = 0;
};

} // namespace launcher::model
