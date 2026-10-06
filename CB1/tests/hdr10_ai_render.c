/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "reference_test.h"
#include "cb1_hdr10_ai.h"
#include <libavutil/dovi_meta.h>
#include <time.h>
#ifndef CB1_HDR10_AI_RENDER_API
extern pl_tex dvbridge_render_hdr10_ai_rgb(struct dvbridge_renderer *,
    const struct dvbridge_policy *,const struct cb1_ai_result *,const struct pl_frame *,
    const struct dvbridge_geometry *) __attribute__((weak));
#endif
static void retire(struct dvbridge_renderer *r)
{
    dvbridge_render_dv_policy_cancel(r);
    for(unsigned i=0;i<10000;++i){
        if(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE)return;
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"Output retirement timed out");
}
static void wire(const struct dvbridge_candidate *candidate)
{
    unsigned count;const uint32_t *packet=dvbridge_packets(candidate,&count);
    assert(packet && count==1 && packet[3]==0 && packet[4]==106 && packet[75]==3);
    const unsigned l1[]={0,0,0,6,1,0,37,12,56,5,132};
    const unsigned l5[]={0,0,0,8,5,0,0,0,0,0,120,0,120};
    const unsigned l3[]={0,0,0,6,3,8,0,8,23,8,2};
    for(unsigned i=0;i<11;++i)assert(packet[76+i]==l1[i]);
    for(unsigned i=0;i<13;++i)assert(packet[87+i]==l5[i]);
    for(unsigned i=0;i<11;++i)assert(packet[100+i]==l3[i]);
    uint32_t crc=0xffffffff;
    for(unsigned i=0;i<128;++i){
        assert(packet[i]<=255);crc^=packet[i]<<24;
        for(unsigned bit=0;bit<8;++bit)crc=crc&0x80000000?(crc<<1)^0x04c11db7:crc<<1;
    }
    assert(!crc);
}
int main(void)
{
    assert(dvbridge_render_hdr10_ai_rgb);
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu.gl->gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    float pixels[8*4*4];for(unsigned i=0;i<8*4;++i){
        pixels[4*i]=.375f;pixels[4*i+1]=.5f;pixels[4*i+2]=.625f;pixels[4*i+3]=1;
    }
    pl_tex tex=reference_texture(gpu.gl->gpu,8,4,pixels);
    struct pl_frame source=reference_frame(tex,8,4);
    source.repr=pl_color_repr_rgb;source.color=(struct pl_color_space){
        .primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ};
    const struct dvbridge_geometry geometry={8,4,0,120,3840,1920};
    struct cb1_ai_result prediction={.id={3,4,7},.pts=0,
        .raw={.l1_min=37,.l1_max=3128,.l1_avg=1412,.l3_min=2048,.l3_max=2071,.l3_avg=2050}};
    struct dvbridge_policy policy={.revision=7,.mode=DVBRIDGE_MODE_STANDARD};
    pl_tex result=dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry);assert(result);
    float sample[4];reference_read(gpu.gl->gpu,result,1200,900,1,1,sample);
    for(unsigned c=0;c<3;++c)assert(fabsf(sample[c]-pixels[c])<=2e-6f);
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.identity.stream==3 && out->value.identity.picture==4 && out->value.identity.revision==7);
    assert(!out->value.resolved && !out->value.fel_reconstructed);
    const AVDOVIMetadata *m=out->output_metadata;
    const AVDOVIDmData *l1=av_dovi_find_level(m,1),*l3=av_dovi_find_level(m,3),*l5=av_dovi_find_level(m,5);
    assert(l1 && l3 && l5 && l1->l1.min_pq==37 && l1->l1.max_pq==3128 && l1->l1.avg_pq==1412);
    uint64_t bits=0;for(unsigned i=0;i<5;++i)bits=bits<<8|l3->dvbridge_original_bytes[i];
    assert((bits>>28&4095)==2048 && (bits>>16&4095)==2071 && (bits>>4&4095)==2050);
    assert(l5->l5.top_offset==120 && l5->l5.bottom_offset==120);
    wire(out->candidate);
    struct dvbridge_dv_policy_snapshot committed;
    assert(!dvbridge_render_dv_policy_committed(r,&committed));
    pl_fmt transport_format=pl_find_fmt(gpu.gl->gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE);
    assert(transport_format);
    pl_tex transport=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=transport_format,
        .renderable=true,.sampleable=true));assert(transport);
    unsigned framebuffer;assert(pl_opengl_unwrap(gpu.gl->gpu,transport,NULL,NULL,&framebuffer));
    assert(dvbridge_render_dv_policy_resolve(r,transport,framebuffer,false));
    out=dvbridge_render_dv_policy_output(r);assert(out);
    struct dvbridge_identity identity={3,4,7},wrong={3,5,7};
    assert(!dvbridge_render_dv_policy_commit(r,&wrong,transport,out->resolve_serial));
    assert(!dvbridge_render_dv_policy_committed(r,&committed));
    assert(dvbridge_render_dv_policy_commit(r,&identity,transport,out->resolve_serial));
    assert(dvbridge_render_dv_policy_committed(r,&committed));
    assert(committed.identity.picture==4 && committed.l1[1]==3128);
    retire(r);
    source.color.hdr.max_luma=NAN;
    assert(!dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    source.color.hdr.max_luma=0;
    struct dvbridge_dv_policy_snapshot after;
    assert(dvbridge_render_dv_policy_committed(r,&after) && !memcmp(&committed,&after,sizeof(after)));
    prediction.id.revision=8;
    assert(!dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    prediction.id.revision=7;source.repr.dovi=(void *)1;
    assert(!dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    source.repr.dovi=NULL;source.enhancement_layer=&source;
    assert(!dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    source.enhancement_layer=NULL;prediction.raw.l1_avg=4095;
    assert(!dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    prediction.raw.l1_avg=1412;
    policy.mode=(enum dvbridge_mode)5;
    assert(!dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    float *dv_pixels=malloc((size_t)3840*2160*4*sizeof(float));assert(dv_pixels);
    source.color.hdr.max_luma=4000;
    for(unsigned preset=0;preset<2;++preset){
        policy.mode=DVBRIDGE_MODE_ENHANCED_DV;policy.enhancement=preset;
        policy.tv=(struct dvbridge_tv_profile){1000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_P3_D65};
        result=dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry);assert(result);
        for(unsigned i=0;i<10000;++i){
            enum dvbridge_dv_policy_status status=dvbridge_render_dv_policy_poll(r);
            if(status==DVBRIDGE_DV_READY)break;
            assert(status==DVBRIDGE_DV_PENDING);nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
        }
        out=dvbridge_render_dv_policy_output(r);assert(out && out->value.sample_count==3840u*1920u/4);
        assert(!av_dovi_find_level(out->output_metadata,3));
        assert(out->value.nominal_max_nits==1000 && !out->value.fel_reconstructed);
        reference_read(gpu.gl->gpu,result,0,0,3840,2160,dv_pixels);
        for(unsigned i=0;i<3840*2160*4;++i)assert(isfinite(dv_pixels[i]));
        retire(r);
    }
    free(dv_pixels);
    pl_tex_destroy(gpu.gl->gpu,&transport);pl_tex_destroy(gpu.gl->gpu,&tex);dvbridge_renderer_destroy(r);
    assert(dvbridge_retirement_owner_destroy(&owner));reference_gpu_destroy(&gpu);
    puts("Native HDR10 Reference grading, generated wire fields and uncommitted identity passed");
}
