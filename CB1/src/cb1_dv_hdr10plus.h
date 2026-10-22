/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_DV_HDR10PLUS_H
#define CB1_DV_HDR10PLUS_H
#include "cb1_hdr10plus_analysis.h"
#include "cb1_hdr10plus_curve.h"
#ifdef __cplusplus
extern "C" {
#endif

enum cb1_dv_hdr10plus_coverage {
    CB1_DV_HDR10PLUS_STATISTICS,
    CB1_DV_HDR10PLUS_L1,
    CB1_DV_HDR10PLUS_L2,
    CB1_DV_HDR10PLUS_L8
};
enum cb1_dv_hdr10plus_reason {
    CB1_DV_HDR10PLUS_OK,
    CB1_DV_HDR10PLUS_NO_ANALYSIS,
    CB1_DV_HDR10PLUS_UNRESOLVED_TRIMS,
    CB1_DV_HDR10PLUS_UNREPRESENTABLE_TRIMS,
    CB1_DV_HDR10PLUS_UNREPRESENTABLE_CURVE
};
struct cb1_dv_hdr10plus_report {
    enum cb1_dv_hdr10plus_coverage coverage;
    enum cb1_dv_hdr10plus_reason reason;
    bool l3_used;
    uint16_t effective_l1[3];
    double maximum_curve_pq_error,maximum_color_pq_error;
};
/* Input statistics describe the reconstructed DV image, before any mapping.
 * This function only builds output metadata; it never applies trims to pixels. */
bool cb1_dv_hdr10plus_metadata(AVDynamicHDRPlus *out,struct cb1_dv_hdr10plus_report *report,
    const void *metadata,size_t bytes,const struct cb1_hdr10plus_statistics *statistics);

#ifdef __cplusplus
}
#endif
#endif
