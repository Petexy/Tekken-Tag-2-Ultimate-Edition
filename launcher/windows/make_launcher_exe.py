#!/usr/bin/env python3
"""Makes the Windows release's launcher, as make_appimage.sh makes the Linux one.

    python3 launcher/windows/make_launcher_exe.py [--cmake-target TARGET [--build-dir DIR] | --stub EXE |
                                                   --cxx COMPILER] [--allow-dirty] OUTPUT

OUTPUT is the .exe to write (Ultimate_Launcher-x86_64.exe for a release). It is
the launcher's program for 64-bit Windows with this project's files in it:
Git's tracked files as they are in the working tree, batch files with Windows
line ends, as resource 100 (RCDATA; appended after the program for a --stub,
which is built already). Nothing of the game is in it: the game is built on the
player's PC from their own .wua. On the player's PC the .exe keeps the files in
%LOCALAPPDATA%\\TTT2Ultimate\\launcher and runs the launcher with them, and
that launcher updates the .exe from this repository's releases (its Python
workers: self_update.py). One made on a branch other than main is a test build:
its launcher updates its files from that branch's newer commits instead.

--cmake-target TARGET
                the program (the default: DEFAULT_CMAKE_TARGET below): a program
                of the new interface (ttt2_launcher_program), cross-built by
                CMake with MinGW-w64 (cmake/toolchain-mingw64.cmake), the
                launcher alone (TTT2_LAUNCHER_ONLY), SDL 3 built in (from
                third_party/SDL: python3 tools/setup_deps.py --launcher), the
                files as its resource 100, stripped, without a time stamp (the
                same commit makes the same bytes); in --build-dir DIR (else a
                temporary folder)
--stub EXE      else a program built already (build-windows-*/ttt2-launcher.exe), the files appended
--cxx COMPILER  else the Python launcher's .exe (entry.cpp, 0.4.0 to 0.8.0)
                compiled here with COMPILER (x86_64-w64-mingw32-g++) and its
                windres, which puts the files in it (with its icon and version
                details when rsvg-convert is there too)
--allow-dirty   pack the working tree as it is, with uncommitted changes and new
                files Git does not ignore (tests: a release is made from a commit)

The version is TTT2_LAUNCHER_VERSION in launcher/builder/CMakeLists.txt, the
AppImage's: a release is tagged v<version> with both attached.
"""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from self_update import BUILD_BRANCH, BUILD_COMMIT, MAGIC, TRAILER, is_launcher_exe, version  # noqa: E402

ICON = REPO / 'launcher/app/io.github.petexy.TekkenTag2UltimateEdition.svg'
# The release's program: the native launcher (launcher/app).
DEFAULT_CMAKE_TARGET = 'ttt2-launcher'
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def die(message):
    sys.exit('make_launcher_exe.py: ' + message)


def git(*args):
    result = subprocess.run(['git', '-C', str(REPO), *args], capture_output=True)
    if result.returncode:
        die('git %s failed: %s' % (args[0], result.stderr.decode('utf-8', 'replace').strip() or result.returncode))
    return result.stdout


def tracked(allow_dirty):
    """{path: bytes} of Git's tracked files, as they are in the working tree
    (with `allow_dirty`, also the new files it does not ignore)."""
    if not allow_dirty and git('status', '--porcelain', '--untracked-files=no').strip():
        die('the working tree has uncommitted changes: commit them, or pass --allow-dirty (tests only)')
    entries = [line.split(b'\t', 1) for line in git('ls-files', '-s', '-z').split(b'\0') if line]
    if allow_dirty:
        entries += [[b'100644', path] for path in git('ls-files', '-o', '--exclude-standard', '-z').split(b'\0') if path]
    files = {}
    for info, path in entries:
        mode, path = info.split()[0], path.decode('utf-8')
        if mode not in (b'100644', b'100755'): die(path + ' is not a plain file (a link or a submodule)')
        file = REPO / path
        if not file.is_file():
            if allow_dirty: continue
            die(path + ' is missing from the working tree')
        data = file.read_bytes()
        # cmd.exe can miss a batch file's labels when its lines end in LF only.
        if path.lower().endswith(('.cmd', '.bat')): data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        files[path] = data
    return files


def payload(files):
    """entry.cpp's files as it reads them: each file's path and bytes, then their trailer."""
    out = bytearray()
    for path in sorted(files):
        name = path.encode('utf-8')
        out += struct.pack('<I', len(name)) + name + struct.pack('<Q', len(files[path])) + files[path]
    return bytes(out) + TRAILER.pack(len(out), len(files), hashlib.sha256(out).digest(), MAGIC)


