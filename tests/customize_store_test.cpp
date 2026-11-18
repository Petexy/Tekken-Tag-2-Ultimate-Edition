#include "title/customize_store.h"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>

namespace store = cafe::title::customize_store;
namespace fs = std::filesystem;

void check(bool ok, const char* message) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

int main() {
    check(store::kSize == 256400, "the title's file size");
    check(store::valid_code("abc") && store::valid_code("ab_9"), "pack codes");
    for (const char* bad : {"", "../x", "a/b", "a.b", "a b", "a\\b"}) check(!store::valid_code(bad), bad);

    const fs::path root = fs::temp_directory_path() / ("customize_store_test_" + std::to_string(std::rand()));
    fs::remove_all(root);
    const fs::path file = store::file_of(root, "abc");
    check(file == root / "customize" / "abc.bin", "the file is named by the code");
    check(store::file_of(root, "abd") != file, "another code, another file");
    check(!store::read(file), "no file: nothing");

    std::vector<uint8_t> bytes(store::kSize, 0);
    bytes[store::kFirstRecord + store::kRecordSize * 1] = 1;                       // slot 1 holds data
    bytes[store::kFirstPicture + store::kPictureSize * 2 + store::kPictureHeader + 5] = 9; // slot 2 has a picture
    bytes[store::kFirstPicture + store::kPictureSize * 3 + 7] = 9;                 // slot 3: only header bytes
    bytes[store::kFirstPicture + store::kPictureSize * 4 - 1] = 9;                 // slot 3: a stray last byte
    check(store::write(file, bytes.data()), "written");
    check(!fs::exists(file.string() + ".tmp"), "no temporary file is left");
    const auto back = store::read(file);
    check(back && *back == bytes, "read back whole");
    check(!store::filled(back->data(), 0) && store::filled(back->data(), 1), "which slots hold data");
    check(!store::filled(back->data(), 10), "no such record");
    check(store::picture_blank(back->data(), 1) && !store::picture_blank(back->data(), 2), "which have a picture");
    check(store::picture_blank(back->data(), 3), "a header or stray last bytes are not a picture");

    bytes[store::kFirstRecord] = 1;
    check(store::write(file, bytes.data()), "written over the old file");
    check(store::filled(store::read(file)->data(), 0), "the new bytes");

    { std::ofstream(file, std::ios::binary | std::ios::trunc) << "short"; }
    check(!store::read(file), "a file of another size is not a save");
    fs::remove_all(root);
    std::puts("Customize store tests passed");
}
