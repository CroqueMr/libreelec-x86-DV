/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_dv_adaptive_rev_b.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

static uint16_t wire(double n)
{
    double x=pow(n/10000,2610.0/16384);
    return lround(4095*pow((3424.0/4096+2413.0/128*x)/(1+2392.0/128*x),2523.0/32));
}

static double seconds(void)
{struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}

static double mapped(const struct cb1_dv_enhanced_plan *p,double x)
{double out[3];assert(cb1_dv_enhanced_pixel(p,(double[3]){x,x,x},out));return out[0];}

static void signed_guides(void)
{
    struct dvbridge_policy p={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,
        .tv={2500,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct cb1_dv_enhanced_source s={.master=1000,.l1_present=true,
        .analysis={0,wire(800),wire(30)},.family=8,.count=1,.weights={1}};
    s.anchors[0]=(struct dvbridge_cm4_anchor){.present=true,
        .target={.max_pq=wire(2500),.primaries=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020),
                 .transfer=PL_COLOR_TRC_PQ},
        .controls={.present_fields=DVBRIDGE_CM4_PRIMARY,
                   .primary={2048,2048,2048,2048,2048,2048}}};
    for(unsigned family=2;family<=8;family+=6){
        s.family=family;struct cb1_dv_enhanced_plan neutral,low,high,far,absent;
        assert(cb1_dv_enhanced_build_rev_b(&neutral,&s,&p)==CB1_DVE_READY);
        s.anchors[0].controls.primary[0]=1536;
        assert(cb1_dv_enhanced_build_rev_b(&low,&s,&p)==CB1_DVE_READY);
        s.anchors[0].controls.primary[0]=2560;
        assert(cb1_dv_enhanced_build_rev_b(&high,&s,&p)==CB1_DVE_READY);
        assert(mapped(&low,800)<mapped(&neutral,800)-5 &&
               mapped(&high,800)>mapped(&neutral,800)+5 &&
               "Signed constant tonal gain must survive shape normalization");
        s.anchors[0].target.max_pq=wire(600);
        assert(cb1_dv_enhanced_build_rev_b(&far,&s,&p)==CB1_DVE_READY);
        assert(mapped(&far,800)>mapped(&neutral,800) && mapped(&far,800)<mapped(&high,800));
        s.anchors[0].target.max_pq=wire(2500);
        s.anchors[0].controls.primary[0]=2048;
        s.count=0;s.family=0;
        assert(cb1_dv_enhanced_build_rev_b(&absent,&s,&p)==CB1_DVE_READY);
        assert(!memcmp(absent.extra,neutral.extra,sizeof(neutral.extra)));
        s.count=1;s.family=family;
    }
    struct cb1_dv_enhanced_plan neutral,low,high;
    assert(cb1_dv_enhanced_build_rev_b(&neutral,&s,&p)==CB1_DVE_READY);
    s.anchors[0].controls.primary[4]=2560;
    assert(cb1_dv_enhanced_build_rev_b(&low,&s,&p)==CB1_DVE_READY);
    s.anchors[0].controls.primary[4]=1536;
    assert(cb1_dv_enhanced_build_rev_b(&high,&s,&p)==CB1_DVE_READY);
    assert(mapped(&low,800)<mapped(&neutral,800) && mapped(&high,800)>mapped(&neutral,800));
    s.anchors[0].controls.present_fields=0;
    assert(cb1_dv_enhanced_build_rev_b(&high,&s,&p)==CB1_DVE_READY);
    assert(!memcmp(high.extra,neutral.extra,sizeof(neutral.extra)));
    s.weights[0]=NAN;
    assert(cb1_dv_enhanced_build_rev_b(&high,&s,&p)==CB1_DVE_INVALID);
    s.weights[0]=0;
    assert(cb1_dv_enhanced_build_rev_b(&high,&s,&p)==CB1_DVE_INVALID);
    s.weights[0]=1;
    for(unsigned field=0;field<5;field++)for(unsigned sign=0;sign<2;sign++){
        s.anchors[0].controls=(struct dvbridge_cm4_controls){
            .present_fields=DVBRIDGE_CM4_PRIMARY|DVBRIDGE_CM4_MID_CONTRAST|DVBRIDGE_CM4_CLIP_TRIM,
            .primary={2048,2048,2048,2048,2048,2048},.mid_contrast=2048,.clip_trim=2048};
        uint16_t code=sign?3072:1024;
        if(field<3)s.anchors[0].controls.primary[field]=code;
        else if(field==3)s.anchors[0].controls.mid_contrast=code;
        else s.anchors[0].controls.clip_trim=code;
        assert(cb1_dv_enhanced_build_rev_b(&high,&s,&p)==CB1_DVE_READY);
        double previous=0;
        for(unsigned x=0;x<=1000;x++){
            double y=mapped(&high,x);
            assert(isfinite(y) && y>=x && y>=previous && y<=2500);
            if(x<=10)assert(y==x);
            previous=y;
        }
    }
}

static void report(void)
{
    struct cb1_dv_enhanced_source source={.master=1000,.l1_present=true,
        .analysis={0,wire(800),wire(30)}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,.tv={2500,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct cb1_dv_enhanced_plan plans[2];
    for(unsigned scene=0;scene<3;scene++){
        source.analysis[1]=wire((double[]){400,800,1000}[scene]);
        source.analysis[2]=wire((double[]){10,30,250}[scene]);
        assert(cb1_dv_enhanced_build(&plans[0],&source,&policy)==CB1_DVE_READY);
        assert(cb1_dv_enhanced_build_rev_b(&plans[1],&source,&policy)==CB1_DVE_READY);
        for(unsigned i=0;i<9;i++){
            double x=(double[]){0,5,10,20,50,100,200,400,800}[i],out[2][3];
            for(unsigned m=0;m<2;m++)assert(cb1_dv_enhanced_pixel(&plans[m],(double[3]){x,x,x},out[m]));
            printf("{\"kind\":\"curve\",\"scene\":%u,\"input_nits\":%.9g,\"baseline\":%.9g,\"rev_b\":%.9g}\n",
                scene,x,out[0][0],out[1][0]);
        }
    }
    for(unsigned mode=0;mode<2;mode++){
        struct cb1_dv_enhanced_plan old={0};double previous_pq=0,max_delta=0;
        for(unsigned f=0;f<240;f++){
            unsigned segment=f/120;
            source.analysis[1]=wire((segment?600:800)+(f%2?2:-2));
            source.analysis[2]=wire(segment?45:30);
            struct cb1_dv_enhanced_plan desired;
            assert((mode?cb1_dv_enhanced_build_rev_b(&desired,&source,&policy):
                cb1_dv_enhanced_build(&desired,&source,&policy))==CB1_DVE_READY);
            cb1_dv_enhanced_transition(&desired,&old,1.0/60,f==0 || f==120);
            if(f!=0 && f!=120)for(unsigned k=0;k<257;k++)assert(fabs(desired.extra[k]-old.extra[k])<=12.5+1e-8);
            double output[3];assert(cb1_dv_enhanced_pixel(&desired,(double[3]){200,200,200},output));
            double q=wire(output[0]);
            if(f && f!=120)max_delta=fmax(max_delta,fabs(q-previous_pq));
            previous_pq=q;old=desired;
        }
        printf("{\"kind\":\"temporal\",\"mode\":%u,\"frames\":240,\"max_step_code12\":%.9g,\"reset_at\":120}\n",mode,max_delta);
    }
    source.analysis[1]=wire(800);source.analysis[2]=wire(30);
    for(unsigned mode=0;mode<2;mode++)for(unsigned repeat=0;repeat<9;repeat++){
        double start=seconds();
        for(unsigned i=0;i<1000;i++)assert((mode?cb1_dv_enhanced_build_rev_b(&plans[mode],&source,&policy):
            cb1_dv_enhanced_build(&plans[mode],&source,&policy))==CB1_DVE_READY);
        printf("{\"kind\":\"cpu_plan\",\"mode\":%u,\"mean_us\":%.9g}\n",mode,(seconds()-start)*1000);
    }
}

int main(int argc,char **argv)
{
    if(argc==2 && !strcmp(argv[1],"--report")){report();return 0;}
    assert(cb1_dv_enhanced_build_rev_b && "Separate authored-DV rev B builder required");
    signed_guides();
    struct dvbridge_policy policy={.revision=3,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,
        .tv={2500,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct cb1_dv_enhanced_source source={.master=1000,.l1_present=true,
        .analysis={0,wire(800),wire(30)},.family=8,.count=1,.weights={1}};
    source.anchors[0]=(struct dvbridge_cm4_anchor){.present=true,
        .target={.max_pq=wire(600),.primaries=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020),
                 .transfer=PL_COLOR_TRC_PQ},
        .controls={.primary={2048,2048,2048,2048,2048,2048},
                   .present_fields=DVBRIDGE_CM4_PRIMARY|DVBRIDGE_CM4_SATURATION|DVBRIDGE_CM4_HUE,
                   .saturation={220,128,128,128,128,128},.hue={128,128,128,128,200,128}}};
    struct cb1_dv_enhanced_source saved=source;
    struct dvbridge_policy saved_policy=policy;
    struct cb1_dv_enhanced_plan old,b,other;
    assert(cb1_dv_enhanced_build(&old,&source,&policy)==CB1_DVE_READY);
    assert(cb1_dv_enhanced_build_rev_b(&b,&source,&policy)==CB1_DVE_READY);
    assert(!memcmp(&source,&saved,sizeof(source)) && !memcmp(&policy,&saved_policy,sizeof(policy)));
    double sum=0;for(unsigned i=2;i<67;i++){sum+=old.color[i];assert(b.color[i]==0);}
    assert(sum>0);
    double previous=0;
    for(unsigned i=0;i<=1000;i++){
        double input[3]={i,i,i},a[3],out[3];
        assert(cb1_dv_enhanced_pixel(&old,input,a) && cb1_dv_enhanced_pixel(&b,input,out));
        assert(out[0]>=i && out[0]>=previous && out[0]<=2500);
        if(i<=10)assert(!memcmp(input,out,sizeof(input)));
        if(i==100)assert(out[0]<a[0] && out[0]-i<(a[0]-i)*.5);
        if(i==800)assert(out[0]<a[0] && out[0]>2000);
        previous=out[0];
    }
    source.anchors[0].controls.saturation[0]=16;source.anchors[0].controls.hue[4]=8;
    assert(cb1_dv_enhanced_build_rev_b(&other,&source,&policy)==CB1_DVE_READY);
    assert(!memcmp(other.extra,b.extra,sizeof(b.extra)) && !memcmp(other.color,b.color,sizeof(b.color)));
    /* A dark destination still participates in the previous curve's fade-out. */
    source=saved;source.analysis[1]=wire(80);source.analysis[2]=wire(10);
    struct cb1_dv_enhanced_plan dark[2];
    assert(cb1_dv_enhanced_build_rev_b(&dark[0],&source,&policy)==CB1_DVE_IDENTITY);
    source.anchors[0].controls.saturation[0]=16;source.anchors[0].controls.hue[4]=8;
    assert(cb1_dv_enhanced_build_rev_b(&dark[1],&source,&policy)==CB1_DVE_IDENTITY);
    for(unsigned i=0;i<2;i++)cb1_dv_enhanced_transition(&dark[i],&b,1.0/60,false);
    assert(!memcmp(dark[0].color,dark[1].color,sizeof(b.color)) &&
        "SDR secondary trims must not reappear during READY to DARK_SCENE");
    assert(!memcmp(dark[0].extra,dark[1].extra,sizeof(b.extra)));
    double fade[2][3];
    for(unsigned i=0;i<2;i++)assert(cb1_dv_enhanced_pixel(&dark[i],(double[3]){80,60,20},fade[i]));
    assert(!memcmp(fade[0],fade[1],sizeof(fade[0])));
    source=saved;source.anchors[0].controls.primary[2]=2304;
    assert(cb1_dv_enhanced_build_rev_b(&other,&source,&policy)==CB1_DVE_READY);
    assert(memcmp(other.extra,b.extra,sizeof(b.extra)) && "HDR trims must still guide expansion");
    source=saved;source.count=source.family=0;
    assert(cb1_dv_enhanced_build_rev_b(&b,&source,&policy)==CB1_DVE_READY);
    for(unsigned peak=600;peak<=4000;peak+=200){
        policy.tv.peak_nits=peak;
        assert(cb1_dv_enhanced_build_rev_b(&b,&source,&policy)!=CB1_DVE_INVALID);
        for(unsigned i=0;i<=1000;i++){
            double rgb[3]={i,.4*i,.05*i},out[3];
            assert(cb1_dv_enhanced_pixel(&b,rgb,out) && out[0]>=rgb[0] && out[0]<=fmax(peak,i)+1e-8);
            if(i)assert(fabs(out[1]/out[0]-.4)<1e-12 && fabs(out[2]/out[0]-.05)<1e-12);
        }
    }
    policy=saved_policy;source=saved;
    assert(cb1_dv_enhanced_build_rev_b(&b,&source,&policy)==CB1_DVE_READY);
    source.analysis[1]=wire(760);
    assert(cb1_dv_enhanced_build_rev_b(&other,&source,&policy)==CB1_DVE_READY);
    cb1_dv_enhanced_transition(&other,&b,1.0/60,false);
    for(unsigned i=0;i<257;i++)assert(fabs(other.extra[i]-b.extra[i])<=12.5+1e-8);
    struct cb1_dv_enhanced_plan desired=other;
    cb1_dv_enhanced_transition(&other,&b,0,true);
    assert(!memcmp(&other,&desired,sizeof(other)));
    policy.mode=DVBRIDGE_MODE_STANDARD;
    assert(cb1_dv_enhanced_build_rev_b(&other,&source,&policy)==CB1_DVE_INVALID);
    assert(cb1_dv_enhanced_build_rev_b(NULL,&source,&saved_policy)==CB1_DVE_INVALID);
    puts("PASS rev B selectivity, immutable source, SDR exclusion, HDR guidance, blacks, bounds and temporal slew");
}
