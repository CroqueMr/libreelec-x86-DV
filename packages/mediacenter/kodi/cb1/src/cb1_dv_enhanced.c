/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_dv_enhanced.h"
#include <math.h>
#include <string.h>

static double limit(double x,double lo,double hi) {return fmax(lo,fmin(hi,x));}
static double smooth(double lo,double hi,double x)
{ x=limit((x-lo)/(hi-lo),0,1);return x*x*(3-2*x); }
static double pq(double nits)
{
    double v=pow(fmax(0,nits)/10000,2610.0/16384);
    return pow((3424.0/4096+2413.0/128*v)/(1+2392.0/128*v),2523.0/32);
}
static double nits(double q)
{
    double v=pow(q,32.0/2523);
    return 10000*pow(fmax(v-3424.0/4096,0)/(2413.0/128-2392.0/128*v),16384.0/2610);
}
static double lookup(const double *v,unsigned last,double x)
{
    x=limit(x,0,1)*last;unsigned i=(unsigned)x;
    return i==last?v[last]:v[i]+(v[i+1]-v[i])*(x-i);
}
static enum cb1_dv_enhanced_status build(struct cb1_dv_enhanced_plan *p,
    const struct cb1_dv_enhanced_source *s,const struct dvbridge_policy *policy,bool ai)
{
    if(!p)return CB1_DVE_INVALID;
    *p=(struct cb1_dv_enhanced_plan){0};
    if(!s || dvbridge_policy_validate(policy)!=DVBRIDGE_POLICY_VALID ||
       policy->mode!=DVBRIDGE_MODE_ENHANCED_DV || !isfinite(s->master) ||
       s->master<=10 || s->master>10000 || s->count>2 || (ai && (s->count || s->family)) ||
       policy->tv.peak_nits<=10)return p->status;
    p->policy=*policy;p->master=s->master;p->target=policy->tv.peak_nits;
    p->envelope=fmax(p->master,p->target);p->family=s->family;p->count=s->count;
    memcpy(p->analysis,s->analysis,sizeof(p->analysis));
    p->status=CB1_DVE_IDENTITY;
    bool guided=!ai && policy->adaptive!=DVBRIDGE_ADAPTIVE_A;
    if(!ai && !guided && !s->count){p->reason=CB1_DVE_NO_CREATIVE;return p->status;}
    if(!s->l1_present){p->reason=CB1_DVE_NO_ANALYSIS;return p->status;}
    if(s->analysis[0]>s->analysis[2] || s->analysis[2]>s->analysis[1] ||
       s->analysis[1]>4095)return p->status=CB1_DVE_INVALID;
    bool scene_expansion=!ai || policy->adaptive!=DVBRIDGE_ADAPTIVE_A;
    if(!scene_expansion && p->target<=p->master){p->reason=CB1_DVE_NO_HEADROOM;return p->status;}
    double high=nits(s->analysis[1]/4095.0),mid=nits(s->analysis[2]/4095.0);
    double amount=smooth(100,400,high)*(1-.5*smooth(.04,.30,mid/fmax(high,1e-9)));
    double retention[257]={0},total_weight=0;
    if(ai || (guided && !s->count))for(unsigned k=0;k<257;k++)retention[k]=1;
    for(unsigned a=0;a<s->count;a++){
        const struct dvbridge_cm4_anchor *anchor=&s->anchors[a];
        double peak=nits(anchor->target.max_pq/4095.0),weight=s->weights[a];
        if(!anchor->present || !isfinite(weight) || weight<0 || weight>1 || peak<=100 || peak>10000)
            return p->status=CB1_DVE_INVALID;
        struct dvbridge_creative_plan basis={.status=DVBRIDGE_CREATIVE_READY,.cm4=true,
            .policy=*policy,.cm4_targets=DVBRIDGE_CM4_TARGETS_RESOLVED,
            .cm4_lower=*anchor,.cm4_output=anchor->target};
        basis.policy.tv.peak_nits=peak;
        struct dvbridge_cm4_coefficients c;
        if(!dvbridge_creative_cm4_coefficients(&c,&basis))return p->status=CB1_DVE_INVALID;
        p->targets[a]=peak;p->weights[a]=weight;total_weight+=weight;
        p->color[0]+=weight*fabs(log2(c.chroma_base));
        p->color[1]+=weight*fabs(log2(c.saturation_gain));
        for(unsigned k=0;k<65;k++){
            double hue=-M_PI+2*M_PI*k/64,sum=0,v=0;
            for(unsigned j=0;j<6;j++){
                double w=exp(4*(cos(hue-c.hue_centres[j])-1));sum+=w;
                v+=w*(fabs(log2(c.secondary_gain[j]))+fabs(c.secondary_rotation[j])/(M_PI/12));
            }
            p->color[k+2]+=weight*v/sum;
        }
        c.chroma_base=c.saturation_gain=1;c.detail_mix=0;
        for(unsigned j=0;j<6;j++){c.secondary_gain[j]=1;c.secondary_rotation[j]=0;}
        for(unsigned j=0;j<5;j++)basis.codes[j]=j<3?anchor->controls.primary[j]:2048;
        for(unsigned k=0;k<257;k++){
            double x=(10+(p->master-10)*k/256)/p->master,out[3];
            bool ok=s->family==8?dvbridge_creative_cm4_apply(&c,(double[3]){x*peak,x*peak,x*peak},out):
                dvbridge_creative_trim_rgb(&basis,(double[3]){x*peak,x*peak,x*peak},out);
            if(!ok)return p->status=CB1_DVE_INVALID;
            retention[k]+=weight*limit(out[0]/peak/fmax(x,1e-6),.5,1.15);
        }
    }
    if(!ai && !(guided && !s->count) && fabs(total_weight-1)>1e-9)return p->status=CB1_DVE_INVALID;
    p->color[66]=p->color[2];
    double shape[257]={0},exponent=scene_expansion?2:3;
    if(scene_expansion)exponent+=2*smooth(.04,.30,mid/fmax(high,1e-9));
    for(unsigned k=1;k<257;k++)shape[k]=shape[k-1]+
        (pow(k/256.0,exponent)-pow((k-1)/256.0,exponent))*(retention[k-1]+retention[k])*.5;
    bool active=false;
    double reference=fmin(p->master,fmax(100,high));
    double normalization=scene_expansion?fmax(1e-9,lookup(shape,256,(reference-10)/(p->master-10))):fmax(1,shape[256]);
    for(unsigned k=0;k<257;k++){
        double u=k/256.0;
        /* Expand scene highlights, not the entire mastering envelope. */
        if(scene_expansion && p->target>reference)
            p->extra[k]=smooth(100,400,high)*(p->target-reference)*fmin(1,shape[k]/normalization);
        else if(p->target>p->master)p->extra[k]=amount*(p->target-p->master)*shape[k]/normalization;
        if(scene_expansion)p->extra[k]+=(1-smooth(p->master,1.5*p->master,p->target))*amount*.12*
            (p->master-10)*16*u*u*(1-u)*(1-u)*retention[k];
        active|=p->extra[k]>0;
    }
    p->reason=active?CB1_DVE_ACTIVE:CB1_DVE_DARK_SCENE;
    return p->status=active?CB1_DVE_READY:CB1_DVE_IDENTITY;
}

