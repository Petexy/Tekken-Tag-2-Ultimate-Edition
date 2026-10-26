// The characters' section (see launcher.h): Tekken 7, Tekken 8 and Steam as
// the importer finds them, what is missing to import, each game's characters
// (Tekken 7's DLC characters with whether the player owns them; a Tekken 8
// character added with a stand-in's moves, and why), and adding and removing
// them through import_character.py. Neither game needs the other: only what
// all added characters share is made again from each one's own game, so the
// characters of a game that is gone need it whenever another is added.

#include "launcher.h"

#include "system.h"
#include "widgets.h"

#include <algorithm>

namespace launcher {
namespace {

GtkWidget* fact_name(const char* text) {
    GtkWidget* l = ui::label(text, "dim", false);
    gtk_widget_set_valign(l, GTK_ALIGN_START);
    return l;
}

std::string display_name(const std::optional<ImporterStatus>& status, const std::string& name) {
    if (status) {
        for (const Fighter& f : status->fighters) {
            if (f.name == name) return f.display;
        }
    }
    return name;
}

std::string names_text(const std::optional<ImporterStatus>& status, const std::vector<std::string>& names) {
    if (names.size() == 1) return display_name(status, names[0]);
    return std::to_string(names.size()) + " characters";
}

// "Reina fights", "2 characters fight".
std::string who_fights(const std::vector<const Fighter*>& who) {
    return who.size() == 1 ? who[0]->display + " fights" : std::to_string(who.size()) + " characters fight";
}

const char* game_name(std::string_view game) { return game == kTekken8 ? "Tekken 8" : "Tekken 7"; }
const char* other_game(std::string_view game) { return game == kTekken8 ? kTekken7 : kTekken8; }

std::string sentence(std::string text) {
    if (!text.empty() && text[0] >= 'a' && text[0] <= 'z') text[0] = static_cast<char>(text[0] - 'a' + 'A');
    return text;
}

// What to do to get these pieces: the command that installs them, or on a
// system whose package manager cannot add to it, where they come from.
GtkWidget* install_hint(const Distro& distro, const std::vector<Package>& packages, const std::string& what,
                        const char* fallback) {
    if (image_based(distro)) return ui::label(image_based_hint(what), "small dim");
    const std::string command = install_command(distro, packages);
    return command.empty() ? ui::label(fallback, "small dim") : ui::command(command);
}

// A line of the card with an icon (dialog-warning-symbolic and the like) and
// a note, and room for a button after it.
GtkWidget* note_line(GtkWidget* card, const char* icon, const std::string& text, bool warn) {
    GtkWidget* line = ui::box(GTK_ORIENTATION_HORIZONTAL, 10, "check-row");
    GtkWidget* image = gtk_image_new_from_icon_name(icon);
    if (warn) gtk_widget_add_css_class(image, "warn");
    gtk_widget_set_valign(image, GTK_ALIGN_START);
    gtk_box_append(GTK_BOX(line), image);
    GtkWidget* note = ui::label(text);
    gtk_widget_set_hexpand(note, TRUE);
    gtk_box_append(GTK_BOX(line), note);
    gtk_box_append(GTK_BOX(card), line);
    return line;
}

// A build of Tekken 8 its helper does not know (a game update).
constexpr const char* kUnknownBuild = "Tekken 8 was updated to a version that Ultimate Launcher cannot save moves from "
                                      "yet";

// Why a game's characters cannot be added while the characters of `other`,
// a game that is gone, are in the game.
std::string shared_needs(std::string_view other) {
    const std::string name = game_name(other);
    return "The " + name + " characters added need " + name + " whenever a character is added: what all of them "
           "share is made again from each one's own game. Install " + name + " again, or remove them first.";
}

} // namespace

std::optional<bool> Launcher::owns(const Fighter& fighter) const {
    if (fighter.dlc == 0) return true;
    if (!owned_answer_) return std::nullopt;
    const auto it = owned_.find(fighter.name);
    if (it == owned_.end()) return std::nullopt;
    return it->second;
}

bool Launcher::can_import(std::string* why) const {
    const auto no = [&](const std::string& reason) {
        if (why) *why = reason;
        return false;
    };
    if (importer_.empty() || python_.empty()) return no("The character importer or Python 3 is missing.");
    if (install_.state != InstallState::kInstalled) return no("Install the game first: characters are made from it.");
    if (!status_) return no("The importer cannot tell what this PC has: " + status_error_);
    if (!status_->numpy || !status_->pillow) return no("Python needs numpy and Pillow to add characters.");
    if (!status_->game_error.empty()) return no("The importer cannot read the installed game: " + status_->game_error);
    return true;
}

std::string Launcher::shared_blocker(const std::string& game) const {
    // (Whatever is added, what the characters share is made again for all of
    // them, each from its own game.)
    if (!status_) return {};
    const std::string other = other_game(game);
    if (status_->readable(other)) return {};
    for (const Fighter& f : status_->fighters) {
        if (f.of(other) && f.added()) return other;
    }
    return {};
}

bool Launcher::game_usable(const std::string& game, std::string* why) const {
    const auto no = [&](const std::string& reason) {
        if (why) *why = reason;
        return false;
    };
    if (!can_import(why)) return false;
    const ImporterStatus& s = *status_;
    if (game == kTekken8) {
        if (!s.tekken8_usable()) return no(s.tekken8_error.empty() ? "Tekken 8 is not installed." : s.tekken8_error);
    } else if (!s.tekken7_usable()) {
        return no(s.tekken7_error.empty() ? "Tekken 7 is not installed." : s.tekken7_error);
    }
    if (const std::string other = shared_blocker(game); !other.empty()) return no(shared_needs(other));
    return true;
}

Launcher::MovesBlock Launcher::moves_block() const {
    if (!status_) return MovesBlock::kBuild;
    const ImporterStatus& s = *status_;
    if (s.tekken8_build_known != true) return MovesBlock::kBuild;
    if (!s.tekken8_run_error.empty()) return MovesBlock::kRun;
    if (s.gamescope.empty() || s.pactl.empty() || s.tekken8_helper.empty()) return MovesBlock::kTools;
    if (!s.steam_running) return MovesBlock::kSteam;
    return MovesBlock::kNone;
}

bool Launcher::addable(const Fighter& f) const {
    // (A moveset not saved yet is saved from its game, which needs Steam; a
    // DLC fighter's import asks Steam whether the DLC is owned, every time.
    // An older importer's pack is replaced, also one to update, a newer
    // one's never.)
    if ((f.added() && !f.update) || f.newer || owns(f) != true || !status_) return false;
    if (f.dlc != 0) return status_->steam_running;
    if (f.of(kTekken8)) {
        // Their moves not saved yet are saved first, with Tekken 8 running
        // hidden. When it cannot save them (a version of the game its helper
        // does not know, what runs it missing), they are added with a
        // stand-in's moves all the same, as the section says; but a pack in
        // the game is never made again with a stand-in's moves (its own, or
        // the same stand-in again).
        if (f.moveset_saved) return true;
        const MovesBlock block = moves_block();
        if (f.added()) return block == MovesBlock::kNone;
        return block != MovesBlock::kSteam;
    }
    return status_->steam_running || (f.moveset_saved && status_->heihachi_saved);
}

std::string Launcher::not_addable_why(const Fighter& f) const {
    if (f.dlc != 0) return "Start Steam: it checks that you own their DLC";
    if (!f.of(kTekken8)) return "Start Steam: Tekken 7 needs it to save their moves";
    switch (moves_block()) {
    case MovesBlock::kBuild: return kUnknownBuild;
    case MovesBlock::kRun: return sentence(status_->tekken8_run_error);
    case MovesBlock::kTools: return "Install what is missing above: it saves their moves";
    default: return "Start Steam: Tekken 8 needs it to save their moves";
    }
}

std::string Launcher::removable(const Fighter& f) const {
    // Removing a character the game loads makes what those left share again,
    // from their games: one that is gone stops it (all of that game's
    // characters go at once with Remove All).
    if (!status_ || !f.added()) return {};
    for (const Fighter& o : status_->fighters) {
        if (o.name != f.name && o.added() && !status_->readable(o.game)) {
            const char* name = game_name(o.game);
            return std::string(name) + " is needed for the " + name + " characters that stay: what they share is made "
                   "again from it" + (o.of(f.game) ? ". Remove All removes them all at once." : ".");
        }
    }
    return {};
}

std::vector<std::string> Launcher::base_to_add(const std::string& game) const {
    std::vector<std::string> names;
    if (status_) {
        for (const Fighter& f : status_->fighters) {
            if (f.of(game) && f.dlc == 0 && !f.update && addable(f)) names.push_back(f.name);
        }
    }
    return names;
}

std::vector<std::string> Launcher::owned_to_add() const {
    std::vector<std::string> names;
    if (status_) {
        for (const Fighter& f : status_->fighters) {
            if (f.of(kTekken7) && f.dlc != 0 && !f.update && addable(f)) names.push_back(f.name);
        }
    }
    return names;
}

std::vector<std::string> Launcher::to_update(const std::string& game, bool stand_ins) const {
    std::vector<std::string> names;
    if (status_) {
        for (const Fighter& f : status_->fighters) {
            if (f.of(game) && f.update && f.stand_in == stand_ins && addable(f)) names.push_back(f.name);
        }
    }
    return names;
}

std::vector<std::string> Launcher::to_remove_all(const std::string& game) const {
    // Only when the game is gone and more than one of its characters is in
    // the game: then one alone cannot go (removable), all of them can.
    std::vector<std::string> names;
    if (!status_ || status_->readable(game)) return names;
    int added = 0;
    for (const Fighter& f : status_->fighters) {
        if (!f.of(game) || !f.installed) continue;
        names.push_back(f.name);
        added += f.added();
    }
    if (added < 2) names.clear();
    return names;
}

// ---------------------------------------------------------------- the section

GtkWidget* Launcher::fighter_row(const Fighter& f, bool usable) {
    // A line each: the name, the state (added, to update, made by an older
    // version, or for the DLC's whether it is owned) and the buttons, in
    // columns.
    GtkWidget* row = ui::box(GTK_ORIENTATION_HORIZONTAL, 12);
    GtkWidget* name = ui::label(f.display, nullptr, false);
    gtk_widget_set_hexpand(name, TRUE);
    gtk_box_append(GTK_BOX(row), name);
    GtkWidget* state = ui::box(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_set_size_request(state, 96, -1);
    gtk_widget_set_halign(state, GTK_ALIGN_END);
    gtk_box_append(GTK_BOX(row), state);
    const std::optional<bool> owned = owns(f);
    GtkWidget* state_label = nullptr;
    if (f.outdated) {
        state_label = ui::label("Older version", "pill warn", false);
        ui::set_tooltip(state_label, "Made by an older version: the game leaves them out until they are added again.");
    } else if (f.newer) {
        state_label = ui::label("Newer version", "pill warn", false);
        ui::set_tooltip(state_label, "Made by a newer version of Ultimate Launcher: the game leaves them out until it "
                                     "is updated.");
    } else if (f.update && !(f.stand_in && !addable(f))) {
        // (A stand-in whose own moves cannot be saved yet is not ready: the
        // note above says what is needed first.)
        state_label = ui::label("Update ready", "pill warn", false);
        ui::set_tooltip(state_label, f.stand_in ? "They fight with Heihachi's moves: updating them gives them their "
                                                  "own."
                                                : "Made by an older version: they are in the game, and updating them "
                                                  "gives them what this version adds.");
    } else if (f.stand_in) {
        state_label = ui::label("Heihachi's moves", "pill neutral", false);
        ui::set_tooltip(state_label, "They fight with Heihachi's moves until their own can be saved (see above).");
    } else if (f.installed) {
        state_label = ui::label("Added", "pill ok", false);
    } else if (f.dlc != 0 && owned) {
        state_label = ui::label(*owned ? "Owned" : "Not owned", "small dim", false);
    }
    if (state_label) {
        gtk_widget_set_hexpand(state_label, TRUE);
        gtk_widget_set_halign(state_label, GTK_ALIGN_END);
        gtk_widget_set_valign(state_label, GTK_ALIGN_CENTER);
        gtk_box_append(GTK_BOX(state), state_label);
    }

    const auto append = [&](GtkWidget* widget) {
        g_object_set_data_full(G_OBJECT(widget), "fighter", g_strdup(f.name.c_str()), g_free);
        gtk_widget_set_size_request(widget, 88, -1);
        gtk_box_append(GTK_BOX(row), widget);
    };
    const auto remove_button = [&](const std::string& id) {
        GtkWidget* button = ui::button("Remove", "flat");
        ui::set_id(button, id);
        const std::string why = removable(f);
        gtk_widget_set_sensitive(button, !task_ && install_.state == InstallState::kInstalled && why.empty());
        if (!why.empty()) gtk_widget_set_tooltip_text(button, why.c_str());
        g_signal_connect(button, "clicked", G_CALLBACK(+[](GtkWidget* b, gpointer data) {
                             static_cast<Launcher*>(data)->start_remove(
                                 {static_cast<const char*>(g_object_get_data(G_OBJECT(b), "fighter"))});
                         }),
                         this);
        append(button);
    };
    const auto add_button = [&](const char* text) {
        GtkWidget* button = ui::button(text);
        ui::set_id(button, "fighter:" + f.name); // (the row's button: Add, then Remove)
        gtk_widget_set_sensitive(button, usable && !task_ && addable(f));
        // (When adding is impossible for another reason, the card says why above.)
        const std::string why = !usable      ? ""
                                : !owned     ? (f.of(kTekken8) ? "Which Tekken 8 DLC you own is not known yet"
                                                               : "Start Steam: it tells which DLC you own")
                                : addable(f) ? ""
                                             : not_addable_why(f);
        if (!why.empty()) gtk_widget_set_tooltip_text(button, why.c_str());
        g_signal_connect(button, "clicked", G_CALLBACK(+[](GtkWidget* b, gpointer data) {
                             static_cast<Launcher*>(data)->start_import(
                                 {static_cast<const char*>(g_object_get_data(G_OBJECT(b), "fighter"))});
                         }),
                         this);
        append(button);
    };
    if (f.outdated || f.update) {
        // (Adding them again replaces the old pack: the main button. A DLC
        // no longer owned cannot be added again, and says so there.)
        remove_button("remove:" + f.name);
        if (owned != false) {
            add_button(f.update ? "Update" : "Add Again");
        } else {
            GtkWidget* note = ui::label("Not owned", "small dim", false);
            gtk_label_set_xalign(GTK_LABEL(note), 0.5f);
            append(note);
        }
    } else if (f.installed) {
        remove_button("fighter:" + f.name);
    } else if (owned == false) {
        append(ui::box(GTK_ORIENTATION_HORIZONTAL, 0)); // (keeps the columns)
    } else {
        add_button("Add");
    }

    GtkWidget* list_row = gtk_list_box_row_new();
    gtk_list_box_row_set_activatable(GTK_LIST_BOX_ROW(list_row), FALSE);
    gtk_widget_set_focusable(list_row, FALSE);
    gtk_list_box_row_set_child(GTK_LIST_BOX_ROW(list_row), row);
    return list_row;
}

void Launcher::show_characters() {
    GtkWidget* card = characters_card_;
    const ui::Rebuild rebuild(card);
    const Distro distro = this_distro();
    if (importer_.empty()) {
        gtk_box_append(GTK_BOX(card), ui::label("The character importer is missing from this launcher.", "error-text"));
        return;
    }
    if (python_.empty()) {
        gtk_box_append(GTK_BOX(card), ui::label("Python 3 is needed to add characters.", "error-text"));
        gtk_box_append(GTK_BOX(card), install_hint(distro, {Package::kPython, Package::kNumpy, Package::kPillow},
                                                   "Python 3 with numpy and Pillow",
                                                   "Install it with your distribution's packages."));
        return;
    }
    if (!status_) {
        GtkWidget* row = ui::box(GTK_ORIENTATION_HORIZONTAL, 12);
        if (status_loading_) {
            GtkWidget* spinner = gtk_spinner_new();
            gtk_spinner_start(GTK_SPINNER(spinner));
            gtk_box_append(GTK_BOX(row), spinner);
            gtk_box_append(GTK_BOX(row), ui::label("Looking for Tekken 7 and Tekken 8…", "dim"));
        } else {
            gtk_box_append(GTK_BOX(row), ui::label("The importer cannot tell what this PC has: " + status_error_,
                                                   "error-text"));
        }
        gtk_box_append(GTK_BOX(card), row);
        return;
    }
    const ImporterStatus& s = *status_;
    if (install_.state != InstallState::kInstalled) {
        note_line(card, "dialog-information-symbolic",
                  "Install the game first: the characters are made from it and from your Tekken 7 or Tekken 8.",
                  false);
    }

    // Tekken 7, Tekken 8 and Steam. (A game that is not installed is only a
    // note while the other one can be used.)
    GtkWidget* facts = gtk_grid_new();
    gtk_grid_set_row_spacing(GTK_GRID(facts), 10);
    gtk_grid_set_column_spacing(GTK_GRID(facts), 18);
    int row = 0;
    // (absent: what its error says when it is not installed at all, which
    // "Not installed" says already)
    const auto game_fact = [&](const char* name, bool usable, bool found, const std::string& path,
                               const std::string& error, const std::string& absent, bool other_usable) {
        gtk_grid_attach(GTK_GRID(facts), fact_name(name), 0, row, 1, 1);
        GtkWidget* fact = nullptr;
        if (usable) {
            fact = ui::label(path, "path", false);
            ui::set_tooltip(fact, path);
        } else if (!found && path.empty() && other_usable) {
            fact = ui::label("Not installed", "dim");
        } else {
            std::string text = found ? "Found, but it cannot be used" : "Not installed";
            if (!error.empty() && error != absent) text += ": " + error;
            fact = ui::label(text, "error-text");
        }
        gtk_widget_set_hexpand(fact, TRUE);
        gtk_grid_attach(GTK_GRID(facts), fact, 1, row++, 1, 1);
    };
    game_fact("Tekken 7", s.tekken7_usable(), s.tekken7_found, s.tekken7_path, s.tekken7_error, "",
              s.tekken8_usable());
    game_fact("Tekken 8", s.tekken8_usable(), s.tekken8_found, s.tekken8_path, s.tekken8_error,
              "Tekken 8 is not installed in any Steam library", s.tekken7_usable());

    // Tekken 8 runs hidden only for moves not saved yet; Tekken 7's tools are
    // listed whenever there is no Tekken 8 (as they always were).
    bool unsaved8 = false;
    for (const Fighter& f : s.fighters) unsaved8 = unsaved8 || (f.of(kTekken8) && !f.moveset_saved);
    const bool for7 = s.tekken7_found || !s.tekken8_found;
    const bool for8 = s.tekken8_usable() && unsaved8 && s.tekken8_build_known == true && s.tekken8_run_error.empty();
    const char* games = for7 && for8 ? "Tekken 7 and Tekken 8" : for8 ? "Tekken 8" : "Tekken 7";
    gtk_grid_attach(GTK_GRID(facts), fact_name("Steam"), 0, row, 1, 1);
    GtkWidget* steam = ui::box(GTK_ORIENTATION_VERTICAL, 3);
    if (!s.steam_installed) {
        gtk_box_append(GTK_BOX(steam),
                       ui::label("Not installed: Tekken 7 and Tekken 8 for PC come from Steam", "error-text"));
    } else if (s.steam_running) {
        gtk_box_append(GTK_BOX(steam), ui::label("Running", nullptr, false));
    } else if (!for7 && !for8) {
        gtk_box_append(GTK_BOX(steam), ui::label("Not running", "dim", false)); // (nothing needs it now)
    } else {
        gtk_box_append(GTK_BOX(steam), ui::label("Not running", "warning-text", false));
        const std::string why = for7 && for8 ? "Tekken 7 and Tekken 8 need it the first time, and it tells which DLC "
                                               "you own."
                                : for8       ? "Tekken 8 needs it the first time, to save their moves."
                                             : "Tekken 7 needs it the first time, and it tells which DLC you own.";
        gtk_box_append(GTK_BOX(steam), ui::label("Start Steam to add characters: " + why, "small dim"));
    }
    gtk_grid_attach(GTK_GRID(facts), steam, 1, row++, 1, 1);

    // What is missing to import, with the command that installs it.
    std::vector<std::string> missing, names; // (as listed, and as named in a sentence)
    std::vector<Package> packages;
    if (!s.numpy || !s.pillow) {
        missing.push_back(!s.numpy && !s.pillow ? "numpy and Pillow for Python"
                          : !s.numpy            ? "numpy for Python"
                                                : "Pillow for Python");
        names.push_back(missing.back());
        if (!s.numpy) packages.push_back(Package::kNumpy);
        if (!s.pillow) packages.push_back(Package::kPillow);
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
    if (!s.game_error.empty() && install_.state == InstallState::kInstalled) {
        gtk_grid_attach(GTK_GRID(facts), fact_name("Game"), 0, row, 1, 1);
        GtkWidget* game = ui::label("The importer cannot read it: " + s.game_error, "error-text");
        gtk_grid_attach(GTK_GRID(facts), game, 1, row++, 1, 1);
    }
    if (!missing.empty()) {
        gtk_grid_attach(GTK_GRID(facts), fact_name("Missing"), 0, row, 1, 1);
        GtkWidget* needed = ui::box(GTK_ORIENTATION_VERTICAL, 6);
        std::string text;
        for (size_t i = 0; i < missing.size(); ++i) text += (i ? "\n" : "") + missing[i];
        gtk_box_append(GTK_BOX(needed), ui::label(text, "warning-text"));
        std::string what;
        for (size_t i = 0; i < names.size(); ++i) {
            what += (i == 0 ? "" : i + 1 == names.size() ? " and " : ", ") + names[i];
        }
        gtk_box_append(GTK_BOX(needed),
                       install_hint(distro, packages, what, "Install them with your distribution's packages."));
        gtk_grid_attach(GTK_GRID(facts), needed, 1, row, 1, 1);
    }
    gtk_box_append(GTK_BOX(card), facts);

    // Each game's characters: the one installed first.
    if (!s.tekken7_found && s.tekken8_found) {
        game_section(card, kTekken8);
        game_section(card, kTekken7);
    } else {
        game_section(card, kTekken7);
        game_section(card, kTekken8);
    }
}

void Launcher::game_section(GtkWidget* card, const std::string& game) {
    const ImporterStatus& s = *status_;
    const bool tekken8 = game == kTekken8;
    const bool usable = game_usable(game);
    GtkWidget* separator = gtk_separator_new(GTK_ORIENTATION_HORIZONTAL);
    gtk_widget_set_margin_top(separator, 4);
    gtk_box_append(GTK_BOX(card), separator);
    GtkWidget* head = ui::box(GTK_ORIENTATION_HORIZONTAL, 12);
    GtkWidget* head_text = ui::box(GTK_ORIENTATION_VERTICAL, 3);
    gtk_widget_set_hexpand(head_text, TRUE);
    gtk_box_append(GTK_BOX(head_text), ui::label(std::string(game_name(game)) + "'s characters", "heading"));
    gtk_box_append(GTK_BOX(head_text),
                   ui::label(std::string("They join the roster beside the game's own fighters. Each takes a few "
                                         "minutes; the first time, ") +
                                 game_name(game) + " runs hidden in the background to save their moves.",
                             "small dim"));
    gtk_box_append(GTK_BOX(head), head_text);
    int base_count = 0;
    for (const Fighter& f : s.fighters) base_count += f.of(game) && f.dlc == 0;
    // (One character alone has its own Add.)
    if (!tekken8 || base_count > 1) {
        const auto base = base_to_add(game);
        GtkWidget* add_all = ui::button("Add All");
        ui::set_id(add_all, tekken8 ? "add-all:tekken8" : "add-all");
        gtk_widget_set_sensitive(add_all, usable && !task_ && !base.empty());
        if (tekken8) clicked(add_all, [](Launcher* self) { self->start_import(self->base_to_add(kTekken8)); });
        else clicked(add_all, [](Launcher* self) { self->start_import(self->base_to_add(kTekken7)); });
        gtk_box_append(GTK_BOX(head), add_all);
    }
    // The game gone, with its characters still in the game: they can go only
    // all at once (what those left share is made again without it).
    if (const auto all = to_remove_all(game); !all.empty()) {
        GtkWidget* remove_all = ui::button("Remove All", "flat");
        ui::set_id(remove_all, "remove-all:" + game);
        gtk_widget_set_valign(remove_all, GTK_ALIGN_CENTER);
        gtk_widget_set_sensitive(remove_all, !task_ && install_.state == InstallState::kInstalled);
        if (tekken8) clicked(remove_all, [](Launcher* self) { self->ask_remove_all(kTekken8); });
        else clicked(remove_all, [](Launcher* self) { self->ask_remove_all(kTekken7); });
        gtk_box_append(GTK_BOX(head), remove_all);
    }
    gtk_box_append(GTK_BOX(card), head);

    // The other game is gone, and its characters need it for what all of
    // them share.
    if (const std::string other = shared_blocker(game); !other.empty() && install_.state == InstallState::kInstalled) {
        note_line(card, "dialog-warning-symbolic", shared_needs(other), true);
    }

    // Packs an older version made, which the game skips, of characters that
    // can be added again (base and DLC alike: the DLC's list may be closed;
    // a DLC not owned only says so in its row); and a newer version's, which
    // it skips too until it is updated.
    std::vector<const Fighter*> outdated, newer;
    for (const Fighter& f : s.fighters) {
        if (!f.of(game)) continue;
        if (f.outdated && owns(f) != false) outdated.push_back(&f);
        if (f.newer) newer.push_back(&f);
    }
    const auto warn_line = [&](const std::vector<const Fighter*>& who, const char* made, const char* todo) {
        if (who.empty()) return;
        const std::string text = who.size() == 1
                                     ? who[0]->display + " was made by " + made + " and is not in the game: "
                                     : std::to_string(who.size()) + " characters were made by " + made +
                                           " and are not in the game: ";
        note_line(card, "dialog-warning-symbolic", text + todo, true);
    };
    warn_line(outdated, "an older version", "add them again.");
    warn_line(newer, "a newer version of Ultimate Launcher", "update it, then the game, to play them.");

    // (Tekken 8) Characters fighting with a stand-in's moves, and why: their
    // own could not be saved, or this version of Tekken 8 is one the helper
    // does not know yet; and what adding one gives when their moves cannot be
    // saved now.
    if (tekken8 && usable) {
        std::vector<const Fighter*> stand_ins, unsaved;
        for (const Fighter& f : s.fighters) {
            if (!f.of(game)) continue;
            if (f.stand_in) stand_ins.push_back(&f);
            else if (!f.installed && !f.moveset_saved && owns(f) != false) unsaved.push_back(&f);
        }
        const MovesBlock block = moves_block();
        if (!stand_ins.empty()) {
            const auto names = to_update(game, true);
            bool known = true; // (their own can be had: saved, or this build saves them)
            for (const Fighter* f : stand_ins) known = known && f->update;
            std::string text = who_fights(stand_ins) + " with Heihachi's moves for now: ";
            if (!known) {
                text += std::string(kUnknownBuild) + ". A later version of it can.";
            } else {
                text += stand_ins.size() == 1 ? "their own could not be saved from Tekken 8 when they were added."
                                              : "theirs could not be saved from Tekken 8 when they were added.";
                text += !names.empty()                   ? " Update to give them their own."
                        : block == MovesBlock::kSteam    ? " Start Steam to update."
                        : block == MovesBlock::kTools    ? " Install what is missing above to update."
                        : block == MovesBlock::kRun      ? " To update: " + sentence(s.tekken8_run_error) + "."
                                                         : "";
            }
            GtkWidget* line = note_line(card, "dialog-information-symbolic", text, false);
            if (!names.empty()) {
                GtkWidget* update = ui::button(names.size() == 1 ? "Update" : "Update All");
                ui::set_id(update, "update-stand-ins");
                gtk_widget_set_valign(update, GTK_ALIGN_CENTER);
                gtk_widget_set_sensitive(update, !task_);
                clicked(update, [](Launcher* self) { self->start_import(self->to_update(kTekken8, true)); });
                gtk_box_append(GTK_BOX(line), update);
            }
        }
        if (!unsaved.empty() && block != MovesBlock::kNone && block != MovesBlock::kSteam) {
            // (Steam not running: their Add says to start it.)
            const std::string fix = block == MovesBlock::kRun ? s.tekken8_run_error : "install what is missing above";
            const std::string text =
                block == MovesBlock::kBuild
                    ? std::string(kUnknownBuild) + ": added now, " + who_fights(unsaved) +
                          " with Heihachi's moves until a later version of it can save their own."
                    : "Their moves cannot be saved from Tekken 8 now: " + fix + ". Added now, " + who_fights(unsaved) +
                          " with Heihachi's moves until updated.";
            note_line(card, "dialog-information-symbolic", text, false);
        }
    }

    // Characters in the game that an older version made: updating them (adding
    // them again) gives them what this version adds.
    std::vector<const Fighter*> updates;
    for (const Fighter& f : s.fighters) {
        if (f.of(game) && f.update && !f.stand_in && owns(f) != false) updates.push_back(&f);
    }
    if (!updates.empty()) {
        const std::string who = updates.size() == 1 ? updates[0]->display + " was"
                                                    : std::to_string(updates.size()) + " characters were";
        GtkWidget* line = note_line(card, "ttt2-update-symbolic",
                                    who + " made by an older version: update " +
                                        (updates.size() == 1 ? "them" : "them all") + " to get what this one adds.",
                                    true);
        const auto names = to_update(game);
        GtkWidget* update_all = ui::button(updates.size() == 1 ? "Update" : "Update All");
        ui::set_id(update_all, tekken8 ? "update-all:tekken8" : "update-all");
        gtk_widget_set_valign(update_all, GTK_ALIGN_CENTER);
        gtk_widget_set_sensitive(update_all, usable && !task_ && !names.empty());
        if (usable && names.empty()) {
            const std::string why = tekken8 ? not_addable_why(*updates[0]) : "Start Steam: Tekken 7 needs it";
            gtk_widget_set_tooltip_text(update_all, why.c_str());
        }
        if (tekken8) clicked(update_all, [](Launcher* self) { self->start_import(self->to_update(kTekken8)); });
        else clicked(update_all, [](Launcher* self) { self->start_import(self->to_update(kTekken7)); });
        gtk_box_append(GTK_BOX(line), update_all);
    }

    GtkWidget* list = gtk_list_box_new();
    gtk_list_box_set_selection_mode(GTK_LIST_BOX(list), GTK_SELECTION_NONE);
    gtk_widget_add_css_class(list, "fighter-list");
    for (const Fighter& f : s.fighters) {
        // (Tekken 7's DLC characters in their own list below; Tekken 8's,
        // whose ownership is not asked yet, with the others.)
        if (f.of(game) && (tekken8 || f.dlc == 0)) gtk_list_box_append(GTK_LIST_BOX(list), fighter_row(f, usable));
    }
    gtk_box_append(GTK_BOX(card), list);
    if (!tekken8) dlc_section(card, usable);
}

void Launcher::dlc_section(GtkWidget* card, bool usable) {
    const ImporterStatus& s = *status_;
    int dlc_count = 0, owned_count = 0, dlc_outdated = 0, dlc_update = 0;
    for (const Fighter& f : s.fighters) {
        if (!f.of(kTekken7) || f.dlc == 0) continue;
        ++dlc_count;
        owned_count += owns(f) == true;
        dlc_outdated += f.outdated && owns(f) != false;
        dlc_update += f.update && owns(f) != false;
    }
    if (dlc_count == 0) return;

    // The DLC's, in a list that opens.
    GtkWidget* title = ui::box(GTK_ORIENTATION_HORIZONTAL, 10);
    gtk_box_append(GTK_BOX(title), ui::label("DLC characters", "heading", false));
    const std::string summary =
        owned_answer_ ? std::to_string(owned_count) + " of " + std::to_string(dlc_count) + " owned"
                      : std::to_string(dlc_count);
    gtk_box_append(GTK_BOX(title), ui::label(summary, "pill neutral", false));
    if (dlc_outdated > 0) {
        gtk_box_append(GTK_BOX(title), ui::label(std::to_string(dlc_outdated) + " to add again", "pill warn", false));
    }
    if (dlc_update > 0) {
        gtk_box_append(GTK_BOX(title), ui::label(std::to_string(dlc_update) + " to update", "pill warn", false));
    }
    GtkWidget* expander = gtk_expander_new(nullptr);
    ui::set_id(expander, "dlc");
    gtk_expander_set_label_widget(GTK_EXPANDER(expander), title);
    gtk_expander_set_expanded(GTK_EXPANDER(expander), dlc_expanded_);
    gtk_widget_set_margin_top(expander, 6);
    g_signal_connect(expander, "notify::expanded", G_CALLBACK(+[](GObject* e, GParamSpec*, gpointer data) {
                         static_cast<Launcher*>(data)->dlc_expanded_ = gtk_expander_get_expanded(GTK_EXPANDER(e));
                     }),
                     this);
    GtkWidget* inside = ui::box(GTK_ORIENTATION_VERTICAL, 12);
    gtk_widget_set_margin_top(inside, 12);
    GtkWidget* owned_row = ui::box(GTK_ORIENTATION_HORIZONTAL, 12);
    GtkWidget* note = nullptr;
    // (Steam's answer kept from before is shown at once: asking again takes
    // most of a minute after a boot.)
    const std::string owns_text = std::to_string(owned_count) + " of them";
    if (owned_state_ == Owned::kChecking) {
        note = ui::box(GTK_ORIENTATION_HORIZONTAL, 10);
        GtkWidget* spinner = gtk_spinner_new();
        gtk_spinner_start(GTK_SPINNER(spinner));
        gtk_box_append(GTK_BOX(note), spinner);
        gtk_box_append(GTK_BOX(note), ui::label(owned_answer_ ? "Asking Steam again which DLC you own (last time: " +
                                                                    owns_text + ")…"
                                                              : "Asking Steam which DLC you own…",
                                                "small dim"));
    } else if (owned_state_ == Owned::kKnown) {
        note = ui::label("Your Steam account owns " + owns_text + ": only those can be added.", "small dim");
    } else if (owned_state_ == Owned::kFailed) {
        note = ui::label(owned_answer_ ? "Steam could not be asked again (" + owned_error_ +
                                             "). It said last time that your account owns " + owns_text + "."
                                       : "Which DLC you own is not known: " + owned_error_,
                         "small error-text");
    } else if (owned_answer_) {
        note = ui::label(s.steam_running ? "Your Steam account owned " + owns_text + " last time Steam was asked."
                                         : "Your Steam account owned " + owns_text +
                                               " last time Steam was asked. Start Steam to add them: it checks again.",
                         "small dim");
    } else if (!s.steam_installed) {
        note = ui::label("Which DLC you own is not known: Steam, which tells it, is not installed.", "small dim");
    } else if (!s.tekken7_usable()) {
        // (Steam is asked as the game asks it, in Tekken 7's Proton prefix:
        // never while Tekken 7 cannot be used, so "not known yet" would wait
        // for nothing.)
        note = ui::label(std::string("Which DLC you own is not known: Steam is asked through Tekken 7, which ") +
                             (s.tekken7_found ? "cannot be used (see above)." : "is not installed."),
                         "small dim");
    } else {
        note = ui::label(s.steam_running ? "Which DLC you own is not known yet."
                                         : "Start Steam to see which DLC you own: only those can be added.",
                         "small dim");
    }
    gtk_widget_set_hexpand(note, TRUE);
    gtk_widget_set_valign(note, GTK_ALIGN_CENTER);
    gtk_box_append(GTK_BOX(owned_row), note);
    const auto owned = owned_to_add();
    GtkWidget* add_owned = ui::button("Add All Owned");
    ui::set_id(add_owned, "add-all-owned");
    gtk_widget_set_sensitive(add_owned, usable && !task_ && !owned.empty());
    clicked(add_owned, [](Launcher* self) { self->start_import(self->owned_to_add()); });
    gtk_box_append(GTK_BOX(owned_row), add_owned);
    gtk_box_append(GTK_BOX(inside), owned_row);
    GtkWidget* dlc_list = gtk_list_box_new();
    gtk_list_box_set_selection_mode(GTK_LIST_BOX(dlc_list), GTK_SELECTION_NONE);
    gtk_widget_add_css_class(dlc_list, "fighter-list");
    for (const Fighter& f : s.fighters) {
        if (f.of(kTekken7) && f.dlc != 0) gtk_list_box_append(GTK_LIST_BOX(dlc_list), fighter_row(f, usable));
    }
    gtk_box_append(GTK_BOX(inside), dlc_list);
    gtk_expander_set_child(GTK_EXPANDER(expander), inside);
    gtk_box_append(GTK_BOX(card), expander);
}

// ---------------------------------------------------------------- tasks

void Launcher::start_import(const std::vector<std::string>& names) {
    std::string why;
    if (task_) return refuse("Another task is running", "Wait for it to end, then add characters.");
    if (!can_import(&why)) return refuse("Cannot add characters", why);
    // (Each from its own game: only the games of the characters asked for.)
    bool tekken7 = false, tekken8 = false;
    for (const Fighter& f : status_->fighters) {
        if (std::find(names.begin(), names.end(), f.name) == names.end()) continue;
        (f.of(kTekken8) ? tekken8 : tekken7) = true;
    }
    if ((tekken7 && !game_usable(kTekken7, &why)) || (tekken8 && !game_usable(kTekken8, &why))) {
        return refuse("Cannot add characters", why);
    }
    std::vector<std::string> argv = importer_command("import_character.py");
    argv.insert(argv.end(), names.begin(), names.end());
    argv.insert(argv.end(), {"--game", install_.folder.string(), "--progress"});
    // (Characters to update only: an update. Their packs are replaced whole,
    // as the importer replaces any.)
    const bool update = !names.empty() && std::all_of(names.begin(), names.end(), [&](const std::string& name) {
        return std::any_of(status_->fighters.begin(), status_->fighters.end(),
                           [&](const Fighter& f) { return f.name == name && f.update; });
    });
    if (start_task(Kind::kImport, (update ? "Updating " : "Adding ") + names_text(status_, names), argv,
                   importer_environment(), nullptr)) {
        task_->subject = names_text(status_, names);
        task_->update = update;
        task_->hidden = tekken7 && tekken8 ? "Tekken 7 or Tekken 8" : tekken8 ? "Tekken 8" : "Tekken 7";
    }
}

void Launcher::start_remove(const std::vector<std::string>& names) {
    if (task_) return refuse("Another task is running", "Wait for it to end, then remove characters.");
    if (importer_.empty() || python_.empty() || install_.state != InstallState::kInstalled) {
        return refuse("Cannot remove characters", "The importer, Python 3 or the installed game is missing.");
    }
    std::vector<std::string> argv = importer_command("import_character.py");
    argv.push_back("--remove");
    argv.insert(argv.end(), names.begin(), names.end());
    argv.insert(argv.end(), {"--game", install_.folder.string(), "--progress"});
    if (start_task(Kind::kRemove, "Removing " + names_text(status_, names), argv, importer_environment(), nullptr)) {
        task_->subject = names_text(status_, names);
    }
}

void Launcher::ask_remove_all(const std::string& game) {
    const auto names = to_remove_all(game);
    if (names.empty()) return;
    // (Not to be undone while that game is gone: asked first.)
    const std::string name = game_name(game);
    const std::string title = "Remove all " + std::to_string(names.size()) + " " + name + " characters?";
    GtkAlertDialog* dialog = gtk_alert_dialog_new("%s", title.c_str());
    const std::string detail = name + " is not installed, so they cannot be added again until it is.";
    gtk_alert_dialog_set_detail(dialog, detail.c_str());
    const char* buttons[] = {"Cancel", "Remove All", nullptr};
    gtk_alert_dialog_set_buttons(dialog, buttons);
    gtk_alert_dialog_set_cancel_button(dialog, 0);
    gtk_alert_dialog_set_default_button(dialog, 0);
    remove_all_game_ = game;
    gtk_alert_dialog_choose(
        dialog, GTK_WINDOW(window_), nullptr,
        +[](GObject* d, GAsyncResult* result, gpointer data) {
            auto* self = static_cast<Launcher*>(data);
            if (gtk_alert_dialog_choose_finish(GTK_ALERT_DIALOG(d), result, nullptr) == 1) {
                self->start_remove(self->to_remove_all(self->remove_all_game_));
            }
        },
        this);
    g_object_unref(dialog);
}

} // namespace launcher
