/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_hdr10_ingress.h"
#include "cb1_hdr10_filter.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/custom.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

/* The frozen FFmpeg 9.0 RGB48 producer uses BT.2020 coefficients rounded to
 * 13 fractional bits and a 255/256 RGB scale. These are analysis conventions,
 * not display adjustments. Source: libswscale/yuv2rgb.c and output.c. */
static const char header[]=
    "int sample_y(ivec2 p){return int(roundEven(texelFetch(Y_input,p+origin,0).r*65535.0))>>bit_shift;}"
    "ivec2 sample_uv(ivec2 p){vec2 q;"
    "p+=subsampled!=0u?origin/2:origin;if(packed!=0u)q=texelFetch(U_input,p,0).rg;"
    "else q=vec2(texelFetch(U_input,p,0).r,texelFetch(V_input,p,0).r);"
    "return ivec2(roundEven(q*65535.0))>>ivec2(bit_shift);}"
    "vec4 analysis_rgb(ivec2 p){int y=4*sample_y(p)-16*(1<<depth_shift)*4;ivec2 uv;"
    "if(subsampled!=0u){int row=p.y/2;"
    "int other=(p.y&1)!=0?min(row+1,int(height)/2-1):max(row-1,0);"
    "uv=3*sample_uv(ivec2(p.x/2,row))+sample_uv(ivec2(p.x/2,other));}"
    "else uv=4*sample_uv(p);uv-=ivec2(128*(1<<depth_shift)*4);"
    "int rounding_bias=1<<(depth_shift+6);int shift=depth_shift+7;"
    "ivec3 value=ivec3(y*9539+uv.y*13752,y*9539-uv.x*1535-uv.y*5328,y*9539+uv.x*17545);"
    "value=(value+ivec3(rounding_bias))>>ivec3(shift);"
    "return vec4(vec3(clamp(value,ivec3(0),ivec3(65535)))/65535.0,1.0);}";

struct cb1_hdr10_ingress {
    pl_gpu gpu;pl_dispatch dispatch;pl_tex texture, horizontal, small, filters[4];pl_fmt format;
    int width,height,subsampled,counts[4];
};

