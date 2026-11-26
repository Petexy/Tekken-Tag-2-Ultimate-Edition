#include "self_update.h"
#include "utf8_path.h"

#include "json.h"
#include "system.h"

#include <memory>

namespace launcher::model {

std::string full_sentence(std::string text) {
    text = i18n::capitalized(std::move(text));
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

std::optional<SelfUpdate::Refusal> SelfUpdate::start(double now, bool go_on) {
    now_ = now;
    if (!config_.appimage) {
        return Refusal{tr("model.cannot_update_launcher", "Cannot update the launcher"),
                       tr("model.not_appimage",
                          "Only the launcher's AppImage updates itself, and this launcher does not run from one.")};
    }
    if (runner_.running())
        return Refusal{tr("common.task_running", "Another task is running"),
                       tr("self.wait", "Wait for it to end, then update the launcher.")};
    if (const std::string why = files_.cannot_replace(*config_.appimage); !why.empty()) {
        return Refusal{tr("model.cannot_update_launcher", "Cannot update the launcher"),
                       tr("self.folder_read_only",
                          "Its folder, {folder}, cannot be written to ({why}): move the AppImage to a folder of yours, "
                          "then update it.",
                          {{"folder", path_utf8(config_.appimage->parent_path())}, {"why", why}})};
    }
    const auto downloader = files_.find_downloader();
    if (!downloader) {
        const std::string command = install_command(files_.distro(), {Package::kCurl});
        return Refusal{tr("model.cannot_update_launcher", "Cannot update the launcher"),
                       command.empty() ? tr("self.no_downloader", "Downloading needs curl or wget: install curl with "
                                                                  "your distribution's packages.")
                                       : tr("self.no_downloader_command", "Downloading needs curl or wget: install curl "
                                                                          "with {command}",
                                            {{"command", command}})};
    }
    downloader_ = *downloader;
    opened_ = false;
    go_on_ = go_on;
    TaskSpec spec;
    spec.kind = TaskKind::kLauncherUpdate;
    spec.title = tr("model.updating_launcher", "Updating the launcher");
    runner_.begin(spec, now);
    runner_.step(tr("self.looking", "Looking for a newer version"));
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
                                       return failed(tr("task.update_cancelled", "Update cancelled"),
                                                     tr("task.launcher_as_it_was", "The launcher is as it was."), true);
                                   }
                                   then(code, *out, *err);
                               }},
                              &error);
    if (!job)
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.cannot_start", "Cannot start {program}: {error}",
                         {{"program", command.argv[0]}, {"error", error}}));
    runner_.set_job(std::move(job));
}

void SelfUpdate::answered(int code, const std::string& out, const std::string& err) {
    if (code != 0 && !json::parse(out)) {
        return failed(tr("task.update_failed", "Update failed"),
                      err.empty() ? tr("self.github_code", "GitHub cannot be reached: the download ended with code {code}.",
                                       {{"code", code}})
                                  : tr("self.github_said", "GitHub cannot be reached: {error}.",
                                       {{"error", last_error(err)}}));
    }
    const ReleaseAnswer answer = parse_release(out);
    if (on_release) on_release(answer);
    if (answer.none ||
        (answer.release && compare_versions(answer.release->version, config_.version).value_or(0) <= 0)) {
        runner_.add_log(answer.none ? "No release is published yet."
                                    : "The newest release is " + answer.release->tag + ".");
        state_ = State::kIdle;
        runner_.finish(true, tr("task.launcher_up_to_date", "The launcher is up to date"),
                       tr("self.newest", "Version {version} is the newest.", {{"version", config_.version}}), false,
                       now_);
        return;
    }
    if (!answer.release) return failed(tr("task.update_failed", "Update failed"), full_sentence(answer.error));
    if (!config_.custom_releases && !answer.release->url.starts_with("https://")) {
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.not_https", "Version {version} is not offered over HTTPS.",
                         {{"version", answer.release->version}}));
    }
    release_ = *answer.release;
    download(now_);
}

