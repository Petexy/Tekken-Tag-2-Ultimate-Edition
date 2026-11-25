#pragma once

// The title's menus: MenuToolKit "menudata" files (BX01, a binary XML; the
// Offline menu's is entry 4615C394, the update's copy in data100 winning).
// The file is a header ("BX01", 1, the offsets of the tag and attribute name
// tables at the end, the number of root elements) and the elements: each a
// tag, a text (a length with its zero, the bytes, padded to four), its
// attributes (an attribute name's number and a text each) and its children.
// Event handlers (OnLoad, OnEnter, ...) are children whose text is a
// compiled Xtal script.

#include "title/language.h"

#include <array>
#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace cafe::title::menudata {

// The Offline menu (frame FrameMode002-01, menu MenuMode002-01) with a row
// SOLO GHOST BATTLE (MenuItemMode002-09) right below GHOST BATTLE: a copy of
// GHOST BATTLE's row, so confirming it starts Ghost Battle as GHOST BATTLE
// does, with its own label and description. The rows' icons and
// descriptions follow the cursor's place (the OnLoad script's icon arrays,
// statics named StaticMode002-0<place + 1>), so both get a place for it.
// Its label and description are in the language at `place` (the label is
// the one the fight's corner shows too). Null when the file is not as expected.
std::optional<std::vector<uint8_t>> add_solo_ghost_row(const std::vector<uint8_t>& file,
                                                       language::Place place = language::place());

// SOLO GHOST BATTLE in each language (the game's GHOST BATTLE and SOLO).
inline constexpr language::Text kSoloGhostLabel = {
    "SOLO GHOST BATTLE", "FANT\xC3\x94ME SOLO", "SOLO-GEISTERKAMPF", "BATTAGLIA FANTASMA SOLO", "COMBATE FANTASMA SOLO",
    "\xD0\xA1\xD0\x9E\xD0\x9B\xD0\x9E-\xD0\x91\xD0\x9E\xD0\x99 \xD0\xA1 "
    "\xD0\x9F\xD0\xA0\xD0\x98\xD0\x97\xD0\xA0\xD0\x90\xD0\x9A\xD0\x90\xD0\x9C\xD0\x98"};

constexpr const char* kSoloGhostRow = "MenuItemMode002-09";
constexpr const char* kOfflineMenu = "MenuMode002-01";
constexpr uint32_t kSoloGhostPlace = 2; // its place in the Offline menu (GHOST BATTLE's is 1)

// CUSTOMIZE mode's character select (title/customize_grid.h). The interfaces' file (entry B43EB78F) holds its
// cursor's class as Xtal source text (interface IFCharacterSelect, the script named `cursor`): with_cursor_script
// hands that text to `edit` and puts what it returns in its place. The menus' file holds the frame
// (FrameCharacterSelect, menu MenuCharacterSelect) with its four direction handlers (compiled scripts):
// with_select_handlers replaces them with source text (OnLeft, OnRight, OnUp, OnDown in that order). Null when a
// file is not as expected (or `edit` returns none).
std::optional<std::vector<uint8_t>> with_cursor_script(
    const std::vector<uint8_t>& file, const std::function<std::optional<std::string>(std::string_view)>& edit);
std::optional<std::vector<uint8_t>> with_select_handlers(const std::vector<uint8_t>& file,
                                                         const std::array<std::string, 4>& sources);

constexpr const char* kSelectInterface = "IFCharacterSelect";
constexpr const char* kCursorScript = "cursor";
constexpr const char* kSelectFrame = "FrameCharacterSelect";
constexpr const char* kSelectMenu = "MenuCharacterSelect";

} // namespace cafe::title::menudata
