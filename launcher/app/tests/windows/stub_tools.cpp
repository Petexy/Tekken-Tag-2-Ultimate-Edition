// Stand-ins for the Windows launcher's tests under Wine (run_wine.sh): one program copied under the names of what
// the launcher and "Start Ultimate Launcher.cmd" run. Nothing is downloaded and no Python runs.
//
//   python.exe   -c ...                 "Launcher runtime ready" (the .cmd's check of its Python)
//                ... --query NAME       %TTT2_STUB_ANSWERS%\NAME.json as it is (save-settings: standard input is kept
//                                       in %TTT2_STUB_ANSWERS%\save-settings.in); none: an error answer
//                ... --worker ACTION    "@step ..." lines for the names after --outfits X, then @done
//   curl.exe     -o FILE URL            a progress bar on standard error, then FILE
//   certutil.exe -hashfile FILE SHA256  %TTT2_STUB_HASH% as the file's hash
//   findstr.exe  /i /x TEXT FILE        0 when a line of FILE is TEXT (any case), else 1
//   tar.exe      -xzf ARCHIVE -C DIR    DIR\python\python.exe and pythonw.exe: copies of this program
//   holder.exe   FILE SECONDS           FILE written and held as the starter of 0.4 to 0.8.0 holds launcher.log for
//                                       its Python (shared for reading only), "held" on standard output, then ended

#include <windows.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

// (UTF-8 text <-> wide: never the ANSI code page, so that a José in a folder is kept, run_wine.sh's jose case.)
std::string utf8(const std::wstring& w) {
    const int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, nullptr, 0, nullptr, nullptr);
    std::string s(n > 0 ? n - 1 : 0, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, s.data(), n, nullptr, nullptr);
    return s;
}

fs::path path_of(const std::string& text) { return fs::path(std::u8string(text.begin(), text.end())); }

std::string env(const char* name) {
    const std::wstring wide_name(name, name + std::char_traits<char>::length(name));
    const DWORD n = GetEnvironmentVariableW(wide_name.c_str(), nullptr, 0);
    if (!n) return "";
    std::wstring v(n, L'\0');
    v.resize(GetEnvironmentVariableW(wide_name.c_str(), v.data(), n));
    return utf8(v);
}

std::string lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}

fs::path self() {
    wchar_t buf[32768];
    const DWORD n = GetModuleFileNameW(nullptr, buf, 32768);
    return fs::path(std::wstring(buf, n));
}

std::string read(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    return {std::istreambuf_iterator<char>(in), {}};
}

void pause(double seconds) { Sleep(static_cast<DWORD>(seconds * 1000)); }

int python(const std::vector<std::string>& a) {
    for (size_t i = 0; i < a.size(); ++i) {
        if (a[i] == "-c") {
            std::printf("Launcher runtime ready\n");
            return 0;
        }
        if (a[i] == "--query" && i + 1 < a.size()) {
            const fs::path answers = path_of(env("TTT2_STUB_ANSWERS"));
            const std::string name = a[i + 1];
            std::ofstream(answers / "queries.log", std::ios::app | std::ios::binary) << name << "\n"; // (what was asked, in order)
            if (name == "save-settings") {
                std::string input{std::istreambuf_iterator<char>(std::cin), {}};
                std::ofstream(answers / "save-settings.in", std::ios::binary) << input;
            }
            const fs::path file = answers / (name + ".json");
            if (!fs::exists(file)) {
                std::printf("{\"error\": \"the stub has no answer for %s\", \"protocol\": 1}\n", name.c_str());
                return 0;
            }
            std::string answer = read(file);
            // (TTT2_STUB_PROTOCOL_FROM_FILES: the protocol is the files' own, query.py's PROTOCOL beside main.py.)
            const size_t at = answer.rfind("\"protocol\": ");
            if (!env("TTT2_STUB_PROTOCOL_FROM_FILES").empty() && at != std::string::npos) {
                std::string protocol = "0";
                for (const std::string& arg : a) {
                    if (arg.size() < 7 || arg.compare(arg.size() - 7, 7, "main.py") != 0) continue;
                    const std::string query = read(path_of(arg).parent_path() / "query.py");
                    if (const size_t p = query.find("PROTOCOL = "); p != std::string::npos)
                        protocol = query.substr(p + 11, query.find_first_not_of("0123456789", p + 11) - p - 11);
                }
                const size_t from = at + 12, to = answer.find_first_not_of("0123456789", from);
                answer.replace(from, to - from, protocol);
            }
            std::fputs(answer.c_str(), stdout);
            return 0;
        }
        if (a[i] == "--worker" && i + 1 < a.size()) {
            std::vector<std::string> names;
            for (size_t j = i + 2; j < a.size(); ++j) {
                if (a[j] == "--outfits" || a[j] == "--cancel-file") {
                    ++j;
                    continue;
                }
                names.push_back(a[j]);
            }
            const double step = env("TTT2_STUB_STEP_SECONDS").empty() ? 0.05 : std::atof(env("TTT2_STUB_STEP_SECONDS").c_str());
            for (size_t n = 0; n < names.size(); ++n) {
                std::printf("@step fighter %s %zu %zu\n", names[n].c_str(), n + 1, names.size());
                std::fflush(stdout);
                pause(step);
            }
            std::printf("@done\n");
            return 0;
        }
    }
    std::fprintf(stderr, "stub python: nothing to do\n");
    return 2;
}

