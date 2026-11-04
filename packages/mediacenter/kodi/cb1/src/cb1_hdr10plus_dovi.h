/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_HDR10PLUS_DOVI_H
#define CB1_HDR10PLUS_DOVI_H
#include <stdbool.h>
#include <libavutil/hdr_dynamic_metadata.h>
#include "cb1_l1l3_model.h"
#ifdef __cplusplus
extern "C" {
#endif

enum cb1_hdr10plus_dovi_status {
    CB1_HDR10PLUS_DOVI_OK, CB1_HDR10PLUS_DOVI_INVALID, CB1_HDR10PLUS_DOVI_UNSUPPORTED
};
enum cb1_hdr10plus_dovi_field {
    CB1_HDR10PLUS_DOVI_MIN=1, CB1_HDR10PLUS_DOVI_MAX=2, CB1_HDR10PLUS_DOVI_AVG=4
};
struct cb1_hdr10plus_dovi_result {
    struct cb1_l1l3 metadata;
    unsigned source_fields, estimated_fields;
    bool untranslated_curve, untranslated_saturation;
};
/* Input must be fully validated at ingress (Kodi VideoSourceSideData::Capture).
 * This adapter validates only fields it consumes; it is not an SEI parser.
 * Single full-picture window; caller verifies frame/scene/area identity.
 * Valid distributions estimate mean PQ by weighted percentile trapezoids.
 * L1 minimum is conservatively0, not the mastering-display minimum.
 * Missing/unusable distribution uses AI when supplied; otherwise PQ(linear
 * average) is a labeled estimate. NULL estimate never invokes image analysis.
 * No image processing, mastering-target inference or source mutation.
 * Zero MaxSCL supplies no usable peak to the current nonzero-peak DV transport.
 * Failure preserves out. */
enum cb1_hdr10plus_dovi_status cb1_hdr10plus_dovi_describe(
    struct cb1_hdr10plus_dovi_result *out,const AVDynamicHDRPlus *source,
    const struct cb1_l1l3 *estimate);
bool cb1_hdr10plus_dovi_same_scene(const AVDynamicHDRPlus *a,const AVDynamicHDRPlus *b);
#ifdef __cplusplus
}
#endif
#endif
