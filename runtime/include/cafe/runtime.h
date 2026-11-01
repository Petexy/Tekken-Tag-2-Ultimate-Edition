#pragma once

// Native Cafe OS runtime: guest memory, image loading, dispatch, diagnostics.

#include "cafe/ppc_context.h"

#include <cstdarg>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace cafe {

// ---------------------------------------------------------------- memory
// One 4 GiB host reservation mirrors the guest address space. Only committed
// ranges are accessible; anything else faults and is reported with its guest
// address.
uint8_t* guest_base();
void reserve_guest_memory();
void commit_guest_memory(uint32_t address, uint32_t size);
bool guest_memory_committed(uint32_t address, uint32_t size);

inline uint8_t* guest_pointer(uint32_t address) { return guest_base() + address; }

// ---------------------------------------------------------------- loading
struct LoadedImage {
    uint32_t entry_point{};
    uint32_t sda_base{};
    uint32_t sda2_base{};
    uint32_t stack_size{};
    uint32_t data_end{}; // first address past .bss
};

// Loads the RPX the code was generated from into guest memory, applying
// relocations exactly as the recompiler did. Refuses any other build.
LoadedImage load_image(const std::vector<uint8_t>& rpx_bytes);
// SHA-256 as lowercase hex (cafe_program_info.rpx_sha256 names the RPX).
std::string sha256_hex(const std::vector<uint8_t>& data);

// ---------------------------------------------------------------- dispatch
void build_dispatch_table();
// Gives a native function a guest-visible address (for function pointers the
// guest stores and calls, e.g. MEMAllocFromDefaultHeap's value).
uint32_t register_host_function(PPCFunc* function, const char* name);
// The name a host function was registered with, or null for other addresses.
const char* host_function_name(uint32_t address);

// ---------------------------------------------------------------- errors
// The context of the guest thread running on this host thread, if any.
PPCContext* current_context();
void set_current_context(PPCContext* ctx);

[[noreturn]] void fatal(const char* format, ...) __attribute__((format(printf, 1, 2)));
void install_fault_handler();
void print_guest_state(const PPCContext& ctx);

// ---------------------------------------------------------------- CPU time
// Threads whose CPU time the GPU statistics report: the calling thread, by
// `name`, or a guest thread, by its OSThread's name when the report is made
// (OSSetThreadName's, else `name`, else its address). A thread that ends
// leaves first.
void track_thread_cpu(const char* name, uint32_t guest_thread = 0);
void untrack_thread_cpu();
// "gpu 40%, present 5%; guest threads 90%, busiest Main 60%": the CPU each
// tracked thread used since the last report, in percent of one core.
std::string thread_cpu_report();

} // namespace cafe
