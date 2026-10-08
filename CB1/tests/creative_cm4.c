/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "task3_fixture.h"
#include "dvbridge_creative.h"
#include <stdio.h>
#include <string.h>
#include <math.h>

static AVDOVIDmData l8(unsigned length)
{
    /* Independent literal RPU bytes: index 20, six neutral 12-bit fields.
     * Optional fields are present zeros, including the secondary vectors. */
    return (AVDOVIDmData){.level=8,.l8={.target_display_index=20,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,
        .trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=2048},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=length,
        .dvbridge_original_bytes={20,0x80,0x08,0x00,0x80,0x08,0x00,0x80,0x08,0x00}};
}

static AVDOVIDmData l10(void)
{
    return (AVDOVIDmData){.level=10,.l10={.target_display_index=20,
        .target_max_pq=3079,.target_min_pq=0,.target_primary_index=2},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
        .dvbridge_original_bytes={20,0xc0,0x70,0x00,2}};
}

static AVDOVIDmData custom_l10(void)
{
    AVDOVIDmData e=l10();
    e.l10.target_primary_index=255;e.dvbridge_original_length=21;
    const uint8_t raw[]={20,0xc0,0x70,0x00,255,0x51,0xeb,0x28,0xf5,
        0x26,0x66,0x4c,0xcc,0x13,0x33,0x07,0xae,0x28,0x06,0x2a,0x1c};
    memcpy(e.dvbridge_original_bytes,raw,sizeof(raw));
    e.l10.target_display_primaries=(AVColorPrimariesDesc){
        .prim={.r={{0x51eb,32767},{0x28f5,32767}},
               .g={{0x2666,32767},{0x4ccc,32767}},
               .b={{0x1333,32767},{0x07ae,32767}}},
        .wp={{0x2806,32767},{0x2a1c,32767}}};
    return e;
}

