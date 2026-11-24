#include "golden.h"

#include "json.h"

#include <algorithm>
#include <cstdio>

namespace launcher::model {

const char* const kSections[7] = {"header", "notice", "game", "characters", "settings", "task", "dialog"};

const char* icon_name(Icon icon) {
    switch (icon) {
    case Icon::kInfo: return "dialog-information-symbolic";
    case Icon::kWarning: return "dialog-warning-symbolic";
    case Icon::kError: return "dialog-error-symbolic";
    case Icon::kOk: return "object-select-symbolic";
    case Icon::kUpdate: return "ttt2-update-symbolic";
    case Icon::kDocument: return "document-open-symbolic";
    case Icon::kPlay: return "media-playback-start-symbolic";
    case Icon::kSettings: return "ttt2-settings-symbolic";
    case Icon::kFolder: return "folder-symbolic";
    case Icon::kBack: return "ttt2-back-symbolic";
    case Icon::kRefresh: return "view-refresh-symbolic";
    case Icon::kCopy: return "edit-copy-symbolic";
    case Icon::kMore: return "view-more-symbolic";
    case Icon::kLog: return "text-x-generic-symbolic";
    case Icon::kNone: return "";
    }
    return "";
}

namespace {

const char* tone_name(Tone tone) {
    switch (tone) {
    case Tone::kDim: return "dim";
    case Tone::kError: return "error";
    case Tone::kWarning: return "warning";
    case Tone::kPath: return "path";
    case Tone::kHeading: return "heading";
    case Tone::kOk: return "ok";
    case Tone::kNormal: return "";
    }
    return "";
}

const char* icon_tone(Tone tone) {
    switch (tone) {
    case Tone::kWarning: return "warn";
    case Tone::kOk: return "ok";
    case Tone::kError: return "bad";
    case Tone::kDim: return "dim";
    default: return "";
    }
}

const char* pill_name(PillKind kind) {
    switch (kind) {
    case PillKind::kOk: return "ok";
    case PillKind::kWarn: return "warn";
    case PillKind::kBad: return "bad";
    case PillKind::kNeutral: return "neutral";
    }
    return "neutral";
}

struct Out {
    Section& s;
    bool path_tips = true;
    std::vector<Action>* all = nullptr; // every action seen (actions_of)
    void add(std::string kind, std::map<std::string, std::string> text, std::map<std::string, bool> flags = {}) {
        for (auto it = text.begin(); it != text.end();) it = it->second.empty() ? text.erase(it) : std::next(it);
        s.push_back({std::move(kind), std::move(text), std::move(flags)});
    }
    void label(const std::string& t, Tone tone = Tone::kNormal, const std::string& tip = {}) {
        // (A path's label has it as its tooltip too: it may be cut short.)
        if (!t.empty())
            add("label", {{"t", t},
                          {"tone", tone_name(tone)},
                          {"tip", tone == Tone::kPath && tip.empty() && path_tips ? t : tip}});
    }
    void pill(const Pill& p) { add("pill", {{"t", p.text}, {"pill", pill_name(p.kind)}, {"tip", p.explain}}); }
    void icon(Icon i, Tone tone) {
        if (i != Icon::kNone) add("icon", {{"t", icon_name(i)}, {"tone", icon_tone(tone)}});
    }
    void action(const Action& a, bool expander_text = true) {
        if (all) all->push_back(a);
        switch (a.kind) {
        case ActionKind::kCheck:
            add("check", {{"id", a.id}, {"t", a.label}, {"tip", a.tooltip}},
                {{"on", a.checked}, {"mixed", a.inconsistent}, {"s", a.enabled}});
            break;
        case ActionKind::kSwitch:
            add("switch", {{"id", a.id}, {"tip", a.tooltip}}, {{"on", a.checked}, {"s", a.enabled}});
            break;
        case ActionKind::kChoice:
            add("choice",
                {{"id", a.id},
                 {"t", a.chosen >= 0 && a.chosen < static_cast<int>(a.choices.size()) ? a.choices[a.chosen] : ""},
                 {"tip", a.tooltip}},
                {{"s", a.enabled}});
            break;
        case ActionKind::kExpander:
            add("expander", {{"id", a.id}, {"t", expander_text ? a.label : ""}}, {{"on", a.checked}});
            break;
        case ActionKind::kMenuItem: break; // (in a menu: not drawn)
        default: {
            std::string cls = a.primary ? "primary" : a.destructive ? "destructive" : a.flat ? "flat" : "";
            add("button", {{"id", a.id}, {"t", a.label}, {"icon", icon_name(a.icon)}, {"tip", a.tooltip}, {"cls", cls}},
                {{"s", a.enabled}});
        }
        }
    }
    void line(const Line& l) {
        switch (l.kind) {
        case Line::Kind::kText: label(l.text, l.tone); break;
        case Line::Kind::kNote:
            icon(l.icon, l.icon_tone);
            label(l.text, l.tone);
            break;
        case Line::Kind::kSpinner:
            add("spinner", {});
            label(l.text, l.tone);
            break;
        case Line::Kind::kCommand: label(l.text, Tone::kNormal); break;
        case Line::Kind::kCheck:
            icon(l.icon, l.icon_tone);
            label(l.title);
            label(l.text, l.tone);
            break;
        case Line::Kind::kFile:
            icon(l.icon, l.icon_tone);
            label(l.title);
            label(l.text, Tone::kPath, l.text);
            break;
        }
        for (const Action& a : l.actions) action(a);
    }
};

void row(Out& o, const FighterRow& r) {
    o.label(r.display);
    if (r.outfits) o.action(*r.outfits);
    if (r.pill) o.pill(*r.pill);
    if (!r.state_text.empty()) o.label(r.state_text, Tone::kDim);
    for (const Action& b : r.buttons) o.action(b);
    if (!r.button_note.empty()) o.label(r.button_note, Tone::kDim);
}

} // namespace

namespace {

Dump flatten_into(const View& v, std::vector<Action>* all) {
    Dump d;
    for (const char* s : kSections) d[s];
    {
        Out o{d["header"], true, all};
        o.label(v.header.title, Tone::kHeading);
        for (const Action& a : v.header.actions) o.action(a);
    }
    if (v.page == Page::kMain) {
        if (v.notice.shown) {
            Out o{d["notice"], true, all};
            o.icon(v.notice.icon, Tone::kNormal);
            o.label(v.notice.title, Tone::kHeading);
            o.label(v.notice.detail, Tone::kDim);
            if (v.notice.page) o.action(*v.notice.page);
            o.action(v.notice.update);
        }
        {
            Out o{d["game"], true, all};
            const GameView& g = v.game;
            o.label(g.title, Tone::kHeading);
            o.label(g.folder, Tone::kPath, g.folder);
            o.pill(g.pill);
            for (const Line& l : g.body) o.line(l);
            for (const Action& a : g.actions) o.action(a);
        }
        {
            Out o{d["characters"], true, all};
            const CharactersView& c = v.characters;
            for (const Line& l : c.lines) o.line(l);
            for (const Fact& f : c.facts) {
                o.label(f.name, Tone::kDim);
                for (const Line& l : f.lines) o.line(l);
            }
            for (const Line& l : c.news) o.line(l);
            if (c.outfits_all) o.action(*c.outfits_all);
            for (const Line& l : c.outfits_notes) o.line(l);
            for (const GameGroup& g : c.games) {
                o.label(g.heading, Tone::kHeading);
                o.label(g.about, Tone::kDim);
                for (const Action& a : g.head) o.action(a);
                for (const Line& l : g.notes) o.line(l);
                for (const FighterRow& r : g.rows) row(o, r);
                if (g.dlc) {
                    const DlcBlock& b = *g.dlc;
                    o.action(b.expander, false);
                    o.label(b.expander.label, Tone::kHeading);
                    for (const Pill& p : b.pills) o.pill(p);
                    if (b.expander.checked) {
                        for (const Line& l : b.notes) o.line(l);
                        o.action(b.add_owned);
                        for (const FighterRow& r : b.rows) row(o, r);
                    }
                }
            }
        }
    } else if (v.settings) {
        Out o{d["settings"], true, all};
        const SettingsView& s = *v.settings;
        if (!s.display.empty()) {
            o.label(s.display_title, Tone::kHeading);
            o.label(s.display_about, Tone::kDim);
            for (const Line& l : s.display_notes) o.line(l);
            for (const SettingRow& r : s.display) {
                o.label(r.name);
                o.label(r.about, Tone::kDim);
                for (const Line& l : r.notes) o.line(l);
                o.action(r.control);
            }
        }
        if (!s.groups.empty()) {
            o.label(s.keys_title, Tone::kHeading);
            o.label(s.keys_about, Tone::kDim);
            for (const Line& l : s.keys_notes) o.line(l);
            for (const KeyGroup& g : s.groups) {
                o.label(g.title, Tone::kHeading);
                for (const KeyRow& r : g.rows) {
                    o.label(r.name);
                    if (!r.note.empty()) o.label(r.note, r.note_tone == Tone::kError ? Tone::kError : r.note_tone);
                    o.action(r.keycap);
                }
            }
            for (const Action& a : s.keys_actions) o.action(a);
        }
        if (s.folders_shown) {
            o.label(s.folders_title, Tone::kHeading);
            o.label(s.folders_about, Tone::kDim);
            for (const FolderRow& r : s.folders) {
                o.label(r.name);
                o.label(r.hint, Tone::kDim);
                o.label(r.value, Tone::kPath, r.value);
                o.action(r.browse);
            }
            for (const Action& a : s.folders_actions) o.action(a);
            for (const Line& l : s.folders_notes) o.line(l);
        }
        o.label(s.launcher_title, Tone::kHeading);
        o.label(s.launcher_about, Tone::kDim);
        for (const SettingRow& r : s.launcher) {
            o.label(r.name);
            o.label(r.about, Tone::kDim);
            o.action(r.control);
        }
    }
    if (v.task.shown) {
        Out o{d["task"], true, all};
        const TaskView& t = v.task;
        if (t.running) o.add("spinner", {});
        o.label(t.title, t.failed ? Tone::kError : Tone::kHeading);
        o.label(t.detail, Tone::kDim);
        o.action(t.button);
        if (t.running) o.add("progress", {});
        if (t.open_log) o.action(*t.open_log);
        o.action(t.details);
    }
    if (v.dialog) {
        Out o{d["dialog"], true, all};
        const Dialog& g = *v.dialog;
        o.label(g.title, Tone::kHeading);
        o.label(g.text, Tone::kDim);
        o.path_tips = false;
        for (const Line& l : g.lines) o.line(l);
        for (const Action& a : g.buttons) o.action(a);
    }
    return d;
}

} // namespace

Dump flatten(const View& v) { return flatten_into(v, nullptr); }

std::vector<Action> actions_of(const View& v) {
    std::vector<Action> all;
    flatten_into(v, &all);
    return all;
}

std::optional<Dump> parse_dump(std::string_view text, std::string* error) {
    const auto doc = json::parse(text, error);
    if (!doc || !doc->is_object()) return std::nullopt;
    Dump d;
    for (const char* s : kSections) {
        Section& section = d[s];
        for (const json::Value& v : (*doc)[s].items()) {
            Element e;
            for (size_t i = 0; i < v.keys().size(); ++i) {
                const std::string& key = v.keys()[i];
                const json::Value& value = v.values()[i];
                if (key == "k")
                    e.kind = value.string();
                else if (value.type() == json::Value::Type::kBool)
                    e.flags[key] = value.boolean();
                else
                    e.text[key] = value.string();
            }
            section.push_back(e);
        }
    }
    return d;
}

namespace {

std::string escaped(const std::string& t) {
    std::string o;
    for (const unsigned char c : t) {
        if (c == '"' || c == '\\') {
            o += '\\';
            o += static_cast<char>(c);
        } else if (c == '\n') {
            o += "\\n";
        } else if (c < 0x20) {
            char b[8];
            std::snprintf(b, sizeof b, "\\u%04x", c);
            o += b;
        } else {
            o += static_cast<char>(c);
        }
    }
    return o;
}

} // namespace

std::string element_text(const Element& e) {
    std::string s = "{\"k\": \"" + e.kind + "\"";
    for (const char* key : {"id", "t", "icon", "tone", "pill", "tip", "cls"}) {
        if (const auto it = e.text.find(key); it != e.text.end())
            s += std::string(", \"") + key + "\": \"" + escaped(it->second) + "\"";
    }
    for (const auto& [k, v] : e.text) {
        if (std::string("id t icon tone pill tip cls").find(k) == std::string::npos) {
            s += ", \"" + k + "\": \"" + escaped(v) + "\"";
        }
    }
    for (const char* key : {"on", "mixed", "s"}) {
        if (const auto it = e.flags.find(key); it != e.flags.end()) {
            s += std::string(", \"") + key + "\": " + (it->second ? "true" : "false");
        }
    }
    return s + "}";
}

std::string dump_json(const Dump& dump) {
    std::string out = "{\n";
    bool first = true;
    for (const char* s : kSections) {
        out += std::string(first ? "" : ",\n") + "  \"" + s + "\": [\n";
        first = false;
        const auto it = dump.find(s);
        if (it != dump.end()) {
            for (size_t i = 0; i < it->second.size(); ++i) {
                out += "    " + element_text(it->second[i]) + (i + 1 < it->second.size() ? ",\n" : "\n");
            }
        }
        out += "  ]";
    }
    return out + "\n}\n";
}

std::vector<std::string> compare(const Dump& golden, const Dump& model, const std::vector<std::string>& ignore_ids) {
    std::vector<std::string> out;
    for (const char* s : kSections) {
        static const Section none;
        const auto g = golden.find(s), m = model.find(s);
        const Section& a = g == golden.end() ? none : g->second;
        Section b = m == model.end() ? none : m->second;
        // (Ids the old app did not give: not compared.)
        for (size_t i = 0; i < b.size() && i < a.size(); ++i) {
            const auto id = b[i].text.find("id");
            if (id != b[i].text.end() && !a[i].text.count("id") &&
                std::find(ignore_ids.begin(), ignore_ids.end(), id->second) != ignore_ids.end()) {
                b[i].text.erase("id");
            }
        }
        const size_t n = std::max(a.size(), b.size());
        for (size_t i = 0; i < n; ++i) {
            if (i < a.size() && i < b.size() && a[i] == b[i]) continue;
            out.push_back(std::string(s) + "[" + std::to_string(i) + "]");
            out.push_back("  golden: " + (i < a.size() ? element_text(a[i]) : std::string("(none)")));
            out.push_back("  model:  " + (i < b.size() ? element_text(b[i]) : std::string("(none)")));
            break; // (the first difference of a section: the rest follows from it)
        }
    }
    return out;
}

} // namespace launcher::model
