#pragma once

// Windows' answers to the new launcher (launcher/windows/query.py, `main.py
// --query NAME`): the last non-empty line of the program's output, one JSON
// object with "protocol": kQueryProtocol, facts only (the model words them).
// Parsed here into the model's facts; tested on any OS from recorded answers
// (tests/windows).

#include "facts.h"
#include "json.h"
#include "release.h"

#include <map>
#include <optional>
#include <string>

namespace launcher::backend {

inline constexpr int kQueryProtocol = 1;

// Why an answer could not be read: "protocol" (the launcher's files are another version's: the launcher refuses
// them), "answer" (no JSON object on its last line), else the answer's own {"error": reason} (raw, for the log).
struct QueryError {
    std::string code; // "protocol", "answer", "error"
    std::string text; // the reason (the answer's "error", or what the line was)
};

// The answer's JSON object, its protocol checked.
std::optional<json::Value> parse_query(const std::string& output, QueryError* error);

// `--query state`.
struct WindowsStateAnswer {
    model::WindowsState state; // root, build, config, play, branch, commit, folders, logs, problems
    std::string version;       // the launcher files' version ("0.8.0")
    std::string files_id;      // what they build, in the kit's form ("0.8.0-<sha>", "0.8.0")
    std::string installed_by;  // what built the installed game, the kit's form ("" unknown)
    fs::path exe;              // the release .exe these files came from ("" a project ZIP or build)
    fs::path installed;        // the complete installation ("" none)
    fs::path icon;             // its icon.png ("" none)
    fs::path display_file, keyboard_file;
};
std::optional<WindowsStateAnswer> parse_windows_state(const std::string& output, QueryError* error);

// The facts the model reads from it: Facts::windows, this_build and build_commit, the install, what built it, its
// icon, whether the launcher updates itself (the release .exe).
void apply_windows_state(const WindowsStateAnswer& answer, model::Facts& facts);

// "0.8.0 <sha>" (self_update.files_id) as the Linux kit names a build: "0.8.0-<sha>".
std::string kit_id(const std::string& files_id);

// `--query check`: the problem ("" code: none).
std::optional<model::SetupProblem> parse_check(const std::string& output, QueryError* error);

// `--query save-settings`: the folders as saved, or why they were not (problem.code "data_name" / "relative",
// problem.what the folder's key).
struct SavedSettings {
    std::map<std::string, std::string> folders;
    model::SetupProblem problem;
};
std::optional<SavedSettings> parse_save_settings(const std::string& output, QueryError* error);

// `--query release`: the newer release (only when it is newer than these files), none published, or GitHub's
// reason.
std::optional<ReleaseAnswer> parse_release_query(const std::string& output, QueryError* error);

} // namespace launcher::backend
