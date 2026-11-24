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
    if (why.empty()) return title + ".";
    std::string lower = why;
    if (!lower.empty() && lower[0] >= 'A' && lower[0] <= 'Z' &&
        !(lower.size() > 1 && lower[1] >= 'A' && lower[1] <= 'Z')) {
        lower[0] = static_cast<char>(lower[0] - 'A' + 'a');
    }
    return title + ": " + lower;
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

// Why a game action waits: the task that runs, the game that runs, the kit.
std::string task_why(const char* then) {
    return refusal_sentence("Another task is running", std::string("Wait for it to end, then ") + then + ".");
}

const char* const kBuilderMissing = "The game builder is missing from this launcher.";

void installed(const Facts& facts, GameView& v) {
    const bool playing = facts.game_running;
    const bool task = facts.task.has_value();
    v.state = GameState::kInstalled;
    v.folder = path_utf8(facts.install.folder);
    v.pill.text = playing                                            ? "Running"
                  : task && facts.task->kind == TaskKind::kUpdate    ? "Updating"
                  : task && facts.task->kind == TaskKind::kUninstall ? "Uninstalling"
                                                                     : "Installed";
    v.pill.kind = task && !playing ? PillKind::kNeutral : PillKind::kOk;
    if (playing && !facts.game_started_here && facts.caps.game_outside) {
        Line l = note_line(Icon::kInfo, "It was started outside the launcher. Quit it to update or uninstall it.",
                           false, Tone::kDim);
        l.tone = Tone::kDim;
        l.small = true;
        v.body.push_back(l);
    }
    const bool update = update_ready(facts);
    const std::string older = older_game(facts);
    // (Windows builds it from the .wua chosen in Folders: the Tk window's words.)
    const std::string again = facts.caps.windows
                                  ? " Update builds it again on this PC from your game: a few minutes."
                                  : " Update builds it again from the game in its folder: a few minutes.";
    if (!older.empty()) {
        Line l = note_line(Icon::kWarning, older + again, true);
        l.tone = Tone::kDim;
        l.small = true;
        v.body.push_back(l);
    } else if (update) {
        Line l = note_line(Icon::kInfo,
                           facts.game_built.empty()
                               ? "This game program was not built by the launcher. Update builds it again from the "
                                 "game in its folder."
                           : facts.caps.windows
                               ? "An update of the game is ready (Ultimate Launcher " + shown_build(facts.this_build) +
                                     "; the game is from " + shown_build(facts.game_built) + ")." + again
                               : "An update of the game program is ready (" + facts.this_build + ", installed " +
                                     facts.game_built + ")." + again,
                           true);
        l.tone = Tone::kDim;
        l.small = true;
        v.body.push_back(l);
    }
    if (!facts.game_error.empty()) v.body.push_back(text_line(facts.game_error, Tone::kError));

    const std::string busy_why = playing ? refusal_sentence("The game is running", "Quit it, then update.")
                                 : task  ? task_why("update")
                                         : kBuilderMissing;
    const auto update_button = [&](bool primary) {
        Action b = button("update", "Update", !playing && !task && facts.builder, busy_why,
                          "Build the game program again with this launcher's version");
        if (primary) {
            b.primary = true;
            b.icon = Icon::kUpdate;
        }
        b.describe.more.push_back(older.empty() ? "" : older);
        if (b.describe.more.back().empty()) b.describe.more.pop_back();
        v.actions.push_back(b);
    };
    if (!older.empty()) {
        update_button(true);
    } else {
        Action play =
            button("play", playing ? "Playing" : "Play", !playing && !task,
                   playing ? refusal_sentence("The game is running", "Only one can run at a time.")
                   : facts.task && facts.task->kind == TaskKind::kShaders
                       ? std::string("The game starts by itself once its shaders are ready.")
                       : task_why("play"));
        play.primary = true;
        play.icon = Icon::kPlay;
        play.describe.state = playing ? "Running" : "";
        v.actions.push_back(play);
    }
    Action settings = button("settings", "", true, {}, "Settings");
    settings.icon = Icon::kSettings;
    settings.describe.title = "Settings";
    v.actions.push_back(settings);
    if (update && older.empty()) update_button(false);
    v.spacer = v.actions.size();
    Action open = button("open-folder", "", true, {}, "Open the install folder");
    open.icon = Icon::kFolder;
    open.describe.title = "Open the install folder";
    open.describe.path = path_utf8(facts.install.folder);
    v.actions.push_back(open);
    if (facts.caps.uninstall) {
        Action u = button("uninstall", "Uninstall…", !playing && !task,
                          playing ? refusal_sentence("The game is running", "Quit it, then uninstall.")
                                  : task_why("uninstall"));
        u.destructive = true;
        u.describe.path = path_utf8(facts.install.folder);
        v.actions.push_back(u);
    }
}

