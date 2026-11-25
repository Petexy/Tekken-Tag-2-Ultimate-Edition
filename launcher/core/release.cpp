// The launcher's own updates (see release.h).

#include "release.h"
#include "utf8_path.h"

#include "json.h"

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <fstream>

namespace launcher {
namespace {

std::string lower(std::string_view text) {
    std::string out(text);
    for (char& c : out) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    return out;
}

bool has(std::string_view text, std::string_view part) { return text.find(part) != std::string_view::npos; }

} // namespace

std::optional<std::vector<unsigned>> version_numbers(std::string_view text) {
    if (!text.empty() && (text.front() == 'v' || text.front() == 'V')) text.remove_prefix(1);
    std::vector<unsigned> numbers;
    for (;;) {
        size_t digits = 0;
        unsigned n = 0;
        while (digits < text.size() && text[digits] >= '0' && text[digits] <= '9') {
            n = n * 10 + static_cast<unsigned>(text[digits] - '0');
            ++digits;
        }
        if (digits == 0 || digits > 9) return std::nullopt;
        numbers.push_back(n);
        text.remove_prefix(digits);
        if (text.empty()) return numbers;
        if (text.front() != '.') return std::nullopt;
        text.remove_prefix(1);
    }
}

std::optional<int> compare_versions(std::string_view a, std::string_view b) {
    const auto x = version_numbers(a), y = version_numbers(b);
    if (!x || !y) return std::nullopt;
    for (size_t i = 0; i < std::max(x->size(), y->size()); ++i) {
        const unsigned p = i < x->size() ? (*x)[i] : 0, q = i < y->size() ? (*y)[i] : 0;
        if (p != q) return p < q ? -1 : 1;
    }
    return 0;
}

std::string_view launcher_version(std::string_view kit_version) {
    return kit_version.substr(0, kit_version.find('-'));
}

bool built_older(std::string_view built, std::string_view kit) {
    if (built.empty() || kit.empty()) return false;
    const auto order = compare_versions(launcher_version(built), launcher_version(kit));
    return order && *order < 0;
}

ReleaseAnswer parse_release(std::string_view text) {
    ReleaseAnswer answer;
    std::string why;
    const auto json = json::parse(text, &why);
    if (!json || !json->is_object()) {
        answer.error = "GitHub's answer is not readable (" + (json ? std::string("not an object") : why) + ")";
        return answer;
    }
    const json::Value& root = *json;
    if (!root["tag_name"].is_string()) {
        // An error: its message says which.
        const std::string message = root["message"].string();
        if (message == "Not Found") answer.none = true;
        else if (has(lower(message), "rate limit")) {
            answer.error = "GitHub answers only so many questions from one network an hour: try again later";
        } else if (!message.empty()) answer.error = "GitHub answered \"" + message + "\"";
        else answer.error = "GitHub's answer names no release";
        return answer;
    }
    Release r;
    r.tag = root["tag_name"].string();
    r.page = root["html_url"].string();
    r.version = r.tag;
    if (!r.version.empty() && (r.version.front() == 'v' || r.version.front() == 'V')) r.version.erase(0, 1);
    if (!version_numbers(r.version)) {
        answer.error = "the newest release, " + r.tag + ", is not named as a version (such as v0.2.0)";
        return answer;
    }
    // Its AppImage for this kind of PC: one named for x86-64, else the only
    // one named for no processor.
    const json::Value* named = nullptr;
    std::vector<const json::Value*> plain;
    for (const json::Value& asset : root["assets"].items()) {
        const std::string name = lower(asset["name"].string());
        if (!name.ends_with(".appimage") || asset["state"].string("uploaded") != "uploaded" ||
            asset["browser_download_url"].string().empty()) {
            continue;
        }
        if (has(name, "x86_64") || has(name, "x86-64") || has(name, "amd64")) {
            if (!named) named = &asset;
        } else if (!has(name, "aarch64") && !has(name, "arm") && !has(name, "i686") && !has(name, "i386")) {
            plain.push_back(&asset);
        }
    }
    const json::Value* chosen = named ? named : plain.size() == 1 ? plain[0] : nullptr;
    if (!chosen) {
        answer.error = "version " + r.version + " has no AppImage to download";
        return answer;
    }
    r.asset = (*chosen)["name"].string();
    r.url = (*chosen)["browser_download_url"].string();
    const double size = (*chosen)["size"].number(-1);
    r.size = size > 0 ? static_cast<uint64_t>(size) : 0;
    const std::string digest = lower((*chosen)["digest"].string());
    if (digest.starts_with("sha256:") && digest.size() == 7 + 64) r.sha256 = digest.substr(7);
    answer.release = std::move(r);
    return answer;
}

std::vector<std::string> download_command(const Downloader& d, const std::string& url, bool api, const fs::path& file,
                                          const std::string& user_agent) {
    static const char* const kAccept = "Accept: application/vnd.github+json";
    static const char* const kApiVersion = "X-GitHub-Api-Version: 2022-11-28";
    std::vector<std::string> argv = {path_utf8(d.program)};
    if (d.curl) {
        // (Without -f for the API: its error answers say why. A download
        // that stalls for a minute stops.)
        argv.insert(argv.end(), {"-sS", "-L", "--connect-timeout", "20", "-A", user_agent});
        if (api) argv.insert(argv.end(), {"--max-time", "60", "-H", kAccept, "-H", kApiVersion});
        else argv.insert(argv.end(), {"-f", "--speed-limit", "1", "--speed-time", "60", "-o", path_utf8(file)});
    } else {
        argv.insert(argv.end(), {"-nv", "--timeout=60", "-U", user_agent});
        if (api) {
            argv.insert(argv.end(), {"--tries=2", "--content-on-error", std::string("--header=") + kAccept,
                                     std::string("--header=") + kApiVersion, "-O", "-"});
        } else {
            argv.insert(argv.end(), {"--tries=3", "-O", path_utf8(file)});
        }
    }
    argv.push_back(url);
    return argv;
}

fs::path update_file(const fs::path& appimage) {
    return appimage.parent_path() / utf8_path("." + path_utf8(appimage.filename()) + ".update");
}

fs::path previous_file(const fs::path& appimage) {
    return appimage.parent_path() / utf8_path("." + path_utf8(appimage.filename()) + ".previous");
}

std::vector<std::string> open_with_rollback(const fs::path& appimage, const std::string& version) {
    // ($1 the AppImage, $2 its previous one, $3 the version opened. 128 + N: ended by signal N.)
    static const char* const script =
        "\"$1\"; c=$?\n"
        "if [ \"$c\" -gt 128 ] && [ -e \"$2\" ] && mv -f \"$2\" \"$1\"; then\n"
        "  echo \"ttt2-launcher: version $3 ended (code $c) before its first frame: the version before is back\" >&2\n"
        "  unset TTT2_LAUNCHER_CONTINUE\n" // (the update stops there: never again by itself)
        "  TTT2_LAUNCHER_ROLLED_BACK=\"$3\" exec \"$1\"\n"
        "fi\n"
        "exit \"$c\"\n";
    return {"/bin/sh", "-c", script, "ttt2-launcher-update", path_utf8(appimage), path_utf8(previous_file(appimage)),
            version};
}

bool is_appimage(const fs::path& file) {
    unsigned char head[20] = {};
    std::ifstream in(file, std::ios::binary);
    if (!in.read(reinterpret_cast<char*>(head), sizeof head)) return false;
    return std::memcmp(head, "\177ELF", 4) == 0 && head[8] == 'A' && head[9] == 'I' && head[10] == 2 &&
           head[18] == 0x3e && head[19] == 0;
}

std::string version_in(std::string_view output) {
    while (!output.empty()) {
        const size_t end = std::min(output.find_first_of(" \t\r\n"), output.size());
        const std::string_view word = output.substr(0, end);
        if (!word.empty() && version_numbers(word)) {
            return std::string(word.front() == 'v' || word.front() == 'V' ? word.substr(1) : word);
        }
        output.remove_prefix(std::min(end + 1, output.size()));
    }
    return {};
}

} // namespace launcher
