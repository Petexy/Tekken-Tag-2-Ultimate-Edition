// Draws: shaders (translated and compiled on first use), pipelines, the
// per-draw constants and resources, index conversion, and the draw.

#include "gpu/vulkan/renderer.h"

#include "gpu/latte.h"
#include "gpu/looks.h"
#include "gpu/still_draws.h"
#include "gx2/types.h"

#include "cafe/runtime.h"

#include <shaderc/shaderc.h>

#include <algorithm>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <thread>
#include <unordered_set>
#include <type_traits>

namespace cafe::gpu::vk {
namespace {

using namespace latte;

uint64_t fnv(const void* data, size_t size, uint64_t h = 0xCBF29CE484222325ull) {
    const auto* p = static_cast<const uint8_t*>(data);
    for (size_t i = 0; i < size; ++i) h = (h ^ p[i]) * 0x100000001B3ull;
    return h;
}

double now_ms() {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

void report_once(const char* what, uint32_t value) {
    static std::mutex mutex; // (pipelines are created on workers too)
    static std::vector<std::pair<std::string, uint32_t>> seen;
    const std::lock_guard lock(mutex);
    for (const auto& s : seen) {
        if (s.first == what && s.second == value) return;
    }
    seen.emplace_back(what, value);
    std::fprintf(stderr, "ttt2: gpu: %s (0x%X)\n", what, value);
}

VkBlendFactor blend_factor(uint32_t f) {
    switch (f) {
    case 0: return VK_BLEND_FACTOR_ZERO;
    case 1: return VK_BLEND_FACTOR_ONE;
    case 2: return VK_BLEND_FACTOR_SRC_COLOR;
    case 3: return VK_BLEND_FACTOR_ONE_MINUS_SRC_COLOR;
    case 4: return VK_BLEND_FACTOR_SRC_ALPHA;
    case 5: return VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
    case 6: return VK_BLEND_FACTOR_DST_ALPHA;
    case 7: return VK_BLEND_FACTOR_ONE_MINUS_DST_ALPHA;
    case 8: return VK_BLEND_FACTOR_DST_COLOR;
    case 9: return VK_BLEND_FACTOR_ONE_MINUS_DST_COLOR;
    case 10: return VK_BLEND_FACTOR_SRC_ALPHA_SATURATE;
    case 13: return VK_BLEND_FACTOR_CONSTANT_COLOR;
    case 14: return VK_BLEND_FACTOR_ONE_MINUS_CONSTANT_COLOR;
    case 15: return VK_BLEND_FACTOR_SRC1_COLOR;
    case 16: return VK_BLEND_FACTOR_ONE_MINUS_SRC1_COLOR;
    case 17: return VK_BLEND_FACTOR_SRC1_ALPHA;
    case 18: return VK_BLEND_FACTOR_ONE_MINUS_SRC1_ALPHA;
    case 19: return VK_BLEND_FACTOR_CONSTANT_ALPHA;
    case 20: return VK_BLEND_FACTOR_ONE_MINUS_CONSTANT_ALPHA;
    default:
        report_once("unsupported blend factor", f);
        return VK_BLEND_FACTOR_ONE;
    }
}

VkBlendOp blend_op(uint32_t f) {
    switch (f) {
    case 0: return VK_BLEND_OP_ADD;
    case 1: return VK_BLEND_OP_SUBTRACT;
    case 2: return VK_BLEND_OP_MIN;
    case 3: return VK_BLEND_OP_MAX;
    case 4: return VK_BLEND_OP_REVERSE_SUBTRACT;
    default: return VK_BLEND_OP_ADD;
    }
}

bool is_integer(VkFormat f) {
    switch (f) {
    case VK_FORMAT_R8_UINT: case VK_FORMAT_R8_SINT: case VK_FORMAT_R8G8_UINT: case VK_FORMAT_R8G8_SINT:
    case VK_FORMAT_R8G8B8A8_UINT: case VK_FORMAT_R8G8B8A8_SINT: case VK_FORMAT_R16_UINT: case VK_FORMAT_R16_SINT:
    case VK_FORMAT_R16G16_UINT: case VK_FORMAT_R16G16_SINT: case VK_FORMAT_R16G16B16A16_UINT:
    case VK_FORMAT_R16G16B16A16_SINT: case VK_FORMAT_R32_UINT: case VK_FORMAT_R32_SINT: case VK_FORMAT_R32G32_UINT:
    case VK_FORMAT_R32G32_SINT: case VK_FORMAT_R32G32B32A32_UINT: case VK_FORMAT_R32G32B32A32_SINT:
    case VK_FORMAT_A2B10G10R10_UINT_PACK32:
        return true;
    default: return false;
    }
}

bool has_stencil(VkFormat f) {
    return f == VK_FORMAT_D24_UNORM_S8_UINT || f == VK_FORMAT_D32_SFLOAT_S8_UINT || f == VK_FORMAT_D16_UNORM_S8_UINT;
}

// Everything a pipeline bakes in; the rest is dynamic state.
struct PipelineKey {
    const ShaderModule* vs;
    const ShaderModule* ps;
    VkFormat colors[8];
    VkFormat depth;
    uint32_t color_count;
    uint32_t blend[8]; // CB_BLENDn_CONTROL, with bit 31 set when blending is enabled
    uint32_t write_mask;
    uint32_t polygon_mode;
    uint32_t topology_class;
    uint32_t depth_clamp;
};

// ~/.cache/ttt2 (or $XDG_CACHE_HOME/ttt2): compiled shaders and pipelines.
std::filesystem::path cache_directory() {
    static const std::filesystem::path dir = [] {
        std::filesystem::path d;
#ifdef _WIN32
        if (const char* x = std::getenv("LOCALAPPDATA"); x && *x) d = std::filesystem::path(x) / "TTT2Ultimate/cache";
        else return std::filesystem::path();
#else
        if (const char* x = std::getenv("XDG_CACHE_HOME"); x && *x) d = x;
        else if (const char* h = std::getenv("HOME")) d = std::filesystem::path(h) / ".cache";
        else return std::filesystem::path();
        d /= "ttt2";
#endif
        std::error_code ec;
        std::filesystem::create_directories(d / "spirv", ec);
        return ec ? std::filesystem::path() : d;
    }();
    return dir;
}

std::vector<uint32_t> load_cached_spirv(uint64_t key) {
    std::vector<uint32_t> code;
    if (cache_directory().empty()) return code;
    char name[32];
    std::snprintf(name, sizeof(name), "%016llx.spv", static_cast<unsigned long long>(key));
    std::ifstream in(cache_directory() / "spirv" / name, std::ios::binary | std::ios::ate);
    if (!in) return code;
    const std::streamsize size = in.tellg();
    if (size <= 0 || size % 4) return code;
    code.resize(static_cast<size_t>(size) / 4);
    in.seekg(0);
    in.read(reinterpret_cast<char*>(code.data()), size);
    if (!in || code[0] != 0x07230203u) code.clear(); // SPIR-V magic
    return code;
}

void store_cached_spirv(uint64_t key, const std::vector<uint32_t>& code) {
    if (cache_directory().empty()) return;
    char name[32];
    std::snprintf(name, sizeof(name), "%016llx.spv", static_cast<unsigned long long>(key));
    const std::filesystem::path path = cache_directory() / "spirv" / name;
    std::ofstream(path.string() + ".tmp", std::ios::binary)
        .write(reinterpret_cast<const char*>(code.data()), static_cast<std::streamsize>(code.size() * 4));
    std::error_code ec;
    std::filesystem::rename(path.string() + ".tmp", path, ec);
}

const char* dump_directory() {
    static const char* dir = [] {
        const char* d = std::getenv("TTT2_DUMP_SHADERS");
        return (d != nullptr && *d != '\0') ? d : nullptr;
    }();
    return dir;
}

// The functions below run on the gpu thread or on a worker (jobs.h): they
// touch nothing of the renderer's.

VkShaderModule create_module(VkDevice device, const std::vector<uint32_t>& spirv) {
    VkShaderModuleCreateInfo mci{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    mci.codeSize = spirv.size() * 4;
    mci.pCode = spirv.data();
    VkShaderModule module = VK_NULL_HANDLE;
    return vkCreateShaderModule(device, &mci, nullptr, &module) == VK_SUCCESS ? module : VK_NULL_HANDLE;
}

// GLSL to SPIR-V (kept in the disk cache) to a module; null when it fails.
VkShaderModule compile_module(VkDevice device, shaderc_compiler* compiler, bool vertex, const std::string& glsl,
                              uint64_t glsl_hash, uint64_t program_hash) {
    const char* kind = vertex ? "vs" : "ps";
    shaderc_compile_options_t options = shaderc_compile_options_initialize();
    shaderc_compile_options_set_target_env(options, shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_3);
    // The driver optimises; SPIR-V optimisation only costs compile time.
    shaderc_compile_options_set_optimization_level(options, shaderc_optimization_level_zero);
    shaderc_compilation_result_t result =
        shaderc_compile_into_spv(compiler, glsl.data(), glsl.size(), vertex ? shaderc_vertex_shader : shaderc_fragment_shader,
                                 kind, "main", options);
    shaderc_compile_options_release(options);
    if (shaderc_result_get_compilation_status(result) != shaderc_compilation_status_success) {
        std::fprintf(stderr, "ttt2: gpu: cannot compile %s %016llx:\n%s\n", kind,
                     static_cast<unsigned long long>(program_hash), shaderc_result_get_error_message(result));
        shaderc_result_release(result);
        return VK_NULL_HANDLE;
    }
    const auto* bytes = reinterpret_cast<const uint32_t*>(shaderc_result_get_bytes(result));
    const std::vector<uint32_t> spirv(bytes, bytes + shaderc_result_get_length(result) / 4);
    shaderc_result_release(result);
    store_cached_spirv(glsl_hash, spirv);
    return create_module(device, spirv);
}

VkPipelineLayout create_layout(const Context& ctx, uint32_t vs_textures, uint32_t ps_textures, bool vs_registers,
                               bool ps_registers) {
    std::vector<VkDescriptorSetLayoutBinding> bindings;
    bindings.push_back({abi::kDrawConstantsBinding, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1,
                        VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT, nullptr});
    if (vs_registers) bindings.push_back({abi::kVsRegistersBinding, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1, VK_SHADER_STAGE_VERTEX_BIT, nullptr});
    if (ps_registers) bindings.push_back({abi::kPsRegistersBinding, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1, VK_SHADER_STAGE_FRAGMENT_BIT, nullptr});
    for (uint32_t slot = 0; slot < abi::kTextureSlots; ++slot) {
        if (vs_textures & (1u << slot)) {
            bindings.push_back({abi::kVsTextureBinding + slot, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1, VK_SHADER_STAGE_VERTEX_BIT, nullptr});
        }
        if (ps_textures & (1u << slot)) {
            bindings.push_back({abi::kPsTextureBinding + slot, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1, VK_SHADER_STAGE_FRAGMENT_BIT, nullptr});
        }
    }
    VkDescriptorSetLayoutCreateInfo dci{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    dci.flags = VK_DESCRIPTOR_SET_LAYOUT_CREATE_PUSH_DESCRIPTOR_BIT_KHR;
    dci.bindingCount = static_cast<uint32_t>(bindings.size());
    dci.pBindings = bindings.data();
    VkDescriptorSetLayout set_layout;
    VK_CHECK(vkCreateDescriptorSetLayout(ctx.device, &dci, nullptr, &set_layout));
    VkPipelineLayoutCreateInfo lci{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    lci.setLayoutCount = 1;
    lci.pSetLayouts = &set_layout;
    VkPipelineLayout layout;
    VK_CHECK(vkCreatePipelineLayout(ctx.device, &lci, nullptr, &layout));
    return layout;
}

// The pipeline cache, from and to the cache directory's pipelines.bin.
VkPipelineCache open_pipeline_cache(VkDevice device) {
    std::vector<char> data;
    if (!cache_directory().empty()) {
        std::ifstream in(cache_directory() / "pipelines.bin", std::ios::binary | std::ios::ate);
        if (in && in.tellg() > 0) {
            data.resize(static_cast<size_t>(in.tellg()));
            in.seekg(0);
            in.read(data.data(), static_cast<std::streamsize>(data.size()));
        }
    }
    VkPipelineCacheCreateInfo pci{VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO};
    pci.initialDataSize = data.size();
    pci.pInitialData = data.empty() ? nullptr : data.data();
    VkPipelineCache cache = VK_NULL_HANDLE;
    if (vkCreatePipelineCache(device, &pci, nullptr, &cache) != VK_SUCCESS) {
        pci.initialDataSize = 0; // stale or from another driver
        pci.pInitialData = nullptr;
        VK_CHECK(vkCreatePipelineCache(device, &pci, nullptr, &cache));
    }
    return cache;
}

void write_pipeline_cache(VkDevice device, VkPipelineCache cache) {
    size_t size = 0;
    if (vkGetPipelineCacheData(device, cache, &size, nullptr) != VK_SUCCESS || size == 0) return;
    std::vector<char> data(size);
    if (vkGetPipelineCacheData(device, cache, &size, data.data()) != VK_SUCCESS) return;
    const std::filesystem::path path = cache_directory() / "pipelines.bin";
    std::ofstream(path.string() + ".tmp", std::ios::binary).write(data.data(), static_cast<std::streamsize>(size));
    std::error_code ec;
    std::filesystem::rename(path.string() + ".tmp", path, ec);
}

// The pipelines the game has needed on this computer, one a line in the
// cache directory's pipelines.list: what it takes to make each again
// without the game running (its shaders by the names of their SPIR-V in
// the cache, the layout's bindings, the state it bakes in), so that
// precompile_shaders() can make them all ahead. After a graphics driver
// update the SPIR-V is still good and the driver's part is not: the list
// is what brings that back before a fight needs it.
constexpr size_t kListNumbers = 28;
constexpr const char* kListTag = "p1";

std::string list_line(const PipelineKey& k) {
    std::string line = kListTag;
    const auto put = [&](uint64_t v) {
        char text[20];
        std::snprintf(text, sizeof(text), " %llx", static_cast<unsigned long long>(v));
        line += text;
    };
    put(k.vs->glsl_hash);
    put(k.ps->glsl_hash);
    put(k.vs->info.texture_mask);
    put(k.ps->info.texture_mask);
    put(k.vs->info.uses_registers);
    put(k.ps->info.uses_registers);
    put(k.color_count);
    put(k.depth);
    for (const VkFormat f : k.colors) put(f);
    for (const uint32_t b : k.blend) put(b);
    put(k.write_mask);
    put(k.polygon_mode);
    put(k.topology_class);
    put(k.depth_clamp);
    return line;
}

bool parse_list_line(const std::string& line, uint64_t numbers[kListNumbers]) {
    const char* p = line.c_str();
    if (line.compare(0, 3, std::string(kListTag) + " ") != 0) return false;
    p += 2;
    for (size_t i = 0; i < kListNumbers; ++i) {
        char* end = nullptr;
        numbers[i] = std::strtoull(p, &end, 16);
        if (end == p) return false;
        p = end;
    }
    while (*p == ' ' || *p == '\r') ++p;
    return *p == '\0';
}

std::vector<std::string> read_pipeline_list() {
    std::vector<std::string> lines;
    if (cache_directory().empty()) return lines;
    std::ifstream in(cache_directory() / "pipelines.list");
    for (std::string line; std::getline(in, line);) {
        if (!line.empty()) lines.push_back(std::move(line));
    }
    return lines;
}

// (The gpu thread's: a pipeline not in the list yet is added to it.)
void note_pipeline(const PipelineKey& k) {
    static std::unordered_set<std::string> seen = [] {
        const std::vector<std::string> lines = read_pipeline_list();
        return std::unordered_set<std::string>(lines.begin(), lines.end());
    }();
    if (cache_directory().empty() || k.vs->glsl_hash == 0 || k.ps->glsl_hash == 0) return;
    std::string line = list_line(k);
    if (!seen.insert(line).second) return;
    line += '\n';
    // (One write of a whole line, at once: the game ends without notice.)
    if (std::FILE* f = std::fopen((cache_directory() / "pipelines.list").string().c_str(), "ab")) {
        std::fwrite(line.data(), 1, line.size(), f);
        std::fclose(f);
    }
}

// `flags`: VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT asks
// for the pipeline only if the cache has it (VK_PIPELINE_COMPILE_REQUIRED
// otherwise, at once).
VkResult create_pipeline(VkDevice device, VkPipelineCache cache, const PipelineKey& k, VkPipelineLayout layout,
                         VkPipelineCreateFlags flags, VkPipeline* pipeline) {
    VkPipelineShaderStageCreateInfo stages[2]{};
    stages[0].sType = stages[1].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT;
    stages[0].module = k.vs->module;
    stages[0].pName = "main";
    stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT;
    stages[1].module = k.ps->module;
    stages[1].pName = "main";
    VkPipelineVertexInputStateCreateInfo vi{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
    VkPipelineInputAssemblyStateCreateInfo ia{VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
    ia.topology = k.topology_class == 0 ? VK_PRIMITIVE_TOPOLOGY_POINT_LIST
                  : k.topology_class == 1 ? VK_PRIMITIVE_TOPOLOGY_LINE_LIST
                                          : VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
    VkPipelineViewportStateCreateInfo vp{VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
    vp.viewportCount = 1;
    vp.scissorCount = 1;
    VkPipelineRasterizationStateCreateInfo rs{VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
    rs.polygonMode = k.polygon_mode == 0 ? VK_POLYGON_MODE_POINT : k.polygon_mode == 1 ? VK_POLYGON_MODE_LINE : VK_POLYGON_MODE_FILL;
    rs.depthClampEnable = k.depth_clamp ? VK_TRUE : VK_FALSE;
    rs.lineWidth = 1.0f;
    VkPipelineMultisampleStateCreateInfo ms{VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
    ms.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
    VkPipelineDepthStencilStateCreateInfo ds{VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO};
    VkPipelineColorBlendAttachmentState attachments[8]{};
    for (uint32_t i = 0; i < k.color_count; ++i) {
        VkPipelineColorBlendAttachmentState& a = attachments[i];
        a.colorWriteMask = k.colors[i] == VK_FORMAT_UNDEFINED ? 0 : (k.write_mask >> (4 * i)) & 0xF;
        if (k.blend[i]) {
            const uint32_t b = k.blend[i];
            a.blendEnable = VK_TRUE;
            a.srcColorBlendFactor = blend_factor(b & 0x1F);
            a.colorBlendOp = blend_op((b >> 5) & 7);
            a.dstColorBlendFactor = blend_factor((b >> 8) & 0x1F);
            if ((b >> 29) & 1) {
                a.srcAlphaBlendFactor = blend_factor((b >> 16) & 0x1F);
                a.alphaBlendOp = blend_op((b >> 21) & 7);
                a.dstAlphaBlendFactor = blend_factor((b >> 24) & 0x1F);
            } else {
                a.srcAlphaBlendFactor = a.srcColorBlendFactor;
                a.alphaBlendOp = a.colorBlendOp;
                a.dstAlphaBlendFactor = a.dstColorBlendFactor;
            }
        }
    }
    VkPipelineColorBlendStateCreateInfo cb{VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
    cb.attachmentCount = k.color_count;
    cb.pAttachments = attachments;
    static const VkDynamicState kDynamic[] = {
        VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR, VK_DYNAMIC_STATE_LINE_WIDTH, VK_DYNAMIC_STATE_DEPTH_BIAS,
        VK_DYNAMIC_STATE_BLEND_CONSTANTS, VK_DYNAMIC_STATE_STENCIL_COMPARE_MASK, VK_DYNAMIC_STATE_STENCIL_WRITE_MASK,
        VK_DYNAMIC_STATE_STENCIL_REFERENCE, VK_DYNAMIC_STATE_CULL_MODE, VK_DYNAMIC_STATE_FRONT_FACE,
        VK_DYNAMIC_STATE_PRIMITIVE_TOPOLOGY, VK_DYNAMIC_STATE_DEPTH_TEST_ENABLE, VK_DYNAMIC_STATE_DEPTH_WRITE_ENABLE,
        VK_DYNAMIC_STATE_DEPTH_COMPARE_OP, VK_DYNAMIC_STATE_DEPTH_BOUNDS_TEST_ENABLE,
        VK_DYNAMIC_STATE_STENCIL_TEST_ENABLE, VK_DYNAMIC_STATE_STENCIL_OP, VK_DYNAMIC_STATE_RASTERIZER_DISCARD_ENABLE,
        VK_DYNAMIC_STATE_DEPTH_BIAS_ENABLE, VK_DYNAMIC_STATE_PRIMITIVE_RESTART_ENABLE,
    };
    VkPipelineDynamicStateCreateInfo dyn{VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO};
    dyn.dynamicStateCount = static_cast<uint32_t>(std::size(kDynamic));
    dyn.pDynamicStates = kDynamic;
    VkPipelineRenderingCreateInfo ri{VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO};
    ri.colorAttachmentCount = k.color_count;
    ri.pColorAttachmentFormats = k.colors;
    ri.depthAttachmentFormat = k.depth;
    ri.stencilAttachmentFormat = has_stencil(k.depth) ? k.depth : VK_FORMAT_UNDEFINED;
    VkGraphicsPipelineCreateInfo gci{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
    gci.pNext = &ri;
    gci.flags = flags;
    gci.stageCount = 2;
    gci.pStages = stages;
    gci.pVertexInputState = &vi;
    gci.pInputAssemblyState = &ia;
    gci.pViewportState = &vp;
    gci.pRasterizationState = &rs;
    gci.pMultisampleState = &ms;
    gci.pDepthStencilState = &ds;
    gci.pColorBlendState = &cb;
    gci.pDynamicState = &dyn;
    gci.layout = layout;
    *pipeline = VK_NULL_HANDLE;
    return vkCreateGraphicsPipelines(device, cache, 1, &gci, nullptr, pipeline);
}

} // namespace

// ------------------------------------------------------- pipeline cache

void Renderer::load_pipeline_cache() { pipeline_cache_ = open_pipeline_cache(ctx_.device); }

void Renderer::save_pipeline_cache() {
    if (cache_directory().empty() || new_pipelines_.exchange(0) == 0) return;
    write_pipeline_cache(ctx_.device, pipeline_cache_);
}

// ---------------------------------------------------------------- shaders

const Program* Renderer::program(uint32_t address, uint32_t size, uint64_t& hash) {
    const uint64_t key = (uint64_t{address} << 32) | size;
    auto it = programs_.find(key);
    if (it == programs_.end()) {
        ProgramEntry e{0, {}, false};
        if (size != 0 && guest_memory_committed(address, size)) {
            std::vector<uint32_t> words(size / 4);
            std::memcpy(words.data(), guest_pointer(address), words.size() * 4); // little-endian, the GPU's order
            e.hash = fnv(words.data(), words.size() * 4);
            std::string error;
            e.ok = decode(words, e.program, error);
            if (!e.ok) std::fprintf(stderr, "ttt2: gpu: shader at 0x%08X: %s\n", address, error.c_str());
        }
        it = programs_.emplace(key, std::move(e)).first;
        if (size != 0) {
            for_pages(address, uint64_t{address} + size, [&](uint32_t page) {
                std::vector<uint64_t>& keys = program_pages_[page];
                if (std::find(keys.begin(), keys.end(), key) == keys.end()) keys.push_back(key);
            });
        }
    }
    hash = it->second.hash;
    return it->second.ok ? &it->second.program : nullptr;
}

const ShaderModule* Renderer::shader(Stage stage, uint32_t address, uint32_t size, uint32_t fetch_address,
                                     uint32_t fetch_size, const ShaderEnvironment& env) {
    uint64_t program_hash = 0, fetch_hash = 0;
    const Program* p = program(address, size, program_hash);
    if (p == nullptr) return nullptr;
    const Program* fetch = nullptr;
    if (stage == Stage::kVertex && fetch_address != 0) fetch = program(fetch_address, fetch_size, fetch_hash);
    const uint64_t keys[3] = {program_hash, fetch_hash, environment_key(env)};
    const uint64_t key = fnv(keys, sizeof(keys));
    // (A module still compiling in the background is returned as it is,
    // its job set; one that failed there counts as failed from now on.)
    const auto settled = [](const ShaderModule* m) -> const ShaderModule* {
        if (m == nullptr) return nullptr;
        if (m->job && JobPool::done(m->job)) m->job.reset();
        return m->job || m->module != VK_NULL_HANDLE ? m : nullptr;
    };
    if (auto it = shaders_.find(key); it != shaders_.end()) return settled(it->second);
    const ShaderModule*& entry = shaders_[key]; // stays null if the shader fails
    const char* kind = stage == Stage::kVertex ? "vs" : "ps";
    TranslatedShader info;
    std::string error;
    const double translate_start = trace_shaders_ ? now_ms() : 0;
    if (!translate(*p, fetch, env, info, error)) {
        std::fprintf(stderr, "ttt2: gpu: cannot translate %s %016llx: %s\n", kind,
                     static_cast<unsigned long long>(program_hash), error.c_str());
        return nullptr;
    }
    if (trace_shaders_) {
        ++frame_costs_.translated;
        frame_costs_.translate_ms += now_ms() - translate_start;
    }
    if (const char* dir = dump_directory()) {
        char name[128];
        std::snprintf(name, sizeof(name), "%s_%016llx_%016llx.glsl", kind, static_cast<unsigned long long>(program_hash),
                      static_cast<unsigned long long>(key));
        std::ofstream(std::filesystem::path(dir) / name) << info.glsl;
    }
    // Environments that translate alike share a module, and so pipelines:
    // the key also covers state a shader does not depend on (textures the
    // title left bound to slots it does not sample, other stages' links).
    const uint64_t glsl_hash = fnv(info.glsl.data(), info.glsl.size());
    const auto same = [&](const TranslatedShader& o) {
        return o.glsl == info.glsl && o.texture_mask == info.texture_mask && o.shadow_mask == info.shadow_mask &&
               o.uses_registers == info.uses_registers && o.constant_bank_mask == info.constant_bank_mask &&
               std::equal(std::begin(o.constant_bank_extent), std::end(o.constant_bank_extent),
                          std::begin(info.constant_bank_extent)) &&
               o.buffer_mask == info.buffer_mask &&
               std::equal(std::begin(o.vb_extent), std::end(o.vb_extent), std::begin(info.vb_extent)) &&
               o.stream_out_complete == info.stream_out_complete;
    };
    uint64_t code = glsl_hash;
    for (auto it = modules_.find(code); it != modules_.end(); it = modules_.find(++code)) {
        if (same(it->second->info)) return settled(entry = it->second.get());
    }
    auto module = std::make_unique<ShaderModule>();
    module->info = std::move(info);
    module->glsl_hash = glsl_hash;
    ShaderModule* const m = module.get();
    const bool vertex = stage == Stage::kVertex;
    const double start = trace_shaders_ ? now_ms() : 0;
    // SPIR-V is cached on disk by the GLSL it came from.
    if (const std::vector<uint32_t> spirv = load_cached_spirv(glsl_hash); !spirv.empty()) {
        m->module = create_module(ctx_.device, spirv);
        if (m->module == VK_NULL_HANDLE) fatal("Vulkan: a shader module could not be created");
        m->cached = true;
        if (trace_shaders_) {
            ++frame_costs_.loaded;
            frame_costs_.load_ms += now_ms() - start;
        }
    } else if (async_shaders_ && !compile_inline_) {
        // The compiler runs on a worker; the draws wait for it or are left
        // out meanwhile (draw()). The module's text and handle are the
        // job's until the job is done.
        const bool trace = trace_shaders_;
        m->job = jobs_.submit([this, m, vertex, glsl_hash, program_hash, trace] {
            const double begin = now_ms();
            m->module = compile_module(ctx_.device, compiler_, vertex, m->info.glsl, glsl_hash, program_hash);
            const double ms = now_ms() - begin;
            ++worker_shaders_;
            worker_shader_us_ += static_cast<uint64_t>(ms * 1000);
            if (trace) std::fprintf(stderr, "shaders: job: %s %016llx compiled in %.1f ms\n", vertex ? "vs" : "ps",
                                    static_cast<unsigned long long>(glsl_hash), ms);
        });
        if (trace_shaders_) ++frame_costs_.queued;
    } else {
        m->module = compile_module(ctx_.device, compiler_, vertex, m->info.glsl, glsl_hash, program_hash);
        if (trace_shaders_) {
            ++frame_costs_.compiled;
            frame_costs_.compile_ms += now_ms() - start;
        }
        if (m->module == VK_NULL_HANDLE) return nullptr;
    }
    entry = m;
    modules_.emplace(code, std::move(module));
    return entry;
}

// -------------------------------------------------------------- pipelines

VkPipelineLayout Renderer::pipeline_layout(uint32_t vs_textures, uint32_t ps_textures, bool vs_registers,
                                           bool ps_registers) {
    const uint64_t key = uint64_t{vs_textures} | (uint64_t{ps_textures} << 18) | (uint64_t{vs_registers} << 36) |
                         (uint64_t{ps_registers} << 37);
    if (auto it = layouts_.find(key); it != layouts_.end()) return it->second;
    return layouts_[key] = create_layout(ctx_, vs_textures, ps_textures, vs_registers, ps_registers);
}

const Pipeline* Renderer::pipeline(const Registers& regs, const ShaderModule* vs, const ShaderModule* ps,
                                   const VkFormat* colors, uint32_t color_count, VkFormat depth, uint32_t topology_class) {
    PipelineKey k;
    std::memset(&k, 0, sizeof(k));
    k.vs = vs;
    k.ps = ps;
    k.color_count = color_count;
    k.depth = depth;
    const uint32_t color_control = regs[reg::CB_COLOR_CONTROL];
    const uint32_t blend_enable = (color_control >> 8) & 0xFF;
    const bool per_mrt = (color_control >> 7) & 1;
    k.write_mask = regs[reg::CB_TARGET_MASK];
    for (uint32_t i = 0; i < color_count; ++i) {
        k.colors[i] = colors[i];
        if (colors[i] == VK_FORMAT_UNDEFINED) continue;
        if ((blend_enable >> i) & 1 && !is_integer(colors[i])) {
            k.blend[i] = (regs[reg::CB_BLEND0_CONTROL + (per_mrt ? i * 4 : 0)] & 0x7FFFFFFF) | 0x80000000u;
        }
    }
    const uint32_t mode = regs[reg::PA_SU_SC_MODE_CNTL];
    if ((mode >> 3) & 3) k.polygon_mode = (mode >> 5) & 7; // front polygon type: 0 points, 1 lines, 2 fill
    else k.polygon_mode = 2;
    k.topology_class = topology_class;
    const uint32_t clip = regs[reg::PA_CL_CLIP_CNTL];
    k.depth_clamp = ((clip >> 26) & 3) == 3; // ZCLIP_NEAR/FAR_DISABLE
    if ((color_control >> 16 & 0xFF) != 0xCC) report_once("unsupported ROP3", (color_control >> 16) & 0xFF);

    const uint64_t key = fnv(&k, sizeof(k));
    auto& entry = pipelines_[key];
    if (entry) {
        // (Still being created in the background: returned with its job set.)
        if (entry->job && JobPool::done(entry->job)) entry->job.reset();
        return entry->job || entry->pipeline ? entry.get() : nullptr;
    }
    entry = std::make_unique<Pipeline>();
    entry->vs = vs;
    entry->ps = ps;
    entry->layout = pipeline_layout(vs->info.texture_mask, ps->info.texture_mask, vs->info.uses_registers,
                                    ps->info.uses_registers);
    Pipeline* const p = entry.get();
    note_pipeline(k);
    const double start = trace_shaders_ ? now_ms() : 0;
    if (compile_inline_) {
        // (Shaders an earlier draw left to the workers: needed now.)
        for (const ShaderModule* m : {vs, ps}) {
            if (!m->job) continue;
            const double begin = now_ms();
            jobs_.finish(m->job);
            m->job.reset();
            ++frame_costs_.waits;
            frame_costs_.wait_ms += now_ms() - begin;
        }
        if (vs->module == VK_NULL_HANDLE || ps->module == VK_NULL_HANDLE) return nullptr; // (a shader failed)
    } else {
        // What the caches already hold is made here, at once, and no draw
        // goes without it: the pipeline cache answers "only if cached"
        // where the device can ask that, else shaders that both came from
        // the disk cache are taken to have their pipeline cached as well.
        const bool compiled = !vs->job && !ps->job;
        if (compiled && ctx_.pipeline_cache_control) {
            const VkResult r = create_pipeline(ctx_.device, pipeline_cache_, k, p->layout,
                                               VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT, &p->pipeline);
            if (trace_shaders_) {
                ++frame_costs_.hits;
                frame_costs_.hit_ms += now_ms() - start;
            }
            if (r == VK_SUCCESS) return p;
            p->pipeline = VK_NULL_HANDLE;
            if (r != VK_PIPELINE_COMPILE_REQUIRED) {
                std::fprintf(stderr, "ttt2: gpu: pipeline creation failed (%d)\n", static_cast<int>(r));
                return nullptr;
            }
        }
        if (!(compiled && !ctx_.pipeline_cache_control && vs->cached && ps->cached)) {
            // On a worker, after the shaders' own jobs (the job keeps them:
            // the gpu thread drops a module's as soon as it is done).
            const bool trace = trace_shaders_;
            ++pipeline_jobs_;
            ++frame_late_pipelines_;
            p->job = jobs_.submit([this, p, k, trace, vs_job = vs->job, ps_job = ps->job] {
                struct Leave {
                    std::atomic<uint32_t>& count;
                    ~Leave() { --count; }
                } leave{pipeline_jobs_};
                if (vs_job) jobs_.finish(vs_job);
                if (ps_job) jobs_.finish(ps_job);
                if (k.vs->module == VK_NULL_HANDLE || k.ps->module == VK_NULL_HANDLE) return; // (a shader failed)
                const double begin = now_ms();
                const VkResult r = create_pipeline(ctx_.device, pipeline_cache_, k, p->layout, 0, &p->pipeline);
                const double ms = now_ms() - begin;
                if (r != VK_SUCCESS) {
                    std::fprintf(stderr, "ttt2: gpu: pipeline creation failed (%d)\n", static_cast<int>(r));
                    p->pipeline = VK_NULL_HANDLE;
                    return;
                }
                ++new_pipelines_;
                ++worker_pipelines_;
                worker_pipeline_us_ += static_cast<uint64_t>(ms * 1000);
                if (trace) std::fprintf(stderr, "shaders: job: pipeline created in %.1f ms\n", ms);
            });
            if (trace_shaders_) ++frame_costs_.queued;
            return p;
        }
    }
    const VkResult r = create_pipeline(ctx_.device, pipeline_cache_, k, p->layout, 0, &p->pipeline);
    ++new_pipelines_;
    if (trace_shaders_) {
        ++frame_costs_.pipelines;
        frame_costs_.pipeline_ms += now_ms() - start;
    }
    if (r != VK_SUCCESS) {
        std::fprintf(stderr, "ttt2: gpu: pipeline creation failed (%d)\n", static_cast<int>(r));
        p->pipeline = VK_NULL_HANDLE;
        return nullptr;
    }
    return p;
}

// ----------------------------------------------------------------- draws

abi::Buffer Renderer::buffer_descriptor(uint32_t address, uint32_t size, uint32_t stride) const {
    uint32_t available = 0;
    const VkDeviceAddress device = address != 0 ? guest_.device_address(address, available) : 0;
    if (device == 0 || size == 0) return {0, 0, 0, stride};
    return {static_cast<uint32_t>(device), static_cast<uint32_t>(device >> 32), std::min(size, available), stride};
}

namespace {
// Bytes of a constant block to copy for interpolation: what the shader
// reads; a block it indexes freely only whole and up to 256 KiB (0: read
// it in place).
uint32_t read_extent(uint32_t size, uint32_t extent) {
    if (extent != UINT32_MAX) return std::min(size, extent);
    return size <= (256u << 10) ? size : 0;
}
} // namespace

// A polygon the title registered as standing still (gpu/still_draws.h), in
// its pass: the slot of last frame's positions reads this frame's (the same
// buffer: video-memory copies redirect both alike), so that pass sees no
// motion. Cheapest tests first: every other draw stops at the count's bit.
bool Renderer::keep_still(const Registers& regs, const Draw& d, abi::DrawConstants& dc, uint32_t* vb_address) {
    const StillDraws* still = still_draws();
    if (still == nullptr || d.source != Draw::kIndexBuffer || !still->counted(d.count)) return false;
    const uint32_t current = still->current, previous = still->previous;
    if (current >= 16 || previous >= 16 || dc.vb[current].size == 0 || dc.vb[previous].size == 0 ||
        dc.vb[current].stride != dc.vb[previous].stride) {
        return false;
    }
    uint64_t hash = 0;
    program(regs[reg::SQ_PGM_START_VS] << 8, regs[reg::SQ_PGM_START_VS + 4] << 3, hash);
    if (hash != still->vertex_program || !still->still(d.index_address, d.count)) return false;
    dc.vb[previous] = dc.vb[current];
    vb_address[previous] = vb_address[current];
    return true;
}

// The pass left out whole (StillDraws::all, a test switch): its vertex shader.
bool Renderer::left_out(const Registers& regs) {
    const StillDraws* still = still_draws();
    if (still == nullptr || !still->all) return false;
    uint64_t hash = 0;
    program(regs[reg::SQ_PGM_START_VS] << 8, regs[reg::SQ_PGM_START_VS + 4] << 3, hash);
    return hash == still->vertex_program;
}

// A draw of a fighter with a look (gpu/looks.h): its kind for the pixel
// shader (ShaderEnvironment::fighter_look; 0 none) and the look. The
// fighter's colour in the draw's constants carries the look's number (read
// where the shaders read it: block 8 bound to a stage that does not read
// it may be another draw's); the motion blur's velocity pass draws the
// fighter's meshes without that colour, from the vertex buffers its draws
// before used in the frame (its static data, this frame's skinned
// vertices), and draws no velocities while the look has just brought it
// from elsewhere. A replay draws as its frame did.
uint8_t Renderer::fighter_look(const Registers& regs, const ShaderModule* vs, uint32_t draw_index, uint32_t& look) {
    FrameRecord& f = frame_records_[current_record_];
    DrawRecord* record = logging_ && draw_index < f.draws.size() ? &f.draws[draw_index] : nullptr;
    if (replaying_) {
        if (record == nullptr) return 0;
        look = record->look;
        return record->look_kind;
    }
    const auto r = [&](uint32_t address) { return regs[address]; };
    const auto number_at = [&](uint32_t cache, uint32_t size, uint32_t at) -> uint32_t {
        const uint32_t block = r(cache + looks::kColourBlock * 4) << 8;
        const uint32_t bytes = r(size + looks::kColourBlock * 4) << 8;
        if (block == 0 || bytes < at + 12 || !guest_memory_committed(block + at, 12)) return 0;
        uint32_t rgb[3];
        std::memcpy(rgb, guest_pointer(block + at), sizeof(rgb)); // (in the GPU's byte order)
        return looks::marked(rgb);
    };
    uint32_t number = 0;
    if ((vs->info.constant_bank_mask >> looks::kColourBlock) & 1) {
        number = number_at(reg::SQ_ALU_CONST_CACHE_VS_0, reg::SQ_ALU_CONST_BUFFER_SIZE_VS_0, looks::kVertexColourAt);
        if (number != 0 && number_at(reg::SQ_ALU_CONST_CACHE_PS_0, reg::SQ_ALU_CONST_BUFFER_SIZE_PS_0,
                                     looks::kPixelColourAt) != number) {
            number = 0; // (the pixel shader's colour too, where it is bound: both are the fighter's)
        }
    }
    uint64_t vertices = 0;
    for (uint32_t i = 0; i < 2; ++i) {
        const uint32_t base = kResourceBase + (resource::kVsAttrib + i) * resource::kWords * 4;
        if ((r(base + 24) >> 30) == (resource::kTypeValidBuffer >> 30)) vertices |= uint64_t{r(base)} << (32 * (1 - i));
    }
    uint8_t kind = 0;
    look = 0;
    if (number != 0 && (look = looks::look(number)) != 0) {
        kind = 1;
        if (vertices >> 32 && vertices & 0xFFFFFFFFu) look_vertices_[vertices] = look;
    } else if (const auto it = look_vertices_.find(vertices); it != look_vertices_.end()) {
        kind = 2;
        look = it->second | (it->second & looks::kStill ? looks::kHidden : 0);
    }
    if (record != nullptr) {
        record->look = look;
        record->look_kind = kind;
    }
    return kind;
}

void Renderer::draw(const Registers& regs, const Draw& d) {
    if (!replaying_) ++draws_;
    const auto r = [&](uint32_t address) { return regs[address]; };
    draw_video_chunks_ = 0;
    // Interpolation: every draw of a frame and of its replays, in order.
    const uint32_t draw_index = logging_ ? begin_draw_record(regs, d) : 0;
    // (A draw its frame left out while its shaders compiled: not in the
    // frame's picture, so not in its replays'.)
    if (replaying_ && logging_ && draw_index < frame_records_[current_record_].draws.size() &&
        frame_records_[current_record_].draws[draw_index].skipped) {
        return;
    }
    const uint32_t instances = std::max<uint32_t>(d.num_instances, 1);

    // Primitive type: Vulkan topology, or a conversion through indices.
    enum class Convert { kNone, kQuads, kQuadStrip, kLoop } convert = Convert::kNone;
    VkPrimitiveTopology topology;
    uint32_t topology_class = 2;
    switch (r(reg::VGT_PRIMITIVE_TYPE)) {
    case 0x01: topology = VK_PRIMITIVE_TOPOLOGY_POINT_LIST; topology_class = 0; break;
    case 0x02: topology = VK_PRIMITIVE_TOPOLOGY_LINE_LIST; topology_class = 1; break;
    case 0x03: topology = VK_PRIMITIVE_TOPOLOGY_LINE_STRIP; topology_class = 1; break;
    case 0x12: topology = VK_PRIMITIVE_TOPOLOGY_LINE_STRIP; topology_class = 1; convert = Convert::kLoop; break;
    case 0x04: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST; break;
    case 0x05: case 0x15: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN; break;
    case 0x06: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP; break;
    case 0x13: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST; convert = Convert::kQuads; break;
    case 0x14: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST; convert = Convert::kQuadStrip; break;
    default:
        report_once("unsupported primitive type", r(reg::VGT_PRIMITIVE_TYPE));
        ++skipped_draws_;
        return;
    }
    if (d.use_opaque) {
        report_once("unsupported stream-out draw", 0);
        ++skipped_draws_;
        return;
    }
    if (d.count == 0 || left_out(regs)) return;
    const bool indexed = d.source != Draw::kAuto || convert != Convert::kNone;
    const bool restart = indexed && (r(reg::VGT_MULTI_PRIM_IB_RESET_EN) & 1) && d.source != Draw::kAuto;
    // (Vulkan restarts strips and fans only: lists draw the marker as a vertex.)
    const bool restart_enabled = restart && topology_class != 0 && topology != VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST &&
                                 topology != VK_PRIMITIVE_TOPOLOGY_LINE_LIST;

    // Render targets.
    std::array<const Target*, 8> colors{};
    uint32_t color_count = 0;
    const uint32_t target_mask = r(reg::CB_TARGET_MASK);
    for (uint32_t t = 0; t < 8; ++t) {
        const uint32_t info = r(reg::CB_COLOR0_INFO + t * 4), base = r(reg::CB_COLOR0_BASE + t * 4);
        if (((target_mask >> (4 * t)) & 0xF) == 0 || ((info >> 2) & 0x3F) == 0 || base == 0) continue;
        colors[t] = color_target(base, r(reg::CB_COLOR0_SIZE + t * 4), info);
        if (colors[t]) color_count = t + 1;
    }
    const uint32_t depth_control = r(reg::DB_DEPTH_CONTROL);
    const Target* depth = nullptr;
    if ((depth_control & 7) != 0 && (r(reg::DB_DEPTH_INFO) & 7) != 0 && r(reg::DB_DEPTH_BASE) != 0) {
        depth = depth_target(r(reg::DB_DEPTH_BASE), r(reg::DB_DEPTH_SIZE), r(reg::DB_DEPTH_INFO));
    }
    const bool rasterizer_discard = (r(reg::PA_CL_CLIP_CNTL) >> 22) & 1;
    const bool stream_out = r(reg::VGT_STRMOUT_EN) & 1;
    if (color_count == 0 && depth == nullptr && !stream_out) {
        // Nothing to write (every target masked off): no effect, nothing lost.
        return;
    }
    // A replay drops stream-out writes (below), so a stream-out draw that
    // rasterises nothing (the fighters' skinning) is left with no effect; its
    // index is taken, so the draws after it still match the frame's.
    if (replaying_ && stream_out && (rasterizer_discard || (color_count == 0 && depth == nullptr))) return;

    // Shaders compiled in the background: whether this draw may be left
    // out while its pipeline (or a shader of it) is made on a worker, to
    // appear once that is there. Only where that delays a part of the
    // picture and nothing else:
    //  - not a stream-out draw: it writes memory (the fighters' skinned
    //    vertices) that later draws and the title read;
    //  - not in a replay: an extra frame draws what its frame drew;
    //  - a depth-tested draw, a thing in the 3D scene: the others are the
    //    passes that make or compose whole images (blur, glow, copies, the
    //    menus' and the HUD's layers), where a draw left out is a black or
    //    broken picture;
    //  - into targets the frame before drew into as well, so the next
    //    frames draw it again: a picture drawn once and kept (rendered to
    //    a texture at a load) would stay without it;
    //  - into targets the title does not read: one written back to its
    //    memory (targets.cpp) would hand it a picture without the draw.
    // (gpu/vulkan/leave_out.h; its test names each case.)
    // Any other draw has what it needs made at once, on this
    // thread, as without the setting. So has a draw that may be left out
    // once the frame has sent four new pipelines to the workers, or while
    // as many are in the making as two a worker: a new scene needs dozens
    // at once, and its first frames with most of it missing would be worse
    // than its one late frame, which comes where the title changes scenes
    // anyway; what a fight brings up on the way (a hit's sparks, a move's
    // trail) comes in ones and twos.
    bool redrawn = true, may_skip = false, cpu_reads = false;
    const bool depth_tested = depth != nullptr && (depth_control & 2);
    if (async_shaders_ || trace_shaders_) {
        if (!replaying_) {
            const auto drawn = [&](const Target* target) {
                if (target == nullptr) return;
                Target& t = *const_cast<Target*>(target);
                if (t.drawn_frame != frame_number_) {
                    t.redrawn = t.drawn_frame + 1 == frame_number_;
                    t.drawn_frame = frame_number_;
                }
                redrawn = redrawn && t.redrawn;
                cpu_reads = cpu_reads || t.write_back;
            };
            for (uint32_t i = 0; i < color_count; ++i) drawn(colors[i]);
            drawn(depth);
        }
        may_skip = may_leave_out({.stream_out = stream_out, .replaying = replaying_, .depth_tested = depth_tested,
                                  .redrawn = redrawn, .cpu_reads = cpu_reads});
    }
    compile_inline_ = !(async_shaders_ && may_skip && frame_late_pipelines_ < max_frame_late_pipelines_ &&
                        pipeline_jobs_.load() < max_late_pipelines_);
    may_skip = may_skip && async_shaders_;

    // Shaders.
    const ShaderCosts costs_before = frame_costs_;
    ShaderEnvironment vs_env, ps_env;
    build_environment(regs.value, Stage::kVertex, vs_env);
    build_environment(regs.value, Stage::kPixel, ps_env);
    const ShaderModule* vs = shader(Stage::kVertex, r(reg::SQ_PGM_START_VS) << 8, r(reg::SQ_PGM_START_VS + 4) << 3,
                                    r(reg::SQ_PGM_START_FS) << 8, r(reg::SQ_PGM_START_FS + 4) << 3, vs_env);
    uint32_t look = 0;
    if (vs != nullptr && (looks::active() || replaying_)) ps_env.fighter_look = fighter_look(regs, vs, draw_index, look);
    const ShaderModule* ps = shader(Stage::kPixel, r(reg::SQ_PGM_START_PS) << 8, r(reg::SQ_PGM_START_PS + 4) << 3, 0, 0,
                                    ps_env);
    if (vs == nullptr || ps == nullptr) {
        report_once(vs == nullptr ? "draw skipped: vertex shader failed, at" : "draw skipped: pixel shader failed, at",
                    vs == nullptr ? r(reg::SQ_PGM_START_VS) << 8 : r(reg::SQ_PGM_START_PS) << 8);
        ++skipped_draws_;
        return;
    }

    // Textures, before the rendering pass: they may upload or copy.
    struct Bound {
        VkImageView view;
        VkSampler sampler;
        bool scaled;
    };
    bool samples_target = false; // a texture that a render target's content came from
    Bound vs_textures[abi::kTextureSlots]{}, ps_textures[abi::kTextureSlots]{};
    const auto bind_textures = [&](const ShaderModule* s, uint32_t resource_base, uint32_t sampler_base,
                                   uint32_t border_base, Bound* out) {
        for (uint32_t slot = 0; slot < abi::kTextureSlots; ++slot) {
            if (!(s->info.texture_mask & (1u << slot))) continue;
            uint32_t words[7];
            for (int i = 0; i < 7; ++i) words[i] = r(kResourceBase + ((resource_base + slot) * resource::kWords + i) * 4);
            uint32_t sampler_words[3];
            for (int i = 0; i < 3; ++i) sampler_words[i] = r(kSamplerBase + ((sampler_base + slot) * sampler::kWords + i) * 4);
            float border[4];
            for (int i = 0; i < 4; ++i) border[i] = std::bit_cast<float>(r(border_base + slot * 16 + i * 4));
            const bool valid = (words[6] >> 30) == (resource::kTypeValidTexture >> 30);
            if (!valid) {
                // Nothing bound (the shader samples it on a path it does not
                // take, or the title relies on it): the GPU reads zeros, and
                // the shader declared a 2D float texture. (Fallen Garden's
                // water has such a slot; skipping the draw left no water.)
                out[slot] = {null_texture().view, sampler(sampler_words, border, (s->info.shadow_mask >> slot) & 1), false};
                continue;
            }
            const Texture* t = texture(words);
            if (t == nullptr) {
                report_once("draw skipped: texture could not be created, format", words[1] >> 26);
                return false;
            }
            out[slot] = {t->view, sampler(sampler_words, border, (s->info.shadow_mask >> slot) & 1), t->scale > 1};
            samples_target = samples_target || t->source != nullptr;
        }
        return true;
    };
    if (!bind_textures(vs, resource::kVsTexture, sampler::kVs, reg::TD_VS_SAMPLER_BORDER0_RED, vs_textures) ||
        !bind_textures(ps, resource::kPsTexture, sampler::kPs, reg::TD_PS_SAMPLER_BORDER0_RED, ps_textures)) {
        ++skipped_draws_;
        return;
    }

    VkFormat formats[8]{};
    for (uint32_t i = 0; i < color_count; ++i) formats[i] = colors[i] ? colors[i]->image.format : VK_FORMAT_UNDEFINED;
    const VkFormat depth_format = depth ? depth->image.format : VK_FORMAT_UNDEFINED;
    const Pipeline* pipe = pipeline(regs, vs, ps, formats, color_count, depth_format, topology_class);
    if (pipe == nullptr) {
        report_once("draw skipped: pipeline could not be created", 0);
        ++skipped_draws_;
        return;
    }
    if (trace_shaders_ && !replaying_ &&
        (frame_costs_.translated != costs_before.translated || frame_costs_.pipelines != costs_before.pipelines ||
         frame_costs_.hits != costs_before.hits || frame_costs_.queued != costs_before.queued)) {
        std::fprintf(stderr, "shaders: first use, frame %llu: prim 0x%X count %u, %s%s%s%s, color 0x%08X %ux%u, depth 0x%08X control 0x%08X blend 0x%02X: %s\n",
                     static_cast<unsigned long long>(frame_number_), r(reg::VGT_PRIMITIVE_TYPE), d.count,
                     stream_out ? "stream-out" : depth_tested ? "depth-tested" : "flat",
                     rasterizer_discard ? ", no raster" : "", samples_target ? ", samples a target" : "",
                     redrawn ? ", redrawn" : ", not drawn the frame before",
                     colors[0] ? colors[0]->address : 0, colors[0] ? colors[0]->pitch : 0, colors[0] ? colors[0]->height : 0,
                     depth ? depth->address : 0, depth_control, (r(reg::CB_COLOR_CONTROL) >> 8) & 0xFF,
                     !may_skip ? "waits" : compile_inline_ ? "waits (many in the making)" : "may be left out");
    }
    if (pipe->job) {
        if (may_skip) {
            if (logging_ && draw_index < frame_records_[current_record_].draws.size()) {
                frame_records_[current_record_].draws[draw_index].skipped = true;
            }
            ++skipped_draws_;
            ++frame_costs_.skipped;
            return;
        }
        // (Run here if no worker has taken it yet, its shaders' too.)
        const double start = now_ms();
        jobs_.finish(pipe->job);
        pipe->job.reset();
        ++frame_costs_.waits;
        frame_costs_.wait_ms += now_ms() - start;
        if (pipe->pipeline == VK_NULL_HANDLE) {
            report_once("draw skipped: pipeline could not be created", 0);
            ++skipped_draws_;
            return;
        }
    }

    // Per-draw constants.
    abi::DrawConstants dc{};
    const bool record = logging_ && !replaying_;
    ConstantSources sources;
    uint32_t vb_address[16] = {}; // (guest addresses: video-memory copies replace some)
    for (uint32_t i = 0; i < 16; ++i) {
        if (const uint32_t a = r(reg::SQ_ALU_CONST_CACHE_VS_0 + i * 4)) {
            const uint32_t size = r(reg::SQ_ALU_CONST_BUFFER_SIZE_VS_0 + i * 4) << 8;
            dc.vs_cb[i] = buffer_descriptor(a << 8, size, 16);
            if (record && (vs->info.constant_bank_mask >> i) & 1) {
                sources.add({0, 0, static_cast<uint8_t>(i), a << 8, read_extent(size, vs->info.constant_bank_extent[i]), 16});
            }
        }
        if (const uint32_t a = r(reg::SQ_ALU_CONST_CACHE_PS_0 + i * 4)) {
            const uint32_t size = r(reg::SQ_ALU_CONST_BUFFER_SIZE_PS_0 + i * 4) << 8;
            dc.ps_cb[i] = buffer_descriptor(a << 8, size, 16);
            if (record && (ps->info.constant_bank_mask >> i) & 1) {
                sources.add({1, 0, static_cast<uint8_t>(i), a << 8, read_extent(size, ps->info.constant_bank_extent[i]), 16});
            }
        }
        const auto buffer = [&](uint32_t slot, int stage, uint32_t mask) {
            const uint32_t base = kResourceBase + slot * resource::kWords * 4;
            if ((r(base + 24) >> 30) != (resource::kTypeValidBuffer >> 30)) return abi::Buffer{};
            const uint32_t stride = (r(base + 8) >> 8) & 0x7FF;
            if (record && stage >= 0 && (mask >> i) & 1) {
                sources.add({static_cast<uint8_t>(stage), 1, static_cast<uint8_t>(i), r(base),
                             read_extent(r(base + 4) + 1, UINT32_MAX), stride});
            }
            return buffer_descriptor(r(base), r(base + 4) + 1, stride);
        };
        dc.vs_buf[i] = buffer(resource::kVsBuffer + i, 0, vs->info.buffer_mask);
        dc.ps_buf[i] = buffer(resource::kPsBuffer + i, 1, ps->info.buffer_mask);
        dc.vb[i] = buffer(resource::kVsAttrib + i, -1, 0);
        if (dc.vb[i].size != 0) vb_address[i] = r(kResourceBase + (resource::kVsAttrib + i) * resource::kWords * 4);
    }
    keep_still(regs, d, dc, vb_address);
    // Stream-out writes guest memory, which a replay must not touch (the
    // draws that read it use what the frame wrote): a replayed draw keeps
    // its rasterised output, its stream-out buffers are empty. With
    // shadows, some write video memory instead (shadows.cpp).
    StreamWrites so_writes;
    if (stream_out && !replaying_) {
        for (uint32_t i = 0; i < 4; ++i) {
            const uint32_t base = r(reg::VGT_STRMOUT_BUFFER_BASE_0 + i * 16) << 8;
            const uint32_t offset = r(reg::VGT_STRMOUT_BUFFER_OFFSET_0 + i * 16) * 4;
            const uint32_t size = r(reg::VGT_STRMOUT_BUFFER_SIZE_0 + i * 16) * 4;
            if (base == 0 || size <= offset) continue;
            dc.so[i] = buffer_descriptor(base + offset, size - offset, 0);
            if (shadows_on_ && (vs_env.stream_out_mask >> i) & 1 && dc.so[i].size != 0) {
                stream_out_target(i, base, offset, size, vs_env.stream_out_stride[i],
                                  (vs->info.stream_out_complete >> i) & 1, indexed || instances > 1 ? 0 : d.count,
                                  dc.so[i], so_writes);
            }
        }
    }
    dc.base_vertex = r(reg::SQ_VTX_BASE_VTX_LOC);
    dc.start_instance = r(reg::SQ_VTX_START_INST_LOC);
    dc.step_rate[0] = r(reg::VGT_INSTANCE_STEP_RATE_0);
    dc.step_rate[1] = r(reg::VGT_INSTANCE_STEP_RATE_0 + 4);
    // The pass's scale: its attachments are all upscaled or none is.
    float pass_scale = 0;
    bool mixed_scales = false;
    const auto take_scale = [&](const Target* t) {
        if (t == nullptr) return;
        if (pass_scale != 0 && pass_scale != t->scale) mixed_scales = true;
        pass_scale = std::max(pass_scale, t->scale);
    };
    for (uint32_t i = 0; i < color_count; ++i) take_scale(colors[i]);
    take_scale(depth);
    if (pass_scale == 0) pass_scale = 1;
    if (mixed_scales) {
        report_once("draw into upscaled and title-sized targets at once, twice the scale",
                    static_cast<uint32_t>(2 * pass_scale));
    }
    dc.alpha_ref = std::bit_cast<float>(r(reg::SX_ALPHA_REF));
    dc.point_size = static_cast<float>((r(reg::PA_SU_POINT_SIZE) >> 16) & 0xFFFF) / 8.0f * pass_scale;
    dc.pixel_scale = pass_scale;
    dc.texture_scale = scale_;
    for (uint32_t slot = 0; slot < abi::kTextureSlots; ++slot) {
        if (vs_textures[slot].scaled) dc.vs_scaled_textures |= 1u << slot;
        if (ps_textures[slot].scaled) dc.ps_scaled_textures |= 1u << slot;
    }
    dc.look = look;
    if (record) record_constants(draw_index, sources, dc);
    if (replaying_) replace_constants(draw_index, dc);
    // TTT2_SHADOW_CHECK=2: the draw as it was, writing guest memory.
    const bool check_draw = shadow_check_ == 2 && so_writes.video_count != 0;
    abi::DrawConstants reference{};
    if (check_draw) {
        reference = dc;
        for (uint32_t i = 0; i < so_writes.video_count; ++i) {
            reference.so[so_writes.video[i].index] = so_writes.video[i].guest;
        }
    }
    if (video_constants_on_ && so_writes.video_count != 0) video_constants(regs, vs, dc);

    // Vertex buffers that may be read from video memory need the vertex
    // indices' range (a replayed stream-out draw writes nothing: left alone).
    bool track = false;
    if (!shadows_.empty() && !(replaying_ && stream_out && rasterizer_discard)) {
        track = stream_out && !replaying_;
        for (uint32_t n = 0; n < 16 && !track; ++n) {
            track = vs->info.vb_extent[n] != 0 && dc.vb[n].size != 0 &&
                    touches_shadow(vb_address[n], uint64_t{vb_address[n]} + dc.vb[n].size);
        }
    }
    uint32_t first_index = UINT32_MAX, last_index = 0;
    // (A replay has its frame's range: the indices cannot have changed.)
    DrawRecord* range_record = nullptr;
    if (track && logging_ && draw_index < frame_records_[current_record_].draws.size()) {
        range_record = &frame_records_[current_record_].draws[draw_index];
        if (replaying_ && range_record->has_range) {
            first_index = range_record->first_index;
            last_index = range_record->last_index;
            range_record = nullptr;
            track = false;
        }
    }
    const bool redirect = track || first_index <= last_index;
    const auto note_index = [&](uint32_t v) {
        if (track) {
            first_index = std::min(first_index, v);
            if (v != 0xFFFFFFFFu || !restart_enabled) last_index = std::max(last_index, v);
        }
        return v;
    };

    // Indices, converted to 32-bit host order (and to triangles for quads).
    uint32_t index_count = d.count;
    VkDeviceSize index_offset = 0;
    if (indexed) {
        const uint32_t type = r(reg::VGT_DMA_INDEX_TYPE);
        const bool wide = type & 1;
        const uint32_t swap = (type >> 2) & 3;
        const uint32_t restart_index = r(reg::VGT_MULTI_PRIM_IB_RESET_INDX);
        const uint8_t* source = nullptr;
        if (d.source != Draw::kAuto) {
            const uint32_t bytes = d.count * (wide ? 4 : 2);
            if (d.host_indices) {
                source = d.host_indices;
            } else {
                if (!guest_memory_committed(d.index_address, bytes)) {
                    report_once("draw skipped: index buffer outside guest memory, at", d.index_address);
                    ++skipped_draws_;
                    return;
                }
                source = guest_pointer(d.index_address);
            }
        }
        const auto index = [&](uint32_t i) -> uint32_t {
            if (source == nullptr) return i;
            uint32_t v;
            if (d.source == Draw::kImmediate) {
                // Packet dwords are big-endian; 16-bit indices low half first.
                const uint32_t word = __builtin_bswap32(reinterpret_cast<const uint32_t*>(source)[wide ? i : i / 2]);
                v = wide ? word : (i & 1 ? word >> 16 : word & 0xFFFF);
            } else if (wide) {
                std::memcpy(&v, source + i * 4, 4);
                if (swap == 2) v = __builtin_bswap32(v);
                else if (swap == 1) v = ((v & 0x00FF00FFu) << 8) | ((v >> 8) & 0x00FF00FFu);
            } else {
                uint16_t h;
                std::memcpy(&h, source + i * 2, 2);
                if (swap != 0) h = static_cast<uint16_t>((h >> 8) | (h << 8));
                v = h;
            }
            if (restart && v == restart_index) return 0xFFFFFFFFu;
            return v;
        };
        if (convert == Convert::kQuads) index_count = d.count / 4 * 6;
        else if (convert == Convert::kQuadStrip) index_count = d.count >= 4 ? (d.count - 2) / 2 * 6 : 0;
        else if (convert == Convert::kLoop) index_count = d.count + 1;
        if (index_count == 0) return;
        uint32_t* out = reinterpret_cast<uint32_t*>(upload(VkDeviceSize{index_count} * 4, 4, index_offset));
        switch (convert) {
        case Convert::kNone:
            if (d.source == Draw::kIndexBuffer && (wide ? swap == 2 || swap == 0 : true)) {
                // The common case, in loops the compiler vectorises (the
                // range of indices kept in loops of their own).
                const uint32_t marker = restart ? restart_index : 0xFFFFFFFFu;
                const auto convert_indices = [&](auto tracking) {
                    // (Locals: the stores could alias what the lambda refers to.)
                    const uint32_t count = index_count, mark = marker;
                    const bool restarts = restart_enabled;
                    uint32_t* to = out;
                    uint32_t lo = UINT32_MAX, hi = 0;
                    if (wide) {
                        const uint32_t* in = reinterpret_cast<const uint32_t*>(source);
                        for (uint32_t i = 0; i < count; ++i) {
                            uint32_t v;
                            std::memcpy(&v, in + i, 4);
                            v = swap == 2 ? __builtin_bswap32(v) : v;
                            const uint32_t x = v == mark ? 0xFFFFFFFFu : v;
                            to[i] = x;
                            if constexpr (decltype(tracking)::value) {
                                lo = std::min(lo, x);
                                hi = std::max(hi, restarts && x == 0xFFFFFFFFu ? 0u : x);
                            }
                        }
                    } else {
                        const uint16_t* in = reinterpret_cast<const uint16_t*>(source);
                        for (uint32_t i = 0; i < count; ++i) {
                            uint16_t h;
                            std::memcpy(&h, in + i, 2);
                            const uint32_t v = swap != 0 ? static_cast<uint16_t>((h >> 8) | (h << 8)) : h;
                            const uint32_t x = v == mark ? 0xFFFFFFFFu : v;
                            to[i] = x;
                            if constexpr (decltype(tracking)::value) {
                                lo = std::min(lo, x);
                                hi = std::max(hi, restarts && x == 0xFFFFFFFFu ? 0u : x);
                            }
                        }
                    }
                    if constexpr (decltype(tracking)::value) {
                        first_index = lo;
                        last_index = hi;
                    }
                };
                if (track) convert_indices(std::true_type{});
                else convert_indices(std::false_type{});
                break;
            }
            for (uint32_t i = 0; i < index_count; ++i) out[i] = note_index(index(i));
            break;
        case Convert::kQuads:
            for (uint32_t q = 0; q < d.count / 4; ++q) {
                static constexpr uint32_t kOrder[6] = {0, 1, 2, 0, 2, 3};
                for (int k = 0; k < 6; ++k) out[q * 6 + k] = note_index(index(q * 4 + kOrder[k]));
            }
            break;
        case Convert::kQuadStrip:
            for (uint32_t q = 0; q < (d.count - 2) / 2; ++q) {
                static constexpr uint32_t kOrder[6] = {0, 1, 3, 0, 3, 2};
                for (int k = 0; k < 6; ++k) out[q * 6 + k] = note_index(index(q * 2 + kOrder[k]));
            }
            break;
        case Convert::kLoop:
            for (uint32_t i = 0; i < d.count; ++i) out[i] = note_index(index(i));
            out[d.count] = index(0);
            break;
        }
    } else {
        first_index = 0;
        last_index = d.count - 1;
    }
    if (range_record != nullptr && !replaying_) {
        range_record->has_range = true;
        range_record->first_index = first_index;
        range_record->last_index = last_index;
    }

    // Vertex buffers stream-out wrote, read from video memory where it can.
    GuestRanges guest_reads;
    if (redirect) {
        redirect_vertex_buffers(vs, dc, vb_address, first_index, last_index, stream_out && !replaying_, guest_reads);
    }

    const VkDeviceSize ubo_align = std::max<VkDeviceSize>(ctx_.properties.limits.minUniformBufferOffsetAlignment, 16);
    VkDeviceSize dc_offset = 0, check_offset = 0;
    std::memcpy(upload(sizeof(dc), ubo_align, dc_offset), &dc, sizeof(dc));
    if (check_draw) std::memcpy(upload(sizeof(reference), ubo_align, check_offset), &reference, sizeof(reference));
    VkDeviceSize reg_offset[2] = {};
    if (vs->info.uses_registers) {
        std::memcpy(upload(4096, ubo_align, reg_offset[0]), &regs.value[reg::SQ_ALU_CONSTANT0_256 >> 2], 4096);
    }
    if (ps->info.uses_registers) {
        std::memcpy(upload(4096, ubo_align, reg_offset[1]), &regs.value[reg::SQ_ALU_CONSTANT0_0 >> 2], 4096);
    }

    // Stream-out data a run of stream-out draws wrote, read by the draws
    // after it (skinned vertices, text): a barrier first, outside the pass.
    // Its copies back to guest memory are recorded there and finished by
    // the next barrier: a draw using guest memory under them waits first.
    const bool writes_stream_out = stream_out && !replaying_;
    int pending = 0;
    if (!copy_backs_.empty() || !unsynced_.empty()) {
        for (uint32_t i = 0; i < 16; ++i) {
            const auto block = [&](uint32_t cache, uint32_t size_reg, uint32_t mask) {
                const uint32_t a = r(cache + i * 4) << 8;
                if ((mask >> i) & 1 && a != 0) guest_reads.add(a, uint64_t{a} + (r(size_reg + i * 4) << 8));
            };
            block(reg::SQ_ALU_CONST_CACHE_VS_0, reg::SQ_ALU_CONST_BUFFER_SIZE_VS_0, vs->info.constant_bank_mask);
            block(reg::SQ_ALU_CONST_CACHE_PS_0, reg::SQ_ALU_CONST_BUFFER_SIZE_PS_0, ps->info.constant_bank_mask);
            const auto resource = [&](uint32_t slot, uint32_t mask) {
                const uint32_t base = kResourceBase + slot * resource::kWords * 4;
                if ((mask >> i) & 1) guest_reads.add(r(base), uint64_t{r(base)} + r(base + 4) + 1);
            };
            resource(resource::kVsBuffer + i, vs->info.buffer_mask);
            resource(resource::kPsBuffer + i, ps->info.buffer_mask);
        }
        pending = copies_back_pending(guest_reads, so_writes);
        if (pending) ++shadow_stats_.flushes;
    }
    if ((stream_out_pending_ && !writes_stream_out) || pending) {
        if (rendering_) end_rendering();
        else barrier();
        if (pending == 2) barrier(); // (the copies just recorded)
    }

    // The rendering pass.
    const auto begin_pass = [&] {
        if (!rendering_ || pass_depth_ != depth ||
            !std::equal(colors.begin(), colors.end(), pass_colors_.begin())) {
            end_rendering();
            uint32_t width = UINT32_MAX, height = UINT32_MAX;
            VkRenderingAttachmentInfo ca[8]{};
            for (uint32_t i = 0; i < color_count; ++i) {
                ca[i].sType = VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO;
                if (colors[i] == nullptr) continue;
                ca[i].imageView = colors[i]->image.view;
                ca[i].imageLayout = VK_IMAGE_LAYOUT_GENERAL;
                ca[i].loadOp = VK_ATTACHMENT_LOAD_OP_LOAD;
                ca[i].storeOp = VK_ATTACHMENT_STORE_OP_STORE;
                width = std::min(width, colors[i]->image.width);
                height = std::min(height, colors[i]->image.height);
            }
            VkRenderingAttachmentInfo da{VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO};
            if (depth) {
                da.imageView = depth->image.view;
                da.imageLayout = VK_IMAGE_LAYOUT_GENERAL;
                da.loadOp = VK_ATTACHMENT_LOAD_OP_LOAD;
                da.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
                width = std::min(width, depth->image.width);
                height = std::min(height, depth->image.height);
            }
            if (width == UINT32_MAX) width = height = 1;
            VkRenderingInfo info{VK_STRUCTURE_TYPE_RENDERING_INFO};
            info.renderArea = {{0, 0}, {width, height}};
            info.layerCount = 1;
            info.colorAttachmentCount = color_count;
            info.pColorAttachments = ca;
            info.pDepthAttachment = depth ? &da : nullptr;
            info.pStencilAttachment = depth && has_stencil(depth->image.format) ? &da : nullptr;
            vkCmdBeginRendering(cmd(), &info);
            rendering_ = true;
            pass_colors_ = colors;
            pass_depth_ = depth;
            pass_width_ = width;
            pass_height_ = height;
        }
    };
    begin_pass();
    VkCommandBuffer c = cmd();
    if (bound_pipeline_ != pipe) {
        vkCmdBindPipeline(c, VK_PIPELINE_BIND_POINT_GRAPHICS, pipe->pipeline);
        bound_pipeline_ = pipe;
    }

    // Descriptors.
    VkWriteDescriptorSet writes[3 + 2 * abi::kTextureSlots];
    uint32_t write_count = 0;
    VkDescriptorBufferInfo buffers[3];
    VkDescriptorImageInfo images[2 * abi::kTextureSlots];
    const auto write_buffer = [&](uint32_t binding, VkDeviceSize offset, VkDeviceSize range) {
        VkDescriptorBufferInfo& b = buffers[write_count];
        b = {ring_.buffer(), offset, range};
        VkWriteDescriptorSet& w = writes[write_count++];
        w = {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
        w.dstBinding = binding;
        w.descriptorCount = 1;
        w.descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        w.pBufferInfo = &b;
    };
    write_buffer(abi::kDrawConstantsBinding, dc_offset, sizeof(dc));
    if (vs->info.uses_registers) write_buffer(abi::kVsRegistersBinding, reg_offset[0], 4096);
    if (ps->info.uses_registers) write_buffer(abi::kPsRegistersBinding, reg_offset[1], 4096);
    uint32_t image_count = 0;
    const auto write_textures = [&](const ShaderModule* s, const Bound* bound, uint32_t binding_base) {
        for (uint32_t slot = 0; slot < abi::kTextureSlots; ++slot) {
            if (!(s->info.texture_mask & (1u << slot))) continue;
            VkDescriptorImageInfo& ii = images[image_count++];
            ii = {bound[slot].sampler, bound[slot].view, VK_IMAGE_LAYOUT_GENERAL};
            VkWriteDescriptorSet& w = writes[write_count++];
            w = {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
            w.dstBinding = binding_base + slot;
            w.descriptorCount = 1;
            w.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
            w.pImageInfo = &ii;
        }
    };
    write_textures(vs, vs_textures, abi::kVsTextureBinding);
    write_textures(ps, ps_textures, abi::kPsTextureBinding);
    ctx_.cmd_push_descriptor_set(c, VK_PIPELINE_BIND_POINT_GRAPHICS, pipe->layout, 0, write_count, writes);

    // Viewport: the Latte transform as is (negative heights flip y).
    const float xscale = std::bit_cast<float>(r(reg::PA_CL_VPORT_XSCALE_0));
    const float xoffset = std::bit_cast<float>(r(reg::PA_CL_VPORT_XSCALE_0 + 4));
    const float yscale = std::bit_cast<float>(r(reg::PA_CL_VPORT_XSCALE_0 + 8));
    const float yoffset = std::bit_cast<float>(r(reg::PA_CL_VPORT_XSCALE_0 + 12));
    const float zscale = std::bit_cast<float>(r(reg::PA_CL_VPORT_XSCALE_0 + 16));
    const float zoffset = std::bit_cast<float>(r(reg::PA_CL_VPORT_XSCALE_0 + 20));
    VkViewport viewport{};
    const float vscale = pass_scale;
    viewport.x = (xoffset - xscale) * vscale;
    viewport.width = 2.0f * xscale * vscale;
    viewport.y = (yoffset - yscale) * vscale;
    viewport.height = 2.0f * yscale * vscale;
    if (viewport.width <= 0.0f) {
        viewport.x += viewport.width;
        viewport.width = std::max(-viewport.width, 1.0f);
    }
    if (vs_env.clip_space_dx) {
        viewport.minDepth = zoffset;
        viewport.maxDepth = zoffset + zscale;
    } else {
        viewport.minDepth = zoffset - zscale;
        viewport.maxDepth = zoffset + zscale;
    }
    viewport.minDepth = std::clamp(viewport.minDepth, 0.0f, 1.0f);
    viewport.maxDepth = std::clamp(viewport.maxDepth, 0.0f, 1.0f);
    if ((r(reg::PA_CL_VTE_CNTL) & 0x3F) != 0x3F) report_once("viewport transform partly disabled", r(reg::PA_CL_VTE_CNTL));
    vkCmdSetViewport(c, 0, 1, &viewport);
    const uint32_t tl = r(reg::PA_SC_GENERIC_SCISSOR_TL), br = r(reg::PA_SC_GENERIC_SCISSOR_TL + 4);
    const uint32_t vtl = r(reg::PA_SC_VPORT_SCISSOR_0_TL), vbr = r(reg::PA_SC_VPORT_SCISSOR_0_TL + 4);
    int32_t x0 = std::max<int32_t>(tl & 0x7FFF, vtl & 0x7FFF), y0 = std::max<int32_t>((tl >> 16) & 0x7FFF, (vtl >> 16) & 0x7FFF);
    int32_t x1 = std::min<int32_t>(br & 0x7FFF, vbr & 0x7FFF), y1 = std::min<int32_t>((br >> 16) & 0x7FFF, (vbr >> 16) & 0x7FFF);
    // An edge takes the image pixels whose centres are inside it: e * scale
    // at the whole scales; at 1.5 the pixels a title pixel covers more than
    // half of (as the rasteriser's coverage of the scaled viewport).
    const auto edge = [&](int32_t e) { return static_cast<int32_t>(std::ceil(e * pass_scale - 0.5f)); };
    x0 = edge(x0);
    y0 = edge(y0);
    x1 = edge(x1);
    y1 = edge(y1);
    x1 = std::min<int32_t>(x1, static_cast<int32_t>(pass_width_));
    y1 = std::min<int32_t>(y1, static_cast<int32_t>(pass_height_));
    VkRect2D scissor{{x0, y0}, {static_cast<uint32_t>(std::max(x1 - x0, 0)), static_cast<uint32_t>(std::max(y1 - y0, 0))}};
    vkCmdSetScissor(c, 0, 1, &scissor);

    const uint32_t mode = r(reg::PA_SU_SC_MODE_CNTL);
    VkCullModeFlags cull = 0;
    if (mode & 1) cull |= VK_CULL_MODE_FRONT_BIT;
    if (mode & 2) cull |= VK_CULL_MODE_BACK_BIT;
    vkCmdSetCullMode(c, cull);
    // FACE: 0 counter-clockwise front, in the y-down window space Vulkan uses too.
    vkCmdSetFrontFace(c, (mode >> 2) & 1 ? VK_FRONT_FACE_CLOCKWISE : VK_FRONT_FACE_COUNTER_CLOCKWISE);
    vkCmdSetPrimitiveTopology(c, topology);
    vkCmdSetPrimitiveRestartEnable(c, restart_enabled);
    vkCmdSetRasterizerDiscardEnable(c, rasterizer_discard);
    vkCmdSetLineWidth(c, 1.0f);
    const bool offset_enable = (mode >> 11) & 1;
    vkCmdSetDepthBiasEnable(c, offset_enable);
    if (offset_enable) {
        const float scale = std::bit_cast<float>(r(reg::PA_SU_POLY_OFFSET_FRONT_SCALE));
        const float offset = std::bit_cast<float>(r(reg::PA_SU_POLY_OFFSET_FRONT_SCALE + 4));
        const float clamp = std::bit_cast<float>(r(reg::PA_SU_POLY_OFFSET_CLAMP));
        vkCmdSetDepthBias(c, offset, clamp, scale / 16.0f);
    }
    float blend_constants[4];
    for (int i = 0; i < 4; ++i) blend_constants[i] = std::bit_cast<float>(r(reg::CB_BLEND_RED + i * 4));
    vkCmdSetBlendConstants(c, blend_constants);

    const bool has_depth = depth != nullptr;
    const bool has_stencil_aspect = has_depth && (depth->image.aspect & VK_IMAGE_ASPECT_STENCIL_BIT);
    vkCmdSetDepthTestEnable(c, has_depth && ((depth_control >> 1) & 1));
    vkCmdSetDepthWriteEnable(c, has_depth && ((depth_control >> 2) & 1));
    vkCmdSetDepthCompareOp(c, static_cast<VkCompareOp>((depth_control >> 4) & 7));
    vkCmdSetDepthBoundsTestEnable(c, VK_FALSE);
    const bool stencil = has_stencil_aspect && (depth_control & 1);
    vkCmdSetStencilTestEnable(c, stencil);
    const bool backface = (depth_control >> 7) & 1;
    const auto op = [](uint32_t v) { return static_cast<VkStencilOp>(v & 7); };
    vkCmdSetStencilOp(c, VK_STENCIL_FACE_FRONT_BIT, op(depth_control >> 11), op(depth_control >> 14), op(depth_control >> 17),
                      static_cast<VkCompareOp>((depth_control >> 8) & 7));
    if (backface) {
        vkCmdSetStencilOp(c, VK_STENCIL_FACE_BACK_BIT, op(depth_control >> 23), op(depth_control >> 26),
                          op(depth_control >> 29), static_cast<VkCompareOp>((depth_control >> 20) & 7));
    } else {
        vkCmdSetStencilOp(c, VK_STENCIL_FACE_BACK_BIT, op(depth_control >> 11), op(depth_control >> 14),
                          op(depth_control >> 17), static_cast<VkCompareOp>((depth_control >> 8) & 7));
    }
    const uint32_t ref = r(reg::DB_STENCILREFMASK), ref_bf = backface ? r(reg::DB_STENCILREFMASK_BF) : ref;
    vkCmdSetStencilReference(c, VK_STENCIL_FACE_FRONT_BIT, ref & 0xFF);
    vkCmdSetStencilCompareMask(c, VK_STENCIL_FACE_FRONT_BIT, (ref >> 8) & 0xFF);
    vkCmdSetStencilWriteMask(c, VK_STENCIL_FACE_FRONT_BIT, (ref >> 16) & 0xFF);
    vkCmdSetStencilReference(c, VK_STENCIL_FACE_BACK_BIT, ref_bf & 0xFF);
    vkCmdSetStencilCompareMask(c, VK_STENCIL_FACE_BACK_BIT, (ref_bf >> 8) & 0xFF);
    vkCmdSetStencilWriteMask(c, VK_STENCIL_FACE_BACK_BIT, (ref_bf >> 16) & 0xFF);

    if (tracing()) {
        uint64_t vh = 0, ph = 0, fh = 0;
        program(r(reg::SQ_PGM_START_VS) << 8, r(reg::SQ_PGM_START_VS + 4) << 3, vh);
        program(r(reg::SQ_PGM_START_PS) << 8, r(reg::SQ_PGM_START_PS + 4) << 3, ph);
        program(r(reg::SQ_PGM_START_FS) << 8, r(reg::SQ_PGM_START_FS + 4) << 3, fh);
        std::fprintf(stderr, "trace: draw prim 0x%X count %u%s inst %u vs %016llx ps %016llx fs %016llx\n",
                     r(reg::VGT_PRIMITIVE_TYPE), d.count, indexed ? " indexed" : "", instances,
                     static_cast<unsigned long long>(vh), static_cast<unsigned long long>(ph),
                     static_cast<unsigned long long>(fh));
        std::fprintf(stderr, "trace:   spi_ps_in 0x%08X 0x%08X interp 0x%08X vs_out_cntl 0x%08X point 0x%08X\n",
                     r(reg::SPI_PS_IN_CONTROL_0), r(reg::SPI_PS_IN_CONTROL_0 + 4), r(reg::SPI_INTERP_CONTROL_0),
                     r(reg::PA_CL_VS_OUT_CNTL), r(reg::PA_SU_POINT_SIZE));
        for (uint32_t i = 0; i < color_count; ++i) {
            if (!colors[i]) continue;
            std::fprintf(stderr, "trace:   color%u 0x%08X fmt 0x%03X %ux%u tile %u mask 0x%X blend %s 0x%08X\n", i,
                         colors[i]->address, colors[i]->format, colors[i]->pitch, colors[i]->height,
                         colors[i]->tile_mode, (target_mask >> (4 * i)) & 0xF,
                         (r(reg::CB_COLOR_CONTROL) >> (8 + i)) & 1 ? "on" : "off", r(reg::CB_BLEND0_CONTROL + i * 4));
        }
        if (depth) {
            std::fprintf(stderr, "trace:   depth 0x%08X fmt 0x%03X %ux%u control 0x%08X\n", depth->address,
                         depth->format, depth->pitch, depth->height, depth_control);
        }
        const auto trace_textures = [&](const ShaderModule* s, uint32_t base, const char* stage) {
            for (uint32_t slot = 0; slot < abi::kTextureSlots; ++slot) {
                if (!(s->info.texture_mask & (1u << slot))) continue;
                uint32_t w[7];
                for (int i = 0; i < 7; ++i) w[i] = r(kResourceBase + ((base + slot) * resource::kWords + i) * 4);
                const Texture* t = texture(w);
                std::fprintf(stderr, "trace:   %s tex%u 0x%08X fmt 0x%03X %ux%ux%u dim %u tile %u pitch %u levels %u sel %03o %s\n",
                             stage, slot, w[2] << 8, texture_surface_format(w[1], w[4]), ((w[0] >> 19) & 0x1FFF) + 1,
                             (w[1] & 0x1FFF) + 1, ((w[1] >> 13) & 0x1FFF) + 1, w[0] & 7, (w[0] >> 3) & 0xF,
                             ((w[0] >> 8) & 0x7FF) * 8 + 8, (w[5] & 0xF) + 1, (w[4] >> 16) & 0xFFF,
                             t && t->source ? "(render target)" : "(memory)");
            }
        };
        trace_textures(vs, resource::kVsTexture, "vs");
        trace_textures(ps, resource::kPsTexture, "ps");
        std::fprintf(stderr, "trace:   viewport %g,%g %gx%g depth %g-%g scissor %d,%d %ux%u cull 0x%X\n", viewport.x,
                     viewport.y, viewport.width, viewport.height, viewport.minDepth, viewport.maxDepth, scissor.offset.x,
                     scissor.offset.y, scissor.extent.width, scissor.extent.height, mode & 7);
    }
    const auto record_draw = [&] {
        if (indexed) {
            vkCmdBindIndexBuffer(c, ring_.buffer(), index_offset, VK_INDEX_TYPE_UINT32);
            vkCmdDrawIndexed(c, index_count, instances, 0, 0, 0);
        } else {
            vkCmdDraw(c, d.count, instances, 0, 0);
        }
    };
    if (check_draw) {
        // The old path first, finished before the new one (whose reads of
        // guest memory then see its output).
        buffers[0].offset = check_offset;
        ctx_.cmd_push_descriptor_set(c, VK_PIPELINE_BIND_POINT_GRAPHICS, pipe->layout, 0, write_count, writes);
        record_draw();
        end_rendering();
        begin_pass();
        vkCmdBindPipeline(c, VK_PIPELINE_BIND_POINT_GRAPHICS, pipe->pipeline);
        bound_pipeline_ = pipe;
        buffers[0].offset = dc_offset;
        ctx_.cmd_push_descriptor_set(c, VK_PIPELINE_BIND_POINT_GRAPHICS, pipe->layout, 0, write_count, writes);
    }
    record_draw();
    if (writes_stream_out) {
        stream_out_pending_ = true;
        note_stream_writes(so_writes);
    }
    video_chunks_touched_ |= draw_video_chunks_; // (an upload may have submitted since the copies)
    if (profiling_) {
        profile_mark("draw", colors[0] ? colors[0]->address : depth ? depth->address : 0,
                     (colors[0] ? scaled(colors[0]->pitch, colors[0]->scale) : 0) << 16 |
                         (colors[0] ? scaled(colors[0]->height, colors[0]->scale) : 0),
                     d.count * std::max(instances, 1u));
    }

    const uint64_t now = stamp();
    for (uint32_t i = 0; i < color_count; ++i) {
        if (colors[i]) {
            const_cast<Target*>(colors[i])->written = now;
            note_target_written(colors[i]);
        }
    }
    if (depth && ((depth_control >> 2) & 1 || stencil)) {
        const_cast<Target*>(depth)->written = now;
        note_target_written(depth);
    }
}

} // namespace cafe::gpu::vk

// `ttt2 --precompile`: every pipeline of the cache directory's list made
// into the pipeline cache, on all processors but one, with no window and
// no game: what the game then asks for is there already. On standard
// output, the launchers' task lines (`@step`, `@progress done total`,
// `@done`) and a summary.
int cafe::gpu::precompile_shaders() {
    using namespace vk;
    const double begin = now_ms();
    if (cache_directory().empty()) {
        std::printf("@error There is no cache folder to keep shaders in\n");
        return 1;
    }
    const std::vector<std::string> lines = read_pipeline_list();
    if (lines.empty()) {
        std::printf("Nothing to prepare yet: the game notes the shaders it uses as it is played on this computer.\n@done\n");
        return 0;
    }
    std::printf("@step shaders Preparing shaders\n");
    std::fflush(stdout);
    Context ctx;
    {
        // (No window: the surface extension only because the device's
        // swapchain extension, which the renderer's device has, wants it.)
        uint32_t count = 0;
        vkEnumerateInstanceExtensionProperties(nullptr, &count, nullptr);
        std::vector<VkExtensionProperties> available(count);
        vkEnumerateInstanceExtensionProperties(nullptr, &count, available.data());
        std::vector<const char*> extensions;
        for (const VkExtensionProperties& e : available) {
            if (std::strcmp(e.extensionName, VK_KHR_SURFACE_EXTENSION_NAME) == 0) extensions.push_back(VK_KHR_SURFACE_EXTENSION_NAME);
        }
        ctx.init(extensions);
    }
    const VkPipelineCache cache = open_pipeline_cache(ctx.device);

    struct Work {
        PipelineKey key;
        VkPipelineLayout layout;
    };
    std::unordered_map<uint64_t, std::unique_ptr<ShaderModule>> modules; // by SPIR-V name; no handle: not in the cache
    std::unordered_map<uint64_t, VkPipelineLayout> layouts;
    std::vector<Work> work;
    size_t unusable = 0, without_shaders = 0;
    const auto module = [&](uint64_t hash) -> const ShaderModule* {
        auto& m = modules[hash];
        if (!m) {
            m = std::make_unique<ShaderModule>();
            if (const std::vector<uint32_t> spirv = load_cached_spirv(hash); !spirv.empty()) {
                m->module = create_module(ctx.device, spirv);
            }
        }
        return m->module != VK_NULL_HANDLE ? m.get() : nullptr;
    };
    std::unordered_set<std::string> seen;
    for (const std::string& line : lines) {
        uint64_t n[kListNumbers];
        if (!parse_list_line(line, n) || n[6] > 8 || !seen.insert(line).second) {
            ++unusable;
            continue;
        }
        Work w;
        std::memset(&w.key, 0, sizeof(w.key));
        w.key.vs = module(n[0]);
        w.key.ps = module(n[1]);
        if (w.key.vs == nullptr || w.key.ps == nullptr) {
            ++without_shaders;
            continue;
        }
        const uint64_t layout_key = (n[2] & 0x3FFFF) | ((n[3] & 0x3FFFF) << 18) | ((n[4] & 1) << 36) | ((n[5] & 1) << 37);
        auto [it, fresh] = layouts.try_emplace(layout_key, VK_NULL_HANDLE);
        if (fresh) {
            it->second = create_layout(ctx, static_cast<uint32_t>(n[2] & 0x3FFFF), static_cast<uint32_t>(n[3] & 0x3FFFF),
                                       n[4] & 1, n[5] & 1);
        }
        w.layout = it->second;
        w.key.color_count = static_cast<uint32_t>(n[6]);
        w.key.depth = static_cast<VkFormat>(n[7]);
        for (size_t i = 0; i < 8; ++i) {
            w.key.colors[i] = static_cast<VkFormat>(n[8 + i]);
            w.key.blend[i] = static_cast<uint32_t>(n[16 + i]);
        }
        w.key.write_mask = static_cast<uint32_t>(n[24]);
        w.key.polygon_mode = static_cast<uint32_t>(n[25]);
        w.key.topology_class = static_cast<uint32_t>(n[26]);
        w.key.depth_clamp = static_cast<uint32_t>(n[27]);
        work.push_back(w);
    }

    std::atomic<size_t> next{0}, done{0}, there{0}, made{0}, failed{0};
    const auto worker = [&] {
        for (size_t i = next++; i < work.size(); i = next++) {
            const Work& w = work[i];
            VkPipeline pipeline = VK_NULL_HANDLE;
            VkResult r = VK_PIPELINE_COMPILE_REQUIRED;
            if (ctx.pipeline_cache_control) {
                r = create_pipeline(ctx.device, cache, w.key, w.layout, VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT,
                                    &pipeline);
                if (r == VK_SUCCESS) ++there;
            }
            if (r == VK_PIPELINE_COMPILE_REQUIRED) {
                r = create_pipeline(ctx.device, cache, w.key, w.layout, 0, &pipeline);
                if (r == VK_SUCCESS) ++made;
            }
            if (r != VK_SUCCESS) ++failed;
            else vkDestroyPipeline(ctx.device, pipeline, nullptr);
            ++done;
        }
    };
    unsigned count = std::max(std::thread::hardware_concurrency(), 2u) - 1;
    if (const char* n = std::getenv("TTT2_SHADER_THREADS")) count = static_cast<unsigned>(std::clamp(std::atoi(n), 1, 64));
    std::vector<std::thread> threads;
    for (unsigned i = 0; i < count; ++i) threads.emplace_back(worker);
    for (size_t shown = SIZE_MAX; done < work.size();) {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        if (const size_t now = done; now != shown) {
            std::printf("@progress %zu %zu\n", now, work.size());
            std::fflush(stdout);
            shown = now;
        }
    }
    for (std::thread& t : threads) t.join();
    if (made != 0) write_pipeline_cache(ctx.device, cache);
    std::printf("@progress %zu %zu\n", work.size(), work.size());
    std::printf("Prepared in %.1f s on %u threads: %zu pipelines of %zu shaders (%zu made now, %zu were there%s); "
                "left out: %zu whose shaders are not in the cache, %zu lines not understood, %zu the driver refused\n@done\n",
                (now_ms() - begin) / 1000.0, count, work.size(), modules.size(), made.load(), there.load(),
                ctx.pipeline_cache_control ? "" : ": the device cannot tell", without_shaders, unusable, failed.load());
    std::fflush(stdout);
    return 0;
}

namespace cafe::gpu::vk {

void Renderer::ShaderCosts::add(const ShaderCosts& o) {
    translated += o.translated, loaded += o.loaded, compiled += o.compiled, pipelines += o.pipelines, hits += o.hits;
    queued += o.queued, waits += o.waits, skipped += o.skipped;
    translate_ms += o.translate_ms, load_ms += o.load_ms, compile_ms += o.compile_ms, pipeline_ms += o.pipeline_ms;
    hit_ms += o.hit_ms, wait_ms += o.wait_ms;
}

// TTT2_TRACE_SHADERS, at each swap: the frame's time on the gpu thread
// (swap to swap) and what first uses of shaders cost in it.
void Renderer::trace_shader_frame() {
    const double now = now_ms();
    const double took = trace_last_swap_ != 0 ? now - trace_last_swap_ : 0;
    trace_last_swap_ = now;
    const ShaderCosts& c = frame_costs_;
    static constexpr double kLong[4] = {25.0, 33.4, 50.0, 100.0};
    for (int i = 0; i < 4; ++i) {
        if (took > kLong[i]) {
            ++long_frames_[i];
            if (c.any()) ++long_compile_frames_[i];
        }
    }
    longest_frame_ = std::max(longest_frame_, took);
    if (c.any() || took > kLong[0]) {
        std::fprintf(stderr, "shaders: frame %llu took %.1f ms: translated %u (%.1f ms), loaded %u (%.1f ms), compiled %u (%.1f ms), "
                             "pipelines %u (%.1f ms), cached pipelines %u (%.1f ms), queued %u, waited for %u (%.1f ms), left out %u draws\n",
                     static_cast<unsigned long long>(frame_number_), took, c.translated, c.translate_ms, c.loaded, c.load_ms,
                     c.compiled, c.compile_ms, c.pipelines, c.pipeline_ms, c.hits, c.hit_ms, c.queued, c.waits, c.wait_ms,
                     c.skipped);
    }
    total_costs_.add(c);
    frame_costs_ = {};
    static double last_totals = now;
    if (now - last_totals >= 10000.0) {
        last_totals = now;
        const ShaderCosts& t = total_costs_;
        std::fprintf(stderr, "shaders: totals at frame %llu: translated %u (%.1f ms), loaded %u (%.1f ms), compiled %u (%.1f ms), "
                             "pipelines %u (%.1f ms), cached pipelines %u (%.1f ms), queued %u, waited for %u (%.1f ms), left out %u draws; "
                             "jobs: %llu shaders (%.1f ms), %llu pipelines (%.1f ms); frames over 25/33.4/50/100 ms: %llu/%llu/%llu/%llu "
                             "(with first uses: %llu/%llu/%llu/%llu), longest %.1f ms\n",
                     static_cast<unsigned long long>(frame_number_), t.translated, t.translate_ms, t.loaded, t.load_ms, t.compiled,
                     t.compile_ms, t.pipelines, t.pipeline_ms, t.hits, t.hit_ms, t.queued, t.waits, t.wait_ms, t.skipped,
                     static_cast<unsigned long long>(worker_shaders_.load()), worker_shader_us_.load() / 1000.0,
                     static_cast<unsigned long long>(worker_pipelines_.load()), worker_pipeline_us_.load() / 1000.0,
                     static_cast<unsigned long long>(long_frames_[0]), static_cast<unsigned long long>(long_frames_[1]),
                     static_cast<unsigned long long>(long_frames_[2]), static_cast<unsigned long long>(long_frames_[3]),
                     static_cast<unsigned long long>(long_compile_frames_[0]), static_cast<unsigned long long>(long_compile_frames_[1]),
                     static_cast<unsigned long long>(long_compile_frames_[2]), static_cast<unsigned long long>(long_compile_frames_[3]),
                     longest_frame_);
    }
}

} // namespace cafe::gpu::vk
