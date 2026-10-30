// Practice: 3 and - (Select) pressed together put both fighters back where
// the stage put them, as Tekken 8's position reset does.
//
// The title starts a Practice round (mode kinds 4 and 5) with its situation
// set-up sub_039C2DB0 for kind 15: its Practice positioner (sub_04F21428)
// places the fighters as the Position Settings say (by default 1 m either
// side of the stage's centre; REVERSE swaps them) and every fighter starts
// over, standing. The reset runs the same set-up from the battle's state
// (GameMode::Impl::state_game_battle, sub_0726DF8C) at the start of a frame,
// with the camera calls of the title's own Practice restart (sub_04A28490):
// the round's start camera, and the 2P one when REVERSE is on.
//
// 3 is the title's own button, after the Controller Setup: the fighter's
// buttons at +2032 (1 to 4 = 0x200 to 0x1000), read from the fighter the
// GamePad drives (its raw buttons at +2052; the training dummy's stay 0).
// The input layer holds - back a moment so that it can join 3
// (cafe::os::arm_select_chord), armed only on the fighters' frames, which
// stop while the pause menu is open; a - that is the chord's never reaches
// the game.

#include "cafe/input.h"
#include "title/practice_checkpoint.h"
#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"

#include <cstdio>
#include <array>
#include <vector>
#include <cstring>
#include <atomic>
#include <mutex>
#include <cstdlib>

PPC_FUNC(sub_03A45CA4);
PPC_FUNC(sub_03A472A4);

namespace cafe::title::checkpoint {
namespace {
std::atomic<Request> pending{Request::None};
std::atomic<bool> notice_ready{false};
std::mutex notice_mutex;
std::string notice;
}
bool enabled() {
    static const bool on=std::getenv("TTT2_PRACTICE_CHECKPOINT")!=nullptr;
    return on;
}
void request(Request command) { if(enabled()) pending.store(command); }
void status(const char* text) {
    { std::lock_guard lock(notice_mutex); notice=text; }
    notice_ready.store(true);
    std::fprintf(stderr,"checkpoint: %s\n",text);
}
bool take_notice(std::string& text) {
    if(!notice_ready.exchange(false)) return false;
    std::lock_guard lock(notice_mutex); text=notice; return true;
}
} // namespace cafe::title::checkpoint

