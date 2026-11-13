/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_HDR10PLUS_ANALYSIS_H
#define CB1_HDR10PLUS_ANALYSIS_H
#include <libplacebo/gpu.h>
#include <libplacebo/opengl.h>
#include <GLES3/gl31.h>
#include "dvbridge_policy.h"
#include "cb1_hdr10plus.h"
#ifdef __cplusplus
extern "C" {
#endif

/* Linear-light nits. Histogram entries use the HDMI 16-nit quantization,
 * saturating at code 255. Every pixel in the selected rectangle is counted. */
struct cb1_hdr10plus_statistics {
    double maxscl[3], average_maxrgb;
    uint64_t count;
    uint32_t histogram[256];
    unsigned y99_nits;
    double y100_percent;
    bool luminance_valid;
};
struct cb1_hdr10plus_scene {
    struct dvbridge_identity last;
    unsigned y99_nits;
    double y100_sum;
    uint64_t pictures;
};
enum cb1_hdr10plus_analysis_status {
    CB1_HDR10PLUS_ANALYSIS_INVALID,
    CB1_HDR10PLUS_ANALYSIS_PENDING,
    CB1_HDR10PLUS_ANALYSIS_READY,
    /* A cancelled job still owns the buffer. Retry submit, not poll. */
    CB1_HDR10PLUS_ANALYSIS_BUSY
};
struct cb1_hdr10plus_analysis;
static inline bool cb1_hdr10plus_analysis_supported(pl_gpu gpu)
{
    pl_opengl gl=gpu?pl_opengl_get(gpu):NULL;
    if(!gl || !gpu->glsl.gles || gl->major<3 || (gl->major==3 && gl->minor<1))return false;
    GLint size,threads,shared,groups,bindings;GLint64 storage;
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_SIZE,0,&size);
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT,0,&groups);
    glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS,&threads);
    glGetIntegerv(GL_MAX_COMPUTE_SHARED_MEMORY_SIZE,&shared);
    glGetIntegerv(GL_MAX_SHADER_STORAGE_BUFFER_BINDINGS,&bindings);
    glGetInteger64v(GL_MAX_SHADER_STORAGE_BLOCK_SIZE,&storage);
    return size>=128 && threads>=128 && shared>=5120 && groups>=64 && bindings>=1 &&
        storage>=64*518*4 && glGetError()==GL_NO_ERROR;
}
struct cb1_hdr10plus_analysis *cb1_hdr10plus_analysis_create(pl_log log, pl_gpu gpu);
void cb1_hdr10plus_analysis_destroy(struct cb1_hdr10plus_analysis **ctx);
void cb1_hdr10plus_analysis_reset(struct cb1_hdr10plus_analysis *ctx);
void cb1_hdr10plus_analysis_clear_scene(struct cb1_hdr10plus_analysis *ctx);
/* Input: reconstructed, full-range BT.2020 PQ RGB, before tone mapping or GUI. */
enum cb1_hdr10plus_analysis_status cb1_hdr10plus_analysis_submit(
    struct cb1_hdr10plus_analysis *ctx, pl_tex rgb, pl_rect2d area,
    struct dvbridge_identity identity, unsigned application_version);
enum cb1_hdr10plus_analysis_status cb1_hdr10plus_analysis_poll(
    struct cb1_hdr10plus_analysis *ctx, struct dvbridge_identity identity,
    struct cb1_hdr10plus_statistics *out);
/* Accumulate on the pending scene snapshot and commit it with the picture. */
void cb1_hdr10plus_scene_update(struct cb1_hdr10plus_scene *scene,
    struct cb1_hdr10plus_statistics *statistics, struct dvbridge_identity identity,
    bool scene_refresh);
void cb1_hdr10plus_analysis_stage_scene(struct cb1_hdr10plus_analysis *ctx,
    struct cb1_hdr10plus_statistics *statistics, bool scene_refresh);
void cb1_hdr10plus_analysis_commit_scene(struct cb1_hdr10plus_analysis *ctx);
/* Descriptive metadata only. No synthesized creative curve. */
bool cb1_hdr10plus_describe(AVDynamicHDRPlus *out,
    const struct cb1_hdr10plus_statistics *statistics, unsigned target_nits);
bool cb1_hdr10plus_describe_for_version(AVDynamicHDRPlus *out,
    const struct cb1_hdr10plus_statistics *statistics, unsigned target_nits,
    unsigned application_version);

#ifdef __cplusplus
}
#endif
#endif
