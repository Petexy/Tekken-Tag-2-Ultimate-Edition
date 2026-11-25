#!/usr/bin/env bash
# C2's way back (compat review #4), end to end, offscreen in a scratch home, against a stand-in of GitHub on
# 127.0.0.1: this launcher, run as an AppImage (a script that sets APPIMAGE/APPDIR), updates itself to a new version
# that passes the update's checks and then breaks (BROKEN: broken.cpp with an AppImage's header).
#
#   way_back.sh LAUNCHER BROKEN WORK PYTHON
#
# crash: the new one ends by SIGSEGV before its first frame: the version before is put back in place and opened,
#        and says what happened (its smoke answer: rolled_back).
# window: the new one cannot open its window: it puts the version before back itself and says so.
# Both: the AppImage file is the old one again, no .previous is left. No display, bus or sound of this PC is used,
# and the launchers that start as a player's have a name of their own (TTT2_LAUNCHER_TEST_INSTANCE): never one in use.
set -u
LAUNCHER=$(readlink -f "$1") BROKEN=$(readlink -f "$2") WORK=$3 PYTHON=$4
rm -rf "$WORK" && mkdir -p "$WORK"
WORK=$(cd "$WORK" && pwd)
failures=0
fail() {
    echo "FAILED: $*" >&2
    failures=$((failures + 1))
}
VERSION=99.0.0

# The broken new version, as an AppImage (type 2) is recognised: "AI" 2 at byte 8.
mkdir -p "$WORK/release"
cp "$BROKEN" "$WORK/release/Golden_Fist_Launcher-x86_64.AppImage"
printf 'AI\002' | dd of="$WORK/release/Golden_Fist_Launcher-x86_64.AppImage" bs=1 seek=8 conv=notrunc status=none

# GitHub's latest release and its AppImage (with its SHA-256), on a free port.
cat > "$WORK/server.py" <<'PY'
import hashlib, http.server, json, os, sys
folder, version, ready = sys.argv[1], sys.argv[2], sys.argv[3]
data = open(os.path.join(folder, 'Golden_Fist_Launcher-x86_64.AppImage'), 'rb').read()
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        port = self.server.server_address[1]
        if self.path == '/latest.json':
            body = json.dumps({'tag_name': 'v' + version, 'draft': False, 'prerelease': False,
                               'html_url': 'http://127.0.0.1:%d/release' % port,
                               'assets': [{'name': 'Golden_Fist_Launcher-x86_64.AppImage', 'state': 'uploaded',
                                           'size': len(data), 'digest': 'sha256:' + hashlib.sha256(data).hexdigest(),
                                           'browser_download_url': 'http://127.0.0.1:%d/file' % port}]}).encode()
        elif self.path == '/file':
            body = data
        else:
            self.send_error(404); return
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args): pass
server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
open(ready, 'w').write(str(server.server_address[1]))
server.serve_forever()
PY
"$PYTHON" "$WORK/server.py" "$WORK/release" "$VERSION" "$WORK/port" &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
for _ in $(seq 100); do [ -s "$WORK/port" ] && break; sleep 0.1; done
PORT=$(cat "$WORK/port" 2>/dev/null)
[ -n "$PORT" ] || { echo "FAILED: no server" >&2; exit 1; }

