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
// on a huge page. A block turned down before is asked without a reserve
// block given back first (those refusals come before the kernel allocates
// anything), and so is every block of the pass after one whose calls (four
// or more) were all turned down as busy; a block made brings the reserve
// back. Only blocks made are progress: a pass that made none waits 1, 2, 4,
// then 8 s before the next, and with nothing left to ask (every block on a
// huge page, or the rest left alone) a pass every four seconds looks for
// blocks newly without one. Each kind of failure is told once.

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
    static constexpr double kLongestMs = 8000;  // the longest wait after passes that made none

    // A pass with the page map: the blocks without a huge page. Returns those
    // to ask for, in address order (the ones left alone taken out). A block no
    // longer among them is forgotten.
    const std::vector<uintptr_t>& begin(const std::vector<uintptr_t>& missing) {
        start_pass(true);
        missing_ = missing;
        std::sort(missing_.begin(), missing_.end());
        for (auto it = strikes_.begin(); it != strikes_.end();) {
            it = std::binary_search(missing_.begin(), missing_.end(), it->first) ? std::next(it) : strikes_.erase(it);
        }
        to_try_.clear();
        for (uintptr_t block : missing_) {
            if (!left_alone(block)) to_try_.push_back(block);
        }
        return to_try_;
    }

    // A pass without the page map (a kernel before 6.7): the caller asks
    // every block in turn, skipping those left_alone().
    void begin_blind() {
        start_pass(false);
        missing_.clear();
        to_try_.clear();
    }

    bool left_alone(uintptr_t block) const {
        const auto it = strikes_.find(block);
        return it != strikes_.end() && it->second.count >= kStrikes;
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
        switch (a) {
        case Answer::made:
        case Answer::had:
            made_ += a == Answer::made;
            strikes_.erase(block);
            break;
        case Answer::no_memory: ++no_memory_; break;
        case Answer::limit: ++limit_; break;
        case Answer::busy:
        case Answer::refused: {
            (a == Answer::busy ? busy_ : refused_)++;
            Strike& s = strikes_[block];
            s.count = std::min(s.count + 1, kStrikes);
            s.kind = a == Answer::busy ? kBusy : kRefused;
            if (s.count == kStrikes) newly_left_ |= s.kind;
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
        if (known_) {
            whole_ = missing_.size() == made_;
            progress_ = made_ > 0;
            // (the blocks made had no strikes left; all the others left alone)
            const auto alone = std::count_if(missing_.begin(), missing_.end(), [&](uintptr_t b) { return left_alone(b); });
            settled_ = !whole_ && static_cast<size_t>(alone) + made_ == missing_.size();
        } else {
            whole_ = whole_blind;
            progress_ = progress_blind;
            settled_ = false;
        }
        with_reserve_ = made_ > 0 || !(tried_ >= kAllBusy && busy_ == tried_);
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

    void start_pass(bool known) {
        known_ = known;
        tried_ = made_ = busy_ = refused_ = no_memory_ = limit_ = 0;
        newly_left_ = 0;
    }

    std::map<uintptr_t, Strike> strikes_; // blocks turned down in the passes before, in a row
    std::vector<uintptr_t> missing_, to_try_;
    bool known_ = true, with_reserve_ = true, whole_ = false, settled_ = false, progress_ = false;
    double wait_ = kQuietMs;
    size_t tried_ = 0, made_ = 0, busy_ = 0, refused_ = 0, no_memory_ = 0, limit_ = 0;
    unsigned newly_left_ = 0, news_ = 0, told_ = 0;
};

} // namespace cafe::keeper
