/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_hdr10_quantiles.h"
#include <libplacebo/opengl.h>
#include <GLES3/gl31.h>
#include <fenv.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

/* Block sums bound rank searches while preserving the exact integer histogram. */
static const char shader_source[] =
    "#version 310 es\nprecision highp float;precision highp int;\n"
    "layout(local_size_x=128)in;layout(binding=0)uniform highp sampler2D video;"
    "layout(std430,binding=0)buffer Histogram{uint bins[];};"
    "layout(std430,binding=1)writeonly buffer Result{uint codes[14];};"
    "uniform uint pass,count;uniform uvec4 area;uniform uvec2 step_size;uniform uint ranks[14];"
    "void main(){uint i=gl_GlobalInvocationID.x;"
    "if(pass==0u){if(i<65537u)bins[i]=0u;return;}"
    "if(pass==1u){if(i>=count)return;uint w=(area.z-area.x+step_size.x-1u)/step_size.x;"
    "uvec2 p=area.xy+uvec2(i%w,i/w)*step_size;vec3 q=texelFetch(video,ivec2(p),0).rgb;"
    "if(any(isnan(q))||any(isinf(q))||any(lessThan(q,vec3(0.0)))||any(greaterThan(q,vec3(1.0))))"
    "{atomicOr(bins[65536],1u);return;}"
    "uint code=uint(roundEven(max(q.r,max(q.g,q.b))*65535.0));atomicAdd(bins[code],1u);return;}"
    "if(pass==2u){if(i>=512u)return;uint sum=0u;"
    "for(uint c=i*128u;c<(i+1u)*128u;c++)sum+=bins[c];bins[65537u+i]=sum;return;}"
    "if(i>=14u)return;uint code=0xffffffffu,total=0u;"
    "if(bins[65536]==0u){for(uint block=0u;block<512u;block++){uint sum=bins[65537u+block];"
    "if(total+sum<=ranks[i]){total+=sum;continue;}"
    "for(uint c=block*128u;c<(block+1u)*128u;c++){total+=bins[c];"
    "if(total>ranks[i]){code=c;break;}}break;}}codes[i]=code;}";

struct cb1_hdr10_quantiles {
    pl_gpu gpu;
    GLuint program,buffers[2],sampler;
    GLsync fence;
    struct cb1_ai_identity id;
    uint64_t stream,revision;
    double fraction[7];
    bool active,pending,failed;
};

static GLuint program_create(void)
{
    GLuint shader=glCreateShader(GL_COMPUTE_SHADER);
    if (!shader) return 0;
    const char *source=shader_source;
    glShaderSource(shader,1,&source,NULL); glCompileShader(shader);
    GLint ok;
    glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
    if (!ok) { glDeleteShader(shader); return 0; }
    GLuint program=glCreateProgram();
    if (program) { glAttachShader(program,shader); glLinkProgram(program); }
    glDeleteShader(shader);
    if (!program) return 0;
    glGetProgramiv(program,GL_LINK_STATUS,&ok);
    if (!ok) { glDeleteProgram(program); return 0; }
    return program;
}

struct cb1_hdr10_quantiles *cb1_hdr10_quantiles_create(pl_gpu gpu)
{
    pl_opengl gl=gpu?pl_opengl_get(gpu):NULL;
    if (!gl || !gpu->glsl.gles || gl->major<3 || (gl->major==3 && gl->minor<1) ||
        glGetError()!=GL_NO_ERROR) return NULL;
    GLint invocations,size,bindings; GLint64 storage;
    glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS,&invocations);
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_SIZE,0,&size);
    glGetIntegerv(GL_MAX_SHADER_STORAGE_BUFFER_BINDINGS,&bindings);
    glGetInteger64v(GL_MAX_SHADER_STORAGE_BLOCK_SIZE,&storage);
    if (invocations<128 || size<128 || bindings<2 || storage<(65537+512)*4 ||
        glGetError()!=GL_NO_ERROR) return NULL;
    struct cb1_hdr10_quantiles *ctx=calloc(1,sizeof(*ctx));
    if (!ctx) return NULL;
    ctx->gpu=gpu; ctx->program=program_create();
    GLint prior; glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&prior);
    glGenBuffers(2,ctx->buffers);
    for (unsigned i=0; i<2; ++i) {
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,ctx->buffers[i]);
        glBufferData(GL_SHADER_STORAGE_BUFFER,i?14*4:(65537+512)*4,NULL,GL_DYNAMIC_READ);
    }
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)prior);
    glGenSamplers(1,&ctx->sampler);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    if (!ctx->program || !ctx->buffers[0] || !ctx->buffers[1] || !ctx->sampler ||
        glGetError()!=GL_NO_ERROR) { cb1_hdr10_quantiles_destroy(&ctx); return NULL; }
    return ctx;
}

