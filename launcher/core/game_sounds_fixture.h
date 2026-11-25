// Made-up game files for the sound tests (launcher/core/game_sounds_test.cpp, launcher/ui/tests/sound_tests.cpp):
// archives, sound banks and audio laid out as the game's (see game_sounds.h), with made-up tones only. Test-only.
#pragma once

#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include "game_sounds.h"

namespace game_sounds_fixture {

namespace gs = launcher::game_sounds;
namespace fs = std::filesystem;
using Bytes = std::vector<std::uint8_t>;
inline constexpr double kPi = 3.14159265358979323846;

inline void put32le(Bytes& b, std::uint32_t v) {
    for (int i = 0; i < 4; ++i) b.push_back(static_cast<std::uint8_t>(v >> (8 * i)));
}
inline void put32be(Bytes& b, std::uint32_t v) {
    for (int i = 3; i >= 0; --i) b.push_back(static_cast<std::uint8_t>(v >> (8 * i)));
}
inline void put16be(Bytes& b, std::uint16_t v) {
    b.push_back(static_cast<std::uint8_t>(v >> 8));
    b.push_back(static_cast<std::uint8_t>(v));
}
inline void putf(Bytes& b, float f) {
    std::uint32_t u;
    std::memcpy(&u, &f, 4);
    put32le(b, u);
}
inline void pad4(Bytes& b) {
    while (b.size() % 4) b.push_back(0);
}
inline void tag(Bytes& b, const char* t) { b.insert(b.end(), t, t + std::strlen(t)); }

// ---- made-up audio ----

// DSP ADPCM with predictor 0 (coefficients 0, 0) and scale 11: each sample is code * 2048 (code -8..7).
inline Bytes adpcm_steps(const std::vector<int>& codes) {
    Bytes out;
    for (std::size_t i = 0; i < codes.size(); i += 14) {
        out.push_back(0x0B);
        for (std::size_t k = 0; k < 14; k += 2) {
            int a = i + k < codes.size() ? codes[i + k] : 0, b = i + k + 1 < codes.size() ? codes[i + k + 1] : 0;
            out.push_back(static_cast<std::uint8_t>((a & 15) << 4 | (b & 15)));
        }
    }
    return out;
}
inline std::vector<int> sine_codes(double hz, int rate, int samples) {
    std::vector<int> c(static_cast<std::size_t>(samples));
    for (int i = 0; i < samples; ++i)
        c[std::size_t(i)] = static_cast<int>(std::lround(7 * std::sin(2 * kPi * hz * i / rate)));
    return c;
}
// An IDSP file of per-channel ADPCM data (all channels the same length), interleaved 16 bytes at a time.
inline Bytes idsp(const std::vector<Bytes>& channels, std::uint32_t rate, std::uint32_t samples,
                  const std::vector<std::int16_t>& coefs = std::vector<std::int16_t>(16, 0)) {
    std::uint32_t ch = static_cast<std::uint32_t>(channels.size()),
                  size = static_cast<std::uint32_t>(channels[0].size());
    Bytes b;
    tag(b, "IDSP");
    for (std::uint32_t v : {0u, ch, rate, samples, 0u, 0u, 16u, 0x40u, 0x60u, 0x40u + 0x60u * ch, size}) put32be(b, v);
    b.resize(0x40, 0);
    for (std::uint32_t c = 0; c < ch; ++c) {
        std::size_t at = b.size();
        for (std::uint32_t v : {samples, samples / 14 * 16, rate}) put32be(b, v);
        b.resize(at + 0x1C, 0);
        for (auto v : coefs) put16be(b, static_cast<std::uint16_t>(v));
        b.resize(at + 0x60, 0);
    }
    for (std::uint32_t o = 0; o < size; o += 16)
        for (const auto& data : channels)
            for (std::uint32_t k = 0; k < 16; ++k) b.push_back(o + k < data.size() ? data[o + k] : 0);
    return b;
}
inline Bytes wave(const std::vector<std::int16_t>& interleaved, int channels, int rate, bool extra_chunk = false,
                  int bits = 16) {
    Bytes body;
    tag(body, "WAVE");
    if (extra_chunk) {
        tag(body, "LIST");
        put32le(body, 3);
        body.insert(body.end(), {'a', 'b', 'c', 0});
    }
    tag(body, "fmt ");
    put32le(body, 16);
    body.insert(body.end(), {1, 0, static_cast<std::uint8_t>(channels), 0});
    put32le(body, static_cast<std::uint32_t>(rate));
    put32le(body, static_cast<std::uint32_t>(rate * 2 * channels));
    body.insert(body.end(), {static_cast<std::uint8_t>(2 * channels), 0, static_cast<std::uint8_t>(bits), 0});
    tag(body, "data");
    put32le(body, static_cast<std::uint32_t>(interleaved.size() * 2));
    for (auto s : interleaved) {
        body.push_back(static_cast<std::uint8_t>(s));
        body.push_back(static_cast<std::uint8_t>(static_cast<std::uint16_t>(s) >> 8));
    }
    Bytes b;
    tag(b, "RIFF");
    put32le(b, static_cast<std::uint32_t>(body.size()));
    b.insert(b.end(), body.begin(), body.end());
    return b;
}

// ---- made-up banks (laid out as nus3bank.py writes them) ----

struct MadeTone {
    std::string name;
    Bytes audio; // an audio tone
    float volume = 0, pan = 0, cents = 0;
    std::vector<std::pair<float, std::uint32_t>> parts; // a link tone
    bool empty = false;                                 // an empty place
    MadeTone() = default;
    MadeTone(std::string n, Bytes a) : name(std::move(n)), audio(std::move(a)) {}
    static MadeTone place() {
        MadeTone t;
        t.empty = true;
        return t;
    }
    static MadeTone link(std::string n, std::vector<std::pair<float, std::uint32_t>> p) {
        MadeTone t;
        t.name = std::move(n);
        t.parts = std::move(p);
        return t;
    }
};
inline Bytes bank(const std::string& name, const std::vector<MadeTone>& tones) {
    Bytes pack, entries;
    std::vector<std::pair<std::uint32_t, std::uint32_t>> table;
    std::uint32_t start = 4 + 8 * static_cast<std::uint32_t>(tones.size());
    for (const auto& t : tones) {
        Bytes e;
        if (t.empty) {
            e.assign(8, 0);
        } else if (t.parts.empty()) {
            e = {0, 0, 0, 0, 0xFF, 0xFF, 0x67, 0x84, 0x7F, 0, 0, 0};
            e.push_back(static_cast<std::uint8_t>(t.name.size() + 1));
            tag(e, t.name.c_str());
            e.push_back(0);
            pad4(e);
            while (pack.size() % 16) pack.push_back(0);
            for (std::uint32_t v :
                 {0u, 8u, static_cast<std::uint32_t>(pack.size()), static_cast<std::uint32_t>(t.audio.size())})
                put32le(e, v);
            pack.insert(pack.end(), t.audio.begin(), t.audio.end());
            for (float f : {t.volume, t.pan, t.cents, 1.f, 1.f, -90.f}) putf(e, f);
            for (std::uint32_t v : {0xFFFFFFFFu, 0xFFFFFFFFu, 36000u, 1u, 1000u, 0u}) put32le(e, v);
        } else {
            e = {0, 0, 0, 0, 0x7F, 0, 0, 0};
            e.push_back(static_cast<std::uint8_t>(t.name.size() + 1));
            tag(e, t.name.c_str());
            e.push_back(0);
            pad4(e);
            std::uint32_t n = static_cast<std::uint32_t>(t.parts.size());
            for (std::uint32_t v : {1u, 8 + 16 * n, 0xFFFFFFFFu, n}) put32le(e, v);
            for (std::uint32_t k = 0; k < n; ++k) {
                put32le(e, k + 1 < n ? k + 1 : 0);
                put32le(e, 0);
                putf(e, t.parts[k].first);
                put32le(e, t.parts[k].second);
            }
            for (float f : {t.volume, 0.f, 0.f, 1.f, 1.f}) putf(e, f);
        }
        table.emplace_back(start + static_cast<std::uint32_t>(entries.size()), static_cast<std::uint32_t>(e.size()));
        entries.insert(entries.end(), e.begin(), e.end());
        pad4(entries);
    }
    Bytes tone;
    put32le(tone, static_cast<std::uint32_t>(tones.size()));
    for (auto [o, s] : table) {
        put32le(tone, o);
        put32le(tone, s);
    }
    tone.insert(tone.end(), entries.begin(), entries.end());
    Bytes binf;
    put32le(binf, 0);
    put32le(binf, 3);
    binf.push_back(static_cast<std::uint8_t>(name.size() + 1));
    tag(binf, name.c_str());
    binf.push_back(0);
    pad4(binf);
    put32le(binf, 7);
    std::vector<std::pair<const char*, Bytes>> chunks = {
        {"PROP", Bytes(4, 0)}, {"BINF", binf}, {"TONE", tone}, {"PACK", pack}};
    Bytes toc;
    put32le(toc, static_cast<std::uint32_t>(chunks.size()));
    for (auto& [t, d] : chunks) {
        tag(toc, t);
        put32le(toc, static_cast<std::uint32_t>(d.size()));
    }
    Bytes rest;
    tag(rest, "BANKTOC ");
    put32le(rest, static_cast<std::uint32_t>(toc.size()));
    rest.insert(rest.end(), toc.begin(), toc.end());
    for (auto& [t, d] : chunks) {
        tag(rest, t);
        put32le(rest, static_cast<std::uint32_t>(d.size()));
        rest.insert(rest.end(), d.begin(), d.end());
    }
    Bytes b;
    tag(b, "NUS3");
    put32le(b, static_cast<std::uint32_t>(rest.size()));
    b.insert(b.end(), rest.begin(), rest.end());
    return b;
}

// ---- made-up archives ----

inline void write_file(const fs::path& p, const Bytes& b) {
    fs::create_directories(p.parent_path());
    std::ofstream f(p, std::ios::binary | std::ios::trunc);
    f.write(reinterpret_cast<const char*>(b.data()), static_cast<std::streamsize>(b.size()));
}
struct MadeEntry {
    std::uint32_t key;
    Bytes contents;
    bool scrambled = false;
};
inline void archive(const fs::path& hdd, const std::string& name, const std::vector<MadeEntry>& entries) {
    Bytes bin(0x100, 0), ofsi, ofsd;
    for (const auto& e : entries) {
        Bytes stored = e.contents;
        if (e.scrambled) gs::scramble(stored.data(), stored.size(), e.key);
        std::uint32_t start = static_cast<std::uint32_t>(bin.size() - 0x100);
        put32be(ofsi, e.key);
        put32be(ofsi, 0);
        put32be(ofsd, start | static_cast<std::uint32_t>(stored.size() & 15));
        bin.insert(bin.end(), stored.begin(), stored.end());
        while (bin.size() % 16) bin.push_back(0xEE);
    }
    put32be(ofsd, static_cast<std::uint32_t>(bin.size() - 0x100));
    Bytes ofs;
    put32be(ofs, 0x14);
    tag(ofs, "ftypnrfo");
    put32be(ofs, 0x00010001);
    tag(ofs, "nrfo");
    put32be(ofs, static_cast<std::uint32_t>(8 + ofsi.size()));
    tag(ofs, "ofsi");
    ofs.insert(ofs.end(), ofsi.begin(), ofsi.end());
    put32be(ofs, static_cast<std::uint32_t>(8 + ofsd.size()));
    tag(ofs, "ofsd");
    ofs.insert(ofs.end(), ofsd.begin(), ofsd.end());
    write_file(hdd / (name + ".ofs"), ofs);
    write_file(hdd / (name + ".bin"), bin);
}
// An install (root/game/content/hdd) whose banks hold every cue's tone, made up: a tone per cue (IDSP or WAVE,
// a different pitch each), banks in data028, se_online scrambled in data100.
inline fs::path make_install(const fs::path& root) {
    std::error_code ec;
    fs::remove_all(root, ec);
    fs::path hdd = root / "game" / "content" / "hdd";
    std::map<std::string, std::vector<MadeTone>> banks;
    for (int cue = 0; cue < gs::kCueCount; ++cue) {
        const auto& src = gs::cue_sources()[std::size_t(cue)];
        if (cue % 2) {
            banks[src.bank].push_back(
                MadeTone(src.tone, idsp({adpcm_steps(sine_codes(300 + 100 * cue, 36000, 7200))}, 36000, 7200)));
        } else {
            std::vector<std::int16_t> s(8820);
            for (std::size_t i = 0; i < s.size(); ++i)
                s[i] = static_cast<std::int16_t>(9000 * std::sin(2 * kPi * (400 + 50 * cue) * double(i) / 44100));
            banks[src.bank].push_back(MadeTone(src.tone, wave(s, 1, 44100)));
        }
    }
    std::vector<MadeEntry> d28, d100;
    for (auto& [name, tones] : banks) {
        MadeEntry e{gs::name_key(name + ".nus3bank"), bank(name, tones)};
        e.scrambled = name == "se_online";
        (e.scrambled ? d100 : d28).push_back(e);
    }
    archive(hdd, "data000", {{0x1234u, Bytes(40, 1)}});
    archive(hdd, "data028", d28);
    archive(hdd, "data100", d100);
    return hdd;
}

} // namespace game_sounds_fixture
