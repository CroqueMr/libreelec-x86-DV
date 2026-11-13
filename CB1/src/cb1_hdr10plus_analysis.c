/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_hdr10plus_analysis.h"
#include <libplacebo/opengl.h>
#include <GLES3/gl31.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

enum { GROUPS=64, WORDS=518, TOTAL_WORDS=GROUPS*WORDS };

static const char analysis_header[]=
    "shared uint hist[256];shared uint yhist[256];shared vec4 sums[128];shared uvec2 counts[128];"
    "vec3 nits(vec3 q){vec3 x=pow(q,vec3(32.0/2523.0));return 10000.0*"
    "pow(max(x-3424.0/4096.0,0.0)/(2413.0/128.0-2392.0/128.0*x),vec3(16384.0/2610.0));}"
    "uint hdmi_bin(float light){return min(255u,uint(floor(light/16.0+0.5)));}";
static const char analysis_body[]=
    "uint lane=gl_LocalInvocationID.x;hist[lane]=0u;hist[lane+128u]=0u;"
    "if(measure_y){yhist[lane]=0u;yhist[lane+128u]=0u;}"
    "counts[lane]=uvec2(0);sums[lane]=vec4(0);barrier();"
    "uvec2 size=uvec2(area.zw-area.xy);uint count=size.x*size.y;"
    "uint last=0u,run=0u,last_y=0u,run_y=0u;"
    "uint tile=count/gl_NumWorkGroups.x+uint(count%gl_NumWorkGroups.x!=0u);"
    "uint first=gl_WorkGroupID.x*tile,length=min(tile,count-min(first,count));"
    "for(uint offset=lane;offset<length;offset+=128u){uint i=first+offset;"
    "ivec2 pos=area.xy+ivec2(i%size.x,i/size.x);vec3 q=texelFetch(video,pos,0).rgb;"
    "if(any(isnan(q))||any(isinf(q))||any(lessThan(q,vec3(0)))||any(greaterThan(q,vec3(1))))"
    "{counts[lane].x=1u;continue;}"
    "float light;"
    "if(measure_y){"
    "vec3 rgb=nits(q);light=max(rgb.r,max(rgb.g,rgb.b));"
    "float y=dot(rgb,vec3(0.2627,0.6780,0.0593));"
    "counts[lane].y+=uint(y<=100.0);"
    "uint bin_y=hdmi_bin(y);"
    "if(bin_y!=last_y){if(run_y>0u)atomicAdd(yhist[last_y],run_y);last_y=bin_y;run_y=0u;}run_y++;"
    "}else light=nits(vec3(max(q.r,max(q.g,q.b)))).r;"
    "uint bin=hdmi_bin(light);"
    "if(bin!=last){if(run>0u)atomicAdd(hist[last],run);last=bin;run=0u;}run++;"
    "sums[lane].xyz=max(sums[lane].xyz,q);sums[lane].w+=light;}"
    "if(run>0u)atomicAdd(hist[last],run);"
    "if(run_y>0u)atomicAdd(yhist[last_y],run_y);"
    "barrier();for(uint step=64u;step>0u;step>>=1u){if(lane<step){"
    "sums[lane].xyz=max(sums[lane].xyz,sums[lane+step].xyz);"
    "sums[lane].w+=sums[lane+step].w;counts[lane]+=counts[lane+step];}barrier();}"
    "uint base=gl_WorkGroupID.x*518u;records[base+lane]=hist[lane];"
    "records[base+lane+128u]=hist[lane+128u];"
    "if(measure_y){records[base+lane+256u]=yhist[lane];records[base+lane+384u]=yhist[lane+128u];}"
    "if(lane==0u){for(uint j=0u;j<4u;j++)records[base+512u+j]=floatBitsToUint(sums[0][j]);"
    "records[base+516u]=counts[0].x;records[base+517u]=counts[0].y;}";

struct cb1_hdr10plus_scene {
    struct dvbridge_identity last;
    unsigned y99_nits;
    double y100_sum;
    uint64_t pictures;
};

struct cb1_hdr10plus_analysis {
    pl_gpu gpu;
    GLuint program, buffer, sampler;
    GLsync fence;
    struct dvbridge_identity identity;
    struct cb1_hdr10plus_scene scene, pending_scene;
    uint64_t count;
    bool pending, measure_y;
};

