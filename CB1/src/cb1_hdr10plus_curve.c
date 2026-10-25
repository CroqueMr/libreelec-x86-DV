/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_hdr10plus_curve.h"
#include <math.h>
#include <string.h>

static double sample(const double *values,double x)
{
    double index=fmin(1024,fmax(0,x*1024));unsigned lo=(unsigned)index;
    return lo==1024?values[1024]:values[lo]+(values[lo+1]-values[lo])*(index-lo);
}

static double pq(double nits)
{
    double x=pow(nits/10000,2610.0/16384);
    return pow((3424.0/4096+2413.0/128*x)/(1+2392.0/128*x),2523.0/32);
}

static bool valid(const struct cb1_hdr10plus_curve *c)
{
    if(!c || !c->count || c->count>9 || c->knee_x>1023 || c->knee_y>1023)return false;
    for(unsigned i=1;i<c->count;i++)if(c->anchors[i]<c->anchors[i-1])return false;
    return true;
}

double cb1_hdr10plus_curve_sample(const struct cb1_hdr10plus_curve *curve,double x)
{
    if(!valid(curve) || !isfinite(x) || x<0 || x>1)return NAN;
    /* Validate the receive-side expansion of the transmitted integers. */
    double kx=curve->knee_x*4.0/4095,ky=curve->knee_y*4.0/4095;
    if(kx>0 && x<kx)return ky*x/kx;
    double t=(x-kx)/(1-kx),p[11]={0};
    for(unsigned i=0;i<curve->count;i++)p[i+1]=curve->anchors[i]*4.0/1023;
    p[curve->count+1]=1;
    for(unsigned n=curve->count+1;n>0;n--)for(unsigned i=0;i<n;i++)p[i]+=(p[i+1]-p[i])*t;
    return ky+(1-ky)*p[0];
}

static double error(const struct cb1_hdr10plus_curve *c,const double *reference,unsigned target)
{
    double worst=0;
    for(unsigned i=0;i<=4096;i++){
        double x=i/4096.0;x*=x;
        double actual=cb1_hdr10plus_curve_sample(c,x);
        if(!isfinite(actual) || actual<0 || actual>1+1e-12)return INFINITY;
        worst=fmax(worst,fabs(pq(actual*target)-reference[i]));
    }
    return worst;
}

static void fit_anchors(struct cb1_hdr10plus_curve *c,const double *values)
{
    double a[9][9]={{0}},b[9]={0},p[9];
    double kx=c->knee_x*4.0/4095,ky=c->knee_y*4.0/4095;
    /* Degree ten, nine interior anchors. Monotone controls guarantee a
     * monotone output after quantization as well as before it. */
    static const unsigned binomial[]={1,10,45,120,210,252,210,120,45,10,1};
    for(unsigned i=1;i<256;i++){
        double t=i/256.0,x=kx+(1-kx)*t;
        double y=(sample(values,x)-ky)/(1-ky)-pow(t,10),basis[9];
        for(unsigned j=0;j<9;j++)basis[j]=binomial[j+1]*pow(t,j+1)*pow(1-t,9-j);
        for(unsigned j=0;j<9;j++){
            b[j]+=basis[j]*y;
            for(unsigned k=0;k<9;k++)a[j][k]+=basis[j]*basis[k];
        }
    }
    for(unsigned j=0;j<9;j++)p[j]=(j+1)/10.0;
    for(unsigned pass=0;pass<128;pass++)for(unsigned j=0;j<9;j++){
        double value=b[j];for(unsigned k=0;k<9;k++)if(k!=j)value-=a[j][k]*p[k];
        p[j]=fmin(j==8?1:p[j+1],fmax(j==0?0:p[j-1],value/a[j][j]));
    }
    c->count=9;for(unsigned j=0;j<9;j++)c->anchors[j]=(uint8_t)fmin(255,lround(p[j]*1023/4));
}

bool cb1_hdr10plus_curve_fit(struct cb1_hdr10plus_curve *out,const double values[CB1_HDR10PLUS_CURVE_SAMPLES],unsigned target)
{
    if(!out || !values || !target || target>992 || target%32)return false;
    for(unsigned i=0;i<CB1_HDR10PLUS_CURVE_SAMPLES;i++){
        if(!isfinite(values[i]) || values[i]<0 || values[i]>1 || (i && values[i]<values[i-1]))return false;
    }
    if(values[0]!=0)return false;
    double reference[4097];
    for(unsigned i=0;i<=4096;i++){
        double x=i/4096.0;x*=x;
        reference[i]=pq(sample(values,x)*target);
    }
    struct cb1_hdr10plus_curve best={.knee_x=1023,.knee_y=(uint16_t)fmin(1023,lround(values[1024]*4095/4)),
        .count=1,.anchors={128}};
    best.maximum_pq_error=error(&best,reference,target);
    static const double knees[]={0,.03125,.0625,.125,.25,.5,.75};
    for(unsigned i=0;i<sizeof(knees)/sizeof(*knees);i++){
        struct cb1_hdr10plus_curve c={.knee_x=(uint16_t)lround(knees[i]*4095/4)};
        c.knee_y=(uint16_t)fmin(1023,lround(sample(values,c.knee_x*4.0/4095)*4095/4));
        if(c.knee_y==1023)continue;
        fit_anchors(&c,values);c.maximum_pq_error=error(&c,reference,target);
        if(c.maximum_pq_error<best.maximum_pq_error)best=c;
    }
    if(best.maximum_pq_error>2.0/1023)return false;
    *out=best;return true;
}

bool cb1_hdr10plus_curve_apply(AVDynamicHDRPlus *m,const struct cb1_hdr10plus_curve *curve)
{
    if(!m || m->num_windows!=1 || !valid(curve))return false;
    AVHDRPlusColorTransformParams *p=&m->params[0];
    p->tone_mapping_flag=1;
    p->knee_point_x=(AVRational){curve->knee_x*4,4095};
    p->knee_point_y=(AVRational){curve->knee_y*4,4095};
    p->num_bezier_curve_anchors=curve->count;
    memset(p->bezier_curve_anchors,0,sizeof(p->bezier_curve_anchors));
    for(unsigned i=0;i<curve->count;i++)
        p->bezier_curve_anchors[i]=(AVRational){curve->anchors[i]*4,1023};
    return true;
}
