#include "title/customize_grid.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace grid = cafe::title::customize_grid;

void check(bool ok, const char* message) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

size_t count(const std::string& text, const std::string& what) {
    size_t n = 0;
    for (size_t at = text.find(what); at != std::string::npos; at = text.find(what, at + 1)) ++n;
    return n;
}

void put32(std::vector<uint8_t>& d, uint32_t x) {
    for (int i = 0; i < 4; ++i) d.push_back(static_cast<uint8_t>(x >> (24 - 8 * i)));
}

// A made-up shop list: one element `<tag id=value>` (the title's BXML layout).
std::vector<uint8_t> shop(const char* tag, const char* value, uint32_t next = 0xFFFFFFFF) {
    std::vector<uint8_t> strings;
    const auto add = [&](const char* text) {
        const uint32_t at = static_cast<uint32_t>(strings.size());
        strings.insert(strings.end(), text, text + std::strlen(text) + 1);
        return at;
    };
    const uint32_t t = add(tag), name = add("id"), v = add(value);
    std::vector<uint8_t> d = {'B', 'X', 'M', 'L'};
    const uint32_t at = 0x20 + 28 + 8;
    put32(d, at + static_cast<uint32_t>(strings.size()));
    put32(d, at);
    put32(d, 0);
    put32(d, 1);
    for (int i = 0; i < 3; ++i) put32(d, 0);
    for (uint32_t x : {t, 0u, next, 0xFFFFFFFFu, 0u, 1u, 0u}) put32(d, x);
    put32(d, name);
    put32(d, v);
    d.insert(d.end(), strings.begin(), strings.end());
    return d;
}

