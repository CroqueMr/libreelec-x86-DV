/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_dv_adaptive_rev_b.h"
#include <math.h>
#include <string.h>

static double smooth(double lo,double hi,double x)
{x=fmax(0,fmin(1,(x-lo)/(hi-lo)));return x*x*(3-2*x);}

enum cb1_dv_enhanced_status cb1_dv_enhanced_build_rev_b(struct cb1_dv_enhanced_plan *p,
    const struct cb1_dv_enhanced_source *s,const struct dvbridge_policy *policy)
{
    if(!p)return CB1_DVE_INVALID;
    *p=(struct cb1_dv_enhanced_plan){0};
    if(!policy || policy->adaptive==DVBRIDGE_ADAPTIVE_A)return p->status;
    if(cb1_dv_enhanced_build(p,s,policy)==CB1_DVE_INVALID)return p->status;
    /* Six-vector secondary trims describe SDR, not HDR expansion. */
    memset(p->color+2,0,65*sizeof(double));
    if(p->status!=CB1_DVE_READY)return p->status;
    double high=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,p->analysis[1]/4095.0),
           mid=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,p->analysis[2]/4095.0);
    /* Tonal balance is authored guidance, not a pixel-occupancy estimate. */
    double key=smooth(.04,.30,mid/fmax(high,1e-9));
    double lo=fmax(10,high*(.12+.08*key)),hi=fmax(lo+1,high*(.65+.10*key));
    for(unsigned k=0;k<257;k++)
        p->extra[k]*=smooth(lo,hi,10+(p->master-10)*k/256);
    return p->status;
}
