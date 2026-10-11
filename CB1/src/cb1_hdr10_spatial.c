/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_hdr10_spatial.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/custom.h>
#include <libplacebo/opengl.h>
#include <GLES3/gl31.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* 38 spatial coordinates and an 18x32 motion grid, never a full image readback. */
enum { RECORD_FLOATS=1768, RECORD_PIXELS=442 };
static const char shader_header[]=
    "void accumulate(inout float sum,inout float error,float value){"
    "precise float corrected=value-error,next=sum+corrected;error=(next-sum)-corrected;sum=next;}"
    "float peak_at(ivec2 p){vec3 q=texelFetch(small_image,p,0).rgb;"
    "if(any(isnan(q))||any(isinf(q))||any(lessThan(q,vec3(0)))||any(greaterThan(q,vec3(1))))return uintBitsToFloat(0x7fc00000u);"
    "return max(q.r,max(q.g,q.b));}"
    "float motion(int index){"
    "if(index>=1766)return 0.0;"
    "int i=index-38,c=i/576;i=i%576;"
    "return texelFetch(small_image,ivec2((i%32)*4,(i/32)*4),0)[c];}"
    "vec2 tile(int index){float total=0.0,maximum=0.0;"
    "for(int y=0;y<18;y++)for(int x=0;x<32;x++){float q=peak_at(ivec2((index%4)*32+x,(index/4)*18+y));"
    "if(isnan(q))return vec2(q);total+=q;maximum=max(maximum,q);}return vec2(total/576.0,maximum);}"
    "vec4 record(int pixel){"
    "if(pixel<8)return vec4(tile(pixel*2),tile(pixel*2+1));"
    "if(pixel==8 || pixel==9)return vec4(0);"
    "if(pixel>9){int i=pixel*4;return vec4(motion(i),motion(i+1),motion(i+2),motion(i+3));}"
    "return vec4(0);}";

/* Parallel texture loads; centroid summation keeps its original row-major order. */
static const char bulk_header[]=
    "layout(std430,binding=0)writeonly buffer Result{float result[1768];};"
    "shared float peaks[128];shared vec4 counts[128];shared uint invalid[128];"
    "void bulk(){uint lane=gl_LocalInvocationID.x;counts[lane]=vec4(0);invalid[lane]=0u;"
    "float mass=0.0,mass_error=0.0;vec2 total=vec2(0),total_error=vec2(0);"
    "for(int y=0;y<72;y++){float q=peak_at(ivec2(int(lane),y));peaks[lane]=q;"
    "invalid[lane]|=isnan(q)?1u:0u;counts[lane]+=vec4(greaterThanEqual(vec4(q),vec4(.5,.7,.8,.9)));"
    "barrier();if(lane==0u){for(int x=0;x<128;x++){q=peaks[x];"
    "float w=max(q-.5,0.0);w*=w;accumulate(mass,mass_error,w);"
    "accumulate(total.x,total_error.x,w*(float(x)*2.0/127.0-1.0));"
    "accumulate(total.y,total_error.y,w*(float(y)*2.0/71.0-1.0));}}barrier();}"
    "for(uint stride=64u;stride>0u;stride>>=1u){if(lane<stride){"
    "counts[lane]+=counts[lane+stride];invalid[lane]|=invalid[lane+stride];}barrier();}"
    "if(lane==0u){vec4 threshold=counts[0]/9216.0;"
    "vec4 center=vec4(mass>0.0?total/mass:vec2(0),motion(38),motion(39));"
    "if(invalid[0]!=0u){threshold=vec4(uintBitsToFloat(0x7fc00000u));center=threshold;}"
    "for(int i=0;i<4;i++){result[32+i]=threshold[i];result[36+i]=center[i];}}}"
    "void main(){bulk();}";

struct cb1_hdr10_spatial {
    pl_gpu gpu;pl_dispatch dispatch;pl_tex result;
    GLuint buffer,framebuffer,program,sampler;GLsync fence;
    uint64_t stream,revision;struct cb1_ai_identity id;bool active,pending,failed;
};

static GLuint program_create(pl_opengl gl)
{
    GLuint shader=glCreateShader(GL_COMPUTE_SHADER);
    if(!shader)return 0;
    const char *version=gl->major>3 || gl->minor>=2 ? "#version 320 es\n" :
        "#version 310 es\n#extension GL_EXT_gpu_shader5 : require\n";
    const char *sources[]={version,"precision highp float;precision highp int;\n",
        "layout(local_size_x=128)in;layout(binding=0)uniform highp sampler2D small_image;\n",
        shader_header,bulk_header};
    glShaderSource(shader,5,sources,NULL);glCompileShader(shader);
    GLint ok;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
    if(!ok){char message[1024];glGetShaderInfoLog(shader,sizeof(message),NULL,message);
        fprintf(stderr,"CB1 spatial shader: %s\n",message);glDeleteShader(shader);return 0;}
    GLuint program=glCreateProgram();
    if(program){glAttachShader(program,shader);glLinkProgram(program);}
    glDeleteShader(shader);
    if(!program)return 0;
    glGetProgramiv(program,GL_LINK_STATUS,&ok);
    if(!ok){glDeleteProgram(program);return 0;}
    return program;
}

