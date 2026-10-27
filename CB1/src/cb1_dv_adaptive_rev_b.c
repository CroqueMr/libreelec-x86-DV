/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_dv_adaptive_rev_b.h"
#include <math.h>

static double smooth(double lo,double hi,double x)
{x=fmax(0,fmin(1,(x-lo)/(hi-lo)));return x*x*(3-2*x);}

static double bounded(double x)
{return fmax(-1,fmin(1,x));}

/* Compare authored and neutral responses in the same target domain. */
static bool signed_guide(double guide[257],double *color,
    const struct cb1_dv_enhanced_source *s,struct cb1_dv_enhanced_plan *p)
{
    double total=0;
    for(unsigned a=0;a<s->count;a++){
        const struct dvbridge_cm4_anchor *anchor=&s->anchors[a];
        double peak=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,anchor->target.max_pq/4095.0),w=s->weights[a];
        if(!anchor->present || anchor->target.max_pq>4095 || !isfinite(w) || w<0 || w>1 ||
           peak<=100 || peak>10000)return false;
        struct dvbridge_creative_plan basis={.status=DVBRIDGE_CREATIVE_READY,.cm4=true,
            .policy=p->policy,.cm4_targets=DVBRIDGE_CM4_TARGETS_RESOLVED,
            .cm4_lower=*anchor,.cm4_output=anchor->target};
        basis.policy.tv.peak_nits=peak;
        struct dvbridge_cm4_coefficients c;
        if(!dvbridge_creative_cm4_coefficients(&c,&basis))return false;
        p->targets[a]=peak;p->weights[a]=w;total+=w;
        /* An authored downmap is not an instruction for an arbitrary brighter TV. */
        double authority=w*fmin(peak/p->target,p->target/peak);
        *color+=authority*bounded(log2(c.chroma_base)+log2(c.saturation_gain));
        c.chroma_base=c.saturation_gain=1;c.detail_mix=0;
        for(unsigned j=0;j<6;j++){c.secondary_gain[j]=1;c.secondary_rotation[j]=0;}
        struct dvbridge_cm4_coefficients neutral=c;
        neutral.sop[0]=neutral.sop[2]=neutral.mid_exponent=1;
        neutral.sop[1]=neutral.clip_strength=0;
        for(unsigned j=0;j<5;j++)basis.codes[j]=
            j<3 && (anchor->controls.present_fields&DVBRIDGE_CM4_PRIMARY)?anchor->controls.primary[j]:2048;
        struct dvbridge_creative_plan neutral_l2=basis;
        for(unsigned j=0;j<5;j++)neutral_l2.codes[j]=2048;
        for(unsigned k=0;k<257;k++){
            double x=(10+(p->master-10)*k/256)/p->master;
            double rgb[3]={x*peak,x*peak,x*peak},out[3],reference[3];
            bool ok=s->family==8?dvbridge_creative_cm4_apply(&c,rgb,out) &&
                    dvbridge_creative_cm4_apply(&neutral,rgb,reference):
                dvbridge_creative_trim_rgb(&basis,rgb,out) &&
                    dvbridge_creative_trim_rgb(&neutral_l2,rgb,reference);
            if(!ok)return false;
            guide[k]+=authority*bounded(log2(fmax(out[0],1e-9)/fmax(reference[0],1e-9)));
        }
    }
    return !s->count || fabs(total-1)<1e-9;
}

enum cb1_dv_enhanced_status cb1_dv_enhanced_build_rev_b(struct cb1_dv_enhanced_plan *p,
    const struct cb1_dv_enhanced_source *s,const struct dvbridge_policy *policy)
{
    if(!p)return CB1_DVE_INVALID;
    *p=(struct cb1_dv_enhanced_plan){0};
    if(!s || s->count>2 || (s->count && s->family!=2 && s->family!=8) ||
       !policy || policy->adaptive==DVBRIDGE_ADAPTIVE_A ||
       dvbridge_policy_validate(policy)!=DVBRIDGE_POLICY_VALID)return p->status;
    struct cb1_dv_enhanced_source base=*s;base.count=base.family=0;
    struct dvbridge_policy base_policy=*policy;base_policy.adaptive_rev_b=false;
    if(cb1_dv_enhanced_build(p,&base,&base_policy)==CB1_DVE_INVALID)return p->status;
    p->policy=*policy;
    p->count=s->count;p->family=s->family;
    double guide[257]={0},color=0;
    if(!signed_guide(guide,&color,s,p))return p->status=CB1_DVE_INVALID;
    if(p->status!=CB1_DVE_READY)return p->status;
    double high=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,p->analysis[1]/4095.0),
           mid=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,p->analysis[2]/4095.0);
    /* Tonal balance is authored guidance, not a pixel-occupancy estimate. */
    double key=smooth(.04,.30,mid/fmax(high,1e-9));
    double lo=fmax(10,high*(.12+.08*key)),hi=fmax(lo+1,high*(.65+.10*key));
    double shape[257]={0},mean=0,exponent=2+2*key;
    for(unsigned k=1;k<257;k++){
        shape[k]=shape[k-1]+(pow(k/256.0,exponent)-pow((k-1)/256.0,exponent))*
            exp2(.375*(guide[k-1]+guide[k]));
        if(k<=192)mean+=guide[k]/192;
    }
    /* Separate amplitude from shape normalization; retain the sign of constant trims. */
    double amplitude=fmax(.55,fmin(1,.85+.30*bounded(mean-.25*color)));
    double reference=fmin(p->master,fmax(100,high)),pos=(reference-10)/(p->master-10)*256;
    unsigned i=(unsigned)pos;
    double norm=fmax(1e-9,i==256?shape[256]:shape[i]+(shape[i+1]-shape[i])*(pos-i));
    double neutral_norm=pow(i/256.0,exponent);
    if(i<256)neutral_norm+=(pow((i+1)/256.0,exponent)-neutral_norm)*(pos-i);
    for(unsigned k=0;k<257;k++){
        double x=10+(p->master-10)*k/256;
        double neutral_shape=fmin(1,pow(k/256.0,exponent)/fmax(1e-9,neutral_norm));
        if(neutral_shape>0)p->extra[k]*=fmin(1,shape[k]/norm)/neutral_shape;
        p->extra[k]*=amplitude*smooth(lo,hi,x);
    }
    return p->status;
}