void cb1_hdr10_quantiles_destroy(struct cb1_hdr10_quantiles **ctx)
{
    if (!ctx || !*ctx) return;
    if ((*ctx)->fence) glDeleteSync((*ctx)->fence);
    glDeleteBuffers(2,(*ctx)->buffers); glDeleteProgram((*ctx)->program);
    glDeleteSamplers(1,&(*ctx)->sampler); free(*ctx); *ctx=NULL;
}

void cb1_hdr10_quantiles_reset(struct cb1_hdr10_quantiles *ctx, uint64_t stream, uint64_t revision)
{
    if (!ctx) return;
    if (ctx->fence) glDeleteSync(ctx->fence);
    ctx->fence=NULL; ctx->pending=false; ctx->active=true;
    ctx->stream=stream; ctx->revision=revision;
}

enum cb1_ai_status cb1_hdr10_quantiles_submit(struct cb1_hdr10_quantiles *ctx, pl_tex texture,
    struct cb1_hdr10_bounds bounds, struct cb1_ai_identity id)
{
    if (!ctx || ctx->failed || !ctx->active || id.stream!=ctx->stream || id.revision!=ctx->revision ||
        !texture || !texture->params.sampleable || texture->params.d ||
        texture->params.w<1 || texture->params.h<1 || texture->params.w>4096 || texture->params.h>4096 ||
        (size_t)texture->params.w*texture->params.h>4096*2160 ||
        bounds.x0>=bounds.x1 || bounds.y0>=bounds.y1 || bounds.x1>(unsigned)texture->params.w ||
        bounds.y1>(unsigned)texture->params.h || bounds.minimum>bounds.maximum ||
        texture->params.format->num_components<3 ||
        (texture->params.format->type!=PL_FMT_FLOAT && texture->params.format->type!=PL_FMT_UNORM))
        return CB1_AI_INVALID;
    for (unsigned i=0; i<3; ++i)
        if (texture->params.format->component_depth[i]<
            (texture->params.format->type==PL_FMT_FLOAT?32:16)) return CB1_AI_INCOMPATIBLE;
    if (ctx->pending) return CB1_AI_PENDING;
    const unsigned width=bounds.x1-bounds.x0,height=bounds.y1-bounds.y0;
    const unsigned sx=width/256?width/256:1,sy=height/144?height/144:1;
    const unsigned count=((width+sx-1)/sx)*((height+sy-1)/sy);
    static const double quantiles[]={.05,.25,.5,.75,.95,.99,.999};
    GLuint ranks[14];
    const int rounding=fegetround();
    if (rounding<0 || fesetround(FE_TONEAREST)) return CB1_AI_INVALID;
    for (unsigned i=0; i<7; ++i) {
        const double index=(count-1)*quantiles[i];
        ranks[2*i]=(GLuint)floor(index); ranks[2*i+1]=(GLuint)ceil(index);
        ctx->fraction[i]=index-floor(index);
    }
    if (fesetround(rounding)) return CB1_AI_INVALID;
    GLint program,active,binding,sampler,generic,indexed[2]; GLint64 offsets[2],sizes[2];
    glGetIntegerv(GL_CURRENT_PROGRAM,&program); glGetIntegerv(GL_ACTIVE_TEXTURE,&active);
    glActiveTexture(GL_TEXTURE0); glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);
    glGetIntegerv(GL_SAMPLER_BINDING,&sampler);
    glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&generic);
    for (unsigned i=0; i<2; ++i) {
        glGetIntegeri_v(GL_SHADER_STORAGE_BUFFER_BINDING,i,&indexed[i]);
        glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_START,i,&offsets[i]);
        glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_SIZE,i,&sizes[i]);
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER,i,ctx->buffers[i]);
    }
    glUseProgram(ctx->program);
    GLuint video=pl_opengl_unwrap(ctx->gpu,texture,NULL,NULL,NULL);
    glBindTexture(GL_TEXTURE_2D,video); glBindSampler(0,ctx->sampler);
    glUniform4ui(glGetUniformLocation(ctx->program,"area"),bounds.x0,bounds.y0,bounds.x1,bounds.y1);
    glUniform2ui(glGetUniformLocation(ctx->program,"step_size"),sx,sy);
    glUniform1ui(glGetUniformLocation(ctx->program,"count"),count);
    glUniform1uiv(glGetUniformLocation(ctx->program,"ranks"),14,ranks);
    const unsigned groups[]={(65537+127)/128,(count+127)/128,4,1};
    for (unsigned pass=0; pass<4; ++pass) {
        glUniform1ui(glGetUniformLocation(ctx->program,"pass"),pass);
        glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT);
        glDispatchCompute(groups[pass],1,1);
    }
    glMemoryBarrier(GL_BUFFER_UPDATE_BARRIER_BIT);
    ctx->fence=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0); glFlush();
    bool ok=video && ctx->fence && glGetError()==GL_NO_ERROR;
    for (unsigned i=0; i<2; ++i) {
        if (indexed[i] && sizes[i])
            glBindBufferRange(GL_SHADER_STORAGE_BUFFER,i,(GLuint)indexed[i],offsets[i],sizes[i]);
        else glBindBufferBase(GL_SHADER_STORAGE_BUFFER,i,(GLuint)indexed[i]);
    }
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)generic); glUseProgram((GLuint)program);
    glBindSampler(0,(GLuint)sampler); glBindTexture(GL_TEXTURE_2D,(GLuint)binding); glActiveTexture((GLenum)active);
    if (!ok || glGetError()!=GL_NO_ERROR) { ctx->failed=true; return CB1_AI_INVALID; }
    ctx->pending=true; ctx->id=id; return CB1_AI_PENDING;
}

