/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_DV_ENHANCED_H
#define CB1_DV_ENHANCED_H
#include "dvbridge_creative.h"
#ifdef __cplusplus
extern "C" {
#endif

#define CB1_DVE_ALGORITHM "cb1-dve-pixel-v1"
#define CB1_DVE_ANALYSIS "cb1-probe-lms-maxpq-v1"
enum cb1_dv_enhanced_status { CB1_DVE_INVALID, CB1_DVE_IDENTITY, CB1_DVE_READY };
enum cb1_dv_enhanced_reason {
    CB1_DVE_ACTIVE, CB1_DVE_NO_CREATIVE, CB1_DVE_NO_ANALYSIS,
    CB1_DVE_NO_HEADROOM, CB1_DVE_DARK_SCENE, CB1_DVE_SOURCE_BOUND
};
struct cb1_dv_enhanced_source {
    double master;
    uint16_t analysis[3]; /* Effective L1, after L3. */
    bool l1_present;
    unsigned family, count;
    struct dvbridge_cm4_anchor anchors[2];
    double weights[2];
};
struct cb1_dv_enhanced_plan {
    enum cb1_dv_enhanced_status status;
    enum cb1_dv_enhanced_reason reason;
    struct dvbridge_policy policy;
    double master, target, envelope, extra[257], color[67];
    uint16_t analysis[3];
    unsigned family, count;
    double targets[2], weights[2];
};
bool dvbridge_creative_enhanced_source(struct cb1_dv_enhanced_source *,
    const void *, size_t, const struct dvbridge_policy *);
bool dvbridge_creative_enhanced_source_b(struct cb1_dv_enhanced_source *,
    const void *, size_t, const struct dvbridge_policy *);
enum cb1_dv_enhanced_status cb1_dv_enhanced_build(struct cb1_dv_enhanced_plan *,
    const struct cb1_dv_enhanced_source *, const struct dvbridge_policy *);
/* AI guidance has effective L1 but no authored creative anchors. */
enum cb1_dv_enhanced_status cb1_dv_enhanced_build_ai(struct cb1_dv_enhanced_plan *,
    const struct cb1_dv_enhanced_source *, const struct dvbridge_policy *);
bool cb1_dv_enhanced_pixel(const struct cb1_dv_enhanced_plan *, const double[3], double[3]);
/* Transform scene L1 through the same neutral-axis curve; preserve protected blacks. */
bool cb1_dv_enhanced_analysis(const struct cb1_dv_enhanced_plan *, uint16_t[3]);
void cb1_dv_enhanced_transition(struct cb1_dv_enhanced_plan *,
    const struct cb1_dv_enhanced_plan *, double dt, bool reset);
#ifdef __cplusplus
}
#endif
#endif
