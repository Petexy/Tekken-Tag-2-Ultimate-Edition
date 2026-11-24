#include "task.h"

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
    if (caps.windows) return "See Details, or Open Log to send it for help.";
    if (code > 128 && code < 128 + 65) {
        const char* name = signal_name(code - 128);
        return std::string("It was stopped: ") + (name ? name : "Real-time signal " + std::to_string(code - 128 - 34)) +
               " (code " + std::to_string(code) + ", see Details)";
    }
    return "It stopped with code " + std::to_string(code) + " (see Details)";
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
            title = "Installed";
            detail = "Play it from here, or as Tekken Tag Tournament 2 in your application menu.";
        } else if (cancelled) {
            title = "Install cancelled";
            detail = spec.started_record ? "Resume it any time: the game's files copied so far are kept."
                                         : "It stopped before copying the game: nothing was installed.";
        } else {
            title = "Install failed";
            detail = why;
        }
        break;
    case TaskKind::kUpdate:
        title = ok ? "Updated" : cancelled ? "Update cancelled" : "Update failed";
        detail = ok ? "The game program is built again for this PC." : cancelled ? "The game is as it was." : why;
        break;
    case TaskKind::kImport:
        if (ok && spec.update) {
            title = added.empty() ? "No characters updated" : "Updated " + joined(added);
            detail = added.empty() ? "" : "Their new version is in the game next time it starts.";
        } else if (ok) {
            title = added.empty() ? "No characters added" : "Added " + joined(added);
            detail = added.empty() ? "" : "They are on the select screen next time the game starts.";
        } else if (spec.update) {
            title = cancelled ? "Updating cancelled" : "Updating " + spec.subject + " failed";
            detail = cancelled ? "The characters updated before stay updated, the others as they were." : why;
        } else {
            title = cancelled ? "Adding cancelled" : "Adding " + spec.subject + " failed";
            detail = cancelled ? "The characters added before stay." : why;
        }
        // (A Tekken 8 fighter whose own moves could not be saved: added all
        // the same, with a stand-in's, until updated.)
        for (const auto& [name, reason] : end.stand_ins) {
            std::string said = reason;
            while (!said.empty() && said.back() == '.') said.pop_back();
            detail +=
                (detail.empty() ? "" : " ") + display(name) + " fights with Heihachi's moves for now: " + said + ".";
        }
        if (!end.skipped.empty()) detail += (detail.empty() ? "" : " ") + ("Skipped " + joined(end.skipped) + ".");
        break;
    case TaskKind::kRemove:
        // (Intended: a cancel says so calmly; the GTK app gave the generic why, "It was stopped: Terminated".)
        title = ok          ? "Removed " + spec.subject
                : cancelled ? "Removing cancelled"
                            : "Removing " + spec.subject + " failed";
        detail = ok          ? "They are gone from the select screen next time the game starts."
                 : cancelled ? "The characters removed before stay removed, the others are kept."
                             : why;
        break;
    case TaskKind::kPackages:
        title = ok ? "Downloaded numpy and Pillow" : cancelled ? "Download cancelled" : "Downloading them failed";
        detail = ok ? "The character importer uses them from now on." : cancelled ? "Nothing was changed." : why;
        break;
    case TaskKind::kShaders:
        // (The game starts whether or not they could be prepared: it makes
        // what is missing as it needs it.)
        title = ok ? "Shaders are ready" : cancelled ? "Preparing shaders cancelled" : "Shaders could not be prepared";
        detail = ok ? "" : cancelled ? "The game was not started." : "The game makes them as it needs them. " + why;
        break;
    case TaskKind::kLauncherUpdate:
    case TaskKind::kLauncherFiles:
        // (Linux: the self-update's steps end it themselves; Windows' worker says what it updated to.)
        if (ok && !end.updated.empty()) {
            title = "Updated to " + end.updated;
            detail = "Opening it…";
            r.updated = end.updated;
        } else if (ok) {
            title = "The launcher is up to date";
            detail = end.last_step;
        } else {
            title = cancelled ? "Update cancelled" : "Update failed";
            detail = cancelled ? "The launcher is as it was." : why;
        }
        break;
    case TaskKind::kSetup:
    case TaskKind::kBuild:
    case TaskKind::kInstallSource:
    case TaskKind::kUpdateInstalled:
    case TaskKind::kBootstrap: {
        // (Windows only: window.py's words.)
        const char* done = spec.kind == TaskKind::kSetup             ? "The game is set up"
                           : spec.kind == TaskKind::kBuild           ? "The game is built"
                           : spec.kind == TaskKind::kInstallSource   ? "The game is installed"
                           : spec.kind == TaskKind::kUpdateInstalled ? "The installed game is updated"
                                                                     : "The launcher is ready";
        if (ok) {
            title = done;
            detail =
                spec.kind == TaskKind::kBuild || spec.kind == TaskKind::kBootstrap ? "" : "Click Play to start it.";
        } else if (cancelled) {
            title = "Cancelled";
            detail = "Completed extraction data is kept.";
        } else {
            title = spec.title + " failed";
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
    cancelled_ = failed_ = started_ = false;
    title_ = spec_.title;
    detail_ = "Starting…";
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
        finish(false, spec_.title + ": cannot start", error, false, now);
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

bool TaskRunner::cancellable() const { return running_ && !cancelled_ && caps_.cancellable.count(spec_.kind) > 0; }

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
    v.button.id = "task";
    v.details.id = "details";
    v.details.label = "Details";
    v.details.kind = ActionKind::kExpander;
    v.details.checked = details_;
    v.details.describe.title = "Details";
    v.details.describe.explain = "The task's log.";
    if (running_) {
        std::string detail = progress_.step();
        if (!progress_.detail().empty()) detail += (detail.empty() ? "" : " · ") + progress_.detail();
        if (progress_.fraction() >= 0) {
            detail +=
                (detail.empty() ? "" : " · ") + std::to_string(static_cast<int>(progress_.fraction() * 100)) + "%";
            v.fraction = progress_.fraction();
        }
        v.detail = !started_ ? detail_ : detail;
        if (cancelled_) {
            v.detail = spec_.kind == TaskKind::kImport
                           ? "Stopping… " + (spec_.hidden.empty() ? std::string("Tekken 7") : spec_.hidden) +
                                 " is closed first when it runs hidden: a few seconds."
                           : std::string("Stopping…");
        }
        v.button.label = cancelled_ ? "Stopping…" : "Cancel";
        v.button.enabled = cancellable();
        v.button.why = cancelled_                           ? "It is stopping."
                       : spec_.kind == TaskKind::kUninstall ? "An uninstall cannot be stopped half-way."
                       : !v.button.enabled                  ? "This task cannot be stopped half-way."
                                                            : "";
    } else {
        v.detail = detail_;
        v.button.label = "Close";
    }
    v.button.describe.title = title_;
    v.button.describe.state = v.detail;
    v.button.describe.why = v.button.why;
    if (caps_.task_log_file) {
        Action open;
        open.id = "open-log";
        open.label = "Open Log";
        open.icon = Icon::kLog;
        open.flat = true;
        open.describe.title = "Open Log";
        open.describe.path = spec_.command.log_file.string();
        v.open_log = open;
    }
    return v;
}

std::optional<TaskFacts> TaskRunner::facts() const {
    if (!running_) return std::nullopt;
    return TaskFacts{spec_.kind, spec_.title, cancelled_};
}

} // namespace launcher::model