enum cb1_ai_status cb1_hdr10_quantiles_poll(struct cb1_hdr10_quantiles *ctx,
    struct cb1_ai_identity id, float out[7])
{
    if (!ctx || ctx->failed || !ctx->pending || !out || id.stream!=ctx->id.stream ||
        id.picture!=ctx->id.picture || id.revision!=ctx->id.revision) return CB1_AI_INVALID;
    GLenum status=glClientWaitSync(ctx->fence,0,0);
    if (status==GL_TIMEOUT_EXPIRED) return CB1_AI_PENDING;
    glDeleteSync(ctx->fence); ctx->fence=NULL; ctx->pending=false;
    if (status!=GL_ALREADY_SIGNALED && status!=GL_CONDITION_SATISFIED) {
        ctx->failed=true; return CB1_AI_INVALID;
    }
    uint32_t codes[14]; GLint prior;
    glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&prior);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,ctx->buffers[1]);
    void *data=glMapBufferRange(GL_SHADER_STORAGE_BUFFER,0,sizeof(codes),GL_MAP_READ_BIT);
    if (data) memcpy(codes,data,sizeof(codes));
    bool ok=data && glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)prior);
    if (!ok || glGetError()!=GL_NO_ERROR) { ctx->failed=true; return CB1_AI_INVALID; }
    for (unsigned i=0; i<7; ++i)
        if (codes[2*i]>codes[2*i+1] || codes[2*i+1]>65535) return CB1_AI_INVALID;
    const int rounding=fegetround();
    if (rounding<0 || fesetround(FE_TONEAREST)) return CB1_AI_INVALID;
    float result[7];
    for (unsigned i=0; i<7; ++i) {
        const double lo=(float)codes[2*i]/65535.f,hi=(float)codes[2*i+1]/65535.f;
        const double t=ctx->fraction[i],delta=hi-lo;
        result[i]=(float)(t<.5?lo+delta*t:hi-delta*(1-t));
    }
    if (fesetround(rounding)) return CB1_AI_INVALID;
    memcpy(out,result,sizeof(result)); return CB1_AI_READY;
}
