#pragma once
#include <array>
#include <cstdint>
#include <span>
#include <string>
#include <vector>
#include <algorithm>
namespace cafe::title::checkpoint {
constexpr uint32_t kScratchBegin=0x108A3C08, kScratchEnd=0x108C2E90;
constexpr size_t kScratchBytes=kScratchEnd-kScratchBegin;
struct ObjectIdentity {
    uint32_t address=0,id=0,row=0,record=0,partner=0,animator=0,animation_set=0;
    bool operator==(const ObjectIdentity&) const = default;
};
struct Identity {
    uint64_t generation=0;
    uint32_t mode=0,kind=0;
    std::array<ObjectIdentity,12> objects{};
    std::array<uint32_t,4> floors{};
    bool operator==(const Identity&) const = default;
    bool supported() const {
        if (!mode || (kind!=4 && kind!=5)) return false;
        for (size_t i=0;i<objects.size();++i) {
            if (!objects[i].address || !objects[i].animator) return false;
            if (i<4 && objects[i].id>=63) return false;
        }
        return true;
    }
};
class Slot {
    Identity identity_{};
    std::vector<uint8_t> bytes_;
public:
    void clear() { bytes_.clear(); }
    bool valid() const { return bytes_.size()==kScratchBytes; }
    bool save(const Identity& id,std::span<const uint8_t> bytes) {
        if (!id.supported() || bytes.size()!=kScratchBytes) return false;
        identity_=id; bytes_.assign(bytes.begin(),bytes.end()); return true;
    }
    bool matches(const Identity& id) const { return valid() && id.supported() && id==identity_; }
    const std::vector<uint8_t>& bytes() const { return bytes_; }
};
// Never take ownership of the title's existing recording/demo scratch slot.
template<class Call> void preserve_scratch(std::span<uint8_t> scratch,Call call) {
    const std::vector<uint8_t> old(scratch.begin(),scratch.end());
    struct Restore {
        std::span<uint8_t> scratch; const std::vector<uint8_t>& old;
        ~Restore() { std::copy(old.begin(),old.end(),scratch.begin()); }
    } restore{scratch,old};
    call();
}
enum class Request : uint32_t { None,Save,Load };
void request(Request request);
bool take_notice(std::string& text);
} // namespace cafe::title::checkpoint
