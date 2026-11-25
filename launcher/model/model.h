#pragma once

// The launcher without its window: the facts, the controllers (the status and
// Steam's answer, GitHub's, the task, the keys, display.ini, the AppImage's
// update) and activate(id) for every element id (U14), as launcher/app's
// Launcher did inside its GTK code. The app draws view() and does the
// Effects that need the OS (file pickers, opening a page, a folder, the
// uninstall's deleting, the preflight's disk reads); everything a program
// does goes through the injected Starter, and time is what the app gives.

#include "builders.h"
#include "facts.h"
#include "preflight.h"
#include "self_update.h"
#include "settings.h"
#include "task.h"
#include "uninstall.h"
#include "view.h"

#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace launcher::model {

// The programs each task and question runs (per OS: LinuxCommands, the
// Windows backend's main.py --worker / --query).
struct Commands {
    virtual ~Commands() = default;
    virtual std::optional<Command> status(const Facts& facts) = 0;
    virtual std::optional<Command> owned(const Facts& facts) = 0;
    virtual std::optional<Command> main_news(const Facts& facts) = 0; // none without a known build commit
    // Whether a newer release is out, asked by the launcher's files (Windows' release .exe). None: the AppImage
    // asks GitHub itself (SelfUpdate), the rest never update themselves.
    virtual std::optional<Command> release(const Facts&) { return std::nullopt; }
    virtual Command import(const Facts& facts, const std::vector<std::string>& names, const std::string& outfits) = 0;
    virtual Command remove(const Facts& facts, const std::vector<std::string>& names) = 0;
    virtual Command packages(const Facts& facts) = 0;
    virtual Command install(const Facts& facts, const fs::path& game, const fs::path& folder) = 0;
    virtual Command update(const Facts& facts) = 0;
    virtual Command shaders(const Facts& facts) = 0;
    virtual std::optional<Command> play(const Facts& facts) = 0;
    // Windows' own tasks (setup, build, install from source, update installed, launcher, files).
    virtual std::optional<Command> worker(const Facts& facts, TaskKind kind) = 0;
    // Before a task (Windows): the folders saved first (Set Up Game's archive and folder: the worker reads them
    // from launcher.json), then what refuses it asked (--query check). None: nothing first.
    virtual std::optional<Command> presave(const Facts&, TaskKind) { return std::nullopt; }
    virtual std::optional<Command> precheck(const Facts&, TaskKind, const std::vector<std::string>&) {
        return std::nullopt;
    }
};

// Linux (spec/linux_app.md 2.x): the importer's scripts with Python, the kit's ttt2-build, the game's program.
struct LinuxCommands : Commands {
    // The importer's environment: PYTHONUNBUFFERED, PYTHONDONTWRITEBYTECODE and the kit's helpers that are there.
    std::map<std::string, std::string> importer_env;
    fs::path game_log; // Places::game_log()

    std::optional<Command> status(const Facts& facts) override;
    std::optional<Command> owned(const Facts& facts) override;
    std::optional<Command> main_news(const Facts& facts) override;
    Command import(const Facts& facts, const std::vector<std::string>& names, const std::string& outfits) override;
    Command remove(const Facts& facts, const std::vector<std::string>& names) override;
    Command packages(const Facts& facts) override;
    Command install(const Facts& facts, const fs::path& game, const fs::path& folder) override;
    Command update(const Facts& facts) override;
    Command shaders(const Facts& facts) override;
    std::optional<Command> play(const Facts& facts) override;
    std::optional<Command> worker(const Facts&, TaskKind) override { return std::nullopt; }
};
// Windows: what the Tk window ran (spec windows 2.1 and 3.2): `<python> -u <root>/launcher/windows/main.py
// --build-dir <build> --config <config>` with --query <name> (status, owned, main: one JSON object on the last
// line) or --worker <action> --cancel-file <logs>/<action>-<stamp>.cancel --outfits <names|none> [names] (its
// log beside it as .log); Python is facts.python, the folders facts.windows (from --query state), in the
// launcher's files folder. Play is what --query state answered (C8).
struct WindowsCommands : Commands {
    // A task's files' stamp: the app's clock ("20261124-140501-123456", as the Tk window named them).
    std::function<std::string()> stamp;