static bool submit_bulk(struct cb1_hdr10_spatial *ctx,pl_tex texture)
{
    GLint program,active,binding,sampler,generic,indexed;GLint64 offset,size;
    glGetIntegerv(GL_CURRENT_PROGRAM,&program);glGetIntegerv(GL_ACTIVE_TEXTURE,&active);
    glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);
    glGetIntegerv(GL_SAMPLER_BINDING,&sampler);
    glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&generic);
    glGetIntegeri_v(GL_SHADER_STORAGE_BUFFER_BINDING,0,&indexed);
    glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_START,0,&offset);
    glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_SIZE,0,&size);
    glUseProgram(ctx->program);glBindSampler(0,ctx->sampler);
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(ctx->gpu,texture,NULL,NULL,NULL));
    glBindBufferBase(GL_SHADER_STORAGE_BUFFER,0,ctx->buffer);
    glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT|GL_PIXEL_BUFFER_BARRIER_BIT);
    glDispatchCompute(1,1,1);glMemoryBarrier(GL_BUFFER_UPDATE_BARRIER_BIT);
    const bool ok=glGetError()==GL_NO_ERROR;
    if(indexed && size)glBindBufferRange(GL_SHADER_STORAGE_BUFFER,0,(GLuint)indexed,offset,size);
    else glBindBufferBase(GL_SHADER_STORAGE_BUFFER,0,(GLuint)indexed);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)generic);glUseProgram((GLuint)program);
    glBindSampler(0,(GLuint)sampler);glBindTexture(GL_TEXTURE_2D,(GLuint)binding);glActiveTexture((GLenum)active);
    return ok && glGetError()==GL_NO_ERROR;
}

struct cb1_hdr10_spatial *cb1_hdr10_spatial_create(pl_gpu gpu)
{
    pl_opengl gl=gpu?pl_opengl_get(gpu):NULL;
    if(!gl || !gpu->glsl.gles || gl->major<3 || (gl->major==3 && gl->minor<1))return NULL;
    pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
    if(!fmt)return NULL;
    struct cb1_hdr10_spatial *ctx=calloc(1,sizeof(*ctx));if(!ctx)return NULL;
    ctx->gpu=gpu;ctx->dispatch=pl_dispatch_create(gpu->log,gpu);
    ctx->result=pl_tex_create(gpu,pl_tex_params(.w=RECORD_PIXELS,.h=1,.format=fmt,.renderable=true,.sampleable=true));
    ctx->program=program_create(gl);
    glGenSamplers(1,&ctx->sampler);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    GLint prior;glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING,&prior);
    glGenBuffers(1,&ctx->buffer);glBindBuffer(GL_PIXEL_PACK_BUFFER,ctx->buffer);
    glBufferData(GL_PIXEL_PACK_BUFFER,RECORD_FLOATS*sizeof(float),NULL,GL_STREAM_READ);
    glBindBuffer(GL_PIXEL_PACK_BUFFER,(GLuint)prior);glGenFramebuffers(1,&ctx->framebuffer);
    if(!ctx->dispatch || !ctx->result || !ctx->buffer || !ctx->framebuffer ||
        !ctx->program || !ctx->sampler || glGetError()!=GL_NO_ERROR){
        cb1_hdr10_spatial_destroy(&ctx);return NULL;
    }
    return ctx;
}

void cb1_hdr10_spatial_destroy(struct cb1_hdr10_spatial **ctx)
{
    if(!ctx || !*ctx)return;
    if((*ctx)->fence)glDeleteSync((*ctx)->fence);
    pl_tex_destroy((*ctx)->gpu,&(*ctx)->result);pl_dispatch_destroy(&(*ctx)->dispatch);
    glDeleteBuffers(1,&(*ctx)->buffer);glDeleteFramebuffers(1,&(*ctx)->framebuffer);
    glDeleteProgram((*ctx)->program);glDeleteSamplers(1,&(*ctx)->sampler);free(*ctx);*ctx=NULL;
}

void cb1_hdr10_spatial_reset(struct cb1_hdr10_spatial *ctx,uint64_t stream,uint64_t revision)
{
    if(!ctx)return;
    if(ctx->fence)glDeleteSync(ctx->fence);
    ctx->fence=NULL;ctx->pending=false;ctx->stream=stream;ctx->revision=revision;ctx->active=true;
}

