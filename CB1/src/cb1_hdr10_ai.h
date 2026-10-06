/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_AI_H
#define CB1_HDR10_AI_H
#include <libplacebo/renderer.h>
#include "cb1_l1l3_model.h"
#ifdef __cplusplus
extern "C" {
#endif
struct cb1_hdr10_ai;
struct cb1_ai_result { struct cb1_ai_identity id;struct cb1_l1l3 raw;double pts; };
/* Submission wall time and asynchronous completion latency, not GPU utilization. */
struct cb1_hdr10_ai_metrics {
    uint64_t pictures,readback_bytes,inferences;
    uint64_t analysis_submit_ns,readback_latency_ns,inference_ns;
    /* Monotonic dispatch generation, including partially failed GPU batches. */
    uint64_t gpu_submissions;
};
/* Caller-confined GLES context; borrowed source planes are consumed only in submit. */
enum cb1_ai_status cb1_hdr10_ai_create(pl_gpu gpu,const char *bundle_dir,struct cb1_hdr10_ai **out);
void cb1_hdr10_ai_destroy(struct cb1_hdr10_ai **ctx);
void cb1_hdr10_ai_reset(struct cb1_hdr10_ai *ctx,uint64_t stream,uint64_t revision);
/* Pending means retry the same identity; a NULL frame advances that accepted job. */
enum cb1_ai_status cb1_hdr10_ai_submit(struct cb1_hdr10_ai *ctx,const struct pl_frame *frame,
    struct cb1_ai_identity id,double pts);
/* The player seals timestamp coverage only after submitting all preceding pictures. */
enum cb1_ai_status cb1_hdr10_ai_advance(struct cb1_hdr10_ai *ctx,double pts);
void cb1_hdr10_ai_end(struct cb1_hdr10_ai *ctx);
enum cb1_ai_status cb1_hdr10_ai_poll(struct cb1_hdr10_ai *ctx,struct cb1_ai_identity id,
    struct cb1_ai_result *out);
void cb1_hdr10_ai_metrics(const struct cb1_hdr10_ai *ctx,struct cb1_hdr10_ai_metrics *out);
#ifdef __cplusplus
}
#endif
#endif