static void target_order(AVDOVIMetadata *m,size_t bytes)
{
    const unsigned orders[][3]={{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};
    const unsigned peaks[][3]={{3000,3000,3200},{3500,3500,3400},
                               {3200,3200,3000},{3400,3400,3500}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    m->num_ext_blocks=6;
    for(unsigned scenario=0;scenario<4;scenario++)for(unsigned order=0;order<6;order++){
        for(unsigned i=0;i<3;i++){
            unsigned target=orders[order][i],index=50+target,maximum=peaks[scenario][target];
            AVDOVIDmData *a=av_dovi_get_ext(m,i),*b=av_dovi_get_ext(m,3+i);
            *a=l8(10);*b=l10();
            a->l8.target_display_index=a->dvbridge_original_bytes[0]=index;
            b->l10.target_display_index=b->dvbridge_original_bytes[0]=index;
            b->l10.target_max_pq=maximum;
            b->dvbridge_original_bytes[1]=maximum>>4;
            b->dvbridge_original_bytes[2]=(maximum&15)<<4;
        }
        struct dvbridge_creative_plan p;
        assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
        if(scenario<2){
            assert(p.cm4_targets==DVBRIDGE_CM4_TARGETS_RESOLVED);
            const struct dvbridge_cm4_anchor *nearest=scenario?&p.cm4_upper:&p.cm4_lower;
            assert(nearest->present && nearest->target.display_index==52);
            assert(nearest->target.max_pq==peaks[scenario][2]);
        }else{
            assert(p.cm4_targets==DVBRIDGE_CM4_INCOMPATIBLE_TARGETS);
            assert(!p.cm4_lower.present && !p.cm4_upper.present);
        }
    }
    m->num_ext_blocks=2;
}

static void snapshots(AVDOVIMetadata *m,size_t bytes,struct dvbridge_policy *policy)
{
    AVDOVIDmData *a=av_dovi_get_ext(m,0),*b=av_dovi_get_ext(m,1);
    const unsigned lengths[]={10,12,13,19,25};
    const unsigned presence[]={1,3,7,15,31};
    struct dvbridge_creative_plan p;
    for(unsigned i=0;i<5;i++){
        *a=l8(lengths[i]);*b=l10();
        void *before=av_memdup(m,bytes),*edited=NULL;size_t edited_bytes=0;assert(before);
        assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
        assert(p.cm4_targets==DVBRIDGE_CM4_TARGETS_RESOLVED);
        assert(p.cm4_lower.present && p.cm4_upper.present && p.cm4_weight==0);
        const struct dvbridge_cm4_anchor *anchor=&p.cm4_lower;
        assert(anchor->controls.present_fields==presence[i]);
        for(int j=0;j<6;j++)assert(anchor->controls.primary[j]==2048);
        assert(anchor->controls.mid_contrast==0 && anchor->controls.clip_trim==0);
        assert(anchor->target.origin==DVBRIDGE_CM4_CUSTOM && anchor->target.display_index==20);
        assert(anchor->target.transfer==PL_COLOR_TRC_UNKNOWN);
        assert(anchor->target.max_pq==3079 && anchor->target.min_pq_present && anchor->target.min_pq==0);
        assert(p.cm4_output.origin==DVBRIDGE_CM4_MANUAL && !p.cm4_output.min_pq_present);
        assert(p.backend!=DVBRIDGE_CREATIVE_CM4 && !(p.applied_levels&(1u<<8)));
        assert(!memcmp(before,m,bytes));
        struct dvbridge_creative_edit_report report;
        enum dvbridge_creative_status status=dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report);
        assert(status!=DVBRIDGE_CREATIVE_INVALID && report.reason!=DVBRIDGE_CREATIVE_EDIT_TARGET_UNRESOLVED);
        assert(edited_bytes==bytes && edited!=m);
        assert(!memcmp(av_dovi_get_ext(edited,1),b,sizeof(*b)));
        assert(!memcmp(a->dvbridge_original_bytes+9,av_dovi_get_ext(edited,0)->dvbridge_original_bytes+9,23));
        av_free(before);av_free(edited);
    }
    // Absent parsed defaults never become present controls.
    *a=l8(10);a->l8.target_mid_contrast=2048;a->l8.clip_trim=4095;
    memset(a->l8.hue_vector_field,128,6);
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(p.cm4_lower.controls.present_fields==DVBRIDGE_CM4_PRIMARY);
    *a=l8(12);a->dvbridge_original_bytes[11]=1;
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_INVALID);
    *a=l8(11);
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_INVALID);
    *a=l8(10);*b=l10();b->dvbridge_original_length=21;
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_INVALID);
    *b=custom_l10();b->l10.target_display_primaries.wp.x.num++;
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_INVALID);
    *b=custom_l10();memset(b->dvbridge_original_bytes+5,0,16);
    b->l10.target_display_primaries=(AVColorPrimariesDesc){
        .prim={.r={{0,32767},{0,32767}},.g={{0,32767},{0,32767}},.b={{0,32767},{0,32767}}},
        .wp={{0,32767},{0,32767}}};
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_INVALID);
    // A valid custom gamut is preserved separately, not forced to the manual gamut.
    *b=custom_l10();
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(p.cm4_targets==DVBRIDGE_CM4_INCOMPATIBLE_TARGETS);
    // Quantized standard coordinates remain compatible with the native table.
    b->dvbridge_original_bytes[7]=0x2a;b->dvbridge_original_bytes[8]=0x3d;
    b->l10.target_display_primaries.prim.r.y.num=0x2a3d;
    policy->tv.gamut=DVBRIDGE_GAMUT_BT709;
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(p.cm4_targets==DVBRIDGE_CM4_TARGETS_RESOLVED);
    assert(p.cm4_lower.target.origin==DVBRIDGE_CM4_CUSTOM);
    assert(fabs(p.cm4_lower.target.primaries.red.y-0x2a3d/32767.0)<1e-7);
    // Literal secondary bytes are retained without normalizing present zero.
    *a=l8(25);const uint8_t saturation[]={0,128,255,3,64,200},hue[]={255,0,128,42,17,89};
    memcpy(a->dvbridge_original_bytes+13,saturation,6);memcpy(a->l8.saturation_vector_field,saturation,6);
    memcpy(a->dvbridge_original_bytes+19,hue,6);memcpy(a->l8.hue_vector_field,hue,6);
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(!memcmp(p.cm4_lower.controls.saturation,saturation,6));
    assert(!memcmp(p.cm4_lower.controls.hue,hue,6));
    policy->tv.gamut=DVBRIDGE_GAMUT_BT2020;
    *a=l8(10);
    *b=l10();b->l10.target_primary_index=b->dvbridge_original_bytes[4]=99;
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(p.cm4_targets==DVBRIDGE_CM4_UNKNOWN_TARGET && !p.cm4_lower.present);
    m->num_ext_blocks=1;*a=l8(10);
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(p.cm4_targets==DVBRIDGE_CM4_UNKNOWN_TARGET);
    assert(!p.cm4_lower.present && !p.cm4_upper.present && p.cm4_weight==0);
    // Identical peaks do not merge P3 and BT.2020 targets.
    m->num_ext_blocks=2;*a=l8(10);*b=l8(25);
    a->l8.target_display_index=a->dvbridge_original_bytes[0]=48;
    b->l8.target_display_index=b->dvbridge_original_bytes[0]=49;
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(p.cm4_targets==DVBRIDGE_CM4_TARGETS_RESOLVED);
    assert(p.cm4_lower.target.display_index==49 && p.cm4_upper.target.display_index==49);
    assert(p.cm4_lower.target.origin==DVBRIDGE_CM4_PRESET && !p.cm4_lower.target.min_pq_present);
    assert(p.cm4_lower.controls.present_fields==31);
    policy->tv.gamut=DVBRIDGE_GAMUT_P3_D65;
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(p.cm4_lower.target.display_index==48 && p.cm4_upper.target.display_index==48);
    // Source target metadata is neither an output measurement nor a CM4 backend.
    policy->mode=DVBRIDGE_MODE_HDR10_EXPERT;
    assert(dvbridge_creative_resolve(&p,m,bytes,policy)==DVBRIDGE_CREATIVE_NEUTRAL);
    assert(p.backend==DVBRIDGE_CREATIVE_NONE && !(p.applied_levels&(1u<<8)));
    policy->mode=DVBRIDGE_MODE_ENHANCED_DV;policy->tv.gamut=DVBRIDGE_GAMUT_BT2020;
}

#ifndef DVBRIDGE_CM4_SCALAR_API
struct dvbridge_cm4_coefficients;
extern bool dvbridge_creative_cm4_coefficients(struct dvbridge_cm4_coefficients *,
    const struct dvbridge_creative_plan *) __attribute__((weak));
extern bool dvbridge_creative_cm4_trim_rgb(const struct dvbridge_creative_plan *,
    const double [3],double [3]) __attribute__((weak));
#endif

