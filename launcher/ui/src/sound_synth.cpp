// The launcher's own sounds (before the game is installed, or when its sounds cannot be read), made in code: a
// fighting game's menu rather than a computer's beeps - short metallic hits and pings, filtered-noise whooshes with
// a moving pan, a low impact under the accepts, a guard-like thud for a refusal, a struck chime for a finished task
// and a full impact (sub drop, crash, ring) for Play. The same numbers every run (seeded noise).
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

#include "ttt2ui/sound.h"

namespace ttt2::ui {

namespace {

namespace gs = launcher::game_sounds;

constexpr double kPi = 3.14159265358979323846;
constexpr double kFs = gs::kRate;

// A stereo buffer being made: sounds are added at a time (s) with a pan (-1 left .. 1 right).
struct Mix {
    std::vector<float> l, r;
    explicit Mix(double seconds) : l(static_cast<std::size_t>(seconds * kFs)), r(l.size()) {}
    std::size_t size() const { return l.size(); }
    void add(std::size_t i, float v, float pan = 0) {
        if (i >= l.size()) return;
        double th = (std::clamp(pan, -1.f, 1.f) + 1) * kPi / 4;
        l[i] += static_cast<float>(v * std::cos(th) * 1.41421356);
        r[i] += static_cast<float>(v * std::sin(th) * 1.41421356);
    }
    void add2(std::size_t i, float vl, float vr) {
        if (i >= l.size()) return;
        l[i] += vl;
        r[i] += vr;
    }
};

struct Noise {
    std::uint64_t s;
    explicit Noise(std::uint64_t seed) : s(seed ? seed : 1) {}
    float next() { // white, -1..1
        s ^= s >> 12;
        s ^= s << 25;
        s ^= s >> 27;
        return static_cast<float>(static_cast<double>((s * 0x2545f4914f6cdd1dull) >> 11) / 4503599627370496.0 - 1.0);
    }
};

// A state-variable filter (topology-preserving, stable at any cutoff).
struct Svf {
    double ic1 = 0, ic2 = 0;
    double lp = 0, bp = 0, hp = 0;
    void step(double x, double fc, double q) {
        double g = std::tan(kPi * std::clamp(fc, 20.0, 0.45 * kFs) / kFs), k = 1 / q;
        double a1 = 1 / (1 + g * (g + k)), a2 = g * a1, a3 = g * a2;
        double v3 = x - ic2, v1 = a1 * ic1 + a2 * v3, v2 = ic2 + a2 * ic1 + a3 * v3;
        ic1 = 2 * v1 - ic1;
        ic2 = 2 * v2 - ic2;
        lp = v2;
        bp = v1;
        hp = x - k * v1 - v2;
    }
};

double expo(double t, double tau) { return t < 0 ? 0 : std::exp(-t / tau); }
// from a to b along t/len, exponentially (frequencies)
double sweep(double a, double b, double t, double len) { return a * std::pow(b / a, std::clamp(t / len, 0.0, 1.0)); }
double rise(double t, double attack) { return t < 0 ? 0 : (t >= attack ? 1 : std::sin(0.5 * kPi * t / attack)); }

// A metallic ping: inharmonic partials (bar / plate ratios) decaying faster the higher they are.
void ping(Mix& m, double at, double f0, double tau, float level, float pan = 0, double detune = 0) {
    static const double ratio[] = {1.0, 2.756, 5.404, 8.933};
    static const double amp[] = {1.0, 0.55, 0.32, 0.18};
    std::size_t start = static_cast<std::size_t>(at * kFs), n = static_cast<std::size_t>(tau * 7 * kFs);
    for (std::size_t i = 0; i < n; ++i) {
        double t = static_cast<double>(i) / kFs, v = 0;
        for (int p = 0; p < 4; ++p) {
            double f = f0 * ratio[p];
            if (f > 0.45 * kFs) continue;
            v += amp[p] * std::sin(2 * kPi * f * t) * expo(t, tau / (1 + 0.6 * p));
        }
        float a = static_cast<float>(v * level * rise(t, 0.0006));
        if (detune == 0)
            m.add(start + i, a, pan);
        else {
            double v2 = 0;
            for (int p = 0; p < 4; ++p) {
                double f = f0 * (1 + detune) * ratio[p];
                if (f > 0.45 * kFs) continue;
                v2 += amp[p] * std::sin(2 * kPi * f * t) * expo(t, tau / (1 + 0.6 * p));
            }
            m.add2(start + i, a, static_cast<float>(v2 * level * rise(t, 0.0006)));
        }
    }
}

// A struck bell (FM: the modulation dies away faster than the tone: bright strike, round ring).
void bell(Mix& m, double at, double f, double ratio, double index, double tau, float level, float pan = 0) {
    std::size_t start = static_cast<std::size_t>(at * kFs), n = static_cast<std::size_t>(tau * 6 * kFs);
    for (std::size_t i = 0; i < n; ++i) {
        double t = static_cast<double>(i) / kFs;
        double mod = index * expo(t, tau * 0.35) * std::sin(2 * kPi * f * ratio * t);
        double v = std::sin(2 * kPi * f * t + mod) * expo(t, tau) * rise(t, 0.001);
        m.add(start + i, static_cast<float>(v * level), pan);
    }
}

// A low impact: a sine falling in pitch, driven into soft clipping.
void thump(Mix& m, double at, double f_from, double f_to, double fall, double tau, float level, double drive = 2) {
    std::size_t start = static_cast<std::size_t>(at * kFs), n = static_cast<std::size_t>(tau * 7 * kFs);
    double phase = 0;
    for (std::size_t i = 0; i < n; ++i) {
        double t = static_cast<double>(i) / kFs;
        phase += 2 * kPi * sweep(f_from, f_to, t, fall) / kFs;
        double v = std::tanh(drive * std::sin(phase) * expo(t, tau) * rise(t, 0.002)) / std::tanh(drive);
        m.add(start + i, static_cast<float>(v * level));
    }
}

// Filtered noise: a band (bp) or everything below (lp) / above (hp) a cutoff moving from f_from to f_to over `len`,
// shaped by an attack and a decay; the pan moves from pan_from to pan_to. Each side its own noise (width).
enum class Band { Low, Pass, High };
void whoosh(Mix& m, double at, double len, double f_from, double f_to, double q, Band band, double attack, double tau,
            float level, float pan_from = 0, float pan_to = 0, std::uint64_t seed = 1) {
    std::size_t start = static_cast<std::size_t>(at * kFs), n = static_cast<std::size_t>((attack + tau * 6) * kFs);
    Noise nl(seed), nr(seed * 7919 + 13);
    Svf fl, fr;
    for (std::size_t i = 0; i < n; ++i) {
        double t = static_cast<double>(i) / kFs;
        double fc = sweep(f_from, f_to, t, len);
        fl.step(nl.next(), fc, q);
        fr.step(nr.next(), fc, q);
        double env = rise(t, attack) * (t < attack ? 1 : expo(t - attack, tau));
        double vl = band == Band::Low ? fl.lp : (band == Band::Pass ? fl.bp : fl.hp);
        double vr = band == Band::Low ? fr.lp : (band == Band::Pass ? fr.bp : fr.hp);
        float pan = pan_from + (pan_to - pan_from) * static_cast<float>(std::clamp(t / std::max(len, 1e-3), 0.0, 1.0));
        double th = (pan + 1) * kPi / 4;
        m.add2(start + i, static_cast<float>(vl * env * level * std::cos(th) * 1.41421356),
               static_cast<float>(vr * env * level * std::sin(th) * 1.41421356));
    }
}

// A short broadband click (the strike of a hit).
void click(Mix& m, double at, double fc, double tau, float level, std::uint64_t seed = 3) {
    whoosh(m, at, 0.01, fc, fc, 0.9, Band::High, 0.0003, tau, level, 0, 0, seed);
}

// A buzz: two detuned square-ish tones through a low-pass (the blocked "no").
void buzz(Mix& m, double at, double f, double detune, double tau, float level) {
    std::size_t start = static_cast<std::size_t>(at * kFs), n = static_cast<std::size_t>(tau * 6 * kFs);
    Svf lp;
    for (std::size_t i = 0; i < n; ++i) {
        double t = static_cast<double>(i) / kFs;
        double v = std::tanh(3 * std::sin(2 * kPi * f * t)) + std::tanh(3 * std::sin(2 * kPi * f * detune * t));
        lp.step(v, sweep(3600, 1100, t, tau * 2), 0.8);
        m.add(start + i, static_cast<float>(lp.lp * 0.5 * level * rise(t, 0.003) * expo(t, tau)));
    }
}

SoundClip to_clip(const Mix& m) {
    SoundClip c;
    c.samples.resize(2 * m.size());
    for (std::size_t i = 0; i < m.size(); ++i) {
        c.samples[2 * i] = m.l[i];
        c.samples[2 * i + 1] = m.r[i];
    }
    return c;
}

SoundClip build(Cue cue) {
    switch (cue) {
    case Cue::Move: { // a quick bright tick: a click and a small high ping
        Mix m(0.09);
        click(m, 0, 4500, 0.0015, 0.8f, 11);
        ping(m, 0, 2350, 0.012, 0.35f);
        return to_clip(m);
    }
    case Cue::Accept: { // "shing": a struck plate over a short low punch, a hiss of shimmer
        Mix m(0.7);
        click(m, 0, 2500, 0.004, 0.7f, 21);
        thump(m, 0, 210, 75, 0.05, 0.035, 0.4f, 2.5);
        ping(m, 0.004, 1180, 0.16, 0.45f, 0, 0.006);
        bell(m, 0.004, 2760, 1.41, 2.5, 0.09, 0.18f);
        whoosh(m, 0.0, 0.3, 9000, 6000, 0.7, Band::High, 0.004, 0.1, 0.12f, -0.3f, 0.3f, 22);
        return to_clip(m);
    }
    case Cue::Back: { // a falling whoosh and a soft low "thup"
        Mix m(0.36);
        whoosh(m, 0, 0.22, 4800, 650, 2.2, Band::Pass, 0.012, 0.06, 1.0f, 0.25f, -0.25f, 31);
        thump(m, 0.01, 150, 70, 0.05, 0.035, 0.35f);
        return to_clip(m);
    }
    case Cue::TabSwitch: { // a tag: a whoosh swelling across from left to right, a clack where it lands
        Mix m(0.42);
        whoosh(m, 0, 0.14, 700, 6500, 1.6, Band::Pass, 0.07, 0.07, 1.0f, -0.8f, 0.8f, 41);
        click(m, 0.075, 3200, 0.003, 0.45f, 42);
        ping(m, 0.075, 1560, 0.03, 0.18f, 0.6f);
        return to_clip(m);
    }
    case Cue::SectionSwitch: { // a short swish and a tick
        Mix m(0.24);
        whoosh(m, 0, 0.09, 1400, 5200, 1.8, Band::Pass, 0.025, 0.04, 0.9f, -0.35f, 0.35f, 51);
        click(m, 0.025, 4000, 0.0015, 0.4f, 52);
        ping(m, 0.025, 1980, 0.015, 0.2f);
        return to_clip(m);
    }
    case Cue::Toggle: { // a switch: two clacks, the second higher
        Mix m(0.16);
        click(m, 0, 3800, 0.0012, 0.6f, 61);
        ping(m, 0, 1760, 0.012, 0.3f);
        click(m, 0.045, 5200, 0.0012, 0.6f, 62);
        ping(m, 0.045, 2217, 0.016, 0.32f);
        return to_clip(m);
    }
    case Cue::Refuse: { // blocked: a dull guard thud and a short low buzz
        Mix m(0.38);
        whoosh(m, 0, 0.02, 900, 600, 0.8, Band::Low, 0.001, 0.025, 1.3f, 0, 0, 71);
        thump(m, 0, 120, 80, 0.04, 0.05, 0.6f, 3);
        buzz(m, 0.012, 155, 1.059, 0.09, 0.6f);
        return to_clip(m);
    }
    case Cue::DrillIn: { // a rising whoosh, a small ping as it arrives
        Mix m(0.38);
        whoosh(m, 0, 0.16, 800, 5200, 2.0, Band::Pass, 0.06, 0.05, 1.0f, -0.2f, 0.3f, 81);
        ping(m, 0.07, 1760, 0.05, 0.22f, 0.3f);
        return to_clip(m);
    }
    case Cue::DrillOut: { // the same, falling back
        Mix m(0.34);
        whoosh(m, 0, 0.15, 5200, 900, 2.0, Band::Pass, 0.02, 0.06, 1.0f, 0.3f, -0.2f, 91);
        ping(m, 0.015, 880, 0.04, 0.2f, -0.2f);
        return to_clip(m);
    }
    case Cue::TaskDone: { // a struck chime: two bright notes a fifth apart over a shimmer
        Mix m(1.1);
        click(m, 0, 3000, 0.003, 0.4f, 101);
        bell(m, 0, 1318.5, 1.0, 1.8, 0.22, 0.5f, -0.25f);
        bell(m, 0.11, 1975.5, 1.0, 1.8, 0.28, 0.5f, 0.25f);
        ping(m, 0.11, 3951, 0.08, 0.1f, 0.25f);
        whoosh(m, 0.1, 0.5, 7000, 9000, 0.7, Band::High, 0.05, 0.12, 0.06f, -0.5f, 0.5f, 102);
        return to_clip(m);
    }
    case Cue::TaskFailed: { // a falling fourth, low and gritty, with a thud on the second note
        Mix m(0.95);
        buzz(m, 0, 293.66, 1.004, 0.16, 0.5f);
        bell(m, 0, 587.3, 1.5, 1.2, 0.14, 0.15f);
        buzz(m, 0.16, 220.0, 1.005, 0.24, 0.6f);
        thump(m, 0.16, 110, 55, 0.08, 0.08, 0.35f, 2);
        return to_clip(m);
    }
    case Cue::Play: { // a full impact: sub drop, a crash closing down, a ringing strike, energy rising after it
        Mix m(1.4);
        thump(m, 0, 130, 45, 0.2, 0.16, 0.7f, 3);
        click(m, 0, 2000, 0.006, 0.9f, 111);
        whoosh(m, 0, 0.6, 9500, 1300, 0.7, Band::Low, 0.002, 0.24, 0.9f, -0.4f, 0.4f, 112);
        bell(m, 0.003, 620, 2.756, 4.0, 0.42, 0.4f, -0.15f);
        ping(m, 0.003, 1530, 0.2, 0.18f, 0.2f, 0.004);
        whoosh(m, 0.12, 0.45, 900, 8000, 3.0, Band::Pass, 0.25, 0.12, 0.25f, 0.5f, -0.5f, 113);
        return to_clip(m);
    }
    }
    return {};
}

} // namespace

SoundClip synthesize(Cue cue) {
    int index = static_cast<int>(cue);
    if (index < 0 || index >= kCueCount) return {};
    SoundClip c = build(cue);
    gs::finish(c, gs::cue_levels()[static_cast<std::size_t>(index)]);
    return c;
}

} // namespace ttt2::ui
