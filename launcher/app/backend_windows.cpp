#include "backend_windows.h"

#include "paths.h"
#include "release.h"
#include "system.h"
#include "win32.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <algorithm>
#include <cstdlib>
#include <fstream>

namespace launcher::app {

namespace {

// (A path in UTF-8, as the starter's arguments are: path::string() would use the ANSI code page.)
std::string u8(const fs::path& p) { return win32::narrow(p.native()); }

bool there(const fs::path& p) {
    std::error_code ec;
    return !p.empty() && fs::exists(p, ec);
}

std::wstring env_wide(const wchar_t* name) {
    const DWORD n = GetEnvironmentVariableW(name, nullptr, 0);
    if (!n) return {};
    std::wstring v(n, L'\0');
    GetEnvironmentVariableW(name, v.data(), n);
    v.resize(n - 1);
    return v;
}

// The last lines of a program's output, for the player's details.
std::string last_lines(const std::string& text, size_t lines) {
    size_t end = text.find_last_not_of("\r\n \t");
    if (end == std::string::npos) return {};
    size_t at = end + 1;
    for (size_t n = 0; n < lines && at > 0; ++n) {
        const size_t nl = text.rfind('\n', at - 1);
        if (nl == std::string::npos) {
            at = 0;
            break;
        }
        at = nl;
    }
    std::string out = text.substr(at, end + 1 - at);
    while (!out.empty() && (out.front() == '\n' || out.front() == '\r')) out.erase(out.begin());
    return out;
}

} // namespace

fs::path program_file() {
    std::wstring buf(32768, L'\0');
    const DWORD n = GetModuleFileNameW(nullptr, buf.data(), static_cast<DWORD>(buf.size()));
    if (!n || n >= buf.size()) return {};
    buf.resize(n);
    return fs::path(buf);
}

fs::path home_folder() {
    const std::wstring profile = env_wide(L"USERPROFILE");
    return profile.empty() ? fs::path(L"C:\\") : fs::path(profile);
}

WindowsFiles windows_files(const fs::path& release_files) {
    WindowsFiles w;
    if (!release_files.empty()) {
        w.root = release_files;
        w.release = true;
    } else {
        // (A CMake build: <project>\build-windows-tools\launcher\ttt2-launcher.exe, or beside main.py's project.)
        fs::path at = program_file().parent_path();
        w.root = at;
        for (int up = 0; up < 4 && !at.empty(); ++up, at = at.parent_path()) {
            if (there(at / "launcher" / "windows" / "main.py")) {
                w.root = at;
                break;
            }
            if (at == at.parent_path()) break;
        }
    }
    w.build = w.root / "build-windows-tools";
    const fs::path private_python = w.root / "local" / "windows-tools" / "python-runtime" / "python" / "python.exe";
    if (const std::wstring given = env_wide(L"TTT2_PYTHON"); !given.empty()) {
        w.python = fs::path(given);
    } else if (there(private_python) || w.release) {
        w.python = private_python;
        w.python_needed = !there(private_python);
    } else {
        wchar_t found[32768];
        if (SearchPathW(nullptr, L"python.exe", nullptr, 32768, found, nullptr)) w.python = fs::path(found);
        else w.python = private_python; // (none: the state query says so)
    }
    return w;
}

model::Facts windows_start_facts(const WindowsFiles& files, const fs::path& chosen_game) {
    model::Facts f;
    f.caps = model::Caps::windows_caps();
    f.launcher_version = TTT2_LAUNCHER_VERSION;
    f.python = files.python;
    f.importer = files.root / "tools" / "characters";
    f.windows.root = files.root;
    f.windows.build = files.build;
    f.chosen_game = chosen_game;
    f.custom_releases = std::getenv("TTT2_LAUNCHER_RELEASES") != nullptr;
    f.custom_github = std::getenv("TTT2_LAUNCHER_GITHUB") != nullptr;
    return f;
}

model::Command first_state_query(const WindowsFiles& files) {
    model::Command c;
    c.argv = {u8(files.python), "-u", u8(files.root / "launcher" / "windows" / "main.py"), "--build-dir",
              u8(files.build), "--query", "state"};
    c.cwd = files.root;
    return c;
}

model::Command bootstrap_command(const WindowsFiles& files) {
    // (call with the name relative to its folder: cmd /c's quote rules never meet the folder's letters.)
    model::Command c;
    std::wstring shell = env_wide(L"ComSpec");
    c.argv = {shell.empty() ? std::string("cmd.exe") : win32::narrow(shell), "/d", "/c", "call",
              "Start Ultimate Launcher.cmd", "--check"};
    c.cwd = files.root;
    return c;
}

std::string WindowsEnvironment::log_end(const fs::path& file) {
    std::ifstream in(file, std::ios::binary | std::ios::ate);
    const std::streamoff size = in ? static_cast<std::streamoff>(in.tellg()) : 0;
    if (size <= 0) return {};
    const std::streamoff from = std::max<std::streamoff>(0, size - 65536);
    std::string text(static_cast<size_t>(size - from), '\0');
    in.seekg(from);
    in.read(text.data(), static_cast<std::streamsize>(text.size()));
    text.resize(static_cast<size_t>(std::max<std::streamsize>(0, in.gcount())));
    return text;
}

bool WindowsEnvironment::exists(const fs::path& path) { return there(path); }

// ---------------------------------------------------------------- getting ready

void WindowsReady::start(double now) {
    job_.reset();
    out_.clear();
    err_.clear();
    ended_ = false;
    code_ = -1;
    since_ = now;
    failure_ = {};
    answer_.reset();
    progress_ = {};
    // (Python may have been gotten by another start meanwhile.)
    const fs::path python = files_.python;
    if (files_.python_needed && there(python)) files_.python_needed = false;
    if (!files_.python_needed) return run_state(now);
    stage_ = Stage::kBootstrap;
    std::string error;
    model::JobEvents ev;
    ev.line = [this](const std::string& line, bool is_error) { (is_error ? err_ : out_) += line + "\n"; };
    ev.exited = [this](int code) {
        ended_ = true;
        code_ = code;
    };
    std::error_code ec;
    fs::create_directories(files_.root / "local", ec);
    job_ = starter_.start(bootstrap_command(files_), std::move(ev), &error);
    if (!job_)
        fail({"Cannot get the launcher ready", "Windows' command processor did not start: " + error + ".", {},
              files_.bootstrap_log(), true});
}

void WindowsReady::run_state(double now) {
    stage_ = Stage::kState;
    since_ = now;
    out_.clear();
    err_.clear();
    ended_ = false;
    std::string error;
    model::JobEvents ev;
    ev.line = [this](const std::string& line, bool is_error) { (is_error ? err_ : out_) += line + "\n"; };
    ev.exited = [this](int code) {
        ended_ = true;
        code_ = code;
    };
    if (!there(files_.python)) {
        return fail({"Python is missing",
                     files_.release ? "The launcher's Python is not in " + u8(files_.python.parent_path()) +
                                          ". Start the launcher again to get it."
                                    : "Install Python 3 from python.org, or set TTT2_PYTHON to its python.exe.",
                     {}, {}, true});
    }
    job_ = starter_.start(first_state_query(files_), std::move(ev), &error);
    if (!job_) fail({"The launcher's files did not start", "Python did not start: " + error + ".", {}, {}, true});
}

void WindowsReady::tick(double now) {
    if (stage_ == Stage::kBootstrap) {
        if (now >= next_read_) {
            next_read_ = now + 0.25;
            WindowsEnvironment env(files_.build);
            progress_ = bootstrap_progress(env.log_end(files_.bootstrap_log()));
        }
        if (!ended_) return;
        job_.reset();
        WindowsEnvironment env(files_.build);
        progress_ = bootstrap_progress(env.log_end(files_.bootstrap_log()));
        if (code_ != 0 || !there(files_.python)) {
            // (What went wrong: the log's last run without its own step lines and curl's bar.)
            std::string said;
            const std::string log = env.log_end(files_.bootstrap_log());
            const size_t from = log.rfind("@step check");
            std::string line;
            for (const char ch : log.substr(from == std::string::npos ? 0 : from) + "\n") {
                if (ch != '\n' && ch != '\r') {
                    line += ch;
                    continue;
                }
                const bool bar = line.find('%') != std::string::npos && line.find("##") != std::string::npos;
                if (!line.empty() && !line.starts_with("@step") && !bar &&
                    line.find_first_not_of(" #\t") != std::string::npos)
                    said += line + "\n";
                line.clear();
            }
            return fail({"Cannot get the launcher ready",
                         "Its Python could not be downloaded and checked. Check your internet connection, then try "
                         "again.",
                         last_lines(said, 4), files_.bootstrap_log(), true});
        }
        files_.python_needed = false;
        return run_state(now);
    }
    if (stage_ != Stage::kState || !ended_) return;
    job_.reset();
    backend::QueryError error;
    auto answer = backend::parse_windows_state(out_, &error);
    if (answer) {
        answer_ = std::move(answer);
        stage_ = Stage::kDone;
        return;
    }
    if (error.code == "protocol") {
        return fail({"These files are another version's",
                     "The launcher's files in " + u8(files_.root) +
                         " are not the ones this launcher came with. Close every Ultimate Launcher, then start it "
                         "again; if this stays, get the newest one from the releases page.",
                     "Their answers' protocol is " + error.text + ", this launcher's " +
                         std::to_string(backend::kQueryProtocol) + ".",
                     {}, false});
    }
    const std::string said = last_lines(err_.empty() ? out_ : err_, 6);
    fail({"The launcher's files did not answer",
          "Python stopped before it said what is installed" + std::string(code_ > 0 ? " (exit code " +
                                                                                       std::to_string(code_) + ")"
                                                                                 : std::string()) +
              ".",
          said.empty() ? error.text : said, files_.root / "local" / "windows-launcher-errors.log", true});
}

void WindowsReady::cancel() {
    if (job_) job_->terminate();
    job_.reset();
}

void WindowsReady::fail(Failure f) {
    stage_ = Stage::kFailed;
    failure_ = std::move(f);
}

} // namespace launcher::app

