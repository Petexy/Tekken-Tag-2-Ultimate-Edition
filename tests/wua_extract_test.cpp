#include <zarchive/zarchivewriter.h>
#include <windows.h>
#include <winioctl.h>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
void check(bool ok, const char* what) { if (!ok) throw std::runtime_error(what); }
void new_part(int32_t, void*) {}
void write_data(const void* bytes, size_t size, void* out) {
    static_cast<std::ofstream*>(out)->write(static_cast<const char*>(bytes), size);
}
void archive(const fs::path& file, const std::map<std::string, std::string>& entries) {
    std::ofstream out(file, std::ios::binary | std::ios::trunc);
    ZArchiveWriter writer(new_part, write_data, &out);
    for (const auto& [path, data] : entries) {
        if (const auto slash = path.rfind('/'); slash != std::string::npos) writer.MakeDir(path.substr(0, slash).c_str(), true);
        writer.StartNewFile(path.c_str());
        writer.AppendData(data.data(), data.size());
    }
    writer.Finalize();
}
std::wstring quote(const std::wstring& text) {
    std::wstring out = L"\"";
    unsigned slashes = 0;
    for (wchar_t c : text) {
        if (c == L'\\') { ++slashes; continue; }
        out.append(slashes * (c == L'"' ? 2 : 1), L'\\');
        slashes = 0;
        if (c == L'"') out += L'\\';
        out += c;
    }
    out.append(slashes * 2, L'\\');
    return out + L'"';
}
DWORD run(const fs::path& exe, const std::vector<std::wstring>& args) {
    std::wstring command = quote(exe.wstring());
    for (const auto& arg : args) command += L" " + quote(arg);
    STARTUPINFOW startup{};
    startup.cb = sizeof startup;
    SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    const HANDLE log = CreateFileW(L"NUL", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                   &security, OPEN_EXISTING, 0, nullptr);
    check(log != INVALID_HANDLE_VALUE, "open child output");
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = startup.hStdOutput = startup.hStdError = log;
    PROCESS_INFORMATION process{};
    const BOOL started = CreateProcessW(exe.c_str(), command.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW,
                                        nullptr, nullptr, &startup, &process);
    CloseHandle(log);
    check(started, "start extractor");
    const DWORD wait = WaitForSingleObject(process.hProcess, 30000);
    if (wait != WAIT_OBJECT_0) TerminateProcess(process.hProcess, 1);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    check(wait == WAIT_OBJECT_0, "extractor completed before timeout");
    return code;
}
std::string contents(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(in), {}};
}
void junction(const fs::path& link, const fs::path& target) {
    fs::create_directory(link);
    const std::wstring substitute = L"\\??\\" + target.wstring(), print = target.wstring();
    struct Header {
        DWORD tag;
        WORD length, reserved;
        WORD substitute_offset, substitute_length, print_offset, print_length;
    };
    const WORD substitute_bytes = static_cast<WORD>(substitute.size() * sizeof(wchar_t));
    const WORD print_bytes = static_cast<WORD>(print.size() * sizeof(wchar_t));
    std::vector<unsigned char> bytes(sizeof(Header) + substitute_bytes + print_bytes + 2 * sizeof(wchar_t));
    auto* header = reinterpret_cast<Header*>(bytes.data());
    *header = {IO_REPARSE_TAG_MOUNT_POINT, static_cast<WORD>(bytes.size() - 8), 0,
               0, substitute_bytes, static_cast<WORD>(substitute_bytes + sizeof(wchar_t)), print_bytes};
    std::memcpy(bytes.data() + sizeof(Header), substitute.data(), substitute_bytes);
    std::memcpy(bytes.data() + sizeof(Header) + header->print_offset, print.data(), print_bytes);
    HANDLE handle = CreateFileW(link.c_str(), GENERIC_WRITE, 0, nullptr, OPEN_EXISTING,
                                FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, nullptr);
    check(handle != INVALID_HANDLE_VALUE, "open junction directory");
    DWORD returned = 0;
    const BOOL ok = DeviceIoControl(handle, FSCTL_SET_REPARSE_POINT, bytes.data(), static_cast<DWORD>(bytes.size()),
                                    nullptr, 0, &returned, nullptr);
    CloseHandle(handle);
    check(ok, "create unprivileged NTFS junction");
}
int main(int argc, char** argv) {
    try {
        check(argc == 3, "extractor and scratch arguments");
        const fs::path exe = fs::absolute(argv[1]);
        const fs::path scratch = fs::absolute(argv[2]) / std::to_string(GetCurrentProcessId());
        fs::create_directories(scratch);
        const auto fixture = scratch / "fixture.wua";
        const auto output = scratch / L"output with spaces-\u00f1";
        const std::string binary("\0\n\r\x1a\xff", 5);
        archive(fixture, {{"title_v16/code/Tekken.rpx", binary}, {"title_v16/meta/meta.xml", "metadata"},
                          {"title_v16/content/data.bin", "content"}});
        check(run(exe, {L"list", fixture.wstring()}) == 0, "list archive");
        check(run(exe, {L"extract-analysis", fixture.wstring(), output.wstring()}) == 0, "extract analysis files");
        check(contents(output / "title_v16/code/Tekken.rpx") == binary, "binary extraction preserves every byte");
        check(!fs::exists(output / "title_v16/content"), "analysis skips content");
        check(run(exe, {L"extract-analysis", fixture.wstring(), output.wstring()}) != 0, "never overwrite existing files");
        check(contents(output / "title_v16/code/Tekken.rpx") == binary, "collision leaves original intact");
        const auto all = scratch / "all";
        check(run(exe, {L"extract-all", fixture.wstring(), all.wstring()}) == 0, "extract full archive");
        check(contents(all / "title_v16/content/data.bin") == "content", "content extraction");

        const auto outside = scratch / "outside";
        fs::create_directories(outside);
        const auto link = scratch / "redirect";
        junction(link, outside);
        check(run(exe, {L"extract-all", fixture.wstring(), link.wstring()}) != 0, "reject junction output ancestor");
        check(fs::is_empty(outside), "no writes through junction");
        fs::remove(link);
        const auto nested = scratch / "nested";
        fs::create_directories(nested / "title_v16");
        junction(nested / "title_v16/code", outside);
        check(run(exe, {L"extract-all", fixture.wstring(), nested.wstring()}) != 0, "reject junction inside archive path");
        check(fs::is_empty(outside), "no writes through nested junction");
        fs::remove(nested / "title_v16/code");
        fs::remove_all(nested);
        if (CreateSymbolicLinkW(link.c_str(), outside.c_str(), SYMBOLIC_LINK_FLAG_DIRECTORY | 0x2)) {
            check(run(exe, {L"extract-all", fixture.wstring(), link.wstring()}) != 0, "reject symlink output ancestor");
            check(fs::is_empty(outside), "no writes through symlink");
            fs::remove(link);
        } else {
            std::cout << "Symbolic-link variant unavailable; unprivileged junction variants passed\n";
        }
        for (const char* name : {"evil:stream", "NUL", "trailing.", "trailing "}) {
            archive(fixture, {{std::string("title/code/") + name, "unsafe"}});
            check(run(exe, {L"extract-all", fixture.wstring(), (scratch / "unsafe").wstring()}) != 0, "reject Windows path aliases");
            check(!fs::exists(scratch / "unsafe"), "validate inventory before creating output");
        }
        fs::remove_all(output);
        fs::remove_all(all);
        fs::remove(outside);
        fs::remove(fixture);
        fs::remove(scratch);
        std::cout << "Windows extraction checks passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "FAIL: " << e.what() << '\n';
        return 1;
    }
}
