#include "title/menudata.h"

#include <cstring>
#include <string>
#include <string_view>
#include <utility>

namespace cafe::title::menudata {
namespace {

struct Element {
    uint32_t tag = 0;
    std::vector<uint8_t> text;
    std::vector<std::pair<uint32_t, std::vector<uint8_t>>> attributes; // the name's number, the text
    std::vector<Element> children;
};

constexpr size_t kHeader = 16, kRoots = 16;
constexpr uint32_t kMaxDepth = 64;

uint32_t be32(const uint8_t* p) { return uint32_t{p[0]} << 24 | uint32_t{p[1]} << 16 | uint32_t{p[2]} << 8 | p[3]; }
void put_be32(uint8_t* p, uint32_t x) {
    for (int i = 0; i < 4; ++i) p[i] = static_cast<uint8_t>(x >> (24 - 8 * i));
}
void append_be32(std::vector<uint8_t>& out, uint32_t x) {
    out.resize(out.size() + 4);
    put_be32(&out[out.size() - 4], x);
}

struct Reader {
    const std::vector<uint8_t>& d;
    size_t at;
    bool ok = true;

    uint32_t u32() {
        if (at + 4 > d.size()) {
            ok = false;
            return 0;
        }
        at += 4;
        return be32(&d[at - 4]);
    }
    std::vector<uint8_t> text() {
        const uint32_t n = u32();
        if (!ok || n > d.size() - at) {
            ok = false;
            return {};
        }
        std::vector<uint8_t> t(d.begin() + static_cast<ptrdiff_t>(at), d.begin() + static_cast<ptrdiff_t>(at + n));
        at += (n + 3) & ~size_t{3};
        return t;
    }
    bool element(Element& e, uint32_t depth) {
        if (depth > kMaxDepth) return false;
        e.tag = u32();
        e.text = text();
        const uint32_t attributes = u32();
        for (uint32_t i = 0; ok && i < attributes; ++i) {
            const uint32_t id = u32();
            e.attributes.emplace_back(id, text());
        }
        const uint32_t children = u32();
        for (uint32_t i = 0; ok && i < children; ++i) {
            e.children.emplace_back();
            if (!element(e.children.back(), depth + 1)) return false;
        }
        return ok;
    }
};

void write_text(std::vector<uint8_t>& out, const std::vector<uint8_t>& t) {
    append_be32(out, static_cast<uint32_t>(t.size()));
    out.insert(out.end(), t.begin(), t.end());
    out.resize(out.size() + (-t.size() & 3));
}

void write(std::vector<uint8_t>& out, const Element& e) {
    append_be32(out, e.tag);
    write_text(out, e.text);
    append_be32(out, static_cast<uint32_t>(e.attributes.size()));
    for (const auto& [id, value] : e.attributes) {
        append_be32(out, id);
        write_text(out, value);
    }
    append_be32(out, static_cast<uint32_t>(e.children.size()));
    for (const Element& child : e.children) write(out, child);
}

// A name table's number for `name` (a count, then {offset, length with the
// zero, number} each, then the names).
std::optional<uint32_t> number_of(const std::vector<uint8_t>& d, uint32_t table, std::string_view name) {
    if (table > d.size() || d.size() - table < 4) return std::nullopt;
    const uint32_t count = be32(&d[table]);
    if (count > (d.size() - table - 4) / 12) return std::nullopt;
    const size_t names = table + 4 + size_t{12} * count;
    for (uint32_t i = 0; i < count; ++i) {
        const uint8_t* entry = &d[table + 4 + size_t{12} * i];
        const uint32_t offset = be32(entry), length = be32(entry + 4);
        if (length != name.size() + 1 || offset > d.size() - names || length > d.size() - names - offset) continue;
        if (std::memcmp(&d[names + offset], name.data(), name.size()) == 0) return be32(entry + 8);
    }
    return std::nullopt;
}

struct Names {
    uint32_t menu_item, static_text, on_load; // tags
    uint32_t name, text, text_id;             // attributes
};

std::string_view as_text(const std::vector<uint8_t>& value) {
    std::string_view v(reinterpret_cast<const char*>(value.data()), value.size());
    return v.substr(0, v.find('\0'));
}

std::string_view name_of(const Element& e, const Names& n) {
    for (const auto& [id, value] : e.attributes) {
        if (id == n.name) return as_text(value);
    }
    return {};
}

Element* find(Element& e, std::string_view name, const Names& n) {
    if (name_of(e, n) == name) return &e;
    for (Element& child : e.children) {
        if (Element* found = find(child, name, n)) return found;
    }
    return nullptr;
}

// The place of the child named `name`, or -1.
ptrdiff_t place_of(const Element& parent, std::string_view name, const Names& n) {
    for (size_t i = 0; i < parent.children.size(); ++i) {
        if (name_of(parent.children[i], n) == name) return static_cast<ptrdiff_t>(i);
    }
    return -1;
}

void set_attribute(Element& e, uint32_t id, std::string_view value) {
    std::vector<uint8_t> text(value.begin(), value.end());
    text.push_back(0);
    for (auto& [a, v] : e.attributes) {
        if (a == id) {
            v = std::move(text);
            return;
        }
    }
    e.attributes.emplace_back(id, std::move(text));
}

void remove_attribute(Element& e, uint32_t id) {
    std::erase_if(e.attributes, [&](const auto& a) { return a.first == id; });
}

// The Offline menu's OnLoad script fills two arrays with the rows' icons
// (small and large), one append a row in the rows' order: `02 02 00 VV`
// (load the value VV) and `43 01 02` (append it). The row at `place` gets
// the icons of the row before it (an append more in each array after that
// row's), the code its new size, and so does the word after it that holds
// the code's size less one (at +66 in the script's tables, after the code).
constexpr size_t kAppend = 7, kRows = 8, kCodeSize = 8, kCode = 12, kLastByte = 66;

bool is_append(const std::vector<uint8_t>& s, size_t at) {
    return at + kAppend <= s.size() && s[at] == 0x02 && s[at + 1] == 0x02 && s[at + 2] == 0x00 && s[at + 4] == 0x43 &&
           s[at + 5] == 0x01 && s[at + 6] == 0x02;
}

bool grow_icon_arrays(std::vector<uint8_t>& script, size_t place) {
    if (script.size() < kCode || std::memcmp(script.data(), "xtal", 4) != 0) return false;
    const uint32_t size = be32(&script[kCodeSize]);
    if (size == 0 || size > script.size() - kCode || script.size() - kCode - size < kLastByte + 4) return false;
    const size_t end = kCode + size, last = end + kLastByte;
    if (be32(&script[last]) != size - 1) return false;
    std::vector<size_t> runs; // the arrays' first appends
    for (size_t at = kCode; at + kAppend <= end;) {
        size_t n = 0;
        while (at + (n + 1) * kAppend <= end && is_append(script, at + n * kAppend)) ++n;
        if (n == 0) {
            ++at;
            continue;
        }
        if (n != kRows) return false;
        runs.push_back(at);
        at += n * kAppend;
    }
    if (runs.size() != 2 || place == 0 || place > kRows) return false;
    for (size_t r = runs.size(); r-- > 0;) { // the later array first: the earlier one's places stay
        const size_t row = runs[r] + (place - 1) * kAppend;
        const std::vector<uint8_t> append(script.begin() + static_cast<ptrdiff_t>(row),
                                          script.begin() + static_cast<ptrdiff_t>(row + kAppend));
        script.insert(script.begin() + static_cast<ptrdiff_t>(row + kAppend), append.begin(), append.end());
    }
    const uint32_t grown = size + 2 * kAppend;
    put_be32(&script[kCodeSize], grown);
    put_be32(&script[last + 2 * kAppend], grown - 1);
    return true;
}

// The frame's statics StaticMode002-01..08 (descriptions) or
// StaticValueMode002-01..08 (values) get one more at `place`: a copy of the
// one before it, the later ones renamed a number on.
bool add_static(Element& frame, std::string_view prefix, size_t place, const char* text, const Names& n) {
    const auto name = [&](size_t i) { return std::string(prefix) + std::to_string(i); };
    std::vector<size_t> places;
    for (size_t i = 1; i <= kRows; ++i) {
        const ptrdiff_t p = place_of(frame, name(i), n);
        if (p < 0 || frame.children[p].tag != n.static_text || (!places.empty() && static_cast<size_t>(p) <= places.back())) {
            return false;
        }
        places.push_back(static_cast<size_t>(p));
    }
    Element added = frame.children[places[place - 1]];
    if (text) {
        set_attribute(added, n.text, text);
        remove_attribute(added, n.text_id);
    }
    set_attribute(added, n.name, name(place + 1));
    for (size_t i = place; i < kRows; ++i) set_attribute(frame.children[places[i]], n.name, name(i + 2));
    frame.children.insert(frame.children.begin() + static_cast<ptrdiff_t>(places[place - 1] + 1), std::move(added));
    return true;
}

constexpr const char* kFrame = "FrameMode002-01";
constexpr const char* kGhostRow = "MenuItemMode002-02";
constexpr const char* kLabel = "SOLO GHOST BATTLE";
constexpr const char* kDescription = "Battle against a series of ghost characters one-on-one. ";

} // namespace

std::optional<std::vector<uint8_t>> add_solo_ghost_row(const std::vector<uint8_t>& file) {
    if (file.size() < kHeader + 4 || std::memcmp(file.data(), "BX01", 4) != 0) return std::nullopt;
    const uint32_t tags = be32(&file[8]), attributes = be32(&file[12]);
    if (tags > file.size() || attributes < tags || attributes > file.size()) return std::nullopt;
    const auto number = [&](uint32_t table, std::string_view name) { return number_of(file, table, name); };
    const auto menu_item = number(tags, "menuitemtext"), static_text = number(tags, "statictext"),
               on_load = number(tags, "OnLoad"), name = number(attributes, "name"), text = number(attributes, "text"),
               text_id = number(attributes, "textid");
    if (!menu_item || !static_text || !on_load || !name || !text || !text_id) return std::nullopt;
    const Names n{*menu_item, *static_text, *on_load, *name, *text, *text_id};

    Reader reader{file, kRoots};
    const uint32_t count = reader.u32();
    std::vector<Element> roots(reader.ok && count <= file.size() / 16 ? count : 0);
    for (Element& root : roots) {
        if (!reader.element(root, 0)) return std::nullopt;
    }
    if (roots.empty() || reader.at != tags) return std::nullopt;

    Element* frame = nullptr;
    for (Element& root : roots) {
        if (!frame) frame = find(root, kFrame, n);
    }
    Element* menu = frame ? find(*frame, kOfflineMenu, n) : nullptr;
    if (!menu || find(*frame, kSoloGhostRow, n)) return std::nullopt;
    const ptrdiff_t ghost = place_of(*menu, kGhostRow, n);
    if (ghost < 0 || menu->children[ghost].tag != n.menu_item) return std::nullopt;
    size_t rows = 0, rows_before = 0, scripts = 0;
    for (size_t i = 0; i < menu->children.size(); ++i) {
        rows += menu->children[i].tag == n.menu_item;
        rows_before += menu->children[i].tag == n.menu_item && static_cast<ptrdiff_t>(i) < ghost;
        scripts += menu->children[i].tag == n.on_load;
    }
    if (rows != kRows || rows_before + 1 != kSoloGhostPlace || scripts != 1) return std::nullopt;

    for (Element& child : menu->children) {
        if (child.tag == n.on_load && !grow_icon_arrays(child.text, kSoloGhostPlace)) return std::nullopt;
    }
    Element row = menu->children[ghost];
    set_attribute(row, n.name, kSoloGhostRow);
    set_attribute(row, n.text, kLabel);
    remove_attribute(row, n.text_id);
    menu->children.insert(menu->children.begin() + ghost + 1, std::move(row));
    // (the menu may be one of the frame's children, which move as these are added)
    menu = nullptr;
    if (!add_static(*frame, "StaticMode002-0", kSoloGhostPlace, kDescription, n) ||
        !add_static(*frame, "StaticValueMode002-0", kSoloGhostPlace, nullptr, n)) {
        return std::nullopt;
    }

    std::vector<uint8_t> out(file.begin(), file.begin() + kHeader);
    append_be32(out, count);
    for (const Element& root : roots) write(out, root);
    const uint32_t moved = static_cast<uint32_t>(out.size());
    out.insert(out.end(), file.begin() + tags, file.end());
    put_be32(&out[8], moved);
    put_be32(&out[12], moved + (attributes - tags));
    return out;
}

} // namespace cafe::title::menudata
