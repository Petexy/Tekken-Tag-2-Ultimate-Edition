#pragma once

// A character added to the roster from a character pack: a directory with
// `character.ini` and the character's files as the title names them
// (`<code>.nud`, `<code>.moveset`, ...), made on the player's machine from
// games they own. Whatever the pack lacks is borrowed from the TTT2 fighter
// it names as its donor, so a pack holding only `character.ini` already
// gives a selectable copy of the donor. `character.ini` names the pack's
// format (`format = 1`; without the line, 1, or 0 for the earliest packs,
// which have their own `keys/`): a pack of another format (an older or a
// newer importer's) is skipped with a warning, and its place is kept for
// its re-import.
//
// The title has room for one more fighter without moving its tables: the
// select id of ZAKO A, a mob of the Fight Lab that no select screen offers,
// two character records it never uses and a motion row no record uses. The
// new fighter takes them, and a 63rd cell of the select grid at the free
// place in its top row.
//
// Packs are read from $TTT2_CHARACTERS, else
// $XDG_DATA_HOME/ttt2/characters (~/.local/share/ttt2/characters).

#include <cstdint>

namespace cafe::title {

// After vfs::open_game and the image load, before the title runs.
void prepare_roster();

// The added fighter (its number: its pack's slot) a fighter (a player
// struct) is, or -1.
int added_slot(uint32_t player);

// The title's situation set-up (sub_039C2DB0's kind): every kind but the
// round end after a KO (26, before its replay) puts every added fighter's
// summoned weapons away, so none stays drawn into the next round.
void summons_situation(uint32_t kind);

} // namespace cafe::title
