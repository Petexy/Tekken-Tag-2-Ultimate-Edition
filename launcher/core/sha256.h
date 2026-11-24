#pragma once

// SHA-256 (FIPS 180-4), for the release .exe's files (its payload's digest,
// payload.h) and downloads: the same on every OS, no system library.

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace launcher {

class Sha256 {
public:
    Sha256();
    void update(const void* data, size_t size);
    void update(std::string_view data) { update(data.data(), data.size()); }
    std::array<uint8_t, 32> finish();

private:
    void block(const uint8_t* p);
    uint32_t h_[8];
    uint8_t buffer_[64];
    size_t used_ = 0;
    uint64_t bytes_ = 0;
};

std::array<uint8_t, 32> sha256(std::string_view data);
std::string hex(const uint8_t* bytes, size_t size);
std::string sha256_hex(std::string_view data);

} // namespace launcher
