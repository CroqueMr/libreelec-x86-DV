/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_HDR10PLUS_CURVE_H
#define CB1_HDR10PLUS_CURVE_H
#include "cb1_hdr10plus.h"
#ifdef __cplusplus
extern "C" {
#endif

#define CB1_HDR10PLUS_CURVE_SAMPLES 1025
struct cb1_hdr10plus_curve {
    uint16_t knee_x,knee_y; /* HDMI 10-bit codes. */
    uint8_t count,anchors[9]; /* HDMI 8-bit codes. */
    double maximum_pq_error;
};
/* Samples are normalized linear output at evenly spaced normalized linear
 * input values. Error is measured after HDMI quantization, in absolute PQ. */
bool cb1_hdr10plus_curve_fit(struct cb1_hdr10plus_curve *out,
    const double values[CB1_HDR10PLUS_CURVE_SAMPLES], unsigned target_nits);
double cb1_hdr10plus_curve_sample(const struct cb1_hdr10plus_curve *curve,double x);
bool cb1_hdr10plus_curve_apply(AVDynamicHDRPlus *metadata,const struct cb1_hdr10plus_curve *curve);

#ifdef __cplusplus
}
#endif
#endif
