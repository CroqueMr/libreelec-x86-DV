/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_placebo.h"
#include "dvbridge_creative.h"
#include "reference_test.h"
#include <stdio.h>
#include <string.h>
#include <math.h>

static struct dvbridge_policy policy(void)
{
    return (struct dvbridge_policy){.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={1000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
}

static AVDOVIDmData trim(unsigned target)
{
    return (AVDOVIDmData){.level=8,.l8={.target_display_index=target,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,
        .trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=2048},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=10,
        .dvbridge_original_bytes={target,0x80,0x08,0x00,0x80,0x08,0x00,0x80,0x08,0x00}};
}

static void statistics(const char *mode)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    av_dovi_get_color(m)->source_max_pq=3079;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,3000,1500}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=6,.l6={.max_luminance=1000}};
    if(!strcmp(mode,"missing"))av_dovi_get_ext(m,0)->level=0;
    if(!strcmp(mode,"invalid"))av_dovi_get_ext(m,0)->l1.min_pq=2000;
    if(!strcmp(mode,"zero"))memset(&av_dovi_get_ext(m,0)->l1,0,sizeof(av_dovi_get_ext(m,0)->l1));
    if(!strcmp(mode,"l3")){
        m->num_ext_blocks=3;
        *av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=3,.l3={2048,4095,2048},
            .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
            .dvbridge_original_bytes={0x80,0x0f,0xff,0x80,0x00}};
    }
    void *copy=av_memdup(m,bytes);assert(copy);
    struct dvbridge_policy p=policy();struct dvbridge_color colour;
    struct pl_color_space target;struct dvbridge_hdr10_metadata signal;
    assert(dvbridge_reference_map(&colour,&target,&signal,&p,m,bytes,false));
    assert(target.hdr.max_luma==1000 && target.primaries==PL_COLOR_PRIM_BT_2020);
    assert(colour.color.hdr.max_luma==1000 && !colour.color.hdr.max_pq_y && !colour.color.hdr.avg_pq_y);
    struct dvbridge_creative_plan plan;
    assert(dvbridge_creative_resolve(&plan,m,bytes,&p)!=DVBRIDGE_CREATIVE_INVALID);
    assert(!plan.l1_present && !(plan.applied_levels&((1u<<1)|(1u<<3))));
    /* Recovery must not retain static descriptors or another scene's analysis. */
    m->num_ext_blocks=2;*av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,3000,1500}};
    assert(dvbridge_reference_map(&colour,&target,&signal,&p,m,bytes,false));
    assert(fabs(colour.color.hdr.max_pq_y-3000/4095.0)<1e-7);
    memcpy(m,copy,bytes);
    /* Existing non-Expert admission stays strict. */
    p.mode=DVBRIDGE_MODE_ENHANCED_DV;
    assert(dvbridge_reference_map(&colour,&target,&signal,&p,m,bytes,false)==!strcmp(mode,"l3"));
    if(!strcmp(mode,"l3"))assert(dvbridge_creative_resolve(&plan,m,bytes,&p)==DVBRIDGE_CREATIVE_INVALID);
    assert(!memcmp(m,copy,bytes));
    av_free(copy);av_free(m);
}

static void targets(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=trim(49);
    struct dvbridge_policy p=policy();struct dvbridge_creative_plan a,b;
    struct dvbridge_cm4_coefficients before,after;
    assert(dvbridge_creative_resolve(&a,m,bytes,&p)!=DVBRIDGE_CREATIVE_INVALID);
    assert(dvbridge_creative_cm4_coefficients(&before,&a));
    m->num_ext_blocks=2;*av_dovi_get_ext(m,1)=trim(250);
    void *copy=av_memdup(m,bytes);assert(copy);
    for(int swap=0;swap<2;swap++){
        assert(dvbridge_creative_resolve(&b,m,bytes,&p)!=DVBRIDGE_CREATIVE_INVALID);
        assert(dvbridge_creative_cm4_coefficients(&after,&b));
        assert(!memcmp(&before,&after,sizeof(before)));
        p.mode=DVBRIDGE_MODE_ENHANCED_DV;
        assert(dvbridge_creative_resolve(&b,m,bytes,&p)==DVBRIDGE_CREATIVE_UNSUPPORTED);
        assert(b.cm4_targets==DVBRIDGE_CM4_UNKNOWN_TARGET && !b.cm4_lower.present);
        p.mode=DVBRIDGE_MODE_HDR10_EXPERT;
        AVDOVIDmData tmp=*av_dovi_get_ext(m,0);
        *av_dovi_get_ext(m,0)=*av_dovi_get_ext(m,1);*av_dovi_get_ext(m,1)=tmp;
    }
    assert(!memcmp(copy,m,bytes));
    /* Contradictory duplicate targets still fail, even if one is unknown. */
    *av_dovi_get_ext(m,1)=trim(49);
    assert(dvbridge_creative_resolve(&b,m,bytes,&p)==DVBRIDGE_CREATIVE_INVALID);
    av_free(copy);av_free(m);
}

