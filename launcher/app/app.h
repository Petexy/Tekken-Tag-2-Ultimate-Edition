#pragma once

// The launcher's window (Ultimate Launcher, Tag Split): the loop that drives the model (launcher/model) and the
// toolkit (launcher/ui), the top band (brand, tabs, version, Sound, Quit), the prompt band, the task strip, the
// seam (its split per screen, its lean, the blue readout's slide, the wipe between screens), the model's dialogs
// and the Effects it asks for. Screens: home.cpp (Home in every state, the install's task screen), picker.cpp (the
// in-app file and folder browser). Test hooks (TTT2_LAUNCHER_TEST_*, --screenshot): tests_hooks.cpp.

#include "backend_linux.h"
#include "browser.h"
#include "launcher_ini.h"
#include "sound_cues.h"
#include "model.h"
#include "single_instance.h"
#include "starter.h"
#include "steps.h"
#include "subprocess.h"
#include "test_actions.h"

#include "ttt2ui/stage.h"
#include "ttt2ui/widgets.h"
#include "ttt2ui/window.h"

#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

namespace launcher::app {

namespace ui = ttt2::ui;
namespace m = launcher::model;

struct Options {
    fs::path game;                  // a .wua given on the command line
    std::string screenshot;         // --screenshot FILE: saved once everything has settled (after the test actions)
    int width = 0, height = 0;      // --size / TTT2_LAUNCHER_TEST_SIZE (0: the default)
    float scale = 0;                // --scale / TTT2_LAUNCHER_TEST_SCALE
    std::vector<TestAction> tests;  // TTT2_LAUNCHER_TEST_ACTIONS
    bool testing = false;           // test actions or a screenshot: offscreen, nothing opened on the desktop
    fs::path shots;                 // TTT2_LAUNCHER_TEST_SHOTS
    // --frames DIR --at MS,MS,...: after the LAST test action, frames at those milliseconds (a stepped clock, no
    // input), then one once everything has settled ("idle"), each checked (Tag Split rule, highlight on its item).
    fs::path frames;
    std::vector<int> frames_at;
    bool trace_cues = false;        // TTT2_LAUNCHER_TEST_CUES: each sound cue as "@cue <name>" (Sound on or off)
    // TTT2_LAUNCHER_TEST_WINDOW=real: tests in a real window (shown and presented: a headless compositor such as
    // cage with WLR_BACKENDS=headless) instead of SDL's offscreen driver.
    bool real_window = false;
    std::unique_ptr<SingleInstance> instance;
};

enum class Screen : int { kHome = 0, kFighters = 1, kSettings = 2 };

// The window's clock: real time, or held and stepped by hand (frame captures: each frame exactly when wanted).
class AppClock final : public ui::Clock {
public:
    double now() const override { return held_ ? virtual_ : real_.now() - offset_; }
    void hold(double t) {
        virtual_ = t;
        held_ = true;
    }
    void release() {
        offset_ = real_.now() - virtual_;
        held_ = false;
    }
    bool held() const { return held_; }

private:
    ui::SystemClock real_;
    double virtual_ = 0, offset_ = 0;
    bool held_ = false;
};

class App {
public:
    explicit App(Options options);
    ~App();
    int run();
    // Work for the UI thread (from any thread: threads' ends, file dialogs); the loop wakes for it.
    void post(std::function<void()> work);
    // What plays the sound cues (sound_cues.h); called on the UI thread, only while Sound is on.
    void set_sound_hook(ttt2::app::SoundHook hook) { sound_ = std::move(hook); }

private:
    // ---- the loop (app.cpp)
    bool open_window();
    void make_model();
    void pump_input(double now, bool wait);
    void frame(double now);
    void declare();
    void on_events(const std::vector<ui::Event>& events);
    void activate(const std::string& id, ttt2::ui::Device device = ttt2::ui::Device::None);
    void refused(const std::string& id);
    void handle(std::vector<m::Effect> effects);
    void go(Screen to);
    void cue(ttt2::app::Cue c);
    // The drill-in lock (FEEDBACK F4): `opener` (a crimson item) gave the focus to `target` on the blue side; the
    // crimson half is locked (ui::Box::locked, the stage's veil) until Back or a click on it. drill_out: the focus
    // goes to `to` (a crimson item clicked), else back to the opener.
    void drill_in(const std::string& opener, const std::string& target);
    void drill_out(const std::string& to = {});
    bool drilled() const;
    void toast(const std::string& title, const std::string& text, bool bad = true);
    void run_preflight(const fs::path& game, const fs::path& folder);
    void run_uninstall(const fs::path& folder, UninstallOptions options);
    void answer_game(const fs::path& game);
    void sync_log();
    std::string focused_label() const;
    const m::Action* action(const std::string& id) const;
    double now() const;
    bool readouts_animating(double t) const {
        return readout_.animating(t) || fighters_ro_.animating(t) || settings_ro_.animating(t);
    }

