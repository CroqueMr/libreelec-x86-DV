/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DVBRIDGE_PLACEBO_H
#define DVBRIDGE_PLACEBO_H
#include <stdbool.h>
#include <stddef.h>
#include <libplacebo/colorspace.h>
#include "dvbridge_policy.h"

struct dvbridge_color {
    struct pl_color_space color;
    struct pl_color_repr repr;
    struct pl_dovi_metadata dovi;
};

struct dvbridge_hdr10_metadata {
    bool level6;
    unsigned max_luminance, min_luminance, max_cll, max_fall;
};
struct dvbridge_hdr10_session {
    struct pl_color_space target;
    struct dvbridge_hdr10_metadata output;
};
/* Construct a stream target and signal together; failure leaves out unchanged.
 * Required enhancement-layer pairing is checked when the picture is rendered. */
bool dvbridge_hdr10_session_init(struct dvbridge_hdr10_session *out,
                                 const void *metadata, size_t bytes);
bool dvbridge_get_hdr10_metadata(struct dvbridge_hdr10_metadata *out,
                                const void *metadata, size_t bytes);
/* Build a static PQ target in nits; dynamic L1 remains on the source only. */
bool dvbridge_hdr10_target(struct pl_color_space *out, const void *metadata, size_t bytes);

/* Output owns its mapping; do not copy it without rebinding repr.dovi. */
bool dvbridge_map_color(struct dvbridge_color *out, const void *metadata,
                       size_t bytes, bool enhancement_layer_paired);
/* Expert-only strict source and nominal LINEAR target. Outputs own their values;
 * color.repr.dovi is rebound exactly as for dvbridge_map_color. */
bool dvbridge_reference_map(struct dvbridge_color *color, struct pl_color_space *nominal,
                           struct dvbridge_hdr10_metadata *signal,
                           const struct dvbridge_policy *policy,
                           const void *metadata, size_t bytes, bool paired);
#endif
