#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <utility>

namespace cafe::title::cpu_identity {
struct Donor { uint32_t id, row; };
// AI initialization walks all four players and also inspects the opponent.
// Borrow both fields for that entire walk, restoring them even on early exit.
template<class Read, class Write, class Lookup, class Call>
void with_donors(const std::array<uint32_t, 4>& players, Read read, Write write,
                 Lookup lookup, Call call) {
    struct Saved { uint32_t player, id, row; Donor donor; };
    std::array<Saved, 4> saved{};
    std::size_t count = 0;
    struct Restore {
        std::array<Saved, 4>& saved; std::size_t& count; Read& read; Write& write;
        ~Restore() {
            while (count) {
                const auto& s = saved[--count];
                if (read(s.player + 84) == s.donor.id) write(s.player + 84, s.id);
                if (read(s.player + 80) == s.donor.row) write(s.player + 80, s.row);
            }
        }
    } restore{saved, count, read, write};
    for (const auto player : players) {
        if (!player) continue;
        bool duplicate = false;
        for (std::size_t i = 0; i < count; ++i) duplicate |= saved[i].player == player;
        if (duplicate) continue;
        const auto id = read(player + 84), row = read(player + 80);
        const auto donor = lookup(id, row);
        if (!donor) continue;
        saved[count++] = {player, id, row, *donor};
        write(player + 84, donor->id);
        write(player + 80, donor->row);
    }
    call();
}
} // namespace cafe::title::cpu_identity
