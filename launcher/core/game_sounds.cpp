// The game's own menu sounds, read from the player's install (game_sounds.h has the formats).
#include "game_sounds.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <exception>
#include <fstream>
#include <map>
#include <memory>

namespace launcher::game_sounds {

namespace {

constexpr std::uint64_t kPayload = 0x100;              // where an archive's entries start in its .bin
constexpr std::uint64_t kMaxIndex = 16u << 20;         // an index is a few KB
constexpr std::uint64_t kMaxScrambledBank = 64u << 20; // a scrambled bank is read whole (none is, so far)
constexpr std::uint64_t kMaxToneTable = 8u << 20;      // the TONE chunk of the largest bank is ~60 KB
constexpr std::uint64_t kMaxToneAudio = 16u << 20;     // the longest menu tone is ~140 KB
constexpr double kMaxRenderSeconds = 10;

std::uint32_t be32(const std::uint8_t* p) {
    return std::uint32_t(p[0]) << 24 | std::uint32_t(p[1]) << 16 | std::uint32_t(p[2]) << 8 | p[3];
}
std::uint32_t le32(const std::uint8_t* p) {
    return std::uint32_t(p[3]) << 24 | std::uint32_t(p[2]) << 16 | std::uint32_t(p[1]) << 8 | p[0];
}
std::uint16_t le16(const std::uint8_t* p) { return static_cast<std::uint16_t>(p[1] << 8 | p[0]); }
std::int16_t be16s(const std::uint8_t* p) { return static_cast<std::int16_t>(p[0] << 8 | p[1]); }
float lef32(const std::uint8_t* p) {
    std::uint32_t u = le32(p);
    float f;
    std::memcpy(&f, &u, 4);
    return f;
}

void set(std::string* error, std::string what) {
    if (error) *error = std::move(what);
}

std::string hex8(std::uint32_t v) {
    static const char* digits = "0123456789abcdef";
    std::string s(8, '0');
    for (int i = 7; i >= 0; --i, v >>= 4) s[static_cast<std::size_t>(i)] = digits[v & 15];
    return s;
}

bool read_file_at(const fs::path& path, std::uint64_t offset, std::size_t size, std::vector<std::uint8_t>& out) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    f.seekg(static_cast<std::streamoff>(offset));
    if (!f) return false;
    out.resize(size);
    if (size == 0) return true;
    f.read(reinterpret_cast<char*>(out.data()), static_cast<std::streamsize>(size));
    return static_cast<std::size_t>(f.gcount()) == size;
}

bool read_whole(const fs::path& path, std::uint64_t limit, std::vector<std::uint8_t>& out) {
    std::error_code ec;
    auto size = fs::file_size(path, ec);
    if (ec || size > limit) return false;
    return read_file_at(path, 0, static_cast<std::size_t>(size), out);
}

int clamp16(std::int64_t v) { return v < -32768 ? -32768 : (v > 32767 ? 32767 : static_cast<int>(v)); }

} // namespace

// ---- cues ----

const char* cue_name(int cue) {
    static const char* names[kCueCount] = {"move",   "accept",   "back",      "tab_switch", "section_switch", "toggle",
                                           "refuse", "drill_in", "drill_out", "task_done",  "task_failed",    "play"};
    return cue >= 0 && cue < kCueCount ? names[cue] : "?";
}

// Chosen by listening to every tone of the menu banks (local notes: agents/sound/NOTES.md, audition page):
// the main menu's own cursor / decide / cancel / return, the select screen's cursor, the practice menu's toggle
// glow, the online lobby's window / match / leave sounds, and from the fight itself the tag-in whoosh, a mid guard
// (a refused action is a blocked one) and the round's FIGHT hit for Play.
const std::array<CueSource, kCueCount>& cue_sources() {
    static const std::array<CueSource, kCueCount> sources = {{
        {"se_Aly_Basic", "main_cursor"},        // Move
        {"se_Aly_Basic", "main_decide"},        // Accept
        {"se_Aly_Basic", "main_cansel"},        // Back
        {"se_Btl_Battle", "se_tag"},            // TabSwitch
        {"se_Aly_Basic", "sele_cursor"},        // SectionSwitch
        {"se_practice", "pra_icon_glow01"},     // Toggle
        {"se_Btl_Battle", "RES_BANK_GRD_MD01"}, // Refuse
        {"se_online", "on_window"},             // DrillIn
        {"se_Aly_Basic", "main_return"},        // DrillOut
        {"se_online", "on_taisen"},             // TaskDone
        {"se_online", "on_room_out"},           // TaskFailed
        {"se_Btl_Battle", "se_fight"},          // Play
    }};
    return sources;
}

