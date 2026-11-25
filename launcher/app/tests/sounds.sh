#!/usr/bin/env bash
# The launcher's sounds as the player hears them (FEEDBACK F7), offscreen against the stubs of tests/stub, each run
# in a scratch home of its own below WORK, through SDL's disk audio driver (a file, never a speaker):
#
#   sounds.sh LAUNCHER STUB WORK PYTHON [GAME_FOLDER]
#
# - Sound on (launcher.ini), and with no launcher.ini at all (on by default): moving (Move), a button (Accept) and the
#   next tab (Tab) write sound to the file;
# - Sound off: the same steps open no audio device at all (no file);
# - the top band's Sound button turns the same setting on (launcher.ini says so) and what follows is heard;
# - Play, then the launcher quits at once: the Play sound is still written whole (the launcher waits for it), and the
#   shaders prepared before the game (on by default) add no chime of their own;
# - Home's UPDATE of two parts chimes once, at the end;
# - GAME_FOLDER (optional: an installed Tekken Tag Tournament 2, only read): the game's own sounds are the ones used.
set -u
LAUNCHER=$1 STUB=$2 WORK=$3 PYTHON=$4 GAME=${5:-}
rm -rf "$WORK" && mkdir -p "$WORK"
failures=0
fail() {
    echo "FAILED: $*" >&2
    failures=$((failures + 1))
}

# home NAME SOUND [GAME]: a scratch home with the game installed (by this kit), launcher.ini's sounds=SOUND (SOUND
# empty: no launcher.ini); GAME: that install's archives seen through a link (read only).
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
    [ -n "$2" ] && printf 'sounds=%s\n' "$2" > "$h/.config/ttt2/launcher.ini"
    if [ -n "${3:-}" ]; then
        mkdir -p "$g/game/content"
        ln -s "$3/game/content/hdd" "$g/game/content/hdd"
    fi
    echo "$h"
}

# run HOME ACTIONS: the launcher's output in HOME/out.txt, its sound in HOME/audio.raw (F32 stereo 48 kHz)
run() {
    local h=$1
    env -u DISPLAY -u WAYLAND_DISPLAY -u APPIMAGE -u APPDIR -u DBUS_SESSION_BUS_ADDRESS \
        HOME="$h" XDG_CONFIG_HOME="$h/.config" XDG_DATA_HOME="$h/.local/share" XDG_CACHE_HOME="$h/.cache" \
        XDG_RUNTIME_DIR="$h/run" TTT2_SAVE_DIR="$h/saves" \
        SDL_AUDIO_DRIVER=disk SDL_AUDIO_DISK_OUTPUT_FILE="$h/audio.raw" \
        TTT2_KIT="$STUB/kit" TTT2_IMPORTER="$STUB/importer" TTT2_PYTHON="$PYTHON" \
        TTT2_STUB_CASE="$STUB/../../../model/tests/golden/installed/case.json" \
        TTT2_LAUNCHER_RELEASES="file://$h/no-release.json" TTT2_LAUNCHER_TEST_CUES=1 \
        TTT2_LAUNCHER_TEST_ACTIONS="$2" timeout 120 "$LAUNCHER" > "$h/out.txt" 2>&1
    local code=$?
    [ "$code" = 0 ] || fail "$h: exit code $code: $(tail -n 5 "$h/out.txt")"
    grep -q '@test .* failed' "$h/out.txt" && fail "$h: $(grep -m 3 '@test .* failed' "$h/out.txt")"
}
cues() { grep -o '@cue [a-z-]*' "$1/out.txt" | cut -d' ' -f2 | tr '\n' ' '; }
# sounding HOME: seconds of the file louder than -60 dBFS (50 ms windows); "none" without a file
sounding() {
    [ -f "$1/audio.raw" ] || { echo none; return; }
    "$PYTHON" -I - "$1/audio.raw" <<'PY'
import array, math, sys
a = array.array('f')
with open(sys.argv[1], 'rb') as f:
    a.frombytes(f.read())
if sys.byteorder != 'little':
    a.byteswap()
win, loud = 4800, 0
for i in range(0, len(a) - win + 1, win):
    if math.sqrt(sum(x * x for x in a[i:i + win]) / win) > 1e-3:
        loud += 1
print(f"{loud * 0.05:.2f}")
PY
}
at_least() { awk -v a="$1" -v b="$2" 'BEGIN { exit !(a != "none" && a + 0 >= b + 0) }'; }

steps="press:Down;wait:0.3;focus:open-folder;press:Return;wait:0.5;press:e;wait:2.5;quit"

h=$(home on yes)
run "$h" "$steps"
[ "$(cues "$h")" = "move accept tab " ] || fail "on: cues $(cues "$h")"
s=$(sounding "$h")
at_least "$s" 0.3 || fail "on: $s s of sound for Move, Accept and Tab"
grep -q "@sounds the launcher's own sounds" "$h/out.txt" || fail "on: $(grep '@sounds' "$h/out.txt")"

h=$(home default "")
run "$h" "$steps"
[ "$(cues "$h")" = "move accept tab " ] || fail "default: cues $(cues "$h")"
s=$(sounding "$h")
at_least "$s" 0.3 || fail "default (no launcher.ini): $s s of sound for Move, Accept and Tab"

h=$(home off no)
run "$h" "$steps"
[ "$(cues "$h")" = "move accept tab " ] || fail "off: cues $(cues "$h")"
[ -e "$h/audio.raw" ] && fail "off: an audio device was opened ($(sounding "$h") s of sound)"

h=$(home button no)
run "$h" "wait:0.3;click:sound;wait:0.6;press:Down;wait:2.3;quit"
[ "$(cues "$h")" = "toggle move " ] || fail "button: cues $(cues "$h")"
grep -q '^sounds=yes' "$h/.config/ttt2/launcher.ini" || fail "button: launcher.ini $(cat "$h/.config/ttt2/launcher.ini")"
s=$(sounding "$h")
at_least "$s" 0.1 || fail "button: $s s of sound after Sound was turned on"

# (The launcher's own Play sound is about 1.4 s long: most of it must be in the file although the window quit.)
h=$(home play yes)
run "$h" "wait:0.3;focus:play;press:Return;quit"
[ "$(cues "$h")" = "play " ] || fail "play: cues $(cues "$h")"
s=$(sounding "$h")
at_least "$s" 0.8 || fail "play: only $s s of the Play sound before the launcher ended"

# (Home's UPDATE, two parts one after the other (the game program built again, then a fighter): one chime at the end.)
h=$(home update yes)
echo "kit 0.0.1" > "$h/Games/Tekken Tag Tournament 2/.ttt2-build"
run "$h" "wait:0.3;update-everything;quit"
[ "$(grep -c '@cue task-done' "$h/out.txt")" = 1 ] || fail "update: cues $(cues "$h")"
grep -q '@cue task-failed' "$h/out.txt" && fail "update: a part failed: $(cues "$h")"

if [ -n "$GAME" ]; then
    h=$(home game yes "$GAME")
    run "$h" "$steps"
    grep -q "@sounds the game's sounds" "$h/out.txt" || fail "game: $(grep '@sounds' "$h/out.txt")"
    s=$(sounding "$h")
    at_least "$s" 0.3 || fail "game: $s s of sound"
fi

if [ "$failures" -gt 0 ]; then
    echo "$failures failure(s)" >&2
    exit 1
fi
if [ -n "$GAME" ]; then
    echo "sounds: all runs passed, the game's sounds too"
else
    echo "sounds: all runs passed"
fi