    Command query(const Facts& facts, const std::string& name) const;
    Command worker_command(const Facts& facts, const std::string& action, const std::vector<std::string>& names,
                           const std::string& outfits) const;
    // `--query release`: GitHub's newest release, for the release .exe (none from a project ZIP or a build).
    std::optional<Command> release(const Facts& facts) override;
    // `--query check --action ACTION [names]`: what refuses a task before it starts (SetupProblem).
    Command check(const Facts& facts, const std::string& action, const std::vector<std::string>& names) const;
    // `--query save-settings`: Settings > Folders checked and saved; the folders go as a JSON object on its input.
    Command save_settings(const Facts& facts, const std::map<std::string, std::string>& folders) const;

    std::optional<Command> status(const Facts& facts) override;
    std::optional<Command> owned(const Facts& facts) override;
    std::optional<Command> main_news(const Facts& facts) override;
    Command import(const Facts& facts, const std::vector<std::string>& names, const std::string& outfits) override;
    Command remove(const Facts& facts, const std::vector<std::string>& names) override;
    Command packages(const Facts&) override { return {}; }                                  // (Linux only)
    Command install(const Facts&, const fs::path&, const fs::path&) override { return {}; } // (Linux only)
    Command update(const Facts& facts) override;
    Command shaders(const Facts& facts) override;
    std::optional<Command> play(const Facts& facts) override { return facts.windows.play; }
    std::optional<Command> worker(const Facts& facts, TaskKind kind) override;
    std::optional<Command> presave(const Facts& facts, TaskKind kind) override;
    std::optional<Command> precheck(const Facts& facts, TaskKind kind, const std::vector<std::string>& names) override;
};
// Whether an element id is one this OS's window has (U1): Windows' More, Set Up Game, Folders, Performance,
// keyboard.ini and log; Linux's install flow, uninstall, numpy/Pillow download and commands to copy.
bool of_this_os(const Caps& caps, const std::string& id);

// The worker action of a task kind ("setup", "build", "install", "update", "upgrade", "launcher", "files",
// "shaders", "import", "remove"), "" for one Windows has none for.
const char* worker_action(TaskKind kind);

std::map<std::string, std::string> importer_environment(const fs::path& kit,
                                                        const std::function<bool(const fs::path&)>& exists);

// What the app does for the model.
struct Effect {
    enum class Kind {
        kChooseGame,   // a .wua (Install…; Windows: Set Up Game's archive): then chosen_game()
        kChooseFolder, // where to install (then chosen_folder()); Windows: folder:<key> (text = the key)
        kRunPreflight, // run_checks(path, path2, work) off the UI thread: then preflight_done(..., generation)
        kUninstall,    // uninstall(places, path, uninstall) off the UI thread: then uninstall_done()
        kOpenUrl,      // text
        kOpenPath,     // a folder or a file (path)
        kCopy,         // text to the clipboard
        kOpenMenu,     // Windows: More's menu (view().game.more)
        kSaveOwned,    // Steam's answer kept (text: the JSON) in Places::owned_cache
        kSaveFolders,  // Windows: Settings > Folders saved (main.py --query save-settings)
        kOpenUpdated,  // Windows: the updated launcher opened (then opened_updated()); go_on: Home's UPDATE goes on there
        kQuit,
    };
    Kind kind;
    std::string text;
    fs::path path, path2;
    UninstallOptions uninstall{};
    uint64_t generation = 0; // kRunPreflight: the request its answer goes with (Preflight::generation)
    bool go_on = false;      // kOpenUpdated: opened with kContinueVariable (the rest of Home's UPDATE runs there)
};

// What the model asks of the PC (the app's real one, a test's).
struct Environment {
    virtual ~Environment() = default;
    // Looks again: the install, what built it, its icon, whether its game runs (not started here).
    virtual void look(Facts& facts) = 0;
    // install_target(): the folder an install into `chosen` goes to, or why not.
    virtual std::optional<fs::path> install_target(const fs::path& chosen, std::string* why) = 0;
    virtual void write_started_record(const fs::path& folder, const fs::path& game) = 0;
    // Whether the install that was stopped had begun copying (the folder's started record).
    virtual bool started(const fs::path& folder) = 0;
    virtual void forget_started_record() = 0;
    virtual std::string log_end(const fs::path& log) = 0; // a log's last 64 KB
    virtual bool exists(const fs::path& path) = 0;
    virtual fs::path build_work() = 0; // Places::build_work()
    // Whether the installed game still runs (one cheap look: Linux /proc), asked every kGameWatchSeconds while a
    // game the launcher did not start runs. Unless an OS can tell: what the facts say.
    virtual bool game_runs(const Facts& facts) { return facts.game_running; }
};