const std::array<CueLevel, kCueCount>& cue_levels() {
    static const std::array<CueLevel, kCueCount> levels = {{
        {-21.f, 0.14f}, // Move: the quietest, it repeats
        {-16.f, 0.80f}, // Accept
        {-18.f, 0.45f}, // Back
        {-18.f, 0.60f}, // TabSwitch
        {-20.f, 0.40f}, // SectionSwitch
        {-20.f, 0.35f}, // Toggle
        {-17.f, 0.45f}, // Refuse
        {-19.f, 0.60f}, // DrillIn
        {-19.f, 0.45f}, // DrillOut
        {-16.f, 1.30f}, // TaskDone
        {-16.f, 1.00f}, // TaskFailed
        {-12.f, 1.40f}, // Play: the strongest
    }};
    return levels;
}

int Loaded::found() const {
    int n = 0;
    for (const auto& c : clips) n += !c.empty();
    return n;
}

// ---- archives ----

std::uint32_t name_key(std::string_view name) {
    static const auto table = [] {
        std::array<std::uint32_t, 256> t{};
        for (std::uint32_t i = 0; i < 256; ++i) {
            std::uint32_t c = i;
            for (int k = 0; k < 8; ++k) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            t[i] = c;
        }
        return t;
    }();
    std::uint32_t r = 0; // (zlib.crc32(name, 0xFFFFFFFF): the register starts at zero, the result is inverted)
    for (unsigned char c : name) r = table[(r ^ c) & 0xFF] ^ (r >> 8);
    return r ^ 0xFFFFFFFFu;
}

void scramble(std::uint8_t* data, std::size_t size, std::uint32_t key, std::uint64_t offset) {
    std::uint32_t w[4];
    std::uint32_t x = key;
    for (auto& s : w) {
        x = x * 0x000BDE95u + 0x008EF345u;
        s = x;
    }
    // Step to the block at `offset` (w = w * 1531 + 5011 per block), by squaring the affine map.
    std::uint64_t steps = offset / 16;
    std::uint32_t mul = 1531, add = 5011; // the map for 2^k blocks
    while (steps) {
        if (steps & 1)
            for (auto& s : w) s = s * mul + add;
        add = add * mul + add;
        mul = mul * mul;
        steps >>= 1;
    }
    for (std::size_t b = 0; b < size; b += 16) {
        for (int j = 0; j < 4; ++j) {
            for (int k = 0; k < 4; ++k) {
                std::size_t i = b + static_cast<std::size_t>(4 * j + k);
                if (i < size) data[i] ^= static_cast<std::uint8_t>(w[j] >> (24 - 8 * k));
            }
            w[j] = w[j] * 1531u + 5011u;
        }
    }
}

bool parse_index(const std::uint8_t* d, std::size_t n, std::vector<IndexEntry>& out) {
    out.clear();
    const std::uint8_t *ofsi = nullptr, *ofsd = nullptr;
    std::size_t si = 0, sd = 0;
    for (std::size_t pos = 0; pos + 8 <= n;) {
        std::uint32_t size = be32(d + pos);
        if (size < 8 || size > n - pos) break;
        if (!ofsi && std::memcmp(d + pos + 4, "ofsi", 4) == 0) {
            ofsi = d + pos + 8;
            si = size - 8;
        } else if (!ofsd && std::memcmp(d + pos + 4, "ofsd", 4) == 0) {
            ofsd = d + pos + 8;
            sd = size - 8;
        }
        pos += size;
    }
    if (!ofsi || !ofsd) return false;
    std::size_t count = si / 8;
    if (sd / 4 != count + 1) return false;
    out.reserve(count);
    for (std::size_t i = 0; i < count; ++i) {
        std::uint32_t a = be32(ofsd + 4 * i), b = be32(ofsd + 4 * (i + 1));
        std::uint64_t start = a & ~0xFu, end = b & ~0xFu, tail = a & 0xFu;
        if (end < start) return false;
        std::uint64_t size = tail == 0 ? end - start : std::max<std::uint64_t>(end - start, 16) - 16 + tail;
        out.push_back({be32(ofsi + 8 * i), be32(ofsi + 8 * i + 4), start, size});
    }
    return true;
}

