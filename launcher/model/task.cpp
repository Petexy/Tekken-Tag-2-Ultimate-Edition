#include "task.h"
#include "utf8_path.h"

#include "rules.h"

namespace launcher::model {

std::string command_text(const std::vector<std::string>& argv) {
    std::string command;
    for (const std::string& a : argv) {
        command += (command.empty() ? "" : " ") + (a.find(' ') == std::string::npos ? a : "\"" + a + "\"");
    }
    return command;
}

namespace {

// What strsignal() says for the signals a task ends by (glibc's words; the
// model builds on Windows too, which has no strsignal).
const char* signal_name(int signal) {
    switch (signal) {
    case 1: return "Hangup";
    case 2: return "Interrupt";
    case 3: return "Quit";
    case 4: return "Illegal instruction";
    case 5: return "Trace/breakpoint trap";
    case 6: return "Aborted";
    case 7: return "Bus error";
    case 8: return "Floating point exception";
    case 9: return "Killed";
    case 11: return "Segmentation fault";
    case 13: return "Broken pipe";
    case 14: return "Alarm clock";
    case 15: return "Terminated";
    case 31: return "Bad system call";
    default: return nullptr;
    }
}

Progress::Kind progress_kind(TaskKind kind) {
    switch (kind) {
    case TaskKind::kImport:
    case TaskKind::kRemove: return Progress::Kind::kImport;
    case TaskKind::kLauncherUpdate:
    case TaskKind::kLauncherFiles:
    case TaskKind::kPackages: return Progress::Kind::kDownload;
    case TaskKind::kShaders: return Progress::Kind::kCount;
    default: return Progress::Kind::kBuild;
    }
}

} // namespace

std::string stopped_why(const Caps& caps, int code) {
    if (caps.windows) return tr("task.see_details", "See Details, or Open Log to send it for help.");
    if (code > 128 && code < 128 + 65) {
        // (The signal's name as the system says it: English, like the log.)
        const char* name = signal_name(code - 128);
        return tr("task.stopped_signal", "It was stopped: {signal} (code {code}, see Details)",
                  {{"signal", name ? std::string(name) : "Real-time signal " + std::to_string(code - 128 - 34)},
                   {"code", code}});
    }
    return tr("task.stopped_code", "It stopped with code {code} (see Details)", {{"code", code}});
}

TaskResult task_result(const Caps& caps, const TaskSpec& spec, const TaskEnd& end,
                       const std::function<std::string(const std::string&)>& display) {
    TaskResult r;
    r.kind = spec.kind;
    r.cancelled = end.cancelled || (caps.windows && end.code == 130);
    r.ok = end.code == 0 && !r.cancelled;
    r.added = end.added;
    std::string why = end.error.empty() ? stopped_why(caps, end.code) : sentence(end.error);
    std::vector<std::string> added;
    for (const std::string& name : end.added) added.push_back(display(name));
    std::string& title = r.title;
    std::string& detail = r.detail;
    const bool ok = r.ok, cancelled = r.cancelled;
    switch (spec.kind) {
    case TaskKind::kInstall:
        if (ok) {
            title = tr("task.installed", "Installed");
            detail = tr("task.installed_about", "Play it from here, or as Tekken Tag Tournament 2 in your application menu.");
        } else if (cancelled) {
            title = tr("task.install_cancelled", "Install cancelled");
            detail = spec.started_record
                         ? tr("task.install_resume", "Resume it any time: the game's files copied so far are kept.")
                         : tr("task.install_nothing", "It stopped before copying the game: nothing was installed.");
        } else {
            title = tr("task.install_failed", "Install failed");
            detail = why;
        }
        break;
    case TaskKind::kUpdate:
        title = ok          ? tr("task.updated", "Updated")
                : cancelled ? tr("task.update_cancelled", "Update cancelled")
                            : tr("task.update_failed", "Update failed");
        detail = ok          ? tr("task.updated_about", "The game program is built again for this PC.")
                 : cancelled ? tr("task.game_as_it_was", "The game is as it was.")
                             : why;
        break;
    case TaskKind::kImport: {
        if (ok && spec.update) {
            title = added.empty() ? tr("task.none_updated", "No characters updated")
                                  : tr("task.updated_names", "Updated {names}", {{"names", joined(added)}});
            detail = added.empty() ? "" : tr("task.updated_names_about", "Their new version is in the game next time it starts.");
        } else if (ok) {
            title = added.empty() ? tr("task.none_added", "No characters added")
                                  : tr("task.added_names", "Added {names}", {{"names", joined(added)}});
            detail = added.empty() ? "" : tr("task.added_names_about", "They are on the select screen next time the game starts.");
        } else if (spec.update) {
            title = cancelled ? tr("task.updating_cancelled", "Updating cancelled")
                              : tr("task.updating_failed", "Updating {what} failed", {{"what", spec.subject}});
            detail = cancelled ? tr("task.updating_cancelled_about",
                                    "The characters updated before stay updated, the others as they were.")
                               : why;
        } else {
            title = cancelled ? tr("task.adding_cancelled", "Adding cancelled")
                              : tr("task.adding_failed", "Adding {what} failed", {{"what", spec.subject}});
            detail = cancelled ? tr("task.adding_cancelled_about", "The characters added before stay.") : why;
        }
        const auto then = [&detail](const std::string& next) {
            detail = detail.empty() ? next : tr("common.two_sentences", "{first} {second}", {{"first", detail}, {"second", next}});
        };
        // (A Tekken 8 fighter whose own moves could not be saved: added all
        // the same, with a stand-in's, until updated.)
        for (const auto& [name, reason] : end.stand_ins) {
            std::string said = reason;
            while (!said.empty() && said.back() == '.') said.pop_back();
            then(tr("task.stand_in", "{name} fights with Heihachi's moves for now: {why}.",
                    {{"name", display(name)}, {"why", said}}));
        }
        if (!end.skipped.empty()) then(tr("task.skipped", "Skipped {list}.", {{"list", joined(end.skipped)}}));
        break;
    }
    case TaskKind::kRemove:
        // (Intended: a cancel says so calmly; the GTK app gave the generic why, "It was stopped: Terminated".)
        title = ok          ? tr("task.removed", "Removed {what}", {{"what", spec.subject}})
                : cancelled ? tr("task.removing_cancelled", "Removing cancelled")
                            : tr("task.removing_failed", "Removing {what} failed", {{"what", spec.subject}});
        detail = ok          ? tr("task.removed_about", "They are gone from the select screen next time the game starts.")
                 : cancelled ? tr("task.removing_cancelled_about",
                                  "The characters removed before stay removed, the others are kept.")
                             : why;
        break;
    case TaskKind::kPackages:
        title = ok          ? tr("task.downloaded", "Downloaded numpy and Pillow")
                : cancelled ? tr("task.download_cancelled", "Download cancelled")
                            : tr("task.download_failed", "Downloading them failed");
        detail = ok          ? tr("task.downloaded_about", "The character importer uses them from now on.")
                 : cancelled ? tr("task.nothing_changed", "Nothing was changed.")
                             : why;
        break;
    case TaskKind::kShaders:
        // (The game starts whether or not they could be prepared: it makes
        // what is missing as it needs it.)
        title = ok          ? tr("task.shaders_ready", "Shaders are ready")
                : cancelled ? tr("task.shaders_cancelled", "Preparing shaders cancelled")
                            : tr("task.shaders_failed", "Shaders could not be prepared");
        detail = ok          ? ""
                 : cancelled ? tr("task.game_not_started", "The game was not started.")
                             : tr("common.two_sentences", "{first} {second}",
                                  {{"first", tr("task.shaders_later", "The game makes them as it needs them.")},
                                   {"second", why}});
        break;
    case TaskKind::kLauncherUpdate:
    case TaskKind::kLauncherFiles:
        // (Linux: the self-update's steps end it themselves; Windows' worker says what it updated to.)
        if (ok && !end.updated.empty()) {
            title = tr("task.updated_to", "Updated to {version}", {{"version", end.updated}});
            detail = tr("task.opening", "Opening it…");
            r.updated = end.updated;
        } else if (ok) {
            title = tr("task.launcher_up_to_date", "The launcher is up to date");
            detail = end.last_step;
        } else {
            title = cancelled ? tr("task.update_cancelled", "Update cancelled") : tr("task.update_failed", "Update failed");
            detail = cancelled ? tr("task.launcher_as_it_was", "The launcher is as it was.") : why;
        }
        break;
    case TaskKind::kSetup:
    case TaskKind::kBuild:
    case TaskKind::kInstallSource:
    case TaskKind::kUpdateInstalled:
    case TaskKind::kBootstrap: {
        // (Windows only: window.py's words.)
        const std::string done = spec.kind == TaskKind::kSetup ? tr("task.set_up", "The game is set up")
                                 : spec.kind == TaskKind::kBuild ? tr("task.built", "The game is built")
                                 : spec.kind == TaskKind::kInstallSource
                                     ? tr("task.game_installed", "The game is installed")
                                 : spec.kind == TaskKind::kUpdateInstalled
                                     ? tr("task.installed_updated", "The installed game is updated")
                                     : tr("task.launcher_ready", "The launcher is ready");
        if (ok) {
            title = done;
            detail = spec.kind == TaskKind::kBuild || spec.kind == TaskKind::kBootstrap
                         ? ""
                         : tr("task.click_play", "Click Play to start it.");
        } else if (cancelled) {
            title = tr("task.cancelled", "Cancelled");
            detail = tr("task.extraction_kept", "Completed extraction data is kept.");
        } else {
            title = tr("task.failed", "{task} failed", {{"task", spec.title}});
            detail = why;
        }
        break;
    }
    case TaskKind::kUninstall:
    case TaskKind::kRefusal: break; // (their own)
    }
    return r;
}

// ---------------------------------------------------------------- the runner

void TaskRunner::clear_for(TaskSpec spec, double now) {
    ++serial_;
    now_ = now;
    spec_ = std::move(spec);
    progress_ = Progress(progress_kind(spec_.kind));
    progress_.set_names(names_);
    end_ = {};
    log_.clear();
    running_ = shown_ = true;
    cancelled_ = failed_ = started_ = replacing_ = false;
    title_ = spec_.title;
    detail_ = tr("task.starting", "Starting…");
    hide_at_ = -1;
}

void TaskRunner::add_log(const std::string& line) {
    log_.push_back(line);
    if (log_.size() > kLogLines + 500) log_.erase(log_.begin(), log_.begin() + 500);
}

bool TaskRunner::start(TaskSpec spec, double now) {
    if (running_) return false;
    clear_for(std::move(spec), now);
    add_log("$ " + command_text(spec_.command.argv));
    std::string error;
    const int serial = serial_;
    job_ = starter_.start(spec_.command,
                          {[this, serial](const std::string& text, bool is_error) {
                               if (serial == serial_ && running_) line(text, is_error);
                           },
                           [this, serial](int code) {
                               if (serial == serial_ && running_) exited(code, now_);
                           }},
                          &error);
    if (!job_) {
        finish(false, tr("task.cannot_start", "{task}: cannot start", {{"task", spec_.title}}), error, false, now);
        return false;
    }
    return true;
}

void TaskRunner::begin(TaskSpec spec, double now) {
    if (running_) return;
    clear_for(std::move(spec), now);
}

void TaskRunner::step(const std::string& text) {
    launcher::Line l;
    l.kind = launcher::Line::Kind::kStep;
    l.word = "update";
    l.text = text;
    if (progress_.feed(l)) started_ = true;
    end_.last_step = text;
}

void TaskRunner::progress(uint64_t done, uint64_t total) {
    launcher::Line l;
    l.kind = launcher::Line::Kind::kProgress;
    l.done = done;
    l.total = total;
    if (progress_.feed(l)) started_ = true;
}

void TaskRunner::set_title(std::string title) {
    spec_.title = title;
    title_ = std::move(title);
}

void TaskRunner::line(const std::string& text, bool is_error) {
    add_log(text);
    if (is_error || !running_) return;
    if (text.starts_with("@launcher-updated ")) {
        end_.updated = text.substr(18);
        return;
    }
    if ((spec_.kind == TaskKind::kLauncherUpdate || spec_.kind == TaskKind::kLauncherFiles) &&
        (text == "@replacing" || text.starts_with("@step update Putting ")))
        replacing_ = true;
    if (text == "@replacing") return;
    const launcher::Line l = parse_line(text);
    switch (l.kind) {
    case launcher::Line::Kind::kError: end_.error = l.text; break;
    case launcher::Line::Kind::kAdded:
    case launcher::Line::Kind::kRemoved: end_.added.push_back(l.word); break;
    case launcher::Line::Kind::kSkipped: end_.skipped.push_back(l.word + ": " + l.text); break;
    case launcher::Line::Kind::kStandIn: end_.stand_ins.emplace_back(l.word, l.text); break;
    case launcher::Line::Kind::kStep: end_.last_step = l.text; break;
    default: break;
    }
    if (progress_.feed(l)) started_ = true;
}

bool TaskRunner::cancellable() const {
    return running_ && !cancelled_ && !replacing_ && caps_.cancellable.count(spec_.kind) > 0;
}

void TaskRunner::cancel() {
    if (!cancellable() || !job_) return;
    cancelled_ = true;
    end_.cancelled = true;
    job_->terminate();
    add_log("Stopping…");
}

void TaskRunner::exited(int code, double now) {
    end_.code = code;
    const std::map<std::string, std::string>& names = names_;
    TaskResult r = task_result(caps_, spec_, end_, [&](const std::string& name) {
        const auto it = names.find(name);
        return it != names.end() ? it->second : name;
    });
    // (The job ends from its own callback: it goes at the next tick, not now.)
    ended_job_ = std::move(job_);
    finish(r.ok, r.title, r.detail, r.cancelled, now);
}

void TaskRunner::finish(bool ok, std::string title, std::string detail, bool cancelled, double now) {
    now_ = now;
    running_ = false;
    shown_ = true;
    failed_ = !ok && !cancelled;
    title_ = std::move(title);
    detail_ = std::move(detail);
    add_log(ok ? "Done." : title_ + (detail_.empty() ? "" : ": " + detail_));
    last_ = TaskResult{spec_.kind, ok, cancelled, title_, detail_, end_.added, ok ? end_.updated : std::string()};
    ++serial_;
    // A success says so for a while; a failure stays until closed.
    hide_at_ = ok ? now + kShownSeconds : -1;
    if (job_) ended_job_ = std::move(job_);
    if (on_end) on_end(last_);
}

void TaskRunner::refuse(const std::string& title, const std::string& why, double now) {
    if (running_) return;
    TaskSpec spec;
    spec.kind = TaskKind::kRefusal;
    spec.title = title;
    clear_for(spec, now);
    finish(false, title, why, false, now);
}

void TaskRunner::tick(double now) {
    now_ = now;
    ended_job_.reset();
    if (!running_ && shown_ && hide_at_ >= 0 && now >= hide_at_ && !details_) {
        shown_ = false;
        hide_at_ = -1;
    }
}

TaskView TaskRunner::view() const {
    TaskView v;
    v.shown = shown_;
    v.running = running_;
    v.title = title_;
    v.failed = failed_;
    v.stopping = running_ && cancelled_;
    v.button.id = "task";
    v.details.id = "details";
    v.details.label = tr("task.details", "Details");
    v.details.kind = ActionKind::kExpander;
    v.details.checked = details_;
    v.details.describe.title = v.details.label;
    v.details.describe.explain = tr("task.details_about", "The task's log.");
    if (running_) {
        std::string detail = progress_.step();
        if (!progress_.detail().empty()) detail += (detail.empty() ? "" : " · ") + progress_.detail();
        if (progress_.fraction() >= 0) {
            detail +=
                (detail.empty() ? "" : " · ") + std::to_string(static_cast<int>(progress_.fraction() * 100)) + "%";
            v.fraction = progress_.fraction();
        }
        v.detail = !started_ ? detail_ : detail;
        // (Play's own step: the step line repeats the title; say what follows.)
        if (spec_.kind == TaskKind::kShaders && (v.detail.empty() || v.detail.starts_with(spec_.title)))
            v.detail = progress_.fraction() >= 0
                           ? tr("task.shaders_then_play_percent", "The game starts once they are ready · {percent}%.",
                                {{"percent", static_cast<int>(progress_.fraction() * 100)}})
                           : tr("task.shaders_then_play", "The game starts once they are ready.");
        if (cancelled_) {
            v.detail = spec_.kind == TaskKind::kImport
                           ? tr("task.stopping_hidden", "Stopping… {game} is closed first when it runs hidden: a few seconds.",
                                {{"game", spec_.hidden.empty() ? std::string("Tekken 7") : spec_.hidden}})
                           : tr("task.stopping", "Stopping…");
        }
        v.button.label = cancelled_ ? tr("task.stopping", "Stopping…") : replacing_ ? "" : tr("common.cancel", "Cancel");
        v.button.enabled = cancellable();
        v.button.why = cancelled_ ? tr("task.why_stopping", "It is stopping.")
                       : replacing_
                           ? tr("task.why_replacing", "The new version is being put in place: it ends in moments.")
                       : spec_.kind == TaskKind::kUninstall
                           ? tr("task.why_uninstall", "An uninstall cannot be stopped half-way.")
                       : !v.button.enabled ? tr("task.why_not_stoppable", "This task cannot be stopped half-way.")
                                           : "";
    } else {
        v.detail = detail_;
        v.button.label = tr("common.close", "Close");
    }
    v.button.describe.title = title_;
    v.button.describe.state = v.detail;
    v.button.describe.why = v.button.why;
    if (caps_.task_log_file) {
        Action open;
        open.id = "open-log";
        open.label = tr("task.open_log", "Open Log");
        open.icon = Icon::kLog;
        open.flat = true;
        open.describe.title = open.label;
        open.describe.path = path_utf8(spec_.command.log_file);
        v.open_log = open;
    }
    return v;
}

std::optional<TaskFacts> TaskRunner::facts() const {
    if (!running_) return std::nullopt;
    return TaskFacts{spec_.kind, spec_.title, cancelled_};
}

} // namespace launcher::model
