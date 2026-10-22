/* SPDX-License-Identifier: MIT */
#include "cb1_hdr10plus_curve.h"
#include "cb1_hdr10plus.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

/* Independent receive-side expansion: HDMI removes two low bits. */
static double received(const uint8_t packet[31],double x)
{
    const uint8_t *p=packet+4;
    unsigned count=p[14]>>4;
    double kx=(((p[14]&15)<<6)|(p[15]>>2))*4.0/4095;
    double ky=(((p[15]&3)<<8)|p[16])*4.0/4095;
    if(x<kx)return ky*x/kx;
    double b[11]={0};
    for(unsigned i=0;i<count;i++)b[i+1]=p[17+i]*4.0/1023;
    b[count+1]=1;
    double t=(x-kx)/(1-kx);
    for(unsigned n=count+1;n;n--)for(unsigned i=0;i<n;i++)b[i]=b[i]*(1-t)+b[i+1]*t;
    return ky+(1-ky)*b[0];
}

int main(void)
{
    double values[CB1_HDR10PLUS_CURVE_SAMPLES];
    struct cb1_hdr10plus_curve c={0};
    for(unsigned i=0;i<CB1_HDR10PLUS_CURVE_SAMPLES;i++)values[i]=i/1024.0*.75;
    assert(!cb1_hdr10plus_curve_fit(&c,values,992));
    /* Independent cubic Bezier oracle, P1=.2, P2=.8. */
    for(unsigned i=0;i<CB1_HDR10PLUS_CURVE_SAMPLES;i++){
        double x=i/1024.0;values[i]=3*x*(1-x)*(1-x)*.2+3*x*x*(1-x)*.8+x*x*x;
    }
    assert(cb1_hdr10plus_curve_fit(&c,values,992));
    assert(c.maximum_pq_error<=2.0/1023);
    double last=-1;
    for(unsigned i=0;i<8193;i++){
        double y=cb1_hdr10plus_curve_sample(&c,i/8192.0);
        assert(y>=last && y>=0 && y<=1);last=y;
    }
    AVDynamicHDRPlus m={.itu_t_t35_country_code=0xb5,.application_version=1,.num_windows=1,
        .targeted_system_display_maximum_luminance={992,1}};
    AVHDRPlusColorTransformParams *p=&m.params[0];
    for(unsigned i=0;i<3;i++)p->maxscl[i]=(AVRational){0,1};
    p->average_maxrgb=p->fraction_bright_pixels=(AVRational){0,1};
    unsigned perc[]={1,5,10,25,50,75,90,95,99};
    p->num_distribution_maxrgb_percentiles=9;
    for(unsigned i=0;i<9;i++)p->distribution_maxrgb[i]=(AVHDRPlusPercentile){perc[i],{i==2?255:0,100000}};
    assert(cb1_hdr10plus_curve_apply(&m,&c));
    assert(m.params[0].num_bezier_curve_anchors==c.count && m.params[0].tone_mapping_flag);
    uint8_t packet[31];assert(cb1_hdr10plus_vsif(packet,&m,false,true)==CB1_HDR10PLUS_OK);
    for(unsigned i=0;i<=8192;i++){
        double x=i/8192.0;
        assert(fabs(received(packet,x)-cb1_hdr10plus_curve_sample(&c,x))<1e-12);
    }
    assert(received(packet,1)==1);
    struct cb1_hdr10plus_curve old=c;
    values[7]=NAN;assert(!cb1_hdr10plus_curve_fit(&c,values,992));assert(!memcmp(&c,&old,sizeof(c)));
    for(unsigned i=0;i<CB1_HDR10PLUS_CURVE_SAMPLES;i++)values[i]=i<512?.0:1.0;
    assert(!cb1_hdr10plus_curve_fit(&c,values,992));
    values[100]=.5;assert(!cb1_hdr10plus_curve_fit(&c,values,992));
    assert(!cb1_hdr10plus_curve_fit(&c,values,1000));
    puts("HDR10+ quantized curves: accuracy, monotonicity, invalid inputs passed");
}
