#include "title/test_record.h"

#include <cstdio>
#include <cstdlib>
#include <vector>

namespace record = cafe::title::test_record;

void check(bool ok, const char* message) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

uint32_t get32(const std::vector<uint8_t>& d, uint32_t at) {
    return uint32_t{d[at]} << 24 | uint32_t{d[at + 1]} << 16 | uint32_t{d[at + 2]} << 8 | d[at + 3];
}

int main() {
    // Made-up numbers: items in slots 0, 5 and 15 (with a variant), two colour registers.
    const auto spec = record::parse("abc:0=7,5=300,15=12/3,c26=40,c31=41,c51=18433");
    check(spec.has_value(), "a well-formed text is read");
    check(spec->who == "abc", "the fighter");
    check(spec->items[0] == 7 && spec->items[5] == 300 && spec->items[15] == 12, "items by slot");
    check(spec->items[1] == record::kNone && spec->items[20] == record::kNone, "slots not named are empty");
    check(spec->variants[15] == 3 && spec->variants[5] == 0xFFFF, "variants");
    check(record::parse("#12:5=1")->who == "#12", "a select id instead of a code");

    for (const char* bad : {"", "abc", ":5=1", "abc:5", "abc:21=1", "abc:-1=1", "abc:5=0", "abc:5=x", "abc:5=1/2",
                            "abc:c25=1", "abc:c96=1", "abc:c30=-1", "abc:5=1,,6=2", "abc:5=70000"})
        check(!record::parse(bad), bad);

    // The record as the title leaves an empty one: no data, slots -1, the rest zero here.
    std::vector<uint8_t> bytes(record::kSize, 0);
    for (uint32_t at = record::kItems; at < record::kItems + 4 * record::kSlots; ++at) bytes[at] = 0xFF;
    bytes[2000] = 0x5A; // (print data: not the switch's)
    record::apply(*spec, bytes.data());
    check(bytes[0] == 1, "the record holds data");
    check(get32(bytes, 4) == 7 && get32(bytes, 4 + 4 * 5) == 300 && get32(bytes, 4 + 4 * 15) == 12, "items stored");
    check(get32(bytes, 4 + 4 * 1) == 0xFFFFFFFF, "an empty slot is -1");
    check(bytes[568] == 0 && bytes[569] == 3, "slot 15's variant at +568");
    check(bytes[570] == 0xFF && bytes[571] == 0xFF && bytes[572] == 0xFF, "no variant: 0xFFFF");
    // Registers 26..30 are group 0, stored second (+636); 31..35 group 1, stored first (+576); 51 = group 5.
    check(get32(bytes, 636 + 4) == 40, "group 0 is stored at +636");
    check(get32(bytes, 576 + 4) == 41, "group 1 is stored at +576");
    check(get32(bytes, 576 + 60 * 5 + 4) == 18433, "group 5, entry 0");
    check(record::colour_offset(95) == 576 + 60 * 13 + 12 * 4, "the last register");
    check(get32(bytes, 576 + 60 * 5 + 12 + 4) == 0, "a colour not named stays the fighter's default");
    check(bytes[2000] == 0x5A, "nothing else is touched");
    std::puts("Test record tests passed");
}
