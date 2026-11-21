# Windows performance changes

Changes to the renderer and the runtime that remove the stutter the
Windows build showed the first time a scene, a stage or a fighter appeared,
and shorten the hitches at scene changes. Nothing here changes how the game
plays: the translated code computes the same results, and draws only wait
or are skipped while a shader is still being built.

Measured on Windows 11 with an RTX 5070 Laptop GPU (NVIDIA driver, discrete
GPU mode), a Core Ultra 9 275HX, 2560x1440 (scale 2), from the `ttt2: gpu:`
statistics and the new `slow frame` lines (below):

| | Before | After |
| --- | --- | --- |
| First fight with shaders not seen before | 15 frames/s over ten seconds, single frames of 1-6 s | 57-60 frames/s; new shaders cost a draw skipped for a frame or two |
| Start-up with shaders seen in earlier runs | every shader translated and every pipeline created again at its first draw | 300-370 pipelines created before the title draws, in 40-90 ms on 8 threads |
| Scene change whose shaders were all on disk | 190 ms (a quarter of it opening SPIR-V files) | 48 ms |
| Scene changes (the title's own work) | 98-102 ms | 61-67 ms |
| `pipelines.bin` (30 MB) saved | on the command processor's thread, every ten seconds while pipelines were made | on a thread of its own |

What is left of the scene-change hitches is the title's own work, on its
main thread and a loading thread (setting up the entering fighters'
animations and skeletons, under `sub_069DEEBC`); the Xbox 360 recompilation
of the game shows the same frames (150 ms of its main thread in places).

## Background shader and pipeline builds

`runtime/src/gpu/vulkan/draw.cpp`

Translating a shader, compiling its GLSL (shaderc) and creating a pipeline
(the driver compiles it for the GPU) took milliseconds to tens of
milliseconds each, on the command processor's thread, in the draw that
needed it; a fight's first frames need dozens. They are now built by a few
worker threads (`BuildQueue`, a third of the logical processors, at most 8).
A draw whose shader or pipeline is not ready waits for it within a budget per
title frame (6 ms; `TTT2_BUILD_BUDGET_MS`), and past that it is skipped until
the build lands, a frame or two later. Stream-out draws (the fighters'
skinning, whose output later frames read) always wait. Modules are still
shared by the shader keys that translate alike, and a translation being
compiled is compiled once for all of them. `TTT2_ASYNC_BUILDS=0` waits for
every build, as before.

## Start-up warm-up (`warm.bin`)

Every shader key (with its translation's interface, `TranslatedShader`
without the GLSL) and every pipeline (its `PipelineKey`, naming its shaders
by key) the renderer makes is recorded, and written with `pipelines.bin` to
`warm.bin` in the cache directory. At the next start the renderer creates
them all again before the title draws: the modules from the SPIR-V cache,
the pipelines on several threads from the driver's `pipelines.bin`. A draw
then finds its shader by key without translating it. The records are valid
for one version of the shader translator: CMake hashes `runtime/src/latte/*`
into `TTT2_TRANSLATOR_HASH`, and records made by another translator are
ignored and made again (without the hash, the executable's size and time
stand in). `TTT2_WARM_UP=0` turns it off.

## SPIR-V cache in memory

A thread reads the SPIR-V cache folder into memory at start-up. Opening one
small file per shader on the command processor's thread cost a quarter of a
190 ms scene change on Windows (a file open takes milliseconds there, more
with a virus scanner looking), and so did each open of a file that is not
there; once the folder is read, a shader not in memory is not on disk.

## Texture eviction time

`TTT2_EVICT_SECONDS` sets how long a texture or target may stay unbound
before it is freed (30 s by default, as before). Textures made again after
an eviction are uploaded and detiled on the command processor's thread; with
video memory to spare, a longer time (600 s) keeps a scene change from
making dozens again at once.

## Paired-single loads and stores inline

`runtime/include/cafe/ppc_ops.h`

`psq_load` and `psq_store` were kept out of line by the compiler because of
the switch over the quantized types: a call per `psq_l` / `psq_st`, 20-30 %
of the CPU time in some scene changes. The float type (GQR type 0, and the
reserved 1-3 treated as float), which the title almost always uses, is now
inline at every use, and the quantized types (4-7) are in
`psq_load_quantized` / `psq_store_quantized`, out of line. The results are
the same: the same loads and stores in the same order, through the same
`load_single` and `store_single_ftz`. `memory_model_test` passes.

## Windows timer resolution

`runtime/src/host/perf.cpp`, called first in `main`

A process that does not ask for it gets Windows' ~15.6 ms timer, and the
runtime's short sleeps (the command processor's `WAIT_REG_MEM` poll of
20 us, the presenter's waits, `OSSleepTicks`) lasted up to that long. The
game now asks for 1 ms (`timeBeginPeriod`, looked up in winmm) and opts out
of Windows 11's power throttling, which can ignore it for an occluded window
or on battery. `TTT2_TIMER_RES=0` leaves the default. The `WAIT_REG_MEM`
poll also yields for its first 0.25 ms before it sleeps.

## Presentation mode

`runtime/src/gpu/vulkan/present.cpp`

`TTT2_PRESENT_MODE=fifo|mailbox|immediate` chooses the swapchain's mode when
frames are presented at times (the default stays mailbox). FIFO is the mode
variable refresh (G-SYNC, FreeSync) follows: on a display whose rate is not
a multiple of 60 (165 Hz is common on laptops) the frames presented at their
times are then shown as they come, evenly.

## Diagnostics

- `ttt2: gpu: slow frame N: X ms between swaps; translating shaders, waiting
  for builds, textures, render targets ...; the rest the title's own work or
  the GPU`: logged for every title frame over 40 ms between swaps (at most
  400), with where the command processor's thread spent it.
- `ttt2: gpu: builds: ... shaders compiled, ... pipelines created in the
  background; ... draws skipped while they ran`: with the 10 s statistics,
  when any were.
- `TTT2_PROFILE_CPU=1` (Windows): a sampling profiler
  (`runtime/src/diagnostics.cpp`). Every millisecond each tracked thread
  that ran for most of it is stopped for a moment and its stack is unwound
  with the executable's unwind tables; `slow frame` lines and the 10 s
  statistics are followed by `ttt2: profile:` lines naming the functions
  their samples were in, by themselves and with what they called, as
  addresses at the executable's default base (`llvm-symbolizer
  --obj=ttt2-ultimate.exe 0x...` names them: `sub_XXXXXXXX` is the title's
  function at `XXXXXXXX`).

## Environment variables

| Variable | Effect |
| --- | --- |
| `TTT2_ASYNC_BUILDS=0` | build every shader and pipeline in the draw that needs it |
| `TTT2_BUILD_BUDGET_MS=<ms>` | how long a title frame waits for background builds before skipping draws (6) |
| `TTT2_WARM_UP=0` | no start-up warm-up from `warm.bin` |
| `TTT2_EVICT_SECONDS=<s>` | time before an unbound texture or target is freed (30) |
| `TTT2_TIMER_RES=0` | keep Windows' default timer resolution |
| `TTT2_PRESENT_MODE=fifo\|mailbox\|immediate` | swapchain mode when presenting at times |
| `TTT2_PROFILE_CPU=1` | sampling profiler of the game's threads (Windows) |

## Not done

- Most of the remaining scene-change time is the title's animation set-up;
  replacing those functions natively would have to reproduce the
  processor's float arithmetic exactly, as the fighters' hit spheres come
  from the same skeletons.
- On a discrete GPU a fight frame still takes 7-8 ms of GPU time at 1440p
  on this laptop (3.3 ms on RADV, per `ARCHITECTURE.md`), from vertex data
  and constants read in place from imported host memory; enough for 60
  frames/s, tight for 120 alongside other GPU work.
- Linux was not built or tested with these changes; the Windows-only parts
  are behind `_WIN32`, and the rest is plain C++20 and Vulkan.
