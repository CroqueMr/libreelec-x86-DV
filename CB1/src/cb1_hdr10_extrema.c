/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_hdr10_extrema.h"
#include "cb1_hdr10_ingress.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/custom.h>
#include <libplacebo/opengl.h>
#include <GLES3/gl3.h>
#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

/* Coordinates packed as exact 24-bit integers in RGBA32F, never color-mapped. */
static const char header[] =
    "uvec2 unpack_xy(float q){uint v=uint(q);return uvec2(v%4096u,v/4096u);}\n"
    "float pack_xy(uvec2 p){return float(p.x+4096u*p.y);}\n"
    "void merge_record(vec4 r,inout uvec2 lo,inout uvec2 hi,inout float low,inout float high,inout bool bad){"
    "if(r.x>=0.0){lo=min(lo,unpack_xy(r.x));hi=max(hi,unpack_xy(r.y));}"
    "bad=bad||r.z<0.0;low=min(low,r.z);high=max(high,r.w);}\n";
static const char scan_body[] =
    "uint group=uint(gl_FragCoord.x)+output_width*uint(gl_FragCoord.y);"
    "uvec2 lo=uvec2(4096u),hi=uvec2(0u);float low=65535.0,high=0.0;bool bad=false;"
    "uvec2 begin=uvec2(0u),end=dimensions;vec4 bounds=texelFetch(bound_input,ivec2(0),0);"
    "if(cropped!=0u && bounds.x>=0.0){begin=unpack_xy(bounds.x);end=unpack_xy(bounds.y)+1u;}"
    "bool full=cropped!=0u && all(equal(begin,uvec2(0u))) && all(equal(end,dimensions));"
    "if(full){color=bounds;}else{"
    /* Adjacent fragments fetch adjacent pixels; every code is still reduced exactly. */
    "uint stride=(count+127u)/128u;uvec2 step=uvec2(stride%dimensions.x,stride/dimensions.x);"
    "uvec2 position=uvec2(group%dimensions.x,group/dimensions.x);"
    "for(uint i=0u;i<128u;i++){uint index=group+i*stride;if(index>=count)break;"
    "uvec2 p=position;position+=step;if(position.x>=dimensions.x){position.x-=dimensions.x;position.y++;}"
    "if(cropped!=0u && (any(lessThan(p,begin))||any(greaterThanEqual(p,end))))continue;"
    "vec3 q=texelFetch(pq_input,ivec2(p),0).rgb;"
    "if(any(isnan(q))||any(isinf(q))||any(lessThan(q,vec3(0.0)))||any(greaterThan(q,vec3(1.0)))){bad=true;continue;}"
    "vec3 code=roundEven(q*65535.0);float minimum=min(code.r,min(code.g,code.b)),maximum=max(code.r,max(code.g,code.b));"
    "low=min(low,minimum);high=max(high,maximum);"
    "if(cropped!=0u || maximum>1.0){lo=min(lo,p);hi=max(hi,p);}}"
    "bad=bad||(cropped!=0u && bounds.z<0.0);"
    "color=vec4(lo.x==4096u?-1.0:pack_xy(lo),pack_xy(hi),bad?-1.0:low,high);}";
static const char tiled_scan_body[] =
    "uint group=uint(gl_FragCoord.x)+output_width*uint(gl_FragCoord.y);"
    "uvec2 lo=uvec2(4096u),hi=uvec2(0u);float low=65535.0,high=0.0;bool bad=false;"
    "uint columns=(dimensions.x+15u)/16u,rows=(dimensions.y+1u)/2u;"
    "if(group>=columns*rows){color=vec4(-1.0,0.0,65535.0,0.0);}else{"
    "uvec2 tile_begin=uvec2(group%columns,group/columns)*uvec2(16u,2u);"
    "uvec2 tile_end=min(tile_begin+uvec2(16u,2u),dimensions);"
    "uvec2 begin=uvec2(0u),end=dimensions;vec4 bounds=texelFetch(bound_input,ivec2(0),0);"
    "if(cropped!=0u && bounds.x>=0.0){begin=unpack_xy(bounds.x);end=unpack_xy(bounds.y)+1u;}"
    "bool full=cropped!=0u && all(equal(begin,uvec2(0u))) && all(equal(end,dimensions));"
    "bool outside=any(greaterThanEqual(tile_begin,end))||any(lessThanEqual(tile_end,begin));"
    "bool enclosed=all(greaterThanEqual(tile_begin,begin))&&all(lessThanEqual(tile_end,end));"
    "if(full){color=bounds;}else if(cropped!=0u && outside){color=vec4(-1.0,0.0,bounds.z<0.0?-1.0:65535.0,0.0);}"
    "else if(cropped!=0u && (enclosed"
