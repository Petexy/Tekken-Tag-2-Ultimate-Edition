// Included inside wua_extract.cpp's anonymous namespace, after Entry.
// Directory-relative NT opens keep extraction attached to the opened directory,
// reject junctions/symlinks, and never replace an existing destination file.
class Fd {
public:
    explicit Fd(HANDLE value = INVALID_HANDLE_VALUE) : value_(value) {}
    ~Fd() { if (value_ != INVALID_HANDLE_VALUE) CloseHandle(value_); }
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
    Fd(Fd&& other) noexcept : value_(std::exchange(other.value_, INVALID_HANDLE_VALUE)) {}
    Fd& operator=(Fd&& other) noexcept {
        if (this != &other) {
            if (value_ != INVALID_HANDLE_VALUE) CloseHandle(value_);
            value_ = std::exchange(other.value_, INVALID_HANDLE_VALUE);
        }
        return *this;
    }
    HANDLE get() const { return value_; }
private:
    HANDLE value_;
};

[[noreturn]] void windows_error(const std::string& operation) {
    throw std::runtime_error(operation + " (Windows error " + std::to_string(GetLastError()) + ")");
}

Fd open_child(HANDLE parent, const fs::path& name, bool directory) {
    using Create = NTSTATUS (NTAPI*)(PHANDLE, ACCESS_MASK, POBJECT_ATTRIBUTES, PIO_STATUS_BLOCK,
                                     PLARGE_INTEGER, ULONG, ULONG, ULONG, ULONG, PVOID, ULONG);
    static const auto create = reinterpret_cast<Create>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "NtCreateFile"));
    if (!create) throw std::runtime_error("NtCreateFile is unavailable");
    const std::wstring text = name.wstring();
    if (text.empty() || text.size() > 32767 || name.has_parent_path())
        throw std::runtime_error("Invalid output path component");
    UNICODE_STRING unicode{};
    unicode.Buffer = const_cast<wchar_t*>(text.data());
    unicode.Length = unicode.MaximumLength = static_cast<USHORT>(text.size() * sizeof(wchar_t));
    OBJECT_ATTRIBUTES attributes{};
    attributes.Length = sizeof attributes;
    attributes.RootDirectory = parent;
    attributes.ObjectName = &unicode;
    attributes.Attributes = 0x40; // OBJ_CASE_INSENSITIVE
    IO_STATUS_BLOCK io{};
    HANDLE result = INVALID_HANDLE_VALUE;
    const auto status = create(&result,
        directory ? FILE_LIST_DIRECTORY | FILE_TRAVERSE | FILE_READ_ATTRIBUTES | SYNCHRONIZE
                  : GENERIC_WRITE | FILE_READ_ATTRIBUTES | DELETE | SYNCHRONIZE,
        &attributes, &io, nullptr, FILE_ATTRIBUTE_NORMAL, FILE_SHARE_READ | FILE_SHARE_WRITE,
        directory ? 3 : 2, // FILE_OPEN_IF / FILE_CREATE (exclusive)
        (directory ? 0x1 : 0x40) | 0x20 | 0x200000, // DIRECTORY/NON_DIRECTORY, SYNCHRONOUS_IO_NONALERT, OPEN_REPARSE_POINT
        nullptr, 0);
    if (status < 0) throw std::runtime_error("Cannot safely open " + name.string() + " (NT status " + std::to_string(status) + ")");
    Fd handle(result);
    FILE_ATTRIBUTE_TAG_INFO tag{};
    if (!GetFileInformationByHandleEx(result, FileAttributeTagInfo, &tag, sizeof tag)) windows_error("Cannot inspect output handle");
    if (tag.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)
        throw std::runtime_error("Refusing an output reparse point: " + name.string());
    return handle;
}

Fd output_directory(const fs::path& output) {
    const auto absolute = fs::absolute(output).lexically_normal();
    Fd current(CreateFileW(absolute.root_path().c_str(), FILE_LIST_DIRECTORY | FILE_TRAVERSE | FILE_READ_ATTRIBUTES,
                           FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
                           FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    if (current.get() == INVALID_HANDLE_VALUE) windows_error("Cannot open output filesystem root");
    for (const auto& component : absolute.relative_path()) {
        validate_component(component.string());
        current = open_child(current.get(), component, true);
    }
    return current;
}

void extract_file(ZArchiveReader& reader, const Entry& entry, HANDLE root) {
    HANDLE duplicate = INVALID_HANDLE_VALUE;
    if (!DuplicateHandle(GetCurrentProcess(), root, GetCurrentProcess(), &duplicate, 0, FALSE, DUPLICATE_SAME_ACCESS))
        windows_error("Cannot duplicate output directory handle");
    Fd parent(duplicate);
    const fs::path relative(entry.path);
    for (const auto& component : relative.parent_path()) parent = open_child(parent.get(), component, true);
    Fd output = open_child(parent.get(), relative.filename(), false);
    try {
        std::vector<unsigned char> buffer(1024 * 1024);
        for (uint64_t offset = 0; offset < entry.size;) {
            const auto length = static_cast<DWORD>(std::min<uint64_t>(buffer.size(), entry.size - offset));
            if (reader.ReadFromFile(entry.node, offset, length, buffer.data()) != length)
                throw std::runtime_error("Short archive read: " + entry.path);
            DWORD done = 0;
            while (done < length) {
                DWORD written = 0;
                if (!WriteFile(output.get(), buffer.data() + done, length - done, &written, nullptr) || !written)
                    windows_error("Cannot write " + entry.path);
                done += written;
            }
            offset += length;
        }
        if (!FlushFileBuffers(output.get())) windows_error("Cannot flush " + entry.path);
    } catch (...) {
        FILE_DISPOSITION_INFO disposition{TRUE};
        SetFileInformationByHandle(output.get(), FileDispositionInfo, &disposition, sizeof disposition);
        throw;
    }
}
