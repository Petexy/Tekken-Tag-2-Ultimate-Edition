#include "self_update.h"
#include "utf8_path.h"

#include "json.h"
#include "system.h"

#include <memory>

namespace launcher::model {

std::string full_sentence(std::string text) {
    if (!text.empty() && text[0] >= 'a' && text[0] <= 'z') text[0] = static_cast<char>(text[0] - 'a' + 'A');
    if (!text.empty() && text.back() != '.') text += '.';
    return text;
}

std::string last_error(std::string text) {
    while (!text.empty() && (text.back() == '\n' || text.back() == ' ')) text.pop_back();
    const size_t start = text.rfind('\n');
    std::string line = start == std::string::npos ? text : text.substr(start + 1);
    for (const char* name : {"curl: ", "wget: ", "wget2: "}) {
        if (line.starts_with(name)) line.erase(0, std::string(name).size());
    }
    if (line.starts_with("(")) {
        if (const size_t close = line.find(") "); close != std::string::npos) line.erase(0, close + 2);
    }
    return line;
}

std::optional<Command> SelfUpdate::check_command() {
    if (!config_.appimage) return std::nullopt;
    const auto downloader = files_.find_downloader();
    if (!downloader) return std::nullopt; // (Update says what is missing)
    return Command{download_command(*downloader, config_.releases, true, {}, config_.user_agent), {}, {}, {}, {}};
}

std::optional<SelfUpdate::Refusal> SelfUpdate::start(double now) {
    now_ = now;
    if (!config_.appimage) {
        return Refusal{"Cannot update the launcher",
                       "Only the launcher's AppImage updates itself, and this launcher does not run from one."};
    }
    if (runner_.running()) return Refusal{"Another task is running", "Wait for it to end, then update the launcher."};
    if (const std::string why = files_.cannot_replace(*config_.appimage); !why.empty()) {
        return Refusal{"Cannot update the launcher", "Its folder, " + path_utf8(config_.appimage->parent_path()) +
                                                         ", cannot be written to (" + why +
                                                         "): move the AppImage to a folder of yours, then update it."};
    }
    const auto downloader = files_.find_downloader();
    if (!downloader) {
        const std::string command = install_command(files_.distro(), {Package::kCurl});
        return Refusal{"Cannot update the launcher",
                       "Downloading needs curl or wget: install curl" +
                           (command.empty() ? std::string(" with your distribution's packages.") : " with " + command)};
    }
    downloader_ = *downloader;
    opened_ = false;
    TaskSpec spec;
    spec.kind = TaskKind::kLauncherUpdate;
    spec.title = "Updating the launcher";
    runner_.begin(spec, now);
    runner_.step("Looking for a newer version");
    state_ = State::kAsking;
    run({download_command(downloader_, config_.releases, true, {}, config_.user_agent), {}, {}, {}, {}}, false,
        [this](int code, const std::string& out, const std::string& err) { answered(code, out, err); });
    return std::nullopt;
}

void SelfUpdate::run(Command command, bool log_out,
                     std::function<void(int, const std::string&, const std::string&)> then) {
    runner_.add_log("$ " + command_text(command.argv));
    auto out = std::make_shared<std::string>();
    auto err = std::make_shared<std::string>();
    const int serial = ++serial_;
    std::string error;
    auto job = starter_.start(command,
                              {[this, out, err, log_out](const std::string& line, bool is_error) {
                                   (is_error ? *err : *out) += line + "\n";
                                   if (is_error || log_out) runner_.add_log(line);
                               },
                               [this, out, err, then, serial](int code) {
                                   if (serial != serial_ || state_ == State::kIdle) return;
                                   const auto task = runner_.facts();
                                   if (task && task->cancelled) {
                                       return failed("Update cancelled", "The launcher is as it was.", true);
                                   }
                                   then(code, *out, *err);
                               }},
                              &error);
    if (!job) return failed("Update failed", "Cannot start " + command.argv[0] + ": " + error);
    runner_.set_job(std::move(job));
}

void SelfUpdate::answered(int code, const std::string& out, const std::string& err) {
    if (code != 0 && !json::parse(out)) {
        return failed("Update failed",
                      "GitHub cannot be reached: " +
                          (err.empty() ? "the download ended with code " + std::to_string(code) : last_error(err)) +
                          ".");
    }
    const ReleaseAnswer answer = parse_release(out);
    if (on_release) on_release(answer);
    if (answer.none ||
        (answer.release && compare_versions(answer.release->version, config_.version).value_or(0) <= 0)) {
        runner_.add_log(answer.none ? "No release is published yet."
                                    : "The newest release is " + answer.release->tag + ".");
        state_ = State::kIdle;
        runner_.finish(true, "The launcher is up to date", "Version " + config_.version + " is the newest.", false,
                       now_);
        return;
    }
    if (!answer.release) return failed("Update failed", full_sentence(answer.error));
    if (!config_.custom_releases && !answer.release->url.starts_with("https://")) {
        return failed("Update failed", "Version " + answer.release->version + " is not offered over HTTPS.");
    }
    release_ = *answer.release;
    download(now_);
}

void SelfUpdate::download(double now) {
    file_ = update_file(*config_.appimage);
    files_.remove(file_); // (one stopped half-way)
    runner_.set_title("Updating the launcher to " + release_.version);
    runner_.step("Downloading version " + release_.version);
    state_ = State::kDownloading;
    watch_at_ = release_.size > 0 ? now + kWatchSeconds : -1;
    run({download_command(downloader_, release_.url, false, file_, config_.user_agent), {}, {}, {}, {}}, true,
        [this](int code, const std::string&, const std::string& err) { downloaded(code, err); });
}

void SelfUpdate::downloaded(int code, const std::string& err) {
    watch_at_ = -1;
    const std::string version = release_.version;
    if (code != 0) {
        return failed("Update failed", "Version " + version + " cannot be downloaded: " +
                                           (err.empty() ? "code " + std::to_string(code) : last_error(err)) + ".");
    }
    const auto size = files_.size(file_);
    if (!size || (release_.size > 0 && *size != release_.size)) {
        return failed("Update failed", "The download of version " + version + " is incomplete (" +
                                           std::to_string(size.value_or(0)) + " of " + std::to_string(release_.size) +
                                           " bytes).");
    }
    if (!release_.sha256.empty() && files_.sha256(file_) != release_.sha256) {
        return failed("Update failed",
                      "The download of version " + version + " is damaged: its SHA-256 is not GitHub's.");
    }
    if (!files_.is_appimage(file_)) {
        return failed("Update failed", "What was downloaded for version " + version + " is not an AppImage.");
    }
    if (const std::string why = files_.make_executable(file_, *config_.appimage); !why.empty()) {
        return failed("Update failed", "The download cannot be made executable (" + why + ").");
    }
    runner_.step("Checking version " + version);
    state_ = State::kChecking;
    timed_out_ = false;
    deadline_ = now_ + kVersionSeconds;
    run({{path_utf8(file_), "--version"}, {}, {}, {}, {}}, true,
        [this](int code, const std::string& out, const std::string&) { started(code, out); });
}

void SelfUpdate::started(int code, const std::string& out) {
    deadline_ = -1;
    const std::string version = release_.version, said = version_in(out);
    if (timed_out_) {
        return failed("Update failed", "Version " + version + " does not start: it did not answer within " +
                                           std::to_string(static_cast<int>(kVersionSeconds)) + " seconds.");
    }
    if (code != 0 || said.empty()) {
        return failed("Update failed", "Version " + version + " does not start on this PC (code " +
                                           std::to_string(code) + ", see Details).");
    }
    if (compare_versions(said, version).value_or(1) != 0) {
        return failed("Update failed", "The AppImage released as version " + version + " is version " + said + ".");
    }
    // (C2: this version stays beside it until the new one drew its first frame, the way back when it cannot.)
    const fs::path previous = previous_file(*config_.appimage);
    if (const std::string why = files_.keep_previous(*config_.appimage); !why.empty())
        runner_.add_log("No copy of this version is kept to go back to (" + why + ").");
    if (const std::string why = files_.replace(file_, *config_.appimage); !why.empty()) {
        files_.remove(previous);
        return failed("Update failed", "It cannot replace " + path_utf8(*config_.appimage) + " (" + why + ").");
    }
    state_ = State::kIdle;
    runner_.add_log("Version " + version + " is in " + path_utf8(*config_.appimage) + ".");
    std::string error;
    Command open{open_with_rollback(*config_.appimage, version), {{kReplacesVariable, std::to_string(config_.pid)}},
                 {}, {}, {}, Command::Mode::kDetached}; // (it outlives this one)
    auto job = starter_.start(open, {}, &error);
    if (!job) {
        runner_.finish(false, "Updated to " + version + ", but it cannot be opened",
                       full_sentence(error) + " Start the launcher again.", false, now_);
        return;
    }
    runner_.add_log("Opening version " + version + "…");
    opened_ = true;
    runner_.finish(true, "Updated to " + version, "Opening it…", false, now_);
}

void SelfUpdate::failed(const std::string& title, const std::string& why, bool cancelled) {
    if (!file_.empty()) files_.remove(file_);
    file_.clear();
    watch_at_ = deadline_ = -1;
    state_ = State::kIdle;
    runner_.finish(false, title, why, cancelled, now_);
}

void SelfUpdate::tick(double now) {
    now_ = now;
    if (state_ == State::kDownloading && watch_at_ >= 0 && now >= watch_at_) {
        runner_.progress(files_.size(file_).value_or(0), release_.size);
        watch_at_ = now + kWatchSeconds;
    }
    if (state_ == State::kChecking && deadline_ >= 0 && now >= deadline_) {
        deadline_ = -1;
        timed_out_ = true;
        if (Job* job = runner_.job()) job->terminate();
    }
}

} // namespace launcher::model
