#pragma once
// Added fighters' meshes TTT2's motion blur leaves out (character.ini `unblurred`: names of meshes in the fighter's
// NUD, e.g. a Tekken 8 fighter's summoned creatures). The title draws every skinned polygon once more into a
// velocity map (its vertices this frame against last frame, both read from the skinning's stream-out records), and
// its post-process smears the picture along that map: a creature sweeping across the screen came out as blocks of
// smear where the game it comes from draws it sharp. The title draws a polygon from the NUD's own indices (copied
// as they are into graphics memory), so a draw is one of a listed mesh's polygons when its indices are that
// polygon's: their count and every index. The renderer (gpu/still_draws.h) then has its velocity draw read this
// frame's record for last frame's too: no motion, no smear. Its colour passes, and every other polygon (the
// fighter's body, every other fighter's), are drawn as before; with no pack listing meshes nothing is registered.
// Cost: a draw whose count no listed polygon has stops at a bit; one that has it is compared once (Remembered).
//
// NUD ("NDP3", big-endian): header 0x30 (+4 size, +10 mesh count, +16 the descriptors' size, +20 the index clump's);
// mesh records of 48 bytes after it (+32 its name in the string table, +42 polygon count, +44 its first polygon
// record); polygon records of 48 (+0 its indices' offset in the index clump, +32 their count, 16-bit). The index
// clump follows the descriptors; the string table follows the index, vertex and vertex-add clumps.
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>

namespace cafe::title::unblurred {
constexpr uint32_t kMagic = 0x4E445033; // "NDP3"
constexpr uint32_t kHeader = 0x30, kRecord = 48, kLongestName = 128;

using Indices = std::vector<uint8_t>; // a polygon's indices as the NUD stores them (16-bit, big-endian)

namespace detail {
inline bool get32(const std::vector<uint8_t>& d, uint64_t offset, uint32_t& v) {
    if (offset + 4 > d.size()) return false;
    v = uint32_t{d[offset]} << 24 | uint32_t{d[offset + 1]} << 16 | uint32_t{d[offset + 2]} << 8 | d[offset + 3];
    return true;
}
inline bool get16(const std::vector<uint8_t>& d, uint64_t offset, uint32_t& v) {
    if (offset + 2 > d.size()) return false;
    v = uint32_t{d[offset]} << 8 | d[offset + 1];
    return true;
}
} // namespace detail

// The polygons of a NUD file (`nud`, its bytes): (listed: its mesh is named in `names`, indices). None where it does
// not add up.
inline std::vector<std::pair<bool, Indices>> polygons(const std::vector<uint8_t>& nud, const std::vector<std::string>& names) {
    using detail::get16, detail::get32;
    std::vector<std::pair<bool, Indices>> out;
    uint32_t magic = 0, meshes = 0, clumps[4] = {};
    if (!get32(nud, 0, magic) || magic != kMagic || !get16(nud, 10, meshes)) return {};
    for (uint32_t i = 0; i < 4; ++i) {
        if (!get32(nud, 16 + 4 * i, clumps[i])) return {};
    }
    const uint64_t indices = uint64_t{kHeader} + clumps[0], strings = indices + clumps[1] + clumps[2] + clumps[3];
    if (strings > nud.size()) return {};
    for (uint32_t k = 0; k < meshes; ++k) {
        const uint64_t record = kHeader + uint64_t{kRecord} * k;
        uint32_t name = 0, count = 0, first = 0;
        if (!get32(nud, record + 32, name) || !get16(nud, record + 42, count) || !get32(nud, record + 44, first)) return {};
        std::string text;
        for (uint64_t i = strings + name; i < nud.size() && text.size() < kLongestName && nud[i] != 0; ++i)
            text.push_back(static_cast<char>(nud[i]));
        const bool listed = std::find(names.begin(), names.end(), text) != names.end();
        for (uint32_t j = 0; j < count; ++j) {
            uint32_t offset = 0, n = 0;
            const uint64_t polygon = first + uint64_t{kRecord} * j;
            if (!get32(nud, polygon, offset) || !get16(nud, polygon + 32, n)) return {};
            if (n == 0 || offset + 2ull * n > clumps[1]) return {};
            const auto begin = nud.begin() + static_cast<std::ptrdiff_t>(indices + offset);
            out.emplace_back(listed, Indices(begin, begin + 2 * n));
        }
    }
    return out;
}

// The listed meshes' polygons of the fighters whose packs list some (built at start-up, read-only after).
class Polygons {
public:
    // A NUD's polygons of the meshes `names` (one whose indices another of its polygons has too is left out: a draw
    // of those indices could be either). -> how many.
    size_t add(const std::vector<uint8_t>& nud, const std::vector<std::string>& names) {
        const auto all = polygons(nud, names);
        size_t added = 0;
        for (const auto& [listed, indices] : all) {
            if (!listed) continue;
            if (std::any_of(all.begin(), all.end(), [&](const auto& p) { return !p.first && p.second == indices; })) continue;
            auto& with = by_count_[static_cast<uint32_t>(indices.size() / 2)];
            if (std::find(with.begin(), with.end(), indices) == with.end()) {
                with.push_back(indices);
                ++added;
            }
        }
        return added;
    }
    bool empty() const { return by_count_.empty(); }

