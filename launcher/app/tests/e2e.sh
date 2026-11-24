#!/usr/bin/env bash
# The launcher end to end, offscreen, against the stubs of tests/stub (never the real importer, builder or game),
# each run in a scratch home of its own below WORK:
#
#   e2e.sh LAUNCHER STUB WORK PYTHON
#
# start + Quit; an install whose game is missing (the checks before it); Play (the stub game writes a marker and
# its output goes to the game log); Update (the stub builder's steps, its build record); an update killed by a
# signal (code 128 + 9 named); Cancel (the builder stopped, nothing left running); Uninstall; a screenshot at a
# size. An install end to end too when WORK's drive has the space the install's checks ask for (16.2 GB).
set -u
LAUNCHER=$1 STUB=$2 WORK=$3 PYTHON=$4
rm -rf "$WORK" && mkdir -p "$WORK"
failures=0
fail() {
    echo "FAILED: $*" >&2
    failures=$((failures + 1))
}

# home NAME STATE: a scratch home; STATE none | installed | older (the game built by an older kit)
home() {
    local h=$WORK/$1
    mkdir -p "$h/.config/ttt2" "$h/run" "$h/Games" "$h/Downloads" && chmod 700 "$h/run"
    printf 'x' > "$h/Downloads/game.wua"
    if [ "$2" != none ]; then
        local g="$h/Games/Tekken Tag Tournament 2"
        mkdir -p "$g"
        cat > "$g/Tekken Tag Tournament 2" <<'GAME'
#!/usr/bin/env bash
echo "stub game started"
[ -n "${TTT2_STUB_MARKER:-}" ] && echo played > "$TTT2_STUB_MARKER"
exit 0
GAME
        chmod +x "$g/Tekken Tag Tournament 2"
        touch "$g/.ttt2-install"
        if [ "$2" = older ]; then echo "kit 0.7.1-1111111111cd" > "$g/.ttt2-build"
        else echo "kit $(head -n1 "$STUB/kit/VERSION")" > "$g/.ttt2-build"; fi
        echo "$g" > "$h/.config/ttt2/installed"
    fi
    echo "$h"
}

# run HOME CASE [VAR=value...] -- [arguments]: the launcher's output in HOME/out.txt
run() {
    local h=$1 case=$2
    shift 2
    local vars=()
    while [ $# -gt 0 ] && [ "$1" != "--" ]; do
        # (The launcher stays open after its actions, as the GTK one did: each list ends with quit.)
        case $1 in
        TTT2_LAUNCHER_TEST_ACTIONS=*quit) vars+=("$1") ;;
        TTT2_LAUNCHER_TEST_ACTIONS=*) vars+=("$1;quit") ;;
        *) vars+=("$1") ;;
        esac
        shift
    done
    [ "${1:-}" = "--" ] && shift
    env -u DISPLAY -u WAYLAND_DISPLAY -u APPIMAGE -u APPDIR -u TTT2_LAUNCHER_TEST_ACTIONS \
        HOME="$h" XDG_CONFIG_HOME="$h/.config" XDG_DATA_HOME="$h/.local/share" XDG_CACHE_HOME="$h/.cache" \
        XDG_RUNTIME_DIR="$h/run" TTT2_SAVE_DIR="$h/saves" \
        TTT2_KIT="$STUB/kit" TTT2_IMPORTER="$STUB/importer" TTT2_PYTHON="$PYTHON" \
        TTT2_STUB_CASE="$STUB/../../../model/tests/golden/$case/case.json" TTT2_STUB_MARKER="$h/played" \
        TTT2_STUB_STEP_SECONDS=0.02 TTT2_LAUNCHER_RELEASES="file://$h/no-release.json" \
        TTT2_LAUNCHER_TEST_SHOTS="$h/shots" "${vars[@]}" \
        timeout 120 "$LAUNCHER" "$@" > "$h/out.txt" 2>&1
    echo $? > "$h/code.txt"
}
has() { grep -q -- "$2" "$1/out.txt" || fail "$1: no '$2' in its output: $(tail -n 5 "$1/out.txt")"; }

