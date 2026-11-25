#pragma once

// The player's name: game.ini's player_name (host/game_settings.h) in place
// of the name the title gives the player offline, "Player" in the game's
// language, wherever it shows (the main menu's player panel, the select and
// versus screens, under the fight's health bar) and in the records it is
// copied into. Without one the title's own stays.

#include <string>

namespace cafe::title {

// After the system heap is made, before the title runs: game.ini's
// player_name (host::game::Settings::player_name; empty: the title's own).
void prepare_player_name(const std::string& name);

} // namespace cafe::title
