#pragma once

// The release .exe's files (Ultimate_Launcher-x86_64.exe): the project's files
// make_launcher_exe.py puts in it as resource 100 (RCDATA) in the TTT2PAY1
// format, which every launcher since 0.4.0 checks in a download
// (self_update.py) and unpacks on the player's PC. Shared by
// launcher/windows/entry.cpp (the Python launcher's .exe) and the new
// launcher's start (startup.h). The format and the unpacking are the same on
// every OS (tests run on Linux too); reading the .exe's own resource and the
// files folder's place are Windows'.
//
// Format: for each file, its path's length (4 bytes), the path (UTF-8, '/'
// between folders), its size (8 bytes), its bytes; then the 56-byte Trailer.
// All numbers little-endian.

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace launcher::payload {

namespace fs = std::filesystem;

struct Trailer {
    uint64_t size, count;     // of the files' part, and how many files
    unsigned char sha256[32]; // of the files' part
    char magic[8];            // "TTT2PAY1"
};
static_assert(sizeof(Trailer) == 56);
inline constexpr char kMagic[8] = {'T', 'T', 'T', '2', 'P', 'A', 'Y', '1'};
inline constexpr int kFilesResource = 100; // (RCDATA)

struct Payload {
    std::string files; // the files' part
    Trailer trailer{};
    bool empty() const { return files.empty() && trailer.count == 0; }
    std::string digest() const; // the files' SHA-256 (hex): the stamp's first line
};

// The files at the end of `all` (a resource, or an .exe with them appended), checked: none when `all` does not end
// with a trailer (a launcher built without files). Throws std::runtime_error with the player's sentence when they
// are incomplete or damaged. `check` false: their digest is taken as the trailer says (startup's quick look before
// handing over to a running launcher; unpack() reads them checked).
std::optional<Payload> read(std::string_view all, bool check = true);

struct Entry {
    std::string path;
    std::string_view data;
};
// The files, each path checked (not empty, no leading '/', no '\\' or ':', no empty, '.' or '..' part). Throws
// "This Ultimate Launcher holds an unsafe path: <p>" / "... is damaged: download it again."
std::vector<Entry> entries(const Payload& payload);

// The files into `root` when they are not the ones unpacked there last (local/launcher-files.txt: their digest,
// then their paths, and launcher/windows/main.py there). Files only the last ones had are deleted; nothing else
// there (local/, the build, the generated code) is touched. Each file is written beside itself and renamed over
// it. Throws "Cannot write <path>." Returns whether it unpacked.
bool unpack(const Payload& payload, const fs::path& root);

// The digest named by the stamp in `root` ("" when none).
std::string unpacked_digest(const fs::path& root);

#ifdef _WIN32
// This program's own files: resource 100, else appended to `exe` (tests, make_launcher_exe.py --stub). Throws
// "Cannot read Ultimate Launcher's own file." when it cannot read it.
std::optional<Payload> own(const fs::path& exe, bool check = true);
// Where the release keeps its files: %LOCALAPPDATA%\TTT2Ultimate\launcher, unless that path has letters beyond
// ASCII (a user name such as José: the game is built there, and the batch files CMake writes in UTF-8 lose such
// letters), then %PUBLIC%'s, else the system drive's. Throws "LOCALAPPDATA is not set."
fs::path files_folder();
// The mutex around unpacking (two starts at once: one unpacks, the other then finds the files there).
inline constexpr const wchar_t* kFilesMutex = L"Local\\TTT2UltimateLauncherFiles";
#endif

} // namespace launcher::payload
