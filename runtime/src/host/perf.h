#pragma once

// Process and thread settings that keep the port's frame pacing steady.

#include <cstdint>

namespace cafe::host {

// Windows: asks for 1 ms timer resolution and opts the process out of
// power throttling. Since Windows 10 2004 a process that does not ask gets
// the ~15.6 ms default, whatever other programs asked for, and every short
// sleep (the command processor's WAIT_REG_MEM poll, the presenter's waits,
// guest OSSleepTicks) lasts up to that long. TTT2_TIMER_RES=0 leaves the
// default. Elsewhere: nothing.
void tune_process_timing();

// Lowers the calling thread's priority below normal (background builds).
void lower_thread_priority();

// Identifies the running executable (its size and modification time): data
// derived from this build's shader translator is only valid for it.
uint64_t executable_stamp();

} // namespace cafe::host
