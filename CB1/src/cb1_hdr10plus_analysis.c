/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_hdr10plus_analysis.h"
#include <libplacebo/opengl.h>
#include <GLES3/gl31.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

enum { GROUPS=64, LANES=128, WORDS=264, TOTAL_WORDS=GROUPS*WORDS };

static const char analysis_header[]=
    "shared uint hist[256];shared vec4 sums[128];shared uint bad[128];"
    "float nits(float q){float x=pow(q,32.0/2523.0);return 10000.0*"
    "pow(max(x-3424.0/4096.0,0.0)/(2413.0/128.0-2392.0/128.0*x),16384.0/2610.0);}";
static const char analysis_body[]=
    "uint lane=gl_LocalInvocationID.x;hist[lane]=0u;hist[lane+128u]=0u;"
    "bad[lane]=0u;sums[lane]=vec4(0);barrier();"
    "uvec2 size=uvec2(area.zw-area.xy);uint count=size.x*size.y;"
    "for(uint i=gl_GlobalInvocationID.x;i<count;i+=8192u){"
    "ivec2 pos=area.xy+ivec2(i%size.x,i/size.x);vec3 q=texelFetch(video,pos,0).rgb;"
    "if(any(isnan(q))||any(isinf(q))||any(lessThan(q,vec3(0)))||any(greaterThan(q,vec3(1))))"
    "{bad[lane]=1u;continue;}"
    "float light=nits(max(q.r,max(q.g,q.b)));"
    "atomicAdd(hist[min(255u,uint(floor(light/16.0+0.5)))],1u);"
    "sums[lane].xyz=max(sums[lane].xyz,q);sums[lane].w+=light;}"
    "barrier();for(uint step=64u;step>0u;step>>=1u){if(lane<step){"
    "sums[lane].xyz=max(sums[lane].xyz,sums[lane+step].xyz);"
    "sums[lane].w+=sums[lane+step].w;bad[lane]|=bad[lane+step];}barrier();}"
    "uint base=gl_WorkGroupID.x*264u;records[base+lane]=hist[lane];"
    "records[base+lane+128u]=hist[lane+128u];"
    "if(lane==0u){for(uint j=0u;j<4u;j++)records[base+256u+j]=floatBitsToUint(sums[0][j]);"
    "records[base+260u]=bad[0];for(uint j=261u;j<264u;j++)records[base+j]=0u;}";

struct cb1_hdr10plus_analysis {
    pl_gpu gpu;
    GLuint program, buffer, sampler;
    GLsync fence;
    struct dvbridge_identity identity;
    uint64_t count;
    bool pending;
};

static GLuint create_program(pl_log log)
{
    const char *parts[]={"#version 310 es\nprecision highp float;precision highp int;\n"
        "layout(local_size_x=128)in;layout(binding=0)uniform highp sampler2D video;uniform ivec4 area;"
        "layout(std430,binding=0)writeonly buffer Statistics{uint records[16896];};",
        analysis_header,"void main(){",analysis_body,"}"};
    GLuint shader=glCreateShader(GL_COMPUTE_SHADER);
    if(!shader)return 0;
    glShaderSource(shader,5,parts,NULL);glCompileShader(shader);
    GLint ok;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
    if(!ok){
        char message[4096];glGetShaderInfoLog(shader,sizeof(message),NULL,message);
        if(log && log->params.log_cb && log->params.log_level>=PL_LOG_ERR)
            log->params.log_cb(log->params.log_priv,PL_LOG_ERR,message);
        glDeleteShader(shader);return 0;
    }
    GLuint program=glCreateProgram();
    if(program){glAttachShader(program,shader);glLinkProgram(program);}
    glDeleteShader(shader);
    if(!program)return 0;
    glGetProgramiv(program,GL_LINK_STATUS,&ok);
    if(!ok){glDeleteProgram(program);return 0;}
    return program;
}

static double eotf(double q)
{
    double x=pow(q,32.0/2523.0);
    return 10000*pow(fmax(0,x-3424.0/4096.0)/(2413.0/128.0-2392.0/128.0*x),16384.0/2610.0);
}

struct cb1_hdr10plus_analysis *cb1_hdr10plus_analysis_create(pl_log log,pl_gpu gpu)
{
    if(!cb1_hdr10plus_analysis_supported(gpu))return NULL;
    struct cb1_hdr10plus_analysis *ctx=calloc(1,sizeof(*ctx));
    if(!ctx)return NULL;
    ctx->gpu=gpu;
    ctx->program=create_program(log);
    GLint prior;glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&prior);
    glGenBuffers(1,&ctx->buffer);glBindBuffer(GL_SHADER_STORAGE_BUFFER,ctx->buffer);
    glBufferData(GL_SHADER_STORAGE_BUFFER,TOTAL_WORDS*sizeof(uint32_t),NULL,GL_DYNAMIC_READ);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)prior);
    glGenSamplers(1,&ctx->sampler);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glSamplerParameteri(ctx->sampler,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    if(!ctx->program || !ctx->buffer || !ctx->sampler || glGetError()!=GL_NO_ERROR){
        cb1_hdr10plus_analysis_destroy(&ctx);return NULL;
    }
    return ctx;
}

