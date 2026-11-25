#!/usr/bin/env bash
# Fighters and Settings as they move and as they are used, offscreen, against the stubs of tests/stub (never the
# real importer or game), each run in a scratch home of its own below WORK:
#
#   screens.sh LAUNCHER STUB WORK PYTHON
#
# Every frame of every run is checked by the launcher itself ("@audit failed ...": everything painted keeps the
# gutter from its half's seam, inside its plate; once settled the focus frame is on the focused item). On top:
# - frame sequences with no input after a tab or section change, at several sizes and scales;
# - Settings' sections and Fighters at 1280x800, 1920x1080, 2560x1440, each at scale 1, 1.25, 1.5 and 2 where
#   that leaves the window's minimum of 960x600 points;
# - a fighter tile's drill-in lock by keys, pad and pointer (the pointer crosses the locked tiles without
#   taking the focus; a click on a tile unlocks onto it; the blue buttons take clicks);
# - the blue side shows the focused fighter only (no second fighter's name);
# - the same walk with Text size 125 and 150 % at 1280x800 and 960x640;
# - the Steam Controller's double reports (each button is the pad's AND a key Steam types, in either order) on a
#   tile, Back in a drill-in and on a page, a dialog's opening: one action each;
# - choosing a key (a key, Esc, the 10 s countdown) and the Steam Controller's double report on a key row
#   (its A is the pad button AND an Enter typed by Steam, in either order: one press, the Enter is not taken as the
#   key, the pad's report is not B);
# - typing the player's name (Settings > Game): the keyboard's text and keys (Enter keeps it, Esc does not, a
#   character it refuses), the on-screen keys with a pad (B, X, Y, Start), the Steam Controller's A on the row and on
#   a key (one press: never Done), a tab change while typing (the name as it was), game.ini as written;
# - the Language row below it: Left and Right change it on the row, the pad's A takes the next one, language:
#   sets one, each written in game.ini;
# - adding and removing a character with the stub importer, and Cancel while it runs.
set -u
LAUNCHER=$1 STUB=$2 WORK=$3 PYTHON=$4
rm -rf "$WORK" && mkdir -p "$WORK"
failures=0
fail() {
    echo "FAILED: $*" >&2
    failures=$((failures + 1))
}

# home NAME: a scratch home with the game installed (by this kit)
home() {
    local h=$WORK/$1
    mkdir -p "$h/.config/ttt2" "$h/run" "$h/Games" && chmod 700 "$h/run"
    local g="$h/Games/Tekken Tag Tournament 2"
    mkdir -p "$g"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$g/Tekken Tag Tournament 2"
    chmod +x "$g/Tekken Tag Tournament 2"
    echo "$g" > "$h/.config/ttt2/installed"
    touch "$g/.ttt2-install"
    echo "kit $(head -n1 "$STUB/kit/VERSION")" > "$g/.ttt2-build"
    echo "$h"
}

