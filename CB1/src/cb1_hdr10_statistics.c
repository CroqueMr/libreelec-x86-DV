/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_hdr10_statistics.h"
#include <libplacebo/opengl.h>
#include <GLES3/gl31.h>
#include <fenv.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

/* Pairwise Welford reduction avoids cancellation in nearly uniform images. */
static const char shader_source[] =
    "#version 310 es\nprecision highp float;precision highp int;\n"
    "layout(local_size_x=128)in;layout(binding=0)uniform highp sampler2D video;"
    "layout(std430,binding=0)buffer Partial{float data[];};"
    "layout(std430,binding=1)writeonly buffer Result{float result[32];};"
    "uniform uint pass,count,groups;uniform uvec4 area;uniform uvec2 step_size;"
    "shared vec4 means[128],variance[128],rgb[128];shared vec2 edges[128];"
    "shared float histogram[16][128];shared uint invalid[128];"
    "vec3 pq(vec3 q){vec3 p=pow(q,vec3(32.0/2523.0));"
    "return 10000.0*pow(max(p-vec3(3424.0/4096.0),vec3(0.0))/"
    "(vec3(2413.0/128.0)-vec3(2392.0/128.0)*p),vec3(16384.0/2610.0));}"
    "vec3 sample_code(ivec2 p){return roundEven(texelFetch(video,p,0).rgb*65535.0)/65535.0;}"
    "void merge(inout vec4 a,inout vec4 v,vec4 b,vec4 w){"
    "if(b.w==0.0)return;if(a.w==0.0){a=b;v=w;return;}"
    "float n=a.w+b.w;vec3 d=b.xyz-a.xyz;"
    "v.xyz+=w.xyz+d*d*(a.w*b.w/n);a.xyz+=d*(b.w/n);a.w=n;}"
    "void main(){uint lane=gl_LocalInvocationID.x;means[lane]=vec4(0);"
    "variance[lane]=vec4(0);rgb[lane]=vec4(0);edges[lane]=vec2(0);invalid[lane]=0u;"
    "for(uint j=0u;j<16u;j++)histogram[j][lane]=0.0;"
    "if(pass==0u){uint i=gl_GlobalInvocationID.x;"
    "if(i<count){uint width=(area.z-area.x+step_size.x-1u)/step_size.x;"
    "uvec2 p=area.xy+uvec2(i%width,i/width)*step_size;"
    "vec3 original=texelFetch(video,ivec2(p),0).rgb;"
    "if(any(isnan(original))||any(isinf(original))||any(lessThan(original,vec3(0)))||any(greaterThan(original,vec3(1))))"
    "{invalid[lane]=1u;}else{vec3 q=sample_code(ivec2(p));"
    "float peak=max(q.r,max(q.g,q.b)),chroma=peak-min(q.r,min(q.g,q.b));"
    "float log_luma=log(1.0+dot(pq(q),vec3(.2627,.6780,.0593)))/log(10001.0);"
    "means[lane]=vec4(peak,log_luma,chroma,1);rgb[lane]=vec4(q,0);"
    "histogram[min(15u,uint(peak*16.0))][lane]=1.0;"
    "if(i>=width){vec3 previous=sample_code(ivec2(p-uvec2(0,step_size.y)));"
    "edges[lane]=vec2(abs(peak-max(previous.r,max(previous.g,previous.b))),1);}}}}"
    "else{for(uint g=lane;g<groups;g+=128u){uint o=g*32u;"
    "merge(means[lane],variance[lane],vec4(data[o],data[o+1u],data[o+2u],data[o+3u]),"
    "vec4(data[o+4u],data[o+5u],data[o+6u],0));"
    "rgb[lane].xyz+=vec3(data[o+7u],data[o+8u],data[o+9u]);"
    "edges[lane]+=vec2(data[o+10u],data[o+11u]);"
    "for(uint j=0u;j<16u;j++)histogram[j][lane]+=data[o+12u+j];"
    "invalid[lane]|=uint(data[o+28u]);}}"
    "barrier();for(uint stride=64u;stride>0u;stride>>=1u){if(lane<stride){"
    "merge(means[lane],variance[lane],means[lane+stride],variance[lane+stride]);"
    "rgb[lane]+=rgb[lane+stride];edges[lane]+=edges[lane+stride];"
    "for(uint j=0u;j<16u;j++)histogram[j][lane]+=histogram[j][lane+stride];"
    "invalid[lane]|=invalid[lane+stride];}barrier();}"
    "if(lane!=0u)return;uint o=pass==0u?gl_WorkGroupID.x*32u:0u;float r[32];"
    "for(uint j=0u;j<32u;j++)r[j]=0.0;"
    "for(uint j=0u;j<4u;j++)r[j]=means[0][j];"
    "for(uint j=0u;j<3u;j++){r[4u+j]=variance[0][j];r[7u+j]=rgb[0][j];}"
    "r[10]=edges[0].x;r[11]=edges[0].y;"
    "for(uint j=0u;j<16u;j++)r[12u+j]=histogram[j][0];r[28]=float(invalid[0]);"
    "for(uint j=0u;j<32u;j++){if(pass==0u)data[o+j]=r[j];else result[j]=r[j];}}";

