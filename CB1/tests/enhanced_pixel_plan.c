/* SPDX-License-Identifier: GPL-3.0-only */
#include "cb1_dv_enhanced.h"
#include "task3_fixture.h"
#include <assert.h>
#include <stdio.h>
#include <math.h>
#include <string.h>

static void matrix(void)
{
    const double pairs[][2]={{500,600},{500,2300},{1000,600},{1000,2300},{4000,1000},{4000,10000}};
    const double samples[][3]={{0,0,0},{12,5,0},{.2,.2,.2},{.5,.5,.5},{.8,.2,.01},{.2,.5,.1},{1,1,1}};
    puts("[");bool comma=false;
    for(unsigned pair=0;pair<6;pair++)for(unsigned preset=1;preset<2;preset++)
    for(unsigned family=0;family<2;family++)for(unsigned gamut=0;gamut<2;gamut++)
    for(unsigned control=0;control<3;control++)for(unsigned anchors=1;anchors<=2;anchors++){
        struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
            .tv={pairs[pair][1],DVBRIDGE_PANEL_UNSET,gamut?DVBRIDGE_GAMUT_P3_D65:DVBRIDGE_GAMUT_BT2020}};
        struct cb1_dv_enhanced_source source={.master=pairs[pair][0],.l1_present=true,
            .analysis={0,3080,1463},.family=family?2:8,.count=anchors,
            .weights={anchors==1?1:.35,anchors==1?0:.65}};
        for(unsigned a=0;a<anchors;a++){
            struct dvbridge_cm4_anchor *v=&source.anchors[a];
            *v=(struct dvbridge_cm4_anchor){.present=true,
                .target={.max_pq=a?3388:2851,.transfer=PL_COLOR_TRC_PQ,
                    .primaries=*pl_raw_primaries_get(gamut?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020)},
                .controls={.primary={2048,2048,2048,2048,2048,2048},.present_fields=31,
                    .mid_contrast=2048,.clip_trim=2048,.saturation={128,128,128,128,128,128},.hue={128,128,128,128,128,128}}};
            if(control==1){v->controls.primary[0]=2304;v->controls.primary[2]=2304;
                v->controls.mid_contrast=2400;v->controls.clip_trim=1800;}
            if(control==2){v->controls.primary[3]=3000;v->controls.primary[4]=2700;
                v->controls.saturation[a]=220;v->controls.hue[4-a]=200;}
            if(family)v->controls.present_fields=1;
        }
        struct cb1_dv_enhanced_plan p;assert(cb1_dv_enhanced_build(&p,&source,&policy)!=CB1_DVE_INVALID);
        for(unsigned sample=0;sample<7;sample++){
            double rgb[3],out[3];for(unsigned j=0;j<3;j++)rgb[j]=sample<2?samples[sample][j]:samples[sample][j]*source.master;
            assert(cb1_dv_enhanced_pixel(&p,rgb,out));
            printf("%s{\"master\":%.17g,\"target\":%.17g,\"preset\":%u,\"family\":%u,\"gamut\":%u,\"control\":%u,\"anchors\":%u,\"input\":[%.17g,%.17g,%.17g],\"output\":[%.17g,%.17g,%.17g]}",
                comma?",\n":"",p.master,p.target,preset,source.family,gamut,control,anchors,rgb[0],rgb[1],rgb[2],out[0],out[1],out[2]);comma=true;
        }
    }
    puts("\n]");
}
int main(int argc,char **argv)
{
    if(argc==2 && !strcmp(argv[1],"--json")){matrix();return 0;}
    assert(cb1_dv_enhanced_build && "Enhanced pixel plan must be implemented");
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct cb1_dv_enhanced_source source={.master=1000,.l1_present=true,
        .analysis={0,3080,1463},.family=8,.count=1,.weights={1}};
    source.anchors[0]=(struct dvbridge_cm4_anchor){.present=true,
        .target={.max_pq=2851,.primaries=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020),
                 .transfer=PL_COLOR_TRC_PQ},
        .controls={.primary={2048,2048,2048,2048,2048,2048},.present_fields=DVBRIDGE_CM4_PRIMARY}};
    struct cb1_dv_enhanced_source adaptive_scene=source;
    adaptive_scene.analysis[1]=2662;
    struct dvbridge_policy adaptive_policy=policy;adaptive_policy.tv.peak_nits=2500;
    struct cb1_dv_enhanced_plan adaptive_plan;
    assert(cb1_dv_enhanced_build(&adaptive_plan,&adaptive_scene,&adaptive_policy)==CB1_DVE_READY);
    double adaptive_highlight[3];
    assert(cb1_dv_enhanced_pixel(&adaptive_plan,(double[3]){390.7172284,390.7172284,390.7172284},adaptive_highlight));
    assert(adaptive_highlight[0]>2100 && adaptive_highlight[0]<2500);
    /* Master-referenced highlights retain the qualified response. */
    struct cb1_dv_enhanced_plan retained;
    
    assert(cb1_dv_enhanced_build(&retained,&source,&policy)==CB1_DVE_READY);
    double retained_out[3];
    assert(cb1_dv_enhanced_pixel(&retained,(double[3]){500,500,500},retained_out));
    assert(fabs(retained_out[0]-818.472)<.03);
    /* A bright highlight below mastering peak must use the available display range. */
    struct cb1_dv_enhanced_source scene=source;scene.analysis[1]=2662;scene.analysis[2]=1463;
    policy.tv.peak_nits=2500;
    struct cb1_dv_enhanced_plan expanded;
    assert(cb1_dv_enhanced_build(&expanded,&scene,&policy)==CB1_DVE_READY);
    double bright[3],shadow[3];
    assert(cb1_dv_enhanced_pixel(&expanded,(double[3]){390.7172284,390.7172284,390.7172284},bright));
    assert(bright[0]>2100 && bright[0]<2500);
    assert(cb1_dv_enhanced_pixel(&expanded,(double[3]){10,10,10},shadow) && shadow[0]==10);
    assert(cb1_dv_enhanced_pixel(&expanded,(double[3]){25,25,25},shadow) && shadow[0]<35);
    /* A lower display target bounds added light, never the original signal. */
    scene.master=4000;scene.analysis[1]=2979;
    assert(cb1_dv_enhanced_build(&expanded,&scene,&policy)==CB1_DVE_READY);
    double previous_signature=0;
    for(unsigned i=0;i<=4000;i++){
        assert(cb1_dv_enhanced_pixel(&expanded,(double[3]){i,i,i},bright));
        assert(bright[0]>=i && bright[0]>=previous_signature);
        assert(bright[0]<=(i<2500?2500:i)+1e-7);
        previous_signature=bright[0];
    }
    policy.tv.peak_nits=2300;
    const double want[]={818.472,818.472};
    for(unsigned preset=1;preset<2;preset++){
        
        struct cb1_dv_enhanced_plan p;
        assert(cb1_dv_enhanced_build(&p,&source,&policy)==CB1_DVE_READY);
        double out[3];assert(cb1_dv_enhanced_pixel(&p,(double[3]){500,500,500},out));
        assert(fabs(out[0]-want[preset])<.03);
        double shadow[3]={12,5,0};
        assert(cb1_dv_enhanced_pixel(&p,shadow,out) && !memcmp(out,shadow,sizeof(out)));
        assert(!cb1_dv_enhanced_pixel(&p,(double[3]){1001,1001,1001},out));
        assert(!cb1_dv_enhanced_pixel(&p,(double[3]){NAN,0,0},out));
        double previous=0;
        for(unsigned i=0;i<=1000;i++){
            assert(cb1_dv_enhanced_pixel(&p,(double[3]){i,i,i},out));
            assert(out[0]>=previous && out[0]<=2300);previous=out[0];
        }
    }
    struct cb1_dv_enhanced_plan p;
    policy.tv.peak_nits=600;
    assert(cb1_dv_enhanced_build(&p,&source,&policy)==CB1_DVE_READY);
    double bounded[3];assert(cb1_dv_enhanced_pixel(&p,(double[3]){500,500,500},bounded));
    assert(bounded[0]>=500 && bounded[0]<=1000);
    source.count=0;policy.tv.peak_nits=2300;
    assert(cb1_dv_enhanced_build(&p,&source,&policy)==CB1_DVE_IDENTITY && p.reason==CB1_DVE_NO_CREATIVE);
    source.count=1;assert(cb1_dv_enhanced_build(&p,&source,&policy)==CB1_DVE_READY);
    struct cb1_dv_enhanced_plan old=p;
    source.analysis[1]=1700;source.analysis[2]=1000;
    policy.revision++;
    assert(cb1_dv_enhanced_build(&p,&source,&policy)==CB1_DVE_IDENTITY);
    cb1_dv_enhanced_transition(&p,&old,0,false);
    assert(!memcmp(p.extra,old.extra,sizeof(p.extra)) && !memcmp(p.color,old.color,sizeof(p.color)));
    assert(cb1_dv_enhanced_build(&p,&source,&policy)==CB1_DVE_IDENTITY);
    cb1_dv_enhanced_transition(&p,&old,1.0/24,false);
    for(unsigned k=0;k<257;k++)assert(fabs(p.extra[k]-old.extra[k])<=.5/24*1300+1e-9);
    p.target++;struct cb1_dv_enhanced_plan desired=p;
    cb1_dv_enhanced_transition(&p,&old,1.0/24,false);
    assert(!memcmp(&p,&desired,sizeof(p)));
    puts("PASS scalar expansion, protected shadows, source bounds and identity");
}
