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
    struct dvbridge_renderer r={0};
    struct witness w={.outcome=1,.fitted=&fitted};
    dvbridge_renderer_set_spatial_fit(&r,fit,&w);
    bool applied=true;
    assert(fit_picture(&r,&source,&source,&out,&applied) && !applied && !w.calls);
    assert(fit_picture(&r,&source,&target,&out,&applied) && applied && w.calls==1);
    assert(w.input.planes[0].texture==&input && out.planes[0].texture==&fitted);
    assert(out.repr.sys==source.repr.sys && out.color.transfer==PL_COLOR_TRC_PQ);
    w.outcome=0;
    assert(!fit_picture(&r,&source,&target,&out,&applied) && w.calls==2);
    w.outcome=2;
    assert(!fit_picture(&r,&source,&target,&out,&applied));
    w.outcome=3;
    assert(!fit_picture(&r,&source,&target,&out,&applied));
    w.outcome=1;fitted.params.w=1920;
    assert(!fit_picture(&r,&source,&target,&out,&applied));
    fitted.params.w=3840;
    fitted.params.format=&rgb8;
    assert(!fit_picture(&r,&source,&target,&out,&applied));
    fitted.params.format=&fp32;
    source.num_planes=2;
    assert(!fit_picture(&r,&source,&target,&out,&applied));
    dvbridge_renderer_set_spatial_fit(&r,NULL,NULL);
    assert(fit_picture(&r,&source,&target,&out,&applied) && !applied);
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