struct cb1_hdr10_statistics {
    pl_gpu gpu;
    GLuint program,buffers[2],sampler;
    GLsync fence;
    struct cb1_ai_identity id;
    struct cb1_hdr10_bounds bounds;
    unsigned width,height,count;
    uint64_t stream,revision;
    bool active,pending,failed;
};

static GLuint program_create(void)
{
    GLuint shader=glCreateShader(GL_COMPUTE_SHADER);
    if (!shader) return 0;
    const char *source=shader_source;
    glShaderSource(shader,1,&source,NULL); glCompileShader(shader);
    GLint ok; glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
    if (!ok) { glDeleteShader(shader); return 0; }
    GLuint program=glCreateProgram();
    if (program) { glAttachShader(program,shader); glLinkProgram(program); }
    glDeleteShader(shader);
    if (!program) return 0;
    glGetProgramiv(program,GL_LINK_STATUS,&ok);
    if (!ok) { glDeleteProgram(program); return 0; }
    return program;
}

struct cb1_hdr10_statistics *cb1_hdr10_statistics_create(pl_gpu gpu)
{
    pl_opengl gl=gpu?pl_opengl_get(gpu):NULL;
    if (!gl || !gpu->glsl.gles || gl->major<3 || (gl->major==3 && gl->minor<1) ||
        glGetError()!=GL_NO_ERROR) return NULL;
    GLint invocations,size,bindings,shared; GLint64 storage;
    glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS,&invocations);
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_SIZE,0,&size);
    glGetIntegerv(GL_MAX_SHADER_STORAGE_BUFFER_BINDINGS,&bindings);
    glGetIntegerv(GL_MAX_COMPUTE_SHARED_MEMORY_SIZE,&shared);
    glGetInteger64v(GL_MAX_SHADER_STORAGE_BLOCK_SIZE,&storage);
    /* The strided grid can exceed 256 by 144 by less than one step. */
    if (invocations<128 || size<128 || bindings<2 || shared<16384 || storage<2048*32*4 ||
        glGetError()!=GL_NO_ERROR) return NULL;
    struct cb1_hdr10_statistics *ctx=calloc(1,sizeof(*ctx));
    if (!ctx) return NULL;
    ctx->gpu=gpu; ctx->program=program_create();
    GLint prior; glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&prior);
    glGenBuffers(2,ctx->buffers);
    for (unsigned i=0; i<2; ++i) {
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,ctx->buffers[i]);
        glBufferData(GL_SHADER_STORAGE_BUFFER,i?32*4:2048*32*4,NULL,GL_DYNAMIC_READ);
    }
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)prior);
    glGenSamplers(1,&ctx->sampler);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    if (!ctx->program || !ctx->buffers[0] || !ctx->buffers[1] || !ctx->sampler ||
        glGetError()!=GL_NO_ERROR) { cb1_hdr10_statistics_destroy(&ctx); return NULL; }
    return ctx;
}

void cb1_hdr10_statistics_destroy(struct cb1_hdr10_statistics **ctx)
{
    if (!ctx || !*ctx) return;
    if ((*ctx)->fence) glDeleteSync((*ctx)->fence);
    glDeleteBuffers(2,(*ctx)->buffers); glDeleteProgram((*ctx)->program);
    glDeleteSamplers(1,&(*ctx)->sampler); free(*ctx); *ctx=NULL;
}

void cb1_hdr10_statistics_reset(struct cb1_hdr10_statistics *ctx,uint64_t stream,uint64_t revision)
{
    if (!ctx) return;
    if (ctx->fence) glDeleteSync(ctx->fence);
    ctx->fence=NULL; ctx->pending=false; ctx->active=true;
    ctx->stream=stream; ctx->revision=revision;
}

