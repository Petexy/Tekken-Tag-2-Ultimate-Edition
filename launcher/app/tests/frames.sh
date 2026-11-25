#!/usr/bin/env bash
# The launcher's screens as they move, offscreen, against the stubs of tests/stub (never the real importer,
# builder or game), each run in a scratch home of its own below WORK:
#
#   frames.sh LAUNCHER STUB WORK PYTHON
#
# Every frame of every run is checked by the launcher itself ("@audit failed ..."): everything painted keeps the
# gutter from its half's seam, and once settled the focus frame is on the focused item. On top:
# - F1: frame sequences with no input after a tab change (0, 50, 100, 200, 400, 700 ms, then settled) at several
#   window sizes and scales: each "@frames <t> ok" (nothing across the seam, the focus frame on its item);
# - F4: the drill-in lock on the checks before an install (Accept on a check with a command -> its Copy button,
#   the crimson side locked; the pointer crosses crimson without taking the focus; a click on a crimson row or
#   Back returns);
# - the Steam Controller's double report (its pad button and the key Steam types for it) is one press;
# - F6: Home after every combination of the Display settings, and in every state with all of them on; Play with
#   "Prepare shaders before playing" (the task strip).
set -u
LAUNCHER=$1 STUB=$2 WORK=$3 PYTHON=$4
rm -rf "$WORK" && mkdir -p "$WORK"
failures=0
fail() {
    echo "FAILED: $*" >&2
    failures=$((failures + 1))
}

# home NAME STATE: a scratch home; STATE none | installed | update | older | unfinished
home() {
    local h=$WORK/$1
    mkdir -p "$h/.config/ttt2" "$h/run" "$h/Games" "$h/Downloads" && chmod 700 "$h/run"
    printf 'x' > "$h/Downloads/game.wua"
    local g="$h/Games/Tekken Tag Tournament 2"
    if [ "$2" != none ]; then
        mkdir -p "$g"
        cat > "$g/Tekken Tag Tournament 2" <<'GAME'
#!/usr/bin/env bash
if [ "${1:-}" = "--precompile" ]; then echo "@step shaders Preparing shaders"; sleep 1; echo "@progress 1 1"; exit 0; fi
echo "stub game started"
[ -n "${TTT2_STUB_MARKER:-}" ] && echo played > "$TTT2_STUB_MARKER"
exit 0
GAME
        chmod +x "$g/Tekken Tag Tournament 2"
        echo "$g" > "$h/.config/ttt2/installed"
    fi
    local kit
    kit=$(head -n1 "$STUB/kit/VERSION")
    case $2 in
    installed) touch "$g/.ttt2-install" && echo "kit $kit" > "$g/.ttt2-build" ;;
    update) touch "$g/.ttt2-install" && echo "kit ${kit%-*}-1111111111cd" > "$g/.ttt2-build" ;;
    older) touch "$g/.ttt2-install" && echo "kit 0.7.1-1111111111cd" > "$g/.ttt2-build" ;;
    unfinished)
        touch "$g/.ttt2-installing"
        printf '%s\n%s\n' "$g" "$h/Downloads/game.wua" > "$h/.config/ttt2/installing"
        ;;
    esac
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
        TTT2_STUB_CASE="$STUB/../../../model/tests/golden/$case/case.json" TTT2_STUB_MARKER="$h/played" \
        TTT2_STUB_STEP_SECONDS=0.02 TTT2_LAUNCHER_RELEASES="file://$h/no-release.json" TTT2_LAUNCHER_TEST_CUES=1 \
        "${vars[@]}" timeout 240 "$LAUNCHER" "$@" > "$h/out.txt" 2>&1
    echo $? > "$h/code.txt"
}
has() { grep -q -- "$2" "$1/out.txt" || fail "$1: no '$2' in its output: $(tail -n 5 "$1/out.txt")"; }
no_audit() { grep -q '@audit failed' "$1/out.txt" && fail "$1: $(grep -m 3 '@audit failed' "$1/out.txt")"; }
# clean HOME [FRAMES]: no audit problem, no failed step; FRAMES: that many "@frames ... ok" and none failed.
clean() {
    local h=$1
    [ "$(cat "$h/code.txt")" = 0 ] || fail "$h: exit code $(cat "$h/code.txt"): $(tail -n 5 "$h/out.txt")"
    no_audit "$h"
    grep -q '@test .* failed' "$h/out.txt" && fail "$h: $(grep -m 3 '@test .* failed' "$h/out.txt")"
    if [ -n "${2:-}" ]; then
        grep -q '@frames .* failed' "$h/out.txt" && fail "$h: $(grep -m 3 '@frames .* failed' "$h/out.txt")"
        local n
        n=$(grep -c '@frames .* ok' "$h/out.txt")
        [ "$n" = "$2" ] || fail "$h: $n frames ok of $2"
    fi
}

case_of() { [ "$1" = none ] && echo not-installed || echo installed; }