bool Archives::list(std::string* error) {
    if (listed_) return !indices_.empty();
    listed_ = true;
    std::error_code ec;
    std::vector<std::string> names;
    for (fs::directory_iterator it(hdd_, ec), end; !ec && it != end; it.increment(ec)) {
        std::string n = it->path().filename().string();
        if (n.size() == 11 && n.compare(0, 4, "data") == 0 && n.compare(7, 4, ".ofs") == 0 &&
            std::all_of(n.begin() + 4, n.begin() + 7, [](char c) { return c >= '0' && c <= '9'; }))
            names.push_back(n.substr(0, 7));
    }
    if (ec) {
        set(error, "cannot list " + hdd_.string() + ": " + ec.message());
        return false;
    }
    std::sort(names.rbegin(), names.rend()); // data100 (the update) first: the last loaded wins
    for (const auto& n : names) {
        Index index;
        index.bin = hdd_ / (n + ".bin");
        indices_.push_back(std::move(index));
    }
    if (indices_.empty()) set(error, "no archives in " + hdd_.string());
    return !indices_.empty();
}

std::optional<Entry> Archives::find(std::uint32_t key, std::string* error) {
    if (!list(error)) return std::nullopt;
    for (auto& index : indices_) {
        if (!index.read) {
            index.read = true;
            std::vector<std::uint8_t> bytes;
            fs::path ofs = index.bin;
            ofs.replace_extension(".ofs");
            std::vector<IndexEntry> entries;
            if (!read_whole(ofs, kMaxIndex, bytes) || !parse_index(bytes.data(), bytes.size(), entries)) {
                continue; // (an unreadable index: the next one may still hold the key)
            }
            index.ok = true;
            for (const auto& e : entries) {
                index.keys.push_back(e.key);
                index.starts.push_back(e.start);
                index.sizes.push_back(e.size);
            }
        }
        if (!index.ok) continue;
        for (std::size_t i = 0; i < index.keys.size(); ++i)
            if (index.keys[i] == key) return Entry{index.bin, key, kPayload + index.starts[i], index.sizes[i]};
    }
    set(error, "no archive entry " + hex8(key));
    return std::nullopt;
}

std::optional<fs::path> find_archives(const fs::path& root) {
    if (root.empty()) return std::nullopt;
    std::error_code ec;
    for (const fs::path& p : {root / "game" / "content" / "hdd", root / "content" / "hdd", root})
        if (fs::is_regular_file(p / "data000.ofs", ec)) return p;
    return std::nullopt;
}

// ---- audio ----

bool decode_dsp_adpcm(const std::uint8_t* data, std::size_t size, const std::int16_t coefs[16], std::size_t samples,
                      std::vector<std::int16_t>& out) {
    out.clear();
    out.reserve(std::min<std::size_t>(samples, size / 8 * 14 + 14));
    std::int64_t y1 = 0, y2 = 0;
    for (std::size_t f = 0; f < size && out.size() < samples; f += 8) {
        int head = data[f];
        int predictor = head >> 4, scale = head & 15;
        if (predictor >= 8) return false;
        std::int64_t c1 = coefs[2 * predictor], c2 = coefs[2 * predictor + 1];
        for (std::size_t b = f + 1; b < f + 8 && b < size; ++b) {
            for (int code : {data[b] >> 4, data[b] & 15}) {
                if (code >= 8) code -= 16;
                std::int64_t v =
                    (std::int64_t(code) * (std::int64_t(1) << scale) * 2048 + c1 * y1 + c2 * y2 + 1024) >> 11;
                int s = clamp16(v);
                if (out.size() < samples) out.push_back(static_cast<std::int16_t>(s));
                y2 = y1;
                y1 = s;
            }
        }
    }
    return true;
}

