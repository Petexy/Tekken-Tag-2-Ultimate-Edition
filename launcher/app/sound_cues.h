#pragma once

// The launcher's sound cues (FEEDBACK F7): the places in the interface where a sound belongs. The App calls its
// hook (App::set_sound_hook) at each, only while Sound is on (the top band's Sound button); what is played (the
// game's own menu sounds read at run time from the installed game, or original fallbacks before it is installed)
// is the hook's business. No hook: no sound (the default).
//
//   Move           the focus moved (keys, pad or the pointer onto another item)
//   Accept         an item was activated (buttons, rows, a dialog's buttons)
//   Back           Back did something (closed the browser or a dialog, went Home)
//   TabSwitch      another top tab (Home, Fighters, Settings)
//   SectionSwitch  another section inside a screen (Settings' Display / Keyboard / Launcher)
//   Toggle         a value changed (a selector's Left/Right, a check box, Sound on/off)
//   Refuse         Accept on a disabled item (its why is shown)
//   DrillIn        an item opened its actions on the other half, which got the focus (FEEDBACK F4)
//   DrillOut       ... and Back (or a click on the locked half) returned
//   TaskDone       an install, update, uninstall or other task ended well
//   TaskFailed     ... ended with an error (not when it was cancelled)
//   Play           the game is being started

#include <functional>

namespace ttt2::app {

enum class Cue {
    Move,
    Accept,
    Back,
    TabSwitch,
    SectionSwitch,
    Toggle,
    Refuse,
    DrillIn,
    DrillOut,
    TaskDone,
    TaskFailed,
    Play,
};

using SoundHook = std::function<void(Cue)>;

inline const char* cue_name(Cue c) {
    static const char* const kNames[] = {"move",   "accept",   "back",      "tab",       "section",     "toggle",
                                         "refuse", "drill-in", "drill-out", "task-done", "task-failed", "play"};
    return kNames[static_cast<int>(c)];
}

} // namespace ttt2::app
