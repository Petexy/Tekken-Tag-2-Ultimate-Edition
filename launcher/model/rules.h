#pragma once

// The rules the views and actions share (launcher/app/characters.cpp and
// game.cpp before): which characters can be added, updated, removed, what
// their outfits do, whether the game is older than this launcher. Windows
// gets the same rules (the Tk window's copy had drifted).

#include "facts.h"

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace launcher::model {

// A build of Tekken 8 its helper does not know (a game update).
extern const char* const kUnknownBuild;

const char* game_name(std::string_view game);  // "Tekken 7", "Tekken 8"
const char* other_game(std::string_view game); // kTekken8 for kTekken7 ...
// A text as a sentence: its first letter in capitals.
std::string sentence(std::string text);
// "A", "A and B", "A, B and C".
std::string joined(const std::vector<std::string>& items);
// "A, B" with at most `most`, then " and N more".
std::string joined_most(const std::vector<std::string>& items, size_t most);
std::string display_name(const Facts& facts, const std::string& name);
// "Kazumi Mishima", "3 characters".
std::string names_text(const Facts& facts, const std::vector<std::string>& names);
const Fighter* fighter(const Facts& facts, std::string_view name);

// While the installed program is from an older launcher than this one: what
// the window says (Play, adding and updating characters wait for Update, in
// Play's place); else empty.
std::string older_game(const Facts& facts);
// Whether Update is offered beside Play: this launcher's build is known and
// the installed program's is another (or unknown).
bool update_ready(const Facts& facts);
// A build as Windows shows it: "0.8.0-1cab8c68f39b" -> "0.8.0 (1cab8c6)" (self_update.shown_id).
std::string shown_build(const std::string& build);
// "Install the game first: ..." (Linux) / "Set up the game first: ..." (Windows); long: the characters card's note.
std::string set_up_first(const Facts& facts, bool long_form);

// What stops a Tekken 8 character's own moves being saved now (Tekken 8
// runs hidden for that): nothing, a build its helper does not know, it
// cannot run hidden (run_error), what runs it is missing, Steam.
enum class MovesBlock { kNone, kBuild, kRun, kTools, kSteam };
MovesBlock moves_block(const Facts& facts);

std::optional<bool> owns(const Facts& facts, const Fighter& fighter);
// What every import needs (the importer, Python's packages, the game).
bool can_import(const Facts& facts, std::string* why = nullptr);
// The other game, when it is gone and characters of it that need it are in
// the game; empty when nothing stops `game`'s.
std::string shared_blocker(const Facts& facts, const std::string& game);
std::string shared_needs(std::string_view other);
bool game_usable(const Facts& facts, const std::string& game, std::string* why = nullptr);
bool addable(const Facts& facts, const Fighter& fighter);
std::string not_addable_why(const Facts& facts, const Fighter& fighter);
std::string unknown_owned_why(const Facts& facts, const Fighter& fighter);
// Why removing that character cannot work now, empty when it can.
std::string removable(const Facts& facts, const Fighter& fighter);
std::vector<std::string> base_to_add(const Facts& facts, const std::string& game);
std::vector<std::string> owned_to_add(const Facts& facts);
std::vector<std::string> to_update(const Facts& facts, const std::string& game, bool stand_ins = false);
std::vector<std::string> to_remove_all(const Facts& facts, const std::string& game);
bool wants_outfits(const Facts& facts, const Fighter& fighter);
bool outfits_choosable(const Fighter& fighter, std::optional<bool> owned);
std::vector<const Fighter*> outfit_choices(const Facts& facts);
bool outfits_changed(const Facts& facts, const Fighter& fighter);
std::vector<std::string> outfits_to_change(const Facts& facts);
bool newer_on_main(const Facts& facts, const std::string& fighter);

// Everything Home's UPDATE brings up to date, in its order: the launcher (a newer release, when this one updates
// itself), the game program (built again: for this launcher, or for the new one after it), the added characters
// whose packs are older than the importer's (those it can make now; the others are left for later, with why).
struct UpdatePlan {
    bool launcher = false;
    std::string launcher_from, launcher_to; // "0.8.0", "0.9.0"
    bool game = false;
    std::string game_for;                   // the launcher version the game is built for ("0.9.0")
    std::vector<std::string> fighters;      // names, in the status's order
    std::vector<std::pair<std::string, std::string>> later; // display name, why not now
    int parts() const { return (launcher ? 1 : 0) + (game ? 1 : 0) + (fighters.empty() ? 0 : 1); }
    bool empty() const { return parts() == 0; }
};
UpdatePlan update_plan(const Facts& facts);

// Whether anything runs in the background (a task, the status, Steam's
// answer, the preflight, GitHub): tests and screenshots wait for none.
bool busy(const Facts& facts, bool release_checking, bool main_checking);

// Windows: the player's sentence for what `--query check` refused before a task ("" when nothing: code ""), as
// window.py and setup_game.py said it; and for what `--query save-settings` refused (code "data_name" /
// "relative", what = the folder's key).
std::string setup_problem_text(const SetupProblem& problem);
std::string save_problem_text(const SetupProblem& problem);

} // namespace launcher::model