# A case: the old launcher (this one, as an AppImage in apps/) updates itself, then the new one breaks ($1).
case_run() {
    local name=$1 h=$WORK/$1
    mkdir -p "$h/apps" "$h/home/Games" "$h/run" && chmod 700 "$h/run"
    : > "$h/out.txt" # (appended to by all: the old one, the new one and the one put back share it)
    local image=$h/apps/Golden_Fist_Launcher-x86_64.AppImage
    # (The version before: this launcher as an AppImage. Put back and opened again, it answers as a player's start.)
    cat > "$image" <<SH
#!/bin/sh
export APPIMAGE="\$0" APPDIR="$(dirname "$LAUNCHER")"
if [ -n "\${TTT2_LAUNCHER_ROLLED_BACK:-}" ]; then
    unset TTT2_LAUNCHER_TEST_ACTIONS
    export TTT2_LAUNCHER_TEST_SMOKE="$h/restored.json"
fi
exec "$LAUNCHER" "\$@"
SH
    chmod 755 "$image"
    cp "$image" "$h/old-one"
    env -i PATH="$PATH" HOME="$h/home" XDG_CONFIG_HOME="$h/home/.config" XDG_DATA_HOME="$h/home/.local/share" \
        XDG_CACHE_HOME="$h/home/.cache" XDG_RUNTIME_DIR="$h/run" TMPDIR="$h" LANG=C.UTF-8 \
        SDL_AUDIO_DRIVER=dummy TTT2_LAUNCHER_TEST_AUDIO=dummy TTT2_LAUNCHER_TEST_VIDEO=offscreen \
        TTT2_LAUNCHER_TEST_INSTANCE="ttt2-way-back-$$-$name" \
        TTT2_LAUNCHER_RELEASES="http://127.0.0.1:$PORT/latest.json" \
        TTT2_LAUNCHER_TEST_ACTIONS="wait:1.5;update-launcher;wait:2;quit" \
        TTT2_BROKEN="$name" TTT2_BROKEN_VERSION="$VERSION" TTT2_BROKEN_LAUNCHER="$LAUNCHER" \
        timeout 120 "$image" >> "$h/out.txt" 2>&1
    echo "old launcher exit $?" >> "$h/out.txt"
}

wait_for() { # SECONDS COMMAND...: until it is true
    local tries=$(($1 * 10))
    shift
    for _ in $(seq "$tries"); do "$@" && return 0; sleep 0.1; done
    return 1
}
same() { cmp -s "$1" "$2"; }
gone() { [ ! -e "$1" ]; }

# crash: the way back puts the old one back and opens it, which says why.
case_run crash
h=$WORK/crash
wait_for 60 test -s "$h/restored.json" || fail "crash: the version before was not opened again (see $h/out.txt)"
grep -q "broken: crashing before any frame" "$h/out.txt" || fail "crash: the new version never ran"
grep -q "version $VERSION ended (code 139) before its first frame: the version before is back" "$h/out.txt" ||
    fail "crash: the way back said nothing"
"$PYTHON" - "$h/restored.json" "$VERSION" <<'PY' || fail "crash: the smoke answer of the one put back"
import json, sys
said = json.load(open(sys.argv[1]))
assert said['rolled_back'] == sys.argv[2] and said['frame'] and not said['error'], said
PY
grep -q "Version $VERSION did not start" "$h/out.txt" || fail "crash: the one put back did not tell the player"
same "$h/apps/Golden_Fist_Launcher-x86_64.AppImage" "$h/old-one" || fail "crash: the AppImage is not the old one"
gone "$h/apps/.Golden_Fist_Launcher-x86_64.AppImage.previous" || fail "crash: a .previous is left"
gone "$h/apps/.Golden_Fist_Launcher-x86_64.AppImage.update" || fail "crash: an .update is left"

# window: the new one puts the version before back itself.
case_run window
h=$WORK/window
wait_for 60 grep -q "the version before this update is back in" "$h/out.txt" ||
    fail "window: the new one did not put the version before back (see $h/out.txt)"
grep -q "cannot open its window" "$h/out.txt" || fail "window: no window failure said"
grep -q "went back to the version it was before this update: start it again" "$h/out.txt" ||
    fail "window: the player is not told"
same "$h/apps/Golden_Fist_Launcher-x86_64.AppImage" "$h/old-one" || fail "window: the AppImage is not the old one"
gone "$h/apps/.Golden_Fist_Launcher-x86_64.AppImage.previous" || fail "window: a .previous is left"

# (The one put back answered and ended: nothing of the cases is left running.)
pid=$("$PYTHON" -c 'import json, sys; print(json.load(open(sys.argv[1]))["pid"])' "$WORK/crash/restored.json" 2>/dev/null)
[ -n "$pid" ] && { wait_for 30 sh -c "! kill -0 $pid 2>/dev/null" || fail "the one put back still runs"; }
[ "$failures" = 0 ] && echo "way_back: all passed"
exit $((failures > 0))
