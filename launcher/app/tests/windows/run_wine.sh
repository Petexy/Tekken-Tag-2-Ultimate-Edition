#!/usr/bin/env bash
# run_wine.sh BUILD WORK [SHOTS]: the Windows launcher (BUILD = a mingw build: launcher/ttt2-launcher.exe, SDL3.dll,
# launcher/app/launcher_win_stub.exe) under headless Wine, drawn offscreen, against stand-ins (stub_tools.cpp): a
# files folder with the real "Start Ultimate Launcher.cmd" and stub curl/certutil/findstr/tar.exe, and a stub
# python.exe answering --query from answers.py. Nothing is downloaded, no Python and no game runs, no window opens,
# no sound plays. WORK holds its Wine prefix (its user folders inside WORK, never linked to the real home) and one
# folder per case; SHOTS (optional) gets each case's pictures.
#
# Cases: bootstrap (the first start: the .cmd hidden, its steps read from the log, then Home's Set Up),
# bootstrap-fail (no download: the failure and Try Again), protocol (another version's files: refused, Releases
# Page), setup (Set Up Game: the .wua and the folder in the in-app browser, then the confirmation), installed (Home,
# More drilled into), folders (Settings > Folders, Browse with New Folder).
set -euo pipefail
B=$(cd "$1" && pwd)
mkdir -p "$2"
WORK=$(cd "$2" && pwd)
SHOTS=${3:-}
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(cd "$HERE/../../../.." && pwd)
EXE=$B/launcher/ttt2-launcher.exe
STUB=$B/launcher/app/launcher_win_stub.exe
WINE=${WINE:-wine}
for f in "$EXE" "$STUB" "$B/launcher/SDL3.dll"; do [ -f "$f" ] || { echo "run_wine: no $f" >&2; exit 2; }; done

unset DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS
export WINEPREFIX=$WORK/prefix WINEDLLOVERRIDES=winemenubuilder.exe=d WINEDEBUG=-all SDL_AUDIO_DRIVER=dummy
export HOME=$WORK/home XDG_CONFIG_HOME=$WORK/home/.config XDG_DATA_HOME=$WORK/home/.local/share XDG_CACHE_HOME=$WORK/home/.cache
mkdir -p "$HOME"
if [ ! -d "$WINEPREFIX/drive_c" ]; then
    "$WINE" wineboot -i >/dev/null 2>&1 || true
    wineserver -w 2>/dev/null || true
fi
# (The prefix's Desktop, Downloads ... point at HOME: links only, removed so that nothing reaches outside WORK.)
find "$WINEPREFIX/drive_c/users" -maxdepth 2 -type l -delete 2>/dev/null || true

winpath() { printf 'Z:%s' "$(printf '%s' "$1" | sed 's#/#\\#g')"; }
HASH=$(grep -o 'findstr.exe /i /x "[0-9a-f]*"' "$SRC/Start Ultimate Launcher.cmd" | grep -o '[0-9a-f]\{64\}')
GOLDEN=$SRC/launcher/model/tests/golden

ONLY=${RUN_WINE_CASES:-}  # (a list of cases to run; all when empty)
want_case() { [ -z "$ONLY" ] || [[ " $ONLY " == *" $1 "* ]]; }

failures=0
fail() {
    echo "run_wine: FAILED $1: $2" >&2
    failures=$((failures + 1))
}

# A case's files folder: the start script (CRLF, as the release has it), main.py's place, the stub tools.
make_root() {
    local dir=$WORK/$1 answers=$2 python=$3
    rm -rf "$dir"
    mkdir -p "$dir/root/launcher/windows" "$dir/root/local" "$dir/root/Downloads" "$dir/root/appdata/TTT2Ultimate/logs" \
        "$dir/root/appdata/TTT2Ultimate/config" "$dir/root/Games" "$dir/shots"
    sed 's/\r*$/\r/' "$SRC/Start Ultimate Launcher.cmd" > "$dir/root/Start Ultimate Launcher.cmd"
    printf '# (the stub python answers instead)\n' > "$dir/root/launcher/windows/main.py"
    for t in curl certutil findstr tar; do cp "$STUB" "$dir/root/$t.exe"; done
    printf 'x' > "$dir/root/Downloads/Tekken Tag Tournament 2 [EUR] (update 16).wua"
    printf 'notes' > "$dir/root/Downloads/notes.txt"
    if [ "$answers" = installed ]; then
        mkdir -p "$dir/root/Games/Tekken Tag Tournament 2"
        printf 'x' > "$dir/root/Games/Tekken Tag Tournament 2/TTT2 Ultimate.exe"
    fi
    if [ "$python" = yes ]; then
        mkdir -p "$dir/root/local/windows-tools/python-runtime/python"
        cp "$STUB" "$dir/root/local/windows-tools/python-runtime/python/python.exe"
    fi
    local golden=$GOLDEN/installed/case.json
    [ "$answers" = setup ] && golden=$GOLDEN/not-installed/case.json
    "${PYTHON:-python3}" "$HERE/answers.py" "$dir/answers" "$(winpath "$dir/root")" "$answers" "$golden"
}

