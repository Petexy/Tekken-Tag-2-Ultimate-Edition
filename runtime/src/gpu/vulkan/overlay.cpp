// The overlay (gpu/overlay.h) over each presentation image: one instanced
// draw of its quads, a quad per instance as a four-vertex strip, blended
// over the image right after the TV scan buffer is copied into it. The
// image holds display-ready (sRGB-encoded) values in a UNORM format, so the
// blend works on those values, as the title's own 2D blends do.
//
// Its solids come first, in a pass of their own with a depth buffer: each
// is a quad over the part of the image it can cover, whose fragments cast
// the pixel's ray through the title's camera (the inverse of its
// view-projection) and find the capsule's surface on it, shading it by its
// normal: lit from the camera, brighter at the edge, with rings round it
// at even heights and angles. The others go twice, their depths first and
// then their colours where those are nearest, so overlapping solids show
// one surface, blended once; those in front go last, without depths.

#include "gpu/overlay.h"
#include "gpu/vulkan/renderer.h"

#include "cafe/runtime.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <shaderc/shaderc.h>
#include <utility>

namespace cafe::gpu::vk {
namespace {

constexpr const char* kVertexShader = R"(#version 460
layout(location = 0) in vec4 rect;
layout(location = 1) in vec4 uv;
layout(location = 2) in vec4 top;
layout(location = 3) in vec4 bottom;
layout(location = 4) in vec4 add;
layout(location = 0) out vec2 v_uv;
layout(location = 1) out vec4 v_colour;
layout(location = 2) flat out vec4 v_add;
void main() {
    const vec2 corner = vec2(gl_VertexIndex & 1, gl_VertexIndex >> 1);
    gl_Position = vec4(mix(rect.xy, rect.zw, corner) / vec2(1280.0, 720.0) * 2.0 - 1.0, 0.0, 1.0);
    v_uv = mix(uv.xy, uv.zw, corner);
    v_colour = mix(top, bottom, corner.y);
    v_add = add;
}
)";

constexpr const char* kFragmentShader = R"(#version 460
layout(set = 0, binding = 0) uniform sampler2D atlas;
layout(location = 0) in vec2 v_uv;
layout(location = 1) in vec4 v_colour;
layout(location = 2) flat in vec4 v_add;
layout(location = 0) out vec4 colour;
// Premultiplied (the blend adds the image's share): the colour times the
// quad's, plus its add; blended additively when the add's alpha is set.
void main() {
    vec4 c = texture(atlas, v_uv) * v_colour;
    c.rgb = min(c.rgb + v_add.rgb, 1.0);
    colour = vec4(c.rgb * c.a, v_add.a > 0.5 ? 0.0 : c.a);
}
)";

// For a picture of the title's (its alpha means nothing).
constexpr const char* kOpaqueFragmentShader = R"(#version 460
layout(set = 0, binding = 0) uniform sampler2D atlas;
layout(location = 0) in vec2 v_uv;
layout(location = 1) in vec4 v_colour;
layout(location = 0) out vec4 colour;
void main() {
    const vec4 c = vec4(texture(atlas, v_uv).rgb, 1.0) * v_colour;
    colour = vec4(c.rgb * c.a, c.a);
}
)";

constexpr const char* kSolidVertexShader = R"(#version 460
layout(location = 0) in vec4 rect;
layout(location = 1) in vec4 a;
layout(location = 2) in vec4 b;
layout(location = 3) in vec4 colour;
layout(location = 0) flat out vec4 v_a;
layout(location = 1) flat out vec4 v_b;
layout(location = 2) flat out vec4 v_colour;
void main() {
    const vec2 corner = vec2(gl_VertexIndex & 1, gl_VertexIndex >> 1);
    gl_Position = vec4(mix(rect.xy, rect.zw, corner) / vec2(1280.0, 720.0) * 2.0 - 1.0, 0.0, 1.0);
    v_a = a;
    v_b = b;
    v_colour = colour;
}
)";

constexpr const char* kSolidFragmentShader = R"(#version 460
layout(push_constant) uniform Push {
    mat4 inverse_view_projection; // the title's, row vectors (so: M * v here)
    vec2 origin, size;            // of the view, in the image's pixels
} push;
layout(location = 0) flat in vec4 v_a; // an end (mm), the radius
layout(location = 1) flat in vec4 v_b; // the other end
layout(location = 2) flat in vec4 v_colour;
layout(location = 0) out vec4 colour;

