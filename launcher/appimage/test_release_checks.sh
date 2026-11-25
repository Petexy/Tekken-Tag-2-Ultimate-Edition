#!/bin/bash
# release_checks.sh's checks on small programs made here for each fault they look for (and on clean ones):
#
#   launcher/appimage/test_release_checks.sh CC CXX [GLIBC_FLOOR_HEADER]
#
# CC, CXX: the build's compilers. GLIBC_FLOOR_HEADER (cmake/GlibcFloor.cmake's): when given and this system's glibc
# is newer than the floor, a program calling atan2f must fail the check without it and pass with it.
set -u
here=$(cd "$(dirname "$0")" && pwd -P)
cc=$1
cxx=$2
floor_header=${3:-}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

# shellcheck source=release_checks.sh
. "$here/release_checks.sh"

# expect PASS|FAIL "words the message must have" COMMAND...: runs a check in a subshell (die exits it).
expect() {
    local want=$1 words=$2 said status
    shift 2
    said=$( ("$@") 2>&1 >/dev/null)
    status=$?
    if [ "$want" = PASS ] && [ $status -eq 0 ]; then
        echo "ok   $*"
    elif [ "$want" = FAIL ] && [ $status -ne 0 ] && [[ $said == *"$words"* ]]; then
        echo "ok   $* (refused: $said)"
    else
        echo "FAIL $*: wanted $want${words:+ ($words)}, got status $status: $said"
        failures=$((failures + 1))
    fi
}

# Programs linked without GNU ld's ISA level mark where possible (LLD writes none; see make_appimage.sh).
link=()
if command -v ld.lld >/dev/null; then link=(-fuse-ld=lld); fi
build() { # OUT SOURCE-SUFFIX COMPILER FLAGS... < SOURCE
    local out=$1 suffix=$2 compiler=$3
    shift 3
    cat >"$work/$out.$suffix"
    "$compiler" -O2 "$work/$out.$suffix" -o "$work/$out" "$@" || { echo "FAIL cannot build $out"; failures=$((failures + 1)); }
}

build clean c "$cc" "${link[@]}" <<'EOF'
#include <stdio.h>
int main(void) { puts("clean"); return 0; }
EOF
build clean_cxx cpp "$cxx" "${link[@]}" <<'EOF'
#include <string>
#include <vector>
#include <cstdio>
int main(int argc, char**) { std::vector<std::string> v(argc, "x"); std::printf("%zu\n", v.size()); }
EOF
expect PASS "" release_check_program --launcher "$work/clean"
expect PASS "" release_check_program --launcher "$work/clean_cxx"
expect PASS "" release_check_isa_level "$work"

# An ISA level mark (GNU ld's -z x86-64-v4).
if "$cc" -fuse-ld=bfd -Wl,-z,x86-64-v4 -x c - -o "$work/marked" <<<'int main(void) { return 0; }' 2>/dev/null; then
    expect FAIL "newer processor than any x86-64" release_check_isa_level "$work/marked"
    expect FAIL "./marked" release_check_isa_level "$work"
    rm -f "$work/marked"
else
    echo "skip ISA level mark (no GNU ld here)"
fi

# An AVX-512 instruction.
build avx512 c "$cc" "${link[@]}" <<'EOF'
int main(void) { __asm__ volatile("vpaddd %zmm0, %zmm1, %zmm2"); return 0; }
EOF
expect FAIL "AVX-512 instructions" release_check_avx512 "$work/avx512"
expect PASS "" release_check_avx512 "$work/clean_cxx"

# Versions above the limits (here: limits below what any program needs).
expect FAIL "needs GLIBC_" bash -c ". '$here/release_checks.sh'; release_glibc=GLIBC_2.1; release_check_versions '$work/clean'"
expect FAIL "needs GLIBCXX_" bash -c ". '$here/release_checks.sh'; release_glibcxx=GLIBCXX_3.4.1; release_check_versions '$work/clean_cxx'"
expect PASS "" release_check_versions "$work/clean_cxx"