bool decode_idsp(const std::uint8_t* d, std::size_t n, Pcm& out, std::string* error) {
    if (n < 0x40 || std::memcmp(d, "IDSP", 4) != 0) {
        set(error, "not IDSP audio");
        return false;
    }
    std::uint32_t channels = be32(d + 8), rate = be32(d + 12), samples = be32(d + 16), inter = be32(d + 28),
                  hsize = be32(d + 32), chsize = be32(d + 36), doff = be32(d + 40), dsize = be32(d + 44);
    if (channels < 1 || channels > 2 || rate < 4000 || rate > 192000 || inter == 0 || inter > 0x10000 ||
        chsize < 0x3C || std::uint64_t(hsize) + std::uint64_t(chsize) * channels > n || doff > n ||
        samples > 60u * 192000u) {
        set(error, "IDSP header out of range");
        return false;
    }
    std::vector<std::vector<std::int16_t>> decoded(channels);
    std::size_t frames = samples;
    for (std::uint32_t c = 0; c < channels; ++c) {
        const std::uint8_t* h = d + hsize + std::size_t(chsize) * c;
        std::int16_t coefs[16];
        for (int i = 0; i < 16; ++i) coefs[i] = be16s(h + 0x1C + 2 * i);
        std::vector<std::uint8_t> data;
        data.reserve(dsize);
        for (std::uint64_t o = 0; o < dsize; o += inter) {
            std::uint64_t p = std::uint64_t(doff) + o * channels + std::uint64_t(c) * inter;
            if (p >= n) break;
            std::uint64_t take = std::min<std::uint64_t>(inter, n - p);
            data.insert(data.end(), d + p, d + p + take);
        }
        if (data.size() > dsize) data.resize(dsize);
        if (!decode_dsp_adpcm(data.data(), data.size(), coefs, samples, decoded[c])) {
            set(error, "DSP ADPCM frame with a predictor past 8");
            return false;
        }
        frames = std::min(frames, decoded[c].size());
    }
    out.rate = static_cast<int>(rate);
    out.channels = static_cast<int>(channels);
    out.samples.resize(frames * channels);
    for (std::size_t i = 0; i < frames; ++i)
        for (std::uint32_t c = 0; c < channels; ++c) out.samples[i * channels + c] = decoded[c][i];
    return true;
}

bool decode_wave(const std::uint8_t* d, std::size_t n, Pcm& out, std::string* error) {
    if (n < 12 || std::memcmp(d, "RIFF", 4) != 0 || std::memcmp(d + 8, "WAVE", 4) != 0) {
        set(error, "not a WAVE file");
        return false;
    }
    int channels = 0, rate = 0, bits = 0, format = 0;
    const std::uint8_t* data = nullptr;
    std::size_t data_size = 0;
    for (std::size_t pos = 12; pos + 8 <= n;) {
        std::uint32_t size = le32(d + pos + 4);
        const std::uint8_t* body = d + pos + 8;
        std::size_t have = std::min<std::size_t>(size, n - pos - 8);
        if (std::memcmp(d + pos, "fmt ", 4) == 0 && have >= 16) {
            format = le16(body);
            channels = le16(body + 2);
            rate = static_cast<int>(le32(body + 4));
            bits = le16(body + 14);
        } else if (std::memcmp(d + pos, "data", 4) == 0) {
            data = body;
            data_size = have;
        }
        if (size > n - pos - 8) break;
        pos += 8 + size + (size & 1);
    }
    if (format != 1 || bits != 16 || channels < 1 || channels > 2 || rate < 4000 || rate > 192000 || !data) {
        set(error, "WAVE file is not 16-bit PCM");
        return false;
    }
    out.rate = rate;
    out.channels = channels;
    std::size_t count = data_size / 2 / static_cast<std::size_t>(channels) * static_cast<std::size_t>(channels);
    out.samples.resize(count);
    for (std::size_t i = 0; i < count; ++i) out.samples[i] = static_cast<std::int16_t>(le16(data + 2 * i));
    return true;
}

bool decode_audio(const std::uint8_t* d, std::size_t n, Pcm& out, std::string* error) {
    if (n >= 4 && std::memcmp(d, "IDSP", 4) == 0) return decode_idsp(d, n, out, error);
    if (n >= 4 && std::memcmp(d, "RIFF", 4) == 0) return decode_wave(d, n, out, error);
    set(error, "unknown audio format");
    return false;
}

// ---- banks ----

