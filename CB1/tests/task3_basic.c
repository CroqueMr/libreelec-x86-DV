#include "task4_legacy_calls.h"
/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Candidate-only probe. Pixel readback and private state stay in tests. */
#include "dvbridge_render.c"
#include "task3_fixture.h"
#include <EGL/egl.h>
#include <stdio.h>
#include <string.h>

static void sample(pl_gpu gpu, pl_tex tex, float pixels[5][4])
{
    GLuint fbo, id = pl_opengl_unwrap(gpu, tex, NULL, NULL, NULL);
    glGenFramebuffers(1, &fbo); glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, id, 0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
    const int xy[][2] = {{1000,100},{1400,500},{1920,1080},{2500,1700},{2900,2100}};
    for (int i = 0; i < 5; ++i)
        glReadPixels(xy[i][0], xy[i][1], 1, 1, GL_RGBA, GL_FLOAT, pixels[i]);
    assert(glGetError() == GL_NO_ERROR);
    glBindFramebuffer(GL_FRAMEBUFFER, 0); glDeleteFramebuffers(1, &fbo);
}

int main(int argc, char **argv)
{
    assert(argc == 2); setvbuf(stdout, NULL, _IONBF, 0);
    const char *mode = argv[1]; size_t bytes;
    AVDOVIMetadata *m = task3_fixture(&bytes);
    struct dvbridge_color mapped;
    struct pl_color_space target;
    if (!strcmp(mode, "zero-mapper") || !strcmp(mode, "zero-target")) {
        if (!strcmp(mode, "zero-mapper")) assert(dvbridge_map_color(&mapped, m, bytes, false));
        else {
            struct dvbridge_hdr10_metadata signal;
            assert(dvbridge_hdr10_target(&target, m, bytes));
            assert(dvbridge_get_hdr10_metadata(&signal, m, bytes));
            assert(signal.max_luminance == 10000 && !signal.max_cll && !signal.max_fall);
        }
        av_free(m); puts("PASS: zero-extension common consumer"); return 0;
    }
    m->num_ext_blocks = 2;
    AVDOVIDmData *l1 = av_dovi_get_ext(m, 0), *l6 = av_dovi_get_ext(m, 1);
    l1->level = 1; l1->l1.min_pq = 12; l1->l1.avg_pq = 3079; l1->l1.max_pq = 4095;
    l6->level = 6; l6->l6.max_luminance = 4000;
    if (!strncmp(mode, "mapper-", 7)) {
        assert(dvbridge_map_color(&mapped, m, bytes, false));
        AVDOVIColorMetadata *c = av_dovi_get_color(m);
        if (!strcmp(mode, "mapper-eotf")) c->signal_eotf = 1;
        else if (!strcmp(mode, "mapper-space")) c->signal_color_space = 1;
        else if (!strcmp(mode, "mapper-param0")) c->signal_eotf_param0 = 1;
        else if (!strcmp(mode, "mapper-param1")) c->signal_eotf_param1 = 1;
        else if (!strcmp(mode, "mapper-param2")) c->signal_eotf_param2 = 1;
        else if (!strcmp(mode, "mapper-pq-order")) { c->source_min_pq = 2000; c->source_max_pq = 1000; }
        else if (!strcmp(mode, "mapper-pq-range")) c->source_max_pq = 4096;
        else if (!strcmp(mode, "mapper-flag")) av_dovi_get_header(m)->disable_residual_flag = 2;
        else assert(0);
        assert(!dvbridge_map_color(&mapped, m, bytes, false));
        av_free(m); puts("PASS: mapper rejects consumed invalid value"); return 0;
    }
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display, NULL, NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    EGLConfig cfg; EGLint n;
    EGLint attr[] = {EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,0x40,EGL_NONE};
    EGLint sa[] = {EGL_WIDTH,64,EGL_HEIGHT,64,EGL_NONE}, ca[] = {EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    assert(eglChooseConfig(display, attr, &cfg, 1, &n) && n);
    EGLSurface surf = eglCreatePbufferSurface(display, cfg, sa);
    EGLContext ctx = eglCreateContext(display, cfg, EGL_NO_CONTEXT, ca);
    assert(eglMakeCurrent(display, surf, surf, ctx));
    pl_opengl gl = pl_opengl_create(NULL, pl_opengl_params(
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,
        .egl_display=display,.egl_context=ctx,.allow_software=true));
    assert(gl);
    struct dvbridge_renderer *r = dvbridge_renderer_create(gl->gpu); assert(r);
    printf("renderer=%s fragment_quad=%d mode=%s\n", glGetString(GL_RENDERER), r->fragment_quad, mode);
    float input[64*64*4];
    for (int i=0;i<64*64*4;++i) input[i] = i%4 == 3 ? 1 : 0.3f + 0.6f*((i/4)%64)/63;
    pl_fmt fmt = pl_find_fmt(gl->gpu, PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE);
    pl_tex tex = pl_tex_create(gl->gpu,pl_tex_params(.w=64,.h=64,.format=fmt,.sampleable=true,.initial_data=input));
    assert(tex);
    struct pl_frame frame = {.num_planes=1,.planes={{.texture=tex,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,64,64}};
    struct dvbridge_geometry geom = {64,64,840,0,2160,2160};
    assert(legacy_hdr10(r,&frame,m,bytes,0,NAN,geom));
    float baseline[5][4], changed[5][4]; sample(gl->gpu, dvbridge_render_texture(r), baseline);
    if (!strcmp(mode, "native-transition")) {
        struct dvbridge_context *native_context = dvbridge_create();
        struct dvbridge_candidate *first = dvbridge_prepare(native_context, m, bytes, 0, geom, false);
        assert(first && dvbridge_commit(native_context, first));
        struct dvbridge_candidate *next = dvbridge_prepare(native_context, m, bytes, 1001.0/24000, geom, false);
        assert(next);
        uint32_t expected[512]; memcpy(expected, dvbridge_packets(next,NULL), sizeof(expected));
        assert(dvbridge_render_rgb(r,&frame,m,bytes,0,NAN,geom));
        assert(dvbridge_render_commit(r));
        assert(legacy_hdr10(r,&frame,m,bytes,50,NAN,geom));
        assert(dvbridge_render_commit(r)); assert(!dvbridge_render_commit(r));
        assert(dvbridge_render_rgb(r,&frame,m,bytes,1001.0/24000,NAN,geom));
        assert(!memcmp(expected,dvbridge_packets(dvbridge_render_candidate(r),NULL),sizeof(expected)));
        dvbridge_candidate_destroy(first); dvbridge_candidate_destroy(next); dvbridge_destroy(native_context);
    } else if (!strcmp(mode, "extension-controls")) {
        /* First L6 remains authoritative; duplicates do not create new trim semantics. */
        AVDOVIDmData *e=av_dovi_get_ext(m,2); *e=*l6; e->l6.max_luminance=1000;
        m->num_ext_blocks=3;
        assert(dvbridge_hdr10_target(&target,m,bytes) && target.hdr.max_luma==4000);
        assert(dvbridge_render_rgb(r,&frame,m,bytes,1,NAN,geom));
        assert(legacy_hdr10(r,&frame,m,bytes,1,NAN,geom));
        sample(gl->gpu,dvbridge_render_texture(r),changed); assert(!memcmp(baseline,changed,sizeof(baseline)));
        *e=(AVDOVIDmData){0}; e->level=8; e->dvbridge_raw_magic=0x41424456;
        e->dvbridge_original_length=10; e->dvbridge_original_bytes[0]=1;
        *av_dovi_get_ext(m,3)=*e; m->num_ext_blocks=4;
        assert(dvbridge_render_rgb(r,&frame,m,bytes,2,NAN,geom));
        assert(legacy_hdr10(r,&frame,m,bytes,2,NAN,geom));
        sample(gl->gpu,dvbridge_render_texture(r),changed); assert(!memcmp(baseline,changed,sizeof(baseline)));
        *e=(AVDOVIDmData){0}; e->level=5; *av_dovi_get_ext(m,3)=*e;
        assert(!dvbridge_render_rgb(r,&frame,m,bytes,3,NAN,geom));
        assert(!legacy_hdr10(r,&frame,m,bytes,3,NAN,geom));
        assert(!dvbridge_render_commit(r));
        m->num_ext_blocks=2;
        AVDOVIColorMetadata *c=av_dovi_get_color(m); c->signal_eotf=0;
        assert(!legacy_hdr10(r,&frame,m,bytes,4,NAN,geom));
        c->signal_eotf=65535; c->source_max_pq=4096;
        assert(!legacy_hdr10(r,&frame,m,bytes,5,NAN,geom));
        c->source_max_pq=4095; av_dovi_get_header(m)->disable_residual_flag=2;
        assert(!legacy_hdr10(r,&frame,m,bytes,6,NAN,geom));
        assert(!dvbridge_render_commit(r));
    } else if (!strcmp(mode, "no-candidate")) {
        assert(!dvbridge_render_candidate(r));
        unsigned count = 999;
        assert(!dvbridge_packets(dvbridge_render_candidate(r), &count) && !count);
        assert(dvbridge_render_commit(r)); assert(!dvbridge_render_commit(r));
        assert(!dvbridge_render_texture(r));
    } else if (!strcmp(mode, "resolve-failure")) {
        assert(!dvbridge_render_hdr10(r, NULL, false, false, 10));
        assert(!dvbridge_render_commit(r)); assert(!dvbridge_render_texture(r));
    } else if (!strcmp(mode, "missing-l1") || !strcmp(mode, "zero-render") || !strcmp(mode, "unusable-l1")) {
        if (!strcmp(mode, "zero-render")) m->num_ext_blocks = 0;
        else if (!strcmp(mode, "missing-l1")) { *l1 = *l6; m->num_ext_blocks = 1; }
        else l1->l1.avg_pq = 4096;
        assert(dvbridge_map_color(&mapped,m,bytes,false));
        assert(dvbridge_hdr10_target(&target,m,bytes));
        assert(!dvbridge_render_rgb(r,&frame,m,bytes,1,NAN,geom));
        assert(legacy_hdr10(r,&frame,m,bytes,1,NAN,geom));
        assert(!dvbridge_render_candidate(r));
        assert(dvbridge_render_commit(r)); assert(!dvbridge_render_commit(r));
    } else if (!strcmp(mode, "unknown") || !strcmp(mode, "duplicate-l2") ||
               !strcmp(mode, "raw-invalid") || !strcmp(mode, "raw-trailer")) {
        AVDOVIDmData *e = av_dovi_get_ext(m, 2); *e = (AVDOVIDmData){0};
        if (!strcmp(mode, "unknown")) e->level = 42;
        else if (!strcmp(mode, "raw-invalid")) e->level = 8;
        else if (!strcmp(mode, "raw-trailer")) {
            e->level = 8; e->dvbridge_raw_magic = 0x41424456;
            e->dvbridge_original_length = 12; e->dvbridge_original_bytes[11] = 1;
        }
        else { e->level = 2; e->l2.target_max_pq = 3079; e->l2.trim_slope = 1500; }
        m->num_ext_blocks = 3;
        if (e->level == 2) { *av_dovi_get_ext(m,3) = *e; m->num_ext_blocks = 4; }
        assert(!dvbridge_render_rgb(r,&frame,m,bytes,1,NAN,geom));
        assert(legacy_hdr10(r,&frame,m,bytes,1,NAN,geom));
        sample(gl->gpu,dvbridge_render_texture(r),changed);
        assert(!memcmp(baseline,changed,sizeof(baseline)));
        printf("unapplied extension pixels bit identical\n");
    } else if (!strcmp(mode, "controls")) {
        uint32_t native[512];
        assert(dvbridge_render_rgb(r,&frame,m,bytes,0,NAN,geom));
        memcpy(native,dvbridge_packets(r->pending,NULL),sizeof(native));
        assert(legacy_hdr10(r,&frame,m,bytes,1,NAN,geom));
        dvbridge_renderer_reset(r); assert(!dvbridge_render_commit(r));
        assert(dvbridge_render_rgb(r,&frame,m,bytes,0,NAN,geom));
        assert(!memcmp(native,dvbridge_packets(r->pending,NULL),sizeof(native)));
        /* Basic success must not advance native serializer IDs or refresh. */
        assert(legacy_hdr10(r,&frame,m,bytes,1,NAN,geom));
        assert(dvbridge_render_commit(r));
        assert(dvbridge_render_rgb(r,&frame,m,bytes,0,NAN,geom));
        assert(!memcmp(native,dvbridge_packets(r->pending,NULL),sizeof(native)));
        *av_dovi_get_ext(m,2)=*l1; m->num_ext_blocks=3;
        assert(!legacy_hdr10(r,&frame,m,bytes,2,NAN,geom));
        assert(!dvbridge_render_commit(r));
        m->num_ext_blocks=2;
        frame.rotation=90;
        assert(!legacy_hdr10(r,&frame,m,bytes,3,NAN,geom));
        assert(!dvbridge_render_commit(r)); frame.rotation=0;
        AVDOVIRpuDataHeader *h=av_dovi_get_header(m); h->disable_residual_flag=0;
        assert(!legacy_hdr10(r,&frame,m,bytes,4,NAN,geom));
        assert(!dvbridge_render_commit(r)); h->disable_residual_flag=1;
        av_dovi_get_mapping(m)->curves[0].poly_order[0]=3;
        assert(!legacy_hdr10(r,&frame,m,bytes,5,NAN,geom));
        assert(!dvbridge_render_commit(r));
    } else assert(0);
    dvbridge_renderer_destroy(r); pl_tex_destroy(gl->gpu,&tex); av_free(m);
    pl_opengl_destroy(&gl);
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(display,ctx); eglDestroySurface(display,surf); eglTerminate(display);
    puts("PASS: Basic correction or transaction contract");
}