void unfinished(const Facts& facts, GameView& v) {
    const bool task = facts.task.has_value();
    v.state = GameState::kNotFinished;
    v.folder = path_utf8(facts.install.folder);
    v.pill = {"Not finished", PillKind::kWarn, {}};
    v.body.push_back(
        text_line("The install stopped before it was complete. Resume it to finish: the files copied so far are kept.",
                  Tone::kDim));
    if (!facts.game_error.empty()) v.body.push_back(text_line(facts.game_error, Tone::kError));
    Action resume = button("resume", "Resume", !task && facts.builder, task ? task_why("install") : kBuilderMissing);
    resume.primary = true;
    resume.describe.path = path_utf8(facts.install.folder);
    v.actions.push_back(resume);
    v.spacer = v.actions.size();
    if (facts.caps.uninstall) {
        Action u = button("uninstall", "Uninstall…", !task, task_why("uninstall"));
        u.destructive = true;
        u.describe.path = path_utf8(facts.install.folder);
        v.actions.push_back(u);
    }
}

void not_installed(const Facts& facts, GameView& v) {
    const bool task = facts.task.has_value();
    v.state = GameState::kNotInstalled;
    v.pill = {"Not installed", PillKind::kNeutral, {}};
    if (facts.caps.setup_game) {
        v.body.push_back(note_line(Icon::kInfo,
                                   "Set Up Game asks for your own European Wii U archive (.wua) with update v16 and a "
                                   "folder. It downloads what it needs, builds the game on this PC from your copy and "
                                   "installs it: about 30 GB, and a while. Your archive is kept.",
                                   false));
        Action setup = button("setup", "Set Up Game…", !task, task_why("set up the game"));
        setup.primary = true;
        v.actions.push_back(setup);
        return;
    }
    v.body.push_back(text_line("Install it from your own copy of TEKKEN TAG TOURNAMENT 2 Wii U EDITION (European, with "
                               "update 16) as a .wua archive. The launcher builds the game program for this PC from "
                               "it, then copies the game into a folder you choose (about 16 GB).",
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
        v.body.push_back(text_line("The game builder is missing from this launcher" +
                                       (facts.kit.empty() ? std::string() : " (" + path_utf8(facts.kit) + ")") +
                                       ": the game cannot be installed.",
                                   Tone::kError));
    }
    if (!facts.game_error.empty()) v.body.push_back(text_line(facts.game_error, Tone::kError));
    Action install = button("install", "Install…", facts.builder && !task,
                            !facts.builder ? std::string(kBuilderMissing) : task_why("install"));
    install.primary = true;
    if (!facts.chosen_game.empty()) install.describe.path = path_utf8(facts.chosen_game);
    v.actions.push_back(install);
}

void installing(const Facts& facts, GameView& v) {
    v.state = GameState::kInstalling;
    v.folder = path_utf8(facts.installing);
    v.pill = {"Installing", PillKind::kNeutral, {}};
    v.body.push_back(text_line("The game program is built for this PC from your game, then the game is copied into "
                               "this folder. Stopping keeps what is copied: the install resumes from there.",
                               Tone::kDim));
}

void preflight(const Facts& facts, GameView& v) {
    const Preflight& p = *facts.preflight;
    v.state = p.running ? GameState::kChecking : GameState::kCannotInstall;
    v.folder = path_utf8(p.folder);
    v.pill = {p.running ? "Checking" : "Cannot install yet", p.running ? PillKind::kNeutral : PillKind::kBad, {}};
    if (p.running) {
        Line l;
        l.kind = Line::Kind::kSpinner;
        l.text = "Checking this PC…";
        l.tone = Tone::kDim;
        v.body.push_back(l);
        return;
    }
    v.body.push_back(text_line("Before the install can start:", Tone::kDim));
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
            Action copy = button("copy:" + c.command, "", true, {}, "Copy");
            copy.icon = Icon::kCopy;
            copy.flat = true;
            copy.describe.title = "Copy the command";
            copy.describe.more.push_back(c.command);
            l.actions.push_back(copy);
        }
        v.body.push_back(l);
    }
    Action again = button("check-again", "Check Again");
    again.primary = true;
    v.actions.push_back(again);
    v.actions.push_back(button("preflight-cancel", "Cancel"));
}

