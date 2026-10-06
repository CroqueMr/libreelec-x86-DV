/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include <time.h>

static bool resolve(struct dvbridge_renderer *r,pl_tex target,unsigned framebuffer)
{
#if DVBRIDGE_DV_POLICY_API >= 2
    return dvbridge_render_dv_policy_resolve(r,target,framebuffer,false);
#else
    (void)framebuffer;return dvbridge_render_dv_policy_resolve(r,target,false);
#endif
}
static struct reference_gpu target_gpu(bool rgb)
{
    struct reference_gpu g={.display=eglGetDisplay(EGL_DEFAULT_DISPLAY)};
    assert(eglInitialize(g.display,NULL,NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    const EGLint attrs[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,0x40,
        EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,rgb?0:8,EGL_NONE};
    const EGLint surface[]={EGL_WIDTH,3840,EGL_HEIGHT,2160,EGL_NONE},context[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLConfig config=NULL,configs[128];EGLint count;
    assert(eglChooseConfig(g.display,attrs,configs,128,&count) && count);
    for(int i=0;i<count;i++){
        EGLint bits[4];const EGLint channels[]={EGL_RED_SIZE,EGL_GREEN_SIZE,EGL_BLUE_SIZE,EGL_ALPHA_SIZE};
        for(unsigned c=0;c<4;c++)assert(eglGetConfigAttrib(g.display,configs[i],channels[c],&bits[c]));
        if(bits[0]==8 && bits[1]==8 && bits[2]==8 && bits[3]==(rgb?0:8)){config=configs[i];break;}
    }
    assert(config);
    g.surface=eglCreatePbufferSurface(g.display,config,surface);
    g.context=eglCreateContext(g.display,config,EGL_NO_CONTEXT,context);
    assert(g.surface && g.context && eglMakeCurrent(g.display,g.surface,g.surface,g.context));
    g.gl=pl_opengl_create(NULL,pl_opengl_params(.allow_software=true,
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,
        .egl_display=g.display,.egl_context=g.context));assert(g.gl);
    return g;
}
static pl_tex renderbuffer_target(pl_gpu gpu,GLenum format,unsigned samples,
                                 GLuint *framebuffer,GLuint *renderbuffer)
{
    glGenRenderbuffers(1,renderbuffer);glBindRenderbuffer(GL_RENDERBUFFER,*renderbuffer);
    if(samples)glRenderbufferStorageMultisample(GL_RENDERBUFFER,samples,format,3840,2160);
    else glRenderbufferStorage(GL_RENDERBUFFER,format,3840,2160);
    glGenFramebuffers(1,framebuffer);glBindFramebuffer(GL_FRAMEBUFFER,*framebuffer);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_RENDERBUFFER,*renderbuffer);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE && glGetError()==GL_NO_ERROR);
    pl_tex target=pl_opengl_wrap(gpu,pl_opengl_wrap_params(.width=3840,.height=2160,.framebuffer=*framebuffer));
    assert(target);return target;
}
static void representation(pl_tex target,unsigned framebuffer,unsigned components)
{
    assert(target->params.format->type==PL_FMT_UNORM && target->params.format->num_components==components);
    glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
    const GLenum channels[]={GL_RED_BITS,GL_GREEN_BITS,GL_BLUE_BITS,GL_ALPHA_BITS};
    GLint bits[4],samples,encoding;
    for(unsigned c=0;c<4;c++){
        glGetIntegerv(channels[c],&bits[c]);
        assert(bits[c]==(c==3 && components==3?0:8) && target->params.format->component_depth[c]==bits[c]);
    }
    glGetIntegerv(GL_SAMPLES,&samples);
    glGetFramebufferAttachmentParameteriv(GL_FRAMEBUFFER,framebuffer?GL_COLOR_ATTACHMENT0:GL_BACK,
        GL_FRAMEBUFFER_ATTACHMENT_COLOR_ENCODING,&encoding);
    assert(samples<=1 && encoding==GL_LINEAR && glGetError()==GL_NO_ERROR);
    fprintf(stderr,"REAL target=%p fbo=%u components=%u depths=%d,%d,%d,%d samples=%d linear\n",
        (void *)target,framebuffer,components,bits[0],bits[1],bits[2],bits[3],samples);
}
static void clear(unsigned framebuffer)
{
    glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);glDisable(GL_SCISSOR_TEST);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glClearColor(1,0,1,1);glClear(GL_COLOR_BUFFER_BIT);
    assert(glGetError()==GL_NO_ERROR);
}
static void pixel(unsigned framebuffer,bool packed)
{
    const unsigned char black[]={128,16,0,255},canary[]={255,0,255,255};
    unsigned char actual[4];glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
    glReadPixels(1800,1500,1,1,GL_RGBA,GL_UNSIGNED_BYTE,actual);
    fprintf(stderr,"TARGET framebuffer=%u packed=%d rgba=%u,%u,%u,%u\n",
        framebuffer,packed,actual[0],actual[1],actual[2],actual[3]);
    assert(glGetError()==GL_NO_ERROR && !memcmp(actual,packed?black:canary,4));
}
static void prepare(struct dvbridge_renderer *r,const struct pl_frame *source,
                    const void *metadata,size_t bytes,struct dvbridge_identity identity)
{
    struct dvbridge_policy policy=reference_policy();policy.mode=DVBRIDGE_MODE_ENHANCED_DV;
    policy.enhancement=DVBRIDGE_ENHANCEMENT_NATURAL;policy.revision=identity.revision;
    assert(dvbridge_render_dv_policy_prepare(r,&policy,&identity,source,metadata,bytes,7,7,
        (struct dvbridge_geometry){2,2,0,0,2,2})==DVBRIDGE_DV_READY);
    enum dvbridge_dv_policy_status status=DVBRIDGE_DV_PENDING;
    for(unsigned callback=0;callback<10000 && status==DVBRIDGE_DV_PENDING;callback++){
        status=dvbridge_render_dv_policy_poll(r);
        if(status==DVBRIDGE_DV_PENDING)nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(status==DVBRIDGE_DV_READY);
}
static void idle(struct dvbridge_renderer *r)
{
    enum dvbridge_dv_policy_status status=DVBRIDGE_DV_BUSY;
    for(unsigned callback=0;callback<10000 && status==DVBRIDGE_DV_BUSY;callback++){
        status=dvbridge_render_dv_policy_poll(r);
        if(status==DVBRIDGE_DV_BUSY)nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(status==DVBRIDGE_DV_IDLE);
}
static void transport_parity(struct dvbridge_renderer *r,pl_gpu gpu,pl_tex rgb,unsigned framebuffer)
{
    GLuint rgba_fbo,rgba_buffer;
    pl_tex rgba=renderbuffer_target(gpu,GL_RGBA8,0,&rgba_fbo,&rgba_buffer);
    representation(rgba,rgba_fbo,4);
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
    const struct dvbridge_dv_policy_snapshot before=out->value;
    unsigned count;const uint32_t *packets=dvbridge_packets(out->candidate,&count);assert(packets && count==1);
    uint32_t packet[128];memcpy(packet,packets,sizeof(packet));
    void *metadata=av_memdup(out->output_metadata,out->bytes);size_t bytes=out->bytes;assert(metadata);
    const size_t pixels=3840u*2160u;
    unsigned char *a=malloc(pixels*4),*b=malloc(pixels*4);assert(a && b);
    assert(resolve(r,rgba,rgba_fbo));
    const uint64_t rgba_serial=dvbridge_render_dv_policy_output(r)->resolve_serial;
    glBindFramebuffer(GL_FRAMEBUFFER,rgba_fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,a);
    assert(glGetError()==GL_NO_ERROR);
    assert(resolve(r,rgb,framebuffer));
    out=dvbridge_render_dv_policy_output(r);assert(out->resolve_serial>rgba_serial);
    assert(!dvbridge_render_dv_policy_commit(r,&before.identity,rgba,rgba_serial));
    assert(!dvbridge_render_dv_policy_commit(r,&before.identity,rgb,rgba_serial));
    glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,b);
    assert(glGetError()==GL_NO_ERROR);
    for(size_t p=0;p<pixels;p++)assert(!memcmp(a+4*p,b+4*p,3) && a[4*p+3]==255);
    packets=dvbridge_packets(out->candidate,&count);
    assert(packets && count==1 && !memcmp(packet,packets,sizeof(packet)));
    assert(bytes==out->bytes && !memcmp(metadata,out->output_metadata,bytes));
    struct dvbridge_dv_policy_snapshot after=out->value;
    after.final_target=before.final_target;after.final_framebuffer=before.final_framebuffer;
    assert(!memcmp(&before,&after,sizeof(before)));
    fprintf(stderr,"PARITY rgb_bytes=%zu packet_words=%zu packet_storage_bytes=%zu packet_logical_bytes=128 packet_id=%u metadata_bytes=%zu identity=%llu/%llu/%llu serial=%llu->%llu exact\n",
        pixels*3,sizeof(packet)/sizeof(*packet),sizeof(packet),packet[1],bytes,(unsigned long long)before.identity.stream,
        (unsigned long long)before.identity.picture,(unsigned long long)before.identity.revision,
        (unsigned long long)rgba_serial,(unsigned long long)out->resolve_serial);
    free(a);free(b);av_free(metadata);pl_tex_destroy(gpu,&rgba);
    assert(glIsFramebuffer(rgba_fbo) && glIsRenderbuffer(rgba_buffer));
    glDeleteFramebuffers(1,&rgba_fbo);glDeleteRenderbuffers(1,&rgba_buffer);
}
static void rejected_rgb_targets(struct dvbridge_renderer *r,pl_gpu gpu,const struct pl_frame *source,
                                 const void *metadata,size_t bytes,pl_tex rgb,unsigned rgb_fbo)
{
    struct dvbridge_dv_policy_snapshot before,after;assert(dvbridge_render_dv_policy_committed(r,&before));
    const GLenum formats[]={GL_RGBA8,GL_RGBA8,GL_RGB565,GL_RGB10_A2,GL_SRGB8_ALPHA8,GL_RGB8,GL_R8,GL_RG8};
    for(unsigned i=0;i<sizeof(formats)/sizeof(*formats);i++){
        GLuint fbo,buffer;pl_tex target=renderbuffer_target(gpu,formats[i],i==5?4:0,&fbo,&buffer);
        if(i<2)representation(target,fbo,4);
        prepare(r,source,metadata,bytes,(struct dvbridge_identity){11,i+3,2});
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,rgb_fbo);glBindFramebuffer(GL_READ_FRAMEBUFFER,fbo);
        glEnable(GL_SCISSOR_TEST);glViewport(3,5,11,13);
        /* Both mismatches use real opaque queried formats, never fabricated alpha. */
        assert(!resolve(r,i==0?rgb:target,i==1?rgb_fbo:fbo));
        GLint draw,read,viewport[4];glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);
        glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);glGetIntegerv(GL_VIEWPORT,viewport);
        assert((unsigned)draw==rgb_fbo && (unsigned)read==fbo && glIsEnabled(GL_SCISSOR_TEST));
        assert(!memcmp(viewport,(GLint[4]){3,5,11,13},sizeof(viewport)) && glGetError()==GL_NO_ERROR);
        assert(!dvbridge_render_dv_policy_output(r));idle(r);
        assert(dvbridge_render_dv_policy_committed(r,&after) && !memcmp(&before,&after,sizeof(before)));
        pixel(rgb_fbo,true);
        fprintf(stderr,"PASS real RGB rejection=%u format=%#x samples=%u prior snapshot/bindings unchanged\n",i,formats[i],i==5?4:0);
        pl_tex_destroy(gpu,&target);assert(glIsFramebuffer(fbo) && glIsRenderbuffer(buffer));
        glDeleteFramebuffers(1,&fbo);glDeleteRenderbuffers(1,&buffer);
    }
    glDisable(GL_SCISSOR_TEST);glBindFramebuffer(GL_FRAMEBUFFER,0);
}
static void rejected_targets(struct dvbridge_renderer *r,pl_gpu gpu,
    const struct pl_frame *source,const void *metadata,size_t bytes,pl_tex target)
{
    struct dvbridge_dv_policy_snapshot before,after;
    assert(dvbridge_render_dv_policy_committed(r,&before));
    GLuint incomplete;glGenFramebuffers(1,&incomplete);glBindFramebuffer(GL_FRAMEBUFFER,incomplete);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE);
    pl_fmt format=pl_find_fmt(gpu,PL_FMT_FLOAT,4,16,32,PL_FMT_CAP_RENDERABLE);assert(format);
    pl_tex wrong_format=pl_tex_create(gpu,pl_tex_params(.w=3840,.h=2160,.format=format,.renderable=true));assert(wrong_format);
    pl_tex wrong_size=pl_opengl_wrap(gpu,pl_opengl_wrap_params(.width=2,.height=2160));assert(wrong_size);
    for(unsigned rejected=0;rejected<4;rejected++){
        prepare(r,source,metadata,bytes,(struct dvbridge_identity){11,2,rejected+2});
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,incomplete);glBindFramebuffer(GL_READ_FRAMEBUFFER,0);
        glEnable(GL_SCISSOR_TEST);glViewport(3,5,11,13);
        if(rejected==3){
            /* Actual final resolve but deliberately no successful-submit receipt. */
            assert(resolve(r,target,0));dvbridge_render_dv_policy_cancel(r);
        }else assert(!resolve(r,rejected==1?wrong_format:rejected==2?wrong_size:target,
                             rejected==0?incomplete:0));
        GLint draw,read,viewport[4];glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);
        glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);glGetIntegerv(GL_VIEWPORT,viewport);
        assert((GLuint)draw==incomplete && read==0 && glIsEnabled(GL_SCISSOR_TEST));
        assert(!memcmp(viewport,(GLint[4]){3,5,11,13},sizeof(viewport)) && glGetError()==GL_NO_ERROR);
        assert(!dvbridge_render_dv_policy_output(r));idle(r);
        assert(dvbridge_render_dv_policy_committed(r,&after) && !memcmp(&before,&after,sizeof(before)));
        pixel(0,true);fprintf(stderr,"PASS rejected target/submission=%u prior snapshot unchanged\n",rejected);
    }
    glDisable(GL_SCISSOR_TEST);glBindFramebuffer(GL_FRAMEBUFFER,0);
    pl_tex_destroy(gpu,&wrong_format);pl_tex_destroy(gpu,&wrong_size);glDeleteFramebuffers(1,&incomplete);
}
int main(int argc,char **argv)
{
    assert(argc==2);const unsigned kind=(unsigned)strtoul(argv[1],NULL,10);
    assert(kind<=6);
    struct reference_gpu g=target_gpu(kind==6);pl_gpu gpu=g.gl->gpu;
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    pl_tex input=reference_texture(gpu,2,2,(float[16]){.2,.2,.2,1,.4,.4,.4,1,.6,.6,.6,1,.8,.8,.8,1});
    struct pl_frame source=reference_frame(input,2,2);
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);assert(metadata);
    metadata->num_ext_blocks=1;AVDOVIDmData *l1=av_dovi_get_ext(metadata,0);
    l1->level=1;l1->l1.max_pq=3079;l1->l1.avg_pq=1667;
    GLuint framebuffer=0,texture=0,renderbuffer=0;
    struct pl_opengl_wrap_params wrap={.width=3840,.height=2160};
    if(kind==1 || kind==5){
        glGenRenderbuffers(1,&renderbuffer);glBindRenderbuffer(GL_RENDERBUFFER,renderbuffer);
        glRenderbufferStorage(GL_RENDERBUFFER,kind==5?GL_RGB8:GL_RGBA8,3840,2160);
        glGenFramebuffers(1,&framebuffer);glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_RENDERBUFFER,renderbuffer);
        wrap.framebuffer=framebuffer;
    }else if(kind>=2 && kind<=4){
        glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
        glTexStorage2D(GL_TEXTURE_2D,1,GL_RGBA8,3840,2160);
        wrap.texture=texture;wrap.iformat=GL_RGBA8;
        if(kind==2){
            glGenFramebuffers(1,&framebuffer);glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
            wrap.framebuffer=framebuffer;
        }
    }
    pl_tex target=pl_opengl_wrap(gpu,&wrap);assert(target);
    if(kind>=5)representation(target,framebuffer,3);
    if(kind==3)assert(pl_opengl_unwrap(gpu,target,NULL,NULL,&framebuffer)==texture && framebuffer);
    clear(0);if(framebuffer)clear(framebuffer);
    struct dvbridge_identity identity={11,1,1};prepare(r,&source,metadata,bytes,identity);
    if(kind==4){
        /* A real texture-backed target cannot be resolved using unrelated FBO0. */
        assert(!resolve(r,target,0));idle(r);pixel(0,false);
    }else{
        assert(resolve(r,target,framebuffer));
        if(kind>=5)transport_parity(r,gpu,target,framebuffer);
        const uint64_t first=dvbridge_render_dv_policy_output(r)->resolve_serial;
        assert(resolve(r,target,framebuffer));
        const uint64_t latest=dvbridge_render_dv_policy_output(r)->resolve_serial;assert(latest>first);
        assert(!dvbridge_render_dv_policy_commit(r,&identity,target,first));
        pixel(framebuffer,true);if(framebuffer)pixel(0,false);
        assert(dvbridge_render_dv_policy_commit(r,&identity,target,latest));idle(r);
        struct dvbridge_dv_policy_snapshot committed;assert(dvbridge_render_dv_policy_committed(r,&committed));
        assert(committed.final_target==target);
        assert(dvbridge_identity_equal(&committed.identity,&identity));
#if DVBRIDGE_DV_POLICY_API >= 2
        assert(committed.final_framebuffer==framebuffer);
#endif
        if(kind==0)rejected_targets(r,gpu,&source,metadata,bytes,target);
        if(kind>=5)rejected_rgb_targets(r,gpu,&source,metadata,bytes,target,framebuffer);
    }
    pl_tex_destroy(gpu,&target);
    if(texture)assert(glIsTexture(texture));
    if(kind==1 || kind==2 || kind==5)assert(glIsFramebuffer(framebuffer));
    if(kind==1 || kind==5)assert(glIsRenderbuffer(renderbuffer));
    if(kind==3)assert(!glIsFramebuffer(framebuffer));
    if(kind==1 || kind==2 || kind==5)glDeleteFramebuffers(1,&framebuffer);
    if(texture)glDeleteTextures(1,&texture);
    if(renderbuffer)glDeleteRenderbuffers(1,&renderbuffer);
    pl_tex_destroy(gpu,&input);av_free(metadata);dvbridge_renderer_destroy(r);
    assert(dvbridge_retirement_owner_destroy(&owner));reference_gpu_destroy(&g);
    fprintf(stderr,"PASS actual target kind=%u ownership preserved\n",kind);
}