void cb1_hdr10plus_analysis_destroy(struct cb1_hdr10plus_analysis **ctx)
{
    if(!ctx || !*ctx)return;
    if((*ctx)->fence)glDeleteSync((*ctx)->fence);
    glDeleteBuffers(1,&(*ctx)->buffer);glDeleteProgram((*ctx)->program);
    glDeleteSamplers(1,&(*ctx)->sampler);
    free(*ctx);*ctx=NULL;
}

void cb1_hdr10plus_analysis_reset(struct cb1_hdr10plus_analysis *ctx)
{
    if(ctx){ctx->pending=false;ctx->identity=(struct dvbridge_identity){0};}
}

enum cb1_hdr10plus_analysis_status cb1_hdr10plus_analysis_submit(
    struct cb1_hdr10plus_analysis *ctx,pl_tex rgb,pl_rect2d area,struct dvbridge_identity id)
{
    if(!ctx || !rgb || !rgb->params.sampleable || !rgb->params.format ||
       rgb->params.format->num_components<3 ||
       (rgb->params.format->type!=PL_FMT_FLOAT && rgb->params.format->type!=PL_FMT_UNORM) ||
       !id.stream || !id.picture ||
       area.x0<0 || area.y0<0 || area.x1<=area.x0 || area.y1<=area.y0 ||
       area.x1>rgb->params.w || area.y1>rgb->params.h ||
       (uint64_t)(area.x1-area.x0)*(area.y1-area.y0)>UINT32_MAX)
        return CB1_HDR10PLUS_ANALYSIS_INVALID;
    if(ctx->pending)return dvbridge_identity_equal(&id,&ctx->identity)?
        CB1_HDR10PLUS_ANALYSIS_PENDING:CB1_HDR10PLUS_ANALYSIS_INVALID;
    if(ctx->fence){
        GLenum status=glClientWaitSync(ctx->fence,GL_SYNC_FLUSH_COMMANDS_BIT,0);
        if(status==GL_TIMEOUT_EXPIRED)return CB1_HDR10PLUS_ANALYSIS_BUSY;
        glDeleteSync(ctx->fence);ctx->fence=NULL;
        if(status==GL_WAIT_FAILED)return CB1_HDR10PLUS_ANALYSIS_INVALID;
    }
    GLenum target;GLuint texture=pl_opengl_unwrap(ctx->gpu,rgb,&target,NULL,NULL);
    if(!texture || target!=GL_TEXTURE_2D || glGetError()!=GL_NO_ERROR)return CB1_HDR10PLUS_ANALYSIS_INVALID;
    GLint program,active,texture_binding,sampler,generic,indexed;GLint64 offset,size;
    glGetIntegerv(GL_CURRENT_PROGRAM,&program);glGetIntegerv(GL_ACTIVE_TEXTURE,&active);
    glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&texture_binding);
    glGetIntegerv(GL_SAMPLER_BINDING,&sampler);
    glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&generic);
    glGetIntegeri_v(GL_SHADER_STORAGE_BUFFER_BINDING,0,&indexed);
    glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_START,0,&offset);
    glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_SIZE,0,&size);
    glBindTexture(GL_TEXTURE_2D,texture);glBindSampler(0,ctx->sampler);
    glBindBufferBase(GL_SHADER_STORAGE_BUFFER,0,ctx->buffer);glUseProgram(ctx->program);
    glUniform4i(glGetUniformLocation(ctx->program,"area"),area.x0,area.y0,area.x1,area.y1);
    glMemoryBarrier(GL_TEXTURE_FETCH_BARRIER_BIT);
    glDispatchCompute(GROUPS,1,1);glMemoryBarrier(GL_BUFFER_UPDATE_BARRIER_BIT);
    ctx->fence=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0);
    bool ok=ctx->fence && glGetError()==GL_NO_ERROR;
    if(indexed && size)glBindBufferRange(GL_SHADER_STORAGE_BUFFER,0,(GLuint)indexed,offset,size);
    else glBindBufferBase(GL_SHADER_STORAGE_BUFFER,0,(GLuint)indexed);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)generic);glUseProgram((GLuint)program);
    glBindSampler(0,(GLuint)sampler);glBindTexture(GL_TEXTURE_2D,(GLuint)texture_binding);
    glActiveTexture((GLenum)active);
    if(!ok || glGetError()!=GL_NO_ERROR)return CB1_HDR10PLUS_ANALYSIS_INVALID;
    ctx->identity=id;ctx->count=(uint64_t)(area.x1-area.x0)*(area.y1-area.y0);ctx->pending=true;
    return CB1_HDR10PLUS_ANALYSIS_PENDING;
}

