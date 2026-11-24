#include "title/record_store.h"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>

namespace store = cafe::title::record_store;
namespace fs = std::filesystem;

void check(bool ok, const char* message) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

void put32(store::Row& row, uint32_t at, uint32_t value) {
    for (uint32_t i = 0; i < 4; ++i) row[at + i] = static_cast<uint8_t>(value >> (24 - 8 * i));
}

// A made-up row: rank 7 with 12 wins and 5 losses, a second set, the four words at the end.
store::Row made_up() {
    store::Row row{};
    row[0] = 7;
    row[2] = 0xFF;
    row[3] = 0xFE; // progress -2
    row[4] = 1;
    row[5] = 2;
    row[6] = 3;
    put32(row, 12, 12);
    put32(row, 16, 5);
    row[20] = 9;
    put32(row, 32, 300);
    put32(row, 36, 70000);
    for (uint32_t at = 40; at < store::kRowSize; at += 4) put32(row, at, 0x01020300 + at);
    return row;
}

int main() {
    const store::Row row = made_up();
    check(store::rank(row, false) == 7 && store::wins(row, false) == 12 && store::losses(row, false) == 5,
          "the first set's numbers");
    check(store::rank(row, true) == 9 && store::wins(row, true) == 300 && store::losses(row, true) == 70000,
          "the second set's numbers");

    // A member's block and back: every field the title copies, nothing else of the block.
    std::vector<uint8_t> member(store::kMemberSize, 0xAA), rest(store::kRestSize, 0xAA);
    store::to_member(row, member.data(), rest.data());
    check(member[4100] == 7 && member[4119] == 12 && member[4123] == 5 && member[4180] == 9, "fields in the block");
    check(member[0] == 0xAA && member[4099] == 0xAA && member[4101] == 0xAA && member[4107] == 0xAA &&
              member[4287] == 0xAA,
          "the block's other bytes stay");
    store::Row back{};
    back[1] = 0x55; // a byte of the row the block does not hold
    store::from_member(back, member.data(), rest.data());
    store::Row expected = row;
    expected[1] = 0x55;
    check(back == expected, "the row comes back from the block");
    for (const store::Field& field : store::kFields) {
        check(field.row + field.size <= store::kRest && field.member + field.size <= store::kMemberSize,
              "fields lie within the row and the block");
    }

    check(store::valid_code("abc") && store::valid_code("a_1") && !store::valid_code("") &&
              !store::valid_code("../abc") && !store::valid_code("a/b") && !store::valid_code("a.b") &&
              !store::valid_code(std::string(33, 'a')),
          "codes that may name a file");

    const fs::path root = fs::temp_directory_path() / ("record_store_test_" + std::to_string(std::rand()));
    fs::remove_all(root);
    check(store::file_of(root, "abc") == root / "records" / "abc.bin", "the file's place");

    {
        store::Rows rows;
        check(rows.row(root, "abc") == store::Row{}, "no file: an empty row");
        check(!fs::exists(root), "asking writes nothing");
        check(rows.save(root, "abc", row), "a row is saved");
        check(fs::file_size(store::file_of(root, "abc")) == store::kRowSize, "the file is one row");
        check(rows.row(root, "abc") == row, "the saved row is the fighter's");
        check(rows.row(root, "xyz") == store::Row{}, "another fighter's row is its own");
        check(rows.row(root, "../abc") == store::Row{} && !rows.save(root, "../abc", row),
              "a code that cannot name a file has no record");
        check(!fs::exists(root / "abc.bin"), "nothing is written outside the folder");
    }
    {
        // A new session (the game started again), other fighters added and removed meanwhile.
        store::Rows rows;
        store::Row other = row;
        other[0] = 3;
        check(rows.save(root, "xyz", other), "another fighter's row");
        check(rows.row(root, "abc") == row, "the row is read back by the fighter's code");
        fs::remove(store::file_of(root, "xyz"));
        store::Rows next;
        check(next.row(root, "abc") == row && next.row(root, "xyz") == store::Row{},
              "a removed fighter's file does not touch the others");
    }
    {
        // Files that are not records are left alone.
        std::ofstream(store::file_of(root, "bad"), std::ios::binary) << "short";
        store::Rows rows;
        check(rows.row(root, "bad") == store::Row{}, "a file of another size is no record");
        check(fs::file_size(store::file_of(root, "bad")) == 5, "and is not touched by reading");
        check(!fs::exists(store::file_of(root, "abc").string() + ".tmp"), "no temporary file is left");
    }
    {
        // The disk refuses (the save folder's place is taken by a file): the row is held and written later.
        const fs::path blocked = root / "blocked";
        std::ofstream(blocked) << "x";
        store::Rows rows;
        check(!rows.save(blocked, "abc", row), "a refused write is reported");
        check(rows.row(blocked, "abc") == row && rows.waiting("abc"), "the row is held for the session");
        fs::remove(blocked);
        check(rows.retry(blocked) && !rows.waiting("abc"), "and written when the disk takes it");
        check(store::read(store::file_of(blocked, "abc")) == std::optional<store::Row>(row), "whole");
        check(rows.save(blocked, "abc", row), "an unchanged row is not a new write");
    }
    fs::remove_all(root);
    std::puts("record_store_test: ok");
    return 0;
}
