// Video-memory copies of what the GPU reads most (renderer.h).
//
// Stream-out output. Each frame the title skins its fighters with
// stream-out draws into four large buffers, which the draws after it read
// as vertex buffers and the next frames' skinning reads again (each
// vertex's state). A buffer seen in two frames a few apart, 1 MiB or more
// (its draws share its end), gets a copy in video memory at the swap. A
// stream-out draw that writes every byte of its vertices
// (TranslatedShader::stream_out_complete, not indexed, one instance)
// writes the copy instead, with the descriptor's size (so the same writes
// past the end are dropped); once recorded, its range is noted (a span) and
// queued to be copied back to guest memory at the next barrier, which the
// first draw after a run of stream-out draws brings anyway. So guest memory
// is right for the CPU once the frame retires, and for anything reading it
// in place. A vertex buffer reads the copy only where every byte the draw
// can fetch (its index range times the stride plus what its fetches read
// past a vertex's start, TranslatedShader::vb_extent) lies in spans
// written in the last kShadowFrames frames and kShadowSeconds; everything
// else reads guest memory. CPU writes the title announces (cpu_wrote),
// stream-out written in place and render targets written back forget
// spans.
//
// Ordering: copies back are recorded at a barrier and finished by the
// next; a draw that reads or writes guest memory under one queued or still
// running gets barriers first (copies_back_pending). A barrier from the
// copies to the host makes them visible to the CPU when their submission
// retires.
//
// Constants. Stream-out draws that write video memory read their buffer
// resources (bone palettes, a few hundred bytes each, read about 28 times
// a vertex) and uniform blocks from video memory the CPU writes
// (video_ring_), copied as the draw is built: what the GPU reads in place
// cannot change before the draw retires (renderer.h), which interpolation's
// records rely on too.
//
// TTT2_SHADOWS=0 reads everything in place (the default on integrated
// GPUs, whose memory is all one); TTT2_SHADOW_CHECK=1 compares the spans
// with guest memory after each frame finished; 2 also draws each
// stream-out draw the old way into guest memory first, without copies
// back, so the spans compare the two paths.

#include "gpu/vulkan/renderer.h"

#include "gpu/latte.h"

#include "cafe/runtime.h"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace cafe::gpu::vk {
namespace {

using namespace latte;

constexpr uint64_t kShadowFrames = 4;      // spans older read guest memory (skinning reads state 1-3 frames back)
constexpr double kShadowSeconds = 0.25;    // and spans older than that (a load between frames)
constexpr uint32_t kMinShadow = 1u << 20;  // smaller stream-out buffers stay in guest memory
constexpr VkDeviceSize kShadowBudget = 256ull << 20;
constexpr VkDeviceSize kVideoHeadroom = 512ull << 20; // video memory left for everything else
constexpr VkDeviceSize kVideoRing = 8ull << 20;       // 8 chunks of 1 MiB
constexpr uint32_t kMaxVideoConstant = 64u << 10;
constexpr uint64_t kIdleFrames = 600;
constexpr uint64_t kRunGap = 8;         // frames between two a buffer is seen in, for it to count as in use
constexpr uint64_t kRetryFrames = 300;  // a buffer that got no video memory tries again after
constexpr uint64_t kMakeWayFrames = 60; // a copy idle that long gives way to a buffer in use over its range
constexpr size_t kMaxCandidates = 16;

double now_seconds() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

abi::Buffer descriptor(VkDeviceAddress a, uint32_t size, uint32_t stride) {
    return {static_cast<uint32_t>(a), static_cast<uint32_t>(a >> 32), size, stride};
}

using Spans = std::map<uint32_t, Renderer::StreamShadow::Span>;

// Removes [begin, end) from the spans, keeping what lies outside it.
void cut(Spans& spans, uint32_t begin, uint64_t end) {
    auto it = spans.lower_bound(begin);
    if (it != spans.begin()) {
        auto prev = std::prev(it);
        if (prev->second.end > begin) {
            const auto tail = prev->second;
            prev->second.end = begin;
            if (tail.end > end) spans.emplace(static_cast<uint32_t>(end), tail);
        }
    }
    it = spans.lower_bound(begin);
    while (it != spans.end() && it->first < end) {
        if (it->second.end > end) {
            const auto rest = it->second;
            spans.erase(it);
            spans.emplace(static_cast<uint32_t>(end), rest);
            break;
        }
        it = spans.erase(it);
    }
}

void report_once(const char* what, uint32_t a, uint32_t b) {
    static std::vector<std::pair<uint32_t, uint32_t>> seen;
    for (const auto& s : seen) {
        if (s.first == a && s.second == b) return;
    }
    seen.emplace_back(a, b);
    std::fprintf(stderr, "ttt2: gpu: %s (0x%08X-0x%08X)\n", what, a, b);
}

} // namespace