    // ---- bands (app.cpp)
    void top_band();
    void bottom_band();
    void task_strip();
    void dialog_band();
    std::vector<ui::Hint> hints() const;

    // ---- screens (home.cpp)
    float share() const;
    bool tall() const;
    bool task_screen() const { return task_screen_; }
    void home(const ui::Box& crimson, const ui::Box& blue);
    void home_installed(const ui::Box& crimson, const ui::Box& blue);
    void home_first_run(const ui::Box& crimson, const ui::Box& blue);
    void home_unfinished(const ui::Box& crimson, const ui::Box& blue);
    void home_preflight(const ui::Box& crimson, const ui::Box& blue);
    void home_task(const ui::Box& crimson, const ui::Box& blue);
    // How far the task is as its screen shows it (a build: its steps, each one share), -1 when unknown.
    double task_fraction() const;
    void game_head(const std::string& kick);
    void home_readout(const std::string& key);
    void notice_card();
    void placeholder(const ui::Box& crimson, const ui::Box& blue);
    std::string slot_target() const;
    // A preflight check row's command to copy (its action id "copy:..."), "" when it has none.
    std::string check_copy(const std::string& row) const;
    bool check_has_copy(const std::string& row) const { return !check_copy(row).empty(); }

    // ---- Fighters (fighters.cpp)
    struct FighterGroup {
        std::string key, title, game; // "t7" / "dlc" / "t8", "Tekken 7 DLC", kTekken7
        const m::GameGroup* group = nullptr;
        bool dlc = false;
        std::vector<const m::FighterRow*> rows;
    };
    // A fighter in the task that runs: their turn (0 waiting, 1 now, 2 done), their share of the bar.
    struct FighterTask {
        bool in = false;
        int index = 0, count = 0, state = 0;
        double fraction = 0;
        const char* verb = "";
        std::string detail;
    };
    std::vector<FighterGroup> fighter_groups() const;
    const Fighter* status_fighter(const std::string& name) const;
    const m::FighterRow* fighter_row(const std::string& name) const;
    std::vector<m::Action> fighter_actions(const m::FighterRow& row) const;
    FighterTask fighter_task(const std::string& name) const;
    std::vector<m::Action> group_actions(const FighterGroup& group) const;
    void fighters(const ui::Box& crimson, const ui::Box& blue);
    void fighters_early(const ui::Box& crimson, const ui::Box& blue);
    void fighters_blue(const ui::Box& blue, const std::vector<FighterGroup>& groups);
    void fighter_view(const std::string& name);
    void group_view(const std::string& group, const std::string& action_id, const std::vector<FighterGroup>& groups);
    void outfits_view();
    void needs_view();
    bool fighters_activate(const std::string& id);

    // ---- Settings (settings_screen.cpp)
    static constexpr double kCaptureSeconds = 10; // choosing a key stops after this long without one
    std::vector<std::string> settings_sections() const;
    void settings_switch(int delta, const std::string& to = {});
    void settings(const ui::Box& crimson, const ui::Box& blue);
    void settings_keys_crimson(const m::SettingsView& view, const std::string& up);
    void settings_blue(const ui::Box& blue, const m::SettingsView& view);
    void setting_view(const m::SettingsView& view, const std::string& id);
    void key_view(const m::SettingsView& view, const std::string& id);
    void folder_view(const m::SettingsView& view, const std::string& key);
    void settings_change(const std::string& id, int delta);
    bool settings_activate(const std::string& id, ttt2::ui::Device device);
    void key_capture_tick(double now);
    std::string folder_default(const std::string& key) const;
    void set_folder(const std::string& key, const std::string& value);
    // The launcher's own settings changed (Sounds, Reduce motion, Button prompts, Text size): applied and saved.
    void apply_launcher_settings();
    void apply_prompts(int prompts);

    // ---- the in-app browser (picker.cpp)
    void open_picker(bool folder, const std::string& purpose);
    void picker_dir(const fs::path& dir);
    void picker_screen(const ui::Box& crimson, const ui::Box& blue);
    bool picker_activate(const std::string& id);
    void picker_chosen(const fs::path& path);
    void close_picker();

    // ---- tests (tests_hooks.cpp)
    void test_tick(double now);
    bool settled(double now) const;
    void shot(const std::string& name);
    void test_said(bool ok, const std::string& message);
    void test_watch_task();
    void test_audit(double now);    // (every frame of a test run: the Tag Split rule; "@audit failed ...")
    void test_capture(double now);  // (--frames)
    // press:/pad:/steam:/click:/hover: test actions: input as the devices give it (through the router).
    bool test_input(const std::string& name, const std::vector<std::string>& args, double now);

    Options o_;
    Places places_;
    std::optional<fs::path> appimage_;
    std::string banner_;