void SelfUpdate::download(double now) {
    file_ = update_file(*config_.appimage);
    files_.remove(file_); // (one stopped half-way)
    runner_.set_title(tr("self.updating_to", "Updating the launcher to {version}", {{"version", release_.version}}));
    runner_.step(tr("self.downloading", "Downloading version {version}", {{"version", release_.version}}));
    state_ = State::kDownloading;
    watch_at_ = release_.size > 0 ? now + kWatchSeconds : -1;
    run({download_command(downloader_, release_.url, false, file_, config_.user_agent), {}, {}, {}, {}}, true,
        [this](int code, const std::string&, const std::string& err) { downloaded(code, err); });
}

void SelfUpdate::downloaded(int code, const std::string& err) {
    watch_at_ = -1;
    const std::string version = release_.version;
    if (code != 0) {
        return failed(tr("task.update_failed", "Update failed"),
                      err.empty() ? tr("self.download_code", "Version {version} cannot be downloaded: code {code}.",
                                       {{"version", version}, {"code", code}})
                                  : tr("self.download_said", "Version {version} cannot be downloaded: {error}.",
                                       {{"version", version}, {"error", last_error(err)}}));
    }
    const auto size = files_.size(file_);
    if (!size || (release_.size > 0 && *size != release_.size)) {
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.incomplete", "The download of version {version} is incomplete ({got} of {size} bytes).",
                         {{"version", version}, {"got", size.value_or(0)}, {"size", release_.size}}));
    }
    if (!release_.sha256.empty() && files_.sha256(file_) != release_.sha256) {
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.damaged", "The download of version {version} is damaged: its SHA-256 is not GitHub's.",
                         {{"version", version}}));
    }
    if (!files_.is_appimage(file_)) {
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.not_appimage", "What was downloaded for version {version} is not an AppImage.",
                         {{"version", version}}));
    }
    if (const std::string why = files_.make_executable(file_, *config_.appimage); !why.empty()) {
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.not_executable", "The download cannot be made executable ({why}).", {{"why", why}}));
    }
    runner_.step(tr("self.checking", "Checking version {version}", {{"version", version}}));
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
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.no_answer", "Version {version} does not start: it did not answer within {seconds} seconds.",
                         {{"version", version}, {"seconds", static_cast<int>(kVersionSeconds)}}));
    }
    if (code != 0 || said.empty()) {
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.does_not_start", "Version {version} does not start on this PC (code {code}, see Details).",
                         {{"version", version}, {"code", code}}));
    }
    if (compare_versions(said, version).value_or(1) != 0) {
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.wrong_version", "The AppImage released as version {version} is version {said}.",
                         {{"version", version}, {"said", said}}));
    }
    // (This version stays beside it until the new one drew its first frame, the way back when it cannot.)
    const fs::path previous = previous_file(*config_.appimage);
    if (const std::string why = files_.keep_previous(*config_.appimage); !why.empty())
        runner_.add_log("No copy of this version is kept to go back to (" + why + ").");
    if (const std::string why = files_.replace(file_, *config_.appimage); !why.empty()) {
        files_.remove(previous);
        return failed(tr("task.update_failed", "Update failed"),
                      tr("self.cannot_replace", "It cannot replace {path} ({why}).",
                         {{"path", path_utf8(*config_.appimage)}, {"why", why}}));
    }
    state_ = State::kIdle;
    runner_.add_log("Version " + version + " is in " + path_utf8(*config_.appimage) + ".");
    std::string error;
    Command open{open_with_rollback(*config_.appimage, version), {{kReplacesVariable, std::to_string(config_.pid)}},
                 {}, {}, {}, Command::Mode::kDetached}; // (it outlives this one)
    if (go_on_) open.env[kContinueVariable] = "update";
    auto job = starter_.start(open, {}, &error);
    if (!job) {
        runner_.finish(false, tr("model.updated_not_opened", "Updated to {version}, but it cannot be opened", {{"version", version}}),
                       tr("common.two_sentences", "{first} {second}",
                          {{"first", full_sentence(error)}, {"second", tr("model.start_again", "Start the launcher again.")}}),
                       false, now_);
        return;
    }
    runner_.add_log("Opening version " + version + "…");
    opened_ = true;
    runner_.finish(true, tr("task.updated_to", "Updated to {version}", {{"version", version}}),
                   tr("task.opening", "Opening it…"), false, now_);
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
