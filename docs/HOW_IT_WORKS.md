# How it works

A short tour of the port: how the Wii U game becomes a PC program, where each part lives in the source tree, and
how to change what the game does. The full design notes, measurements and milestones are in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Contents

- [Static recompilation](#static-recompilation)
- [The source tree](#the-source-tree)
- [Changing the game](#changing-the-game)

## Static recompilation

Golden Fist Launcher (called Ultimate Launcher up to 0.8.0) installs, updates
and starts an unofficial native Linux (and Windows) port of **Tekken Tag Tournament 2 Wii U
Edition**, and adds Tekken 7's and Tekken 8's fighters to it. The port is made
by static recompilation: the game's PowerPC code is translated to C++
ahead of time and runs as native x86-64 code on a reimplementation of the
Wii U's system libraries. There is no CPU emulation; the game's GPU commands
and shaders are translated to Vulkan as it runs.

The game program is **made to be modified**: every function of the game is a C++ function that
can be replaced ([see below](#changing-the-game)).

## The source tree

- `recomp/`: `cafe-recomp` loads the RPX, finds all 205,200 function entry
  points and writes the 79,564 reachable ones as C++ functions (`--all`
  writes every one). Guest calls are C++ calls; indirect calls go through an
  address table.
- `runtime/src/os/`: the Cafe OS libraries the game imports (threads,
  synchronisation, memory, file system, saves, input, sound mixing), written
  natively.
- `runtime/src/gx2/` and `runtime/src/gpu/`: GX2 writes real GPU command
  buffers, which a command processor executes; the Vulkan renderer
  (`runtime/src/gpu/vulkan/`) translates the GPU's shaders to SPIR-V
  (`runtime/src/latte/`), interpolates frames and paces presentation.
- `runtime/src/title/`: what this game shows differently on a computer: the
  menu buttons, the icon sets, texts and the title screen, made at start-up
  from the game's archives (their format is described in
  [`docs/ARCHITECTURE.md`](ARCHITECTURE.md#presentation-on-a-computer)),
  and the added fighters from their character packs.
- `tools/characters/`: the importer that makes a character pack from the
  player's own Tekken 7 or Tekken 8 and Tekken Tag Tournament 2
  ([`docs/ARCHITECTURE.md`](ARCHITECTURE.md#added-fighters); how to use it:
  [Adding fighters](ADDING_FIGHTERS.md)).
- `launcher/`: Golden Fist Launcher ([what it does](LAUNCHER.md)).
- `tests/`: a memory-model test, tests of reading split archives and of the
  game's file formats and the icons and texts made from them, and
  differential tests that run every instruction form the game uses against
  Dolphin's PowerPC interpreter ([running them](BUILDING.md#tests)).

## Changing the game

A generated function `sub_<address>` can be replaced by defining it in a
`.cpp` file added to the `ttt2` target (`target_sources(ttt2 PRIVATE ...)` in
`CMakeLists.txt`); every call, direct or through a function pointer, then
reaches the replacement, and `sub_<address>_orig` is still the original:

```cpp
#include "cafe/ppc_ops.h"

PPC_FUNC(sub_0123ABCD_orig);
PPC_FUNC(sub_0123ABCD) {
    // ... before
    sub_0123ABCD_orig(ctx, base);
    // ... after
}
```

To build the game program with your change: [Building from source](BUILDING.md#building-the-game-program).