#ifdef CB1_PROBE_TILED_UNCLIPPED
    "||true"
#endif
    ")){vec4 r=texelFetch(tile_input,ivec2(group%output_width,group/output_width),0);"
    "color=vec4(pack_xy(tile_begin),pack_xy(tile_end-1u),bounds.z<0.0?-1.0:r.z,r.w);}else{"
    "for(uint i=0u;i<32u;i++){uvec2 p=tile_begin+uvec2(i%16u,i/16u);"
    "if(any(greaterThanEqual(p,tile_end)))continue;"
    "if(cropped!=0u && (any(lessThan(p,begin))||any(greaterThanEqual(p,end))))continue;"
    "vec3 q=texelFetch(pq_input,ivec2(p),0).rgb;"
    "if(any(isnan(q))||any(isinf(q))||any(lessThan(q,vec3(0.0)))||any(greaterThan(q,vec3(1.0)))){bad=true;continue;}"
    "vec3 code=roundEven(q*65535.0);float minimum=min(code.r,min(code.g,code.b)),maximum=max(code.r,max(code.g,code.b));"
    "low=min(low,minimum);high=max(high,maximum);"
    "if(cropped!=0u || maximum>1.0){lo=min(lo,p);hi=max(hi,p);}}"
    "bad=bad||(cropped!=0u && bounds.z<0.0);"
    "color=vec4(lo.x==4096u?-1.0:pack_xy(lo),pack_xy(hi),bad?-1.0:low,high);}}";
static const char reduce_body[] =
    "uint group=uint(gl_FragCoord.x)+output_width*uint(gl_FragCoord.y);"
    "uvec2 lo=uvec2(4096u),hi=uvec2(0u);float low=65535.0,high=0.0;bool bad=false;"
    "uint stride=coalesced!=0u?(count+127u)/128u:1u;uint start=coalesced!=0u?group:group*128u;"
    "uvec2 position=uvec2(start%input_width,start/input_width),step=uvec2(stride%input_width,stride/input_width);"
    "for(uint i=0u;i<128u;i++){uint index=start+i*stride;if(index>=count)break;"
    "vec4 r=texelFetch(pq_input,ivec2(position),0);"
    "\n#ifdef CB1_COMPACT_INPUT\nr=unpack_record(r,position*uvec2(SOURCE_TILE,2u));\n#endif\n"
    "merge_record(r,lo,hi,low,high,bad);"
    "position+=step;if(position.x>=input_width){position.x-=input_width;position.y++;}}"
    "color=vec4(lo.x==4096u?-1.0:pack_xy(lo),pack_xy(hi),bad?-1.0:low,high);";

static const char direct_codes[]=
    "void mark_code(ivec3 code,uvec2 p,inout uvec2 lo,inout uvec2 hi,inout float low,inout float high){"
    "int minimum=min(code.r,min(code.g,code.b)),maximum=max(code.r,max(code.g,code.b));"
    "low=min(low,float(minimum));high=max(high,float(maximum));"
    "if(maximum>1){lo=min(lo,p);hi=max(hi,p);}}";