enum cb1_ai_status cb1_hdr10_statistics_submit(struct cb1_hdr10_statistics *ctx,pl_tex texture,
    struct cb1_hdr10_bounds bounds,struct cb1_ai_identity id)
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
    GLenum target;
    GLuint video=pl_opengl_unwrap(ctx->gpu,texture,&target,NULL,NULL);
    if (!video || target!=GL_TEXTURE_2D) return CB1_AI_INCOMPATIBLE;
    if (ctx->pending) return CB1_AI_PENDING;
    const unsigned width=bounds.x1-bounds.x0,height=bounds.y1-bounds.y0;
    const unsigned sx=width/256?width/256:1,sy=height/144?height/144:1;
    const unsigned count=((width+sx-1)/sx)*((height+sy-1)/sy),groups=(count+127)/128;
    if (groups>2048) return CB1_AI_INCOMPATIBLE;
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
    glBindTexture(GL_TEXTURE_2D,video); glBindSampler(0,ctx->sampler);
    glUniform4ui(glGetUniformLocation(ctx->program,"area"),bounds.x0,bounds.y0,bounds.x1,bounds.y1);
    glUniform2ui(glGetUniformLocation(ctx->program,"step_size"),sx,sy);
    glUniform1ui(glGetUniformLocation(ctx->program,"count"),count);
    glUniform1ui(glGetUniformLocation(ctx->program,"groups"),groups);
    glUniform1ui(glGetUniformLocation(ctx->program,"pass"),0);
    glDispatchCompute(groups,1,1); glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT);
    glUniform1ui(glGetUniformLocation(ctx->program,"pass"),1);
    glDispatchCompute(1,1,1); glMemoryBarrier(GL_BUFFER_UPDATE_BARRIER_BIT);
    ctx->fence=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0); glFlush();
    bool ok=ctx->fence && glGetError()==GL_NO_ERROR;
    for (unsigned i=0; i<2; ++i) {
        if (indexed[i] && sizes[i])
            glBindBufferRange(GL_SHADER_STORAGE_BUFFER,i,(GLuint)indexed[i],offsets[i],sizes[i]);
        else glBindBufferBase(GL_SHADER_STORAGE_BUFFER,i,(GLuint)indexed[i]);
    }
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)generic); glUseProgram((GLuint)program);
    glBindSampler(0,(GLuint)sampler); glBindTexture(GL_TEXTURE_2D,(GLuint)binding); glActiveTexture((GLenum)active);
    if (!ok || glGetError()!=GL_NO_ERROR) { ctx->failed=true; return CB1_AI_INVALID; }
    ctx->pending=true; ctx->id=id; ctx->bounds=bounds;
    ctx->width=(unsigned)texture->params.w; ctx->height=(unsigned)texture->params.h;ctx->count=count;
    return CB1_AI_PENDING;
}

enum cb1_ai_status cb1_hdr10_statistics_poll(struct cb1_hdr10_statistics *ctx,
    struct cb1_ai_identity id,float out[35])
{
    if (!ctx || ctx->failed || !ctx->pending || !out || id.stream!=ctx->id.stream ||
        id.picture!=ctx->id.picture || id.revision!=ctx->id.revision) return CB1_AI_INVALID;
    GLenum status=glClientWaitSync(ctx->fence,0,0);
    if (status==GL_TIMEOUT_EXPIRED) return CB1_AI_PENDING;
    glDeleteSync(ctx->fence); ctx->fence=NULL; ctx->pending=false;
    if (status!=GL_ALREADY_SIGNALED && status!=GL_CONDITION_SATISFIED) {
        ctx->failed=true; return CB1_AI_INVALID;
    }
    float values[32]; GLint prior;
    glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&prior);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,ctx->buffers[1]);
    void *data=glMapBufferRange(GL_SHADER_STORAGE_BUFFER,0,sizeof(values),GL_MAP_READ_BIT);
    if (data) memcpy(values,data,sizeof(values));
    bool ok=data && glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)prior);
    if (!ok || glGetError()!=GL_NO_ERROR) { ctx->failed=true; return CB1_AI_INVALID; }
    for (unsigned j=0; j<32; ++j) if (!isfinite(values[j])) return CB1_AI_INVALID;
    if (values[28]!=0 || values[3]!=(float)ctx->count || values[3]<=0 ||
        values[4]<0 || values[5]<0 || values[6]<0 || values[11]<0) return CB1_AI_INVALID;
    const int rounding=fegetround();
    if (rounding<0 || fesetround(FE_TONEAREST)) return CB1_AI_INVALID;
    float result[35]={0};
    result[0]=(float)ctx->bounds.minimum/65535.f; result[1]=(float)ctx->bounds.maximum/65535.f;
    result[2]=values[0]; result[3]=(float)sqrt((double)values[4]/values[3]);
    result[11]=values[1];result[12]=(float)sqrt((double)values[5]/values[3]);
    for (unsigned j=0; j<3; ++j) result[13+j]=(float)((double)values[7+j]/values[3]);
    result[16]=(float)sqrt((double)values[6]/values[3]);
    result[17]=values[11]>0?(float)((double)values[10]/values[11]):0;
    result[18]=(float)((double)(ctx->bounds.x1-ctx->bounds.x0)*(ctx->bounds.y1-ctx->bounds.y0)/
        ((double)ctx->width*ctx->height));
    for (unsigned j=0; j<16; ++j) result[19+j]=(float)((double)values[12+j]/values[3]);
    if (fesetround(rounding)) return CB1_AI_INVALID;
    memcpy(out,result,sizeof(result)); return CB1_AI_READY;
}