// Windows: More, and its menu.
void more(const Facts& facts, GameView& v) {
    if (!facts.caps.more_menu) return;
    const bool task = facts.task.has_value();
    const bool is_installed = facts.install.state == InstallState::kInstalled;
    Action m = button("more", "More", !task, task_why("build or install"), "Build, install and the logs");
    m.kind = ActionKind::kMenu;
    m.icon = Icon::kMore;
    v.actions.push_back(m);
    const auto entry = [&](std::string id, std::string label, bool enabled, std::string why) {
        Action a = button(std::move(id), std::move(label), enabled, std::move(why));
        a.kind = ActionKind::kMenuItem;
        v.more.push_back(a);
    };
    entry("more:build", "Build / Rebuild", true, {});
    entry("more:install", "Install from Wii U Source", true, {});
    entry("more:update", "Update Installed Game", is_installed, "Choose a complete installation before updating.");
    if (is_installed) entry("more:setup-again", "Set Up Again…", true, {});
    entry("more:open-logs", "Open Logs Folder", true, {});
    entry("more:latest-log", "Open Latest Log", true, {});
}

// What each of the game's actions does, said on the blue side beside it (the Tag Split's readout; the GTK
// window had only tooltips): as the mock's texts (concepts/tagsplit2), from the facts.
void explain(const Facts& facts, GameView& v) {
    const auto shown = [](const fs::path& p) { return shown_path(p); };
    const bool task = facts.task.has_value();
    for (Action& a : v.actions) {
        std::string& x = a.describe.explain;
        if (a.id == "play") {
            x = facts.game_running ? "Tekken Tag Tournament 2 is running. Update and Uninstall wait until it is closed."
                                   : "Starts Tekken Tag Tournament 2 with the Display settings and keys as they are now.";
        } else if (a.id == "update") {
            x = older_game(facts).empty()
                    ? "Builds the game program again with this launcher's version: a few minutes. The game and your "
                      "saves stay as they are."
                    : "Builds the game again with this launcher's version (" +
                          std::string(launcher_version(facts.this_build)) +
                          "): a few minutes. Then it can be played, and fighters added or updated.";
        } else if (a.id == "settings") {
            x = facts.install.state == InstallState::kInstalled
                    ? "Display and keyboard, which the game uses when it starts, and the launcher's own sounds, "
                      "motion and button prompts."
                    : "The launcher's own sounds, motion and button prompts. Display and keyboard come with the game.";
        } else if (a.id == "open-folder") {
            x = "Opens " + shown(facts.install.folder) + " in the file manager.";
        } else if (a.id == "uninstall") {
            x = "Deletes the game and its program from this folder. It asks first: your saves and the added "
                "characters can stay.";
            if (facts.game_running) x += " Not while the game is running: close it first.";
            else if (task) x += " Not while a task is running.";
        } else if (a.id == "resume") {
            x = "Finishes the install into " + shown(facts.install.folder) + ": the files copied so far are kept.";
        } else if (a.id == "install") {
            x = facts.chosen_game.empty()
                    ? "Asks for your .wua first, then checks this PC and installs."
                    : "Checks this PC, then builds the game program from " + path_utf8(facts.chosen_game.filename()) +
                          " and copies the game into the folder chosen.";
        } else if (a.id == "check-again") {
            x = "Checks this PC again: the install starts once everything is ready.";
        } else if (a.id == "preflight-cancel") {
            x = "Goes back without installing.";
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
    // Settings: always there (U17: the launcher's own settings with any state of the game; the game's when
    // installed, on Windows also before Set Up Game, for its folders).
    if (v.state != GameState::kInstalled && v.state != GameState::kChecking && v.state != GameState::kCannotInstall) {
        Action settings;
        settings.id = "settings";
        settings.icon = Icon::kSettings;
        settings.tooltip = "Settings";
        settings.describe.title = "Settings";
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
    b.note = std::string("The Wii U game as a native ") + facts.caps.platform_name +
             " program, built on this PC from your own copy, with Tekken 7's and Tekken 8's characters added from "
             "yours.";
    b.icon = facts.icon && facts.install.state == InstallState::kInstalled;
    return b;
}

Header header_view(const Facts& facts, bool in_settings) {
    Header h;
    h.title = in_settings ? "Settings" : "Ultimate Launcher";
    if (in_settings) {
        Action back = button("back", "", true, {}, "Back");
        back.icon = Icon::kBack;
        back.describe.title = "Back";
        h.actions.push_back(back);
        return h;
    }
    Action refresh = button("refresh", "", true, {}, "Check again");
    refresh.icon = Icon::kRefresh;
    refresh.describe.title = "Check again";
    h.actions.push_back(refresh);
    if (facts.self_update) {
        const bool newer = facts.newer.has_value();
        const bool test_build = facts.caps.branch_updates && !facts.windows.branch.empty();
        std::string tip = newer ? "Update the launcher to version " + facts.newer->version + " (this is version " +
                                      facts.launcher_version + ")"
                          : test_build ? "Update the launcher from " + facts.windows.branch + " (this is " +
                                             facts.launcher_version + ", " + facts.windows.commit.substr(0, 7) + ")"
                                       : "Update the launcher (this is version " + facts.launcher_version + ")";
        Action update = button("update-launcher", "", true, {}, tip);
        update.icon = Icon::kUpdate;
        update.describe.title = "Update the launcher";
        update.describe.explain = tip;
        h.actions.push_back(update);
        h.update_offered = newer || (test_build && facts.main_news && facts.main_news->ahead > 0);
    }
    return h;
}

NoticeView notice_view(const Facts& facts) {
    NoticeView n;
    const bool task = facts.task.has_value();
    n.update = button("notice-update", "Update", !task, task_why("update the launcher"));
    n.update.primary = true;
    if (facts.newer) {
        n.update.describe.explain = "Downloads version " + facts.newer->version +
                                    (facts.caps.windows ? ", checks it, then it replaces this launcher and opens."
                                                        : ", checks it, then it replaces this AppImage and opens.");
    }
    const auto page = [&](const std::string& link, bool shown) {
        if (!shown) return;
        Action p = button("release-page", "What's New");
        p.describe.path = link;
        p.describe.explain = "Opens the release page of " + (facts.newer ? facts.newer->version : std::string()) +
                             " in the browser.";
        n.page = p;
    };
    if (facts.self_update && facts.newer) {
        n.shown = true;
        n.title = "Version " + facts.newer->version + " of the launcher is out";
        const std::string have = facts.caps.windows && facts.newer->version == facts.launcher_version
                                     ? std::string("a test build of it")
                                     : facts.launcher_version;
        n.detail = "You have " + have + ". Update replaces this " + (facts.caps.windows ? "launcher" : "AppImage") +
                   " with it and opens it.";
        page(facts.newer->page,
             facts.newer->page.starts_with("https://") || (facts.custom_releases && !facts.newer->page.empty()));
    } else if (facts.self_update && facts.caps.branch_updates && !facts.windows.branch.empty() && facts.main_news &&
               facts.main_news->ahead > 0) {
        const MainNews& news = *facts.main_news;
        n.shown = true;
        n.title = "Newer changes are on " + facts.windows.branch;
        const std::string newest = news.changes.empty() ? "" : ", the newest: “" + news.changes[0] + "”";
        n.detail = std::to_string(news.ahead) + " change" + (news.ahead == 1 ? "" : "s") + " since this test build (" +
                   facts.launcher_version + ", " + facts.windows.commit.substr(0, 7) + ")" + newest +
                   ". Update gets them without a new .exe.";
        page(news.page, news.page.starts_with("https://") || facts.custom_github);
    }
    return n;
}

// ---------------------------------------------------------------- dialogs

Dialog uninstall_view(const Facts& facts, const fs::path& saves, bool saves_custom, const UninstallChoice& choice) {
    Dialog d;
    d.id = "uninstall";
    d.title = "Uninstall Tekken Tag Tournament 2?";
    d.text = "This deletes the game, its program and its menu entry from this folder; anything else in it stays:";
    d.lines.push_back(text_line(path_utf8(facts.install.folder), Tone::kPath));
    const auto check = [&](std::string id, std::string label, bool on) {
        Action a = button(std::move(id), std::move(label));
        a.kind = ActionKind::kCheck;
        a.checked = on;
        a.describe.state = on ? "On" : "Off";
        Line l;
        l.actions.push_back(a);
        return l;
    };
    Line s = check("uninstall-saves", "Also delete saves", choice.saves);
    s.actions[0].describe.path = path_utf8(saves);
    if (saves_custom)
        s.actions[0].describe.more.push_back("Only the game's saves in it are deleted; anything else there stays.");
    d.lines.push_back(s);
    d.lines.push_back(text_line(path_utf8(saves), Tone::kPath));
    if (saves_custom) {
        d.lines.push_back(
            text_line("Only the game's saves in it are deleted; anything else there stays.", Tone::kDim, true));
    }
    d.lines.push_back(check("uninstall-characters",
                            "Also delete added characters and what was saved from Tekken 7 and Tekken 8",
                            choice.characters));
    d.buttons.push_back(button("uninstall-cancel", "Cancel"));
    Action u = button("uninstall-confirm", "Uninstall");
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
    d.title = "Remove all " + std::to_string(names.size()) + " " + name + " characters?";
    d.text = name + " is not installed, so they cannot be added again until it is.";
    d.buttons.push_back(button("remove-all-cancel", "Cancel"));
    Action r = button("remove-all-confirm", "Remove All");
    r.destructive = true;
    d.buttons.push_back(r);
    d.cancel = d.default_id = "remove-all-cancel";
    return d;
}

Dialog stop_and_quit_view(const std::string& task_title) {
    Dialog d;
    d.id = "stop-and-quit";
    d.title = "Stop and quit?";
    d.text = task_title + " is not finished. Stop it and close the launcher?";
    d.buttons.push_back(button("keep-running", "Keep Running"));
    Action s = button("stop-and-quit", "Stop and Quit");
    s.destructive = true;
    d.buttons.push_back(s);
    d.cancel = d.default_id = "keep-running";
    return d;
}

Dialog task_running_view() {
    Dialog d;
    d.id = "task-running";
    d.title = "Task running";
    d.text = "Wait for this task to finish, or cancel it first. The launcher stays open so that cleaning up and "
             "logging can finish.";
    d.buttons.push_back(button("message-ok", "OK"));
    d.cancel = d.default_id = "message-ok";
    return d;
}

Dialog setup_confirm_view() {
    Dialog d;
    d.id = "setup";
    d.title = "Set Up Game";
    d.text = "The launcher will download missing tools, build the game from your archive, and install it. This first "
             "setup needs internet, at least 30 GB of free space and may take a while. Your original archive is kept. "
             "Continue?";
    d.buttons.push_back(button("setup-cancel", "Cancel"));
    Action ok = button("setup-confirm", "OK");
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
    d.buttons.push_back(button("message-ok", "OK"));
    d.cancel = d.default_id = "message-ok";
    return d;
}

} // namespace launcher::model