// ---------------------------------------------------------------- Linux's parts, as Windows has them
// (The model's preflight and the AppImage's update are Linux's: their pieces of launcher/core are in
// ttt2_launcher_core_linux. Windows never runs them, but the model refers to them: here they say so, and
// free_space is real, for the in-app browser.)

namespace launcher {

std::vector<std::string> missing_cpu_features() { return {}; }
std::optional<Compiler> find_compiler(std::string* why) {
    if (why) *why = "the Windows setup brings its own compiler";
    return std::nullopt;
}
std::optional<uint64_t> free_space(const fs::path& folder) {
    std::error_code ec;
    fs::path at = folder;
    while (!at.empty() && !fs::exists(at, ec) && at != at.parent_path()) at = at.parent_path();
    const fs::space_info s = fs::space(at, ec);
    if (ec) return std::nullopt;
    return static_cast<uint64_t>(s.available);
}
uint64_t file_system(const fs::path&) { return 0; }
uint64_t size_of(const fs::path& folder) {
    uint64_t total = 0;
    std::error_code ec;
    for (fs::recursive_directory_iterator it(folder, fs::directory_options::skip_permission_denied, ec), end;
         !ec && it != end; it.increment(ec)) {
        if (it->is_regular_file(ec)) total += it->file_size(ec);
    }
    return total;
}
Distro this_distro() { return {}; }
std::string cannot_replace(const fs::path&) { return "Windows updates its launcher with its own worker"; }
std::optional<Downloader> find_downloader() { return std::nullopt; }
std::string make_executable(const fs::path&, const fs::path&) { return "not on Windows"; }
std::string replace_appimage(const fs::path&, const fs::path&) { return "not on Windows"; }

} // namespace launcher
