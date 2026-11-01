/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reference_test.h"
#include "../src/cb1_cmv40.h"
#include "../src/dvbridge_render.c"

static void decisions(void)
{
    size_t bytes; AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={12,3079,1200}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2};
    av_dovi_get_color(m)->source_max_pq=3079; /* Approximately 1000 nits. */
    struct cb1_cmv40_options o={0};
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_OFF);
    o.mode=CB1_CMV40_NO_L2;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_NOT_SELECTED);
    o.mode=CB1_CMV40_ALWAYS;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_APPEND);
    o.mode=CB1_CMV40_AUTO;o.tv_peak=1001;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_APPEND);
    o.tv_peak=999;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_NOT_SELECTED);
    o.trigger=1000; /* CE recognizes 3079 as nominal 1000 nits. */
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_APPEND);
    av_dovi_get_color(m)->source_max_pq=3388; /* Approximately 2000 nits. */
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_NOT_SELECTED);
    o.trigger=2000;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_APPEND);
    o.mode=CB1_CMV40_AUTO2;o.headroom=20;o.tv_peak=1000;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_APPEND);
    av_dovi_get_ext(m,0)->l1.max_pq=3160;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_APPEND);
    av_dovi_get_ext(m,0)->l1.max_pq=3161;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_NOT_SELECTED);
    av_dovi_get_ext(m,0)->l1.max_pq=3300;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_NOT_SELECTED);
    o.tv_peak=0;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_NEEDS_TV);
    m->num_ext_blocks=1;*av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=2};
    o.tv_peak=1000;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_APPEND); /* CE missing-L1 rule. */
    m->num_ext_blocks=0;
    for(int mode=1;mode<=4;mode++){
        o.mode=mode;o.tv_peak=0;
        assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_APPEND);
    }
    m->num_ext_blocks=1;*av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=254};
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_EXISTING);
    o.mode=5;assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_INVALID);
    o.mode=CB1_CMV40_AUTO2;o.headroom=51;
    assert(cb1_cmv40_decide(&o,m,bytes)==CB1_CMV40_INVALID);
    assert(cb1_cmv40_decide(NULL,m,bytes)==CB1_CMV40_INVALID);
    av_free(m);
}

static void copy_and_defaults(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={12,3079,1200}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2};
    void *saved=av_memdup(m,bytes);assert(saved);
    struct cb1_cmv40_options o={.mode=CB1_CMV40_NO_L2};
    enum cb1_cmv40_status status;size_t output_bytes;AVDOVIMetadata *out=NULL;
    assert(cb1_cmv40_output(&o,m,bytes,true,&out,&output_bytes,&status));
    assert(status==CB1_CMV40_NOT_SELECTED && out && out->num_ext_blocks==1);
    assert(av_dovi_get_ext(out,0)->level==1);av_free(out);
    o.mode=CB1_CMV40_ALWAYS;
    assert(cb1_cmv40_output(&o,m,bytes,true,&out,&output_bytes,&status));
    assert(status==CB1_CMV40_APPEND && out->num_ext_blocks==5);
    const unsigned levels[]={1,3,9,254,11};
    for(unsigned i=0;i<5;i++)assert(av_dovi_get_ext(out,i)->level==levels[i]);
    const uint8_t l3[]={0x80,0x08,0x00,0x80,0x00};
    assert(av_dovi_get_ext(out,1)->dvbridge_original_length==5);
    assert(!memcmp(av_dovi_get_ext(out,1)->dvbridge_original_bytes,l3,5));
    assert(av_dovi_get_ext(out,2)->dvbridge_original_bytes[0]==0);
    assert(av_dovi_get_ext(out,3)->dvbridge_original_bytes[0]==0);
    assert(av_dovi_get_ext(out,3)->dvbridge_original_bytes[1]==2);
    assert(av_dovi_get_ext(out,4)->dvbridge_original_bytes[0]==1);
    AVDOVIMetadata *again=NULL;size_t again_bytes;
    assert(cb1_cmv40_output(&o,out,output_bytes,false,&again,&again_bytes,&status));
    assert(status==CB1_CMV40_EXISTING && !again); /* Idempotent, no allocation. */
    assert(!memcmp(m,saved,bytes));av_free(saved);av_free(out);
    o.mode=CB1_CMV40_DISABLED;
    assert(cb1_cmv40_output(&o,m,bytes,false,&out,&output_bytes,&status));
    assert(status==CB1_CMV40_OFF && !out);
    assert(!cb1_cmv40_output(&o,m,sizeof(*m)-1,false,&out,&output_bytes,&status));
    m->num_ext_blocks=0;o.mode=CB1_CMV40_ALWAYS;
    size_t offset=m->ext_block_offset,stride=m->ext_block_size;
    m->ext_block_offset=0;
    assert(!cb1_cmv40_output(&o,m,bytes,false,&out,&output_bytes,&status));
    m->ext_block_offset=offset;m->ext_block_size=0;
    assert(!cb1_cmv40_output(&o,m,bytes,false,&out,&output_bytes,&status));
    m->ext_block_size=stride;
    m->ext_block_offset=m->color_offset;
    assert(!cb1_cmv40_output(&o,m,bytes,false,&out,&output_bytes,&status));
    m->ext_block_offset=offset;
    m->num_ext_blocks=AV_DOVI_MAX_EXT_BLOCKS;
    for(int i=0;i<m->num_ext_blocks;i++)*av_dovi_get_ext(m,i)=(AVDOVIDmData){.level=2};
    assert(!cb1_cmv40_output(&o,m,bytes,false,&out,&output_bytes,&status));
    assert(!out);
    av_free(m);
}

