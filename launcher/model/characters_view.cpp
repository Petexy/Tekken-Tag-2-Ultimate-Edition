// The characters' card (launcher/app/characters.cpp's show_characters,
// outfits_line, game_section, dlc_section and fighter_row): Tekken 7,
// Tekken 8 and Steam as the importer finds them, what is missing to import,
// each game's characters and Tekken 7's DLC.

#include "builders.h"
#include "rules.h"

#include <cstdio>

namespace launcher::model {

Line install_hint(const Distro& distro, const std::vector<Package>& packages, const std::string& what,
                  const char* fallback) {
    if (image_based(distro)) return text_line(image_based_hint(what), Tone::kDim, true);
    const std::string command = install_command(distro, packages);
    if (command.empty()) return text_line(fallback, Tone::kDim, true);
    Line l;
    l.kind = Line::Kind::kCommand;
    l.text = command;
    Action copy;
    copy.id = "copy:" + command;
    copy.icon = Icon::kCopy;
    copy.flat = true;
    copy.tooltip = "Copy";
    copy.describe.title = "Copy the command";
    copy.describe.more.push_back(command);
    l.actions.push_back(copy);
    return l;
}

namespace {

Action button(std::string id, std::string label, bool enabled, std::string why = {}, std::string tooltip = {}) {
    Action a;
    a.id = std::move(id);
    a.label = std::move(label);
    a.enabled = enabled;
    a.tooltip = std::move(tooltip);
    a.why = enabled ? std::string() : std::move(why);
    a.describe.title = a.label;
    a.describe.why = a.why;
    return a;
}

std::string task_why(const char* then) {
    return refusal_sentence("Another task is running", std::string("Wait for it to end, then ") + then + ".");
}

// "Reina fights", "2 characters fight".
std::string who_fights(const std::vector<const Fighter*>& who) {
    return who.size() == 1 ? who[0]->display + " fights" : std::to_string(who.size()) + " characters fight";
}

// Why an import button of a game is disabled, when nothing else says: the
// task, the game, what the button's own rule says.
std::string game_why(const Facts& facts, const std::string& game) {
    std::string why;
    if (facts.task) return task_why("add characters");
    if (!game_usable(facts, game, &why)) return why;
    return {};
}

FighterRow fighter_row(const Facts& facts, const Fighter& f, bool usable) {
    FighterRow r;
    r.name = f.name;
    r.display = f.display;
    const bool task = facts.task.has_value();
    const std::optional<bool> owned = owns(facts, f);
    const bool choosable = outfits_choosable(f, owned);
    if (choosable || (f.outfits > 0 && f.added())) {
        Action o;
        o.id = "outfits:" + f.name;
        o.label = "Outfits";
        o.kind = ActionKind::kCheck;
        o.checked = choosable ? wants_outfits(facts, f) : f.outfits_added;
        o.enabled = choosable && !task;
        const std::string count = std::to_string(f.outfits);
        o.tooltip = !f.added() || f.update
                        ? "Also make their " + count + " outfits for the costume chooser: adding them takes much longer"
                    : !choosable      ? (f.outfits_added ? "Their pack has their outfits" : "Their pack has no outfits")
                    : f.outfits_added ? "Their pack has their outfits: untick, then Update, to remove them"
                                      : "Tick, then Update, to add their " + count + " outfits (it takes much longer)";
        o.why = o.enabled ? "" : task ? task_why("change outfits") : o.tooltip;
        o.describe.title = f.display + ": outfits";
        o.describe.state = o.checked ? "On" : "Off";
        o.describe.explain = o.tooltip;
        o.describe.why = o.why;
        r.outfits = o;
    }
    if (f.outdated) {
        r.pill = Pill{"Older version", PillKind::kWarn,
                      "Made by an older version: the game leaves them out until they are added again."};
    } else if (f.newer) {
        r.pill = Pill{"Newer version", PillKind::kWarn,
                      "Made by a newer version of Golden Fist Launcher: the game leaves them out until it is updated."};
    } else if (f.update && !(f.stand_in && !addable(facts, f))) {
        r.pill = Pill{"Update ready", PillKind::kWarn,
                      f.stand_in ? "They fight with Heihachi's moves: updating them gives them their own."
                                 : "Made by an older version: they are in the game, and updating them gives them what "
                                   "this version adds."};
    } else if (outfits_changed(facts, f)) {
        r.pill = f.outfits_added ? Pill{"Outfits to remove", PillKind::kWarn, "Update them to remove their outfits."}
                                 : Pill{"Outfits to add", PillKind::kWarn, "Update them to add their outfits."};
    } else if (f.stand_in) {
        r.pill = Pill{"Heihachi's moves", PillKind::kNeutral,
                      "They fight with Heihachi's moves until their own can be saved (see above)."};
    } else if (f.added() && newer_on_main(facts, f.name)) {
        const std::string& branch = facts.caps.branch_updates ? facts.windows.branch : std::string();
        r.pill = branch.empty() ? Pill{"Newer on main", PillKind::kNeutral,
                                       "Main has an update for them: it comes with the next release."}
                                : Pill{"Newer on " + branch, PillKind::kNeutral,
                                       branch + " has an update for them: Update the launcher, then them."};
    } else if (f.installed) {
        r.pill = Pill{"Added", PillKind::kOk, {}};
    } else if (f.dlc != 0 && owned) {
        r.state_text = *owned ? "Owned" : "Not owned";
    }

    const bool installed_game = facts.install.state == InstallState::kInstalled;
    const auto remove_button = [&](const std::string& id) {
        const std::string why = removable(facts, f);
        Action b = button(id, "Remove", !task && installed_game && why.empty(),
                          !why.empty() ? why
                          : task       ? task_why("remove characters")
                                       : "The importer, Python 3 or the installed game is missing.",
                          why);
        b.flat = true;
        b.describe.title = "Remove " + f.display;
        r.buttons.push_back(b);
    };
    const auto add_button = [&](const char* text) {
        const bool can = addable(facts, f);
        const std::string tip = !usable  ? ""
                                : !owned ? unknown_owned_why(facts, f)
                                : can    ? ""
                                         : not_addable_why(facts, f);
        std::string why = tip;
        if (why.empty() && !usable) why = game_why(facts, f.game);
        if (why.empty() && task) why = task_why("add characters");
        Action b = button("fighter:" + f.name, text, usable && !task && can, why, tip);
        b.describe.title = std::string(text) + " " + f.display;
        r.buttons.push_back(b);
    };
    if (f.outdated || f.update || outfits_changed(facts, f)) {
        remove_button("remove:" + f.name);
        if (owned != false)
            add_button(f.outdated ? "Add Again" : "Update");
        else
            r.button_note = "Not owned";
    } else if (f.installed) {
        remove_button("fighter:" + f.name);
    } else if (owned != false) {
        add_button("Add");
    }
    r.describe.title = f.display;
    r.describe.state = r.pill ? r.pill->text : !r.state_text.empty() ? r.state_text : "Not added";
    r.describe.explain = r.pill ? r.pill->explain : "";
    if (owned == false) r.describe.more.push_back("Your Steam account does not own their DLC");
    return r;
}

// A game's DLC characters (each game's: the old launcher had only Tekken 7's apart).
void dlc_block(const Facts& facts, GameGroup& g, bool usable) {
    const ImporterStatus& s = *facts.status;
    const bool tekken8 = g.game == kTekken8;
    const bool askable = tekken8 ? s.tekken8_usable() : s.tekken7_usable();
    int dlc_count = 0, owned_count = 0, known_count = 0, dlc_outdated = 0, dlc_update = 0;
    for (const Fighter& f : s.fighters) {
        if (!f.of(g.game) || f.dlc == 0) continue;
        ++dlc_count;
        owned_count += owns(facts, f) == true;
        known_count += owns(facts, f).has_value();
        dlc_outdated += f.outdated && owns(facts, f) != false;
        dlc_update += f.update && owns(facts, f) != false;
    }
    if (dlc_count == 0) return;
    const bool known = known_count > 0;
    DlcBlock d;
    d.expander.id = tekken8 ? "dlc:tekken8" : "dlc";
    d.expander.label = "DLC characters";
    d.expander.kind = ActionKind::kExpander;
    d.expander.checked = facts.dlc_expanded;
    d.expander.describe.title = std::string(game_name(g.game)) + "'s DLC characters";
    d.pills.push_back({known ? std::to_string(owned_count) + " of " + std::to_string(dlc_count) + " owned"
                             : std::to_string(dlc_count),
                       PillKind::kNeutral,
                       {}});
    if (dlc_outdated > 0) d.pills.push_back({std::to_string(dlc_outdated) + " to add again", PillKind::kWarn, {}});
    if (dlc_update > 0) d.pills.push_back({std::to_string(dlc_update) + " to update", PillKind::kWarn, {}});
    d.expander.describe.state = d.pills[0].text;

    const Owned& o = facts.owned;
    const std::string owns_text = std::to_string(owned_count) + " of them";
    Line note;
    if (o.state == OwnedState::kChecking) {
        note.kind = Line::Kind::kSpinner;
        note.text = known ? "Asking Steam again which DLC you own (last time: " + owns_text + ")…"
                          : "Asking Steam which DLC you own…";
        note.tone = Tone::kDim;
        note.small = true;
    } else if ((o.state == OwnedState::kFailed || o.errors.count(g.game)) && askable) {
        const auto failed = o.errors.find(g.game);
        const std::string& why = failed != o.errors.end() ? failed->second : o.error;
        note = text_line(known ? "Steam could not be asked again (" + why +
                                     "). It said last time that your account owns " + owns_text + "."
                               : "Which DLC you own is not known: " + why,
                         Tone::kError, true);
    } else if (o.state == OwnedState::kKnown && known) {
        note = text_line("Your Steam account owns " + owns_text + ": only those can be added.", Tone::kDim, true);
    } else if (known) {
        note = text_line(s.steam_running ? "Your Steam account owned " + owns_text + " last time Steam was asked."
                                         : "Your Steam account owned " + owns_text +
                                               " last time Steam was asked. Start Steam" +
                                               // (a Tekken 8 one whose moves are saved is added without it)
                                               (tekken8 ? " and it checks again." : " to add them: it checks again."),
                         Tone::kDim, true);
    } else if (!s.steam_installed) {
        note = text_line("Which DLC you own is not known: Steam, which tells it, is not installed.", Tone::kDim, true);
    } else if (!askable) {
        note = text_line("Which DLC you own is not known: Steam is asked through " +
                             std::string(game_name(g.game)) + ", which " +
                             ((tekken8 ? s.tekken8_found : s.tekken7_found) ? "cannot be used (see above)." : "is not installed."),
                         Tone::kDim, true);
    } else {
        note = text_line(s.steam_running ? "Which DLC you own is not known yet."
                                         : "Start Steam to see which DLC you own: only those can be added.",
                         Tone::kDim, true);
    }
    d.notes.push_back(note);
    d.expander.describe.explain = note.text;
    const auto owned = owned_to_add(facts, g.game);
    std::string why = facts.task ? task_why("add characters") : game_why(facts, g.game);
    if (why.empty() && owned.empty()) why = "No owned DLC character can be added now.";
    d.add_owned = button(tekken8 ? "add-all-owned:tekken8" : "add-all-owned", "Add All Owned",
                         usable && !facts.task && !owned.empty(), why);
    d.add_owned.describe.title = "Add All Owned: " + d.expander.describe.title;
    for (const Fighter& f : s.fighters) {
        if (f.of(g.game) && f.dlc != 0) d.rows.push_back(fighter_row(facts, f, usable));
    }
    g.dlc = d;
}

GameGroup game_group(const Facts& facts, const std::string& game) {
    const ImporterStatus& s = *facts.status;
    const bool tekken8 = game == kTekken8;
    const bool usable = game_usable(facts, game);
    const bool task = facts.task.has_value();
    const bool installed_game = facts.install.state == InstallState::kInstalled;
    GameGroup g;
    g.game = game;
    g.heading = std::string(game_name(game)) + "'s characters";
    g.about = std::string("They join the roster beside the game's own fighters. Each takes a few minutes; the first "
                          "time, ") +
              game_name(game) + " runs hidden in the background to save their moves.";
    int base_count = 0;
    for (const Fighter& f : s.fighters) base_count += f.of(game) && f.dlc == 0;
    if (!tekken8 || base_count > 1) {
        const auto base = base_to_add(facts, game);
        std::string why = task ? task_why("add characters") : game_why(facts, game);
        if (why.empty() && base.empty()) why = "Every character that can be added now is added.";
        Action add_all =
            button(tekken8 ? "add-all:tekken8" : "add-all", "Add All", usable && !task && !base.empty(), why);
        add_all.describe.title = "Add All: " + g.heading;
        g.head.push_back(add_all);
    }
    if (const auto all = to_remove_all(facts, game); !all.empty()) {
        Action remove_all =
            button("remove-all:" + game, "Remove All", !task && installed_game, task_why("remove characters"));
        remove_all.flat = true;
        remove_all.describe.title = "Remove All: " + g.heading;
        remove_all.describe.explain =
            std::string(game_name(game)) + " is not installed, so they cannot be added again until it is.";
        g.head.push_back(remove_all);
    }
    if (const std::string other = shared_blocker(facts, game); !other.empty() && installed_game) {
        g.notes.push_back(note_line(Icon::kWarning, shared_needs(other), true));
    }

    std::vector<const Fighter*> outdated, newer;
    for (const Fighter& f : s.fighters) {
        if (!f.of(game)) continue;
        if (f.outdated && owns(facts, f) != false) outdated.push_back(&f);
        if (f.newer) newer.push_back(&f);
    }
    const auto warn_line = [&](const std::vector<const Fighter*>& who, const char* made, const char* todo) {
        if (who.empty()) return;
        const std::string text =
            who.size() == 1
                ? who[0]->display + " was made by " + made + " and is not in the game: "
                : std::to_string(who.size()) + " characters were made by " + made + " and are not in the game: ";
        g.notes.push_back(note_line(Icon::kWarning, text + todo, true));
    };
    warn_line(outdated, "an older version", "add them again.");
    warn_line(newer, "a newer version of Golden Fist Launcher", "update it, then the game, to play them.");

    if (tekken8 && usable) {
        std::vector<const Fighter*> stand_ins, unsaved;
        for (const Fighter& f : s.fighters) {
            if (!f.of(game)) continue;
            if (f.stand_in)
                stand_ins.push_back(&f);
            else if (!f.installed && !f.moveset_saved && owns(facts, f) != false)
                unsaved.push_back(&f);
        }
        const MovesBlock block = moves_block(facts);
        if (!stand_ins.empty()) {
            const auto names = to_update(facts, game, true);
            bool known = true;
            for (const Fighter* f : stand_ins) known = known && f->update;
            std::string text = who_fights(stand_ins) + " with Heihachi's moves for now: ";
            if (!known) {
                text += std::string(kUnknownBuild) + ". A later version of it can.";
            } else {
                text += stand_ins.size() == 1 ? "their own could not be saved from Tekken 8 when they were added."
                                              : "theirs could not be saved from Tekken 8 when they were added.";
                text += !names.empty()                ? " Update to give them their own."
                        : block == MovesBlock::kSteam ? " Start Steam to update."
                        : block == MovesBlock::kTools ? " Install what is missing above to update."
                        : block == MovesBlock::kRun   ? " To update: " + sentence(s.tekken8_run_error) + "."
                                                      : "";
            }
            Line line = note_line(Icon::kInfo, text, false);
            if (!names.empty()) {
                line.actions.push_back(button("update-stand-ins", names.size() == 1 ? "Update" : "Update All", !task,
                                              task_why("update characters")));
            }
            g.notes.push_back(line);
        }
        if (!unsaved.empty() && block != MovesBlock::kNone && block != MovesBlock::kSteam) {
            const std::string fix = block == MovesBlock::kRun ? s.tekken8_run_error : "install what is missing above";
            const std::string text = block == MovesBlock::kBuild
                                         ? std::string(kUnknownBuild) + ": added now, " + who_fights(unsaved) +
                                               " with Heihachi's moves until a later version of it can save their own."
                                         : "Their moves cannot be saved from Tekken 8 now: " + fix + ". Added now, " +
                                               who_fights(unsaved) + " with Heihachi's moves until updated.";
            g.notes.push_back(note_line(Icon::kInfo, text, false));
        }
    }

    std::vector<const Fighter*> updates;
    for (const Fighter& f : s.fighters) {
        if (f.of(game) && f.update && !f.stand_in && owns(facts, f) != false) updates.push_back(&f);
    }
    if (!updates.empty()) {
        const std::string who =
            updates.size() == 1 ? updates[0]->display + " was" : std::to_string(updates.size()) + " characters were";
        Line line = note_line(Icon::kUpdate,
                              who + " made by an older version: update " + (updates.size() == 1 ? "them" : "them all") +
                                  " to get what this one adds.",
                              true);
        const auto names = to_update(facts, game);
        std::string tip;
        if (usable && names.empty()) {
            tip = !tekken8                                ? "Start Steam: Tekken 7 needs it"
                  : !owns(facts, *updates[0]).has_value() ? unknown_owned_why(facts, *updates[0])
                                                          : not_addable_why(facts, *updates[0]);
        }
        std::string why = !tip.empty() ? tip : task ? task_why("update characters") : game_why(facts, game);
        line.actions.push_back(button(tekken8 ? "update-all:tekken8" : "update-all",
                                      updates.size() == 1 ? "Update" : "Update All", usable && !task && !names.empty(),
                                      why, tip));
        g.notes.push_back(line);
    }

    for (const Fighter& f : s.fighters) {
        if (f.of(game) && f.dlc == 0) g.rows.push_back(fighter_row(facts, f, usable));
    }
    dlc_block(facts, g, usable);
    return g;
}

void outfits_line(const Facts& facts, CharactersView& v) {
    const auto choices = outfit_choices(facts);
    if (choices.empty()) return;
    const bool task = facts.task.has_value();
    size_t wanted = 0, making = 0;
    std::vector<const Fighter*> changed;
    for (const Fighter* f : choices) {
        wanted += wants_outfits(facts, *f);
        making += wants_outfits(facts, *f) && (!f->added() || f->update || !f->outfits_added);
        if (outfits_changed(facts, *f)) changed.push_back(f);
    }
    Action every;
    every.id = "outfits-all";
    every.label = "Import outfits for every character";
    every.kind = ActionKind::kCheck;
    every.checked = wanted == choices.size();
    every.inconsistent = wanted > 0 && wanted < choices.size();
    every.enabled = !task;
    every.why = task ? task_why("change outfits") : "";
    every.tooltip = "Outfits are complete bodies for the in-game costume chooser. Without them, a character has their "
                    "default costume.";
    every.describe.title = every.label;
    every.describe.state = every.checked ? "All" : every.inconsistent ? "Some" : "None";
    every.describe.explain = every.tooltip;
    every.describe.why = every.why;
    v.outfits_all = every;
    if (making > 0) {
        v.outfits_notes.push_back(note_line(Icon::kWarning,
                                            "Importing outfits can drastically prolong adding and updating characters: "
                                            "each outfit is a complete extra body made from your Tekken 7's files.",
                                            true));
    }
    if (changed.empty()) return;
    const std::string text =
        changed.size() > 1 ? std::to_string(changed.size()) + " characters' outfits change when they are updated."
        : changed[0]->outfits_added ? changed[0]->display + "'s outfits are removed when they are updated."
                                    : changed[0]->display + "'s outfits are added when they are updated.";
    Line line = note_line(Icon::kUpdate, text, true);
    const auto names = outfits_to_change(facts);
    std::string why_import;
    const bool importable = can_import(facts, &why_import);
    const std::string tip = importable && names.empty() ? not_addable_why(facts, *changed[0]) : "";
    const std::string why = !tip.empty() ? tip : task ? task_why("update characters") : why_import;
    line.actions.push_back(button("update-outfits", changed.size() == 1 ? "Update" : "Update All",
                                  importable && !task && !names.empty(), why, tip));
    v.outfits_notes.push_back(line);
}

// One button for every game's characters: each game's own and the owned DLC ones, from the games that can be used.
void add_all_owned(const Facts& facts, CharactersView& v) {
    const auto names = all_owned_to_add(facts);
    std::string why;
    if (facts.task) {
        why = task_why("add characters");
    } else if (!can_import(facts, &why)) {
    } else if (names.empty()) {
        why = game_usable(facts, kTekken7) || game_usable(facts, kTekken8)
                  ? "Every character you own that can be added now is added."
                  : "Neither Tekken 7 nor Tekken 8 can be used to add characters now.";
    }
    Action a = button("add-all-owned:all", "Add All Owned", why.empty(), why);
    a.describe.title = "Add All Owned: every game's characters";
    a.describe.explain = "Adds every character that can be added now from the games on this PC: Tekken 7's and "
                         "Tekken 8's own, and the DLC characters your Steam account owns.";
    v.add_all_owned = a;
}

} // namespace

CharactersView characters_view(const Facts& facts) {
    CharactersView v;
    const Distro& distro = facts.distro;
    if (facts.importer.empty()) {
        v.early = true;
        v.lines.push_back(text_line("The character importer is missing from this launcher.", Tone::kError));
        return v;
    }
    if (facts.python.empty()) {
        v.early = true;
        v.lines.push_back(text_line("Python 3 is needed to add characters.", Tone::kError));
        v.lines.push_back(install_hint(distro, {Package::kPython, Package::kNumpy, Package::kPillow},
                                       "Python 3 with numpy and Pillow",
                                       "Install it with your distribution's packages."));
        return v;
    }
    if (!facts.status) {
        v.early = true;
        if (facts.status_loading) {
            Line l;
            l.kind = Line::Kind::kSpinner;
            l.text = "Looking for Tekken 7 and Tekken 8…";
            l.tone = Tone::kDim;
            v.lines.push_back(l);
        } else {
            v.lines.push_back(
                text_line("The importer cannot tell what this PC has: " + facts.status_error, Tone::kError));
        }
        return v;
    }
    const ImporterStatus& s = *facts.status;
    if (facts.install.state != InstallState::kInstalled) {
        v.lines.push_back(note_line(Icon::kInfo, set_up_first(facts, true), false));
    }
    if (const std::string older = older_game(facts); !older.empty()) {
        v.lines.push_back(note_line(Icon::kWarning, older, true));
    }

    const auto game_fact = [&](const char* name, bool usable, bool found, const std::string& path,
                               const std::string& error, const std::string& absent, bool other_usable) {
        Fact fact;
        fact.name = name;
        fact.describe.title = name;
        if (usable) {
            fact.lines.push_back(text_line(path, Tone::kPath));
            fact.describe.path = path;
            fact.describe.state = "Found";
        } else if (!found && path.empty() && other_usable) {
            fact.lines.push_back(text_line("Not installed", Tone::kDim));
            fact.describe.state = "Not installed";
        } else {
            std::string text = found ? "Found, but it cannot be used" : "Not installed";
            if (!error.empty() && error != absent) text += ": " + error;
            fact.lines.push_back(text_line(text, Tone::kError));
            fact.describe.state = text;
        }
        v.facts.push_back(fact);
    };
    game_fact("Tekken 7", s.tekken7_usable(), s.tekken7_found, s.tekken7_path, s.tekken7_error, "", s.tekken8_usable());
    game_fact("Tekken 8", s.tekken8_usable(), s.tekken8_found, s.tekken8_path, s.tekken8_error,
              "Tekken 8 is not installed in any Steam library", s.tekken7_usable());

    bool unsaved8 = false;
    for (const Fighter& f : s.fighters) unsaved8 = unsaved8 || (f.of(kTekken8) && !f.moveset_saved);
    const bool for7 = s.tekken7_found || !s.tekken8_found;
    const bool for8 = s.tekken8_usable() && unsaved8 && s.tekken8_build_known == true && s.tekken8_run_error.empty();
    const char* games = for7 && for8 ? "Tekken 7 and Tekken 8" : for8 ? "Tekken 8" : "Tekken 7";
    Fact steam;
    steam.name = "Steam";
    steam.describe.title = "Steam";
    if (!s.steam_installed) {
        steam.lines.push_back(text_line("Not installed: Tekken 7 and Tekken 8 for PC come from Steam", Tone::kError));
    } else if (s.steam_running) {
        steam.lines.push_back(text_line("Running"));
    } else if (!for7 && !for8) {
        steam.lines.push_back(text_line("Not running", Tone::kDim));
    } else {
        steam.lines.push_back(text_line("Not running", Tone::kWarning));
        const std::string why = for7 && for8 ? "Tekken 7 and Tekken 8 need it the first time, and it tells which DLC "
                                               "you own."
                                : for8       ? "Tekken 8 needs it the first time, to save their moves."
                                             : "Tekken 7 needs it the first time, and it tells which DLC you own.";
        steam.lines.push_back(text_line("Start Steam to add characters: " + why, Tone::kDim, true));
    }
    steam.describe.state = steam.lines[0].text;
    v.facts.push_back(steam);

    if (!s.game_error.empty() && facts.install.state == InstallState::kInstalled) {
        Fact game;
        game.name = "Game";
        game.describe.title = "Game";
        game.lines.push_back(text_line("The importer cannot read it: " + s.game_error, Tone::kError));
        v.facts.push_back(game);
    }

    if (facts.caps.prerequisites_listed) {
        std::vector<std::string> missing, names;
        std::vector<Package> packages;
        const bool get_packages = (!s.numpy || !s.pillow) && s.packages_gettable && facts.caps.packages_download;
        if (!s.numpy || !s.pillow) {
            missing.push_back(!s.numpy && !s.pillow ? "numpy and Pillow for Python"
                              : !s.numpy            ? "numpy for Python"
                                                    : "Pillow for Python");
            if (!get_packages) {
                names.push_back(missing.back());
                if (!s.numpy) packages.push_back(Package::kNumpy);
                if (!s.pillow) packages.push_back(Package::kPillow);
            }
        }
        if (s.gamescope.empty() && (for7 || for8)) {
            missing.push_back(std::string("gamescope (runs ") + games + " hidden)");
            names.emplace_back("gamescope");
            packages.push_back(Package::kGamescope);
        }
        if (s.pactl.empty() && (for7 || for8)) {
            missing.push_back(for7 && for8 ? "pactl (a silent sound output for them)"
                                           : "pactl (a silent sound output for it)");
            names.emplace_back("pactl");
            packages.push_back(Package::kPactl);
        }
        const bool helper7 = for7 && s.helper.empty(), helper8 = for8 && s.tekken8_helper.empty();
        if (helper7 || helper8) {
            missing.push_back(helper7 && helper8 ? "MinGW (builds small helpers for Tekken 7 and Tekken 8)"
                              : helper8          ? "MinGW (builds a small helper for Tekken 8)"
                                                 : "MinGW (builds a small helper for Tekken 7)");
            names.emplace_back("MinGW");
            packages.push_back(Package::kMingw);
        }
        if (s.tekken8_usable() && s.cc.empty()) {
            missing.push_back("a C compiler (builds two small parts of the importer for Tekken 8)");
            names.emplace_back("a C compiler");
            packages.push_back(Package::kCompiler);
        }
        if (!missing.empty()) {
            Fact needed;
            needed.name = "Missing";
            needed.describe.title = "Missing";
            std::string text;
            for (size_t i = 0; i < missing.size(); ++i) text += (i ? "\n" : "") + missing[i];
            needed.lines.push_back(text_line(text, Tone::kWarning));
            needed.describe.state = text;
            if (get_packages) {
                char size[32];
                std::snprintf(size, sizeof size, "%.0f MB", static_cast<double>(s.packages_size) / 1e6);
                Line line = text_line(std::string("Golden Fist Launcher can download them for this Python (") + size +
                                          " from PyPI, Python's package index) into a folder of its own: nothing of "
                                          "the system changes.",
                                      Tone::kDim, true);
                line.actions.push_back(
                    button("get-packages", "Download", !facts.task, task_why("download numpy and Pillow")));
                needed.lines.push_back(line);
            } else if ((!s.numpy || !s.pillow) && !s.packages_error.empty()) {
                needed.lines.push_back(text_line(
                    "Golden Fist Launcher cannot download them itself: " + s.packages_error + ".", Tone::kDim, true));
            }
            if (!names.empty()) {
                needed.lines.push_back(
                    install_hint(distro, packages, joined(names), "Install them with your distribution's packages."));
            }
            v.facts.push_back(needed);
        }
    }
    if (facts.main_news && !facts.main_news->fresh.empty()) {
        std::vector<std::string> names;
        for (const auto& [name, display] : facts.main_news->fresh) names.push_back(display);
        const std::string& branch = facts.caps.branch_updates ? facts.windows.branch : std::string();
        v.news.push_back(note_line(Icon::kInfo,
                                   branch.empty()
                                       ? "Main adds " + joined(names) + ": they come with the next release."
                                       : branch + " adds " + joined(names) + ": Update the launcher to get them.",
                                   false));
    }

    add_all_owned(facts, v);
    outfits_line(facts, v);

    if (!s.tekken7_found && s.tekken8_found) {
        v.games.push_back(game_group(facts, kTekken8));
        v.games.push_back(game_group(facts, kTekken7));
    } else {
        v.games.push_back(game_group(facts, kTekken7));
        v.games.push_back(game_group(facts, kTekken8));
    }
    return v;
}

} // namespace launcher::model
