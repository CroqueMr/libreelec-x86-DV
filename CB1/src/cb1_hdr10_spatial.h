/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_SPATIAL_H
#define CB1_HDR10_SPATIAL_H
#include <libplacebo/gpu.h>
#include "cb1_l1l3_model.h"
struct cb1_hdr10_spatial;
struct cb1_hdr10_spatial_result { float features[38],motion[3*18*32]; };
struct cb1_hdr10_spatial *cb1_hdr10_spatial_create(pl_gpu gpu);
void cb1_hdr10_spatial_destroy(struct cb1_hdr10_spatial **ctx);
void cb1_hdr10_spatial_reset(struct cb1_hdr10_spatial *ctx,uint64_t stream,uint64_t revision);
/* Input is the matched 128x72 binary16-quantized analysis texture. */
enum cb1_ai_status cb1_hdr10_spatial_submit(struct cb1_hdr10_spatial *ctx,pl_tex texture,struct cb1_ai_identity id);
enum cb1_ai_status cb1_hdr10_spatial_poll(struct cb1_hdr10_spatial *ctx,struct cb1_ai_identity id,
    struct cb1_hdr10_spatial_result *out);
#endif
