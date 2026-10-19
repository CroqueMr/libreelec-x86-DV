/* SPDX-License-Identifier: GPL-3.0-only */
#include "cb1_dv_enhanced.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static uint16_t wire(double n)
{double x=pow(n/10000,2610.0/16384);return lround(4095*pow((3424.0/4096+2413.0/128*x)/(1+2392.0/128*x),2523.0/32));}
int main(void)
{
    struct cb1_dv_enhanced_source s={.master=1000,.l1_present=true,
        .analysis={0,wire(800),wire(30)}};
    struct dvbridge_policy p={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2500,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct cb1_dv_enhanced_plan a,b,fp16;
    assert(cb1_dv_enhanced_build(&a,&s,&p)==CB1_DVE_IDENTITY && a.reason==CB1_DVE_NO_CREATIVE);
    p.adaptive=DVBRIDGE_ADAPTIVE_B_FP32;
    assert(cb1_dv_enhanced_build(&b,&s,&p)==CB1_DVE_READY && !b.count && !b.family);
    double previous=0;
    for(unsigned i=0;i<=1000;i++){
        double input[3]={i,i,i},out[3];
        assert(cb1_dv_enhanced_pixel(&b,input,out));
        assert(out[0]>=i && out[0]>=previous && out[0]<=2500);
        assert(out[0]==out[1] && out[1]==out[2]);previous=out[0];
        if(i<=10)assert(!memcmp(input,out,sizeof(input)));
        if(i==800)assert(out[0]>1500);
    }
    p.adaptive=DVBRIDGE_ADAPTIVE_B_FP16;
    assert(cb1_dv_enhanced_build(&fp16,&s,&p)==CB1_DVE_READY);
    assert(!memcmp(fp16.extra,b.extra,sizeof(b.extra)) && !memcmp(fp16.color,b.color,sizeof(b.color)));
    /* Small L1 fluctuations cannot bypass the established temporal slew limit. */
    s.analysis[1]=wire(760);
    assert(cb1_dv_enhanced_build(&fp16,&s,&p)==CB1_DVE_READY);
    cb1_dv_enhanced_transition(&fp16,&b,1.0/60,false);
    for(unsigned k=0;k<257;k++)assert(fabs(fp16.extra[k]-b.extra[k])<=.5/60*1500+1e-8);
    /* Selecting A must never blend the previous B curve into its first frame. */
    struct cb1_dv_enhanced_plan fresh=b;
    fresh.policy.adaptive=DVBRIDGE_ADAPTIVE_A;fresh.count=1;
    memset(fresh.extra,0,sizeof(fresh.extra));
    a=fresh;cb1_dv_enhanced_transition(&a,&b,1.0/60,false);
    assert(!memcmp(&a,&fresh,sizeof(a)) && "A/B histories must be isolated");
    s.analysis[1]=wire(800);s.family=8;s.count=1;s.weights[0]=1;
    s.anchors[0]=(struct dvbridge_cm4_anchor){.present=true,
        .target={.max_pq=wire(600),.primaries=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020),.transfer=PL_COLOR_TRC_PQ},
        .controls={.primary={2048,2048,2304,2200,2300,2048},.present_fields=DVBRIDGE_CM4_PRIMARY}};
    assert(cb1_dv_enhanced_build(&a,&s,&p)==CB1_DVE_READY);
    assert(memcmp(a.extra,b.extra,sizeof(a.extra)) && a.color[0]>0 && a.color[1]>0);
    double rgb[3]={500,200,50},out[3];
    assert(cb1_dv_enhanced_pixel(&a,rgb,out));
    assert(out[0]>=rgb[0] && out[0]<=2500 && fabs(out[0]/out[1]-2.5)<1e-12);
    s.l1_present=false;
    assert(cb1_dv_enhanced_build(&b,&s,&p)==CB1_DVE_IDENTITY && b.reason==CB1_DVE_NO_ANALYSIS);
    s.l1_present=true;s.analysis[0]=4095;
    assert(cb1_dv_enhanced_build(&b,&s,&p)==CB1_DVE_INVALID);
    p.mode=DVBRIDGE_MODE_STANDARD;
    assert(dvbridge_policy_validate(&p)==DVBRIDGE_POLICY_INVALID_VALUE);
    puts("PASS Adaptive A isolation, B without trims, black/peak limits, temporal slew and precision policy");
}
