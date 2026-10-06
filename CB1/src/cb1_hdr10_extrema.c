/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_hdr10_extrema.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/custom.h>
#include <libplacebo/opengl.h>
#include <GLES3/gl3.h>
#include <math.h>
#include <stdlib.h>
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
static const char reduce_body[] =
    "uint group=uint(gl_FragCoord.x)+output_width*uint(gl_FragCoord.y);"
    "uvec2 lo=uvec2(4096u),hi=uvec2(0u);float low=65535.0,high=0.0;bool bad=false;"
    "for(uint i=0u;i<128u;i++){uint index=group*128u+i;if(index>=count)break;"
    "vec4 r=texelFetch(pq_input,ivec2(index%input_width,index/input_width),0);"
    "merge_record(r,lo,hi,low,high,bad);}"
    "color=vec4(lo.x==4096u?-1.0:pack_xy(lo),pack_xy(hi),bad?-1.0:low,high);";

struct cb1_hdr10_extrema {
    pl_gpu gpu;
    pl_dispatch dispatch;
    pl_tex scan, temporary[2], bounds, final;
    GLuint result, framebuffer;
    GLsync fence;
    pl_fmt format;
    unsigned width, height;
    struct cb1_ai_identity id;
    uint64_t stream, revision;
    bool pending, failed, active;
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
                     unsigned count, bool scan, bool cropped)
{
    struct pl_shader_desc descriptors[] = {
        {.desc={.name="pq_input",.type=PL_DESC_SAMPLED_TEX},
         .binding={.object=input,.sample_mode=PL_TEX_SAMPLE_NEAREST}},
        {.desc={.name="bound_input",.type=PL_DESC_SAMPLED_TEX},
         .binding={.object=ctx->bounds,.sample_mode=PL_TEX_SAMPLE_NEAREST}},
    };
    unsigned size[2] = {ctx->width, ctx->height}, crop = cropped;
    unsigned input_width = (unsigned)input->params.w, output_width = (unsigned)output->params.w;
    struct pl_shader_var uniforms[] = {
        {.var=pl_var_uvec2("dimensions"),.data=size,.dynamic=true},
        {.var=pl_var_uint("cropped"),.data=&crop,.dynamic=true},
        {.var=pl_var_uint("count"),.data=&count,.dynamic=true},
        {.var=pl_var_uint("input_width"),.data=&input_width,.dynamic=true},
        {.var=pl_var_uint("output_width"),.data=&output_width,.dynamic=true},
    };
    pl_shader shader = pl_dispatch_begin(ctx->dispatch);
    bool ok = pl_shader_custom(shader, &(struct pl_custom_shader){
        .description="CB1 HDR10 integer bounds",.header=header,.body=scan?scan_body:reduce_body,
        .output=PL_SHADER_SIG_COLOR,.descriptors=descriptors,.num_descriptors=scan?2:1,
        .variables=uniforms,.num_variables=5});
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

static bool reduce(struct cb1_hdr10_extrema *ctx, unsigned count, pl_tex final)
{
    pl_tex input = ctx->scan;
    unsigned next = 0;
    while (count > 1) {
        unsigned groups = (count+127)/128;
        if (groups != 1 && !allocate(ctx, &ctx->temporary[next], groups)) return false;
        pl_tex output = groups == 1 ? final : ctx->temporary[next];
        if (!dispatch(ctx, input, output, count, false, false)) return false;
        input = output;
        next ^= 1;
        count = groups;
    }
    /* A one-group scan still needs an exact copy into its separate final target. */
    if (input != final && !dispatch(ctx, input, final, 1, false, false)) return false;
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

enum cb1_ai_status cb1_hdr10_extrema_submit(struct cb1_hdr10_extrema *ctx, pl_tex texture,
                                          struct cb1_ai_identity id)
{
    if (!ctx || ctx->failed || !ctx->active || id.stream != ctx->stream ||
        id.revision != ctx->revision || !texture || !texture->params.sampleable || texture->params.d ||
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
    if (ctx->pending) return CB1_AI_PENDING;
    const unsigned count = (unsigned)(texture->params.w*texture->params.h);
    const unsigned groups = (count+127)/128;
    ctx->width = (unsigned)texture->params.w; ctx->height = (unsigned)texture->params.h;
    pl_dispatch_reset_frame(ctx->dispatch);
    if (!allocate(ctx, &ctx->scan, groups) ||
        !dispatch(ctx, texture, ctx->scan, count, true, false) ||
        !reduce(ctx, groups, ctx->bounds) ||
        !dispatch(ctx, texture, ctx->scan, count, true, true) ||
        !reduce(ctx, groups, ctx->final) || !download(ctx)) {
        ctx->failed = true;
        return CB1_AI_INVALID;
    }
    ctx->pending = true;
    ctx->id = id;
    return CB1_AI_PENDING;
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