# run CASE EXPECTED_EXIT ACTIONS [extra env...]: the launcher, its standard error in WORK/CASE/run.log.
run() {
    local name=$1 want=$2 actions=$3
    shift 3
    local dir=$WORK/$name code=0
    env TTT2_STUB_ANSWERS="$(winpath "$dir/answers")" TTT2_STUB_HASH="$HASH" TTT2_STUB_CURL_SECONDS=1.5 \
        TTT2_LAUNCHER_TEST_FILES="$(winpath "$dir/root")" TTT2_LAUNCHER_TEST_ACTIONS="$actions" \
        TTT2_LAUNCHER_TEST_SHOTS="$(winpath "$dir/shots")" TTT2_LAUNCHER_RELEASES="file:///none.json" \
        USERPROFILE="$(winpath "$dir/root")" "$@" \
        timeout 240 "$WINE" "$EXE" --size 1280x800 --scale 1 --screenshot "$(winpath "$dir/shots/end.png")" \
        >"$dir/out.log" 2>"$dir/run.log" || code=$?
    if [ "$code" != "$want" ]; then fail "$name" "exit $code, not $want (see $dir/run.log)"; fi
    if grep -q '^@test .* failed' "$dir/run.log"; then fail "$name" "$(grep '^@test .* failed' "$dir/run.log" | head -3)"; fi
    if [ -n "$SHOTS" ]; then
        mkdir -p "$SHOTS"
        for f in "$dir"/shots/*.png; do [ -f "$f" ] && cp "$f" "$SHOTS/wine-$name-$(basename "$f")"; done
    fi
    return 0
}

expect() { grep -q -- "$2" "$WORK/$1/run.log" || fail "$1" "no \"$2\" (see $WORK/$1/run.log)"; }

# The first start: Python gotten by the real start script (hidden), its steps shown, then Home's Set Up.
if want_case bootstrap; then
    make_root bootstrap setup no
    run bootstrap 0 "wait:0.4;quit"
    expect bootstrap "@ready bootstrap-download"
    expect bootstrap "@ready state"
    [ -f "$WORK/bootstrap/root/local/windows-tools/python-runtime/python/python.exe" ] || fail bootstrap "no Python put in place"
    grep -q '@step ready' "$WORK/bootstrap/root/local/windows-bootstrap.log" || fail bootstrap "the log has no @step ready"
    grep -q '100.0%' "$WORK/bootstrap/root/local/windows-bootstrap.log" || fail bootstrap "the log has no download progress"
fi

# No download: the failure, with Try Again and the log.
if want_case bootstrap-fail; then
    make_root bootstrap-fail setup no
    run bootstrap-fail 3 "quit" TTT2_STUB_CURL_FAIL=1
    expect bootstrap-fail "@ready failed Cannot get the launcher ready"
fi

# Another version's files: refused, no Try Again.
if want_case protocol; then
    make_root protocol protocol yes
    run protocol 3 "quit"
    expect protocol "@ready failed These files are another version's"
fi

# Set Up Game: the archive, then the folder (a new one), then the confirmation.
if want_case setup; then
    make_root setup setup yes
    # (The in-app browser starts in the Windows user's Downloads: the archive is put there.)
    for u in "$WINEPREFIX"/drive_c/users/*/; do
        case "$(basename "$u")" in Public | Default) continue ;; esac
        mkdir -p "$u/Downloads"
        printf 'x' > "$u/Downloads/Tekken Tag Tournament 2 [EUR] (update 16).wua"
        rm -rf "$u/New folder"
    done
    run setup 0 "focus:setup;press:Return;wait:0.6;press:Return;wait:0.6;focus:pk/new;press:Return;wait:0.6;focus:pk/choose-here;press:Return;wait:0.8"
    expect setup "@test press:Return ok"
    ls -d "$WINEPREFIX"/drive_c/users/*/"New folder" >/dev/null 2>&1 || fail setup "New Folder made no folder"
    expect setup "@test focus:pk/choose-here ok"
fi

# Installed: Home, then More drilled into.
if want_case installed; then
    make_root installed installed yes
    run installed 0 "focus:more;press:Return;wait:0.6"
fi

# Settings > Folders, Browse on the data folder.
if want_case folders; then
    make_root folders installed yes
    run folders 0 "tab:settings;focus:sec:folders;press:Return;wait:0.6;focus:fold:data;wait:0.6"
fi

if [ "$failures" -gt 0 ]; then
    echo "run_wine: $failures failed" >&2
    exit 1
fi
echo "run_wine: all passed"