struct cb1_hdr10_ingress *cb1_hdr10_ingress_create(pl_gpu gpu)
{
    if (!gpu || !gpu->glsl.gles || gpu->glsl.version<300) return NULL;
    pl_fmt format=pl_find_fmt(gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
    if (!format) return NULL;
    struct cb1_hdr10_ingress *ctx=calloc(1,sizeof(*ctx));if (!ctx)return NULL;
    ctx->gpu=gpu;ctx->format=format;ctx->dispatch=pl_dispatch_create(gpu->log,gpu);
    if (!ctx->dispatch){free(ctx);return NULL;}return ctx;
}

void cb1_hdr10_ingress_destroy(struct cb1_hdr10_ingress **ctx)
{
    if (!ctx || !*ctx)return;
    pl_tex_destroy((*ctx)->gpu,&(*ctx)->texture);pl_dispatch_destroy(&(*ctx)->dispatch);
    pl_tex_destroy((*ctx)->gpu,&(*ctx)->horizontal);pl_tex_destroy((*ctx)->gpu,&(*ctx)->small);
    for(unsigned i=0;i<4;++i)pl_tex_destroy((*ctx)->gpu,&(*ctx)->filters[i]);
    free(*ctx);*ctx=NULL;
}

static enum cb1_ai_status admissible(struct cb1_hdr10_ingress *ctx,const struct pl_frame *source)
{
    if (!ctx || !source)return CB1_AI_INVALID;
    if (source->color.transfer!=PL_COLOR_TRC_PQ || source->color.primaries!=PL_COLOR_PRIM_BT_2020 ||
        source->repr.sys!=PL_COLOR_SYSTEM_BT_2020_NC || source->repr.levels!=PL_COLOR_LEVELS_LIMITED ||
        source->enhancement_layer || source->repr.dovi || source->num_overlays ||
        (source->num_planes!=2 && source->num_planes!=3) || source->repr.bits.sample_depth!=16 ||
        (source->repr.bits.color_depth!=10 && source->repr.bits.color_depth!=12) ||
        (source->repr.bits.bit_shift!=0 && source->repr.bits.bit_shift!=16-source->repr.bits.color_depth))
        return CB1_AI_INCOMPATIBLE;
    pl_tex y=source->planes[0].texture,u=source->planes[1].texture;
    if (!y || !u)return CB1_AI_INVALID;
    const int width=y->params.w,height=y->params.h;
    unsigned sub=u->params.w==width/2 && u->params.h==height/2,packed=source->num_planes==2;
    const struct pl_rect2df crop=source->crop;
    if (!isfinite(crop.x0) || !isfinite(crop.y0) || !isfinite(crop.x1) || !isfinite(crop.y1) ||
        crop.x0<0 || crop.y0<0 || crop.x1>width || crop.y1>height ||
        crop.x1<=crop.x0 || crop.y1<=crop.y0 || crop.x1-crop.x0>4096 || crop.y1-crop.y0>2160 ||
        floorf(crop.x0)!=crop.x0 || floorf(crop.y0)!=crop.y0 ||
        floorf(crop.x1)!=crop.x1 || floorf(crop.y1)!=crop.y1 ||
        (sub && (((int)crop.x0|(int)crop.y0|(int)crop.x1|(int)crop.y1|width|height)&1)) ||
        (!sub && (u->params.w!=width || u->params.h!=height)))
        return CB1_AI_INCOMPATIBLE;
    for (int i=0; i<source->num_planes; ++i) {
        const struct pl_plane *p=&source->planes[i];
        if (!p->texture || p->texture->params.d || !p->texture->params.sampleable || p->flipped ||
            p->shift_x!=0 || p->shift_y!=0 || p->component_mapping[0]!=i ||
            p->components!=(packed && i==1?2:1) ||
            p->texture->params.format->type!=PL_FMT_UNORM || p->texture->params.format->component_depth[0]!=16 ||
            p->texture->params.w!=(i?u->params.w:width) || p->texture->params.h!=(i?u->params.h:height))
            return CB1_AI_INCOMPATIBLE;
    }
    if (packed && source->planes[1].component_mapping[1]!=2)return CB1_AI_INCOMPATIBLE;
    return CB1_AI_READY;
}

enum cb1_ai_status cb1_hdr10_ingress_rgb(struct cb1_hdr10_ingress *ctx,
    const struct pl_frame *source,pl_tex *out)
{
    if(!out)return CB1_AI_INVALID;
    enum cb1_ai_status status=admissible(ctx,source);if(status!=CB1_AI_READY)return status;
    pl_tex y=source->planes[0].texture,u=source->planes[1].texture;
    const int width=(int)(source->crop.x1-source->crop.x0),height=(int)(source->crop.y1-source->crop.y0);
    int origin[2]={(int)source->crop.x0,(int)source->crop.y0};
    unsigned sub=u->params.w==y->params.w/2 && u->params.h==y->params.h/2,packed=source->num_planes==2;
    if (!pl_tex_recreate(ctx->gpu,&ctx->texture,pl_tex_params(.w=width,.h=height,
        .format=ctx->format,.sampleable=true,.renderable=true)))return CB1_AI_INCOMPATIBLE;
    struct pl_shader_desc descriptors[]={
        {.desc={.name="Y_input",.type=PL_DESC_SAMPLED_TEX},.binding={.object=y,.sample_mode=PL_TEX_SAMPLE_NEAREST}},
        {.desc={.name="U_input",.type=PL_DESC_SAMPLED_TEX},.binding={.object=u,.sample_mode=PL_TEX_SAMPLE_NEAREST}},
        {.desc={.name="V_input",.type=PL_DESC_SAMPLED_TEX},.binding={.object=packed?u:source->planes[2].texture,.sample_mode=PL_TEX_SAMPLE_NEAREST}}};
    char source_header[sizeof(header)+64];
    snprintf(source_header,sizeof(source_header),"%s%s",packed?"#define V_input U_input\n":"",header);
    int depth_shift=source->repr.bits.color_depth-8,bit_shift=source->repr.bits.bit_shift;
    unsigned h=(unsigned)height;
    struct pl_shader_var variables[]={
        {.var=pl_var_uint("subsampled"),.data=&sub,.dynamic=true},
        {.var=pl_var_uint("packed"),.data=&packed,.dynamic=true},
        {.var=pl_var_uint("height"),.data=&h,.dynamic=true},
        {.var=pl_var_int("depth_shift"),.data=&depth_shift,.dynamic=true},
        {.var=pl_var_int("bit_shift"),.data=&bit_shift,.dynamic=true},
        {.var={.name="origin",.type=PL_VAR_SINT,.dim_v=2,.dim_m=1,.dim_a=1},.data=origin,.dynamic=true}};
    pl_shader shader=pl_dispatch_begin(ctx->dispatch);
    bool ok=pl_shader_custom(shader,&(struct pl_custom_shader){.description="CB1 RGB48 analysis ingress",
        .header=source_header,.body="color=analysis_rgb(ivec2(gl_FragCoord.xy));",.output=PL_SHADER_SIG_COLOR,
        .descriptors=descriptors,.num_descriptors=packed?2:3,.variables=variables,.num_variables=6});
    if (ok)ok=pl_dispatch_finish(ctx->dispatch,pl_dispatch_params(.shader=&shader,.target=ctx->texture));
    pl_dispatch_abort(ctx->dispatch,&shader);
    if (!ok)return CB1_AI_INVALID;
    *out=ctx->texture;return CB1_AI_READY;
}

static bool filters_prepare(struct cb1_hdr10_ingress *ctx,int width,int height,bool sub)
{
    if(ctx->width==width && ctx->height==height && ctx->subsampled==sub)return true;
    pl_fmt fmt=pl_find_fmt(ctx->gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE);
    if(!fmt)return false;
    const int sources[]={width,sub?width/2:width,height,sub?height/2:height};
    const int targets[]={128,sub?64:128,72,72};
    for(unsigned n=0;n<4;++n){
        struct cb1_hdr10_filter f={0};
        if(!cb1_hdr10_filter_build(sources[n],targets[n],n<2?14:12,&f))return false;
        float *data=calloc((size_t)(f.size+1)*f.length,sizeof(*data));
        if(!data){cb1_hdr10_filter_free(&f);return false;}
        for(int i=0;i<f.length;++i){
            data[i*(f.size+1)]=(float)f.positions[i];
            for(int j=0;j<f.size;++j)data[i*(f.size+1)+j+1]=(float)f.weights[i*f.size+j];
        }
        pl_tex_destroy(ctx->gpu,&ctx->filters[n]);
        ctx->filters[n]=pl_tex_create(ctx->gpu,pl_tex_params(.w=f.size+1,.h=f.length,
            .format=fmt,.sampleable=true,.initial_data=data));
        ctx->counts[n]=f.size;free(data);cb1_hdr10_filter_free(&f);
        if(!ctx->filters[n]){ctx->width=0;return false;}
    }
    ctx->width=width;ctx->height=height;ctx->subsampled=sub;return true;
}

/* Integer intermediate rounding follows the frozen RGB48 producer. */
static const char small_header[]=
    "int coefficient(highp sampler2D f,int tap,int row){return int(texelFetch(f,ivec2(tap,row),0).r);}"
    "vec4 horizontal_rgb(ivec2 p){int y=0;ivec2 uv=ivec2(0);"
    "int start=coefficient(HY,0,p.x);"
    "for(int j=0;j<hy_count;j++)y+=sample_y(ivec2(start+j,p.y))*coefficient(HY,j+1,p.x);"
    "int x=subsampled!=0u?p.x/2:p.x;start=coefficient(HC,0,x);"
    "for(int j=0;j<hc_count;j++)uv+=sample_uv(ivec2(start+j,min(p.y,int(height)/(subsampled!=0u?2:1)-1)))*coefficient(HC,j+1,x);"
    "return vec4(float(min(y>>(depth_shift+3),524287)),"
    "vec2(min(uv>>ivec2(depth_shift+3),ivec2(524287))),1);}"
    "vec4 vertical_rgb(ivec2 p){int y=0;ivec2 uv=ivec2(0);"
    "int start=coefficient(VY,0,p.y);"
    "for(int j=0;j<vy_count;j++)y+=int(texelFetch(intermediate,ivec2(p.x,start+j),0).r)*coefficient(VY,j+1,p.y);"
    "start=coefficient(VC,0,p.y);"
    "for(int j=0;j<vc_count;j++)uv+=ivec2(texelFetch(intermediate,ivec2(p.x,start+j),0).gb)*coefficient(VC,j+1,p.y);"
    "y=(y>>14)-8192;uv=(uv>>ivec2(14))-ivec2(65536);"
    "ivec3 rgb=ivec3(y*9539+uv.y*13752,y*9539-uv.x*1535-uv.y*5328,y*9539+uv.x*17545);"
    "vec3 value=vec3(clamp((rgb+ivec3(8192))>>ivec3(14),ivec3(0),ivec3(65535)))/65535.0;"
    "vec2 rg=unpackHalf2x16(packHalf2x16(value.rg));"
    "float b=unpackHalf2x16(packHalf2x16(value.bb)).x;return vec4(rg,b,1);}";

enum cb1_ai_status cb1_hdr10_ingress_small(struct cb1_hdr10_ingress *ctx,
    const struct pl_frame *source,pl_tex *out)
{
    if(!out)return CB1_AI_INVALID;
    enum cb1_ai_status status=admissible(ctx,source);if(status!=CB1_AI_READY)return status;
    int width=(int)(source->crop.x1-source->crop.x0),height=(int)(source->crop.y1-source->crop.y0);
    int origin[2]={(int)source->crop.x0,(int)source->crop.y0};
    unsigned sub=source->planes[1].texture->params.w==source->planes[0].texture->params.w/2,
        packed=source->num_planes==2,h=(unsigned)height;
    if(!filters_prepare(ctx,width,height,sub))return CB1_AI_INCOMPATIBLE;
    pl_fmt fmt=pl_find_fmt(ctx->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
    if(!fmt || !pl_tex_recreate(ctx->gpu,&ctx->horizontal,pl_tex_params(.w=128,.h=height,.format=fmt,.sampleable=true,.renderable=true)) ||
        !pl_tex_recreate(ctx->gpu,&ctx->small,pl_tex_params(.w=128,.h=72,.format=fmt,.sampleable=true,.renderable=true)))return CB1_AI_INCOMPATIBLE;
    struct pl_shader_desc descriptors[8];const char *names[]={"Y_input","U_input","V_input","HY","HC","VY","VC","intermediate"};
    pl_tex textures[]={source->planes[0].texture,source->planes[1].texture,packed?source->planes[1].texture:source->planes[2].texture,
        ctx->filters[0],ctx->filters[1],ctx->filters[2],ctx->filters[3],ctx->horizontal};
    for(unsigned i=0;i<8;++i)descriptors[i]=(struct pl_shader_desc){.desc={.name=names[i],.type=PL_DESC_SAMPLED_TEX},
        .binding={.object=textures[i],.sample_mode=PL_TEX_SAMPLE_NEAREST}};
    unsigned descriptor_count=8;
    if(packed){for(unsigned i=2;i<7;++i)descriptors[i]=descriptors[i+1];descriptor_count=7;}
    char source_header[sizeof(header)+64];
    snprintf(source_header,sizeof(source_header),"%s%s",packed?"#define V_input U_input\n":"",header);
    int depth_shift=source->repr.bits.color_depth-8,bit_shift=source->repr.bits.bit_shift;
    struct pl_shader_var variables[]={
        {.var=pl_var_uint("subsampled"),.data=&sub,.dynamic=true},
        {.var=pl_var_uint("packed"),.data=&packed,.dynamic=true},
        {.var=pl_var_uint("height"),.data=&h,.dynamic=true},
        {.var=pl_var_int("depth_shift"),.data=&depth_shift,.dynamic=true},
        {.var=pl_var_int("bit_shift"),.data=&bit_shift,.dynamic=true},
        {.var=pl_var_int("hy_count"),.data=&ctx->counts[0],.dynamic=true},
        {.var=pl_var_int("hc_count"),.data=&ctx->counts[1],.dynamic=true},
        {.var=pl_var_int("vy_count"),.data=&ctx->counts[2],.dynamic=true},
        {.var=pl_var_int("vc_count"),.data=&ctx->counts[3],.dynamic=true},
        {.var={.name="origin",.type=PL_VAR_SINT,.dim_v=2,.dim_m=1,.dim_a=1},.data=origin,.dynamic=true}};
    /* Both passes share declarations; the horizontal pass must not sample its own target. */
    descriptors[descriptor_count-1].binding.object=ctx->small;
    for(unsigned pass=0;pass<2;++pass){
        if(pass)descriptors[descriptor_count-1].binding.object=ctx->horizontal;
        pl_shader shader=pl_dispatch_begin(ctx->dispatch);
        bool ok=pl_shader_custom(shader,&(struct pl_custom_shader){.description="CB1 source-plane analysis downsample",
            .header=source_header,.body="",.output=PL_SHADER_SIG_NONE,.descriptors=descriptors,.num_descriptors=descriptor_count,
            .variables=variables,.num_variables=10});
        if(ok)ok=pl_shader_custom(shader,&(struct pl_custom_shader){.header=small_header,
            .body=pass?"color=vertical_rgb(ivec2(gl_FragCoord.xy));":"color=horizontal_rgb(ivec2(gl_FragCoord.xy));",
            .output=PL_SHADER_SIG_COLOR});
        if(ok)ok=pl_dispatch_finish(ctx->dispatch,pl_dispatch_params(.shader=&shader,.target=pass?ctx->small:ctx->horizontal));
        pl_dispatch_abort(ctx->dispatch,&shader);if(!ok)return CB1_AI_INVALID;
    }
    *out=ctx->small;return CB1_AI_READY;
}
