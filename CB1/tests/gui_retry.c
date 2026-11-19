/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
static unsigned calls;
static unsigned failures=1;
static bool processing;
static bool gui=true;
static bool submit(pl_renderer,const struct pl_frame *,const struct pl_frame *,const struct pl_render_params *);
#define pl_render_image submit
#include "dvbridge_render.c"
#undef pl_render_image
static bool submit(pl_renderer r,const struct pl_frame *s,const struct pl_frame *t,const struct pl_render_params *p)
{
    ++calls;
    if(processing && gui && calls==2)assert(p->cb1_processing && p->cb1_processing->groups==CB1_PROCESSING_COLOUR);
    if(calls<=failures)return false;
    const struct active_mask *mask=p->hooks[0]->priv;
    assert(!mask->gui_quad);
    return pl_render_image(r,s,t,p);
}
int main(int argc,char **argv)
{
    processing=argc>1;
    if(argc>1 && !strcmp(argv[1],"movie"))gui=false;
    if(argc>1 && !strcmp(argv[1],"both"))failures=2;
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    float pixels[8*8*4];for(unsigned i=0;i<sizeof(pixels)/sizeof(*pixels);i++)pixels[i]=.5f;
    pl_tex input=reference_texture(g.gl->gpu,8,8,pixels);
    pl_tex output=pl_tex_create(g.gl->gpu,pl_tex_params(.w=8,.h=8,
        .format=pl_find_named_fmt(g.gl->gpu,"rgba8"),.renderable=true));assert(output);
    struct pl_frame source=reference_frame(input,8,8),target=reference_frame(output,8,8);
    uint32_t words[128]={0};
    struct active_mask mask={.rect={0,0,8,8},.raster={8,8},.gui_quad=gui,
        .source_domain=true,.reference_transport=true,.packets=words,.count=1};
    struct pl_hook hook={.stages=PL_HOOK_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&mask,.hook=pack_active_area};
    const struct pl_hook *hooks[]={&hook};
    struct pl_render_params params=pl_render_fast_params;params.hooks=hooks;params.num_hooks=1;
    if(processing){
        size_t size;AVDOVIMetadata *metadata=task3_fixture(&size);
        assert(cb1_processing_prepare(&r->processing,g.gl->gpu,&source,metadata,size,false,CB1_PROCESSING_COLOUR));
        av_free(metadata);assert(r->processing.view.groups==CB1_PROCESSING_COLOUR);
        params.cb1_processing=&r->processing.view;
    }
    assert(render_image(r,&source,&target,&params,&mask,NULL,false));
    assert(calls==failures+1 && !mask.gui_quad);
    assert(r->processing_failed_groups==(failures==2 || !gui?CB1_PROCESSING_COLOUR:0));
    if(processing && gui && failures==1)assert(params.cb1_processing==&r->processing.view);
    pl_tex_destroy(g.gl->gpu,&input);pl_tex_destroy(g.gl->gpu,&output);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);return 0;
}
