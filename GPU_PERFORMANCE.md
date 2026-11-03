# Issue #15: CPU command-processing investigation

Source: NexusSecret/Tekken-Tag-2-Ultimate-Edition at
`f4fc20bd447745396b64b838ad928ff8d55c3204` (fork of Petexy).
Issue: https://github.com/Petexy/Tekken-Tag-2-Ultimate-Edition/issues/15
reports about 23 FPS and a CPU thread named `gpu` at 99%. The Steam Deck
observations supplied for this investigation are consistent with a CPU-side
submission bottleneck. No Deck capture or gameplay benchmark was available
in this workspace, so the ranking below is a source-based hypothesis, not a
measured attribution or a demonstrated FPS improvement.

## Architecture and ordering

Reviewed `docs/ARCHITECTURE.md`: Runtime, GX2 and the GPU, Latte shaders,
Vulkan renderer, interpolation, presentation, and runtime diagnostics.

1. Guest threads are native host threads. `gx2/cbpool.cpp::submit_main`,
   `flush`, and `GX2DirectCallDisplayList` submit big-endian PM4 in guest
   memory through `gpu::submit`. Ring reuse waits for retired timestamps.
2. `gpu/command_processor.cpp::command_processor_main` names its host thread
   **gpu**. It drains CPU-write notifications, then `execute` and
   `execute_packet` decode PM4, follow indirect buffers, update/shadow Latte
   registers, and call Backend operations directly. There is no intervening
   renderer worker or separate process.
3. `vulkan/draw.cpp::Renderer::draw` constructs shader environments, resolves
   targets/textures/samplers, looks up shaders/pipelines, builds constants and
   indices, pushes descriptors, sets dynamic state, and records draws on gpu.
   `shader` decodes/translates Latte to GLSL, loads cached SPIR-V or calls
   shaderc, and creates modules on first use. `pipeline` calls
   `vkCreateGraphicsPipelines` on misses. Disk caches reduce subsequent work;
   they do not move misses off the command thread.
4. `vulkan/renderer.cpp::submit` ends rendering, records target readbacks,
   ends the command buffer, and calls `vkQueueSubmit` under `queue_mutex_`.
   It runs at submitted-buffer boundaries and end-of-pipe events as well as
   renderer-driven flushes. Small guest submissions may multiply overhead.
5. `command_processor.cpp::retirement_main` (**gpu retire**) waits on the
   Vulkan timeline, calls `Renderer::retired` to tile staging readbacks into
   guest memory, then publishes timestamps/EOP memory writes/frame readiness
   in FIFO order under the required kernel synchronization.
6. `vulkan/present.cpp::presenter_main` (**present**) handles presentation and
   refresh pacing, using a compute presentation queue when available, with a
   shared rendering-queue fallback. `gpu/display.cpp` handles guest vblanks
   and flips under the kernel lock. SDL event handling is on the main thread.

The architecture's statement that the command processor "never waits" is an
intent, not an unconditional property: slot reuse and upload-ring reuse call
`wait_value`; presentation-image acquisition can wait; WAIT_REG_MEM polls
with 20 microsecond sleeps. Synchronous debug capture also waits. These must
be measured rather than assumed to explain 100% CPU usage.

## Likely bottlenecks and serial work