enum cb1_hdr10plus_analysis_status cb1_hdr10plus_analysis_poll(
    struct cb1_hdr10plus_analysis *ctx,struct dvbridge_identity id,struct cb1_hdr10plus_statistics *out)
{
    if(!ctx || !out || !ctx->pending || !dvbridge_identity_equal(&id,&ctx->identity))
        return CB1_HDR10PLUS_ANALYSIS_INVALID;
    GLenum status=glClientWaitSync(ctx->fence,GL_SYNC_FLUSH_COMMANDS_BIT,0);
    if(status==GL_TIMEOUT_EXPIRED)return CB1_HDR10PLUS_ANALYSIS_PENDING;
    glDeleteSync(ctx->fence);ctx->fence=NULL;
    uint32_t words[TOTAL_WORDS];
    ctx->pending=false;
    if(status!=GL_ALREADY_SIGNALED && status!=GL_CONDITION_SATISFIED)return CB1_HDR10PLUS_ANALYSIS_INVALID;
    GLint prior;glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&prior);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,ctx->buffer);
    const void *data=glMapBufferRange(GL_SHADER_STORAGE_BUFFER,0,sizeof(words),GL_MAP_READ_BIT);
    if(data)memcpy(words,data,sizeof(words));
    bool ok=data && glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,(GLuint)prior);
    if(!ok || glGetError()!=GL_NO_ERROR)return CB1_HDR10PLUS_ANALYSIS_INVALID;
    struct cb1_hdr10plus_statistics s={0};double sum=0;
    for(unsigned g=0;g<GROUPS;g++){
        const uint32_t *p=words+g*WORDS;
        if(p[260])return CB1_HDR10PLUS_ANALYSIS_INVALID;
        for(unsigned i=0;i<256;i++){s.histogram[i]+=p[i];s.count+=p[i];}
        float values[4];memcpy(values,p+256,sizeof(values));
        for(unsigned i=0;i<4;i++)if(!isfinite(values[i]) || values[i]<0)return CB1_HDR10PLUS_ANALYSIS_INVALID;
        for(unsigned i=0;i<3;i++)s.maxscl[i]=fmax(s.maxscl[i],eotf(values[i]));
        sum+=values[3];
    }
    if(s.count!=ctx->count)return CB1_HDR10PLUS_ANALYSIS_INVALID;
    s.average_maxrgb=sum/s.count;
    *out=s;return CB1_HDR10PLUS_ANALYSIS_READY;
}

bool cb1_hdr10plus_describe(AVDynamicHDRPlus *out,const struct cb1_hdr10plus_statistics *s,unsigned target)
{
    if(!out || !s || !s->count || s->count>UINT32_MAX || !target || target>992 || target%32 ||
       !isfinite(s->average_maxrgb) || s->average_maxrgb<0 || s->average_maxrgb>10000)return false;
    uint64_t count=0;for(unsigned i=0;i<256;i++)count+=s->histogram[i];
    if(count!=s->count)return false;
    AVDynamicHDRPlus m={.itu_t_t35_country_code=0xb5,.application_version=1,.num_windows=1,
        .targeted_system_display_maximum_luminance={(int)target,1}};
    AVHDRPlusColorTransformParams *p=&m.params[0];
    p->window_upper_left_corner_x=p->window_upper_left_corner_y=(AVRational){0,1};
    p->window_lower_right_corner_x=p->window_lower_right_corner_y=(AVRational){1,1};
    for(unsigned i=0;i<3;i++){
        if(!isfinite(s->maxscl[i]) || s->maxscl[i]<0 || s->maxscl[i]>10000)return false;
        p->maxscl[i]=(AVRational){(int)lround(s->maxscl[i]*10),100000};
    }
    p->average_maxrgb=(AVRational){(int)lround(s->average_maxrgb*10),100000};
    if(p->average_maxrgb.num>p->maxscl[0].num && p->average_maxrgb.num>p->maxscl[1].num &&
       p->average_maxrgb.num>p->maxscl[2].num)return false;
    p->fraction_bright_pixels=(AVRational){0,1};
    static const uint8_t percent[]={1,5,10,25,50,75,90,95,99};
    static const unsigned rank[]={100,0,0,2500,5000,7500,9000,9500,9998};
    p->num_distribution_maxrgb_percentiles=9;
    for(unsigned i=0;i<9;i++){
        unsigned value=i==2?255:0;
        if(i!=1 && i!=2){
            uint64_t need=(s->count*rank[i]+9999)/10000,seen=0;
            for(unsigned bin=0;bin<256;bin++){
                seen+=s->histogram[bin];if(seen>=need){value=bin*160;break;}
            }
        }
        p->distribution_maxrgb[i]=(AVHDRPlusPercentile){.percentage=percent[i],.percentile={(int)value,100000}};
    }
    *out=m;return true;
}
