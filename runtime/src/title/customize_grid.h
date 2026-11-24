#pragma once

// CUSTOMIZE mode's character grid with the added fighters in it.
//
// The mode's character select (frame FrameCharacterSelect of the menus' file, interface IFCharacterSelect) is not
// the fights' select screen: its cursor is a script. The interface file holds the class CharacterSelectCursor as
// Xtal source text (compiled when the file loads): GetFighterID(x, y) is a table of 3 rows x 22 columns of the
// title's fighters (row 0 the top row with its free ends, no '?' column: the fights' grid column c is x = c left of
// '?' and c - 1 right of it), IsFocusableCharacter(x, y) says whether the cursor may stop on a cell, and
// GetCursorPosX / GetCursorPosY place the cursor's picture (48 a column, 65 a row). The frame's OnLeft / OnRight /
// OnUp / OnDown handlers (compiled Xtal) step x through 0..21 and y through 0..2 with those numbers in them.
//
// The shared layouts draw an added fighter's face in its cell of that grid as on the fights' screen, and move the
// whole grid a row down when it has the new top row (shared/grid.ini). The script knows neither: an added face
// cannot be reached, and with the new top row the cursor's picture is drawn a row above the cell it is on (on the
// top row of the title's fighters it shows in the new top row).
//
// So the class's four methods are renamed (Stock...) and new ones put before them, which answer for the added
// fighters' cells and hand everything else to the stock ones; and the frame's four handlers are replaced by source
// text that steps through the cells in the grid's own order (Move). The class keeps its meaning for x 0..21 and
// y 0..2 (other screens use it with handlers of their own: the profile's character records, the ending movies, the
// leaderboards, the replay search); the cells beyond are x 22, 23 (right of the rows), 24, 25 (left of them: columns
// -1 and -2) and y 3 (the new top row).

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace cafe::title::customize_grid {

struct Cell {
    int32_t column = 0, row = 0; // the fights' grid: column -2..24 ('?' is 11), row -1 (the new top row) .. 2
    uint32_t id = 0;             // the fighter's select id
    bool open = false;           // whether CUSTOMIZE mode can be entered with it
};

constexpr int32_t kColumns = 22, kRows = 3; // the stock table
constexpr int32_t kQuestionColumn = 11;     // the fights' grid's '?' column: no cell of this grid

// A fights' grid place as the script's x and y; none for a place this grid has no cell for.
inline std::optional<std::pair<int32_t, int32_t>> script_place(int32_t column, int32_t row) {
    if (column == kQuestionColumn || column < -2 || column > 24 || row < -1 || row > 2) return std::nullopt;
    const int32_t c = column > kQuestionColumn ? column - 1 : column; // -2..23
    return std::pair<int32_t, int32_t>{c >= 0 ? c : 23 - c, row < 0 ? 3 : row};
}

inline std::string number(int64_t n) { return std::to_string(n); }

// The methods put into the class before its own (which are renamed Stock...). rows: the grid has the new top row.
inline std::string methods(const std::vector<Cell>& cells, bool rows) {
    std::string ids, open, columns = " 0";
    bool left[2] = {false, false}, right[2] = {false, false}, top = false;
    for (const Cell& cell : cells) {
        const auto at = script_place(cell.column, cell.row);
        if (!at) continue;
        const std::string here = "if ( x == " + number(at->first) + " && y == " + number(at->second) + " ) { return ";
        ids += "                 " + here + number(cell.id) + "; }\r\n";
        open += "                 " + here + (cell.open ? "true" : "false") + "; }\r\n";
        if (at->first >= 24) left[at->first - 24] = true;
        else if (at->first >= 22) right[at->first - 22] = true;
        top = top || at->second == 3;
    }
    for (int32_t x = 1; x < kColumns; ++x) columns += ", " + number(x);
    // the cursor's order of the columns, left to right, and of the rows, top to bottom
    if (right[0] || right[1]) columns += ", 22";
    if (right[1]) columns += ", 23";
    if (left[0] || left[1]) columns = " 24," + columns;
    if (left[1]) columns = " 25," + columns;
    std::string s;
    s += "             GetCursorPosX( x )\r\n             {\r\n";
    s += "                 if ( x >= 24 ) { return StockCursorPosX( 23 - x ); }\r\n";
    s += "                 return StockCursorPosX( x );\r\n             }\r\n";
    s += "             GetCursorPosY( y )\r\n             {\r\n";
    s += "                 if ( y == 3 ) { return StockCursorPosY( -1 ) + " + number(rows ? 65 : 0) + "; }\r\n";
    s += "                 return StockCursorPosY( y ) + " + number(rows ? 65 : 0) + ";\r\n             }\r\n";
    s += "             GetFighterID( x, y )\r\n             {\r\n" + ids;
    s += "                 if ( x < 0 || x > 21 || y < 0 || y > 2 ) { return lib::ID_PRA; }\r\n";
    s += "                 return StockFighterID( x, y );\r\n             }\r\n";
    s += "             IsFocusableCharacter( x, y )\r\n             {\r\n" + open;
    s += "                 if ( x < 0 || x > 21 || y < 0 || y > 2 ) { return false; }\r\n";
    s += "                 return StockFocusable( x, y );\r\n             }\r\n";
    // One step of the cursor from (x, y): pressed (trig) it goes on, round the ends, to the next cell it may stop
    // on; held (the key's repeat) it takes the next cell or stays, as the stock handlers do.
    s += "             Move( x, y, dx, dy, trig )\r\n             {\r\n";
    s += "                 cols : [" + columns + " ];\r\n";
    s += std::string("                 rows : [ ") + (top ? "3, " : "") + "0, 1, 2 ];\r\n";
    s += "                 i : 0;\r\n                 j : 0;\r\n";
    s += "                 for ( k:0 ; k<cols.size() ; k++ ) { if ( cols[k] == x ) { i = k; } }\r\n";
    s += "                 for ( k:0 ; k<rows.size() ; k++ ) { if ( rows[k] == y ) { j = k; } }\r\n";
    s += "                 if ( trig ) {\r\n";
    s += "                     found : false;\r\n";
    s += "                     for ( k:0 ; k<cols.size() ; k++ ) {\r\n";
    s += "                         if ( found ) {\r\n                         } else {\r\n";
    s += "                             i = i + dx;\r\n                             j = j + dy;\r\n";
    s += "                             if ( i < 0 ) { i = cols.size() - 1; }\r\n";
    s += "                             if ( i >= cols.size() ) { i = 0; }\r\n";
    s += "                             if ( j < 0 ) { j = rows.size() - 1; }\r\n";
    s += "                             if ( j >= rows.size() ) { j = 0; }\r\n";
    s += "                             if ( IsFocusableCharacter( cols[i], rows[j] ) ) { found = true; }\r\n";
    s += "                         }\r\n                     }\r\n";
    s += "                     if ( found ) { return [ cols[i], rows[j] ]; }\r\n";
    s += "                     return [ x, y ];\r\n                 }\r\n";
    s += "                 i = i + dx;\r\n                 j = j + dy;\r\n";
    s += "                 if ( i >= 0 && i < cols.size() && j >= 0 && j < rows.size() ) {\r\n";
    s += "                     if ( IsFocusableCharacter( cols[i], rows[j] ) ) { return [ cols[i], rows[j] ]; }\r\n";
    s += "                 }\r\n                 return [ x, y ];\r\n             }\r\n";
    return s;
}

// The place of a method's declaration in the class's text: `name` followed, after blanks, by '{'.
inline size_t declaration(std::string_view text, std::string_view name) {
    for (size_t at = text.find(name); at != std::string_view::npos; at = text.find(name, at + 1)) {
        const size_t next = text.find_first_not_of(" \t\r\n", at + name.size());
        if (next != std::string_view::npos && text[next] == '{') return at;
    }
    return std::string_view::npos;
}

// The interface's cursor script with the added fighters' cells; none if it is not as expected.
inline std::optional<std::string> with_cells(std::string_view script, const std::vector<Cell>& cells, bool rows) {
    struct Rename {
        std::string_view from, to;
    };
    static constexpr Rename kRenames[] = {{"GetCursorPosX( x )", "StockCursorPosX( x )"},
                                          {"GetCursorPosY( y )", "StockCursorPosY( y )"},
                                          {"IsFocusableCharacter( x, y )", "StockFocusable( x, y )"},
                                          {"GetFighterID( x, y )", "StockFighterID( x, y )"}};
    if (script.find("global::CharacterSelectCursor : class") == std::string_view::npos ||
        script.find("Stock") != std::string_view::npos) {
        return std::nullopt;
    }
    std::string out(script);
    for (const Rename& r : kRenames) {
        const size_t at = declaration(out, r.from);
        if (at == std::string::npos) return std::nullopt;
        out.replace(at, r.from.size(), r.to);
    }
    const size_t first = declaration(out, kRenames[0].to);
    const size_t line = out.rfind('\n', first);
    if (first == std::string::npos || line == std::string::npos) return std::nullopt;
    out.insert(line + 1, methods(cells, rows));
    return out;
}

// A handler of the frame's menu (OnLeft: dx -1, keys "KeyLeft" and "KeyLSLeft"; ...), as source text.
inline std::string handler(int dx, int dy, std::string_view key, std::string_view stick_key) {
    std::string s;
    s += "\t\tx : ( lib::MenuEntityGetText( \"StaticTextCharacterSelectCursorX\" ) ).to_i();\r\n";
    s += "\t\ty : ( lib::MenuEntityGetText( \"StaticTextCharacterSelectCursorY\" ) ).to_i();\r\n";
    s += "\t\tto : global::CharacterSelect.cursors[0].Move( x, y, " + number(dx) + ", " + number(dy) +
         ", ( lib::MenuMenuKeyTrig() & ( global::" + std::string(key) + " | global::" + std::string(stick_key) +
         " ) ) != 0 );\r\n";
    s += "\t\tif ( to[0] != x || to[1] != y ) {\r\n";
    s += "\t\t\tlib::MenuSoundKeyOn( lib::SoundIdCursor );\r\n";
    s += "\t\t\tglobal::CharacterSelect.cursors[0].CursorSetCharacter( to[0], to[1], \"CharacterSelect_\", true );\r\n";
    s += "\t\t\tlib::MenuEntitySetText( to[0].to_s(), \"StaticTextCharacterSelectCursorX\" );\r\n";
    s += "\t\t\tlib::MenuEntitySetText( to[1].to_s(), \"StaticTextCharacterSelectCursorY\" );\r\n";
    s += "\t\t\tlib::SetFighterIdToProfileDRC( global::CharacterSelect.cursors[0].GetFighterID( to[0], to[1] ) );\r\n";
    s += "\t\t}\r\n\t\treturn false;\r\n\t";
    return s;
}

// The fighter a shop list (the title's BXML: its first element `<Fighter id="n">`, title/customize_grid.h's
// reader of what convert/wardrobe.py writes) is listed under, as the title's parser reads it (59 is 44); none if
// the bytes are not such a file.
inline std::optional<uint32_t> shop_fighter(const std::vector<uint8_t>& d) {
    const auto be = [&](size_t at) {
        return uint32_t{d[at]} << 24 | uint32_t{d[at + 1]} << 16 | uint32_t{d[at + 2]} << 8 | d[at + 3];
    };
    if (d.size() < 0x20 + 28 || d[0] != 'B' || d[1] != 'X' || d[2] != 'M' || d[3] != 'L') return std::nullopt;
    const uint32_t size = be(4), strings = be(8), nodes = be(16);
    if (size != d.size() || nodes == 0 || nodes > (d.size() - 0x20) / 28 || strings >= d.size() || d.back() != 0) {
        return std::nullopt;
    }
    const size_t attributes = 0x20 + size_t{28} * nodes;
    const uint32_t count = be(0x20 + 20), first = be(0x20 + 24);
    const auto text = [&](uint32_t offset) -> std::string_view {
        if (offset >= d.size() - strings) return {};
        return reinterpret_cast<const char*>(&d[strings + offset]); // (the file ends with a zero)
    };
    if (text(be(0x20)) != "Fighter" || be(0x20 + 8) != 0xFFFFFFFF) return std::nullopt; // one element at the top
    for (uint32_t i = 0; i < count; ++i) {
        const size_t at = attributes + size_t{8} * (first + i);
        if (at + 8 > strings || text(be(at)) != "id") continue;
        const std::string_view value = text(be(at + 4));
        if (value.empty() || value.size() > 2 || value.find_first_not_of("0123456789") != std::string_view::npos) {
            return std::nullopt;
        }
        const uint32_t id = static_cast<uint32_t>(std::stoul(std::string(value)));
        return id == 59 ? 44 : id;
    }
    return std::nullopt;
}

// The fighter whose camera PAINT first shows an added fighter's new paint with (title/roster.cpp): the title keeps
// one camera per select id for it, for 0..58 only (59..62 zeros, then other data); an added fighter takes the
// camera of the fighter its customization comes from, the shop list's fighter, else its donor; none past the rows.
constexpr uint32_t kPaintCameraRows = 59;
inline std::optional<uint32_t> paint_camera_fighter(std::optional<uint32_t> shop, uint32_t donor) {
    const uint32_t fighter = shop ? *shop : donor;
    return fighter < kPaintCameraRows ? std::optional<uint32_t>(fighter) : std::nullopt;
}

} // namespace cafe::title::customize_grid
