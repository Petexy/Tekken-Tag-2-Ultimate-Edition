// Meshes the motion blur leaves out (title/unblurred.h): a made-up NUD, its indices copied into made-up guest memory.
#include "title/unblurred.h"
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
using namespace cafe::title::unblurred;

namespace {
std::vector<uint8_t> file;

void put32(uint32_t offset, uint32_t v) {
    for (int i = 0; i < 4; ++i) file[offset + i] = static_cast<uint8_t>(v >> (24 - 8 * i));
}
void put16(uint32_t offset, uint32_t v) {
    file[offset] = static_cast<uint8_t>(v >> 8);
    file[offset + 1] = static_cast<uint8_t>(v);
}

// Meshes "dog_body" (polygons of 5 and 3 indices), "dog_glow" (3 and 4) and "dog_tail" (3: the same indices as the
// body's second), their indices back to back. -> the index clump's offset in the file.
uint32_t make_nud() {
    const char* names[3] = {"dog_body", "dog_glow", "dog_tail"};
    const std::vector<std::vector<uint16_t>> indices = {{0, 1, 2, 3, 4}, {7, 8, 9}, {0, 1, 2}, {3, 2, 1, 0}, {7, 8, 9}};
    const uint32_t mesh_polygons[3] = {2, 2, 1};
    const uint32_t meshes = 3, count = 5, descriptors = 48 * (meshes + count);
    uint32_t index_bytes = 0;
    for (const auto& p : indices) index_bytes += 2 * static_cast<uint32_t>(p.size());
    std::string strings;
    uint32_t name_at[3];
    for (int k = 0; k < 3; ++k) {
        name_at[k] = static_cast<uint32_t>(strings.size());
        strings += names[k];
        strings.push_back('\0');
    }
    const uint32_t clump = kHeader + descriptors, strings_at = clump + index_bytes;
    file.assign(strings_at + strings.size(), 0);
    put32(0, kMagic);
    put32(4, static_cast<uint32_t>(file.size()));
    put16(10, meshes);
    put32(16, descriptors);
    put32(20, index_bytes); // (no vertex clumps)
    uint32_t polygon = 0, offset = 0;
    for (uint32_t k = 0; k < meshes; ++k) {
        put32(kHeader + 48 * k + 32, name_at[k]);
        put16(kHeader + 48 * k + 42, mesh_polygons[k]);
        put32(kHeader + 48 * k + 44, kHeader + 48 * meshes + 48 * polygon);
        for (uint32_t j = 0; j < mesh_polygons[k]; ++j, ++polygon) {
            const uint32_t record = kHeader + 48 * meshes + 48 * polygon;
            put32(record, offset);
            put16(record + 32, static_cast<uint32_t>(indices[polygon].size()));
            for (uint16_t i : indices[polygon]) {
                put16(clump + offset, i);
                offset += 2;
            }
        }
    }
    std::memcpy(file.data() + strings_at, strings.data(), strings.size());
    return clump;
}

constexpr uint32_t kGuest = 0x30000000; // where the made-up guest memory starts
std::vector<uint8_t> guest;
const uint8_t* at(uint32_t address, uint32_t bytes) {
    if (address < kGuest || address - kGuest + uint64_t{bytes} > guest.size()) return nullptr;
    return guest.data() + (address - kGuest);
}
} // namespace

int main() {
    const uint32_t clump = make_nud();

    // the file's polygons, listed or not, with their indices
    const auto all = polygons(file, {"dog_glow"});
    assert(all.size() == 5);
    assert(!all[0].first && !all[1].first && all[2].first && all[3].first && !all[4].first);
    assert(all[3].second == (Indices{0, 3, 0, 2, 0, 1, 0, 0}));
    assert(polygons(std::vector<uint8_t>(file.begin() + 4, file.end()), {"dog_glow"}).empty()); // not a NUD
    std::vector<uint8_t> cut(file.begin(), file.begin() + clump + 6);
    assert(polygons(cut, {"dog_glow"}).empty());                                                 // cut short

    // the title's copy of the index clump, as the GPU reads it
    guest.assign(0x100, 0xEE);
    guest.insert(guest.end(), file.begin() + clump, file.begin() + clump + 30);
    const uint32_t copy = kGuest + 0x100;
    Polygons listed;
    assert(listed.empty() && !listed.find(at, copy + 16, 3));
    assert(listed.add(file, {"dog_glow"}) == 2 && !listed.empty());
    assert(listed.find(at, copy + 16, 3) && listed.find(at, copy + 22, 4)); // the glow's polygons
    assert(!listed.find(at, copy, 5) && !listed.find(at, copy + 10, 3));     // the body's
    assert(!listed.find(at, copy + 16, 2) && !listed.find(at, copy + 22, 3)); // other counts
    assert(!listed.find(at, copy + 18, 3) && !listed.find(at, 0x10000000, 3)); // other indices; nothing there
    assert(listed.add(file, {"dog_glow"}) == 0);                              // (each once)

    // a listed polygon whose indices an unlisted one has too is left out (a draw of them could be the body's)
    Polygons tail;
    assert(tail.add(file, {"dog_tail"}) == 0 && tail.empty());
    assert(!tail.find(at, copy + 10, 3));
    Polygons both;
    assert(both.add(file, {"dog_body", "dog_tail"}) == 2 && both.find(at, copy + 10, 3) && both.find(at, copy, 5)); // (alike: once)

    // the counts some listed polygon has, as bits
    const std::vector<uint64_t> bits = listed.count_bits();
    assert(bits.size() == 1 && bits[0] == ((1u << 3) | (1u << 4)));
    assert(Polygons{}.count_bits().empty());

    // answers remembered per draw: compared once per generation, again when its first or last indices changed
    Remembered seen;
    assert(seen.find(listed, at, copy + 16, 3, 0) && seen.find(listed, at, copy + 16, 3, 0) && seen.compared() == 1);
    assert(!seen.find(listed, at, copy + 10, 3, 0) && !seen.find(listed, at, copy + 10, 3, 0) && seen.compared() == 2);
    assert(seen.find(listed, at, copy + 16, 3, 1) && seen.compared() == 3);   // a new generation
    guest[0x100 + 16] = 0x7F;                                                 // other indices there now
    assert(!seen.find(listed, at, copy + 16, 3, 1) && seen.compared() == 4);
    guest[0x100 + 16] = 0x00;
    assert(seen.find(listed, at, copy + 16, 3, 1) && seen.compared() == 5);
    assert(!seen.find(listed, at, 0x10000000, 3, 1) && seen.compared() == 5); // nothing there: not compared
    return 0;
}