static void domain(void)
{
    struct dvbridge_policy p=policy();struct dvbridge_creative_plan plan={
        .status=DVBRIDGE_CREATIVE_READY,.cm4=true,.cm4_targets=DVBRIDGE_CM4_TARGETS_RESOLVED,.policy=p};
    plan.cm4_output=(struct dvbridge_cm4_target){.transfer=PL_COLOR_TRC_PQ,
        .primaries=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020)};
    plan.cm4_lower.present=true;plan.cm4_lower.target=plan.cm4_output;
    plan.cm4_lower.controls=(struct dvbridge_cm4_controls){.present_fields=31,
        .primary={2048,2048,2048,2048,2048,2048},.mid_contrast=2048,.clip_trim=2048,
        .saturation={255,0,128,180,64,128},.hue={0,255,128,200,128,64}};
    struct dvbridge_cm4_coefficients expert,other;
    assert(dvbridge_creative_cm4_coefficients(&expert,&plan));
    assert(expert.present==1023); /* Presence is not execution. */
    for(int i=0;i<6;i++)assert(expert.secondary_gain[i]==1 && expert.secondary_rotation[i]==0);
    plan.policy.mode=DVBRIDGE_MODE_ENHANCED_DV;
    assert(dvbridge_creative_cm4_coefficients(&other,&plan));
    assert(other.secondary_gain[0]!=1 && other.secondary_rotation[0]!=0);
    const double input[]={50,200,700};double output[3];
    assert(dvbridge_creative_cm4_apply(&expert,input,output));
    assert(!memcmp(input,output,sizeof(input)));
}

static void images(void)
{
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    float input[8*8*4],reference[8*8*4],actual[8*8*4];
    for(int i=0;i<64;i++){
        for(int c=0;c<3;c++)input[4*i+c]=i%8?(.1f+.07f*(i%8)+.02f*c):0;
        input[4*i+3]=1;
    }
    pl_tex texture=reference_texture(gpu,8,8,input);
    struct pl_frame frame=reference_frame(texture,8,8);
    struct dvbridge_policy p=policy();struct dvbridge_identity id={1,1,1};
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=3;
    av_dovi_get_color(m)->source_max_pq=3696;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=0};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=6,.l6={.max_luminance=4000}};
    *av_dovi_get_ext(m,2)=trim(49);
    av_dovi_get_ext(m,2)->l8.trim_power=2304;
    av_dovi_get_ext(m,2)->dvbridge_original_bytes[4]=0x90;
    void *saved=av_memdup(m,bytes);assert(saved);
    assert(dvbridge_render_hdr10_policy_rgb(r,&p,&id,&frame,m,bytes,0,0,
        (struct dvbridge_geometry){8,8,0,0,8,8}));
    reference_read(gpu,dvbridge_render_texture(r),0,0,8,8,reference);
    assert(dvbridge_render_policy_output(r)->creative.reason==DVBRIDGE_CREATIVE_STATIC_MISSING_L1);
    for(int variant=0;variant<4;variant++){
        memcpy(m,saved,bytes);++id.picture;
        if(variant==0)*av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={2000,3000,1500}};
        if(variant==1){
            m->num_ext_blocks=4;*av_dovi_get_ext(m,3)=trim(250);
        }
        if(variant==2){
            /* A valid dynamic scene between two static ones must not leak. */
            *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,3000,1500}};
            assert(dvbridge_render_hdr10_policy_rgb(r,&p,&id,&frame,m,bytes,0,0,
                (struct dvbridge_geometry){8,8,0,0,8,8}));
            memcpy(m,saved,bytes);++id.picture;
        }
        if(variant==3){
            m->num_ext_blocks=4;
            *av_dovi_get_ext(m,3)=(AVDOVIDmData){.level=3,.l3={2048,2048,2048},
                .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
                .dvbridge_original_bytes={0x80,0x08,0x00,0x80,0x00}};
        }
        void *copy=av_memdup(m,bytes);assert(copy);
        assert(dvbridge_render_hdr10_policy_rgb(r,&p,&id,&frame,m,bytes,0,0,
            (struct dvbridge_geometry){8,8,0,0,8,8}));
        reference_read(gpu,dvbridge_render_texture(r),0,0,8,8,actual);
        assert(!memcmp(reference,actual,sizeof(reference)) && !memcmp(copy,m,bytes));
        av_free(copy);
    }
    for(int i=0;i<64;i++)for(int c=0;c<3;c++){
        assert(isfinite(actual[4*i+c]) && actual[4*i+c]>=0 && actual[4*i+c]<=1);
        if(i%8==0)assert(actual[4*i+c]==0);
    }
    dvbridge_renderer_destroy(r);pl_tex_destroy(gpu,&texture);reference_gpu_destroy(&g);
    av_free(saved);av_free(m);
}

int main(int argc,char **argv)
{
    assert(argc==2);
    if(!strcmp(argv[1],"targets"))targets();
    else if(!strcmp(argv[1],"domain"))domain();
    else if(!strcmp(argv[1],"images"))images();
    else statistics(argv[1]);
    printf("PASS Expert robustness %s\n",argv[1]);
}