def ico(pngs):
    """An .ico of PNG images (each {size: bytes})."""
    head = struct.pack('<HHH', 0, 1, len(pngs))
    offset, entries, data = 6 + 16 * len(pngs), b'', b''
    for size, png in sorted(pngs.items()):
        entries += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return head + entries + data


def make_icon(out, rsvg):
    """The launcher's icon (ICON drawn at each of ICON_SIZES by rsvg-convert) as the .ico `out`."""
    with tempfile.TemporaryDirectory(prefix='ttt2-launcher-icon-') as temporary:
        pngs = {}
        for size in ICON_SIZES:
            png = Path(temporary) / ('icon-%d.png' % size)
            subprocess.run([rsvg, '-w', str(size), '-h', str(size), '-o', str(png), str(ICON)], check=True)
            pngs[size] = png.read_bytes()
    Path(out).write_bytes(ico(pngs))


# The resource that holds the files (entry.cpp's kFilesResource): an ordinary
# part of a program, which virus scanners' guesses take less for a dropper's
# payload than data appended after it.
FILES_RESOURCE = 100


def resource(cxx, windres, number, work, files):
    """The files (resource FILES_RESOURCE), the manifest, version details and,
    when rsvg-convert is there, the icon, as an object file to link."""
    rsvg = shutil.which('rsvg-convert')
    windres = windres or shutil.which(cxx.rsplit('-', 1)[0] + '-windres') or shutil.which('windres') or shutil.which('llvm-windres')
    if not windres: die('windres is not installed (MinGW-w64\'s binutils): it puts the files in the .exe')
    (work / 'files.bin').write_bytes(files)
    icon = ''
    if rsvg:
        make_icon(work / 'launcher.ico', rsvg)
        icon = '1 ICON "launcher.ico"\n'
    else:
        print('make_launcher_exe.py: no icon: needs rsvg-convert', file=sys.stderr)
    (work / 'launcher.manifest').write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges>
    <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
  </requestedPrivileges></security></trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1"><application>
    <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
  </application></compatibility>
</assembly>
''', encoding='utf-8')
    numbers = ','.join((number.split('.') + ['0'] * 4)[:4])
    (work / 'launcher.rc').write_text(icon + '''%(files)d RCDATA "files.bin"
1 24 "launcher.manifest"
1 VERSIONINFO
FILEVERSION %(numbers)s
PRODUCTVERSION %(numbers)s
FILEOS 0x40004
FILETYPE 0x1
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904B0"
    BEGIN
      VALUE "FileDescription", "Ultimate Launcher"
      VALUE "FileVersion", "%(version)s"
      VALUE "InternalName", "ttt2-launcher"
      VALUE "OriginalFilename", "Ultimate_Launcher-x86_64.exe"
      VALUE "ProductName", "Tekken Tag 2 Ultimate Edition"
      VALUE "ProductVersion", "%(version)s"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