static const char direct_tile_body[]=
    "uint group=uint(gl_FragCoord.x)+output_width*uint(gl_FragCoord.y);"
    "uint columns=(dimensions.x+SOURCE_TILE-1u)/SOURCE_TILE,rows=(dimensions.y+1u)/2u;"
    "uvec2 lo=uvec2(4096u),hi=uvec2(0u);float low=65535.0,high=0.0;"
    "if(group<columns*rows){uvec2 tb=uvec2(gl_FragCoord.xy)*uvec2(SOURCE_TILE,2u);"
    "int row=int(tb.y)/2,last=int(height)/2-1;"
    "\n#ifdef CB1_SOURCE_GATHER\n"
    "vec2 uv_pos=vec2(ivec2(int(tb.x)/2,row)+origin/2)+vec2(1.0,0.0);"
    "vec2 uv_size=vec2(textureSize(U_input,0));"
    "ivec4 ua=ivec4(roundEven(textureGather(U_input,uv_pos/uv_size,0)*65535.0))>>ivec4(bit_shift);"
    "ivec4 va=ivec4(roundEven((source_packed!=0u?textureGather(U_input,uv_pos/uv_size,1):textureGather(V_input,uv_pos/uv_size,0))*65535.0))>>ivec4(bit_shift);"
    "uv_pos.y+=1.0;"
    "ivec4 ub=ivec4(roundEven(textureGather(U_input,uv_pos/uv_size,0)*65535.0))>>ivec4(bit_shift);"
    "ivec4 vb=ivec4(roundEven((source_packed!=0u?textureGather(U_input,uv_pos/uv_size,1):textureGather(V_input,uv_pos/uv_size,0))*65535.0))>>ivec4(bit_shift);"
    "ivec2 up_u=row>0?ua.wz:ua.xy,up_v=row>0?va.wz:va.xy;"
    "ivec2 down_u=row<last?ub.xy:ua.xy,down_v=row<last?vb.xy:va.xy;"
    "ivec2 even_pair[2]=ivec2[2](3*ivec2(ua.x,va.x)+ivec2(up_u.x,up_v.x),3*ivec2(ua.y,va.y)+ivec2(up_u.y,up_v.y));"
    "ivec2 odd_pair[2]=ivec2[2](3*ivec2(ua.x,va.x)+ivec2(down_u.x,down_v.x),3*ivec2(ua.y,va.y)+ivec2(down_u.y,down_v.y));"
    "\n#endif\n"
    "for(uint i=0u;i<SOURCE_TILE/2u;i++){uint x=tb.x+2u*i;if(x>=dimensions.x)break;"
    "\n#ifdef CB1_SOURCE_GATHER\n"
    "ivec2 yp=ivec2(x,tb.y)+origin;"
    "ivec4 ys=ivec4(roundEven(textureGather(Y_input,(vec2(yp)+1.0)/vec2(textureSize(Y_input,0)),0)*65535.0))>>ivec4(bit_shift);"
    "\n#else\n"
    "ivec4 ys=ivec4(sample_y(ivec2(x,tb.y+1u)),sample_y(ivec2(x+1u,tb.y+1u)),"
    "sample_y(ivec2(x+1u,tb.y)),sample_y(ivec2(x,tb.y)));"
    "\n#endif\n"
    "\n#ifdef CB1_SOURCE_GATHER\n"
    "ivec2 even=even_pair[i],odd=odd_pair[i];"
    "\n#else\n"
    "ivec2 uv=sample_uv(ivec2(int(x)/2,row));"
    "ivec2 even=3*uv+sample_uv(ivec2(int(x)/2,max(row-1,0)));"
    "ivec2 odd=3*uv+sample_uv(ivec2(int(x)/2,min(row+1,last)));"
    "\n#endif\n"
    "mark_code(analysis_code(ys.w,even),uvec2(x,tb.y),lo,hi,low,high);"
    "mark_code(analysis_code(ys.z,even),uvec2(x+1u,tb.y),lo,hi,low,high);"
    "mark_code(analysis_code(ys.x,odd),uvec2(x,tb.y+1u),lo,hi,low,high);"
    "mark_code(analysis_code(ys.y,odd),uvec2(x+1u,tb.y+1u),lo,hi,low,high);}}"
    "\n#ifdef CB1_COMPACT_OUTPUT\n"
    "uvec2 tb=uvec2(gl_FragCoord.xy)*uvec2(SOURCE_TILE,2u);"
    "uint local=lo.x==4096u?0u:1u+(lo.x-tb.x)+SOURCE_TILE*(lo.y-tb.y)+2u*SOURCE_TILE*(hi.x-tb.x)+2u*SOURCE_TILE*SOURCE_TILE*(hi.y-tb.y);"
    "color=vec4(float(local),low,high,0.0)/65535.0;"
    "\n#else\ncolor=vec4(lo.x==4096u?-1.0:pack_xy(lo),pack_xy(hi),low,high);\n#endif\n";

