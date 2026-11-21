#pragma once

// The rule of the thread that keeps the memory the GPU reads on huge pages
// (keep_guest_memory_fast, memory.cpp): which blocks a pass asks the kernel
// for, whether a block of the thread's reserve is given back first, when the
// next pass comes, and what the log is told. No system calls here: a test
// plays it through with made-up answers (tests/memory_keeper_test.cpp).
//
// A block the kernel turns down in three passes in a row as busy (EAGAIN: a
// page held in place, as a driver pins memory it imports) or as not for it
// (EINVAL) is left alone; asked again, it would be turned down again, every
// pass, for as long as the game runs. It gets a fresh start once it is seen
// on a huge page, and the blocks left alone are looked at again now and then:
// up to four of them, in turn, 30 s after the last were left alone, then
// after 60, 120 and every 240 s while they are still turned down; one made
// (its pages let go) gives all of them a fresh start. A block turned down
// before is asked without a reserve block given back first (those refusals
// come before the kernel allocates anything), and so is every block of the
// pass after one whose calls (four or more) were all turned down as busy; a
// block made brings the reserve back.
// Only blocks made are progress, and only while the kernel has the memory
// for them: a pass that made none, or one in which the kernel said it had no
// memory (or the game's memory limit was reached) even if it made a few,
// waits 1, 2, 4, then 8 s before the next. Every such answer means the kernel
// compacted and reclaimed memory for a 2 MiB block, which takes the coldest
// pages of the PC, the game's own code and data among them; on a PC that
// short, a pass a second making one or two blocks pushed the rest of the game
// out of memory for minutes and it ran slower than with no keeper at all.
// With nothing left to ask (every block on a huge page, or the rest left
// alone) a pass every four seconds looks for blocks newly without one. Each
// kind of failure is told once.

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <iterator>
#include <map>
#include <vector>

namespace cafe::keeper {

// What the kernel said to one block (MADV_COLLAPSE).
enum class Answer {
    made,      // the block has its huge page now
    had,       // it had one already (without the page map: a call that returned at once)
    no_memory, // ENOMEM: the PC has no free 2 MiB block
    limit,     // EBUSY: no room under the game's memory limit (its cgroup)
    busy,      // EAGAIN: a page is held in place (pinned), locked or being moved
    refused,   // EINVAL (or another error): the kernel will not do it for this block
};

// The kinds of failure, each told once in the log.
enum Kind : unsigned { kNoMemory = 1u << 0, kLimit = 1u << 1, kBusy = 1u << 2, kRefused = 1u << 3 };

class Plan {
public:
    static constexpr int kStrikes = 3;          // passes in a row a block is turned down before it is left alone
    static constexpr size_t kAllBusy = 4;       // calls in a pass, all turned down as busy: the next pass goes without the reserve
    static constexpr double kSlowCallMs = 20;   // a call this long ends the burst (the kernel had to look for memory)
    static constexpr double kQuietMs = 1000;    // after a pass that made blocks
    static constexpr double kCalmMs = 4000;     // with nothing left to ask
    static constexpr double kLongestMs = 8000;  // the longest wait after passes that made none (or met no memory)
    static constexpr double kLookAgainMs = 30000;       // blocks left alone: the first look again
    static constexpr double kLookAgainLongestMs = 240000; // ... and the longest time between two looks
    static constexpr size_t kLookAgainBlocks = 4;       // blocks left alone asked again at a look

    // A pass with the page map, at now_ms (any steady clock): the blocks
    // without a huge page. Returns those to ask for, in address order (the
    // ones left alone taken out, but for those looked at again). A block no
    // longer among them is forgotten.
    const std::vector<uintptr_t>& begin(const std::vector<uintptr_t>& missing, double now_ms) {
        missing_ = missing;
        std::sort(missing_.begin(), missing_.end());
        for (auto it = strikes_.begin(); it != strikes_.end();) {
            it = std::binary_search(missing_.begin(), missing_.end(), it->first) ? std::next(it) : strikes_.erase(it);
        }
        start_pass(true, now_ms);
        to_try_.clear();
        for (uintptr_t block : missing_) {
            if (!left_alone(block)) to_try_.push_back(block);
        }
        return to_try_;
    }

