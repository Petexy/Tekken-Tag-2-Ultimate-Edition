#include "install.h"
#include "cafe/generated.h"
#include "cafe/runtime.h"
#include "wua.h"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#define NOMINMAX
#include <windows.h>

namespace cafe::install {
namespace {

namespace fs = std::filesystem;

constexpr const char* kExecutableName = "Tekken Tag Tournament 2.exe";
constexpr const char* kMarker = ".ttt2-install";
constexpr const char* kStarted = ".ttt2-installing";
constexpr size_t kChunk = 8u << 20;

struct Failure : std::runtime_error {
    using std::runtime_error::runtime_error;
};
[[noreturn]] void fail(const std::string& message) { throw Failure(message); }

fs::path full_path(const std::string& text) {
    std::error_code ec;
    const fs::path absolute = fs::absolute(fs::path(text), ec);
    if (ec) fail("cannot resolve path " + text + ": " + ec.message());
    return absolute;
}

fs::path app_data_root() {
    const char* appdata = std::getenv("APPDATA");
    if (appdata != nullptr && *appdata != '\0') return fs::path(appdata);
    const char* local = std::getenv("LOCALAPPDATA");
    if (local != nullptr && *local != '\0') return fs::path(local);
    return fs::current_path();
}

fs::path config_file() {
    return app_data_root() / "ttt2" / "installed";
}

std::optional<fs::path> self_path() {
    std::wstring buffer(32768, L'\0');
    const DWORD size = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
    if (size == 0 || size >= buffer.size()) return std::nullopt;
    buffer.resize(size);
    return fs::path(buffer);
}

void record_folder(const fs::path& folder) {
    const fs::path file = config_file();
    std::error_code ec;
    fs::create_directories(file.parent_path(), ec);
    if (ec) fail("cannot create config folder " + file.parent_path().string() + ": " + ec.message());
    std::ofstream out(file);
    if (!out) fail("cannot write install record " + file.string());
    out << folder.string() << "\n";
}

std::optional<fs::path> recorded_folder() {
    std::ifstream in(config_file());
    std::string text;
    if (!in || !std::getline(in, text) || text.empty()) return std::nullopt;
    return full_path(text);
}

void install_executable(const fs::path& folder) {
    const std::optional<fs::path> self = self_path();
    if (!self) fail("cannot find the running executable path");
    std::error_code ec;
    fs::create_directories(folder, ec);
    if (ec) fail("cannot create install folder " + folder.string() + ": " + ec.message());
    fs::copy_file(*self, folder / kExecutableName, fs::copy_options::overwrite_existing, ec);
    if (ec) fail("cannot copy the executable into " + folder.string() + ": " + ec.message());
}

struct Entry {
    std::string path;
    uint64_t size = 0;
    ZArchiveNodeHandle node = ZARCHIVE_INVALID_NODE;
};

class Source {
public:
    explicit Source(const fs::path& path) {
        std::error_code ec;
        if (fs::is_directory(path, ec)) {
            directory_ = fs::exists(path / "code/Tekken.rpx", ec) ? path : path / "game";
            if (!fs::exists(directory_ / "code/Tekken.rpx", ec)) fail(path.string() + " holds no code/Tekken.rpx");
            for (auto it = fs::recursive_directory_iterator(directory_, fs::directory_options::follow_directory_symlink, ec);
                 !ec && it != fs::recursive_directory_iterator(); it.increment(ec)) {
                if (it.depth() > 32) fail(directory_.string() + " has folders too deep (a link loop?)");
                if (it->is_directory(ec)) continue;
                const std::string relative = it->path().lexically_relative(directory_).generic_string();
                if (!it->is_regular_file(ec)) fail(it->path().string() + " is not a file");
                if (relative.ends_with(".part")) continue;
                files_.push_back({relative, it->file_size(ec)});
                if (ec) fail("cannot read " + it->path().string() + ": " + ec.message());
            }
            if (ec) fail("cannot list " + directory_.string() + ": " + ec.message());
            std::sort(files_.begin(), files_.end(), [](const Entry& a, const Entry& b) { return a.path < b.path; });
            return;
        }
        archive_.reset(ZArchiveReader::OpenFromFile(path));
        if (!archive_) fail("cannot open " + path.string() + " as a .wua archive");
        const std::vector<std::string> layers = wua::game_layers(*archive_);
        if (layers.empty()) fail(path.string() + " holds no title with code/Tekken.rpx");
        for (const wua::File& f : wua::game_files(*archive_, layers)) files_.push_back({f.path, f.size, f.node});
    }

