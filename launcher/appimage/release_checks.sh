#!/bin/bash
# The checks a Linux release program of the launcher must pass to start on any x86-64 PC with the oldest distribution
# it is for (Ubuntu 24.04: glibc 2.39, GCC 14's libstdc++): make_appimage.sh runs them on the AppDir before it packs
# it, and they can be run on a program alone:
#
#   launcher/appimage/release_checks.sh [--launcher] FILE...
#
# checks each FILE's ISA level, instructions, glibc and libstdc++ versions and needed libraries (with --launcher,
# the launcher's own rule: only the C and C++ runtimes' libraries, SDL and the display's libraries being built in or
# opened at run time). Sourced (". release_checks.sh"), it defines the functions below and checks nothing; each stops
# with die (the caller's, else one that prints "<script>: <message>" and exits 1).
#
# Needs readelf, objdump, sort -V; ldd for release_newest_glibc_linked_here.

# The oldest distributions' versions.
release_glibc=GLIBC_2.39
release_glibcxx=GLIBCXX_3.4.33
# What the launcher program itself may need: everything else it uses is in it (SDL 3, built statically) or
# opened by it at run time (X11, Wayland, libdecor, PipeWire, PulseAudio, ALSA, udev, D-Bus, Vulkan, GL).
release_launcher_libraries=(libc.so.6 libm.so.6 libstdc++.so.6 libgcc_s.so.1 ld-linux-x86-64.so.2)

if ! declare -F die >/dev/null; then
    die() {
        echo "${0##*/}: $*" >&2
        exit 1
    }
fi

# release_matching_files TEST PATH...: the files of PATH... (a folder's named from inside it, as ./x/y) for which
# the command TEST FILE succeeds, one per line.
release_matching_files() {
    local test=$1 path file
    shift
    for path in "$@"; do
        if [ -d "$path" ]; then
            (cd "$path" && find . -type f -print | while IFS= read -r file; do
                if "$test" "$file"; then echo "$file"; fi
            done)
        elif "$test" "$path"; then
            echo "$path"
        fi
    done
}

release_isa_marked() {
    readelf -n "$1" 2>/dev/null | grep -q 'x86 ISA needed:.*x86-64-v[234]'
}

release_has_avx512() {
    objdump -d -w "$1" 2>/dev/null | awk -F'\t' '$2 ~ /^62 / && $3 !~ /bad/ {found = 1; exit} END {exit !found}'
}

# release_check_isa_level PATH...: no file may be marked as needing more than the baseline x86-64 (GNU ld copies the
# x86 ISA level of the system's startup files, x86-64-v4 on CachyOS, into every program; glibc then refuses to start
# it on a processor without AVX-512: "CPU ISA level is lower than required").
release_check_isa_level() {
    local marked
    marked=$(release_matching_files release_isa_marked "$@")
    [ -z "$marked" ] || die "these need a newer processor than any x86-64 (their ISA level): $marked"
}

# release_check_avx512 PATH...: nor may any hold an AVX-512 instruction (EVEX: in 64-bit code, one whose first byte is
# 62). On such a system, static libraries are compiled for its processor (CachyOS's x86-64-v4 libstdc++.a once stopped
# the kit's programs with SIGILL on a Steam Deck), and nothing marks the code they bring.
release_check_avx512() {
    local avx512
    avx512=$(release_matching_files release_has_avx512 "$@")
    [ -z "$avx512" ] || die "these hold AVX-512 instructions, which many x86-64 processors do not have: $avx512"
}

# release_newest FILE NAME: the newest NAME_ version FILE needs (NAME: GLIBC, GLIBCXX).
release_newest() {
    readelf -V "$1" | sed -n "s/.*Name: $2_\([0-9.]*\).*/\1/p" | sort -V | tail -n 1
}

# release_newest_glibc_linked_here FILE LIMIT: the newest GLIBC_ version FILE needs that this system's glibc has no
# version of up to LIMIT. For a program linked here against this system's glibc as the players' PCs link it against
# theirs (kit_check: the game program): a function glibc gave a new default version since (atan2f: 2.43, beside its
# 2.2.5 one) is bound to that version here and to its older one there, so only what has no version up to the limit
# counts: a function older glibcs lack, or a name the headers rename (C23's __isoc23_strtol).
release_newest_glibc_linked_here() {
    local libs name version oldest
    libs=$(ldd "$1" | sed -n 's/^.* => \(\/[^ ]*\) (.*$/\1/p')
    objdump -T "$1" | sed -n 's/.*\*UND\*.*(GLIBC_\([0-9.]*\)) *\([^ ]*\)$/\2 \1/p' | while read -r name version; do
        [ "$(printf '%s\n' "$version" "$2" | sort -V | tail -n 1)" = "$2" ] && continue
        # shellcheck disable=SC2086
        oldest=$(objdump -T $libs 2>/dev/null | awk -v n="$name" '$NF == n && $0 !~ /\*UND\*/ {
            v = $(NF - 1); gsub(/[()]/, "", v); if (v ~ /^GLIBC_/) print substr(v, 7) }' | sort -V | head -n 1)
        if [ -z "$oldest" ] || [ "$(printf '%s\n' "$oldest" "$2" | sort -V | tail -n 1)" != "$2" ]; then echo "$version"; fi
    done | sort -V | tail -n 1
}