static GLuint create_program(pl_log log)
{
    const char *parts[]={"#version 310 es\nprecision highp float;precision highp int;\n"
        "layout(local_size_x=128)in;layout(binding=0)uniform highp sampler2D video;uniform ivec4 area;"
        "uniform bool measure_y;"
        "layout(std430,binding=0)writeonly buffer Statistics{uint records[];};",
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

void cb1_hdr10plus_analysis_clear_scene(struct cb1_hdr10plus_analysis *ctx)
{
    if(ctx)ctx->scene=(struct cb1_hdr10plus_scene){0};
}

enum cb1_hdr10plus_analysis_status cb1_hdr10plus_analysis_submit(
    struct cb1_hdr10plus_analysis *ctx,pl_tex rgb,pl_rect2d area,struct dvbridge_identity id,
    unsigned version)
{
    if(!ctx || version>1 || !rgb || !rgb->params.sampleable || !rgb->params.format ||
       rgb->params.format->num_components<3 ||
       (rgb->params.format->type!=PL_FMT_FLOAT && rgb->params.format->type!=PL_FMT_UNORM) ||
       !id.stream || !id.picture ||
       area.x0<0 || area.y0<0 || area.x1<=area.x0 || area.y1<=area.y0 ||
       area.x1>rgb->params.w || area.y1>rgb->params.h ||
       (uint64_t)(area.x1-area.x0)*(area.y1-area.y0)>UINT32_MAX)
        return CB1_HDR10PLUS_ANALYSIS_INVALID;
    if(ctx->pending)return dvbridge_identity_equal(&id,&ctx->identity) && ctx->measure_y==(version==1)?
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
    glUniform1i(glGetUniformLocation(ctx->program,"measure_y"),version==1);
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
    ctx->measure_y=version==1;
    return CB1_HDR10PLUS_ANALYSIS_PENDING;
}

static unsigned percentile_bin(const uint32_t histogram[256],uint64_t count,unsigned rank)
{
    const uint64_t need=(count*rank+9999)/10000;
    uint64_t seen=0;
    for(unsigned bin=0;bin<256;bin++){
        seen+=histogram[bin];
        if(seen>=need)return bin;
    }
    return 0;
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
    uint32_t yhist[256]={0};
    uint64_t dark=0;
    for(unsigned g=0;g<GROUPS;g++){
        const uint32_t *p=words+g*WORDS;
        if(p[516])return CB1_HDR10PLUS_ANALYSIS_INVALID;
        for(unsigned i=0;i<256;i++){s.histogram[i]+=p[i];s.count+=p[i];}
        if(ctx->measure_y){
            for(unsigned i=0;i<256;i++)yhist[i]+=p[256+i];
            dark+=p[517];
        }
        float values[4];memcpy(values,p+512,sizeof(values));
        for(unsigned i=0;i<4;i++)if(!isfinite(values[i]) || values[i]<0)return CB1_HDR10PLUS_ANALYSIS_INVALID;
        for(unsigned i=0;i<3;i++)s.maxscl[i]=fmax(s.maxscl[i],eotf(values[i]));
        sum+=(double)values[3];
    }
    if(s.count!=ctx->count)return CB1_HDR10PLUS_ANALYSIS_INVALID;
    s.average_maxrgb=sum/s.count;
    if(ctx->measure_y){
        s.y99_nits=16*percentile_bin(yhist,s.count,9999);
        s.y100_percent=100.0*dark/s.count;
        s.luminance_valid=true;
    }
    *out=s;return CB1_HDR10PLUS_ANALYSIS_READY;
}

static void scene_update(struct cb1_hdr10plus_scene *scene,
    struct cb1_hdr10plus_statistics *s,struct dvbridge_identity id,bool scene_refresh)
{
    if(!s->luminance_valid)return;
    const struct dvbridge_identity last=scene->last;
    if(!dvbridge_identity_equal(&last,&id)){
        /* A missing picture may have carried the scene cut. */
        if(scene_refresh || id.stream!=last.stream || id.revision!=last.revision ||
           id.picture<=last.picture || id.picture-last.picture>1)
            *scene=(struct cb1_hdr10plus_scene){0};
        if(s->y99_nits>scene->y99_nits)scene->y99_nits=s->y99_nits;
        scene->y100_sum+=s->y100_percent;
        scene->pictures++;
        scene->last=id;
    }
    s->y99_nits=scene->y99_nits;
    s->y100_percent=scene->y100_sum/scene->pictures;
}

void cb1_hdr10plus_analysis_stage_scene(struct cb1_hdr10plus_analysis *ctx,
    struct cb1_hdr10plus_statistics *s,bool scene_refresh)
{
    ctx->pending_scene=(struct cb1_hdr10plus_scene){0};
    if(!s->luminance_valid)return;
    ctx->pending_scene=ctx->scene;
    scene_update(&ctx->pending_scene,s,ctx->identity,scene_refresh);
}

void cb1_hdr10plus_analysis_commit_scene(struct cb1_hdr10plus_analysis *ctx)
{
    ctx->scene=ctx->pending_scene;
}

bool cb1_hdr10plus_describe(AVDynamicHDRPlus *out,const struct cb1_hdr10plus_statistics *s,unsigned target)
{
    return cb1_hdr10plus_describe_for_version(out,s,target,1);
}

bool cb1_hdr10plus_describe_for_version(AVDynamicHDRPlus *out,
    const struct cb1_hdr10plus_statistics *s,unsigned target,unsigned version)
{
    if(!out || !s || version>1 || !s->count || s->count>UINT32_MAX || !target || target>992 || target%32 ||
       !isfinite(s->average_maxrgb) || s->average_maxrgb<0 || s->average_maxrgb>10000)return false;
    uint64_t count=0;for(unsigned i=0;i<256;i++)count+=s->histogram[i];
    if(count!=s->count)return false;
    if(version==1 && s->luminance_valid &&
       (s->y99_nits>4080 || !isfinite(s->y100_percent) ||
        s->y100_percent<0 || s->y100_percent>100))return false;
    AVDynamicHDRPlus m={.itu_t_t35_country_code=0xb5,.application_version=version,.num_windows=1,
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
    static const unsigned rank[]={100,500,1000,2500,5000,7500,9000,9500,9998};
    p->num_distribution_maxrgb_percentiles=9;
    for(unsigned i=0;i<9;i++){
        unsigned value;
        if(version==1 && i==1)value=s->luminance_valid?s->y99_nits*10:0;
        else if(version==1 && i==2)value=s->luminance_valid?(unsigned)lround(s->y100_percent):255;
        else value=160*percentile_bin(s->histogram,s->count,rank[i]);
        p->distribution_maxrgb[i]=(AVHDRPlusPercentile){.percentage=percent[i],.percentile={(int)value,100000}};
    }
    *out=m;return true;
}