enum class Page { kMain, kSettings };

struct View {
    Page page = Page::kMain;
    Header header;
    Banner banner;
    NoticeView notice;
    GameView game;
    CharactersView characters;
    std::optional<SettingsView> settings;
    TaskView task;
    std::optional<Dialog> dialog;
    bool operator==(const View&) const = default;
};

class LauncherModel {
public:
    static constexpr double kStatusSeconds = 5;         // back in the window: looked at again after this
    static constexpr double kReleaseSeconds = 6 * 3600; // GitHub asked again after this
    static constexpr double kGameWatchSeconds = 2;      // a game started elsewhere: looked for again after this
    static constexpr double kContinueSeconds = 300;     // continue_update(): given up when the facts take longer

    struct Parts {
        Commands& commands;
        Starter& starter;
        Environment& environment;
        KeyStore& keys;
        UpdateFiles* update_files = nullptr; // Linux AppImage (with SelfUpdate::Config::appimage)
        SelfUpdate::Config update{};
        fs::path display_file;
        KeyLabel key_label = us_key_label;
        // Windows: reads the answers of the steps before a task (backend/windows_backend.h's parse_save_settings
        // and parse_check, as their problem: code "" none); unset, tasks start at once.
        std::function<std::optional<SetupProblem>(const std::string& output, std::string* error)> read_save,
            read_check;
    };
    LauncherModel(Facts facts, Parts parts);

    // ---- events from the app
    void start(double now);     // the window opened: look, the status, GitHub
    void tick(double now);      // timers: notes, auto-hide, the update's watch, a game started elsewhere
    // When tick() has something to do next by itself (the loop wakes for it), a large number when nothing.
    double next_tick(double now) const;
    void activated(double now); // the window active again (6 h: GitHub; 5 s: the status)
    void deactivated();         // keys held are forgotten (not a key chosen while tests run)
    std::vector<Effect> activate(const std::string& id, double now);
    std::vector<Effect> choose(const std::string& id, int index, double now); // a list's entry
    std::vector<Effect> request_close(double now);
    // Answers to effects.
    std::vector<Effect> chosen_game(const fs::path& game, double now);
    std::vector<Effect> chosen_folder(const fs::path& folder, double now);
    // The checks' answer to kRunPreflight `generation`: an answer to an earlier request (another folder, or checked
    // again since) is dropped; the install starts only when they pass and no task runs.
    std::vector<Effect> preflight_done(const std::vector<Check>& checks, double now, uint64_t generation);
    void uninstall_done(const UninstallReport& report, double now);
    void opened_updated(const std::string& error, double now); // Windows: "" when the new launcher opened
    // Keys while Settings is open (U4): true when used.
    bool key_down(int usage, bool repeat, double now);
    void key_up(int usage, double now);
    void pick_key(int input, Device device, double now);
    void cancel_key() { keys_.cancel(); }
    void set_monitors(std::vector<Monitor> monitors) { monitors_ = std::move(monitors); }
    void set_launcher_settings(LauncherSettings s) { launcher_ = s; }
    // Windows: what --query state answered (after each task too).
    void set_windows_state(WindowsState state);
    // Home's UPDATE after its launcher part (kContinueVariable: the launcher that updated this one opened it so):
    // the rest starts by itself once the facts are complete (the importer's answer in, nothing running), never the
    // launcher's part again. Given up after kContinueSeconds.
    void continue_update(double now);
    // A part of Home's UPDATE runs, or starts next by itself: the task screen shows the update.
    bool in_update() const { return chain_ && (chain_->running || chain_->next); }
    // The task that ended was a part of Home's UPDATE that is not its end (another part follows, here or in the new
    // launcher): one sound for the whole update (updates_done()).
    bool update_goes_on() const { return chain_ && !chain_->stopped && !chain_->done; }
    // The task shown (running or its result) is a part of Home's UPDATE (view().task.chain says which).
    bool update_shown() const {
        return chain_ && (chain_->running || chain_->next || chain_->end_serial == runner_.serial());
    }
    // How many of Home's UPDATEs ended with every part done (the app's sound when it changes).
    int updates_done() const { return updates_done_; }
    // Something the player is told as a refusal is (no task runs then): the app's own news, e.g. files put back.
    void tell(const std::string& title, const std::string& text, double now) { refuse(title, text, now); }

