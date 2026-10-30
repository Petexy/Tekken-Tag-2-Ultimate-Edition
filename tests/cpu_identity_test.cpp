#include "title/cpu_identity.h"
#include <cassert>
#include <map>
#include <stdexcept>
using cafe::title::cpu_identity::Donor;
using cafe::title::cpu_identity::with_donors;
int main() {
    std::map<uint32_t, uint32_t> memory;
    const std::array<uint32_t, 4> players{0x1000, 0x2000, 0x3000, 0x4000};
    for (unsigned i=0; i<4; ++i) {
        memory[players[i]+84]=i ? 68+i : 13;
        memory[players[i]+80]=i ? 68+i : 13;
    }
    auto read=[&](uint32_t at) { return memory.at(at); };
    auto write=[&](uint32_t at,uint32_t value) { memory[at]=value; };
    auto lookup=[](uint32_t id,uint32_t row)->std::optional<Donor> {
        if (id>=69 && id<=71 && row==id) return Donor{38,38};
        return std::nullopt;
    };
    const auto original=memory;
    // The original routine replaces its current-player pointer mid-call and
    // reads BOTH members' tables. All four must already have valid metadata.
    with_donors(players,read,write,lookup,[&] {
        for (unsigned i=0;i<4;++i) {
            for (auto p : {players[i],players[(i+1)%4]}) {
                assert(read(p+84)<63);
                assert(read(p+80)<67);
            }
        }
        with_donors(players,read,write,lookup,[&] { assert(read(players[2]+84)==38); });
        assert(read(players[2]+84)==38); // nested call must not restore outer scope
        memory[0x9000]=123; // AI's resulting state must survive restoration
    });
    for (auto [at,value]:original) assert(read(at)==value);
    assert(read(0x9000)==123);
    bool threw=false;
    try {
        with_donors(players,read,write,lookup,[&] { throw std::runtime_error("early exit"); });
    } catch (const std::runtime_error&) { threw=true; }
    assert(threw);
    for (auto [at,value]:original) assert(read(at)==value);
    // Repeated/null pointers are safe; actual game changes are not overwritten.
    with_donors(std::array<uint32_t,4>{players[1],players[1],0,0},read,write,lookup,[&] {
        write(players[1]+84,7);
    });
    assert(read(players[1]+84)==7);
    assert(read(players[1]+80)==69);
    // A mismatched row is not mistaken for a live installed fighter.
    write(players[2]+80,12);
    with_donors(players,read,write,lookup,[&] { assert(read(players[2]+84)==70); });
    assert(read(players[2]+80)==12);
}