    // toolkit
    ui::Window window_;
    std::unique_ptr<ui::TextureRegistry> textures_;
    std::unique_ptr<ui::TextEngine> text_;
    std::unique_ptr<ui::Icons> icons_;
    std::unique_ptr<ui::Canvas> canvas_;
    std::unique_ptr<ui::Ui> ui_;
    std::unique_ptr<ui::SplitStage> stage_;
    std::unique_ptr<ui::Wipe> wipe_;
    ui::InputRouter router_;
    AppClock clock_;
    ui::Readout readout_;
    ui::LogView log_;
    size_t log_seen_ = 0;
    std::string log_last_;

    // model
    std::unique_ptr<ProcessHost> host_;
    std::unique_ptr<backend::ProcessStarter> starter_;
    std::unique_ptr<LinuxEnvironment> env_;
    m::LinuxCommands commands_;
    std::unique_ptr<m::KeyFile> keys_;
    LinuxUpdateFiles files_;
    std::unique_ptr<m::LauncherModel> model_;
    m::View view_;

    // posted work
    std::mutex posted_mutex_;
    std::deque<std::function<void()>> posted_;
    std::vector<std::thread> threads_;
    int working_ = 0; // threads not ended (preflight, uninstall)

    // what is shown
    Screen screen_ = Screen::kHome;
    std::map<int, std::string> saved_focus_;
    bool quit_ = false;
    bool first_ = true;
    double last_ = 0;
    int last_dy_ = 0;
    std::string readout_key_ = "play";
    int pre_index_ = 0;           // the check the blue side shows (preflight)
    bool task_screen_ = false;    // the install / update / uninstall / launcher update fills Home
    m::TaskKind task_kind_ = m::TaskKind::kInstall;
    std::string task_title_;
    bool task_was_running_ = false;
    std::string pending_choose_;  // kChooseGame's purpose ("" install, "resume")
    fs::path slot_folder_;        // where the install goes (first run's second slot)
    std::string toast_title_, toast_text_;
    bool toast_bad_ = true;
    double toast_until_ = -1;
    bool sounds_ = false;
    ttt2::app::SoundHook sound_;
    struct Drill {
        Screen screen;
        std::string opener, target;
    };
    std::optional<Drill> drill_;

    // Fighters
    std::string fighters_key_;                       // what the blue side shows ("f:<name>", "g:<group>:<id>", ...)
    ui::Readout fighters_ro_, settings_ro_;
    std::map<std::string, std::string> group_of_button_;  // a group action's id -> its group's key
    // Settings
    std::string settings_section_ = "display"; // display / keyboard / launcher / folders
    std::string settings_key_;                 // the row the blue side shows
    int settings_slide_ = 1;                   // the side the last value change came from
    double capture_since_ = 0;                 // choosing a key since
    m::LauncherSettings applied_{};            // the launcher's settings as applied
    fs::path launcher_ini_;                    // where they are kept (beside display.ini)
    bool forced_glyphs_ = false;               // TTT2_CONTROLLER chose the prompts
    std::map<std::string, std::string> folder_defaults_; // Windows: Settings > Folders' defaults
    bool folders_changed_ = false;
    // Every action the screen declared this frame (Fighters, Settings): their whys, labels and kinds.
    std::map<std::string, m::Action> screen_actions_;

    // the in-app browser
    struct Picker {
        bool folder = false;
        std::string purpose; // "game", "folder"
        bool then_answer = false; // the model asked: its chosen_game / chosen_folder
        fs::path dir;
        std::vector<Entry> entries;
        std::vector<Place> places;
        std::string error;
        std::optional<uint64_t> free;
        std::string back_focus;
    };
    std::optional<Picker> picker_;
    std::string picker_key_; // the browser's entry the blue side shows

    // tests
    size_t test_next_ = 0;
    int test_number_ = 0;
    enum class TestWait { kNone, kSettle, kTask, kPlay, kTime, kPreflight, kQuitting } test_wait_ = TestWait::kNone;
    TestAction test_now_;
    std::string test_label_;
    double test_since_ = 0, test_until_ = 0, idle_since_ = 0;
    int frames_idle_ = 0;
    bool test_running_shot_ = false, test_cancelled_ = false, test_task_seen_ = false;
    bool test_start_shot_ = false, screenshot_done_ = false;
    double cancel_poll_ = 0;
    int test_quit_ = 0;        // TTT2_LAUNCHER_TEST_QUIT_AT: 1 Quit pressed, 2 its dialog's picture taken
    double test_quit_at_ = 0;  // when that picture is taken
    int exit_code_ = 0;
    std::vector<std::pair<double, ui::RawEvent>> test_raw_;  // input of test actions, fed when due
    bool capturing_ = false;
    double capture_t0_ = 0;
    size_t capture_i_ = 0;
    std::vector<std::string> audit_seen_;
    int audit_failures_ = 0;
    std::string audit_where_;  // what the audit lines name (the test step)
    // The frame as painted (events are handled after it: a focus they move shows on the next frame).
    std::string painted_focus_;
    ui::Rect painted_highlight_{}, painted_focus_rect_{};
};

} // namespace launcher::app
