# Standalone port architecture

Goal: a native Linux x86-64 Tekken Tag Tournament 2 (Wii U, EU v16) that runs
**without CPU emulation, without Cemu**, and whose code can be freely modified
afterwards. Decided 2026-10-01.

```
Tekken.rpx ──► cafe-recomp ──► generated/*.cpp  (one C++ function per guest function)
                                      │
                 runtime/ (native Cafe OS: coreinit, gx2→Vulkan, snd, vpad, fs)
                                      │
                 PPC_FUNC(sub_...) overrides of guest functions ──► ttt2 (ELF x86-64)
```

## Why our own recompiler

nWiiURecomp lifts *basic blocks* that return to a dispatch loop with an
instruction budget and an interpreter fallback: an accelerated emulator, built
for hosting inside Cemu. A port wants *function-level* output (the
XenonRecomp / N64Recomp model): `bl` is a C++ call, `blr` a return, every guest
function a named, overridable C++ function. (nWiiURecomp was evaluated first
and is not used.)

## Facts the design rests on

Measured on the v16 RPX with `build/recomp/cafe-census`:

| Fact | Consequence |
| --- | --- |
| `.symtab` holds 205,140 sized `STT_FUNC` symbols that partition `.text` exactly (0 overlaps, 5 gaps); names are stripped | Function boundaries are given, not guessed |
| 29,769,084 instructions, **0 undecodable words** in any function | No data islands inside code |
| 190 instruction variants, standard Espresso set incl. paired singles; no `sc` | All OS access is through the 508 imports |
| Game writes GQR5 (`mtspr 901`) | Quantized `psq_l/psq_st` need real GQR state |
| 470,080 `bctrl`, 8,775 `bctr`; 106,292 relocations take function addresses | Indirect calls go through a guest-address → host-function table |
| Switches are `lis/addi; mtctr; bctr` into an in-function table of `b`s (222 functions) | `bctr` with known in-function targets becomes `switch` + `goto` |
| ~1,000 branches enter the save/restore-register helpers at `0x0913D06C..0x0913D3F4` mid-sequence | Branch targets inside another function become alternate entry functions |
| Entry calls an undefined weak symbol (address 0) behind a guard | Null calls trap with a diagnostic |
| Only 79,507 functions / 6.0M instructions (20.3%) are reachable from the entry point and address-taken functions | Compile the reachable set optimised; the rest cheaply, logging if ever called |

Every stored code address in an RPL carries a relocation, which is what makes
the reachability bound sound.

## Generated code conventions

- Guest state: `PPCContext` (r0–r31, f0–f31 as paired doubles, CR as eight
  fields, LR, CTR, XER, FPSCR, GQR0–7, reservation).
- Guest memory: one 4 GiB host reservation; guest address `a` is `base + a`.
  Data stays big-endian; loads/stores byte-swap.
- Every guest load and store is a volatile access (`ppc_ops.h`): guest memory
  is shared between guest threads, so the compiler must perform each access
  in program order. With plain loads clang compiled a guest spin-wait
  (`lwz; cmpwi; bne` to itself) into a single read and the game's worker
  handshake broke. `build/tests/memory_model_test` guards this.
- Each function: `void sub_XXXXXXXX(PPCContext& ctx, uint8_t* base)`, emitted
  as a weak alias of `sub_XXXXXXXX_orig`, so user code can replace any function
  by defining it, and still call the original.
- Imports: calls to stub addresses become calls to
  `cafe_import_<module>_<name>`. The runtime defines the implemented ones;
  generated weak defaults stop with "unimplemented import" for the rest.
- Planned: a names file mapping addresses to readable names as they are
  identified.

## Runtime (native Cafe OS)

Implemented in host C++, no guest-code interpretation:

1. **coreinit**: heaps, threads (guest thread = host thread), mutex /
   condition / semaphore / event / alarm / message queue, time, OSDynLoad,
   filesystem mapped onto the extracted content directory, save directory
   under `~/.local/share/ttt2/`.
2. **gx2 → GPU** (see below): GX2 implemented natively, writing PM4 command
   buffers that a command processor executes against a Latte register file
   and hands to a rendering backend: Vulkan, or null for headless runs.
   Latte shaders the game ships are translated to GLSL and compiled to
   SPIR-V at run time; tiled surfaces are detiled.
3. **snd_core / snd_user → host audio**: AX voices mixed natively and
   played through SDL3 (see the audio section below).
4. **vpad / padscore → SDL3 gamepads and the keyboard**: the GamePad, and
   up to four Pro Controllers for other players (below, *Players*).
5. **nsysnet / nlibcurl / nn_\***: offline stubs.

Cemu and decaf-emu were references for the system's and the GPU's behaviour,
and Dolphin's interpreter is the instruction tests' oracle; no code from them
is in this repository. Facts such as structure layouts, register values and
the processor's estimate tables come from their reverse engineering and
hardware measurements.

Guest threads are host threads; every kernel object is examined and changed
under one kernel lock. A blocked thread sleeps on a *wait channel* keyed by
the object it waits for (a mutex, condition, semaphore, event, message
queue, thread queue or thread, by guest address; or the interrupt lock,
display, GPU, alarm schedule), and waking an object notifies only its
channel. With one shared condition variable every mutex unlock and every
OSRestoreInterrupts woke all ~40 of the title's blocked threads: the title's
allocator locks a mutex per allocation, and the boot-time loading screen
took ~17 s of herd wake-ups for 0.9 s of work (now ~1 s; CPU use fell from
~5 cores to a quarter of one).

System libraries the title loads with OSDynLoad are implemented the same
way: `swkbd` (software keyboard) and `erreula` (error viewer) have no UI
yet, so a request for text is confirmed with the title's own initial text
and an error is printed and acknowledged. An OSDynLoad export the runtime
lacks still gets an address; calling it stops with its name.

### GX2 and the GPU

```
GX2 (runtime/src/gx2/) ──PM4──► command buffers in guest memory
                                     │ GX2Flush / display lists
                                     ▼
command processor thread (runtime/src/gpu/) ── Latte register file
   draws, clears, copies, swaps ──► Backend (Vulkan; null when headless)
   timestamps, GPU-written memory, swap/flip counts ──► guest
```

- GX2 writes real PM4 packets, big-endian, into the command buffer pool
  GX2Init receives, used as a ring, or into display lists. Context states
  work as on hardware: register writes are shadowed into the
  GX2ContextState while it is current and loaded back with LOAD_* packets.
  Operations the console performs with GX2-internal shaders (clears,
  surface copies, resolves, scan-buffer copies, swaps) are runtime-defined
  packets (opcodes 0x01-0x08) carrying the GX2 structures the title passed.
- Addresses in command buffers are guest virtual addresses; the title never
  translates addresses itself.
- Surface layouts (size, alignment, pitch, mip offsets, tile mode) come from
  AMD's address library in its R600 variant (MIT, pinned in
  `dependencies.lock.json`, `third_party/addrlib`), with the console's
  parameters, because the title allocates from them and ships pre-tiled
  textures laid out by them.
- Fetch shaders are generated as real Latte microcode (little-endian, the
  GPU's order), so the shader translator reads vertex layouts from one
  format whether GX2 or the title produced them.
- The display flips frames at 59.94 Hz, honouring the swap interval;
  GX2GetSwapStatus reports what the title paces its loop on.
- GX2CopySurface with an unaligned linear (LINEAR_SPECIAL) surface on
  either side is a synchronous CPU copy, as on the console: the title
  copies each texture out of one staging buffer and reuses the buffer at
  once. Other copies go to the GPU in order.
- GX2Invalidate's CPU flag (and DMA engine transfers) tell the renderer the
  CPU wrote memory (`gpu::cpu_wrote`); SURFACE_SYNC packets are GPU cache
  operations only. The title flushes the whole texture cache several times
  a frame, which says nothing about what changed.
- A texture over a render target of a different format with the same
  element size is copied from it, reinterpreted: the title compresses
  textures on the GPU by rendering each 4x4 block as one texel (BC1 over
  R16G16B16A16, BC3 over R32G32B32A32_UINT) and samples the memory as BC1
  or BC3, every mip level from its own target.
- The title never uses multisampled render targets and never issues a
  stream-out "draw opaque" (it does not import GX2DrawStreamOut); neither
  is implemented.

### Audio

Every 3 ms AX frame (`runtime/src/os/ax.cpp`) mixes each playing voice,
runs the title's frame callbacks, passes each device's output through the
device final-mix callbacks (48 kHz planar 32-bit buffers in 16-bit range:
TV 6 channels, GamePad 4 x 2) and plays the TV's channels 0-1 as stereo
(`runtime/src/host/audio.cpp`, SDL3). A voice reads PCM16, PCM8 or
DSP-ADPCM from guest memory at its 16.16 rate ratio (relative to AX's
32 kHz renderer), linearly interpolated, scaled by its volume envelope and
mixed into each device channel by its device mix; volumes ramp by their
per-sample deltas. Frames are steady 3 ms ticks, as on the console: the
title's sound engine fills its voices from its own threads, and frames run
in bursts at the device's demand read audio it has not written yet (that
silenced half of the output after the intro). With a device the tick is
nudged by at most 0.5% to keep ~2048 frames queued, following the device's
clock (in practice by a few hundredths of a percent); if the queue runs dry
(start-up, a stall) silence refills it at once.

The title's CRI ADX2 middleware decodes and mixes in software and outputs
5.1 at 44.1 kHz through six looping PCM16 voices of 2,880 samples; their
device mixes fold them to TV stereo, and their volume envelopes come from
the MIX library (`snd_user.cpp`: input levels in 0.1 dB, ramped over one
frame). No voice sends to the aux (effect) buses, so AXFX effects are
never run; filters are accepted and not applied.

### Latte shaders