# Start, then Quit.
h=$(home start none)
run "$h" not-installed "TTT2_LAUNCHER_TEST_ACTIONS=quit"
has "$h" '@test quit ok'
[ -f "$h/shots/00-start.png" ] || fail "start: no picture of the start"

# Install with a game that is not there: the checks before it say so, nothing is started.
h=$(home missing none)
run "$h" not-installed "TTT2_LAUNCHER_TEST_ACTIONS=install:$h/Downloads/nothing.wua:$h/Games/Tekken Tag Tournament 2"
has "$h" '@test install:.* failed .*nothing.wua does not exist'
[ -e "$h/Games/Tekken Tag Tournament 2" ] && fail "missing: the install folder was made"

# Play: the stub game runs (its marker), its output in the game log.
h=$(home play installed)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=play"
has "$h" '@test play ok'
[ -f "$h/played" ] || fail "play: the game did not start"
grep -q 'stub game started' "$h/.cache/ttt2/game.log" 2>/dev/null || fail "play: no game log in .cache/ttt2/game.log"

# Update: the builder's steps to the end, its build record.
h=$(home update older)
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=update"
has "$h" '@test update ok'
grep -q "kit $(head -n1 "$STUB/kit/VERSION")" "$h/Games/Tekken Tag Tournament 2/.ttt2-build" ||
    fail "update: the build record is not the stub kit's"

# An update killed by a signal: 128 + 9, named.
h=$(home killed older)
run "$h" installed TTT2_STUB_FAIL=signal:compile "TTT2_LAUNCHER_TEST_ACTIONS=update"
has "$h" '@test update failed .*stopped: Killed (code 137'

# Cancel at the first step: stopped, the builder gone.
h=$(home cancel older)
run "$h" installed TTT2_STUB_STEP_SECONDS=0.3 TTT2_LAUNCHER_TEST_CANCEL=-1 TTT2_STUB_PIDFILE="$h/builder.pid" \
    "TTT2_LAUNCHER_TEST_ACTIONS=update"
has "$h" '@test update failed Update cancelled'
[ -f "$h/shots/01-update-stopping.png" ] || fail "cancel: no picture of Stopping"
if [ -f "$h/builder.pid" ] && kill -0 "$(cat "$h/builder.pid")" 2>/dev/null; then
    fail "cancel: the builder still runs"
fi

# Uninstall, saves kept.
h=$(home uninstall installed)
mkdir -p "$h/saves" && echo save > "$h/saves/slot"
run "$h" installed "TTT2_LAUNCHER_TEST_ACTIONS=uninstall:keep"
has "$h" '@test uninstall:keep ok'
[ -e "$h/Games/Tekken Tag Tournament 2/Tekken Tag Tournament 2" ] && fail "uninstall: the game is still there"
[ -f "$h/saves/slot" ] || fail "uninstall: the saves are gone"

# A picture at a size.
h=$(home shot installed)
run "$h" installed -- --screenshot "$h/home.png" --size 960x640
"$PYTHON" - "$h/home.png" <<'PY' || fail "screenshot: not a 960x640 PNG"
import struct, sys
with open(sys.argv[1], "rb") as f:
    head = f.read(24)
assert head[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
w, h = struct.unpack(">II", head[16:24])
assert (w, h) == (960, 640), (w, h)
PY

# The install end to end, when there is the space its checks ask for.
free=$(df -Pk "$WORK" | awk 'NR == 2 { print $4 }')
if [ "${free:-0}" -ge $((17 * 1024 * 1024)) ]; then
    h=$(home install none)
    run "$h" not-installed \
        "TTT2_LAUNCHER_TEST_ACTIONS=install:$h/Downloads/game.wua:$h/Games/Tekken Tag Tournament 2;play"
    has "$h" '@test install:.* ok'
    has "$h" '@test play ok'
    [ -f "$h/Games/Tekken Tag Tournament 2/.ttt2-install" ] || fail "install: no install marker"
    [ -f "$h/played" ] || fail "install: the game did not start after it"
else
    echo "install end to end left out: $((free / 1024 / 1024)) GB free in $WORK, the checks ask for 16.2"
fi

if [ "$failures" -gt 0 ]; then
    echo "$failures failed (outputs in $WORK/*/out.txt)" >&2
    exit 1
fi
echo "launcher e2e: all passed"