static const char crop_reduce_body[] =
    "uint group=uint(gl_FragCoord.x)+output_width*uint(gl_FragCoord.y);"
    "vec4 bounds=texelFetch(bound_input,ivec2(0),0);"
    "uvec2 begin=uvec2(0u),end=dimensions;"
    "if(bounds.x>=0.0){begin=unpack_xy(bounds.x);end=unpack_xy(bounds.y)+1u;}"
    "bool full=all(equal(begin,uvec2(0u))) && all(equal(end,dimensions));"
    "if(full){color=bounds;}else{"
    "uvec2 lo=uvec2(4096u),hi=uvec2(0u);float low=65535.0,high=0.0;bool bad=bounds.z<0.0;"
    "uint columns=(dimensions.x+SOURCE_TILE-1u)/SOURCE_TILE,tile_width=uint(textureSize(tile_input,0).x);"
    "for(uint n=0u;n<128u;n++){uint index=coalesced!=0u?group+n*((count+127u)/128u):group*128u+n;if(index>=count)break;"
    "uvec2 tb=uvec2(index%columns,index/columns)*uvec2(SOURCE_TILE,2u);"
    "uvec2 te=min(tb+uvec2(SOURCE_TILE,2u),dimensions);"
    "if(any(greaterThanEqual(tb,end)) || any(lessThanEqual(te,begin)))continue;"
    "if(all(greaterThanEqual(tb,begin)) && all(lessThanEqual(te,end))){"
    "vec4 r=texelFetch(tile_input,ivec2(index%tile_width,index/tile_width),0);"
    "\n#ifdef CB1_COMPACT_CROP\nr=unpack_record(r,tb);\n#endif\n"
    "merge_record(vec4(pack_xy(tb),pack_xy(te-1u),r.z,r.w),lo,hi,low,high,bad);"
    "}else{"
    "for(uint i=0u;i<2u*SOURCE_TILE;i++){uvec2 p=tb+uvec2(i%SOURCE_TILE,i/SOURCE_TILE);"
    "if(any(greaterThanEqual(p,te)) || any(lessThan(p,begin)) || any(greaterThanEqual(p,end)))continue;"
    "vec3 q=source_at(p);"
    "if(any(isnan(q))||any(isinf(q))||any(lessThan(q,vec3(0.0)))||any(greaterThan(q,vec3(1.0)))){bad=true;continue;}"
    "vec3 code=roundEven(q*65535.0);"
    "low=min(low,min(code.r,min(code.g,code.b)));high=max(high,max(code.r,max(code.g,code.b)));"
    "lo=min(lo,p);hi=max(hi,p);}}}"
    "color=vec4(lo.x==4096u?-1.0:pack_xy(lo),pack_xy(hi),bad?-1.0:low,high);}";


struct cb1_hdr10_extrema {
    pl_gpu gpu;
    pl_dispatch dispatch;
    pl_tex scan, cropped_scan, temporary[2], bounds, final;
    GLuint result, framebuffer;
    GLsync fence;
    pl_fmt format;
    unsigned width, height;
    struct cb1_ai_identity id;
    uint64_t stream, revision;
    bool pending, failed, active, tiled, coalesced, compact;
};

/* GLES buffer transfers are not exposed by the matched libplacebo backend.
 * Isolate the 16-byte PBO/fence bridge without changing renderer capabilities. */
static bool download(struct cb1_hdr10_extrema *ctx)
{
    GLint framebuffer, buffer, alignment, row_length, skip_rows, skip_pixels;
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &framebuffer);
    glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING, &buffer);
    glGetIntegerv(GL_PACK_ALIGNMENT, &alignment);
    glGetIntegerv(GL_PACK_ROW_LENGTH, &row_length);
    glGetIntegerv(GL_PACK_SKIP_ROWS, &skip_rows);
    glGetIntegerv(GL_PACK_SKIP_PIXELS, &skip_pixels);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, ctx->framebuffer);
    glFramebufferTexture2D(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D,
        pl_opengl_unwrap(ctx->gpu, ctx->final, NULL, NULL, NULL), 0);
    bool ok = glCheckFramebufferStatus(GL_READ_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE;
    if (ok) {
        glBindBuffer(GL_PIXEL_PACK_BUFFER, ctx->result);
        glPixelStorei(GL_PACK_ALIGNMENT, 4);
        glPixelStorei(GL_PACK_ROW_LENGTH, 0);
        glPixelStorei(GL_PACK_SKIP_ROWS, 0);
        glPixelStorei(GL_PACK_SKIP_PIXELS, 0);
        glReadPixels(0, 0, 1, 1, GL_RGBA, GL_FLOAT, NULL);
        ctx->fence = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
        ok = ctx->fence && glGetError() == GL_NO_ERROR;
        glFlush();
    }
    glPixelStorei(GL_PACK_ALIGNMENT, alignment);
    glPixelStorei(GL_PACK_ROW_LENGTH, row_length);
    glPixelStorei(GL_PACK_SKIP_ROWS, skip_rows);
    glPixelStorei(GL_PACK_SKIP_PIXELS, skip_pixels);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, (GLuint)buffer);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, (GLuint)framebuffer);
    return ok && glGetError() == GL_NO_ERROR;
}

