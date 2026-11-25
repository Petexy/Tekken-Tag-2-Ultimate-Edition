#include "title/text.h"

#include <algorithm>
#include <cstring>
#include <map>
#include <optional>
#include <set>
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
    } else {
        out += static_cast<char>(0xE0 | (c >> 12));
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

// A key: letters, '_', digits ("common_4", "Manu_627"), after the previous
// record's padding.
bool key_at(const std::vector<uint8_t>& bank, size_t at, std::string_view& key) {
    if (at == 0 || bank[at - 1] != 0) return false;
    key = string_at(bank, at);
    const size_t underscore = key.find('_');
    if (underscore == 0 || underscore == std::string_view::npos || underscore + 1 >= key.size()) return false;
    const auto letters = key.substr(0, underscore), digits = key.substr(underscore + 1);
    return std::all_of(letters.begin(), letters.end(), [](char c) { return std::isalpha(static_cast<unsigned char>(c)); }) &&
           std::all_of(digits.begin(), digits.end(), [](char c) { return std::isdigit(static_cast<unsigned char>(c)); });
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
// the records' area), its number << 16 | 0x12}, by number. Tables 2 (the
// texts' hashes: the upper half a hash, the lower the text's length) and 3
// (the keys'; none for a record without a key): a count, then 8 bytes per
// entry {the hash, where the record's entry is in table 1}, by hash. Each
// table is padded with 0xFF to 16 bytes. The records' area: a word (where
// its records end, + 4), then the records, each its header (a hash of the
// text, its length), text, English text and key; then 0xFF past that
// word's end, to 16 bytes. Some records share a number; some have none
// (0xFFFF: found by their key).
struct Indexed {
    struct Record {
        uint32_t word = 0;             // number << 16 | 0x12
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

// A record's text (after its header, up to its English text).
std::string_view text_of(const Indexed::Record& r) {
    const std::string_view room(reinterpret_cast<const char*>(r.bytes.data() + 4), r.english - 4);
    return room.substr(0, room.find('\0'));
}

// A part's English and Russian banks, read.
struct Part {
    size_t russian_at;
    Indexed english, russian;
};

// The Russian record of each English text: of the records Russian has the
// number of, the text most of them have (the first of those first found).
class Translations {
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
            const auto same = std::find_if(candidates.begin(), candidates.end(), [&](const Counted& c) {
                return text_of(*c.record) == text_of(*found->second);
            });
            if (same != candidates.end()) ++same->count;
            else candidates.push_back({found->second, 1});
        }
    }

    const Indexed::Record* of(const Indexed::Record& english) const {
        const auto found = by_english_.find(text_of(english));
        if (found == by_english_.end()) return nullptr;
        const Counted* best = &found->second.front();
        for (const Counted& c : found->second) best = c.count > best->count ? &c : best;
        return best->record;
    }

private:
    struct Counted {
        const Indexed::Record* record;
        size_t count;
    };
    std::map<std::string_view, std::vector<Counted>> by_english_;
};

} // namespace

std::vector<size_t> fill_missing_texts(std::vector<std::vector<uint8_t>*> banks) {
    constexpr size_t kLanguages = kBankRussian;
    std::vector<Part> parts;
    for (size_t i = kLanguages - 1; i < banks.size(); ++i) {
        // a part's banks, Japanese to Russian
        bool part = true;
        for (size_t l = 0; l < kLanguages && part; ++l) part = bank_language(*banks[i + 1 - kLanguages + l]) == l + 1;
        if (!part) continue;
        auto russian = read_index(*banks[i]);
        auto english = read_index(*banks[i + kBankEnglish - kLanguages]);
        if (russian && english) parts.push_back({i, std::move(*english), std::move(*russian)});
    }
    Translations translations;
    for (const Part& part : parts) translations.add(part);
    std::vector<size_t> filled;
    for (const Part& part : parts) {
        // Russian's records, and English's of the numbers Russian has none of: in Russian where Russian has
        // the same English text elsewhere (the Wii U's own screens repeat SELECT, CONFIRM, ON, OFF ...)
        std::set<uint32_t> numbers;
        for (const Indexed::Record& r : part.russian.records) numbers.insert(r.number());
        Indexed merged = part.russian;
        for (const Indexed::Record& english : part.english.records) {
            if (!english.keyed || english.number() == kNoNumber || numbers.count(english.number())) continue;
            Indexed::Record r = english;
            if (const Indexed::Record* russian = translations.of(english)) {
                // the Russian header and text, the English original and key
                r.bytes.assign(russian->bytes.begin(), russian->bytes.begin() + russian->english);
                r.bytes.insert(r.bytes.end(), english.bytes.begin() + english.english, english.bytes.end());
                r.english = russian->english;
                r.key = russian->english + (english.key - english.english);
                r.hashes[0] = russian->hashes[0];
            }
            merged.records.push_back(std::move(r));
        }
        if (merged.records.size() == part.russian.records.size()) continue;
        std::stable_sort(merged.records.begin(), merged.records.end(),
                         [](const Indexed::Record& a, const Indexed::Record& b) { return a.number() < b.number(); });
        *banks[part.russian_at] = write_index(*banks[part.russian_at], merged);
        filled.push_back(part.russian_at);
    }
    return filled;
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