static unsigned packet_blocks(const struct dvbridge_candidate *candidate)
{
    unsigned count;const uint32_t *packets=dvbridge_packets(candidate,&count);assert(packets && count);
    for(unsigned i=0;i<count;i++){
        uint8_t packet[128];for(unsigned j=0;j<128;j++)packet[j]=packets[128*i+j];
        assert(!dvbridge_dv_crc(packet,128));
    }
    return packets[75]; /* First packet payload starts at byte 5; block count is byte 70. */
}

static void renderer(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={12,3079,1200}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2000,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    struct dvbridge_geometry geo={64,64,840,0,2160,2160};
    float pixels[64*64*4];
    for(unsigned i=0;i<64*64*4;i++)pixels[i]=i%4==3?1:0.1f+0.8f*(i%64)/63;
    pl_tex tex=reference_texture(g.gl->gpu,64,64,pixels);struct pl_frame source=reference_frame(tex,64,64);
    assert(dvbridge_render_rgb(r,&source,m,bytes,0,NAN,geo));
    size_t size=(size_t)3840*2160*4*sizeof(float);
    float *before=malloc(size),*after=malloc(size);assert(before && after);
    reference_read(g.gl->gpu,dvbridge_render_texture(r),0,0,3840,2160,before);
    struct cb1_cmv40_options o={.mode=CB1_CMV40_ALWAYS,.headroom=20};
    dvbridge_renderer_set_cmv40(r,&o);
    assert(dvbridge_render_rgb(r,&source,m,bytes,0,NAN,geo));
    assert(dvbridge_renderer_cmv40_status(r)==CB1_CMV40_APPEND);
    reference_read(g.gl->gpu,dvbridge_render_texture(r),0,0,3840,2160,after);
    assert(!memcmp(before,after,size));free(before);free(after);
    assert(packet_blocks(r->pending)==7); /* L1, L2, L5, L3, L9, L11, L254. */
    dvbridge_renderer_set_l2_trims_disabled(r,true);
    assert(dvbridge_render_rgb(r,&source,m,bytes,0,NAN,geo));
    assert(packet_blocks(r->pending)==6);
    o.mode=CB1_CMV40_NO_L2;dvbridge_renderer_set_cmv40(r,&o);
    assert(dvbridge_render_rgb(r,&source,m,bytes,0,NAN,geo));
    assert(dvbridge_renderer_cmv40_status(r)==CB1_CMV40_NOT_SELECTED);
    assert(packet_blocks(r->pending)==2); /* Source had L2: only L1 and L5 remain. */
    dvbridge_renderer_set_cmv40(r,&(struct cb1_cmv40_options){.mode=CB1_CMV40_AUTO2,.tv_peak=1000,.headroom=20});
    dvbridge_renderer_set_l2_trims_disabled(r,false);
    for(unsigned i=0;i<8;i++){
        av_dovi_get_ext(m,0)->l1.max_pq=i%2?3500:3079;
        assert(dvbridge_render_rgb(r,&source,m,bytes,i/30.0,NAN,geo));
        assert(dvbridge_renderer_cmv40_status(r)==(i%2?CB1_CMV40_NOT_SELECTED:CB1_CMV40_APPEND));
        assert(packet_blocks(r->pending)==(i%2?3:7));
    }
    assert(dv_policy_prepare(r,NULL,NULL,NULL,NULL,0,0,0,geo,NULL,false,NULL)==DVBRIDGE_DV_UNSUPPORTED);
    assert(!r->cmv40.mode && !r->l2_trims_disabled);
    dvbridge_renderer_set_cmv40(r,&o);
    assert(!render_hdr10_ai(r,NULL,NULL,NULL,NULL,NULL,false,NULL));
    assert(!r->cmv40.mode);
    pl_tex_destroy(g.gl->gpu,&tex);dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);av_free(m);
}