    const std::vector<Entry>& files() const { return files_; }

    std::optional<std::vector<uint8_t>> read_all(const std::string& path) {
        const auto it = std::find_if(files_.begin(), files_.end(), [&](const Entry& e) { return e.path == path; });
        if (it == files_.end()) return std::nullopt;
        std::vector<uint8_t> data(it->size);
        read(*it, 0, it->size, data.data());
        return data;
    }

    void read(const Entry& e, uint64_t offset, uint64_t length, uint8_t* out) {
        if (archive_) {
            if (archive_->ReadFromFile(e.node, offset, length, out) != length) fail("cannot read " + e.path + " from the archive");
            return;
        }
        std::ifstream in(directory_ / fs::path(e.path), std::ios::binary);
        if (!in) fail("cannot read " + (directory_ / fs::path(e.path)).string());
        in.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
        in.read(reinterpret_cast<char*>(out), static_cast<std::streamsize>(length));
        if (!in || static_cast<uint64_t>(in.gcount()) != length) {
            fail("cannot read " + (directory_ / fs::path(e.path)).string());
        }
    }

private:
    std::unique_ptr<ZArchiveReader> archive_;
    fs::path directory_;
    std::vector<Entry> files_;
};

void copy_title(Source& source, const fs::path& out) {
    std::error_code ec;
    fs::create_directories(out, ec);
    if (ec) fail("cannot create game folder " + out.string() + ": " + ec.message());
    std::vector<uint8_t> chunk(kChunk);
    for (const Entry& e : source.files()) {
        const fs::path target = out / fs::path(e.path);
        fs::create_directories(target.parent_path(), ec);
        if (ec) fail("cannot create " + target.parent_path().string() + ": " + ec.message());
        std::ofstream out_file(target, std::ios::binary | std::ios::trunc);
        if (!out_file) fail("cannot write " + target.string());
        uint64_t at = 0;
        while (at < e.size) {
            const uint64_t take = std::min<uint64_t>(chunk.size(), e.size - at);
            source.read(e, at, take, chunk.data());
            out_file.write(reinterpret_cast<const char*>(chunk.data()), static_cast<std::streamsize>(take));
            if (!out_file) fail("cannot write " + target.string());
            at += take;
        }
    }
}

int install(const std::vector<std::string>& positional) {
    if (positional.size() != 2) {
        fail("on Windows, install expects: ttt2 --install GAME FOLDER [--no-launcher]");
    }
    const fs::path source = full_path(positional[0]);
    Source game(source);
    const auto rpx = game.read_all("code/Tekken.rpx");
    if (!rpx || sha256_hex(*rpx) != cafe_program_info.rpx_sha256) {
        fail(source.string() + " is not the game this port was made from: TEKKEN TAG 2 Wii U EDITION, EU, version 16");
    }
    const fs::path folder = full_path(positional[1]);
    std::error_code ec;
    fs::create_directories(folder, ec);
    if (ec) fail("cannot create install folder " + folder.string() + ": " + ec.message());
    const fs::path started = folder / kStarted;
    const fs::path marker = folder / kMarker;
    std::ofstream(started.string()).close();
    copy_title(game, folder / "game");
    install_executable(folder);
    std::ofstream(marker.string()).close();
    fs::remove(started, ec);
    record_folder(folder);
    std::fprintf(stderr, "ttt2: installed in %s\n", folder.string().c_str());
    return 0;
}

int update(const std::vector<std::string>& positional) {
    if (positional.size() > 1) fail("too many arguments: ttt2 --update [FOLDER]");
    const std::optional<fs::path> folder = positional.empty() ? recorded_folder() : std::optional(full_path(positional[0]));
    if (!folder) fail("no complete install to update: run ttt2 --install first");
    std::error_code ec;
    if (!fs::exists(*folder / kMarker, ec)) fail("no complete install to update: run ttt2 --install first");
    install_executable(*folder);
    std::fprintf(stderr, "ttt2: updated the executable in %s\n", folder->string().c_str());
    return 0;
}

} // namespace

int run(const std::vector<std::string>& args) {
    try {
        bool updating = false;
        std::vector<std::string> positional;
        for (const std::string& arg : args) {
            if (arg == "--install") continue;
            if (arg == "--update") updating = true;
            else if (arg == "--no-launcher") continue;
            else if (!arg.empty() && arg[0] == '-') fail("unknown option " + arg);
            else positional.push_back(arg);
        }
        return updating ? update(positional) : install(positional);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "ttt2: install: %s\n", e.what());
        return 1;
    }
}

