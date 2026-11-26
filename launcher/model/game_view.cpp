// The game's card (launcher/app/game.cpp's show_game and its states; the
// Windows card's Set Up Game, More and folder from window.py), the header,
// the banner, the launcher update notice and the dialogs.

#include "builders.h"
#include "utf8_path.h"
#include "rules.h"

#include <cstdlib>

namespace launcher::model {

Line text_line(std::string text, Tone tone, bool small) {
    Line l;
    l.kind = Line::Kind::kText;
    l.text = std::move(text);
    l.tone = tone;
    l.small = small;
    return l;
}

Line note_line(Icon icon, std::string text, bool warn, Tone icon_tone) {
    Line l;
    l.kind = Line::Kind::kNote;
    l.icon = icon;
    l.icon_tone = warn ? Tone::kWarning : icon_tone;
    l.text = std::move(text);
    return l;
}

std::string refusal_sentence(const std::string& title, const std::string& why) {
    if (why.empty()) return tr("common.refusal_alone", "{title}.", {{"title", title}});
    std::string lower = why;
    // (After the colon in small letters, as English, French, Italian, Spanish and Polish write it; German keeps its
    // nouns' capitals.)
    if (i18n::language() != "de" && !lower.empty() && lower[0] >= 'A' && lower[0] <= 'Z' &&
        !(lower.size() > 1 && lower[1] >= 'A' && lower[1] <= 'Z')) {
        lower[0] = static_cast<char>(lower[0] - 'A' + 'a');
    }
    return tr("common.refusal", "{title}: {why}", {{"title", title}, {"why", lower}});
}

namespace {

Action button(std::string id, std::string label, bool enabled = true, std::string why = {}, std::string tooltip = {}) {
    Action a;
    a.id = std::move(id);
    a.label = std::move(label);
    a.enabled = enabled;
    a.why = enabled ? std::string() : std::move(why);
    a.tooltip = std::move(tooltip);
    a.describe.title = a.label;
    a.describe.explain = a.tooltip;
    a.describe.why = a.why;
    return a;
}

// Why a game action waits: the task that runs ("Wait for it to end, then ..."), the game that runs, the kit.
std::string task_why(const std::string& then) { return refusal_sentence(tr("common.task_running", "Another task is running"), then); }

std::string builder_missing() { return tr("game.builder_missing", "The game builder is missing from this launcher."); }

// A text without its last full stop (to go on after it).
std::string without_stop(std::string text) {
    while (!text.empty() && (text.back() == '.' || text.back() == ' ')) text.pop_back();
    return text;
}

} // namespace

std::vector<UpdatePart> update_parts(const Facts& facts, const UpdatePlan& plan) {
    std::vector<UpdatePart> parts;
    if (plan.launcher) {
        parts.push_back({"launcher",
                         tr("update.launcher_title", "Golden Fist Launcher {from} → {to}",
                            {{"from", plan.launcher_from}, {"to", plan.launcher_to}}),
                         facts.caps.windows
                             ? tr("update.launcher_text_windows",
                                  "Downloads {to} in place of this launcher, which then restarts by itself and goes on.",
                                  {{"to", plan.launcher_to}})
                             : tr("update.launcher_text",
                                  "Downloads {to} in place of this AppImage, which then restarts by itself and goes on.",
                                  {{"to", plan.launcher_to}})});
    }
    if (plan.game) {
        std::string text;
        if (plan.launcher)
            text = facts.caps.windows ? tr("update.game_new_windows",
                                           "Built again by the new launcher, on this PC from your game: a few minutes. "
                                           "Saves and settings stay.")
                                      : tr("update.game_new",
                                           "Built again by the new launcher, from the game in its folder: a few "
                                           "minutes. Saves and settings stay.");
        else
            text = facts.caps.windows ? tr("update.game_for_windows",
                                           "Built again for {version}, on this PC from your game: a few minutes. Saves "
                                           "and settings stay.",
                                           {{"version", plan.game_for}})
                                      : tr("update.game_for",
                                           "Built again for {version}, from the game in its folder: a few minutes. "
                                           "Saves and settings stay.",
                                           {{"version", plan.game_for}});
        parts.push_back({"game", tr("update.game_title", "The game program"), text});
    }
    if (!plan.fighters.empty()) {
        bool tekken7 = false, tekken8 = false;
        std::vector<std::string> names;
        for (const std::string& name : plan.fighters) {
            const Fighter* f = fighter(facts, name);
            if (f) (f->of(kTekken8) ? tekken8 : tekken7) = true;
            names.push_back(display_name(facts, name));
        }
        const std::string games = tekken7 && tekken8 ? tr("common.both_games", "Tekken 7 and Tekken 8")
                                  : tekken8          ? "Tekken 8"
                                                     : "Tekken 7";
        parts.push_back({"fighters", tr("update.fighters_title", "Fighters"),
                         trn("update.fighters_text", static_cast<long long>(names.size()),
                             "{names} gets the newest pack, made from your own {games}.",
                             "{names} get the newest pack, made from your own {games}.",
                             {{"names", names.size() <= 4 ? joined(names) : joined_most(names, 3)}, {"games", games}})});
    }
    if (!plan.later.empty()) {
        std::string text;
        for (const auto& [name, why] : plan.later)
            text += (text.empty() ? "" : "; ") +
                    tr("update.later_item", "{name} ({why})", {{"name", name}, {"why", without_stop(why)}});
        parts.push_back({"later", tr("update.later_title", "Left for later"),
                         tr("update.later_text", "{list}.", {{"list", text}})});
    }
    return parts;
}

namespace {

void installed(const Facts& facts, GameView& v) {
    const bool playing = facts.game_running;
    const bool task = facts.task.has_value();
    v.state = GameState::kInstalled;
    v.folder = path_utf8(facts.install.folder);
    v.pill.text = playing                                            ? tr("game.pill_running", "Running")
                  : task && facts.task->kind == TaskKind::kUpdate    ? tr("game.pill_updating", "Updating")
                  : task && facts.task->kind == TaskKind::kUninstall ? tr("game.pill_uninstalling", "Uninstalling")
                                                                     : tr("game.pill_installed", "Installed");
    v.pill.kind = task && !playing ? PillKind::kNeutral : PillKind::kOk;
    v.pill.live = playing;
    if (playing && !facts.game_started_here && facts.caps.game_outside) {
        Line l = note_line(Icon::kInfo,
                           tr("game.started_outside",
                              "It was started outside the launcher. Quit it to update or uninstall it."),
                           false, Tone::kDim);
        l.tone = Tone::kDim;
        l.small = true;
        v.body.push_back(l);
    }
    const bool update = update_ready(facts);
    const std::string older = older_game(facts);
    // (Windows builds it from the .wua chosen in Folders: the Tk window's words.)
    const std::string again = facts.caps.windows
                                  ? tr("game.again_windows", "Update builds it again on this PC from your game: a few "
                                                             "minutes.")
                                  : tr("game.again", "Update builds it again from the game in its folder: a few "
                                                     "minutes.");
    const auto with_again = [&](const std::string& text) {
        return tr("common.two_sentences", "{first} {second}", {{"first", text}, {"second", again}});
    };
    if (!older.empty()) {
        Line l = note_line(Icon::kWarning, with_again(older), true);
        l.tone = Tone::kDim;
        l.small = true;
        v.body.push_back(l);
    } else if (update) {
        Line l = note_line(Icon::kInfo,
                           facts.game_built.empty()
                               ? tr("game.not_built_here", "This game program was not built by the launcher. Update "
                                                           "builds it again from the game in its folder.")
                           : facts.caps.windows
                               ? with_again(tr("game.update_ready_windows",
                                               "An update of the game is ready (Golden Fist Launcher {this}; the game "
                                               "is from {game}).",
                                               {{"this", shown_build(facts.this_build)},
                                                {"game", shown_build(facts.game_built)}}))
                               : with_again(tr("game.update_ready",
                                               "An update of the game program is ready ({this}, installed {game}).",
                                               {{"this", facts.this_build}, {"game", facts.game_built}})),
                           true);
        l.tone = Tone::kDim;
        l.small = true;
        v.body.push_back(l);
    }
    if (!facts.game_error.empty()) v.body.push_back(text_line(facts.game_error, Tone::kError));

    const auto game_runs = [](const std::string& then) {
        return refusal_sentence(tr("game.running_title", "The game is running"), then);
    };
    const std::string wait_update = tr("game.wait_update", "Wait for it to end, then update.");
    const std::string quit_update = tr("game.quit_update", "Quit it, then update.");
    const std::string busy_why = playing ? game_runs(quit_update) : task ? task_why(wait_update) : builder_missing();
    const auto update_button = [&](bool primary) {
        Action b = button("update", tr("game.update", "Update"), !playing && !task && facts.builder, busy_why,
                          tr("game.update_tip", "Build the game program again with this launcher's version"));
        if (primary) {
            b.primary = true;
            b.icon = Icon::kUpdate;
        }
        b.describe.more.push_back(older.empty() ? "" : older);
        if (b.describe.more.back().empty()) b.describe.more.pop_back();
        v.actions.push_back(b);
    };
    // Home's UPDATE (any part pending): in Play's place; Play is then an ordinary entry (none while the game is older
    // than this launcher can run).
    const UpdatePlan plan = update_plan(facts);
    if (!plan.empty()) {
        Action all = button("update-everything", tr("game.update", "Update"), !playing && !task,
                            playing ? game_runs(quit_update) : task_why(wait_update),
                            tr("game.update_everything_tip", "Bring the launcher, the game and the fighters up to date"));
        all.primary = true;
        all.icon = Icon::kUpdate;
        all.describe.explain = trn("game.update_parts", plan.parts(), "One part to bring up to date:",
                                   "{n} parts, brought up to date one after another:");
        v.actions.push_back(all);
        v.update = update_parts(facts, plan);
    }
    if (!older.empty()) {
        if (plan.empty()) update_button(true);
    } else {
        Action play =
            button("play", playing ? tr("game.playing", "Playing") : tr("game.play", "Play"), !playing && !task,
                   playing ? game_runs(tr("game.only_one", "Only one can run at a time."))
                   : facts.task && facts.task->kind == TaskKind::kShaders
                       ? tr("game.starts_after_shaders", "The game starts by itself once its shaders are ready.")
                       : task_why(tr("game.wait_play", "Wait for it to end, then play.")));
        play.primary = plan.empty();
        play.icon = Icon::kPlay;
        play.describe.state = playing ? tr("game.pill_running", "Running") : "";
        v.actions.push_back(play);
    }
    Action settings = button("settings", "", true, {}, tr("common.settings", "Settings"));
    settings.icon = Icon::kSettings;
    settings.describe.title = tr("common.settings", "Settings");
    v.actions.push_back(settings);
    if (update && older.empty() && plan.empty()) update_button(false);
    v.spacer = v.actions.size();
    Action open = button("open-folder", "", true, {}, tr("game.open_folder", "Open the install folder"));
    open.icon = Icon::kFolder;
    open.describe.title = tr("game.open_folder", "Open the install folder");
    open.describe.path = path_utf8(facts.install.folder);
    v.actions.push_back(open);
    if (facts.caps.uninstall) {
        Action u = button("uninstall", tr("game.uninstall", "Uninstall…"), !playing && !task,
                          playing ? game_runs(tr("game.quit_uninstall", "Quit it, then uninstall."))
                                  : task_why(tr("game.wait_uninstall", "Wait for it to end, then uninstall.")));
        u.destructive = true;
        u.describe.path = path_utf8(facts.install.folder);
        v.actions.push_back(u);
    }
}

void unfinished(const Facts& facts, GameView& v) {
    const bool task = facts.task.has_value();
    v.state = GameState::kNotFinished;
    v.folder = path_utf8(facts.install.folder);
    v.pill = {tr("game.pill_not_finished", "Not finished"), PillKind::kWarn, {}};
    v.body.push_back(text_line(tr("game.unfinished", "The install stopped before it was complete. Resume it to "
                                                     "finish: the files copied so far are kept."),
                               Tone::kDim));
    if (!facts.game_error.empty()) v.body.push_back(text_line(facts.game_error, Tone::kError));
    const std::string wait_install = tr("game.wait_install", "Wait for it to end, then install.");
    Action resume = button("resume", tr("game.resume", "Resume"), !task && facts.builder,
                           task ? task_why(wait_install) : builder_missing());
    resume.primary = true;
    resume.describe.path = path_utf8(facts.install.folder);
    v.actions.push_back(resume);
    v.spacer = v.actions.size();
    if (facts.caps.uninstall) {
        Action u = button("uninstall", tr("game.uninstall", "Uninstall…"), !task,
                          task_why(tr("game.wait_uninstall", "Wait for it to end, then uninstall.")));
        u.destructive = true;
        u.describe.path = path_utf8(facts.install.folder);
        v.actions.push_back(u);
    }
}

void not_installed(const Facts& facts, GameView& v) {
    const bool task = facts.task.has_value();
    v.state = GameState::kNotInstalled;
    v.pill = {tr("game.pill_not_installed", "Not installed"), PillKind::kNeutral, {}};
    if (facts.caps.setup_game) {
        v.body.push_back(note_line(Icon::kInfo,
                                   tr("game.setup_about",
                                      "Set Up Game asks for your own European Wii U archive (.wua) with update v16 and "
                                      "a folder. It downloads what it needs, builds the game on this PC from your copy "
                                      "and installs it: about 30 GB, and a while. Your archive is kept."),
                                   false));
        Action setup = button("setup", tr("game.setup", "Set Up Game…"), !task,
                              task_why(tr("game.wait_setup", "Wait for it to end, then set up the game.")));
        setup.primary = true;
        v.actions.push_back(setup);
        return;
    }
    v.body.push_back(text_line(tr("game.install_about",
                                  "Install it from your own copy of TEKKEN TAG TOURNAMENT 2 Wii U EDITION (European, "
                                  "with update 16) as a .wua archive. The launcher builds the game program for this PC "
                                  "from it, then copies the game into a folder you choose (about 16 GB)."),
                               Tone::kDim));
    if (!facts.chosen_game.empty()) {
        Line file;
        file.kind = Line::Kind::kFile;
        file.icon = Icon::kDocument;
        file.icon_tone = Tone::kDim;
        file.title = path_utf8(facts.chosen_game.filename());
        file.text = path_utf8(facts.chosen_game.parent_path());
        v.body.push_back(file);
    }
    if (!facts.builder) {
        v.body.push_back(text_line(facts.kit.empty()
                                       ? tr("game.builder_missing_install",
                                            "The game builder is missing from this launcher: the game cannot be "
                                            "installed.")
                                       : tr("game.builder_missing_in",
                                            "The game builder is missing from this launcher ({kit}): the game cannot "
                                            "be installed.",
                                            {{"kit", path_utf8(facts.kit)}}),
                                   Tone::kError));
    }
    if (!facts.game_error.empty()) v.body.push_back(text_line(facts.game_error, Tone::kError));
    Action install = button("install", tr("game.install", "Install…"), facts.builder && !task,
                            !facts.builder ? builder_missing()
                                           : task_why(tr("game.wait_install", "Wait for it to end, then install.")));
    install.primary = true;
    if (!facts.chosen_game.empty()) install.describe.path = path_utf8(facts.chosen_game);
    v.actions.push_back(install);
}

void installing(const Facts& facts, GameView& v) {
    v.state = GameState::kInstalling;
    v.folder = path_utf8(facts.installing);
    v.pill = {tr("game.pill_installing", "Installing"), PillKind::kNeutral, {}};
    v.body.push_back(text_line(tr("game.installing",
                                  "The game program is built for this PC from your game, then the game is copied into "
                                  "this folder. Stopping keeps what is copied: the install resumes from there."),
                               Tone::kDim));
}

void preflight(const Facts& facts, GameView& v) {
    const Preflight& p = *facts.preflight;
    v.state = p.running ? GameState::kChecking : GameState::kCannotInstall;
    v.folder = path_utf8(p.folder);
    v.pill = {p.running ? tr("game.pill_checking", "Checking") : tr("game.pill_cannot_install", "Cannot install yet"),
              p.running ? PillKind::kNeutral : PillKind::kBad, {}, p.running};
    if (p.running) {
        Line l;
        l.kind = Line::Kind::kSpinner;
        l.text = tr("game.checking_pc", "Checking this PC…");
        l.tone = Tone::kDim;
        v.body.push_back(l);
        return;
    }
    v.body.push_back(text_line(tr("game.before_install", "Before the install can start:"), Tone::kDim));
    for (const Check& c : p.checks) {
        Line l;
        l.kind = Line::Kind::kCheck;
        l.icon = c.ok ? Icon::kOk : Icon::kError;
        l.icon_tone = c.ok ? Tone::kOk : Tone::kError;
        l.title = c.title;
        l.text = c.detail;
        l.tone = c.ok ? Tone::kDim : Tone::kNormal;
        l.small = true;
        if (!c.command.empty()) {
            Action copy = button("copy:" + c.command, "", true, {}, tr("game.copy", "Copy"));
            copy.icon = Icon::kCopy;
            copy.flat = true;
            copy.describe.title = tr("game.copy_command", "Copy the command");
            copy.describe.more.push_back(c.command);
            l.actions.push_back(copy);
        }
        v.body.push_back(l);
    }
    Action again = button("check-again", tr("game.check_again", "Check Again"));
    again.primary = true;
    v.actions.push_back(again);
    v.actions.push_back(button("preflight-cancel", tr("common.cancel", "Cancel")));
}

// Windows: More, and its menu.
void more(const Facts& facts, GameView& v) {
    if (!facts.caps.more_menu) return;
    const bool task = facts.task.has_value();
    const bool is_installed = facts.install.state == InstallState::kInstalled;
    Action m = button("more", tr("game.more", "More"), !task,
                      task_why(tr("game.wait_build", "Wait for it to end, then build or install.")),
                      tr("game.more_tip", "Build, install and the logs"));
    m.kind = ActionKind::kMenu;
    m.icon = Icon::kMore;
    v.actions.push_back(m);
    const auto entry = [&](std::string id, std::string label, bool enabled, std::string why) {
        Action a = button(std::move(id), std::move(label), enabled, std::move(why));
        a.kind = ActionKind::kMenuItem;
        v.more.push_back(a);
    };
    entry("more:build", tr("more.build", "Build / Rebuild"), true, {});
    entry("more:install", tr("more.install", "Install from Wii U Source"), true, {});
    entry("more:update", tr("more.update", "Update Installed Game"), is_installed,
          tr("more.update_why", "Choose a complete installation before updating."));
    if (is_installed) entry("more:setup-again", tr("more.setup_again", "Set Up Again…"), true, {});
    entry("more:open-logs", tr("more.open_logs", "Open Logs Folder"), true, {});
    entry("more:latest-log", tr("more.latest_log", "Open Latest Log"), true, {});
}

// What each of the game's actions does, said on the blue side beside it (the Tag Split's readout; the GTK
// window had only tooltips): as the mock's texts, from the facts.
void explain(const Facts& facts, GameView& v) {
    const auto shown = [](const fs::path& p) { return shown_path(p); };
    const bool task = facts.task.has_value();
    for (Action& a : v.actions) {
        std::string& x = a.describe.explain;
        if (a.id == "play") {
            x = facts.game_running ? tr("game.play_running", "Tekken Tag Tournament 2 is running. Update and "
                                                             "Uninstall wait until it is closed.")
                                   : tr("game.play_explain", "Starts Tekken Tag Tournament 2 with the Display "
                                                             "settings and keys as they are now.");
        } else if (a.id == "update") {
            x = older_game(facts).empty()
                    ? tr("game.update_explain", "Builds the game program again with this launcher's version: a few "
                                                "minutes. The game and your saves stay as they are.")
                    : tr("game.update_explain_older",
                         "Builds the game again with this launcher's version ({version}): a few minutes. Then it can "
                         "be played, and fighters added or updated.",
                         {{"version", std::string(launcher_version(facts.this_build))}});
        } else if (a.id == "settings") {
            x = facts.install.state == InstallState::kInstalled
                    ? tr("game.settings_explain", "Display and keyboard, which the game uses when it starts, and the "
                                                  "launcher's own sounds, motion and button prompts.")
                    : tr("game.settings_explain_before", "The launcher's own sounds, motion and button prompts. "
                                                         "Display and keyboard come with the game.");
        } else if (a.id == "open-folder") {
            x = tr("game.open_folder_explain", "Opens {folder} in the file manager.",
                   {{"folder", shown(facts.install.folder)}});
        } else if (a.id == "uninstall") {
            x = tr("game.uninstall_explain", "Deletes the game and its program from this folder. It asks first: your "
                                             "saves and the added characters can stay.");
            if (facts.game_running)
                x = tr("common.two_sentences", "{first} {second}",
                       {{"first", x}, {"second", tr("game.not_while_running", "Not while the game is running: close "
                                                                               "it first.")}});
            else if (task)
                x = tr("common.two_sentences", "{first} {second}",
                       {{"first", x}, {"second", tr("game.not_while_task", "Not while a task is running.")}});
        } else if (a.id == "resume") {
            x = tr("game.resume_explain", "Finishes the install into {folder}: the files copied so far are kept.",
                   {{"folder", shown(facts.install.folder)}});
        } else if (a.id == "install") {
            x = facts.chosen_game.empty()
                    ? tr("game.install_explain", "Asks for your .wua first, then checks this PC and installs.")
                    : tr("game.install_explain_file",
                         "Checks this PC, then builds the game program from {file} and copies the game into the folder "
                         "chosen.",
                         {{"file", path_utf8(facts.chosen_game.filename())}});
        } else if (a.id == "check-again") {
            x = tr("game.check_again_explain", "Checks this PC again: the install starts once everything is ready.");
        } else if (a.id == "preflight-cancel") {
            x = tr("game.preflight_cancel_explain", "Goes back without installing.");
        }
    }
}

} // namespace

// A path as the window shows it: the home folder as ~.
std::string shown_path(const fs::path& path) {
    const std::string p = path_utf8(path);
    const char* home = std::getenv("HOME");
    if (home && *home) {
        const std::string h = std::string(home);
        if (p == h) return "~";
        if (p.size() > h.size() && p.compare(0, h.size(), h) == 0 && p[h.size()] == '/') return "~" + p.substr(h.size());
    }
    return p;
}

GameView game_view(const Facts& facts) {
    GameView v;
    if (facts.preflight && facts.caps.install_flow)
        preflight(facts, v);
    else if (facts.task && facts.task->kind == TaskKind::kInstall && !facts.installing.empty())
        installing(facts, v);
    else if (facts.install.state == InstallState::kInstalled)
        installed(facts, v);
    else if (facts.install.state == InstallState::kUnfinished && facts.caps.install_flow)
        unfinished(facts, v);
    else
        not_installed(facts, v);
    // Settings: always there (the launcher's own settings with any state of the game; the game's when
    // installed, on Windows also before Set Up Game, for its folders).
    if (v.state != GameState::kInstalled && v.state != GameState::kChecking && v.state != GameState::kCannotInstall) {
        Action settings;
        settings.id = "settings";
        settings.icon = Icon::kSettings;
        settings.tooltip = tr("common.settings", "Settings");
        settings.describe.title = tr("common.settings", "Settings");
        const size_t at = std::min(v.spacer, v.actions.size());
        v.actions.insert(v.actions.begin() + static_cast<long>(std::min<size_t>(at, v.actions.empty() ? 0 : 1)),
                         settings);
        if (v.spacer != SIZE_MAX) ++v.spacer;
    }
    if (facts.caps.more_menu && v.state != GameState::kChecking && v.state != GameState::kCannotInstall) {
        if (v.spacer == SIZE_MAX) v.spacer = v.actions.size();
        more(facts, v);
    }
    explain(facts, v);
    return v;
}

Banner banner_view(const Facts& facts) {
    Banner b;
    b.note = tr("banner.note",
                "The Wii U game as a native {platform} program, built on this PC from your own copy, with Tekken 7's "
                "and Tekken 8's characters added from yours.",
                {{"platform", facts.caps.platform_name}});
    b.icon = facts.icon && facts.install.state == InstallState::kInstalled;
    return b;
}

Header header_view(const Facts& facts, bool in_settings) {
    Header h;
    h.title = in_settings ? tr("common.settings", "Settings") : "Golden Fist Launcher";
    if (in_settings) {
        Action back = button("back", "", true, {}, tr("common.back", "Back"));
        back.icon = Icon::kBack;
        back.describe.title = tr("common.back", "Back");
        h.actions.push_back(back);
        return h;
    }
    Action refresh = button("refresh", "", true, {}, tr("header.refresh", "Check again"));
    refresh.icon = Icon::kRefresh;
    refresh.describe.title = tr("header.refresh", "Check again");
    h.actions.push_back(refresh);
    if (facts.self_update) {
        const bool newer = facts.newer.has_value();
        const bool test_build = facts.caps.branch_updates && !facts.windows.branch.empty();
        std::string tip =
            newer ? tr("header.update_to", "Update the launcher to version {version} (this is version {this})",
                       {{"version", facts.newer->version}, {"this", facts.launcher_version}})
            : test_build ? tr("header.update_from", "Update the launcher from {branch} (this is {this}, {commit})",
                              {{"branch", facts.windows.branch}, {"this", facts.launcher_version},
                               {"commit", facts.windows.commit.substr(0, 7)}})
                         : tr("header.update", "Update the launcher (this is version {this})",
                              {{"this", facts.launcher_version}});
        Action update = button("update-launcher", "", true, {}, tip);
        update.icon = Icon::kUpdate;
        update.describe.title = tr("header.update_title", "Update the launcher");
        update.describe.explain = tip;
        h.actions.push_back(update);
        h.update_offered = newer || (test_build && facts.main_news && facts.main_news->ahead > 0);
    }
    return h;
}

NoticeView notice_view(const Facts& facts) {
    NoticeView n;
    const bool task = facts.task.has_value();
    n.update = button("notice-update", tr("game.update", "Update"), !task,
                      task_why(tr("notice.wait_update", "Wait for it to end, then update the launcher.")));
    n.update.primary = true;
    if (facts.newer) {
        n.update.describe.explain =
            facts.caps.windows
                ? tr("notice.update_explain_windows",
                     "Downloads version {version}, checks it, then it replaces this launcher and opens.",
                     {{"version", facts.newer->version}})
                : tr("notice.update_explain", "Downloads version {version}, checks it, then it replaces this AppImage "
                                              "and opens.",
                     {{"version", facts.newer->version}});
    }
    const auto page = [&](const std::string& link, bool shown) {
        if (!shown) return;
        Action p = button("release-page", tr("notice.whats_new", "What's New"));
        p.describe.path = link;
        p.describe.explain = tr("notice.whats_new_explain", "Opens the release page of {version} in the browser.",
                                {{"version", facts.newer ? facts.newer->version : std::string()}});
        n.page = p;
    };
    if (facts.self_update && facts.newer) {
        n.shown = true;
        n.title = tr("notice.out", "Version {version} of the launcher is out", {{"version", facts.newer->version}});
        const std::string have = facts.caps.windows && facts.newer->version == facts.launcher_version
                                     ? tr("notice.test_build", "a test build of it")
                                     : facts.launcher_version;
        n.detail = facts.caps.windows
                       ? tr("notice.have_windows", "You have {have}. Update replaces this launcher with it and opens it.",
                            {{"have", have}})
                       : tr("notice.have", "You have {have}. Update replaces this AppImage with it and opens it.",
                            {{"have", have}});
        // (Installed: Home's UPDATE does it with the rest, the game and the fighters; this one says so.)
        if (update_plan(facts).launcher && facts.install.state == InstallState::kInstalled) {
            n.whole = true;
            n.detail = tr("notice.have_whole", "You have {have}. Update on Home gets it first, then brings the game "
                                               "program and the fighters up to date.",
                          {{"have", have}});
        }
        page(facts.newer->page,
             facts.newer->page.starts_with("https://") || (facts.custom_releases && !facts.newer->page.empty()));
    } else if (facts.self_update && facts.caps.branch_updates && !facts.windows.branch.empty() && facts.main_news &&
               facts.main_news->ahead > 0) {
        const MainNews& news = *facts.main_news;
        n.shown = true;
        n.title = tr("notice.newer_on", "Newer changes are on {branch}", {{"branch", facts.windows.branch}});
        const i18n::Args args = {{"this", facts.launcher_version},
                                 {"commit", facts.windows.commit.substr(0, 7)},
                                 {"newest", news.changes.empty() ? std::string() : news.changes[0]}};
        n.detail = news.changes.empty()
                       ? trn("notice.changes", news.ahead, "{n} change since this test build ({this}, {commit}).",
                             "{n} changes since this test build ({this}, {commit}).", args)
                       : trn("notice.changes_newest", news.ahead,
                             "{n} change since this test build ({this}, {commit}), the newest: “{newest}”.",
                             "{n} changes since this test build ({this}, {commit}), the newest: “{newest}”.", args);
        n.detail = tr("common.two_sentences", "{first} {second}",
                      {{"first", n.detail},
                       {"second", facts.program_in_exe
                                      ? tr("notice.update_gets_exe", "Update gets them; changes to the launcher "
                                                                     "program itself need a new test build.")
                                      : tr("notice.update_gets", "Update gets them.")}});
        page(news.page, news.page.starts_with("https://") || facts.custom_github);
    }
    return n;
}

// ---------------------------------------------------------------- dialogs

Dialog uninstall_view(const Facts& facts, const fs::path& saves, bool saves_custom, const UninstallChoice& choice) {
    Dialog d;
    d.id = "uninstall";
    d.title = tr("dialog.uninstall_title", "Uninstall Tekken Tag Tournament 2?");
    d.text = tr("dialog.uninstall_text",
                "This deletes the game, its program and its menu entry from this folder; anything else in it stays:");
    d.lines.push_back(text_line(path_utf8(facts.install.folder), Tone::kPath));
    const auto check = [&](std::string id, std::string label, bool on) {
        Action a = button(std::move(id), std::move(label));
        a.kind = ActionKind::kCheck;
        a.checked = on;
        a.describe.state = on ? tr("common.on", "On") : tr("common.off", "Off");
        Line l;
        l.actions.push_back(a);
        return l;
    };
    Line s = check("uninstall-saves", tr("dialog.uninstall_saves", "Also delete saves"), choice.saves);
    s.actions[0].describe.path = path_utf8(saves);
    const std::string only_saves =
        tr("dialog.uninstall_only_saves", "Only the game's saves in it are deleted; anything else there stays.");
    if (saves_custom) s.actions[0].describe.more.push_back(only_saves);
    d.lines.push_back(s);
    d.lines.push_back(text_line(path_utf8(saves), Tone::kPath));
    if (saves_custom) d.lines.push_back(text_line(only_saves, Tone::kDim, true));
    d.lines.push_back(check("uninstall-characters",
                            tr("dialog.uninstall_characters",
                               "Also delete added characters and what was saved from Tekken 7 and Tekken 8"),
                            choice.characters));
    d.buttons.push_back(button("uninstall-cancel", tr("common.cancel", "Cancel")));
    Action u = button("uninstall-confirm", tr("dialog.uninstall", "Uninstall"));
    u.destructive = true;
    d.buttons.push_back(u);
    d.cancel = d.default_id = "uninstall-cancel";
    return d;
}

Dialog remove_all_view(const Facts& facts, const std::string& game) {
    Dialog d;
    d.id = "remove-all";
    const auto names = to_remove_all(facts, game);
    const std::string name = game_name(game);
    d.title = trn("dialog.remove_all_title", static_cast<long long>(names.size()), "Remove all {n} {game} characters?",
                  "Remove all {n} {game} characters?", {{"game", name}});
    d.text = tr("dialog.remove_all_text", "{game} is not installed, so they cannot be added again until it is.",
                {{"game", name}});
    d.buttons.push_back(button("remove-all-cancel", tr("common.cancel", "Cancel")));
    Action r = button("remove-all-confirm", tr("dialog.remove_all", "Remove All"));
    r.destructive = true;
    d.buttons.push_back(r);
    d.cancel = d.default_id = "remove-all-cancel";
    return d;
}

Dialog stop_and_quit_view(const std::string& task_title) {
    Dialog d;
    d.id = "stop-and-quit";
    d.title = tr("dialog.stop_title", "Stop and quit?");
    d.text = tr("dialog.stop_text", "{task} is not finished. Stop it and close the launcher?", {{"task", task_title}});
    d.buttons.push_back(button("keep-running", tr("dialog.keep_running", "Keep Running")));
    Action s = button("stop-and-quit", tr("dialog.stop_and_quit", "Stop and Quit"));
    s.destructive = true;
    d.buttons.push_back(s);
    d.cancel = d.default_id = "keep-running";
    return d;
}

Dialog task_running_view() {
    Dialog d;
    d.id = "task-running";
    d.title = tr("dialog.task_running_title", "Task running");
    d.text = tr("dialog.task_running_text", "Wait for this task to finish, or cancel it first. The launcher stays open "
                                            "so that cleaning up and logging can finish.");
    d.buttons.push_back(button("message-ok", tr("common.ok", "OK")));
    d.cancel = d.default_id = "message-ok";
    return d;
}

Dialog setup_confirm_view() {
    Dialog d;
    d.id = "setup";
    d.title = tr("dialog.setup_title", "Set Up Game");
    d.text = tr("dialog.setup_text",
                "The launcher will download missing tools, build the game from your archive, and install it. This "
                "first setup needs internet, at least 30 GB of free space and may take a while. Your original archive "
                "is kept. Continue?");
    d.buttons.push_back(button("setup-cancel", tr("common.cancel", "Cancel")));
    Action ok = button("setup-confirm", tr("common.ok", "OK"));
    ok.primary = true;
    d.buttons.push_back(ok);
    d.cancel = d.default_id = "setup-cancel";
    return d;
}

Dialog message_view(const std::string& title, const std::string& text) {
    Dialog d;
    d.id = "message";
    d.title = title;
    d.text = text;
    d.buttons.push_back(button("message-ok", tr("common.ok", "OK")));
    d.cancel = d.default_id = "message-ok";
    return d;
}

} // namespace launcher::model
