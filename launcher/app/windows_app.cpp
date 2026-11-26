// Windows' own parts of the window: getting ready before the launcher shows (the
// first start's Python, then --query state with its protocol checked), the state asked again after each task, and
// Settings > Folders saved through --query save-settings.

#ifdef _WIN32

#include "app.h"
#include "payload.h"

#include "rules.h"
#include "win32.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>

namespace launcher::app {

using namespace ttt2::ui;
namespace c = theme::color;
namespace tx = theme::text;

namespace {

Box fit(Box b, SeamFit f) {
    b.fit = f;
    return b;
}

Focus crimson_focus(bool is_default = false) {
    Focus f;
    f.group = -1;
    f.is_default = is_default;
    return f;
}

std::string u8(const fs::path& p) { return win32::narrow(p.native()); }

// What the start script is doing, in the launcher's language: its "@step <id> <text>" lines are English (a .cmd
// file has one language), so the known ids are said from the catalog; another id keeps the script's own words.
std::string bootstrap_now(const BootstrapProgress& p) {
    if (p.step == "check") return tr("ready.now_check", "Checking the launcher's tools");
    if (p.step == "download") return tr("ready.now_download", "Downloading Python for the launcher");
    if (p.step == "verify") return tr("ready.now_verify", "Checking the download");
    if (p.step == "unpack") return tr("ready.now_unpack", "Unpacking Python");
    if (p.step == "ready") return tr("ready.now_ready", "The launcher's Python is ready");
    return p.text;
}

} // namespace

// Until the model can be made: the first start's Python, the state. False: the window was closed.
bool App::windows_ready() {
    host_ = std::make_unique<ProcessHost>(wake_loop);
    starter_ = std::make_unique<backend::ProcessStarter>(*host_);
    // (Tests: a files folder as the release .exe's, TTT2_LAUNCHER_TEST_FILES: its first start gets Python.)
    fs::path files = o_.files;
    if (const std::wstring f = win32::environment(L"TTT2_LAUNCHER_TEST_FILES"); o_.testing && !f.empty()) files = f;
    win_files_ = windows_files(files, o_.windows);
    ready_ = std::make_unique<WindowsReady>(*win_files_, *starter_);
    if (win_files_->release) {
        // (Its own files again when the state's protocol is another one: a test build's Update got a newer
        // program's files.)
        ready_->restore_files = [root = win_files_->root] {
            try {
                payload::unpack_own_again(program_file(), root);
                return std::string();
            } catch (const std::exception& error) {
                return std::string(error.what());
            }
        };
    }
    stage_->set_target(.5f, false, 0);
    stage_->snap();
    last_ = now();
    // (A smoke start, --ui-smoke-test: its first frame, then the end, before anything is started: no Python is
    // downloaded, no state asked.)
    if (!o_.smoke.empty()) {
        ready_frame(now());
        if (quit_) return false;
    }
    ready_->start(now());
    std::string shot_step;
    double terminal_since = -1;
    while (!quit_) {
        const double t = now();
        SDL_Event ev;
        bool got = SDL_WaitEventTimeout(&ev, o_.testing ? 8 : 50);
        while (got) {
            if (ev.type == SDL_EVENT_QUIT || ev.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
                ready_->cancel();
                return false;
            }
            RawEvent raw;
            if (!o_.testing && window_.translate(ev, raw, t) && !raw.filtered) router_.feed(raw);
            got = SDL_PollEvent(&ev);
        }
        host_->pump();
        {
            std::deque<std::function<void()>> work;
            {
                std::lock_guard<std::mutex> lock(posted_mutex_);
                work.swap(posted_);
            }
            for (auto& w : work) w();
        }
        ready_->tick(now());
        if (ready_->stage() == WindowsReady::Stage::kDone) {
            if (ready_->files().python != win_files_->python) win_files_ = ready_->files();
            win_files_->python_needed = false;
            return true;
        }
        ready_frame(now());
        // Tests: a picture of each step, and of a failure once it has settled (then --screenshot ends the run).
        if (o_.testing) {
            const std::string step = ready_->stage() == WindowsReady::Stage::kBootstrap
                                         ? "bootstrap-" + (ready_->progress().step.empty() ? std::string("start")
                                                                                           : ready_->progress().step)
                                     : ready_->stage() == WindowsReady::Stage::kState ? std::string("state")
                                                                                       : std::string("failed");
            if (step != shot_step && !stage_->animating()) {
                shot_step = step;
                shot("ready-" + step);
                std::fprintf(stderr, "@ready %s\n", step.c_str());
            }
            if (ready_->stage() == WindowsReady::Stage::kFailed) {
                if (terminal_since < 0) terminal_since = now();
                if (now() - terminal_since > 0.6) {
                    std::fprintf(stderr, "@ready failed %s: %s\n", ready_->failure().title.c_str(),
                                 ready_->failure().detail.c_str());
                    if (!o_.screenshot.empty()) {
                        std::string error;
                        if (!window_.screenshot(o_.screenshot, &error))
                            std::fprintf(stderr, "ttt2-launcher: %s\n", error.c_str());
                    }
                    exit_code_ = 3;
                    return false;
                }
            }
        }
    }
    ready_->cancel();
    return false;
}

void App::ready_frame(double t) {
    stage_->set_target(.5f, false, 0);
    stage_->update(t, static_cast<float>(std::clamp(t - last_, 0.0, .25)), window_.points(), false);
    last_ = t;
    router_.tick(t);
    FrameInput in;
    in.size = window_.points();
    in.scale = window_.scale();
    in.now = t;
    in.actions = router_.take_actions();
    in.mouse = router_.take_mouse();
    in.glyphs = router_.glyphs();
    ui_->begin(in);
    ready_declare();
    ui_->end();
    const std::vector<Event> events = ui_->take_events();
    window_.set_drag_area({0, 0, in.size.x, theme::kTopBand}, {ui_->rect("frame")});
    const Vec2 px = window_.pixels();
    canvas_->begin(window_.scale(), static_cast<int>(px.x), static_cast<int>(px.y));
    SDL_SetRenderDrawColor(window_.renderer(), 3, 3, 6, 255);
    SDL_RenderClear(window_.renderer());
    stage_->draw(*canvas_, t);
    watermark(*canvas_, *text_, "Tag", {in.size.x + 30, in.size.y - theme::kBottomBand + 60});
    ui_->paint(*canvas_);
    canvas_->flush();
    if (!o_.smoke.empty() && smoke()) quit_ = true; // (the first frame: the ready loop ends, exit 0)
    if (!o_.testing || o_.real_window) {
        SDL_RenderPresent(window_.renderer());
        if (first_) window_.show();
    }
    first_ = false;
    for (const Event& e : events) {
        const bool accept = e.kind == EventKind::Activate;
        if (accept && (e.id == "ready:quit" || e.id == "quit" || e.id == "frame/close")) quit_ = true;
        else if (accept && e.id == "frame/min") window_.minimise();
        else if (accept && e.id == "frame/full") window_.toggle_fullscreen();
        else if (accept && e.id == "ready:retry") ready_->retry(now());
        else if (accept && e.id == "ready:log") {
            std::string error;
            open_with_desktop(file_url(ready_->failure().log), &error);
        } else if (accept && e.id == "ready:releases") {
            std::string error;
            open_with_desktop("https://github.com/Petexy/Golden-Fist-Launcher/releases", &error);
        } else if (e.kind == EventKind::Back) {
            quit_ = true;
        }
    }
}

void App::ready_declare() {
    Ui& ui = *ui_;
    const Vec2 size = ui.frame().size;
    {
        Box top;
        top.layout = Layout::Row;
        top.align = Align::Center;
        top.w = Size::fixed(size.x);
        top.h = Size::fixed(theme::kTopBand);
        top.pad = {30, 0, 0, 0};
        auto g = ui.open("top", top);
        brand(ui, "brand", "Golden Fist", "Launcher");
        ui.leaf("top/space", Box{.w = Size::grow()}, {}, {});
        TextSpec version{tr("app.version", "Launcher {version}", {{"version", TTT2_LAUNCHER_VERSION}}), tx::kVersion,
                         c::kFaint};
        version.drop = true;
        text(ui, "version", version, Box{.margin = {0, 0, 18, 0}, .shrink_order = 3});
        caption_buttons(ui, "frame", window_.can_minimise(), window_.can_toggle_fullscreen(), window_.fullscreen(),
                        true, Box{.h = Size::fixed(theme::kTopBand)});
    }
    const float sh = stage_->share_now();
    const Seam seam = stage_->layout_seam(sh);
    const Rect cr = stage_->crimson_area(sh), bl = stage_->blue_area(sh);
    Box crimson;
    crimson.seam = seam;
    crimson.margin = {cr.x - 16, cr.y, 0, 0};
    crimson.w = Size::fixed(cr.w + 16 + 22);
    crimson.h = Size::fixed(std::max(60.f, cr.h + 14));
    crimson.pad = {16, 0, 22, 8};
    Box blue;
    blue.seam = seam;
    blue.margin = {bl.x - 16, bl.y, 0, 0};
    blue.w = Size::fixed(bl.w + 16 + 16);
    blue.h = Size::fixed(std::max(60.f, bl.h + 14));
    blue.pad = {16, 0, 16, 8};
    blue.mirror = true;
    const WindowsReady& r = *ready_;
    const bool failed = r.stage() == WindowsReady::Stage::kFailed;
    const bool bootstrap = r.stage() == WindowsReady::Stage::kBootstrap ||
                           (failed && r.files().python_needed);
    {
        auto g = ui.open("ready/crimson", crimson);
        section_label(ui, "ready/label", bootstrap ? tr("ready.first_start", "First start") : tr("ready.starting", "Starting"),
                      Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        text(ui, "ready/title",
             TextSpec{.text = failed      ? r.failure().title
                              : bootstrap ? tr("ready.getting_ready", "Getting the launcher ready")
                                          : tr("ready.reading_files", "Reading the launcher's files"),
                      .style = tx::kBig, .chroma = 3, .autofit_min = 26},
             fit(Box{.margin = {0, 0, 0, 14}}, SeamFit::CrimsonRect));
        // The steps: the first start's (the .cmd's log), then reading the files.
        struct S {
            const char* id;
            std::string name;
        };
        // (Short: the step rows' name column is as wide as their longest name; the blue side says each step whole.)
        const S kSteps[] = {{"check", tr("ready.step_tools", "Tools")},
                            {"download", tr("ready.step_download", "Download")},
                            {"verify", tr("ready.step_verify", "Check it")},
                            {"unpack", tr("ready.step_unpack", "Unpack")},
                            {"state", tr("ready.step_state", "Read files")}};
        const BootstrapProgress& p = r.progress();
        int at = 4;
        if (r.stage() == WindowsReady::Stage::kBootstrap || (failed && bootstrap)) {
            at = 0;
            for (int i = 0; i < 4; ++i)
                if (p.step == kSteps[i].id) at = i;
            if (p.step == "ready") at = 4;
        }
        std::vector<std::string> names;
        for (int i = bootstrap ? 0 : 4; i < 5; ++i) names.push_back(kSteps[i].name);
        const float name_width = step_name_width(ui.text(), names);
        auto rows = ui.open("ready/rows", Box{.gap = 6});
        for (int i = bootstrap ? 0 : 4; i < 5; ++i) {
            StepRowSpec s;
            s.name = kSteps[i].name;
            s.name_width = name_width;
            s.number = bootstrap ? i + 1 : 1;
            s.state = i < at ? StepState::Done : i > at ? StepState::Pending : failed ? StepState::Failed
                                                                                      : StepState::Current;
            s.fraction = i < at ? 1.f : i == at && i == 1 && p.download >= 0 ? static_cast<float>(p.download) : 0.f;
            s.count = i < at ? tr("hint.done", "Done")
                      : i == at && i == 1 && p.download >= 0
                          ? tr("ready.percent", "{percent} %", {{"percent", static_cast<int>(p.download * 100)}})
                          : std::string();
            step_row(ui, "ready/step" + std::to_string(i), s, fit({}, SeamFit::CrimsonSkewed));
        }
        if (failed) {
            auto b = ui.open("ready/btns", fit(Box{.layout = Layout::Row, .margin = {0, 14, 0, 0}, .gap = 12,
                                                   .line_gap = 12, .wrap = true},
                                               SeamFit::CrimsonRect));
            if (r.failure().retry) {
                ButtonSpec retry;
                retry.label = tr("task.try_again", "Try Again");
                retry.kind = ButtonKind::Primary;
                retry.half = Half::Crimson;
                button(ui, "ready:retry", retry, crimson_focus(true));
            } else {
                ButtonSpec rel;
                rel.label = tr("ready.releases_page", "Releases Page");
                rel.kind = ButtonKind::Primary;
                rel.half = Half::Crimson;
                button(ui, "ready:releases", rel, crimson_focus(true));
            }
            if (!r.failure().log.empty()) {
                ButtonSpec log;
                log.label = tr("task.open_log", "Open Log");
                log.half = Half::Crimson;
                button(ui, "ready:log", log, crimson_focus());
            }
            ButtonSpec quit;
            quit.label = tr("dialog.quit", "Quit");
            quit.kind = ButtonKind::Ghost;
            quit.half = Half::Crimson;
            button(ui, "ready:quit", quit, crimson_focus());
        }
    }
    {
        auto g = ui.open("ready/blue", blue);
        section_label(ui, "ready/b-label", "Golden Fist Launcher", Half::Blue, {}, fit({}, SeamFit::BlueRect));
        const std::string about =
            failed ? r.failure().text
            : bootstrap
                ? tr("ready.bootstrap_about", "Its first start gets the Python its tasks run with (about 30 MB, "
                                              "checked against the launcher's pinned copy) into {folder}. Only once: "
                                              "later starts open at once.",
                     {{"folder", u8(r.files().root / "local")}})
                : tr("ready.state_about", "The launcher asks its files what is installed, where your folders are and "
                                          "how the game starts.");
        text(ui, "ready/about", TextSpec{.text = about, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
             fit(Box{.margin = {0, 10, 0, 10}}, SeamFit::BlueRect));
        if (failed && !r.failure().detail.empty())
            text(ui, "ready/detail",
                 TextSpec{.text = r.failure().detail, .style = tx::kFactValue, .color = c::kBlueFaint, .wrap = true},
                 fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
        if (bootstrap && !failed && !r.progress().text.empty())
            text(ui, "ready/now", TextSpec{.text = bootstrap_now(r.progress()), .style = tx::kKick, .color = c::kCyan},
                 fit({}, SeamFit::BlueRect));
    }
    {
        Box bottom;
        bottom.layout = Layout::Row;
        bottom.align = Align::Center;
        bottom.w = Size::fixed(size.x);
        bottom.h = Size::fixed(theme::kBottomBand);
        bottom.margin = {0, size.y - theme::kBottomBand, 0, 0};
        bottom.pad = {34, 0, 26, 0};
        auto g = ui.open("bottom", bottom);
        std::vector<Hint> hs;
        if (failed) {
            hs.push_back({Prompt::Move, tr("hint.move", "Move")});
            hs.push_back({Prompt::Accept, focused_label().empty() ? tr("hint.choose", "Choose") : focused_label()});
        }
        hs.push_back({Prompt::Back, tr("dialog.quit", "Quit")});
        hint_bar(ui, "hints", hs, {}, size.x - bottom.pad.left - bottom.pad.right);
    }
}

// After each task (and Settings > Folders saved): what is installed and where, asked again.
void App::windows_state_again() {
    if (state_job_) {
        state_again_ = true;
        return;
    }
    state_out_.clear();
    m::JobEvents ev;
    ev.line = [this](const std::string& line, bool is_error) {
        if (!is_error) state_out_ += line + "\n";
    };
    ev.exited = [this](int) {
        post([this] {
            state_job_.reset();
            backend::QueryError error;
            if (const auto answer = backend::parse_windows_state(state_out_, &error)) {
                m::Facts& f = model_->mutable_facts();
                backend::apply_windows_state(*answer, f);
                exe_ = answer->exe;
                model_->set_windows_state(f.windows);
                folders_from_state(f.windows);
            } else {
                std::fprintf(stderr, "ttt2-launcher: --query state: %s %s\n", error.code.c_str(), error.text.c_str());
            }
            if (state_again_) {
                state_again_ = false;
                windows_state_again();
            }
        });
    };
    std::string error;
    auto& commands = static_cast<m::WindowsCommands&>(*commands_);
    state_job_ = starter_->start(commands.query(model_->facts(), "state"), std::move(ev), &error);
    if (!state_job_) std::fprintf(stderr, "ttt2-launcher: --query state did not start: %s\n", error.c_str());
}

// Settings > Folders' Save Folders: checked and saved by Python (--query save-settings), the player told why not.
void App::save_folders() {
    if (save_job_) return;
    save_out_.clear();
    m::JobEvents ev;
    ev.line = [this](const std::string& line, bool is_error) {
        if (!is_error) save_out_ += line + "\n";
    };
    ev.exited = [this](int) {
        post([this] {
            save_job_.reset();
            backend::QueryError error;
            const auto saved = backend::parse_save_settings(save_out_, &error);
            if (!saved) {
                toast(tr("model.folders_not_saved", "Folders not saved"),
                      error.text.empty() ? tr("app.files_no_answer", "The launcher's files did not answer.") : error.text);
                cue(ttt2::app::Cue::TaskFailed);
                return;
            }
            if (!saved->problem.code.empty()) {
                toast(tr("model.folders_not_saved", "Folders not saved"), m::save_problem_text(saved->problem));
                cue(ttt2::app::Cue::TaskFailed);
                return;
            }
            model_->mutable_facts().windows.folders = saved->folders;
            folders_changed_ = false;
            toast(tr("app.folders_saved", "Folders saved"),
                  tr("app.folders_saved_about", "The launcher and the game use them from now on."), false);
            cue(ttt2::app::Cue::TaskDone);
            windows_state_again();
        });
    };
    std::string error;
    auto& commands = static_cast<m::WindowsCommands&>(*commands_);
    save_job_ = starter_->start(commands.save_settings(model_->facts(), model_->facts().windows.folders),
                                std::move(ev), &error);
    if (!save_job_)
        toast(tr("model.folders_not_saved", "Folders not saved"),
              tr("app.python_not_started", "Python did not start: {error}.", {{"error", error}}));
}

} // namespace launcher::app

#endif