static struct dvbridge_creative_plan scalar_plan(unsigned control,unsigned gamut)
{
    struct dvbridge_creative_plan p={.status=DVBRIDGE_CREATIVE_READY,.cm4=true,
        .cm4_targets=DVBRIDGE_CM4_TARGETS_RESOLVED,.policy={.tv={1000,DVBRIDGE_PANEL_OLED,
        gamut?DVBRIDGE_GAMUT_P3_D65:DVBRIDGE_GAMUT_BT2020}}};
    p.cm4_output.primaries=*pl_raw_primaries_get(gamut?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020);
    p.cm4_output.transfer=PL_COLOR_TRC_PQ;
    p.cm4_lower.present=true;p.cm4_lower.target=p.cm4_output;
    struct dvbridge_cm4_controls *c=&p.cm4_lower.controls;
    c->present_fields=31;c->mid_contrast=c->clip_trim=2048;
    for(unsigned i=0;i<6;i++){c->primary[i]=2048;c->saturation[i]=c->hue[i]=128;}
    if(control<6 && control)c->primary[control-1]=3072;
    if(control==6)c->primary[5]=4095;
    if(control==7)c->mid_contrast=3072;
    if(control==8)c->clip_trim=0;
    if(control==9){c->saturation[0]=255;c->saturation[2]=0;}
    if(control==10){c->hue[0]=0;c->hue[2]=255;}
    if(control==11){c->primary[0]=2304;c->primary[1]=2200;c->primary[2]=1900;
        c->primary[3]=3000;c->primary[4]=2700;c->mid_contrast=2400;c->clip_trim=1800;
        c->saturation[1]=180;c->hue[4]=200;}
    return p;
}

static void scalar_contract(bool emit)
{
    assert(dvbridge_creative_cm4_coefficients && "CM4 scalar coefficients are not implemented");
    assert(dvbridge_creative_cm4_trim_rgb && "CM4 scalar trim is not implemented");
    double out[3];const double rgb[][3]={{0,0,0},{1e-9,1e-9,1e-9},{125,125,125},
        {250,250,250},{500,500,500},{750,750,750},{1000,1000,1000},
        {500,80,40},{40,500,80},{80,40,500},{500,500,40},{40,500,500},{500,40,500}};
    if(emit)printf("{\"cases\":[");
    bool comma=false;
    for(unsigned gamut=0;gamut<2;gamut++)for(unsigned c=0;c<12;c++){
        struct dvbridge_creative_plan p=scalar_plan(c,gamut);
        for(unsigned i=0;i<sizeof(rgb)/sizeof(rgb[0]);i++){
            assert(dvbridge_creative_cm4_trim_rgb(&p,rgb[i],out));
            if(!c)assert(!memcmp(out,rgb[i],sizeof(out)));
            for(int j=0;j<3;j++)assert(isfinite(out[j]));
            if(emit){printf("%s{\"gamut\":%u,\"control\":%u,\"rgb\":[%.17g,%.17g,%.17g],\"out\":[%.17g,%.17g,%.17g]}",
                comma?",":"",gamut,c,rgb[i][0],rgb[i][1],rgb[i][2],out[0],out[1],out[2]);comma=true;}
        }
    }
    if(emit)puts("]}");
#ifdef DVBRIDGE_CM4_SCALAR_API
    struct dvbridge_creative_plan p=scalar_plan(0,0);struct dvbridge_cm4_coefficients c;
    assert(dvbridge_creative_cm4_coefficients(&c,&p));
    assert(c.present==1023 && c.one_anchor==0 && c.detail_mix==0);
    p.cm4_upper=p.cm4_lower;p.cm4_weight=.5;
    p.cm4_upper.controls.mid_contrast=4095;
    p.cm4_lower.controls.present_fields&=~DVBRIDGE_CM4_HUE;
    assert(dvbridge_creative_cm4_coefficients(&c,&p));
    assert(fabs(c.mid_exponent-(1+exp2(2047.0/2048))/2)<1e-12);
    assert(c.one_anchor==(1u<<9));
    p.cm4_weight=NAN;assert(!dvbridge_creative_cm4_coefficients(&c,&p));p.cm4_weight=.5;
    p.cm4_upper.target.primaries=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_709);
    assert(!dvbridge_creative_cm4_coefficients(&c,&p));
    p=scalar_plan(0,0);p.cm4_lower.controls.primary[0]=4096;
    assert(!dvbridge_creative_cm4_coefficients(&c,&p));
    p=scalar_plan(0,0);p.policy.tv.peak_nits=INFINITY;
    assert(!dvbridge_creative_cm4_trim_rgb(&p,rgb[0],out));
    p=scalar_plan(0,0);double invalid[]={NAN,1,2};
    assert(!dvbridge_creative_cm4_trim_rgb(&p,invalid,out));
    p.cm4_targets=DVBRIDGE_CM4_UNKNOWN_TARGET;
    assert(!dvbridge_creative_cm4_coefficients(&c,&p));
    p=scalar_plan(0,0);p.cm4_lower.controls.present_fields=DVBRIDGE_CM4_PRIMARY;
    assert(dvbridge_creative_cm4_coefficients(&c,&p));assert(c.present==63);
    assert(c.mid_exponent==1 && c.clip_strength==0 && c.secondary_gain[0]==1);
    p.cm4_lower.controls.primary[1]=2304;
    assert(dvbridge_creative_cm4_trim_rgb(&p,rgb[0],out));assert(out[0]==62.5);
    p.cm4_lower.controls.primary[1]=1024;
    assert(dvbridge_creative_cm4_trim_rgb(&p,rgb[0],out));assert(out[0]==0);
#endif
}

