/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_QUANTILES_H
#define CB1_HDR10_QUANTILES_H
#include "cb1_hdr10_extrema.h"
#ifdef __cplusplus
extern "C" {
#endif
struct cb1_hdr10_quantiles;
/* RGB48 MaxRGB quantiles on the frozen active-area grid.
 * GLES 3.1, current borrowed context, one submission at a time.
 * Caller supplies bounds validated by the full-resolution extrema pass.
 * No image readback; only fourteen exact order-statistic codes are transferred. */
struct cb1_hdr10_quantiles *cb1_hdr10_quantiles_create(pl_gpu gpu);
void cb1_hdr10_quantiles_destroy(struct cb1_hdr10_quantiles **ctx);
void cb1_hdr10_quantiles_reset(struct cb1_hdr10_quantiles *ctx, uint64_t stream, uint64_t revision);
enum cb1_ai_status cb1_hdr10_quantiles_submit(struct cb1_hdr10_quantiles *ctx, pl_tex pq,
    struct cb1_hdr10_bounds bounds, struct cb1_ai_identity id);
/* Quantiles: .05, .25, .5, .75, .95, .99, .999. Failure/pending preserves out. */
enum cb1_ai_status cb1_hdr10_quantiles_poll(struct cb1_hdr10_quantiles *ctx,
    struct cb1_ai_identity id, float out[7]);
#ifdef __cplusplus
}
#endif
#endif