`runtime/src/latte/` decodes Latte microcode (control flow, ALU groups,
texture and vertex fetches, subroutines) and translates it to GLSL
(`translate.cpp`). Each invocation runs as one thread of the console GPU:
GPRs are integer `ivec4`s that float instructions bit-cast, an ALU group
reads every operand before it writes, PV/PS carry the previous group's
results, and DX9-style `MUL`/`MULADD`/`DOT4` treat 0 × anything as 0. The
per-thread active mask and push/pop stack are variables, so every clause
is guarded and the jumps that only skip inactive threads are dropped;
DX10 loops become `while` loops with `break`. Relative register addressing
(`R[base + AR]`, used by loops over register arrays such as the main
menu's depth-of-field blur) goes through `rel_load`/`rel_store`, which
switch over the program's registers (`SQ_PGM_RESOURCES.NUM_GPRS`) so the
register file is only ever indexed by constants: indexing it directly
made the driver keep all 128 registers in scratch memory, and that one
blur took 16.5 ms a pass at 1440p (now 0.07 ms; every shader the title
uses through a match compiles with no scratch memory, checked with
`RADV_DEBUG=shaderstats`). What the microcode does not
decide (vertex semantics, the VS→PS parameter linkage, texture types,
render target number types, alpha test, point sprites, stream-out) comes
from the register file (`environment.cpp`) and is part of the shader key.
The fetch shader is inlined at `CALL_FS`.

Shaders read guest memory directly through buffer device addresses
(`shader_abi.h`): vertex buffers (decoded and endian-swapped in the
shader), uniform blocks (raw little-endian, as the title stores them) and
buffer fetches; stream-out (`MEM_STREAM`) writes guest memory the same
way. `cafe-shader translate <dump dir>` translates and compiles every
draw recorded with `TTT2_DUMP_SHADERS`.

### Vulkan renderer

`runtime/src/gpu/vulkan/`: Vulkan 1.3 with dynamic rendering, push
descriptors and extended dynamic state; one pipeline per shader pair,
attachment formats and blend state.

- Guest memory (MEM2, MEM1) is imported with VK_EXT_external_memory_host,
  so the GPU reads the title's buffers in place. Stream-out writes it
  from vertex shaders (skinned fighters, text); the first draw after a run
  of stream-out draws ends the rendering pass for a barrier, which a pass
  cannot hold, so the draws reading the output see all of it.
- Guest memory is system memory, which a discrete GPU reads over the bus,
  4 bytes at a time (uncached on some: NVIDIA documents pinned host memory
  so). On RADV a fight frame takes about 3.3 ms at any resolution; slower
  links or uncached reads multiply what skinning costs: per vertex about
  112 dword reads of bone matrices, 28 of vertex data and 20 stores, and
  16-20 reads for each draw of the skinned vertex (issues #45, #48). So on
  a discrete GPU (`shadows.cpp`) the stream-out buffers of 1 MiB or more
  in use (the title's four skinning buffers, which it writes about every
  other frame) get copies in video memory, made at a swap. A stream-out
  draw that writes every byte of its vertices (the translator's
  `stream_out_complete`: each dword of the stride at the top level of the
  main program; not indexed, one instance) writes the copy, and its range
  goes back to guest memory with a `vkCmdCopyBuffer` at the barrier after
  the run (finished by the next barrier, and before the submission
  retires: the CPU and anything reading in place see the same bytes as
  before). A vertex buffer reads the copy only when every byte the draw
  can fetch (the index range, base vertex and stride, plus the
  translator's `vb_extent`: what the fetch shader, called first and
  indexed by the vertex index, reads past a vertex's start) was written
  there in the last 4 frames (skinning reads each vertex's state from a
  buffer it wrote 1-3 frames before) and 250 ms, and not since announced as
  written by the CPU (`cpu_wrote`) or a render target's write-back, nor
  overwritten by stream-out in place; anything else reads guest memory. A
  draw using guest memory under a copy back not yet finished gets a
  barrier first. The stream-out draws writing video memory read their
  buffer resources and uniform blocks (bone palettes) from copies the CPU
  writes into host-visible video memory as the draw is built (as
  interpolation's records do). Replays (120 fps) still run each skinning
  draw, which then reads its inputs (bone palettes, vertex data) in place:
  leaving the stream-out draws that draw nothing out of replays removes
  that.
  The 10 s statistics add a `video memory:` line (copies, reads from video
  and guest memory and why, replays' reads included, constants copied,
  vertex data the skinning still reads in place).
  `TTT2_SHADOWS=0` reads everything in place; `TTT2_SHADOW_CHECK=1`
  compares every copy with guest memory once each frame finished, and `=2`
  also draws each such stream-out draw the old way into guest memory
  (without copies back), comparing both paths' output.
- Submission is asynchronous: command buffers (8 in turn) and upload
  memory (8 chunks of a 256 MiB host buffer) are tracked on a timeline
  semaphore and reused once the GPU has finished with them. The command
  processor never waits; a retirement thread performs what the guest can
  observe (retired timestamps, end-of-pipe memory writes, finished
  frames) in command order once the GPU work before it has finished, so
  buffers the guest reuses after a wait are no longer read.
- Render targets and depth buffers are GPU images keyed by address,
  format and size (the title aliases memory between differently sized
  targets). A texture is an image per resource: copied from a render
  target at its address if the GPU wrote that last, otherwise detiled from
  guest memory and reloaded when the CPU writes it and its hash changes.
  Depth buffers sampled as textures are copied through a buffer. A slot a
  shader samples with nothing bound reads zeros (a 1x1 image), as on the
  GPU: Fallen Garden's and Heaven Garden's water draws have one, and
  skipping them left those stages without water.
- Write-back: the title reads some render targets with the CPU, as the
  console's GPU renders into guest memory. Its exposure averages the scene
  down to one element of a 64x64 target and reads it two frames later
  (three targets in turn); with nothing there it read black and turned the
  exposure up, which washed stages out (Odeum of Illusions: a white floor,
  white spotlights). Small colour targets at the title's size (up to
  64 KiB, stored as in guest memory) are copied to staging memory at the
  end of each submission that wrote them (before a frame's replays) and
  tiled into guest memory by the retirement thread once it finished,
  before the CPU can see that it has. The staging memory is CPU-cached
  where the driver has such memory: read element by element from
  write-combined memory, the tiling kept that thread ~12% busy.
- Detiling (`gpu/tiling.cpp`) uses addrlib once per 8×8 micro tile: in
  thin single-sample modes every micro tile has the same internal layout
  (verified against per-element addrlib, `TTT2_CHECK_TILING=1`).
- The TV scan buffer is blitted, letterboxed, to an SDL3 window
  (`runtime/src/host/window.cpp`, on the process's main thread).
- Upscaling: targets the size of the screen and its halvings (heights 720,
  368, 192, 96) get images 1, 1.5, 2, 3 or 4 times larger (display.ini's
  resolution or `TTT2_SCALE`, else enough to cover the display, 2 on 1080p
  and 1440p, 3 on 4K). Shadow maps, the GPU's texture-compression targets
  and the GamePad screen keep the title's size. Passes into upscaled
  targets scale the viewport, scissor and point size; pixel shaders see
  `gl_FragCoord` in the title's pixels; textures copied from upscaled
  targets stay upscaled, and shaders scale texel coordinates, size queries
  and texel offsets for them (`DrawConstants` carries the scale and a
  per-stage mask). Copies between images of different scale are filtered
  blits. At 1.5 a title pixel covers one or two image pixels: sizes round
  up (`scaled()`; an odd size ends in half a pixel), a mip level's copy is
  clamped to the image's level (whose sizes halve the rounded one), a
  scissor edge e becomes ceil(1.5e − 0.5) (the pixels whose centres it
  covers), a texel fetch reads image texel floor(1.5c + 0.5), and a size
  query gives level 0's size divided by 1.5, rounded, then halved to the
  level. At the whole scales each of these is the exact product (or
  quotient).
- Validated 2026-10-02 with the Khronos layer (core, synchronization,
  object lifetime, thread safety) through boot, menus and a match: no
  errors or hazards. One warning remains by design,
  Undefined-Value-ShaderOutputNotConsumed: some depth-only passes use pixel
  shaders that also write colour, which Vulkan discards when no colour
  attachment is bound; trimming those outputs would multiply shader
  variants.
- Frame interpolation (`gpu/vulkan/interpolate.cpp`, default when the
  primary display or the window's refreshes at 100 Hz or more, exactly
  (`display::kInterpolationHz`: 99.98 Hz gets 60), unless display.ini says
  `interpolation = no`, fixed for a run; `TTT2_FPS=60/120/180/240` over
  both): the title's logic, physics
  and hitboxes stay at 59.94 steps a second; between two of its frames the
  renderer shows K-1 more. The command processor logs each frame (register
  writes and operations with their arguments, nothing the guest can
  observe) and replays it after the swap; every draw's constant data
  (uniform blocks, buffer resources: camera, transforms, the characters'
  bone matrices, fetched by the vertex shaders) is copied into a
  GPU-visible record that the real draw reads too, and a replay blends it
  with the previous frame's matching draw, value by value where both are
  ordinary floats, except values that are small whole numbers (up to 4096)
  or 64ths (up to 64) in both frames: indices kept as floats and
  sprite-sheet cells step to this frame's value (blending the school stage
  crowd's flipbook cell drew the halves of neighbouring cells: legs above,
  bodies sunk into the ground; Norway's fire drew blobs in the sky). The
  limits matter: floats in the tens of thousands are coarse enough that
  moving values land on 64ths every few frames, and on infinite stages the
  camera's matrix holds such values, changing by hundreds a frame when it
  turns; stepping one of them while the rest moved threw the scene off
  screen in extra frames (black frames with only the HUD and hit sparks,
  the sky half black). Draws match by key (shaders,
  targets, vertex count and first texture): first those whose data did not
  change, then by how far their floats moved in all (integers and flags
  that changed count first), near their place among those with their key,
  and only draws that are each other's nearest pair, nearest pairs first.
  Things sharing a key come and go: a blinking cursor once paired every
  later menu sprite with its neighbour, and the Netherlands stage's tulip
  field (patches of one mesh, a world matrix each) gains and loses patches
  as the camera swings round; a new patch paired with the most similar
  other one was drawn halfway between the two, and each patch down the line
  then took its neighbour's partner (counting changes "large" by a quarter
  of their size could not tell a patch 3750 units away from a sway value
  crossing zero). A draw left without a partner is drawn where its frame
  has it, its blocks shared with paired draws (the camera's) blended as
  theirs are. Only depth-tested (3D) draws blend: menus and the HUD
  place parts of a widget with vertex data the CPU writes each frame, which
  a replay cannot blend, so they are shown as the frame has them
  (`TTT2_INTERP_2D=1` blends them too). Draws whose data mostly jumps (a
  different object, a cut) and frames where fewer than 80% of draws match
  are shown as they are. Replays skip anything that writes guest memory
  (stream-out writes, CPU-side surface copies); render targets a frame
  reads before writing them start replays from their start-of-frame
  content, and the next frame sees the real frame's. With unblended replays
  (`TTT2_INTERP_TEST=1`) every extra frame equals its real frame pixel for
  pixel (checked through menus, character select and fights). Particles
  whose geometry the CPU rebuilds each frame and the HUD move at 60 Hz, and
  so do models skinned through stream-out: in fights the fighters are
  (point draws that write their skinned vertices), so their extra frames
  show the real frame's pose. A frame whose swap comes while the GPU has
  yet to finish the previous frame's images gets no extra frames (the
  previous image stays up through their part of its slot): the title learns
  a frame is done only after its replays, so on a shared or overloaded GPU
  they would slow the game itself (measured: a fight on a desktop
  compositor taking ~80% of the GPU went from 46-51 to 55-60 title frames a
  second; the statistics line counts the extra frames skipped). Nor does
  one while the command processor has no time for them: it renders them
  too, on its one CPU thread, so a slower CPU kept it busy all the time and
  the game slowed down (issue #15; a fight with 16 µs more per draw, as a
  slower CPU: 46 title frames a second, now 59-60 with the extra frames
  left out of heavy scenes only). It goes by averages over 16 frames of its
  time without commands and of the replays' time per second of the frame's
  own work (which holds when a scene changes), keeping them while a
  millisecond would be left and taking them up again at three; the
  statistics line shows how busy it is.
- Presentation (`gpu/vulkan/present.cpp`) runs on its own thread and on a
  compute queue (AMD's asynchronous compute, `TTT2_PRESENT_BLIT=1` for
  the rendering queue): a present there waits only for its own frame, not
  for rendering queued after it. A compute shader scales the frame,
  letterboxed, into the swapchain; a swapchain within 2 pixels of the
  frame's size gets it 1:1, centred (a window sized for the render size
  can come out a pixel short under fractional desktop scaling, and a
  0.999 scale would blur the whole frame). The mode follows the display
  the window is on, chosen again when the window moves to another display or
  its mode changes. On a display refreshing at a multiple of 60 Hz of at
  least 120 Hz with present waits (`VK_KHR_present_wait2`), the thread
  presents at every refresh in FIFO order, a few presents ahead of the
  screen (about 8 ms: 3 at 240 Hz, 2 at 120 Hz; KWin latches a commit
  about two refreshes before showing it, and tells late that it did), and
  counts refreshes one per present reaching the screen, plus, by time
  since the last present it waited for, any refresh the screen showed
  twice (once the next present confirms it: a single late wake-up is not
  one), part refreshes carried over (a display slower than reported by
  other than a whole factor) and, when it fell behind or the compositor
  stalled, the time that passed. Every 60th of a second of them is the title's vertical blank
  (`gpu::host_vsync`; the 59.94 Hz timer stands in when they stop for two
  frames, e.g. for a hidden window, or at once when presentation stops
  following the display, and the blanks it gives count against the
  host's when they resume), and each frame's images are due at fixed
  refreshes after the vblank its frame started from, the extra frames
  first and the real one last. So the title runs at the display's own
  rate (59.99 Hz on a 239.97 Hz display) and every image stays on screen
  for the same number of refreshes: measured in fights at 2x on a 240 Hz
  KWin desktop, 99% of images shown for exactly two refreshes (before,
  frames timed by the clock alone came 6 to 11 ms apart). The time
  between presents it waited for checks the reported rate: a display
  refreshing more than 2% faster (in two windows of 240 presents in a
  row) chooses the mode again with the measured rate; a slower one, or a
  compositor skipping refreshes, is already counted by time
  (`TTT2_DISPLAY_HZ` fakes a reported rate to test this). Presents that fail or do not reach the screen show the newest
  finished image at once, so the queue keeps moving; when the renderer
  replaces the presentation images (the TV buffer changed size) the
  thread lets go of them first. The lead from vblank to the first image
  is what frames needed over the last ten seconds, all but the slowest
  1%, raised at once when frames keep coming late (7-9 refreshes,
  ~30-37 ms, in fights). On other displays, including 60 Hz ones where
  presenting every refresh would only add its queue's latency
  (`TTT2_PRESENT_TIMED=1` forces it), frames get display slots one title
  frame apart (re-anchored when the title falls behind) at a lead after
  their swap and are presented at those times (mailbox). With
  interpolation the real image is shown half a frame later than
  without.
- Compiled SPIR-V and the Vulkan pipeline cache persist in
  `~/.cache/ttt2` (`$XDG_CACHE_HOME/ttt2`). A shader's key covers state its
  translation may not depend on (textures the title left bound to slots it
  does not sample, the other stage's links), so shaders that translate
  alike share a module, and with it their pipelines: a 40-second fight
  made 1,124 modules of 182 different translations and 1,115 pipelines,
  each compiled by the driver on a first run (now 182 and 168).

## Presentation on a computer

`runtime/src/title/` changes what the title shows, not how it plays, and
makes everything from the Wii U game's own files at start-up
(`title::prepare_presentation`, about 0.35 s).

**The title's archives** (`title/archive.*`). `content/hdd/dataNNN.ofs`
indexes `dataNNN.bin`: chunks `ofsi` (each entry's name hash, the CRC-32 of
its name with the register starting at zero, and a word) and
`ofsd` (one big-endian offset per entry into the `.bin`'s payload at 0x100,
plus the end; entries are 16-byte aligned and the low four bits give the
entry's length modulo 16). Every entry is scrambled by XOR with four 32-bit
linear congruential streams, one per big-endian word of each 16-byte block,
seeded from the name hash (x = x * 0xBDE95 + 0x8EF345, four times) and
stepped once per block (w = w * 1531 + 5011); most Wii U entries are then a
zlib stream behind a 16-byte `NRCZ` header (size, flags). Textures are
`NTP3` (BC1/BC2/BC3 blocks in rows, or ARGB8), fonts an `NFH` glyph table
plus an `NTP3` texture, texts `NTXB` banks. At start-up the title puts
every entry of every index into one tree by name hash, the archives in a
fixed order and the update's data100 last, so data100's newer copies of a
few entries win (a French text bank among them). The VFS can serve an
archive with entries replaced or added (`vfs::set_archive_entries`, calls
adding up): a rebuilt index, new entries after the last one, and the `.bin`
assembled from pieces of the original and the new entries.

**Menu buttons.** The title's menus ask which button confirms and which
cancels (`sub_03483B78`, `sub_03483C08`); the answer is a word at +8 of the
system settings object built by `sub_0864107C` (from the PlayStation 3
version's system setting; 1 on the Wii U: confirm with A, the right button).
The port overrides `sub_0864107C` to keep the object's address and writes 0
(confirm with the bottom button) unless a Nintendo controller is in use, at
start and whenever the controller changes. The help bar's icons follow the
same word. Fights read the buttons themselves, so they do not change.

**Icons** (`title/font.*`, `title/draw.*`). Button icons are glyphs of the
main font (data003, glyph table 3A27BC43, texture 4FC9A19E) at private-use
code points that name a button by place (E024 right, E025 bottom, E026 top,
E027 left, four on for highlighted ones; E036/E037 + and −; 2282/2283 L R,
2286/2287 ZL ZR; 253C… the D-pad; E015-E023 Tekken button combinations). Two
textures are made: neutral (face buttons as the font's own four-dot Tekken
button pictures with that button's dot lit, Start and Select as arrows) and
PlayStation-style (symbols, L1 R1 L2 R2, Start and Select, a split D-pad and
coloured dots, drawn with 16 samples per pixel and the font's letters). The
renderer swaps them in (`gpu/replacements.h`): a texture whose level 0 has a
registered MD5 loads the current set as RGBA8 instead, and loads again when
the controller changes (`host::on_controller_change`: the kind of the last
gamepad pressed, SDL's PS3/PS4/PS5 and Switch types).

**Controller pictures** (`title/controllers.*`, `title/pictures.*`). The
player entry screen pictures each controller that joined: the GamePad's,
Pro Controller's, Wii Remote's and Classic Controller's, white on its stand
in the middle (320x220), lit red or cyan on a player's side (1P, 2P) and
small (168x104), in pages 12 to 18 of the screen's texture sets (data007
FB833313 and 82DCEE9A, alike but for some pages' texts). The GamePad's
pictures show the device on the GamePad (while every device drives it,
the one used last) and the Pro Controller's that on the first Pro
Controller: a keyboard, a PlayStation-style or an Xbox-style controller
(any other gamepad) drawn here, or, for a Nintendo controller, the
title's Pro Controller. The drawings are signed distance shapes, white
with grey lines like the title's; the lit ones are made from them as the
title's are, measured: outside, a glow of the side's colour (FC0000,
00D9F9) whose alpha falls from about 190 at the edge to none 14 pixels
out; inside, a tint (FF0000, 00FFFF) mixed in 46 % at the edge and nothing
26 pixels in. The small ones are the pictures at 0.465 of the size, the
body's thickness showing below in a pale blue grey, on a soft black oval.
The pages are made when a picture's device changes, drawn beside the
title's start (some tens of milliseconds), and swapped in through
`gpu/replacements.h` like the icons.

**Fonts** (`title/font.*`). A glyph table (`NFH`) holds the font's size in
pixels at +4 and the glyph count at +8 (little- or big-endian, by font),
then from 0x450 a 32-byte record per glyph sorted by code point: from +4 its
box in the texture (x, y), left bearing, top above the baseline, advance and
line height (64ths of a pixel), width and height, and the code point
(big-endian) at +22; the rest is bookkeeping (the glyph's place among those
of its code points' high byte). Texts are drawn with the main font
(24 px, 3A27BC43/4FC9A19E), a plain one (descriptions, 7C74E49A/099AF947)
and the Korean and Japanese gothic fonts (22 px, help panels such as
Controller Setup; B1277EE3/C4C9633E, 46B70814/335915C9), which have Latin
letters; only the main font has the icon glyphs.

**Texts** (`title/text.*`). An `NTXB` record is the key (padded to four with
at least one zero), two bytes, the length in characters, the UTF-8 text and
the English original (each padded with at least two zeros); the bank's index
points at records, so a text can change in place. In every bank (data003's
and data100's), names of the Wii U's buttons (English, French, Italian,
German, Spanish: "the X Button", "bouton X", "X-Knopf", "+Control Pad", …)
become the buttons' icons, which are always shorter, and the prompt "PRESS
THE + BUTTON" and its translations show the Start icon. An icon in a text is
a symbol no text uses that all four fonts have (£ ¥ ¢ ª for the right,
bottom, top and left buttons, ＼ ³ » for +, − and the D-pad), its glyph
changed in each: in the main font to the icon's box and placement, in the
others to a box over unused glyphs (Þ, Œ, …; unused ideographs and Hangul
in the gothic fonts) where the icon is drawn, scaled to 21 texels, into the
font's texture (one per kind of controller). The changed banks and glyph
tables reach the title through the archive overlays.

**Title screen** (`title/title_screen.*`). The logo is a video ending on the
still in the title screen's texture set (data007 76C7E3CF). The new logo is
that still subtitled "ULTIMATE EDITION" in the brush lettering of its "Wii U
EDITION". The old subtitle goes: rows below the "TAG TOURNAMENT 2" banner
fade to black (the kanji tucked behind it) and its stroke that curls up
beside the banner is removed (thin bright parts connected to the subtitle).
The lettering is black ink inside a rough white shape that runs round each
word; the port finds the white (bright, near grey, connected to the
subtitle), the shape it goes round (closed and filled), and in it the ink
(dark) and windows onto the logo behind (the rest, where wide enough to
have an inside). "ULTIMATE" follows Excentrian's design for this logo
(issue #9): its letters' boxes and spacing, and the outlines of its M and
A. It is drawn finely (4x4 subtexels to a texel, averaged down for smooth,
anti-aliased edges): U is WiiU's ink, T, I and E are EDITION's (ends cut
from a neighbour rounded off) and L is EDITION's I with its E's bottom arm,
each stretched over its box, set where mostly black and cleaned up (only
its largest part, small holes and notches up to a texel wide filled); M
and A are filled from the outlines, their edge roughened by smooth noise.
Letters stay a texel apart. Its white is five texels wide round the ink
without its whiskers (an opening by a disc of 1.5 texels), give or take
half a texel of noise, at least two round the whiskers, and fills the
shape's holes (distances: an exact Euclidean distance transform).
EDITION and the underline are pasted
back from the Wii U still (the shape's large solid parts and what lies
close to them, so that highlight specks of the logo touching it stay
behind), the line centred where the old one was: EDITION moves right, and
the underline grows by repeating a stretch of itself. Video frames (BT.601
limited-range planes passed to the renderer's plane filter) that fit
a * Wii U still + b (least squares over the logo, b from the black around
it, the fit explaining over half the variance) become a * new still + b plus
what the fit left (the fade from white and the light sweeping over the
logo), small differences dropped as coding noise and the rest blurred where
the stills differ; chroma moves by a * the stills' difference. The copyright
lines (700x32 textures) lose the three words before the last seven ("Wii U
EDITION" before "& (C) 2012 …") and are centred again.

## Practice: position reset

In Practice, 3 and − (Select) pressed together put both fighters back
where the stage put them, as Tekken 8's position reset does
(`title/practice.cpp`).
The reset is the title's own start of a Practice round: the mode manager's
kind (+444) is 4 or 5 (`sub_06ECB3CC`), and a round starts
(`GameMode::Impl::state_game_preinitbattle`, `sub_0726BDA0`) with the
situation set-up `sub_039C2DB0` for situation 15. Its Practice positioner
(`sub_04F21428`, for situations 12 to 15) places the fighters as the
pause menu's POSITION SETTINGS say (by default 1 m either side of the
stage's centre, x = -1000 and 1000; the settings object `0x108D1C60` has
the start type at +24 and REVERSE, the player on the right, at +100), and
every fighter starts over, standing. The port runs that set-up at the start
of a frame of `GameMode::Impl::state_game_battle` (`sub_0726DF8C`), then
the camera calls of the title's own Practice restart (`sub_04A28490`): the
round's start camera (`sub_05FBB480(camera, 0)`) and, with REVERSE on, the
2P camera (`sub_05FBC0A4(camera, 2, 1.0, 1)`).

3 is the title's button, after its Controller Setup: a fighter's buttons
are at +2032 (1 to 4 = 0x200, 0x400, 0x800, 0x1000 held, 1, 2, 4, 8 pressed
this frame; directions at +2036), and the GamePad's own buttons at +2052,
which stay 0 for the training dummy; the fighter a side has in play is its
first member at `0x1087FB60 + 4 * side`, or that one's partner (+172) when
+7808 is 0 (`sub_05C5EF14`). The battle state keeps running while the pause
menu is open; the fighters' frame (`sub_03ADB118`) stops. That frame arms
the chord in the input layer (`cafe::os::arm_select_chord`, with whether the
GamePad's fighter holds 3): while it is armed, VPADRead holds a press of −
back for eight of those frames (the fighter sees a button two or three
frames after the pad has it), and if 3 is held by then the press is the
chord's: the game never sees it, and the battle state takes it
(`take_select_chord`). Otherwise the press reaches the game late, also
when it was let go meanwhile. 3 and − in either order reset, and − alone
still reaches the game. The position reset also starts the frame data
panels' totals over.

## Practice: frame data

In Practice a panel for each side shows its attacks' damage and properties,
frame data, posture and distance, as Tekken 8's Practice does
(`title/framedata.cpp`). It is read from the fighters' state after each
fighters' frame (`sub_03ADB118`, so it stops with the pause menu), from the
fighter each side has in play (player structs of 10592 bytes from
`0x10884B50`). Measured with per-frame dumps of the structs in scripted
Practice rounds (Jun against Jun: hits, a GUARD ALL dummy, the Counter
setting on):

| Field | Meaning |
| --- | --- |
| +0, +8 | position x, z (f32, millimetres) |
| +96, +100 | health (s16; 180 for a solo fighter) and its recoverable ceiling (equal for a solo fighter; tag rounds not checked) |
| +136 | the fighter's own moveset (+272: the one in use; a fighter hit plays the attacker's reactions from the attacker's moveset) |
| +212, +280 | the move in play's frame (from 1) and its record |
| +444, +448 | the attack in play's base damage and hit level (the attacker) |
| +488 | the combo's damage so far as dealt, after the multipliers (the fighter hit; 0 again once it recovers) |
| +872 | posture, low byte: 1-3 standing, 5-7 crouching, 12/13 down, 14 juggled, 25 airborne (Tekken 7's simple move states) |
| +1152 | the frame's hit events, for that frame only: on the fighter hit 0x800000 an attack hit it, 0x20000000 it blocked, 0x80000 a counter hit (0x20000 one the Counter setting makes); on the attacker 0x200000 its attack reached. Bits 12-15 hold its reaction's state while it lasts: 6 the hit's frame, 1 after it, 7 from the frame it meets the wall (a splat; later wall hits add 0x400000), 8 the floor |
| +522 | the move in play's last frame before the fighter can act (16 bits; a hit or block reaction's too) |
| +1160 | bit 0x100: the fighter can act, lit from the first frame its move can be cancelled into another or the first frame back in its neutral move |
| +1180 | the last hit's base damage (the fighter hit) |
| +2704 | bit 0x10000, on the frame it was hit: a punish (hit during its own attack's recovery) |

A move record (0x70 bytes) has its hit level at +0x10 (the second byte: 1
low, 2 mid, 4 special low (crouching jabs), 5 high; 7, 8 and 11 only on
item moves) and its first and last active frames at +0x64 and +0x68
(Jun's jab: 10, as Tekken's frame data gives its startup). Frame advantage
is the difference of the frames each fighter needs until it can act again:
Jun's jab +8 on hit and +1 on block, as in Tekken's frame data, d+3 −3 on
hit and −14 on block. It shows on the frame the hit or block lands, from
both moves' +522 (the attacker's attack, the defender's reaction), and is
checked by counting until both can act (+1160), which corrects it where the
defender goes on through other moves (a knockdown: +27 on the hit, +53 once
Jun's f+4 victim is up); the two agreed on every other hit measured. The damage multiplier shown is the one the
title's own DAMAGE display shows (120% for a solo fighter, 144% for a solo
fighter's counter hit, else the dealt damage over the base). The Counter,
Punish and Wall badges light from those markers, the ones the title's HIT
INFO shows COUNTER, PUNISH and WALL HIT from (checked against a player's
counter hits, punishes and wall hits with Reina against Jinpachi), and stay
lit for the combo, as those texts do; Wall lights on the frame the state
turns 7 during a combo, so a first splat counts as well as later wall hits.
No marker for CLEAN was found, so that badge stays dim. The
practice settings object (`0x108D1C60`) holds Action 1 at +4 (4: GUARD
ALL), the HUD Information rows at +48 to +76 (COMMAND HISTORY, HEALTH GAUGE,
DAMAGE INFO 1 and 2, COMBO INFO, HIT INFO, ATTACK PROPERTIES, HIT ANALYSIS;
1 = on) and Counter at +80; the panels stand above the hint line along the
bottom, where DAMAGE INFO 2's bars also go.

COMMAND HISTORY is on to begin with: the practice settings' defaults
(`sub_04F1F270`, r3 the settings: as the game starts, for the pause menu's
DEFAULT) set it on, and as a Practice round starts (`sub_04F2544C`, after
the saved settings were copied in) the port sets it on again, its pause
menu value too (the menu fills its values from the saved settings before
the round starts and reads them back as it closes). It can be turned off
for the session. Its row in HUD Information has the default cursor and
entry texts of a row whose default is on (HEALTH GAUGE's), so ON is green.
COMMAND HISTORY shows an input history after Tekken 8's in place of the
title's bar along the bottom. The title turns its bar on with
`sub_04F1EDAC` (r3 the practice HUD at `0x108D1D50`, r4 1: bit 0 of its
+4 set, then the bar started by `sub_04F1BB34`), from the settings word as
a round starts (`sub_04F2544C`) and from the pause menu's value as it
closes; the port makes it never turn on, and the word, which the pause menu
shows and sets as before, turns on the port's history instead. The
player's fighter (the side the GamePad drives: +2052, its raw buttons) has
its buttons at +2032 (1 to 4 held: 0x200 to 0x1000; pressed this frame: 1
to 8) and its direction at +2036 (bit n for numpad direction n, forward
being 6 as it faces); each fighters' frame either adds a frame to the
newest row or starts a row, and the overlay draws the last 27 in a column
along the left edge, from under the 1P name tag, with the main font's icons: the bold arrows at `0xE008` to
`0xE00F` (numpad order, 5 skipped; `0xE000` on the thin ones) and the
Tekken button pictures at `0xE014` + the buttons held (1 in bit 0 to 4 in
bit 3).

ADV. COLORS colours the fighters by frame advantage, as Tekken 8 does: from
a hit or block until both can act again, the fighter ahead blue, the one
behind red (by the advantage the moves give until one of them can act,
then by which one can). The title draws a fighter in a colour it multiplies
the fighter's with (four floats: red, green, blue, alpha; white leaves it
as it is, alpha below one fades the hair), which it gets from
`sub_04E1A0FC` (r3 the fighter): the fighter's own at +7840, or, with HIT
ANALYSIS on, a blue one (0.2, 0.4, 0.8 at `0x1030CD70`) while the fighter's
+1161 byte is 0. The port returns one of its own two instead for the
fighters it colours (1.7, 0.2, 0.2 and 0.25, 0.4, 1.8), until a quarter of a
second after the last fighters' frame, so not once Practice is left.

The position reset has a hint of its own at the bottom right, on the
line where the title puts its hints (Defensive Training's "Select +
button: Start", at the left: 23 pixels high at y 643 to 666 of the TV
image): Select's icon and 3's button picture from the main font's texture
with the port's icons for the controller in use (neutral or PlayStation,
`font::neutral_icons`/`playstation_icons`), "+" and "Reset Position" in
the label font outlined as the title outlines its hints. The panels and
the top view stand above that line (their bottom at y 634, whether DAMAGE
INFO 2's bars are on or not; those bars share the line). The title's own
hints stay where its HUD movie puts them: their place is in that movie's
data, not found (its text is kept as glyphs, not as a string).

The panels are pictures over the title's image (`gpu/overlay.h`): quads in
the TV image's 1280 × 720 coordinates from one RGBA atlas, which the
renderer draws over each presentation image (`gpu/vulkan/overlay.cpp`, an
instanced draw blended right after the TV scan buffer is copied in), so
extra frames have them too and nothing reaches guest memory; TTT2_CAPTURE's
TV captures are saved again with them. They last a quarter of a second
unless shown again, so they go when the fighters' frames stop. The atlas
holds the panel, the title's own: the main menu's player box (data007's
menu textures, an NTP3 of 800 x 116 in BC3, drawn by the title as light
over the scene, black round it), cut into a nine-slice whose edges keep
their size (the top left corner's cut and inner step, the bottom right's
notch) and whose middles come from a plain stretch of rim. What the
texture's edges reach without crossing the rim's line (brighter than 60;
the glow round it is as bright as the glass inside) is outside, the notch
closed where its glass ends (it meets black there); the outside's glow
becomes light (its brightness the cover, its colour at full strength), the
inside dark glass at 72% and the rim opaque, all at four texels a pixel,
filtered, so the outline cuts smoothly on larger screens. 2P's has its
colours turned to their opposites (the teal rim red). Without the texture
a box drawn in its likeness stands in. The panels sit in
from the screen's sides under the fighters, and the ASCII glyphs of the title's Japanese gothic font (labels)
and main bold italic font (values), neither of which has a space glyph.

The pause menu's ULTIMATE SETTINGS row takes the place of TOUCH SELECT, which
opens the GamePad's Easy Input screen. The pause menu is a Lumen movie
whose script calls native functions by name (registered by `sub_04F26xxx`
for Practice's own, `sub_085Bxxxx` for the menus'). Choosing a row it
switches frames (`MenuDelaySwitchFrame`, `sub_085A7C38`, the frame's name
at r4: `FramePracticeEasyInput` for TOUCH SELECT); entering one it puts the
focus on a row (`MenuContainerSetFocusName`, `sub_085AA2D8`: r3 the row,
r4 the menu); rows show and hide by `MenuSetVisible` and
`MenuSetFocusable` (r3 0/1, r4 the entity's name). ULTIMATE SETTINGS is HUD
Information's frame (`FramePracticeMenu01-09-04`, reached through ADVANCED
SETTINGS) borrowed: TOUCH SELECT's switch goes there instead, and while it
is ULTIMATE SETTINGS its header, first six rows' labels and descriptions
(practice texts 1039, 669, 670, 674 to 677, 824 to 841) say its own, its
other two rows are hidden, and its rows' values are its settings.
(ADVANCED SETTINGS itself has no spare row: its frame holds its five.)
Those values are
select values (`SelectValuePracticeMenu01-09-04-NN`, names at `0x1031C9C8`
on, 0x24 apart; cursor 0 ON, 1 OFF) that the title fills from the practice
settings' HUD words as the pause menu opens (`MenuSelectValueSetCursor`
through `sub_04F9FB6C`) and reads back (`sub_04F9FB8C`): the port sets
them as the frame comes and again once its focus is set (the title may
refill them from the HUD words in between), reads them every battle frame
while it is up (a pause menu closed from it is gone before the port could
read them after) and gives HUD Information its own back. A value is drawn
green at its row's default and yellow otherwise by its entries' styles
(entries of 40 bytes from the pointer at +348, the style at +36; +368 the
default cursor): a row whose default differs from its HUD Information
row's (COMMAND HISTORY's is OFF, the panels' on; COMBO INFO's and HIT
INFO's ON, HITBOXES' and TOP CAMERA's off) takes the styles and default of
a row whose default is the one it needs, and gets its own back when HUD
Information next shows. The title's practice code reads the menu's values
back through `sub_04F9FB8C` as the pause menu closes (and applies the HUD's
parts from them); while the rows are ULTIMATE SETTINGS', it gets HUD
Information's own values, as they were when the submenu opened, so a pause
menu closed from the submenu does not turn on DAMAGE INFO 2's bars with
ADV. COLORS, nor turn off COMBO INFO and HIT INFO with HITBOXES and TOP
CAMERA (the menu's script shows the values through its own native). Its back, to ADVANCED SETTINGS' frame, goes to
the pause menu's own instead, with the focus on the ULTIMATE SETTINGS row
(`MenuItemPracticeMenu01-13`); entered as HUD Information again, its rows
show again. Texts are rewritten in the loaded banks in guest memory (found
once by a scan of MEM2 near the menu and practice banks' keys, ~105 ms at
the start of a Practice round) while needed, and put back after: the row's
description (menu text Manu_1669, which other menus may show) while
Practice runs, the submenu's while it is open; a text can only take the
space of the one it replaces. The row's label, longer than TOUCH SELECT's
space, is set on the row itself whenever the pause menu's frame comes up
(`MenuEntitySetText`, `sub_085A9978`: r3 the text, plain ASCII, r4 the
entity's name); the pause menu's labels come from the movie's own data,
not through the script (`MenuEntitySetTextID` is not called).

HITBOXES draws where the title tests attacks against bodies. Each fighter
has 14 spheres on its bones (+2168, 24 bytes each: the centre, the radius
at +12 and again at +20, its square at +16), placed every frame from its
bone matrices (`sub_03C74F50`, bones from the table at `0x101F51A4`),
large (a hip's 440 mm). An attack tests line segments, at +2072 (24 bytes
each: two ends; at most four, their number in the byte at +1158 on the
frames they are tested), against the other fighter's spheres
(`sub_039C0948` → `sub_039C0508`, each line against each sphere by
`sub_039C006C`: hit when the line passes within the radius; the extra
radius `sub_039C0460` adds is 0 for fighters of equal size). The move's
hitbox bones (its record's +0x60, four bytes) give the lines: a point at a
fist or a foot, a forearm or a shin from a bone to the next. The eight
spheres at +2504 (16 bytes: centre, radius, scaled by +1652) are the
fighters' push spheres, not drawn. The port draws the spheres as 3D solids
in the fighter's side's colour (red where a line crossed them, for a third
of a second), the lines as thin capsules in front of everything, fading,
through the camera that renders the scene: the camera manager
(`*(*0x1084FEBC + 732)`) keeps it at +392, a camera holding its eye,
target and up at +0x10, +0x20, +0x30, near and far at +0x48 and +0x44,
aspect at +0x50, its projection at +0xA0, view at +0xE0 (row vectors, the
view looking down its −z; the default Practice camera has none of its
rotation) and the two multiplied at +0x60. The overlay (`gpu/overlay.h`)
takes the solids with that matrix: the renderer casts each pixel's ray
through its inverse and finds the capsules' surfaces exactly, shading them
by their normals (lit from the camera, brighter at the edge, rings at even
heights and angles), the bodies' nearest surfaces only (their depths in a
first pass, then their colours where those are nearest, blended once),
the lines last, without depths.

SLOW MOTION (OFF, 1/2, 1/4) holds the battle's frame (`sub_0726DF8C`,
which runs the fighters, their pushing and knockback, the camera, effects
and the HUD) on all but every second or fourth frame while the fighters
are in play, the title showing the same scene in between, as Smash Bros.'
training mode steps its frames. Holding only the fighters' frame
(`sub_03ADB118`) made them wiggle: the rest of the battle frame went on
moving them (pushing apart, knockback) at full speed. The pad steps with
it (`os::set_input_step`): VPADRead shows a change on every second or
fourth read only, with every button pressed since (one pressed and let go
in between as held for that read), and the frames that run are those after
such a read, so no press is lost (Start opens the pause menu at 1/4; on a
held frame it went unseen). The stepping lasts a quarter of a second
unless set again each battle frame, so the pad goes back to usual when the
battle's frames stop; the pause menu, run from the battle's frame too,
keeps its speed, as frames are held only after one whose fighters ran.
Its row (ATTACK PROPERTIES') has three values where that row has two: its
select value's entries (a vector at +348/+352/+356, 40 bytes each) are the
port's three while the row is ULTIMATE SETTINGS', the row's own put back
before its looks (the title frees them). An entry's text is the menu's
text kind and id at +32 and +36 (the value as drawn, with its arrows and
its colour in the text's control codes: U+FFF2 and two code units, FF20
FF20 green at the row's default, FF20 FFFF yellow otherwise; read through
`sub_045590E0`), or, with both 0, its own string (inline at +4 up to 15
bytes, else at the pointer at +20, its length at +24, room at +28): OFF is
the row's own green OFF, 1/2 and 1/4 its yellow ON's text with the word
changed. (What the port called the entries' styles are these text ids.)

TOP CAMERA shows the fight from straight above in a window between the
panels while the main camera stays as it is: over the fighters' middle,
their line across the window with 1P's end on the left (up, the way away
from the default camera), high enough for both with a metre round them,
with the render camera's own projection; it eases there (a sixth of the
way a frame following the fighters, a tenth rising or sinking as they part
or close in), placed at once when the window comes up. The title draws its frame once;
the renderer draws it again (`gpu/overlay.h`'s window, `Renderer::
view_constants`): the frame interpolation's log of the frame is replayed
once more after its extra frames (`begin_replay(0)`), every draw reading
its recorded constants, in which the camera's view-projection matrix (as
the camera holds it, or transposed, in the block's byte order, within the
first 4 KiB of a block: a few blocks a frame) is replaced by the one from
above; the TV image that replay ends in is kept, and the overlay shows its
middle half in the window, the solids drawn over it through the matching
matrix. The renderer looks for the cameras of the last few frames the
port showed, as the frame it replays may be one or two behind. Logging
the frames and recording their constants, which interpolation does
anyway, run while the window is on at 60 frames a second too
(`Backend::logs_frames`, asked at each swap). Carried targets get the
frame's start back for the replay and its end after, as for the extra
frames, and every other target the frame wrote is copied aside before the
replay and put back after it: later frames may read one without writing
it first (the pause menu keeps the picture of the scene it opened over,
and showed it from above). A replay in which the camera was not found
(a frame rendered from the pause menu's camera, as it closes) keeps the
window's last picture. Only frames that showed a new window are replayed
(`overlay::window_generation`): not a held slow-motion frame, nor the
pause menu's first frame, which takes its picture of the scene (replaying
it on Fallen Garden left a 256 x 256 corner of the stage's work target, in
its purple, in that picture). The title culls its scene for its own camera, so
what that camera could not see is missing from above (the floor is
whole); 2D effects the CPU places on the screen stay where they are on it.
(Writing the matrix into the render camera itself at the end of each
battle frame, `sub_0726DF8C`, turned the main camera instead; the title
then culled for it too.)

Easy Input crashed with an added fighter: it keeps each fighter's four
GamePad move slots in a table of 59 (`0x108638F8`, read through
`sub_02774188`, written through `sub_027741EC`), and both stop the title
(a store to address 0) on a larger select id; its state machine
(`sub_0239AA84`) loads them (`sub_0239CBD4`) once the screen asks (bit 0x2
of `0x108516EC`). Practice no longer opens it, and wherever else it opens,
added fighters get empty slots of their own (not saved), so it loads for
them too.

## Input delay

The Wii U game acts on a fighter's buttons two frames after it reads them,
in every mode; Cemu's "Reduce input lag" graphic pack takes that away by
loading 0 in its place (`li r7, 0` at `0x02EF885C`). The port leaves it
out by default (`title/input_delay.cpp`). Each frame a fighter's input
(`sub_03F536C8`) puts the pad's buttons at the front of its side's queue
in the object at `*0x107B391C` (`sub_02EF7DC8`; per side a deque of
words at +4 + 24 * side) and takes the buttons of as many frames back as
the object's first word says (`sub_02EF8828`: it drops the oldest until
that many and one are left and takes the oldest). That word is set by
`sub_02EF9010` when a mode starts (`sub_06ECC76C`, `sub_06EDCD8C`) to the
title's default, which only `sub_05C5D7B0` reads (the word at
`0x107CDE3C`, 2 in the game's data), and by Practice's Input Delay setting
(`sub_04F24EFC`: 1 to 5 bars give 15, 10, 8, 5 and 3 frames from the
bytes at `0x1031C658`, off the default). The port replaces what
`sub_05C5D7B0` returns with display.ini's `input_delay` (no: 0 frames;
yes: the game's own) or `TTT2_INPUT_DELAY`, so with 0 a fighter acts on
the buttons of the frame they are read in, and Practice's bars still
delay as they say. The game logs `ttt2: input delay: 0 frames in place of
the game's 2` when a mode first asks; `TTT2_TRACE_INPUT_DELAY=1` logs each
delay the queues get.

## Added fighters

`runtime/src/title/roster.*` adds fighters from character packs (folders in
`$TTT2_CHARACTERS`, else `$XDG_DATA_HOME/ttt2/characters`, else
`~/.local/share/ttt2/characters`), made on the
player's machine from their own games by `tools/characters/`. This repository
holds no part of any fighter.

**Where it fits.** A fighter is a select id (0-58; the 63-entry code table
at `0x107C57F4` adds 59-62, the practice dummy, an empty dummy and the
Fight Lab's two mobs; 63 means "random" or "none") with a three-letter code,
character records (`0x107B4220`, 139 x 84 bytes: id, costume slot, place in
the UI order, motion row; 139 means "none") and a motion row (`0x105A51C4`,
68 x the keys of its motion pack, moveset and movelist). Added fighter k
(its pack's `slot`; a pack naming none takes the first free one) takes ids
the title does not have: select id 64 + k, records 140 + 2k and 141 + 2k
(held by the port, not in the title's table), a motion row (the rows no
fighter names, 58, 64, 61, 62 and 65, then rows from 69 on, whose keys the
port puts in the spare row 63 while `sub_075DA0C8` reads them) and a select
grid cell 62 + k. The title's per-fighter tables have 63 rows, so the
functions that would read past them for an added fighter, or turn its id
into 62 or "none", are overridden: the record accessors (`sub_033D502C`
and the functions around it), the code table's reader in the character
loader (`sub_044BE1EC`, run with a stand-in: Paul's code slot holds the
added fighter's code meanwhile, and the player gets the real id after), the
readers of tables indexed by id (given the donor's id, or the donor's row
lent the added fighter's entries while they run), and the match set-up's
id bytes (side struct +640, a member every 4288 bytes), which twelve setters
cap at 62 (the port writes the picks back after them and before the VS
screen reads them through `sub_06EEAEE4`). At start-up, after the title
registers its own fighters (`sub_065C3128`), the port registers each added
fighter's code with the title's key registry (`*0x107A3FB4`: per code, the
keys of its body files and part packs by type) and chara master
(`*0x107A71E8`), the way the title registers its own.

**Its cell.** The select grid (`0x107B7668`, 32-byte cells: fighter, the
cells the cursor moves to, column and row) has 62 cells; it grows over the
following, unused grid of the PlayStation 3's smaller roster. The added
cells sit at the free ends of the top row (columns 0-2 and 19-22), then in
new columns beyond the rows' ends (-1 and 23, then -2 and 24), then in
a new top row (row -1, from the '?' column outwards; `kRowCells`), which
the grid has only while a fighter's place is past those 19 cells: the
cursor's place on the screen is computed from the column and row
(`sub_06F4D7B8`: 48 pixels a column, 65 a row, both signed; nothing else
reads them), and the importer puts each cell's picture in the grid's
layouts at its column and row: a copy of a row-1 panel, whose card sits
6 units above its place where a top-row panel's sits on it (so a cell in
the top row is placed that much lower), drawn after the panels of its
row and the rows above (each row's panels cover the bottom of the row
above them). For the new row the importer moves the
title's three rows (and the band under them) down a row into the space
under the grid, stretches the '?' panel over four rows and drops the
"CHOOSE YOUR CHARACTER" banner (`art.four_rows`; the new row's empty cells
show the background); `shared/grid.ini` (`grid = rows`) tells the port,
which then moves the '?' cell up, the cursor's row 1 down 65
(`0x10531388`) and the button guide (one object every menu shares, placed
by `sub_04DC6A48`) down 40 while the grid is on screen. Every row is a
ring left and right and every column a ring up and down, in column and
row order, as the title's own cells are
(rebuilt from the cells' columns and rows, this reproduces the title's
links exactly). A slot with no fighter has a random cell nothing moves to;
the grilles over the top row's ends are hidden where a cell sits.

**Its files.** The pack's files reach the title as entries added to data100
(`vfs::set_archive_entries`) under keys of its own code (the CRCs of
`<code>.xml` and so on, and of `<code>/parts/<kind>` for its part packs);
whatever the pack leaves out is copied from the donor, a TTT2 fighter the
pack names. A pack: `character.ini` (format, code, donor, sex, slot, chr_tones),
`<code>.xml/.nud/.nut/.bon` (item database, model, textures, skeleton),
`<code>.moveset/.motion`, optionally `<code>.mop/.havok.xml/.mvl`, its sound
banks, costume parts in `parts/<kind>/<index>` and its own pictures in
`art/`. The title's entries that several added fighters change (layouts, the
big portraits' container, the HUD's pictures, the colour palettes and grid,
the select screen's name calls) are made by the importer for all installed
packs together, each fighter at its number, in the folder `shared/keys/`
(`<key>.bin` a changed copy, `<key>.add` textures appended to a container; a
copy of a sound bank stays raw, in the original's archive). The port loads
only packs whose `format` is its own (`kPackFormat`, the importer's
`pack.PACK_FORMAT`) and never a pack's own `keys/`: the earliest packs carried
title entries made for them alone there, whose texture pages, joined before
`shared/`'s, moved every added fighter's pictures one place. A pack without a
`format` line is format 1, or 0 when it has such a `keys/` folder; both sides
read numbers (`format`, `slot`) as ASCII digits only, else as none. An older
or a newer pack is skipped with a warning and keeps its number for its
re-import, `shared/` is made for current packs only, and `launcher.py status`
reports such a fighter as `outdated` (or `newer`, which the importer does not
replace). A current pack's `revision` (none: 0; the port ignores it) below
`pack.revision` (`pack.REVISION` for changes every fighter gets, plus a
definition's `REVISION` for its own) is loaded but misses what importing the
fighter now gives: `launcher.py status` reports it as `update`. Numbers go to packs as the port gives them (`pack.placed`): a pack
without a code of three lower-case letters or a donor has none, named slots
count below 128, and of two packs of one code the first by number is
loaded. Each frame the
game skins the vertices of the models on screen (both fighters, some stages'
animals) into one of four stream-out buffers (80 bytes a vertex: position,
normal, tangents and a per-vertex state its skinning shader carries from
frame to frame), and in a match's first frame those of all four fighters,
which is the only time a tag partner's state is set up; a partner that does
not fit there draws black from its tag-in on. The buffers are sized for the
title's fighters (20,000-34,000 vertices, 7 MiB each), so the port triples
them (`sub_08977AE8`'s configuration), and the importer keeps an added fighter
under 42,000 vertices (leaving out 2P colour layers if it must; Noctis, whose
model holds all his summoned weapons and his trousers, 90,000: two of him and
two others fit) and its textures at 4 MB like the title's (the largest
halved). The effect files a match copies in (the common ones, the stage's and
each fighter's) share the resource manager's 20 MiB pool (`sub_08A7ED8C`'s
size) with textures that are loading and much else; two fighters with many
effects filled it and the match did not load, so with added fighters it is
twice the size. And the CPU's play (`sub_039A6214`) reads a table of 67
fighters by the player's motion row with no bound, past which added fighters
from place 5 on lie: the attract demo crashed on Lidia, so it gets the
donor's row meanwhile.

**Its voice.** A fighter has sound banks (raw NUS3BANKs in the sound
archives): shouts, damage voices, KO screams and the announcer's call of its
name (`se_Chr_<code>`), win quotes (`se_Dwi_<code>`), intro lines
(`rm_Dst_<code>`) and the long win quote one win pose streams
(`rm_Dwi_<code>`, found by key in a table of 63, `0x105C5180`, as the intro
lines are in two others; a fighter with none there streams from a file with
no name, which the title reports as an error). The first two are found by
bank ids (`sub_07A5CAC8`, `sub_07A5CAA4`) whose keys `sub_07A5D01C` gives.
The title has a bank object for each id below 264 and only four ids with no
bank (1, 122, 233, 253), so an added fighter has one bank (its shouts, then
its win quotes: `se_Chr_<code>` with `chr_tones` in `character.ini`), and a
fight load (`sub_079660FC`, asking each member's ids) binds one of the four
to it: an id is given to another fighter only when no fighter list holds it
and its bank object holds no bank (the title unloads a match's banks when it
ends), so a fighter always loads its own bank on a newly bound id, and a tag
match's four fighters fit. The sound library also refuses a bank whose
project id (in its `BINF` chunk) a loaded bank already has, so every added
fighter's banks get ids of their own (1000 + 4 x its number + the bank's
kind; the title's are 0-461). Moves do not name tones: a shout or damage voice
is a number in the fighter's voice list (`0x107D44EC`, by select id, copied
at start-up by `sub_0796F300`), which holds sound ids, and the sound table
(`sub_079E5B1C`, 8506 x {tone, bank id, group, flags}) gives each id its tone
and bank. A move's shout n (`2 << 24 | n`) is the n-th entry of category 5
(the entries whose 16-bit mask has a bit of `0x105DEFDC[5]`, 0x20;
`sub_0796F4C0` counts them, `sub_0796F218` finds the n-th; n past the count,
like the 999 most moves of both games carry, plays nothing), a damage voice
n the (count - 1 - n)-th of category 6, and both games number shouts alike
(short, medium, long, then the others), so the importer fills the donor's
tones by its voice list: shout n gets the Tekken 7 fighter's shout n, and
shouts past the donor's count are tones appended to the bank
(`character.ini` `voice_extra`), which the port adds to the fighter's voice
list (answering `sub_0796F4C0` and lending the list and its counts to
`sub_0796F218`). The added fighter's bank keeps the donor's layout, so the
port gives it the donor's voice list with its ids pointing at copies of the
donor's sound table entries (an extended table, new ids above the ones
`sub_079E5CD0` remaps) whose bank is the id bound to it and whose win quotes
come after its shouts. Win quotes are played by tone of the se_Dwi bank
(property 0x82f9, value 0x0E003000 | tone, `sub_07753DA0`: the port adds
`chr_tones`). The select screen's name calls are tones of the shared bank
se_Slt_StartChar (`sub_079E5D64(id, 1)`); the shared folder adds every
fighter's to a changed copy of it. Between matches the title releases its
fighters' cached bank files (`sub_07967F58`); the port releases the added
fighters' then too.

**Its pictures.** The 2D screens find a fighter's pictures by its UI
position, its row in tables of 59 (from the select id through `sub_06F0A484`
or from a record through `sub_06F0A4A4`): labels of per-fighter sprites in
the Lumen layouts of data007 (`face_<code>`, `chara_face_yoko_<code>`,
`p1_chara_waku_<code>`, whose animation ends on the fighter's name), keys of
portrait textures, frames of the big select portraits. An added fighter has
no row of its own, so the port gives it Paul's (0) and, while the code works
on it, Paul's row of each table holds that fighter's entries (label names,
keys, the big portraits' frames 118 + 2 x number); the functions that ask put
Paul's back when they return. The
select screen asks for both team members first and sets their pictures
after, so there each member's pictures follow its own question (told apart
by call sites), and moving between Paul and the added fighter resets the
member's cached position. In fights the HUD draws names and faces from its
texture container by numbers from a table by UI position (`0x1035AC88`), the
position from the record (`sub_033D555C`); the shared folder adds three textures per
fighter after the container's 259, and Paul's numbers become a fighter's while
the HUD draws it.

**Its costume.** The select screen's costume chooser lists a fighter's
costumes from rows by select id (`0x103B4B84`, read by `sub_0580D690`, 59
rows) with a picture each, from a texture container whose key is in another
table of 59 (`0x10161590`), then five customisation slots; the added
fighter's place in that table is past its end, in unrelated strings, and a
key nobody requested makes the chooser assert. The added fighter has one
costume: the list function reads its row (the donor's costume 1) in the
place of Paul's, its pictures (the pack's `art/costumes.nut`, else the
donor's) have their key lent to that place only while the chooser's
functions run, and the chooser leaves out the customisation slots (made per
fighter in a mode the added fighter is not in). Opening the chooser notes the
fighter under the cursor (`sub_02669380`, which asserts an id below 63): an
added fighter is noted as its donor.

**Its outfits.** A pack may hold up to 14 complete bodies besides its own
(`character.ini`'s `outfits = <code> ...`, each code's `.nud .nut .bon .xml
.mop`, one picture each in `art/costumes.nut`): the importer makes one from
each of Tekken 7's preset sets for the fighter (a definition's `PRESETS`,
`convert/outfits.py`), for the fighters `--outfits` names (the launchers'
Outfits boxes; all by default); the preset of the fighter's own costume is its own body,
the only one with 2P colour layers (palette entries go by select id, which
outfits share). The chooser then lists the donor's costume 1 once per outfit
and the pick (`sub_033E265C`) chooses the body; 14 entries is the chooser's
room (its customisation rows stop there, `033E379C`). Each outfit is
registered as a body of its own (registry and chara master) under a private
32-bit key from 0x10000, never a select id: the chara master's lookup by code
(`sub_0209506C`) gives back the fighter's id, the loader (`sub_044BE1EC`) asks
for the outfit's code and drops a finished body when only the code changed
(outfits share a record), and the recipe initialiser (`sub_02091898`) gets the
outfit's code strings while the fighter's id and motion row stay; a slot's
remembered outfit is dropped when its fighter changes (going back to the menu
reuses a slot without a load). Outfit textures have ids of their own
(`0x10500000 + (place × 16 + outfit) × 0x1000`): two outfits of one fighter
meet in a match. A code that clashes with a fighter's or another outfit's
leaves out both packs.

**Its extra bones (Kazumi's tiger).** A skeleton's OPT list names extra
bones (`cha:OPT<number>_<name>`); the fighter's spring file (`<code>.mop`,
one 0x60-byte entry per bone number) swings them, and a bone in the list
without an entry hangs under gravity. Some fighters' extra bones are
animated: a move property (0x82de; 0x82df only in win poses, 0x82e0 under
another condition) starts an animation of part 3 of the motion pack on the
fighter's animator at player +7944 (value 0x4000 + index, frame at +16),
and per-fighter code posts the channels into the bones' records (the model's
bone container at +80, `sub_06A5C5FC` by bone number: a 144-byte record,
the local transform first). Both the animator's clock (`sub_05BDC714`) and
the posing (Devil Jin's wings: `sub_069D3184`, from the per-fighter
dispatcher `sub_069D8B30`) are written for a few character ids only, and
body animations' extra channels are taken by the same per-fighter code (at
most 64; more make it write to address 0). The pack's tiger is extra bones
600 on with a spring entry that keeps each still (Devil Jin's kind, flag 8),
hidden 100 m below the floor in the bind pose; for the added fighter the
port moves the clock of its part-3 animations and, after the dispatcher,
writes each bone's local transform from the animation's raw channels
(translation, rotation, scale per bone), the last frame putting the tiger
back below the floor.

**Its hair and tails (Lucky Chloe).** Tekken 7 simulates chains of bones
that its meshes model straight out from the body (her twin tails stand 1.3
m out sideways in the bind pose). The importer poses each chain hanging
(links turned to directions the fighter's definition gives, the vertices
with them) and makes its bones extra bones 300 on, each with a copy of
Lili's hair entry (flag 0: it swings) and Lili's collider round the neck in
the spring file; TTT2 then swings them as it swings Lili's hair.

**Its weapons (Negan's bat).** Tekken 7 draws a weapon as part of the
costume, skinned to an attachment bone under a hand (or the hips, the back),
and the moves pose that bone with the extra channels of their body
animations: after the 23 body channels, a pair (translation, rotation) per
weapon bone; without the pair the bone stays where Tekken 7's bind pose has
it. The pairs are TTT2's own kind: TTT2 poses Yoshimitsu's katanas (extra
bones under his hands) from such pairs, writing them into the bones'
records unchanged, and Tekken 7's item moves are TTT2's very animations. So a
pair is the weapon bone's local transform in TTT2's frame of its parent (their
resting values are Tekken 7's bind poses: Kunimitsu II's swords within 2
degrees and 1 mm; her kunai flies straight at the opponent); the bone's own
axes are Tekken 7's with y reversed, and the pairs come in Tekken 7's order
(Negan: the left bat's, then the right's). The importer makes each weapon an extra bone
(800 + the pair's number; still ones 820 on) bound where Tekken 7's bind pose
has it, skins the weapon's triangles to it and gives it still spring entries;
the points it hits with become extra bones under it. Every frame TTT2
samples each fighter's current animation with all its channels
(`sub_069DF470` -> `sub_069DCBD0` -> the sampler `sub_0689C42C`) and copies
the extra ones into the model (+13984; +13220 how many), where only some
fighters' code reads them; after the per-fighter dispatcher the port writes
them as the weapon bones' local transforms. (The sampling a move starts with,
`sub_06897540`, is once a move: pairs taken from it froze a weapon at its
animation's first frame, and Noctis's thrown sword never left his hand.) A
weapon always in hand ignores a pair over 1.5 m out: Tekken 7's spin
reactions carry 20 m paths in those channels. Hits:
TTT2's hit test (`sub_03C74F50`) takes a bone's position only for hit
locations 0..21 and keeps points per player for 27..77, those of a held
item at player +3416 (70..77, written only by items; above 77 a location
has no position at all), so the weapon's points hit as locations 70..73 and
the port writes their positions there every frame, made from the parent
bone's world matrix (the title keeps none for still extra bones). That
matrix (the hit test's skeleton) is a frame behind the animation, so the
points take the local drawn the frame before; with the current one, Noctis's
thrown sword (1 to 4 m from a hand swinging down) had its points fly over the
opponent's head while the sword drawn went through him.

**Summoned weapons (Noctis).** Noctis's mesh of weapons holds a copy of each
for each hand (a great sword, a sword, a dagger; a spear in the right, a
shield on the left forearm), and the pairs of a hand carry one pose, the
grip's; a move shows weapon n with property 0x82a7 (value n) until 0x82a8
(n, or 16: all; his stance ends them all), and its appearing and vanishing
particles come with 0x82af (n << 16 | effect id). The importer turns 0x82a7 /
0x82a8 into 0x822E / 0x822F (ids TTT2's property interpreter ignores and no
TTT2 moveset uses; the intro and win poses get those of Tekken 7's pose too),
the particles into the fighter's effects at the weapon's hand (their mesh
particles, the weapon's own models, are left out: the model draws them), and
character.ini lists a weapon's summon (`k:parent:points:summon`). The port
keeps each player's summoned weapons (a hook on the interpreter,
`sub_03AE86A0`) and collapses a weapon not summoned into its bone (axes 0).
Tekken 7 puts the weapons away when the fighter is hit (its game does, not
the moveset); the added fighter is hit, falls and gets up through the
donor's generic moves and its stance, so each of those dismisses them as it
starts (his own moves never pass through them with a weapon out).
His Warp-Strike throws the sword (its pair flies it up to 4.8 m) and warps to
it when it hits; Tekken 7 dismisses it as it hits, with particles of its mesh
lingering there (left out, as above), and summons it again for the warp. The
importer starts the move a hit leads to (the definition's `WEAPON_HOLD`) with
0x822B (another id TTT2 ignores), and the port keeps a thrown weapon (over
40 cm from its hand) where it was drawn last, drawn though dismissed (placed
with the hand's pose extrapolated a frame on), until
the warp's animation has it nearer the hand than that, a dismissal of all, or
two seconds.
His moves hit with a weapon's tip (Tekken 7's hitbox (tip, 0, tip, hand)) and
some with its guard: a hand's weapons share the four point slots (a point
`n>slot`), a slot taking the summoned weapon's point, else the first listed's.

**Saving Tekken 7's movesets** (`tekken7/autodump.py`, `tekken7/memdump.py`,
`tools/characters/t7helper/`): Tekken 7's data files are encrypted, and a
fighter's moveset is readable only once the game has loaded it, so the game
runs, unseen and untouched: Proton inside gamescope's headless backend, its
sound sent to a silent sink of its own (it does not start without an audio
device). A small Windows program built with MinGW runs in the game's prefix
(served over a localhost socket that wants a per-run secret: Proton's
launcher passes no stdin or stdout on). It asks Steam, as the game does,
which DLC the player owns (only owned fighters are dumped), and it calls
the game's own functions while the game sits on its start-up screens: the
loader that takes a fighter's three-letter code and has the game's
background tasks read its files (moveset, animations, command list; the
game decrypts them), then the two in-place conversions the game runs before
a fight, which turn the moveset's offsets and indices into pointers and the
command list's offsets into the form it keeps. The helper knows those six
functions (and the two below) and checks their first bytes before calling
any, so another build of the game is refused, not crashed; no address comes
from the connection. Its addresses are the ones at the exe's preferred base,
moved to where the game is loaded (Wine Staging's builds, Proton-GE's among
them, load the exe elsewhere).
Nothing is pressed and no screen is read, so key bindings, settings,
language and pop-ups play no part. The dumper then reads the result from
the game's memory: the moveset is one buffer (header with the aliases, 19
tables back to back, the strings), every link an address; the .tkmvst form
has row indices, string and animation offsets instead, and the command
list's offsets are turned back. The first 15 fighters and Heihachi load in
one run and match TKMovesets2's files exactly: every table, name, animation
and the command list (Geese's and Noctis's load the same way).
Everything a session starts has a tag of its own in its environment (Wine
starts its processes detached, so they are no children of gamescope). Its
end, also on SIGTERM (the launcher's Cancel; the importer turns SIGTERM and
SIGHUP into an exit that runs it), ends those, and runs `wineserver -k` only
when nothing else uses the prefix: a Tekken 7 the player starts from Steam
meanwhile goes on (Steam's start waits for the session's Wine to end). One
session runs at a time per prefix (a lock in `$XDG_RUNTIME_DIR`), and what a
killed importer left running is ended by the next. The helper's build and
the run's logs are in `$XDG_CACHE_HOME/ttt2/tekken7`.

Some packages and sound banks Tekken 7 also keeps encrypted inside its paks
(Geese Howard's and Noctis's costumes, Noctis's voice bank: about 2,300
files, which then do not start with the package tag or BKHD); the game
decodes them in its pak file layer as it opens them. In the same run the
helper has the game read those files with Unreal's whole-file reader
(`FFileHelper::LoadFileToArray`, the call its asset registry uses), a batch
of paths at a time on one thread of its own (the pak layer keeps a reader
per thread), copies the buffers out and frees them with the game's
`FMemory::Free`; paths must be relative ones under the game's content. The
dumper saves them under their pak paths in `~/.local/share/ttt2/tekken7/files/`,
and the importer's pak reader takes a file from there whenever the pak's
copy is encrypted. No key is looked for or used: the game reads its own
files, as it does when it loads the fighter.

**The importer** (`tools/characters/`, Python with numpy and Pillow) reads
Tekken 7's pak files (version 3; every entry is flagged encrypted but
stored plain, but for the files above, read from the saved copies) and its
Unreal Engine 4.14 packages, the fighters' movesets
(.tkmvst, TKMovesets2's layout) and the installed TTT2 game. The model keeps the
donor's skeleton with the Tekken 7 joint positions (the face joints keep
the donor's offsets, as face animations set absolute positions), skins the
Tekken 7 meshes to it and bakes the costume's colours into BC1/BC3
textures of at most three mip levels. Tekken 7's skin shader brightens its
skin textures, which TTT2 draws as they are, so skin colours are scaled by
a gain measured at import time on the fighters both games have (each one's
TTT2 face texture against its Tekken 7 face, of the fighter's sex: the median
of the five nearest in brightness to the added fighter's face, as TTT2 evens
skin tones out); hair keeps Tekken 7's alpha cut-off rather than the
template's. Tekken 7 also lifts its cloth and hair with rim lights TTT2's
templates lack, which matters only for the darkest (Noctis's outfit and hair,
their colours 0.02-0.06 of the textures'): a definition can give a material
kind or a material a gain (`GAIN`, measured against a Tekken 7 screenshot
relative to the skin) and take a texture's brightness alone (`GREY`: his
outfit is blue-grey where its textures are mauve); his hair's lighter tips
come from a gradient texture its material samples beside its parameters.
Tekken 7 simulates cloth (coats, robes, ribbons, headscarves) with APEX
clothing assets serialised after the mesh, whose physical mesh gives each
vertex how far the cloth may move from its skinned place; TTT2 has no cloth
simulation for fighters, only chains of spring bones (Lars's coat tails:
nine chains of six bones, angle limits, ellipsoid capsules round his legs,
links between neighbouring chains), so the importer makes the same from
each asset whose cloth hangs: chains rooted along the line the free part
hangs from, bones at its mean every 15-20 cm down it, the drawn vertices
skinned to two neighbouring chains, cloth modelled flowing (ribbons,
scarf tails) hung down, and capsules fitted to the fighter's hips, legs and
trunk. The game pushes a bone that crosses a capsule's surface, not one
wholly inside it, and a round starts with the cloth at rest on its parent
bones, so cloth hanging where a thigh stands forward would start inside it
and stay there: the chains' rest is draped over the fighter's own standing
pose (its standing move's first frame), every link of cloth closed round a
leg turned out of the thigh and shin capsules and a ball round each knee (an
open coat's edges are left: the leg passes through the opening). The chains
may swing out up to 1.2 rad (Lars's coat's 0.2 rad at the top held the cloth
inside a leg), and those draped off a leg no further in than that rest: it lies
inside the capsules, where nothing would push cloth sagging back into the leg.
An item that another item of the costume depends on (`DependencyItems`:
Noctis's trousers and boots, worn with his jacket) is worn too when the
definition says so (`DEPENDENCY_ITEMS`). A fighter's character effects are found by bare names its item
database lists, which the title expands to `<code>/alo/<name>.alo` with the
fighter's own code (each fighter's folder has its own copies of the effect
files and their textures): the importer copies the effect files an added
fighter uses (its donor's, and the closest of TTT2's own for its Tekken 7
effect ids) with their textures into the pack's `alo/` folder, which the
port serves under the fighter's code. Tekken 7 plays some moves' animations
as deltas over another (Akuma's forward and back jumps); TTT2 has no such
layers, so those moves become the donor's generic moves. Materials are classified by their Tekken 7 parent material
(skin, eyes, mouth, blended face layers, hair, cloth with or without holes),
a hair material's second pass (the same triangles) is left out, and a
definition lists only exceptions. The moveset keeps the donor's generic
and tag moves and converts the fighter's own: body animations are the same
in both games but for byte order; requirement and property ids, hitbox
codes and reactions are mapped through tables derived at import time by
aligning Heihachi's moveset in both games; projectiles (Kazumi's tiger
strikes) become TTT2 projectiles, which the same five properties spawn in
both games (limb, three offsets, the projectile); a summoned model (her
tiger, an actor of its own in Tekken 7) joins the skeleton as extra bones
with its meshes, its animations (decoded from Unreal's variable-key
compression) become part-3 animations and the moves that summon it play
them; mechanics TTT2 lacks (Rage
Arts and Drives, power crush armour, screws) are left out, and the moves
that bound are the definition's (Tekken 7's after the Tekken 7 Bound Mod):
they get TTT2's bound entry and Tag Assault twins.
The donor's intros and win poses stay (their camera animations end the
intro and the win screen) and play the fighter's animations. The command
list is converted from Tekken 7's (both games keep an MVLT
file of names, commands in nine languages and demos given as pad inputs).
The voice is decoded from Tekken 7's Wwise banks (IMA ADPCM), re-encoded as
DSP ADPCM where the donor's banks use it, and laid out like the donor's
banks. The pictures: every layout with per-fighter labels gets the
fighter's beside Paul's (whole label animations copied), its Tekken 7
pictures scaled so that its face sits where the others' faces sit, cut to
the area theirs cover and laid in the frame and background they share; its
name is put together from letters cut out of the other fighters' name
pictures (the title's own lettering), with the shadow measured on them; the
costume chooser's picture is its Tekken 7 costume-slot picture cut out of its
grey panel and stood in the room the title's own pictures share.
Player 2's colours: TTT2 tints "colourable" cloth per player
(2 x grey x lerp(A, B, mask)) from two palette entries per material; the
fighter's cloth that changes between Tekken 7's 1P and 2P costumes gets an
alpha-tested colourable layer over the changing texels, with colours fitted
to both costumes and placed in grid cells no other fighter uses (the pack
carries the colour grid and both palettes). The pack holds Namco's assets:
the importer refuses to write it inside this repository, and `.gitignore`
keeps the games' file types out.

Tekken 7's 2D fighters' gauges (Akuma's, Eliza's, Geese's; `GAUGE` in a definition,
`convert/gauge.py`, `title/gauge.cpp`): Tekken 7 keeps the gauge in its
executable, the moveset only tests it (requirement 629: at least `param`,
635: less) and changes it (0x81c2 adds its value: EX moves -500, supers
-1000), with 0x8228 (the move's attacks build none) and 0x8229 (the fighter
lights up). The converted moveset keeps them on the port's own ids:
requirements 190 and 191 (no TTT2 moveset uses them and sub_0404FF30 takes
them as false; ids above 642 would not do, as the cancel rows' loader
sub_040D2300 marks rows testing them as special ones, never tested for a
player) and properties 0x8220, 0x8222 and 0x8223 (TTT2's interpreter
passes over them). The runtime does what Tekken 7's executable does around
them: after each fighters' frame a fighter that lost health gains that
times 112% / 150% (Akuma's / anyone else's), its opponent 225% / 300%, of a
blocked attack's damage 37% / 50% and 75% / 100%; the gauge empties at a
match's start and carries over between rounds (the title's situation
set-up `sub_039C2DB0` keeps it for its round end, 26, its next round, 4
and 6, and a match won, 7; a match's first round, 1 and 3, Practice's 12
and 15 and the fighters' load, 23, empty it). As it reaches its most from
below, Akuma's and Eliza's play Tekken 7's `SE_battle_spgauge_full` (its
gauge-full event's listener plays that common sound for them; no move
does): the importer appends it as one more item sound and writes its
number as the gauge line's seventh field, and the runtime plays it through
the title's item sound player `sub_077537D0`. The flash multiplies the
fighter's colour (sub_04E1A0FC) by yellow for a moment. The HUD is Tekken
7's, from its HUD movie (a Scaleform SWF, `tekken7/swf.py`): the importer
plays each clip's timeline and writes every frame's placed pictures into
the pack's `gauge/` (gauge.ini over gauge.nut), and the runtime shows the
clips Tekken 7's HUD code would for the gauge (a stock fills, every stock
full, the gauge spent) on the overlay's HUD layer, the slots' bars moved
along their masks, while the fighters' round phase (player +2048) is past
its intro. Each side's panel ends where its own life bar's frame ends
(the title's HUD size option, 0x107C9908, moves both) and rests a little
above the title's texts at the screen's bottom (Survival's `WINS: n`), in
Practice above the frame data panels' line; those panels go above it (its
box: where its resting pictures' texels cover at least half). The pictures shown only in the glow and lightning clips (Eliza's
bats and flares) are kept at half size, the sheet as BC3.
Geese's gauge holds three stocks and has Tekken 7's MAX mode: 1+2+3 spends
a stock and starts a timer (player +0xcd8: at most 720 frames, one less a
frame; requirement 176 tests it running, 0x82a9 adds to it) that his EX
moves need and shorten, his supers end, and while it runs he builds no
gauge; the port's ids are requirement 192 and property 0x8224. His HUD is
his own movie's (SW_UI_HUD_Rage_MRY, played as Tekken 7's SwfHUDMRYGauge
does): a power bar for the stock being filled with the stock count beside
it (the count's clip baked once per number), MAXIMUM when every stock is
full, the MAX timer's bar with MAXMODE while it runs; he is drawn in a
pulsing light blue (his colour multiplied, as the flash) until it ends.
A super stops time for the opponent as it starts (Tekken 7's 0x828c, slow
motion: its value's low 16 bits the frames, with 0x828d, its fighter
immune; Double Reppuken 70 frames from its 8th, its hit at the 80th): the
importer writes it as property 0x8225, and the runtime skips the
opponent's own frame (`sub_0414FA10`, r3 the fighter: its move, animation
and inputs) and puts it back where it stopped after each battle frame (the
pushing and knockback run outside it), until the frames are over or a
fighter is hit. TTT2 has no hit stop to borrow (the move frames run on
through a hit), and without the stop the opponent recovered long before
the super's hit (1,2,1,2 into Double Reppuken no combo). Tekken 7 shows the
attacker meanwhile through camera animations of the fighter's own (0x8439
/ 0x843a); the port writes a close-up of its own into the render camera
after each battle frame (eye, target, up, view and view-projection: the
title draws from them), from the side the camera was on, turning and
closing in, and lets the title's camera take over when the stop ends.
A Tekken 7 projectile hits a fighter once: Raging Storm's, allowed 10
hits, deals its 43 once, while TTT2's deals its hits on every frame it
touches the opponent (six of them, 140 and more). A projectile that hits
more turns into the next on its hit (a cancel row testing 784, the
projectile hit, with option 0x40; 787 blocked): Double Reppuken's and
Messatsu Gou Hadou's five of 13 and 20. TTT2's projectiles have such
cancel lists but no test for their own hit, so a 2D fighter's projectile
gets the chain's length as its hits (they come on consecutive frames).

The 2D fighters' sound effects (`convert/sounds.py`): Tekken 7 plays a move's
sound with 0x84c4 / 0x84c6 = bank << 24 | n, bank 15 being the common sound
manager's list (`BP_TekkenCommonSoundManager` BattleSysTones: 57
`mrx_hadou01_shot`, 71 `SE_battle_spgauge_start` an EX move's start, 72
`SE_battle_spcombo_start` a super's, 404 `se_mry_rep_shot`, ...), whose
events are in AkBankBattle.bnk or the fighter's own voice bank (Geese's);
a projectile's hit sound is its missile blueprint's (the AkAudioEvent it
names ending `_hit` / `_hit_flame`). The importer appends those the kept
moves use to the fighter's se_Chr (copies of the donor's item sound tone,
`itm_lar_03`; character.ini `sound_extra`), and the moves play them as item
sounds: 0x82f9 = 12 << 24 | 1 << 12 | n (kind 1: the player's own list,
which the runtime makes the donor's item sounds and then these), as does a
projectile row's hit sound (field 16). They play alongside the voice.
A projectile's look turns to the way the projectile flies (its place from
frame to frame; Tekken 7 turns its missile so), and before the projectile
has moved, to the way its row gives (its forward and up speeds): the
effect library gives a particle the emitter's frame when it spawns, and
the look's bodies (Akuma's egg, rings and swirls) spawn on its first frame,
so the air fireball's flew level along its path. An effect that starts with
a projectile thrown up or down (within 150 ms of it: the air fireball's
flash, which Tekken 7 sets on the throwing hand) turns whole about its
fighter's left to the projectile's path (atan2 of the row's up and forward
speeds, -52 degrees for Akuma's): left level, its orbs and wind went
straight up or straight back. Such a projectile ends where it meets the
floor (its frames left set to 1 once its lowest point is at the floor's
height, as Tekken 7's missiles end there; TTT2's flew on through it). An air
move hangs at its height until it has thrown its projectile, then falls on
(Tekken 7's air fireball: thrown right after the take-off it comes out just
above the floor). Falling through its startup, one started late in the jump
landed well before its throw, which then never came (the touchdown goes to
the move's ground_fall frame) or came from the floor a sixth of a second
later.

## The launcher

`launcher/` is what players start: `ttt2-launcher`, shown as "Ultimate
Launcher" (to be shipped as an AppImage). Nothing derived from the
game may be shipped, so the game program is built on the player's PC from
their own `.wua`, by the tools this build uses and the system's C++
compiler.

- **The kit** (`launcher/builder`, target `ttt2_kit`: `<build>/launcher/kit`,
  installed as `<prefix>/lib/ttt2/kit`): `bin/ttt2-build`, `bin/cafe-recomp`,
  the headers the generated code includes, the runtime and `main.cpp` as
  `lib/libttt2_runtime.a` (the objects the ttt2 target links; they must be
  position-independent) with the archives it uses, `lib/generated_stub.o`,
  `kit.ini`, `VERSION` (the launcher's version and the commit) and
  `t7helper.exe` and `t8helper.exe` when MinGW is there. `kit.ini` holds the generated code's
  compile flags (the ttt2 build's own, `TTT2_GENERATED_OPTIONS`) and the
  link: the runtime archive whole (its imports must replace the generated
  weak defaults and its export registrations stay), then the other
  archives, then the system's libraries by soname, found on the player's PC
  through the loader's cache, so no development packages are needed (else
  in `LD_LIBRARY_PATH`, `LIBRARY_PATH` or the compiler's library path, with
  a run path to their folder). `needs` is the newest glibc and libstdc++
  versions the kit's programs need, for the messages. The stub
  (`kit_stub.cmake`) defines empty what the runtime uses of the generated
  code (the tables of `cafe/generated.h`, no entries, and the `sub_*`
  functions it calls or hooks, by name only): the kit build links it with
  `kit.ini`'s lines and starts it before it writes them.
- **`ttt2-build check|install|update`** checks the game's
  `code/Tekken.rpx` (the v16 hash; the update over the base game, as
  `wua.cpp` reads it), the processor (x86-64-v3), that cafe-recomp starts,
  a compiler (`--compiler`, `$CXX`, else `clang++`, `clang++-N`, `g++`,
  `g++-N`; one that says it is a compiler tried already is skipped, so each
  of ccache's links counts; each tried on a file that needs guaranteed tail
  calls and links C++ with libstdc++), the libraries, then the stub linked
  as the program will be and started with `--help`, so a C or C++ library
  older than the kit's or a missing library is named before the build, and
  memory and free space (the install folder's also for the work folder's
  copy of the program, when they share a file system). `check` without
  GAME runs only these checks of the PC. The hints name the distribution's
  install command, or on an image-based system (the launcher's rule) where
  it must come from instead. Then it extracts the RPX, runs cafe-recomp
  (0.54 GB of C++; the RPX goes once translated), compiles the files
  largest first, as many at a time as processors and memory allow (up to
  1.1 GB per file with Clang, 1.3 GB with GCC), links, and runs the new
  program's `--install GAME FOLDER` or `--update FOLDER`. About 2.5 minutes
  with Clang on 12 threads, 5 with GCC. It works in
  `$XDG_CACHE_HOME/ttt2/build/run-XXXXXX`, deleted afterwards (one left by
  a killed build is deleted by the next); SIGTERM stops the compilers and
  cleans up. `<folder>/.ttt2-build` names the kit version and the compiler:
  the launcher offers Update when its kit's version differs.
- **Progress**, one line each on stdout (anything else is log text):
  `@step <id> <text>` (check, extract, recompile, compile, link, copy,
  finish), `@progress <done> <total>` (compile: files; copy: bytes),
  `@folder <path>`, `@error <text>`, `@done`. With `TTT2_INSTALL_PROGRESS=1`
  (ttt2-build sets it) `ttt2 --install`/`--update` print `@folder`,
  `@progress` (at most ten a second) and `@error`.
- **The importer's side** (`tools/characters/launcher.py`): `status` is one
  JSON object, in about 0.1 s and without numpy, with what adding fighters
  needs (numpy and Pillow, gamescope, pactl, each game's helper, a C
  compiler, Steam, Tekken 7's folder or why it cannot be used and whether
  its files can be read (`readable`: what `shared/` needs even when it
  cannot run), Tekken 8's folder, whether it is the build its helper knows
  (`build_known`, read from the exe only while a fighter's own moveset is
  not saved) and why it cannot run hidden (`run_error`), the packs folder,
  and per fighter its game (`"game": "tekken8"`), its
  DLC's app id, whether it is added, whether its pack is outdated (an older
  importer's: the game skips it) or newer (a newer importer's: skipped too,
  and never replaced by this importer), whether the pack the game loads is
  to update (an older revision, or a Tekken 8 fighter's `stand_in` pack
  once its own moveset can be had) and whether its moveset is saved);
  `owned` asks Steam through the hidden helper which DLC fighters the
  account owns (Steam is never started). `import_character.py --progress`
  adds `@step dump|fighter|shared`, `@added`, `@stand-in` (a Tekken 8
  fighter added with Heihachi's moves, and why), `@removed`, `@skipped`,
  `@error` and `@done` lines (a game the packs there need for `shared/` and
  that is gone fails before anything is saved or written), and `--remove`
  deletes packs again (numpy only
  when what the packs left share is made again; not at all when only packs
  the game does not load go, as `shared/` never held them). A pack is made
  whole in a hidden folder beside its place (`.<code>.part`, `character.ini`
  last) that then replaces the fighter's earlier pack folder whole (nothing
  of an older pack stays), so a Cancel leaves no half pack; a pack folder
  that is a link is replaced where it leads only when that is empty or that
  fighter's pack, and an earlier pack left as `.<code>.old` by a write killed
  between its two renames is put back before anything is placed.
  `--no-shared` still remakes `shared/` for a fighter that was not in it. Steam from Flatpak or Snap is reported
  (`steam.sandbox`) with Tekken 7's folder, as not supported yet.
- **The window** (`launcher/app`, plain GTK 4.10, no libadwaita; its logic
  without GTK in `launcher/core`, tested by `launcher_core_test`) finds the
  kit, the importer and Python beside it (`../lib/ttt2/kit`,
  `../share/ttt2/characters`, `../lib/ttt2/python/bin/python3`), else in
  the build and source trees it was built from (unless built with
  `TTT2_LAUNCHER_BUILD_TREE_PATHS=OFF`, as for the AppImage, whose program
  names no folder of the build machine), else `python3` in PATH, and
  passes the kit's `t7helper.exe` and `t8helper.exe` to the importer as
  `TTT2_T7HELPER` and `TTT2_T8HELPER`. Its characters have a part per game
  (the installed one first); neither game needs the other, but while one
  is gone with its fighters added (they need it for `shared/`), the other's
  adds are refused with a note, removing one of them alone is too, and
  **Remove All** (asked first) removes all of them at once. A Tekken 8
  fighter's Add needs Steam only when its moveset can be saved (its build
  known, it can run hidden); else it is added with Heihachi's moves as the
  importer does, and the part says why. It
  checks the processor, the compiler and free space before an install, to
  name what is missing with the distribution's install command (on an
  image-based system, by the builder's rule and words, where it must come
  from instead), and runs one task at a time through GSubprocess, reading
  its lines as they come, each in a process group of its own that gets
  SIGTERM if the launcher dies. Cancel sends SIGTERM to the program alone
  (it stops what it started in order: the importer closes the hidden
  Tekken 7 or Tekken 8), kills what is left of the group once it has ended, and the
  whole group with SIGKILL when it has not ended within 45 s. The game runs
  in a session of its own; it counts as running when any `/proc/<pid>/exe`
  is the install's program (also "(deleted)"), whoever started it, and
  Play, Update and Uninstall wait for it. Steam's last answer of the DLC
  owned is kept in `$XDG_CACHE_HOME/ttt2/dlc-owned.json`, shown at once
  and asked again in the background. The install's state is install.cpp's;
  `$XDG_CONFIG_HOME/ttt2/installing` is the launcher's note of an install
  it started that has not finished (the folder and the `.wua`, for
  Resume; the folder's bytes as `@folder` gives them). Uninstall deletes
  only what an install makes (the program, `icon.png`, `game/`, the
  markers, and of `.part` files only the program's and `.ttt2-build`'s)
  through file descriptors, never following a link or crossing into
  another file system and never while the game runs, then the folder if it
  is empty (and the link to it, when it is reached through one), the menu
  entry and the record when they are that folder's, and the shader caches;
  when asked, the saves the game wrote (`common/` and the 8-digit user
  folders, nothing else of a `TTT2_SAVE_DIR` folder) and the character
  packs (with the importer's hidden `.<code>.part` and `.<code>.old`
  folders). The game's settings, `keyboard.ini` and `display.ini`, are
  kept (`~/.config/ttt2` goes only when it is left empty). A character
  whose pack is outdated shows "Older version", Remove
  and Add Again (Add All and Add All Owned add them again too, and a line
  above the list counts them); a newer version's shows "Newer version" and
  Remove only; one to update shows "Update ready", Remove and Update (a
  line above the list counts them, with Update All; Add All leaves them,
  and an import of only such characters is called an update).

**The AppImage**: `launcher/appimage/make_appimage.sh OUTPUT BUILD_DIR`
configures BUILD_DIR afresh (a folder of its own: it refuses another build
folder) for Release with Clang and Ninja, with
`TTT2_LAUNCHER_BUILD_TREE_PATHS=OFF`, without `TTT2_GENERATED_DIR` and
`TTT2_RPX`, and with `-ffile-prefix-map` so that the source paths the
runtime's messages name are relative; it builds `ttt2-launcher` and
`ttt2_kit`, installs them with `cmake --install --prefix AppDir/usr --strip`,
refuses an AppDir holding anything but the launcher, the kit, the importer's
scripts and C sources (and checks that what a Tekken 8 import needs is there), the desktop entry and the icon (nothing of the game, no tests, no
Python caches), adds `AppRun` (it only starts `usr/bin/ttt2-launcher`: no
`LD_LIBRARY_PATH`, as the compiler, Python, gamescope, Proton and the game
it starts must not load anything of the AppImage), the desktop entry, the
icon and `.DirIcon` at the AppDir's root, and packs it as zstd squashfs
behind the AppImage type 2 runtime (downloaded once to `--runtime-cache DIR`,
`$TTT2_APPIMAGE_CACHE` or `BUILD_DIR/appimage-cache`, and checked to be an
x86-64 ELF program; the runtime reads a file back before the image is put
in place). Its programs are linked with LLD: GNU ld copies the ISA level the
system's `Scrt1.o` is marked with into every program, and on a system built
for its own processor (CachyOS's znver4 packages) that is x86-64-v4, which
glibc refuses to start on a processor without AVX-512 ("CPU ISA level is
lower than required", a Steam Deck's Zen 2); LLD writes none, and the script
refuses an AppDir with any file marked above the baseline. Nor may any
file hold an AVX-512 instruction: such a system's own static libraries are
compiled for its processor (the kit's programs once linked CachyOS's
x86-64-v4 `libstdc++.a` and `libgcc_eh.a`, and a Steam Deck stopped them at
start-up with SIGILL, "exit code 132"), so the kit's programs use the
system's libstdc++, like the launcher. cafe-recomp is C++23: GCC 16's
libstdc++ declares `std::format`'s code an extern template only in C++20,
which made C++20 programs need GCC 16's libstdc++. The launcher is held to
the API of GTK 4.10 and the GLib it needs (2.76), and the script refuses
any of the programs, and the game program as the kit links it
(`kit_check`), that needs a newer glibc or libstdc++ than Ubuntu 24.04 has
(2.39, GCC 14's). Now the launcher needs glibc 2.38 and GCC 13's libstdc++,
and the game program glibc 2.38 and GCC 13.2's (`kit.ini`'s `needs`); the
kit's programs need libstdc++ (as the launcher), libcrypto 3, zstd and zlib,
which such distributions all have. (GCC 16's libstdc++ exports std::string's C++20 members, so a
call to one that is not inlined makes a program need it: `install.cpp`
calls string_view's.) It is about 4 MB.

Still to do for an AppImage for any distribution: ship SDL 3 (Ubuntu 24.04
has none; any 3.2 or newer will do) and shaderc in the kit for the game
program (link those, copy them to `<install>/lib/` with a mark that
uninstall then deletes it by, as it leaves any `lib/` alone now, and add an
`$ORIGIN/lib` rpath); bundle GTK 4 and GLib, and once AppRun sets
`LD_LIBRARY_PATH` or GTK and GIO variables for them, restore those for the
programs the launcher starts, as the compiler, Python and the game must not
load the AppImage's libraries (and ttt2-build would give the game a run path into
the AppImage for a library it found through `LD_LIBRARY_PATH`). The
player's compiler cannot be bundled.

## Running the port

`build/ttt2 "<path>/TEKKEN TAG 2 Wii U EDITION (EU).wua"` reads the
executable and all assets from the archive in place (a directory with
code/, content/, meta/ also works). Reading through the archive costs
nothing measurable in play (`TTT2_TRACE_FS=1`): a fight reads ~0.5 MB of
music per 10 s (0.3 ms), loading a stage ~95 MB (0.5 s from a hard disk,
mostly seeks).

`ttt2 --install [GAME [FOLDER]] [--no-launcher]` (`install.cpp`) installs
the port like other programs: the game's `.wua` and the install folder
come from the desktop's file dialogs (SDL3, the XDG desktop portal; they
may open behind the active window, see the taskbar), from a terminal
prompt when there are none, or from the arguments. A chosen folder that
is empty, new or an earlier install is the install folder; any other gets
a "Tekken Tag Tournament 2" folder inside. The game is checked against
the RPX hash the port was generated from before anything is copied, and
against the free space. The install folder gets `game/` (code/,
content/, meta/; 15.9 GB, ~4 minutes from a hard disk), the executable
named "Tekken Tag Tournament 2" (what users see; `ttt2` stays the build's name),
`icon.png` (meta/iconTex.tga) and `.ttt2-install`, written last;
`$XDG_CONFIG_HOME/ttt2/installed` names the folder, and
`$XDG_DATA_HOME/applications/ttt2.desktop` puts it in the application menu
(the window's Wayland app id is `ttt2`, so it gets that entry's icon). Files
are copied through `<name>.part` and renamed when complete, so an
interrupted install resumes; files already there are kept, so a file
replaced for a mod survives installing again (deleting one restores it).
`ttt2` without arguments runs the game next to the executable or, failing
that, the recorded install; `ttt2 --update [FOLDER]` copies a rebuilt
executable into the install. Saves go to `$TTT2_SAVE_DIR`, default
`~/.local/share/ttt2/save`. The OS layer is in `runtime/src/os/`; each OS
function is plain C++ registered with `CAFE_EXPORT(module, name, fn)`, and
anything not implemented stops with the function's name and a guest
backtrace. Iterating on the runtime rebuilds and relinks in ~2 s.

The window shows the TV image (F11 toggles fullscreen; display.ini, below,
says how it starts). Keyboard, by default: W/A/S/D the D-pad up, left,
down, right; face buttons by place, I top (the Wii U's X), J left (Y), K
bottom (B), L right (A); H/`;` L/R, U/O ZL/ZR, Enter +, Backspace −, Home
HOME, the arrows the left stick; SDL gamepads map by button position. Keys
are SDL scancodes (USB HID usages: a key's place on the keyboard, whatever
its layout prints on it), taken from `$XDG_CONFIG_HOME/ttt2/keyboard.ini`
(`~/.config` when the variable is unset or not absolute) by
`runtime/src/host/keymap.cpp`. The launcher's Settings write that file
whole (a temporary file renamed over it); by hand it is one `input = key`
per line, the inputs `dpad_up`, `dpad_down`, `dpad_left`, `dpad_right`,
`face_top`, `face_bottom`, `face_left`, `face_right` (X, B, Y and A, by
place), `l`, `r`, `zl`, `zr`, `stick_up`, `stick_down`, `stick_left`,
`stick_right`, `plus`, `minus` and `home`. A key is a decimal scancode
(4 to 511) or SDL's name for one
(`SDL_GetScancodeFromName`, in any case: `Z`, `Return`, `Left Shift`, `Menu`).
Digits are always a scancode: the digit keys only as numbers (the 1 key is
30, the 5 key 34), and `5` is the B key. `#` starts a comment at the start
of a line or after a space (also a tab, `\r`, `\v` or `\f`, which count as
spaces), so SDL's `#` and `Keypad #` must be given as numbers, 50 and 204. Unknown inputs, bad keys and the
reserved F11, Escape and GUI keys are left out with a warning, keeping that
input's default; of an input given twice the later line counts, and one key
on two inputs presses both. The window's loop stats the file about once a
second and reads it again when it changed (another inode, size or time), so
keys changed in the launcher apply while the game runs; each read logs
`ttt2: keyboard: <n> of 19 keys from <file>` (or `keyboard: defaults (no
<file>)`); only a regular file of at most 64 KiB is read. Keys typed by a
Steam controller's keyboard device are ignored (Steam types Enter for its A,
which would be +), and F11 held toggles fullscreen once. The launcher reads
the file as the game does (it knows all of SDL's key names, and shows a key
it cannot take from the keyboard by SDL's name or its number); where the
file gives one key to two inputs, which it cannot show, its Settings page
says so, gives each input a key of its own and saves that when a key is
chosen or Restore Defaults pressed. There a key is taken when pressed, but
Ctrl, Shift and Alt alone only once let go (with another key they are a
shortcut, which stops choosing), and the keys' labels follow the keyboard's
layout (GTK 4.18's, else that of the last key pressed that every layout
defines). Saving writes through a link to where it leads, keeping that
file's mode.

**Players** (`host/window.cpp`, `os/input.cpp`, `title/controllers.cpp`).
The title takes one player's input from the controller that pressed + on
its title screen (a Pro Controller cannot move the menus the GamePad
opened), so the keyboard and every gamepad drive the GamePad, as one
player's, everywhere but in the modes for several players. Those (VS
Battle, Team Battle, Pair Play) begin on a player entry screen ("Press the
controller's +"), which the title builds for the Wii U's GamePad, Pro
Controllers and Wii Remotes. There the first device to press + takes the
GamePad and every other one that presses + the next Pro Controller, and
each player drives only their own; devices that have not pressed + drive
the GamePad until it is taken. The title offers VS Battle and Pair Play
only while a controller other than the GamePad is connected, so each
device beyond the first (the keyboard counts) keeps a Pro Controller
connected, idle until a device takes it. Every offline mode loads the screen's
layouts (data007 794FFCD9 and FA2AD1D0) as it starts, which begins a
session; the mode manager (`*(*(*0x10872CB8 + 228) + 228)`, its kind at
+444) tells the rest. VS Battle shows the screen inside its mode (kind 9);
Team Battle and Pair Play show it with no mode, and start theirs (14, and
0 as Arcade) once the players have joined; the other modes start at once
(Arcade 0, Practice 4 and 5, Survival 10, Time Attack 11, Ghost Battle 12)
with no one joined, which ends the session. When the menus are back (kind
6) every device drives the GamePad again and the Pro Controllers
disconnect. A press of + by a second device within 100 ms of one that took
a controller takes none (a controller that shows as two devices, as beside
Steam's virtual gamepad). The title reads
the Pro Controllers with `KPADReadEx` (`KPADStatus`, 0xF0 bytes: the
extension's kind at 0x5C, 0x1F for a Pro Controller, which it counts as
device kind 14; WPAD's data format at 0x5F, 22; the buttons by WPAD's
Pro Controller bits from 0x60, the sticks from 0x6C); a Pro Controller just
connected shows no buttons for three reads, so that the title has seen it
connect before the + that connected it (held for four reads after). Its
WPAD calls (`WPADRead`, `WPADProbe`) belong to an older library of the
title's (core Wii Remote, Nunchuk and Classic Controller only) that
nothing runs.

How the game starts comes from `$XDG_CONFIG_HOME/ttt2/display.ini` (the
same folder rule), read once by `open_window` before the window is made
(`runtime/src/host/display_settings.cpp`, without SDL: the launcher builds
the same file into its core, so what its Settings write is what the game
reads), so a change applies at the next start. It is one `name = value`
per line, `#` starting a comment as in keyboard.ini: `fullscreen = yes` or
`no` (default no; fullscreen keeps the desktop's mode), `resolution =
auto`, `1280x720`, `1920x1080`, `2560x1440`, `3840x2160` or `5120x2880`
(the render scale 1, 1.5, 2, 3 or 4; default auto, the scale that covers
the primary display's height in pixels) and `interpolation = yes` or `no`
(default yes: 120 frames a second when the primary display or the one the
window opens on refreshes at 100 Hz or more, compared exactly, 60 below;
no: 60 always) and `input_delay = yes` or `no` (default no: fighters act on
a button in the frame the game reads it; yes: two frames later, as the Wii
U game does; see [Input delay](#input-delay)).
Booleans also take `true`/`false`, `on`/`off` and `1`/`0`, and values (not
names) may be in any case; an unknown name or a bad value is left out with
a warning, keeping that setting's default, and of a name given twice the
later line counts. Only a regular file of at most 64 KiB is read; one that
cannot be means the defaults. `TTT2_FULLSCREEN` (`1` fullscreen, another
value windowed), `TTT2_SCALE` (1, 1.5, 2, 3 or 4), `TTT2_FPS` and
`TTT2_INPUT_DELAY` (0 to 15 frames) win over the file when set and not
empty, and a value they cannot use is left out with a line in the log.
The window opens at the render size (in the
desktop's units: pixels over its scale) when that leaves at least 64 units
across and 128 down free on the primary display, otherwise at the largest
multiple of 640x360 that does (at least 640x360; Automatic always so). The
game logs `ttt2: display: fullscreen no, resolution auto, interpolation yes,
input delay no (from <file>)` (or `display: defaults (no <file>)`), a line
per variable set, `ttt2: window: <w>x<h> pixels, windowed` and `ttt2: GPU:
rendering at <w>x<h> (scale <s>)`. The launcher's Settings show the four
above the keys, in a Game section: Fullscreen and 120 fps switches, a
Resolution list (Automatic, 1280 × 720 ... 5120 × 2880, as wide as its
widest item whichever is chosen) and an Input delay switch. Under them it
says what the game will do only as far as it can be sure, since GTK cannot name the primary
display on Wayland (`automatic_note` and `refresh_note` in
`launcher/core/display.h`). With one monitor: the size Automatic gives on
it (its height in pixels from GTK 4.14's fractional scale; before 4.14
only a whole scale factor of 1 counts, as fractional scaling rounds the
factor up, otherwise no size is named) and, when it reports a refresh rate
below 100 Hz by the game's exact rule, that the game stays at 60 fps (a
rate just below is shown with decimals, "99.98 Hz", never as 100). With
several: "enough to cover the main display" without a size, and the 60 fps
note only when every monitor reports a rate below 100 Hz (it gives the
highest). The monitors are read again each time the page opens and when
one is added or removed. The page reads the file each time it opens and
writes it whole whenever a control changes, as keyboard.ini (a temporary
file renamed over it, through a link, keeping its mode); when that fails
it shows why and puts the control back, and a file that is there but
cannot be read gets a note saying the game uses the defaults.

`TTT2_GPU=null` runs headless without a window. Sound plays on the
default output device; `TTT2_AUDIO=0` disables it and
`TTT2_AUDIO_VOLUME=<percent>` scales it.

Unattended runs press buttons with `TTT2_INPUT_SCRIPT`. From a cold start
this reaches an arcade match (solo, Heihachi) at about 72 s; append
presses such as `,72:y,73:x,...` to fight:
`TTT2_INPUT_SCRIPT="8:plus,21:plus,24:plus,31:a,37:a,41:right,42:right,43:right,45:a,49:right,50:right,53:a,57:a"`.
Character select refuses a character already picked for the team. An item
`@<name hash>` waits until the title first reads that archive entry and
times after it count from then, presses before it that have not come yet
being dropped, so scripts do not drift with loading times (screens'
entries: `TTT2_TRACE_ENTRIES=1`).

A guest memory fault prints the guest registers and backtrace, says when
the address lies just below the stack pointer (a stack overflow), and
gives the host code offset, which `addr2line -f -e build/ttt2
<offset>` turns into the guest function. The main thread gets at least a
2 MB stack whatever the RPX asks for (TTT2's says 64 KB, but its menus
nest two functions with 501 KB frames).

Debugging: every guest function is a native function (`sub_XXXXXXXX_orig`),
so gdb breakpoints, watchpoints and backtraces work on guest code directly;
host threads are named `<OSThread address>/<core>`. The export thunks take
`(PPCContext&, uint8_t* base)`, so `$rsi` in any `imp_*` frame is the guest
base address. `TTT2_TRACE_THREADS=1` logs thread creation, priorities,
affinities and names. The GPU backends print frames per second and draws
per frame every ten seconds. The captures, dumps and traces below hold the
game's own images, shaders and sounds: write them under `local/`, which Git
ignores. Renderer debugging:

| Variable | Effect |
| --- | --- |
| `TTT2_CAPTURE=<dir>` | TV/GamePad images as PNG every `TTT2_CAPTURE_INTERVAL` seconds (default 5) |
| `TTT2_CAPTURE_SEQUENCE=<n>` | with `TTT2_CAPTURE`, also every image shown for the next n frames after each capture, in order (`seq_<capture>_<frame>_<n>.png`, the real image last) |
| `TTT2_TRACE_AT=<s>`, `TTT2_TRACE_FRAME=<n>` | log every command of one frame; with `TTT2_CAPTURE`, save all its render targets |
| `TTT2_INPUT_SCRIPT="25:plus,26.5:a"` | press GamePad buttons at given seconds, for unattended runs (`@<hash>` items wait for an archive entry; `30:plus#2` presses on Pro Controller 1, `#3`-`#5` the others, connected for the run) |
| `TTT2_TRACE_ENTRIES=1` | every archive entry the title reads, with times |
| `TTT2_TRACE_ROSTER=1` | the added fighter's entries |
| `TTT2_DUMP_SHADERS=<dir>` | shader binaries, draw registers and generated GLSL |
| `TTT2_DUMP_TEXTURES=<dir>` | every texture loaded from memory, as PNG |
| `TTT2_TRACE_TARGETS=1`, `TTT2_WATCH=<hex address>` | render target creation; writes and loads touching an address |
| `TTT2_CHECK_TILING=1` | compare fast detiling with addrlib per element |
| `TTT2_SCALE=1/1.5/2/3/4` | render scale of screen-sized targets (over display.ini's resolution; default from the display) |
| `TTT2_FPS=60/120/180/240` | frames shown per second (over display.ini's interpolation; default 120 on displays of 100 Hz and more) |
| `TTT2_INTERP_TEST=1` | replays without blending: extra frames must equal real ones |
| `TTT2_INTERP_2D=1` | blend flat (not depth-tested) draws too |
| `TTT2_PRESENT_TIMED=1` | present at chosen times instead of at every refresh |
| `TTT2_PRESENT_QUEUE=1..4` | presents kept ahead of the screen when presenting every refresh (default about 8 ms of refreshes) |
| `TTT2_DISPLAY_HZ=<hz>` | report this refresh rate for the window's display (tests the rate check) |
| `TTT2_FULLSCREEN=1` | start fullscreen (another value: windowed; over display.ini) |
| `TTT2_INPUT_DELAY=0..15` | frames a fighter waits before acting on a button, in place of the game's own 2 (over display.ini's input_delay) |
| `TTT2_TRACE_INTERP=1`, `TTT2_TRACE_PACING=1` | draw matching, carried targets; frame readiness, swap times after the vblank |
| `TTT2_PROFILE_AT=<s>` | GPU time of every operation of one frame |
| `TTT2_SHADOWS=0/1` | stream-out output and its draws' constants read in place (0) or from copies in video memory (1; the default on discrete GPUs) |
| `TTT2_SHADOW_CHECK=1/2` | compare those copies with guest memory after each frame (2: also draw the stream-out draws the old way, into guest memory) |
| `TTT2_VK_VALIDATION=1` | Khronos validation layer, if installed (synchronization checks: `khronos_validation.validate_sync = true` in a file named by `VK_LAYER_SETTINGS_PATH`) |
| `TTT2_AUDIO_DUMP=<file.wav>` | everything played, as 48 kHz stereo WAV (also without a device) |
| `TTT2_TRACE_AX=1` | voice set-up, device mixes, output level |
| `TTT2_TRACE_FS=1` | file and save opens, reads and writes, with times |
| `TTT2_TRACE_TEXTURES=1` | every texture loaded from memory once, with the MD5 a replacement names |
| `TTT2_TRACE_PRESENTATION=1` | how long the icons, texts and logo took to prepare |
| `TTT2_TRACE_PRACTICE=1` | each position reset in Practice |
| `TTT2_TRACE_INPUT_DELAY=1` | each input delay the fighters' queues get (a mode's start, Practice's Input Delay) |
| `TTT2_CONTROLLER=playstation/nintendo/xbox` | icons and menu buttons for this kind of controller |
| `TTT2_DEVICES=keyboard,playstation,...` | the devices the controller pictures show, for the GamePad and Pro Controllers 1-4 (`keyboard`, `playstation`, `xbox`, `nintendo`) |
| `TTT2_TRACE_PLAYERS=1` | modes for several players starting and ending, and each device taking a controller |

The launcher (`launcher/app`, `ttt2-launcher`) runs by itself for tests,
through the same code as its buttons (only the file pickers and the
confirmations are left out); `--screenshot FILE` saves its window once it
has loaded, then quits:

| Variable | Effect |
| --- | --- |
| `TTT2_LAUNCHER_TEST_ACTIONS="install:<GAME>:<FOLDER>;add:kazumi;quit"` | actions one after another, each once the one before has ended: `install:<GAME>:<FOLDER>`, `update`, `add:<name>[,<name>...]`, `add-all-base`, `add-all-owned`, `remove:<name>`, `uninstall:keep`, `uninstall:all`, `play` (ends once the game has run 3 s), `quit`, `add-all:<game>` and `remove-all:<game>` (a game's Add All and Remove All, `tekken7` or `tekken8`, the latter without its question), and `expand-dlc`, `expand-log`, `show-uninstall`, `wait:<seconds>`, `focus:<id>` (the keyboard focus on `play`, `uninstall`, `fighter:<name>`, `add-all`, `dlc` ...) and `refresh` (logs the id focused afterwards); for Settings `settings` (opens it through the gear), `back`, `bind:<input>:<XKB keycode>[+<XKB keycode>...]` (that input's key clicked unless it waits for one already, then those keys pressed one after another and let go the other way round through the window's key handler, e.g. `bind:face_bottom:39` gives it S, `bind:zl:64` Left Alt, `bind:zl:64+23` is Alt+Tab, which stops choosing; a refused key, Esc and a shortcut log `failed` with the reason) and `reset-keys` (Restore Defaults), and for its Game section `fullscreen:yes`/`no`, `interpolation:yes`/`no`, `input-delay:yes`/`no` and `resolution:<value>` (a value of display.ini's `resolution`, in any case: `auto`, `1920x1080` ...), each setting that switch or list as a click does, which saves display.ini, then reading the file back (`ok` when it holds what was set; the text is what it holds, or why it could not be saved); each logs `@test <action> ok\|failed <why>` to stderr |
| `TTT2_LAUNCHER_TEST_SHOTS=<dir>` | the window as `<dir>/NN-<action>.png` after each action (`00-start.png` first, `NN-<action>-running.png` half-way through its task) |
| `TTT2_LAUNCHER_TEST_PAGE=1` | also all of the window's content, scrolled into view or not, as `...-page.png` |
| `TTT2_LAUNCHER_TEST_SCALE=2`, `TTT2_LAUNCHER_TEST_SIZE=<w>x<h>` | pictures at twice the scale; the window's size |
| `TTT2_LAUNCHER_TEST_CANCEL=<0..1>` | press Cancel once a task's progress is that far (`-1`: at its first step), saving `NN-<action>-stopping.png` |
| `TTT2_LAUNCHER_TEST_CANCEL_FILE=<file>` | press Cancel once that file exists (a script watching the task makes it, e.g. once the hidden Tekken 7 or Tekken 8 runs), saving `NN-<action>-stopping.png` |
| `TTT2_KIT`, `TTT2_IMPORTER`, `TTT2_PYTHON` | the builder's kit, the importer (`tools/characters`) and Python the launcher uses (default: installed beside it, else the build and source trees it was built from unless `TTT2_LAUNCHER_BUILD_TREE_PATHS=OFF`, and `python3`) |

## Verification

- Per-instruction differential tests (`build/tests/semantics_test`, done):
  `cafe-semgen` samples up to 48 real encodings of every non-control-flow
  instruction variant in the game (6,753 encodings); each runs on 300 random
  machine states (edge integers, NaNs, infinities, denormals, random GQR
  formats) and must match Dolphin's Broadway interpreter bit for bit in every
  register and in memory. Dolphin is built from `third_party/ref` against a
  shim (`tests/oracle/`; its `Interpreter.h` and `PowerPC.h` are derived from
  the checkout at configure time) and is a test-only dependency: the test
  programs contain GPL-2.0-or-later code and are not distributed. Result 2026-10-01: 0
  mismatches. One oracle correction: Dolphin's `addme`/`subfme` carry is
  wrong when CA=1 (architecture and Cemu agree on CA=1); the test documents it.
  Branches, `lwarx`/`stwcx.`, `dcbz` and traps are not covered by it yet.
- Reference checkouts (sparse, read-only, never shipped; the README's Tests
  section has the commands for Dolphin's, a non-cone sparse checkout), at
  these revisions:
  Dolphin `771fb154059c5812d6a715a23226249cc42877a2` into
  `third_party/ref/dolphin` (Source/Core/Core/PowerPC/Interpreter,
  Gekko.h, PowerPC.h, ConditionRegister.*, Common/{BitField,BitUtils,
  CommonTypes,FloatUtils,Inline,Swap}); Cemu (MPL-2.0)
  `0a2b6ff7db61871b0dd028ac47dc72eda94351a1` into `third_party/ref/cemu`
  (src/Cafe/HW/Espresso/Interpreter, src/Cafe/HW/Latte/{ISA,Core,LatteAddrLib},
  src/Cafe/OS/libs/{coreinit,gx2,snd_core,dmae,swkbd,erreula,...});
  decaf-emu (GPL-3.0) `e6c528a20a41c34e0f9eb91dd3da40f119db2dee` into
  `third_party/ref/decaf` (src/libdecaf/src/cafe/libraries/{gx2,swkbd,erreula},
  src/libgpu/latte, src/libgpu/src). Where the two disagree, Cemu's
  behaviour was preferred because it runs this title.
- `build/tests/memory_model_test`: guest polling loops, compiled as the
  generator emits them with the port's flags, must wait for and then see
  another thread's store (fails against plain loads; passes).
- Per-function differential tests on the real image.
- Later: function-entry/exit traces from the game running in Cemu (test oracle
  only) compared with the port.
- Acceptance is behavioural: boots, menus, an offline match, saves, and long
  runs without divergence. A window opening is not acceptance.

## Milestones

| | Milestone | Exit criterion |
| --- | --- | --- |
| M0 | Loader, decoder, census | Done 2026-10-01 |
| M1 | Code generator for the full ISA | Done 2026-10-01: all 205,200 entries compile (`--all`, 14 min); semantics and control-flow tests pass with 0 mismatches |
| M2 | Runtime core, boot | Done 2026-10-01: the game runs its main loop at a steady 59.9 frames/s (vsync-paced) on the null GPU backend, every static import implemented |
| M3 | GX2 → Vulkan | Done 2026-10-01: intro movie, logos, title screen, attract-mode fights, main menu and character select render correctly at ~58 frames/s |
| M4 | Input, audio, filesystem, saves | Done 2026-10-02: menus and character select navigate, sound plays (checked from WAV dumps: content, levels, no buffer underruns), saves load and persist (the battle record survives a restart) |
| M5 | Gameplay | Reached with scripted input 2026-10-02: an arcade match from character select through both rounds, K.O., continue and game over, back to the menu with the record updated. Confirmed by hand 2026-10-05: a whole arcade mode played through |
| M6 | Hardening | All stages/characters, long runs, performance |