    // A pass without the page map (a kernel before 6.7): the caller asks
    // every block in turn, skipping those left_alone().
    void begin_blind(double now_ms) {
        missing_.clear();
        start_pass(false, now_ms);
        to_try_.clear();
    }

    bool left_alone(uintptr_t block) const {
        const auto it = strikes_.find(block);
        return it != strikes_.end() && it->second.count >= kStrikes &&
               std::find(looking_.begin(), looking_.end(), block) == looking_.end();
    }

    // Whether a block of the reserve is given back right before this block is
    // asked for (so its huge page is where the kernel finds one).
    bool reserve_for(uintptr_t block) const { return with_reserve_ && strikes_.find(block) == strikes_.end(); }

    // The reserve could not be filled: the kernel had no memory.
    void reserve_short() { ++no_memory_; }

    // One call's answer; false: the burst ends (the kernel has no memory to
    // give, or had to look for it).
    bool answer(uintptr_t block, Answer a, double call_ms) {
        ++tried_;
        const bool looked = std::find(looking_.begin(), looking_.end(), block) != looking_.end();
        look_tried_ += looked;
        look_busy_ += looked && a == Answer::busy;
        switch (a) {
        case Answer::made:
        case Answer::had:
            made_ += a == Answer::made;
            strikes_.erase(block);
            let_go_ = let_go_ || looked;
            break;
        case Answer::no_memory: ++no_memory_; break;
        case Answer::limit: ++limit_; break;
        case Answer::busy:
        case Answer::refused: {
            (a == Answer::busy ? busy_ : refused_)++;
            Strike& s = strikes_[block];
            const bool was_left = s.count >= kStrikes;
            s.count = std::min(s.count + 1, kStrikes);
            s.kind = a == Answer::busy ? kBusy : kRefused;
            if (s.count == kStrikes && !was_left) {
                newly_left_ |= s.kind;
                last_left_ms_ = now_ms_;
            }
            break;
        }
        }
        return call_ms < kSlowCallMs && a != Answer::no_memory && a != Answer::limit;
    }

    // The end of a pass: milliseconds until the next. With the page map the
    // plan knows whether the blocks are all on huge pages and whether it made
    // any; without it the caller says (whole, progress: from the kernel's
    // counts of the process's memory).
    double end(bool whole_blind = false, bool progress_blind = false) {
        // The look again: a block made gives all left alone a fresh start;
        // none made, the next look comes twice as late (up to 240 s).
        fresh_start_ = false;
        if (!looking_.empty()) {
            if (let_go_) {
                for (auto it = strikes_.begin(); it != strikes_.end();) {
                    it = it->second.count >= kStrikes ? strikes_.erase(it) : std::next(it);
                }
                look_every_ = kLookAgainMs;
                fresh_start_ = true;
            } else {
                look_every_ = std::min(look_every_ * 2, kLookAgainLongestMs);
            }
            looked_ms_ = now_ms_;
            looking_.clear();
        }
        // The kernel said it had no memory (or the limit): it compacted and
        // reclaimed for nothing, so the pass is no progress, blocks made or not.
        strained_ = no_memory_ > 0 || limit_ > 0;
        if (known_) {
            whole_ = missing_.size() == made_;
            progress_ = made_ > 0 && !strained_;
            // (the blocks made had no strikes left; all the others left alone)
            const auto alone = std::count_if(missing_.begin(), missing_.end(), [&](uintptr_t b) { return left_alone(b); });
            settled_ = !whole_ && static_cast<size_t>(alone) + made_ == missing_.size();
        } else {
            whole_ = whole_blind;
            progress_ = progress_blind && !strained_;
            settled_ = false;
        }
        // (the calls of a look again do not count: those blocks go without it anyway)
        const size_t tried = tried_ - look_tried_, busy = busy_ - look_busy_;
        with_reserve_ = made_ > 0 || !(tried >= kAllBusy && busy == tried);
        double delay;
        if (whole_ || settled_) {
            delay = kCalmMs;
            wait_ = kQuietMs;
        } else if (progress_) {
            delay = kQuietMs;
            wait_ = kQuietMs;
        } else {
            delay = wait_;
            wait_ = std::min(wait_ * 2, kLongestMs);
        }
        news_ = newly_left_;
        if (!progress_ && no_memory_ > 0) news_ |= kNoMemory;
        if (!progress_ && limit_ > 0) news_ |= kLimit;
        news_ &= ~told_;
        told_ |= news_;
        return delay;
    }

