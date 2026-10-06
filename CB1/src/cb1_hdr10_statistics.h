/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_STATISTICS_H
#define CB1_HDR10_STATISTICS_H
#include "cb1_hdr10_extrema.h"
#ifdef __cplusplus
extern "C" {
#endif
struct cb1_hdr10_statistics;
/* Caller-confined GLES 3.1 context. One RGB48-compatible job at a time.
 * Quantile slots 4..10 remain zero, supplied by the exact histogram helper. */
struct cb1_hdr10_statistics *cb1_hdr10_statistics_create(pl_gpu gpu);
void cb1_hdr10_statistics_destroy(struct cb1_hdr10_statistics **ctx);
void cb1_hdr10_statistics_reset(struct cb1_hdr10_statistics *ctx,uint64_t stream,uint64_t revision);
enum cb1_ai_status cb1_hdr10_statistics_submit(struct cb1_hdr10_statistics *ctx,pl_tex texture,
    struct cb1_hdr10_bounds bounds,struct cb1_ai_identity id);
/* Nonblocking, identity-bound, 128-byte statistics readback. Failure preserves out. */
enum cb1_ai_status cb1_hdr10_statistics_poll(struct cb1_hdr10_statistics *ctx,
    struct cb1_ai_identity id,float out[35]);
#ifdef __cplusplus
}
#endif
#endif