namespace {

// A tone entry, read: false for an empty place or one that is not understood.
bool parse_tone(const std::uint8_t* t, std::size_t n, Tone& tone) {
    if (n <= 16) return false;
    tone.link = t[4] == 0x7F;
    std::size_t at = tone.link ? 8 : 12;
    std::size_t len = t[at];
    if (len == 0 || at + 1 + len > n) return false;
    tone.name.assign(reinterpret_cast<const char*>(t + at + 1), len - 1);
    std::size_t o = at + 1 + len;
    o += (4 - o % 4) % 4;
    if (tone.link) {
        if (o + 16 > n || le32(t + o + 8) != 0xFFFFFFFFu) return false;
        std::uint32_t count = le32(t + o + 12);
        if (count == 0 || count > 32 || le32(t + o + 4) != 8 + 16 * count || o + 16 + 16 * std::size_t(count) > n)
            return false;
        for (std::uint32_t k = 0; k < count; ++k) {
            const std::uint8_t* p = t + o + 16 + 16 * k;
            tone.parts.emplace_back(lef32(p + 8), static_cast<int>(le32(p + 12)));
        }
        std::size_t v = o + 16 + 16 * std::size_t(count);
        tone.volume_db = v + 4 <= n ? lef32(t + v) : 0.f;
        if (!std::isfinite(tone.volume_db)) tone.volume_db = 0;
        return true;
    }
    if (o + 16 > n || le32(t + o + 4) != 8) return false;
    tone.pack_offset = le32(t + o + 8);
    tone.pack_size = le32(t + o + 12);
    if (o + 28 <= n) {
        tone.volume_db = lef32(t + o + 16);
        tone.pan = lef32(t + o + 20);
        tone.cents = lef32(t + o + 24);
    }
    for (float* f : {&tone.volume_db, &tone.pan, &tone.cents})
        if (!std::isfinite(*f)) *f = 0;
    return true;
}

} // namespace

bool Bank::open(ReadAt read, std::uint64_t size, std::string* error) {
    read_ = std::move(read);
    size_ = size;
    tones_.clear();
    std::vector<std::uint8_t> head;
    if (size < 24 || !read_(0, static_cast<std::size_t>(std::min<std::uint64_t>(size, 512)), head) ||
        std::memcmp(head.data(), "NUS3", 4) != 0 || std::memcmp(head.data() + 8, "BANKTOC ", 8) != 0) {
        set(error, "not a sound bank");
        return false;
    }
    std::uint32_t toc = le32(head.data() + 16), count = le32(head.data() + 20);
    if (count > 32 || 24 + 8 * std::size_t(count) > head.size()) {
        set(error, "sound bank table out of range");
        return false;
    }
    std::uint64_t pos = 0x14 + std::uint64_t(toc);
    std::uint64_t tone_at = 0, tone_size = 0;
    bool have_tone = false;
    for (std::uint32_t i = 0; i < count; ++i) {
        const std::uint8_t* tag = head.data() + 24 + 8 * i;
        std::uint64_t chunk = le32(tag + 4);
        if (pos + 8 + chunk > size) {
            set(error, "sound bank chunk past its end");
            return false;
        }
        if (std::memcmp(tag, "TONE", 4) == 0) {
            tone_at = pos + 8;
            tone_size = chunk;
            have_tone = true;
        } else if (std::memcmp(tag, "PACK", 4) == 0) {
            pack_ = pos + 8;
            pack_size_ = chunk;
        } else if (std::memcmp(tag, "BINF", 4) == 0) {
            std::vector<std::uint8_t> binf;
            if (chunk >= 9 && chunk < 512 && read_(pos + 8, static_cast<std::size_t>(chunk), binf)) {
                std::size_t len = binf[8];
                if (len >= 1 && 9 + len <= binf.size()) name_.assign(reinterpret_cast<const char*>(&binf[9]), len - 1);
            }
        }
        pos += 8 + chunk;
    }
    std::vector<std::uint8_t> table;
    if (!have_tone || tone_size < 4 || tone_size > kMaxToneTable ||
        !read_(tone_at, static_cast<std::size_t>(tone_size), table)) {
        set(error, "sound bank without a tone table");
        return false;
    }
    std::uint32_t tones = le32(table.data());
    if (tones > 100000 || 4 + 8 * std::uint64_t(tones) > table.size()) {
        set(error, "sound bank tone table out of range");
        return false;
    }
    tones_.resize(tones);
    for (std::uint32_t i = 0; i < tones; ++i) {
        std::uint32_t o = le32(table.data() + 4 + 8 * i), s = le32(table.data() + 8 + 8 * i);
        if (std::uint64_t(o) + s > table.size()) continue;
        Tone tone;
        if (parse_tone(table.data() + o, s, tone)) tones_[i] = std::move(tone);
    }
    return true;
}

int Bank::find(std::string_view tone) const {
    for (std::size_t i = 0; i < tones_.size(); ++i)
        if (!tones_[i].name.empty() && tones_[i].name == tone) return static_cast<int>(i);
    return -1;
}

