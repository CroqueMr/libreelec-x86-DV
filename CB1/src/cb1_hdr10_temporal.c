/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_hdr10_temporal.h"
#include <fenv.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

enum { MAX_SAMPLES=256, MOTION_VALUES=1728 };
struct sample { struct cb1_hdr10_descriptor d;struct cb1_ai_identity id;float motion[MOTION_VALUES],difference,shape;bool exposure,candidate,settled,gap; };
struct cb1_hdr10_temporal {
    struct sample samples[MAX_SAMPLES];size_t count;
    uint64_t stream,revision;bool active,ended,calibrated;
    float calibration[222];double calibration_start,frontier,active_cut,history_low,history_high,history_energy,history_mass;
};

/* NumPy-compatible binary32 pairwise sum, BSD-3-Clause.
 * Copyright (c) 2005-2025, NumPy Developers. See LICENSES/BSD-NumPy.txt. */
static float sum32(const float *v,size_t n)
{
    if(n<8){float sum=-0.f;for(size_t i=0;i<n;++i)sum+=v[i];return sum;}
    if(n>128){size_t half=n/2;half-=half%8;return sum32(v,half)+sum32(v+half,n-half);}
    float lanes[8];memcpy(lanes,v,sizeof(lanes));size_t i=8;
    for(;i<n-n%8;i+=8)for(unsigned j=0;j<8;++j)lanes[j]+=v[i+j];
    float sum=((lanes[0]+lanes[1])+(lanes[2]+lanes[3]))+((lanes[4]+lanes[5])+(lanes[6]+lanes[7]));
    for(;i<n;++i)sum+=v[i];
    return sum;
}

static void motion_edge(const float *before,const float *after,struct sample *out)
{
    float delta[MOTION_VALUES],absolute[MOTION_VALUES],residual[MOTION_VALUES];
    for(unsigned i=0;i<MOTION_VALUES;++i){delta[i]=after[i]-before[i];absolute[i]=fabsf(delta[i]);}
    out->difference=sum32(absolute,MOTION_VALUES)/MOTION_VALUES;
    bool gain_valid=true;
    for(unsigned c=0;c<3;++c){
        const unsigned first=c*576;float mean=sum32(delta+first,576)/576;
        float a_mean=sum32(before+first,576)/576,b_mean=sum32(after+first,576)/576;
        float a[576],b[576],energy[576],cross[576];
        for(unsigned i=0;i<576;++i){
            absolute[first+i]=fabsf(delta[first+i]-mean);
            a[i]=before[first+i]-a_mean;b[i]=after[first+i]-b_mean;
            energy[i]=a[i]*a[i];cross[i]=a[i]*b[i];
        }
        float total=sum32(energy,576),gain=total>1e-8f?sum32(cross,576)/total:1.f;
        gain_valid&=gain>.25f && gain<4.f;
        for(unsigned i=0;i<576;++i)residual[first+i]=fabsf(b[i]-gain*a[i]);
    }
    out->shape=sum32(absolute,MOTION_VALUES)/MOTION_VALUES;
    out->exposure=gain_valid && sum32(residual,MOTION_VALUES)/MOTION_VALUES<.008f;
}

struct cb1_hdr10_temporal *cb1_hdr10_temporal_create(void){return calloc(1,sizeof(struct cb1_hdr10_temporal));}
void cb1_hdr10_temporal_destroy(struct cb1_hdr10_temporal **ctx){if(ctx && *ctx){free(*ctx);*ctx=NULL;}}
void cb1_hdr10_temporal_reset(struct cb1_hdr10_temporal *ctx,uint64_t stream,uint64_t revision)
{
    if(!ctx)return;
    ctx->count=0;ctx->stream=stream;ctx->revision=revision;ctx->active=true;ctx->ended=false;ctx->calibrated=false;
    ctx->calibration_start=-1;ctx->frontier=-1;ctx->active_cut=0;ctx->history_low=1;ctx->history_high=0;ctx->history_energy=ctx->history_mass=0;
}
void cb1_hdr10_temporal_end(struct cb1_hdr10_temporal *ctx){if(ctx)ctx->ended=true;}
enum cb1_ai_status cb1_hdr10_temporal_advance(struct cb1_hdr10_temporal *ctx,double pts)
{
    if(!ctx || !ctx->active || !ctx->count || ctx->ended || !isfinite(pts) || pts<ctx->frontier-1e-9)
        return CB1_AI_INVALID;
    ctx->frontier=fmax(pts,ctx->frontier);return CB1_AI_READY;
}
size_t cb1_hdr10_temporal_size(const struct cb1_hdr10_temporal *ctx){return ctx?ctx->count:0;}

