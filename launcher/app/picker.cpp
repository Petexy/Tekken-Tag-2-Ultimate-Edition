// The in-app file and folder browser (#picker / #picker-folder): a controller chooses the game's .wua and the
// install folder here; the system's picker is one button away for mouse users. Crimson: the folder's places and
// entries; blue: the focused entry, what the launcher thinks of it, and Choose.

#include "app.h"
#include "utf8_path.h"

#include "system.h"

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
    if (key == "source") return "Wii U archive's folder";
    if (key == "title") return "extracted game";
    if (key == "install") return "installation folder";
    if (key == "data") return "data folder";
    if (key == "packs") return "characters folder";
    if (key == "saves") return "saves folder";
    if (key == "tools") return "Windows tools folder";
    return key + " folder";
}

} // namespace

void App::open_picker(bool folder, const std::string& purpose) {
    const fs::path home = home_folder();
    Picker p;
    p.folder = folder;
    p.purpose = purpose;
    const char* user = std::getenv("USER");
    p.places = places(home, user ? user : "");
    p.back_focus = ui_->focused();
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
    picker_dir(start_folder(from, {home / "Downloads", home}));
    wipe_->start(now(), 1, model_->launcher_settings().reduce_motion);
    stage_->note_input(now());
}

void App::picker_dir(const fs::path& dir) {
    if (!picker_) return;
    picker_->dir = dir;
    picker_->error.clear();
    picker_->entries = list_folder(dir, picker_->folder, &picker_->error);
    picker_->free = free_space(dir);
    // The first .wua, else the first entry after "up".
    std::string first = "pk/here";
    if (!picker_->folder) {
        for (size_t i = 0; i < picker_->entries.size(); ++i)
            if (picker_->entries[i].wua) {
                first = "pe:" + std::to_string(i);
                break;
            }
    }
    // (A folder: this one, as the row on top chooses it; a file: the first entry after "up" without a .wua.)
    if (!picker_->folder && first == "pk/here" && picker_->entries.size() > 1) first = "pe:1";
    else if (!picker_->folder && first == "pk/here" && !picker_->entries.empty()) first = "pe:0";
    ui_->focus(first, true);
}

void App::close_picker() {
    if (!picker_) return;
    const std::string back = picker_->back_focus;
    picker_.reset();
    wipe_->start(now(), -1, model_->launcher_settings().reduce_motion);
    ui_->focus(back, true);
}

