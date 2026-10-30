#include "title/practice_checkpoint.h"
#include <cassert>
#include <stdexcept>
using namespace cafe::title::checkpoint;
int main() {
    Identity id{};id.mode=0x1000;id.kind=4;id.generation=3;
    for(size_t i=0;i<id.objects.size();++i) id.objects[i]={uint32_t(0x2000+i*0x2960),6,6,12,0,uint32_t(0x20000+96*i),0};
    assert(id.supported());
    Slot slot;std::vector<uint8_t> scratch(kScratchBytes,0xA5);
    assert(!slot.matches(id));
    preserve_scratch(scratch,[&] {
        scratch[123]=0x11;
        assert(slot.save(id,scratch));
    });
    assert(scratch[123]==0xA5);
    assert(slot.matches(id));assert(slot.bytes()[123]==0x11);
    // The title can reuse its scratch without overwriting the private slot.
    scratch[123]=0x33;assert(slot.bytes()[123]==0x11);
    auto changed=id;changed.generation++;assert(!slot.matches(changed));
    changed=id;changed.objects[0].animator++;assert(!slot.matches(changed));
    changed=id;changed.objects[0].address++;assert(!slot.matches(changed));
    changed=id;changed.objects[0].row++;assert(!slot.matches(changed));
    changed=id;changed.objects[0].animation_set++;assert(!slot.matches(changed));
    changed=id;changed.floors[1]=0x3f800000;assert(!slot.matches(changed));
    changed=id;changed.mode++;assert(!slot.matches(changed));
    changed=id;changed.objects[2].id=81;assert(!changed.supported());
    assert(!slot.save(changed,scratch));
    changed=id;changed.kind=12;assert(!changed.supported());
    bool threw=false;
    try { preserve_scratch(scratch,[&] { scratch[4]=0;throw std::runtime_error("interrupted"); }); }
    catch(const std::runtime_error&) { threw=true; }
    assert(threw && scratch[4]==0xA5);
    preserve_scratch(scratch,[&] { std::copy(slot.bytes().begin(),slot.bytes().end(),scratch.begin());assert(scratch[123]==0x11); });
    assert(scratch[123]==0x33);
    slot.clear();assert(!slot.valid() && !slot.matches(id));
}