static double fit_pq(double nits)
{
    double v=pow(fmax(0,nits)/10000,2610.0/16384);
    return pow((3424.0/4096+2413.0/128*v)/(1+2392.0/128*v),2523.0/32);
}
static double fit_nits(double q)
{
    double v=pow(fmax(0,fmin(1,q)),32.0/2523);
    return 10000*pow(fmax(0,v-3424.0/4096)/(2413.0/128-2392.0/128*v),16384.0/2610);
}
static void custom_target_edit(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    AVDOVIDmData *a=av_dovi_get_ext(m,0),*b=av_dovi_get_ext(m,1);
    *a=l8(10);*b=l10();av_dovi_get_color(m)->source_max_pq=3079;
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={fit_nits(3079.0/4095),DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    struct dvbridge_creative_plan p;void *edited=NULL;size_t edited_bytes=0;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)!=DVBRIDGE_CREATIVE_INVALID);
    assert(p.cm4_lower.target.transfer==PL_COLOR_TRC_UNKNOWN);
    struct dvbridge_creative_edit_report report;
    assert(dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report)==DVBRIDGE_CREATIVE_NEUTRAL);
    assert(report.candidate_evaluations && report.reason==DVBRIDGE_CREATIVE_OK);
    assert(report.candidate_evaluations<=3 && "An exact identity must not run the trim search");
    assert(edited_bytes==bytes && !memcmp(m,edited,bytes));av_free(edited);
    b->l10.target_primary_index=b->dvbridge_original_bytes[4]=99;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)!=DVBRIDGE_CREATIVE_INVALID);
    assert(dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(report.reason==DVBRIDGE_CREATIVE_EDIT_TARGET_UNRESOLVED);
    assert(!memcmp(m,edited,bytes));av_free(edited);av_free(m);
    puts("PASS resolved custom target edit without inferred EOTF; unknown gamut preserved");
}
static void authored_signature(bool emit)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    AVDOVIDmData *a=av_dovi_get_ext(m,0),*b=av_dovi_get_ext(m,1);
    /* Literal packed primary/midtone/clipping words and non-neutral secondary controls. */
    const uint8_t raw[]={20,0x90,0x08,0x00,0x76,0xc8,0xfc,0x83,0x48,0x00,0x8f,0xc8,0x00,
        140,128,120,135,125,128,130,128,126,129,127,128};
    *a=(AVDOVIDmData){.level=8,.l8={.target_display_index=20,.trim_slope=2304,
        .trim_offset=2048,.trim_power=1900,.trim_chroma_weight=2300,.trim_saturation_gain=2100,
        .ms_weight=2048,.target_mid_contrast=2300,.clip_trim=2048,
        .saturation_vector_field={140,128,120,135,125,128},.hue_vector_field={130,128,126,129,127,128}},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=25};
    memcpy(a->dvbridge_original_bytes,raw,sizeof(raw));*b=l10();
    av_dovi_get_color(m)->source_max_pq=3079;
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .enhancement=DVBRIDGE_ENHANCEMENT_SIGNATURE,
        .tv={1000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    void *before=av_memdup(m,bytes),*edited=NULL;size_t edited_bytes=0;
    struct dvbridge_creative_plan p;struct dvbridge_creative_edit_report report;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)!=DVBRIDGE_CREATIVE_INVALID);
    assert(p.cm4_lower.target.transfer==PL_COLOR_TRC_UNKNOWN);
    assert(dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report)==DVBRIDGE_CREATIVE_READY);
    assert(edited_bytes==bytes && report.reason==DVBRIDGE_CREATIVE_OK && !memcmp(m,before,bytes));
    const AVDOVIDmData *e=av_dovi_get_ext(edited,0);
    assert(report.l8_coverage.edited && !(report.l8_coverage.edited&~31u));
    assert(!memcmp(b,av_dovi_get_ext(edited,1),sizeof(*b)));
    assert((a->dvbridge_original_bytes[8]&15)==(e->dvbridge_original_bytes[8]&15));
    assert(!memcmp(a->dvbridge_original_bytes+9,e->dvbridge_original_bytes+9,23));
    AVDOVIDmData restored=*e;
    restored.l8.trim_slope=a->l8.trim_slope;restored.l8.trim_offset=a->l8.trim_offset;
    restored.l8.trim_power=a->l8.trim_power;restored.l8.trim_chroma_weight=a->l8.trim_chroma_weight;
    restored.l8.trim_saturation_gain=a->l8.trim_saturation_gain;
    memcpy(restored.dvbridge_original_bytes,a->dvbridge_original_bytes,sizeof(restored.dvbridge_original_bytes));
    assert(!memcmp(a,&restored,sizeof(*a)));
    if(emit){
        printf("{\"primary\":[%u,%u,%u,%u,%u,%u],\"samples\":[",
            e->l8.trim_slope,e->l8.trim_offset,e->l8.trim_power,e->l8.trim_chroma_weight,
            e->l8.trim_saturation_gain,e->l8.ms_weight);
        policy.mode=DVBRIDGE_MODE_HDR10_EXPERT;policy.tv.peak_nits=fit_nits(3079.0/4095);
        assert(dvbridge_creative_resolve(&p,edited,edited_bytes,&policy)!=DVBRIDGE_CREATIVE_INVALID);
        assert(p.cm4_lower.target.transfer==PL_COLOR_TRC_UNKNOWN);
        for(unsigned i=0;i<33;i++){
            double v=fit_nits(i/32.0*3079/4095),out[3];
            assert(dvbridge_creative_cm4_trim_rgb(&p,(double[3]){v,v,v},out));
            printf("%s{\"rgb\":[%.17g,%.17g,%.17g],\"out\":[%.17g,%.17g,%.17g]}",
                i?",":"",v,v,v,out[0],out[1],out[2]);
        }
        static const double colours[][3]={{10,1,0},{100,50,25},{1,10,100},{1000,0,0},{0,1000,1000}};
        for(unsigned i=0;i<5;i++){
            double out[3];assert(dvbridge_creative_cm4_trim_rgb(&p,colours[i],out));
            printf(",{\"rgb\":[%.17g,%.17g,%.17g],\"out\":[%.17g,%.17g,%.17g]}",
                colours[i][0],colours[i][1],colours[i][2],out[0],out[1],out[2]);
        }
        puts("]}");
    }else puts("PASS changed Signature with authored primary/optional controls and custom UNKNOWN target");
    av_free(before);av_free(edited);av_free(m);
}
static void fit_contract(bool emit)
{
    const unsigned peaks[]={500,800,1000,1500,2000};
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=1;
    AVDOVIDmData *a=av_dovi_get_ext(m,0);*a=l8(10);
    a->l8.target_display_index=a->dvbridge_original_bytes[0]=49;
    av_dovi_get_color(m)->source_max_pq=3079;
    if(emit)printf("{\"cases\":[");
    for(unsigned preset=0;preset<2;preset++)for(unsigned j=0;j<5;j++){
        struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
            .enhancement=preset,.tv={peaks[j],DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
        struct dvbridge_creative_plan p;void *edited=NULL;size_t edited_bytes=0;
        assert(dvbridge_creative_resolve(&p,m,bytes,&policy)!=DVBRIDGE_CREATIVE_INVALID);
        struct dvbridge_creative_edit_report report;
        enum dvbridge_creative_status status=dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report);
        fprintf(stderr,"fit preset=%u peak=%u status=%u evaluations=%u pq=%.9g chroma=%.9g hue=%.9g ns=%llu\n",
            preset,peaks[j],status,report.candidate_evaluations,report.maximum_pq_error,
            report.maximum_relative_chroma_error,report.maximum_hue_error,(unsigned long long)report.fit_ns);
        assert(edited && edited_bytes==bytes);
        if(emit){
            AVDOVIDmData *e=av_dovi_get_ext(edited,0);
            printf("%s{\"preset\":%u,\"peak\":%u,\"status\":%u,\"master_q\":3079,\"scene\":1,\"words\":[%u,%u,%u,%u,%u]}",
                preset || j?",":"",preset,peaks[j],status,e->l8.trim_slope,e->l8.trim_offset,
                e->l8.trim_power,e->l8.trim_chroma_weight,e->l8.trim_saturation_gain);
        }
        assert(status==DVBRIDGE_CREATIVE_NEUTRAL || status==DVBRIDGE_CREATIVE_READY);
        if(!preset && j<=2)
            assert(report.candidate_evaluations<=3 && "Natural identity must have bounded validation-only work");
        if(preset)
            assert(report.candidate_evaluations<=4 && "A valid edited seed must not run the trim search");
        {
            policy.mode=DVBRIDGE_MODE_HDR10_EXPERT;policy.tv.peak_nits=fit_nits(3079.0/4095);
            struct dvbridge_creative_plan q;dvbridge_creative_resolve(&q,edited,bytes,&policy);
            double reference=floor(fit_pq(fmax(1000,peaks[j]))*4095+.5);
            double headroom=fmax(-.5,fmin(.5,(reference-3079)/3079));
            for(unsigned k=0;k<=32;k++){
                double u=k/32.0,value=fit_nits(u*3079/4095),out[3];
                assert(dvbridge_creative_cm4_trim_rgb(&q,(double[3]){value,value,value},out));
                double peak=fit_nits(3079.0/4095),x=value/peak,gate=fmin(1,value);
                gate=gate*gate*(3-2*gate);
                double high=fmax(0,fmin(1,(x-.25)/.75));high=high*high*(3-2*high);
                double wanted=value+gate*(preset?.02:.04*fmax(0,headroom)*high)*value*(1-x);
                assert(fabs(fit_pq(out[0])-fit_pq(wanted))<=2.0/1024);
            }
        }
        av_free(edited);
    }
    /* At the source peak Natural is representable as an exact identity. */
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={fit_nits(3079.0/4095),DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    struct dvbridge_creative_plan p;void *edited=NULL;size_t edited_bytes=0;
    dvbridge_creative_resolve(&p,m,bytes,&policy);
    assert(dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,NULL)==DVBRIDGE_CREATIVE_NEUTRAL);
    assert(!memcmp(m,edited,bytes));av_free(edited);
    /* Optional bytes and presence survive accepted edits and rejected fits. */
    const unsigned lengths[]={10,12,13,19,25};
    for(unsigned k=0;k<5;k++){
        *a=l8(lengths[k]);a->l8.target_display_index=a->dvbridge_original_bytes[0]=49;
        void *before=av_memdup(m,bytes);struct dvbridge_creative_edit_report report;
        dvbridge_creative_resolve(&p,m,bytes,&policy);
        enum dvbridge_creative_status status=dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report);
        assert(status!=DVBRIDGE_CREATIVE_INVALID && edited_bytes==bytes);
        const AVDOVIDmData *e=av_dovi_get_ext(edited,0);
        assert(e->dvbridge_original_length==lengths[k]);
        assert((a->dvbridge_original_bytes[8]&15)==(e->dvbridge_original_bytes[8]&15));
        assert(!memcmp(a->dvbridge_original_bytes+9,e->dvbridge_original_bytes+9,23));
        assert(a->l8.ms_weight==e->l8.ms_weight && a->l8.target_mid_contrast==e->l8.target_mid_contrast && a->l8.clip_trim==e->l8.clip_trim);
        assert(!memcmp(a->l8.saturation_vector_field,e->l8.saturation_vector_field,6));
        assert(!memcmp(a->l8.hue_vector_field,e->l8.hue_vector_field,6));
        assert(!memcmp(m,before,bytes));av_free(before);av_free(edited);
    }
    /* A zero-maximum scene is an identity for both presets, without a fitted pass. */
    m->num_ext_blocks=2;*a=l8(10);a->l8.target_display_index=a->dvbridge_original_bytes[0]=49;
    AVDOVIDmData *stats=av_dovi_get_ext(m,1);*stats=(AVDOVIDmData){.level=1};
    policy.enhancement=DVBRIDGE_ENHANCEMENT_SIGNATURE;
    dvbridge_creative_resolve(&p,m,bytes,&policy);struct dvbridge_creative_edit_report report;
    assert(dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report)==DVBRIDGE_CREATIVE_NEUTRAL);
    assert(!report.candidate_evaluations && !memcmp(edited,m,bytes));av_free(edited);
    /* Both existing families are preserved for a non-PQ preset target. */
    *stats=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3000,.trim_slope=2048,.trim_offset=2048,
        .trim_power=2048,.trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=-1}};
    policy.tv.peak_nits=500;
    a->l8.target_display_index=a->dvbridge_original_bytes[0]=1;
    dvbridge_creative_resolve(&p,m,bytes,&policy);
    assert(dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(!memcmp(edited,m,bytes) && !report.l2_coverage.edited && !report.l8_coverage.edited);
    assert(report.l2_coverage.present==31 && report.l8_coverage.present==63);av_free(edited);
    /* Effective L1/L3 is consumed once; neither source block is rewritten. */
    a->l8.target_display_index=a->dvbridge_original_bytes[0]=49;
    m->num_ext_blocks=3;*stats=(AVDOVIDmData){.level=1,.l1={.min_pq=0,.max_pq=3000,.avg_pq=1500}};
    AVDOVIDmData *offset=av_dovi_get_ext(m,2);
    *offset=(AVDOVIDmData){.level=3,.l3={2048,2068,2078},.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=5,.dvbridge_original_bytes={0x80,0x08,0x14,0x81,0xe0}};
    policy.enhancement=DVBRIDGE_ENHANCEMENT_NATURAL;policy.tv.peak_nits=1000;
    dvbridge_creative_resolve(&p,m,bytes,&policy);
    assert(p.analysis[1]==3020 && p.analysis[2]==1530);
    dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report);
    assert(!memcmp(av_dovi_get_ext(edited,1),stats,sizeof(*stats)));
    assert(!memcmp(av_dovi_get_ext(edited,2),offset,sizeof(*offset)));
    void *with_offsets=edited;
    m->num_ext_blocks=2;stats->l1.max_pq=3020;stats->l1.avg_pq=1530;
    dvbridge_creative_resolve(&p,m,bytes,&policy);
    dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report);
    assert(!memcmp(av_dovi_get_ext(edited,0),av_dovi_get_ext(with_offsets,0),sizeof(*a)));
    av_free(with_offsets);av_free(edited);
    /* Present authored black lift and clipped intervals survive an accepted identity. */
    m->num_ext_blocks=1;*a=l8(10);a->l8.target_display_index=a->dvbridge_original_bytes[0]=49;
    a->l8.trim_slope=3072;a->l8.trim_offset=2100;
    a->dvbridge_original_bytes[1]=0xc0;a->dvbridge_original_bytes[2]=0x08;a->dvbridge_original_bytes[3]=0x34;
    policy.tv.peak_nits=fit_nits(3079.0/4095);
    dvbridge_creative_resolve(&p,m,bytes,&policy);
    assert(dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report)==DVBRIDGE_CREATIVE_NEUTRAL);
    assert(!memcmp(edited,m,bytes));av_free(edited);
    av_free(m);
    if(emit)puts("]}");else puts("PASS quantized Enhanced objective, raw words, optional presence, identity and coherent rejection");
}