int main() {
    // A made-up cursor class with the four methods the title's has (and their calls).
    const std::string script =
        "global::CharacterSelectCursor : class\r\n{\r\n    initialize() {}\r\n"
        "    GetCursorPosX( x )\r\n    {\r\n        return x * 48;\r\n    }\r\n"
        "    GetCursorPosY( y )\r\n    {\r\n        return y * 65;\r\n    }\r\n"
        "    IsFocusableCharacter( x, y )\r\n    {\r\n        return GetFighterID( x, y ) != 0;\r\n    }\r\n"
        "    Place( x, y )\r\n    {\r\n        Set( GetCursorPosX( x ), GetCursorPosY( y ) );\r\n    }\r\n"
        "    GetFighterID( x, y )\r\n    {\r\n        return 1;\r\n    }\r\n}\r\n";

    // The places: left of '?' a column is x, right of it one less; beside the rows 22.. and 24..; the new row 3.
    check(*grid::script_place(19, 0) == std::pair<int32_t, int32_t>(18, 0), "right of '?': a column less");
    check(*grid::script_place(2, 0) == std::pair<int32_t, int32_t>(2, 0), "left of '?': the column");
    check(*grid::script_place(23, 1) == std::pair<int32_t, int32_t>(22, 1), "the first column right of the rows");
    check(*grid::script_place(24, 2) == std::pair<int32_t, int32_t>(23, 2), "the second column right of the rows");
    check(*grid::script_place(-1, 1) == std::pair<int32_t, int32_t>(24, 1), "the first column left of the rows");
    check(*grid::script_place(-2, 0) == std::pair<int32_t, int32_t>(25, 0), "the second column left of the rows");
    check(*grid::script_place(12, -1) == std::pair<int32_t, int32_t>(11, 3), "the new top row is y 3");
    check(!grid::script_place(11, 0) && !grid::script_place(25, 0) && !grid::script_place(0, 3), "no such cell");

    // One fighter in the title's top row that can be entered, one that cannot; no new row.
    const auto plain = grid::with_cells(script, {{19, 0, 64, true}, {2, 0, 65, false}}, false);
    check(plain.has_value(), "the class is changed");
    for (const char* stock : {"StockCursorPosX( x )\r\n    {", "StockCursorPosY( y )\r\n    {",
                              "StockFocusable( x, y )\r\n    {", "StockFighterID( x, y )\r\n    {"})
        check(count(*plain, stock) == 1, "each of the title's methods is kept under its Stock name");
    check(count(*plain, "Set( GetCursorPosX( x ), GetCursorPosY( y ) );") == 1, "calls keep their names");
    check(count(*plain, "return GetFighterID( x, y ) != 0;") == 1, "the stock test asks the new table");
    check(plain->find("if ( x == 18 && y == 0 ) { return 64; }") != std::string::npos, "its cell names it");
    check(plain->find("if ( x == 18 && y == 0 ) { return true; }") != std::string::npos, "it can be entered");
    check(plain->find("if ( x == 2 && y == 0 ) { return false; }") != std::string::npos, "the other cannot");
    check(plain->find("return StockCursorPosY( y ) + 0;") != std::string::npos, "the rows are where they were");
    check(plain->find("rows : [ 0, 1, 2 ];") != std::string::npos, "three rows");
    check(plain->find(" 21 ];") != std::string::npos && plain->find("cols : [ 0, 1,") != std::string::npos,
          "the title's 22 columns only");
    check(plain->find("GetCursorPosX( x )\r\n             {") < plain->find("StockCursorPosX( x )"),
          "the new methods come before the title's");
    check(plain->find("initialize() {}") < plain->find("GetCursorPosX( x )"), "inside the class");

    // The new top row, and cells beside the rows.
    const auto rows = grid::with_cells(script, {{12, -1, 83, true}, {23, 1, 73, false}, {-2, 2, 80, true}}, true);
    check(rows.has_value(), "the class is changed (new row)");
    check(rows->find("if ( x == 11 && y == 3 ) { return 83; }") != std::string::npos, "a cell of the new row");
    check(rows->find("if ( x == 22 && y == 1 ) { return false; }") != std::string::npos, "a cell beside the rows");
    check(rows->find("if ( x == 25 && y == 2 ) { return true; }") != std::string::npos, "a cell left of the rows");
    check(rows->find("return StockCursorPosY( y ) + 65;") != std::string::npos, "every row is a row down");
    check(rows->find("if ( y == 3 ) { return StockCursorPosY( -1 ) + 65; }") != std::string::npos,
          "the new row is where the title's top row was");
    check(rows->find("rows : [ 3, 0, 1, 2 ];") != std::string::npos, "the new row comes first");
    check(rows->find("cols : [ 25, 24, 0, 1,") != std::string::npos && rows->find(" 21, 22 ];") != std::string::npos,
          "the columns beside the rows in the cursor's order, only those with a cell");
    // A new row without a cell in it is not a row of the cursor.
    check(grid::with_cells(script, {{19, 0, 64, true}}, true)->find("rows : [ 0, 1, 2 ];") != std::string::npos,
          "no cell in the new row: the cursor has three rows");

    check(!grid::with_cells("class Other {}", {}, false), "another script is left alone");
    check(!grid::with_cells(*plain, {}, false), "a changed script is not changed again");
    std::string broken = script;
    broken.replace(broken.find("GetCursorPosY( y )\r\n"), 18, "CursorY( y )");
    check(!grid::with_cells(broken, {}, false), "a class without one of the methods is left alone");

    const std::string left = grid::handler(-1, 0, "KeyLeft", "KeyLSLeft");
    check(left.find("Move( x, y, -1, 0, ( lib::MenuMenuKeyTrig() & ( global::KeyLeft | global::KeyLSLeft ) ) != 0 )") !=
              std::string::npos, "a handler steps its way on its keys");
    check(left.find("xtal") == std::string::npos, "a handler is source text");

    check(grid::shop_fighter(shop("Fighter", "42")) == 42u, "the list's fighter");
    check(grid::shop_fighter(shop("Fighter", "59")) == 44u, "59 is the title's fighter 44");
    check(!grid::shop_fighter(shop("Fighter", "4x")) && !grid::shop_fighter(shop("Fighter", "")), "not a number");
    check(!grid::shop_fighter(shop("Item", "42")), "another element");
    check(!grid::shop_fighter(shop("Fighter", "42", 1)), "more than one element at the top");
    check(!grid::shop_fighter({}) && !grid::shop_fighter({'B', 'X', 'M', 'L', 0, 0, 0, 8}), "not a list");
    auto cut = shop("Fighter", "42");
    cut.pop_back();
    check(!grid::shop_fighter(cut), "a cut file");
    std::puts("customize_grid_test: ok");
    return 0;
}
