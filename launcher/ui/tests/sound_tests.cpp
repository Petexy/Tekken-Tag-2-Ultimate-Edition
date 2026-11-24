// The launcher's sounds (ttt2ui/sound.h) without a speaker: SDL's dummy audio driver only (set here too), the game's
// sounds from a made-up install (launcher/core/game_sounds_fixture.h). Argument: a scratch folder (the build folder).
#include <SDL3/SDL.h>

#include <chrono>
#include <cmath>
#include <cstdio>
#include <functional>
#include <string>
#include <thread>
#include <vector>

#include "game_sounds_fixture.h"
#include "ttt2ui/anim.h"
#include "ttt2ui/sound.h"

using namespace ttt2::ui;
namespace gs = launcher::game_sounds;
namespace fx = game_sounds_fixture;
namespace fs = std::filesystem;

namespace {

int g_failed = 0, g_checks = 0;
const char* g_current = "";
void check(bool ok, const std::string& what, int line) {
    ++g_checks;
    if (!ok) {
        ++g_failed;
        std::printf("FAIL %s (line %d): %s\n", g_current, line, what.c_str());
    }
}
#define CHECK(c) check((c), #c, __LINE__)

fs::path g_scratch;

Cue cue_at(int i) { return static_cast<Cue>(i); }

// Mixes `frames` frames of what plays.
std::vector<float> mixed(Sounds& s, int frames) {
    std::vector<float> out(2 * std::size_t(frames));
    s.mix(out.data(), frames);
    return out;
}

void test_own_sounds() {
    for (int i = 0; i < kCueCount; ++i) {
        const auto& level = gs::cue_levels()[std::size_t(i)];
        SoundClip a = synthesize(cue_at(i)), b = synthesize(cue_at(i));
        std::string name = cue_name(cue_at(i));
        check(!a.empty(), name + " is made", __LINE__);
        check(a.samples == b.samples, name + " is the same every time", __LINE__);
        check(a.seconds() <= level.max_seconds + 1e-3, name + " is short enough", __LINE__);
        check(gs::peak(a) <= gs::kPeakLimit + 1e-5f, name + " is not clipped", __LINE__);
        float loud = gs::loudness_db(a);
        check(std::fabs(loud - level.loudness_db) < 0.6f || gs::peak(a) >= gs::kPeakLimit - 1e-4f,
              name + " at its level (" + std::to_string(loud) + " dB)", __LINE__);
    }
    CHECK(synthesize(Cue::Move).seconds() <= 0.1); // a cursor tick, it repeats
    CHECK(synthesize(Cue::Play).seconds() >= 0.6); // the strong one
    CHECK(gs::loudness_db(synthesize(Cue::Play)) > gs::loudness_db(synthesize(Cue::Accept)));
    CHECK(gs::loudness_db(synthesize(Cue::Accept)) > gs::loudness_db(synthesize(Cue::Move)));
    // The tab whoosh moves across: its two sides differ.
    SoundClip tab = synthesize(Cue::TabSwitch);
    double diff = 0;
    for (std::size_t i = 0; i < tab.frames(); ++i) diff += std::fabs(tab.samples[2 * i] - tab.samples[2 * i + 1]);
    CHECK(diff / double(tab.frames()) > 0.005);
    CHECK(std::string(cue_name(Cue::Play)) == "play" && std::string(cue_name(Cue::TabSwitch)) == "tab_switch");
}

void test_mixing_and_limits() {
    ManualClock clock(10);
    Sounds s(&clock);
    s.set_output(false); // (no device: mix() is the device here)
    s.play(Cue::Accept);
    CHECK(s.voices() == 0); // off by default
    s.set_enabled(true);
    CHECK(s.source() == Sounds::Source::Own);
    s.play(Cue::Accept);
    CHECK(s.voices() == 1);
    auto accept = s.clip(Cue::Accept);
    auto out = mixed(s, 256);
    bool same = true;
    for (std::size_t i = 0; i < out.size(); ++i)
        if (std::fabs(accept->samples[i]) < 0.79f) same = same && std::fabs(out[i] - accept->samples[i]) < 1e-6f;
    CHECK(same);
    // The same cue again at once (one press seen by two devices): one sound. Later: two, mixed.
    s.play(Cue::Accept);
    CHECK(s.voices() == 1);
    clock.advance(0.05);
    s.play(Cue::Back);
    CHECK(s.voices() == 2);
    auto back = s.clip(Cue::Back);
    out = mixed(s, 64);
    same = true;
    for (std::size_t i = 0; i < out.size(); ++i) {
        float want = accept->samples[512 + i] + back->samples[i];
        if (std::fabs(want) < 0.79f) same = same && std::fabs(out[i] - want) < 1e-5f;
    }
    CHECK(same);

    // A held direction: cursor sounds at most every 45 ms, and a new one cuts the last one short.
    Sounds m(&clock);
    m.set_output(false);
    m.set_enabled(true);
    m.play(Cue::Move);
    clock.advance(0.02);
    m.play(Cue::Move);
    CHECK(m.voices() == 1);
    clock.advance(0.03);
    m.play(Cue::Move);
    CHECK(m.voices() == 2);
    mixed(m, gs::kRate / 200 + 2); // the fade of the cut one
    CHECK(m.voices() == 1);

    // Many at once: never more than a few sounding; the oldest go.
    Sounds many(&clock);
    many.set_output(false);
    many.set_enabled(true);
    for (int i = 0; i < 40; ++i) {
        clock.advance(0.031);
        many.play(cue_at(i % kCueCount));
    }
    CHECK(many.voices() <= 12);
    mixed(many, gs::kRate / 100);
    CHECK(many.voices() <= 7);
    // Everything played to its end: silence, nothing left.
    for (int k = 0; k < 200 && many.voices(); ++k) mixed(many, 2048);
    CHECK(many.voices() == 0);
    out = mixed(many, 128);
    float top = 0;
    for (float v : out) top = std::max(top, std::fabs(v));
    CHECK(top == 0.f);

    // Off: what plays stops, nothing new starts.
    s.set_enabled(false);
    CHECK(s.voices() == 0);
    s.play(Cue::Play);
    CHECK(s.voices() == 0);
}

void test_device() {
    // (Never a speaker: the dummy driver, whatever the environment says.)
    SDL_SetHintWithPriority(SDL_HINT_AUDIO_DRIVER, "dummy", SDL_HINT_OVERRIDE);
    ManualClock clock(100);
    {
        Sounds s(&clock);
        s.set_game_folder({});
        s.tick();
        CHECK(!s.device_open());
        s.play(Cue::Move); // off: nothing opened
        CHECK(!s.device_open());
        s.set_enabled(true);
        s.tick();
        CHECK(!s.device_open()); // on, but nothing played yet
        CHECK(!SDL_WasInit(SDL_INIT_AUDIO));
        s.play(Cue::Move);
        if (!s.device_open()) {
            std::printf("SKIP device: SDL's dummy audio driver did not open (%s)\n", SDL_GetError());
            return;
        }
        clock.advance(1.0);
        s.tick();
        CHECK(s.device_open()); // a second after the sound: still open
        for (int i = 0; i < 100 && s.voices(); ++i) std::this_thread::sleep_for(std::chrono::milliseconds(10));
        CHECK(s.voices() == 0); // (the dummy device played it)
        clock.advance(1.2);
        s.tick();
        CHECK(!s.device_open()); // ~2 s of silence: closed
        s.play(Cue::Accept);
        CHECK(s.device_open()); // opened again for the next sound
        s.set_enabled(false);
        CHECK(!s.device_open()); // off: closed at once
        CHECK(!SDL_WasInit(SDL_INIT_AUDIO));
        s.set_enabled(true);
        s.play(Cue::Back);
        CHECK(s.device_open());
    }
    CHECK(!SDL_WasInit(SDL_INIT_AUDIO)); // (gone with the Sounds)
}

void test_game_sounds() {
    fs::path root = g_scratch / "sound_tests_install";
    fx::make_install(root);
    gs::Loaded direct = gs::load_cues(root);
    CHECK(direct.found() == kCueCount);

    ManualClock clock(5);
    Sounds s(&clock);
    s.set_output(false);
    s.set_game_folder(root);
    CHECK(s.source() == Sounds::Source::Own); // off: nothing read
    s.set_enabled(true);
    CHECK(s.source() == Sounds::Source::Loading);
    CHECK(s.wait_loaded(20));
    s.tick();
    CHECK(s.source() == Sounds::Source::Game);
    check(s.status().find("game's sounds") != std::string::npos, "status: " + s.status(), __LINE__);
    for (int i = 0; i < kCueCount; ++i)
        check(s.clip(cue_at(i))->samples == direct.clips[std::size_t(i)].samples,
              std::string(cue_name(cue_at(i))) + " is the game's", __LINE__);
    s.play(Cue::Toggle);
    CHECK(s.voices() == 1);

    // No game any more: the launcher's own again.
    s.set_game_folder({});
    CHECK(s.source() == Sounds::Source::Own);
    CHECK(s.clip(Cue::Move)->samples == synthesize(Cue::Move).samples);

    // A game whose archives cannot be read: the launcher's own, and why.
    fs::path broken = g_scratch / "sound_tests_broken";
    std::error_code ec;
    fs::remove_all(broken, ec);
    fx::write_file(broken / "game" / "content" / "hdd" / "data000.ofs", fx::Bytes(64, 0xAB));
    s.set_game_folder(broken);
    CHECK(s.wait_loaded(20));
    s.tick();
    CHECK(s.source() == Sounds::Source::Own);
    CHECK(s.status().find("own") != std::string::npos);
    CHECK(s.clip(Cue::Play)->samples == synthesize(Cue::Play).samples);

    // Several folders in a row (the install moving): only the last one's sounds are taken.
    s.set_game_folder(root);
    s.set_game_folder(broken);
    s.set_game_folder(root);
    CHECK(s.wait_loaded(20));
    s.tick();
    CHECK(s.source() == Sounds::Source::Game);

    // The demo's WAV files: 12 own, and 12 of the game's with a game.
    fs::path wavs = g_scratch / "sound_tests_wav";
    fs::remove_all(wavs, ec);
    CHECK(write_sound_wavs(wavs, {}) == kCueCount);
    CHECK(fs::exists(wavs / "01_move_own.wav") && fs::exists(wavs / "12_play_own.wav"));
    fs::remove_all(wavs, ec);
    CHECK(write_sound_wavs(wavs, root) == 2 * kCueCount);
    CHECK(fs::file_size(wavs / "12_play_game.wav", ec) == 44 + direct.clips[11].samples.size() * 2);
    fs::remove_all(wavs, ec);
    fs::remove_all(root, ec);
    fs::remove_all(broken, ec);
}

} // namespace

int main(int argc, char** argv) {
    SDL_SetHintWithPriority(SDL_HINT_AUDIO_DRIVER, "dummy", SDL_HINT_OVERRIDE);
    g_scratch = argc > 1 ? fs::path(argv[1]) : fs::temp_directory_path();
    const std::pair<const char*, std::function<void()>> tests[] = {
        {"own_sounds", test_own_sounds},
        {"mixing_and_limits", test_mixing_and_limits},
        {"device", test_device},
        {"game_sounds", test_game_sounds},
    };
    for (const auto& [name, run] : tests) {
        g_current = name;
        run();
    }
    std::printf("%d checks, %d failed\n", g_checks, g_failed);
    SDL_Quit();
    return g_failed ? 1 : 0;
}