    // Bit n set: some listed polygon has n indices (most draws' counts miss: gpu::StillDraws::counted).
    std::vector<uint64_t> count_bits() const {
        std::vector<uint64_t> bits(by_count_.empty() ? 0 : by_count_.rbegin()->first / 64 + 1);
        for (const auto& [count, with] : by_count_) bits[count / 64] |= uint64_t{1} << (count % 64);
        return bits;
    }

    // A draw of `count` indices at `address` (read through at(address, bytes): the bytes, or null) is one of them.
    template <class At> bool find(const At& at, uint32_t address, uint32_t count) const {
        const auto it = by_count_.find(count);
        if (it == by_count_.end()) return false;
        const uint8_t* indices = at(address, 2 * count);
        if (indices == nullptr) return false;
        return std::any_of(it->second.begin(), it->second.end(),
                           [&](const Indices& p) { return std::memcmp(p.data(), indices, p.size()) == 0; });
    }

private:
    std::map<uint32_t, std::vector<Indices>> by_count_;
};

// The answers for the draws seen (their indices' address and count), so the same draw is not compared again every
// frame. One stands while the generation is the one it was found in (the title starts a new one when its fighters'
// models can have moved: a match's, a round's set-up) and the draw's first and last indices are still the ones it
// saw; else the draw is compared again. (One thread: the renderer's.)
class Remembered {
public:
    template <class At>
    bool find(const Polygons& polygons, const At& at, uint32_t address, uint32_t count, uint32_t generation) {
        const uint8_t* indices = at(address, 2 * count);
        if (indices == nullptr) return false;
        uint64_t first = 0, last = 0;
        const size_t bytes = std::min<size_t>(8, 2 * size_t{count});
        std::memcpy(&first, indices, bytes);
        std::memcpy(&last, indices + 2 * size_t{count} - bytes, bytes);
        const uint64_t key = uint64_t{address} << 32 | count;
        const auto it = seen_.find(key);
        if (it != seen_.end() && it->second.generation == generation && it->second.first == first &&
            it->second.last == last) {
            return it->second.found;
        }
        if (seen_.size() >= kMostSeen) seen_.clear();
        ++compared_;
        const bool found = polygons.find(at, address, count);
        seen_[key] = {generation, first, last, found};
        return found;
    }
    size_t compared() const { return compared_; } // draws compared in full (the rest answered from memory)

private:
    static constexpr size_t kMostSeen = 4096;
    struct Seen {
        uint32_t generation;
        uint64_t first, last;
        bool found;
    };
    std::unordered_map<uint64_t, Seen> seen_;
    size_t compared_ = 0;
};

} // namespace cafe::title::unblurred
