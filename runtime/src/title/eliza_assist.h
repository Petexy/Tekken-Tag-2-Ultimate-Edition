#pragma once
#include <cstdint>
#include <string_view>

namespace cafe::title::eliza_assist {
// Opt in only the imported fighters with verified string/stance ownership.
inline bool noctis_air_sequence(std::string_view name) {
    return name == "Mz_rk00" || name == "Mz_rk00y" || name == "Mz_rk01" ||
           name == "Mz_rk01y" || name == "Mz_rk01_JUMP" ||
           name == "Mz_sJUMP_00F" || name == "Mz_sJUMPr00F" ||
           name == "Mz_jprp01" || name == "Mz_jprp01F" || name == "Mz_jprp02";
}
inline bool supported(std::string_view code) {
    return code == "elz" || code == "mry" || code == "rei" || code == "mrz";
}
inline bool owns_move(std::string_view code, std::string_view name) {
    return code == "elz" ? name.starts_with("Vp_") :
           code == "mry" ? name.starts_with("My_") :
           code == "rei" ? name.starts_with("Zbr_") :
           code == "mrz" && noctis_air_sequence(name);
}
// Reina's installed moves include several finite directional stance entries,
// including alternate d/f+1 rows used against airborne opponents. Protect all
// of those input windows, rather than maintaining a single-move allowlist.
// The caller already restricts this to Reina. Preserve native requirements,
// timing and destinations; never extend neutral/group/automatic recovery rows.
inline uint32_t reina_stance_window(std::string_view name, uint32_t direction,
                                    uint32_t button, uint32_t mode, uint32_t end) {
    return name.starts_with("Zbr_") && direction && direction < 0x8000 &&
           !button && mode == 0x182 && end && end < 180 ? end : 0;
}
// Protect stance selection and the first kick's string input window.
// Committed finishers run through native inactive assist handling, allowing
// the main fighter to act while their animations are still playing.
inline bool entry(std::string_view name) {
    return name == "Vp_rk00B" || name == "Vp_dash_C" ||
           name == "Vp_dash_EX" || name == "Vp_dash_EX2";
}
inline bool continuation(std::string_view name) {
    return name == "Vp_6rklk";
}
// Native 041CE0B0 consumes a positive countdown; 1 schedules its next tick.
inline constexpr uint32_t kRetryExpiryNextFrame = 1;
// TTT2 marks the fighter whose bound started the Tag Assault: the property
// 0x8256 (only in the starter's ...DA twins) runs sub_04E19DE4(player, 1),
// which sets player+7820 on that fighter only (+7816, "in a Tag Assault", goes
// on both; nothing is set when +7816 is already 1); the assault's end,
// sub_04E19DE4(player, 0), clears both on both. The native expiry
// (sub_04E187B8) belongs to the partner who came in: it hands the pad back to
// the starter and sends the caller out after its move. So only that partner
// may hold a session. The starter has the pad back after the expiry while
// +7816 is still set; a session of its own would end by running the expiry on
// the starter, a tag out nobody pressed (issues #32, #96).
inline bool holds_sessions(bool supported_fighter, bool started_assault) {
    return supported_fighter && !started_assault;
}
// Installed input-only captures use 0x2800 and write the special buffer.
// Ordinary finite string inputs use 0x182/0x183. Neither automatic hit
// transitions nor a move's neutral-recovery row extend control.
struct InputWindow {
    uint32_t last = 0;
    bool buffered = false;
    uint32_t bridge_last = 0;
    void add(uint32_t mode, uint32_t button, uint32_t end, bool special_capture) {
        if (!end || end >= 180) return;
        if (mode == 0x2800 && special_capture) buffered = true;
        else if (!button || (mode != 0x182 && mode != 0x183)) return;
        if (end > last) last = end;
    }
    uint32_t control_end() const { return last ? last + 1 : 0; }
    uint32_t bridge_end() const { return bridge_last ? bridge_last + 1 : 0; }
};
// Jaei Ken's opening rush has no player-selected follow-up. Contact
// automatically enters My_Jyaei_C2 during its active interval. Preserve
// an existing assist session across that gap, never start one mid-rush.
inline uint32_t geese_contact_bridge(std::string_view name, uint32_t last_active) {
    return name == "My_Jyaei_C" && last_active && last_active < 180 ? last_active + 1 : 0;
}
// These contact-gated automatic stages connect the selected kick string to
// its aerial input window. Continue an existing session; never start one here.
// Read their actual finite windows from the installed pack; leave guards intact.
inline uint32_t noctis_contact_bridge(std::string_view name, uint32_t direction,
                                      uint32_t button, uint32_t mode, uint32_t end) {
    if (button || direction >= 0x8000 || !end || end >= 180) return 0;
    return ((name == "Mz_rk00y" && mode == 0x182) ||
            (name == "Mz_rk01" && mode == 0x401) ||
            (name == "Mz_rk01y" && mode == 0x880)) ? end : 0;
}
struct Session {
    uint32_t partner = 0;
    bool active = false;
    bool update_window(bool supported, bool human, bool assault,
                       uint32_t current_partner, uint32_t frame,
                       uint32_t control_end, bool starts, bool continues) {
        if (!supported || !human || !assault || !current_partner || !frame ||
            !control_end || control_end > 180 || frame >= control_end ||
            (!starts && !continues)) {
            *this = {};
            return false;
        }
        if (partner && partner != current_partner) *this = {};
        if (starts) { active = true; partner = current_partner; }
        return active;
    }
    bool update(bool eliza, bool human, bool assault, uint32_t current_partner,
                std::string_view name, uint32_t frame, uint32_t recovery) {
        return update_window(eliza, human, assault, current_partner, frame,
                             recovery, entry(name), continuation(name));
    }
};
} // namespace cafe::title::eliza_assist
