#include "rules.h"

#include <algorithm>

namespace launcher::model {

const char* const kUnknownBuild =
    "Tekken 8 was updated to a version that Golden Fist Launcher cannot save moves from yet";

const char* game_name(std::string_view game) { return game == kTekken8 ? "Tekken 8" : "Tekken 7"; }
const char* other_game(std::string_view game) { return game == kTekken8 ? kTekken7 : kTekken8; }

std::string sentence(std::string text) {
    if (!text.empty() && text[0] >= 'a' && text[0] <= 'z') text[0] = static_cast<char>(text[0] - 'a' + 'A');
    return text;
}

std::string joined(const std::vector<std::string>& items) {
    std::string out;
    for (size_t i = 0; i < items.size(); ++i) out += (i == 0 ? "" : i + 1 == items.size() ? " and " : ", ") + items[i];
    return out;
}

std::string joined_most(const std::vector<std::string>& items, size_t most) {
    std::string out;
    for (size_t i = 0; i < items.size() && i < most; ++i) out += (i ? ", " : "") + items[i];
    if (items.size() > most) out += " and " + std::to_string(items.size() - most) + " more";
    return out;
}

const Fighter* fighter(const Facts& facts, std::string_view name) {
    if (!facts.status) return nullptr;
    for (const Fighter& f : facts.status->fighters) {
        if (f.name == name) return &f;
    }
    return nullptr;
}

std::string display_name(const Facts& facts, const std::string& name) {
    const Fighter* f = fighter(facts, name);
    return f ? f->display : name;
}

std::string names_text(const Facts& facts, const std::vector<std::string>& names) {
    if (names.size() == 1) return display_name(facts, names[0]);
    return std::to_string(names.size()) + " characters";
}

std::string older_game(const Facts& facts) {
    if (facts.install.state != InstallState::kInstalled) return {};
    if (!built_older(facts.game_built, facts.this_build)) return {};
    return "The game is from an older version of the launcher (" + std::string(launcher_version(facts.game_built)) +
           "; this one is " + std::string(launcher_version(facts.this_build)) +
           "): update it to play and to add or update characters, which need the newer game.";
}

bool update_ready(const Facts& facts) {
    // (Windows: a game whose build is not recorded is not offered an update: the Tk window's rule, as its games
    // from before the record are many.)
    if (facts.caps.windows && facts.game_built.empty()) return false;
    return facts.install.state == InstallState::kInstalled && !facts.this_build.empty() &&
           facts.game_built != facts.this_build;
}

std::string shown_build(const std::string& build) {
    const size_t dash = build.rfind('-');
    if (dash == std::string::npos) return build;
    return build.substr(0, dash) + " (" + build.substr(dash + 1, 7) + ")";
}

std::string set_up_first(const Facts& facts, bool long_form) {
    const char* const verb = facts.caps.setup_game ? "Set up" : "Install";
    return std::string(verb) + (long_form
                                    ? " the game first: the characters are made from it and from your Tekken 7 or "
                                      "Tekken 8."
                                    : " the game first: characters are made from it.");
}

MovesBlock moves_block(const Facts& facts) {
    if (!facts.status) return MovesBlock::kBuild;
    const ImporterStatus& s = *facts.status;
    if (s.tekken8_build_known != true) return MovesBlock::kBuild;
    if (!s.tekken8_run_error.empty()) return MovesBlock::kRun;
    // (Windows: the worker gets what runs it; there is nothing to install by hand.)
    if (facts.caps.prerequisites_listed && (s.gamescope.empty() || s.pactl.empty() || s.tekken8_helper.empty())) {
        return MovesBlock::kTools;
    }
    if (!s.steam_running) return MovesBlock::kSteam;
    return MovesBlock::kNone;
}

std::optional<bool> owns(const Facts& facts, const Fighter& fighter) {
    if (fighter.dlc == 0) return true;
    if (!facts.owned.has_answer) return std::nullopt;
    const auto it = facts.owned.answer.find(fighter.name);
    if (it == facts.owned.answer.end()) return std::nullopt;
    return it->second;
}

bool can_import(const Facts& facts, std::string* why) {
    const auto no = [&](const std::string& reason) {
        if (why) *why = reason;
        return false;
    };
    if (facts.importer.empty() || facts.python.empty()) return no("The character importer or Python 3 is missing.");
    if (facts.install.state != InstallState::kInstalled) {
        return no(set_up_first(facts, false));
    }
    if (const std::string older = older_game(facts); !older.empty()) return no(older);
    if (!facts.status) return no("The importer cannot tell what this PC has: " + facts.status_error);
    // (Windows: the worker gets numpy and Pillow itself.)
    if (facts.caps.prerequisites_listed && (!facts.status->numpy || !facts.status->pillow)) {
        return no("Python needs numpy and Pillow to add characters.");
    }
    if (!facts.status->game_error.empty()) {
        return no("The importer cannot read the installed game: " + facts.status->game_error);
    }
    return true;
}

std::string shared_needs(std::string_view other) {
    const std::string name = game_name(other);
    return "The " + name + " characters added need " + name +
           " whenever a character is added: what all of them "
           "share is made again, and neither their packs (made by an older version) nor what they share now have "
           "their pictures. Install " +
           name + " again, or remove them first.";
}

std::string shared_blocker(const Facts& facts, const std::string& game) {
    if (!facts.status) return {};
    const std::string other = other_game(game);
    if (facts.status->readable(other)) return {};
    for (const Fighter& f : facts.status->fighters) {
        if (f.of(other) && f.added() && f.needs_game) return other;
    }
    return {};
}

bool game_usable(const Facts& facts, const std::string& game, std::string* why) {
    const auto no = [&](const std::string& reason) {
        if (why) *why = reason;
        return false;
    };
    if (!can_import(facts, why)) return false;
    const ImporterStatus& s = *facts.status;
    if (game == kTekken8) {
        if (!s.tekken8_usable()) return no(s.tekken8_error.empty() ? "Tekken 8 is not installed." : s.tekken8_error);
    } else if (!s.tekken7_usable()) {
        return no(s.tekken7_error.empty() ? "Tekken 7 is not installed." : s.tekken7_error);
    }
    if (const std::string other = shared_blocker(facts, game); !other.empty()) return no(shared_needs(other));
    return true;
}

bool addable(const Facts& facts, const Fighter& f) {
    // (A moveset not saved yet is saved from its game, which needs Steam; a
    // Tekken 7 DLC fighter's import asks Steam whether the DLC is owned, every
    // time, a Tekken 8 one's as its moves are saved. An older importer's pack
    // is replaced, also one to update, a newer one's never.)
    if ((f.added() && !f.update && !outfits_changed(facts, f)) || f.newer || owns(facts, f) != true || !facts.status) {
        return false;
    }
    const ImporterStatus& s = *facts.status;
    if (f.dlc != 0 && !f.of(kTekken8)) return s.steam_running;
    if (f.of(kTekken8)) {
        // Their moves not saved yet are saved first, with Tekken 8 running
        // hidden. When it cannot save them, they are added with a stand-in's
        // moves all the same; but a pack in the game is never made again with
        // a stand-in's moves.
        if (f.moveset_saved) return true;
        const MovesBlock block = moves_block(facts);
        if (f.added()) return block == MovesBlock::kNone;
        return block != MovesBlock::kSteam;
    }
    return s.steam_running || (f.moveset_saved && s.heihachi_saved);
}

std::string not_addable_why(const Facts& facts, const Fighter& f) {
    if (f.dlc != 0 && !f.of(kTekken8)) return "Start Steam: it checks that you own their DLC";
    if (!f.of(kTekken8)) return "Start Steam: Tekken 7 needs it to save their moves";
    switch (moves_block(facts)) {
    case MovesBlock::kBuild: return kUnknownBuild;
    case MovesBlock::kRun: return sentence(facts.status->tekken8_run_error);
    case MovesBlock::kTools: return "Install what is missing above: it saves their moves";
    default: return "Start Steam: Tekken 8 needs it to save their moves";
    }
}

std::string unknown_owned_why(const Facts& facts, const Fighter& f) {
    const char* game = f.of(kTekken8) ? kTekken8 : kTekken7;
    if (facts.status && !facts.status->steam_running) return "Start Steam: it tells which DLC you own";
    if (const auto failed = facts.owned.errors.find(game); failed != facts.owned.errors.end()) {
        return "Steam could not be asked through " + std::string(game_name(game)) + " (" + failed->second +
               "): Refresh asks it again";
    }
    if (facts.owned.state == OwnedState::kFailed) {
        return "Steam could not tell which DLC you own (" + facts.owned.error + ")";
    }
    return "Which " + std::string(game_name(game)) + " DLC you own is not known yet";
}

std::string removable(const Facts& facts, const Fighter& f) {
    if (!facts.status || !f.added()) return {};
    for (const Fighter& o : facts.status->fighters) {
        if (o.name != f.name && o.added() && o.needs_game && !facts.status->readable(o.game)) {
            const char* name = game_name(o.game);
            return std::string(name) + " is needed for the " + name +
                   " characters that stay: what they share is made "
                   "again from it" +
                   (o.of(f.game) ? ". Remove All removes them all at once." : ".");
        }
    }
    return {};
}

std::vector<std::string> base_to_add(const Facts& facts, const std::string& game) {
    std::vector<std::string> names;
    if (facts.status) {
        for (const Fighter& f : facts.status->fighters) {
            if (f.of(game) && f.dlc == 0 && !f.added() && addable(facts, f)) names.push_back(f.name);
        }
    }
    return names;
}

UpdatePlan update_plan(const Facts& facts) {
    UpdatePlan p;
    const bool installed = facts.install.state == InstallState::kInstalled;
    if (facts.self_update && facts.newer) {
        p.launcher = true;
        p.launcher_from = facts.launcher_version;
        p.launcher_to = facts.newer->version;
    }
    // (A new launcher brings its own build of the game: built again after it, always.)
    if (installed && facts.builder && (p.launcher || update_ready(facts))) {
        p.game = true;
        p.game_for = p.launcher ? p.launcher_to : std::string(launcher_version(facts.this_build));
    }
    if (!installed || !facts.status) return p;
    // (What the game piece changes: the characters wait for an older game no more.)
    Facts after = facts;
    if (p.game) after.game_built = after.this_build;
    for (const Fighter& f : facts.status->fighters) {
        if (!f.installed || !f.update) continue;
        const std::optional<bool> owned = owns(facts, f);
        if (owned == false) continue; // (as on their page: nothing to do about it)
        std::string why;
        if (!owned) why = unknown_owned_why(facts, f);
        else if (!addable(facts, f)) why = not_addable_why(facts, f);
        else game_usable(after, f.of(kTekken8) ? kTekken8 : kTekken7, &why); // (why stays empty when it is)
        if (why.empty()) p.fighters.push_back(f.name);
        else p.later.emplace_back(f.display.empty() ? f.name : f.display, why);
    }
    return p;
}

std::vector<std::string> owned_to_add(const Facts& facts) {
    std::vector<std::string> names;
    if (facts.status) {
        for (const Fighter& f : facts.status->fighters) {
            if (f.of(kTekken7) && f.dlc != 0 && !f.added() && addable(facts, f)) names.push_back(f.name);
        }
    }
    return names;
}

std::vector<std::string> to_update(const Facts& facts, const std::string& game, bool stand_ins) {
    std::vector<std::string> names;
    if (facts.status) {
        for (const Fighter& f : facts.status->fighters) {
            if (f.of(game) && f.update && f.stand_in == stand_ins && addable(facts, f)) names.push_back(f.name);
        }
    }
    return names;
}

std::vector<std::string> to_remove_all(const Facts& facts, const std::string& game) {
    std::vector<std::string> names;
    if (!facts.status || facts.status->readable(game)) return names;
    int added = 0;
    bool needed = false;
    for (const Fighter& f : facts.status->fighters) {
        if (!f.of(game) || !f.installed) continue;
        names.push_back(f.name);
        added += f.added();
        needed = needed || f.needs_game;
    }
    if (added < 2 || !needed) names.clear();
    return names;
}

bool wants_outfits(const Facts& facts, const Fighter& f) {
    if (f.outfits == 0) return false;
    const auto it = facts.outfits.find(f.name);
    return it != facts.outfits.end() ? it->second : f.outfits_added;
}

bool outfits_choosable(const Fighter& f, std::optional<bool> owned) {
    return f.outfits > 0 && owned != false && !f.newer;
}

std::vector<const Fighter*> outfit_choices(const Facts& facts) {
    std::vector<const Fighter*> out;
    if (facts.status) {
        for (const Fighter& f : facts.status->fighters) {
            if (outfits_choosable(f, owns(facts, f))) out.push_back(&f);
        }
    }
    return out;
}

bool outfits_changed(const Facts& facts, const Fighter& f) {
    return f.added() && !f.update && outfits_choosable(f, owns(facts, f)) && wants_outfits(facts, f) != f.outfits_added;
}

std::vector<std::string> outfits_to_change(const Facts& facts) {
    std::vector<std::string> names;
    if (facts.status) {
        for (const Fighter& f : facts.status->fighters) {
            if (outfits_changed(facts, f) && addable(facts, f)) names.push_back(f.name);
        }
    }
    return names;
}

bool newer_on_main(const Facts& facts, const std::string& name) {
    return facts.main_news && std::find(facts.main_news->fighters.begin(), facts.main_news->fighters.end(), name) !=
                                  facts.main_news->fighters.end();
}

bool busy(const Facts& facts, bool release_checking, bool main_checking) {
    return facts.task || facts.status_loading || facts.owned.state == OwnedState::kChecking ||
           (facts.preflight && facts.preflight->running) || release_checking || main_checking;
}

// ---- Windows' refusals

namespace {

std::string folder_name(const std::string& key) {
    if (key == "source") return "Wii U archive";
    if (key == "title") return "extracted game";
    if (key == "install") return "installation folder";
    if (key == "data") return "data folder";
    if (key == "packs") return "characters folder";
    if (key == "saves") return "saves folder";
    if (key == "tools") return "Windows tools folder";
    return key + " folder";
}

} // namespace

std::string setup_problem_text(const SetupProblem& p) {
    const std::string& c = p.code;
    if (c.empty()) return {};
    if (c == "inputs") return "Choose your Wii U archive (.wua) and an installation folder first.";
    if (c == "tools_folder")
        return "Set Up Game builds into the project's build-windows-tools folder: start the launcher from its own "
               "files, not from another build folder.";
    if (c == "installer_letters") {
        const std::string what = p.what == "install" ? "installation folder" : p.what == "source" ? "Wii U archive"
                                                                                                  : p.what;
        return "The " + what + " (" + p.path + ") has letters the game's installer cannot be given on this PC: " +
               p.letters + ". Choose one whose path has only plain letters, such as C:\\Games\\TTT2.";
    }
    if (c == "tools_letters") {
        const std::string what = p.what == "project" ? "launcher's files folder" : "Windows tools folder";
        return "The " + what + " (" + p.path + ") has letters the Windows build tools cannot read: " + p.letters +
               ". Use a folder whose path has only plain letters, such as C:\\TTT2 (outside OneDrive); the "
               "release Golden_Fist_Launcher-x86_64.exe keeps its files in such a folder by itself.";
    }
    if (c == "project_length")
        return "The launcher's files are in a folder whose path is too long for the Windows build tools (" + p.path +
               "). Put a fresh copy in a short folder such as D:\\TTT2, then set up again; your archive need not "
               "move.";
    if (c == "tools_length")
        return "The Windows tools folder's path is too long (" + p.path +
               "): choose a shorter one in Settings > Folders.";
    if (c == "no_build") return "Build the Windows game first: More > Build / Rebuild.";
    if (c == "no_install") return "Choose a complete installation before updating it (Settings > Folders).";
    if (c == "no_paths")
        return "Choose the Wii U source and the installation folder first (Settings > Folders), then install.";
    if (c == "no_fighters") return "Choose at least one character.";
    if (c == "title")
        return "The game's extracted files are not usable: set up the game again, or choose its folder in "
               "Settings > Folders.";
    return "The launcher's files refused it (" + c + ").";
}

std::string save_problem_text(const SetupProblem& p) {
    if (p.code.empty()) return {};
    if (p.code == "data_name")
        return "The data folder must end in TTT2Ultimate, so that the game and the launcher share their settings.";
    if (p.code == "relative") return "The " + folder_name(p.what) + " must be a full path, with its drive.";
    return "The launcher's files refused the folders (" + p.code + ").";
}

} // namespace launcher::model
