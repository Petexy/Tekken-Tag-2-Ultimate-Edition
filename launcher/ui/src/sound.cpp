// The launcher's sounds (sound.h): the game's own or the launcher's, mixed into one lazily opened SDL audio stream.
#include "ttt2ui/sound.h"

#include <SDL3/SDL.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <mutex>
#include <thread>
#include <vector>

#include "ttt2ui/anim.h"

namespace ttt2::ui {

namespace gs = launcher::game_sounds;

namespace {

constexpr double kCloseAfter = 2.0;           // seconds of silence before the device is closed
constexpr double kRetryOpenAfter = 5.0;       // after a device could not be opened
constexpr std::size_t kMaxVoices = 6;         // sounds at once (the oldest is faded out for a new one)
constexpr int kChokeFrames = gs::kRate / 200; // 5 ms: how fast a cut-off sound fades
constexpr double kSameCueGap = 0.030;         // the same cue again within this: one sound (two devices, one press)
constexpr double kMoveGap = 0.045;            // cursor sounds at most ~22 a second (a held direction, a mouse sweep)

// Cues of one group cut each other short (a new cursor sound ends the last one): -1 none.
int choke_group(Cue c) {
    switch (c) {
    case Cue::Move: return 0;
    case Cue::TabSwitch:
    case Cue::SectionSwitch: return 1;
    case Cue::Toggle: return 2;
    default: return -1;
    }
}

struct Voice {
    std::shared_ptr<const SoundClip> clip;
    std::size_t pos = 0;
    int group = -1;
    int fade = -1; // frames left of a fade out, -1: none
};

// Work done on a thread of its own once sounds are on (its result is taken by tick(), play() or clip()): the game's
// sounds read, or the launcher's own made (~60 ms: not on the frame that first plays them).
struct Load {
    std::mutex mu;
    bool done = false;
    gs::Loaded result;
    std::array<SoundClip, kCueCount> own{};
};

} // namespace

const char* cue_name(Cue cue) { return gs::cue_name(static_cast<int>(cue)); }

struct Sounds::Impl {
    SystemClock system_clock;
    const Clock* clock = nullptr;
    bool enabled = false, output = true;
    std::filesystem::path game_root;

    // what each cue plays: the game's (when read) or the launcher's (made when first needed)
    std::array<std::shared_ptr<const SoundClip>, kCueCount> game{}, own{};
    Source source = Source::Own;
    std::string status = "the launcher's own sounds (no game folder)";
    std::shared_ptr<Load> load;        // the game's, being read
    std::filesystem::path loaded_root; // read (or being read) from
    std::shared_ptr<Load> own_load;    // the launcher's own, being made
    bool own_started = false;
    std::vector<std::pair<std::thread, std::shared_ptr<Load>>> loaders; // joined once done (or at the end)

    std::array<double, kCueCount> last_play{};
    double busy_until = -1e9, retry_open_at = -1e9;

    mutable std::mutex mu; // voices (the audio thread mixes them)
    std::vector<Voice> voices;

    SDL_AudioStream* stream = nullptr;
    bool audio_init = false;

    double now() const { return (clock ? clock : &system_clock)->now(); }

    // A job on its own thread: the game's sounds from `root`, or (root empty) the launcher's own.
    std::shared_ptr<Load> spawn(const std::filesystem::path& root) {
        auto l = std::make_shared<Load>();
        try {
            loaders.emplace_back(std::thread([l, root] {
                                     gs::Loaded r;
                                     std::array<SoundClip, kCueCount> own{};
                                     if (!root.empty())
                                         r = gs::load_cues(root);
                                     else
                                         for (int c = 0; c < kCueCount; ++c)
                                             own[std::size_t(c)] = synthesize(static_cast<Cue>(c));
                                     std::lock_guard<std::mutex> lock(l->mu);
                                     l->result = std::move(r);
                                     l->own = std::move(own);
                                     l->done = true;
                                 }),
                                 l);
        } catch (const std::exception& e) { // (no thread: the own sounds are made when played, the game's not read)
            SDL_Log("sounds: %s", e.what());
            return nullptr;
        }
        return l;
    }

    void start_load() {
        if (!enabled) return;
        if (!own_started) {
            own_started = true;
            own_load = spawn({});
        }
        if (game_root.empty() || (loaded_root == game_root && (load || source == Source::Game))) return;
        loaded_root = game_root;
        load = spawn(game_root);
        source = load ? Source::Loading : Source::Own;
        status = load ? "reading the game's sounds from " + game_root.string()
                      : "the launcher's own sounds (the game's could not be read)";
    }

    void join_finished() {
        for (auto& [thread, state] : loaders) {
            std::lock_guard<std::mutex> lock(state->mu);
            if (state->done && thread.joinable()) thread.join();
        }
        loaders.erase(std::remove_if(loaders.begin(), loaders.end(), [](const auto& l) { return !l.first.joinable(); }),
                      loaders.end());
    }

