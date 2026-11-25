// What installing needs of the player's PC that is the same on any OS (see
// system.h): the processor features a cpuinfo text lacks, os-release, and
// the package manager's commands for the hints. (system.cpp: Linux's own.)

#include "system.h"

#include <array>
#include <map>
#include <set>
#include <sstream>

namespace launcher {
namespace {

std::string unquote(std::string_view value) {
    if (value.size() >= 2 && (value.front() == '"' || value.front() == '\'') && value.back() == value.front()) {
        value = value.substr(1, value.size() - 2);
    }
    std::string out;
    for (size_t i = 0; i < value.size(); ++i) {
        if (value[i] == '\\' && i + 1 < value.size()) ++i;
        out += value[i];
    }
    return out;
}

enum class Family { kUnknown, kArch, kDebian, kFedora, kSuse };

Family family(const Distro& distro) {
    for (const std::string& id : distro.like) {
        if (id == "arch") return Family::kArch;
        if (id == "debian" || id == "ubuntu") return Family::kDebian;
        if (id == "fedora" || id == "rhel" || id == "centos") return Family::kFedora;
        if (id == "suse" || id == "opensuse" || id.starts_with("opensuse-")) return Family::kSuse;
    }
    return Family::kUnknown;
}

} // namespace

std::vector<std::string> missing_cpu_features(std::string_view cpuinfo) {
    // x86-64-v2 and v3 (v1 is any x86-64), as the kernel names them, and as
    // people know them.
    static const std::pair<const char*, const char*> kFeatures[] = {
        {"cx16", "CMPXCHG16B"}, {"lahf_lm", "LAHF"}, {"popcnt", "POPCNT"}, {"pni", "SSE3"},
        {"ssse3", "SSSE3"},     {"sse4_1", "SSE4.1"}, {"sse4_2", "SSE4.2"}, {"avx", "AVX"},
        {"avx2", "AVX2"},       {"bmi1", "BMI1"},    {"bmi2", "BMI2"},     {"f16c", "F16C"},
        {"fma", "FMA"},         {"abm", "LZCNT"},    {"movbe", "MOVBE"},   {"xsave", "XSAVE"},
    };
    std::set<std::string> flags;
    std::istringstream in{std::string(cpuinfo)};
    std::string line;
    while (std::getline(in, line)) {
        if (!line.starts_with("flags")) continue;
        const size_t colon = line.find(':');
        if (colon == std::string::npos) continue;
        std::istringstream words(line.substr(colon + 1));
        for (std::string w; words >> w;) flags.insert(w);
        break; // (every processor lists the same)
    }
    std::vector<std::string> missing;
    for (const auto& [flag, name] : kFeatures) {
        if (!flags.contains(flag)) missing.push_back(name);
    }
    return missing;
}

Distro parse_os_release(std::string_view text) {
    Distro d;
    std::istringstream in{std::string(text)};
    std::string line, like;
    while (std::getline(in, line)) {
        const size_t equals = line.find('=');
        if (equals == std::string::npos || line.starts_with('#')) continue;
        const std::string key = line.substr(0, equals), value = unquote(line.substr(equals + 1));
        if (key == "ID") d.id = value;
        else if (key == "ID_LIKE") like = value;
        else if (key == "NAME") d.name = value;
        else if (key == "VARIANT_ID") d.variant = value;
    }
    if (!d.id.empty()) d.like.push_back(d.id);
    std::istringstream words(like);
    for (std::string w; words >> w;) d.like.push_back(w);
    return d;
}

bool image_based(const Distro& d) {
    if (d.ostree || d.id == "steamos" || d.id == "nixos" || d.id == "guix") return true;
    for (const char* variant : {"silverblue", "kinoite", "sericea", "onyx", "atomic", "iot", "coreos"}) {
        if (d.variant == variant) return true;
    }
    // (like holds the id and each word of ID_LIKE.)
    for (const std::string& id : d.like) {
        for (const char* name : {"microos", "aeon", "kalpa", "bazzite"}) {
            if (id.find(name) != std::string::npos) return true;
        }
    }
    return false;
}

std::string image_based_hint(const std::string& what) {
    // (Word for word the builder's: the player may see both.)
    return "This system's own files cannot be changed with a package manager: " + what +
           " must come from a toolbox or distrobox container, or from the system's own way of adding software.";
}

std::string install_command(const Distro& distro, const std::vector<Package>& packages) {
    // The package of each piece, per family (in the order of Family).
    static const std::map<Package, std::array<const char*, 4>> kNames = {
        // (Debian's clang leaves the C++ library's headers to build-essential,
        // as the builder says too.)
        {Package::kCompiler, {"clang", "clang build-essential", "clang gcc-c++", "clang gcc-c++"}},
        {Package::kPython, {"python", "python3", "python3", "python3"}},
        {Package::kNumpy, {"python-numpy", "python3-numpy", "python3-numpy", "python3-numpy"}},
        {Package::kPillow, {"python-pillow", "python3-pil", "python3-pillow", "python3-Pillow"}},
        {Package::kGamescope, {"gamescope", "gamescope", "gamescope", "gamescope"}},
        {Package::kPactl, {"libpulse", "pulseaudio-utils", "pulseaudio-utils", "pulseaudio-utils"}},
        {Package::kMingw, {"mingw-w64-gcc", "gcc-mingw-w64-x86-64", "mingw64-gcc", "mingw64-cross-gcc"}},
        {Package::kCurl, {"curl", "curl", "curl", "curl"}},
    };
    static const char* const kCommands[] = {"sudo pacman -S --needed", "sudo apt install", "sudo dnf install",
                                            "sudo zypper install"};
    const Family f = family(distro);
    if (f == Family::kUnknown || packages.empty() || image_based(distro)) return {};
    const size_t k = static_cast<size_t>(f) - 1;
    std::string command = kCommands[k];
    std::set<std::string> named;
    for (Package p : packages) {
        if (named.insert(kNames.at(p)[k]).second) command += std::string(" ") + kNames.at(p)[k];
    }
    return command;
}

} // namespace launcher
