/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_TEMPORAL_H
#define CB1_HDR10_TEMPORAL_H
#include "cb1_hdr10_features.h"
#include "cb1_l1l3_model.h"
struct cb1_hdr10_temporal;
struct cb1_hdr10_temporal_result {
    struct cb1_ai_identity id;
    double pts,observed_until,peak;
    uint16_t base[3];float calibration[222];
};
struct cb1_hdr10_temporal *cb1_hdr10_temporal_create(void);
void cb1_hdr10_temporal_destroy(struct cb1_hdr10_temporal **ctx);
void cb1_hdr10_temporal_reset(struct cb1_hdr10_temporal *ctx,uint64_t stream,uint64_t revision);
enum cb1_ai_status cb1_hdr10_temporal_push(struct cb1_hdr10_temporal *ctx,
    const struct cb1_hdr10_descriptor *descriptor,const float motion[1728],struct cb1_ai_identity id);
/* Explicit EOF supplies a short final lookahead, never a guessed timeout. */
void cb1_hdr10_temporal_end(struct cb1_hdr10_temporal *ctx);
/* Seal a decoded timestamp frontier after every preceding picture was submitted. */
enum cb1_ai_status cb1_hdr10_temporal_advance(struct cb1_hdr10_temporal *ctx,double pts);
size_t cb1_hdr10_temporal_size(const struct cb1_hdr10_temporal *ctx);
enum cb1_ai_status cb1_hdr10_temporal_poll(struct cb1_hdr10_temporal *ctx,
    struct cb1_ai_identity id,struct cb1_hdr10_temporal_result *out);
#endif
