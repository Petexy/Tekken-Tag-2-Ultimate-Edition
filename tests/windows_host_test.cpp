#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "cafe/vfs.h"
#include "host/file.h"
#include "host/keymap.h"
#include "host/display_settings.h"
#include "host/time.h"
#include "install.h"
#include <array>
#include <atomic>
#include <cstdio>
#include <fstream>
#include <stdexcept>
#include <thread>
#include <winioctl.h>

PPC_FUNC(windows_alias_probe) { ctx.r[3] = 42; (void)base; }
PPC_FUNC(windows_alias_probe_orig);

namespace fs = std::filesystem;
void check(bool ok, const char* what) { if (!ok) throw std::runtime_error(what); }

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--fault") {
            cafe::install_fault_handler();
            cafe::reserve_guest_memory();
            *static_cast<volatile uint8_t*>(cafe::guest_base() + 0xf000) = 1;
            throw std::runtime_error("uncommitted page did not fault");
        }
        check(argc == 2, "scratch folder argument");
        const fs::path scratch = fs::absolute(argv[1]);
        fs::create_directories(scratch);
        cafe::reserve_guest_memory();
        check(!cafe::guest_memory_committed(0x10000, 4), "reserved pages start inaccessible");
        cafe::commit_guest_memory(0x10001, 8);
        check(cafe::guest_memory_committed(0x10000, 4096), "commit covers guest pages");
        check(!cafe::guest_memory_committed(0xfffffffcu, 8), "reject addresses past 4 GiB");
        cafe::ppc::st32(cafe::guest_base(), 0x10001, 0x12345678);
        check(cafe::ppc::ld32(cafe::guest_base(), 0x10001) == 0x12345678, "unaligned big-endian guest access");
        cafe::commit_guest_memory(0x10000, 4096);
        check(cafe::ppc::ld32(cafe::guest_base(), 0x10001) == 0x12345678, "recommit preserves guest memory");

        cafe::PPCContext ctx{};
        windows_alias_probe(ctx, cafe::guest_base());
        check(ctx.r[3] == 42, "strong function replaces generated weak alias on COFF");
        windows_alias_probe_orig(ctx, cafe::guest_base());
        check(ctx.r[3] == 1, "original guest body stays callable");

        const fs::path unicode = scratch / L"file-\u00f1-\u65e5.bin";
        const int fd = cafe::host::file::open(unicode, O_RDWR | O_CREAT | O_TRUNC);
        check(fd >= 0, "Unicode file paths");
        DWORD sparse_result = 0;
        check(DeviceIoControl(reinterpret_cast<HANDLE>(_get_osfhandle(fd)), FSCTL_SET_SPARSE,
                              nullptr, 0, nullptr, 0, &sparse_result, nullptr), "sparse test file");
        const std::array<unsigned char, 5> data{0, 10, 13, 26, 255};
        constexpr uint64_t offset = (uint64_t{1} << 32) + 17;
        check(cafe::host::file::write_at(fd, data.data(), data.size(), offset) == data.size(), "64-bit file offsets and binary writes");
        std::array<unsigned char, 5> read{};
        check(cafe::host::file::read_at(fd, read.data(), read.size(), offset) == data.size() && read == data, "64-bit binary reads");
        const std::array<unsigned char, 5> other{5, 4, 3, 2, 1};
        check(cafe::host::file::write_at(fd, other.data(), other.size(), 0) == other.size(), "second positional record");
        std::atomic<bool> concurrent_ok{true};
        const auto read_many = [&](uint64_t at, const auto& expected) {
            for (unsigned i = 0; i < 2000; ++i) {
                std::array<unsigned char, 5> bytes{};
                if (cafe::host::file::read_at(fd, bytes.data(), bytes.size(), at) != bytes.size() || bytes != expected)
                    concurrent_ok = false;
            }
        };
        std::thread first([&] { read_many(0, other); });
        std::thread second([&] { read_many(offset, data); });
        first.join();
        second.join();
        check(concurrent_ok, "concurrent positional reads preserve each offset");
        close(fd);
        fs::remove(unicode);

        const fs::path config = scratch / "keyboard.ini";
        const auto resolver = [](const std::string&) { return uint16_t{0}; };
        cafe::host::keymap::Watcher watcher(config, resolver);
        check(watcher.reload().has_value(), "initial keyboard settings load");
        check(!watcher.reload(), "unchanged keyboard settings");
        { std::ofstream out(config); out << "face_top = scancode:15\n"; }
        check(watcher.reload().has_value(), "created keyboard settings detected");
        check(!watcher.reload(), "unchanged file stamp");
        { std::ofstream out(config); out << "face_top = scancode:16\n# edited\n"; }
        check(watcher.reload().has_value(), "edited keyboard settings detected");
        fs::remove(config);
        check(watcher.reload().has_value(), "deleted keyboard settings detected");

        const fs::path display = scratch / "display.ini";
        { std::ofstream out(display); out << "resolution = 1920x1080\nfullscreen = yes\ninterpolation = no\n"; }
        const auto loaded = cafe::host::display::load(display);
        check(loaded.error.empty() && loaded.settings.fullscreen && !loaded.settings.interpolation &&
              loaded.settings.resolution == cafe::host::display::Resolution::k1080, "Windows display settings load");
        fs::remove(display);
        check(fs::is_regular_file(cafe::host::file::executable()), "Windows executable lookup");
        check(cafe::host::utc_offset(std::time(nullptr)) % 60 == 0, "local UTC offset");

        cafe::vfs::set_save_root(scratch);
        int32_t handle = -1;
        check(cafe::vfs::open_file("/vol/save/binary.dat", "w+", handle) == cafe::vfs::kOk, "save file creation");
        uint64_t transferred = 0;
        check(cafe::vfs::write_file(handle, data.data(), data.size(), 0, transferred) == cafe::vfs::kOk && transferred == data.size(), "VFS binary write");
        read.fill(0);
        check(cafe::vfs::read_file(handle, read.data(), read.size(), 0, transferred) == cafe::vfs::kOk && read == data, "VFS binary read");
        check(cafe::vfs::close_file(handle) == cafe::vfs::kOk, "save file close");
        fs::remove(scratch / "binary.dat");
        fs::remove(scratch);
        std::puts("Windows memory, file I/O, settings, VFS, and weak aliases passed");
        return 0;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "FAIL: %s\n", e.what());
        return 1;
    }
}