| Priority | Candidate on gpu | Evidence / qualification |
| --- | --- | --- |
| 1 | Steady per-draw CPU work | `draw`: builds both shader environments, reconstructs/hash-checks pipeline state, walks resource slots, prepares constants and endian-converted indices, allocates a descriptor-write vector and pushes descriptors each draw. Most dynamic state is emitted every draw; pipeline binding is already cached. Existing program/shader/pipeline/texture caches and direct imported guest buffers must be preserved. |
| 2 | Texture validation/conversion | `textures.cpp::load_texture` checks target aliases even on lookup, hashes complete dirty surfaces/mips, allocates temporary planes, detiles on CPU, and may compute replacement MD5/mips. `cpu_wrote` walks page maps and targets. Whole-cache SURFACE_SYNC is already ignored; indiscriminately removing invalidation is unsafe. Actual frequency is unknown. |
| 3 | Cold compilation and driver work | `draw.cpp::shader`, `pipeline`, `save_pipeline_cache`: synchronous translation, shaderc, Vulkan creation, disk reads/writes; likely stutter contributor, not yet evidence for persistent warm-cache 20–30 FPS. |
| 4 | Submission, waits, and locks | `renderer.cpp::cmd`, `upload`, `submit`, `wait_value`; `present.cpp::take_present_image`; PM4 WAIT_REG_MEM. Queue mutex can contend with fallback presentation. `targets.cpp::copy_write_backs` holds the writeback mutex while recording and possibly allocating staging buffers; retirement tiles outside that mutex. |
| 5 | Optional replay | `command_processor.cpp::replay_frame`, `interpolate.cpp`: frame logs, copied indices/constants, matching, and extra draws. Disabling interpolation should remove this component, as reported, so it cannot alone explain the symptom. |

`gx2/surface.cpp::GX2CopySurface` can call `tiling.cpp::copy_surface_memory`
synchronously on the **calling guest thread** for LINEAR_SPECIAL staging
copies; ordered backend copies run on gpu. Do not attribute every CPU copy
to gpu. `targets.cpp::copy_surface` also has a CPU-memory fallback.

Retirement and presentation already offload completion and pacing. Their
idle time is often correct: they cannot decode the mutable register stream
or publish guest-visible completion early. No general renderer worker pool
was found. Low utilization of these threads alone does not establish wasted
parallel capacity.

## Instrumentation in this pass

`gpu/cpu_profile.h`, enabled with `TTT2_CPU_PROFILE=1`, aggregates fixed-size
thread-local counters, with no per-event heap allocation or profiling mutex.
It reports calls, inclusive wall time, exclusive/self wall time, maximum
call wall time, queue high water sampled on dequeue, and submitted top-level
PM4 words (indirect-buffer words are not included). Reports identify host
thread hashes; use the scope labels or perf thread names to associate them.
Linux thread CPU time is sampled once per reporting interval, allowing
CPU consumption to be distinguished from wall time spent blocked/descheduled.
Scopes cover command cycles/queue idle/packets/replay, shader lookups/misses,
compilation, pipeline creation/cache persistence, draw/descriptors,
texture hashing/loading/target copies, detile/tile, command-buffer access,
upload, timeline waits, queue-lock acquisition/submit, retirement, and
presentation-image acquisition/present calls.

Nested times are inclusive; **do not sum inclusive rows**. Self time excludes
instrumented children, not all callees. Recursive packets can contribute
multiple inclusive durations. `draw` self includes remaining preparation,
state emission, and driver recording. `texture_load` counts lookups including
clean early exits, not actual uploads. `timeline_wait` includes counter-query
fast paths. `pipeline_create` counts misses, including failures. Queue high
water is sampled, not an exact global maximum. Present reports cover scoped
calls, not the entire presenter loop or its idle time. Intervals report when
an outer scope exits after at least two seconds; a stuck scope or fully idle
thread does not emit a live heartbeat. No exit flush is installed because
runtime workers are detached. Profile logging and clock reads perturb timing;
compare enabled and disabled captures.

### Reproducible Deck validation

- Build the same optimized revision and generated game code. Record CPU/GPU
  clocks, power cap, driver, display mode, scale, cache state, interpolation,
  scene, and fighter selection. Use the same replay/practice sequence.
- Warm up, then record at least 60 seconds with interpolation off at native
  scale: `TTT2_CPU_PROFILE=1 ./ttt2 <normal arguments> 2>cpu-profile.log`.
  Repeat without the flag to quantify profiler overhead. Repeat three times.
- Correlate existing renderer FPS/draws/GPU-busy/wait statistics with CPU
  profile windows. Capture `perf record -g -t <gpu TID> -- sleep 30` during
  gameplay to resolve large self-time rows into leaf functions/driver work.
- Capture a separate cold-cache run using an isolated XDG_CACHE_HOME; retain
  the normal cache. Compare shader_miss/compile/pipeline_create counts and
  latency with the warm run. Compare a lower scale at the same scene.
