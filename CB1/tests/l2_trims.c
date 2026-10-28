/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reference_test.h"
#include "../src/dvbridge_render.c"

static void same_packets(const struct dvbridge_candidate *actual,
                         const struct dvbridge_candidate *expected)
{
    assert(actual && expected);
    unsigned na,ne;
    const uint32_t *a=dvbridge_packets(actual,&na),*e=dvbridge_packets(expected,&ne);
    assert(na==ne && !memcmp(a,e,na*128*sizeof(*a)));
    for(unsigned i=0;i<na;i++){
        uint8_t packet[128];
        for(unsigned j=0;j<128;j++)packet[j]=a[i*128+j];
        assert(!dvbridge_dv_crc(packet,sizeof(packet)));
    }
}

static AVDOVIMetadata *extensions(size_t *bytes)
{
    size_t original_bytes;AVDOVIMetadata *base=task3_fixture(&original_bytes);
    /* A producer may extend each block. Compaction must use the full stride. */
    size_t stride=base->ext_block_size+16;
    *bytes=base->ext_block_offset+AV_DOVI_MAX_EXT_BLOCKS*stride;
    AVDOVIMetadata *m=av_mallocz(*bytes);assert(m);
    memcpy(m,base,base->ext_block_offset);av_free(base);m->ext_block_size=stride;
    m->num_ext_blocks=9;
    for(int i=0;i<m->num_ext_blocks;i++)
        memset((uint8_t *)av_dovi_get_ext(m,i)+sizeof(AVDOVIDmData),0x81+i,stride-sizeof(AVDOVIDmData));
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2000,
        .trim_slope=2100,.trim_offset=1900,.trim_power=2300,.trim_chroma_weight=1700,
        .trim_saturation_gain=2200,.ms_weight=-1}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=1,.l1={.min_pq=12,.max_pq=3079,.avg_pq=1200}};
    *av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=8,.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=10,.dvbridge_original_bytes={1,0x12,0x34}};
    *av_dovi_get_ext(m,3)=(AVDOVIDmData){.level=3,.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=5,.dvbridge_original_bytes={0x12,0x34,0x56,0x78,0x90}};
    *av_dovi_get_ext(m,4)=*av_dovi_get_ext(m,0);av_dovi_get_ext(m,4)->l2.target_max_pq=3079;
    *av_dovi_get_ext(m,5)=(AVDOVIDmData){.level=5,.l5={.left_offset=2,.right_offset=2,.top_offset=1,.bottom_offset=1}};
    *av_dovi_get_ext(m,6)=(AVDOVIDmData){.level=6,.l6={.max_luminance=4000,.max_cll=3000,.max_fall=1000}};
    *av_dovi_get_ext(m,7)=(AVDOVIDmData){.level=9,.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=1,.dvbridge_original_bytes={2}};
    *av_dovi_get_ext(m,8)=(AVDOVIDmData){.level=254,.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=2,.dvbridge_original_bytes={1,2}};
    return m;
}

static void source_signal(AVDOVIMetadata *m,bool p5)
{
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->vdr_bit_depth=12;h->vdr_rpu_profile=p5?0:1;h->bl_video_full_range_flag=p5;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    c->signal_bit_depth=12;c->signal_full_range_flag=1;c->signal_color_space=p5?2:0;
    for(int i=0;i<3;i++)c->ycc_to_rgb_offset[i]=(AVRational){p5&&!i?0:1,i?2:16};
}