static bool cut_candidate(const struct cb1_hdr10_temporal *ctx,size_t i,size_t observed)
{
    size_t first=1,last=observed;
    for(size_t j=i;j>0;--j)if(ctx->samples[j].gap){first=j+1;break;}
    for(size_t j=i+1;j<observed;++j)if(ctx->samples[j].gap){last=j;break;}
    double neighbourhood=0;unsigned count=0;
    for(int offset=-2;offset<=2;++offset){
        ptrdiff_t next=(ptrdiff_t)i+offset;
        if(offset && next>=(ptrdiff_t)first && (size_t)next<last){neighbourhood+=ctx->samples[next].difference;++count;}
    }
    double threshold=fmax(.03,2*fmax(.003,count?neighbourhood/count:0));
    const struct sample *s=&ctx->samples[i];
    return s->difference>threshold && s->shape>.012f && !s->exposure;
}

enum cb1_ai_status cb1_hdr10_temporal_push(struct cb1_hdr10_temporal *ctx,
    const struct cb1_hdr10_descriptor *d,const float motion[MOTION_VALUES],struct cb1_ai_identity id)
{
    if(!ctx || !ctx->active || !d || !motion || id.stream!=ctx->stream || id.revision!=ctx->revision ||
        !isfinite(d->pts) || d->pts<0)return CB1_AI_INVALID;
    for(unsigned i=0;i<35;++i)if(!isfinite(d->global[i]))return CB1_AI_INVALID;
    for(unsigned i=0;i<38;++i)if(!isfinite(d->spatial[i]))return CB1_AI_INVALID;
    for(unsigned i=0;i<MOTION_VALUES;++i)if(!isfinite(motion[i]) || motion[i]<0 || motion[i]>1)return CB1_AI_INVALID;
    if(d->global[0]<0 || d->global[1]>1 || d->global[0]>d->global[2] || d->global[2]>d->global[1])return CB1_AI_INVALID;
    if(ctx->count){
        struct sample *last=&ctx->samples[ctx->count-1];
        if(last->id.picture==id.picture)return d->pts==last->d.pts?CB1_AI_READY:CB1_AI_INVALID;
        if(d->pts<=last->d.pts || d->pts<ctx->frontier || id.picture<=last->id.picture)return CB1_AI_INVALID;
    }
    if(ctx->ended)return CB1_AI_INVALID;
    if(ctx->count==MAX_SAMPLES)return CB1_AI_PENDING;
    struct sample *s=&ctx->samples[ctx->count];s->d=*d;s->id=id;memcpy(s->motion,motion,sizeof(s->motion));
    s->difference=s->shape=0;s->exposure=s->candidate=s->settled=false;
    s->gap=ctx->count && d->pts-ctx->samples[ctx->count-1].d.pts>1.;
    if(ctx->count && !s->gap)motion_edge(ctx->samples[ctx->count-1].motion,motion,s);
    else if(!ctx->count)ctx->active_cut=d->pts;
    ctx->frontier=d->pts;++ctx->count;
    if(ctx->count>3){
        size_t i=ctx->count-3;
        ctx->samples[i].candidate=cut_candidate(ctx,i,ctx->count);
        ctx->samples[i].settled=true;
    }
    return CB1_AI_READY;
}

static bool confirmed_cut(const struct cb1_hdr10_temporal *ctx,size_t i,size_t observed,double available)
{
    if(!i || i>=observed)return false;
    const struct sample *s=&ctx->samples[i];
    if(s->gap)return s->d.pts<=available+1e-9;
    size_t consumed=i+2<observed?i+2:observed-1;
    double confirmation=fmax(s->d.pts+.2,ctx->samples[consumed].d.pts);
    bool candidate=s->settled && i+2<observed?s->candidate:cut_candidate(ctx,i,observed);
    return candidate &&
        confirmation<=available+1e-9;
}

static bool baseline(const struct cb1_hdr10_temporal *ctx,size_t start,size_t end,bool cut,
    uint16_t base[3],double *peak)
{
    double low=ctx->history_mass>0 && start==0?ctx->history_low:1;
    double high=ctx->history_mass>0 && start==0?ctx->history_high:0;
    double energy=start==0?ctx->history_energy:0,mass=start==0?ctx->history_mass:0;
    for(size_t i=start;i<end;++i){
        const struct cb1_hdr10_descriptor *d=&ctx->samples[i].d;
        low=fmin(low,d->global[0]);high=fmax(high,d->global[1]);
        double dt=i+1<end || (cut && ctx->samples[i+1].d.pts-d->pts<=1.)?ctx->samples[i+1].d.pts-d->pts:
            i>start?d->pts-ctx->samples[i-1].d.pts:1./24.;
        energy+=dt*d->global[2];mass+=dt;
    }
    if(mass<=0 || !isfinite(energy))return false;
    double average=fmin(high,fmax(low,energy/mass));
    base[0]=(uint16_t)fmin(12,nearbyint(low*4095));
    base[2]=(uint16_t)fmax(2081,nearbyint(high*4095));
    base[1]=(uint16_t)fmin(base[2]-1,fmax(819,nearbyint(average*4095)));*peak=high;return true;
}

