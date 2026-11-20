#pragma once

// A tag team's won match, and the added fighters.
//
// The title plays a team's win in parts its movesets time between the two
// fighters (Arcade Battle, Ghost Battle and VS Battle alike; moves
// `<code>_wem_1..3` for the one who won, `<code>_wes_1..3` for the partner):
//   the winner's pose (wem_1)   | the partner waits, put away (wes_1)
//   the winner waits (wem_2)    | the partner's pose (wes_2)
//   both hold their last pose (wem_3, wes_3), whose end ends the scene.
// A part hands over with move property 0x80A2 at the frame the title's own
// pose ENDS (frame 100): it writes 1 into the other fighter's signal word,
// which that one's waiting move tests (requirement 313) to go on. A fighter's
// signal word is cleared whenever it starts a move.
//
// An added fighter's parts play its own win pose from Tekken 7 or 8, several
// seconds long, where the donor's lasted 100 frames (the importer keeps the
// donor's properties and their frames). So it handed over at frame 100 of a
// longer pose: the other started its part at once, finished it and handed
// back while the first was still posing, and that signal was cleared when the
// first went on to its waiting move. It then waited, put away, for a signal
// that had already come: the bonus panel over an empty stage, for ever (Start
// skips the scene). Any team with an added fighter in it met this when it won.
//
// Here an added fighter's part ends at its hand-over, as the donor's did (the
// move's frame is put past the animation's end, so the move goes on to the
// next one), and the hand-over is held back until the fighter has left the
// move (Handovers). The scene keeps the title's rhythm and its cameras, which
// last as long as the donor's poses: the first 100 frames of the winner's
// pose, the first 100 of the partner's, then both in their poses' last frame
// (what the importer makes of the third part). Letting each pose play to its
// own end was tried: the cameras stop after their 100 frames and showed an
// empty stage for the seconds a pose went on.
//
// A fighter alone plays `wem_1` as well and leaves it for `wem_3` by a
// cancel at that same frame 100 (requirement 485: no team): it is left alone
// here, or it would be sent to wait for a partner it has not got.
//
// (`<code>_wnm_1`, a round's win pose, and `<code>_wns_1` also hold a form
// that ends in a pose for two, picked with requirement 506 from a table by
// the partner's motion row, sub_0404E4A4; no mode was found that plays it,
// so nothing is done about it.)

#include <cstdint>
#include <string_view>
#include <vector>

namespace cafe::title::win_pose {

constexpr uint32_t kHandoverProperty = 0x80A2; // value -> the partner's signal word
constexpr uint32_t kSignal = 500;              // a player's signal word (requirement 313 tests it)
constexpr int32_t kPastTheEnd = 30000;         // a move frame past any animation's end

// Whether a move (by its name, which an added fighter's moveset keeps from its
// donor: `ju_wem_1`, `la_wes_2`) is a part of a team's win.
constexpr bool is_part(std::string_view move_name) {
    return move_name.find("_wem_") != std::string_view::npos || move_name.find("_wes_") != std::string_view::npos;
}

// Hand-overs held back until their sender's part is over.
class Handovers {
public:
    // `sender`, in its move `move`, hands `value` over to `receiver` (again for the same part: once).
    void hold(uint32_t sender, uint32_t move, uint32_t receiver, uint32_t value) {
        for (Held& h : held_) {
            if (h.sender == sender) {
                h = {sender, move, receiver, value};
                return;
            }
        }
        held_.push_back({sender, move, receiver, value});
    }
    // Gives (`give(receiver, value)`) those whose sender has left the move it was held in
    // (`move_of(sender)` its move now), and forgets them.
    template <typename MoveOf, typename Give>
    void deliver(MoveOf&& move_of, Give&& give) {
        for (size_t i = 0; i < held_.size();) {
            if (move_of(held_[i].sender) == held_[i].move) {
                ++i;
                continue;
            }
            give(held_[i].receiver, held_[i].value);
            held_.erase(held_.begin() + static_cast<std::ptrdiff_t>(i));
        }
    }
    // A new fight: nothing of the last one's is owed.
    void clear() { held_.clear(); }
    bool empty() const { return held_.empty(); }

private:
    struct Held {
        uint32_t sender, move, receiver, value;
    };
    std::vector<Held> held_;
};

} // namespace cafe::title::win_pose
