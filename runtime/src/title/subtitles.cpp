#include "title/subtitles.h"

#include "title/text.h"

#include <map>
#include <string>

namespace cafe::title::subtitles {
namespace {

constexpr size_t kEnglishEntry = 1;

struct PolishLine {
    std::string_view key;
    std::u8string_view text;
};

constexpr PolishLine kPolish[] = {
#include "title/subtitles_polish.inc"
    {}, // (the end: the table may be empty)
};

constexpr PolishLine kStory[] = {
#include "title/subtitles_story_polish.inc"
    {}, // (the end: the table may be empty)
};

std::vector<Line> lines_of(std::span<const PolishLine> table) {
    std::vector<Line> out;
    for (const PolishLine& l : table) {
        if (!l.key.empty()) out.push_back({l.key, {reinterpret_cast<const char*>(l.text.data()), l.text.size()}});
    }
    return out;
}

// A line's timing around its words (UTF-8): U+FFFB show U+FFFC hide U+FFF5 U+0001 before, U+FFFB U+0001 U+FFFC
// U+FFFF after.
constexpr std::string_view kShow = "\xEF\xBF\xBB", kStart = "\xEF\xBF\xB5\x01",
                           kEnd = "\xEF\xBF\xBB\x01\xEF\xBF\xBC\xEF\xBF\xBF";

// The text with `words` in its words' place; nothing when it is not a timed line.
std::optional<std::string> with_words(std::string_view text, std::string_view words) {
    const size_t start = text.find(kStart);
    if (!text.starts_with(kShow) || start == std::string_view::npos || !text.ends_with(kEnd) ||
        start + kStart.size() > text.size() - kEnd.size()) {
        return std::nullopt;
    }
    return std::string(text.substr(0, start + kStart.size())) + std::string(words) + std::string(kEnd);
}

uint32_t be32(const std::vector<uint8_t>& b, size_t at) {
    return uint32_t{b[at]} << 24 | uint32_t{b[at + 1]} << 16 | uint32_t{b[at + 2]} << 8 | b[at + 3];
}

void put_be32(std::vector<uint8_t>& b, size_t at, uint32_t v) {
    for (int i = 0; i < 4; ++i) b[at + i] = static_cast<uint8_t>(v >> (24 - 8 * i));
}

void pad16(std::vector<uint8_t>& b) { b.resize((b.size() + 15) & ~size_t{15}, 0); }

// {offset, size} of each of a table's entries (a u32 count, then the pairs), each within `limit`; nothing if one
// is not.
std::optional<std::vector<std::pair<size_t, size_t>>> table_of(const std::vector<uint8_t>& b, size_t limit) {
    if (b.size() < 4) return std::nullopt;
    const size_t count = be32(b, 0);
    if (4 + 8 * count > b.size()) return std::nullopt;
    std::vector<std::pair<size_t, size_t>> out;
    for (size_t i = 0; i < count; ++i) {
        const size_t offset = be32(b, 4 + 8 * i), size = be32(b, 8 + 8 * i);
        if (offset > limit || size > limit - offset) return std::nullopt;
        out.push_back({offset, size});
    }
    return out;
}

// The first text of a bank, or nothing.
std::optional<std::string> first_text(const std::vector<uint8_t>& bank) {
    std::optional<std::string> first;
    text::with_texts(bank, [&](size_t record, std::string_view text) -> std::optional<std::string> {
        if (record == 0) first = std::string(text);
        return std::nullopt;
    });
    return first;
}

// A line's container with Polish in its English entry, or nothing to keep it.
std::optional<std::vector<uint8_t>> container_in_polish(const std::vector<uint8_t>& container, size_t entry,
                                                        const std::map<std::string, std::string_view>& ours,
                                                        bool& added) {
    const auto banks = table_of(container, container.size());
    if (!banks || banks->size() <= kPolishEntry) return std::nullopt;
    const auto bank = [&](size_t k) {
        const auto [offset, size] = (*banks)[k];
        return std::vector<uint8_t>(container.begin() + static_cast<ptrdiff_t>(offset),
                                    container.begin() + static_cast<ptrdiff_t>(offset + size));
    };
    std::vector<uint8_t> out = container;
    // an added fighter's own Polish
    // (the importer's: its language byte the entry's + 1 and a timed text; the title's own entry 10 holds " ",
    // and an added fighter's entries without a text of their own are its English bank)
    const std::vector<uint8_t> own = bank(kPolishEntry);
    const std::optional<std::string> polish = first_text(own);
    if (text::bank_language(own) == kPolishEntry + 1 && (*banks)[kPolishEntry] != (*banks)[kEnglishEntry] && polish &&
        with_words(*polish, "")) {
        put_be32(out, 4 + 8 * kEnglishEntry, static_cast<uint32_t>((*banks)[kPolishEntry].first));
        put_be32(out, 8 + 8 * kEnglishEntry, static_cast<uint32_t>((*banks)[kPolishEntry].second));
        added = true;
        return out;
    }
    // ours, with the English line's timing
    const auto changed = text::with_texts(bank(kEnglishEntry), [&](size_t record, std::string_view text) {
        const std::string key = std::to_string(entry) + (record == 0 ? "" : "." + std::to_string(record));
        const auto our = ours.find(key);
        return our == ours.end() ? std::nullopt : with_words(text, our->second);
    });
    if (!changed || *changed == bank(kEnglishEntry)) return std::nullopt;
    pad16(out);
    put_be32(out, 4 + 8 * kEnglishEntry, static_cast<uint32_t>(out.size()));
    put_be32(out, 8 + 8 * kEnglishEntry, static_cast<uint32_t>(changed->size()));
    out.insert(out.end(), changed->begin(), changed->end());
    return out;
}

} // namespace

std::span<const Line> polish_lines() {
    static const std::vector<Line> lines = lines_of(kPolish);
    return lines;
}

std::span<const Line> story_lines() {
    static const std::vector<Line> lines = lines_of(kStory);
    return lines;
}

std::optional<Polish> in_polish(const std::vector<uint8_t>& file, std::span<const Line> ours) {
    const auto entries = table_of(file, file.size());
    if (!entries) return std::nullopt;
    std::map<std::string, std::string_view> by_key;
    for (const Line& l : ours) by_key.emplace(std::string(l.key), l.text);
    Polish polish;
    std::vector<uint8_t>& out = polish.file;
    out.assign(4 + 8 * entries->size(), 0);
    put_be32(out, 0, static_cast<uint32_t>(entries->size()));
    pad16(out);
    for (size_t i = 0; i < entries->size(); ++i) {
        const auto [offset, size] = (*entries)[i];
        std::vector<uint8_t> entry(file.begin() + static_cast<ptrdiff_t>(offset),
                                   file.begin() + static_cast<ptrdiff_t>(offset + size));
        bool added = false;
        if (auto changed = container_in_polish(entry, i, by_key, added)) {
            entry = std::move(*changed);
            ++(added ? polish.added : polish.ours);
        }
        put_be32(out, 4 + 8 * i, static_cast<uint32_t>(out.size()));
        put_be32(out, 8 + 8 * i, static_cast<uint32_t>(entry.size()));
        out.insert(out.end(), entry.begin(), entry.end());
        pad16(out);
    }
    return polish;
}

} // namespace cafe::title::subtitles
