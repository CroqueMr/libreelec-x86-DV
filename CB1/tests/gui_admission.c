/* SPDX-License-Identifier: MIT */
/* Observe the real shader contract emitted by each production pack owner. */
#include "reference_test.h"
static unsigned seen,optimized;
static bool observe_shader(pl_shader,const struct pl_custom_shader *);
#define pl_shader_custom observe_shader
#ifndef CB1_RENDER_IMPLEMENTATION
#define CB1_RENDER_IMPLEMENTATION "dvbridge_render.c"
#endif
#include CB1_RENDER_IMPLEMENTATION
#undef pl_shader_custom
static bool observe_shader(pl_shader shader,const struct pl_custom_shader *params)
{
    if(params->header && strstr(params->header,"vec3 cb1_gui_value(")){
        ++seen;optimized+=strstr(params->header,"#define CB1_GUI_QUAD 1")!=NULL;
    }
    return pl_shader_custom(shader,params);
}
int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    if(!r->fragment_quad){dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);return 77;}
    enum{W=1920,H=1080};float *data=malloc((size_t)W*H*4*sizeof(*data));assert(data);
    for(unsigned i=0;i<W*H*4;i++)data[i]=i%4==3?1:.25f;
    pl_tex input=reference_texture(g.gl->gpu,W,H,data);
    for(unsigned i=0;i<W*H*4;i++)data[i]=i%4==3?.5f:.1f;
    pl_tex gui=reference_texture(g.gl->gpu,W,H,data);
    free(data);
    float values[4]={0,0,0,1};
    pl_tex degamma=reference_texture(g.gl->gpu,1,1,values),pq=reference_texture(g.gl->gpu,1,1,values);
    pl_tex output=pl_tex_create(g.gl->gpu,pl_tex_params(.w=W,.h=H,
        .format=pl_find_named_fmt(g.gl->gpu,"rgba8"),.renderable=true));assert(output);
    struct pl_frame source=reference_frame(input,W,H);
    source.repr=pl_color_repr_rgb;
    source.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ};
    struct dvbridge_geometry geometry={W,H,0,0,W,H,W,H};
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);
    metadata->num_ext_blocks=1;
    AVDOVIDmData *l1=av_dovi_get_ext(metadata,0);l1->level=1;
    l1->l1.max_pq=3079;l1->l1.avg_pq=1600;
    av_dovi_get_header(metadata)->vdr_bit_depth=12;
    AVDOVIColorMetadata *color=av_dovi_get_color(metadata);
    color->signal_bit_depth=12;color->signal_full_range_flag=1;
    for(unsigned i=0;i<3;i++)color->ycc_to_rgb_offset[i]=(AVRational){1,i?2:16};
    dvbridge_renderer_set_optimized_dv(r,true);
    r->dv.fence_sync=glFenceSync;r->dv.wait_sync=glClientWaitSync;r->dv.delete_sync=glDeleteSync;
    for(unsigned owner=0;owner<3;owner++)for(unsigned variant=0;variant<3;variant++){
        fprintf(stderr,"GUI admission owner=%u variant=%u\n",owner,variant);
        struct dvbridge_native_overlay overlay={.texture=gui,.degamma=degamma,.pq=pq,
            .rect={0,0,W,H},.optimized=variant!=0,.input_pq=variant==2};
        seen=optimized=0;
        if(owner==0){
            assert(dvbridge_render_packed_overlay(r,&source,metadata,bytes,1+variant,NAN,geometry,output,false,&overlay));
        }else if(owner==1){
            r->dv.output.value.geometry=geometry;r->dv.output.value.container=source.color;
            r->dv.overlay=overlay;r->dv.enhanced_overlay=true;
            unsigned count;const uint32_t *packets=dvbridge_packets(r->pending,&count);
            assert(packets && count);
            assert(dve_pack_overlay(r,input,output,false,packets,count,false));
        }else{
            assert(ai_render_pixels(r,&source,geometry,output,false,&overlay,NULL));
        }
        assert(seen && optimized==(variant==1?seen:0));
    }
    /* The fused AI owner already declares its subgroup extensions before its
     * image uniforms. Packing must not append a second extension afterwards. */
    pl_dispatch dispatch=pl_dispatch_create(g.log,g.gl->gpu);
    pl_shader shader=pl_dispatch_begin(dispatch);
    assert(pl_shader_sample_direct(shader,pl_sample_src(.tex=input)));
    struct pl_custom_shader prior={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .prelude="#extension GL_KHR_shader_subgroup_basic:require\n"
            "#extension GL_KHR_shader_subgroup_quad:require\n"
            "layout(rgba16f,binding=0)writeonly uniform highp image2D cb1_gui_prior;\n"};
    assert(pl_shader_custom(shader,&prior));
    struct dvbridge_native_overlay overlay={.texture=gui,.degamma=degamma,.pq=pq,.rect={0,0,W,H}};
    unsigned count;const uint32_t *packets=dvbridge_packets(r->pending,&count);
    struct active_mask mask={.ai_renderer=r,.gui_quad=true,.overlay=&overlay,
        .rect={0,0,W,H},.raster={W,H},.packets=packets,.count=count};
    struct pl_hook_params hook={.stage=PL_HOOK_OUTPUT,.sh=shader};
    assert(!pack_active_area(&mask,&hook).failed);
    assert(pl_dispatch_finish(dispatch,pl_dispatch_params(.shader=&shader,.target=output)));
    pl_dispatch_destroy(&dispatch);
    glFinish();av_free(metadata);
    pl_tex_destroy(g.gl->gpu,&input);pl_tex_destroy(g.gl->gpu,&gui);pl_tex_destroy(g.gl->gpu,&output);
    pl_tex_destroy(g.gl->gpu,&degamma);pl_tex_destroy(g.gl->gpu,&pq);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);return 0;
}