static void protected_authored(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=1;
    av_dovi_get_color(m)->source_max_pq=3079;
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .enhancement=DVBRIDGE_ENHANCEMENT_SIGNATURE,
        .tv={1500,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    for(unsigned cm4=0;cm4<2;cm4++){
        AVDOVIDmData *a=av_dovi_get_ext(m,0);
        if(cm4){
            *a=l8(10);a->l8.target_display_index=a->dvbridge_original_bytes[0]=49;
            a->l8.trim_slope=3072;a->l8.trim_offset=2049;
            a->dvbridge_original_bytes[1]=0xc0;a->dvbridge_original_bytes[2]=0x08;
            a->dvbridge_original_bytes[3]=0x01;
        }else *a=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,.trim_slope=3072,
            .trim_offset=2049,.trim_power=2048,.trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=-1}};
        void *before=av_memdup(m,bytes),*edited=NULL;size_t count=0;
        struct dvbridge_creative_plan p;struct dvbridge_creative_edit_report report;
        dvbridge_creative_resolve(&p,m,bytes,&policy);
        enum dvbridge_creative_status status=dvbridge_creative_edit(&edited,&count,m,bytes,&p,&report);
        fprintf(stderr,"protected authored cm4=%u status=%u reason=%u\n",cm4,status,report.reason);
        assert(!memcmp(before,m,bytes) && count==bytes);
        assert(status==DVBRIDGE_CREATIVE_READY || status==DVBRIDGE_CREATIVE_UNSUPPORTED);
        if(status==DVBRIDGE_CREATIVE_UNSUPPORTED){
            assert(report.reason==DVBRIDGE_CREATIVE_EDIT_NOT_REPRESENTABLE);
            assert(!memcmp(edited,m,bytes));
        }else{
            struct dvbridge_policy expert=policy;expert.mode=DVBRIDGE_MODE_HDR10_EXPERT;
            expert.tv.peak_nits=fit_nits(3079.0/4095);
            struct dvbridge_creative_plan source,result;
            dvbridge_creative_resolve(&source,m,bytes,&expert);
            dvbridge_creative_resolve(&result,edited,count,&expert);
            double prior_source=0,prior_result=0;
            for(unsigned i=0;i<=256;i++){
                double value=fit_nits((3079.0/4095)*i/256),input[3]={value,value,value},a0[3],a1[3];
                assert(cm4?dvbridge_creative_cm4_trim_rgb(&source,input,a0):dvbridge_creative_trim_rgb(&source,input,a0));
                assert(cm4?dvbridge_creative_cm4_trim_rgb(&result,input,a1):dvbridge_creative_trim_rgb(&result,input,a1));
                double q0=fit_pq(a0[0]),q1=fit_pq(a1[0]);
                if(!i)assert(a0[0]>0 && fabs(q1-q0)<=2e-5);
                if(value<=1)assert(fabs(q1-q0)<=2.0/1024);
                if(i && fabs(q0-prior_source)<=1e-12)assert(fabs(q1-prior_result)<=2e-5);
                if(i && q0-prior_source>2e-5)assert(q1>prior_result);
                prior_source=q0;prior_result=q1;
            }
        }
        av_free(before);av_free(edited);
    }
    AVDOVIDmData *a=av_dovi_get_ext(m,0);
    *a=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,.trim_slope=2048,.trim_offset=2048,
        .trim_power=2048,.trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=-1}};
    struct dvbridge_creative_plan p;struct dvbridge_creative_edit_report report;
    void *edited=NULL;size_t count=0;dvbridge_creative_resolve(&p,m,bytes,&policy);
    assert(dvbridge_creative_edit(&edited,&count,m,bytes,&p,&report)==DVBRIDGE_CREATIVE_READY);
    assert(report.l2_coverage.edited);av_free(edited);
    m->num_ext_blocks=2;*av_dovi_get_ext(m,1)=*a;
    AVDOVIDmData *second=av_dovi_get_ext(m,1);
    second->l2.target_max_pq=3200;second->l2.trim_slope=3072;second->l2.trim_offset=2100;
    dvbridge_creative_resolve(&p,m,bytes,&policy);
    enum dvbridge_creative_status status=dvbridge_creative_edit(&edited,&count,m,bytes,&p,&report);
    assert(status==DVBRIDGE_CREATIVE_READY || status==DVBRIDGE_CREATIVE_UNSUPPORTED);
    if(status==DVBRIDGE_CREATIVE_UNSUPPORTED){
        assert(report.reason==DVBRIDGE_CREATIVE_EDIT_NOT_REPRESENTABLE);
        assert(!report.l2_coverage.edited && !report.l8_coverage.edited && !memcmp(edited,m,bytes));
    }else{
        assert(report.l2_coverage.edited && !report.l8_coverage.edited);
        struct dvbridge_policy expert=policy;expert.mode=DVBRIDGE_MODE_HDR10_EXPERT;
        for(unsigned anchor=0;anchor<2;anchor++){
            expert.tv.peak_nits=fit_nits(av_dovi_get_ext(m,anchor)->l2.target_max_pq/4095.0);
            struct dvbridge_creative_plan source,result;
            dvbridge_creative_resolve(&source,m,bytes,&expert);
            dvbridge_creative_resolve(&result,edited,count,&expert);
            double last=0;
            for(unsigned i=0;i<=256;i++){
                double value=expert.tv.peak_nits*i/256,input[3]={value,value,value},a0[3],a1[3];
                assert(dvbridge_creative_trim_rgb(&source,input,a0));
                assert(dvbridge_creative_trim_rgb(&result,input,a1));
                double q0=fit_pq(a0[0]),q1=fit_pq(a1[0]);
                if(!i)assert(fabs(q1-q0)<=2e-5);
                if(value<=1)assert(fabs(q1-q0)<=2.0/1024);
                assert(q1>=last-1e-12);last=q1;
            }
        }
    }
    av_free(edited);av_free(m);
}

