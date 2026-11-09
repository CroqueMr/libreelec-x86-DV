/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "dvbridge_policy.h"
#include <math.h>

bool dvbridge_sdr_target(const struct dvbridge_sdr_profile *p,double *peak,double *gamma,double *black)
{
    if(!p || !peak || !gamma || !black || p->preset<DVBRIDGE_SDR_REFERENCE ||
       p->preset>DVBRIDGE_SDR_CUSTOM)return false;
    double n=p->preset==DVBRIDGE_SDR_REFERENCE?100:p->preset==DVBRIDGE_SDR_BRIGHT?200:p->peak_nits;
    double g=p->preset==DVBRIDGE_SDR_REFERENCE?2.4:p->preset==DVBRIDGE_SDR_BRIGHT?2.2:p->gamma;
    double b=p->preset==DVBRIDGE_SDR_CUSTOM?p->black_nits:0;
    if(!isfinite(n) || n<20 || n>500 || !isfinite(g) || g<1.8 || g>2.8 ||
       !isfinite(b) || b<0 || b>5 || b>=n)return false;
    *peak=n;*gamma=g;*black=b;return true;
}

enum dvbridge_policy_status dvbridge_policy_validate(const struct dvbridge_policy *policy)
{
    if (!policy || policy->mode < DVBRIDGE_MODE_DISABLED ||
        policy->mode >= DVBRIDGE_MODE_COUNT)
        return DVBRIDGE_POLICY_INVALID_VALUE;
    if(policy->mode==DVBRIDGE_MODE_SDR){
        double peak,gamma,black;
        return policy->adaptive==DVBRIDGE_ADAPTIVE_A &&
            dvbridge_sdr_target(&policy->sdr,&peak,&gamma,&black)?
            DVBRIDGE_POLICY_VALID:DVBRIDGE_POLICY_INVALID_VALUE;
    }
    if(policy->adaptive<DVBRIDGE_ADAPTIVE_A || policy->adaptive>DVBRIDGE_ADAPTIVE_B_FP16 ||
       (policy->adaptive!=DVBRIDGE_ADAPTIVE_A && policy->mode!=DVBRIDGE_MODE_ENHANCED_DV))
        return DVBRIDGE_POLICY_INVALID_VALUE;
    const struct dvbridge_tv_profile *tv = &policy->tv;
    if (tv->panel < DVBRIDGE_PANEL_UNSET || tv->panel > DVBRIDGE_PANEL_LCD ||
        tv->gamut < DVBRIDGE_GAMUT_UNSET || tv->gamut > DVBRIDGE_GAMUT_BT2020 ||
        !isfinite(tv->peak_nits) || tv->peak_nits < 0 || tv->peak_nits > 10000)
        return DVBRIDGE_POLICY_INVALID_VALUE;
    if (tv->peak_nits == 0 && tv->panel == DVBRIDGE_PANEL_UNSET &&
        tv->gamut == DVBRIDGE_GAMUT_UNSET)
        return (policy->mode == DVBRIDGE_MODE_HDR10_EXPERT || policy->mode == DVBRIDGE_MODE_ENHANCED_DV) ?
            DVBRIDGE_POLICY_TV_PROFILE_REQUIRED : DVBRIDGE_POLICY_VALID;
    if (tv->gamut == DVBRIDGE_GAMUT_UNSET)
        return DVBRIDGE_POLICY_TV_PROFILE_REQUIRED;
    if(policy->mode==DVBRIDGE_MODE_HDR10_EXPERT &&
       (tv->peak_nits<50 || !isfinite(policy->expert_black_nits) ||
        policy->expert_black_nits<0 || policy->expert_black_nits>.5 ||
        policy->expert_black_nits>=tv->peak_nits ||
        (policy->expert_output_bits && (policy->expert_output_bits<10 || policy->expert_output_bits>16))))
        return DVBRIDGE_POLICY_INVALID_VALUE;
    return tv->peak_nits > 0 ? DVBRIDGE_POLICY_VALID : DVBRIDGE_POLICY_INVALID_VALUE;
}

bool dvbridge_identity_equal(const struct dvbridge_identity *a, const struct dvbridge_identity *b)
{
    return a && b && a->stream == b->stream && a->picture == b->picture &&
           a->revision == b->revision;
}
