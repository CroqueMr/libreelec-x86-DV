/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reference_test.h"
#define DVBRIDGE_PQ_ENCODER_TEST 1
#include "../src/dvbridge_render.c"

int main(void)
{
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=3;
    av_dovi_get_color(m)->source_max_pq=3696;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,3696,1500}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=6,.l6={.max_luminance=4000}};
    *av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,
        .trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=-1}};
    av_dovi_get_header(m)->disable_residual_flag=0;
    av_dovi_get_mapping(m)->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(unsigned c=0;c<3;c++)av_dovi_get_mapping(m)->nlq[c]=
        (AVDOVINLQParams){.vdr_in_max=4096,.nlq_offset=512,.linear_deadzone_slope=1};
    void *original=av_memdup(m,bytes);assert(original);
    size_t count=3840u*2160;float *data=malloc(count*4*sizeof(*data));assert(data);
    for(size_t i=0;i<count;i++)for(unsigned c=0;c<4;c++)
        data[4*i+c]=c==3?1:(i%3840<32?0:.05f+.85f*((i+c*71)%997)/996);
    pl_tex input=reference_texture(gpu,3840,2160,data);free(data);
    float ep[16];for(unsigned i=0;i<16;i++)ep[i]=i%4==3?1:512.0f/1023;
    pl_tex el=reference_texture(gpu,2,2,ep),out=reference_texture(gpu,3840,2160,NULL);
    struct pl_frame enhancement=reference_frame(el,2,2),source=reference_frame(input,3840,2160);
    source.enhancement_layer=&enhancement;
    struct dvbridge_policy p=reference_policy();p.tv.peak_nits=1000;p.tv.gamut=DVBRIDGE_GAMUT_BT2020;
    struct dvbridge_identity id={1,1,p.revision};
    float *first=malloc(count*4*sizeof(*first)),*second=malloc(count*4*sizeof(*second));assert(first && second);
    for(unsigned pass=0;pass<2;pass++){
        assert(dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,m,bytes,0,0,
            (struct dvbridge_geometry){3840,2160,0,0,3840,2160},out,false,false,10));
        reference_read(gpu,out,0,0,3840,2160,pass?second:first);id.picture++;
    }
    assert(!memcmp(first,second,count*4*sizeof(*first)) &&
        "A repeated neutral Expert picture must not change after its first frame");
    assert(!r->cm29_tail_atlas && cm29_gpu_map_build_count==0 &&
        "Neutral Expert must not allocate an unused first-frame-only lattice");
    assert(!memcmp(m,original,bytes));
    free(first);free(second);av_free(original);av_free(m);
    pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&el);pl_tex_destroy(gpu,&out);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);
    puts("PASS neutral Expert first/repeated frame exact, no unused lattice, metadata immutable");
}