int curl(const std::vector<std::string>& a) {
    fs::path out;
    for (size_t i = 0; i + 1 < a.size(); ++i)
        if (a[i] == "-o") out = path_of(a[i + 1]);
    if (env("TTT2_STUB_CURL_FAIL") == "1") {
        std::fprintf(stderr, "curl: (6) Could not resolve host: github.com\n");
        return 6;
    }
    const double seconds = env("TTT2_STUB_CURL_SECONDS").empty() ? 2 : std::atof(env("TTT2_STUB_CURL_SECONDS").c_str());
    for (int n = 0; n <= 20; ++n) {
        const std::string bar(static_cast<size_t>(n * 3), '#');
        std::fprintf(stderr, "\r%-60s %5.1f%%", bar.c_str(), n * 5.0);
        std::fflush(stderr);
        pause(seconds / 20);
    }
    std::fprintf(stderr, "\n");
    std::ofstream(out, std::ios::binary) << "stub archive";
    return 0;
}

int certutil(const std::vector<std::string>& a) {
    const std::string file = a.size() > 1 ? a[1] : "";
    std::printf("SHA256 hash of %s:\r\n%s\r\nCertUtil: -hashfile command completed successfully.\r\n", file.c_str(),
                env("TTT2_STUB_HASH").c_str());
    return 0;
}

int findstr(const std::vector<std::string>& a) {
    std::vector<std::string> words;
    for (const std::string& w : a)
        if (!w.empty() && w[0] != '/') words.push_back(w);
    if (words.size() < 2) return 2;
    std::ifstream in(path_of(words[1]), std::ios::binary);
    for (std::string line; std::getline(in, line);) {
        while (!line.empty() && (line.back() == '\r' || line.back() == '\n')) line.pop_back();
        if (lower(line) == lower(words[0])) return 0;
    }
    return 1;
}

int tar(const std::vector<std::string>& a) {
    fs::path dir;
    for (size_t i = 0; i + 1 < a.size(); ++i)
        if (a[i] == "-C") dir = path_of(a[i + 1]);
    pause(0.4);
    std::error_code ec;
    fs::create_directories(dir / "python", ec);
    fs::copy_file(self(), dir / "python" / "python.exe", fs::copy_options::overwrite_existing, ec);
    if (ec) return 1;
    fs::copy_file(self(), dir / "python" / "pythonw.exe", fs::copy_options::overwrite_existing, ec);
    return ec ? 1 : 0;
}

} // namespace

int main() {
    int count = 0;
    wchar_t** wide = CommandLineToArgvW(GetCommandLineW(), &count);
    std::vector<std::string> a;
    for (int i = 1; i < count; ++i) a.push_back(utf8(wide[i]));
    const std::string name = lower(self().stem().string());
    if (name == "python" || name == "pythonw") return python(a);
    if (name == "curl") return curl(a);
    if (name == "certutil") return certutil(a);
    if (name == "findstr") return findstr(a);
    if (name == "tar") return tar(a);
    if (name == "holder" && a.size() == 2) {
        const std::wstring file(path_of(a[0]).wstring());
        HANDLE h = CreateFileW(file.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_ALWAYS,
                               FILE_ATTRIBUTE_NORMAL, nullptr);
        if (h == INVALID_HANDLE_VALUE) return 3;
        DWORD wrote = 0;
        WriteFile(h, "the bridge's log\r\n", 18, &wrote, nullptr);
        std::printf("held\n");
        std::fflush(stdout);
        pause(std::atof(a[1].c_str()));
        CloseHandle(h);
        return 0;
    }
    std::fprintf(stderr, "stub tools: copy me as python/curl/certutil/findstr/tar.exe (not %s)\n", name.c_str());
    return 2;
}
