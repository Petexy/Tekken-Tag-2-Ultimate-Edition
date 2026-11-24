#include "app.h"

#include "preflight.h"
#include "rules.h"
#include "uninstall.h"
#ifdef _WIN32
#include "win32.h"
#endif

#define SDL_MAIN_NOIMPL
#include <SDL3/SDL_main.h>
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <unistd.h>
#endif

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace launcher::app {

using namespace ttt2::ui;
namespace c = theme::color;
namespace tx = theme::text;

// The loop's own event: posted work or a program's lines are waiting (ProcessHost's wake, threads, file dialogs).
static const Uint32 kWake = SDL_EVENT_USER;

// (Also windows_app.cpp's.)
void wake_loop() {
    SDL_Event e{};
    e.type = kWake;
    SDL_PushEvent(&e);
}

namespace {

bool full_kind(m::TaskKind k) {
    return k == m::TaskKind::kInstall || k == m::TaskKind::kUpdate || k == m::TaskKind::kUninstall ||
           k == m::TaskKind::kLauncherUpdate;
}

Box fitted(Box b, SeamFit f) {
    b.fit = f;
    return b;
}

} // namespace

App::App(Options options) : o_(std::move(options)) {
#ifndef _WIN32
    places_ = Places::from_environment();
#endif
}

App::~App() {
    for (std::thread& t : threads_)
        if (t.joinable()) t.join();
    model_.reset();
    starter_.reset();
    host_.reset();
}

void App::post(std::function<void()> work) {
    {
        std::lock_guard<std::mutex> lock(posted_mutex_);
        posted_.push_back(std::move(work));
    }
    wake_loop();
}

double App::now() const { return clock_.now(); }

bool App::open_window() {
    SDL_SetMainReady();
    WindowOptions wo;
    wo.title = "Ultimate Launcher";
    wo.app_id = TTT2_LAUNCHER_APP_ID;
    wo.version = TTT2_LAUNCHER_VERSION;
    const int w = o_.width > 0 ? o_.width : 1280, h = o_.height > 0 ? o_.height : 800;
    wo.size = {static_cast<float>(w), static_cast<float>(h)};
    wo.min_size = o_.testing ? Vec2{320, 240} : Vec2{960, 600};
    wo.offscreen = o_.testing && !o_.real_window;
    wo.forced_scale = o_.scale;
    if (!window_.open(wo)) return false;
    if (o_.testing && o_.scale > 0) SDL_SetWindowSize(window_.sdl(), w, h);
    window_.update_scale();
    textures_ = std::make_unique<TextureRegistry>(window_.renderer());
    text_ = std::make_unique<TextEngine>(*textures_);
    text_->set_system_fallback(!o_.testing);
    icons_ = std::make_unique<Icons>(*textures_);
    canvas_ = std::make_unique<Canvas>(window_.renderer(), *textures_);
    ui_ = std::make_unique<Ui>(*text_, *icons_);
    ui_->set_highlight(paint_focus_highlight);
    stage_ = std::make_unique<SplitStage>(*textures_, 20261124);
    stage_->set_frozen(o_.testing);
    wipe_ = std::make_unique<Wipe>(*textures_);
    if (const char* glyphs = std::getenv("TTT2_CONTROLLER")) {
        const std::string g = glyphs;
        forced_glyphs_ = g == "ps" || g == "playstation" || g == "xbox" || g == "nintendo" || g == "keyboard";
        if (g == "ps" || g == "playstation") router_.force_glyphs(true, Glyphs::PlayStation);
        else if (g == "xbox") router_.force_glyphs(true, Glyphs::Xbox);
        else if (g == "nintendo") router_.force_glyphs(true, Glyphs::Nintendo);
        else if (g == "keyboard") router_.force_glyphs(true, Glyphs::Keyboard);
    }
    return true;
}

void App::make_model() {
    if (!host_) host_ = std::make_unique<ProcessHost>(wake_loop);
    if (!starter_) starter_ = std::make_unique<backend::ProcessStarter>(*host_);
#ifdef _WIN32
    // (windows_ready() has the state: its folders and files.)
    const backend::WindowsStateAnswer& answer = ready_->answer();
    m::Facts facts = windows_start_facts(*win_files_, o_.game);
    backend::apply_windows_state(answer, facts);
    env_ = std::make_unique<WindowsEnvironment>(win_files_->build);
    auto commands = std::make_unique<m::WindowsCommands>();
    commands->stamp = [] {
        SYSTEMTIME t;
        GetLocalTime(&t);
        char b[40];
        std::snprintf(b, sizeof b, "%04u%02u%02u-%02u%02u%02u-%03u000", t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute,
                      t.wSecond, t.wMilliseconds);
        return std::string(b);
    };
    commands_ = std::move(commands);
    display_file_ = answer.display_file;
    keyboard_file_ = answer.keyboard_file;
    const auto data = facts.windows.folders.find("data");
    owned_cache_ = data == facts.windows.folders.end() || data->second.empty()
                       ? fs::path()
                       : fs::path(data->second) / "launcher" / "dlc-owned.json";
    exe_ = answer.exe;
    banner_ = std::string("ttt2-launcher ") + TTT2_LAUNCHER_VERSION + " (Windows): files " +
              win_files_->root.string() + ", python " + facts.python.string();
    folders_from_state(facts.windows);
#else
    env_ = std::make_unique<LinuxEnvironment>(places_);
    m::Facts facts = start_facts(places_, program_file().parent_path(), o_.game, &appimage_, &banner_);
    auto commands = std::make_unique<m::LinuxCommands>();
    commands->importer_env =
        m::importer_environment(facts.kit, [](const fs::path& p) { std::error_code ec; return fs::exists(p, ec); });
    commands->game_log = places_.game_log();
    commands_ = std::move(commands);
    display_file_ = places_.display();
    keyboard_file_ = places_.keyboard();
    owned_cache_ = places_.owned_cache();
#endif
    if (!owned_cache_.empty() && !facts.owned.has_answer) {
        if (const auto saved = saved_ownership(owned_cache_)) {
            facts.owned.answer = saved->owned;
            facts.owned.has_answer = true;
        }
    }
    std::fprintf(stderr, "%s\n", banner_.c_str());
    keys_ = std::make_unique<m::KeyFile>(keyboard_file_);
    m::LauncherModel::Parts parts{*commands_, *starter_, *env_, *keys_, nullptr, {}, {}, sdl_key_label, {}, {}};
    parts.display_file = display_file_;
    parts.key_label = sdl_key_label;
#ifdef _WIN32
    // (Before each task: Set Up Game's folders saved, then --query check.)
    parts.read_save = [](const std::string& out, std::string* error) -> std::optional<m::SetupProblem> {
        backend::QueryError e;
        const auto saved = backend::parse_save_settings(out, &e);
        if (!saved && error) *error = e.text;
        return saved ? std::optional<m::SetupProblem>(saved->problem) : std::nullopt;
    };
    parts.read_check = [](const std::string& out, std::string* error) {
        backend::QueryError e;
        auto problem = backend::parse_check(out, &e);
        if (!problem && error) *error = e.text;
        return problem;
    };
#endif
#ifndef _WIN32
    if (appimage_) {
        parts.update_files = &files_;
        parts.update.appimage = appimage_;
    }
    parts.update.pid = static_cast<int>(getpid());
#else
    parts.update.pid = static_cast<int>(GetCurrentProcessId());
#endif
    parts.update.version = TTT2_LAUNCHER_VERSION;
    if (const char* releases = std::getenv("TTT2_LAUNCHER_RELEASES"); releases && *releases) {
        parts.update.releases = releases;
        parts.update.custom_releases = true;
    }
    parts.update.user_agent = std::string("ttt2-launcher/") + TTT2_LAUNCHER_VERSION;
    model_ = std::make_unique<m::LauncherModel>(std::move(facts), parts);
    model_->set_monitors(sdl_monitors());
    // The launcher's own settings (launcher.ini beside display.ini).
    launcher_ini_ = parts.display_file.parent_path() / "launcher.ini";
    applied_ = read_launcher_ini(launcher_ini_);
    model_->set_launcher_settings(applied_);
    sounds_ = applied_.sounds;
    if (applied_.prompts > 0 && !forced_glyphs_) apply_prompts(applied_.prompts);
    if (applied_.text_size != 100) window_.set_user_text_scale(applied_.text_size / 100.f);
    // Where the install goes until another folder is chosen: ~/Games when there is one.
    const fs::path home = home_folder();
    std::error_code ec;
    slot_folder_ = (fs::is_directory(home / "Games", ec) ? home / "Games" : home) / launcher::kProgramName;
}

// Settings > Folders' values and defaults as the state says (Windows).
void App::folders_from_state(const m::WindowsState& state) {
    folder_defaults_ = state.folder_defaults;
    folders_changed_ = false;
}

// ---------------------------------------------------------------- the loop

int App::run() {
    if (!open_window()) return 1;
#ifdef _WIN32
    if (!windows_ready()) return exit_code_;
#endif
    make_model();
    const double t0 = now();
    model_->start(t0);
    handle(model_->take_effects());
    stage_->set_target(share(), tall(), 0);
    stage_->snap();
    last_ = t0;
    idle_since_ = t0;
    while (!quit_) {
        const double t = now();
        const bool busy = ui_->animating() || stage_->animating() || wipe_->active(t) || router_.holding() || first_ ||
                          readouts_animating(t);
        pump_input(t, !busy && !o_.testing);
        frame(now());
        if (o_.testing) test_tick(now());
    }
    model_.reset();
    return exit_code_;
}

void App::pump_input(double t, bool wait) {
    SDL_Event ev;
    bool got;
    if (wait) {
        double wake = std::min({stage_->next_ambient_time(), router_.holding() ? router_.next_repeat_time() : 1e18,
                                window_.next_pad_poll(), t + 0.25});
        if (toast_until_ > t) wake = std::min(wake, toast_until_);
        const int ms = static_cast<int>(std::clamp((wake - t) * 1000, 0.0, 250.0));
        got = SDL_WaitEventTimeout(&ev, ms);
    } else if (o_.testing) {
        // (Offscreen: no vsync to pace the loop.)
        got = SDL_WaitEventTimeout(&ev, 8);
    } else {
        got = SDL_PollEvent(&ev);
    }
    while (got) {
        if (ev.type == SDL_EVENT_QUIT || ev.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
            handle(model_->request_close(now()));
        } else if (ev.type == SDL_EVENT_RENDER_DEVICE_RESET) {
            textures_->device_reset();
        } else if (ev.type == SDL_EVENT_RENDER_TARGETS_RESET) {
            textures_->targets_reset();
        } else if (ev.type == SDL_EVENT_WINDOW_FOCUS_LOST) {
            router_.release_all();
            model_->deactivated();
        } else if (ev.type == SDL_EVENT_WINDOW_FOCUS_GAINED) {
            model_->activated(now());
        } else if (ev.type == SDL_EVENT_DISPLAY_ADDED || ev.type == SDL_EVENT_DISPLAY_REMOVED ||
                   ev.type == SDL_EVENT_DISPLAY_CURRENT_MODE_CHANGED) {
            model_->set_monitors(sdl_monitors());
        }
        RawEvent raw;
        if (!o_.testing && window_.translate(ev, raw, now()) && !raw.filtered) {
            router_.feed(raw);
            stage_->note_input(now());
        } else if (o_.testing) {
            window_.translate(ev, raw, now());
        }
        got = SDL_PollEvent(&ev);
    }
    // (Tests: their input, as the devices would give it.)
    for (auto it = test_raw_.begin(); it != test_raw_.end();) {
        if (it->first > now() + 1e-9) {
            ++it;
            continue;
        }
        RawEvent raw = it->second;
        raw.time = now();
        router_.feed(raw);
        stage_->note_input(now());
        it = test_raw_.erase(it);
    }
    window_.pads_tick(now(), model_->facts().game_running);
    stage_->set_ambient(window_.focused() && window_.visible());
    // Programs' lines and ends, posted work, later starts handed over.
    host_->pump();
    std::deque<std::function<void()>> work;
    {
        std::lock_guard<std::mutex> lock(posted_mutex_);
        work.swap(posted_);
    }
    for (auto& w : work) w();
    if (o_.instance) {
        for (const Forwarded& f : o_.instance->take()) {
            for (const std::string& a : f.args) {
                if (!a.empty() && a[0] != '-') model_->mutable_facts().chosen_game = normal(a);
            }
            SDL_RaiseWindow(window_.sdl());
        }
    }
}

void App::frame(double t) {
    model_->tick(t);
    handle(model_->take_effects());
    router_.tick(t);
    key_capture_tick(t);
    // The install, an update, the uninstall and the launcher's update fill Home while they run, and their end stays
    // there until it is closed.
    const m::TaskRunner& runner = model_->task();
    const bool running = runner.running();
    if (running && !task_was_running_ && full_kind(runner.spec().kind)) {
        task_kind_ = runner.spec().kind;
        task_title_ = runner.spec().title;
        if (!task_screen_) {
            task_screen_ = true;
            if (picker_) picker_.reset();
            if (screen_ != Screen::kHome) go(Screen::kHome);
            else wipe_->start(t, 1, model_->launcher_settings().reduce_motion);
            ui_->focus("task", true);
        }
    }
    if (task_was_running_ && !running && !runner.last().cancelled)
        cue(runner.last().ok ? ttt2::app::Cue::TaskDone : ttt2::app::Cue::TaskFailed);
#ifdef _WIN32
    // (What a task changed: the install, the build, the logs. Asked again after each one, C8.)
    if (task_was_running_ && !running) windows_state_again();
#endif
    task_was_running_ = running;
    sync_log();
    view_ = model_->view();
    if (drill_ && (drill_->screen != screen_ || picker_ || view_.dialog)) drill_.reset();

    // The seam first: this frame is laid out for the split as it is DRAWN now (springing), never for a target or
    // an old split (FEEDBACK F1). It leans toward the half that had the focus.
    {
        const Rect fr = ui_->rect(ui_->focused());
        const int side = view_.dialog || fr.empty()                                   ? 0
                         : fr.center().x > stage_->seam_now().x_at(fr.center().y) ? 1
                                                                                  : -1;
        stage_->set_target(share(), tall(), drilled() ? 1 : side);
        stage_->set_locked(drilled() ? -1 : 0);
        if (first_) stage_->snap();
        stage_->update(t, static_cast<float>(std::clamp(t - last_, 0.0, .25)), window_.points(),
                       model_->launcher_settings().reduce_motion);
        last_ = t;
    }

    FrameInput in;
    in.size = window_.points();
    in.scale = window_.scale();
    in.now = t;
    in.actions = router_.take_actions();
    in.mouse = router_.take_mouse();
    in.reduced_motion = model_->launcher_settings().reduce_motion;
    in.glyphs = router_.glyphs();
    for (const ActionEvent& a : in.actions)
        if (a.action == ttt2::ui::Action::Up || a.action == ttt2::ui::Action::Down)
            last_dy_ = a.action == ttt2::ui::Action::Up ? -1 : 1;
    ui_->begin(in);
    declare();
    ui_->end();
    const std::vector<Event> events = ui_->take_events();
    painted_focus_ = ui_->focused();
    painted_highlight_ = ui_->highlight_rect();
    painted_focus_rect_ = ui_->focus_rect();
    if (drilled()) {
        // (Its blue actions gone - nothing left to reach there: back to the opener.)
        const std::vector<std::string> ids = ui_->focusable_ids();
        if (std::find(ids.begin(), ids.end(), ui_->focused()) == ids.end()) drill_out();
    }
    if (o_.testing) test_audit(t);
    window_.set_drag_area({0, 0, in.size.x, theme::kTopBand},
                          {ui_->rect("tabs"), ui_->rect("sound"), ui_->rect("quit"), ui_->rect("frame")});

    const Vec2 px = window_.pixels();
    canvas_->begin(window_.scale(), static_cast<int>(px.x), static_cast<int>(px.y));
    SDL_SetRenderDrawColor(window_.renderer(), 3, 3, 6, 255);
    SDL_RenderClear(window_.renderer());
    wipe_->set_area(theme::kTopBand, in.size.y - theme::kBottomBand);
    wipe_->begin_frame(*canvas_, in.size);
    stage_->draw(*canvas_, t);
    const char* mark = picker_ ? "Files" : task_screen_ && screen_ == Screen::kHome ? "Kit"
                       : screen_ == Screen::kFighters                               ? "Roster"
                       : screen_ == Screen::kSettings                               ? "Setup"
                                                                                    : "Tag";
    watermark(*canvas_, *text_, mark, {in.size.x + 30, in.size.y - theme::kBottomBand + 60});
    ui_->paint(*canvas_);
    wipe_->end_frame(*canvas_, t);
    canvas_->flush();
    if (!o_.testing || o_.real_window) {
        SDL_RenderPresent(window_.renderer());
        if (first_) window_.show();
    }
    first_ = false;
    on_events(events);
}

void App::sync_log() {
    const std::vector<std::string>& lines = model_->task().log();
    const auto add = [&](const std::string& l) {
        if (l.starts_with("@progress")) return;
        if (l.starts_with("@step ")) {
            const size_t sp = l.find(' ', 6);
            log_.append(sp == std::string::npos ? l.substr(6) : l.substr(sp + 1), LogKind::Status);
        } else if (l.starts_with("@error ")) {
            log_.append(l.substr(7), LogKind::Error);
        } else if (l.starts_with("@")) {
            return;
        } else {
            log_.append(l, l.find("error") != std::string::npos ? LogKind::Error : LogKind::Normal);
        }
    };
    const bool same = !lines.empty() && lines.size() >= log_seen_ && log_seen_ > 0 && lines[log_seen_ - 1] == log_last_;
    if (lines.size() == log_seen_ && (lines.empty() || lines.back() == log_last_)) return;
    if (!same) {
        log_.clear();
        log_seen_ = 0;
    }
    for (size_t i = log_seen_; i < lines.size(); ++i) add(lines[i]);
    log_seen_ = lines.size();
    log_last_ = lines.empty() ? std::string() : lines.back();
}

void App::declare() {
    Ui& ui = *ui_;
    const Vec2 size = ui.frame().size;
    top_band();
    const float sh = stage_->share_now();
    const Seam seam = stage_->layout_seam(sh);
    const Rect cr = stage_->crimson_area(sh), bl = stage_->blue_area(sh);
    Box crimson;
    crimson.seam = seam;
    crimson.scroll = true;
    crimson.margin = {cr.x - 16, cr.y, 0, 0};
    crimson.w = Size::fixed(cr.w + 16 + 22);
    crimson.h = Size::fixed(std::max(60.f, cr.h + 14));
    crimson.pad = {16, 0, 22, 8};
    Box blue;
    blue.seam = seam;
    blue.scroll = true;
    blue.margin = {bl.x - 16, bl.y, 0, 0};
    blue.w = Size::fixed(bl.w + 16 + 16);
    blue.h = Size::fixed(std::max(60.f, bl.h + 14));
    blue.pad = {16, 0, 16, 8};
    blue.mirror = true;  // FEEDBACK F2: the blue half's straight edge is its right one
    crimson.locked = drilled();
    if (wipe_->active(ui.now())) {
        const Vec2 d = wipe_->new_offset(ui.now());
        crimson.shift = d;
        blue.shift = d;
    }
    // (The root is a Stack: each half places itself by its margins.)
    screen_actions_.clear();
    if (picker_) picker_screen(crimson, blue);
    else if (screen_ == Screen::kHome) home(crimson, blue);
    else if (screen_ == Screen::kFighters) fighters(crimson, blue);
    else settings(crimson, blue);
    task_strip();
    if (view_.dialog) dialog_band();
    bottom_band();
    (void)size;
}

// ---------------------------------------------------------------- bands

void App::top_band() {
    Ui& ui = *ui_;
    const Vec2 size = ui.frame().size;
    Box top;
    top.layout = Layout::Row;
    top.align = Align::Center;
    top.w = Size::fixed(size.x);
    top.h = Size::fixed(theme::kTopBand);
    top.pad = {30, 0, 22, 0};
    auto g = ui.open("top", top);
    brand(ui, "brand", "Ultimate", "Launcher");
    int to_update = 0;
    if (const auto& s = model_->facts().status) {
        for (const Fighter& f : s->fighters) to_update += f.added() && f.update;
    }
    const Tab tabs[] = {{"tab:home", "Home", ""},
                        {"tab:fighters", "Fighters", to_update ? std::to_string(to_update) : ""},
                        {"tab:settings", "Settings", ""}};
    tab_bar(ui, "tabs", tabs, static_cast<int>(screen_));
    ui.leaf("top/space", Box{.w = Size::grow()}, {}, {});
    TextSpec version{std::string("Launcher ") + TTT2_LAUNCHER_VERSION, tx::kVersion, c::kFaint};
    version.drop = true;
    text(ui, "version", version, Box{.margin = {0, 0, 16, 0}, .shrink_order = 3});
    icon_button(ui, "sound",
                {sounds_ ? "stroke:sound-on" : "stroke:sound-off", sounds_ ? "Sound on" : "Sound off", sounds_},
                Box{.margin = {0, 0, 10, 0}});
    icon_button(ui, "quit", {"stroke:power", "Quit"});
    caption_buttons(ui, "frame", window_.can_minimise(), window_.can_toggle_fullscreen(), window_.fullscreen(), false,
                    Box{.margin = {10, 0, 0, 0}});
}

std::string App::focused_label() const {
    const std::string& f = ui_->focused();
    if (const m::Action* a = action(f)) return a->label.empty() ? a->describe.title : a->label;
    return {};
}

std::vector<Hint> App::hints() const {
    std::vector<Hint> h;
    const std::string& f = ui_->focused();
    h.push_back({Prompt::Move, "Move"});
    auto accept = [&](std::string label) {
        // ("Install…" opens something first: the prompt says what, without the dots.)
        if (label.ends_with("…")) label.resize(label.size() - std::string("…").size());
        if (!label.empty()) h.push_back({Prompt::Accept, label});
    };
    if (view_.dialog) {
        const m::Action* a = nullptr;
        for (const m::Action& b : view_.dialog->buttons)
            if (b.id == f) a = &b;
        for (const m::Line& l : view_.dialog->lines)
            for (const m::Action& b : l.actions)
                if (b.id == f) a = &b;
        if (a) accept(a->kind == m::ActionKind::kCheck ? "Tick" : a->label);
        for (const m::Action& b : view_.dialog->buttons)
            if (b.id == view_.dialog->cancel && b.id != f) h.push_back({Prompt::Back, b.label});
        return h;
    }
    if (picker_) {
        if (f.starts_with("pp:") || f == "pk/here") accept(f == "pk/here" && picker_->folder ? "Choose" : "Open");
        else if (f.starts_with("pe:")) {
            const size_t i = std::strtoul(f.c_str() + 3, nullptr, 10);
            if (i < picker_->entries.size()) {
                const Entry& e = picker_->entries[i];
                accept(e.kind != Entry::Kind::kFile ? "Open" : e.wua ? "Choose" : "");
            }
        } else if (f == "pk/choose" || f == "pk/choose-here") accept("Choose");
        else if (f == "pk/system") accept("Open");
        h.push_back({Prompt::Back, "Back"});
        return h;
    }
    const bool disabled = [&] {
        const m::Action* a = action(f);
        return a && !a->enabled;
    }();
    if (screen_ == Screen::kHome && task_screen_) {
        // (Each prompt once: the focused button's as Enter, the others by their own keys. Stopping: none.)
        const bool running = model_->task().running();
        const bool can_cancel = running && view_.task.button.enabled && model_->task().cancellable();
        std::string back = can_cancel ? "Cancel" : running ? "" : "Close";
        if (f == "task" && running) {
            if (can_cancel) accept("Cancel");
            back.clear();
        } else if (f == "task/play") accept("Play");
        else if (f == "task/again") accept("Try Again");
        else if (f == "task/close") {
            accept("Close");
            back.clear();
        }
        const std::string details = view_.task.details.checked ? "Hide Details" : "Details";
        if (f == "details") accept(details);
        if (!back.empty()) h.push_back({Prompt::Back, back});
        if (f != "details") h.push_back({Prompt::Context2, details});
        h.push_back({Prompt::Tabs, "Tabs"});
        return h;
    }
    if (drilled()) {
        if (!disabled) accept(focused_label().empty() && f.starts_with("copy:") ? "Copy" : focused_label());
        h.push_back({Prompt::Back, "Back"});
        h.push_back({Prompt::Tabs, "Tabs"});
        return h;
    }
    if (screen_ == Screen::kSettings && !drilled()) {
        if (model_->keys().picking() >= 0) {
            h.clear();
            h.push_back({Prompt::AnyKey, "Press a key"});
            h.push_back({Prompt::Back, "Keep"});
            return h;
        }
        const m::Action* a = action(f);
        if (a && (a->kind == m::ActionKind::kSwitch || a->kind == m::ActionKind::kChoice)) {
            if (a->enabled) {
                h.push_back({Prompt::Change, "Change"});
                accept(a->kind == m::ActionKind::kSwitch ? "Switch" : "Next");
            }
        } else if (f.starts_with("key:")) {
            accept("Change Key");
        } else if (f.starts_with("fold:")) {
            accept("Options");
        } else if (a && a->enabled) {
            accept(a->label);
        }
        if (settings_sections().size() > 1) h.push_back({Prompt::Sections, "Section"});
        h.push_back({Prompt::Back, "Home"});
        h.push_back({Prompt::Tabs, "Tabs"});
        return h;
    }
    if (screen_ == Screen::kFighters) {
        if (f.starts_with("tile:")) {
            accept("Options");
            if (const m::Action* o = action("outfits:" + f.substr(5)); o && o->enabled)
                h.push_back({Prompt::Context1, "Outfits"});
        } else if (f == "fx:needs" || f == "fx:early") {
            accept("Options");
        } else if (const m::Action* a = action(f); a && a->enabled) {
            accept(a->kind == m::ActionKind::kCheck ? (a->checked ? "Untick" : "Tick") : a->label);
        }
        h.push_back({Prompt::Back, "Home"});
        h.push_back({Prompt::Tabs, "Tabs"});
        return h;
    }
    if (!disabled) {
        if (f == "fighters" || f == "settings") accept("Open");
        else if (f == "slot:game" || f == "slot:folder") accept("Choose");
        else if (f.starts_with("check:")) accept(check_has_copy(f) ? "Commands" : "");
        else accept(focused_label());
    }
    if (screen_ != Screen::kHome) h.push_back({Prompt::Back, "Home"});
    else if (view_.game.state == m::GameState::kChecking || view_.game.state == m::GameState::kCannotInstall)
        h.push_back({Prompt::Back, "Cancel"});
    h.push_back({Prompt::Tabs, "Tabs"});
    return h;
}

void App::bottom_band() {
    Ui& ui = *ui_;
    const Vec2 size = ui.frame().size;
    Box bottom;
    bottom.layout = Layout::Row;
    bottom.align = Align::Center;
    bottom.w = Size::fixed(size.x);
    bottom.h = Size::fixed(theme::kBottomBand);
    bottom.margin = {0, size.y - theme::kBottomBand, 0, 0};
    bottom.pad = {34, 0, 26, 0};
    auto g = ui.open("bottom", bottom);
    const std::vector<Hint> hs = hints();
    hint_bar(ui, "hints", hs);
}

// The task strip: a task that does not fill the screen (adding characters, shaders before Play, numpy and Pillow),
// a refusal, a note (a disabled item's why).
void App::task_strip() {
    Ui& ui = *ui_;
    const Vec2 size = ui.frame().size;
    const double t = ui.now();
    const bool toast = toast_until_ > t;
    const m::TaskView& tv = view_.task;
    const bool task = tv.shown && !(task_screen_ && screen_ == Screen::kHome);
    if (!toast && !task) return;
    const float h = 62;
    Box band;
    band.layout = Layout::Row;
    band.align = Align::Center;
    band.w = Size::fixed(size.x);
    band.h = Size::fixed(h);
    band.margin = {0, size.y - theme::kBottomBand - h, 0, 0};
    band.pad = {34, 0, 26, 0};
    band.gap = 18;
    auto g = ui.open("strip", band, [](PaintContext& ctx) {
        ctx.canvas.fill_rect(ctx.rect, rgba(7, 8, 13, .94f));
        ctx.canvas.fill_rect({ctx.rect.x, ctx.rect.y, ctx.rect.w, 1}, rgba(255, 255, 255, .1f));
    });
    {
        auto col = ui.open("strip/words", Box{.w = Size::grow(), .gap = 3});
        const std::string title = toast ? toast_title_ : tv.title;
        const std::string detail = toast ? toast_text_ : tv.detail;
        const Color tc = toast ? (toast_bad_ ? c::kBad : c::kText) : tv.failed ? c::kBad : c::kText;
        text(ui, "strip/title", TextSpec{title, tx::kStepName, tc});
        TextSpec d{detail, tx::kParaSmall, c::kDim};
        text(ui, "strip/detail", d);
    }
    if (!toast && tv.running) {
        progress_bar(ui, "strip/bar", static_cast<float>(tv.fraction), Tone::Blue,
                     Box{.w = Size::fixed(std::max(120.f, size.x * .36f))});
        if (tv.fraction >= 0) {
            text(ui, "strip/pct",
                 TextSpec{std::to_string(static_cast<int>(std::lround(tv.fraction * 100))) + "%",
                          TextStyle{theme::Font::DisplayBlackItalic, 28, 0, false, 1}, c::kText});
        }
    }
    if (!toast && !tv.button.label.empty()) {
        ButtonSpec b;
        b.label = tv.button.label;
        b.size = ButtonSize::Tiny;
        b.kind = tv.running ? ButtonKind::Danger : ButtonKind::Ghost;
        b.disabled = !tv.button.enabled;
        Focus f;
        f.nav = false;
        button(ui, "strip/task", b, f);
    }
}

void App::dialog_band() {
    Ui& ui = *ui_;
    const m::Dialog& d = *view_.dialog;
    const Vec2 size = ui.frame().size;
    const float yc = (theme::kTopBand + size.y - theme::kBottomBand) / 2;
    const bool uninstall = d.id == "uninstall";
    const float height = uninstall ? 360 : 300;
    const BandLayout L = band_layout(size, std::round(yc - height / 2), height);
    auto g = ttt2::ui::dialog_band(ui, "dlg", L);
    const char* label = d.id == "uninstall"       ? "Uninstall"
                        : d.id == "stop-and-quit" ? "Quit"
                        : d.id == "remove-all"    ? "Remove all"
                        : d.id == "setup"         ? "Set Up"
                                                  : "Message";
    {
        auto cg = ui.open("dlg/crimson", L.crimson);
        section_label(ui, "dlg/label", label, Half::Crimson, {}, fitted({}, SeamFit::CrimsonRect));
        text(ui, "dlg/title", TextSpec{.text = d.title, .style = tx::kDialogTitle, .wrap = true},
             fitted(Box{.margin = {0, 0, 0, d.id == "stop-and-quit" ? 6.f : 14.f}}, SeamFit::CrimsonRect));
        if (d.id == "stop-and-quit")
            text(ui, "dlg/sub", TextSpec{"The task is not finished.", tx::kParaSmall, c::kRedDim},
                 fitted(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        for (const m::Line& l : d.lines) {
            for (const m::Action& a : l.actions) {
                if (a.kind != m::ActionKind::kCheck) continue;
                Focus f;
                option_row(ui, a.id, {a.label, a.checked, !a.enabled}, f, fitted({}, SeamFit::CrimsonSkewed));
            }
        }
        auto bg = ui.open("dlg/btns", fitted(Box{.layout = Layout::Row, .margin = {0, 6, 0, 0}, .gap = 12,
                                                 .wrap = true},
                                             SeamFit::CrimsonRect));
        for (const m::Action& a : d.buttons) {
            ButtonSpec b;
            b.label = a.label;
            b.half = Half::Crimson;
            b.disabled = !a.enabled;
            if (a.id == d.cancel) b.prompt = Prompt::Back;
            if (a.destructive) b.kind = ButtonKind::Danger;
            else if (a.primary) b.kind = ButtonKind::Primary;
            Focus f;
            f.is_default = a.id == d.default_id;
            button(ui, a.id, b, f);
        }
    }
    auto bg = ui.open("dlg/blue", L.blue);
    section_label(ui, "dlg/what-label", "What happens", Half::Blue, {}, fitted({}, SeamFit::BlueRect));
    std::vector<WhatLine> what;
    if (uninstall) {
        bool saves = false, chars = false;
        for (const m::Line& l : d.lines)
            for (const m::Action& a : l.actions) {
                if (a.id == "uninstall-saves") saves = a.checked;
                if (a.id == "uninstall-characters") chars = a.checked;
            }
        const m::Facts& f = model_->facts();
        what.push_back({"Deleted",
                        WhatTone::Removed,
                        {{"The game, its program and its menu entry, from "}, {m::shown_path(f.install.folder), true}}});
        what.push_back({"Stays", WhatTone::Kept, {{"Anything else in that folder."}}});
        what.push_back({"Saves",
                        saves ? WhatTone::Removed : WhatTone::Kept,
                        {{saves ? "Deleted too: " : "Kept: "}, {m::shown_path(f.saves), true}}});
        what.push_back(
            {"Fighters",
             chars ? WhatTone::Removed : WhatTone::Kept,
             {{chars ? "The added characters and what was saved from Tekken 7 and Tekken 8 are deleted too."
                     : "The added characters are kept, for when it is installed again."}}});
    } else if (d.id == "stop-and-quit") {
        const std::string title = model_->task().spec().title;
        const double done = task_fraction();
        what.push_back({"Task",
                        WhatTone::Neutral,
                        {{done >= 0 ? title + ": " + std::to_string(static_cast<int>(done * 100)) + "% done."
                                    : title + " is not finished."}}});
        what.push_back({"Stop", WhatTone::Removed, {{"Stop and Quit stops it, then the launcher closes."}}});
        what.push_back({"Keep", WhatTone::Kept, {{"Keep Running goes back: the task goes on."}}});
    } else if (d.id == "remove-all") {
        // (Remove All exists only while that game is gone: its characters cannot be made again until it is back.)
        std::vector<std::string> shown;
        const std::string game = d.title.find("Tekken 8") != std::string::npos ? kTekken8 : kTekken7;
        for (const std::string& n : m::to_remove_all(model_->facts(), game))
            shown.push_back(m::display_name(model_->facts(), n));
        what.push_back({"Removed", WhatTone::Removed, {{m::joined_most(shown, 8) + ": their packs, from the game."}}});
        what.push_back({"Stays", WhatTone::Kept, {{"The game's own fighters and the other game's characters."}}});
        what.push_back({"Later", WhatTone::Neutral, {{d.text}}});
    } else if (d.id == "setup") {
        // (Windows: the archive and the folder just chosen, and what the setup does with them.)
        const auto& folders = model_->facts().windows.folders;
        const auto folder = [&](const char* key) {
            const auto it = folders.find(key);
            return it == folders.end() ? std::string() : it->second;
        };
        what.push_back({"Archive", WhatTone::Kept, {{"Read, never changed: "}, {m::shown_path(folder("source")), true}}});
        what.push_back({"Folder", WhatTone::Neutral, {{"The game goes into "}, {m::shown_path(folder("install")), true}}});
        what.push_back({"Needs",
                        WhatTone::Neutral,
                        {{"Internet for its tools (downloaded once), at least 30 GB free, and a while."}}});
    } else {
        what.push_back({"", WhatTone::Neutral, {{d.text}}});
        for (const m::Line& l : d.lines)
            if (l.actions.empty() && !l.text.empty()) what.push_back({"", WhatTone::Neutral, {{l.text, true}}});
    }
    what_list(ui, "dlg/what", what, fitted({}, SeamFit::BlueRect));
}

// ---------------------------------------------------------------- events

void App::go(Screen to) {
    if (to == screen_) return;
    cue(ttt2::app::Cue::TabSwitch);
    // (A drill-in ends with its screen; the screen keeps the opener as its focus.)
    saved_focus_[static_cast<int>(screen_)] = drilled() ? drill_->opener : ui_->focused();
    drill_.reset();
    if (model_->keys().picking() >= 0) model_->cancel_key();
    router_.end_capture();
    const int dir = static_cast<int>(to) > static_cast<int>(screen_) ? 1 : -1;
    // The model's page follows (Settings reads display.ini and the keys when opened).
    if (to == Screen::kSettings && model_->page() != m::Page::kSettings) handle(model_->activate("settings", now()));
    if (to != Screen::kSettings && model_->page() == m::Page::kSettings) handle(model_->activate("back", now()));
    screen_ = to;
    wipe_->start(now(), dir, model_->launcher_settings().reduce_motion);
    stage_->note_input(now());
    const auto it = saved_focus_.find(static_cast<int>(to));
    ui_->focus(it != saved_focus_.end() ? it->second : std::string(), true);
}

void App::apply_prompts(int prompts) {
    static const Glyphs kGlyphs[] = {Glyphs::Keyboard, Glyphs::Keyboard, Glyphs::Xbox, Glyphs::PlayStation,
                                     Glyphs::Nintendo};
    router_.force_glyphs(prompts > 0, kGlyphs[std::clamp(prompts, 0, 4)]);
}

void App::apply_launcher_settings() {
    const m::LauncherSettings s = model_->launcher_settings();
    sounds_ = s.sounds;
    if (s == applied_) return;
    if (s.prompts != applied_.prompts && !forced_glyphs_) apply_prompts(s.prompts);
    if (s.text_size != applied_.text_size) window_.set_user_text_scale(s.text_size / 100.f);
    applied_ = s;
    std::string error;
    if (!write_launcher_ini(launcher_ini_, s, &error)) toast("Not saved", error);
}

void App::cue(ttt2::app::Cue c) {
    if (o_.trace_cues) std::fprintf(stderr, "@cue %s\n", ttt2::app::cue_name(c));
    if (sounds_ && sound_) sound_(c);
}

bool App::drilled() const { return drill_ && drill_->screen == screen_ && !picker_ && !view_.dialog; }

void App::drill_in(const std::string& opener, const std::string& target) {
    drill_ = Drill{screen_, opener, target};
    ui_->focus(target);
    stage_->note_input(now());
    cue(ttt2::app::Cue::DrillIn);
}

void App::drill_out(const std::string& to) {
    if (!drill_) return;
    const std::string opener = drill_->opener;
    drill_.reset();
    ui_->focus(to.empty() ? opener : to);
    stage_->note_input(now());
    cue(ttt2::app::Cue::DrillOut);
}

void App::toast(const std::string& title, const std::string& text, bool bad) {
    toast_title_ = title;
    toast_text_ = text;
    toast_bad_ = bad;
    toast_until_ = now() + 4;
}

const m::Action* App::action(const std::string& id) const {
    for (const m::Action& a : view_.game.actions)
        if (a.id == id) return &a;
    for (const m::Line& l : view_.game.body)
        for (const m::Action& a : l.actions)
            if (a.id == id) return &a;
    if (view_.notice.shown) {
        if (view_.notice.update.id == id) return &view_.notice.update;
        if (view_.notice.page && view_.notice.page->id == id) return &*view_.notice.page;
    }
    if (const auto it = screen_actions_.find(id); it != screen_actions_.end()) return &it->second;
    return nullptr;
}

void App::on_events(const std::vector<Event>& events) {
    for (const Event& e : events) {
        switch (e.kind) {
        case EventKind::TabNext:
        case EventKind::TabPrev:
            if (view_.dialog || picker_) break;
            go(static_cast<Screen>((static_cast<int>(screen_) + (e.kind == EventKind::TabNext ? 1 : 2)) % 3));
            break;
        case EventKind::Back:
            if (view_.dialog) {
                cue(ttt2::app::Cue::Back);
                activate(view_.dialog->cancel);
            } else if (drilled()) {
                drill_out();
            } else if (picker_) {
                cue(ttt2::app::Cue::Back);
                close_picker();
            } else if (screen_ != Screen::kHome) {
                go(Screen::kHome);
            } else if (task_screen_) {
                if (model_->task().running()) {
                    if (model_->task().cancellable()) {
                        cue(ttt2::app::Cue::Back);
                        activate("task");
                    }
                } else {
                    cue(ttt2::app::Cue::Back);
                    activate("task/close");
                }
            } else if (view_.game.state == m::GameState::kChecking ||
                       view_.game.state == m::GameState::kCannotInstall) {
                cue(ttt2::app::Cue::Back);
                activate("preflight-cancel");
            }
            break;
        case EventKind::Context2:
            if (task_screen_ && screen_ == Screen::kHome && !view_.dialog && !picker_) activate("details");
            break;
        case EventKind::Context1:
            // (Fighters: F / X ticks the focused fighter's outfits.)
            if (screen_ == Screen::kFighters && !view_.dialog && e.id.starts_with("tile:")) {
                const std::string id = "outfits:" + e.id.substr(5);
                if (const m::Action* o = action(id); o && o->enabled) {
                    activate(id);
                    cue(ttt2::app::Cue::Toggle);
                }
            }
            break;
        case EventKind::ClickOutside:
            if (view_.dialog) {
                cue(ttt2::app::Cue::Back);
                activate(view_.dialog->cancel);
            }
            break;
        case EventKind::Unlock:
            // (A click on the locked crimson half: back, onto the item clicked if there was one.)
            if (drilled()) drill_out(e.delta ? e.id : std::string());
            break;
        case EventKind::Fullscreen: window_.toggle_fullscreen(); break;
        case EventKind::FocusMoved: cue(ttt2::app::Cue::Move); break;
        case EventKind::Change:
            if (screen_ == Screen::kSettings && !view_.dialog && !picker_) settings_change(e.id, e.delta);
            else cue(ttt2::app::Cue::Toggle);
            break;
        case EventKind::SectionPrev:
        case EventKind::SectionNext:
            if (screen_ == Screen::kSettings && !view_.dialog && !picker_ && !drilled())
                settings_switch(e.kind == EventKind::SectionNext ? 1 : -1);
            break;
        case EventKind::Refused:
            cue(ttt2::app::Cue::Refuse);
            refused(e.id);
            break;
        case EventKind::Activate: {
            using ttt2::app::Cue;
            const m::Action* a = action(e.id);
            const bool tab = e.id.starts_with("tab:") || e.id == "fighters" || e.id == "settings" || e.id == "ph/home";
            if (e.id == "play" || e.id == "task/play") cue(Cue::Play);
            else if (e.id == "sound" || (a && a->kind == m::ActionKind::kCheck)) {
                // (Sound: its cue after the switch, so turning it on is heard.)
            } else if (!tab && !(e.id.starts_with("check:") && check_has_copy(e.id)) &&
                       !(a && (a->kind == m::ActionKind::kSwitch || a->kind == m::ActionKind::kChoice)) &&
                       !e.id.starts_with("sec:") && !e.id.starts_with("tile:") && !e.id.starts_with("fold:"))
                cue(Cue::Accept);
            activate(e.id, e.device);
            if (e.id == "sound" || (a && (a->kind == m::ActionKind::kCheck || a->kind == m::ActionKind::kSwitch ||
                                          a->kind == m::ActionKind::kChoice)))
                cue(Cue::Toggle);
            break;
        }
        default: break;
        }
    }
}

void App::refused(const std::string& id) {
    if (const m::Action* a = action(id); a && !a->why.empty()) {
        toast(a->describe.title.empty() ? a->label : a->describe.title, a->why);
        return;
    }
    if (id == "pk/choose") toast("Not a .wua", "Choose the game's .wua archive.");
}

void App::activate(const std::string& id, ttt2::ui::Device device) {
    const double t = now();
    stage_->note_input(t);
    if (picker_ && picker_activate(id)) return;
    if (screen_ == Screen::kSettings && !view_.dialog && settings_activate(id, device)) return;
    if (id == "tab:home" || id == "ph/home") return go(Screen::kHome);
    if (id == "tab:fighters" || id == "fighters") return go(Screen::kFighters);
    if (id == "tab:settings") return go(Screen::kSettings);
    if (id == "settings" && !view_.dialog) return go(Screen::kSettings);
    if (id == "sound") {
        m::LauncherSettings s = model_->launcher_settings();
        s.sounds = !s.sounds;
        model_->set_launcher_settings(s);
        apply_launcher_settings();
        return;
    }
    if (id == "quit" || id == "frame/close") return handle(model_->request_close(t));
    if (id == "frame/min") return window_.minimise();
    if (id == "frame/full") return window_.toggle_fullscreen();
    if (id == "slot:game") return open_picker(false, "game");
    if (id == "slot:folder") return open_picker(true, "folder");
    if (id == "strip/task") return handle(model_->activate("task", t));
    if (screen_ == Screen::kFighters && fighters_activate(id)) return;
    if (id.starts_with("check:")) {
        // A check with commands to copy: they are on the blue side (FEEDBACK F4: drill in, crimson locked).
        if (const std::string copy = check_copy(id); !copy.empty()) drill_in(id, copy);
        return;
    }
    if (id == "task/close") {
        task_screen_ = false;
        if (!model_->task().running() && view_.task.shown) handle(model_->activate("task", t));
        wipe_->start(t, -1, model_->launcher_settings().reduce_motion);
        ui_->focus("", true);
        return;
    }
    if (id == "task/play") {
        activate("task/close");
        return activate("play");
    }
    if (id == "task/again") {
        const m::TaskKind k = task_kind_;
        task_screen_ = false;
        if (!model_->task().running() && view_.task.shown) handle(model_->activate("task", t));
        if (k == m::TaskKind::kInstall) {
            if (model_->facts().install.state == InstallState::kUnfinished) return activate("resume");
            return activate("install");
        }
        if (k == m::TaskKind::kUpdate) return activate("update");
        if (k == m::TaskKind::kLauncherUpdate) return activate("notice-update");
        return;
    }
    handle(model_->activate(id, t));
}

void App::answer_game(const fs::path& game) {
    const std::string purpose = pending_choose_;
    std::vector<m::Effect> fx = model_->chosen_game(game, now());
    pending_choose_ = purpose; // (kChooseFolder after it: resume goes back into its folder)
    handle(std::move(fx));
    pending_choose_.clear();
}

void App::handle(std::vector<m::Effect> effects) {
    for (m::Effect& e : effects) {
        switch (e.kind) {
        case m::Effect::Kind::kChooseGame: {
            pending_choose_ = e.text;
            const fs::path chosen = model_->facts().chosen_game;
            std::error_code ec;
            if (e.text != "resume" && !chosen.empty() && fs::is_regular_file(chosen, ec)) {
                answer_game(chosen);
            } else {
                open_picker(false, "game");
                if (picker_) picker_->then_answer = true;
            }
            break;
        }
        case m::Effect::Kind::kChooseFolder: {
            // (Windows: Set Up Game's folder, or Settings > Folders' folder:<key>: the in-app browser.)
            if (model_->facts().caps.windows) {
                open_picker(true, e.text == "install" ? std::string("setup-folder") : "folder:" + e.text);
                break;
            }
            const fs::path folder =
                pending_choose_ == "resume" ? model_->facts().install.folder : slot_folder_;
            handle(model_->chosen_folder(folder, now()));
            break;
        }
        case m::Effect::Kind::kRunPreflight: run_preflight(e.path, e.path2); break;
        case m::Effect::Kind::kUninstall: run_uninstall(e.path, e.uninstall); break;
        case m::Effect::Kind::kOpenUrl:
        case m::Effect::Kind::kOpenPath: {
            const std::string url = e.kind == m::Effect::Kind::kOpenUrl ? e.text : file_url(e.path);
            if (o_.testing) {
                std::fprintf(stderr, "@open %s\n", url.c_str());
                break;
            }
            std::string error;
            if (!open_with_desktop(url, &error)) toast("Cannot open it", error);
            break;
        }
        case m::Effect::Kind::kCopy:
            if (copy_text(e.text)) toast("Copied", e.text, false);
            break;
        case m::Effect::Kind::kSaveOwned:
            if (!owned_cache_.empty()) save_ownership(owned_cache_, e.text);
            break;
        case m::Effect::Kind::kQuit: quit_ = true; break;
        case m::Effect::Kind::kOpenMenu: {
            // Windows' More: its entries on the blue side, drilled into from its row (F4).
            for (const m::Action& a : model_->view().game.more) {
                if (!a.enabled) continue;
                drill_in("more", a.id);
                break;
            }
            break;
        }
        case m::Effect::Kind::kSaveFolders:
#ifdef _WIN32
            save_folders();
#endif
            break;
        case m::Effect::Kind::kOpenUpdated: {
#ifdef _WIN32
            // The updated .exe, started on its own; it waits for this launcher to end (C3, TTT2_LAUNCHER_AFTER).
            m::Command c;
            const fs::path exe = exe_;
            c.argv = {win32::narrow(exe.native())};
            c.cwd = exe.parent_path();
            c.env["TTT2_LAUNCHER_AFTER"] = std::to_string(GetCurrentProcessId());
            c.mode = m::Command::Mode::kDetached;
            c.log_file = win_files_->root / "local" / "launcher-reopened.log";
            std::string error;
            auto job = exe.empty() ? nullptr : starter_->start(c, {}, &error);
            if (exe.empty()) error = "the launcher's .exe is not known";
            model_->opened_updated(job || error.empty() ? std::string() : error, now());
            if (job) quit_ = true;
#endif
            break;
        }
        }
    }
}

void App::run_preflight(const fs::path& game, const fs::path& folder) {
#ifdef _WIN32
    (void)game;
    (void)folder;
#else
    const fs::path work = places_.build_work();
    ++working_;
    threads_.emplace_back([this, game, folder, work] {
        m::SystemProbe probe;
        std::vector<m::Check> checks = m::run_checks(game, folder, work, probe);
        post([this, checks = std::move(checks)] {
            --working_;
            handle(model_->preflight_done(checks, now()));
        });
    });
#endif
}

void App::run_uninstall(const fs::path& folder, UninstallOptions options) {
#ifdef _WIN32
    (void)folder;
    (void)options;
#else
    const Places places = places_;
    ++working_;
    threads_.emplace_back([this, places, folder, options] {
        UninstallReport report = uninstall(places, folder, options);
        post([this, report = std::move(report)] {
            --working_;
            model_->uninstall_done(report, now());
        });
    });
#endif
}

} // namespace launcher::app