float sphere(vec3 ro, vec3 rd, vec3 c, float r) {
    const vec3 oc = ro - c;
    const float b = dot(oc, rd), h = b * b - (dot(oc, oc) - r * r);
    return h < 0.0 ? -1.0 : -b - sqrt(h);
}

// Along the ray to the capsule's nearest surface, or -1.
float capsule(vec3 ro, vec3 rd, vec3 pa, vec3 pb, float r) {
    float best = 1e30;
    const vec3 ba = pb - pa, oa = ro - pa;
    const float baba = dot(ba, ba);
    if (baba > 1e-9) {
        const float bard = dot(ba, rd), baoa = dot(ba, oa), rdoa = dot(rd, oa), oaoa = dot(oa, oa);
        const float a = baba - bard * bard, b = baba * rdoa - baoa * bard, c = baba * oaoa - baoa * baoa - r * r * baba;
        const float h = b * b - a * c;
        if (a > 1e-12 && h >= 0.0) {
            const float t = (-b - sqrt(h)) / a, y = baoa + t * bard;
            if (t > 0.0 && y > 0.0 && y < baba) best = t;
        }
    }
    const float s0 = sphere(ro, rd, pa, r), s1 = sphere(ro, rd, pb, r);
    if (s0 > 0.0) best = min(best, s0);
    if (s1 > 0.0) best = min(best, s1);
    return best < 1e29 ? best : -1.0;
}

void main() {
    const vec2 t = (gl_FragCoord.xy - push.origin) / push.size;
    const vec2 ndc = vec2(t.x * 2.0 - 1.0, 1.0 - t.y * 2.0);
    const vec4 near = push.inverse_view_projection * vec4(ndc, -1.0, 1.0);
    const vec4 far = push.inverse_view_projection * vec4(ndc, 0.5, 1.0);
    // In metres from the first end, for precision.
    const vec3 ro = (near.xyz / near.w - v_a.xyz) * 0.001;
    const vec3 rd = normalize(far.xyz / far.w - near.xyz / near.w);
    const vec3 b = (v_b.xyz - v_a.xyz) * 0.001;
    const float hit = capsule(ro, rd, vec3(0.0), b, v_a.w * 0.001);
    if (hit < 0.0) discard;
    const vec3 p = ro + rd * hit;
    const float along = clamp(dot(p, b) / max(dot(b, b), 1e-12), 0.0, 1.0);
    const vec3 normal = normalize(p - b * along);
    const float facing = clamp(dot(normal, -rd), 0.0, 1.0), rim = pow(1.0 - facing, 2.0);
    const float diffuse = clamp(dot(normal, normalize(-rd + vec3(0.0, 0.8, 0.0))), 0.0, 1.0);
    const vec2 ring = vec2(asin(clamp(normal.y, -1.0, 1.0)), atan(normal.z, normal.x)) * (6.0 / 3.14159265);
    const vec2 line = (0.5 - abs(fract(ring) - 0.5)) / max(fwidth(ring), vec2(1e-4));
    const float grid = 1.0 - clamp(min(line.x, line.y), 0.0, 1.0);
    colour = vec4(v_colour.rgb * (0.35 + 0.65 * diffuse) + vec3(0.35 * rim + 0.25 * grid),
                  clamp(v_colour.a * (0.6 + 0.8 * rim + 0.5 * grid), 0.0, 1.0));
    gl_FragDepth = clamp(hit / 100.0, 0.0, 1.0);
}
)";

// A solid as the vertex shader reads it, per instance.
struct SolidInstance {
    float rect[4], a[4], b[4];
    uint8_t colour[4];
    float pad[3];
};
static_assert(sizeof(SolidInstance) == 64);

struct SolidPush {
    float inverse_view_projection[16];
    float origin[2], size[2];
};

