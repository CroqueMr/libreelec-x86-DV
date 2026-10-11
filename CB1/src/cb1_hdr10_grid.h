/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_GRID_H
#define CB1_HDR10_GRID_H
#include "cb1_hdr10_extrema.h"
#include <libplacebo/opengl.h>
#include <GLES3/gl31.h>

/* Private GPU dependency. The extrema owner retains this texture until collection. */
#define CB1_HDR10_GRID_GLSL \
    "layout(binding=1)uniform highp sampler2D bound_input;" \
    "uniform uint deferred_bounds;uniform uvec2 dimensions;" \
    "uvec4 analysis_area(){if(deferred_bounds==0u)return input_area;" \
    "vec4 b=texelFetch(bound_input,ivec2(0),0);" \
    "if(any(isnan(b))||any(isinf(b))||b.x<0.0||b.x>16777215.0||b.y<0.0||b.y>16777215.0)" \
    "return uvec4(0u,0u,dimensions);" \
    "uvec2 lo=uvec2(uint(b.x)%4096u,uint(b.x)/4096u)," \
    "hi=uvec2(uint(b.y)%4096u,uint(b.y)/4096u)+1u;" \
    "if(any(greaterThanEqual(lo,hi))||any(greaterThan(hi,dimensions)))return uvec4(0u,0u,dimensions);" \
    "return uvec4(lo,hi);}"

static inline unsigned cb1_hdr10_grid_count(struct cb1_hdr10_bounds b)
{
    unsigned w=b.x1-b.x0,h=b.y1-b.y0,sx=w/256?w/256:1,sy=h/144?h/144:1;
    return ((w+sx-1)/sx)*((h+sy-1)/sy);
}
static inline bool cb1_hdr10_grid_valid(struct cb1_hdr10_bounds b,unsigned w,unsigned h)
{
    return b.x0<b.x1 && b.y0<b.y1 && b.x1<=w && b.y1<=h && b.minimum<=b.maximum;
}
static inline GLuint cb1_hdr10_grid_texture(pl_gpu gpu,pl_tex texture)
{
    if(!texture || !texture->params.sampleable || texture->params.d ||
       texture->params.w!=1 || texture->params.h!=1 ||
       texture->params.format->type!=PL_FMT_FLOAT || texture->params.format->num_components!=4)
        return 0;
    for(unsigned i=0;i<4;++i)if(texture->params.format->component_depth[i]<32)return 0;
    GLenum target=0;
    GLuint name=pl_opengl_unwrap(gpu,texture,&target,NULL,NULL);
    return target==GL_TEXTURE_2D?name:0;
}
#endif
