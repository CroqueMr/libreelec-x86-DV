/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <libplacebo/renderer.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned passes;
static enum pl_hdr_metadata_type selected_metadata;
static bool traced_render(pl_renderer renderer, const struct pl_frame *image,
                          const struct pl_frame *target, const struct pl_render_params *params)
{
    assert(params->min_fbo_precision == 32 && !params->peak_detect_params);
    if (!image->repr.dovi) {
        assert(!memcmp(&image->color,&target->color,sizeof(image->color)));
        return pl_render_image(renderer,image,target,params);
    }
    ++passes;
    assert(params->color_map_params);
    selected_metadata = params->color_map_params->metadata;
    assert(!params->color_map_params->inverse_tone_mapping);
    assert(params->color_map_params->tone_mapping_function == &pl_tone_map_spline);
    assert(params->color_map_params->gamut_mapping == &pl_gamut_map_perceptual);
    return pl_render_image(renderer,image,target,params);
}
#define pl_render_image traced_render
#include "dvbridge_render.c"
#undef pl_render_image
#include "task4_api.h"
#include "task3_fixture.h"
#include <EGL/egl.h>

static void sample(pl_gpu gpu, pl_tex tex, float pixel[4])
{
    GLuint fbo, id = pl_opengl_unwrap(gpu,tex,NULL,NULL,NULL);
    glGenFramebuffers(1,&fbo); glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,id,0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
    glReadPixels(1920,1080,1,1,GL_RGBA,GL_FLOAT,pixel);
    assert(glGetError()==GL_NO_ERROR);
    glBindFramebuffer(GL_FRAMEBUFFER,0); glDeleteFramebuffers(1,&fbo);
}

