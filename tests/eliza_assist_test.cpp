#include "title/eliza_assist.h"
#include <cassert>
#include <initializer_list>
using cafe::title::eliza_assist::Session;
int main() {
    Session s;
    auto update = [&](const char* name, unsigned frame, unsigned recovery,
                      bool assault = true, unsigned partner = 1) {
        return s.update(true, true, assault, partner, name, frame, recovery);
    };
    // A late b+4 -> Glide entry remains possible beyond its frame-15 hit.
    assert(update("Vp_rk00B", 1, 45));
    assert(update("Vp_rk00B", 27, 45));
    assert(update("Vp_dash_EX", 1, 33));
    assert(update("Vp_dash_EX", 24, 33));
    assert(update("Vp_6rklk", 1, 46));
    assert(update("Vp_6rklk", 18, 46));
    // Selecting either finisher returns input ownership immediately;
    // neither its startup nor its hit animation may extend the session.
    assert(!update("Vp_66lklk", 1, 58));
    assert(!update("Vp_66lklk", 23, 58));
    assert(!update("Vp_66lklk_H", 1, 54));
    assert(!update("Vp_6rklk", 1, 19)); // cannot restart mid-string
    assert(update("Vp_dash_C", 1, 33));
    assert(update("Vp_6rklk", 18, 19));
    assert(!update("Vp_6rklkrk", 1, 50));
    // If no second kick was selected, return when its input window closes.
    assert(update("Vp_dash_C", 1, 33));
    assert(update("Vp_6rklk", 18, 19));
    assert(!update("Vp_6rklk", 19, 19));
    assert(!update("Jn_3lp00", 1, 30)); // next df+1 belongs to the main
    assert(update("Vp_dash_EX2", 1, 33));
    assert(!update("sDm_High", 1, 30)); // interruption releases immediately
    assert(!update("Vp_6rklk", 1, 46));
    assert(update("Vp_dash_EX", 1, 33));
    assert(!update("Co_StChgOutB", 1, 35));
    assert(update("Vp_rk00B", 1, 45));
    assert(!update("Vp_rk00B", 2, 45, false));
    assert(!s.update(false, true, true, 1, "Vp_dash_EX", 1, 33));
    assert(!s.update(true, false, true, 1, "Vp_dash_EX", 1, 33));
    assert(!s.update(true, true, true, 0, "Vp_dash_EX", 1, 33));
    assert(update("Vp_dash_EX", 1, 33));
    assert(!update("Vp_6rklk", 1, 46, true, 2)); // roster/partner changed
    assert(!update("Vp_rk00B", 0, 45));
    assert(!update("Vp_dash_EX", 1, 0));
    assert(!update("Vp_dash_EX", 1, 10000));
    // Timings follow the installed pack, including modified recovery.
    assert(update("Vp_rk00B", 45, 60));
    assert(!update("Vp_rk00B", 60, 60));
    // A deferred expiry releases on finisher selection, even when the
    // incoming move is still at frame 1 with many recovery frames left.
    for (const char* finisher : {"Vp_66lklk", "Vp_66lklk_H", "Vp_6rklkrk"}) {
        Session sequence;
        assert(sequence.update(true, true, true, 1, "Vp_dash_EX", 1, 33));
        assert(sequence.update(true, true, true, 1, "Vp_6rklk", 18, 19));
        assert(!sequence.update(true, true, true, 1, finisher, 1, 58));
        assert(!sequence.update(true, true, true, 1, finisher, 2, 58));
    }
    using cafe::title::eliza_assist::InputWindow;
    InputWindow input;
    input.add(0x2800, 0, 25, true); // Geese 2: restored motion capture
    input.add(0x182, 0, 25, false); // automatic special dispatch
    input.add(0x80, 0, 47, false);  // neutral recovery is irrelevant
    assert(input.buffered && input.control_end() == 26);
    Session geese;
    assert(geese.update_window(true, true, true, 1, 25, input.control_end(), true, false));
    InputWindow f1;
    f1.add(0x2800, 0, 34, true); // f+1 owns its fresh motion window
    assert(geese.update_window(true, true, true, 1, 1, f1.control_end(), true, false));
    assert(geese.update_window(true, true, true, 1, 34, f1.control_end(), true, false));
    // Committing a terminal special releases before its startup finishes.
    assert(!geese.update_window(true, true, true, 1, 1, 0, false, false));
    assert(!geese.update_window(true, true, true, 1, 2, 0, false, false));
    InputWindow shoryu;
    shoryu.add(0x182, 0x40000002, 22, false);
    shoryu.add(0x182, 0x40000008, 22, false);
    Session eliza;
    assert(eliza.update_window(true, true, true, 1, 22, shoryu.control_end(), true, false));
    assert(!eliza.update_window(true, true, true, 1, 23, shoryu.control_end(), true, false));
    // Ignore unbounded neutral input tables and unrelated property actions.
    InputWindow neutral;
    neutral.add(0x182, 0x40000001, 32767, false);
    neutral.add(0x2800, 0, 40, false);
    neutral.add(0x80, 0, 60, false);
    assert(!neutral.buffered && !neutral.control_end());
    assert(!eliza.update_window(false, true, true, 1, 1, 23, true, false));
    assert(!eliza.update_window(true, true, false, 1, 1, 23, true, false));
    assert(!eliza.update_window(true, false, true, 1, 1, 23, true, false));

    // 2 -> f+1 -> hcb+3 must not hand control back between the opening
    // rush and its automatic contact follow-up (the latter can super-cancel).
    Session jaei;
    assert(jaei.update_window(true, true, true, 1, 20, 26, true, false));
    assert(jaei.update_window(true, true, true, 1, 1, 35, true, false));
    const auto rush_end = cafe::title::eliza_assist::geese_contact_bridge("My_Jyaei_C", 29);
    assert(rush_end == 30);
    assert(jaei.update_window(true, true, true, 1, 1, rush_end, false, true));
    assert(jaei.update_window(true, true, true, 1, 22, rush_end, false, true));
    assert(jaei.update_window(true, true, true, 1, 1, 29, true, false)); // My_Jyaei_C2
    assert(jaei.update_window(true, true, true, 1, 28, 29, true, false));
    assert(!jaei.update_window(true, true, true, 1, 29, 29, true, false));
    Session whiff;
    assert(whiff.update_window(true, true, true, 1, 1, 35, true, false));
    assert(whiff.update_window(true, true, true, 1, 29, rush_end, false, true));
    assert(!whiff.update_window(true, true, true, 1, 30, rush_end, false, true));
    Session detached;
    assert(!detached.update_window(true, true, true, 1, 1, rush_end, false, true));
    assert(!cafe::title::eliza_assist::geese_contact_bridge("My_Jyaei_D", 29));
    assert(!cafe::title::eliza_assist::geese_contact_bridge("Vp_66lklk", 23));

    // Reina uses the same finite ownership windows as the existing 2D assists.
    using cafe::title::eliza_assist::supported;
    using cafe::title::eliza_assist::owns_move;
    assert(supported("rei") && supported("elz") && supported("mry"));
    assert(!supported("jun") && !supported("akm"));
    assert(owns_move("rei", "Zbr_sen_RK") && owns_move("rei", "Zbr_3LP"));
    assert(!owns_move("rei", "Ju_sKAM00_") && !owns_move("elz", "Zbr_3LP"));
    InputWindow reina_string;
    reina_string.add(0x182, 0x40000002, 20, false);
    Session reina;
    assert(reina.update_window(true, true, true, 7, 13, reina_string.control_end(), true, false));
    assert(reina.update_window(true, true, true, 7, 20, reina_string.control_end(), true, false));
    assert(!reina.update_window(true, true, true, 7, 21, reina_string.control_end(), true, false));
    assert(!reina.update_window(true, true, true, 7, 1, 0, false, false)); // committed SEN 4 releases control
    assert(!reina.update_window(true, false, true, 7, 1, 21, true, false));
    assert(!reina.update_window(true, true, false, 7, 1, 21, true, false));

    using cafe::title::eliza_assist::reina_stance_window;
    assert(reina_stance_window("Zbr_6RPLK", 64, 0, 0x182, 22) == 22);
    assert(!reina_stance_window("My_Jyaei_C", 64, 0, 0x182, 22));
    assert(!reina_stance_window("Zbr_6RPLK", 0, 0, 0x182, 22));
    assert(!reina_stance_window("Zbr_6RPLK", 64, 4, 0x182, 22));
    assert(!reina_stance_window("Zbr_6RPLK", 64, 0, 0x2800, 22));
    assert(!reina_stance_window("Zbr_6RPLK", 64, 0, 0x182, 32767));
    Session sentai;
    assert(sentai.update_window(true, true, true, 1, 1, 27, true, false)); // f+2 -> 3
    assert(sentai.update_window(true, true, true, 1, 22, 23, true, false)); // f+2,3 -> SEN
    assert(sentai.update_window(true, true, true, 1, 24, 25, true, false)); // SEN -> 3+4
    assert(!sentai.update_window(true, true, true, 1, 1, 0, false, false)); // commit; native finisher

    // Every directional Sentai route identified in the installed Reina pack.
    assert(reina_stance_window("Zbr_3LP", 64, 0, 0x182, 16) == 16); // d/f+1
    assert(reina_stance_window("Zbr_66RP", 64, 0, 0x182, 17) == 17); // f,f+2
    assert(reina_stance_window("Zbr_4LPLPLK", 64, 0, 0x182, 21) == 21); // b+1,1,3
    assert(reina_stance_window("Zbr_LPLPRP", 1006, 0, 0x182, 20) == 20); // conditional 1,1,2
    assert(reina_stance_window("Zbr_#1752", 64, 0, 0x182, 17) == 17); // d/f+1 variant
    assert(reina_stance_window("Zbr_#2248", 64, 0, 0x182, 16) == 16); // d/f+1 variant
    assert(!reina_stance_window("Zbr_66RP", 0x8000, 0, 0x182, 17)); // neutral/end
    assert(!reina_stance_window("Zbr_66RP", 0x800b, 0, 0x182, 17)); // group
    assert(!reina_stance_window("Zbr_66RP", 64, 0, 0x182, 0));
    assert(!reina_stance_window("Zbr_66RP", 64, 0, 0x182, 180));
    Session df1_sentai;
    assert(df1_sentai.update_window(true,true,true,1,1,21,true,false));
    assert(df1_sentai.update_window(true,true,true,1,17,18,true,false)); // airborne variant
    assert(df1_sentai.update_window(true,true,true,1,1,23,true,false)); // Sentai
    assert(!df1_sentai.update_window(true,true,true,1,1,0,false,false)); // finisher committed

    // Noctis: preserve selection across the hit-confirmed float entry, then
    // both buffered air punches. All terminal 1 / 1+2 / third-2 attacks release.
    using cafe::title::eliza_assist::noctis_contact_bridge;
    assert(supported("mrz"));
    assert(owns_move("mrz","Mz_rk00") && owns_move("mrz","Mz_rk01_JUMP"));
    assert(owns_move("mrz","Mz_jprp01F") && owns_move("mrz","Mz_jprp02"));
    for (const char* terminal : {"Mz_jplp00F","Mz_jpWPF","Mz_rk01jpWPF","Mz_jprp03"})
        assert(!owns_move("mrz",terminal));
    assert(!owns_move("mrz","Mz_rp00F") && !owns_move("elz","Mz_jprp02"));
    assert(noctis_contact_bridge("Mz_rk00y",0,0,0x182,13)==13);
    assert(noctis_contact_bridge("Mz_rk01",0,0,0x401,27)==27);
    assert(noctis_contact_bridge("Mz_rk01y",0,0,0x880,35)==35);
    assert(!noctis_contact_bridge("Mz_rk01y",0,0,0x880,32767));
    assert(!noctis_contact_bridge("Mz_rk01",0x800b,0,0x401,27));
    assert(!noctis_contact_bridge("Mz_rk01",0,2,0x401,27));
    assert(!noctis_contact_bridge("Mz_jprp03",0,0,0x401,27));
    Session noctis;
    assert(noctis.update_window(true,true,true,1,1,14,true,false)); // opening kick input
    assert(noctis.update_window(true,true,true,1,13,14,false,true)); // buffered second hit
    assert(noctis.update_window(true,true,true,1,27,28,false,true)); // air contact
    assert(noctis.update_window(true,true,true,1,35,36,false,true)); // automatic jump
    assert(noctis.update_window(true,true,true,1,42,43,true,false)); // select air 1/2/1+2
    assert(noctis.update_window(true,true,true,1,15,16,true,false)); // 2 -> 2
    assert(noctis.update_window(true,true,true,1,17,18,true,false)); // 2 -> third 2
    assert(!noctis.update_window(true,true,true,1,1,0,false,false)); // committed finisher
    Session missed_float;
    assert(missed_float.update_window(true,true,true,1,1,14,true,false));
    assert(missed_float.update_window(true,true,true,1,27,28,false,true));
    assert(!missed_float.update_window(true,true,true,1,28,28,false,true)); // whiff expires
    Session detached_float;
    assert(!detached_float.update_window(true,true,true,1,1,36,false,true));
    assert(!noctis.update_window(true,true,false,1,1,43,true,false));
    assert(!noctis.update_window(true,false,true,1,1,43,true,false));

    // Only the partner who came in for the Tag Assault holds a session; the
    // fighter whose bound started it (player+7820) has the pad back after the
    // native expiry and must never run that expiry on itself (#32, #96).
    using cafe::title::eliza_assist::holds_sessions;
    assert(holds_sessions(supported("mry"), false));  // Geese came in
    assert(!holds_sessions(supported("mry"), true));  // Geese started it
    assert(!holds_sessions(supported("elz"), true) && !holds_sessions(supported("rei"), true) &&
           !holds_sessions(supported("mrz"), true));
    assert(!holds_sessions(supported("mrx"), false)); // Akuma: no sessions at all
}
