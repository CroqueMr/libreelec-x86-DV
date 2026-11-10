/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include <libplacebo/shaders/custom.h>
static bool fail_intermediate;
static unsigned draws,hook_failures;
static bool checked_shader(pl_shader,const struct pl_custom_shader *);
static bool checked_render(pl_renderer,const struct pl_frame *,const struct pl_frame *,
                           const struct pl_render_params *);
#define pl_shader_custom checked_shader
#define pl_render_image checked_render
#include "../src/dvbridge_render.c"
#undef pl_render_image
#undef pl_shader_custom

static bool checked_shader(pl_shader sh,const struct pl_custom_shader *p)
{
    if(fail_intermediate&&p->body&&!strcmp(p->body,"color.rgb=clamp(color.rgb,0.0,1.0);")){
        hook_failures++;return false;
    }
    return pl_shader_custom(sh,p);
}
static bool checked_render(pl_renderer r,const struct pl_frame *s,const struct pl_frame *t,
                           const struct pl_render_params *p)
{
    draws++;return pl_render_image(r,s,t,p);
}

int main(void)
{
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu.gl->gpu);assert(r);
    float pixels[8*8*4];for(unsigned i=0;i<8*8;i++){
        pixels[4*i]=pixels[4*i+1]=pixels[4*i+2]=.4f;pixels[4*i+3]=1;
    }
    pl_tex input=reference_texture(gpu.gl->gpu,8,8,pixels),output=reference_texture(gpu.gl->gpu,8,8,NULL);
    struct pl_frame source=reference_frame(input,8,8);source.repr.alpha=PL_ALPHA_NONE;
    struct dvbridge_geometry g={8,8,0,0,8,8,8,8};
    struct dvbridge_policy p={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    struct dvbridge_identity id={1,1,3};size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
#define DIRECT() dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,m,bytes,1,1,g,output,false,false,8)
#define REJECT() do{unsigned before=draws;assert(!DIRECT());assert(draws==before);assert(!dvbridge_render_policy_output(r));checks++;}while(0)
#define STAGED() do{assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&source,m,bytes,1,1,g));assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,8));checks++;}while(0)
    unsigned checks=0;
    assert(DIRECT());assert(dvbridge_render_policy_commit(r,&id,output));
    struct dvbridge_hdr10_policy_output accepted;
    assert(dvbridge_render_policy_committed(r,&accepted));
    /* Preflight ineligibility does not draw or publish a successor. */
    g=(struct dvbridge_geometry){8,8,2,2,4,4,8,8};REJECT();STAGED();
    g=(struct dvbridge_geometry){8,8,0,0,8,8,8,8};
    g.crop[0]=2;g.crop[2]=6;g.crop[3]=8;REJECT();STAGED();memset(g.crop,0,sizeof(g.crop));
    g.placement[0]=1;g.placement[2]=7;g.placement[3]=8;REJECT();STAGED();memset(g.placement,0,sizeof(g.placement));
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=5,.l5={1,1,1,1}};m->num_ext_blocks=1;
    REJECT();STAGED();g.ignore_l5=true;assert(DIRECT());checks++;g.ignore_l5=false;m->num_ext_blocks=0;
    source.rotation=PL_ROTATION_90;REJECT();source.rotation=PL_ROTATION_0;
    source.repr.alpha=PL_ALPHA_PREMULTIPLIED;REJECT();source.repr.alpha=PL_ALPHA_NONE;
    source.num_overlays=1;REJECT();source.num_overlays=0;
    source.profile.len=1;REJECT();source.profile.len=0;
    id.revision++;REJECT();id.revision--;
    pl_tex save=source.planes[0].texture;source.planes[0].texture=output;REJECT();source.planes[0].texture=save;
    pl_tex final=output;output=r->rgb;REJECT();output=final;
    const char *formats[]={"rgba8","rgba16f"};
    for(unsigned i=0;i<2;i++){
        pl_fmt fmt=pl_find_named_fmt(gpu.gl->gpu,formats[i]);assert(fmt);
        pl_tex inadequate=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=8,.h=8,.format=fmt,.renderable=true));assert(inadequate);
        unsigned prior=draws;
        assert(!dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,m,bytes,1,1,g,inadequate,false,false,i?8:10));
        assert(draws==prior);checks++;pl_tex_destroy(gpu.gl->gpu,&inadequate);
    }
    output=reference_texture(gpu.gl->gpu,4,8,NULL);REJECT();pl_tex_destroy(gpu.gl->gpu,&output);output=final;
    unsigned before=draws;
    assert(!dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,m,bytes,1,1,g,output,false,false,7));
    assert(!dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,m,bytes,1,1,g,output,false,false,17));
    assert(!dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,m,bytes,NAN,1,g,output,false,false,8));
    assert(draws==before);checks+=3;
    struct pl_frame el=source;source.enhancement_layer=&el;
    el.planes[0].texture=output;REJECT();el.planes[0].texture=input;
    assert(!dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,m,bytes,1,2,g,output,false,false,8));
    checks++;source.enhancement_layer=NULL;
    /* Non-RPU HDR/HDR+ keep the original staged SDR import path. */
    source.repr=pl_color_repr_rgb;source.color=(struct pl_color_space){
        .primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,.hdr={.max_luma=1000}};
    assert(!dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,NULL,0,1,1,g,output,false,false,8));
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&source,NULL,0,1,1,g));
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,8));checks++;
    source.color.hdr.scene_max[0]=source.color.hdr.scene_max[1]=source.color.hdr.scene_max[2]=400;
    source.color.hdr.scene_avg=100;
    assert(!dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,NULL,0,1,1,g,output,false,false,8));
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&source,NULL,0,1,1,g));
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,8));checks++;
    source.repr=(struct pl_color_repr){.alpha=PL_ALPHA_NONE};source.color=(struct pl_color_space){0};
    p.mode=DVBRIDGE_MODE_HDR10_EXPERT;p.tv=(struct dvbridge_tv_profile){1500,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT709};
    assert(!DIRECT());checks++;p=(struct dvbridge_policy){.revision=3,.mode=DVBRIDGE_MODE_SDR};
    /* A real native hook error must cancel this picture, not silently invoke
     * the staged owner or overwrite previously committed output facts. */
    id.picture=2;fail_intermediate=true;before=draws;
    assert(!DIRECT());assert(draws>before&&hook_failures>0);
    assert(!dvbridge_render_policy_output(r));
    struct dvbridge_hdr10_policy_output after;
    assert(dvbridge_render_policy_committed(r,&after));
    assert(dvbridge_identity_equal(&after.identity,&accepted.identity));checks++;
    dvbridge_renderer_reset(r);assert(!dvbridge_render_policy_committed(r,&after));checks++;
    printf("PASS %u guard/owner controls; injected_hook_failures=%u\n",checks,hook_failures);
    av_free(m);pl_tex_destroy(gpu.gl->gpu,&input);pl_tex_destroy(gpu.gl->gpu,&output);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&gpu);return 0;
}