enum cb1_ai_status cb1_hdr10_temporal_poll(struct cb1_hdr10_temporal *ctx,
    struct cb1_ai_identity id,struct cb1_hdr10_temporal_result *out)
{
    if(!ctx || !ctx->active || !out || id.stream!=ctx->stream || id.revision!=ctx->revision)return CB1_AI_INVALID;
    size_t requested=0;while(requested<ctx->count && ctx->samples[requested].id.picture!=id.picture)++requested;
    if(requested==ctx->count)return CB1_AI_INVALID;
    double pts=ctx->samples[requested].d.pts;
    if(!ctx->ended && ctx->frontier<pts+1.-1e-9)return CB1_AI_PENDING;
    double available=fmin(pts+1.,ctx->ended?ctx->samples[ctx->count-1].d.pts:ctx->frontier);
    size_t observed=requested+1;
    while(observed<ctx->count && ctx->samples[observed].d.pts<=pts+1.+1e-9)++observed;
    const int rounding=fegetround();if(rounding<0 || fesetround(FE_TONEAREST))return CB1_AI_INVALID;
    size_t span=0;
    for(size_t i=1;i<=requested;++i)if(ctx->samples[i].gap)span=i;
    if(span && ctx->samples[span].d.pts!=ctx->calibration_start){
        ctx->calibrated=false;
        ctx->active_cut=ctx->samples[span].d.pts;ctx->history_low=1;ctx->history_high=0;
        ctx->history_energy=ctx->history_mass=0;
    }
    if(!ctx->calibrated){
        double calibration_until=fmin(ctx->samples[span].d.pts+1.,available);
        size_t seen=span+1;
        while(seen<observed && ctx->samples[seen].d.pts<=calibration_until+1e-9)++seen;
        size_t end=seen;
        for(size_t i=span+1;i<seen;++i)if(confirmed_cut(ctx,i,seen,calibration_until)){end=i;break;}
        struct cb1_hdr10_descriptor prefix[MAX_SAMPLES];for(size_t i=span;i<end;++i)prefix[i-span]=ctx->samples[i].d;
        uint16_t base[3];double peak;
        bool ok=baseline(ctx,span,end,end<seen,base,&peak) &&
            cb1_hdr10_prefix(prefix,end-span,base,true,end==seen,ctx->calibration);
        if(!ok){fesetround(rounding);return CB1_AI_INVALID;}ctx->calibrated=true;
        ctx->calibration_start=ctx->samples[span].d.pts;
    }
    size_t start=0,end=observed;
    for(size_t i=1;i<observed;++i)if(confirmed_cut(ctx,i,observed,available)){
        if(i<=requested)start=i;else{end=i;break;}
    }
    if(start && ctx->samples[start].d.pts>ctx->active_cut){
        ctx->active_cut=ctx->samples[start].d.pts;ctx->history_low=1;ctx->history_high=0;
        ctx->history_energy=ctx->history_mass=0;
    }
    while(start<end && ctx->samples[start].d.pts<ctx->active_cut)++start;
    struct cb1_hdr10_temporal_result result={.id=id,.pts=pts,.observed_until=ctx->samples[observed-1].d.pts};
    bool ok=start<end && baseline(ctx,start,end,end<observed,result.base,&result.peak);
    memcpy(result.calibration,ctx->calibration,sizeof(result.calibration));
    if(fesetround(rounding) || !ok)return CB1_AI_INVALID;
    /* Keep two preceding edge observations; older pixels become scalar statistics. */
    size_t retire=requested>2?requested-2:0;
    for(size_t i=0;i<retire;++i)if(ctx->samples[i].d.pts>=ctx->active_cut){
        const struct cb1_hdr10_descriptor *d=&ctx->samples[i].d;
        double dt=ctx->samples[i+1].d.pts-d->pts;
        ctx->history_low=fmin(ctx->history_low,d->global[0]);ctx->history_high=fmax(ctx->history_high,d->global[1]);
        ctx->history_energy+=dt*d->global[2];ctx->history_mass+=dt;
    }
    if(retire){memmove(ctx->samples,ctx->samples+retire,(ctx->count-retire)*sizeof(*ctx->samples));ctx->count-=retire;}
    *out=result;return CB1_AI_READY;
}
