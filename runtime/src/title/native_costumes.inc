// Included inside roster.cpp's private namespace, after the costume table helpers.
// Native identity and motion rows stay in the title. Only body recipes differ.
void prepare_native_costume(const fs::path& folder, const std::string& target,
                            const std::map<uint32_t, Located>& located,
                            std::map<uint32_t, std::vector<uint8_t>>& overlay) {
    std::ifstream ini(folder / "native.ini");
    if (!ini) return;
    std::map<std::string, std::string> values;
    for (std::string line; std::getline(ini, line);) {
        line = line.substr(0, line.find('#'));
        const auto equal = line.find('=');
        if (equal != std::string::npos) values[trim(line.substr(0, equal))] = trim(line.substr(equal + 1));
    }
    if (values["format"] != "1" || values["target"] != target) return;
    std::vector<std::string> codes;
    std::set<std::string> unique;
    std::stringstream supplied(values["outfits"]);
    for (std::string code; std::getline(supplied, code, ',');) {
        code = trim(code);
        if (code.size() != 3 || !std::all_of(code.begin(), code.end(), [](char c) {
                return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'); }) || fighter_id(code) ||
            !unique.insert(code).second) return;
        for (const auto& added : g_added) {
            if (!added.active) continue;
            if (added.code == code || std::any_of(added.outfits.begin(), added.outfits.end(),
                [&](const Outfit& outfit) { return outfit.code == code; })) return;
        }
        for (const auto& [owner, native] : g_native)
            if (std::any_of(native.fighter.outfits.begin(), native.fighter.outfits.end(),
                [&](const Outfit& outfit) { return outfit.code == code; })) return;
        codes.push_back(code);
    }
    const auto id = fighter_id(target);
    if (!id || codes.empty() || codes.size() > 64) return;
    const auto row = motion_row(*id);
    if (!row) return;
    const uint32_t list = load(kCostumeLists + 8 * *id), count = load(kCostumeLists + 8 * *id + 4);
    if (count == 0 || count >= 9 || !list) return;
    auto previews = read_file(folder / "art/costumes.nut");
    if (!previews || previews->size() < 8 || std::memcmp(previews->data(), "NTP3", 4) != 0 ||
        ((uint32_t((*previews)[6]) << 8) | (*previews)[7]) != count + codes.size()) return;
    const auto previous = g_native.find(*id);
    const size_t previous_count = previous == g_native.end() ? 0 : previous->second.fighter.outfits.size();
    if (previous_count + codes.size() > 64) return;
    std::map<uint32_t, uint32_t> original_parts, original_textures;
    if (values["source"] == "wiiu-swimsuits") {
        std::ifstream registry(folder / "registry.ini");
        if (!registry) return;
        for (std::string line; std::getline(registry, line);) {
            const auto equal = line.find('=');
            if (equal == std::string::npos) return;
            const std::string name = trim(line.substr(0, equal));
            try {
                size_t used = 0;
                const std::string value = trim(line.substr(equal + 1));
                const auto key = std::stoul(value, &used, 16);
                if (used != value.size() || key > 0xFFFFFFFFul) return;
                if (name.rfind("part.", 0) == 0) {
                    const auto kind = std::stoul(name.substr(5));
                    if (kind != 7 && kind != 8 && kind != 9 && kind != 10 && kind != 11 && kind != 12 && kind != 13 && kind != 15) return;
                    if (!original_parts.emplace(kind, static_cast<uint32_t>(key)).second) return;
                } else if (name.rfind("texture.", 0) == 0) {
                    const auto index = std::stoul(name.substr(8));
                    if (index >= 20 || !original_textures.emplace(index, static_cast<uint32_t>(key)).second) return;
                } else return;
            } catch (const std::exception&) { return; }
        }
        if (original_parts.size() != 8 || original_textures.size() != 20) return;
    }
    // A supplemental pack carries the original previews plus only its own extras.
    // Append those extras after any existing Tekken 7 imports for this fighter.
    const uint32_t preview_key = key_of("native/" + target + "/art/costumes.nut");
    if (previous_count) {
        const auto old = overlay.find(preview_key);
        if (old == overlay.end()) return;
        auto existing = archive::unpack(old->second, preview_key);
        if (!existing) return;
        size_t at = 16;
        for (uint32_t i = 0; i < count; ++i) {
            if (at + 4 > previews->size()) return;
            const uint32_t size = uint32_t((*previews)[at]) << 24 | uint32_t((*previews)[at+1]) << 16 |
                                  uint32_t((*previews)[at+2]) << 8 | (*previews)[at+3];
            if (size < 16 || size > previews->size() - at) return;
            at += size;
        }
        std::vector<uint8_t> extras(previews->begin(), previews->begin() + 16);
        extras.insert(extras.end(), previews->begin() + static_cast<std::ptrdiff_t>(at), previews->end());
        extras[6] = static_cast<uint8_t>(codes.size() >> 8);
        extras[7] = static_cast<uint8_t>(codes.size());
        previews = with_textures(std::move(*existing), extras);
        if (!previews) return;
    }
    std::error_code ec;
    for (const auto& code : codes) {
        for (const char* suffix : {".nud", ".nut", ".bon", ".xml", ".mop"})
            if (!fs::is_regular_file(folder / (code + suffix), ec)) return;
    }
    std::map<uint32_t, std::vector<uint8_t>> entries;
    for (const auto& item : fs::recursive_directory_iterator(folder, ec)) {
        if (!item.is_regular_file() || item.is_symlink()) continue;
        const std::string name = fs::relative(item.path(), folder).generic_string();
        if (name == "native.ini" || name == "presets.json") continue;
        const bool preview = name == "art/costumes.nut";
        const auto owner = std::find_if(codes.begin(), codes.end(), [&](const std::string& code) {
            return name.rfind(code + ".", 0) == 0 || name.rfind(code + "/alo/", 0) == 0;
        });
        if (!preview && owner == codes.end()) continue;
        const auto bytes = read_file(item.path());
        if (!bytes) return;
        const uint32_t key = preview ? preview_key : key_of(name);
        const uint32_t donor_key = preview ? load(kCostumePreviews + 4 * *id) : key_of(target + name.substr(3));
        uint8_t flags[8] = {};
        if (const auto donor = title_entry(located, donor_key))
            std::copy(donor->second.begin(), donor->second.end(), flags);
        entries[key] = archive::pack(preview ? *previews : *bytes, key, flags);
    }
    // Commit all native fighters together. Rebuilding a growing archive for
    // each profile repeatedly copies every previously prepared model/texture.
    for (const auto& [key, bytes] : entries) if (key != preview_key && overlay.contains(key)) return;
    for (auto& [key, bytes] : entries) overlay.insert_or_assign(key, std::move(bytes));
    NativeCostumes native = previous == g_native.end() ? NativeCostumes{} : previous->second;
    native.fighter.active = true;
    native.fighter.id = *id;
    native.fighter.row = *row;
    native.fighter.code = target;
    native.fighter.code_string = load(kCodes + 4 * *id);
    native.native_count = count;
    native.count = count + static_cast<uint32_t>(outfit_menu::NativePage{count, previous_count + codes.size()}.visible());
    native.entries = system_alloc(8 * native.count);
    native.key = preview_key;
    std::memcpy(guest_pointer(native.entries), guest_pointer(list), count * 8);
    // Extra bodies use costume 1's native equipment recipe, with their own empty-part XML.
    for (size_t i = 0; i < codes.size(); ++i) {
        const uint32_t registry_id = 0x20000 + static_cast<uint32_t>(g_native_ids.size());
        native.fighter.outfits.push_back({codes[i], registry_id, guest_string(codes[i])});
        g_native_ids[registry_id] = *id;
        if (!original_parts.empty()) {
            g_original_part_keys[codes[i]] = original_parts;
            g_original_texture_keys[codes[i]] = original_textures;
        }
    }
    for (uint32_t i = count; i < native.count; ++i)
        std::memcpy(guest_pointer(native.entries + 8 * i), guest_pointer(list), 8);
    g_native[*id] = std::move(native);
    if (values["source"] == "wiiu-swimsuits")
        std::fprintf(stderr, "ttt2: Wii U swimsuits v1: %s: %zu presets appended after %zu imported outfits\n", target.c_str(), codes.size(), previous_count);
    std::fprintf(stderr, "ttt2: native roster costumes v2: %s: %zu T7 presets; %u native costumes and five custom slots retained\n", target.c_str(), codes.size(), count);
}

// Native costume targets, including the Kunimitsu swimsuit experiment.
void prepare_native_costumes(const fs::path& directory) {
    g_native.clear();
    g_original_part_keys.clear();
    g_original_texture_keys.clear();
    g_native_ids.clear();
    g_native_choosers.clear();
    std::vector<std::string> targets;
    std::error_code ec;
    for (const char* target : {"pau", "law", "yos", "xia", "ask", "jin", "dvj", "lil", "bob", "dra", "bry", "jac", "jul", "kaz", "hei", "nin", "ann", "lar", "asa", "kin", "aki", "edd", "fen", "gan", "hwo", "kum", "pan", "lee", "leo", "lei", "mar", "mig", "ste", "zaf", "knm"}) {
        if (fs::is_regular_file(directory / "native" / target / "native.ini", ec)) targets.push_back(target);
    }
    std::vector<std::string> swimsuits;
    for (uint32_t id = 0; id < 63; ++id) {
        const char* target = reinterpret_cast<const char*>(guest_pointer(load(kCodes + 4 * id)));
        if (std::strlen(target) == 3 && fs::is_regular_file(directory / "swimsuits" / target / "native.ini", ec))
            swimsuits.emplace_back(target);
    }
    if (targets.empty() && swimsuits.empty()) return;
    // Native donors do not change during preparation; read the game's indexes once.
    const auto located = locate_entries();
    std::map<uint32_t, std::vector<uint8_t>> overlay;
    for (const auto& target : targets)
        prepare_native_costume(directory / "native" / target, target, located, overlay);
    for (const auto& target : swimsuits)
        prepare_native_costume(directory / "swimsuits" / target, target, located, overlay);
    if (overlay.empty()) return;
    if (vfs::set_archive_entries("content/hdd/data100", overlay)) {
        g_active = true;
    } else {
        g_native.clear();
        g_native_ids.clear();
        std::fprintf(stderr, "ttt2: native costumes: archive overlay failed; keeping original costumes\n");
    }
}

// Native loader records and identities are never virtualized. Substitute only
// the body code, remembering it by player slot for asynchronous recipe creation.
PPC_FUNC(sub_044BE1EC_orig);
bool load_native_costume(PPCContext& ctx, uint8_t* base) {
    const uint32_t record = ctx.r[5], slot = ctx.r[4];
    if (record >= 139) return false;
    const uint32_t id = load(kRecords + kRecordSize * record + kRecId);
    const auto found = g_native.find(id);
    if (found == g_native.end()) return false;
    const Added& fighter = found->second.fighter;
    const Outfit* selected = nullptr;
    if (slot < 4) {
        const uint32_t pick = g_native_picks[slot & 1][slot / 2];
        for (const auto& outfit : fighter.outfits) if (outfit.id == pick) selected = &outfit;
    }
    const uint32_t code_place = kCodes + 4 * id, old_code = load(code_place);
    const uint32_t code = selected ? selected->code_string : old_code;
    g_outfit_bodies.remember(slot, id, selected ? selected->id : 0);
    static std::map<std::pair<uint32_t, uint32_t>, uint32_t> requested;
    const auto key = std::make_pair(ctx.r[3], slot);
    const uint32_t state = ctx.r[3] + 28 + 56 * slot;
    const bool invalidate = slot < 5 && outfit_menu::needs_reload(requested[key], code,
        load8(state + 1) != 0, load(state + 12), record);
    if (invalidate) store(state + 12, 139);
    store(code_place, code);
    sub_044BE1EC_orig(ctx, base);
    store(code_place, old_code);
    if (slot < 5) {
        if (ctx.r[3]) {
            if (selected && requested[key] != code && std::getenv("TTT2_TRACE_ROSTER"))
                std::fprintf(stderr, "ttt2: native costume: slot %u accepted body %s (fighter %u, native row %u)\n",
                    slot, selected->code.c_str(), id, fighter.row);
            requested[key] = code;
        }
        else if (invalidate && !load8(state + 1)) store(state + 12, record);
    }
    return true;
}
