#!/usr/bin/env bash
# The other video driver: the launcher in a headless cage (WLR_BACKENDS=headless: Wayland and
# Xwayland of its own, nothing on this PC's screen) on a private bus, a start as a player's (TTT2_LAUNCHER_TEST_SMOKE)
# whose first frame says the driver. The player's SDL_VIDEODRIVER / SDL_VIDEO_DRIVER naming a driver that fails must
# not keep the other one from being tried.
#
#   video_fallback.sh LAUNCHER WORK
#
# Skipped (77) without cage, Xwayland or dbus-run-session.
set -u
LAUNCHER=$(readlink -f "$1") WORK=$2
for p in cage Xwayland dbus-run-session; do command -v "$p" > /dev/null || { echo "SKIP: no $p"; exit 77; }; done
rm -rf "$WORK" && mkdir -p "$WORK"
WORK=$(cd "$WORK" && pwd)
# (Each case's XDG_RUNTIME_DIR, short: a Wayland socket's path has at most 107 bytes.)
RUNS=$(mktemp -d /tmp/ttt2-vf.XXXXXX)
trap 'rm -rf "$RUNS"' EXIT
failures=0

# smoke NAME EXPECTED [VAR=value...]: the frame's driver (video=EXPECTED) or, EXPECTED "none", no frame.
smoke() {
    local name=$1 want=$2 h=$WORK/$1 run=$RUNS/$1
    shift 2
    mkdir -p "$h/home" "$run" && chmod 700 "$run"
    cat > "$h/inner.sh" <<IN
#!/bin/sh
exec env $* "$LAUNCHER" > "$h/out.txt" 2>&1
IN
    chmod +x "$h/inner.sh"
    env -i PATH="$PATH" HOME="$h/home" XDG_CONFIG_HOME="$h/home/.config" XDG_DATA_HOME="$h/home/.local/share" \
        XDG_CACHE_HOME="$h/home/.cache" XDG_RUNTIME_DIR="$run" TMPDIR="$h" LANG=C.UTF-8 \
        SDL_AUDIO_DRIVER=dummy TTT2_LAUNCHER_TEST_AUDIO=dummy TTT2_LAUNCHER_TEST_SMOKE="$h/smoke.json" \
        TTT2_LAUNCHER_TEST_INSTANCE="ttt2-video-fallback-$$-$name" \
        WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
        timeout 60 dbus-run-session -- cage -- "$h/inner.sh" > "$h/cage.txt" 2>&1
    local got
    got=$(python3 -c 'import json, sys; f = json.load(open(sys.argv[1]))["frame"]; print(f.split()[0][6:] if f else "none")' \
        "$h/smoke.json" 2>/dev/null || echo "no answer")
    if [ "$got" = "$want" ]; then
        echo "ok $name: $got"
    else
        echo "FAILED $name: video $got, not $want (see $h/out.txt)" >&2
        failures=$((failures + 1))
    fi
}

smoke plain-wayland wayland SDL_VIDEO_DRIVER=wayland
smoke plain-x11 x11 SDL_VIDEO_DRIVER=x11
# (The cases: the driver named fails, the other is there.)
smoke named-wayland-gone x11 WAYLAND_DISPLAY=nonexistent SDL_VIDEODRIVER=wayland
smoke named-x11-gone wayland DISPLAY=:99 SDL_VIDEODRIVER=x11
smoke new-name-x11-gone wayland DISPLAY=:99 SDL_VIDEO_DRIVER=x11
[ "$failures" = 0 ] && echo "video_fallback: all passed"
exit $((failures > 0))
