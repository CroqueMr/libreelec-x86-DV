/* SPDX-License-Identifier: MIT */
#ifndef CB1_REFERENCE_TEST_H
#define CB1_REFERENCE_TEST_H
#include "dvbridge_render.h"
#include "dvbridge_policy.h"
#include "task3_fixture.h"
#include <EGL/egl.h>
#include <GLES3/gl31.h>
#include <libplacebo/opengl.h>
#include <math.h>
#include <string.h>

/* Weak ingress declarations let the pre-implementation test fail an assertion. */
#ifndef DVBRIDGE_HDR10_POLICY_API
struct dvbridge_hdr10_policy_output {
    struct dvbridge_identity identity;
    struct dvbridge_policy policy;
    struct pl_color_space nominal_target, container;
    struct dvbridge_hdr10_metadata hdr10;
    struct dvbridge_geometry geometry;
    bool fel_reconstructed, resolved;
    pl_tex final_target;
};
extern bool dvbridge_render_hdr10_policy_rgb(struct dvbridge_renderer *, const struct dvbridge_policy *,
    const struct dvbridge_identity *, const struct pl_frame *, const void *, size_t,
    double, double, struct dvbridge_geometry) __attribute__((weak));
extern const struct dvbridge_hdr10_policy_output *dvbridge_render_policy_output(const struct dvbridge_renderer *) __attribute__((weak));
extern bool dvbridge_render_hdr10_policy_resolve(struct dvbridge_renderer *, pl_tex, bool, bool, unsigned) __attribute__((weak));
extern bool dvbridge_render_policy_commit(struct dvbridge_renderer *, const struct dvbridge_identity *, pl_tex) __attribute__((weak));
extern void dvbridge_render_policy_cancel(struct dvbridge_renderer *) __attribute__((weak));
extern bool dvbridge_render_policy_committed(const struct dvbridge_renderer *, struct dvbridge_hdr10_policy_output *) __attribute__((weak));
#endif

static void reference_log(void *priv, enum pl_log_level level, const char *msg)
{ (void)priv; (void)level; fprintf(stderr,"%s\n",msg); }
struct reference_gpu { EGLDisplay display; EGLSurface surface; EGLContext context; pl_opengl gl; pl_log log; };
static struct reference_gpu reference_gpu_create(void)
{
    struct reference_gpu g = {.display=eglGetDisplay(EGL_DEFAULT_DISPLAY)};
    assert(eglInitialize(g.display,NULL,NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    EGLConfig config; EGLint n;
    const EGLint attr[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,0x40,EGL_NONE};
    const EGLint sa[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE}, ca[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    assert(eglChooseConfig(g.display,attr,&config,1,&n) && n);
    g.surface=eglCreatePbufferSurface(g.display,config,sa);
    g.context=eglCreateContext(g.display,config,EGL_NO_CONTEXT,ca);
    assert(eglMakeCurrent(g.display,g.surface,g.surface,g.context));
    if (getenv("CB1_REFERENCE_TRACE"))
        g.log=pl_log_create(PL_API_VER,pl_log_params(.log_cb=reference_log,.log_level=PL_LOG_TRACE));
    g.gl=pl_opengl_create(g.log,pl_opengl_params(.get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,
        .egl_display=g.display,.egl_context=g.context,.allow_software=true));
    assert(g.gl);
    fprintf(stderr,"GPU: %s; %s; GLSL %s\n",glGetString(GL_RENDERER),glGetString(GL_VERSION),glGetString(GL_SHADING_LANGUAGE_VERSION));
    GLint range[2],precision; glGetShaderPrecisionFormat(GL_FRAGMENT_SHADER,GL_HIGH_FLOAT,range,&precision);
    fprintf(stderr,"fragment highp: range %d/%d precision %d; linear16 LUT %s\n",range[0],range[1],precision,
        pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_LINEAR)?"available":"unavailable");
    pl_fmt tone_fmt=pl_find_fmt(g.gl->gpu,PL_FMT_FLOAT,1,16,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR);
    fprintf(stderr,"pinned automatic tone LUT format: %s depth %d host %d\n",tone_fmt?tone_fmt->name:"none",
        tone_fmt?tone_fmt->component_depth[0]:0,tone_fmt?tone_fmt->host_bits[0]:0);
    return g;
}
static void reference_gpu_destroy(struct reference_gpu *g)
{
    pl_opengl_destroy(&g->gl);
    pl_log_destroy(&g->log);
    eglMakeCurrent(g->display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(g->display,g->context); eglDestroySurface(g->display,g->surface); eglTerminate(g->display);
}
static pl_tex reference_texture(pl_gpu gpu,int w,int h,const float *data)
{
    pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
    assert(fmt);
    pl_tex tex=pl_tex_create(gpu,pl_tex_params(.w=w,.h=h,.format=fmt,.sampleable=true,.renderable=true,.initial_data=data));
    assert(tex); return tex;
}
static void reference_read(pl_gpu gpu,pl_tex tex,int x,int y,int w,int h,float *data)
{
    GLuint fbo,id=pl_opengl_unwrap(gpu,tex,NULL,NULL,NULL);
    assert(id); glGenFramebuffers(1,&fbo); glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,id,0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
    glReadPixels(x,y,w,h,GL_RGBA,GL_FLOAT,data); assert(glGetError()==GL_NO_ERROR);
    glBindFramebuffer(GL_FRAMEBUFFER,0); glDeleteFramebuffers(1,&fbo);
}
static struct pl_frame reference_frame(pl_tex tex,int w,int h)
{
    return (struct pl_frame){.num_planes=1,.planes={{.texture=tex,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,w,h}};
}
static struct dvbridge_policy reference_policy(void)
{
    return (struct dvbridge_policy){.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={1500,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT709}};
}
#endif