// The inverse of a 4 x 4 matrix (row-major); false if it has none.
bool invert(const float m[16], float out[16]) {
    double a[4][8];
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) a[r][c] = m[4 * r + c], a[r][4 + c] = r == c ? 1 : 0;
    }
    for (int c = 0; c < 4; ++c) {
        int pivot = c;
        for (int r = c + 1; r < 4; ++r) {
            if (std::abs(a[r][c]) > std::abs(a[pivot][c])) pivot = r;
        }
        if (std::abs(a[pivot][c]) < 1e-12) return false;
        std::swap(a[c], a[pivot]);
        const double d = a[c][c];
        for (double& v : a[c]) v /= d;
        for (int r = 0; r < 4; ++r) {
            if (r == c) continue;
            const double f = a[r][c];
            for (int k = 0; k < 8; ++k) a[r][k] -= f * a[c][k];
        }
    }
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) out[4 * r + c] = static_cast<float>(a[r][4 + c]);
    }
    return true;
}

// The part of the TV image the solid can cover (its box's corners seen
// through the camera), a little more; all of it when it reaches behind.
void cover(const overlay::Solid& s, const float m[16], float rect[4]) {
    rect[0] = rect[1] = 1e9f, rect[2] = rect[3] = -1e9f;
    for (int corner = 0; corner < 8; ++corner) {
        float p[3];
        for (int k = 0; k < 3; ++k) {
            const float lo = std::min(s.a[k], s.b[k]) - s.radius, hi = std::max(s.a[k], s.b[k]) + s.radius;
            p[k] = corner & (1 << k) ? hi : lo;
        }
        const auto clip = [&](int k) { return p[0] * m[k] + p[1] * m[4 + k] + p[2] * m[8 + k] + m[12 + k]; };
        const float w = clip(3);
        if (!(w > 1)) {
            rect[0] = rect[1] = 0, rect[2] = overlay::kWidth, rect[3] = overlay::kHeight;
            return;
        }
        const float x = (clip(0) / w + 1) * overlay::kWidth / 2, y = (1 - clip(1) / w) * overlay::kHeight / 2;
        rect[0] = std::min(rect[0], x), rect[1] = std::min(rect[1], y);
        rect[2] = std::max(rect[2], x), rect[3] = std::max(rect[3], y);
    }
    rect[0] = std::max(rect[0] - 2, 0.0f), rect[1] = std::max(rect[1] - 2, 0.0f);
    rect[2] = std::min(rect[2] + 2, overlay::kWidth), rect[3] = std::min(rect[3] + 2, overlay::kHeight);
}

// A quad as the vertex shader reads it, per instance.
struct Instance {
    float rect[4], uv[4];
    uint8_t top[4], bottom[4], add[4];
};
static_assert(sizeof(Instance) == 44);

void bytes(uint32_t rgba, uint8_t out[4]) {
    for (int i = 0; i < 4; ++i) out[i] = static_cast<uint8_t>(rgba >> (24 - 8 * i));
}

} // namespace

