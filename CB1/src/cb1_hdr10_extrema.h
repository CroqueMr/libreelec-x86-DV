/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_EXTREMA_H
#define CB1_HDR10_EXTREMA_H
#include <libplacebo/gpu.h>
#include "cb1_l1l3_model.h"
#ifdef __cplusplus
extern "C" {
#endif

struct cb1_hdr10_extrema;
struct cb1_hdr10_bounds {
    unsigned x0, y0, x1, y1;
    uint16_t minimum, maximum;
};
/* RGB PQ is quantized to the frozen RGB48 analysis representation.
 * One submission at a time. GPU/context remains valid through destruction.
 * Submit borrows the texture; libplacebo owns pending command references. */
struct cb1_hdr10_extrema *cb1_hdr10_extrema_create(pl_gpu gpu);
void cb1_hdr10_extrema_destroy(struct cb1_hdr10_extrema **ctx);
/* Retire pending results on seek or policy change; no GPU recovery is implied. */
void cb1_hdr10_extrema_reset(struct cb1_hdr10_extrema *ctx, uint64_t stream, uint64_t revision);
enum cb1_ai_status cb1_hdr10_extrema_submit(struct cb1_hdr10_extrema *ctx, pl_tex pq,
                                          struct cb1_ai_identity id);
/* Non-blocking query; invalid/pending leaves out unchanged. Reads 16 bytes. */
enum cb1_ai_status cb1_hdr10_extrema_poll(struct cb1_hdr10_extrema *ctx,
                                       struct cb1_ai_identity id,
                                       struct cb1_hdr10_bounds *out);
#ifdef __cplusplus
}
#endif
#endif