static bool dispatch(struct cb1_hdr10_extrema *ctx, pl_tex input, pl_tex output,
                     unsigned count, bool scan, bool cropped,const struct pl_frame *source)
{
    struct pl_shader_desc descriptors[3] = {
        {.desc={.name="pq_input",.type=PL_DESC_SAMPLED_TEX},
         .binding={.object=input,.sample_mode=PL_TEX_SAMPLE_NEAREST}},
        {.desc={.name="bound_input",.type=PL_DESC_SAMPLED_TEX},
         .binding={.object=ctx->bounds,.sample_mode=PL_TEX_SAMPLE_NEAREST}},
    };
    unsigned size[2] = {ctx->width, ctx->height}, crop = cropped, coalesced=ctx->coalesced;
    unsigned input_width = (unsigned)input->params.w, output_width = (unsigned)output->params.w;
    struct pl_shader_var uniforms[] = {
        {.var=pl_var_uvec2("dimensions"),.data=size,.dynamic=true},
        {.var=pl_var_uint("cropped"),.data=&crop,.dynamic=true},
        {.var=pl_var_uint("count"),.data=&count,.dynamic=true},
        {.var=pl_var_uint("input_width"),.data=&input_width,.dynamic=true},
        {.var=pl_var_uint("output_width"),.data=&output_width,.dynamic=true},
        {.var=pl_var_uint("coalesced"),.data=&coalesced,.dynamic=true},
    };
    unsigned descriptor_count=scan?2:1;
    if(source && scan){descriptors[0]=descriptors[1];descriptor_count=1;}
    char aliased_header[sizeof(header)+64];
    const char *shader_header=header;
    if (scan && ctx->tiled && !cropped && !source) {
        snprintf(aliased_header,sizeof(aliased_header),"#define tile_input bound_input\n%s",header);
        shader_header=aliased_header;
    }
    if (scan && ctx->tiled && cropped) descriptors[descriptor_count++]=(struct pl_shader_desc){
        .desc={.name="tile_input",.type=PL_DESC_SAMPLED_TEX},
        .binding={.object=ctx->scan,.sample_mode=PL_TEX_SAMPLE_NEAREST}};
    static const char decode[]=
        "vec4 unpack_record(vec4 r,uvec2 tb){uvec3 code=uvec3(roundEven(r.rgb*65535.0));"
        "if(code.x==0u)return vec4(-1.0,0.0,float(code.y),float(code.z));"
        "uint v=code.x-1u;"
        "uvec2 lo=tb+uvec2(v&(SOURCE_TILE-1u),(v>>SOURCE_BITS)&1u),hi=tb+uvec2((v>>(SOURCE_BITS+1u))&(SOURCE_TILE-1u),(v>>(2u*SOURCE_BITS+1u))&1u);"
        "return vec4(pack_xy(lo),pack_xy(hi),float(code.y),float(code.z));}";
    char compact_header[sizeof(header)+sizeof(decode)+192];
    if(ctx->compact){
        snprintf(compact_header,sizeof(compact_header),"%s%s%s%s%s",
            source && scan && !cropped?"#define CB1_COMPACT_OUTPUT 1\n":"",
            input==ctx->scan && !scan?"#define CB1_COMPACT_INPUT 1\n":"",
            source && cropped?"#define CB1_COMPACT_CROP 1\n":"",shader_header,decode);
        shader_header=compact_header;
    }
    char source_header[sizeof(compact_header)+128];
    bool gather=source && ctx->gpu->glsl.version>=310;
    if(source)for(int p=0;p<source->num_planes;p++)
        gather=gather && source->planes[p].texture->params.format->gatherable;
    snprintf(source_header,sizeof(source_header),"#define SOURCE_TILE 4u\n#define SOURCE_BITS 2u\n%s%s",
        gather?"#define CB1_SOURCE_GATHER 1\n":"",shader_header);
    shader_header=source_header;
    pl_shader shader = pl_dispatch_begin(ctx->dispatch);
    bool ok = !source || !scan || cb1_hdr10_ingress_source_shader(shader,source);
    if(ok && source && scan)ok=pl_shader_custom(shader,&(struct pl_custom_shader){
        .header=direct_codes,.prelude="#define source_at(p) analysis_rgb(ivec2(p)).rgb\n",.output=PL_SHADER_SIG_NONE});
    if(ok)ok = pl_shader_custom(shader, &(struct pl_custom_shader){
        .description="CB1 HDR10 integer bounds",.header=shader_header,.body=source && scan?(cropped?crop_reduce_body:direct_tile_body):scan?(ctx->tiled?tiled_scan_body:scan_body):reduce_body,
        .output=PL_SHADER_SIG_COLOR,.descriptors=descriptors,.num_descriptors=descriptor_count,
        .variables=uniforms,.num_variables=6});
    if (ok) ok = pl_dispatch_finish(ctx->dispatch, pl_dispatch_params(.shader=&shader,.target=output));
    pl_dispatch_abort(ctx->dispatch, &shader);
    return ok;
}