static void enhanced_intent(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=1;
    av_dovi_get_color(m)->source_max_pq=3079;
    for(unsigned cm4=0;cm4<2;cm4++)for(unsigned preset=0;preset<2;preset++){
        AVDOVIDmData *a=av_dovi_get_ext(m,0);
        if(cm4){*a=l8(10);a->l8.target_display_index=a->dvbridge_original_bytes[0]=49;}
        else *a=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
            .trim_slope=2048,.trim_offset=2048,.trim_power=2048,
            .trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=-1}};
        struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
            .enhancement=preset,.tv={1500,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
        void *before=av_memdup(m,bytes),*edited=NULL;size_t edited_bytes=0;
        struct dvbridge_creative_plan p;struct dvbridge_creative_edit_report report;
        assert(dvbridge_creative_resolve(&p,m,bytes,&policy)!=DVBRIDGE_CREATIVE_INVALID);
        enum dvbridge_creative_status status=dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,&report);
        fprintf(stderr,"intent cm4=%u preset=%u status=%u reason=%u pq=%g chroma=%g hue=%g\n",
            cm4,preset,status,report.reason,report.maximum_pq_error,report.maximum_relative_chroma_error,report.maximum_hue_error);
        assert(status==DVBRIDGE_CREATIVE_READY || (!preset && status==DVBRIDGE_CREATIVE_NEUTRAL));
        assert(!memcmp(before,m,bytes) && edited_bytes==bytes);
        policy.mode=DVBRIDGE_MODE_HDR10_EXPERT;policy.tv.peak_nits=fit_nits(3079.0/4095);
        struct dvbridge_creative_plan source,result;
        dvbridge_creative_resolve(&source,m,bytes,&policy);
        dvbridge_creative_resolve(&result,edited,edited_bytes,&policy);
        const double levels[]={0,.001,.01,.1,1,10,100,250,500,750,1000};
        double last=0;
        for(unsigned i=0;i<sizeof(levels)/sizeof(levels[0]);i++){
            double input[3]={levels[i],levels[i],levels[i]},original[3],out[3];
            assert(cm4?dvbridge_creative_cm4_trim_rgb(&source,input,original):dvbridge_creative_trim_rgb(&source,input,original));
            assert(cm4?dvbridge_creative_cm4_trim_rgb(&result,input,out):dvbridge_creative_trim_rgb(&result,input,out));
            if(i==0)assert(out[0]==original[0]);
            assert(out[0]>=last-1e-10);last=out[0];
            if(levels[i]==100){
                if(preset)assert(out[0]>original[0] && "Signature must not darken authored midtones");
                else assert(fabs(fit_pq(out[0])-fit_pq(original[0]))<=2.0/1024);
            }
        }
        av_free(before);av_free(edited);
    }
    av_free(m);puts("PASS authored CM2.9/CM4 preset intent, black and monotonicity");
}