''' % dict(numbers=numbers, version=number, files=FILES_RESOURCE), encoding='utf-8')
    subprocess.run([windres, '-O', 'coff', '-i', 'launcher.rc', '-o', 'launcher.res.o'], cwd=work, check=True)
    return work / 'launcher.res.o'


def compile_launcher(cxx, windres, number, work, files):
    """entry.cpp compiled with the files in it."""
    if not shutil.which(cxx): die(cxx + ' is not installed (MinGW-w64, or pass --cxx or --stub)')
    out = work / 'launcher.exe'
    core = HERE.parent / 'core'  # (its files as launcher/core reads them: payload.h)
    subprocess.run([cxx, '-std=c++20', '-O2', '-municode', '-mwindows', '-static', '-s',
                    '-DTTT2_LAUNCHER_VERSION="%s"' % number, '-I', str(core), str(HERE / 'entry.cpp'),
                    *(str(core / name) for name in ('payload.cpp', 'sha256.cpp', 'win32.cpp')),
                    str(resource(cxx, windres, number, work, files)),
                    '-o', str(out), '-ladvapi32', '-lshell32'], check=True)
    return out.read_bytes()


def cmake_build(target, build_dir, work, files):
    """TARGET, a launcher program of launcher/ui (ttt2_launcher_program), built by CMake for 64-bit Windows with the
    files in it: the launcher alone (TTT2_LAUNCHER_ONLY), SDL built in (TTT2_LAUNCHER_SDL=static), stripped, its
    paths relative to the project as make_appimage.sh's (the same .exe from the same commit anywhere)."""
    for tool in ('cmake', 'ninja'):
        if not shutil.which(tool): die(tool + ' is not installed')
    if not (REPO / 'third_party/SDL/CMakeLists.txt').is_file():
        die("SDL's source is missing: python3 tools/setup_deps.py --launcher")
    build = Path(build_dir).resolve() if build_dir else work / 'build'
    build.mkdir(parents=True, exist_ok=True)
    # (in the build folder, which a kept one then builds again as it was)
    payload_file, icon = build / 'release-files.bin', build / 'release-icon.ico'
    payload_file.write_bytes(files)
    rsvg = shutil.which('rsvg-convert')
    if rsvg:
        make_icon(icon, rsvg)
    else:
        print('make_launcher_exe.py: no icon: needs rsvg-convert', file=sys.stderr)
    prefix_maps = '-ffile-prefix-map=%s/= -ffile-prefix-map=%s/=' % (REPO, build)
    subprocess.run(['cmake', '-S', str(REPO), '-B', str(build), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_TOOLCHAIN_FILE=' + str(REPO / 'cmake/toolchain-mingw64.cmake'),
                    '-DTTT2_LAUNCHER_ONLY=ON', '-DTTT2_LAUNCHER_SDL=static',
                    '-DTTT2_LAUNCHER_PAYLOAD=' + payload_file.as_posix(),
                    '-DTTT2_LAUNCHER_ICON=' + (icon.as_posix() if rsvg else ''),
                    '-DCMAKE_C_FLAGS=' + prefix_maps, '-DCMAKE_CXX_FLAGS=' + prefix_maps,
                    '-DCMAKE_EXE_LINKER_FLAGS=-s'], check=True)
    cache = (build / 'CMakeCache.txt').read_text(encoding='utf-8', errors='replace')
    if 'TTT2_LAUNCHER_SDL_MODE:INTERNAL=static' not in cache.splitlines():
        die('the build does not have SDL built in (TTT2_LAUNCHER_SDL=static)')
    subprocess.run(['cmake', '--build', str(build), '--target', target], check=True)
    program = build / 'launcher' / (target + '.exe')
    if not program.is_file(): die('%s did not make %s (not a launcher/ui program?)' % (target, program))
    return program.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('output', type=Path)
    which = parser.add_mutually_exclusive_group()
    which.add_argument('--stub', type=Path)
    which.add_argument('--cxx')
    which.add_argument('--cmake-target')
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--windres')
    parser.add_argument('--allow-dirty', action='store_true')
    args = parser.parse_args()
    if args.build_dir and (args.stub or args.cxx): parser.error('--build-dir is for --cmake-target')
    if args.windres and not args.cxx: parser.error('--windres is for --cxx')
    number = version(REPO)
    output = args.output.resolve()
    if not output.parent.is_dir(): die('%s is not a folder' % output.parent)
    files = tracked(args.allow_dirty)
    # (Its build's commit: the launcher asks GitHub what main has beyond it, self_update.build_commit.
    # Its branch: one other than main makes it a test build, whose files follow that branch, update_files.)
    files[BUILD_COMMIT] = git('rev-parse', 'HEAD').strip() + b'\n'
    branch = git('rev-parse', '--abbrev-ref', 'HEAD').strip()
    if branch != b'HEAD': files[BUILD_BRANCH] = branch + b'\n'
    for needed in ('launcher/windows/main.py', 'Start Ultimate Launcher.cmd', 'launcher/builder/CMakeLists.txt'):
        if needed not in files: die('the project lacks ' + needed)
    with tempfile.TemporaryDirectory(prefix='ttt2-launcher-exe-') as temporary:
        if args.stub:
            program = args.stub.read_bytes()
            if program[:2] != b'MZ': die('%s is not a Windows program' % args.stub)
            if program[-TRAILER.size:][-len(MAGIC):] == MAGIC:
                die('%s already holds files: give the launcher as built' % args.stub)
            program += payload(files)
        elif args.cxx:
            program = compile_launcher(args.cxx, args.windres, number, Path(temporary), payload(files))
        else:
            program = cmake_build(args.cmake_target or DEFAULT_CMAKE_TARGET, args.build_dir, Path(temporary),
                                  payload(files))
        part = output.with_name(output.name + '.part')
        part.write_bytes(program)
    if not is_launcher_exe(part):
        part.unlink(); die('the .exe made is not a 64-bit Windows launcher')
    os.replace(part, output)
    print('Made %s: Ultimate Launcher %s, %d files (%.1f MB)'
          % (output, number, len(files), output.stat().st_size / 1e6))


if __name__ == '__main__':
    main()
