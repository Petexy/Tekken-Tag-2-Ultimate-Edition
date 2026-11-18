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
    // A save the disk does not take: the folder's place is taken by a file, so nothing can be written under it.
    fs::remove_all(root);
    fs::create_directories(root);
    { std::ofstream(root / "customize") << "in the way"; }
    store::Unsaved unsaved;
    bytes[store::kFirstRecord + store::kRecordSize * 2] = 1;
    check(!store::write(file, bytes.data()), "a write that cannot be done says so");
    check(!unsaved.save(root, "abc", bytes.data()), "a failed save is not a done one");
    check(unsaved.waiting("abc") && unsaved.any() && !unsaved.waiting("abd"), "it waits, by code");
    const auto kept = unsaved.load(root, "abc");
    check(kept && *kept == bytes, "the fighter still gets what was saved");
    check(!unsaved.load(root, "abd"), "another fighter gets nothing of it");
    check(unsaved.retry(root).empty() && unsaved.waiting("abc"), "still no disk: it keeps waiting");
    std::vector<uint8_t> newer = bytes;
    newer[store::kFirstRecord + store::kRecordSize * 3] = 1;
    check(!unsaved.save(root, "abc", newer.data()), "a second failed save");
    check(*unsaved.load(root, "abc") == newer, "the newest bytes are the ones kept");
    fs::remove(root / "customize");
    const auto done = unsaved.retry(root);
    check(done.size() == 1 && done[0] == "abc" && !unsaved.any(), "the disk is back: written, nothing waits");
    check(store::read(file) && *store::read(file) == newer, "the file holds the newest bytes");
    check(*unsaved.load(root, "abc") == newer, "and a load reads the file");
    check(unsaved.retry(root).empty(), "nothing left to try");
    // A failed save leaves the file that is there as it was.
    fs::permissions(file.parent_path(), fs::perms::owner_read | fs::perms::owner_exec);
    if (!store::write(file, bytes.data())) { // (a user who may write anywhere cannot make this case)
        check(!unsaved.save(root, "abc", bytes.data()), "a read-only folder: not saved");
        check(*store::read(file) == newer, "the old file is whole");
        check(*unsaved.load(root, "abc") == bytes, "the session has the new bytes");
        fs::permissions(file.parent_path(), fs::perms::owner_all);
        check(unsaved.retry(root).size() == 1 && *store::read(file) == bytes, "written once the folder allows it");
        check(!fs::exists(file.string() + ".tmp"), "no temporary file is left after the retries");
    }
    fs::permissions(file.parent_path(), fs::perms::owner_all);
    fs::remove_all(root);
    std::puts("Customize store tests passed");
}