# A function this glibc re-versioned (2.43: atan2f): needs the floor header.
newest_glibc=$(ldd --version 2>/dev/null | sed -n '1s/.* \([0-9][0-9.]*\)$/\1/p')
if [ -n "$floor_header" ] && [ -n "$newest_glibc" ] && \
    [ "$(printf '%s\n' "$newest_glibc" 2.42 | sort -V | tail -n 1)" = "$newest_glibc" ] && [ "$newest_glibc" != 2.42 ]; then
    source=$'#include <math.h>\n#include <stdlib.h>\nint main(int c, char** v) { (void)v; return (int)atan2f((float)c, (float)rand()); }'
    build unpinned c "$cc" "${link[@]}" -lm <<<"$source"
    build pinned c "$cc" "${link[@]}" -include "$floor_header" -lm <<<"$source"
    expect FAIL "needs GLIBC_2.4" release_check_versions "$work/unpinned"
    expect PASS "" release_check_versions "$work/pinned"
else
    echo "skip glibc floor header (no header, or this glibc ($newest_glibc) re-versions nothing above the floor)"
fi

# Libraries: the launcher's own rule, and the known list.
build zlib c "$cc" "${link[@]}" -Wl,--no-as-needed -lz <<'EOF'
#include <zlib.h>
int main(void) { return zlibVersion()[0] == 0; }
EOF
expect FAIL "the launcher may only need" release_check_launcher_libraries "$work/zlib"
expect PASS "" release_check_libraries "$work/zlib" libc.so.6 libz.so.1
expect FAIL "needs libz.so.1, which the distributions" release_check_libraries "$work/zlib" libc.so.6
printf 'version = 1\nlibraries = libc.so.6 libSDL3.so.0\n' >"$work/kit.ini"
expect PASS "" release_check_libraries "$work/kit.ini" libc.so.6 libSDL3.so.0
expect FAIL "needs libSDL3.so.0" release_check_libraries "$work/kit.ini" libc.so.6
printf 'version = 1\n' >"$work/kit.ini"
expect FAIL "kit.ini names no libraries" release_check_libraries "$work/kit.ini" libc.so.6

# The build's SDL.
mkdir -p "$work/build"
printf 'TTT2_LAUNCHER_SDL:STRING=static\nTTT2_LAUNCHER_SDL_MODE:INTERNAL=static\n' >"$work/build/CMakeCache.txt"
expect PASS "" release_check_static_sdl "$work/build"
printf 'TTT2_LAUNCHER_SDL:STRING=\nTTT2_LAUNCHER_SDL_MODE:INTERNAL=system\n' >"$work/build/CMakeCache.txt"
expect FAIL "TTT2_LAUNCHER_SDL=static" release_check_static_sdl "$work/build"

# The license texts: the repository's as a package has them, then each one missing, and one empty.
for file in "${release_license_files[@]}"; do
    mkdir -p "$(dirname "$work/licenses/$file")"
    cp "$here/../../$file" "$work/licenses/$file"
done
expect PASS "" release_check_licenses "$work/licenses"
for file in "${release_license_files[@]}"; do
    mv "$work/licenses/$file" "$work/license"
    expect FAIL "the license text $file is missing" release_check_licenses "$work/licenses"
    mv "$work/license" "$work/licenses/$file"
done
: >"$work/licenses/LICENSE"
expect FAIL "the license text LICENSE is missing (or empty)" release_check_licenses "$work/licenses"

# The command line.
expect PASS "" "$here/release_checks.sh" --launcher "$work/clean_cxx"
expect FAIL "the launcher may only need" "$here/release_checks.sh" --launcher "$work/zlib"

[ $failures -eq 0 ] && echo "all release checks behave" || echo "$failures failed"
[ $failures -eq 0 ]