# run HOME CASE [VAR=value...] -- [arguments]: the launcher's output in HOME/out.txt (no session bus, no sound)
run() {
    local h=$1 case=$2
    shift 2
    local vars=()
    while [ $# -gt 0 ] && [ "$1" != "--" ]; do
        vars+=("$1")
        shift
    done
    [ "${1:-}" = "--" ] && shift
    env -u DISPLAY -u WAYLAND_DISPLAY -u APPIMAGE -u APPDIR -u TTT2_LAUNCHER_TEST_ACTIONS -u DBUS_SESSION_BUS_ADDRESS \
        HOME="$h" XDG_CONFIG_HOME="$h/.config" XDG_DATA_HOME="$h/.local/share" XDG_CACHE_HOME="$h/.cache" \
        XDG_RUNTIME_DIR="$h/run" TTT2_SAVE_DIR="$h/saves" SDL_AUDIO_DRIVER=dummy \
        TTT2_KIT="$STUB/kit" TTT2_IMPORTER="$STUB/importer" TTT2_PYTHON="$PYTHON" \
        TTT2_STUB_CASE="$STUB/../../../model/tests/golden/$case/case.json" \
        TTT2_LAUNCHER_RELEASES="file://$h/no-release.json" TTT2_LAUNCHER_TEST_CUES=1 \
        "${vars[@]}" timeout 240 "$LAUNCHER" "$@" > "$h/out.txt" 2>&1
    echo $? > "$h/code.txt"
}
has() { grep -q -- "$2" "$1/out.txt" || fail "$1: no '$2' in its output: $(tail -n 5 "$1/out.txt")"; }
hasnt() { grep -q -- "$2" "$1/out.txt" && fail "$1: '$2' in its output: $(grep -m 2 -- "$2" "$1/out.txt")"; }
# clean HOME [FRAMES]: exit 0, no audit problem, no failed step; FRAMES: that many "@frames ... ok", none failed.
clean() {
    local h=$1
    [ "$(cat "$h/code.txt")" = 0 ] || fail "$h: exit code $(cat "$h/code.txt"): $(tail -n 5 "$h/out.txt")"
    grep -q '@audit failed' "$h/out.txt" && fail "$h: $(grep -m 3 '@audit failed' "$h/out.txt")"
    grep -q '@test .* failed' "$h/out.txt" && fail "$h: $(grep -m 3 '@test .* failed' "$h/out.txt")"
    if [ -n "${2:-}" ]; then
        grep -q '@frames .* failed' "$h/out.txt" && fail "$h: $(grep -m 3 '@frames .* failed' "$h/out.txt")"
        local n
        n=$(grep -c '@frames .* ok' "$h/out.txt")
        [ "$n" = "$2" ] || fail "$h: $n frames ok of $2"
    fi
}

# No input after a tab or section change: every frame laid out for the drawn seam, the focus frame on its item.
for spec in "1280x800 1 tab:fighters" "2560x1440 1.5 tab:settings;press:c" "1920x1080 1.25 tab:settings;press:c;press:c" \
    "2560x1440 2 tab:fighters;tab:settings" "2560x1440 1.25 tab:settings;tab:fighters" \
    "1920x1080 1 tab:settings;press:z"; do
    read -r size scale actions <<< "$spec"
    name=f1-$size-$scale-$(echo "$actions" | tr -c 'a-z0-9\n' '-')
    h=$(home "$name")
    run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=$actions" -- --frames "$h/frames" --size "$size" --scale "$scale"
    clean "$h" 7
done

# Each Settings section, its rows walked, and Fighters, at every size and scale (every frame audited).
# (Game first: its name typed on the keyboard and with a pad down to the last keys, then left as it was.)
walk="tab:settings;press:Down;press:Right;press:Left;press:Up;press:Return;type:Zorbax;pad:down;pad:down;pad:down"
walk+=";pad:down;pad:east;press:c;press:Down;press:Down;press:Right;press:Left;press:c;press:Down;press:Right;press:c"
walk+=";press:Down;press:Down;press:Right;press:Left;press:c;tab:fighters;press:Down;press:Right;press:Down;press:Down;quit"
# (Only the windows a player can have: at least 960x600 points, the window's minimum.)
for size in 1280x800 1920x1080 2560x1440; do
    for scale in 1 1.25 1.5 2; do
        awk -v s="$size" -v k="$scale" 'BEGIN { split(s, d, "x"); exit !(d[1] / k >= 960 && d[2] / k >= 600) }' ||
            continue
        h=$(home "f5-$size-$scale")
        run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=$walk" -- --size "$size" --scale "$scale"
        clean "$h"
        [ "$(grep -c '@test .* ok' "$h/out.txt")" -ge 32 ] || fail "f5-$size-$scale: the walk stopped early"
    done
done
# The same walk with a larger Text size at the Steam Deck's 1280x800 and at 960x640: laid out for at
# least the Deck's 1280x800 at 150 % (853x533 points, ui_scale's tests), every frame audited.
for size in 1280x800 960x640; do
    for text in 125 150; do
        h=$(home "text-$size-$text")
        printf 'text_size=%s\n' "$text" > "$h/.config/ttt2/launcher.ini"
        run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=$walk" -- --size "$size"
        clean "$h"
        [ "$(grep -c '@test .* ok' "$h/out.txt")" -ge 32 ] || fail "text-$size-$text: the walk stopped early"
    done
done

# Accept on a tile gives the focus to its blue actions and locks the tiles until Back or a click on them.
h=$(home f4-keys)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;focus:tile:josie;press:Return" -- --frames "$h/frames" \
    --size 1920x1080 --scale 1.5
clean "$h" 7
has "$h" '@cue drill-in'
has "$h" '@frames idle ok (focus fighter:josie,'
h=$(home f4-pad)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;focus:tile:josie;pad:south;pad:east" -- --frames "$h/frames"
clean "$h" 7
has "$h" '@cue drill-out'
has "$h" '@frames idle ok (focus tile:josie,'
h=$(home f4-pointer)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;click:tile:josie;hover:tile:kazumi;hover:tile:reina" -- \
    --frames "$h/frames" --size 2560x1440 --scale 2
clean "$h" 7
has "$h" '@frames idle ok (focus fighter:josie,'
[ "$(sed -n '/@cue drill-in/,$p' "$h/out.txt" | grep -c '@cue move')" = 0 ] ||
    fail "f4-pointer: the pointer moved the focus on the locked tiles"
h=$(home f4-unlock)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;click:tile:josie;click:tile:kazumi" -- --frames "$h/frames"
clean "$h" 7
has "$h" '@cue drill-out'
has "$h" '@frames idle ok (focus tile:kazumi,'
h=$(home f4-blue-click)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;click:tile:kazumi;click:outfits:kazumi;wait:0.6" -- \
    --frames "$h/frames"
clean "$h" 7
has "$h" '@frames idle ok (focus outfits:kazumi,'
hasnt "$h" '@cue drill-out'

# The Steam Controller's A and B, each a pad button AND a key Steam types, in either order (the key first: the pad's
# report comes at the next poll, after the key's frame): one Accept or Back wherever it lands, never a second one on
# what the first opened.
for how in steam steam-key; do
    h=$(home "$how-drill-in")
    run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;focus:tile:josie;$how:south;wait:0.5" -- --frames "$h/frames"
    clean "$h" 7
    [ "$(sed -n '/@cue drill-in/,$p' "$h/out.txt" | grep -v '@cue move' | grep -c '@cue')" = 1 ] ||
        fail "$how-drill-in: $(grep '@cue' "$h/out.txt" | grep -v move | tr '\n' '|')"
    has "$h" '@frames idle ok (focus fighter:josie,'
    h=$(home "$how-drill-out")
    run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;focus:tile:josie;pad:south;wait:0.4;$how:east;wait:0.5" -- \
        --frames "$h/frames"
    clean "$h" 7
    [ "$(sed -n '/@cue drill-out/,$p' "$h/out.txt" | grep -v '@cue move' | grep -c '@cue')" = 1 ] ||
        fail "$how-drill-out: $(grep '@cue' "$h/out.txt" | grep -v move | tr '\n' '|')"
    has "$h" '@frames idle ok (focus tile:josie,'
    h=$(home "$how-back-tab")
    run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;$how:east;wait:0.5" -- --frames "$h/frames"
    clean "$h" 7
    [ "$(grep -c '@cue tab' "$h/out.txt")" = 2 ] || fail "$how-back-tab: $(grep -c '@cue tab' "$h/out.txt") tab changes"
    # (Back on Home's slab: UPDATE, the installed case has a fighter to update.)
    has "$h" '@frames idle ok (focus update-everything,'
    h=$(home "$how-dialog")
    run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=focus:uninstall;$how:south;wait:0.6" -- --frames "$h/frames"
    clean "$h" 7
    [ "$(grep -c '@cue accept' "$h/out.txt")" = 1 ] || fail "$how-dialog: the dialog's button was pressed too"
    has "$h" '@frames idle ok (focus uninstall-cancel,'
done

# Choosing a key.
h=$(home keys-take)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;press:c;press:c;press:Return;press:j;quit"
clean "$h"
has "$h" '@capture start key:dpad_up'
has "$h" '@capture end D-pad Up is J'
grep -q '^dpad_up *= *13' "$h/.config/ttt2/keyboard.ini" || fail "keys-take: keyboard.ini has $(grep dpad_up "$h/.config/ttt2/keyboard.ini")"
h=$(home keys-esc)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;press:c;press:c;press:Return;press:Escape;quit"
clean "$h"
has "$h" '@capture end cancelled with Esc'
h=$(home keys-timeout)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;press:c;press:c;press:Return;wait:10.6;quit"
clean "$h"
has "$h" '@capture end no key was taken yet'
# The Steam Controller's A on a key row: the pad's press starts choosing; the Enter Steam types for it 4 ms later is
# not taken as the key (and starts nothing else); B then stops choosing with D-pad Up still W.
h=$(home keys-steam)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;press:c;press:c;steam:south;wait:0.5;pad:east;quit"
clean "$h"
has "$h" '@capture start key:dpad_up'
has "$h" '@capture end no key was taken yet'
[ "$(grep -c '@capture start' "$h/out.txt")" = 1 ] || fail "keys-steam: one A started choosing more than once"
hasnt "$h" 'is Return'
# The other order: the Enter Steam types arrives first and starts choosing; the pad's report of the same
# A, read at the next poll 30 ms later, is not the pad's B: choosing goes on, the next key is taken.
h=$(home keys-steam-key)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;press:c;press:c;steam-key:south;wait:0.5;press:j;quit"
clean "$h"
has "$h" '@capture start key:dpad_up'
has "$h" '@capture end D-pad Up is J'
[ "$(grep -c '@capture' "$h/out.txt")" = 2 ] || fail "keys-steam-key: $(grep '@capture' "$h/out.txt" | tr '\n' '|')"
hasnt "$h" '@cue back'
# A key it refuses (F11 stays with the game): its note, a refusal cue, choosing goes on until a key it takes.
h=$(home keys-refuse)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;press:c;press:c;press:Return;press:F11;press:j;quit"
clean "$h"
has "$h" '@cue refuse'
has "$h" '@capture end D-pad Up is J'

# Typing the player's name (Settings > Game, its row first). The keyboard: its text, Backspace, a character it
# refuses (said, a refusal cue, typing goes on), Enter keeps the name in game.ini.
name_is() {
    grep -q "^player_name = $2\$" "$1/.config/ttt2/game.ini" ||
        fail "$1: game.ini has $(grep player_name "$1/.config/ttt2/game.ini" 2>/dev/null || echo 'no name')"
}
h=$(home name-keys)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;press:Return;type:Zorbax;press:BackSpace;type:é;type:Q;press:Return;quit"
clean "$h"
has "$h" '@name start'
has "$h" '@cue refuse'
has "$h" '@name end game.ini: player name ZorbaQ'
name_is "$h" ZorbaQ
# Esc, and a tab changed while typing: the name as it was.
h=$(home name-esc)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=player-name:Kept;press:Return;type:Other;press:Escape;press:Return;type:Gone;tab:home;wait:0.3;quit"
clean "$h"
# (Esc says the name kept; Home leaves Settings, typing ends with it.)
has "$h" '@name end kept: game.ini: player name Kept'
[ "$(grep -c '@name end' "$h/out.txt")" = 2 ] ||
    fail "name-esc: $(grep '@name' "$h/out.txt" | tr '\n' '|')"
name_is "$h" Kept
# A pad on the on-screen keys: A types (a capital first), X deletes, Y types a space, Start keeps the name.
h=$(home name-pad)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;pad:south;pad:south;pad:west;pad:right;pad:south;pad:north;pad:south;pad:start;quit"
clean "$h"
has "$h" '@name end game.ini: player name W w'
name_is "$h" "W w"
# The Steam Controller's A (its pad's A AND an Enter Steam types, in either order), on the row and on a key: one
# press each, the Enter never taken as Done (the name goes on being typed).
for how in steam steam-key; do
    h=$(home "name-$how")
    run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;$how:south;wait:0.5;$how:south;wait:0.5;type:x;pad:start;quit"
    clean "$h"
    [ "$(grep -c '@name start' "$h/out.txt")" = 1 ] || fail "name-$how: $(grep '@name' "$h/out.txt" | tr '\n' '|')"
    name_is "$h" Qx
done
# The Language row (Settings > Game, below Player name): Right and Left change it on the row, the pad's A takes the
# next one, language: sets one, each saved in game.ini (fr, de, fr, it, es, then it).
h=$(home language)
run "$h" installed \
    "TTT2_LAUNCHER_TEST_ACTIONS=tab:settings;press:Down;press:Right;press:Right;press:Left;language:IT;pad:south;press:Left;quit"
clean "$h"
has "$h" '@test language:IT ok'
grep -q '^language = it$' "$h/.config/ttt2/game.ini" ||
    fail "language: game.ini has $(grep language "$h/.config/ttt2/game.ini" 2>/dev/null || echo 'no language')"

# Adding and removing with the stub importer: the fighter's own progress, the task strip; Cancel.
h=$(home add)
run "$h" installed TTT2_STUB_STEP_SECONDS=0.3 "TTT2_LAUNCHER_TEST_SHOTS=$h/shots" \
    "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;focus:tile:kazumi;add:kazumi;remove:lucky_chloe;quit"
clean "$h"
has "$h" '@test add:kazumi ok'
has "$h" '@test remove:lucky_chloe ok'
h=$(home add-cancel)
run "$h" installed TTT2_STUB_STEP_SECONDS=1 TTT2_LAUNCHER_TEST_CANCEL=0 \
    "TTT2_LAUNCHER_TEST_ACTIONS=tab:fighters;add-all:tekken7;quit"
has "$h" '@test add-all:tekken7 failed'
grep -q '@audit failed' "$h/out.txt" && fail "add-cancel: $(grep -m 3 '@audit failed' "$h/out.txt")"

if [ "$failures" -gt 0 ]; then
    echo "$failures failed (outputs in $WORK/*/out.txt)" >&2
    exit 1
fi
echo "launcher screens: all passed"