enum cb1_dv_enhanced_status cb1_dv_enhanced_build(struct cb1_dv_enhanced_plan *p,
    const struct cb1_dv_enhanced_source *s,const struct dvbridge_policy *policy)
{return build(p,s,policy,false);}

enum cb1_dv_enhanced_status cb1_dv_enhanced_build_ai(struct cb1_dv_enhanced_plan *p,
    const struct cb1_dv_enhanced_source *s,const struct dvbridge_policy *policy)
{return build(p,s,policy,true);}

bool cb1_dv_enhanced_pixel(const struct cb1_dv_enhanced_plan *p,const double rgb[3],double out[3])
{
    if(!p || !rgb || !out || p->status==CB1_DVE_INVALID)return false;
    double y=0,peak=0;
    const double luma[3]={.262700212011267,.677998071518871,.059301716469862};
    for(unsigned j=0;j<3;j++){
        if(!isfinite(rgb[j]) || rgb[j]<0 || rgb[j]>10000)return false;
        y+=luma[j]*rgb[j];peak=fmax(peak,rgb[j]);
    }
    if(y>p->master+1e-7 || peak>p->envelope+1e-7)return false;
    memcpy(out,rgb,3*sizeof(double));
    if(p->status==CB1_DVE_IDENTITY || y<=10)return true;
    double extra=lookup(p->extra,256,(y-10)/(p->master-10));
    bool color=false;for(unsigned j=0;j<67;j++)color|=p->color[j]!=0;
    if(color && !(rgb[0]==rgb[1] && rgb[1]==rgb[2])){
        pl_matrix3x3 lms=pl_ipt_rgb2lms(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
        double v[3];for(unsigned j=0;j<3;j++)v[j]=pq(lms.m[j][0]*rgb[0]+lms.m[j][1]*rgb[1]+lms.m[j][2]*rgb[2]);
        double i=.4*v[0]+.4*v[1]+.2*v[2],ct=4.455*v[0]-4.851*v[1]+.396*v[2],
            cp=.8056*v[0]+.3572*v[1]-1.1628*v[2];
        double gate=smooth(0,.15,i>0?hypot(ct,cp)/i:0),z=limit(i/pq(p->master),0,1);
        double severity=p->color[0]*fabs(2*z-1)+p->color[1]+lookup(p->color+2,64,(atan2(cp,ct)+M_PI)/(2*M_PI));
        extra*=fmax(.65,1/(1+.5*gate*severity));
    }
    double ceiling=p->count || p->policy.adaptive!=DVBRIDGE_ADAPTIVE_A?p->target:p->envelope;
    double delta=extra/y,headroom=fmax(0,ceiling/peak-1),knee=.9*headroom,width=.1*headroom;
    if(delta>knee){double tail=delta-knee;delta=knee+(width+tail>0?width*tail/(width+tail):0);}
    for(unsigned j=0;j<3;j++)out[j]=rgb[j]*(1+delta);
    return true;
}

bool cb1_dv_enhanced_analysis(const struct cb1_dv_enhanced_plan *p,uint16_t out[3])
{
    if(!p || !out || p->status==CB1_DVE_INVALID)return false;
    for(unsigned i=0;i<3;i++){
        double q=p->analysis[i]/4095.0,y=nits(q),expanded[3];out[i]=p->analysis[i];
        if(y<=10 || y>p->master+1e-7)continue;
        y=fmin(y,p->master);
        if(!cb1_dv_enhanced_pixel(p,(double[3]){y,y,y},expanded))return false;
        out[i]=(uint16_t)fmin(4095,out[i]+fmax(0,lround(4096*(pq(expanded[0])-q))));
    }
    out[2]=fmax(out[0],fmin(out[1],out[2]));
    return out[0]<=out[1];
}

void cb1_dv_enhanced_transition(struct cb1_dv_enhanced_plan *p,
    const struct cb1_dv_enhanced_plan *old,double dt,bool reset)
{
    if(!p || !old || reset || !isfinite(dt) || dt<0 || dt>1 ||
       (p->policy.adaptive==DVBRIDGE_ADAPTIVE_A)!=(old->policy.adaptive==DVBRIDGE_ADAPTIVE_A) ||
       p->status==CB1_DVE_INVALID || old->status==CB1_DVE_INVALID ||
       (!p->count && p->policy.revision!=old->policy.revision) ||
       p->policy.tv.gamut!=old->policy.tv.gamut || p->master!=old->master || p->target!=old->target ||
       (p->reason!=CB1_DVE_ACTIVE && p->reason!=CB1_DVE_DARK_SCENE))return;
    double change=0,maximum=0,sector=0;
    for(unsigned k=0;k<257;k++){
        change=fmax(change,fabs(p->extra[k]-old->extra[k]));maximum=fmax(maximum,fmax(p->extra[k],old->extra[k]));
    }
    for(unsigned k=2;k<67;k++)sector=fmax(sector,fabs(p->color[k]-old->color[k]));
    change+=.5*(fabs(p->color[0]-old->color[0])+fabs(p->color[1]-old->color[1])+sector)*maximum;
    double budget=.5*dt*fmax(fabs(p->target-p->master),.12*(p->master-10));
    double alpha=fmin(1,budget/fmax(change,1e-12));bool active=false;
    for(unsigned k=0;k<257;k++){p->extra[k]=old->extra[k]*(1-alpha)+p->extra[k]*alpha;active|=p->extra[k]>0;}
    for(unsigned k=0;k<67;k++)p->color[k]=old->color[k]*(1-alpha)+p->color[k]*alpha;
    p->status=active?CB1_DVE_READY:CB1_DVE_IDENTITY;
}
