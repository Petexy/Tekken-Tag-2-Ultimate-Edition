#pragma once

// The title's data archives, content/hdd/dataNNN.ofs + dataNNN.bin. The
// .ofs file indexes the entries: each one's name hash and where it lies in
// the .bin file's payload. Every entry is scrambled with a stream keyed by its name hash;
// on the Wii U most are also zlib streams behind an "NRCZ" header.
//
// .ofs: chunks "ftyp" "head" "ofsi" (hash, word per entry) "ofsd" (one
//       offset per entry and one for the end: big-endian, the low four bits
//       the entry's length modulo 16, entries 16-byte aligned).
// .bin: chunks "ftyp" "head" "idgt", then "imge" holding the payload at
//       kPayload.

#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <vector>

namespace cafe::title::archive {

constexpr uint64_t kPayload = 0x100;

struct Entry {
    uint32_t hash = 0;
    uint64_t offset = 0; // in the payload
    uint64_t size = 0;   // as stored, before the alignment padding
};

struct Index {
    std::vector<Entry> entries;
    uint64_t payload_size = 0;
    const Entry* find(uint32_t hash) const;
};

std::optional<Index> parse_index(const std::vector<uint8_t>& ofs);

// Scrambles or unscrambles (the same operation) an entry stored at the
// start of `data`.
void scramble(uint8_t* data, size_t size, uint32_t hash);

// An entry as stored -> its contents. None if a compressed entry is damaged.
std::optional<std::vector<uint8_t>> unpack(std::vector<uint8_t> stored, uint32_t hash);

// The first bytes of an entry's contents, up to `size`, from the start of
// the entry as stored (enough of it to hold the zlib stream's code tables:
// a kilobyte does).
std::vector<uint8_t> peek(std::vector<uint8_t> stored_start, uint32_t hash, size_t size);

// The flag bytes (8 to 15) of a stored entry's NRCZ header; zero if it has
// none. `stored_start` holds at least the entry's first 16 bytes.
void stored_flags(std::vector<uint8_t> stored_start, uint32_t hash, uint8_t (&flags)[8]);

// Contents -> an entry as stored, compressed behind an NRCZ header with
// `flags` (copy them from the entry replaced).
std::vector<uint8_t> pack(const std::vector<uint8_t>& contents, uint32_t hash, const uint8_t (&flags)[8]);

// Contents -> an entry as stored, behind an NRCZ header with `flags` like
// pack's, but as a zlib stream of stored blocks: not compressed, so that its
// size, stored_size, follows from the size of the contents alone.
std::vector<uint8_t> store(const std::vector<uint8_t>& contents, uint32_t hash, const uint8_t (&flags)[8]);
uint64_t stored_size(uint64_t contents_size);

// An entry to serve, as stored: `size` bytes, held (`data`) or made each
// time the title reads it (`make`, which may run on any thread; none or
// another size reads as zeros). A fighter pack's files are served the second
// way: nothing of them is read before the title asks, and nothing is kept.
struct Source {
    uint64_t size = 0;
    std::shared_ptr<const std::vector<uint8_t>> data;
    std::function<std::optional<std::vector<uint8_t>>()> make;
};
Source held(std::vector<uint8_t> stored);

// An archive with some entries replaced or added: the new .ofs, and the new
// .bin as pieces of the original .bin and of the new entries.
struct Piece {
    uint64_t at = 0;     // in the new .bin
    uint64_t size = 0;   // with the padding to 16 bytes, which reads as zeros
    uint64_t source = 0; // in the original .bin, when `entry` is null
    std::shared_ptr<const Source> entry;
};
struct Rebuilt {
    std::vector<uint8_t> ofs;
    std::vector<Piece> bin;
    uint64_t bin_size = 0;
};

// `bin_header` is the original .bin's first kPayload bytes; `entries` maps
// name hashes to entries as stored: an entry the archive holds is replaced,
// others are added after its last entry. The title looks every name hash up
// in one tree built from all the archives' indices (the last archive read,
// data100, wins), so an entry can be added to any of them. None if the
// index does not parse, or if the new .bin would pass what the index's
// 32-bit offsets reach (4 GB).
std::optional<Rebuilt> rebuild(const std::vector<uint8_t>& ofs, const std::vector<uint8_t>& bin_header,
                               const std::map<uint32_t, std::shared_ptr<const Source>>& entries);

} // namespace cafe::title::archive
