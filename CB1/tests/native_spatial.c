/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <string.h>
#include "../src/dvbridge_render.c"

#ifdef DVBRIDGE_SPATIAL_API
struct witness { unsigned calls; int outcome; struct pl_frame input; pl_tex fitted; };
static bool fit(void *priv,const struct pl_frame *source,const struct pl_frame *target,
                struct pl_frame *out)
{
    struct witness *w=priv;
    w->calls++;w->input=*source;
    if(!w->outcome)return false;
    *out=*source;
    out->planes[0].texture=w->fitted;
    out->crop=target->crop;
    if(w->outcome==2)out->color.transfer=PL_COLOR_TRC_SRGB;
    if(w->outcome==3)out->crop.x1--;
    return true;
}
#endif

int main(void)
{
#ifndef DVBRIDGE_SPATIAL_API
    assert(!"Final fitting needs one borrowed-frame native spatial boundary");
#else
    struct pl_fmt_t fp32={.type=PL_FMT_FLOAT,.num_components=4,.component_depth={32,32,32,32}};
    struct pl_fmt_t fp16={.type=PL_FMT_FLOAT,.num_components=4,.component_depth={16,16,16,16}};
    struct pl_fmt_t rgb8={.type=PL_FMT_UNORM,.num_components=4,.component_depth={8,8,8,8}};
    struct pl_tex_t input={.params={.w=1920,.h=1080,.format=&fp32}};
    struct pl_tex_t fitted={.params={.w=3840,.h=2160,.format=&fp32}};
    struct pl_tex_t final={.params={.w=3840,.h=2160}};
    struct pl_frame source={.num_planes=1,
        .planes={{.texture=&input,.components=4,.component_mapping={0,1,2,3}}},
        .repr=pl_color_repr_rgb,.color={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ},
        .crop={0,0,1920,1080}};
    struct pl_frame target=source,out={0};
    target.planes[0].texture=&final;target.crop=(pl_rect2df){0,0,3840,2160};
    pl_rect2df visible;
    struct dvbridge_geometry geometry={1920,1080,0,0,3840,2160,3840,2160,
        {480,270,1440,810}};
    assert(picture_crop(&visible,geometry,&input));
    assert(visible.x0==480 && visible.y0==270 && visible.x1==1440 && visible.y1==810);
    geometry=(struct dvbridge_geometry){1920,1080,960,0,1920,2160,3840,2160,
        {480,0,1440,1080}};
    assert(picture_crop(&visible,geometry,&input));
    assert(visible.x0==0 && visible.y0==0 && visible.x1==1920 && visible.y1==1080);
#if DVBRIDGE_TARGET_API < 3
    assert(!"Native fractional placement must retain its sampling phase");
#else
    geometry=(struct dvbridge_geometry){1920,1080,0,186,2560,1068,2560,1440,
        {0,0,1920,1080},{0,186.6666667f,2560,1253.3333333f}};
    assert(picture_crop(&visible,geometry,&input));
    assert(fabs(visible.y0+189.0f)<.001f && fabs(visible.y1-1269.0f)<.001f);
    struct dvbridge_renderer fractional={0};
    assert(configure_target(&fractional,geometry) && !fractional.target_identity);
    AVDOVIMetadata metadata={0};float aperture[4];
    assert(reference_area(aperture,&metadata,geometry));
    for(unsigned i=0;i<4;i++)assert(fabsf(aperture[i]-geometry.placement[i])<.001f);
    struct dvbridge_geometry invalid=geometry;invalid.placement[1]=NAN;
    assert(!reference_area(aperture,&metadata,invalid));
#endif
    struct dvbridge_renderer r={0};
    /* Work surfaces use the decoded raster, never output placement/crop. */
    for(int width=638;width<=3838;width+=800){
        geometry.source_width=width;geometry.source_height=width/2+7;
        struct dvbridge_geometry local=source_geometry(geometry);
        assert(configure_target(&r,local) && r.target_identity);
        assert(local.width==width && local.height==geometry.source_height);
        for(unsigned i=0;i<4;i++)assert(!local.crop[i] && !local.placement[i]);
        assert(geometry.placement[1]!=0 && geometry.crop[3]!=0);
    }
    struct witness w={.outcome=1,.fitted=&fitted};
    dvbridge_renderer_set_spatial_fit(&r,fit,&w);
    bool applied=true;
    assert(fit_picture(&r,&source,&source,&out,&applied,32) && !applied && !w.calls);
    assert(fit_picture(&r,&source,&target,&out,&applied,32) && applied && w.calls==1);
    assert(w.input.planes[0].texture==&input && out.planes[0].texture==&fitted);
    assert(out.repr.sys==source.repr.sys && out.color.transfer==PL_COLOR_TRC_PQ);
    w.outcome=0;
    assert(!fit_picture(&r,&source,&target,&out,&applied,32) && w.calls==2);
    w.outcome=2;
    assert(!fit_picture(&r,&source,&target,&out,&applied,32));
    w.outcome=3;
    assert(!fit_picture(&r,&source,&target,&out,&applied,32));
    w.outcome=1;fitted.params.w=1920;
    assert(!fit_picture(&r,&source,&target,&out,&applied,32));
    fitted.params.w=3840;
    fitted.params.format=&rgb8;
    assert(!fit_picture(&r,&source,&target,&out,&applied,32));
    fitted.params.format=&fp16;
    assert(fit_picture(&r,&source,&target,&out,&applied,16) && applied);
    assert(!fit_picture(&r,&source,&target,&out,&applied,32));
    fitted.params.format=&fp32;
    source.num_planes=2;
    assert(!fit_picture(&r,&source,&target,&out,&applied,32));
    dvbridge_renderer_set_spatial_fit(&r,NULL,NULL);
    assert(fit_picture(&r,&source,&target,&out,&applied,32) && !applied);
    struct pl_tex_t gui={.params={.w=1920,.h=1080,.sampleable=true}};
    struct pl_tex_t degamma={.params={.w=256,.h=1,.sampleable=true}},pq=degamma;
    struct dvbridge_native_overlay overlay={.texture=&gui,.degamma=&degamma,.pq=&pq,
        .rect={0,0,1920,1080}};
    assert(overlay_valid(&overlay,1920,1080));
    assert(!overlay_valid(&overlay,3840,2160));
    overlay.rect[3]=1081;
    assert(!overlay_valid(&overlay,1920,1080));
#endif
    puts("PASS native spatial handoff: identity, domain, dimensions and failed-fit rejection");
}