    void take_load() {
        if (!loaders.empty()) join_finished();
        if (own_load) {
            bool taken = false;
            {
                std::lock_guard<std::mutex> lock(own_load->mu);
                if (own_load->done) {
                    for (int c = 0; c < kCueCount; ++c) {
                        auto& clip = own_load->own[std::size_t(c)];
                        if (!own[std::size_t(c)] && !clip.empty())
                            own[std::size_t(c)] = std::make_shared<const SoundClip>(std::move(clip));
                    }
                    taken = true;
                }
            }
            if (taken) own_load.reset();
        }
        if (!load) return;
        gs::Loaded r;
        {
            std::lock_guard<std::mutex> lock(load->mu);
            if (!load->done) return;
            r = std::move(load->result);
        }
        load.reset();
        const int found = r.found();
        for (int c = 0; c < kCueCount; ++c) {
            auto& clip = r.clips[std::size_t(c)];
            game[std::size_t(c)] = clip.empty() ? nullptr : std::make_shared<const SoundClip>(std::move(clip));
        }
        source = found ? Source::Game : Source::Own;
        if (found == kCueCount)
            status = "the game's sounds (" + r.archives.string() + ")";
        else if (found)
            status = "the game's sounds, " + std::to_string(kCueCount - found) + " of the launcher's own (" +
                     (r.log.empty() ? std::string("?") : r.log.front()) + ")";
        else
            status = "the launcher's own sounds (" + (r.log.empty() ? std::string("?") : r.log.front()) + ")";
        for (const auto& line : r.log) SDL_Log("sounds: %s", line.c_str());
        join_finished();
    }

    std::shared_ptr<const SoundClip> clip(Cue cue) {
        std::size_t i = static_cast<std::size_t>(cue);
        if (game[i]) return game[i];
        if (!own[i]) own[i] = std::make_shared<const SoundClip>(synthesize(cue));
        return own[i];
    }

    static void SDLCALL feed(void* user, SDL_AudioStream* s, int additional, int) {
        auto* self = static_cast<Impl*>(user);
        float buffer[2 * 512];
        for (int left = additional / 8; left > 0;) {
            int n = std::min(left, 512);
            self->mix(buffer, n);
            SDL_PutAudioStreamData(s, buffer, n * 8);
            left -= n;
        }
    }

    bool open_device(double t) {
        if (stream) return true;
        if (!output || t < retry_open_at) return false;
        if (!SDL_WasInit(SDL_INIT_AUDIO)) {
            if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {
                SDL_Log("sounds: no audio (%s)", SDL_GetError());
                retry_open_at = t + kRetryOpenAfter;
                return false;
            }
            audio_init = true;
        }
        SDL_SetHintWithPriority(SDL_HINT_AUDIO_DEVICE_SAMPLE_FRAMES, "512", SDL_HINT_DEFAULT);
        const SDL_AudioSpec spec{SDL_AUDIO_F32, 2, gs::kRate};
        stream = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, &Impl::feed, this);
        if (!stream) {
            SDL_Log("sounds: cannot open the audio device (%s)", SDL_GetError());
            retry_open_at = t + kRetryOpenAfter;
            return false;
        }
        SDL_ResumeAudioStreamDevice(stream);
        return true;
    }

    void close_device(bool quit_audio) {
        if (stream) {
            SDL_DestroyAudioStream(stream); // (also closes the device it opened; the callback has stopped)
            stream = nullptr;
        }
        if (quit_audio && audio_init) {
            SDL_QuitSubSystem(SDL_INIT_AUDIO);
            audio_init = false;
        }
    }

    void mix(float* out, int frames) {
        std::fill(out, out + 2 * frames, 0.f);
        std::lock_guard<std::mutex> lock(mu);
        for (auto& v : voices) {
            const auto& s = v.clip->samples;
            std::size_t total = v.clip->frames();
            for (int i = 0; i < frames && v.pos < total; ++i, ++v.pos) {
                float g = 1.f;
                if (v.fade >= 0) {
                    if (v.fade == 0) {
                        v.pos = total;
                        break;
                    }
                    g = static_cast<float>(v.fade--) / kChokeFrames;
                }
                out[2 * i] += s[2 * v.pos] * g;
                out[2 * i + 1] += s[2 * v.pos + 1] * g;
            }
        }
        voices.erase(
            std::remove_if(voices.begin(), voices.end(), [](const Voice& v) { return v.pos >= v.clip->frames(); }),
            voices.end());
        // Several loud sounds at once: rounded off above -2 dBFS instead of clipping.
        for (int i = 0; i < 2 * frames; ++i) {
            float x = out[i], a = std::fabs(x);
            if (a > 0.8f) out[i] = std::copysign(0.8f + 0.2f * std::tanh((a - 0.8f) / 0.2f), x);
        }
    }
};

Sounds::Sounds(const Clock* clock) : impl_(std::make_unique<Impl>()) { impl_->clock = clock; }

Sounds::~Sounds() {
    impl_->close_device(true);
    for (auto& l : impl_->loaders)
        if (l.first.joinable()) l.first.join(); // (a reading still going: at most a second or so)
}

