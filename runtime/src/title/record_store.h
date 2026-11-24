#pragma once
// An added fighter's play record (rank, wins, losses), kept by the port.
//
// The title keeps the player's record with each fighter in its profile: a table of 63 rows of 76 bytes by select
// id, part of its save. A fight works on a copy of the row in the team member's block of the profile and writes it
// back to the row afterwards. An added fighter (select id 64 on) has no row: the bytes "after the table" are the
// profile's other saved fields. The port keeps such a row itself, in a file of its own per added fighter, in the
// title's layout, named by the pack's CODE (select ids move when packs are added or removed):
// `<save folder>/records/<code>.bin`, 76 bytes, big-endian as the title holds them:
//   +0  u8 rank, +2 s16 and +4..+6 u8 its progress, +12 u32 wins, +16 u32 losses      (the first set of numbers)
//   +20 u8 rank, +24 s16 and +26..+28 u8 its progress, +32 u32 wins, +36 u32 losses,
//   +40..+56 five u32                                                                 (the second set)
//   +60 four u32
// The port never interprets a row beyond the three numbers the title's own menus ask for. A file of another size
// is not a record and is left alone (the fighter then starts from an empty row).
#include <array>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>

namespace cafe::title::record_store {
constexpr uint32_t kRowSize = 76;
using Row = std::array<uint8_t, kRowSize>;

// A row's fields and where a team member's block holds them (offsets from the member's id byte); the last four
// words are kept apart from the block, 16 bytes per member.
struct Field {
    uint32_t row, member, size;
};
constexpr Field kFields[] = {
    {0, 4100, 1},  {2, 4102, 2},  {4, 4104, 1},  {5, 4105, 1},  {6, 4106, 1},  {12, 4116, 4}, {16, 4120, 4},
    {20, 4180, 1}, {24, 4184, 2}, {26, 4186, 1}, {27, 4187, 1}, {28, 4188, 1}, {32, 4192, 4}, {36, 4196, 4},
    {40, 4200, 4}, {44, 4204, 4}, {48, 4208, 4}, {52, 4212, 4}, {56, 4216, 4},
};
constexpr uint32_t kMemberSize = 4288; // a member's block
constexpr uint32_t kRest = 60, kRestSize = 16;
static_assert(kRest + kRestSize == kRowSize);

// The row into a member's block and its 16 bytes apart (what the title does when a fighter is picked).
inline void to_member(const Row& row, uint8_t* member, uint8_t* rest) {
    for (const Field& field : kFields) std::memcpy(member + field.member, row.data() + field.row, field.size);
    std::memcpy(rest, row.data() + kRest, kRestSize);
}

// The member's block back into the row (what the title does after a fight); the row's other bytes stay.
inline void from_member(Row& row, const uint8_t* member, const uint8_t* rest) {
    for (const Field& field : kFields) std::memcpy(row.data() + field.row, member + field.member, field.size);
    std::memcpy(row.data() + kRest, rest, kRestSize);
}

// The numbers the title's menus ask for: of the first set, or of the second.
inline uint32_t word(const Row& row, uint32_t at) {
    return uint32_t{row[at]} << 24 | uint32_t{row[at + 1]} << 16 | uint32_t{row[at + 2]} << 8 | row[at + 3];
}
inline uint32_t rank(const Row& row, bool second) { return row[second ? 20 : 0]; }
inline uint32_t wins(const Row& row, bool second) { return word(row, second ? 32 : 12); }
inline uint32_t losses(const Row& row, bool second) { return word(row, second ? 36 : 16); }

// A pack's code as a file name: letters, digits and '_' only (a code is a folder name the player may have made).
inline bool valid_code(std::string_view code) {
    if (code.empty() || code.size() > 32) return false;
    for (const char c : code) {
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_')) return false;
    }
    return true;
}

// The file of the fighter with this code under the port's save folder.
inline std::filesystem::path file_of(const std::filesystem::path& save_root, std::string_view code) {
    return save_root / "records" / (std::string(code) + ".bin");
}

// The file's row, if it is there and whole.
inline std::optional<Row> read(const std::filesystem::path& file) {
    std::error_code ec;
    if (!std::filesystem::is_regular_file(file, ec) || std::filesystem::file_size(file, ec) != kRowSize || ec)
        return std::nullopt;
    std::ifstream in(file, std::ios::binary);
    Row row;
    if (!in.read(reinterpret_cast<char*>(row.data()), kRowSize)) return std::nullopt;
    return row;
}

// Writes the file whole or not at all: a temporary file beside it, then a rename over it.
inline bool write(const std::filesystem::path& file, const Row& row) {
    std::error_code ec;
    std::filesystem::create_directories(file.parent_path(), ec);
    std::filesystem::path temporary = file;
    temporary += ".tmp";
    {
        std::ofstream out(temporary, std::ios::binary | std::ios::trunc);
        out.write(reinterpret_cast<const char*>(row.data()), kRowSize);
        out.flush();
        if (!out) {
            out.close();
            std::filesystem::remove(temporary, ec);
            return false;
        }
    }
    std::filesystem::rename(temporary, file, ec);
    if (ec) {
        std::filesystem::remove(temporary, ec);
        return false;
    }
    return true;
}

// The rows of the fighters used so far, by code. A row is read from its file the first time it is asked for and
// then held: the held row is the record for the rest of the session, also when the disk refuses a write (a full or
// read-only save folder). A refused row is written again with the next one that is saved, or by `retry`.
class Rows {
  public:
    // A fighter's row: the held one, else its file's, else an empty one. A code that cannot name a file has an
    // empty row every time.
    const Row& row(const std::filesystem::path& save_root, std::string_view code) {
        static const Row empty{};
        if (!valid_code(code)) return empty;
        const auto held = rows_.find(std::string(code));
        if (held != rows_.end()) return held->second.row;
        Held& made = rows_[std::string(code)];
        if (const auto file = read(file_of(save_root, code))) made.row = *file;
        return made.row;
    }

    // Takes a fighter's new row; true when every row taken so far is on the disk. An unchanged row whose file is
    // there is not written again.
    bool save(const std::filesystem::path& save_root, std::string_view code, const Row& row) {
        if (!valid_code(code)) return false;
        const auto held = rows_.find(std::string(code));
        if (held == rows_.end() || held->second.row != row || !held->second.on_disk) {
            Held& now = rows_[std::string(code)];
            // (a row never read from or written to its file may equal the file's: compare before writing)
            const bool same = read(file_of(save_root, code)) == std::optional<Row>(row);
            now.row = row;
            now.on_disk = same;
            now.waiting = !same;
        }
        return retry(save_root);
    }

    // Writes the rows the disk has not taken yet; true when none is left.
    bool retry(const std::filesystem::path& save_root) {
        bool all = true;
        for (auto& [code, held] : rows_) {
            if (!held.waiting) continue;
            if (write(file_of(save_root, code), held.row)) {
                held.waiting = false;
                held.on_disk = true;
            } else {
                all = false;
            }
        }
        return all;
    }

    bool waiting(std::string_view code) const {
        const auto held = rows_.find(std::string(code));
        return held != rows_.end() && held->second.waiting;
    }

  private:
    struct Held {
        Row row{};
        bool on_disk = false; // the file holds this row
        bool waiting = false; // a write of it is owed
    };
    std::map<std::string, Held> rows_;
};
} // namespace cafe::title::record_store
