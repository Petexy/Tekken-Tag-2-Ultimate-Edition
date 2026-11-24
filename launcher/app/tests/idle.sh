#!/usr/bin/env bash
# The launcher left alone (ARCHITECTURE sec 7, U9): started as a player starts it (no test actions; drawn offscreen),
# against the stubs of tests/stub, each run in a scratch home of its own below WORK, every frame put on the screen
# counted (TTT2_LAUNCHER_TEST_PRESENTS):
#
#   idle.sh LAUNCHER STUB WORK PYTHON
#
# - no input: at most kAmbientHz (30) frames a second while ambient motion runs, none once it paused (20 s);
# - the same with a gamepad connected (polled ~120 times a second: a poll that brings nothing draws nothing);
# - Reduce motion: no frames at all after the start, also with a gamepad;
# - the game running: no frames after the start, focused or not (it is behind the game);
# - and the launcher's CPU time once nothing is drawn stays small.
# The runs go side by side (about 30 s in all).
set -u
LAUNCHER=$1 STUB=$2 WORK=$3 PYTHON=$4
rm -rf "$WORK" && mkdir -p "$WORK"
failures=0
fail() {
    echo "FAILED: $*" >&2
    failures=$((failures + 1))
}
SECONDS_RUN=27

# start NAME LAUNCHER_INI [VAR=value...]: a scratch home with the game installed (by this kit), the launcher started
# in it in the background; its pid in NAME/pid. GAME_RUNNING=1 in the variables: a stub game runs (a copy of sleep
# as the installed game, so the launcher sees it running).
start() {
    local name=$1 ini=$2
    shift 2
    local h=$WORK/$name
    mkdir -p "$h/.config/ttt2" "$h/run" "$h/Games" && chmod 700 "$h/run"
    local g="$h/Games/Tekken Tag Tournament 2"
    mkdir -p "$g"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$g/Tekken Tag Tournament 2"
    chmod +x "$g/Tekken Tag Tournament 2"
    echo "$g" > "$h/.config/ttt2/installed"
    touch "$g/.ttt2-install"
    echo "kit $(head -n1 "$STUB/kit/VERSION")" > "$g/.ttt2-build"
    printf '%b' "$ini" > "$h/.config/ttt2/launcher.ini"
    local vars=() game=
    for v in "$@"; do
        if [ "$v" = GAME_RUNNING=1 ]; then game=1; else vars+=("$v"); fi
    done
    if [ -n "$game" ]; then
        rm -f "$g/Tekken Tag Tournament 2"
        cp "$(command -v sleep)" "$g/Tekken Tag Tournament 2"
        "$g/Tekken Tag Tournament 2" $((SECONDS_RUN + 20)) &
        echo $! > "$h/game.pid"
    fi
    env -u DISPLAY -u WAYLAND_DISPLAY -u APPIMAGE -u APPDIR -u TTT2_LAUNCHER_TEST_ACTIONS -u DBUS_SESSION_BUS_ADDRESS \
        HOME="$h" XDG_CONFIG_HOME="$h/.config" XDG_DATA_HOME="$h/.local/share" XDG_CACHE_HOME="$h/.cache" \
        XDG_RUNTIME_DIR="$h/run" TTT2_SAVE_DIR="$h/saves" SDL_AUDIO_DRIVER=dummy TTT2_LAUNCHER_TEST_AUDIO=dummy \
        TTT2_KIT="$STUB/kit" TTT2_IMPORTER="$STUB/importer" TTT2_PYTHON="$PYTHON" \
        TTT2_STUB_CASE="$STUB/../../../model/tests/golden/installed/case.json" \
        TTT2_LAUNCHER_RELEASES="file://$h/no-release.json" TTT2_LAUNCHER_TEST_VIDEO=offscreen \
        TTT2_LAUNCHER_TEST_PRESENTS="$h/presents.txt" TTT2_LAUNCHER_TEST_INSTANCE="ttt2-launcher-idle-test-$$-$name" \
        "${vars[@]}" "$LAUNCHER" > "$h/out.txt" 2>&1 &
    echo $! > "$h/pid"  # (env runs it in its own place: this is the launcher's pid)
}
# (Whatever happens to this script, nothing it started stays.)
stop_all() {
    local p pid exe
    for p in "$WORK"/*/pid "$WORK"/*/game.pid; do
        [ -f "$p" ] || continue
        pid=$(cat "$p")
        exe=$(readlink "/proc/$pid/exe" 2>/dev/null) || continue
        # (Only what it started: the launcher, or a stub game in its homes.)
        [ "$exe" = "$(readlink -f "$LAUNCHER")" ] || [[ "$exe" == "$WORK"/* ]] && kill -KILL "$pid" 2>/dev/null
    done
}
trap stop_all EXIT

# cpu NAME: the launcher's CPU ticks so far
cpu() { awk '{print $14 + $15}' "/proc/$(cat "$WORK/$1/pid")/stat" 2>/dev/null || echo 0; }
# frames NAME FROM TO: frames put on the screen in [FROM, TO) seconds after the start
frames() { cat "$WORK/$1/presents.txt" 2>/dev/null | awk -v a="$2" -v b="$3" '$1 >= a && $1 < b { n++ } END { print n + 0 }'; }

runs=(still pad reduced reduced-pad game game-away)
start still ''
start pad '' TTT2_LAUNCHER_TEST_PAD=1
start reduced 'reduce_motion=yes\n'
start reduced-pad 'reduce_motion=yes\n' TTT2_LAUNCHER_TEST_PAD=1
start game '' GAME_RUNNING=1
start game-away '' GAME_RUNNING=1 TTT2_LAUNCHER_TEST_BLUR=2
sleep 22.5
declare -A cpu0
for r in "${runs[@]}"; do cpu0[$r]=$(cpu "$r"); done
sleep $((SECONDS_RUN - 22)).5
tck=$(getconf CLK_TCK)
for r in "${runs[@]}"; do
    used=$(( $(cpu "$r") - ${cpu0[$r]} ))
    echo "$r: $(awk -v d="$used" -v t="$tck" 'BEGIN { printf "%.1f", 100 * d / t / 5 }') % of one core at 22.5-27.5 s" \
        >> "$WORK/cpu.txt"
    # (At most a fifth of one core while nothing is drawn: a poll or a wait that spins would take all of it.)
    [ "$used" -le $((tck / 5 * 5)) ] || fail "$r: $used CPU ticks in 5 s with nothing to draw"
    kill -TERM "$(cat "$WORK/$r/pid")" 2>/dev/null
done
sleep 3
for r in "${runs[@]}"; do
    kill -0 "$(cat "$WORK/$r/pid")" 2>/dev/null && fail "$r: still running 3 s after SIGTERM"
    wait "$(cat "$WORK/$r/pid")" 2>/dev/null
    [ -f "$WORK/$r/game.pid" ] && kill "$(cat "$WORK/$r/game.pid")" 2>/dev/null
    [ -s "$WORK/$r/presents.txt" ] || { fail "$r: no frame was put on the screen: $(tail -n 3 "$WORK/$r/out.txt")"; continue; }
    echo "$r: $(frames "$r" 0 2) frames at 0-2 s, $(frames "$r" 2 19) at 2-19 s, $(frames "$r" 22 $SECONDS_RUN) at 22-$SECONDS_RUN s" \
        >> "$WORK/frames.txt"
done
cat "$WORK/frames.txt" "$WORK/cpu.txt"

# Ambient motion: frames, but never more than 30 a second; none once it paused 20 s after the start.
for r in still pad; do
    n=$(frames "$r" 2 19)
    [ "$n" -ge 17 ] || fail "$r: $n frames at 2-19 s (the ambient motion stopped)"
    [ "$n" -le $((31 * 17)) ] || fail "$r: $n frames at 2-19 s: more than 30 a second"
    [ "$(frames "$r" 22 $SECONDS_RUN)" -le 1 ] || fail "$r: $(frames "$r" 22 $SECONDS_RUN) frames after the pause"
done
grep -q '@idle pad connected' "$WORK/pad/out.txt" || fail "pad: no gamepad: $(grep -m 1 '@idle pad' "$WORK/pad/out.txt")"
grep -q '@idle pad connected' "$WORK/reduced-pad/out.txt" || fail "reduced-pad: no gamepad"
# Still: nothing drawn after the start (a pad poll or the model's tick that changed nothing draws nothing).
for r in reduced reduced-pad game game-away; do
    n=$(frames "$r" 3 $SECONDS_RUN)
    [ "$n" -le 1 ] || fail "$r: $n frames at 3-$SECONDS_RUN s with nothing to draw"
done
grep -q '@idle focus lost' "$WORK/game-away/out.txt" || fail "game-away: the focus was not taken away"

if [ "$failures" -gt 0 ]; then
    echo "$failures failed (outputs in $WORK/*/out.txt)" >&2
    exit 1
fi
echo "launcher idle: all passed"