    // After end(): every block on a huge page / the rest all left alone /
    // blocks made (or, blind, more memory on huge pages) / the kinds of
    // failure to tell the log now (each once).
    bool whole() const { return whole_; }
    bool settled() const { return settled_; }
    bool progress() const { return progress_; }
    unsigned news() const { return news_; }
    // The kernel said no memory (or the limit) in this pass.
    bool strained() const { return strained_; }
    // A block left alone was made when looked at again: the others got a fresh start.
    bool fresh_start() const { return fresh_start_; }
    // Blocks left alone asked again in this pass.
    size_t looked_at() const { return looked_at_; }

    // This pass's calls.
    size_t tried() const { return tried_; }
    size_t made() const { return made_; }
    size_t busy() const { return busy_; }
    size_t refused() const { return refused_; }
    size_t no_memory() const { return no_memory_; }
    size_t limit() const { return limit_; }
    // Blocks left alone (of a kind, or all).
    size_t left(unsigned kinds = kBusy | kRefused) const {
        return static_cast<size_t>(std::count_if(strikes_.begin(), strikes_.end(), [&](const auto& s) {
            return s.second.count >= kStrikes && (s.second.kind & kinds) != 0;
        }));
    }
    bool with_reserve() const { return with_reserve_; }

private:
    struct Strike {
        int count = 0;
        unsigned kind = 0;
    };

    void start_pass(bool known, double now_ms) {
        known_ = known;
        now_ms_ = now_ms;
        tried_ = made_ = busy_ = refused_ = no_memory_ = limit_ = look_tried_ = look_busy_ = 0;
        newly_left_ = 0;
        let_go_ = false;
        looking_.clear();
        // Time to look at blocks left alone again? Up to four, the ones after
        // the last looked at (by address), so each gets its turn.
        std::vector<uintptr_t> alone;
        for (const auto& [block, s] : strikes_) {
            if (s.count >= kStrikes) alone.push_back(block);
        }
        if (alone.empty()) look_every_ = kLookAgainMs;
        const double since = std::max(last_left_ms_, looked_ms_);
        if (!alone.empty() && now_ms_ - since >= look_every_) {
            auto from = std::upper_bound(alone.begin(), alone.end(), look_cursor_);
            for (size_t n = 0; n < std::min(kLookAgainBlocks, alone.size()); ++n) {
                if (from == alone.end()) from = alone.begin();
                looking_.push_back(*from++);
            }
            look_cursor_ = looking_.back();
        }
        looked_at_ = looking_.size();
    }

    std::map<uintptr_t, Strike> strikes_; // blocks turned down in the passes before, in a row
    std::vector<uintptr_t> missing_, to_try_;
    std::vector<uintptr_t> looking_;      // blocks left alone, asked again this pass
    bool known_ = true, with_reserve_ = true, whole_ = false, settled_ = false, progress_ = false, strained_ = false;
    bool let_go_ = false, fresh_start_ = false;
    double wait_ = kQuietMs;
    double now_ms_ = 0, last_left_ms_ = 0, looked_ms_ = 0, look_every_ = kLookAgainMs;
    uintptr_t look_cursor_ = 0;
    size_t tried_ = 0, made_ = 0, busy_ = 0, refused_ = 0, no_memory_ = 0, limit_ = 0, looked_at_ = 0;
    size_t look_tried_ = 0, look_busy_ = 0;
    unsigned newly_left_ = 0, news_ = 0, told_ = 0;
};

} // namespace cafe::keeper
