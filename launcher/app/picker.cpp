// The in-app file and folder browser (#picker / #picker-folder): a controller chooses the game's .wua and the
// install folder here; the system's picker is one button away for mouse users. Crimson: the folder's places and
// entries; blue: the focused entry, what the launcher thinks of it, and Choose.
//
// Folders are read off the UI thread (a slow or sleeping drive never stalls input): the places once per opening,
// each folder's entries, then its folders' item counts, each answer posted back and dropped when another folder was
// asked for since. Only the rows in or near the view are declared (a folder of thousands stays as quick as one of
// ten); each row is fitted to the seam on its own (the staircase), so a long list keeps its width.

#include "app.h"
#include "utf8_path.h"

#include "system.h"

#include <SDL3/SDL_scancode.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>

namespace launcher::app {

using namespace ttt2::ui;
namespace c = theme::color;
namespace tx = theme::text;

namespace {

Box fit(Box b, SeamFit f) {
    b.fit = f;
    return b;
}

const Color kValue = rgb(0xdbe3f1);
constexpr float kPlacesWidth = 176, kPlacesMaxWidth = 224; // (wider for a language's longer place names)
constexpr float kRowGap = 6; // between the rows of a list

Focus crimson_focus(bool is_default = false) {
    Focus f;
    f.group = -1;
    f.is_default = is_default;
    return f;
}

Focus blue_focus() {
    Focus f;
    f.group = 1;
    return f;
}

std::string folder_name(const fs::path& p) {
    const std::string n = path_utf8(p.filename());
    return n.empty() ? path_utf8(p) : n;
}

// Settings > Folders' names, as the picker's title says them.
std::string folder_title(const std::string& key) {
    if (key == "source") return tr("picker.folder_source", "Wii U archive's folder");
    if (key == "title") return tr("picker.folder_title", "extracted game");
    if (key == "install") return tr("picker.folder_install", "installation folder");
    if (key == "data") return tr("picker.folder_data", "data folder");
    if (key == "packs") return tr("picker.folder_packs", "characters folder");
    if (key == "saves") return tr("picker.folder_saves", "saves folder");
    if (key == "tools") return tr("picker.folder_tools", "Windows tools folder");
    return tr("picker.folder_other", "{key} folder", {{"key", key}});
}

// The entry an id names ("pe:<index>"), none for another id.
const Entry* entry_of(const std::vector<Entry>& entries, const std::string& id) {
    if (!id.starts_with("pe:")) return nullptr;
    const size_t i = std::strtoul(id.c_str() + 3, nullptr, 10);
    return i < entries.size() ? &entries[i] : nullptr;
}

} // namespace

// A folder's listing as the worker read it.
struct App::Listing {
    fs::path dir; // the folder listed (the nearest one there when the one asked for is not)
    std::vector<Entry> entries;
    std::string error;
    std::optional<uint64_t> free;
    bool target_asked = false;
    std::optional<fs::path> target;
    std::string target_why;
};

void App::open_picker(bool folder, const std::string& purpose) {
    const fs::path home = home_folder();
    Picker p;
    p.folder = folder;
    p.purpose = purpose;
    p.back_focus = ui_->focused();
    p.session = ++picker_serial_;
    const m::Facts& f = model_->facts();
    fs::path from = folder ? slot_folder_ : f.chosen_game.empty() ? home / "Downloads" : f.chosen_game.parent_path();
    if (purpose.starts_with("folder:") || purpose == "setup-folder") {
        const auto it = f.windows.folders.find(purpose == "setup-folder" ? "install" : purpose.substr(7));
        // (The folders are UTF-8: as a wide path, so that a José in one is kept.)
        from = it == f.windows.folders.end() || it->second.empty()
                   ? home
                   : fs::path(std::u8string(it->second.begin(), it->second.end()));
    }
    picker_ = std::move(p);
    // The places (drives, Steam's and Wine's folders: disks are looked at), off the UI thread.
    const char* user = std::getenv("USER");
    run_detached([this, session = picker_->session, home, user = std::string(user ? user : "")](const Poster& post) {
        std::vector<Place> found = places(home, user);
        post([this, session, found = std::move(found)]() mutable {
            if (!picker_ || picker_->session != session) return;
            picker_->places = std::move(found);
            picker_->places_ready = true;
        });
    });
    picker_dir(from, {home / "Downloads", home});
    wipe_->start(now(), 1, model_->launcher_settings().reduce_motion);
    stage_->note_input(now());
}

void App::picker_dir(fs::path dir, const std::vector<fs::path>& fallbacks, fs::path refocus) {
    if (!picker_) return;
    Picker& p = *picker_;
    const bool again = !refocus.empty() && dir == p.dir;
    p.dir = dir;
    p.generation = ++picker_serial_;
    p.loading = true;
    p.counting = false;
    p.refocus = refocus;
    if (!again) {
        // (Another folder: its entries once they are read; the folder's row has the focus until then.)
        p.entries.clear();
        p.error.clear();
        p.free.reset();
        p.target_known = false;
        p.target.reset();
        p.target_why.clear();
        ui_->focus("pk/here", true);
    }
    const bool folders = p.folder, hidden = picker_hidden_;
#ifdef _WIN32
    const bool target = false;
#else
    const bool target = p.folder && p.purpose == "folder";
#endif
    run_detached([this, generation = p.generation, dir, fallbacks, folders, hidden, target](const Poster& post) {
        Listing l;
        l.dir = fallbacks.empty() ? dir : start_folder(dir, fallbacks);
        l.entries = list_folder(l.dir, folders, &l.error, hidden, false);
        l.free = free_space(l.dir);
#ifndef _WIN32
        if (target) {
            l.target_asked = true;
            l.target = launcher::install_target(l.dir, &l.target_why);
        }
#else
        (void)target;
#endif
        std::vector<fs::path> folders_in;
        for (const Entry& e : l.entries)
            if (e.kind == Entry::Kind::kFolder) folders_in.push_back(e.path);
        post([this, generation, l = std::move(l)]() mutable { picker_listed(generation, std::move(l)); });
        if (folders_in.empty()) return;
        // Then what each of its folders holds (one more read per folder).
        std::vector<int> counts;
        counts.reserve(folders_in.size());
        for (const fs::path& f : folders_in) counts.push_back(count_items(f, hidden));
        post([this, generation, counts = std::move(counts)]() mutable {
            picker_counted(generation, std::move(counts));
        });
    });
}

void App::picker_listed(uint64_t generation, Listing listing) {
    if (!picker_ || picker_->generation != generation) return;
    Picker& p = *picker_;
    const std::string was = ui_->focused();
    fs::path keep;
    if (const Entry* e = entry_of(p.entries, was)) keep = e->path;
    p.dir = listing.dir;
    p.entries = std::move(listing.entries);
    p.error = std::move(listing.error);
    p.free = listing.free;
    if (listing.target_asked) {
        p.target_known = true;
        p.target = std::move(listing.target);
        p.target_why = std::move(listing.target_why);
    }
    p.loading = false;
    p.counting = std::any_of(p.entries.begin(), p.entries.end(),
                             [](const Entry& e) { return e.kind == Entry::Kind::kFolder; });
    // Listed again (Show hidden): the entry that had the focus keeps it (its index may have changed).
    if (!p.refocus.empty() || !keep.empty()) {
        const fs::path want = !keep.empty() ? keep : p.refocus;
        p.refocus.clear();
        if (was.starts_with("pe:")) {
            std::string to = "pk/here";
            for (size_t i = 0; i < p.entries.size(); ++i)
                if (p.entries[i].path == want) to = "pe:" + std::to_string(i);
            ui_->focus(to, true);
        }
        return;
    }
    // A new folder whose row still has the focus: the first .wua, else the first entry after "up" (a folder's
    // browser: this folder's row, as it chooses it).
    if (was != "pk/here" || p.folder) return;
    std::string first;
    for (size_t i = 0; i < p.entries.size() && first.empty(); ++i)
        if (p.entries[i].wua) first = "pe:" + std::to_string(i);
    if (first.empty() && p.entries.size() > 1) first = "pe:1";
    else if (first.empty() && !p.entries.empty()) first = "pe:0";
    if (!first.empty()) ui_->focus(first, true);
}

void App::picker_counted(uint64_t generation, std::vector<int> counts) {
    if (!picker_ || picker_->generation != generation) return;
    size_t k = 0;
    for (Entry& e : picker_->entries)
        if (e.kind == Entry::Kind::kFolder && k < counts.size()) e.items = counts[k++];
    picker_->counting = false;
}

void App::picker_toggle_hidden() {
    if (!picker_) return;
    picker_hidden_ = !picker_hidden_;
    cue(ttt2::app::Cue::Toggle);
    // (The same folder again; the entry focused keeps the focus.)
    const Entry* e = entry_of(picker_->entries, ui_->focused());
    picker_dir(picker_->dir, {}, e ? e->path : picker_->dir);
}

bool App::shortcut(const ui::RawEvent& raw) {
    // Ctrl+H in the browser: hidden folders shown or not (as GTK's file chooser and file managers).
    if (picker_ && !view_.dialog && raw.kind == ui::RawEvent::KeyDown && raw.ctrl && !raw.alt && !raw.gui &&
        !raw.os_repeat && raw.code == SDL_SCANCODE_H && !router_.capturing()) {
#ifndef _WIN32
        picker_toggle_hidden();
        return true;
#endif
    }
    return false;
}

void App::close_picker() {
    if (!picker_) return;
    const std::string back = picker_->back_focus;
    picker_.reset();
    wipe_->start(now(), -1, model_->launcher_settings().reduce_motion);
    ui_->focus(back, true);
}

// `path` is a copy: it is often the picker's own entry or folder, gone once close_picker() resets the picker (read
// after that, the archive's path reached the model with its first letter overwritten in a French or Russian Windows
// launcher: "\0:\users\...").
void App::picker_chosen(fs::path path) {
    if (!picker_) return;
    const Picker p = *picker_;
    close_picker();
    if (p.purpose == "game") {
        if (p.then_answer) {
            answer_game(path);
        } else {
            model_->mutable_facts().chosen_game = path;
        }
        // (Windows' Set Up Game opens the folder's browser next: it keeps the focus.)
        if (!picker_) ui_->focus("slot:game", true);
    } else if (p.purpose == "setup-folder") {
        handle(model_->chosen_folder(path, now()));
    } else if (p.purpose.starts_with("folder:")) {
        const std::u8string folder = path.u8string(); // (UTF-8, as the state gives them: never the ANSI code page)
        set_folder(p.purpose.substr(7), std::string(folder.begin(), folder.end()));
        ui_->focus("fold:" + p.purpose.substr(7), true);
    } else {
        slot_folder_ = path;
        ui_->focus("slot:folder", true);
    }
}

bool App::picker_activate(const std::string& id) {
    if (!picker_) return false;
    Picker& p = *picker_;
    const auto entry = [&](const std::string& key) { return entry_of(p.entries, key); };
    if (id == "pk/hidden") {
        picker_toggle_hidden();
        return true;
    }
    if (id.starts_with("pp:")) {
        const size_t i = std::strtoul(id.c_str() + 3, nullptr, 10);
        if (i < p.places.size()) picker_dir(p.places[i].path);
        return true;
    }
    if (const Entry* e = entry(id)) {
        if (e->kind != Entry::Kind::kFile) picker_dir(e->path);
        else if (e->wua && !p.folder) picker_chosen(e->path);
        else
            toast(tr("picker.not_archive", "Not a Wii U game archive"),
                  tr("picker.needs_wua", "The launcher needs a .wua archive of the European game with update 16."));
        return true;
    }
    if (id == "pk/here") {
        if (p.folder) picker_chosen(p.dir);
        return true;
    }
    if (id == "pk/choose-here") {
        picker_chosen(p.dir);
        return true;
    }
    if (id == "pk/new") {
        // (No typing: "New folder", "New folder 2", ...; renamed later in the file manager if wanted.)
        std::error_code ec;
        fs::path made;
        for (int n = 1; n < 100 && made.empty(); ++n) {
            const fs::path f = p.dir / utf8_path(n == 1 ? tr("picker.new_folder_name", "New folder")
                                                        : tr("picker.new_folder_n", "New folder {n}", {{"n", n}}));
            if (!fs::exists(f, ec) && fs::create_directory(f, ec)) made = f;
        }
        if (made.empty()) {
            toast(tr("picker.no_new_folder", "No new folder"),
                  ec ? ec.message() : tr("picker.cannot_hold", "This folder cannot hold another one."));
            return true;
        }
        picker_dir(made);
        cue(ttt2::app::Cue::Accept);
        return true;
    }
    if (id == "pk/choose") {
        if (const Entry* e = entry(picker_key_)) {
            if (e->kind == Entry::Kind::kFolder && p.folder) picker_chosen(e->path);
            else if (e->kind == Entry::Kind::kFile && e->wua && !p.folder) picker_chosen(e->path);
        } else if (p.folder) {
            picker_chosen(p.dir);
        }
        return true;
    }
    if (id == "pk/open") {
        if (const Entry* e = entry(picker_key_); e && e->kind != Entry::Kind::kFile) picker_dir(e->path);
        return true;
    }
    if (id == "pk/system") {
        if (o_.testing) {
            toast("Not in tests", "The system's picker is not opened while the launcher is tested."); // (tests only)
            return true;
        }
        const bool folder = p.folder;
        const fs::path start = p.dir;
        auto done = [this, folder](fs::path chosen) {
            if (!chosen.empty() && picker_ && picker_->folder == folder) picker_chosen(chosen);
        };
        if (folder) system_pick_folder(window_.sdl(), start, [this](std::function<void()> w) { post(std::move(w)); }, done);
        else system_pick_game(window_.sdl(), start, [this](std::function<void()> w) { post(std::move(w)); }, done);
        return true;
    }
    return false;
}

// The folder's entries as rows: only those in or near the view are declared, each fitted to the
// seam at its own height; spacers stand for the others, each exactly as tall as its rows and their gaps, so every
// row is where it would be with all of them (the scroll bar, PgUp/PgDn and scroll anchoring see the whole list).
// Declared: the rows in view and one view's worth around it (at the scroll offset and at its target), one view's
// worth around the focused row (Down from it, a focus set from outside: the first .wua), and the last row (End).
void App::picker_rows() {
    Ui& ui = *ui_;
    Picker& p = *picker_;
    const int n = static_cast<int>(p.entries.size());
    if (n == 0) return;
    const float pitch = theme::metric::kFileRowHeight + kRowGap;
    // Where the rows were (content space of the crimson scroller) and what it shows, from the last frame.
    float view_h = ui.frame().size.y, top = 0, at = 0, target = 0;
    NodeState* scroller = ui.state("pk/crimson");
    const NodeState* rows = ui.state("pk/rows");
    if (scroller && scroller->rect.h > 0) {
        view_h = scroller->rect.h;
        if (rows && rows->rect.h > 0) top = rows->rect.y - scroller->rect.y + p.last_scroll;
        // (A jump of more than a few views - End, Home, the first .wua far down - is not animated: every frame
        // shows rows that are declared.)
        if (std::fabs(scroller->scroll.target - scroller->scroll.value) > 3 * view_h) scroller->scroll.snap();
        at = scroller->scroll.value;
        target = scroller->scroll.target;
    }
    p.last_scroll = at;
    const int per_view = static_cast<int>(std::ceil(view_h / pitch)) + 1;
    std::vector<std::pair<int, int>> spans; // [from, to] rows
    const auto around = [&](float offset) {
        const int first = static_cast<int>(std::floor((offset - top) / pitch));
        spans.push_back({first - per_view, first + 2 * per_view});
    };
    around(at);
    if (target != at) around(target);
    int focused = -1;
    const std::string& f = ui.focused().starts_with("pe:") ? ui.focused() : picker_key_;
    if (f.starts_with("pe:")) focused = static_cast<int>(std::strtol(f.c_str() + 3, nullptr, 10));
    if (focused >= 0 && focused < n) spans.push_back({focused - per_view, focused + per_view});
    spans.push_back({n - 1, n - 1});
    for (auto& s : spans) s = {std::clamp(s.first, 0, n - 1), std::clamp(s.second, 0, n - 1)};
    std::sort(spans.begin(), spans.end());
    std::vector<std::pair<int, int>> merged;
    for (const auto& s : spans) {
        if (!merged.empty() && s.first <= merged.back().second + 1) merged.back().second = std::max(merged.back().second, s.second);
        else merged.push_back(s);
    }
    auto list = ui.open("pk/rows", Box{.gap = kRowGap});
    int next = 0, spacers = 0;
    p.declared = 0;
    // k rows left out: as tall as they and their gaps are, less the one gap the column puts after the spacer.
    const auto spacer = [&](int k) {
        ui.leaf("pk/rows/gap" + std::to_string(spacers++), Box{.h = Size::fixed(k * pitch - kRowGap)}, {}, {});
    };
    for (const auto& [from, to] : merged) {
        if (from > next) spacer(from - next);
        for (int i = from; i <= to; ++i) {
            const Entry& e = p.entries[static_cast<size_t>(i)];
            FileRowSpec r;
            r.name = e.name;
            if (e.kind == Entry::Kind::kUp) {
                r.icon = "stroke:up";
                r.meta = tr("picker.up_meta", "up");
            } else if (e.kind == Entry::Kind::kFolder) {
                r.icon = "stroke:folder";
                r.meta = e.items < 0 ? "" : trn("picker.items", e.items, "{n} item", "{n} items");
            } else {
                r.icon = e.wua ? "stroke:disc" : "stroke:file";
                r.meta = size_text(e.size);
                r.tone = e.wua ? Tone::Ok : Tone::Dim;
            }
            file_row(ui, "pe:" + std::to_string(i), r, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
            ++p.declared;
        }
        next = to + 1;
    }
    if (next < n) spacer(n - next);
}

void App::picker_screen(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    Picker& p = *picker_;
    const std::string title = !p.folder ? tr("picker.choose_wua_title", "Choose the game's .wua")
                              : p.purpose.starts_with("folder:")
                                  ? tr("picker.choose_the", "Choose the {folder}", {{"folder", folder_title(p.purpose.substr(7))}})
                                  : tr("picker.choose_where", "Choose where to install");
    {
        auto g = ui.open("pk/crimson", crimson);
        section_label(ui, "pk/label", title, Half::Crimson, {}, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::CrimsonRect));
        MenuRowSpec here{"stroke:open", m::shown_path(p.dir), p.folder ? tr("hint.choose", "Choose") : ""};
        here.compact = true;
        here.mono_title = true;
        menu_row(ui, "pk/here", here, crimson_focus(p.entries.empty()), fit({}, SeamFit::CrimsonSkewed));
        // (Not fitted as a whole: a long list's bottom lies far left on the slanted seam. The rows
        // and lines in it are fitted each on its own.)
        auto cols = ui.open("pk/cols", Box{.layout = Layout::Row, .margin = {0, 12, 0, 0}, .gap = 18,
                                           .align = Align::Start});
        {
            // (As wide as its longest row needs, "Téléchargements", "Домашняя папка": 176 to 224 points.)
            TextEngine& te = ui.text();
            // (A file row: icon, name, 12 points, its kind, the ends; the slanted rows lower down a little narrower.)
            auto row_width = [&te](const std::string& name, const std::string& meta) {
                return std::ceil(16 + 18 + 12 + te.width(tx::kFileName, name) + 12 + te.width(tx::kFileMeta, meta) +
                                 16 + 8);
            };
            float places_width = kPlacesWidth;
            for (const Place& place : p.places) places_width = std::max(places_width, row_width(place.name, place.kind));
#ifndef _WIN32
            places_width = std::max(places_width, row_width(tr("picker.show_hidden", "Show hidden"), ""));
#endif
            places_width = std::min(places_width, kPlacesMaxWidth);
            auto pl = ui.open("pk/places", Box{.w = Size::fixed(places_width), .gap = kRowGap});
            // (Each as wide as the column, narrower where the seam comes closer: a small window, a long list.)
            text(ui, "pk/places-h", TextSpec{tr("picker.places", "Places"), tx::kLabel, c::kRedLabel},
                 fit(Box{.max_w = places_width, .margin = {0, 0, 0, 4}}, SeamFit::CrimsonRect));
            for (size_t i = 0; i < p.places.size(); ++i) {
                FileRowSpec r{p.places[i].icon, p.places[i].name, p.places[i].kind};
                if (p.places[i].path == p.dir) r.tone = Tone::Ok;
                file_row(ui, "pp:" + std::to_string(i), r, crimson_focus(),
                         fit(Box{.max_w = places_width}, SeamFit::CrimsonSkewed));
            }
#ifndef _WIN32
            // Folders whose names start with a dot (.local, .steam, .var): a row the pad reaches (and Ctrl+H, X).
            // (Ticked when on, as a check box.)
            FileRowSpec hid{picker_hidden_ ? "stroke:check" : "stroke:dots", tr("picker.show_hidden", "Show hidden"), ""};
            hid.tone = picker_hidden_ ? Tone::Ok : Tone::Neutral;
            file_row(ui, "pk/hidden", hid, crimson_focus(),
                     fit(Box{.max_w = places_width, .margin = {6, 0, 0, 0}}, SeamFit::CrimsonSkewed));
#endif
        }
        auto en = ui.open("pk/entries", Box{.w = Size::grow(), .gap = kRowGap});
        const bool nothing = p.entries.empty() || (p.entries.size() == 1 && p.entries[0].kind == Entry::Kind::kUp);
        text(ui, "pk/entries-h",
             TextSpec{!p.error.empty() ? tr("picker.cannot_read", "Cannot read it: {error}", {{"error", p.error}})
                      : p.folder        ? tr("settings.folders", "Folders")
                                        : tr("picker.files_folders", "Files and folders"),
                      tx::kLabel, c::kRedLabel},
             fit(Box{.margin = {0, 0, 0, 4}}, SeamFit::CrimsonRect));
        if (p.loading && p.entries.empty())
            text(ui, "pk/reading", TextSpec{tr("picker.reading", "Reading this folder…"), tx::kParaSmall, c::kRedDim},
                 fit(Box{.margin = {6, 4, 0, 0}}, SeamFit::CrimsonRect));
        else
            picker_rows();
        if (nothing && !p.loading && p.error.empty())
            text(ui, "pk/empty",
                 TextSpec{p.folder ? tr("picker.no_folders", "No folders in it: the row above chooses it.")
                                   : tr("picker.empty", "No files or folders in it."),
                          tx::kParaSmall, c::kRedDim},
                 fit(Box{.margin = {6, 4, 0, 0}}, SeamFit::CrimsonRect));
    }
    auto g = ui.open("pk/blue", blue);
    const std::string& fo = ui.focused();
    if (fo.starts_with("pe:") || fo.starts_with("pp:") || fo == "pk/here" || fo == "pk/hidden") picker_key_ = fo;
    const std::string key = path_utf8(p.dir) + "|" + picker_key_;
    readout_.show(key, last_dy_, ui.now());
    readout_.build(ui, "pk/ro", Box{}, [&](const std::string&) {
        const std::string k = picker_key_;
        ButtonSpec sys;
        sys.label = p.folder ? tr("picker.system_folder", "System Folder Picker…") : tr("picker.system_file", "System File Picker…");
        sys.size = ButtonSize::Small;
        const auto big = [&](const std::string& id, const std::string& name) {
            // (As the mock's: the name big and split, smaller until it fits, then cut in the middle.)
            text(ui, id,
                 TextSpec{.text = name, .style = tx::kBig, .ellipsis = Ellipsis::Middle, .chroma = 3,
                          .autofit_min = 22},
                 fit(Box{.margin = {0, 2, 0, 10}}, SeamFit::BlueRect));
        };
        if (k == "pk/hidden") {
            section_label(ui, "pk/b-label", tr("picker.hidden_folders", "Hidden folders"), Half::Blue, {}, fit({}, SeamFit::BlueRect));
            big("pk/b-name", picker_hidden_ ? tr("picker.shown", "Shown") : tr("picker.not_shown", "Not shown"));
            const Fact list[] = {{tr("folders.now", "Now"),
                                  {{picker_hidden_ ? tr("picker.listed_too", "Listed too") : tr("picker.left_out", "Left out"), kValue}},
                                  false},
                                 {tr("picker.keys", "Keys"), {{"Ctrl+H", kValue}}, false}};
            facts(ui, "pk/b-facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
            text(ui, "pk/b-para",
                 TextSpec{.text = tr("picker.hidden_about", "Names starting with a dot (.local, .steam, .var) are left "
                                                            "out of the lists, as file managers do. Accept shows them "
                                                            "too; again hides them."),
                          .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
                 fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
            button(ui, "pk/system", sys, blue_focus(), fit({}, SeamFit::BlueRect));
            return;
        }
        if (k.starts_with("pp:")) {
            const size_t i = std::strtoul(k.c_str() + 3, nullptr, 10);
            if (i < p.places.size()) {
                section_label(ui, "pk/b-label",
                              p.places[i].kind.empty() ? tr("picker.place", "Place")
                                                       : tr("picker.kind_place", "{kind} place", {{"kind", p.places[i].kind}}),
                              Half::Blue, {}, fit({}, SeamFit::BlueRect));
                big("pk/b-name", p.places[i].name);
                const Fact list[] = {{tr("picker.where", "Where"), {{m::shown_path(p.places[i].path), kValue}}}};
                facts(ui, "pk/b-facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                text(ui, "pk/b-para", TextSpec{.text = tr("picker.opens_in_list", "Accept opens it in the list."), .style = tx::kPara,
                                               .color = c::kBlueDim, .wrap = true},
                     fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
                button(ui, "pk/system", sys, blue_focus(), fit({}, SeamFit::BlueRect));
                return;
            }
        }
        if (k.starts_with("pe:")) {
            const size_t i = std::strtoul(k.c_str() + 3, nullptr, 10);
            if (i < p.entries.size()) {
                const Entry& e = p.entries[i];
                if (e.kind == Entry::Kind::kUp || e.kind == Entry::Kind::kFolder) {
                    section_label(ui, "pk/b-label", tr("home.folder", "Folder"), Half::Blue, {}, fit({}, SeamFit::BlueRect));
                    big("pk/b-name", e.kind == Entry::Kind::kUp ? tr("picker.up", "Up") : e.name);
                    std::vector<Fact> list = {{e.kind == Entry::Kind::kUp ? tr("picker.to", "To") : tr("picker.where", "Where"),
                                               {{m::shown_path(e.path), kValue}}}};
                    if (e.kind == Entry::Kind::kFolder && e.items >= 0)
                        list.push_back({tr("picker.holds", "Holds"), {{trn("picker.items", e.items, "{n} item", "{n} items"), kValue}}, false});
                    else if (e.kind == Entry::Kind::kFolder && e.items == kNotCounted)
                        list.push_back({tr("picker.holds", "Holds"), {{tr("picker.counting", "Counting…"), kValue}}, false});
                    facts(ui, "pk/b-facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                    const std::string para = e.kind == Entry::Kind::kUp ? tr("picker.goes_up", "Goes up one folder.")
                                             : p.folder ? tr("picker.folder_para", "Accept opens it; Choose takes it as it is.")
                                                        : tr("picker.accept_opens", "Accept opens it.");
                    text(ui, "pk/b-para", TextSpec{.text = para, .style = tx::kPara, .color = c::kBlueDim,
                                                   .wrap = true},
                         fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
                    auto row = ui.open("pk/b-btns",
                                       fit(Box{.layout = Layout::Row, .gap = 12, .wrap = true}, SeamFit::BlueRect));
                    if (p.folder && e.kind == Entry::Kind::kFolder) {
                        ButtonSpec ch;
                        ch.label = tr("hint.choose", "Choose");
                        ch.kind = ButtonKind::Blue;
                        ch.size = ButtonSize::Small;
                        button(ui, "pk/choose", ch, blue_focus());
                    }
                    ButtonSpec op;
                    op.label = tr("hint.open", "Open");
                    op.size = ButtonSize::Small;
                    button(ui, "pk/open", op, blue_focus());
                    return;
                }
                section_label(ui, "pk/b-label", tr("picker.file", "File"), Half::Blue, {}, fit({}, SeamFit::BlueRect));
                big("pk/b-name", e.name);
                pill(ui, "pk/b-pill", e.wua ? tr("picker.archive", "A Wii U game archive") : tr("picker.not_archive", "Not a Wii U game archive"),
                     e.wua ? Tone::Ok : Tone::Dim, false, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                const Fact list[] = {{tr("picker.size", "Size"), {{size_text(e.size), kValue}}, false},
                                     {tr("picker.where", "Where"), {{m::shown_path(p.dir), kValue}}}};
                facts(ui, "pk/b-facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                const std::string why =
                    e.wua ? tr("picker.wua_about", "The launcher needs the European game with update 16 as a .wua: the "
                                                   "install checks it fully before it builds anything.")
                          : tr("picker.needs_wua", "The launcher needs a .wua archive of the European game with update 16.");
                text(ui, "pk/b-para", TextSpec{.text = why, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
                     fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
                auto row =
                    ui.open("pk/b-btns", fit(Box{.layout = Layout::Row, .gap = 12, .wrap = true}, SeamFit::BlueRect));
                if (e.wua) {
                    ButtonSpec ch;
                    ch.label = tr("hint.choose", "Choose");
                    ch.kind = ButtonKind::Blue;
                    ch.size = ButtonSize::Small;
                    ch.prompt = Prompt::Accept;
                    button(ui, "pk/choose", ch, blue_focus());
                }
                button(ui, "pk/system", sys, blue_focus());
                return;
            }
        }
        // This folder.
        section_label(ui, "pk/b-label", tr("picker.this_folder", "This folder"), Half::Blue, {}, fit({}, SeamFit::BlueRect));
        big("pk/b-name", folder_name(p.dir));
        std::vector<Fact> list = {{tr("picker.where", "Where"), {{m::shown_path(p.dir), kValue}}}};
        if (p.free) list.push_back({tr("picker.free", "Free"), {{size_text(*p.free), kValue}}, false});
#ifndef _WIN32
        // (Read with the listing, not each frame: install_target looks at the disk.)
        if (p.folder && p.purpose == "folder" && p.target_known) {
            list.push_back({tr("picker.the_game", "The game"),
                            {{p.target ? m::shown_path(*p.target) : p.target_why, p.target ? kValue : c::kWarn}}});
        }
#endif
        facts(ui, "pk/b-facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
        std::string para = tr("picker.choose_wua_para", "Choose a .wua in the list on the left: the launcher marks the "
                                                        "ones that can be the game.");
        if (p.purpose.starts_with("folder:")) {
            para = tr("picker.folder_choose_para", "Choose This Folder takes it as the {folder}; New Folder makes an "
                                                   "empty one in it.",
                      {{"folder", folder_title(p.purpose.substr(7))}});
        } else if (p.purpose == "setup-folder") {
            para = tr("picker.setup_folder_para", "The game is installed into this folder: about 30 GB with its tools. "
                                                  "New Folder makes an empty one in it.");
        } else if (p.folder) {
#ifndef _WIN32
            para = p.target && normal(*p.target) == normal(p.dir)
                       ? tr("picker.into_itself", "The game goes into this folder itself (it is empty): about 16 GB, "
                                                  "plus 3 GB while building.")
                       : tr("picker.into_own", "The game goes into its own folder in here: about 16 GB, plus 3 GB "
                                               "while building.");
#endif
        }
        text(ui, "pk/b-para", TextSpec{.text = para, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
             fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
        auto row = ui.open("pk/b-btns", fit(Box{.layout = Layout::Row, .gap = 12, .wrap = true}, SeamFit::BlueRect));
        if (p.folder) {
            ButtonSpec ch;
            ch.label = tr("picker.choose_this", "Choose This Folder");
            ch.kind = ButtonKind::Blue;
            ch.size = ButtonSize::Small;
            ch.prompt = Prompt::Accept;
            button(ui, "pk/choose-here", ch, blue_focus());
            ButtonSpec nf;
            nf.label = tr("picker.new_folder", "New Folder");
            nf.size = ButtonSize::Small;
            button(ui, "pk/new", nf, blue_focus());
        }
        button(ui, "pk/system", sys, blue_focus());
    });
}

} // namespace launcher::app