static void routes(void)
{
    size_t bytes;AVDOVIMetadata *m=extensions(&bytes),*without=av_memdup(m,bytes);assert(without);
    /* Explicit fixture indices, independent of production's level filter. */
    const unsigned retained[]={1,2,3,5,6,7,8};
    without->num_ext_blocks=7;
    for(unsigned i=0;i<7;i++)memcpy(av_dovi_get_ext(without,i),av_dovi_get_ext(m,retained[i]),m->ext_block_size);
    struct dvbridge_renderer r={.context=dvbridge_create()};assert(r.context);
    struct dvbridge_geometry geo={64,64,840,0,2160,2160};
    for(unsigned route=0;route<5;route++){
        bool master=route==2 || route==4,source=route==1,ipt=route==3;
        source_signal(m,route==4);source_signal(without,route==4);
        void *saved=av_memdup(m,bytes);assert(saved);
        struct dvbridge_candidate *(*prepare)(const struct dvbridge_context *,const void *,size_t,
            double,struct dvbridge_geometry,bool,bool)=ipt?dvbridge_prepare_ipt_output:
            master?dvbridge_prepare_master_source_output:source?dvbridge_prepare_source_output:dvbridge_prepare_output;
        struct dvbridge_candidate *original=prepare(r.context,m,bytes,0,geo,false,false);
        struct dvbridge_candidate *expected=prepare(r.context,without,bytes,0,geo,false,false);
        assert(original && expected);
        struct dvbridge_candidate *actual=prepare_picture_candidate(&r,m,bytes,0,geo,false,false,master,source,ipt,false);
        same_packets(actual,original);dvbridge_candidate_destroy(actual);
        actual=prepare_picture_candidate(&r,m,bytes,0,geo,false,false,master,source,ipt,true);
        same_packets(actual,expected);dvbridge_candidate_destroy(actual);
        actual=prepare_picture_candidate(&r,without,bytes,0,geo,false,false,master,source,ipt,true);
        same_packets(actual,expected);dvbridge_candidate_destroy(actual);
        /* Output toggles must use the normal committed serializer revision/id. */
        assert(dvbridge_commit(r.context,expected));
        dvbridge_candidate_destroy(expected);
        expected=prepare(r.context,m,bytes,1.0/24,geo,false,false);
        actual=prepare_picture_candidate(&r,m,bytes,1.0/24,geo,false,false,master,source,ipt,false);
        same_packets(actual,expected);dvbridge_candidate_destroy(actual);dvbridge_candidate_destroy(expected);
        /* Existing malformed and duplicate-L2 failures must not be hidden. */
        av_dovi_get_ext(m,4)->l2.target_max_pq=2000;
        assert(!prepare_picture_candidate(&r,m,bytes,0,geo,false,false,master,source,ipt,true));
        av_dovi_get_ext(m,4)->l2.target_max_pq=3079;
        av_dovi_get_ext(m,0)->l2.trim_slope=4096;
        assert(!prepare_picture_candidate(&r,m,bytes,0,geo,false,false,master,source,ipt,true));
        av_dovi_get_ext(m,0)->l2.trim_slope=2100;
        assert(!prepare_picture_candidate(&r,m,sizeof(*m)-1,0,geo,false,false,master,source,ipt,true));
        assert(!memcmp(m,saved,bytes));av_free(saved);dvbridge_candidate_destroy(original);
    }
    dvbridge_destroy(r.context);av_free(without);av_free(m);
}

int main(void)
{
    routes();
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.min_pq=12,.max_pq=3079,.avg_pq=1200}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2000,
        .trim_slope=2100,.trim_offset=1900,.trim_power=2300,.trim_chroma_weight=1700,
        .trim_saturation_gain=2200,.ms_weight=-1}};
    void *saved=av_memdup(m,bytes);assert(saved);
    AVDOVIMetadata *without=av_memdup(m,bytes);assert(without);without->num_ext_blocks=1;
    struct dvbridge_geometry geo={64,64,840,0,2160,2160};
    float pixels[64*64*4];
    for(unsigned i=0;i<64*64*4;i++)pixels[i]=i%4==3?1:0.2f+0.6f*((i/4)%64)/63;
    pl_tex tex=reference_texture(g.gl->gpu,64,64,pixels);
    struct pl_frame source=reference_frame(tex,64,64);
    struct dvbridge_candidate *expected=dvbridge_prepare_output(r->context,without,bytes,0,geo,false,false);
    assert(expected);
    /* Default-off packets and all movie pixels are the unchanged renderer. */
    assert(!r->l2_trims_disabled);
    struct dvbridge_candidate *original=dvbridge_prepare_output(r->context,m,bytes,0,geo,false,false);
    assert(dvbridge_render_rgb(r,&source,m,bytes,0,NAN,geo));
    same_packets(dvbridge_render_candidate(r),original);dvbridge_candidate_destroy(original);
    size_t movie_bytes=(size_t)3840*2160*4*sizeof(float);
    float *before=malloc(movie_bytes),*after=malloc(movie_bytes);assert(before && after);
    reference_read(g.gl->gpu,dvbridge_render_texture(r),0,0,3840,2160,before);
    dvbridge_renderer_set_l2_trims_disabled(r,true);
    assert(dvbridge_render_rgb(r,&source,m,bytes,0,NAN,geo));
    same_packets(dvbridge_render_candidate(r),expected);
    reference_read(g.gl->gpu,dvbridge_render_texture(r),0,0,3840,2160,after);
    assert(!memcmp(before,after,movie_bytes));free(before);free(after);
    /* Enabling affects the next prepare, never a prepared candidate. */
    dvbridge_renderer_set_l2_trims_disabled(r,false);
    same_packets(dvbridge_render_candidate(r),expected);
    dvbridge_renderer_set_l2_trims_disabled(r,true);
    assert(dv_policy_prepare(r,NULL,NULL,NULL,NULL,0,0,0,geo,NULL,false,NULL)==DVBRIDGE_DV_UNSUPPORTED);
    assert(!r->l2_trims_disabled);
    dvbridge_renderer_set_l2_trims_disabled(r,true);
    assert(!render_hdr10_ai(r,NULL,NULL,NULL,NULL,NULL,false,NULL));
    assert(!r->l2_trims_disabled);
    assert(!memcmp(m,saved,bytes));
    dvbridge_candidate_destroy(expected);av_free(without);av_free(saved);av_free(m);
    pl_tex_destroy(g.gl->gpu,&tex);dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);
    puts("PASS L2 canonical/source/Master/IPT/P5 packets, CRC, validation, immutable input, transitions and exact movie pixels");
}