# release_check_versions [--linked-here] FILE: FILE needs no newer glibc ($release_glibc) or libstdc++
# ($release_glibcxx) than the oldest distributions have; --linked-here: glibc's as release_newest_glibc_linked_here
# counts it.
release_check_versions() {
    local linked_here= program limit need
    if [ "$1" = --linked-here ]; then
        linked_here=1
        shift
    fi
    program=$1
    for limit in "$release_glibc" "$release_glibcxx"; do
        if [ -n "$linked_here" ] && [ "${limit%_*}" = GLIBC ]; then
            need=$(release_newest_glibc_linked_here "$program" "${limit##*_}")
        else
            need=$(release_newest "$program" "${limit%_*}")
        fi
        if [ -n "$need" ] && [ "$(printf '%s\n' "$need" "${limit##*_}" | sort -V | tail -n 1)" != "${limit##*_}" ]; then
            die "${program##*/} needs ${limit%_*}_$need: the oldest distributions it is for have $limit"
        fi
    done
}

# release_needed FILE: the libraries FILE needs (DT_NEEDED), or for a kit.ini those on its "libraries =" line.
release_needed() {
    if [ "${1##*/}" = kit.ini ]; then
        local libraries
        libraries=$(sed -n 's/^libraries = //p' "$1")
        [ -n "$libraries" ] || die "kit.ini names no libraries"
        printf '%s\n' $libraries
    else
        readelf -d "$1" | sed -n 's/.*(NEEDED).*\[\(.*\)\]$/\1/p'
    fi
}

# release_check_libraries FILE KNOWN...: FILE needs no library but the KNOWN ones (those the distributions it is for
# have: a newer one of this system, such as OpenSSL 4's libcrypto.so.4, would stop it everywhere else).
release_check_libraries() {
    local program=$1 library libraries
    shift
    libraries=$(release_needed "$program") || exit
    for library in $libraries; do
        [[ " $* " == *" $library "* ]] ||
            die "${program##*/} needs $library, which the distributions it is for do not have (OpenSSL 3's is libcrypto.so.3)"
    done
}

# release_check_launcher_libraries FILE: the launcher needs nothing but the C and C++ runtimes' libraries: SDL is
# built into it, the display's libraries are opened when it starts (so it starts, and says what is missing, on any
# system: Ubuntu 24.04 has no SDL 3, SteamOS's is unknown).
release_check_launcher_libraries() {
    local program=$1 library libraries
    libraries=$(release_needed "$program") || exit
    for library in $libraries; do
        [[ " ${release_launcher_libraries[*]} " == *" $library "* ]] ||
            die "${program##*/} needs $library: the launcher may only need ${release_launcher_libraries[*]} (SDL is built into it, the display's libraries are opened when it starts)"
    done
}

# release_check_static_sdl BUILD_DIR: the build's launcher has SDL built in (TTT2_LAUNCHER_SDL=static), not the
# system's.
release_check_static_sdl() {
    grep -qx 'TTT2_LAUNCHER_SDL:STRING=static' "$1/CMakeCache.txt" &&
        grep -qx 'TTT2_LAUNCHER_SDL_MODE:INTERNAL=static' "$1/CMakeCache.txt" ||
        die "$1 does not build SDL into the launcher (TTT2_LAUNCHER_SDL=static; its source: python3 tools/setup_deps.py --launcher)"
}

# release_check_program [--launcher] FILE: every check above on one program.
release_check_program() {
    local launcher=
    if [ "$1" = --launcher ]; then
        launcher=1
        shift
    fi
    [ -f "$1" ] || die "$1 is not a file"
    release_check_isa_level "$1"
    release_check_avx512 "$1"
    release_check_versions "$1"
    if [ -n "$launcher" ]; then
        release_check_launcher_libraries "$1"
    else
        release_check_libraries "$1" "${release_launcher_libraries[@]}"
    fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    set -eu
    launcher=()
    if [ "${1:-}" = --launcher ]; then
        launcher=(--launcher)
        shift
    fi
    if [ $# -eq 0 ] || [ "$1" = -h ] || [ "$1" = --help ]; then
        echo "usage: $0 [--launcher] FILE..."
        [ $# -ne 0 ]
        exit $?
    fi
    for tool in readelf objdump; do
        command -v "$tool" >/dev/null || die "$tool is not installed"
    done
    for file in "$@"; do
        release_check_program ${launcher[@]+"${launcher[@]}"} "$file"
        echo "ok: $file"
    done
fi
