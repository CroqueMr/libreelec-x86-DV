/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"

static void image(struct dvbridge_renderer *r,pl_gpu gpu,const struct pl_frame *f,
    AVDOVIMetadata *m,size_t bytes,struct dvbridge_policy *p,float out[16])
{
    struct dvbridge_identity id={4,7,p->revision};
    assert(dvbridge_render_hdr10_policy_rgb(r,p,&id,f,m,bytes,0,0,(struct dvbridge_geometry){2,2,0,0,2,2}));
    reference_read(gpu,dvbridge_render_texture(r),0,0,2,2,out);
}
int main(void)
{
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    float pixels[16]={.25,.3,.4,1,.3,.4,.5,1,.4,.5,.6,1,.5,.6,.7,1};
    pl_tex input=reference_texture(gpu,2,2,pixels);struct pl_frame f=reference_frame(input,2,2);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0);l1->level=1;l1->l1.max_pq=3079;l1->l1.avg_pq=1667;
    AVDOVIDmData *l2=av_dovi_get_ext(m,1);l2->level=2;l2->l2.target_max_pq=3000;
    l2->l2.trim_slope=l2->l2.trim_offset=l2->l2.trim_power=2048;
    l2->l2.trim_chroma_weight=l2->l2.trim_saturation_gain=2048;l2->l2.ms_weight=-1;
    struct dvbridge_policy p=reference_policy();p.tv.peak_nits=800;p.tv.gamut=DVBRIDGE_GAMUT_BT2020;
    float neutral[16],trimmed[16],basic1[16],basic2[16];
    image(r,gpu,&f,m,bytes,&p,neutral);
    struct dvbridge_hdr10_session session;assert(dvbridge_hdr10_session_init(&session,m,bytes));
    assert(dvbridge_render_hdr10_rgb(r,&session,&f,m,bytes,0,0,(struct dvbridge_geometry){2,2,0,0,2,2}));
    reference_read(gpu,dvbridge_render_texture(r),0,0,2,2,basic1);
    l2->l2.trim_power=2600;image(r,gpu,&f,m,bytes,&p,trimmed);
    assert(memcmp(trimmed,neutral,sizeof(neutral)));
    assert(dvbridge_render_hdr10_rgb(r,&session,&f,m,bytes,0,0,(struct dvbridge_geometry){2,2,0,0,2,2}));
    reference_read(gpu,dvbridge_render_texture(r),0,0,2,2,basic2);assert(!memcmp(basic1,basic2,sizeof(basic1)));
    printf("{\"neutral\":[");
    for(int i=0;i<4;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",neutral[i*4],neutral[i*4+1],neutral[i*4+2]);
    printf("],\"trimmed\":[");
    for(int i=0;i<4;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",trimmed[i*4],trimmed[i*4+1],trimmed[i*4+2]);
    puts("]}");
    // Source offset can deliberately lift content black; borders are separate.
    memset(pixels,0,sizeof(pixels));for(int i=3;i<16;i+=4)pixels[i]=1;
    pl_tex black=reference_texture(gpu,2,2,pixels);f=reference_frame(black,2,2);
    l2->l2.trim_power=2048;l2->l2.trim_offset=2200;image(r,gpu,&f,m,bytes,&p,trimmed);
    assert(trimmed[0]>0 && trimmed[1]>0 && trimmed[2]>0);
    dvbridge_renderer_destroy(r);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&black);av_free(m);reference_gpu_destroy(&g);
    puts("PASS real creative pixel effect, Basic invariance, intentional content-black offset");
}