int main(int argc,char **argv)
{
    assert(argc==2); setvbuf(stdout,NULL,_IONBF,0);
    size_t bytes; AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=2;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0), *l6=av_dovi_get_ext(m,1);
    l1->level=1; l1->l1.min_pq=12; l1->l1.avg_pq=3079; l1->l1.max_pq=4095;
    l6->level=6; l6->l6.max_luminance=4000;
    struct dvbridge_hdr10_session session;
    assert(dvbridge_hdr10_session_init(&session,m,bytes));
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display,NULL,NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    EGLConfig cfg; EGLint n;
    const EGLint attr[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,0x40,EGL_NONE};
    const EGLint sa[]={EGL_WIDTH,64,EGL_HEIGHT,64,EGL_NONE}, ca[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    assert(eglChooseConfig(display,attr,&cfg,1,&n) && n);
    EGLSurface surf=eglCreatePbufferSurface(display,cfg,sa);
    EGLContext ctx=eglCreateContext(display,cfg,EGL_NO_CONTEXT,ca);
    assert(eglMakeCurrent(display,surf,surf,ctx));
    pl_opengl gl=pl_opengl_create(NULL,pl_opengl_params(
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,
        .egl_display=display,.egl_context=ctx,.allow_software=true));
    assert(gl); struct dvbridge_renderer *r=dvbridge_renderer_create(gl->gpu); assert(r);
    float input[64*64*4];
    for(int i=0;i<64*64*4;++i) input[i]=i%4==3?1:0.3f+0.6f*((i/4)%64)/63;
    pl_fmt fmt=pl_find_fmt(gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE);
    pl_tex tex=pl_tex_create(gl->gpu,pl_tex_params(.w=64,.h=64,.format=fmt,.sampleable=true,.initial_data=input));
    assert(tex);
    struct pl_frame frame={.num_planes=1,.planes={{.texture=tex,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,64,64}};
    struct dvbridge_geometry geom={64,64,840,0,2160,2160};
    assert(HDR10(r,&session,&frame,m,bytes,0,NAN,geom));
    assert(selected_metadata==PL_HDR_METADATA_CIE_Y && passes==1);
    float first[4], changed[4]; sample(gl->gpu,dvbridge_render_texture(r),first);
    if (!strcmp(argv[1],"latch")) {
        l6->l6.max_luminance=1000;
        assert(HDR10(r,&session,&frame,m,bytes,1,NAN,geom));
        printf("target after changed L6: %g\n",r->reconstructed_color.hdr.max_luma);
        sample(gl->gpu,dvbridge_render_texture(r),changed);
        printf("changed-L6 center PQ: %.9g %.9g %.9g -> %.9g %.9g %.9g\n",
               first[0],first[1],first[2],changed[0],changed[1],changed[2]);
        assert(r->reconstructed_color.hdr.max_luma==4000);
        assert(!memcmp(first,changed,sizeof(first)));
        dvbridge_renderer_reset(r);
        assert(HDR10(r,&session,&frame,m,bytes,0,NAN,geom));
        assert(r->reconstructed_color.hdr.max_luma==4000);
        assert(session.output.max_luminance==4000);
    } else if (!strcmp(argv[1],"mapping")) {
        l1->l1.avg_pq=1200; l1->l1.max_pq=3300;
        assert(HDR10(r,&session,&frame,m,bytes,1,NAN,geom));
        sample(gl->gpu,dvbridge_render_texture(r),changed);
        assert(memcmp(first,changed,sizeof(first))); /* Actual per-picture L1 affects pixels. */
        l1->l1.avg_pq=4096;
        assert(HDR10(r,&session,&frame,m,bytes,2,NAN,geom));
        assert(selected_metadata==PL_HDR_METADATA_HDR10);
        sample(gl->gpu,dvbridge_render_texture(r),first);
        *l1=*l6; m->num_ext_blocks=1;
        assert(HDR10(r,&session,&frame,m,bytes,3,NAN,geom));
        assert(selected_metadata==PL_HDR_METADATA_HDR10);
        sample(gl->gpu,dvbridge_render_texture(r),changed);
        assert(!memcmp(first,changed,sizeof(first)));
        AVDOVIDmData *e=av_dovi_get_ext(m,1);
        e->level=2; e->l2.trim_slope=1900; m->num_ext_blocks=2;
        assert(HDR10(r,&session,&frame,m,bytes,4,NAN,geom));
        sample(gl->gpu,dvbridge_render_texture(r),changed); assert(!memcmp(first,changed,sizeof(first)));
        e->level=8; e->dvbridge_original_bytes[0]=99;
        assert(HDR10(r,&session,&frame,m,bytes,5,NAN,geom));
        sample(gl->gpu,dvbridge_render_texture(r),changed); assert(!memcmp(first,changed,sizeof(first)));
    } else if (!strcmp(argv[1],"joined")) {
        assert(!dvbridge_render_candidate(r));
        pl_fmt outfmt=pl_find_fmt(gl->gpu,PL_FMT_UNORM,4,10,0,PL_FMT_CAP_RENDERABLE);
        assert(outfmt);
        pl_tex out=pl_tex_create(gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=outfmt,.renderable=true));
        assert(out);
        assert(dvbridge_render_hdr10(r,out,false,true,10));
        assert(passes==1); /* Resolve is quantization, not a second map. */
        assert(dvbridge_render_commit(r)); assert(!dvbridge_render_commit(r));
        assert(!dvbridge_render_texture(r));
        pl_tex_destroy(gl->gpu,&out);
    } else if (!strcmp(argv[1],"rejection")) {
        av_dovi_get_header(m)->disable_residual_flag=0;
        assert(!HDR10(r,&session,&frame,m,bytes,1,NAN,geom));
        assert(!dvbridge_render_commit(r));
        av_dovi_get_header(m)->disable_residual_flag=1;
        av_dovi_get_mapping(m)->curves[0].poly_order[0]=3;
        assert(!HDR10(r,&session,&frame,m,bytes,2,NAN,geom));
        assert(!dvbridge_render_commit(r));
        assert(session.target.hdr.max_luma==4000 && session.output.max_luminance==4000);
    } else assert(0);
    dvbridge_renderer_destroy(r); pl_tex_destroy(gl->gpu,&tex); av_free(m); pl_opengl_destroy(&gl);
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(display,ctx); eglDestroySurface(display,surf); eglTerminate(display);
    puts("PASS: real Basic reconstruction, policy and single-use presentation control");
}