void App::picker_chosen(const fs::path& path) {
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
    const auto entry = [&](const std::string& key) -> const Entry* {
        if (!key.starts_with("pe:")) return nullptr;
        const size_t i = std::strtoul(key.c_str() + 3, nullptr, 10);
        return i < p.entries.size() ? &p.entries[i] : nullptr;
    };
    if (id.starts_with("pp:")) {
        const size_t i = std::strtoul(id.c_str() + 3, nullptr, 10);
        if (i < p.places.size()) picker_dir(p.places[i].path);
        return true;
    }
    if (const Entry* e = entry(id)) {
        if (e->kind != Entry::Kind::kFile) picker_dir(e->path);
        else if (e->wua && !p.folder) picker_chosen(e->path);
        else toast("Not a Wii U game archive", "The launcher needs a .wua archive of the European game with update 16.");
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
            const fs::path f = p.dir / (n == 1 ? std::string("New folder") : "New folder " + std::to_string(n));
            if (!fs::exists(f, ec) && fs::create_directory(f, ec)) made = f;
        }
        if (made.empty()) {
            toast("No new folder", ec ? ec.message() : std::string("This folder cannot hold another one."));
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
            toast("Not in tests", "The system's picker is not opened while the launcher is tested.");
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

void App::picker_screen(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    Picker& p = *picker_;
    const std::string title = !p.folder                         ? "Choose the game's .wua"
                              : p.purpose.starts_with("folder:") ? "Choose the " + folder_title(p.purpose.substr(7))
                                                                 : "Choose where to install";
    {
        auto g = ui.open("pk/crimson", crimson);
        section_label(ui, "pk/label", title, Half::Crimson, {}, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::CrimsonRect));
        MenuRowSpec here{"stroke:open", m::shown_path(p.dir), p.folder ? "Choose" : ""};
        here.compact = true;
        here.mono_title = true;
        menu_row(ui, "pk/here", here, crimson_focus(p.entries.empty()), fit({}, SeamFit::CrimsonSkewed));
        auto cols = ui.open("pk/cols", fit(Box{.layout = Layout::Row, .margin = {0, 12, 0, 0}, .gap = 18,
                                               .align = Align::Start},
                                           SeamFit::CrimsonRect));
        {
            auto pl = ui.open("pk/places", Box{.w = Size::fixed(176), .gap = 6});
            text(ui, "pk/places-h", TextSpec{"Places", tx::kLabel, c::kRedLabel}, Box{.margin = {0, 0, 0, 4}});
            for (size_t i = 0; i < p.places.size(); ++i) {
                FileRowSpec r{p.places[i].icon, p.places[i].name, ""};
                if (p.places[i].path == p.dir) r.tone = Tone::Ok;
                file_row(ui, "pp:" + std::to_string(i), r, crimson_focus());
            }
        }
        auto en = ui.open("pk/entries", Box{.w = Size::grow(), .gap = 6});
        const bool nothing = p.entries.empty() || (p.entries.size() == 1 && p.entries[0].kind == Entry::Kind::kUp);
        text(ui, "pk/entries-h",
             TextSpec{!p.error.empty() ? "Cannot read it: " + p.error
                      : p.folder        ? "Folders"
                                        : "Files and folders",
                      tx::kLabel, c::kRedLabel},
             Box{.margin = {0, 0, 0, 4}});
        for (size_t i = 0; i < p.entries.size(); ++i) {
            const Entry& e = p.entries[i];
            FileRowSpec r;
            r.name = e.name;
            if (e.kind == Entry::Kind::kUp) {
                r.icon = "stroke:up";
                r.meta = "up";
            } else if (e.kind == Entry::Kind::kFolder) {
                r.icon = "stroke:folder";
                r.meta = e.items < 0 ? "" : std::to_string(e.items) + (e.items == 1 ? " item" : " items");
            } else {
                r.icon = e.wua ? "stroke:disc" : "stroke:file";
                r.meta = size_text(e.size);
                r.tone = e.wua ? Tone::Ok : Tone::Dim;
            }
            file_row(ui, "pe:" + std::to_string(i), r, crimson_focus());
        }
        if (nothing && p.error.empty())
            text(ui, "pk/empty",
                 TextSpec{p.folder ? "No folders in it: the row above chooses it." : "No files or folders in it.",
                          tx::kParaSmall, c::kRedDim},
                 Box{.margin = {6, 4, 0, 0}});
    }
    auto g = ui.open("pk/blue", blue);
    const std::string& fo = ui.focused();
    if (fo.starts_with("pe:") || fo.starts_with("pp:") || fo == "pk/here") picker_key_ = fo;
    const std::string key = path_utf8(p.dir) + "|" + picker_key_;
    readout_.show(key, last_dy_, ui.now());
    readout_.build(ui, "pk/ro", Box{}, [&](const std::string&) {
        const std::string k = picker_key_;
        ButtonSpec sys;
        sys.label = p.folder ? "System Folder Picker…" : "System File Picker…";
        sys.size = ButtonSize::Small;
        const auto big = [&](const std::string& id, const std::string& name) {
            // (As the mock's: the name big and split, smaller until it fits, then cut in the middle.)
            text(ui, id,
                 TextSpec{.text = name, .style = tx::kBig, .ellipsis = Ellipsis::Middle, .chroma = 3,
                          .autofit_min = 22},
                 fit(Box{.margin = {0, 2, 0, 10}}, SeamFit::BlueRect));
        };
        if (k.starts_with("pp:")) {
            const size_t i = std::strtoul(k.c_str() + 3, nullptr, 10);
            if (i < p.places.size()) {
                section_label(ui, "pk/b-label", "Place", Half::Blue, {}, fit({}, SeamFit::BlueRect));
                big("pk/b-name", p.places[i].name);
                const Fact list[] = {{"Where", {{m::shown_path(p.places[i].path), kValue}}}};
                facts(ui, "pk/b-facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                text(ui, "pk/b-para", TextSpec{.text = "Accept opens it in the list.", .style = tx::kPara,
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
                    section_label(ui, "pk/b-label", "Folder", Half::Blue, {}, fit({}, SeamFit::BlueRect));
                    big("pk/b-name", e.kind == Entry::Kind::kUp ? "Up" : e.name);
                    std::vector<Fact> list = {{e.kind == Entry::Kind::kUp ? "To" : "Where",
                                               {{m::shown_path(e.path), kValue}}}};
                    if (e.kind == Entry::Kind::kFolder && e.items >= 0)
                        list.push_back({"Holds", {{std::to_string(e.items) + " items", kValue}}, false});
                    facts(ui, "pk/b-facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                    const std::string para = e.kind == Entry::Kind::kUp ? "Goes up one folder."
                                             : p.folder ? "Accept opens it; Choose takes it as it is."
                                                        : "Accept opens it.";
                    text(ui, "pk/b-para", TextSpec{.text = para, .style = tx::kPara, .color = c::kBlueDim,
                                                   .wrap = true},
                         fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
                    auto row = ui.open("pk/b-btns",
                                       fit(Box{.layout = Layout::Row, .gap = 12, .wrap = true}, SeamFit::BlueRect));
                    if (p.folder && e.kind == Entry::Kind::kFolder) {
                        ButtonSpec ch;
                        ch.label = "Choose";
                        ch.kind = ButtonKind::Blue;
                        ch.size = ButtonSize::Small;
                        button(ui, "pk/choose", ch, blue_focus());
                    }
                    ButtonSpec op;
                    op.label = "Open";
                    op.size = ButtonSize::Small;
                    button(ui, "pk/open", op, blue_focus());
                    return;
                }
                section_label(ui, "pk/b-label", "File", Half::Blue, {}, fit({}, SeamFit::BlueRect));
                big("pk/b-name", e.name);
                pill(ui, "pk/b-pill", e.wua ? "A Wii U game archive" : "Not a Wii U game archive",
                     e.wua ? Tone::Ok : Tone::Dim, false, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                const Fact list[] = {{"Size", {{size_text(e.size), kValue}}, false},
                                     {"Where", {{m::shown_path(p.dir), kValue}}}};
                facts(ui, "pk/b-facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                const std::string why =
                    e.wua ? "The launcher needs the European game with update 16 as a .wua: the install checks it "
                            "fully before it builds anything."
                          : "The launcher needs a .wua archive of the European game with update 16.";
                text(ui, "pk/b-para", TextSpec{.text = why, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
                     fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
                auto row =
                    ui.open("pk/b-btns", fit(Box{.layout = Layout::Row, .gap = 12, .wrap = true}, SeamFit::BlueRect));
                if (e.wua) {
                    ButtonSpec ch;
                    ch.label = "Choose";
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
        section_label(ui, "pk/b-label", "This folder", Half::Blue, {}, fit({}, SeamFit::BlueRect));
        big("pk/b-name", folder_name(p.dir));
        std::vector<Fact> list = {{"Where", {{m::shown_path(p.dir), kValue}}}};
        if (p.free) list.push_back({"Free", {{size_text(*p.free), kValue}}, false});
#ifndef _WIN32
        if (p.folder && p.purpose == "folder") {
            std::string why;
            const auto target = launcher::install_target(p.dir, &why);
            list.push_back({"The game", {{target ? m::shown_path(*target) : why, target ? kValue : c::kWarn}}});
        }
#endif
        facts(ui, "pk/b-facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
        std::string para = "Choose a .wua in the list on the left: the launcher marks the ones that can be the game.";
        if (p.purpose.starts_with("folder:")) {
            para = "Choose This Folder takes it as the " + folder_title(p.purpose.substr(7)) +
                   "; New Folder makes an empty one in it.";
        } else if (p.purpose == "setup-folder") {
            para = "The game is installed into this folder: about 30 GB with its tools. New Folder makes an empty "
                   "one in it.";
        } else if (p.folder) {
#ifndef _WIN32
            const auto target = launcher::install_target(p.dir);
            para = target && normal(*target) == normal(p.dir)
                       ? "The game goes into this folder itself (it is empty): about 16 GB, plus 3 GB while building."
                       : "The game goes into its own folder in here: about 16 GB, plus 3 GB while building.";
#endif
        }
        text(ui, "pk/b-para", TextSpec{.text = para, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
             fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
        auto row = ui.open("pk/b-btns", fit(Box{.layout = Layout::Row, .gap = 12, .wrap = true}, SeamFit::BlueRect));
        if (p.folder) {
            ButtonSpec ch;
            ch.label = "Choose This Folder";
            ch.kind = ButtonKind::Blue;
            ch.size = ButtonSize::Small;
            ch.prompt = Prompt::Accept;
            button(ui, "pk/choose-here", ch, blue_focus());
            ButtonSpec nf;
            nf.label = "New Folder";
            nf.size = ButtonSize::Small;
            button(ui, "pk/new", nf, blue_focus());
        }
        button(ui, "pk/system", sys, blue_focus());
    });
}

} // namespace launcher::app
