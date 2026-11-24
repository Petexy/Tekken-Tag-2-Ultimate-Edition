// The launcher's sounds: Tekken Tag Tournament 2's own menu sounds, read at run time from the player's installed game
// (launcher/core/game_sounds.h: never shipped, never in the repository), and until the game is installed (or when
// reading it fails) the launcher's own sounds made in code (sound_synth.cpp: short, punchy, metallic, whooshes).
//
// The device: opened on the first sound (never before: --version, --screenshot and tests that do not play stay
// silent and open nothing; tests run with SDL_AUDIO_DRIVER=dummy), closed after ~2 s of silence (tick()). Sounds
// overlap (mixed, at most a few at once); a cue repeated faster than it can be heard (a held direction, the mouse
// over a row of tiles) is limited, and a new cursor sound cuts the old one short. Every cue has its own loudness
// (game_sounds::cue_levels()), the same for the game's and the launcher's sounds. Reduce motion does not mute.
#pragma once

#include <filesystem>
#include <memory>
#include <string>

#include "game_sounds.h"

namespace ttt2::ui {

class Clock;

// The app's copy is launcher/app/sound_cues.h (ttt2::app::Cue, the same names in the same order).
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
    Play
};
inline constexpr int kCueCount = 12;
static_assert(kCueCount == launcher::game_sounds::kCueCount);
const char* cue_name(Cue cue); // "move", "accept", ...

using SoundClip = launcher::game_sounds::Clip; // 48 kHz, stereo, interleaved float

class Sounds {
public:
    // `clock`: the time play() and tick() go by (seconds; nullptr: SDL's). Tests pass a ManualClock.
    explicit Sounds(const Clock* clock = nullptr);
    ~Sounds();
    Sounds(const Sounds&) = delete;
    Sounds& operator=(const Sounds&) = delete;

    // Off by default (the launcher's setting). Off: nothing plays and the device is closed at once.
    void set_enabled(bool on);
    bool enabled() const;
    // The installed game's folder (the install folder, its game/ folder, or empty: none). Its sounds are read in the
    // background once sounds are on; until they are read (or when they cannot be) the launcher's own play.
    void set_game_folder(const std::filesystem::path& installed_game_root_or_empty);
    void play(Cue cue);
    // Every frame (or at least a few times a second): takes the game's sounds once read, closes the device after
    // ~2 s of silence.
    void tick();

    // ---- beyond the contract: the demo, tests and diagnostics ----
    enum class Source { Own, Loading, Game };
    Source source() const;
    std::string status() const; // one line: where the sounds come from, or why not the game's
    bool device_open() const;
    int voices() const; // sounds playing now
    // Waits (at most `seconds`) for the game's sounds being read; true when none are being read any more.
    bool wait_loaded(double seconds);
    // What play(cue) plays now.
    std::shared_ptr<const SoundClip> clip(Cue cue);
    // When false no device is ever opened: play() still mixes into voices that mix() takes (tests).
    void set_output(bool allowed);
    // The audio device's work: the next `frames` frames of every playing sound, mixed (interleaved stereo).
    void mix(float* out, int frames);

    struct Impl;

private:
    std::unique_ptr<Impl> impl_;
};

// The launcher's own sound for a cue (made in code, finished to the cue's level and length).
SoundClip synthesize(Cue cue);

// Writes every cue's sounds as 16-bit WAV files into `dir`: <n>_<cue>_own.wav and, when `game_root` holds the game,
// <n>_<cue>_game.wav. The number of files written; what failed on stderr.
int write_sound_wavs(const std::filesystem::path& dir, const std::filesystem::path& game_root);

} // namespace ttt2::ui
