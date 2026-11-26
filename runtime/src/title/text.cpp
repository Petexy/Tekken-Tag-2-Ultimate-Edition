#include "title/text.h"

#include <algorithm>
#include <cstring>
#include <map>
#include <optional>
#include <set>
#include <span>
#include <string>
#include <string_view>

namespace cafe::title::text {
namespace {

// In the rewrites, these bytes stand for icons.
constexpr char kA = '\x01', kB = '\x02', kX = '\x03', kY = '\x04', kStart = '\x05', kSelect = '\x06', kCross = '\x07';

char32_t icon(char c) {
    switch (c) {
    case kA: return kRightButton; // the Wii U's A is the right face button
    case kB: return kBottomButton;
    case kX: return kTopButton;
    case kY: return kLeftButton;
    case kStart: return kStartButton;
    case kSelect: return kSelectButton;
    default: return kPad;
    }
}

struct Rewrite {
    std::string_view from, to;
};

// The prompts to press Start, whole (the title screen's and the attract
// mode's): their translations put the icon where the phrasing allows.
constexpr Rewrite kPrompts[] = {
    {"PRESS THE + BUTTON", "PRESS \x05 BUTTON"},
    {"APPUYER SUR LE BOUTON +", "APPUYER SUR LE BOUTON \x05"},
    {"PREMI IL PULSANTE +", "PREMI IL PULSANTE \x05"},
    {"PLUS/START-KNOPF DR\xC3\x9C" "CKEN", "\x05-KNOPF DR\xC3\x9C" "CKEN"},
    {"PULSA EL BOT\xC3\x93N +", "PULSA \x05"},
    {"\xD0\x9D\xD0\x90\xD0\x96\xD0\x90\xD0\xA2\xD0\xAC START", "\xD0\x9D\xD0\x90\xD0\x96\xD0\x90\xD0\xA2\xD0\xAC \x05"},
    {"NACI\xC5\x9ANIJ PRZYCISK +", "NACI\xC5\x9ANIJ \x05"}, // (our Polish)
};

// Button names within texts, each language's: the name becomes the icon
// ("press the X Button" -> "press the [X]"), which is always shorter. A
// name starting or ending with a letter only matches as a whole word.
constexpr Rewrite kNames[] = {
    // English
    {"A, B, X, and Y Buttons", "\x01, \x02, \x03, and \x04"},
    {"+ Control Pad", "\x07"},
    {"+Control Pad", "\x07"},
    {"+ Button", "\x05"},
    {"- Button", "\x06"},
    {"A Button", "\x01"},
    {"B Button", "\x02"},
    {"X Button", "\x03"},
    {"Y Button", "\x04"},
    // French
    {"boutons A, B, X et Y", "\x01, \x02, \x03 et \x04"},
    {"manette +", "\x07"},
    {"bouton +", "\x05"},
    {"touche +", "\x05"},
    {"bouton -", "\x06"},
    {"bouton A", "\x01"},
    {"bouton B", "\x02"},
    {"bouton X", "\x03"},
    {"bouton Y", "\x04"},
    // Italian
    {"pulsantiera +", "\x07"},
    {"pulsante +", "\x05"},
    {"pulsante -", "\x06"},
    {"pulsante A", "\x01"},
    {"pulsante B", "\x02"},
    {"pulsante X", "\x03"},
    {"pulsante Y", "\x04"},
    // German
    {"A-, B-, X- oder Y-Knopf", "\x01, \x02, \x03 oder \x04"},
    {"PLUS/START-Knopf", "\x05"},
    {"Minus-Knopf", "\x06"},
    {"A-Knopf", "\x01"},
    {"B-Knopf", "\x02"},
    {"X-Knopf", "\x03"},
    {"Y-Knopf", "\x04"},
    // Spanish
    {"botones A, B, X e Y", "\x01, \x02, \x03 e \x04"},
    {"bot\xC3\xB3n +", "\x05"},
    {"Bot\xC3\xB3n +", "\x05"},
    {"bot\xC3\xB3n -", "\x06"},
    {"Bot\xC3\xB3n -", "\x06"},
    {"bot\xC3\xB3n A", "\x01"},
    {"Bot\xC3\xB3n A", "\x01"},
    {"bot\xC3\xB3n B", "\x02"},
    {"Bot\xC3\xB3n B", "\x02"},
    {"bot\xC3\xB3n X", "\x03"},
    {"Bot\xC3\xB3n X", "\x03"},
    {"bot\xC3\xB3n Y", "\x04"},
    {"Bot\xC3\xB3n Y", "\x04"},
    // Russian (the PlayStation 3's and Xbox 360's texts: START is the + Button, SELECT and BACK the - Button)
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD1\x83 START", "\x05"},
    {"\xD0\x9D\xD0\xB0\xD0\xB6\xD0\xB0\xD1\x82\xD1\x8C START", "\xD0\x9D\xD0\xB0\xD0\xB6\xD0\xB0\xD1\x82\xD1\x8C \x05"},
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD1\x83 SELECT", "\x06"},
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD1\x83 BACK", "\x06"},
    // and our translations' (text_russian.inc): "кнопками A, B, X и Y", "кнопку +", "кнопку -", "кнопку A" ...,
    // "крестовину" (the +Control Pad)
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD0\xB0\xD0\xBC\xD0\xB8 A, B, X \xD0\xB8 Y", "\x01, \x02, \x03 \xD0\xB8 \x04"},
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD1\x83 +", "\x05"},
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD1\x83 -", "\x06"},
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD1\x83 A", "\x01"},
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD1\x83 B", "\x02"},
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD1\x83 X", "\x03"},
    {"\xD0\xBA\xD0\xBD\xD0\xBE\xD0\xBF\xD0\xBA\xD1\x83 Y", "\x04"},
    {"\xD0\xBA\xD1\x80\xD0\xB5\xD1\x81\xD1\x82\xD0\xBE\xD0\xB2\xD0\xB8\xD0\xBD\xD1\x83", "\x07"},
    // Polish (our translations, text_polish.inc): "przycisk A" and the cases the texts use ("przycisku A",
    // "przyciskiem A"), "przyciski A, B, X i Y" ..., "krzy\xC5\xBC" "ak" (the +Control Pad) and its cases
    {"przycisk A", "\x01"}, {"przycisk B", "\x02"}, {"przycisk X", "\x03"}, {"przycisk Y", "\x04"},
    {"przycisk +", "\x05"}, {"przycisk -", "\x06"}, {"przycisku A", "\x01"}, {"przycisku B", "\x02"},
    {"przycisku X", "\x03"}, {"przycisku Y", "\x04"}, {"przycisku +", "\x05"}, {"przycisku -", "\x06"},
    {"przyciskiem A", "\x01"}, {"przyciskiem B", "\x02"}, {"przyciskiem X", "\x03"}, {"przyciskiem Y", "\x04"},
    {"przyciskiem +", "\x05"}, {"przyciskiem -", "\x06"}, {"Przycisk A", "\x01"}, {"Przycisk B", "\x02"},
    {"Przycisk X", "\x03"}, {"Przycisk Y", "\x04"}, {"Przycisk +", "\x05"}, {"Przycisk -", "\x06"},
    {"Przycisku A", "\x01"}, {"Przycisku B", "\x02"}, {"Przycisku X", "\x03"}, {"Przycisku Y", "\x04"},
    {"Przycisku +", "\x05"}, {"Przycisku -", "\x06"}, {"Przyciskiem A", "\x01"}, {"Przyciskiem B", "\x02"},
    {"Przyciskiem X", "\x03"}, {"Przyciskiem Y", "\x04"}, {"Przyciskiem +", "\x05"}, {"Przyciskiem -", "\x06"},
    {"przyciski A, B, X i Y", "\x01, \x02, \x03 i \x04"},
    {"przycisk\xC3\xB3w A, B, X i Y", "\x01, \x02, \x03 i \x04"},
    {"przyciskami A, B, X i Y", "\x01, \x02, \x03 i \x04"}, {"Przyciski A, B, X i Y", "\x01, \x02, \x03 i \x04"},
    {"Przycisk\xC3\xB3w A, B, X i Y", "\x01, \x02, \x03 i \x04"},
    {"Przyciskami A, B, X i Y", "\x01, \x02, \x03 i \x04"}, {"krzy\xC5\xBC" "ak", "\x07"},
    {"krzy\xC5\xBC" "aka", "\x07"}, {"krzy\xC5\xBC" "akiem", "\x07"}, {"krzy\xC5\xBC" "aku", "\x07"},
    {"Krzy\xC5\xBC" "ak", "\x07"}, {"Krzy\xC5\xBC" "aka", "\x07"}, {"Krzy\xC5\xBC" "akiem", "\x07"},
    {"Krzy\xC5\xBC" "aku", "\x07"},
};

// A text's space: its bytes and at least two zero bytes, to four. A key's:
// at least one zero byte.
size_t text_space(size_t bytes) { return (bytes + 2 + 3) & ~size_t{3}; }
size_t key_space(size_t bytes) { return (bytes + 1 + 3) & ~size_t{3}; }

// Letters, digits and anything not ASCII (letters of other alphabets).
bool wordlike(char c) {
    const auto u = static_cast<unsigned char>(c);
    return u >= 0x80 || std::isalnum(u);
}

size_t characters(std::string_view utf8) {
    return static_cast<size_t>(std::count_if(utf8.begin(), utf8.end(), [](char c) { return (c & 0xC0) != 0x80; }));
}

void append_utf8(std::string& out, char32_t c) {
    if (c < 0x80) {
        out += static_cast<char>(c);
    } else if (c < 0x800) {
        out += static_cast<char>(0xC0 | (c >> 6));
        out += static_cast<char>(0x80 | (c & 0x3F));
    } else if (c < 0x10000) {
        out += static_cast<char>(0xE0 | (c >> 12));
        out += static_cast<char>(0x80 | ((c >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (c & 0x3F));
    } else {
        out += static_cast<char>(0xF0 | (c >> 18));
        out += static_cast<char>(0x80 | ((c >> 12) & 0x3F));
        out += static_cast<char>(0x80 | ((c >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (c & 0x3F));
    }
}

// `to` with its icon bytes as the icons' UTF-8.
std::string expand(std::string_view to) {
    std::string out;
    for (const char c : to) {
        if (c >= kA && c <= kCross) append_utf8(out, icon(c));
        else out += c;
    }
    return out;
}

// The text with button names as icons; unchanged if it names none.
std::string rewrite(std::string_view text) {
    for (const Rewrite& r : kPrompts) {
        if (text == r.from) return expand(r.to);
    }
    std::string out;
    size_t i = 0;
    while (i < text.size()) {
        const Rewrite* match = nullptr;
        for (const Rewrite& r : kNames) {
            if (text.compare(i, r.from.size(), r.from) != 0) continue;
            if (wordlike(r.from.front()) && i > 0 && wordlike(text[i - 1])) continue;
            const size_t end = i + r.from.size();
            if (wordlike(r.from.back()) && end < text.size() && wordlike(text[end])) continue;
            match = &r;
            break;
        }
        if (match) {
            out += expand(match->to);
            i += match->from.size();
        } else {
            out += text[i++];
        }
    }
    return out;
}

// The zero-terminated string at `at` (empty if it runs off the end).
std::string_view string_at(const std::vector<uint8_t>& bank, size_t at) {
    if (at >= bank.size()) return {};
    const auto* begin = reinterpret_cast<const char*>(bank.data() + at);
    const void* end = std::memchr(begin, 0, bank.size() - at);
    return end ? std::string_view(begin, static_cast<size_t>(static_cast<const char*>(end) - begin)) : std::string_view{};
}

// A key: letters, '_', digits ("common_4", "Manu_627").
bool is_key(std::string_view key) {
    const size_t underscore = key.find('_');
    if (underscore == 0 || underscore == std::string_view::npos || underscore + 1 >= key.size()) return false;
    const auto letters = key.substr(0, underscore), digits = key.substr(underscore + 1);
    return std::all_of(letters.begin(), letters.end(), [](char c) { return std::isalpha(static_cast<unsigned char>(c)); }) &&
           std::all_of(digits.begin(), digits.end(), [](char c) { return std::isdigit(static_cast<unsigned char>(c)); });
}

// A key after the previous record's padding.
bool key_at(const std::vector<uint8_t>& bank, size_t at, std::string_view& key) {
    if (at == 0 || bank[at - 1] != 0) return false;
    key = string_at(bank, at);
    return is_key(key);
}

} // namespace

bool is_bank(const std::vector<uint8_t>& contents) {
    return contents.size() >= 0x30 && std::memcmp(contents.data(), "NTXB", 4) == 0;
}

namespace {

// Calls `visit(header, start, text)` for each text of the bank, in order;
// `visit` returns where to go on looking (past what it wrote) or 0.
template <typename Visit>
void each_text(const std::vector<uint8_t>& bank, Visit&& visit) {
    if (!is_bank(bank)) return;
    for (size_t at = 0x30; at + 8 < bank.size(); at += 4) {
        std::string_view key;
        if (!key_at(bank, at, key)) continue;
        const size_t header = at + key_space(key.size());
        const size_t start = header + 4;
        if (start >= bank.size()) continue;
        const std::string_view text = string_at(bank, start);
        if ((size_t{bank[header + 2]} << 8 | bank[header + 3]) != characters(text)) continue; // not a record
        if (const size_t next = visit(header, start, text)) at = next - 4;
    }
}

} // namespace

int show_button_icons(std::vector<uint8_t>& bank) {
    int changed = 0;
    each_text(bank, [&](size_t header, size_t start, std::string_view text) -> size_t {
        const std::string to = rewrite(text);
        const size_t room = text_space(text.size());
        if (to == text || to.size() + 2 > room || start + room > bank.size()) return 0;
        std::memset(&bank[start], 0, room);
        std::memcpy(&bank[start], to.data(), to.size());
        const size_t count = characters(to);
        bank[header + 2] = static_cast<uint8_t>(count >> 8);
        bank[header + 3] = static_cast<uint8_t>(count);
        ++changed;
        return start + room; // past the text
    });
    return changed;
}

uint8_t bank_language(const std::vector<uint8_t>& bank) { return is_bank(bank) ? bank[6] : 0; }

namespace {

uint32_t be32(const std::vector<uint8_t>& b, size_t at) {
    return uint32_t{b[at]} << 24 | uint32_t{b[at + 1]} << 16 | uint32_t{b[at + 2]} << 8 | b[at + 3];
}

void put_be32(std::vector<uint8_t>& b, size_t at, uint32_t v) {
    for (int k = 0; k < 4; ++k) b[at + k] = static_cast<uint8_t>(v >> (24 - 8 * k));
}

size_t align16(size_t v) { return (v + 15) & ~size_t{15}; }

// A bank read through its index: the header's words, then (0x10) the
// offsets of three tables and of the records' area. Table 1: a count, then
// per record 16 bytes {its header, its English text, its key (offsets in
// the records' area), its number << 16 | a low word (mostly 0x12, also
// 0x22 ... 0xF2: kept as it is)}, by number. Tables 2 (the English texts'
// hashes: the upper half a hash, the lower the English text's length, the
// same in every language's bank) and 3 (the keys'; none for a record
// without a key): a count, then 8 bytes per
// entry {the hash, where the record's entry is in table 1}, by hash. Each
// table is padded with 0xFF to 16 bytes. The records' area: a word (where
// its records end, + 4), then the records, each its header (a hash of the
// text, its length), text, English text and key; then 0xFF past that
// word's end, to 16 bytes. Some records share a number; some have none
// (0xFFFF: found by their key).
struct Indexed {
    struct Record {
        uint32_t word = 0;             // number << 16 | its low word (mostly 0x12)
        std::vector<uint8_t> bytes;    // from its header to its key's end
        uint32_t english = 0, key = 0; // in `bytes`
        std::optional<uint32_t> hashes[2];
        bool keyed = false;
        uint32_t number() const { return word >> 16; }
    };
    std::vector<Record> records; // table 1's order
};

constexpr uint32_t kNoNumber = 0xFFFF;

std::optional<Indexed> read_index(const std::vector<uint8_t>& bank) {
    if (!is_bank(bank)) return std::nullopt;
    const size_t t1 = be32(bank, 0x10), tables[2] = {be32(bank, 0x14), be32(bank, 0x18)}, area = be32(bank, 0x1C);
    if (t1 + 4 > bank.size() || area >= bank.size()) return std::nullopt;
    const size_t n = be32(bank, t1);
    if (t1 + 4 + 16 * n > bank.size()) return std::nullopt;
    Indexed x;
    x.records.resize(n);
    for (const size_t table : tables) {
        if (table + 4 > bank.size()) return std::nullopt;
        const size_t entries = be32(bank, table);
        if (entries > n || table + 4 + 8 * entries > bank.size()) return std::nullopt;
        for (size_t j = 0; j < entries; ++j) {
            const size_t entry = be32(bank, table + 8 + 8 * j);
            if (entry < 4 || (entry - 4) % 16 != 0 || (entry - 4) / 16 >= n) return std::nullopt;
            std::optional<uint32_t>& hash = x.records[(entry - 4) / 16].hashes[table == tables[1]];
            if (hash) return std::nullopt;
            hash = be32(bank, table + 4 + 8 * j);
        }
    }
    for (size_t i = 0; i < n; ++i) {
        const size_t e = t1 + 4 + 16 * i;
        const size_t header = area + be32(bank, e), english = area + be32(bank, e + 4), key = area + be32(bank, e + 8);
        if (!(header + 4 <= english && english <= key && key < bank.size())) return std::nullopt;
        const std::string_view k = string_at(bank, key);
        const size_t end = key + key_space(k.size());
        if (end > bank.size()) return std::nullopt;
        Indexed::Record& r = x.records[i];
        r.word = be32(bank, e + 12);
        r.bytes.assign(bank.begin() + static_cast<ptrdiff_t>(header), bank.begin() + static_cast<ptrdiff_t>(end));
        r.english = static_cast<uint32_t>(english - header);
        r.key = static_cast<uint32_t>(key - header);
        r.keyed = !k.empty();
    }
    return x;
}

// The bank of these records, its first words (magic, language) `like`'s.
std::vector<uint8_t> write_index(const std::vector<uint8_t>& like, const Indexed& x) {
    const size_t n = x.records.size();
    // each table's entries: by hash (the texts' by the hash's upper half), then by record
    std::vector<std::pair<uint32_t, size_t>> entries[2];
    for (size_t i = 0; i < n; ++i) {
        for (int k = 0; k < 2; ++k) {
            if (x.records[i].hashes[k]) entries[k].push_back({*x.records[i].hashes[k], i});
        }
    }
    const auto by = [](uint32_t mask) {
        return [mask](const auto& a, const auto& b) { return (a.first & mask) < (b.first & mask); };
    };
    std::stable_sort(entries[0].begin(), entries[0].end(), by(0xFFFF0000));
    std::stable_sort(entries[1].begin(), entries[1].end(), by(0xFFFFFFFF));
    const size_t t1 = 0x30, t2 = align16(t1 + 4 + 16 * n), t3 = align16(t2 + 4 + 8 * entries[0].size()),
                 area = align16(t3 + 4 + 8 * entries[1].size());
    size_t used = 4;
    for (const Indexed::Record& r : x.records) used += r.bytes.size();
    std::vector<uint8_t> out(align16(area + used + 4 + 1), 0xFF); // past the area's end word, to 16
    std::copy(like.begin(), like.begin() + 8, out.begin());
    put_be32(out, 0x08, static_cast<uint32_t>(out.size()));
    put_be32(out, 0x0C, 0x30);
    put_be32(out, 0x10, static_cast<uint32_t>(t1));
    put_be32(out, 0x14, static_cast<uint32_t>(t2));
    put_be32(out, 0x18, static_cast<uint32_t>(t3));
    put_be32(out, 0x1C, static_cast<uint32_t>(area));
    put_be32(out, t1, static_cast<uint32_t>(n));
    put_be32(out, area, static_cast<uint32_t>(used + 4));
    size_t at = 4;
    for (size_t i = 0; i < n; ++i) {
        const Indexed::Record& r = x.records[i];
        const size_t e = t1 + 4 + 16 * i;
        put_be32(out, e, static_cast<uint32_t>(at));
        put_be32(out, e + 4, static_cast<uint32_t>(at + r.english));
        put_be32(out, e + 8, static_cast<uint32_t>(at + r.key));
        put_be32(out, e + 12, r.word);
        std::copy(r.bytes.begin(), r.bytes.end(), out.begin() + static_cast<ptrdiff_t>(area + at));
        at += r.bytes.size();
    }
    for (int k = 0; k < 2; ++k) {
        const size_t table = k == 0 ? t2 : t3;
        put_be32(out, table, static_cast<uint32_t>(entries[k].size()));
        for (size_t j = 0; j < entries[k].size(); ++j) {
            put_be32(out, table + 4 + 8 * j, entries[k][j].first);
            put_be32(out, table + 8 + 8 * j, static_cast<uint32_t>(4 + 16 * entries[k][j].second));
        }
    }
    return out;
}

} // namespace

namespace {

// The code points of UTF-8 text (a malformed byte: itself).
std::u32string decode(std::string_view utf8) {
    std::u32string out;
    for (size_t i = 0; i < utf8.size();) {
        const auto b = static_cast<unsigned char>(utf8[i]);
        const size_t length = b < 0xC0 ? 1 : b < 0xE0 ? 2 : b < 0xF0 ? 3 : 4;
        if (b >= 0x80 && (b < 0xC0 || i + length > utf8.size())) {
            out += b;
            ++i;
            continue;
        }
        char32_t c = length == 1 ? b : b & (0x3F >> (length - 1));
        for (size_t k = 1; k < length; ++k) c = c << 6 | (static_cast<unsigned char>(utf8[i + k]) & 0x3F);
        out += c;
        i += length;
    }
    return out;
}

bool is_code(char32_t c) { return c < 0x20 || (c >= 0xE000 && c <= 0xF8FF) || (c >= 0xFFF0 && c <= 0xFFFF); }

// How many code points after a control code (U+FFF0 on) are its arguments:
// the title's table of them (0x102F619C, by the code's low four bits, read
// by its text functions, sub_04D4866C ...) has two for U+FFF2 (a colour: two
// halves, U+FF20 or U+FFFF each), none for U+FFFF and one for the others.
size_t arguments(char32_t code) { return code == 0xFFF2 ? 2 : code == 0xFFFF ? 0 : 1; }

bool is_marked_symbol(char32_t c) {
    switch (c) {
    case kRightButton: case kBottomButton: case kTopButton: case kLeftButton: case kStartButton: case kSelectButton:
    case kPad: case U'☆': case U'【': case U'】': case U'↑': case U'↓': return true;
    default: return false;
    }
}

// T(1 << b) of the header hash's linear map.
constexpr uint16_t kHashColumns[16] = {0x3133, 0x6266, 0xC4CC, 0xA989, 0x7303, 0xE606, 0xCC0D, 0x981B,
                                       0x2110, 0x4220, 0x8440, 0x0881, 0x3112, 0x6224, 0xC448, 0x8891};

} // namespace

std::u32string markup(std::string_view text) {
    const std::u32string points = decode(rewrite(text));
    std::u32string out;
    for (size_t i = 0; i < points.size(); ++i) {
        const char32_t c = points[i];
        if (is_code(c)) {
            out += c;
            if (c >= 0xFFF0) {
                // its arguments (as many as the text still has: one cut short differs from a whole one)
                for (size_t n = arguments(c); n > 0 && i + 1 < points.size(); --n) out += points[++i];
            }
        } else if (is_marked_symbol(c)) {
            out += c;
        }
    }
    return out;
}

uint16_t text_hash(std::string_view text) {
    uint16_t h = 0;
    for (const char32_t c : decode(text)) {
        uint16_t t = 0;
        for (int b = 0; b < 16; ++b) {
            if (h >> b & 1) t ^= kHashColumns[b];
        }
        h = static_cast<uint16_t>(t ^ c);
    }
    return h;
}

namespace {

struct RussianText {
    std::string_view key;
    std::u8string_view text;
};

constexpr RussianText kRussian[] = {
#include "title/text_russian.inc"
};

} // namespace

std::span<const Translation> russian_texts() {
    static const std::vector<Translation> texts = [] {
        std::vector<Translation> out;
        for (const RussianText& t : kRussian) {
            out.push_back({t.key, {reinterpret_cast<const char*>(t.text.data()), t.text.size()}});
        }
        return out;
    }();
    return texts;
}

namespace {

// Latin and Cyrillic (А-я, Ёё) letters in capitals or small; other code points as they are.
char32_t to_upper(char32_t c) {
    if ((c >= U'a' && c <= U'z') || (c >= 0x0430 && c <= 0x044F)) return c - 0x20;
    return c == 0x0451 ? 0x0401 : c;
}

char32_t to_lower(char32_t c) {
    if ((c >= U'A' && c <= U'Z') || (c >= 0x0410 && c <= 0x042F)) return c + 0x20;
    return c == 0x0401 ? 0x0451 : c;
}

} // namespace

std::optional<std::string> with_references(
    std::string_view text, const std::function<std::optional<std::string_view>(std::string_view key)>& russian) {
    std::string out;
    size_t at = 0;
    for (size_t open; (open = text.find('{', at)) != std::string_view::npos;) {
        const size_t close = text.find('}', open);
        if (close == std::string_view::npos || text.substr(at, open - at).find('}') != std::string_view::npos) {
            return std::nullopt;
        }
        std::string_view key = text.substr(open + 1, close - open - 1), form;
        if (const size_t colon = key.find(':'); colon != std::string_view::npos) {
            form = key.substr(colon + 1);
            key = key.substr(0, colon);
        }
        if (!is_key(key) || !(form.empty() || form == "upper" || form == "capital")) return std::nullopt;
        const std::optional<std::string_view> record = russian(key);
        if (!record) return std::nullopt;
        std::string_view words = *record;
        words.remove_prefix(std::min(words.find_first_not_of(' '), words.size()));
        words.remove_suffix(words.size() - (words.find_last_not_of(' ') + 1));
        if (words.empty()) return std::nullopt;
        out += text.substr(at, open - at);
        if (form.empty()) {
            out += words;
        } else {
            bool first = true; // (the first letter, for "capital")
            for (const char32_t c : decode(words)) {
                const bool letter = to_upper(c) != c || to_lower(c) != c;
                append_utf8(out, form == "upper" || (letter && first) ? to_upper(c) : to_lower(c));
                first = first && !letter;
            }
        }
        at = close + 1;
    }
    if (text.find('}', at) != std::string_view::npos) return std::nullopt;
    out += text.substr(at);
    return out;
}

namespace {

// A record's text (after its header, up to its English text).
std::string_view text_of(const Indexed::Record& r) {
    const std::string_view room(reinterpret_cast<const char*>(r.bytes.data() + 4), r.english - 4);
    return room.substr(0, room.find('\0'));
}

std::string_view key_of(const Indexed::Record& r) {
    const std::string_view rest(reinterpret_cast<const char*>(r.bytes.data() + r.key), r.bytes.size() - r.key);
    return rest.substr(0, rest.find('\0'));
}

// The English record with `text` in its English one's place (its header
// that text's: hash and length; table 1's word its line count: up to 15,
// in bits 4-7); its English text, key and number stay, and so do its index
// hashes (of its English text and of its key).
Indexed::Record with_text(const Indexed::Record& english, std::string_view text) {
    Indexed::Record r = english;
    const uint32_t lines = std::min<uint32_t>(static_cast<uint32_t>(std::count(text.begin(), text.end(), '\n')) + 1, 15);
    r.word = (r.word & ~uint32_t{0xF0}) | lines << 4;
    const uint16_t hash = text_hash(text);
    const size_t count = characters(text);
    r.bytes = {static_cast<uint8_t>(hash), static_cast<uint8_t>(hash >> 8), static_cast<uint8_t>(count >> 8),
               static_cast<uint8_t>(count)};
    r.bytes.insert(r.bytes.end(), text.begin(), text.end());
    r.bytes.resize(4 + text_space(text.size()), 0);
    r.english = static_cast<uint32_t>(r.bytes.size());
    r.bytes.insert(r.bytes.end(), english.bytes.begin() + english.english, english.bytes.end());
    r.key = r.english + (english.key - english.english);
    return r;
}

// A part's English and Russian banks, read.
struct Part {
    size_t russian_at;
    Indexed english, russian;
};

// The Russian text of each English text: of the records Russian has the
// number of, the text most of them have (the first of those first found).
class Matches {
public:
    void add(const Part& part) {
        std::map<uint32_t, const Indexed::Record*> russian;
        for (const Indexed::Record& r : part.russian.records) {
            if (r.keyed && r.number() != kNoNumber) russian.emplace(r.number(), &r);
        }
        for (const Indexed::Record& r : part.english.records) {
            const auto found = russian.find(r.number());
            if (!r.keyed || found == russian.end() || text_of(r).empty()) continue;
            std::vector<Counted>& candidates = by_english_[text_of(r)];
            const std::string_view text = text_of(*found->second);
            const auto same = std::find_if(candidates.begin(), candidates.end(),
                                           [&](const Counted& c) { return c.text == text; });
            if (same != candidates.end()) ++same->count;
            else candidates.push_back({text, 1});
        }
    }

    std::optional<std::string_view> of(std::string_view english) const {
        const auto found = by_english_.find(english);
        if (found == by_english_.end()) return std::nullopt;
        const Counted* best = &found->second.front();
        for (const Counted& c : found->second) best = c.count > best->count ? &c : best;
        return best->text;
    }

private:
    struct Counted {
        std::string_view text;
        size_t count;
    };
    std::map<std::string_view, std::vector<Counted>> by_english_;
};

} // namespace

Filled fill_missing_texts(std::vector<std::vector<uint8_t>*> banks, std::span<const Translation> russian) {
    constexpr size_t kLanguages = kBankRussian;
    std::vector<Part> parts;
    for (size_t i = kLanguages - 1; i < banks.size(); ++i) {
        // a part's banks, Japanese to Russian
        bool part = true;
        for (size_t l = 0; l < kLanguages && part; ++l) part = bank_language(*banks[i + 1 - kLanguages + l]) == l + 1;
        if (!part) continue;
        auto russian_bank = read_index(*banks[i]);
        auto english = read_index(*banks[i + kBankEnglish - kLanguages]);
        if (russian_bank && english) parts.push_back({i, std::move(*english), std::move(*russian_bank)});
    }
    std::map<std::string_view, std::string_view> ours;
    for (const Translation& t : russian) ours.emplace(t.key, t.text);
    Matches matches;
    for (const Part& part : parts) matches.add(part);
    // the player's Russian texts by key, as the banks were (for our texts' references)
    std::map<std::string_view, std::string_view> game;
    for (const Part& part : parts) {
        for (const Indexed::Record& r : part.russian.records) {
            if (r.keyed) game.emplace(key_of(r), text_of(r));
        }
    }
    const auto game_text = [&](std::string_view key) -> std::optional<std::string_view> {
        const auto found = game.find(key);
        return found == game.end() ? std::nullopt : std::optional(found->second);
    };
    Filled filled;
    for (const Part& part : parts) {
        // Russian's records, and English's of the numbers Russian has none of, in Russian where their markup
        // allows
        std::set<uint32_t> numbers;
        for (const Indexed::Record& r : part.russian.records) numbers.insert(r.number());
        Indexed merged = part.russian;
        for (const Indexed::Record& english : part.english.records) {
            if (!english.keyed || english.number() == kNoNumber || numbers.count(english.number())) continue;
            const std::u32string marks = markup(text_of(english));
            std::optional<std::string> text;
            if (const auto our = ours.find(key_of(english)); our != ours.end()) {
                std::optional<std::string> expanded = with_references(our->second, game_text);
                if (!expanded) filled.unresolved.emplace_back(our->first);
                else if (markup(*expanded) == marks) text = std::move(expanded);
                else filled.kept_english.emplace_back(our->first);
            } else if (const auto match = matches.of(text_of(english)); match && markup(*match) == marks) {
                text = std::string(*match);
            }
            merged.records.push_back(text ? with_text(english, *text) : english);
        }
        if (merged.records.size() == part.russian.records.size()) continue;
        std::stable_sort(merged.records.begin(), merged.records.end(),
                         [](const Indexed::Record& a, const Indexed::Record& b) { return a.number() < b.number(); });
        *banks[part.russian_at] = write_index(*banks[part.russian_at], merged);
        filled.banks.push_back(part.russian_at);
    }
    return filled;
}

namespace {

struct PolishText {
    std::string_view key;
    std::u8string_view text;
};

constexpr PolishText kPolish[] = {
#include "title/text_polish.inc"
    {}, // (the end: the table may be empty)
};

// A text's markup without its line breaks (a translation may break its lines elsewhere).
std::u32string markup_unbroken(std::string_view text) {
    std::u32string marks = markup(text);
    std::erase(marks, U'\n');
    return marks;
}

} // namespace

std::span<const Translation> polish_texts() {
    static const std::vector<Translation> texts = [] {
        std::vector<Translation> out;
        for (const PolishText& t : kPolish) {
            if (!t.key.empty()) out.push_back({t.key, {reinterpret_cast<const char*>(t.text.data()), t.text.size()}});
        }
        return out;
    }();
    return texts;
}

Filled put_polish(std::vector<std::vector<uint8_t>*> banks, std::span<const Translation> polish) {
    constexpr size_t kLanguages = kBankRussian;
    struct EnglishPart {
        size_t at;
        Indexed english;
    };
    std::vector<EnglishPart> parts;
    for (size_t i = kLanguages - 1; i < banks.size(); ++i) {
        // a part's banks, Japanese to Russian
        bool part = true;
        for (size_t l = 0; l < kLanguages && part; ++l) part = bank_language(*banks[i + 1 - kLanguages + l]) == l + 1;
        if (!part) continue;
        const size_t at = i + kBankEnglish - kLanguages;
        if (auto english = read_index(*banks[at])) parts.push_back({at, std::move(*english)});
    }
    std::map<std::string_view, std::string_view> ours;
    for (const Translation& t : polish) ours.emplace(t.key, t.text);
    // ours by English text: a record without a text of its own takes that of another key with its English text
    // (the first in the banks' order; copied: the records change below). One whose text is empty (a pin) stays
    // English and gives none.
    std::map<std::string, std::string_view, std::less<>> by_english;
    for (const EnglishPart& part : parts) {
        for (const Indexed::Record& r : part.english.records) {
            if (!r.keyed || text_of(r).empty()) continue;
            const auto our = ours.find(key_of(r));
            if (our != ours.end() && !our->second.empty()) by_english.emplace(std::string(text_of(r)), our->second);
        }
    }
    Filled filled;
    for (EnglishPart& part : parts) {
        bool changed = false;
        for (Indexed::Record& r : part.english.records) {
            if (!r.keyed || text_of(r).empty()) continue;
            const auto our = ours.find(key_of(r));
            if (our != ours.end() && our->second.empty()) continue; // pinned: stays English
            const auto same = our == ours.end() ? by_english.find(text_of(r)) : by_english.end();
            if (our == ours.end() && same == by_english.end()) continue;
            const std::string_view text = our != ours.end() ? our->second : same->second;
            if (markup_unbroken(text) != markup_unbroken(text_of(r))) {
                if (our != ours.end()) filled.kept_english.emplace_back(our->first);
                continue;
            }
            r = with_text(r, text);
            changed = true;
        }
        if (!changed) continue;
        *banks[part.at] = write_index(*banks[part.at], part.english);
        filled.banks.push_back(part.at);
    }
    return filled;
}

std::optional<std::vector<uint8_t>> with_texts(
    const std::vector<uint8_t>& bank,
    const std::function<std::optional<std::string>(size_t record, std::string_view text)>& change) {
    auto indexed = read_index(bank);
    if (!indexed) return std::nullopt;
    bool changed = false;
    for (size_t i = 0; i < indexed->records.size(); ++i) {
        Indexed::Record& r = indexed->records[i];
        std::optional<std::string> text = change(i, text_of(r));
        if (!text || *text == text_of(r)) continue;
        r = with_text(r, *text);
        changed = true;
    }
    return changed ? write_index(bank, *indexed) : bank;
}

void code_points(const std::vector<uint8_t>& bank, std::set<char32_t>& used) {
    each_text(bank, [&](size_t, size_t, std::string_view text) -> size_t {
        for (size_t i = 0; i < text.size();) {
            const auto b = static_cast<unsigned char>(text[i]);
            const size_t length = b < 0x80 ? 1 : b >= 0xF0 ? 4 : b >= 0xE0 ? 3 : 2;
            char32_t c = length == 1 ? b : b & (0x3F >> (length - 1));
            for (size_t k = 1; k < length && i + k < text.size(); ++k) c = c << 6 | (static_cast<unsigned char>(text[i + k]) & 0x3F);
            used.insert(c);
            i += length;
        }
        return 0;
    });
}

} // namespace cafe::title::text
