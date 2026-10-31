#pragma once

// The title's menus: MenuToolKit "menudata" files (BX01, a binary XML; the
// Offline menu's is entry 4615C394, the update's copy in data100 winning).
// The file is a header ("BX01", 1, the offsets of the tag and attribute name
// tables at the end, the number of root elements) and the elements: each a
// tag, a text (a length with its zero, the bytes, padded to four), its
// attributes (an attribute name's number and a text each) and its children.
// Event handlers (OnLoad, OnEnter, ...) are children whose text is a
// compiled Xtal script.

#include <cstdint>
#include <optional>
#include <vector>

namespace cafe::title::menudata {

// The Offline menu (frame FrameMode002-01, menu MenuMode002-01) with a row
// SOLO GHOST BATTLE (MenuItemMode002-09) right below GHOST BATTLE: a copy of
// GHOST BATTLE's row, so confirming it starts Ghost Battle as GHOST BATTLE
// does, with its own label and description. The rows' icons and
// descriptions follow the cursor's place (the OnLoad script's icon arrays,
// statics named StaticMode002-0<place + 1>), so both get a place for it.
// Null when the file is not as expected.
std::optional<std::vector<uint8_t>> add_solo_ghost_row(const std::vector<uint8_t>& file);

constexpr const char* kSoloGhostRow = "MenuItemMode002-09";
constexpr const char* kOfflineMenu = "MenuMode002-01";
constexpr uint32_t kSoloGhostPlace = 2; // its place in the Offline menu (GHOST BATTLE's is 1)

} // namespace cafe::title::menudata
