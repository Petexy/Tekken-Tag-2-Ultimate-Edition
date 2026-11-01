#pragma once

// Solo Ghost Battle, an Offline mode of the port's: Ghost Battle (the
// title's mode kind 12) fought one on one. The Offline menu has a row for it
// right below GHOST BATTLE (title/menudata.h), which starts Ghost Battle as
// GHOST BATTLE's row does; while a session started from it runs:
// - the select screen gives the player a solo fighter without asking Tag or
//   Solo, as the title's own Mushroom Battle does;
// - every ghost fights alone: its card shows its fighter alone and its
//   partner's place goes to the ghost's own fighter, as the title does for a
//   ghost whose partner is not available yet;
// - the fight's corner names the mode SOLO GHOST BATTLE.
// Ghost Battle's records, ranks and rewards are the same.

namespace cafe::title {

// After vfs::open_game and the image load, before the title runs: the
// Offline menu's row.
void prepare_solo_ghost_battle();

// A Ghost Battle session started from the SOLO GHOST BATTLE row runs.
bool solo_ghost_battle();

} // namespace cafe::title
