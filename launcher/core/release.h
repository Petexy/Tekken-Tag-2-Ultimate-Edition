#pragma once

// The launcher's own updates: its newest release on GitHub (with the
// AppImage attached to it), version numbers, downloading with the system's
// curl or wget, and the AppImage the launcher runs from, which an update
// replaces with the newer one.

#include "paths.h"

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace launcher {

// The repository's newest release as GitHub's API gives it (drafts and
// pre-releases are never it). $TTT2_LAUNCHER_RELEASES is asked instead when
// set (tests: an answer of their own, on this PC).
inline constexpr const char* kLatestRelease =
    "https://api.github.com/repos/Petexy/Tekken-Tag-2-Ultimate-Edition/releases/latest";

// The variable that holds the pid of the launcher an update replaces: the
// new one waits for it to end before it opens its window (one window per
// user: the old one's would be shown instead).
inline constexpr const char* kReplacesVariable = "TTT2_LAUNCHER_AFTER";

// A version's numbers ("0.1.0", "v0.2", "V1.10.3"); none when it is not one.
std::optional<std::vector<unsigned>> version_numbers(std::string_view text);
// Below 0, 0, above 0 as `a` is older than, the same as or newer than `b`
// (a missing number is 0: 0.2 is 0.2.0); none when either is not a version.
std::optional<int> compare_versions(std::string_view a, std::string_view b);

// The launcher version a kit's version names (kit_version, built_version):
// "0.6.2" of "0.6.2-1cab8c68f39b".
std::string_view launcher_version(std::string_view kit_version);
// Whether an install's program, built by the kit `built` names
// (built_version), is from an older launcher than this one's kit (`kit`,
// kit_version). The characters this launcher's importer makes need what the
// newer program has (their summons, effects and hit reactions: an older one
// plays them without), so it is updated before it is played, and before
// characters are added or updated. Not when either is unknown or not a
// version (a program ttt2 --install made), nor for the same version (another
// commit of it) or a newer one.
bool built_older(std::string_view built, std::string_view kit);

struct Release {
    std::string version;    // its tag without the "v"
    std::string tag;
    std::string page;       // its page on GitHub (what is new in it)
    std::string asset, url; // the AppImage's file name, and where it is downloaded from
    uint64_t size = 0;
    std::string sha256;     // its digest (lowercase hex), when GitHub gives one
};

// GitHub's answer about the newest release: the release with its AppImage,
// `none` when no release is published, else why it cannot be updated to.
struct ReleaseAnswer {
    std::optional<Release> release;
    bool none = false;
    std::string error;
};
ReleaseAnswer parse_release(std::string_view json);

// The AppImage this launcher runs from: $APPIMAGE, as the AppImage's runtime
// sets it, when the program (/proc/self/exe) is inside $APPDIR, where that
// runtime mounted it. Otherwise none: the variables may be another
// AppImage's, inherited from a program that started the launcher.
std::optional<fs::path> running_appimage(const fs::path& program, const char* appimage, const char* appdir);

// Why a new AppImage cannot be put in the place of `appimage` (its folder is
// not writable, say); empty when it can.
std::string cannot_replace(const fs::path& appimage);

// What downloads: curl, else wget, from $PATH.
struct Downloader {
    fs::path program;
    bool curl = true;
};
std::optional<Downloader> find_downloader();

// The command that downloads `url`: GitHub's API answer (`api`) to standard
// output, also when it is an error (it says why), or a file to `file`.
std::vector<std::string> download_command(const Downloader& downloader, const std::string& url, bool api,
                                          const fs::path& file, const std::string& user_agent);

// Where the new AppImage is downloaded to: beside the old one (one file
// system, so that it can be renamed over it), hidden.
fs::path update_file(const fs::path& appimage);

// Whether `file` is an x86-64 AppImage of type 2 (as make_appimage.sh makes
// them): an ELF program with "AI" 2 at byte 8.
bool is_appimage(const fs::path& file);

// The version a launcher's --version names ("ttt2-launcher 0.2.0"), or empty.
std::string version_in(std::string_view output);

// The new AppImage made executable as the old one is (same permissions),
// so that it can run before it replaces it. Why not, or empty.
std::string make_executable(const fs::path& update, const fs::path& appimage);
// `update` renamed over `appimage`. Why not, or empty.
std::string replace_appimage(const fs::path& update, const fs::path& appimage);

// C2's way back: the AppImage an update replaces is kept beside it, hidden, until the new one drew its first frame.
fs::path previous_file(const fs::path& appimage); // ".<name>.previous"
// `appimage` kept as previous_file() (a hard link, else a copy). Why not, or empty.
std::string keep_previous(const fs::path& appimage);
// It back in its place (renamed over `appimage`). Why not, or empty.
std::string restore_previous(const fs::path& appimage);
// After a first frame: the previous one is not needed any more.
void forget_previous(const fs::path& appimage);
// The variable a launcher put back in place is opened with: the version that never opened its window.
inline constexpr const char* kRolledBackVariable = "TTT2_LAUNCHER_ROLLED_BACK";
// How the updated `appimage` (release `version`) is opened: through /bin/sh, which waits for it. When it ended by a
// signal (a crash) while previous_file() is still there (no first frame), the previous one is put back and opened
// with kRolledBackVariable=version (and TTT2_LAUNCHER_AFTER still: it waits for the one that updated, too). (One
// that cannot open its window puts it back itself: restore_previous.)
std::vector<std::string> open_with_rollback(const fs::path& appimage, const std::string& version);

// Whether a process still runs: it exists and has not ended (an ended one
// stays a zombie until its parent has seen it end).
bool process_alive(int pid);

} // namespace launcher