std::optional<fs::path> installed_game() {
    std::vector<fs::path> folders;
    std::error_code ec;
    if (const std::optional<fs::path> self = self_path()) folders.push_back(self->parent_path());
    if (const std::optional<fs::path> recorded = recorded_folder()) folders.push_back(*recorded);
    for (const fs::path& folder : folders) {
        if (fs::exists(folder / kMarker, ec)) return folder / "game";
        if (fs::exists(folder / kStarted, ec)) {
            std::fprintf(stderr, "ttt2: the install in %s is incomplete: run ttt2 --install again to finish it\n",
                         folder.string().c_str());
        }
    }
    return std::nullopt;
}

bool decode_tga(const std::vector<uint8_t>& tga, std::vector<uint8_t>& rgba, uint32_t& width, uint32_t& height) {
    if (tga.size() < 18) return false;
    const uint32_t w = tga[12] | uint32_t{tga[13]} << 8, h = tga[14] | uint32_t{tga[15]} << 8;
    const uint32_t type = tga[2], bits = tga[16], descriptor = tga[17];
    if (tga[1] != 0 || (type != 2 && type != 10) || (bits != 24 && bits != 32) || w == 0 || h == 0) return false;
    const size_t bytes = bits / 8, count = size_t{w} * h;
    size_t at = 18 + tga[0];
    if (at > tga.size() || count > (tga.size() - at) / bytes * (type == 10 ? 128 : 1)) return false;
    std::vector<uint8_t> pixels;
    pixels.reserve(count * 4);
    const auto put = [&](size_t from) {
        pixels.insert(pixels.end(), {tga[from + 2], tga[from + 1], tga[from], bytes == 4 ? tga[from + 3] : uint8_t{255}});
    };
    while (pixels.size() < count * 4) {
        size_t run = 1;
        bool repeat = false;
        if (type == 10) {
            if (at >= tga.size()) return false;
            run = (tga[at] & 0x7F) + 1;
            repeat = tga[at++] & 0x80;
        }
        if (pixels.size() / 4 + run > count || at + (repeat ? 1 : run) * bytes > tga.size()) return false;
        for (size_t i = 0; i < run; ++i) {
            put(at);
            if (!repeat) at += bytes;
        }
        if (repeat) at += bytes;
    }
    rgba.resize(pixels.size());
    for (uint32_t y = 0; y < h; ++y) {
        const uint32_t row = (descriptor & 0x20) ? y : h - 1 - y;
        for (uint32_t x = 0; x < w; ++x) {
            const uint32_t column = (descriptor & 0x10) ? w - 1 - x : x;
            std::memcpy(&rgba[(size_t{y} * w + x) * 4], &pixels[(size_t{row} * w + column) * 4], 4);
        }
    }
    width = w;
    height = h;
    return true;
}

} // namespace cafe::install