static void optional_append_failure(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=22;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={12,3079,1200}};
    for(int i=1;i<22;i++)*av_dovi_get_ext(m,i)=(AVDOVIDmData){.level=2,
        .l2={.target_max_pq=100+i,.trim_slope=2048,.trim_offset=2048,.trim_power=2048,
            .trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=-1}};
    struct dvbridge_renderer r={.context=dvbridge_create(),.cmv40={.mode=CB1_CMV40_ALWAYS}};assert(r.context);
    struct dvbridge_geometry geo={64,64,840,0,2160,2160};
    struct dvbridge_candidate *original=dvbridge_prepare_output(r.context,m,bytes,0,geo,false,false);assert(original);
    struct dvbridge_candidate *actual=prepare_picture_candidate(&r,m,bytes,0,geo,false,false,false,false,false,false);
    assert(actual && r.cmv40_status==CB1_CMV40_REJECTED);
    unsigned a,b;const uint32_t *x=dvbridge_packets(actual,&a),*y=dvbridge_packets(original,&b);
    assert(a==b && !memcmp(x,y,a*128*sizeof(*x)));
    dvbridge_candidate_destroy(actual);dvbridge_candidate_destroy(original);dvbridge_destroy(r.context);av_free(m);
}

static void carrier_pixels(void)
{
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->rpu_type=2;h->rpu_format=18;h->vdr_bit_depth=12;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    c->signal_bit_depth=12;c->signal_full_range_flag=1;
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={12,3079,1200}};
    struct pl_frame f={.num_planes=2,.crop={0,0,3840,2160},
        .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
    for(unsigned p=0;p<2;p++){
        pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,p?2:1,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
        pl_tex tex=pl_tex_create(g.gl->gpu,pl_tex_params(.w=p?1920:3840,.h=p?1080:2160,
            .format=fmt,.sampleable=true,.renderable=true));assert(tex);
        f.planes[p]=(struct pl_plane){.texture=tex,.components=p?2:1,.component_mapping={p,2},.shift_x=p?-.5f:0};
        pl_tex_clear(g.gl->gpu,tex,(float[4]){.5f,.45f,.55f,1});
    }
    pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
    pl_tex target=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.sampleable=true,.renderable=true));assert(target);
    size_t size=(size_t)3840*2160*4;uint8_t *before=malloc(size),*after=malloc(size);assert(before && after);
    struct dvbridge_geometry geo={3840,2160,0,0,3840,2160};
    GLuint fbo;glGenFramebuffers(1,&fbo);
    for(unsigned route=0;route<5;route++){
        dvbridge_renderer_set_optimized_dv(r,route==4);
        bool p5=route>=2;h->vdr_rpu_profile=p5?0:1;h->bl_video_full_range_flag=p5;
        c->signal_color_space=p5?2:0;
        for(unsigned i=0;i<3;i++)c->ycc_to_rgb_offset[i]=(AVRational){p5&&!i?0:1,i?2:16};
        unsigned packets=0;
        for(unsigned enabled=0;enabled<2;enabled++){
            struct cb1_cmv40_options o={.mode=enabled?CB1_CMV40_ALWAYS:CB1_CMV40_DISABLED,.headroom=20};
            dvbridge_renderer_set_cmv40(r,&o);
            int status=route==4?(dvbridge_render_packed_overlay(r,&f,m,bytes,1,NAN,geo,target,false,NULL)?CB1_MASTER_READY:CB1_MASTER_FAILED):
                route&1?dvbridge_render_master_reference_ipt(r,&f,m,bytes,1,NAN,geo,target,false,NULL):
                    dvbridge_render_master_reference(r,&f,m,bytes,1,NAN,geo,target,false,NULL);
            bool ok=status==CB1_MASTER_READY;
            if(!ok)fprintf(stderr,"CM4 carrier route=%u enabled=%u status=%d\n",route,enabled,status);
            assert(ok);
            assert(dvbridge_renderer_cmv40_status(r)==(enabled?CB1_CMV40_APPEND:CB1_CMV40_OFF));
            unsigned count;assert(dvbridge_packets(r->pending,&count));if(count>packets)packets=count;
            glBindFramebuffer(GL_FRAMEBUFFER,fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,target,NULL,NULL,NULL),0);
            assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
            glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,enabled?after:before);
            assert(glGetError()==GL_NO_ERROR);glBindFramebuffer(GL_FRAMEBUFFER,0);
        }
        for(size_t p=0;p<size/4;p++)for(unsigned b=0;b<4;b++){
            unsigned mask=b==2 && p<(size_t)packets*3072?0xef:0xff;
            assert((before[p*4+b]&mask)==(after[p*4+b]&mask));
        }
    }
    puts("PASS exact movie carrier codes on both Masters and P5 Reference; only metadata embedding bit excluded");
    glDeleteFramebuffers(1,&fbo);free(before);free(after);av_free(m);
    pl_tex_destroy(g.gl->gpu,&target);
    for(unsigned p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&f.planes[p].texture);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);
}

int main(void)
{
    decisions();copy_and_defaults();renderer();optional_append_failure();carrier_pixels();
    puts("PASS CM4 five choices, original-L2 decisions, thresholds, defaults, immutable copy and idempotence");
}