VkShaderModule Renderer::overlay_module(const char* source, bool vertex) {
    shaderc_compile_options_t options = shaderc_compile_options_initialize();
    shaderc_compile_options_set_target_env(options, shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_3);
    shaderc_compilation_result_t result =
        shaderc_compile_into_spv(compiler_, source, std::strlen(source),
                                 vertex ? shaderc_vertex_shader : shaderc_fragment_shader, "overlay", "main", options);
    shaderc_compile_options_release(options);
    if (shaderc_result_get_compilation_status(result) != shaderc_compilation_status_success) {
        fatal("Vulkan: the overlay shader does not compile: %s", shaderc_result_get_error_message(result));
    }
    VkShaderModuleCreateInfo mci{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    mci.codeSize = shaderc_result_get_length(result);
    mci.pCode = reinterpret_cast<const uint32_t*>(shaderc_result_get_bytes(result));
    VkShaderModule module;
    VK_CHECK(vkCreateShaderModule(ctx_.device, &mci, nullptr, &module));
    shaderc_result_release(result);
    return module;
}

VkPipeline Renderer::overlay_pipeline(VkFormat format, bool opaque) {
    if (const auto it = overlay_pipelines_.find({format, opaque}); it != overlay_pipelines_.end()) return it->second;
    if (overlay_layout_ == VK_NULL_HANDLE) {
        const VkDescriptorSetLayoutBinding binding{0, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1,
                                                   VK_SHADER_STAGE_FRAGMENT_BIT, nullptr};
        VkDescriptorSetLayoutCreateInfo dli{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
        dli.flags = VK_DESCRIPTOR_SET_LAYOUT_CREATE_PUSH_DESCRIPTOR_BIT_KHR;
        dli.bindingCount = 1;
        dli.pBindings = &binding;
        VkDescriptorSetLayout set_layout;
        VK_CHECK(vkCreateDescriptorSetLayout(ctx_.device, &dli, nullptr, &set_layout));
        VkPipelineLayoutCreateInfo pli{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
        pli.setLayoutCount = 1;
        pli.pSetLayouts = &set_layout;
        VK_CHECK(vkCreatePipelineLayout(ctx_.device, &pli, nullptr, &overlay_layout_));
        VkSamplerCreateInfo sci{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
        sci.magFilter = sci.minFilter = VK_FILTER_LINEAR;
        sci.addressModeU = sci.addressModeV = sci.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
        VK_CHECK(vkCreateSampler(ctx_.device, &sci, nullptr, &overlay_sampler_));
    }
    const VkShaderModule vs = overlay_module(kVertexShader, true),
                         fs = overlay_module(opaque ? kOpaqueFragmentShader : kFragmentShader, false);
    const VkPipelineShaderStageCreateInfo stages[2] = {
        {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, nullptr, 0, VK_SHADER_STAGE_VERTEX_BIT, vs, "main", nullptr},
        {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, nullptr, 0, VK_SHADER_STAGE_FRAGMENT_BIT, fs, "main", nullptr},
    };
    const VkVertexInputBindingDescription binding{0, sizeof(Instance), VK_VERTEX_INPUT_RATE_INSTANCE};
    const VkVertexInputAttributeDescription attributes[5] = {
        {0, 0, VK_FORMAT_R32G32B32A32_SFLOAT, offsetof(Instance, rect)},
        {1, 0, VK_FORMAT_R32G32B32A32_SFLOAT, offsetof(Instance, uv)},
        {2, 0, VK_FORMAT_R8G8B8A8_UNORM, offsetof(Instance, top)},
        {3, 0, VK_FORMAT_R8G8B8A8_UNORM, offsetof(Instance, bottom)},
        {4, 0, VK_FORMAT_R8G8B8A8_UNORM, offsetof(Instance, add)},
    };
    VkPipelineVertexInputStateCreateInfo vi{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
    vi.vertexBindingDescriptionCount = 1;
    vi.pVertexBindingDescriptions = &binding;
    vi.vertexAttributeDescriptionCount = 5;
    vi.pVertexAttributeDescriptions = attributes;
    VkPipelineInputAssemblyStateCreateInfo ia{VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
    ia.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP;
    VkPipelineViewportStateCreateInfo vp{VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
    vp.viewportCount = vp.scissorCount = 1;
    VkPipelineRasterizationStateCreateInfo rs{VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
    rs.polygonMode = VK_POLYGON_MODE_FILL;
    rs.cullMode = VK_CULL_MODE_NONE;
    rs.lineWidth = 1.0f;
    VkPipelineMultisampleStateCreateInfo ms{VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
    ms.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
    VkPipelineDepthStencilStateCreateInfo ds{VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO};
    VkPipelineColorBlendAttachmentState blend{};
    blend.blendEnable = VK_TRUE;
    blend.srcColorBlendFactor = VK_BLEND_FACTOR_ONE; // (premultiplied by the shaders)
    blend.dstColorBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
    blend.colorBlendOp = VK_BLEND_OP_ADD;
    blend.srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
    blend.dstAlphaBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
    blend.alphaBlendOp = VK_BLEND_OP_ADD;
    blend.colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT | VK_COLOR_COMPONENT_B_BIT |
                           VK_COLOR_COMPONENT_A_BIT;
    VkPipelineColorBlendStateCreateInfo cb{VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
    cb.attachmentCount = 1;
    cb.pAttachments = &blend;
    const VkDynamicState dynamic[2] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
    VkPipelineDynamicStateCreateInfo dyn{VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO};
    dyn.dynamicStateCount = 2;
    dyn.pDynamicStates = dynamic;
    VkPipelineRenderingCreateInfo ri{VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO};
    ri.colorAttachmentCount = 1;
    ri.pColorAttachmentFormats = &format;
    VkGraphicsPipelineCreateInfo gpi{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
    gpi.pNext = &ri;
    gpi.stageCount = 2;
    gpi.pStages = stages;
    gpi.pVertexInputState = &vi;
    gpi.pInputAssemblyState = &ia;
    gpi.pViewportState = &vp;
    gpi.pRasterizationState = &rs;
    gpi.pMultisampleState = &ms;
    gpi.pDepthStencilState = &ds;
    gpi.pColorBlendState = &cb;
    gpi.pDynamicState = &dyn;
    gpi.layout = overlay_layout_;
    VkPipeline pipeline;
    VK_CHECK(vkCreateGraphicsPipelines(ctx_.device, VK_NULL_HANDLE, 1, &gpi, nullptr, &pipeline));
    vkDestroyShaderModule(ctx_.device, vs, nullptr);
    vkDestroyShaderModule(ctx_.device, fs, nullptr);
    overlay_pipelines_[{format, opaque}] = pipeline;
    return pipeline;
}

VkPipeline Renderer::overlay_solid_pipeline(VkFormat format, int pass) {
    if (const auto it = overlay_solid_pipelines_.find({format, pass}); it != overlay_solid_pipelines_.end()) {
        return it->second;
    }
    if (overlay_solid_layout_ == VK_NULL_HANDLE) {
        const VkPushConstantRange range{VK_SHADER_STAGE_FRAGMENT_BIT, 0, sizeof(SolidPush)};
        VkPipelineLayoutCreateInfo pli{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
        pli.pushConstantRangeCount = 1;
        pli.pPushConstantRanges = &range;
        VK_CHECK(vkCreatePipelineLayout(ctx_.device, &pli, nullptr, &overlay_solid_layout_));
    }
    const VkShaderModule vs = overlay_module(kSolidVertexShader, true), fs = overlay_module(kSolidFragmentShader, false);
    const VkPipelineShaderStageCreateInfo stages[2] = {
        {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, nullptr, 0, VK_SHADER_STAGE_VERTEX_BIT, vs, "main", nullptr},
        {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, nullptr, 0, VK_SHADER_STAGE_FRAGMENT_BIT, fs, "main", nullptr},
    };
    const VkVertexInputBindingDescription binding{0, sizeof(SolidInstance), VK_VERTEX_INPUT_RATE_INSTANCE};
    const VkVertexInputAttributeDescription attributes[4] = {
        {0, 0, VK_FORMAT_R32G32B32A32_SFLOAT, offsetof(SolidInstance, rect)},
        {1, 0, VK_FORMAT_R32G32B32A32_SFLOAT, offsetof(SolidInstance, a)},
        {2, 0, VK_FORMAT_R32G32B32A32_SFLOAT, offsetof(SolidInstance, b)},
        {3, 0, VK_FORMAT_R8G8B8A8_UNORM, offsetof(SolidInstance, colour)},
    };
    VkPipelineVertexInputStateCreateInfo vi{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
    vi.vertexBindingDescriptionCount = 1;
    vi.pVertexBindingDescriptions = &binding;
    vi.vertexAttributeDescriptionCount = 4;
    vi.pVertexAttributeDescriptions = attributes;
    VkPipelineInputAssemblyStateCreateInfo ia{VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
    ia.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP;
    VkPipelineViewportStateCreateInfo vp{VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
    vp.viewportCount = vp.scissorCount = 1;
    VkPipelineRasterizationStateCreateInfo rs{VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
    rs.polygonMode = VK_POLYGON_MODE_FILL;
    rs.cullMode = VK_CULL_MODE_NONE;
    rs.lineWidth = 1.0f;
    VkPipelineMultisampleStateCreateInfo ms{VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
    ms.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
    VkPipelineDepthStencilStateCreateInfo ds{VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO};
    ds.depthTestEnable = pass < 2;
    ds.depthWriteEnable = pass == 0;
    ds.depthCompareOp = pass == 0 ? VK_COMPARE_OP_LESS : VK_COMPARE_OP_EQUAL;
    VkPipelineColorBlendAttachmentState blend{};
    blend.blendEnable = VK_TRUE;
    blend.srcColorBlendFactor = VK_BLEND_FACTOR_SRC_ALPHA;
    blend.dstColorBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
    blend.colorBlendOp = VK_BLEND_OP_ADD;
    blend.srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
    blend.dstAlphaBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
    blend.alphaBlendOp = VK_BLEND_OP_ADD;
    blend.colorWriteMask = pass == 0 ? 0 : VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT | VK_COLOR_COMPONENT_B_BIT |
                                               VK_COLOR_COMPONENT_A_BIT;
    VkPipelineColorBlendStateCreateInfo cb{VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
    cb.attachmentCount = 1;
    cb.pAttachments = &blend;
    const VkDynamicState dynamic[2] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
    VkPipelineDynamicStateCreateInfo dyn{VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO};
    dyn.dynamicStateCount = 2;
    dyn.pDynamicStates = dynamic;
    VkPipelineRenderingCreateInfo ri{VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO};
    ri.colorAttachmentCount = 1;
    ri.pColorAttachmentFormats = &format;
    ri.depthAttachmentFormat = VK_FORMAT_D32_SFLOAT;
    VkGraphicsPipelineCreateInfo gpi{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
    gpi.pNext = &ri;
    gpi.stageCount = 2;
    gpi.pStages = stages;
    gpi.pVertexInputState = &vi;
    gpi.pInputAssemblyState = &ia;
    gpi.pViewportState = &vp;
    gpi.pRasterizationState = &rs;
    gpi.pMultisampleState = &ms;
    gpi.pDepthStencilState = &ds;
    gpi.pColorBlendState = &cb;
    gpi.pDynamicState = &dyn;
    gpi.layout = overlay_solid_layout_;
    VkPipeline pipeline;
    VK_CHECK(vkCreateGraphicsPipelines(ctx_.device, VK_NULL_HANDLE, 1, &gpi, nullptr, &pipeline));
    vkDestroyShaderModule(ctx_.device, vs, nullptr);
    vkDestroyShaderModule(ctx_.device, fs, nullptr);
    overlay_solid_pipelines_[{format, pass}] = pipeline;
    return pipeline;
}

void Renderer::draw_overlay_solids(const Image& target, const void* scene_pointer, const float* view_projection,
                                   const float* view) {
    const overlay::Scene& scene = *static_cast<const overlay::Scene*>(scene_pointer);
    SolidPush push{};
    if (!invert(view_projection, push.inverse_view_projection)) return;
    // The view (TV pixels) in the image.
    const float sx = static_cast<float>(target.width) / overlay::kWidth, sy = static_cast<float>(target.height) / overlay::kHeight;
    push.origin[0] = view[0] * sx, push.origin[1] = view[1] * sy;
    push.size[0] = (view[2] - view[0]) * sx, push.size[1] = (view[3] - view[1]) * sy;
    end_rendering();
    if (overlay_depth_.image == VK_NULL_HANDLE || overlay_depth_.width != target.width ||
        overlay_depth_.height != target.height) {
        if (overlay_depth_.image != VK_NULL_HANDLE) {
            submit(true); // nothing recorded uses the old one any more
            destroy_image(overlay_depth_);
        }
        overlay_depth_ = create_image(VK_FORMAT_D32_SFLOAT, VK_IMAGE_ASPECT_DEPTH_BIT, target.width, target.height, 1, 1,
                                      VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT, VK_IMAGE_VIEW_TYPE_2D);
    }
    // The others, then those in front.
    std::vector<const overlay::Solid*> order;
    for (const overlay::Solid& s : scene.solids) {
        if (!s.in_front) order.push_back(&s);
    }
    const uint32_t others = static_cast<uint32_t>(order.size());
    for (const overlay::Solid& s : scene.solids) {
        if (s.in_front) order.push_back(&s);
    }
    VkDeviceSize offset = 0;
    auto* instances = reinterpret_cast<SolidInstance*>(upload(order.size() * sizeof(SolidInstance), 16, offset));
    for (size_t i = 0; i < order.size(); ++i) {
        const overlay::Solid& s = *order[i];
        SolidInstance& in = instances[i];
        in = {};
        cover(s, view_projection, in.rect);
        for (int k = 0; k < 4; ++k) { // (into the view)
            const float lo = view[k & 1], extent = (view[2 + (k & 1)] - lo) / (k & 1 ? overlay::kHeight : overlay::kWidth);
            in.rect[k] = lo + in.rect[k] * extent;
        }
        for (int k = 0; k < 3; ++k) in.a[k] = s.a[k], in.b[k] = s.b[k];
        in.a[3] = s.radius;
        bytes(s.colour, in.colour);
    }
    VkPipeline pipelines[3];
    for (int pass = 0; pass < 3; ++pass) pipelines[pass] = overlay_solid_pipeline(target.format, pass);
    barrier(); // the copy into the image, the depth buffer's last use
    VkCommandBuffer c = cmd();
    VkRenderingAttachmentInfo attachment{VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO};
    attachment.imageView = target.view;
    attachment.imageLayout = VK_IMAGE_LAYOUT_GENERAL;
    attachment.loadOp = VK_ATTACHMENT_LOAD_OP_LOAD;
    attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
    VkRenderingAttachmentInfo depth{VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO};
    depth.imageView = overlay_depth_.view;
    depth.imageLayout = VK_IMAGE_LAYOUT_GENERAL;
    depth.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
    depth.storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
    depth.clearValue.depthStencil = {1.0f, 0};
    VkRenderingInfo info{VK_STRUCTURE_TYPE_RENDERING_INFO};
    info.renderArea = {{0, 0}, {target.width, target.height}};
    info.layerCount = 1;
    info.colorAttachmentCount = 1;
    info.pColorAttachments = &attachment;
    info.pDepthAttachment = &depth;
    vkCmdBeginRendering(c, &info);
    const VkViewport viewport{0, 0, static_cast<float>(target.width), static_cast<float>(target.height), 0, 1};
    const int32_t x0 = std::max(0, static_cast<int32_t>(push.origin[0])), y0 = std::max(0, static_cast<int32_t>(push.origin[1]));
    const VkRect2D scissor{{x0, y0},
                           {std::min(target.width - static_cast<uint32_t>(x0), static_cast<uint32_t>(std::ceil(push.size[0]))),
                            std::min(target.height - static_cast<uint32_t>(y0), static_cast<uint32_t>(std::ceil(push.size[1])))}};
    vkCmdSetViewport(c, 0, 1, &viewport);
    vkCmdSetScissor(c, 0, 1, &scissor);
    const VkBuffer buffer = ring_.buffer();
    vkCmdBindVertexBuffers(c, 0, 1, &buffer, &offset);
    for (int pass = 0; pass < 3; ++pass) {
        const uint32_t first = pass < 2 ? 0 : others, count = pass < 2 ? others : static_cast<uint32_t>(order.size()) - others;
        if (count == 0) continue;
        vkCmdBindPipeline(c, VK_PIPELINE_BIND_POINT_GRAPHICS, pipelines[pass]);
        vkCmdPushConstants(c, overlay_solid_layout_, VK_SHADER_STAGE_FRAGMENT_BIT, 0, sizeof(push), &push);
        vkCmdDraw(c, 4, count, 0, first);
    }
    vkCmdEndRendering(c);
    bound_pipeline_ = nullptr;
}

void Renderer::draw_overlay(const Image& target) {
    const overlay::State state = overlay::current();
    static constexpr float kWhole[4] = {0, 0, overlay::kWidth, overlay::kHeight};
    draw_overlay_quads(target, overlay_hud_atlas_, state.hud_atlas, state.hud_quads);
    if (state.scene) draw_overlay_solids(target, state.scene.get(), state.scene->view_projection, kWhole);
    draw_overlay_quads(target, overlay_atlas_, state.atlas, state.quads);
    if (state.window && view_image_valid_) {
        const overlay::Window& w = *state.window;
        const overlay::Quad q{w.rect[0], w.rect[1], w.rect[2], w.rect[3], w.crop[0] / overlay::kWidth,
                              w.crop[1] / overlay::kHeight, w.crop[2] / overlay::kWidth, w.crop[3] / overlay::kHeight,
                              0xFFFFFFFF, 0xFFFFFFFF};
        draw_overlay_image(target, view_image_, {q}, true);
        if (state.scene) draw_overlay_solids(target, state.scene.get(), w.view_projection, w.rect);
    }
    draw_overlay_quads(target, overlay_pointer_atlas_, state.pointer_atlas, state.pointer_quads);
}

void Renderer::draw_overlay_quads(const Image& target, OverlayAtlas& cached,
                                  const std::shared_ptr<const overlay::Atlas>& atlas,
                                  const std::shared_ptr<const std::vector<overlay::Quad>>& quads) {
    if (!quads || !atlas || atlas->width == 0) return;
    end_rendering();
    if (atlas.get() != cached.source) {
        if (cached.image.image != VK_NULL_HANDLE) {
            submit(true); // nothing recorded reads the old one any more
            destroy_image(cached.image);
        }
        const overlay::Atlas& a = *atlas;
        cached.image = create_image(VK_FORMAT_R8G8B8A8_UNORM, VK_IMAGE_ASPECT_COLOR_BIT, a.width, a.height, 1, 1,
                                    VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT,
                                    VK_IMAGE_VIEW_TYPE_2D);
        VkDeviceSize offset = 0;
        uint8_t* p = upload(a.pixels.size(), 16, offset);
        std::memcpy(p, a.pixels.data(), a.pixels.size());
        VkBufferImageCopy region{};
        region.bufferOffset = offset;
        region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        region.imageExtent = {a.width, a.height, 1};
        vkCmdCopyBufferToImage(cmd(), ring_.buffer(), cached.image.image, VK_IMAGE_LAYOUT_GENERAL, 1, &region);
        cached.source = atlas.get();
        cached.keep = atlas;
    }
    draw_overlay_image(target, cached.image, *quads);
}

// Quads sampling `image`.
void Renderer::draw_overlay_image(const Image& target, const Image& image_source, const std::vector<overlay::Quad>& quads,
                                  bool opaque) {
    VkDeviceSize offset = 0;
    auto* instances = reinterpret_cast<Instance*>(upload(quads.size() * sizeof(Instance), 16, offset));
    for (size_t i = 0; i < quads.size(); ++i) {
        const overlay::Quad& q = quads[i];
        Instance& in = instances[i];
        in = {{q.x0, q.y0, q.x1, q.y1}, {q.u0, q.v0, q.u1, q.v1}, {}, {}, {}};
        bytes(q.top, in.top);
        bytes(q.bottom, in.bottom);
        bytes(q.add, in.add);
    }
    const VkPipeline pipeline = overlay_pipeline(target.format, opaque);
    barrier(); // the copy into the image, the atlas upload
    VkCommandBuffer c = cmd();
    VkRenderingAttachmentInfo attachment{VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO};
    attachment.imageView = target.view;
    attachment.imageLayout = VK_IMAGE_LAYOUT_GENERAL;
    attachment.loadOp = VK_ATTACHMENT_LOAD_OP_LOAD;
    attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
    VkRenderingInfo info{VK_STRUCTURE_TYPE_RENDERING_INFO};
    info.renderArea = {{0, 0}, {target.width, target.height}};
    info.layerCount = 1;
    info.colorAttachmentCount = 1;
    info.pColorAttachments = &attachment;
    vkCmdBeginRendering(c, &info);
    const VkViewport viewport{0, 0, static_cast<float>(target.width), static_cast<float>(target.height), 0, 1};
    const VkRect2D scissor{{0, 0}, {target.width, target.height}};
    vkCmdSetViewport(c, 0, 1, &viewport);
    vkCmdSetScissor(c, 0, 1, &scissor);
    vkCmdBindPipeline(c, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
    const VkDescriptorImageInfo image{overlay_sampler_, image_source.view, VK_IMAGE_LAYOUT_GENERAL};
    VkWriteDescriptorSet write{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
    write.dstBinding = 0;
    write.descriptorCount = 1;
    write.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
    write.pImageInfo = &image;
    ctx_.cmd_push_descriptor_set(c, VK_PIPELINE_BIND_POINT_GRAPHICS, overlay_layout_, 0, 1, &write);
    const VkBuffer buffer = ring_.buffer();
    vkCmdBindVertexBuffers(c, 0, 1, &buffer, &offset);
    vkCmdDraw(c, 4, static_cast<uint32_t>(quads.size()), 0, 0);
    vkCmdEndRendering(c);
    bound_pipeline_ = nullptr;
}

} // namespace cafe::gpu::vk
