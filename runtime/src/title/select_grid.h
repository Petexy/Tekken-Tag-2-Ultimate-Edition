#pragma once

#include <algorithm>
#include <cstdint>
#include <map>
#include <tuple>
#include <vector>

// The character select's grid of cells, as the port joins the added
// fighters' cells to the title's own. No runtime: tests use it on made-up
// grids.
namespace cafe::title::select_grid {

struct Cell {
    int32_t column, row;
    uint32_t cell; // its index in the grid
};
// The cells the cursor moves to from a cell.
struct Links {
    uint32_t up, down, left, right;
};

// Each row a ring left and right in column order, each column a ring up and
// down in row order (as the title's own cells are): a cell alone in its row
// or column moves to itself.
inline std::map<uint32_t, Links> rings(std::vector<Cell> cells) {
    std::map<uint32_t, Links> links;
    for (const Cell& c : cells) links[c.cell] = {c.cell, c.cell, c.cell, c.cell};
    auto ring = [&](auto same, auto along, uint32_t Links::* back, uint32_t Links::* ahead) {
        std::sort(cells.begin(), cells.end(), [&](const Cell& a, const Cell& b) {
            return std::tuple(same(a), along(a), a.cell) < std::tuple(same(b), along(b), b.cell);
        });
        for (size_t i = 0; i < cells.size();) {
            size_t j = i;
            while (j < cells.size() && same(cells[j]) == same(cells[i])) ++j;
            for (size_t n = i; n < j; ++n) {
                const uint32_t next = cells[n + 1 < j ? n + 1 : i].cell;
                links[cells[n].cell].*ahead = next;
                links[next].*back = cells[n].cell;
            }
            i = j;
        }
    };
    const auto row = [](const Cell& c) { return c.row; };
    const auto column = [](const Cell& c) { return c.column; };
    ring(row, column, &Links::left, &Links::right);
    ring(column, row, &Links::up, &Links::down);
    return links;
}

// The '?' (random) of two rows in one cell. The title knows its '?' cells by
// their index (what they pick, what the cursor shows on them, the buttons
// that do nothing there), three of them, one for each of its rows; a grid
// with one more row has one '?' too few. So one of the title's, `upper`,
// stands for two places: its own and that of `lower`, a cell of the grid
// that is joined to its neighbours like any other but that no cursor ever
// rests on. Each cursor remembers which of the two it is at. The title moves
// a cursor from leave() and, when the move is done, the cursor is put on
// arrive(); stay() when it did not move. (On a '?' the cursor is one frame
// over the whole column, so the two places look the same.)
class RandomTwin {
public:
    RandomTwin(uint32_t upper, uint32_t lower) : upper_(upper), lower_(lower) {}
    uint32_t upper() const { return upper_; }
    uint32_t lower() const { return lower_; }
    // The cell the title moves `cursor` from, which rests on `cell`.
    uint32_t leave(uint32_t cursor, uint32_t cell) const {
        const auto it = at_lower_.find(cursor);
        return cell == upper_ && it != at_lower_.end() && it->second ? lower_ : cell;
    }
    // The cell `cursor` rests on after the title moved it to `cell`.
    uint32_t arrive(uint32_t cursor, uint32_t cell) {
        if (cell == upper_ || cell == lower_) at_lower_[cursor] = cell == lower_;
        return stay(cell);
    }
    // The cell a cursor rests on that the title left on `cell`.
    uint32_t stay(uint32_t cell) const { return cell == lower_ ? upper_ : cell; }

private:
    uint32_t upper_, lower_;
    std::map<uint32_t, bool> at_lower_; // by cursor: at `lower`'s place
};

} // namespace cafe::title::select_grid
