/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_DV_ADAPTIVE_REV_B_H
#define CB1_DV_ADAPTIVE_REV_B_H
#include "cb1_dv_enhanced.h"
#define CB1_DVE_REV_B_TITLE "Dolby Vision Adaptive HDR Mapping rev B"
#define CB1_DVE_REV_B_ALGORITHM "cb1-dve-signed-revb-v2"
#define CB1_DVE_REV_B_RUNTIME_API 1
/* Authored-DV alternative; AI policy must not select this builder. */
#ifdef __cplusplus
extern "C" {
#endif
enum cb1_dv_enhanced_status cb1_dv_enhanced_build_rev_b(struct cb1_dv_enhanced_plan *,
    const struct cb1_dv_enhanced_source *, const struct dvbridge_policy *);
#ifdef __cplusplus
}
#endif
#endif