bool Bank::audio(int index, Pcm& out, std::string* error) const {
    if (index < 0 || std::size_t(index) >= tones_.size() || tones_[std::size_t(index)].link ||
        tones_[std::size_t(index)].name.empty()) {
        set(error, "no audio tone " + std::to_string(index));
        return false;
    }
    const Tone& t = tones_[std::size_t(index)];
    if (t.pack_size == 0 || t.pack_size > kMaxToneAudio || std::uint64_t(t.pack_offset) + t.pack_size > pack_size_) {
        set(error, "tone " + t.name + ": audio out of range");
        return false;
    }
    std::vector<std::uint8_t> bytes;
    if (!read_(pack_ + t.pack_offset, t.pack_size, bytes)) {
        set(error, "tone " + t.name + ": cannot read its audio");
        return false;
    }
    std::string why;
    if (!decode_audio(bytes.data(), bytes.size(), out, &why)) {
        set(error, "tone " + t.name + ": " + why);
        return false;
    }
    return true;
}

bool Bank::render(int index, Clip& out, std::string* error) const {
    out.samples.clear();
    if (index < 0 || std::size_t(index) >= tones_.size() || tones_[std::size_t(index)].name.empty()) {
        set(error, "no tone " + std::to_string(index));
        return false;
    }
    const Tone& top = tones_[std::size_t(index)];
    std::vector<std::pair<float, int>> parts = top.link ? top.parts : std::vector<std::pair<float, int>>{{1.f, index}};
    float link_db = top.link ? top.volume_db : 0.f;
    bool any = false;
    for (auto [weight, part] : parts) {
        if (part < 0 || std::size_t(part) >= tones_.size() || tones_[std::size_t(part)].link) continue;
        const Tone& t = tones_[std::size_t(part)];
        if (t.name.empty() || t.volume_db <= -60.f || !(weight > 0.f)) continue; // a silenced side
        Pcm pcm;
        if (!audio(part, pcm, error)) return false;
        double rate = pcm.rate * std::pow(2.0, std::clamp(t.cents, -2400.f, 2400.f) / 1200.0);
        float gain = weight * std::pow(10.f, (t.volume_db + link_db) / 20.f);
        float p = std::clamp(t.pan / 90.f, -1.f, 1.f), th = (p + 1) * 0.78539816f;
        float gl = std::cos(th) * 1.41421356f * gain, gr = std::sin(th) * 1.41421356f * gain;
        std::size_t frames = pcm.frames();
        if (frames == 0 || frames / rate > kMaxRenderSeconds) continue;
        std::vector<float> side[2];
        for (int c = 0; c < 2; ++c) {
            std::vector<float> ch(frames);
            int src = std::min(c, pcm.channels - 1);
            for (std::size_t i = 0; i < frames; ++i)
                ch[i] = pcm.samples[i * std::size_t(pcm.channels) + std::size_t(src)] / 32768.f;
            side[c] = resample(ch, rate);
            if (pcm.channels == 1) {
                side[1] = side[0];
                break;
            }
        }
        std::size_t n = side[0].size();
        if (out.samples.size() < 2 * n) out.samples.resize(2 * n, 0.f);
        for (std::size_t i = 0; i < n; ++i) {
            out.samples[2 * i] += side[0][i] * gl;
            out.samples[2 * i + 1] += side[1][i] * gr;
        }
        any = true;
    }
    if (!any) {
        set(error, "tone " + top.name + " plays nothing");
        return false;
    }
    return true;
}

// ---- shaping ----

std::vector<float> resample(const std::vector<float>& in, double rate) {
    if (in.empty() || !(rate > 0)) return {};
    double step = rate / kRate; // input samples per output sample
    if (std::fabs(step - 1.0) < 1e-9) return in;
    double cutoff = std::min(1.0, 1.0 / step);     // of the input's Nyquist
    double radius = std::min(64.0, 12.0 / cutoff); // input samples each side
    std::size_t out_n = static_cast<std::size_t>(std::ceil(static_cast<double>(in.size()) / step));
    std::vector<float> out(out_n);
    const double pi = 3.14159265358979323846;
    for (std::size_t j = 0; j < out_n; ++j) {
        double x = static_cast<double>(j) * step;
        long lo = static_cast<long>(std::ceil(x - radius)), hi = static_cast<long>(std::floor(x + radius));
        double sum = 0, wsum = 0;
        for (long k = lo; k <= hi; ++k) {
            double t = x - static_cast<double>(k);
            double s = t == 0 ? 1.0 : std::sin(pi * cutoff * t) / (pi * cutoff * t);
            double w = 0.42 + 0.5 * std::cos(pi * t / radius) + 0.08 * std::cos(2 * pi * t / radius); // Blackman
            double h = s * w;
            wsum += h;
            if (k >= 0 && static_cast<std::size_t>(k) < in.size()) sum += h * in[static_cast<std::size_t>(k)];
        }
        out[j] = static_cast<float>(wsum != 0 ? sum / wsum : 0);
    }
    return out;
}