void Renderer::init_shadows() {
    const char* on = std::getenv("TTT2_SHADOWS");
    if (const char* c = std::getenv("TTT2_SHADOW_CHECK")) shadow_check_ = std::atoi(c);
    const char* why = nullptr;
    if (on != nullptr && *on == '0') why = "TTT2_SHADOWS=0";
    else if (ctx_.properties.deviceType != VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU && !(on != nullptr && *on == '1'))
        why = "not a discrete GPU";
    if (why != nullptr) {
        std::fprintf(stderr, "ttt2: GPU: stream-out output read in place (%s)\n", why);
        shadow_check_ = 0;
        return;
    }
    shadows_on_ = true;
    video_constants_on_ = video_ring_.init(ctx_, kVideoRing,
                                           VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    std::fprintf(stderr, "ttt2: GPU: stream-out output and %s in video memory (TTT2_SHADOWS=0 reads them in place)%s\n",
                 video_constants_on_ ? "the constants of the draws writing it"
                                     : "not their constants (no host-visible video memory)",
                 shadow_check_ == 2 ? ", both paths drawn and compared"
                 : shadow_check_    ? ", checked against guest memory"
                                    : "");
}

bool Renderer::touches_shadow(uint32_t begin, uint64_t end) const {
    for (const auto& s : shadows_) {
        if (begin < s->end && end > s->begin) return true;
    }
    return false;
}

// A stream-out draw's buffer `index` at guest base + offset, whose end is
// base + size, `vertices` written (0: indexed or instanced, any): the
// shadow's copy when one covers it and the draw writes every byte of its
// vertices, else guest memory as `so` has it, forgetting the copy there.
void Renderer::stream_out_target(uint32_t index, uint32_t base, uint32_t offset, uint32_t size, uint32_t stride,
                                 bool complete, uint32_t vertices, abi::Buffer& so, StreamWrites& writes) {
    const uint64_t end = uint64_t{base} + size;
    // A shadow candidate (1 MiB or more): its lowest base, its run of
    // frames (the title writes each buffer every other frame or so).
    if (end <= UINT32_MAX) {
        auto c = std::find_if(stream_buffers_.begin(), stream_buffers_.end(),
                              [&](const StreamBuffer& b) { return b.end == end; });
        if (c != stream_buffers_.end()) {
            c->begin = std::min(c->begin, base);
            if (c->last + kRunGap < frame_number_) c->first = frame_number_;
            c->last = frame_number_;
        } else if (size >= kMinShadow) {
            const StreamBuffer b{base, static_cast<uint32_t>(end), frame_number_, frame_number_, 0};
            if (stream_buffers_.size() < kMaxCandidates) {
                stream_buffers_.push_back(b);
            } else { // (the one seen longest ago makes way)
                *std::min_element(stream_buffers_.begin(), stream_buffers_.end(),
                                  [](const StreamBuffer& x, const StreamBuffer& y) { return x.last < y.last; }) = b;
            }
        }
    }
    const uint32_t start = base + offset;
    StreamShadow* s = nullptr;
    if (complete && vertices != 0) {
        for (const auto& sh : shadows_) {
            if (sh->end == end && sh->begin <= base) s = sh.get();
        }
    }
    if (s != nullptr) {
        const uint32_t bytes = static_cast<uint32_t>(std::min<uint64_t>(so.size, uint64_t{vertices} * stride));
        writes.video[writes.video_count++] = {s, index, start, start + bytes, so};
        so = descriptor(s->buffer.address + (start - s->begin), so.size, so.stride);
        s->used_frame = frame_number_;
        if (tracing()) std::fprintf(stderr, "trace:   so%u 0x%08X+0x%X into video memory\n", index, start, bytes);
        return;
    }
    if (tracing()) std::fprintf(stderr, "trace:   so%u 0x%08X+0x%X in place\n", index, start, so.size);
    // In place, anywhere up to the descriptor's end: a copy there is older.
    const uint64_t guest_end = std::min<uint64_t>(uint64_t{start} + so.size, UINT32_MAX);
    writes.guest[writes.guest_count][0] = start;
    writes.guest[writes.guest_count++][1] = static_cast<uint32_t>(guest_end);
    forget_written(start, guest_end);
}

// After the draw is recorded: its spans, and its copies back; what it
// wrote in place, by the submission holding it (one entry per buffer end).
void Renderer::note_stream_writes(const StreamWrites& writes) {
    for (uint32_t i = 0; i < writes.video_count; ++i) {
        const StreamWrites::Write& w = writes.video[i];
        if (w.end <= w.begin) continue;
        cut(w.shadow->written, w.begin, w.end);
        w.shadow->written.emplace(w.begin, StreamShadow::Span{w.end, frame_number_, recording_time_});
        copy_backs_.push_back({w.shadow, w.begin, w.end});
        shadow_stats_.written += w.end - w.begin;
    }
    for (uint32_t i = 0; i < writes.guest_count; ++i) {
        const uint32_t begin = writes.guest[i][0], end = writes.guest[i][1];
        auto it = std::find_if(stream_out_in_place_.begin(), stream_out_in_place_.end(),
                               [&](const StreamOutRange& r) { return r.end == end; });
        if (it == stream_out_in_place_.end()) {
            stream_out_in_place_.push_back({begin, end, submitted_ + 1});
        } else {
            it->begin = std::min(it->begin, begin);
            it->value = submitted_ + 1;
        }
    }
}

void Renderer::forget_written(uint32_t address, uint64_t end) {
    for (const auto& s : shadows_) {
        if (address < s->end && end > s->begin && !s->written.empty()) cut(s->written, address, end);
    }
}

// The vertex buffers of a draw (first..last its vertex indices) read from
// video memory where stream-out wrote all they can fetch recently; the
// ranges that read guest memory over a shadow go to `reads`.
void Renderer::redirect_vertex_buffers(const ShaderModule* vs, abi::DrawConstants& dc, const uint32_t* vb_address,
                                       uint32_t first, uint32_t last, bool stream_out_draw, GuestRanges& reads) {
    const double now = recording_ ? recording_time_ : now_seconds();
    for (uint32_t n = 0; n < 16; ++n) {
        const uint32_t extent = vs->info.vb_extent[n];
        abi::Buffer& b = dc.vb[n];
        const uint32_t a = vb_address[n];
        if (extent == 0 || b.size == 0 || first > last) continue;
        // What its fetches can read: in the shader's 32-bit arithmetic,
        // (index + base vertex) * stride + offset, bounded by the size;
        // unaligned words read the next word too.
        uint64_t lo = a, hi = uint64_t{a} + b.size;
        bool predicted = false;
        if (extent != UINT32_MAX) {
            const uint64_t v0 = uint64_t{first} + dc.base_vertex, v1 = uint64_t{last} + dc.base_vertex;
            const uint64_t top = v1 * b.stride + extent;
            if (v1 <= UINT32_MAX && top <= UINT32_MAX) {
                lo = (a + v0 * b.stride) & ~uint64_t{3};
                hi = a + std::min<uint64_t>(top, b.size) + (((a | b.stride) & 3) != 0 ? 4 : 0);
                predicted = true;
            }
        }
        if (lo >= hi) continue; // (nothing in bounds: no reads)
        if (!touches_shadow(a, hi)) {
            if (stream_out_draw) shadow_stats_.vertex_bytes += hi - lo;
            continue;
        }
        StreamShadow* s = nullptr;
        for (const auto& sh : shadows_) {
            if (a >= sh->begin && a < sh->end) s = sh.get();
        }
        uint64_t* reason = &shadow_stats_.unpredictable;
        if (predicted) {
            reason = &shadow_stats_.partial;
            if (s != nullptr && hi <= s->end) {
                // Contiguous spans over [lo, hi), all recent.
                auto it = s->written.upper_bound(static_cast<uint32_t>(lo));
                bool old = false;
                if (it != s->written.begin()) {
                    --it;
                    uint64_t at = lo;
                    while (it != s->written.end() && it->first <= at && it->second.end > at) {
                        old |= it->second.frame + kShadowFrames <= frame_number_ ||
                               now - it->second.time > kShadowSeconds;
                        at = it->second.end;
                        if (at >= hi) break;
                        ++it;
                    }
                    if (at >= hi) reason = old ? &shadow_stats_.old : nullptr;
                }
            }
        }
        if (reason == nullptr) {
            b = descriptor(s->buffer.address + (a - s->begin), std::min(b.size, s->end - a), b.stride);
            s->used_frame = frame_number_;
            ++shadow_stats_.hits;
            continue;
        }
        ++*reason;
        if (stream_out_draw) shadow_stats_.vertex_bytes += hi - lo;
        reads.add(static_cast<uint32_t>(lo), hi);
        if (tracing()) {
            const char* why = reason == &shadow_stats_.old       ? "not recent"
                              : reason == &shadow_stats_.partial ? "partly written"
                                                                 : "unpredictable";
            std::fprintf(stderr, "trace:   vb%u 0x%08X+0x%X read in place (%s): 0x%08X-0x%08X\n", n, a, b.size, why,
                         static_cast<uint32_t>(lo), static_cast<uint32_t>(hi));
        }
    }
}

// The buffer resources and uniform blocks of a stream-out draw writing
// video memory, copied into video memory (where the CPU can write).
void Renderer::video_constants(const Registers& regs, const ShaderModule* vs, abi::DrawConstants& dc) {
    const FrameRecord& record = frame_records_[current_record_];
    const auto copy = [&](abi::Buffer& b, uint32_t guest, uint32_t bytes) {
        if (bytes == 0) return;
        const VkDeviceAddress from = b.address_lo | (uint64_t{b.address_hi} << 32);
        // (Stream-out output is written by the GPU after this copy: in
        // video memory, or in place by a submission yet to finish.)
        const uint64_t guest_end = uint64_t{guest} + bytes;
        bool written = touches_shadow(guest, guest_end);
        for (const StreamOutRange& r : stream_out_in_place_) written |= guest < r.end && guest_end > r.begin;
        const uint8_t* source = nullptr;
        uint32_t address = 0;
        if (record.data.mapped != nullptr && from >= record.data.address &&
            from - record.data.address + bytes <= record.data.size) {
            source = record.data.mapped + (from - record.data.address); // interpolation's copy
        } else if (guest_.guest_address(from, bytes, address) && guest_memory_committed(address, bytes)) {
            source = guest_pointer(address);
        }
        if (bytes > kMaxVideoConstant || written || source == nullptr) {
            ++shadow_stats_.in_place;
            return;
        }
        // At an address with the same low bits: shaders round addresses down.
        const VkDeviceSize need = bytes + 256;
        VkDeviceSize offset = 0;
        uint8_t* p = video_ring_.allocate(need, 256, offset);
        if (p == nullptr) {
            const uint32_t next = video_ring_.next_chunk();
            if (draw_video_chunks_ & (1u << next) || need > video_ring_.chunk_size()) {
                ++shadow_stats_.in_place;
                return;
            }
            if (video_chunks_touched_ & (1u << next)) submit(false); // the commands being recorded use it
            wait_value(video_chunk_value_[next]);
            video_ring_.advance();
            p = video_ring_.allocate(need, 256, offset);
        }
        video_chunks_touched_ |= 1u << video_ring_.chunk();
        draw_video_chunks_ |= 1u << video_ring_.chunk();
        const VkDeviceSize shift = (from - (video_ring_.address() + offset)) & 255;
        std::memcpy(p + shift, source, bytes);
        b = descriptor(video_ring_.address() + offset + shift, bytes, b.stride);
        shadow_stats_.constants += bytes;
        ++shadow_stats_.blocks;
    };
    for (uint32_t i = 0; i < 16; ++i) {
        if ((vs->info.buffer_mask >> i) & 1) {
            const uint32_t base = kResourceBase + (resource::kVsBuffer + i) * resource::kWords * 4;
            copy(dc.vs_buf[i], regs[base], dc.vs_buf[i].size);
        }
        if ((vs->info.constant_bank_mask >> i) & 1) {
            const uint32_t extent = vs->info.constant_bank_extent[i];
            copy(dc.vs_cb[i], regs[reg::SQ_ALU_CONST_CACHE_VS_0 + i * 4] << 8,
                 extent == UINT32_MAX ? dc.vs_cb[i].size : std::min(dc.vs_cb[i].size, extent));
        }
    }
}

// Whether a draw reading or writing `ranges` and writing `writes` must wait
// for copies back: 0 no, 1 for copies running (a barrier), 2 for copies
// yet to be recorded (two: one records them, one waits for them).
int Renderer::copies_back_pending(const GuestRanges& ranges, const StreamWrites& writes) const {
    const auto overlaps = [](const std::vector<CopyBack>& copies, uint32_t begin, uint32_t end) {
        for (const CopyBack& c : copies) {
            if (c.begin < end && begin < c.end) return true;
        }
        return false;
    };
    int pending = ranges.overflow ? 2 : 0;
    const auto test = [&](uint32_t begin, uint32_t end) {
        if (!touches_shadow(begin, end)) return; // (copies back are all in shadows)
        if (overlaps(copy_backs_, begin, end)) pending = 2;
        else if (overlaps(unsynced_, begin, end)) pending = std::max(pending, 1);
    };
    for (uint32_t i = 0; i < ranges.count; ++i) test(ranges.range[i][0], ranges.range[i][1]);
    for (uint32_t i = 0; i < writes.guest_count; ++i) test(writes.guest[i][0], writes.guest[i][1]);
    // (A copy back reading what the draw writes again: one queued could be
    // recorded just before the draw, by the pass it begins.)
    for (uint32_t i = 0; i < writes.video_count && pending < 2; ++i) {
        if (overlaps(copy_backs_, writes.video[i].begin, writes.video[i].end)) pending = 2;
        else if (overlaps(unsynced_, writes.video[i].begin, writes.video[i].end)) pending = 1;
    }
    return pending;
}

// At a barrier (outside a pass): the stream-out output written since the
// last one, copied back to guest memory; the next barrier finishes it.
void Renderer::copy_back() {
    if (shadow_check_ == 2) { // (guest memory has the old path's output)
        copy_backs_.clear();
        return;
    }
    std::sort(copy_backs_.begin(), copy_backs_.end(), [](const CopyBack& x, const CopyBack& y) {
        return x.shadow != y.shadow ? x.shadow < y.shadow : x.begin < y.begin;
    });
    // Overlapping and adjacent ranges merged (not across the gaps between
    // parts: other draws' output may lie there).
    std::vector<CopyBack> merged;
    for (const CopyBack& c : copy_backs_) {
        if (!merged.empty() && merged.back().shadow == c.shadow && c.begin <= merged.back().end) {
            merged.back().end = std::max(merged.back().end, c.end);
        } else {
            merged.push_back(c);
        }
    }
    copy_backs_.clear();
    std::vector<VkBufferCopy> regions;
    uint64_t bytes = 0;
    for (size_t i = 0; i < merged.size();) {
        StreamShadow* s = merged[i].shadow;
        VkBuffer guest = VK_NULL_HANDLE;
        regions.clear();
        for (; i < merged.size() && merged[i].shadow == s; ++i) {
            VkBuffer buffer;
            VkDeviceSize offset;
            if (!guest_.locate(merged[i].begin, merged[i].end - merged[i].begin, buffer, offset)) {
                // (Across guest memory's regions: what video memory holds is
                // forgotten, readers take guest memory.)
                cut(s->written, merged[i].begin, merged[i].end);
                report_once("stream-out output not in one guest memory region, not copied back", merged[i].begin,
                            merged[i].end);
                continue;
            }
            if (guest != VK_NULL_HANDLE && buffer != guest) {
                vkCmdCopyBuffer(cmd(), s->buffer.buffer, guest, static_cast<uint32_t>(regions.size()), regions.data());
                regions.clear();
            }
            guest = buffer;
            regions.push_back({merged[i].begin - s->begin, offset, merged[i].end - merged[i].begin});
            bytes += merged[i].end - merged[i].begin;
        }
        if (!regions.empty()) {
            vkCmdCopyBuffer(cmd(), s->buffer.buffer, guest, static_cast<uint32_t>(regions.size()), regions.data());
        }
    }
    // For the CPU once the submission retires (the GPU's own reads wait
    // for the next barrier).
    VkMemoryBarrier2 mb{VK_STRUCTURE_TYPE_MEMORY_BARRIER_2};
    mb.srcStageMask = VK_PIPELINE_STAGE_2_COPY_BIT;
    mb.srcAccessMask = VK_ACCESS_2_TRANSFER_WRITE_BIT;
    mb.dstStageMask = VK_PIPELINE_STAGE_2_HOST_BIT;
    mb.dstAccessMask = VK_ACCESS_2_HOST_READ_BIT;
    VkDependencyInfo di{VK_STRUCTURE_TYPE_DEPENDENCY_INFO};
    di.memoryBarrierCount = 1;
    di.pMemoryBarriers = &mb;
    vkCmdPipelineBarrier2(cmd(), &di);
    unsynced_ = std::move(merged);
    shadow_stats_.copied += bytes;
    profile_mark("stream-out copy back", static_cast<uint32_t>(bytes), static_cast<uint32_t>(unsynced_.size()));
    if (tracing()) {
        std::fprintf(stderr, "trace: stream-out copy back, %zu ranges, %llu bytes\n", unsynced_.size(),
                     static_cast<unsigned long long>(bytes));
    }
}

// At the swap: spans no later draw may read dropped; shadows made for the
// stream-out buffers in use (seen in this frame and one shortly before),
// remade when one grows, dropped when unused or when a buffer in use with
// another end needs their range.
void Renderer::update_shadows() {
    if (!shadows_on_) return;
    const uint64_t next = frame_number_ + 1;
    for (const auto& s : shadows_) {
        for (auto it = s->written.begin(); it != s->written.end();) {
            if (it->second.frame + 2 * kShadowFrames <= next) it = s->written.erase(it); // (kept a while: "not recent")
            else ++it;
        }
    }
    if (!stream_out_in_place_.empty()) { // (written by submissions now finished: in guest memory)
        uint64_t done = 0;
        VK_CHECK(vkGetSemaphoreCounterValue(ctx_.device, timeline_, &done));
        std::erase_if(stream_out_in_place_, [&](const StreamOutRange& r) { return r.value <= done; });
    }
    std::vector<StreamShadow*> drop;
    for (const auto& s : shadows_) {
        if (s->used_frame + kIdleFrames < frame_number_) drop.push_back(s.get());
    }
    for (const StreamBuffer& c : stream_buffers_) {
        if (c.last != frame_number_ || c.last == c.first || c.retry > frame_number_) continue;
        for (const auto& s : shadows_) {
            // Grown: made again. Another buffer's over this one's range,
            // idle a while (not at once: two in turn would remake theirs
            // again and again): made for this one.
            const bool grown = s->end == c.end && s->begin > c.begin;
            const bool over = s->end != c.end && c.begin < s->end && c.end > s->begin;
            if (grown || (over && s->used_frame + kMakeWayFrames < frame_number_)) drop.push_back(s.get());
        }
    }
    if (!drop.empty()) {
        submit(true); // (nothing recorded uses them now)
        unsynced_.clear();
        for (StreamShadow* s : drop) {
            const auto it = std::find_if(shadows_.begin(), shadows_.end(), [&](const auto& p) { return p.get() == s; });
            if (it == shadows_.end()) continue;
            ctx_.destroy_buffer((*it)->buffer);
            shadows_.erase(it);
        }
    }
    VkDeviceSize total = 0;
    for (const auto& s : shadows_) total += s->end - s->begin;
    for (StreamBuffer& c : stream_buffers_) {
        if (c.last != frame_number_ || c.last == c.first || c.retry > frame_number_) continue;
        bool taken = false;
        for (const auto& s : shadows_) taken |= c.begin < s->end && c.end > s->begin;
        if (taken) continue;
        const VkDeviceSize size = c.end - c.begin;
        Buffer b;
        if (total + size <= kShadowBudget && ctx_.video_memory_left() >= size + kVideoHeadroom) {
            b = ctx_.try_create_buffer(size,
                                       VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT |
                                           VK_BUFFER_USAGE_TRANSFER_DST_BIT,
                                       VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT);
        }
        // (Its addresses keep guest memory's low bits, which shaders use.)
        if (b.buffer == VK_NULL_HANDLE || (b.address & 255) != 0) {
            ctx_.destroy_buffer(b);
            c.retry = frame_number_ + kRetryFrames;
            report_once("no video memory for a stream-out buffer, read in place for now", c.begin, c.end);
            continue;
        }
        end_rendering();
        vkCmdFillBuffer(cmd(), b.buffer, 0, VK_WHOLE_SIZE, 0); // (zeros where a wrong read would show)
        barrier();
        auto s = std::make_unique<StreamShadow>();
        s->begin = c.begin;
        s->end = c.end;
        s->buffer = b;
        s->used_frame = frame_number_;
        shadows_.push_back(std::move(s));
        total += size;
        std::fprintf(stderr, "ttt2: gpu: stream-out buffer 0x%08X-0x%08X in video memory\n", c.begin, c.end - 1);
    }
    std::erase_if(stream_buffers_, [&](const StreamBuffer& c) { return c.last + kIdleFrames < frame_number_; });
}

// TTT2_SHADOW_CHECK: at the swap, once the GPU finished the frame, every
// span's bytes in video memory against guest memory's.
void Renderer::check_shadows() {
    if (shadows_.empty()) return;
    constexpr VkDeviceSize kStaging = 32ull << 20;
    if (check_staging_.buffer == VK_NULL_HANDLE) {
        check_staging_ = ctx_.create_buffer(kStaging, VK_BUFFER_USAGE_TRANSFER_DST_BIT,
                                            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
                                            VK_MEMORY_PROPERTY_HOST_CACHED_BIT);
    }
    struct Range {
        uint32_t begin, end;
        VkDeviceSize staged;
    };
    std::vector<Range> batch;
    VkDeviceSize used = 0;
    const auto compare = [&] {
        if (batch.empty()) return;
        VkMemoryBarrier2 mb{VK_STRUCTURE_TYPE_MEMORY_BARRIER_2};
        mb.srcStageMask = VK_PIPELINE_STAGE_2_COPY_BIT;
        mb.srcAccessMask = VK_ACCESS_2_TRANSFER_WRITE_BIT;
        mb.dstStageMask = VK_PIPELINE_STAGE_2_HOST_BIT;
        mb.dstAccessMask = VK_ACCESS_2_HOST_READ_BIT;
        VkDependencyInfo di{VK_STRUCTURE_TYPE_DEPENDENCY_INFO};
        di.memoryBarrierCount = 1;
        di.pMemoryBarriers = &mb;
        vkCmdPipelineBarrier2(cmd(), &di);
        submit(true);
        for (const Range& r : batch) {
            const uint8_t* copy = check_staging_.mapped + r.staged;
            const uint8_t* guest = guest_pointer(r.begin);
            ++shadow_stats_.checked;
            shadow_stats_.checked_bytes += r.end - r.begin;
            if (std::memcmp(copy, guest, r.end - r.begin) == 0) continue;
            ++shadow_stats_.differ;
            if (check_logged_++ >= 16) continue;
            uint32_t at = 0;
            while (at + 4 <= r.end - r.begin && std::memcmp(copy + at, guest + at, 4) == 0) at += 4;
            uint32_t c = 0, g = 0;
            std::memcpy(&c, copy + at, std::min<uint32_t>(4, r.end - r.begin - at));
            std::memcpy(&g, guest + at, std::min<uint32_t>(4, r.end - r.begin - at));
            std::fprintf(stderr,
                         "ttt2: gpu: shadow check: frame %llu: 0x%08X+0x%X differs at +0x%X (video memory %08X, guest "
                         "%08X)\n",
                         static_cast<unsigned long long>(frame_number_), r.begin, r.end - r.begin, at, c, g);
        }
        batch.clear();
        used = 0;
    };
    submit(true); // (the frame's copies back done)
    unsynced_.clear();
    for (const auto& s : shadows_) {
        for (const auto& [begin, span] : s->written) {
            for (uint32_t at = begin; at < span.end;) {
                const uint32_t n = static_cast<uint32_t>(std::min<VkDeviceSize>(span.end - at, kStaging - used));
                if (n == 0) {
                    compare();
                    continue;
                }
                const VkBufferCopy region{at - s->begin, used, n};
                end_rendering();
                vkCmdCopyBuffer(cmd(), s->buffer.buffer, check_staging_.buffer, 1, &region);
                batch.push_back({at, at + n, used});
                used += n;
                at += n;
            }
        }
    }
    compare();
}

void Renderer::print_shadow_statistics(uint64_t frames) {
    const double f = static_cast<double>(std::max<uint64_t>(frames, 1));
    const ShadowStats& s = shadow_stats_;
    VkDeviceSize bytes = 0;
    for (const auto& sh : shadows_) bytes += sh->end - sh->begin;
    char check[160] = "";
    if (shadow_check_) {
        std::snprintf(check, sizeof(check), "; check: %llu ranges, %.1f MB compared, %llu differ",
                      static_cast<unsigned long long>(s.checked), s.checked_bytes / 1e6,
                      static_cast<unsigned long long>(s.differ));
    }
    std::fprintf(stderr,
                 "ttt2: gpu: video memory: %zu stream-out buffers (%.0f MB), %.2f MB written per frame (%.2f MB copied "
                 "back, %.2f extra barriers); vertex buffer reads from video memory %.0f, guest memory %.0f (%.0f not "
                 "recent, %.0f partly written, %.0f unpredictable) per title frame, replays included; stream-out "
                 "draws: constants %.1f KB per frame (%.0f blocks, %.1f in place), vertex data %.2f MB read in "
                 "place%s\n",
                 shadows_.size(), bytes / 1e6, s.written / f / 1e6, s.copied / f / 1e6, s.flushes / f, s.hits / f,
                 (s.old + s.partial + s.unpredictable) / f, s.old / f, s.partial / f, s.unpredictable / f,
                 s.constants / f / 1e3, s.blocks / f, s.in_place / f, s.vertex_bytes / f / 1e6, check);
    shadow_stats_ = ShadowStats{};
}

} // namespace cafe::gpu::vk