# F1: after a tab change, no input: each frame laid out for the seam as drawn, the focus frame on its item.
for spec in "installed 1280x800 1 tab:fighters" "installed 1920x1080 1.5 tab:settings" \
    "installed 2560x1440 2 tab:settings;tab:home" "installed 2560x1440 1.25 tab:fighters;tab:home" \
    "none 1280x800 1 tab:settings;tab:home" "older 1920x1080 1.25 tab:fighters"; do
    read -r state size scale actions <<< "$spec"
    name=f1-$state-$size-$scale-$(echo "$actions" | tr -c 'a-z0-9\n' '-')
    h=$(home "$name" "$state")
    run "$h" "$(case_of "$state")" "TTT2_LAUNCHER_TEST_ACTIONS=$actions" -- --frames "$h/frames" --size "$size" \
        --scale "$scale"
    clean "$h" 7
done

# F4: the drill-in lock (a C++ compiler that is not there: its check has a command to copy).
missing_cxx() {
    local h
    h=$(home "$1" none)
    run "$h" not-installed CXX=ttt2-no-such-compiler \
        "TTT2_LAUNCHER_TEST_ACTIONS=install:$h/Downloads/game.wua:$h/Games/Tekken Tag Tournament 2;focus:check:2;$2" \
        -- --frames "$h/frames" --size "${3:-1280x800}" --scale "${4:-1}"
    echo "$h"
}
h=$(missing_cxx drill-in "press:Return" 1920x1080 1.5)
grep -q '@test install:.* failed C++ compiler' "$h/out.txt" || fail "drill-in: the compiler check did not fail"
has "$h" '@cue drill-in'
has "$h" '@frames idle ok (focus copy:'
no_audit "$h"
h=$(missing_cxx drill-click "pad:south;hover:check:0;click:check:0")
has "$h" '@frames f0000 ok (focus copy:'   # (the pointer crossed crimson: the focus stayed)
has "$h" '@cue drill-out'
has "$h" '@frames idle ok (focus check:0,'
no_audit "$h"
[ "$(grep -c '@cue move' "$h/out.txt")" = 0 ] || fail "drill-click: the pointer moved the focus on a locked side"
h=$(missing_cxx drill-back "press:Return;pad:east" 2560x1440 2)
has "$h" '@cue drill-out'
has "$h" '@frames idle ok (focus check:2,'
no_audit "$h"

# The Steam Controller: one press of A is its pad button and an Enter Steam types: one Accept.
h=$(home steam installed)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=focus:settings;steam:south;wait:0.5" -- --frames "$h/frames"
clean "$h" 7
[ "$(grep -c '@cue tab' "$h/out.txt")" = 1 ] || fail "steam: $(grep -c '@cue tab' "$h/out.txt") tab switches for one A"
# (The other order: the key first, the pad's report after the key's frame, on the Settings page by then: still one.)
h=$(home steam-key installed)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=focus:settings;steam-key:south;wait:0.5" -- --frames "$h/frames"
clean "$h" 7
[ "$(grep -c '@cue tab' "$h/out.txt")" = 1 ] || fail "steam-key: $(grep -c '@cue tab' "$h/out.txt") tab switches for one A"
[ "$(sed -n '/@cue tab/,$p' "$h/out.txt" | grep -v '@cue move' | grep -c '@cue')" = 1 ] ||
    fail "steam-key: the pad's report of the A acted on the Settings page"
grep -q '@frames idle ok (focus fullscreen,' "$h/out.txt" || fail "steam-key: $(grep -m 1 '@frames idle' "$h/out.txt")"

# F6: Home after every combination of the Display settings (changed in Settings, one at a time: a Gray code walk).
settings=(fullscreen interpolation input-delay async-shaders precompile-shaders)
actions="fullscreen:no;interpolation:no;input-delay:no;async-shaders:no;precompile-shaders:no;tab:home"
for i in $(seq 1 31); do
    g=$((i ^ (i >> 1))) p=$(((i - 1) ^ ((i - 1) >> 1)))
    for b in 0 1 2 3 4; do
        if [ $(((g ^ p) >> b & 1)) = 1 ]; then
            actions+=";${settings[$b]}:$([ $((g >> b & 1)) = 1 ] && echo yes || echo no);tab:home"
        fi
    done
done
actions+=";resolution:1280x720;tab:home;resolution:3840x2160;tab:home;resolution:auto;tab:home"
h=$(home f6-combinations installed)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=$actions;quit" -- --size 1280x800 --scale 1.25
clean "$h"
steps=$(grep -c '@test .* ok' "$h/out.txt")
[ "$steps" -ge 70 ] || fail "f6-combinations: $steps steps"
all_on="fullscreen:yes;interpolation:yes;input-delay:yes;async-shaders:yes;precompile-shaders:yes;resolution:2560x1440"
for state in none installed update older unfinished; do
    h=$(home "f6-$state" "$state")
    run "$h" "$(case_of "$state")" "TTT2_LAUNCHER_TEST_ACTIONS=$all_on;tab:home" -- --frames "$h/frames" \
        --size 2560x1440 --scale 2
    clean "$h" 7
done
# Play with the shaders prepared first: the task strip under the plates.
h=$(home f6-play-shaders installed)
run "$h" play-shaders "TTT2_LAUNCHER_TEST_ACTIONS=precompile-shaders:yes;tab:home;play" -- --frames "$h/frames" \
    --at 0,100,300,600,900
clean "$h" 6
[ -f "$h/played" ] || fail "f6-play-shaders: the game did not start after its shaders"

if [ "$failures" -gt 0 ]; then
    echo "$failures failed (outputs in $WORK/*/out.txt)" >&2
    exit 1
fi
echo "launcher frames: all passed"
