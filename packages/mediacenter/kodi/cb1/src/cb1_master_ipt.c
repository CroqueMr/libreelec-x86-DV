/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_master_ipt.h"
#include "cb1_master_reference.h"
#include <libavutil/dovi_meta.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>

/* Observed Yblod TV-led IPT convention. No fitted output offsets. */
const int16_t cb1_ipt_output_ycc[9]={8194,799,1681,8194,-933,1091,8194,267,-5545};
const int16_t cb1_ipt_output_lms[9]={17080,-348,-348,-348,17080,-348,-348,-348,17080};

static bool inverse(double out[9],const double a[9])
{
    double d=a[0]*(a[4]*a[8]-a[5]*a[7])-a[1]*(a[3]*a[8]-a[5]*a[6])+a[2]*(a[3]*a[7]-a[4]*a[6]);
    if(!isfinite(d) || fabs(d)<1e-12)return false;
    const double adj[]={a[4]*a[8]-a[5]*a[7],a[2]*a[7]-a[1]*a[8],a[1]*a[5]-a[2]*a[4],
        a[5]*a[6]-a[3]*a[8],a[0]*a[8]-a[2]*a[6],a[2]*a[3]-a[0]*a[5],
        a[3]*a[7]-a[4]*a[6],a[1]*a[6]-a[0]*a[7],a[0]*a[4]-a[1]*a[3]};
    for(int i=0;i<9;i++)out[i]=adj[i]/d;
    return true;
}

bool cb1_master_ipt_prepare(struct cb1_master_ipt *out,const void *metadata,size_t bytes)
{
    if(!out)return false;
    memset(out,0,sizeof(*out));
    if(!cb1_master_reference_transport(metadata,bytes))return false;
    const AVDOVIColorMetadata *c=av_dovi_get_color((const AVDOVIMetadata *)metadata);
    struct cb1_master_ipt plan={0}; double a[9],b[9],invb[9];
    for(int i=0;i<9;i++) {
        a[i]=cb1_ipt_output_ycc[i]/8192.; b[i]=cb1_ipt_output_lms[i]/16384.;
        plan.decode[i]=av_q2d(c->ycc_to_rgb_matrix[i]);
    }
    if(!inverse(plan.encode,a) || !inverse(invb,b))return false;
    for(int i=0;i<3;i++) {
        plan.offset[i]=av_q2d(c->ycc_to_rgb_offset[i]);
        for(int j=0;j<3;j++)for(int k=0;k<3;k++)
            plan.linear[3*i+j]+=invb[3*i+k]*av_q2d(c->rgb_to_lms_matrix[3*k+j]);
    }
    *out=plan; return true;
}

static double pq(double x,bool encode)
{
    const double m1=2610./16384,m2=2523./32,c1=3424./4096,c2=2413./128,c3=2392./128;
    x=fmax(0,fmin(1,x));
    if(encode){double p=pow(x,m1);return pow((c1+c2*p)/(1+c3*p),m2);}
    double p=pow(x,1/m2);return pow(fmax(p-c1,0)/(c2-c3*p),1/m1);
}

void cb1_master_ipt_convert(const struct cb1_master_ipt *p,const double in[3],double out[3])
{
    double rgb[3]={0},lms[3]={0};
    for(int i=0;i<3;i++) {
        for(int j=0;j<3;j++)rgb[i]+=p->decode[3*i+j]*(in[j]-p->offset[j]);
        rgb[i]=pq(rgb[i],false);
    }
    for(int i=0;i<3;i++) {
        for(int j=0;j<3;j++)lms[i]+=p->linear[3*i+j]*rgb[j];
        lms[i]=pq(lms[i],true);
    }
    for(int i=0;i<3;i++) {
        out[i]=i?.5:0;
        for(int j=0;j<3;j++)out[i]+=p->encode[3*i+j]*lms[j];
    }
}

bool cb1_master_ipt_tables(pl_gpu gpu,pl_tex tables[2],bool compact)
{
    if(tables[0] && tables[1])return true;
    const int components=compact?1:2;
    pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_FLOAT,components,32,32,PL_FMT_CAP_SAMPLEABLE);
    if(!fmt)return false;
    float *data=malloc(components*256*257*sizeof(float));if(!data)return false;
    pl_tex next[2]={0};bool ok=true;
    for(int encode=0;encode<2 && ok;encode++) {
        for(int i=0;i<256*257;i++)for(int side=0;side<components;side++) {
            double x=fmin(i+side,65536)/65536.;
            data[components*i+side]=pq(encode?x*x*x*x:x,encode);
        }
        next[encode]=pl_tex_create(gpu,pl_tex_params(.w=256,.h=257,.format=fmt,
            .sampleable=true,.initial_data=data));
        ok=next[encode]!=NULL;
    }
    free(data);
    if(!ok){pl_tex_destroy(gpu,&next[0]);pl_tex_destroy(gpu,&next[1]);return false;}
    for(int i=0;i<2;i++){pl_tex_destroy(gpu,&tables[i]);tables[i]=next[i];}
    return true;
}

