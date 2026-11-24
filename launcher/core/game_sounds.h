#pragma once

// The game's own menu sounds for the launcher, read at run time from the player's installed Tekken Tag Tournament 2.
// Nothing of the game is in this repository or shipped with the launcher: only the names of its sound banks and
// tones are written here (cue_sources()); the sounds themselves are decoded from the player's install when the
// launcher starts with sounds on. Portable C++ without SDL (Linux, Windows, MinGW).
//
// The formats (as tools/characters/ttt2char/ttt2/archive.py, nus3bank.py and dsp.py read them):
// - content/hdd/dataNNN.ofs + .bin: the archives. An index (.ofs) is a list of big-endian chunks {u32 size, tag,
//   payload}: `ofsi` holds {u32 key, u32 word} per entry, `ofsd` a u32 offset per entry plus the end, into the .bin's
//   payload at 0x100; the low four bits of an offset are the entry's length modulo 16 (0: a multiple of 16). The
//   title loads data000.. in order and then the update's data100: for a key held twice the last one loaded wins.
//   An entry's key is the CRC-32 of its name with the register starting at zero; a sound bank's name is
//   "<bank>.nus3bank". Sound banks are stored as they are; other entries are scrambled (XOR with four 32-bit linear
//   congruential streams seeded from the key, one per big-endian word of each 16-byte block) and mostly zlib
//   compressed (NRCZ, not read here: no sound bank is).
// - NUS3BANK (little-endian): "NUS3", u32 size, "BANKTOC ", u32 table size, u32 chunk count, {tag, u32 size} per
//   chunk, then the chunks {tag, u32 size, data} in that order. TONE: u32 count, {u32 offset, u32 size} per tone,
//   the tones. PACK: the tones' audio.
//   An audio tone: byte 4 is not 0x7F, its name (u8 length with the NUL, the name) at 12, padding to 4, {u32 0,
//   u32 8, u32 offset into PACK, u32 size}, then f32 volume (dB, -90 = silent), f32 pan (-90 left .. 90 right),
//   f32 pitch (cents), ...; after its last 0xFFFFFFFF: {u32 sample rate, u32 channels, u32 samples}.
//   A link tone (plays other tones together; a stereo sound is two mono tones panned left and right): byte 4 is
//   0x7F, its name at 8, padding to 4, {u32 1, u32 list size, u32 0xFFFFFFFF, u32 count}, count x {u32 next, u32 0,
//   f32 weight, u32 tone index}, then f32 volume (dB). Entries of 16 bytes or less are empty places.
//   A tone's audio: IDSP (big-endian header + Nintendo DSP ADPCM, interleaved per channel) or a RIFF WAVE file
//   (16-bit PCM).
// - DSP ADPCM: frames of 8 bytes for 14 samples, a header byte (predictor << 4 | scale) and 14 signed 4-bit codes,
//   high half first: sample = clamp16((((code << scale) << 11) + c1 * h1 + c2 * h2 + 1024) >> 11).

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace launcher::game_sounds {

namespace fs = std::filesystem;

// Every clip: kRate Hz, stereo, interleaved float (L R L R ...), within -1..1.
inline constexpr int kRate = 48000;

struct Clip {
    std::vector<float> samples;
    std::size_t frames() const { return samples.size() / 2; }
    bool empty() const { return samples.empty(); }
    double seconds() const { return static_cast<double>(frames()) / kRate; }
};

// The launcher's cues, in the order of ttt2::ui::Cue (launcher/ui/include/ttt2ui/sound.h) and of the app's copy
// (launcher/app/sound_cues.h): Move, Accept, Back, TabSwitch, SectionSwitch, Toggle, Refuse, DrillIn, DrillOut,
// TaskDone, TaskFailed, Play.
inline constexpr int kCueCount = 12;
const char* cue_name(int cue); // "move", "accept", ... (file names of --sounds-wav)

// What a cue plays from the game: a tone (an audio tone or a link tone) of a bank.
struct CueSource {
    const char* bank; // "se_Aly_Basic"
    const char* tone; // "main_cursor"
};
const std::array<CueSource, kCueCount>& cue_sources();

// How loud and how long a cue is, for the game's sounds and the fallback ones alike: its loudness (the loudest
// 50 ms, K-weighted as ITU-R BS.1770, dB), its peak at most kPeakLimit, and at most max_seconds long (faded out when
// shortened).
struct CueLevel {
    float loudness_db;
    float max_seconds;
};
const std::array<CueLevel, kCueCount>& cue_levels();
inline constexpr float kPeakLimit = 0.891f; // -1 dBFS

// The game's sounds for every cue (empty clips where one could not be read), and what went wrong, one line each.
struct Loaded {
    fs::path archives;                   // the content/hdd folder read, empty when none was found
    std::array<Clip, kCueCount> clips{}; // finished (finish()) for their cue
    std::vector<std::string> log;
    int found() const;
};

// The folder holding the game's archives (data000.ofs ...) from what the launcher knows of the install: the install
// folder (as the installer makes it on Linux and Windows: <folder>/game/content/hdd), the game folder in it
// (<game>/content/hdd) or that folder itself. nullopt when none of them holds data000.ofs.
std::optional<fs::path> find_archives(const fs::path& root);

// Reads every cue's sound from the install found from `root`. Never throws: whatever fails is logged and leaves that
// cue's clip empty (the launcher then plays its own sound). Reads only the banks' tables and the tones it plays.
Loaded load_cues(const fs::path& root);

// ---- The pieces (tests use them on made-up data) ----

// An entry's key: CRC-32 (reflected, 0xEDB88320) of its name with the register starting at zero.
std::uint32_t name_key(std::string_view name);

// XOR with the entry's key stream; the same call scrambles and unscrambles. `offset` (a multiple of 16) is where
// `data` starts in the entry.
void scramble(std::uint8_t* data, std::size_t size, std::uint32_t key, std::uint64_t offset = 0);

// The archives of an install (content/hdd), read on demand.
struct Entry {
    fs::path bin; // its archive's .bin
    std::uint32_t key = 0;
    std::uint64_t start = 0; // in the .bin (payload at 0x100 included)
    std::uint64_t size = 0;
};
class Archives {
public:
    explicit Archives(fs::path hdd) : hdd_(std::move(hdd)) {}
    // The entry with this key in the archive loaded last that holds it (data100, then data055 .. data000).
    std::optional<Entry> find(std::uint32_t key, std::string* error = nullptr);

private:
    struct Index {
        fs::path bin;
        std::vector<std::uint32_t> keys;
        std::vector<std::uint64_t> starts, sizes;
        bool read = false, ok = false;
    };
    bool list(std::string* error);
    fs::path hdd_;
    bool listed_ = false;
    std::vector<Index> indices_; // loaded last first
};

// An index's entries (.ofs bytes): false when it is not one.
struct IndexEntry {
    std::uint32_t key, word;
    std::uint64_t start, size; // in the .bin's payload (add 0x100 for the file)
};
bool parse_index(const std::uint8_t* data, std::size_t size, std::vector<IndexEntry>& out);

// Reads `size` bytes at `offset` of an entry into `out`: false on any failure.
using ReadAt = std::function<bool(std::uint64_t offset, std::size_t size, std::vector<std::uint8_t>& out)>;

// 16-bit PCM, interleaved.
struct Pcm {
    int rate = 0;
    int channels = 0;
    std::vector<std::int16_t> samples;
    std::size_t frames() const { return channels ? samples.size() / static_cast<std::size_t>(channels) : 0; }
};
// The DSP ADPCM decoder: `samples` samples (fewer when the data ends) from frames of 8 bytes; false when a frame
// names a predictor past the 8 pairs (`coefs`: c1, c2 for each).
bool decode_dsp_adpcm(const std::uint8_t* data, std::size_t size, const std::int16_t coefs[16], std::size_t samples,
                      std::vector<std::int16_t>& out);
bool decode_idsp(const std::uint8_t* data, std::size_t size, Pcm& out, std::string* error = nullptr);
bool decode_wave(const std::uint8_t* data, std::size_t size, Pcm& out, std::string* error = nullptr);
bool decode_audio(const std::uint8_t* data, std::size_t size, Pcm& out, std::string* error = nullptr);

// A sound bank, read in parts through `read` (its header, its tone table, then each tone's audio when asked).
struct Tone {
    std::string name;
    bool link = false;
    // an audio tone:
    std::uint32_t pack_offset = 0, pack_size = 0;
    float volume_db = 0, pan = 0, cents = 0;
    // a link tone: (weight, tone index) of the tones it plays
    std::vector<std::pair<float, int>> parts;
};
class Bank {
public:
    bool open(ReadAt read, std::uint64_t size, std::string* error = nullptr);
    const std::string& name() const { return name_; }
    int find(std::string_view tone) const; // -1 when it has none of this name
    const std::vector<Tone>& tones() const { return tones_; }
    bool audio(int tone, Pcm& out, std::string* error = nullptr) const;
    // A tone played as the game plays it (each part at its volume, pan and pitch), as a clip.
    bool render(int tone, Clip& out, std::string* error = nullptr) const;

private:
    ReadAt read_;
    std::uint64_t size_ = 0, pack_ = 0, pack_size_ = 0;
    std::string name_;
    std::vector<Tone> tones_;
};

// Resamples one channel of `pcm` (as floats) from `rate` to kRate (windowed sinc, low-passed when shrinking).
std::vector<float> resample(const std::vector<float>& in, double rate);

// Makes a clip the cue's: drops silence before it and after it, shortens it to max_seconds (fading out), sets its
// loudness and keeps its peak at most kPeakLimit.
void finish(Clip& clip, const CueLevel& level);
// The loudest 50 ms of a clip (K-weighted mean square of both channels, dB), -120 when silent.
float loudness_db(const Clip& clip);
float peak(const Clip& clip);

// A 16-bit PCM WAV file of a clip.
std::vector<std::uint8_t> wav_file(const Clip& clip);

} // namespace launcher::game_sounds