static bool allocate(struct cb1_hdr10_extrema *ctx, pl_tex *texture, unsigned count)
{
    unsigned width = count < 256 ? count : 256;
    return pl_tex_recreate(ctx->gpu, texture, pl_tex_params(.w=(int)width,
        .h=(int)((count+width-1)/width),.format=ctx->format,.sampleable=true,
        .renderable=true,.host_readable=count==1));
}

static bool reduce(struct cb1_hdr10_extrema *ctx, pl_tex input, unsigned count, pl_tex final)
{
    unsigned next = 0;
    while (count > 1) {
        unsigned groups = (count+127)/128;
        if (groups != 1 && !allocate(ctx, &ctx->temporary[next], groups)) return false;
        pl_tex output = groups == 1 ? final : ctx->temporary[next];
        if (!dispatch(ctx, input, output, count, false, false,NULL)) return false;
        input = output;
        next ^= 1;
        count = groups;
    }
    /* A one-group scan still needs an exact copy into its separate final target. */
    if (input != final && !dispatch(ctx, input, final, 1, false, false,NULL)) return false;
    return true;
}

struct cb1_hdr10_extrema *cb1_hdr10_extrema_create(pl_gpu gpu)
{
    pl_opengl gl = gpu ? pl_opengl_get(gpu) : NULL;
    if (!gl || !gpu->glsl.gles || gpu->glsl.version < 300 || glGetError() != GL_NO_ERROR) return NULL;
    pl_fmt format = pl_find_fmt(gpu, PL_FMT_FLOAT, 4, 32, 32,
        PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_HOST_READABLE);
    if (!format) return NULL;
    struct cb1_hdr10_extrema *ctx = calloc(1, sizeof(*ctx));
    if (!ctx) return NULL;
    ctx->gpu = gpu; ctx->format = format;
    ctx->dispatch = pl_dispatch_create(gpu->log, gpu);
    const float empty[4] = {-1,0,0,0};
    ctx->bounds = pl_tex_create(gpu, pl_tex_params(.w=1,.h=1,.format=format,
        .sampleable=true,.renderable=true,.initial_data=empty));
    ctx->final = pl_tex_create(gpu, pl_tex_params(.w=1,.h=1,.format=format,
        .sampleable=true,.renderable=true,.host_readable=true));
    GLint buffer;
    glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING, &buffer);
    glGenBuffers(1, &ctx->result);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, ctx->result);
    glBufferData(GL_PIXEL_PACK_BUFFER, 16, NULL, GL_STREAM_READ);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, (GLuint)buffer);
    glGenFramebuffers(1, &ctx->framebuffer);
    if (!ctx->dispatch || !ctx->bounds || !ctx->final || !ctx->result ||
        !ctx->framebuffer || glGetError() != GL_NO_ERROR) {
        cb1_hdr10_extrema_destroy(&ctx); return NULL;
    }
    return ctx;
}

