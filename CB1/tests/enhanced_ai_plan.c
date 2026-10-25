/* SPDX-License-Identifier: GPL-3.0-only */
#include "cb1_dv_enhanced.h"
#include "cb1_circuit.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

extern enum cb1_dv_enhanced_status cb1_dv_enhanced_build_ai(
    struct cb1_dv_enhanced_plan *,const struct cb1_dv_enhanced_source *,
    const struct dvbridge_policy *) __attribute__((weak));

int main(int argc,char **argv)
{
    assert(cb1_dv_enhanced_build_ai && "AI must use the shared Enhanced plan");
    assert(!strcmp(cb1_circuit_version(CB1_HDR10_DV_ADAPTIVE),"CB1-HDR10DVA.0.7"));
    assert(!strcmp(cb1_circuit_version(CB1_HDR10_DV_REFERENCE),"CB1-HDR10DVR.0.1.3"));
    struct cb1_dv_enhanced_source s={.master=1000,.l1_present=true,.analysis={0,3080,1463}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct cb1_dv_enhanced_plan p;
    assert(cb1_dv_enhanced_build(&p,&s,&policy)==CB1_DVE_IDENTITY && p.reason==CB1_DVE_NO_CREATIVE);
    assert(cb1_dv_enhanced_build_ai(&p,&s,&policy)==CB1_DVE_READY);
    assert(!p.count && !p.family);
    for(unsigned k=0;k<67;k++)assert(p.color[k]==0);
    double out[3],shadow[3]={12,5,0};
    assert(cb1_dv_enhanced_pixel(&p,shadow,out) && !memcmp(shadow,out,sizeof(out)));
    assert(!cb1_dv_enhanced_pixel(&p,(double[3]){1001,1001,1001},out));
    s.count=1;assert(cb1_dv_enhanced_build_ai(&p,&s,&policy)==CB1_DVE_INVALID);s.count=0;
    s.family=8;assert(cb1_dv_enhanced_build_ai(&p,&s,&policy)==CB1_DVE_INVALID);s.family=0;
    s.analysis[2]=4095;assert(cb1_dv_enhanced_build_ai(&p,&s,&policy)==CB1_DVE_INVALID);s.analysis[2]=1463;
    s.master=NAN;assert(cb1_dv_enhanced_build_ai(&p,&s,&policy)==CB1_DVE_INVALID);s.master=1000;
    s.l1_present=false;assert(cb1_dv_enhanced_build_ai(&p,&s,&policy)==CB1_DVE_IDENTITY && p.reason==CB1_DVE_NO_ANALYSIS);s.l1_present=true;
    const double masters[]={1000,4000},targets[]={600,1000,2300,10000};
    const double samples[][3]={{0,0,0},{12,5,0},{.1,.1,.1},{.5,.5,.5},{1,1,1},{.8,.2,.1},{.1,.2,.8}};
    bool json=argc==2 && !strcmp(argv[1],"--json"),comma=false;
    if(json)puts("[");
    for(unsigned m=0;m<2;m++)for(unsigned t=0;t<4;t++)for(unsigned preset=0;preset<1;preset++){
        s.master=masters[m];policy.tv.peak_nits=targets[t];
        assert(cb1_dv_enhanced_build_ai(&p,&s,&policy)!=CB1_DVE_INVALID);
        if(!preset && targets[t]<=s.master)assert(p.status==CB1_DVE_IDENTITY && p.reason==CB1_DVE_NO_HEADROOM);
        for(unsigned k=0;k<7;k++){
            double rgb[3];for(unsigned j=0;j<3;j++)rgb[j]=samples[k][j]*(k<2?1:s.master);
            assert(cb1_dv_enhanced_pixel(&p,rgb,out));
            for(unsigned j=0;j<3;j++)assert(isfinite(out[j]) && out[j]>=0 && out[j]<=p.envelope);
            if(json)printf("%s{\"master\":%.17g,\"target\":%.17g,\"preset\":%u,\"family\":0,\"gamut\":0,\"control\":0,\"anchors\":0,\"input\":[%.17g,%.17g,%.17g],\"output\":[%.17g,%.17g,%.17g]}",
                comma?",\n":"",s.master,policy.tv.peak_nits,preset,rgb[0],rgb[1],rgb[2],out[0],out[1],out[2]);
            comma=true;
        }
    }
    if(json)puts("\n]");
    policy.adaptive=DVBRIDGE_ADAPTIVE_B_FP16;
    for(unsigned m=0;m<2;m++)for(unsigned t=0;t<4;t++){
        s.master=masters[m];policy.tv.peak_nits=targets[t];
        struct cb1_dv_enhanced_plan authored;
        assert(cb1_dv_enhanced_build(&authored,&s,&policy)!=CB1_DVE_INVALID);
        assert(cb1_dv_enhanced_build_ai(&p,&s,&policy)==authored.status);
        assert(!memcmp(p.extra,authored.extra,sizeof(p.extra)));
        assert(!memcmp(p.color,authored.color,sizeof(p.color)));
        uint16_t a[3],b[3];
        assert(cb1_dv_enhanced_analysis(&p,a) && cb1_dv_enhanced_analysis(&authored,b));
        assert(!memcmp(a,b,sizeof(a)));
        assert(cb1_dv_enhanced_pixel(&p,(double[3]){500,500,500},out));
        assert(out[0]>500 && out[0]<=fmax(500,policy.tv.peak_nits));
        assert(cb1_dv_enhanced_pixel(&p,shadow,out) && !memcmp(shadow,out,sizeof(out)));
    }
    if(!json)puts("PASS shared Adaptive DV/AI curves, analysis, neutral guidance, bounds and shadows");
}
