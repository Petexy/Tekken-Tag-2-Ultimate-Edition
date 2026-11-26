#pragma once

// The launcher's window (Golden Fist Launcher, Tag Split): the loop that drives the model (launcher/model) and the
// toolkit (launcher/ui), the top band (brand, tabs, version, Sound, Quit), the prompt band, the task strip, the
// seam (its split per screen, its lean, the blue readout's slide, the wipe between screens), the model's dialogs
// and the Effects it asks for. Screens: home.cpp (Home in every state, the install's task screen), picker.cpp (the
// in-app file and folder browser). Test hooks (TTT2_LAUNCHER_TEST_*, --screenshot): tests_hooks.cpp.

#ifdef _WIN32
#include "backend_windows.h"
#else
#include "backend_linux.h"
#endif
#include "browser.h"
#include "launcher_ini.h"
#include "sound_cues.h"
#include "model.h"
#include "single_instance.h"
#include "starter.h"
#include "steps.h"
#include "subprocess.h"
#include "test_actions.h"

#include "ttt2ui/sound.h"
#include "ttt2ui/stage.h"
#include "ttt2ui/widgets.h"
#include "ttt2ui/window.h"

#include <atomic>
#include <cstdio>
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
// Every text a player reads goes through these (launcher/core/i18n.h).
using i18n::tr;
using i18n::trn;

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
    fs::path files; // Windows' release .exe: the folder its files are in (startup's Start::files)
    // --ui-smoke-test FILE / TTT2_LAUNCHER_TEST_SMOKE: the first frame drawn, what was found written there as JSON
    // (smoke_start: this start's facts, JSON members), then the end.
    fs::path smoke;
    std::string rolled_back; // TTT2_LAUNCHER_ROLLED_BACK: the version an update opened, which never drew
    bool go_on_update = false; // TTT2_LAUNCHER_CONTINUE=update: Home's UPDATE goes on here after the launcher's part
    std::string smoke_start;
    bool offscreen = false; // TTT2_LAUNCHER_TEST_VIDEO=offscreen (Wine without a display)
#ifdef _WIN32
    WindowsArgs windows; // --files, --build-dir, --config (the source ZIP's bridge)
#else
    struct {
        fs::path files, build, config; // (Windows' options: taken and left unused)
    } windows;
#endif
};

// Wakes the loop (an event of its own): posted work or a program's lines are waiting.
void wake_loop();

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
    // What plays the sound cues (sound_cues.h); called on the UI thread, only while Sound is on. Without one set
    // before run(), the window's own player plays them (ui::Sounds: the game's menu sounds, else the launcher's).
    void set_sound_hook(ttt2::app::SoundHook hook) { sound_ = std::move(hook); }