namespace {

using namespace cafe;

constexpr uint32_t kMatchObject = 0x10872CB8; // *(*(*it + 228) + 228) = the mode manager (sub_06ECB1B0)
constexpr uint32_t kModeKind = 444;
constexpr uint32_t kPracticeKinds[] = {4, 5};                       // as sub_06ECB3CC
constexpr uint32_t kPracticeSettings = 0x108D1C60, kReverse = 100; // sub_04F1BD58; 1: the player on the right
constexpr uint32_t kSidePlayers = 0x1087FB60;                     // per side: its first member (sub_05C5EF14)
constexpr uint32_t kPlayerActive = 7808, kPlayerPartner = 172;
constexpr uint32_t kPlayerButtons = 2032, kButton3 = 0x800, kPlayerPad = 2052;
constexpr uint32_t kPracticeStart = 15; // the situation of a Practice round's start
constexpr uint32_t k2PCamera = 2;

uint32_t load(uint8_t* base, uint32_t address) { return ppc::ld32(base, address); }

bool practice(uint8_t* base) {
    const uint32_t object = load(base, kMatchObject);
    const uint32_t match = object ? load(base, object + 228) : 0;
    const uint32_t mode = match ? load(base, match + 228) : 0;
    if (!mode) return false;
    const uint32_t kind = load(base, mode + kModeKind);
    for (uint32_t k : kPracticeKinds) {
        if (kind == k) return true;
    }
    return false;
}

// The fighter a side has in play (sub_05C5EF14).
uint32_t active_fighter(uint8_t* base, uint32_t side) {
    const uint32_t first = load(base, kSidePlayers + 4 * side);
    if (!first || load(base, first + kPlayerActive)) return first;
    return load(base, first + kPlayerPartner);
}

bool three_held(uint8_t* base) {
    for (uint32_t side = 0; side < 2; ++side) {
        const uint32_t fighter = active_fighter(base, side);
        if (fighter && load(base, fighter + kPlayerPad) && (load(base, fighter + kPlayerButtons) & kButton3)) {
            return true;
        }
    }
    return false;
}

// Calls guest function `f` with arguments (and f1); -> r3. The caller's registers are kept.
uint32_t call(PPCContext& ctx, uint8_t* base, void (*f)(PPCContext&, uint8_t*), std::initializer_list<uint32_t> args,
              double f1 = 0.0) {
    const PPCContext saved = ctx;
    uint32_t r = 3;
    for (uint32_t a : args) ctx.r[r++] = a;
    ctx.f[1] = {f1, f1};
    f(ctx, base);
    const uint32_t result = ctx.r[3];
    ctx = saved;
    return result;
}

namespace checkpoint=cafe::title::checkpoint;
checkpoint::Slot checkpoint_slot;
uint64_t checkpoint_generation=0;

checkpoint::Identity checkpoint_identity(uint8_t* base) {
    checkpoint::Identity id{}; id.generation=checkpoint_generation;
    const uint32_t object=load(base,kMatchObject);
    const uint32_t match=object ? load(base,object+228) : 0;
    id.mode=match ? load(base,match+228) : 0;
    id.kind=id.mode ? load(base,id.mode+kModeKind) : 0;
    for(uint32_t i=0;i<12;++i) {
        const uint32_t p=load(base,kSidePlayers+4*i);
        if(!p || !guest_memory_committed(p,0x2960)) { id.mode=0;return id; }
        const uint32_t animator=load(base,p+7944);
        if(!animator || !guest_memory_committed(animator,20)) { id.mode=0;return id; }
        id.objects[i]={p,load(base,p+84),load(base,p+80),load(base,p+88),
                       load(base,p+172),animator,load(base,animator+8)};
        if(i<4) id.floors[i]=load(base,p+72);
    }
    return id;
}

// Executes only on the fighter simulation thread, never in the SDL input thread.
void process_checkpoint(PPCContext& ctx,uint8_t* base) {
    if(!checkpoint::enabled()) return;
    const auto command=checkpoint::pending.exchange(checkpoint::Request::None);
    if(!practice(base)) {
        checkpoint_slot.clear();
        if(command!=checkpoint::Request::None) checkpoint::status("Checkpoints are available in Practice only");
        return;
    }
    if(command==checkpoint::Request::None) return;
    const auto id=checkpoint_identity(base);
    if(!id.supported()) {
        checkpoint::status("Prototype supports native roster slots only (including native Hwoarang replacement)");
        return;
    }
    if(!guest_memory_committed(checkpoint::kScratchBegin,checkpoint::kScratchBytes)) {
        checkpoint::status("Checkpoint recording buffer unavailable");return;
    }
    std::span<uint8_t> scratch(base+checkpoint::kScratchBegin,checkpoint::kScratchBytes);
    if(command==checkpoint::Request::Save) {
        std::vector<uint8_t> before(12*0x2960);
        for(size_t i=0;i<12;++i) std::memcpy(before.data()+i*0x2960,base+id.objects[i].address,0x2960);
        bool changed=false;
        checkpoint::preserve_scratch(scratch,[&] {
            call(ctx,base,sub_03A45CA4,{});
            for(size_t i=0;i<12;++i) changed |= std::memcmp(before.data()+i*0x2960,base+id.objects[i].address,0x2960)!=0;
            if(!changed) checkpoint_slot.save(id,scratch);
        });
        if(changed) { checkpoint_slot.clear();checkpoint::status("Capture rejected: combat objects changed during copying"); }
        else checkpoint::status("Checkpoint saved - F8 to load");
    } else {
        if(!checkpoint_slot.matches(id)) {
            checkpoint::status("No matching checkpoint - F5 to save again");return;
        }
        checkpoint::preserve_scratch(scratch,[&] {
            std::copy(checkpoint_slot.bytes().begin(),checkpoint_slot.bytes().end(),scratch.begin());
            call(ctx,base,sub_03A472A4,{});
        });
        checkpoint::status("Checkpoint loaded - F5 to replace, F8 to repeat");
    }
}

// Investigation-only observer for the title's OWN combat copy/restore pair.
// It reads combat state and logs only when TTT2_CHECKPOINT_OBSERVE is set.
constexpr uint32_t kCombatObjects = 12, kCombatObjectBytes = 0x2960;
bool checkpoint_observing() {
    static const bool enabled = std::getenv("TTT2_CHECKPOINT_OBSERVE") != nullptr;
    return enabled;
}
void observe_combat(const char* event, uint8_t* base) {
    if (!checkpoint_observing() || !practice(base)) return;
    for (uint32_t i = 0; i < kCombatObjects; ++i) {
        const uint32_t p = load(base, kSidePlayers + 4*i);
        if (!p || !guest_memory_committed(p, kCombatObjectBytes)) {
            std::fprintf(stderr,"checkpoint-observe event=%s object=%u unavailable=%08X\n",event,i,p);
            continue;
        }
        const uint32_t move = load(base,p+280), animator=load(base,p+7944);
        uint32_t motion=0;
        if (animator && guest_memory_committed(animator,20)) motion=load(base,animator+12);
        std::fprintf(stderr,
            "checkpoint-observe event=%s object=%u player=%08X id=%u row=%u record=%08X partner=%08X move=%08X frame=%u active=%u owner=%u assist=%u animator=%08X motion=%08X pos=%08X/%08X/%08X floor=%08X damage=%u/%u combo=%u\n",
            event,i,p,load(base,p+84),load(base,p+80),load(base,p+88),load(base,p+172),
            move,load(base,p+212),load(base,p+7808),load(base,p+7808),load(base,p+7816),
            animator,motion,load(base,p),load(base,p+4),load(base,p+8),load(base,p+72),
            load(base,p+1176),load(base,p+1180),load(base,p+0x1cc));
    }
}


} // namespace