float peak(const Clip& clip) {
    float p = 0;
    for (float s : clip.samples) p = std::max(p, std::fabs(s));
    return p;
}

float loudness_db(const Clip& clip) {
    // How loud it sounds rather than how much energy it has: the K-weighting of ITU-R BS.1770 (a high shelf from
    // ~1.5 kHz and a high-pass below ~100 Hz; its coefficients for 48 kHz), then the loudest 50 ms.
    const std::size_t window = kRate / 20, hop = kRate / 100, frames = clip.frames();
    if (frames == 0) return -120.f;
    std::vector<double> weighted(frames);
    for (int c = 0; c < 2; ++c) {
        double x1 = 0, x2 = 0, y1 = 0, y2 = 0, z1 = 0, z2 = 0;
        for (std::size_t i = 0; i < frames; ++i) {
            double x = clip.samples[2 * i + std::size_t(c)];
            double y = 1.53512485958697 * x - 2.69169618940638 * x1 + 1.19839281085285 * x2 + 1.69065929318241 * y1 -
                       0.73248077421585 * y2;
            x2 = x1;
            x1 = x;
            double z = y - 2 * y1 + y2 + 1.99004745483398 * z1 - 0.99007225036621 * z2;
            y2 = y1;
            y1 = y;
            z2 = z1;
            z1 = z;
            weighted[i] += z * z;
        }
    }
    double best = 0;
    for (std::size_t start = 0;; start += hop) {
        std::size_t end = std::min(frames, start + window);
        double e = 0;
        for (std::size_t i = start; i < end; ++i) e += weighted[i];
        best = std::max(best, e / (2.0 * double(window)));
        if (end >= frames) break;
    }
    return best > 1e-12 ? static_cast<float>(10.0 * std::log10(best)) : -120.f;
}

void finish(Clip& clip, const CueLevel& level) {
    std::size_t frames = clip.frames();
    float top = peak(clip);
    if (frames == 0 || top <= 0) {
        clip.samples.clear();
        return;
    }
    auto loud = [&](std::size_t i, float t) {
        return std::fabs(clip.samples[2 * i]) > t || std::fabs(clip.samples[2 * i + 1]) > t;
    };
    // Silence before (the sound starts on the press: 2 ms kept before -40 dB of its peak) and after (-60 dB).
    std::size_t first = 0;
    while (first < frames && !loud(first, top * 0.01f)) ++first;
    first = first > kRate / 500 ? first - kRate / 500 : 0;
    std::size_t last = frames;
    while (last > first && !loud(last - 1, top * 0.001f)) --last;
    std::size_t keep = std::min<std::size_t>(last - first, static_cast<std::size_t>(level.max_seconds * kRate));
    std::vector<float> s(clip.samples.begin() + std::ptrdiff_t(2 * first),
                         clip.samples.begin() + std::ptrdiff_t(2 * (first + keep)));
    clip.samples.swap(s);
    frames = keep;
    // A short fade in (no click where it was cut) and a fade out over the last quarter (at most 80 ms) when cut.
    std::size_t in = std::min<std::size_t>(frames, kRate / 1000);
    for (std::size_t i = 0; i < in; ++i)
        for (int c = 0; c < 2; ++c)
            clip.samples[2 * i + std::size_t(c)] *= static_cast<float>(i) / static_cast<float>(in);
    if (first + keep < last) {
        std::size_t fade = std::min<std::size_t>(frames / 4, kRate * 80 / 1000);
        for (std::size_t i = 0; i < fade; ++i) {
            float g = 0.5f + 0.5f * std::cos(3.14159265f * static_cast<float>(i + 1) / static_cast<float>(fade));
            for (int c = 0; c < 2; ++c) clip.samples[2 * (frames - fade + i) + std::size_t(c)] *= g;
        }
    }
    float now = loudness_db(clip);
    if (now <= -119.f) {
        clip.samples.clear();
        return;
    }
    float gain = std::pow(10.f, (level.loudness_db - now) / 20.f);
    float p = peak(clip);
    if (p * gain > kPeakLimit) gain = kPeakLimit / p;
    for (float& v : clip.samples) v *= gain;
}

