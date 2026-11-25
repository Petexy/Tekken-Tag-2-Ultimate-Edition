#!/usr/bin/env bash
# The in-app .wua browser, offscreen against the stubs of tests/stub, each run in a scratch home
# of its own below WORK (no bus, SDL's dummy audio):
#
#   picker.sh LAUNCHER STUB WORK PYTHON [SLOW_FOLDERS_SO]
#
# - a Downloads of 5 / 40 / 300 / 3000 files at 1280x800 and of 3000 at 2560x1440 (scale 2): the rows in view keep
#   their width (fitted to the seam row by row, not by the list's bottom), only those near the view are declared, End
#   reaches the last row and Home the first, and the screens' audit stays clean;
# - Show hidden: Ctrl+H lists the dot names, the crimson "Show hidden" row (the pad's way) hides them again;
# - SLOW_FOLDERS_SO (tests/slow_folders.c): a folder that takes 3 s to open never stops the window: the browser
#   opens at once ("Reading this folder") and its entries come after.
set -u
LAUNCHER=$1 STUB=$2 WORK=$3 PYTHON=$4 SLOW=${5:-}
rm -rf "$WORK" && mkdir -p "$WORK"
failures=0
fail() {
    echo "FAILED: $*" >&2
    failures=$((failures + 1))
}

# home NAME N: a first start (nothing installed) whose Downloads holds N empty files
home() {
    local h=$WORK/$1
    mkdir -p "$h/.config/ttt2" "$h/run" "$h/Games" "$h/Downloads" && chmod 700 "$h/run"
    (cd "$h/Downloads" && for i in $(seq 1 "$2"); do : > "file$i.txt"; done)
    echo "$h"
}

# run HOME ACTIONS [launcher args]: after the Home's game slot (the browser opens), each output line with the seconds
# since the start in HOME/out.txt
run() {
    local h=$1 actions=$2
    shift 2
    env -u DISPLAY -u WAYLAND_DISPLAY -u APPIMAGE -u APPDIR -u DBUS_SESSION_BUS_ADDRESS \
        HOME="$h" XDG_CONFIG_HOME="$h/.config" XDG_DATA_HOME="$h/.local/share" XDG_CACHE_HOME="$h/.cache" \
        XDG_RUNTIME_DIR="$h/run" TTT2_SAVE_DIR="$h/saves" USER=player \
        SDL_AUDIO_DRIVER=dummy TTT2_LAUNCHER_TEST_AUDIO=dummy \
        TTT2_KIT="$STUB/kit" TTT2_IMPORTER="$STUB/importer" TTT2_PYTHON="$PYTHON" \
        TTT2_STUB_CASE="$STUB/../../../model/tests/golden/not-installed/case.json" \
        TTT2_LAUNCHER_RELEASES="file://$h/no-release.json" \
        TTT2_LAUNCHER_TEST_ACTIONS="toggle:slot:game;$actions;quit" timeout 180 "$LAUNCHER" "$@" 2>&1 |
        "$PYTHON" -I -u -c '
import sys, time
t0 = time.monotonic()
for line in sys.stdin:
    print(f"{time.monotonic() - t0:.2f} {line}", end="")' > "$h/out.txt"
    local code=${PIPESTATUS[0]}
    [ "$code" = 0 ] || fail "$h: exit code $code: $(tail -n 5 "$h/out.txt")"
    grep -q '@test .* failed' "$h/out.txt" && fail "$h: $(grep -m 3 '@test .* failed' "$h/out.txt")"
    grep -q '@audit failed' "$h/out.txt" && fail "$h: $(grep -m 3 '@audit failed' "$h/out.txt")"
}
# declared HOME K: how many rows the K-th "rows:" check found declared
declared() { grep '@test rows:.* ok' "$1/out.txt" | sed -n "$2p" | sed 's/.* of \([0-9]*\) declared.*/\1/'; }
# rows_line HOME K: the K-th "rows:" check's answer
rows_line() { grep '@test rows:.* ok' "$1/out.txt" | sed -n "$2p" | sed 's/.* ok //'; }

# (300 points: a file's name and size side by side; before the fix 40 entries left 130, 300 entries a sliver.)
list="rows:pe::300;press:End;rows:pe::300;focus:pe:1;press:PageDown;rows:pe::300;press:Home;rows:pe::300"
for case in "5 1280x800 1" "40 1280x800 1" "300 1280x800 1" "3000 1280x800 1" "3000 2560x1440 2"; do
    set -- $case
    h=$(home "list-$1-$2" "$1")
    run "$h" "$list" --size "$2" --scale "$3"
    [ "$(grep -c '@test rows:.* ok' "$h/out.txt")" = 4 ] || fail "$1 at $2: $(grep '@test rows' "$h/out.txt" | tail -n 2)"
    for k in 1 2 3 4; do
        d=$(declared "$h" "$k")
        [ -n "$d" ] && [ "$d" -le $(($1 + 1)) ] && [ "$d" -le 80 ] || fail "$1 at $2: check $k: $(rows_line "$h" "$k")"
    done
done

# Show hidden: two dot names in Downloads besides two files and the way up
h=$(home hidden 1)
mkdir -p "$h/Downloads/.cache-dir" && : > "$h/Downloads/.old.wua" && : > "$h/Downloads/game.wua"
run "$h" "rows:pe::0;press:Ctrl+H;rows:pe::0;focus:pk/hidden;press:Return;rows:pe::0"
[ "$(declared "$h" 1)/$(declared "$h" 2)/$(declared "$h" 3)" = "3/5/3" ] ||
    fail "hidden: rows $(declared "$h" 1)/$(declared "$h" 2)/$(declared "$h" 3), not 3/5/3 (Ctrl+H, then its row)"

# A slow folder (a home named /slow...: every folder in it takes 3 s to open)
if [ -n "$SLOW" ]; then
    h=$(home slowhome 4)
    mkdir -p "$h/Downloads/sub"
    SLOW_MS=3000 LD_PRELOAD="$SLOW" run "$h" "rows:pe::0"
    opened=$(awk '/@test toggle:slot:game started/ { s = $1 } /@test toggle:slot:game ok/ { print $1 - s }' "$h/out.txt")
    awk -v d="${opened:-99}" 'BEGIN { exit !(d < 1.0) }' || fail "slow: the browser took $opened s to open"
    [ "$(declared "$h" 1)" = 6 ] || fail "slow: rows $(rows_line "$h" 1) once read (6: up, sub, 4 files)"
fi

if [ "$failures" -gt 0 ]; then
    echo "$failures failure(s)" >&2
    exit 1
fi
echo "picker: all runs passed${SLOW:+, a slow folder too}"
