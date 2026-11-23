#include "title/select_grid.h"
#include <cassert>
#include <cstdint>
#include <map>
#include <vector>
using cafe::title::select_grid::Cell;
using cafe::title::select_grid::Links;
using cafe::title::select_grid::RandomTwin;
using cafe::title::select_grid::rings;

namespace {
// A made-up grid like the title's: three rows of five cells (columns 0-4),
// the middle column's the '?' cells (2, 7, 12); cell = 5 * row + column.
// With `top` a fourth row over them (row -1, cells 20 + column, no cell at
// column 2): the first row's '?' moves up into it and cell 30 stands in the
// first row's middle.
constexpr uint32_t kUpper = 2, kLower = 30;
std::map<uint32_t, Links> grid(bool top, bool stand_in) {
    std::vector<Cell> cells;
    for (int32_t row = 0; row < 3; ++row) {
        for (int32_t column = 0; column < 5; ++column) cells.push_back({column, row, static_cast<uint32_t>(5 * row + column)});
    }
    if (top) {
        cells[kUpper].row = -1;
        for (int32_t column : {0, 1, 3, 4}) cells.push_back({column, -1, static_cast<uint32_t>(20 + column)});
        if (stand_in) cells.push_back({2, 0, kLower});
    }
    return rings(cells);
}
// A cursor moved as the port moves it: from leave(), to where the title's
// links lead, resting on arrive().
struct Cursor {
    const std::map<uint32_t, Links>& links;
    RandomTwin& twin;
    uint32_t key, cell;
    uint32_t move(uint32_t Links::* direction) {
        const uint32_t to = links.at(twin.leave(key, cell)).*direction;
        return cell = twin.arrive(key, to);
    }
    uint32_t idle() { return cell = twin.stay(twin.leave(key, cell)); }
};
} // namespace

int main() {
    // The rows and columns are rings, in column and row order.
    {
        const auto links = grid(false, false);
        assert(links.size() == 15);
        assert(links.at(1).right == 2 && links.at(2).right == 3 && links.at(3).left == 2 && links.at(2).left == 1);
        assert(links.at(4).right == 0 && links.at(0).left == 4);
        assert(links.at(2).down == 7 && links.at(7).down == 12 && links.at(12).down == 2 && links.at(2).up == 12);
    }
    // A cell alone in its row or column moves to itself.
    {
        const auto links = rings({{0, 0, 5}, {1, 0, 6}, {7, 3, 9}});
        assert(links.at(9).left == 9 && links.at(9).right == 9 && links.at(9).up == 9 && links.at(9).down == 9);
        assert(links.at(5).right == 6 && links.at(6).right == 5 && links.at(5).up == 5);
    }
    // What went wrong: the '?' moved up and nothing stood in its row, so the
    // row's cursor passed from 1 to 3.
    {
        const auto links = grid(true, false);
        assert(links.at(1).right == 3 && links.at(3).left == 1);
        assert(links.at(21).right == kUpper && links.at(kUpper).right == 23);
    }
    const auto links = grid(true, true);
    RandomTwin twin(kUpper, kLower);
    Cursor one{links, twin, 100, 6}, two{links, twin, 200, 6};
    // From the row that lost its '?': right and left reach it and go on in
    // the same row, as in the rows under it.
    assert(one.move(&Links::up) == 1);
    assert(one.move(&Links::right) == kUpper);
    assert(one.idle() == kUpper);
    assert(one.move(&Links::right) == 3);
    assert(one.move(&Links::left) == kUpper);
    assert(one.move(&Links::left) == 1);
    assert(one.move(&Links::down) == 6 && one.move(&Links::right) == 7 && one.move(&Links::right) == 8);
    // The new row's '?' is the same cell, and its cursor stays in its row.
    assert(two.move(&Links::up) == 1 && two.move(&Links::up) == 21);
    assert(two.move(&Links::right) == kUpper);
    assert(two.move(&Links::right) == 23);
    assert(two.move(&Links::left) == kUpper);
    // Two cursors on the '?', each in its own row.
    assert(one.move(&Links::left) == 7 && one.move(&Links::left) == 6);
    assert(one.move(&Links::up) == 1 && one.move(&Links::right) == kUpper);
    assert(one.idle() == kUpper && two.idle() == kUpper);
    assert(one.move(&Links::left) == 1 && two.move(&Links::left) == 21);
    // The '?' column is a ring of four places: up and down pass through
    // both places of the one cell.
    Cursor three{links, twin, 300, 7};
    assert(three.move(&Links::up) == kUpper);       // from the second row's '?' to the first row's
    assert(three.move(&Links::right) == 3);
    assert(three.move(&Links::left) == kUpper);
    assert(three.move(&Links::up) == kUpper);       // to the new row's
    assert(three.move(&Links::right) == 23);
    assert(three.move(&Links::left) == kUpper);
    assert(three.move(&Links::up) == 12);           // round to the bottom row's
    assert(three.move(&Links::down) == kUpper);     // back to the new row's
    assert(three.move(&Links::left) == 21);
    assert(three.move(&Links::right) == kUpper);
    assert(three.move(&Links::down) == kUpper);     // the first row's
    assert(three.move(&Links::left) == 1);
    assert(three.move(&Links::right) == kUpper);
    assert(three.move(&Links::down) == 7);
    // A cursor never rests on the cell that stands in.
    assert(twin.stay(kLower) == kUpper && twin.stay(kUpper) == kUpper && twin.stay(5) == 5);
    // Other cells are not touched by the twin.
    assert(twin.leave(100, 9) == 9 && twin.arrive(100, 9) == 9);
    return 0;
}