void Sounds::set_enabled(bool on) {
    if (impl_->enabled == on) return;
    impl_->enabled = on;
    if (!on) {
        impl_->close_device(true);
        std::lock_guard<std::mutex> lock(impl_->mu);
        impl_->voices.clear();
    } else {
        impl_->start_load();
    }
}

bool Sounds::enabled() const { return impl_->enabled; }

void Sounds::set_game_folder(const std::filesystem::path& root) {
    if (root == impl_->game_root) return;
    impl_->game_root = root;
    impl_->game.fill(nullptr);
    impl_->load.reset(); // (a reading from the old folder is left to finish; its result is not taken)
    impl_->loaded_root.clear();
    impl_->source = Source::Own;
    impl_->status =
        root.empty() ? "the launcher's own sounds (no game folder)" : "the launcher's own sounds (not read yet)";
    impl_->start_load();
}

void Sounds::play(Cue cue) {
    Impl& m = *impl_;
    if (!m.enabled) return;
    int index = static_cast<int>(cue);
    if (index < 0 || index >= kCueCount) return;
    double t = m.now();
    m.take_load();
    double gap = cue == Cue::Move ? kMoveGap : kSameCueGap;
    if (m.last_play[std::size_t(index)] > 0 && t - m.last_play[std::size_t(index)] < gap &&
        t >= m.last_play[std::size_t(index)])
        return;
    m.last_play[std::size_t(index)] = t > 0 ? t : 1e-9;
    auto clip = m.clip(cue);
    if (!clip || clip->empty()) return;
    if (m.output && !m.open_device(t)) return;
    {
        std::lock_guard<std::mutex> lock(m.mu);
        int group = choke_group(cue);
        for (auto& v : m.voices)
            if (group >= 0 && v.group == group && v.fade < 0) v.fade = kChokeFrames;
        if (m.voices.size() >= kMaxVoices) {
            // the oldest still sounding is faded out; past twice the limit the oldest go at once
            for (auto& v : m.voices)
                if (v.fade < 0) {
                    v.fade = kChokeFrames;
                    break;
                }
            if (m.voices.size() >= 2 * kMaxVoices) m.voices.erase(m.voices.begin());
        }
        m.voices.push_back({clip, 0, group, -1});
    }
    m.busy_until = std::max(m.busy_until, t + clip->seconds());
}

void Sounds::tick() {
    Impl& m = *impl_;
    m.take_load();
    if (!m.stream) return;
    double t = m.now();
    if (t < m.busy_until + kCloseAfter) return;
    {
        std::lock_guard<std::mutex> lock(m.mu);
        if (!m.voices.empty()) return;
    }
    m.close_device(false);
}

Sounds::Source Sounds::source() const { return impl_->source; }
std::string Sounds::status() const { return impl_->status; }
bool Sounds::device_open() const { return impl_->stream != nullptr; }

int Sounds::voices() const {
    std::lock_guard<std::mutex> lock(impl_->mu);
    return static_cast<int>(impl_->voices.size());
}

bool Sounds::wait_loaded(double seconds) {
    auto l = impl_->load;
    for (double waited = 0; l; waited += 0.005) {
        {
            std::lock_guard<std::mutex> lock(l->mu);
            if (l->done) break;
        }
        if (waited >= seconds) return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    impl_->take_load();
    return !impl_->load;
}

std::shared_ptr<const SoundClip> Sounds::clip(Cue cue) {
    impl_->take_load();
    return impl_->clip(cue);
}

void Sounds::set_output(bool allowed) {
    impl_->output = allowed;
    if (!allowed) impl_->close_device(false);
}

void Sounds::mix(float* out, int frames) { impl_->mix(out, frames); }

int write_sound_wavs(const std::filesystem::path& dir, const std::filesystem::path& game_root) {
    std::error_code ec;
    std::filesystem::create_directories(dir, ec);
    gs::Loaded loaded;
    if (!game_root.empty()) {
        loaded = gs::load_cues(game_root);
        for (const auto& line : loaded.log) std::fprintf(stderr, "sounds: %s\n", line.c_str());
    }
    int written = 0;
    auto write = [&](const SoundClip& clip, const std::string& name) {
        auto bytes = gs::wav_file(clip);
        std::ofstream f(dir / name, std::ios::binary | std::ios::trunc);
        f.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
        if (f)
            ++written;
        else
            std::fprintf(stderr, "sounds: cannot write %s\n", (dir / name).string().c_str());
    };
    for (int c = 0; c < kCueCount; ++c) {
        char prefix[8];
        std::snprintf(prefix, sizeof prefix, "%02d_", c + 1);
        std::string base = prefix + std::string(gs::cue_name(c));
        write(synthesize(static_cast<Cue>(c)), base + "_own.wav");
        if (!loaded.clips[std::size_t(c)].empty()) write(loaded.clips[std::size_t(c)], base + "_game.wav");
    }
    return written;
}

} // namespace ttt2::ui