void cb1_hdr10_extrema_destroy(struct cb1_hdr10_extrema **ctx)
{
    if (!ctx || !*ctx) return;
    pl_dispatch_destroy(&(*ctx)->dispatch);
    for (unsigned i = 0; i < 2; ++i) pl_tex_destroy((*ctx)->gpu, &(*ctx)->temporary[i]);
    pl_tex_destroy((*ctx)->gpu, &(*ctx)->scan);
    pl_tex_destroy((*ctx)->gpu, &(*ctx)->cropped_scan);
    pl_tex_destroy((*ctx)->gpu, &(*ctx)->bounds);
    pl_tex_destroy((*ctx)->gpu, &(*ctx)->final);
    if ((*ctx)->fence) glDeleteSync((*ctx)->fence);
    glDeleteFramebuffers(1, &(*ctx)->framebuffer);
    glDeleteBuffers(1, &(*ctx)->result);
    free(*ctx); *ctx = NULL;
}

void cb1_hdr10_extrema_reset(struct cb1_hdr10_extrema *ctx, uint64_t stream, uint64_t revision)
{
    if (!ctx) return;
    if (ctx->fence) glDeleteSync(ctx->fence);
    ctx->fence = NULL;
    ctx->pending = false;
    ctx->stream = stream;
    ctx->revision = revision;
    ctx->active = true;
}

bool cb1_hdr10_extrema_set_coalesced(struct cb1_hdr10_extrema *ctx,bool enabled)
{
    if(!ctx || ctx->pending)return false;
    ctx->coalesced=enabled;return true;
}

static enum cb1_ai_status submit(struct cb1_hdr10_extrema *ctx,pl_tex texture,
    const struct pl_frame *source,struct cb1_ai_identity id)
{
    if(!ctx || ctx->failed || !ctx->active || id.stream!=ctx->stream || id.revision!=ctx->revision)
        return CB1_AI_INVALID;
    if(!source){
        if (!texture || !texture->params.sampleable || texture->params.d ||
            texture->params.w < 1 || texture->params.h < 1 ||
            texture->params.w > 4096 || texture->params.h > 4096 ||
            (size_t)texture->params.w*texture->params.h > 4096*2160 ||
            texture->params.format->num_components < 3 ||
            (texture->params.format->type != PL_FMT_FLOAT && texture->params.format->type != PL_FMT_UNORM))
            return CB1_AI_INVALID;
        for (unsigned c = 0; c < 3; ++c)
            if (texture->params.format->component_depth[c] <
                (texture->params.format->type == PL_FMT_FLOAT ? 32 : 16))
                return CB1_AI_INCOMPATIBLE;
    }
    if (ctx->pending) return CB1_AI_PENDING;
    const unsigned count=source?(unsigned)((source->crop.x1-source->crop.x0)*(source->crop.y1-source->crop.y0)):
        (unsigned)(texture->params.w*texture->params.h);
    ctx->width=source?(unsigned)(source->crop.x1-source->crop.x0):(unsigned)texture->params.w;
    ctx->height=source?(unsigned)(source->crop.y1-source->crop.y0):(unsigned)texture->params.h;
    ctx->tiled=source || (ctx->width>=3840 && ctx->height>=1080);
#ifdef CB1_PROBE_TILED_FORCE_SMALL
    ctx->tiled=true;
#endif
#ifdef CB1_PROBE_TILED_GUARD
    extern void cb1_probe_extrema_selected(unsigned,unsigned,bool);
    cb1_probe_extrema_selected(ctx->width,ctx->height,ctx->tiled);
#endif
    const unsigned tile_width=source?4:16;
    const unsigned groups=ctx->tiled?((ctx->width+tile_width-1)/tile_width)*((ctx->height+1)/2):(count+127)/128;
    const unsigned cropped_groups=source?(groups+127)/128:groups;
    if(ctx->tiled && !allocate(ctx,&ctx->cropped_scan,cropped_groups)){ctx->failed=true;return CB1_AI_INVALID;}
    pl_dispatch_reset_frame(ctx->dispatch);
    /* Records use alpha as data, not opacity. Preserve the caller's blend state. */
    GLboolean blend=glIsEnabled(GL_BLEND);glDisable(GL_BLEND);
    ctx->compact=source && ctx->coalesced;
    pl_fmt scan_format=ctx->compact?pl_find_fmt(ctx->gpu,PL_FMT_UNORM,4,16,16,
        PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE):ctx->format;
    if(!scan_format){ctx->compact=false;scan_format=ctx->format;}
    unsigned scan_width=source?(ctx->width+tile_width-1)/tile_width:groups<256?groups:256;
    bool ok=scan_format && pl_tex_recreate(ctx->gpu,&ctx->scan,pl_tex_params(.w=scan_width,
        .h=(groups+scan_width-1)/scan_width,.format=scan_format,.sampleable=true,.renderable=true)) &&
        dispatch(ctx,texture,ctx->scan,count,true,false,source) &&
        reduce(ctx,ctx->scan,groups,ctx->bounds) &&
        dispatch(ctx,texture,ctx->tiled?ctx->cropped_scan:ctx->scan,source?groups:count,true,true,source) &&
        reduce(ctx,ctx->tiled?ctx->cropped_scan:ctx->scan,cropped_groups,ctx->final) && download(ctx);
    if(blend)glEnable(GL_BLEND);
    if(!ok){
        ctx->failed=true;return CB1_AI_INVALID;
    }
    ctx->pending = true;
    ctx->id = id;
    return CB1_AI_PENDING;
}