- Use `TTT2_PROFILE_AT=<seconds>` separately for existing Vulkan operation
  timestamps: that profiler explicitly waits and should not be the FPS baseline.
- High gpu thread CPU + draw/texture self time supports host preparation;
  high cp_idle suggests producer starvation; timeline/present waits suggest
  backpressure; growing retirement backlog with writeback_tile time suggests
  readback/completion pressure. Present acquisition includes image management
  and mutex waits, so use a scheduler/lock trace before blaming display pacing.
- Follow up only where needed: per-opcode counts, upload/hash bytes, actual
  cache-hit ratios, submission sizes, queue residence latency, and finer
  environment/index/state phases. These are not yet implemented counters.

## Ranked optimization candidates (safest to riskiest)

1. Replace bounded per-draw descriptor vectors with stack storage; reuse
   scratch plane/index storage where lifetimes are proven. Measure allocator
   samples and self time before/after. No ordering change.
2. Cache redundant dynamic-state emissions and shader environments using
   explicit dirty dependencies. Reset caches at command-buffer/pass boundaries;
   retain all alias/invalidation behavior. Compare rendered frames and Vulkan
   validation through menus, water, exposure, stream-out fighters and matches.
3. Reduce repeated dirty-range scans/hashing or duplicate detiling only with
   measured evidence. Preserve CPU writes, DMA, aliasing, mip and replacement
   generation semantics. Compare conversion outputs with TTT2_CHECK_TILING=1.
4. Move cache-file serialization off gpu using owned snapshots; prewarm known
   shaders/pipelines. Bound queue size and preserve driver/cache synchronization.
5. Async translation/compilation or detiling from immutable input snapshots,
   with ordered join before first use, explicit ownership and cancellation.
   Shaderc/compiler/cache objects and Vulkan resources cannot simply be shared.
   Never read mutable staging guest memory later without a lifetime guarantee.
6. Batch submissions or narrow barriers only with a dependency proof for EOP,
   guest timestamps, stream-out, readbacks, aliasing, and upload-ring reuse.
7. Parallel command recording/decoding is highest risk: register shadow state,
   resource writes/aliases, descriptor lifetimes, replay, and completion order
   span packets. Do not undertake it in this first pass.

The initial investigation pass made no performance optimization or scheduling change.
The first follow-up below removes a bounded per-draw allocation.
Benchmark each later candidate independently against baseline, recording FPS,
frame-time percentiles, gpu thread CPU, relevant scope times and correctness.

## Validation status

The profiler header and accounting test passed syntax checks with the available
Clang cross compiler (Linux target, warnings as errors). Full runtime build,
CTest execution, Vulkan validation and Deck benchmarks remain outstanding:
this Windows workspace has no configured POSIX build, third_party sources,
generated title code, or playable game assets. No FPS improvement is claimed.

## First optimization: descriptor scratch storage

`vulkan/draw.cpp::Renderer::draw` now stores descriptor writes in an
uninitialized `std::array` plus an active count instead of constructing and
reserving a vector on every draw. There are at most three uniform-buffer
writes and 18 texture writes per shader stage: 39 records. Only initialized
records up to the active count are passed to Vulkan. Buffer/image records,
bindings, descriptor order, and the push call are unchanged. Vulkan consumes
the input records during the call, so their existing stack lifetime suffices.

This removes one vector reserve/allocation and destruction/deallocation per
draw reaching the descriptor phase, including replay draws. It adds no cache,
thread, synchronization, or resource lifetime dependency. It does not remove
the driver's descriptor processing or address the larger per-draw costs.

Validation: reviewed the three buffer paths and both bounded texture loops;
checked that the active count is used for all appends and the Vulkan call;
`git diff --check` passes. Full compilation and gameplay benchmarking remain
pending the Linux build and title assets described above. No speedup has yet
been measured. Compare this change against the instrumented vector version
using the same warm scene, first without CPU profiling for frame times, then
with profiling for descriptors calls/self time and gpu thread CPU. Keep this
change separate from later state caching or texture changes.