std::vector<std::uint8_t> wav_file(const Clip& clip) {
    std::vector<std::uint8_t> out;
    auto u32 = [&](std::uint32_t v) {
        for (int i = 0; i < 4; ++i) out.push_back(static_cast<std::uint8_t>(v >> (8 * i)));
    };
    auto u16 = [&](std::uint16_t v) {
        out.push_back(static_cast<std::uint8_t>(v));
        out.push_back(static_cast<std::uint8_t>(v >> 8));
    };
    auto tag = [&](const char* t) { out.insert(out.end(), t, t + 4); };
    std::uint32_t data = static_cast<std::uint32_t>(clip.samples.size() * 2);
    tag("RIFF");
    u32(36 + data);
    tag("WAVE");
    tag("fmt ");
    u32(16);
    u16(1);
    u16(2);
    u32(kRate);
    u32(kRate * 4);
    u16(4);
    u16(16);
    tag("data");
    u32(data);
    for (float s : clip.samples) {
        long v = std::lround(std::clamp(s, -1.f, 1.f) * 32767.f);
        u16(static_cast<std::uint16_t>(static_cast<std::int16_t>(v)));
    }
    return out;
}

// ---- the cues ----

namespace {

// A bank of the install: stored as it is (as every sound bank of the game) and then read in parts, or scrambled and
// then read whole.
std::shared_ptr<Bank> open_bank(Archives& archives, const std::string& name, std::string& error) {
    auto entry = archives.find(name_key(name + ".nus3bank"), &error);
    if (!entry) return nullptr;
    Entry e = *entry;
    std::vector<std::uint8_t> magic;
    ReadAt reader;
    if (read_file_at(e.bin, e.start, 4, magic) && std::memcmp(magic.data(), "NUS3", 4) == 0) {
        reader = [e](std::uint64_t offset, std::size_t size, std::vector<std::uint8_t>& out) {
            return offset + size <= e.size && read_file_at(e.bin, e.start + offset, size, out);
        };
    } else {
        auto whole = std::make_shared<std::vector<std::uint8_t>>();
        if (e.size > kMaxScrambledBank || !read_file_at(e.bin, e.start, static_cast<std::size_t>(e.size), *whole)) {
            error = "cannot read entry " + hex8(e.key);
            return nullptr;
        }
        scramble(whole->data(), whole->size(), e.key);
        reader = [whole](std::uint64_t offset, std::size_t size, std::vector<std::uint8_t>& out) {
            if (offset + size > whole->size()) return false;
            out.assign(whole->begin() + std::ptrdiff_t(offset), whole->begin() + std::ptrdiff_t(offset + size));
            return true;
        };
    }
    auto bank = std::make_shared<Bank>();
    if (!bank->open(reader, e.size, &error)) return nullptr;
    return bank;
}

} // namespace

Loaded load_cues(const fs::path& root) {
    Loaded loaded;
    try {
        auto hdd = find_archives(root);
        if (!hdd) {
            loaded.log.push_back("no game archives under " + root.string());
            return loaded;
        }
        loaded.archives = *hdd;
        Archives archives(*hdd);
        std::map<std::string, std::shared_ptr<Bank>> banks; // nullptr: could not be opened (logged once)
        for (int cue = 0; cue < kCueCount; ++cue) {
            const CueSource& src = cue_sources()[std::size_t(cue)];
            auto it = banks.find(src.bank);
            if (it == banks.end()) {
                std::string error;
                it = banks.emplace(src.bank, open_bank(archives, src.bank, error)).first;
                if (!it->second) loaded.log.push_back(std::string(src.bank) + ": " + error);
            }
            const auto& bank = it->second;
            if (!bank) continue;
            int tone = bank->find(src.tone);
            std::string error;
            Clip clip;
            if (tone < 0)
                error = std::string("no tone ") + src.tone;
            else if (bank->render(tone, clip, &error)) {
                finish(clip, cue_levels()[std::size_t(cue)]);
                if (clip.empty()) error = std::string(src.tone) + " is silent";
            }
            if (!clip.empty() && error.empty())
                loaded.clips[std::size_t(cue)] = std::move(clip);
            else
                loaded.log.push_back(std::string(src.bank) + ": " + (error.empty() ? "unreadable" : error));
        }
    } catch (const std::exception& e) {
        loaded.log.push_back(std::string("reading the game's sounds failed: ") + e.what());
    }
    return loaded;
}

} // namespace launcher::game_sounds
