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
# More drilled into), folders (Settings > Folders, Browse with New Folder), sounds (Sound on: what is heard), josé
# (a José in every folder: the later queries reach Python, compat review #1), restore (a test build whose Update got
# a newer program's files: the .exe puts its own back and says a new test build is needed, compat review #3).
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
# (No sound reaches a speaker: Wine blanks SDL_AUDIO_DRIVER for Windows programs, so the launcher's tests choose
# their driver with TTT2_LAUNCHER_TEST_AUDIO, and Wine's own audio drivers are off.)
export WINEPREFIX=$WORK/prefix WINEDEBUG=-all SDL_AUDIO_DRIVER=dummy TTT2_LAUNCHER_TEST_AUDIO=dummy
export WINEDLLOVERRIDES="winemenubuilder.exe=d;winepulse.drv=d;winealsa.drv=d;wineoss.drv=d;winecoreaudio.drv=d"
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

# A José in every folder (compat review #1: a libc++ build, as a player's Set Up Game makes, turned the model's
# paths into the ANSI code page): the first state, then the status and owned questions through the model's
# own commands reach the stub Python, and Home shows the installed game.
# A test build's .exe (files appended) whose files an Update replaced with a newer program's: query.py's PROTOCOL 2
# under the .exe's digest. The .exe puts its own files back, asks again and says a new test build is needed.
if want_case restore; then
    make_root restore installed yes
    "${PYTHON:-python3}" - "$SRC" "$EXE" "$WORK/restore" <<'PY'
import hashlib, sys
from pathlib import Path
src, exe, case = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(src / 'launcher/windows'))
from make_launcher_exe import payload
import self_update
root = case / 'root'
own = {'launcher/windows/main.py': (root / 'launcher/windows/main.py').read_bytes(),
       'launcher/windows/query.py': b'PROTOCOL = 1\n',
       'Start Ultimate Launcher.cmd': (root / 'Start Ultimate Launcher.cmd').read_bytes(),
       self_update.BUILD_BRANCH: b'dev-test\n', self_update.BUILD_COMMIT: b'a' * 40 + b'\n'}
files = payload(own)
(case / 'test-build.exe').write_bytes(exe.read_bytes() + files)
digest = hashlib.sha256(files[:-self_update.TRAILER.size]).hexdigest()
updated = dict(own, **{'launcher/windows/query.py': b'PROTOCOL = 2\n', 'launcher/app/newer.cpp': b'newer',
                       self_update.BUILD_COMMIT: b'b' * 40 + b'\n'})
for name, data in updated.items():
    (root / name).parent.mkdir(parents=True, exist_ok=True); (root / name).write_bytes(data)
(root / self_update.STAMP).write_text(digest + '\n' + ''.join(n + '\n' for n in sorted(updated)), encoding='utf-8')
PY
    EXE_SAVED=$EXE
    EXE=$WORK/restore/test-build.exe
    cp "$B/launcher/SDL3.dll" "$WORK/restore/"
    run restore 0 "wait:1.0" TTT2_STUB_PROTOCOL_FROM_FILES=1
    EXE=$EXE_SAVED
    expect restore "@ready restored its own files (their protocol 2)"
    [ "$(cat "$WORK/restore/root/launcher/windows/query.py" 2>/dev/null)" = "PROTOCOL = 1" ] || fail restore "query.py not put back"
    [ ! -e "$WORK/restore/root/launcher/app/newer.cpp" ] || fail restore "the update's own file left"
    grep -qx 'a\{40\}' "$WORK/restore/root/launcher/windows/build-commit" || fail restore "build-commit not put back"
    [ "$(grep -cx state "$WORK/restore/answers/queries.log" 2>/dev/null)" = 2 ] || fail restore "the state not asked twice"
fi

if want_case josé; then
    make_root josé installed yes
    run josé 0 "wait:1.5;focus:more;press:Return;wait:0.6"
    for q in state status owned; do
        grep -qx "$q" "$WORK/josé/answers/queries.log" 2>/dev/null || fail josé "no --query $q reached Python ($WORK/josé/answers/queries.log)"
    done
    [ "$(grep -c . "$WORK/josé/answers/queries.log" 2>/dev/null)" -ge 3 ] || fail josé "too few queries"
fi

# Sounds (FEEDBACK F7): Sound on (launcher.ini beside display.ini), SDL's disk audio driver into a file: moving, a
# drill-in and out, the next tab are heard. GAME_SOUNDS (optional: an installed game's folder, only read, linked
# in): the game's own sounds are the ones used.
if want_case sounds; then
    make_root sounds installed yes
    printf 'sounds=yes\n' > "$WORK/sounds/root/appdata/TTT2Ultimate/config/launcher.ini"
    if [ -n "${GAME_SOUNDS:-}" ]; then
        mkdir -p "$WORK/sounds/root/Games/Tekken Tag Tournament 2/game/content"
        ln -s "$GAME_SOUNDS/game/content/hdd" "$WORK/sounds/root/Games/Tekken Tag Tournament 2/game/content/hdd"
    fi
    run sounds 0 "press:Down;wait:0.3;focus:more;press:Return;wait:0.3;press:Escape;wait:0.3;press:e;wait:2.2;quit" \
        TTT2_LAUNCHER_TEST_AUDIO=disk SDL_AUDIO_DISK_OUTPUT_FILE="$(winpath "$WORK/sounds/audio.raw")" \
        TTT2_LAUNCHER_TEST_CUES=1
    expect sounds "@cue move"
    expect sounds "@cue tab"
    [ -s "$WORK/sounds/audio.raw" ] || fail sounds "no sound written (no $WORK/sounds/audio.raw)"
    if [ -n "${GAME_SOUNDS:-}" ]; then expect sounds "@sounds the game's sounds"; fi
fi

if [ "$failures" -gt 0 ]; then
    echo "run_wine: $failures failed" >&2
    exit 1
fi
echo "run_wine: all passed"
