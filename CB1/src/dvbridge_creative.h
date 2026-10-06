/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef DVBRIDGE_CREATIVE_H
#define DVBRIDGE_CREATIVE_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <libplacebo/colorspace.h>
#include "dvbridge_policy.h"
#ifdef __cplusplus
extern "C" {
#endif

enum dvbridge_creative_status {
    DVBRIDGE_CREATIVE_INVALID, DVBRIDGE_CREATIVE_UNSUPPORTED,
    DVBRIDGE_CREATIVE_NEUTRAL, DVBRIDGE_CREATIVE_READY
};
enum dvbridge_creative_backend {
    DVBRIDGE_CREATIVE_NONE, DVBRIDGE_CREATIVE_CM29,
    DVBRIDGE_CREATIVE_CM29_COMPATIBILITY, DVBRIDGE_CREATIVE_PRESERVE_CM4,
    DVBRIDGE_CREATIVE_CM4 /* Independent scalar/spatial contract. */
};
enum dvbridge_creative_reason {
    DVBRIDGE_CREATIVE_OK, DVBRIDGE_CREATIVE_NO_ANCHOR,
    DVBRIDGE_CREATIVE_CM4_EDIT_UNQUALIFIED, DVBRIDGE_CREATIVE_CM4_RENDER_PARTIAL,
    DVBRIDGE_CREATIVE_SPATIAL_UNQUALIFIED, DVBRIDGE_CREATIVE_DETAIL_NO_COMPRESSION,
    DVBRIDGE_CREATIVE_EDIT_NOT_REPRESENTABLE, DVBRIDGE_CREATIVE_EDIT_TARGET_UNRESOLVED,
    DVBRIDGE_CREATIVE_MASTERING_UNSUPPORTED, DVBRIDGE_CREATIVE_MASTERING_INCONSISTENT
};
enum dvbridge_cm4_target_origin {
    DVBRIDGE_CM4_PRESET, DVBRIDGE_CM4_CUSTOM, DVBRIDGE_CM4_MANUAL
};
enum dvbridge_cm4_target_status {
    DVBRIDGE_CM4_NO_CONTROLS, DVBRIDGE_CM4_TARGETS_RESOLVED,
    DVBRIDGE_CM4_UNKNOWN_TARGET, DVBRIDGE_CM4_INCOMPATIBLE_TARGETS
};
enum dvbridge_cm4_presence {
    DVBRIDGE_CM4_PRIMARY=1u, DVBRIDGE_CM4_MID_CONTRAST=2u,
    DVBRIDGE_CM4_CLIP_TRIM=4u, DVBRIDGE_CM4_SATURATION=8u,
    DVBRIDGE_CM4_HUE=16u
};
struct dvbridge_cm4_target {
    uint8_t display_index;
    uint16_t min_pq, max_pq;
    struct pl_raw_primaries primaries;
    enum pl_color_transfer transfer;
    enum dvbridge_cm4_target_origin origin;
    bool min_pq_present; /* Preset/manual black level is not inferred. */
};
struct dvbridge_cm4_controls {
    uint16_t primary[6]; /* Slope, offset, power, chroma, saturation, ms. */
    uint16_t mid_contrast, clip_trim;
    uint8_t saturation[6], hue[6];
    uint32_t present_fields;
};
struct dvbridge_cm4_anchor {
    struct dvbridge_cm4_target target;
    struct dvbridge_cm4_controls controls;
    bool present;
};
#define DVBRIDGE_CM4_SCALAR_API 1
struct dvbridge_creative_coverage {
    uint32_t present, applied, preserved, edited, one_anchor;
};
#define DVBRIDGE_CM4_ALGORITHM "cb1-cm4-v1"
#define DVBRIDGE_DV_ENHANCED_ALGORITHM "cb1-dve-v3"
struct dvbridge_creative_edit_report {
    enum dvbridge_creative_status status;
    enum dvbridge_creative_reason reason;
    struct dvbridge_creative_coverage l2_coverage, l8_coverage;
    double maximum_pq_error, maximum_relative_chroma_error, maximum_hue_error;
    uint32_t candidate_evaluations;
    uint64_t fit_ns;
    bool cache_hit;
};
/* Decoded multipliers, absolute-linear basis and bounded signed adjustments. */
struct dvbridge_cm4_coefficients {
    double peak_nits, sop[3], chroma_base, saturation_gain, mid_exponent;
    double clip_strength, detail_mix, secondary_gain[6], secondary_rotation[6];
    double luma[3], hue_centres[6], rgb_to_lms[9], lms_to_rgb[9];
    uint32_t present, one_anchor;
};
struct dvbridge_creative_plan {
    enum dvbridge_creative_status status;
    enum dvbridge_creative_backend backend;
    enum dvbridge_creative_reason reason;
    struct dvbridge_policy policy;
    uint16_t analysis[3]; /* Effective L1 min,max,avg, with L3 applied once. */
    double target_pq, master_pq, codes[5]; /* SOP, chroma, saturation, 12-bit code domain. */
    struct pl_raw_primaries mastering_primaries;
    uint32_t applied_levels, preserved_levels;
    uint64_t source_hash;
    size_t source_bytes;
    bool cm4, l1_present, l3_present, anchor_present, mastering_primaries_present;
    struct dvbridge_cm4_anchor cm4_lower, cm4_upper;
    struct dvbridge_cm4_target cm4_output;
    enum dvbridge_cm4_target_status cm4_targets;
    double cm4_weight; /* Bounded PQ distance between matching target anchors. */
    struct dvbridge_creative_coverage l2_coverage, l8_coverage;
};
enum dvbridge_creative_status dvbridge_creative_resolve(struct dvbridge_creative_plan *out,
    const void *metadata, size_t bytes, const struct dvbridge_policy *policy);
/* Output is a new av_malloc buffer. Caller releases it with av_free. */
enum dvbridge_creative_status dvbridge_creative_edit(void **output, size_t *output_bytes,
    const void *metadata, size_t bytes, const struct dvbridge_creative_plan *plan,
    struct dvbridge_creative_edit_report *report);
/* Trim-only scalar reference, absolute linear nits before output gamut mapping. */
bool dvbridge_creative_trim_rgb(const struct dvbridge_creative_plan *plan,
    const double input[3], double output[3]);
bool dvbridge_creative_cm4_coefficients(struct dvbridge_cm4_coefficients *out,
    const struct dvbridge_creative_plan *plan);
bool dvbridge_creative_cm4_trim_rgb(const struct dvbridge_creative_plan *plan,
    const double input[3], double output[3]);
#ifdef __cplusplus
}
#endif
#endif
