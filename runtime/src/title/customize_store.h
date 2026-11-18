#pragma once
// An added fighter's saved customizations, kept by the port.
//
// The title saves a fighter's customizations as one file of its save per select id (63 files, a full directory, an
// assert on an id of 63 or more), so an added fighter has no place there. The port keeps the same thing in a file
// of its own per added fighter, in the title's layout, named by the pack's CODE (select ids move when packs are
// added or removed): `<save folder>/customize/<code>.bin`, 256,400 bytes:
//   +0       4 bytes
//   +4       10 records of 4096 bytes (title/test_record.h): 0-4 the five customization slots, 5-9 the edited
//            default costumes
//   +0xA004  12 bytes
//   +0xA010  11 pictures of 19,584 bytes (a 96-byte texture header the title rewrites when it uses one, then the
//            pixels): the pictures of the slots as the costume chooser shows them, made in CUSTOMIZE mode
// The title's working buffer (one per player side) holds exactly this, so loading is a copy into it and saving a
// copy out of it; the port never interprets a record. A file of another size is not a save and is left alone.
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

namespace cafe::title::customize_store {
constexpr uint32_t kSize = 0x3E990;
constexpr uint32_t kRecords = 10, kRecordSize = 4096, kFirstRecord = 4, kSlots = 5;
constexpr uint32_t kPictures = 11, kPictureSize = 19584, kPictureHeader = 96, kFirstPicture = 0xA010;
// (the pixels proper; the picture's last bytes were seen to hold stray values in a buffer the title never filled)
constexpr uint32_t kPicturePixels = 19456;
static_assert(kPictureHeader + kPicturePixels <= kPictureSize);
static_assert(kFirstRecord + kRecords * kRecordSize + 12 == kFirstPicture);
static_assert(kFirstPicture + kPictures * kPictureSize == kSize);

// A pack's code as a file name: letters, digits and '_' only (a code is a folder name the player may have made).
inline bool valid_code(std::string_view code) {
    if (code.empty() || code.size() > 32) return false;
    for (const char c : code) {
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_')) return false;
    }
    return true;
}

// The file of the fighter with this code under the port's save folder.
inline std::filesystem::path file_of(const std::filesystem::path& save_root, std::string_view code) {
    return save_root / "customize" / (std::string(code) + ".bin");
}

// The file's bytes, if it is there and whole.
inline std::optional<std::vector<uint8_t>> read(const std::filesystem::path& file) {
    std::error_code ec;
    if (!std::filesystem::is_regular_file(file, ec) || std::filesystem::file_size(file, ec) != kSize || ec)
        return std::nullopt;
    std::ifstream in(file, std::ios::binary);
    std::vector<uint8_t> bytes(kSize);
    if (!in.read(reinterpret_cast<char*>(bytes.data()), kSize)) return std::nullopt;
    return bytes;
}

// Writes the file whole or not at all: a temporary file beside it, then a rename over it.
inline bool write(const std::filesystem::path& file, const uint8_t* bytes) {
    std::error_code ec;
    std::filesystem::create_directories(file.parent_path(), ec);
    std::filesystem::path temporary = file;
    temporary += ".tmp";
    {
        std::ofstream out(temporary, std::ios::binary | std::ios::trunc);
        out.write(reinterpret_cast<const char*>(bytes), kSize);
        out.flush();
        if (!out) {
            out.close();
            std::filesystem::remove(temporary, ec);
            return false;
        }
    }
    std::filesystem::rename(temporary, file, ec);
    if (ec) {
        std::filesystem::remove(temporary, ec);
        return false;
    }
    return true;
}

// Whether record `number` of a file's or buffer's bytes holds a customization.
inline bool filled(const uint8_t* bytes, uint32_t number) {
    return number < kRecords && bytes[kFirstRecord + kRecordSize * number] != 0;
}

// Whether slot `number` has no picture (a slot written by a tool: CUSTOMIZE mode takes the picture).
inline bool picture_blank(const uint8_t* bytes, uint32_t number) {
    if (number >= kPictures) return true;
    const uint8_t* pixels = bytes + kFirstPicture + kPictureSize * number + kPictureHeader;
    for (uint32_t i = 0; i < kPicturePixels; ++i) {
        if (pixels[i]) return false;
    }
    return true;
}
} // namespace cafe::title::customize_store