PPC_FUNC(sub_039C2DB0_orig);
PPC_FUNC(sub_039C2DB0) { // Any native situation reset starts a new checkpoint generation.
    ++checkpoint_generation;
    const bool had_slot=checkpoint_slot.valid();checkpoint_slot.clear();
    if(had_slot && checkpoint::enabled()) checkpoint::status("Checkpoint cleared by practice reset");
    sub_039C2DB0_orig(ctx,base);
}
PPC_FUNC(sub_05FBD4C8); // -> the camera
PPC_FUNC(sub_05FBB480); // the camera (r3) as at a round's start (r4 = 0)
PPC_FUNC(sub_05FBC0A4); // the camera (r3) of a side (r4 = 2: 2P; f1 = 1, r5 = 1)

// The fighters' frame (not while the pause menu is open): the chord can happen.
PPC_FUNC(sub_03ADB118_orig);
PPC_FUNC(sub_03ADB118) {
    process_checkpoint(ctx,base);
    if (checkpoint_observing() && practice(base)) {
        static uint64_t ticks=0;
        if (++ticks % 120 == 1) observe_combat("fighter-frame",base);
    }
    if (practice(base)) os::arm_select_chord(three_held(base));
    sub_03ADB118_orig(ctx, base);
}

PPC_FUNC(sub_0726DF8C_orig);
PPC_FUNC(sub_0726DF8C) {
    if (os::take_select_chord() && practice(base)) {
        const bool reverse = load(base, kPracticeSettings + kReverse) == 1;
        if (std::getenv("TTT2_TRACE_PRACTICE")) {
            std::fprintf(stderr, "ttt2: practice: position reset%s\n", reverse ? " (reversed)" : "");
        }
        call(ctx, base, sub_039C2DB0, {kPracticeStart});
        const uint32_t camera = call(ctx, base, sub_05FBD4C8, {});
        call(ctx, base, sub_05FBB480, {camera, 0});
        if (reverse) call(ctx, base, sub_05FBC0A4, {camera, k2PCamera, 1}, 1.0);
    }
    sub_0726DF8C_orig(ctx, base);
}

// Preserve normal engine behavior. Trace the native demonstration save/restore
// paths so their object lifetimes and animation resync can be validated live.
PPC_FUNC(sub_03A45CA4_orig);
PPC_FUNC(sub_03A45CA4) {
    std::array<uint32_t,kCombatObjects> objects{};
    std::vector<uint8_t> before;
    if (checkpoint_observing() && practice(base)) {
        bool valid=true;
        for (uint32_t i=0;i<kCombatObjects;++i) {
            objects[i]=load(base,kSidePlayers+4*i);
            valid &= objects[i] && guest_memory_committed(objects[i],kCombatObjectBytes);
        }
        if (valid) {
            before.resize(kCombatObjects*kCombatObjectBytes);
            for (uint32_t i=0;i<kCombatObjects;++i)
                std::memcpy(before.data()+i*kCombatObjectBytes,base+objects[i],kCombatObjectBytes);
            observe_combat("native-save-before",base);
        }
    }
    sub_03A45CA4_orig(ctx,base);
    if (!before.empty()) {
        unsigned changed=0;
        for (uint32_t i=0;i<kCombatObjects;++i)
            for (uint32_t b=0;b<kCombatObjectBytes;++b)
                changed += before[i*kCombatObjectBytes+b] != base[objects[i]+b];
        std::fprintf(stderr,"checkpoint-observe native-save source_bytes_changed=%u scratch=108A3C08-108C2E90\n",changed);
    }
}
PPC_FUNC(sub_03A472A4_orig);
PPC_FUNC(sub_03A472A4) {
    observe_combat("native-restore-before",base);
    sub_03A472A4_orig(ctx,base);
    observe_combat("native-restore-after",base);
}
