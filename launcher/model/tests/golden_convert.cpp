// golden_convert ROOT RUN_DIR OUT_DIR [linux|windows]
//
// Turns what an old launcher dumped in one golden case's run into the
// golden files model_test reads (see golden/README.md):
//   RUN_DIR/dumps/NN-<step>.json  ->  OUT_DIR/<os>/NN-<step>.json
//   RUN_DIR/log.txt's "@test" lines  ->  OUT_DIR/<os>/tests.txt
// ROOT, the folder the case ran in (its HOME), becomes /home/player, so the
// goldens name no real folder; each dump is read and written again in the one
// shape golden.cpp writes (keys in order, one element a line), so a dump that
// is not the goldens' shape stops here.

#include "golden.h"

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <sstream>

using namespace launcher;
using namespace launcher::model;

namespace {

const char* const kHome = "/home/player";

std::string read(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    std::stringstream s;
    s << in.rdbuf();
    return s.str();
}

std::string replaced(std::string text, const std::string& from, const std::string& to) {
    for (size_t at = text.find(from); at != std::string::npos; at = text.find(from, at + to.size())) {
        text.replace(at, from.size(), to);
    }
    return text;
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 4) {
        std::fprintf(stderr, "usage: golden_convert ROOT RUN_DIR OUT_DIR [linux|windows]\n");
        return 2;
    }
    const std::string root = fs::path(argv[1]).lexically_normal().string();
    const fs::path run = argv[2], out = fs::path(argv[3]) / (argc > 4 ? argv[4] : "linux");
    std::error_code ec;
    fs::remove_all(out, ec);
    fs::create_directories(out, ec);
    if (ec) {
        std::fprintf(stderr, "%s: %s\n", out.string().c_str(), ec.message().c_str());
        return 1;
    }
    std::vector<fs::path> dumps;
    for (const auto& f : fs::directory_iterator(run / "dumps", ec)) {
        if (f.path().extension() == ".json") dumps.push_back(f.path());
    }
    std::sort(dumps.begin(), dumps.end());
    if (dumps.empty()) {
        std::fprintf(stderr, "%s: no dumps\n", (run / "dumps").string().c_str());
        return 1;
    }
    for (const fs::path& f : dumps) {
        std::string error;
        const auto dump = parse_dump(replaced(read(f), root, kHome), &error);
        if (!dump) {
            std::fprintf(stderr, "%s: %s\n", f.string().c_str(), error.empty() ? "not a dump" : error.c_str());
            return 1;
        }
        std::ofstream(out / f.filename(), std::ios::binary) << dump_json(*dump);
    }
    std::istringstream log(replaced(read(run / "log.txt"), root, kHome));
    std::ofstream said(out / "tests.txt", std::ios::binary);
    for (std::string line; std::getline(log, line);) {
        if (line.starts_with("@test")) said << line << "\n";
    }
    std::printf("%zu dumps\n", dumps.size());
    return 0;
}
