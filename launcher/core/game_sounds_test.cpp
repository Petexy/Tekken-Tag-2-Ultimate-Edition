// game_sounds: the archives, banks and audio of the game read from MADE-UP files written here (no game data in the
// repository), checked against values the project's Python readers give for the same made-up input
// (tools/characters/ttt2char/ttt2/archive.py, dsp.py). Argument: a scratch folder (the build folder).
#include "game_sounds.h"
#include "game_sounds_fixture.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <string>
#include <vector>

namespace gs = launcher::game_sounds;
namespace fs = std::filesystem;
using namespace game_sounds_fixture;

namespace {

int g_failed = 0, g_checks = 0;
void check(bool ok, const char* what, int line) {
    ++g_checks;
    if (!ok) {
        ++g_failed;
        std::printf("FAIL line %d: %s\n", line, what);
    }
}
#define CHECK(c) check((c), #c, __LINE__)

gs::ReadAt reader(const Bytes& b) {
    return [&b](std::uint64_t o, std::size_t n, std::vector<std::uint8_t>& out) {
        if (o + n > b.size()) return false;
        out.assign(b.begin() + std::ptrdiff_t(o), b.begin() + std::ptrdiff_t(o + n));
        return true;
    };
}
int zero_crossings(const gs::Clip& c, int channel) {
    int n = 0;
    for (std::size_t i = 1; i < c.frames(); ++i)
        n += (c.samples[2 * (i - 1) + std::size_t(channel)] < 0) != (c.samples[2 * i + std::size_t(channel)] < 0);
    return n;
}
float channel_peak(const gs::Clip& c, int channel) {
    float p = 0;
    for (std::size_t i = 0; i < c.frames(); ++i) p = std::max(p, std::fabs(c.samples[2 * i + std::size_t(channel)]));
    return p;
}

// ---- tests ----

void test_keys_and_scramble() {
    CHECK(gs::name_key("se_Aly_Basic.nus3bank") == 0x4c67b8a7u); // (archive.key_of, a name, not data)
    CHECK(gs::name_key("se_Btl_Battle.nus3bank") == 0xd1870ef8u);
    CHECK(gs::name_key("a") == 0xc54aae31u);
    CHECK(gs::name_key("") == 0xffffffffu);
    const std::uint8_t expect[48] = {0xb3, 0x28, 0x55, 0x1e, 0xdb, 0x6d, 0xcb, 0x21, 0xb3, 0x1e, 0x44, 0x68,
                                     0x75, 0x57, 0x62, 0xeb, 0x68, 0x2d, 0x1c, 0x11, 0x03, 0xd7, 0xe3, 0xc2,
                                     0xfc, 0x78, 0xc7, 0xbf, 0xa3, 0xd4, 0x55, 0x00, 0x2f, 0x06, 0xfb, 0xaa,
                                     0x3e, 0xd1, 0x62, 0x4d, 0xfd, 0x61, 0xbd, 0x74, 0xd4, 0xf9, 0x7b, 0xd7};
    Bytes d(48);
    for (int i = 0; i < 48; ++i) d[std::size_t(i)] = static_cast<std::uint8_t>(i);
    gs::scramble(d.data(), d.size(), 0x12345678u); // archive.scramble(bytes(range(48)), 0x12345678)
    CHECK(std::memcmp(d.data(), expect, 48) == 0);
    Bytes tail(16);
    for (int i = 0; i < 16; ++i) tail[std::size_t(i)] = static_cast<std::uint8_t>(32 + i);
    gs::scramble(tail.data(), tail.size(), 0x12345678u, 32);
    CHECK(std::memcmp(tail.data(), expect + 32, 16) == 0);
    gs::scramble(d.data(), d.size(), 0x12345678u);
    CHECK(d[0] == 0 && d[47] == 47);
}

void test_dsp_adpcm() {
    // dsp.decode(frames, coefs, 81) of the Python reader (clamping on both sides included).
    const std::int16_t coefs[16] = {0,    0,   2048, 0,     3900, -1900, 1200, 600,
                                    -500, 300, 4000, -2000, 2047, -1024, 100,  -100};
    const Bytes frames = {0x00, 0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0x1b, 0x7f, 0x80, 0x08,
                          0xf0, 0x11, 0x22, 0x33, 0x2c, 0x87, 0x65, 0x43, 0x21, 0x0f, 0xed, 0xcb,
                          0x5f, 0x77, 0x77, 0x77, 0x77, 0x77, 0x77, 0x77, 0x6f, 0x88, 0x88, 0x88,
                          0x88, 0x88, 0x88, 0x88, 0x73, 0x1e, 0x2d, 0x3c, 0x4b, 0x5a, 0x69, 0x78};
    const std::vector<int> expect = {
        1,      2,      3,      4,      5,      6,      7,      -8,     -7,     -6,     -5,     -4,     -3,     -2,
        14334,  12286,  -4098,  -4098,  -4098,  -20482, -22530, -22530, -20482, -18434, -14338, -10242, -4098,  2046,
        -25070, -20967, 7907,   32767,  32767,  32767,  32767,  32767,  31999,  26441,  12473,  -13066, -32768, -32768,
        32767,  32767,  32767,  32767,  32767,  32767,  32767,  32767,  32767,  32767,  32767,  32767,  32767,  32767,
        -32768, -32768, -32768, -32768, -32768, -32768, -32768, -32768, -32768, -32768, -32768, -32768, -32768, -32768,
        8,      1584,   93,     -97,    15,     -27,    30,     -37,    37,     -44,    44};
    std::vector<std::int16_t> out;
    CHECK(gs::decode_dsp_adpcm(frames.data(), frames.size(), coefs, expect.size(), out));
    bool same = out.size() == expect.size();
    for (std::size_t i = 0; same && i < out.size(); ++i) same = out[i] == expect[i];
    CHECK(same);
    // More samples asked than the data has: what there is. A predictor past 8: refused.
    CHECK(gs::decode_dsp_adpcm(frames.data(), 16, coefs, 1000, out) && out.size() == 28);
    const Bytes bad = {0x80, 0, 0, 0, 0, 0, 0, 0};
    CHECK(!gs::decode_dsp_adpcm(bad.data(), bad.size(), coefs, 14, out));
}

void test_idsp_and_wave() {
    // Two channels of different lengths of steps, 16-byte interleave over several blocks.
    std::vector<int> a = sine_codes(1000, 36000, 300), b(300);
    for (int i = 0; i < 300; ++i) b[std::size_t(i)] = (i / 7) % 2 ? 5 : -5;
    Bytes ca = adpcm_steps(a), cb = adpcm_steps(b);
    Bytes file = idsp({ca, cb}, 36000, 300);
    gs::Pcm pcm;
    std::string error;
    CHECK(gs::decode_idsp(file.data(), file.size(), pcm, &error));
    CHECK(pcm.rate == 36000 && pcm.channels == 2 && pcm.frames() == 300);
    bool same = pcm.frames() == 300;
    for (std::size_t i = 0; same && i < 300; ++i)
        same = pcm.samples[2 * i] == a[i] * 2048 && pcm.samples[2 * i + 1] == b[i] * 2048;
    CHECK(same);
    // Cut short: fewer samples, no failure; a bad header: refused.
    gs::Pcm cut;
    CHECK(gs::decode_idsp(file.data(), file.size() - 40, cut) && cut.frames() < 300 && cut.frames() > 250);
    Bytes broken = file;
    broken[11] = 9; // 9 channels
    CHECK(!gs::decode_idsp(broken.data(), broken.size(), cut));
    CHECK(!gs::decode_idsp(file.data(), 0x30, cut));

    std::vector<std::int16_t> st = {1, -1, 1000, -1000, 32767, -32768};
    Bytes w = wave(st, 2, 22050, true);
    CHECK(gs::decode_audio(w.data(), w.size(), pcm) && pcm.rate == 22050 && pcm.channels == 2 && pcm.samples == st);
    Bytes w8 = wave(st, 2, 22050, false, 8);
    gs::Pcm pcm8;
    CHECK(!gs::decode_wave(w8.data(), w8.size(), pcm8));
    const Bytes junk = {'O', 'G', 'G', 'S', 0, 0};
    CHECK(!gs::decode_audio(junk.data(), junk.size(), pcm));
}

void test_index() {
    // Entry sizes that are and are not multiples of 16 (the low bits of an offset).
    Bytes ofs;
    put32be(ofs, 8 + 3 * 8);
    tag(ofs, "ofsi");
    for (std::uint32_t k : {1u, 2u, 3u}) {
        put32be(ofs, k);
        put32be(ofs, 0);
    }
    put32be(ofs, 8 + 4 * 4);
    tag(ofs, "ofsd");
    for (std::uint32_t o : {0x00u | 4u, 0x10u, 0x30u | 0xFu, 0x50u}) put32be(ofs, o);
    std::vector<gs::IndexEntry> e;
    CHECK(gs::parse_index(ofs.data(), ofs.size(), e) && e.size() == 3);
    CHECK(e.size() == 3 && e[0].size == 4 && e[1].start == 0x10 && e[1].size == 0x20 && e[2].start == 0x30 &&
          e[2].size == 0x1F);
    Bytes cut(ofs.begin(), ofs.end() - 4);
    CHECK(!gs::parse_index(cut.data(), cut.size(), e));
}

std::vector<MadeTone> menu_like_tones() {
    std::vector<MadeTone> t;
    MadeTone sine{"beep",
                  wave(
                      [] {
                          std::vector<std::int16_t> s(4800);
                          for (std::size_t i = 0; i < s.size(); ++i)
                              s[i] = static_cast<std::int16_t>(16000 * std::sin(2 * kPi * 1000 * double(i) / 48000));
                          return s;
                      }(),
                      1, 48000)};
    t.push_back(MadeTone::place()); // 0: an empty place
    t.push_back(sine);              // 1: a 1 kHz tone, 0.1 s
    MadeTone up = sine;
    up.name = "beep_up";
    up.cents = 1200; // 2: an octave up
    t.push_back(up);
    MadeTone left = sine, right = sine;
    left.name = "lnk_left";
    left.pan = -90;
    right.name = "lnk_right";
    right.pan = 90;
    right.volume = -6.0206f;
    t.push_back(left);                                         // 3
    t.push_back(right);                                        // 4
    t.push_back(MadeTone::link("pair", {{1.f, 3}, {1.f, 4}})); // 5: link to 3 + 4
    MadeTone muted = sine;
    muted.name = "muted";
    muted.volume = -90;
    t.push_back(muted);                                             // 6
    t.push_back(MadeTone::link("left_only", {{1.f, 3}, {1.f, 6}})); // 7: link to 3 + silenced 6
    MadeTone adpcm{"steps", idsp({adpcm_steps(sine_codes(500, 32000, 3200))}, 32000, 3200)};
    t.push_back(adpcm);                                               // 8: IDSP mono
    t.push_back(MadeTone("broken", Bytes{'I', 'D', 'S', 'P', 0, 0})); // 9: unreadable audio
    return t;
}

void test_bank() {
    Bytes b = bank("se_Made_Up", menu_like_tones());
    gs::Bank bank;
    std::string error;
    CHECK(bank.open(reader(b), b.size(), &error));
    CHECK(bank.name() == "se_Made_Up");
    CHECK(bank.tones().size() == 10);
    CHECK(bank.find("beep") == 1 && bank.find("pair") == 5 && bank.find("nothing") == -1 && bank.find("") == -1);
    CHECK(bank.tones()[5].link && bank.tones()[5].parts.size() == 2 && bank.tones()[5].parts[1].second == 4);
    CHECK(bank.tones()[4].pan == 90 && std::fabs(bank.tones()[4].volume_db + 6.0206f) < 1e-4f);
    gs::Clip c;
    CHECK(bank.render(1, c) && c.frames() == 4800);
    CHECK(zero_crossings(c, 0) >= 198 && zero_crossings(c, 0) <= 201); // 1 kHz for 0.1 s
    CHECK(std::fabs(channel_peak(c, 0) - 16000.f / 32768.f) < 0.01f &&
          std::fabs(channel_peak(c, 1) - channel_peak(c, 0)) < 1e-6f);
    gs::Clip up;
    CHECK(bank.render(2, up) && up.frames() >= 2399 && up.frames() <= 2401); // an octave up: half as long, 2 kHz
    CHECK(zero_crossings(up, 0) >= 197 && zero_crossings(up, 0) <= 201);
    gs::Clip pair;
    CHECK(bank.render(5, pair));
    // Hard left at 0 dB + hard right at -6 dB: each on its side only.
    CHECK(std::fabs(channel_peak(pair, 0) - 1.41421356f * 16000.f / 32768.f) < 0.01f);
    CHECK(std::fabs(channel_peak(pair, 1) - 0.5f * 1.41421356f * 16000.f / 32768.f) < 0.01f);
    gs::Clip lo;
    CHECK(bank.render(7, lo) && channel_peak(lo, 1) < 1e-3f && channel_peak(lo, 0) > 0.5f);
    gs::Clip steps;
    CHECK(bank.render(8, steps) && steps.frames() == 4800); // 32 kHz -> 48 kHz
    CHECK(!bank.render(9, c, &error) && !error.empty());
    CHECK(!bank.render(0, c) && !bank.render(42, c));
    // Not a bank; a bank cut short (its tone table past the end).
    Bytes junk(64, 0);
    CHECK(!bank.open(reader(junk), junk.size()));
    Bytes cut(b.begin(), b.begin() + 200);
    CHECK(!bank.open(reader(cut), cut.size()));
}

void test_shaping() {
    // Resampling keeps a level and a tone's pitch.
    std::vector<float> dc(3600, 0.5f);
    auto up = gs::resample(dc, 36000);
    CHECK(up.size() == 4800 && std::fabs(up[2400] - 0.5f) < 1e-4f);
    std::vector<float> s(36000);
    for (std::size_t i = 0; i < s.size(); ++i)
        s[i] = static_cast<float>(0.8 * std::sin(2 * kPi * 440 * double(i) / 36000));
    auto r = gs::resample(s, 36000);
    float p = 0;
    for (std::size_t i = 1000; i < r.size() - 1000; ++i) p = std::max(p, std::fabs(r[i]));
    CHECK(r.size() == 48000 && std::fabs(p - 0.8f) < 0.01f);
    // A tone far above the output's range (rendered an octave and more up) is filtered out, not aliased down.
    std::vector<float> hi(96000);
    for (std::size_t i = 0; i < hi.size(); ++i)
        hi[i] = static_cast<float>(std::sin(2 * kPi * 30000 * double(i) / 96000));
    auto d = gs::resample(hi, 96000);
    float dp = 0;
    for (std::size_t i = 500; i < d.size() - 500; ++i) dp = std::max(dp, std::fabs(d[i]));
    CHECK(dp < 0.02f);

    // finish: silence before dropped (2 ms kept), cut to max length with a fade, loudness set, peak limited.
    gs::Clip c;
    c.samples.assign(2 * 48000, 0.f);
    for (std::size_t i = 4800; i < 48000; ++i) {
        float v = static_cast<float>(0.3 * std::sin(2 * kPi * 300 * double(i) / 48000));
        c.samples[2 * i] = v;
        c.samples[2 * i + 1] = v;
    }
    gs::finish(c, {-20.f, 0.5f});
    CHECK(c.frames() == 24000);
    CHECK(std::fabs(gs::loudness_db(c) + 20.f) < 0.2f);
    CHECK(std::fabs(c.samples[2 * (c.frames() - 1)]) < 0.01f); // faded out at the cut
    bool silent_start = true;
    for (std::size_t i = 0; i < 90; ++i) silent_start = silent_start && c.samples[2 * i] == 0.f;
    CHECK(silent_start); // (the 2 ms kept before the sound: 96 frames of silence, the first 90 at least)
    gs::Clip loud;
    loud.samples.assign(2 * 4800, 0.f);
    for (std::size_t i = 0; i < 4800; ++i) loud.samples[2 * i] = loud.samples[2 * i + 1] = (i % 100 == 0) ? 1.f : 0.01f;
    gs::finish(loud, {-3.f, 1.f});
    CHECK(gs::peak(loud) <= gs::kPeakLimit + 1e-6f);
    gs::Clip silent;
    silent.samples.assign(200, 0.f);
    gs::finish(silent, {-20.f, 1.f});
    CHECK(silent.empty());
    Bytes w = gs::wav_file(c);
    CHECK(w.size() == 44 + c.samples.size() * 2 && std::memcmp(w.data(), "RIFF", 4) == 0 &&
          std::memcmp(w.data() + 8, "WAVEfmt ", 8) == 0);
}

void test_load_cues(const fs::path& scratch) {
    fs::path root = scratch / "game_sounds_fixture";
    std::error_code ec;
    fs::remove_all(root, ec);
    fs::path hdd = root / "game" / "content" / "hdd";

    // Each bank the cues name, with the cue's tone made up (a short IDSP or WAVE beep), in data028; a decoy copy of
    // one bank with silence in data005 (an earlier archive: the later one wins); se_online scrambled in data100.
    std::map<std::string, std::vector<MadeTone>> banks;
    for (int cue = 0; cue < gs::kCueCount; ++cue) {
        const auto& src = gs::cue_sources()[std::size_t(cue)];
        auto& tones = banks[src.bank];
        MadeTone t{src.tone, cue % 2 ? idsp({adpcm_steps(sine_codes(300 + 100 * cue, 36000, 7200))}, 36000, 7200)
                                     : wave(std::vector<std::int16_t>(4410, 0), 1, 44100)};
        if (cue % 2 == 0) {
            std::vector<std::int16_t> s(8820);
            for (std::size_t i = 0; i < s.size(); ++i)
                s[i] = static_cast<std::int16_t>(9000 * std::sin(2 * kPi * (400 + 50 * cue) * double(i) / 44100));
            t.audio = wave(s, 1, 44100);
        }
        tones.push_back(t);
    }
    std::vector<MadeEntry> d28, d100;
    for (auto& [name, tones] : banks) {
        MadeEntry e{gs::name_key(name + ".nus3bank"), bank(name, tones)};
        if (name == "se_online") {
            e.scrambled = true;
            d100.push_back(e);
        } else {
            d28.push_back(e);
        }
    }
    std::vector<MadeTone> quiet = {{"main_cursor", wave(std::vector<std::int16_t>(100, 0), 1, 48000)}};
    archive(hdd, "data005", {{gs::name_key("se_Aly_Basic.nus3bank"), bank("se_Aly_Basic", quiet)}});
    archive(hdd, "data000", {{0x1234u, Bytes(40, 1)}});
    archive(hdd, "data028", d28);
    archive(hdd, "data100", d100);

    CHECK(gs::find_archives(root) == hdd);
    CHECK(gs::find_archives(root / "game") == hdd);
    CHECK(gs::find_archives(hdd) == hdd);
    CHECK(!gs::find_archives(scratch / "nowhere"));
    CHECK(!gs::find_archives({}));

    gs::Archives archives(hdd);
    auto e = archives.find(gs::name_key("se_Aly_Basic.nus3bank"));
    CHECK(e && e->bin.filename() == "data028.bin");
    CHECK(!archives.find(0xDEADBEEFu));

    gs::Loaded all = gs::load_cues(root);
    CHECK(all.found() == gs::kCueCount);
    CHECK(all.log.empty());
    for (const auto& line : all.log) std::printf("  log: %s\n", line.c_str());
    for (int cue = 0; cue < gs::kCueCount; ++cue) {
        const auto& c = all.clips[std::size_t(cue)];
        const auto& level = gs::cue_levels()[std::size_t(cue)];
        CHECK(!c.empty() && c.seconds() <= level.max_seconds + 1e-3);
        CHECK(c.empty() || std::fabs(gs::loudness_db(c) - level.loudness_db) < 0.5f ||
              gs::peak(c) >= gs::kPeakLimit - 1e-4f);
    }

    // A tone gone and a bank broken: those cues only are empty (and logged); the rest still play the game's.
    banks["se_practice"][0].name = "renamed";
    Bytes broken = bank("se_Btl_Battle", banks["se_Btl_Battle"]);
    broken.resize(broken.size() / 2);
    std::vector<MadeEntry> again;
    for (auto& [name, tones] : banks)
        if (name != "se_online")
            again.push_back({gs::name_key(name + ".nus3bank"), name == "se_Btl_Battle" ? broken : bank(name, tones)});
    archive(hdd, "data028", again);
    gs::Loaded some = gs::load_cues(root);
    int battle = 0;
    for (int cue = 0; cue < gs::kCueCount; ++cue)
        battle += std::string(gs::cue_sources()[std::size_t(cue)].bank) == "se_Btl_Battle";
    CHECK(some.found() == gs::kCueCount - battle - 1);
    CHECK(some.clips[5].empty()); // Toggle (se_practice)
    bool logged_tone = false, logged_bank = false;
    for (const auto& line : some.log) {
        logged_tone = logged_tone || line.find("no tone pra_icon_glow01") != std::string::npos;
        logged_bank = logged_bank || line.rfind("se_Btl_Battle:", 0) == 0;
    }
    CHECK(logged_tone && logged_bank);

    // No install: nothing, said once.
    gs::Loaded none = gs::load_cues(scratch / "no_such_install");
    CHECK(none.found() == 0 && none.log.size() == 1 && none.archives.empty());
    fs::remove_all(root, ec);
}

} // namespace

int main(int argc, char** argv) {
    fs::path scratch = argc > 1 ? fs::path(argv[1]) : fs::temp_directory_path();
    test_keys_and_scramble();
    test_dsp_adpcm();
    test_idsp_and_wave();
    test_index();
    test_bank();
    test_shaping();
    test_load_cues(scratch);
    std::printf("%d checks, %d failed\n", g_checks, g_failed);
    return g_failed ? 1 : 0;
}
