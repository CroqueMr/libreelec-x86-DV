/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_FEATURES_H
#define CB1_HDR10_FEATURES_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Compact GPU results only. No decoded image is accepted by this interface. */
struct cb1_hdr10_descriptor {
    double pts;
    float global[35], spatial[38];
};
/* Image-derived CM2.9 construction baseline, min/avg/max order.
 * A finite boundary supplies the last duration; NaN denotes an unobserved end.
 * Failure preserves both outputs. Input is a prefix of at most one second. */
bool cb1_hdr10_baseline(const struct cb1_hdr10_descriptor *samples, size_t count,
                       double boundary_pts, uint16_t out[3], double *measured_peak);
/* Aggregate one already observed prefix, bounded to one second.
 * Base fields use min/avg/max. Failure preserves out. */
bool cb1_hdr10_prefix(const struct cb1_hdr10_descriptor *samples, size_t count,
                     const uint16_t base[3], bool left_censored, bool right_censored,
                     float out[222]);
#ifdef __cplusplus
}
#endif
#endif