private:
    // ---- the loop (app.cpp)
    bool open_window();
    void make_model();
    // Reads input and news until `draw_at` (or a wake: ambient frame, repeat, pad poll, the model's tick); whether
    // anything came that may change the picture.
    bool pump_input(double now, double draw_at);
    void frame(double now);
    bool animating(double t) const;
    bool slowed() const;
    bool model_changed(double t);
    double ambient_clock(double t);
    void test_idle_hooks(double t);
    void declare();
    void on_events(const std::vector<ui::Event>& events);
    void activate(const std::string& id, ttt2::ui::Device device = ttt2::ui::Device::None);
    void refused(const std::string& id);
    void handle(std::vector<m::Effect> effects);
    void go(Screen to);
    void cue(ttt2::app::Cue c);
    // ---- sounds (app.cpp): the one player behind the cues, kept in step with the Sound setting and the install
    void start_sounds();
    void sounds_tick();    // every frame: the setting, the game's folder when it changed, the player's tick
    void finish_sounds();  // at the end: a Play sound still heard is let finish (the window hidden), then closed
    static constexpr double kPlayHeard = 1.4; // seconds the Play sound is let finish when the launcher ends
    fs::path sound_folder() const;
    // The drill-in lock: `opener` (a crimson item) gave the focus to `target` on the blue side; the
    // crimson half is locked (ui::Box::locked, the stage's veil) until Back or a click on it. drill_out: the focus
    // goes to `to` (a crimson item clicked), else back to the opener.
    void drill_in(const std::string& opener, const std::string& target);
    void drill_out(const std::string& to = {});
    bool drilled() const;
    void toast(const std::string& title, const std::string& text, bool bad = true);
    void run_preflight(const fs::path& game, const fs::path& folder, uint64_t generation);
    void run_uninstall(const fs::path& folder, UninstallOptions options);
    // Work on a thread of its own, joined at the end (the preflight, the uninstall); threads that have ended are
    // joined and forgotten whenever another one starts.
    void spawn(std::function<void()> work);
    void prune_threads();
    // Work that may never end (reading a folder on a drive that hangs): a thread that is not joined; what it posts
    // after the window has gone is dropped (Mailbox).
    using Poster = std::function<void(std::function<void()>)>;
    void run_detached(std::function<void(const Poster& post)> work);
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
    std::string strip_from_;  // the item focused before the task strip's button (Up from it goes back there)
    void dialog_band();
    std::vector<ui::Hint> hints() const;

    // ---- screens (home.cpp)
    float share() const;
    bool tall() const;
    bool task_screen() const { return task_screen_; }
    void home(const ui::Box& crimson, const ui::Box& blue);
    ttt2::ui::SlabSpec update_slab() const;
    void update_list(const launcher::model::Action& a);
    void home_installed(const ui::Box& crimson, const ui::Box& blue);
    void home_first_run(const ui::Box& crimson, const ui::Box& blue);
    void home_unfinished(const ui::Box& crimson, const ui::Box& blue);
    void home_preflight(const ui::Box& crimson, const ui::Box& blue);
    void home_setup(const ui::Box& crimson, const ui::Box& blue); // Windows before Set Up Game
    void more_view();                                                 // Windows' More, drilled into from Home
    void more_describe();
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
        std::string key, title, game; // "t7" / "dlc" / "t8" / "dlc8", "Tekken 7 DLC", kTekken7
        const m::GameGroup* group = nullptr;
        bool dlc = false;
        std::vector<const m::FighterRow*> rows;
    };
    // A fighter in the task that runs: their turn (0 waiting, 1 now, 2 done), their share of the bar.
    struct FighterTask {
        bool in = false;
        int index = 0, count = 0, state = 0;
        double fraction = 0;
        std::string verb;      // "Adding", "Updating", "Removing" (in the launcher's language)
        bool removing = false;
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
    // The added fighters' portraits (their packs' art/portrait_1p.nut, game_art.h): read on a thread when the
    // importer's status or a finished task may have changed the packs; textures by display name.
    void update_portraits();
    ui::TextureId portrait_of(const std::string& display) const;
    void group_view(const std::string& group, const std::string& action_id, const std::vector<FighterGroup>& groups);
    void outfits_view();
    void add_all_view();
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
    void name_edit_view(const m::SettingsView& view, const ui::Box& blue);
    void name_press(const std::string& id, bool click);
    void name_edit_tick(double now);
    bool name_edit_sync(double now);
    bool name_edit_event(const ui::Event& e);
    void key_view(const m::SettingsView& view, const std::string& id);
    void folder_view(const m::SettingsView& view, const std::string& key);
    void settings_change(const std::string& id, int delta);
    bool settings_activate(const std::string& id, ttt2::ui::Device device);
    void key_capture_tick(double now);
    std::string folder_default(const std::string& key) const;
    void set_folder(const std::string& key, const std::string& value);
    // The launcher's own settings changed (Sounds, Reduce motion, Button prompts, Text size): applied and saved.
    void apply_launcher_settings();
    void apply_language(const std::string& setting);
    void apply_prompts(int prompts);

    // ---- the in-app browser (picker.cpp)
    void open_picker(bool folder, const std::string& purpose);
    // Lists `dir` off the UI thread (its answer posted back, an older one dropped). `fallbacks`: `dir` may not be
    // there (then its nearest parent that is, else the first of them). `refocus`: the same folder listed again (Show
    // hidden): its entries stay until the new list comes, and that entry keeps the focus.
    // (`dir` and `refocus` by value: they are often one of the picker's own entries, cleared on the way.)
    void picker_dir(fs::path dir, const std::vector<fs::path>& fallbacks = {}, fs::path refocus = {});
    struct Listing;
    void picker_listed(uint64_t generation, Listing listing);
    void picker_counted(uint64_t generation, std::vector<int> counts);
    void picker_toggle_hidden();
    void picker_screen(const ui::Box& crimson, const ui::Box& blue);
    void picker_rows();
    bool picker_activate(const std::string& id);
    // (By value: the callers pass the picker's own entry or folder, and choosing closes the picker.)
    void picker_chosen(fs::path path);
    void close_picker();

    // ---- tests (tests_hooks.cpp)
    void test_tick(double now);
    bool settled(double now) const;
    void shot(const std::string& name);
    void test_said(bool ok, const std::string& message);
    void test_watch_task();
    void test_audit(double now);    // (every frame of a test run: the Tag Split rule; "@audit failed ...")
    void test_capture(double now);  // (--frames)
    // --ui-smoke-test: before this frame is shown, what it is (video driver, renderer, two pixels) or why there is
    // none, written once; true once written (the run then ends).
    bool smoke(const std::string& error = {});
    bool smoke_done_ = false;
    // press:/pad:/steam:/click:/hover: test actions: input as the devices give it (through the router).
    bool test_input(const std::string& name, const std::vector<std::string>& args, double now);
    // A key the window takes before the router does (Ctrl+H in the browser): true when it was taken.
    bool shortcut(const ui::RawEvent& raw);

    // ---- Windows (windows_app.cpp): getting ready before the model (the first start's Python, --query state), the
    // state asked again after each task, Settings > Folders saved.
#ifdef _WIN32
    bool windows_ready();
    void ready_frame(double now);
    void ready_declare();
    void windows_state_again();
    void save_folders();
    std::unique_ptr<WindowsReady> ready_;
    std::optional<WindowsFiles> win_files_;
    std::unique_ptr<m::Job> state_job_, save_job_;
    std::string state_out_, save_out_;
    bool state_again_ = false;
    fs::path exe_; // the release .exe these files came from ("" a CMake build)
#endif
    void folders_from_state(const m::WindowsState& state);

    Options o_;
#ifndef _WIN32
    Places places_;
    std::optional<fs::path> appimage_;
#endif
    fs::path display_file_, keyboard_file_, owned_cache_;
    std::string banner_;

    // toolkit
    ui::Window window_;
    // The sounds' player (after window_: closed before SDL goes).
    std::unique_ptr<ui::Sounds> player_;
    fs::path player_folder_;
    bool player_folder_set_ = false;
    double play_heard_until_ = 0; // (SDL's clock, seconds) the Play sound still playing until then
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
    std::unique_ptr<m::Environment> env_;
    std::unique_ptr<m::Commands> commands_;
    std::unique_ptr<m::KeyFile> keys_;
#ifndef _WIN32
    LinuxUpdateFiles files_;
#endif
    std::unique_ptr<m::LauncherModel> model_;
    m::View view_;

    // posted work
    std::mutex posted_mutex_;
    std::deque<std::function<void()>> posted_;
    struct Worker {
        std::thread thread;
        std::shared_ptr<std::atomic<bool>> done;
    };
    std::vector<Worker> threads_;
    int working_ = 0; // threads not ended (preflight, uninstall)
    // Where detached threads post: closed (app = null) when the window goes.
    struct Mailbox {
        std::mutex mutex;
        App* app = nullptr;
    };
    std::shared_ptr<Mailbox> mailbox_;

    // what is shown
    Screen screen_ = Screen::kHome;
    std::map<int, std::string> saved_focus_;
    bool quit_ = false;
    bool first_ = true;
    double last_ = 0;
    // When frames are drawn (run()): only on change.
    static constexpr double kModelTick = .25;  // the model's timers are looked at this often without other news
    static constexpr double kSlowFrame = .5;   // at most this often while the game has the player or when hidden
    bool dirty_ = true;
    double last_drawn_ = -1e9, next_tick_ = 0;
    double ambient_base_ = 0, ambient_since_ = -1;  // the decorative loops' clock (ambient_clock)
    // the idle tests' hooks (test_idle_hooks)
    bool test_idle_read_ = false, test_pad_ = false, test_pad_open_ = false;
    SDL_JoystickID test_pad_id_ = 0;
    double test_blur_at_ = -1, presents_t0_ = 0;
    std::FILE* presents_ = nullptr;
    int last_dy_ = 0;
    std::string readout_key_ = "play";
    int pre_index_ = 0;           // the check the blue side shows (preflight)
    bool task_screen_ = false;    // the install / update / uninstall / launcher update fills Home
    m::TaskKind task_kind_ = m::TaskKind::kInstall;
    std::string task_title_;
    bool task_was_running_ = false;
    int updates_done_ = 0; // the model's updates_done() last heard (its chime)
    std::string home_primary_; // Home's slab's id last drawn (Play, Update, Install, ...)
    double update_scroll_since_ = -1; // when UPDATE's parts came on the blue side (scrolled to for a moment)
    size_t update_parts_seen_ = 0;
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
    struct PortraitArt {
        fs::path file;
        fs::file_time_type mtime{};
        std::uintmax_t size = 0;
        ui::TextureId texture = 0;
    };
    std::map<std::string, PortraitArt> portraits_;   // by display name
    std::string portraits_key_;                      // what they were read for
    int portraits_generation_ = 0;                   // + 1 at each task's end (packs made or removed)
    bool portraits_loading_ = false;
    ui::Readout fighters_ro_, settings_ro_;
    std::map<std::string, std::string> group_of_button_;  // a group action's id -> its group's key
    // Settings
    std::string settings_section_ = "game";    // game / display / keyboard / launcher / folders
    std::string settings_key_;                 // the row the blue side shows
    int settings_slide_ = 1;                   // the side the last value change came from
    double capture_since_ = 0;                 // choosing a key since
    std::optional<m::NameEditView> name_edit_shown_; // the name being typed as shown last (its readout fading out)
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
        uint64_t session = 0;     // this opening (its places' answer)
        uint64_t generation = 0;  // the listing asked for last (an older answer is dropped)
        bool places_ready = false;
        bool loading = false;     // dir's listing has not come yet
        bool counting = false;    // its folders' items are being counted
        fs::path refocus;         // the entry to focus again when the listing comes (Show hidden)
        // install_target(dir) (Linux, the install folder's browser): read with the listing, not every frame.
        bool target_known = false;
        std::optional<fs::path> target;
        std::string target_why;
        // The rows as declared (virtualised: only those in or near the view, the focused one's and the last).
        float last_scroll = 0;    // the crimson scroll the rows were last laid out with
        int declared = 0;         // rows declared in the last frame
    };
    std::optional<Picker> picker_;
    std::string picker_key_; // the browser's entry the blue side shows
    uint64_t picker_serial_ = 0;
    bool picker_hidden_ = false; // Show hidden (Ctrl+H): names starting with a dot listed too

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