enum cb1_ai_status cb1_hdr10_extrema_submit(struct cb1_hdr10_extrema *ctx,pl_tex texture,
    struct cb1_ai_identity id)
{ return submit(ctx,texture,NULL,id); }

enum cb1_ai_status cb1_hdr10_extrema_submit_source(struct cb1_hdr10_extrema *ctx,
    const struct pl_frame *source,struct cb1_ai_identity id)
{
    enum cb1_ai_status status=cb1_hdr10_ingress_validate(source);
    if(status!=CB1_AI_READY)return status;
    if(source->planes[1].texture->params.w!=source->planes[0].texture->params.w/2 ||
       source->planes[1].texture->params.h!=source->planes[0].texture->params.h/2)
        return CB1_AI_INCOMPATIBLE;
    return submit(ctx,source->planes[0].texture,source,id);
}

pl_tex cb1_hdr10_extrema_pending(struct cb1_hdr10_extrema *ctx,struct cb1_ai_identity id)
{
    if(!ctx || ctx->failed || !ctx->pending || id.stream!=ctx->id.stream ||
       id.picture!=ctx->id.picture || id.revision!=ctx->id.revision)return NULL;
    return ctx->final;
}

enum cb1_ai_status cb1_hdr10_extrema_poll(struct cb1_hdr10_extrema *ctx,
                                       struct cb1_ai_identity id, struct cb1_hdr10_bounds *out)
{
    if (!ctx || ctx->failed || !out || !ctx->pending || id.stream != ctx->id.stream ||
        id.picture != ctx->id.picture || id.revision != ctx->id.revision) return CB1_AI_INVALID;
    GLenum status = glClientWaitSync(ctx->fence, 0, 0);
    if (status == GL_TIMEOUT_EXPIRED) return CB1_AI_PENDING;
    glDeleteSync(ctx->fence); ctx->fence = NULL;
    if (status != GL_ALREADY_SIGNALED && status != GL_CONDITION_SATISFIED) {
        ctx->failed = true; return CB1_AI_INVALID;
    }
    float record[4];
    ctx->pending = false;
    GLint buffer;
    glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING, &buffer);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, ctx->result);
    void *mapped = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, sizeof(record), GL_MAP_READ_BIT);
    if (mapped) memcpy(record, mapped, sizeof(record));
    bool ok = mapped && glUnmapBuffer(GL_PIXEL_PACK_BUFFER);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, (GLuint)buffer);
    if (!ok || glGetError() != GL_NO_ERROR) {
        ctx->failed = true; return CB1_AI_INVALID;
    }
    for (unsigned i = 0; i < 4; ++i)
        if (!isfinite(record[i]) || record[i] != floorf(record[i])) return CB1_AI_INVALID;
    if (record[0] < -1 || record[0] > 16777215 || record[1] < 0 || record[1] > 16777215 ||
        record[2] < 0 || record[2] > record[3] || record[3] > 65535)
        return CB1_AI_INVALID;
    struct cb1_hdr10_bounds bounds = {0,0,ctx->width,ctx->height,
                                    (uint16_t)record[2],(uint16_t)record[3]};
    if (record[0] >= 0) {
        uint32_t first = (uint32_t)record[0], last = (uint32_t)record[1];
        bounds.x0 = first%4096; bounds.y0 = first/4096;
        bounds.x1 = last%4096+1; bounds.y1 = last/4096+1;
    }
    if (bounds.x0 >= bounds.x1 || bounds.y0 >= bounds.y1 ||
        bounds.x1 > ctx->width || bounds.y1 > ctx->height) return CB1_AI_INVALID;
    *out = bounds;
    return CB1_AI_READY;
}
