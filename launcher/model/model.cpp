#include "model.h"
#include "utf8_path.h"

#include <set>

#include "json.h"
#include "rules.h"

#include <algorithm>

namespace launcher::model {

// ---------------------------------------------------------------- Linux's commands

std::map<std::string, std::string> importer_environment(const fs::path& kit,
                                                        const std::function<bool(const fs::path&)>& exists) {
    // (The importer may be read-only, as in the AppImage: no bytecode files next to it.)
    std::map<std::string, std::string> env = {{"PYTHONUNBUFFERED", "1"}, {"PYTHONDONTWRITEBYTECODE", "1"}};
    if (exists(kit / "t7helper.exe")) env["TTT2_T7HELPER"] = path_utf8(kit / "t7helper.exe");
    if (exists(kit / "t8helper.exe")) env["TTT2_T8HELPER"] = path_utf8(kit / "t8helper.exe");
    // (The importer's C parts, so that no C compiler is needed: ttt2char/native.py.)
    if (exists(kit / "native/decimate.so")) env["TTT2_NATIVE_DECIMATE"] = path_utf8(kit / "native/decimate.so");
    if (exists(kit / "native/oodle.so")) env["TTT2_NATIVE_OODLE"] = path_utf8(kit / "native/oodle.so");
    return env;
}

namespace {

// A program's answer: its whole output, or (main.py's --query answers, launcher/backend/windows_backend.h) its last
// line, after what a module printed first.
std::string answer_of(const std::string& out) {
    std::string error;
    if (json::parse(out, &error)) return out;
    size_t end = out.find_last_not_of("\r\n \t");
    if (end == std::string::npos) return out;
    const size_t start = out.rfind('\n', end);
    return out.substr(start == std::string::npos ? 0 : start + 1, end + 1 - (start == std::string::npos ? 0 : start + 1));
}


Command script(const Facts& facts, const std::map<std::string, std::string>& env, const char* name) {
    return Command{{path_utf8(facts.python), path_utf8(facts.importer / name)}, env, {}, {}, {}};
}

} // namespace

// ---------------------------------------------------------------- Windows' commands

const char* worker_action(TaskKind kind) {
    switch (kind) {
    case TaskKind::kSetup: return "setup";
    case TaskKind::kBuild: return "build";
    case TaskKind::kInstallSource: return "install";
    case TaskKind::kUpdateInstalled: return "update";
    case TaskKind::kUpdate: return "upgrade";
    case TaskKind::kLauncherUpdate: return "launcher";
    case TaskKind::kLauncherFiles: return "files";
    case TaskKind::kShaders: return "shaders";
    case TaskKind::kImport: return "import";
    case TaskKind::kRemove: return "remove";
    default: return "";
    }
}

Command WindowsCommands::query(const Facts& facts, const std::string& name) const {
    const WindowsState& w = facts.windows;
    Command c;
    c.argv = {path_utf8(facts.python),
              "-u",
              path_utf8(w.root / "launcher/windows/main.py"),
              "--build-dir",
              path_utf8(w.build),
              "--config",
              path_utf8(w.config),
              "--query",
              name};
    c.cwd = w.root;
    return c;
}

Command WindowsCommands::worker_command(const Facts& facts, const std::string& action,
                                        const std::vector<std::string>& names, const std::string& outfits) const {
    const WindowsState& w = facts.windows;
    static int serial = 0;
    const std::string stamp_text = stamp ? stamp() : std::to_string(++serial);
    Command c;
    c.log_file = w.logs / (action + "-" + stamp_text + ".log");
    c.cancel_file = w.logs / (action + "-" + stamp_text + ".cancel");
    c.argv = {path_utf8(facts.python),
              "-u",
              path_utf8(w.root / "launcher/windows/main.py"),
              "--build-dir",
              path_utf8(w.build),
              "--config",
              path_utf8(w.config),
              "--worker",
              action,
              "--cancel-file",
              path_utf8(c.cancel_file),
              "--outfits",
              outfits.empty() ? "none" : outfits};
    c.argv.insert(c.argv.end(), names.begin(), names.end());
    c.cwd = w.root;
    // (The launcher's own update replaces the .exe or its files: never ended half-way, C3.)
    if (action == "launcher" || action == "files") c.mode = Command::Mode::kSelfUpdate;
    // (A test build's files: the .exe's program stays as it is, so changes to it are refused, self_update.py.)
    if (action == "files" && facts.program_in_exe) c.env["TTT2_LAUNCHER_PROGRAM_IN_EXE"] = "1";
    return c;
}

std::optional<Command> WindowsCommands::release(const Facts& facts) {
    if (facts.python.empty() || facts.windows.root.empty() || !facts.self_update) return std::nullopt;
    return query(facts, "release");
}

Command WindowsCommands::check(const Facts& facts, const std::string& action,
                               const std::vector<std::string>& names) const {
    Command c = query(facts, "check");
    c.argv.insert(c.argv.end(), {"--action", action});
    c.argv.insert(c.argv.end(), names.begin(), names.end());
    return c;
}

Command WindowsCommands::save_settings(const Facts& facts, const std::map<std::string, std::string>& folders) const {
    Command c = query(facts, "save-settings");
    std::string object;
    for (const auto& [key, value] : folders) object += (object.empty() ? "" : ", ") + json::quote(key) + ": " +
                                                       json::quote(value);
    c.input = "{" + object + "}";
    return c;
}

std::optional<Command> WindowsCommands::status(const Facts& facts) {
    if (facts.python.empty() || facts.windows.root.empty()) return std::nullopt;
    return query(facts, "status");
}

std::optional<Command> WindowsCommands::owned(const Facts& facts) {
    if (facts.python.empty() || facts.windows.root.empty()) return std::nullopt;
    return query(facts, "owned");
}

std::optional<Command> WindowsCommands::main_news(const Facts& facts) {
    if (facts.python.empty() || facts.windows.root.empty() || facts.build_commit.empty()) return std::nullopt;
    return query(facts, "main");
}

Command WindowsCommands::import(const Facts& facts, const std::vector<std::string>& names, const std::string& outfits) {
    return worker_command(facts, "import", names, outfits);
}

Command WindowsCommands::remove(const Facts& facts, const std::vector<std::string>& names) {
    return worker_command(facts, "remove", names, {});
}

Command WindowsCommands::update(const Facts& facts) { return worker_command(facts, "upgrade", {}, {}); }

Command WindowsCommands::shaders(const Facts& facts) { return worker_command(facts, "shaders", {}, {}); }

std::optional<Command> WindowsCommands::presave(const Facts& facts, TaskKind kind) {
    if (kind != TaskKind::kSetup || facts.python.empty() || facts.windows.root.empty()) return std::nullopt;
    return save_settings(facts, facts.windows.folders);
}

std::optional<Command> WindowsCommands::precheck(const Facts& facts, TaskKind kind,
                                                 const std::vector<std::string>& names) {
    static const std::set<std::string> kChecked = {"setup",   "build",  "install", "update",
                                                   "upgrade", "import", "remove",  "shaders"};
    const std::string action = worker_action(kind);
    if (!kChecked.count(action) || facts.python.empty() || facts.windows.root.empty()) return std::nullopt;
    return check(facts, action, names);
}

std::optional<Command> WindowsCommands::worker(const Facts& facts, TaskKind kind) {
    const std::string action = worker_action(kind);
    if (action.empty() || facts.python.empty() || facts.windows.root.empty()) return std::nullopt;
    return worker_command(facts, action, {}, {});
}

// ---------------------------------------------------------------- Linux's commands

std::optional<Command> LinuxCommands::status(const Facts& facts) {
    if (facts.importer.empty() || facts.python.empty()) return std::nullopt;
    Command c = script(facts, importer_env, "launcher.py");
    c.argv.push_back("status");
    if (facts.install.state == InstallState::kInstalled)
        c.argv.insert(c.argv.end(), {"--game", path_utf8(facts.install.folder)});
    return c;
}

std::optional<Command> LinuxCommands::owned(const Facts& facts) {
    if (facts.importer.empty() || facts.python.empty()) return std::nullopt;
    Command c = script(facts, importer_env, "launcher.py");
    c.argv.push_back("owned");
    return c;
}

std::optional<Command> LinuxCommands::main_news(const Facts& facts) {
    if (facts.build_commit.empty() || facts.importer.empty() || facts.python.empty()) return std::nullopt;
    Command c = script(facts, importer_env, "launcher.py");
    c.argv.insert(c.argv.end(), {"main", "--commit", facts.build_commit});
    return c;
}

Command LinuxCommands::import(const Facts& facts, const std::vector<std::string>& names, const std::string& outfits) {
    Command c = script(facts, importer_env, "import_character.py");
    c.argv.insert(c.argv.end(), names.begin(), names.end());
    c.argv.insert(c.argv.end(), {"--outfits", outfits.empty() ? "none" : outfits, "--game",
                                 path_utf8(facts.install.folder), "--progress"});
    return c;
}

Command LinuxCommands::remove(const Facts& facts, const std::vector<std::string>& names) {
    Command c = script(facts, importer_env, "import_character.py");
    c.argv.push_back("--remove");
    c.argv.insert(c.argv.end(), names.begin(), names.end());
    c.argv.insert(c.argv.end(), {"--game", path_utf8(facts.install.folder), "--progress"});
    return c;
}

Command LinuxCommands::packages(const Facts& facts) {
    Command c = script(facts, importer_env, "get_python_packages.py");
    c.argv.push_back("--progress");
    return c;
}

Command LinuxCommands::install(const Facts& facts, const fs::path& game, const fs::path& folder) {
    return Command{
        {path_utf8(facts.kit / "bin/ttt2-build"), "install", path_utf8(game), path_utf8(folder)}, {}, {}, {}, {}};
}

Command LinuxCommands::update(const Facts& facts) {
    return Command{{path_utf8(facts.kit / "bin/ttt2-build"), "update", path_utf8(facts.install.folder)}, {}, {}, {}, {}};
}

Command LinuxCommands::shaders(const Facts& facts) {
    return Command{{path_utf8(facts.install.folder / kProgramName), "--precompile"}, {}, {}, {}, {}};
}

std::optional<Command> LinuxCommands::play(const Facts& facts) {
    return Command{{path_utf8(facts.install.folder / kProgramName)}, {}, {}, game_log, {}, Command::Mode::kDetached};
}

// ---------------------------------------------------------------- the model

LauncherModel::LauncherModel(Facts facts, Parts parts)
    : facts_(std::move(facts)), parts_(parts), runner_(parts.starter, facts_.caps), display_(parts.display_file),
      keys_(parts.keys, parts.key_label) {
    if (parts_.update_files && parts_.update.appimage) {
        self_update_ = std::make_unique<SelfUpdate>(runner_, parts_.starter, *parts_.update_files, parts_.update);
        self_update_->on_release = [this](const ReleaseAnswer& answer) {
            // (A newer release without its AppImage yet is not offered.)
            if (answer.none)
                facts_.newer.reset();
            else if (answer.release) {
                if (compare_versions(answer.release->version, facts_.launcher_version).value_or(0) > 0) {
                    facts_.newer = answer.release;
                } else {
                    facts_.newer.reset();
                }
            }
        };
    }
    runner_.on_end = [this](const TaskResult& r) { task_ended(r); };
    display_.load();
}

bool LauncherModel::busy() const {
    return runner_.running() || before_.has_value() || facts_.status_loading || facts_.owned.state == OwnedState::kChecking ||
           (facts_.preflight && facts_.preflight->running) || release_checking_ || main_checking_;
}

void LauncherModel::sync() {
    facts_.task = runner_.facts();
    if (facts_.status) {
        std::map<std::string, std::string> names;
        for (const Fighter& f : facts_.status->fighters) names[f.name] = f.display;
        runner_.set_names(std::move(names));
    }
}

void LauncherModel::start(double now) {
    now_ = now;
    refresh(now);
    check_release(now);
    check_main(now);
}

void LauncherModel::tick(double now) {
    now_ = now;
    // A game started elsewhere (seen by look()): looked for again now and then, so that its end is seen without a
    // refresh (the old launcher's 2 s poll) - Home leaves PLAYING, Update and Uninstall can run again.
    if (facts_.game_running && !facts_.game_started_here && now >= game_look_) {
        game_look_ = now + kGameWatchSeconds;
        facts_.game_running = parts_.environment.game_runs(facts_);
    }
    runner_.tick(now);
    keys_.tick(now);
    if (self_update_) self_update_->tick(now);
    if (folders_note_until_ >= 0 && now >= folders_note_until_) {
        folders_note_.clear();
        folders_note_until_ = -1;
    }
    done_job_.reset();
    if (before_ && before_done_) before_answered(now);
    // Home's UPDATE: its next part once the launcher has looked again after the last one (or, continued from the
    // launcher that updated this one, its rest once this one has looked).
    if (chain_ && chain_->next && settled()) start_part(now);
    if (continue_ && settled()) {
        continue_ = false;
        Facts without = facts_;
        without.newer.reset(); // (the launcher's part is done: the one that opened this one did it)
        const UpdatePlan plan = update_plan(without);
        if (plan.empty()) {
            said_ = "The update has nothing more to do";
        } else {
            Chain c;
            c.parts.push_back({"launcher", "Golden Fist Launcher " + facts_.launcher_version, "Done."});
            for (UpdatePart& p : update_parts(without, plan))
                if (p.kind != "later") c.parts.push_back(std::move(p));
            c.at = 1;
            c.launcher_to = facts_.launcher_version;
            c.results.push_back("launcher " + facts_.launcher_version);
            c.later = plan.later;
            chain_ = std::move(c);
            start_part(now);
        }
    } else if (continue_ && now >= continue_until_) {
        continue_ = false;
        said_ = "The update did not go on: the launcher took too long to look";
    }
    sync();
}

double LauncherModel::next_tick(double now) const {
    // (Home's UPDATE waiting for its next part: looked at often, the loop sleeps otherwise.)
    if ((chain_ && chain_->next) || continue_) return now + 0.25;
    return facts_.game_running && !facts_.game_started_here ? game_look_ : 1e18;
}

void LauncherModel::continue_update(double now) {
    continue_ = true;
    continue_until_ = now + kContinueSeconds;
}

bool LauncherModel::settled() const {
    return !runner_.running() && !before_ && !facts_.status_loading && !status_job_ && !dialog_ &&
           !(facts_.preflight && facts_.preflight->running) && !facts_.game_running &&
           !(self_update_ && self_update_->running());
}

void LauncherModel::start_update_all(double now) {
    if (runner_.running() || before_) return refuse("Another task is running", "Wait for it to end, then update.", now);
    if (facts_.game_running) return refuse("The game is running", "Quit it, then update.", now);
    const UpdatePlan plan = update_plan(facts_);
    if (plan.empty()) {
        said_ = "Everything is up to date";
        return;
    }
    Chain c;
    for (UpdatePart& p : update_parts(facts_, plan))
        if (p.kind != "later") c.parts.push_back(std::move(p));
    c.launcher_to = plan.launcher_to;
    c.later = plan.later;
    chain_ = std::move(c);
    start_part(now);
}

// The part at chain_->at, as its own task (each refusal ends it as a failed one: part_ended).
void LauncherModel::start_part(double now) {
    Chain& c = *chain_;
    c.next = c.stopped = false;
    c.running = true;
    const std::string kind = c.parts[c.at].kind;
    if (kind == "launcher") {
        if (facts_.caps.windows) {
            start_worker(TaskKind::kLauncherUpdate, "Updating the launcher", now);
        } else if (!self_update_) {
            refuse("Cannot update the launcher",
                   "Only the launcher's AppImage updates itself, and this launcher does not run from one.", now);
        } else if (const auto refusal = self_update_->start(now, c.at + 1 < c.parts.size())) {
            refuse(refusal->title, refusal->why, now);
        }
    } else if (kind == "game") {
        start_update(now);
    } else {
        // (Those it can update now, the game new: the facts are newer than the plan.)
        Facts after = facts_;
        after.newer.reset();
        const UpdatePlan plan = update_plan(after);
        c.later = plan.later;
        if (plan.fighters.empty()) {
            // (None left to do now: the part is done without a task.)
            c.running = false;
            c.results.push_back("no fighters");
            part_done();
            return;
        }
        start_import(plan.fighters, now);
    }
}

void LauncherModel::part_done() {
    Chain& c = *chain_;
    if (++c.at >= c.parts.size()) {
        c.at = c.parts.size() - 1;
        c.done = true;
        ++updates_done_;
    } else {
        c.next = true;
    }
}

void LauncherModel::part_ended(const TaskResult& r) {
    Chain& c = *chain_;
    c.running = false;
    c.end_serial = runner_.serial();
    if (r.kind == TaskKind::kRefusal || !r.ok) {
        c.stopped = true;
        return;
    }
    const std::string kind = c.parts[c.at].kind;
    if (kind == "launcher") {
        const std::string version = !r.updated.empty() ? r.updated : c.launcher_to;
        c.results.push_back("launcher " + version);
        // (Opened: it goes on with the rest, this one quits.)
        if ((self_update_ && self_update_->opened()) || !r.updated.empty()) {
            c.handed_over = true;
            return;
        }
    } else if (kind == "game") {
        c.results.push_back("the game program");
        // (Built: the game is this launcher's now, also before Windows' state says so.)
        facts_.game_built = facts_.this_build;
    } else {
        const size_t n = runner_.spec().names.size();
        c.results.push_back(n == 1 ? display_name(facts_, runner_.spec().names[0])
                                   : std::to_string(n) + " fighters");
    }
    part_done();
}

void LauncherModel::activated(double now) {
    now_ = now;
    // (GitHub is asked again after hours, not each time.)
    if (now - release_time_ > kReleaseSeconds) {
        check_release(now);
        check_main(now);
    }
    if (busy()) return;
    if (now - status_time_ > kStatusSeconds) refresh(now);
}

void LauncherModel::deactivated() {
    // (Its keys' releases go elsewhere now; a key chosen is not.)
    keys_.cancel();
}

void LauncherModel::refresh(double now) {
    parts_.environment.look(facts_);
    // (Settings stays open when the game is gone: its launcher section is always there, U17.)
    load_status(now);
}

void LauncherModel::check_again(double now) {
    // (A game Steam could not be asked through is asked again: it may be closed now.)
    if (facts_.owned.state == OwnedState::kFailed ||
        (facts_.owned.state == OwnedState::kKnown && !facts_.owned.errors.empty())) {
        facts_.owned.state = OwnedState::kUnknown;
    }
    refresh(now);
}

void LauncherModel::load_status(double now) {
    // (Asked while one runs, as the install changes: once more after it.)
    status_again_ = facts_.status_loading;
    if (facts_.status_loading) return;
    const auto command = parts_.commands.status(facts_);
    if (!command) return;
    status_out_.clear();
    status_err_.clear();
    std::string error;
    facts_.status_loading = true;
    status_job_ = parts_.starter.start(
        *command,
        {[this](const std::string& line, bool is_error) { (is_error ? status_err_ : status_out_) += line + "\n"; },
         [this](int code) {
             facts_.status_loading = false;
             status_time_ = now_;
             std::string why;
             if (auto parsed = parse_status(answer_of(status_out_), &why)) {
                 facts_.status = std::move(parsed);
                 facts_.status_error.clear();
             } else {
                 facts_.status.reset();
                 std::string last = status_err_;
                 while (!last.empty() && last.back() == '\n') last.pop_back();
                 if (const size_t at = last.rfind('\n'); at != std::string::npos) last.erase(0, at + 1);
                 facts_.status_error = code != 0 && !last.empty() ? last : "its answer is not readable (" + why + ")";
             }
             // Steam closed: asked again once it runs again (as another
             // account, maybe); its answer is still shown meanwhile.
             if (facts_.status && !facts_.status->steam_running && facts_.owned.state != OwnedState::kChecking) {
                 facts_.owned.state = OwnedState::kUnknown;
             }
             done_job_ = std::move(status_job_);
             sync();
             if (status_again_) return load_status(now_);
             check_ownership(now_);
         }},
        &error);
    if (!status_job_) {
        facts_.status_loading = false;
        facts_.status.reset();
        facts_.status_error = "Python cannot start: " + error;
    }
    (void)now;
}

void LauncherModel::check_ownership(double now) {
    (void)now;
    if (!facts_.status || facts_.owned.state != OwnedState::kUnknown || runner_.running() ||
        !facts_.status->steam_running) {
        return;
    }
    // (Each game's DLC is asked through that game, when one of them can be used.)
    bool dlc = false;
    for (const Fighter& f : facts_.status->fighters) {
        dlc =
            dlc || (f.dlc != 0 && (f.of(kTekken8) ? facts_.status->tekken8_usable() : facts_.status->tekken7_usable()));
    }
    if (!dlc) return;
    const auto command = parts_.commands.owned(facts_);
    if (!command) return;
    owned_out_.clear();
    facts_.owned.state = OwnedState::kChecking;
    facts_.owned.errors.clear();
    std::string error;
    owned_job_ = parts_.starter.start(*command,
                                      {[this](const std::string& line, bool is_error) {
                                           if (!is_error) owned_out_ += line + "\n";
                                       },
                                       [this](int) {
                                           Ownership answer = parse_owned(answer_of(owned_out_));
                                           Owned& o = facts_.owned;
                                           if (answer.error.empty()) {
                                               // (A game Steam could not be asked through keeps its fighters' last
                                               // answer.)
                                               for (const auto& [name, owns] : answer.owned) o.answer[name] = owns;
                                               o.errors = std::move(answer.errors);
                                               o.has_answer = true;
                                               o.state = OwnedState::kKnown;
                                               pending_.push_back(
                                                   {Effect::Kind::kSaveOwned, ownership_json(o.answer), {}, {}, {}});
                                           } else {
                                               o.error = answer.error;
                                               o.errors = std::move(answer.errors);
                                               o.state = OwnedState::kFailed;
                                           }
                                           done_job_ = std::move(owned_job_);
                                       }},
                                      &error);
    if (!owned_job_) {
        facts_.owned.error = error;
        facts_.owned.state = OwnedState::kFailed;
    }
}

void LauncherModel::check_release(double now) {
    if (release_checking_) return;
    // (The AppImage asks GitHub itself; the release .exe asks its files, which answer whether it is newer.)
    const bool files = !self_update_;
    const auto command = self_update_ ? self_update_->check_command() : parts_.commands.release(facts_);
    if (!command) return;
    release_checking_ = true;
    release_time_ = now;
    release_out_.clear();
    release_err_.clear();
    std::string error;
    release_job_ = parts_.starter.start(
        *command,
        {[this](const std::string& line, bool is_error) { (is_error ? release_err_ : release_out_) += line + "\n"; },
         [this, files](int code) {
             release_checking_ = false;
             // (Quietly: no notice when GitHub cannot be asked now.)
             if (files) {
                 const auto value = json::parse(answer_of(release_out_));
                 if (const auto answer = value ? release_query_answer(*value) : std::nullopt) {
                     if (answer->release)
                         facts_.newer = answer->release;
                     else if (answer->none || answer->error.empty())
                         facts_.newer.reset(); // (none published, or none newer than this one)
                 }
             } else if (code == 0 || json::parse(release_out_)) {
                 const ReleaseAnswer answer = parse_release(answer_of(release_out_));
                 if (self_update_->on_release) self_update_->on_release(answer);
             }
             done_job_ = std::move(release_job_);
         }},
        &error);
    if (!release_job_) release_checking_ = false;
}

void LauncherModel::check_main(double now) {
    if (main_checking_) return;
    const auto command = parts_.commands.main_news(facts_);
    if (!command) return;
    release_time_ = std::max(release_time_, now);
    main_checking_ = true;
    main_out_.clear();
    std::string error;
    main_job_ = parts_.starter.start(*command,
                                     {[this](const std::string& line, bool is_error) {
                                          if (!is_error) main_out_ += line + "\n";
                                      },
                                      [this](int) {
                                          main_checking_ = false;
                                          // (Quietly: no notice when GitHub cannot be asked now, or does not know this
                                          // build.)
                                          MainNews news = parse_main_news(answer_of(main_out_));
                                          if (news.error.empty()) facts_.main_news = std::move(news);
                                          done_job_ = std::move(main_job_);
                                      }},
                                     &error);
    if (!main_job_) main_checking_ = false;
}

// ---------------------------------------------------------------- tasks

void LauncherModel::refuse(const std::string& title, const std::string& why, double now) {
    said_ = why;
    if (runner_.running()) {
        dialog_ = message_view(title, why);
        return;
    }
    runner_.refuse(title, why, now);
    sync();
}

void LauncherModel::start_task(TaskSpec spec, double now) {
    if (runner_.running() || before_) return refuse("Another task is running", "Wait for it to end.", now);
    if (parts_.read_check && parts_.read_save) {
        before_ = Before{std::move(spec), 0, false};
        return before_next(now);
    }
    runner_.start(std::move(spec), now);
    sync();
}

// Windows: the next step before the task, or the task.
void LauncherModel::before_next(double now) {
    Before& b = *before_;
    std::optional<Command> command;
    while (b.stage < 2 && !command) {
        b.save = b.stage == 0;
        command = b.save ? parts_.commands.presave(facts_, b.spec.kind)
                         : parts_.commands.precheck(facts_, b.spec.kind, b.spec.names);
        ++b.stage;
    }
    if (!command) {
        TaskSpec spec = std::move(b.spec);
        before_.reset();
        runner_.start(std::move(spec), now);
        sync();
        return;
    }
    before_out_.clear();
    before_err_.clear();
    before_done_ = false;
    std::string error;
    before_job_ = parts_.starter.start(
        *command,
        {[this](const std::string& line, bool is_error) { (is_error ? before_err_ : before_out_) += line + "\n"; },
         [this](int) { before_done_ = true; }},
        &error);
    if (!before_job_) {
        const std::string title = b.spec.title;
        before_.reset();
        refuse(title + ": not started", "Python did not start: " + error + ".", now);
    }
}

// (On the next tick: never inside the job's own handler.)
void LauncherModel::before_answered(double now) {
    before_done_ = false;
    done_job_ = std::move(before_job_);
    Before& b = *before_;
    std::string error;
    const auto problem = (b.save ? parts_.read_save : parts_.read_check)(before_out_, &error);
    if (!problem || !problem->code.empty()) {
        const std::string title = b.spec.title;
        const bool save = b.save;
        before_.reset();
        std::string why;
        if (!problem) {
            std::string last = before_err_;
            while (!last.empty() && last.back() == '\n') last.pop_back();
            if (const size_t at = last.rfind('\n'); at != std::string::npos) last.erase(0, at + 1);
            why = "The launcher's files did not answer" + (last.empty() ? " (" + error + ")" : ": " + last) + ".";
        } else {
            why = save ? save_problem_text(*problem) : setup_problem_text(*problem);
        }
        refuse(title + ": not started", why, now);
        return;
    }
    before_next(now);
}

void LauncherModel::start_import(const std::vector<std::string>& names, double now) {
    std::string why;
    if (runner_.running()) return refuse("Another task is running", "Wait for it to end, then add characters.", now);
    if (!can_import(facts_, &why)) return refuse("Cannot add characters", why, now);
    // (Each from its own game: only the games of the characters asked for.)
    bool tekken7 = false, tekken8 = false;
    for (const Fighter& f : facts_.status->fighters) {
        if (std::find(names.begin(), names.end(), f.name) == names.end()) continue;
        (f.of(kTekken8) ? tekken8 : tekken7) = true;
    }
    if ((tekken7 && !game_usable(facts_, kTekken7, &why)) || (tekken8 && !game_usable(facts_, kTekken8, &why))) {
        return refuse("Cannot add characters", why, now);
    }
    // (Their outfits as their boxes say.)
    std::string outfits;
    for (const Fighter& f : facts_.status->fighters) {
        if (std::find(names.begin(), names.end(), f.name) != names.end() && wants_outfits(facts_, f)) {
            outfits += (outfits.empty() ? "" : ",") + f.name;
        }
    }
    // (Characters to update only: an update. Their packs are replaced whole.)
    const bool update = !names.empty() && std::all_of(names.begin(), names.end(), [&](const std::string& name) {
        const Fighter* f = fighter(facts_, name);
        return f && (f->update || outfits_changed(facts_, *f));
    });
    TaskSpec spec;
    spec.kind = TaskKind::kImport;
    spec.subject = names_text(facts_, names);
    spec.title = (update ? "Updating " : "Adding ") + spec.subject;
    spec.command = parts_.commands.import(facts_, names, outfits);
    spec.update = update;
    spec.names = names;
    spec.hidden = tekken7 && tekken8 ? "Tekken 7 or Tekken 8" : tekken8 ? "Tekken 8" : "Tekken 7";
    start_task(std::move(spec), now);
}

void LauncherModel::start_remove(const std::vector<std::string>& names, double now) {
    if (runner_.running()) return refuse("Another task is running", "Wait for it to end, then remove characters.", now);
    if (facts_.importer.empty() || facts_.python.empty() || facts_.install.state != InstallState::kInstalled) {
        return refuse("Cannot remove characters", "The importer, Python 3 or the installed game is missing.", now);
    }
    TaskSpec spec;
    spec.kind = TaskKind::kRemove;
    spec.subject = names_text(facts_, names);
    spec.title = "Removing " + spec.subject;
    spec.command = parts_.commands.remove(facts_, names);
    spec.names = names;
    start_task(std::move(spec), now);
}

void LauncherModel::start_update(double now) {
    if (runner_.running()) return refuse("Another task is running", "Wait for it to end, then update.", now);
    if (!facts_.builder) return refuse("Cannot update", "The game builder is missing from this launcher.", now);
    if (facts_.game_running) return refuse("The game is running", "Quit it, then update.", now);
    facts_.game_error.clear();
    TaskSpec spec;
    spec.kind = TaskKind::kUpdate;
    spec.title = "Updating the game program";
    spec.command = parts_.commands.update(facts_);
    if (facts_.caps.windows) {
        const auto worker = parts_.commands.worker(facts_, TaskKind::kUpdate);
        if (!worker) return refuse("Cannot update", "The launcher's files are incomplete.", now);
        spec.command = *worker;
    }
    start_task(std::move(spec), now);
}

void LauncherModel::start_worker(TaskKind kind, std::string title, double now) {
    if (runner_.running()) return refuse("Another task is running", "Wait for it to end.", now);
    const auto command = parts_.commands.worker(facts_, kind);
    if (!command) return refuse("Cannot start " + title, "The launcher's files are incomplete.", now);
    TaskSpec spec;
    spec.kind = kind;
    spec.title = std::move(title);
    spec.command = *command;
    start_task(std::move(spec), now);
}

std::vector<Effect> LauncherModel::play(double now) {
    // (Two would share the saves and the shader cache.)
    if (facts_.game_running) {
        refuse("The game is running", "Only one can run at a time.", now);
        return {};
    }
    if (const std::string older = older_game(facts_); !older.empty()) {
        refuse("Update the game first", older, now);
        return {};
    }
    if (facts_.caps.windows && !facts_.windows.play_problem.empty()) {
        refuse("Cannot start the game",
               facts_.windows.play_problem == "exe"
                   ? "The installed game's program is missing: set it up again."
                   : "This development build has no Wii U source: choose it in Settings.",
               now);
        return {};
    }
    // Settings' "Prepare shaders before playing", as display.ini says when Play is pressed (intended: the GTK app
    // used what Settings last read): the game program first makes the shaders it has used on this PC, then the
    // game starts (task_ended).
    if (display_.read().precompile_shaders && !runner_.running()) {
        facts_.game_error.clear();
        TaskSpec spec;
        spec.kind = TaskKind::kShaders;
        spec.title = "Preparing shaders";
        spec.command = parts_.commands.shaders(facts_);
        if (facts_.caps.windows) {
            if (const auto worker = parts_.commands.worker(facts_, TaskKind::kShaders)) spec.command = *worker;
        }
        runner_.start(std::move(spec), now);
        sync();
        if (runner_.running()) return {};
    }
    launch_game(now);
    return {};
}

void LauncherModel::launch_game(double now) {
    (void)now;
    if (facts_.game_running) return;
    facts_.game_error.clear();
    const auto command = parts_.commands.play(facts_);
    if (!command) return;
    std::string error;
    const fs::path log = command->log_file;
    game_job_ = parts_.starter.start(
        *command,
        {nullptr,
         [this, log](int code) {
             facts_.game_running = facts_.game_started_here = false;
             if (facts_.caps.game_error_report && code != 0 && code != 128 + 15 && code != 128 + 2) {
                 facts_.game_error =
                     stopped_text(code, parts_.environment.log_end(log), log, parts_.environment.exists(log));
             }
             done_job_ = std::move(game_job_);
         }},
        &error);
    if (!game_job_) {
        facts_.game_error = "The game cannot start: " + error;
        return;
    }
    facts_.game_running = facts_.game_started_here = true;
}

void LauncherModel::task_ended(const TaskResult& r) {
    sync();
    if (chain_ && chain_->running) part_ended(r);
    if (r.kind == TaskKind::kRefusal) return;
    said_ = r.ok ? r.title : r.title + (r.detail.empty() ? "" : ": " + r.detail);
    if (r.kind == TaskKind::kInstall) {
        // Done, or stopped before ttt2 --install began (while the program was built): there is nothing to resume.
        if (r.ok || !parts_.environment.started(facts_.installing)) parts_.environment.forget_started_record();
        facts_.installing.clear();
    }
    if (r.ok && !r.updated.empty()) {
        Effect open{Effect::Kind::kOpenUpdated, r.updated, {}, {}, {}};
        open.go_on = chain_ && chain_->handed_over && chain_->at + 1 < chain_->parts.size();
        pending_.push_back(open);
    }
    if (self_update_ && self_update_->opened()) quit_after_task_ = true;
    if (quit_after_task_) {
        pending_.push_back({Effect::Kind::kQuit, {}, {}, {}, {}});
        return;
    }
    if (r.kind == TaskKind::kShaders && !r.cancelled) launch_game(now_);
    refresh(now_);
}

std::vector<Effect> LauncherModel::uninstall_confirmed(double now) {
    dialog_.reset();
    if (runner_.running()) {
        refuse("Another task is running", "Wait for it to end, then uninstall.", now);
        return {};
    }
    // (The uninstall looks again right before it deletes anything.)
    if (facts_.game_running) {
        refuse("The game is running", "Quit it, then uninstall.", now);
        return {};
    }
    TaskSpec spec;
    spec.kind = TaskKind::kUninstall;
    spec.title = "Uninstalling Tekken Tag Tournament 2";
    runner_.begin(spec, now);
    runner_.add_log("Uninstalling from " + path_utf8(facts_.install.folder));
    sync();
    Effect e{Effect::Kind::kUninstall, {}, facts_.install.folder, {}, {uninstall_.saves, uninstall_.characters}};
    return {e};
}

void LauncherModel::uninstall_done(const UninstallReport& r, double now) {
    now_ = now;
    std::vector<std::string> left, problems;
    for (const std::string& l : r.left) left.push_back(l);
    for (const UninstallProblem& p : r.problems) problems.push_back(p.text());
    for (const std::string& p : problems) runner_.add_log("Not deleted: " + p);
    for (const std::string& l : left) runner_.add_log("Left in the folder: " + l);
    if (!r.refused.empty()) {
        runner_.finish(false, "Not uninstalled", r.refused, false, now);
        return;
    }
    std::string detail;
    if (!r.folder_removed && !left.empty()) {
        detail =
            "Left in " + path_utf8(facts_.install.folder) + ", as they are not the game's: " + joined_most(left, 6) + ".";
    }
    if (!problems.empty())
        detail += (detail.empty() ? "" : " ") + std::string("Not deleted: ") + joined_most(problems, 3) + ".";
    if (detail.empty()) {
        const UninstallChoice& o = uninstall_;
        detail = o.saves && o.characters ? "Your saves, the added characters and what was saved from Tekken 7 "
                                           "and Tekken 8 are deleted too."
                 : o.saves               ? "Your saves are deleted too; the added characters are kept."
                 : o.characters          ? "The added characters and what was saved from Tekken 7 and Tekken 8 "
                                           "are deleted too; your saves are kept."
                                         : "Your saves and the added characters are kept.";
    }
    runner_.finish(r.problems.empty(), r.problems.empty() ? "Uninstalled" : "Uninstalled, but not everything", detail,
                   false, now);
}

void LauncherModel::opened_updated(const std::string& error, double now) {
    if (error.empty()) return;
    const bool handed = chain_ && chain_->handed_over;
    runner_.finish(false, "Updated to " + runner_.last().updated + ", but it cannot be opened",
                   full_sentence(error) + " Start the launcher again.", false, now);
    if (handed) {
        // (Nothing goes on with the rest: it stops here, the new launcher's UPDATE does it.)
        chain_->handed_over = false;
        chain_->stopped = true;
        chain_->end_serial = runner_.serial();
    }
}

void LauncherModel::set_windows_state(WindowsState state) { facts_.windows = std::move(state); }

// ---------------------------------------------------------------- actions

std::vector<Effect> LauncherModel::chosen_game(const fs::path& game, double now) {
    (void)now;
    facts_.chosen_game = game;
    if (facts_.caps.setup_game) setup_source_ = game;
    return {Effect{Effect::Kind::kChooseFolder, "install", {}, {}, {}}};
}

std::vector<Effect> LauncherModel::chosen_folder(const fs::path& chosen, double now) {
    if (facts_.caps.setup_game) {
        facts_.windows.folders["source"] = path_utf8(setup_source_);
        facts_.windows.folders["install"] = path_utf8(chosen);
        dialog_ = setup_confirm_view();
        return {};
    }
    if (runner_.running()) {
        refuse("Another task is running", "Wait for it to end, then install.", now);
        return {};
    }
    if (!facts_.builder) {
        refuse("Cannot install", "The game builder is missing from this launcher.", now);
        return {};
    }
    std::string error;
    const auto folder = parts_.environment.install_target(chosen, &error);
    if (!folder) {
        refuse("Cannot install into this folder",
               path_utf8(chosen.lexically_normal()) + " " + error + ": choose another folder.", now);
        return {};
    }
    facts_.game_error.clear();
    facts_.preflight = Preflight{facts_.chosen_game, *folder, true, {}, ++preflight_serial_};
    return {Effect{Effect::Kind::kRunPreflight, {}, facts_.chosen_game, *folder, {}, preflight_serial_}};
}

std::vector<Effect> LauncherModel::preflight_done(const std::vector<Check>& checks, double now, uint64_t generation) {
    // (Not the request asked last - another folder chosen, or checked again while it ran: dropped; the last one's
    // answer comes too.)
    if (!facts_.preflight || facts_.preflight->generation != generation || !facts_.preflight->running) return {};
    facts_.preflight->running = false;
    facts_.preflight->checks = checks;
    if (const std::string failed = failed_check(checks); !failed.empty()) {
        said_ = failed;
        return {};
    }
    // (A task began while the checks ran: they stay on Home, Check Again starts the install once it has ended.)
    if (runner_.running()) {
        refuse("Another task is running", "Wait for it to end, then install.", now);
        return {};
    }
    const fs::path game = facts_.preflight->game, folder = facts_.preflight->folder;
    facts_.preflight.reset();
    parts_.environment.write_started_record(folder, game);
    facts_.installing = folder;
    TaskSpec spec;
    spec.kind = TaskKind::kInstall;
    spec.title = "Installing Tekken Tag Tournament 2";
    spec.command = parts_.commands.install(facts_, game, folder);
    start_task(std::move(spec), now);
    return {};
}

std::vector<Effect> LauncherModel::request_close(double now) {
    if (!runner_.running()) return {Effect{Effect::Kind::kQuit, {}, {}, {}, {}}};
    const TaskFacts task = *runner_.facts();
    if (facts_.caps.close_policy == ClosePolicy::kRefuse) {
        dialog_ = task_running_view();
        return {};
    }
    // (An uninstall cannot be stopped half-way, and a task stopping already is cleaning up: the window closes
    // once it is done.)
    if (task.kind == TaskKind::kUninstall || task.cancelled) {
        quit_after_task_ = true;
        return {};
    }
    (void)now;
    dialog_ = stop_and_quit_view(task.title);
    return {};
}

std::vector<Effect> LauncherModel::choose(const std::string& id, int index, double now) {
    (void)now;
    if (id == "resolution") {
        if (!display_.set(id, index)) said_ = display_.error();
    } else if (id == "text-size" && index >= 0 && static_cast<size_t>(index) < std::size(kTextSizes)) {
        launcher_.text_size = kTextSizes[index];
    } else if (id == "prompts" && index >= 0 && static_cast<size_t>(index) < std::size(kPrompts)) {
        launcher_.prompts = index;
    }
    return {};
}

bool LauncherModel::key_down(int usage, bool repeat, double now) {
    const bool used = keys_.key_down(usage, repeat, now);
    said_ = keys_.taken().text;
    return used;
}

void LauncherModel::key_up(int usage, double now) {
    keys_.key_up(usage, now);
    said_ = keys_.taken().text;
}

void LauncherModel::pick_key(int input, Device device, double now) { keys_.pick(input, device, now); }

bool of_this_os(const Caps& caps, const std::string& id) {
    const auto among = [&](std::initializer_list<const char*> ids) {
        for (const char* i : ids) {
            const std::string_view s = i;
            if (s.ends_with(':') ? id.starts_with(s) : id == s) return true;
        }
        return false;
    };
    if (among({"more", "more:", "setup", "setup-confirm", "setup-cancel", "folder:", "save-folders", "performance",
               "open-keyboard-file", "open-log"})) {
        return caps.windows;
    }
    if (among({"install", "resume", "check-again", "preflight-cancel"})) return caps.install_flow;
    if (among({"uninstall", "uninstall-saves", "uninstall-characters", "uninstall-cancel", "uninstall-confirm"})) {
        return caps.uninstall;
    }
    if (among({"get-packages"})) return caps.packages_download;
    if (among({"copy:"})) return caps.prerequisites_listed;
    return true;
}

std::vector<Effect> LauncherModel::activate(const std::string& id, double now) {
    now_ = now;
    said_.clear();
    std::vector<Effect> effects;
    const auto rest = [&](const char* prefix) -> std::optional<std::string> {
        const std::string p = prefix;
        if (id.size() > p.size() && id.compare(0, p.size(), p) == 0) return id.substr(p.size());
        return std::nullopt;
    };
    const bool task = runner_.running();

    // ---- dialogs first: their buttons
    if (dialog_) {
        const std::string d = dialog_->id;
        if (id == "uninstall-saves")
            uninstall_.saves = !uninstall_.saves;
        else if (id == "uninstall-characters")
            uninstall_.characters = !uninstall_.characters;
        else if (id == "uninstall-confirm")
            return uninstall_confirmed(now);
        else if (id == "remove-all-confirm") {
            dialog_.reset();
            start_remove(to_remove_all(facts_, remove_all_game_), now);
        } else if (id == "stop-and-quit") {
            dialog_.reset();
            if (runner_.running()) {
                quit_after_task_ = true;
                runner_.cancel();
            }
        } else if (id == "setup-confirm") {
            dialog_.reset();
            start_worker(TaskKind::kSetup, "Setting up the game", now);
        } else if (id == dialog_->cancel || id == "message-ok" || id == "keep-running" || id == "remove-all-cancel" ||
                   id == "uninstall-cancel" || id == "setup-cancel") {
            dialog_.reset();
        }
        sync();
        return effects;
    }

    // (Another OS's item: not there to activate, U1.)
    if (!of_this_os(facts_.caps, id)) {
        said_ = "no " + id + " to activate";
        return effects;
    }
    if (id == "refresh")
        check_again(now);
    else if (id == "back") {
        keys_.close();
        page_ = Page::kMain;
    } else if (id == "settings") {
        // U17: always there (the game's part when it is installed; Windows' folders always).
        display_.load();
        keys_.load();
        page_ = Page::kSettings;
    } else if (id == "update-launcher" || id == "notice-update") {
        if (facts_.caps.windows) {
            const bool files = !facts_.newer && !facts_.windows.branch.empty();
            start_worker(files ? TaskKind::kLauncherFiles : TaskKind::kLauncherUpdate, "Updating the launcher", now);
        } else if (!self_update_) {
            refuse("Cannot update the launcher",
                   "Only the launcher's AppImage updates itself, and this launcher does not run from one.", now);
        } else if (const auto refusal = self_update_->start(now)) {
            refuse(refusal->title, refusal->why, now);
        }
    } else if (id == "release-page") {
        const std::string page = facts_.newer ? facts_.newer->page : facts_.main_news ? facts_.main_news->page : "";
        if (!page.empty()) effects.push_back({Effect::Kind::kOpenUrl, page, {}, {}, {}});
    } else if (id == "install" || id == "setup" || id == "more:setup-again") {
        if (task)
            refuse("Another task is running", "Wait for it to end, then install.", now);
        else if (!facts_.caps.setup_game && !facts_.builder) {
            refuse("Cannot install", "The game builder is missing from this launcher.", now);
        } else
            effects.push_back({Effect::Kind::kChooseGame, {}, {}, {}, {}});
    } else if (id == "resume") {
        if (task)
            refuse("Another task is running", "Wait for it to end, then install.", now);
        else if (parts_.environment.exists(facts_.install.game)) {
            facts_.chosen_game = facts_.install.game;
            return chosen_folder(facts_.install.folder, now);
        } else {
            // (The launcher did not start it, or the archive has moved.)
            effects.push_back({Effect::Kind::kChooseGame, "resume", {}, {}, {}});
        }
    } else if (id == "check-again") {
        if (facts_.preflight) {
            facts_.preflight->running = true;
            facts_.preflight->checks.clear();
            facts_.preflight->generation = ++preflight_serial_;
            effects.push_back({Effect::Kind::kRunPreflight, {}, facts_.preflight->game, facts_.preflight->folder, {},
                               preflight_serial_});
        }
    } else if (id == "preflight-cancel") {
        facts_.preflight.reset();
    } else if (id == "uninstall") {
        if (task)
            refuse("Another task is running", "Wait for it to end, then uninstall.", now);
        else if (facts_.game_running)
            refuse("The game is running", "Quit it, then uninstall.", now);
        else {
            uninstall_ = {};
            dialog_ = uninstall_view(facts_, facts_.saves, facts_.saves_custom, uninstall_);
        }
    } else if (id == "update")
        start_update(now);
    else if (id == "update-everything")
        start_update_all(now);
    else if (id == "update-resume") {
        // (Try Again: from the part that stopped, the parts done stay done.)
        if (chain_ && chain_->stopped && !task && !before_)
            start_part(now);
        else
            start_update_all(now);
    }
    else if (id == "play") {
        auto e = play(now);
        effects.insert(effects.end(), e.begin(), e.end());
    } else if (id == "open-folder") {
        effects.push_back({Effect::Kind::kOpenPath, {}, facts_.install.folder, {}, {}});
    } else if (id == "get-packages") {
        if (task)
            refuse("Another task is running", "Wait for it to end, then download numpy and Pillow.", now);
        else if (facts_.importer.empty() || facts_.python.empty()) {
            refuse("Cannot download numpy and Pillow", "The character importer or Python 3 is missing.", now);
        } else {
            TaskSpec spec;
            spec.kind = TaskKind::kPackages;
            spec.title = "Downloading numpy and Pillow";
            spec.command = parts_.commands.packages(facts_);
            start_task(std::move(spec), now);
        }
    } else if (id == "outfits-all") {
        if (!task) {
            const auto choices = outfit_choices(facts_);
            const bool all = std::all_of(choices.begin(), choices.end(),
                                         [&](const Fighter* f) { return wants_outfits(facts_, *f); });
            for (const Fighter* f : choices) facts_.outfits[f->name] = !all;
        }
    } else if (const auto name = rest("outfits:")) {
        const Fighter* f = fighter(facts_, *name);
        if (f && !task && outfits_choosable(*f, owns(facts_, *f))) facts_.outfits[f->name] = !wants_outfits(facts_, *f);
    } else if (id == "update-outfits")
        start_import(outfits_to_change(facts_), now);
    else if (const auto name = rest("fighter:")) {
        const Fighter* f = fighter(facts_, *name);
        if (!f)
            said_ = *name + " is not known";
        else if (f->installed && !f->outdated && !f->update && !outfits_changed(facts_, *f))
            start_remove({f->name}, now);
        else
            start_import({f->name}, now);
    } else if (const auto name = rest("remove:")) {
        start_remove({*name}, now);
    } else if (id == "add-all")
        start_import(base_to_add(facts_, kTekken7), now);
    else if (const auto game = rest("add-all:"))
        start_import(base_to_add(facts_, *game), now);
    else if (const auto game = rest("remove-all:")) {
        if (!to_remove_all(facts_, *game).empty()) {
            remove_all_game_ = *game;
            dialog_ = remove_all_view(facts_, *game);
        }
    } else if (id == "update-stand-ins")
        start_import(to_update(facts_, kTekken8, true), now);
    else if (id == "update-all")
        start_import(to_update(facts_, kTekken7), now);
    else if (const auto game = rest("update-all:"))
        start_import(to_update(facts_, *game), now);
    else if (id == "add-all-owned")
        start_import(owned_to_add(facts_, kTekken7), now);
    else if (id == "add-all-owned:all")
        start_import(all_owned_to_add(facts_), now);
    else if (const auto game = rest("add-all-owned:"))
        start_import(owned_to_add(facts_, *game), now);
    else if (id == "dlc" || id == "dlc:tekken8") // (both games' open together)
        facts_.dlc_expanded = !facts_.dlc_expanded;
    else if (id == "task") {
        if (task)
            runner_.cancel();
        else if (chain_ && chain_->next) {
            // (Cancel between two parts of Home's UPDATE: the next one never starts.)
            chain_->next = false;
            chain_->stopped = true;
        } else
            runner_.close();
    } else if (id == "details")
        runner_.set_details(!runner_.view().details.checked);
    else if (const auto command = rest("copy:"))
        effects.push_back({Effect::Kind::kCopy, *command, {}, {}, {}});
    // ---- Settings
    else if (id == "fullscreen" || id == "interpolation" || id == "input-delay" || id == "async-shaders" ||
             id == "precompile-shaders") {
        const display::Settings& s = display_.settings();
        const bool on = id == "fullscreen"      ? s.fullscreen
                        : id == "interpolation" ? s.interpolation
                        : id == "input-delay"   ? s.input_delay
                        : id == "async-shaders" ? s.async_shaders
                                                : s.precompile_shaders;
        if (!display_.set(id, !on)) said_ = display_.error();
    } else if (id == "resolution") {
        const auto& all = display::kResolutions;
        const int at = static_cast<int>(std::find(std::begin(all), std::end(all), display_.settings().resolution) -
                                        std::begin(all));
        return choose(id, (at + 1) % static_cast<int>(std::size(all)), now);
    } else if (id == "performance") {
        if (!display_.performance()) said_ = display_.error();
    } else if (const auto input = rest("key:")) {
        keys_.pick(input_index(*input), Device::kKeyboard, now);
    } else if (id == "restore-keys") {
        keys_.restore(now);
        said_ = keys_.keymap().is_default() ? "the default keys" : "not restored";
    } else if (id == "sounds")
        launcher_.sounds = !launcher_.sounds;
    else if (id == "reduce-motion")
        launcher_.reduce_motion = !launcher_.reduce_motion;
    else if (id == "prompts")
        return choose(id, (launcher_.prompts + 1) % static_cast<int>(std::size(kPrompts)), now);
    else if (id == "text-size") {
        const auto at = std::find(std::begin(kTextSizes), std::end(kTextSizes), launcher_.text_size);
        return choose(id, static_cast<int>((at - std::begin(kTextSizes) + 1) % std::size(kTextSizes)), now);
    }
    // ---- Windows
    else if (id == "more")
        effects.push_back({Effect::Kind::kOpenMenu, {}, {}, {}, {}});
    else if (id == "more:build")
        start_worker(TaskKind::kBuild, "Building the game", now);
    else if (id == "more:install")
        start_worker(TaskKind::kInstallSource, "Installing the game", now);
    else if (id == "more:update")
        start_worker(TaskKind::kUpdateInstalled, "Updating the installed game", now);
    else if (id == "more:open-logs")
        effects.push_back({Effect::Kind::kOpenPath, {}, facts_.windows.logs, {}, {}});
    else if (id == "more:latest-log") {
        if (facts_.windows.latest_log.empty()) {
            dialog_ =
                message_view("No log yet", "No task has written a log in " + path_utf8(facts_.windows.logs) + " yet.");
        } else {
            effects.push_back({Effect::Kind::kOpenPath, {}, facts_.windows.latest_log, {}, {}});
        }
    } else if (id == "open-log") {
        effects.push_back({Effect::Kind::kOpenPath, {}, runner_.spec().command.log_file, {}, {}});
    } else if (const auto key = rest("folder:")) {
        effects.push_back({Effect::Kind::kChooseFolder, *key, {}, {}, {}});
    } else if (id == "save-folders") {
        if (task)
            refuse("Folders not saved", "Wait for the task to end before changing folders.", now);
        else {
            effects.push_back({Effect::Kind::kSaveFolders, {}, {}, {}, {}});
            folders_note_ = "Saved.";
            folders_note_until_ = now + 4;
        }
    } else if (id == "open-keyboard-file") {
        if (const auto* file = dynamic_cast<const KeyFile*>(&parts_.keys)) {
            effects.push_back({Effect::Kind::kOpenPath, {}, file->file, {}, {}});
        }
    } else {
        said_ = "no " + id + " to activate";
    }
    sync();
    return effects;
}

std::vector<Effect> LauncherModel::take_effects() {
    std::vector<Effect> out;
    out.swap(pending_);
    return out;
}

View LauncherModel::view() const {
    View v;
    v.page = page_;
    v.header = header_view(facts_, page_ == Page::kSettings);
    v.banner = banner_view(facts_);
    v.notice = notice_view(facts_);
    v.game = game_view(facts_);
    v.characters = characters_view(facts_);
    if (page_ == Page::kSettings) {
        SettingsInput in;
        in.display = &display_;
        in.monitors = monitors_;
        in.keys = &keys_;
        in.launcher = launcher_;
        in.folders_note = folders_note_;
        v.settings = settings_view(facts_, in);
    }
    v.task = runner_.view();
    if (update_shown()) {
        const Chain& c = *chain_;
        TaskView::Chain& ch = v.task.chain;
        ch.count = static_cast<int>(c.parts.size());
        ch.at = static_cast<int>(c.at) + 1;
        const std::string& kind = c.parts[c.at].kind;
        ch.part = kind == "launcher" ? "The launcher" : kind == "game" ? "The game program" : "Fighters";
        for (size_t i = c.at + (c.next ? 0 : 1); i < c.parts.size() && !c.done; ++i) ch.next.push_back(c.parts[i]);
        ch.waiting = c.next;
        ch.handed_over = c.handed_over;
        ch.stopped = c.stopped;
        ch.done = c.done;
        if (c.done) {
            std::vector<std::string> brought;
            for (const std::string& r : c.results)
                if (r != "no fighters") brought.push_back(r);
            ch.summary = brought.empty() ? std::string("Everything is up to date") : "Updated: " + joined(brought);
        }
        for (const auto& [name, why] : c.later) {
            std::string w = why;
            while (!w.empty() && (w.back() == '.' || w.back() == ' ')) w.pop_back();
            ch.later += (ch.later.empty() ? "Left for later: " : "; ") + name + " (" + w + ")";
        }
        if (!ch.later.empty()) ch.later += ".";
    }
    v.dialog = dialog_;
    if (dialog_ && dialog_->id == "uninstall")
        v.dialog = uninstall_view(facts_, facts_.saves, facts_.saves_custom, uninstall_);
    return v;
}

} // namespace launcher::model