enum cb1_ai_status cb1_hdr10_spatial_submit(struct cb1_hdr10_spatial *ctx,pl_tex texture,struct cb1_ai_identity id)
{
    if(!ctx || ctx->failed || !ctx->active || id.stream!=ctx->stream || id.revision!=ctx->revision ||
        !texture || !texture->params.sampleable || texture->params.d || texture->params.w!=128 ||
        texture->params.h!=72 || texture->params.format->type!=PL_FMT_FLOAT ||
        texture->params.format->num_components<3)return CB1_AI_INVALID;
    for(unsigned i=0;i<3;++i)if(texture->params.format->component_depth[i]<32)return CB1_AI_INCOMPATIBLE;
    if(ctx->pending)return CB1_AI_PENDING;
    struct pl_shader_desc descriptor={.desc={.name="small_image",.type=PL_DESC_SAMPLED_TEX},
        .binding={.object=texture,.sample_mode=PL_TEX_SAMPLE_NEAREST}};
    pl_shader shader=pl_dispatch_begin(ctx->dispatch);
    bool ok=pl_shader_custom(shader,&(struct pl_custom_shader){.description="CB1 compact spatial analysis",
        .header=shader_header,.body="color=record(int(gl_FragCoord.x));",
        .output=PL_SHADER_SIG_COLOR,.descriptors=&descriptor,.num_descriptors=1});
    if(ok)ok=pl_dispatch_finish(ctx->dispatch,pl_dispatch_params(.shader=&shader,.target=ctx->result));
    pl_dispatch_abort(ctx->dispatch,&shader);
    if(!ok){ctx->failed=true;return CB1_AI_INVALID;}
    GLint framebuffer,buffer,alignment,row,rows,pixels;
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&framebuffer);glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING,&buffer);
    glGetIntegerv(GL_PACK_ALIGNMENT,&alignment);glGetIntegerv(GL_PACK_ROW_LENGTH,&row);
    glGetIntegerv(GL_PACK_SKIP_ROWS,&rows);glGetIntegerv(GL_PACK_SKIP_PIXELS,&pixels);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,ctx->framebuffer);
    GLuint image=pl_opengl_unwrap(ctx->gpu,ctx->result,NULL,NULL,NULL);
    glFramebufferTexture2D(GL_READ_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,image,0);
    glBindBuffer(GL_PIXEL_PACK_BUFFER,ctx->buffer);glPixelStorei(GL_PACK_ALIGNMENT,4);
    glPixelStorei(GL_PACK_ROW_LENGTH,0);glPixelStorei(GL_PACK_SKIP_ROWS,0);glPixelStorei(GL_PACK_SKIP_PIXELS,0);
    if(glCheckFramebufferStatus(GL_READ_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE){
        glReadPixels(0,0,RECORD_PIXELS,1,GL_RGBA,GL_FLOAT,NULL);
        if(submit_bulk(ctx,texture))ctx->fence=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0);
        glFlush();
    }
    ok=ctx->fence && glGetError()==GL_NO_ERROR;
    glPixelStorei(GL_PACK_ALIGNMENT,alignment);glPixelStorei(GL_PACK_ROW_LENGTH,row);
    glPixelStorei(GL_PACK_SKIP_ROWS,rows);glPixelStorei(GL_PACK_SKIP_PIXELS,pixels);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,(GLuint)framebuffer);glBindBuffer(GL_PIXEL_PACK_BUFFER,(GLuint)buffer);
    if(!ok || glGetError()!=GL_NO_ERROR){ctx->failed=true;return CB1_AI_INVALID;}
    ctx->pending=true;ctx->id=id;return CB1_AI_PENDING;
}

enum cb1_ai_status cb1_hdr10_spatial_poll(struct cb1_hdr10_spatial *ctx,struct cb1_ai_identity id,
    struct cb1_hdr10_spatial_result *out)
{
    if(!ctx || ctx->failed || !ctx->pending || !out || id.stream!=ctx->id.stream ||
        id.picture!=ctx->id.picture || id.revision!=ctx->id.revision)return CB1_AI_INVALID;
    GLenum status=glClientWaitSync(ctx->fence,0,0);if(status==GL_TIMEOUT_EXPIRED)return CB1_AI_PENDING;
    glDeleteSync(ctx->fence);ctx->fence=NULL;ctx->pending=false;
    if(status!=GL_ALREADY_SIGNALED && status!=GL_CONDITION_SATISFIED){ctx->failed=true;return CB1_AI_INVALID;}
    float record[RECORD_FLOATS];GLint prior;glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING,&prior);
    glBindBuffer(GL_PIXEL_PACK_BUFFER,ctx->buffer);
    void *data=glMapBufferRange(GL_PIXEL_PACK_BUFFER,0,sizeof(record),GL_MAP_READ_BIT);
    if(data)memcpy(record,data,sizeof(record));
    bool ok=data && glUnmapBuffer(GL_PIXEL_PACK_BUFFER);glBindBuffer(GL_PIXEL_PACK_BUFFER,(GLuint)prior);
    if(!ok || glGetError()!=GL_NO_ERROR){ctx->failed=true;return CB1_AI_INVALID;}
    for(unsigned i=0;i<1766;++i)if(!isfinite(record[i]) || record[i]<(i<36 || i>=38?0:-1) || record[i]>1)return CB1_AI_INVALID;
    struct cb1_hdr10_spatial_result value;
    memcpy(value.features,record,sizeof(value.features));memcpy(value.motion,record+38,sizeof(value.motion));
    *out=value;return CB1_AI_READY;
}
