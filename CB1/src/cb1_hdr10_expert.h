/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_HDR10_EXPERT_H
#define CB1_HDR10_EXPERT_H
#include "dvbridge_creative.h"
#include "dvbridge_placebo.h"
#include <libplacebo/tone_mapping.h>
#include <libplacebo/shaders/colorspace.h>

/* Frame-owned value plan. Source DOVI points into this owner, never a caller's
 * temporary metadata. Scalar scene data is not relabelled as CIE-Y metadata. */
struct cb1_hdr10_expert_plan {
    struct dvbridge_color source;
    struct pl_color_space target;
    struct dvbridge_hdr10_metadata signal;
    struct dvbridge_creative_plan creative;
    struct pl_tone_map_params tone;
    float tone_shape[3];
};
bool cb1_hdr10_expert_prepare(struct cb1_hdr10_expert_plan *out,
    const struct dvbridge_policy *policy,const void *metadata,size_t bytes,bool paired);
/* Finite validated Expert policy only. Native output/range is not a user trim. */
float cb1_hdr10_expert_ceiling(const struct dvbridge_policy *policy);
/* Linear target RGB chroma only; luminance trims execute in the tone LUT. */
bool cb1_hdr10_expert_trim(pl_shader shader,const struct dvbridge_creative_plan *plan,
                          enum pl_color_primaries primaries);
#endif