    // What the model needs done that came from a program's end (Steam's answer kept, quit after a task, ...):
    // the app takes them each frame.
    std::vector<Effect> take_effects();

    // ---- what is shown
    View view() const;
    const Facts& facts() const { return facts_; }
    Facts& mutable_facts() { return facts_; }
    bool busy() const;
    const TaskRunner& task() const { return runner_; }
    TaskRunner& task() { return runner_; }
    const KeyCapture& keys() const { return keys_; }
    const DisplayController& display() const { return display_; }
    Page page() const { return page_; }
    const LauncherSettings& launcher_settings() const { return launcher_; }
    // The test action's answer of the last thing done (refusals, bind: ...), "" when none.
    const std::string& said() const { return said_; }

private:
    void refresh(double now);
    void check_again(double now);
    void load_status(double now);
    void check_ownership(double now);
    void check_release(double now);
    void check_main(double now);
    void refuse(const std::string& title, const std::string& why, double now);
    void start_task(TaskSpec spec, double now);
    void start_import(const std::vector<std::string>& names, double now);
    void start_remove(const std::vector<std::string>& names, double now);
    void start_update(double now);
    void start_worker(TaskKind kind, std::string title, double now);
    std::vector<Effect> play(double now);
    void launch_game(double now);
    std::vector<Effect> uninstall_confirmed(double now);
    void task_ended(const TaskResult& result);
    void before_next(double now);
    void before_answered(double now);
    void sync();
    // Home's UPDATE (update_plan's parts, one task each).
    void start_update_all(double now);
    void start_part(double now);
    void part_ended(const TaskResult& result);
    void part_done();
    bool settled() const; // nothing runs or is asked: the facts are the PC's

    Facts facts_;
    Parts parts_;
    TaskRunner runner_;
    std::unique_ptr<SelfUpdate> self_update_;
    DisplayController display_;
    KeyCapture keys_;
    LauncherSettings launcher_;
    std::vector<Monitor> monitors_;
    Page page_ = Page::kMain;

    std::optional<Dialog> dialog_;
    std::string remove_all_game_;
    UninstallChoice uninstall_;
    fs::path setup_source_;

    std::unique_ptr<Job> status_job_, owned_job_, main_job_, release_job_, game_job_, done_job_;
    std::string status_out_, status_err_, owned_out_, main_out_, release_out_, release_err_;
    bool status_again_ = false, release_checking_ = false, main_checking_ = false;
    double status_time_ = -1e9, release_time_ = -1e9, now_ = 0;
    double game_look_ = 0;          // a game started elsewhere: when it is looked for next
    uint64_t preflight_serial_ = 0; // the last kRunPreflight asked
    bool quit_after_task_ = false;
    std::string folders_note_;
    double folders_note_until_ = -1;
    std::string said_;
    std::vector<Effect> pending_;
    // Windows: a task waiting for the steps before it (presave, precheck).
    struct Before {
        TaskSpec spec;
        int stage = 0; // 0 presave next, 1 precheck next, 2 the task
        bool save = false; // the step running is the presave
    };
    std::optional<Before> before_;
    std::unique_ptr<Job> before_job_;
    std::string before_out_, before_err_;
    bool before_done_ = false;
    // Home's UPDATE that runs, waits for its next part, or stopped (Try Again goes on from it).
    struct Chain {
        std::vector<UpdatePart> parts; // launcher, game, fighters: those to do, in order
        size_t at = 0;                 // the part that runs, starts next, or stopped
        bool running = false;          // its task was started and has not ended
        bool next = false;             // the part `at` starts once settled()
        bool stopped = false;
        bool done = false;
        bool handed_over = false;      // the launcher's part ended with the new launcher opened
        std::string launcher_to;       // the version the launcher's part brings
        std::vector<std::string> results; // what each part done brought: "launcher 0.9.0", "the game program", ...
        std::vector<std::pair<std::string, std::string>> later; // characters left for later, and why
        int end_serial = -1;           // the runner's serial when its last part ended (that result is the update's)
    };
    std::optional<Chain> chain_;
    bool continue_ = false;
    double continue_until_ = -1;
    int updates_done_ = 0;
};

} // namespace launcher::model