static void native_profiles(void)
{
    const unsigned peaks[]={500,800,1000,1500,2000};
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=1;
    AVDOVIDmData *a=av_dovi_get_ext(m,0);*a=l8(10);
    a->l8.target_display_index=a->dvbridge_original_bytes[0]=49;
    av_dovi_get_color(m)->source_max_pq=3079;
    for(unsigned preset=0;preset<2;preset++)for(unsigned j=0;j<5;j++){
        struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
            .enhancement=preset,.tv={peaks[j],DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
        struct dvbridge_creative_plan p;void *edited=NULL;size_t edited_bytes=0;
        assert(dvbridge_creative_resolve(&p,m,bytes,&policy)!=DVBRIDGE_CREATIVE_INVALID);
        enum dvbridge_creative_status want=preset || j>2?DVBRIDGE_CREATIVE_READY:DVBRIDGE_CREATIVE_NEUTRAL;
        assert(dvbridge_creative_edit(&edited,&edited_bytes,m,bytes,&p,NULL)==want);
        assert(p.policy.tv.peak_nits==peaks[j] && !memcmp(&policy,&p.policy,sizeof(policy)));
        const AVDOVIDmData *e=av_dovi_get_ext(edited,0);
        const unsigned words[]={e->l8.trim_slope,e->l8.trim_offset,e->l8.trim_power,
            e->l8.trim_chroma_weight,e->l8.trim_saturation_gain};
        for(unsigned i=0;i<5;i++)assert(words[i]>=1536 && words[i]<=2560);
        assert(e->l8.trim_offset==2048 && e->l8.ms_weight==2048);
        assert(edited_bytes==bytes && a->l8.trim_power==2048);
        av_free(edited);
    }
    av_free(m);puts("PASS native Natural/Signature coverage, reference floor and unchanged TV capacity");
}

int main(int argc,char **argv)
{
    if(argc==2 && !strcmp(argv[1],"--intent")){enhanced_intent();return 0;}
    if(argc==2 && !strcmp(argv[1],"--authored-json")){authored_signature(true);return 0;}
    if(argc==2 && !strcmp(argv[1],"--native-profiles")){native_profiles();return 0;}
    if(argc==2 && !strcmp(argv[1],"--custom-target")){custom_target_edit();return 0;}
    if(argc==2 && (!strcmp(argv[1],"--fit") || !strcmp(argv[1],"--fit-json"))){
        if(!strcmp(argv[1],"--fit")){enhanced_intent();protected_authored();}
        fit_contract(!strcmp(argv[1],"--fit-json"));return 0;}
    scalar_contract(argc==2 && !strcmp(argv[1],"--scalar"));
    if(argc==2)return 0;
    custom_target_edit();
    authored_signature(false);
    native_profiles();
    size_t bytes; AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    AVDOVIDmData *a=av_dovi_get_ext(m,0),*b=av_dovi_get_ext(m,1);
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={1000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    struct dvbridge_creative_plan p;
    *a=l8(10);*b=l10();
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);

    a->l8.trim_power++;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    *a=l8(12);a->l8.target_mid_contrast=1;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    *a=l8(13);a->l8.clip_trim=1;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    *a=l8(19);a->l8.saturation_vector_field[5]=1;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    *a=l8(25);a->l8.hue_vector_field[0]=1;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    *a=l8(10);b->l10.target_max_pq++;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    *b=l8(10);
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    *a=l10();*b=l10();
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    *a=l8(10);*b=l10();b->l10.target_min_pq=4095;
    b->dvbridge_original_bytes[2]=0x7f;b->dvbridge_original_bytes[3]=0xff;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    *b=l10();b->l10.target_display_index=b->dvbridge_original_bytes[0]=49;
    a->l8.target_display_index=a->dvbridge_original_bytes[0]=49;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    snapshots(m,bytes,&policy);
    target_order(m,bytes);
    av_free(m);puts("PASS CM4 parsed/raw equality, presence, target snapshots and preserved edits");
}
