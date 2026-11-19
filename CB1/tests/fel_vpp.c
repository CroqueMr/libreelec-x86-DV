/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_gl_frame.h"
#include "dvbridge_fel_vpp.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <libavutil/hwcontext.h>

static AVFrame *input(AVBufferRef *device, int ycode)
{
    AVBufferRef *pool = av_hwframe_ctx_alloc(device);
    assert(pool);
    AVHWFramesContext *fc = (void *)pool->data;
    fc->format = AV_PIX_FMT_VAAPI; fc->sw_format = AV_PIX_FMT_P010LE;
    fc->width = 1920; fc->height = 1080; fc->initial_pool_size = 2;
    assert(av_hwframe_ctx_init(pool) >= 0);
    AVFrame *hw = av_frame_alloc(), *sw = av_frame_alloc();
    assert(hw && sw && av_hwframe_get_buffer(pool, hw, 0) >= 0);
    sw->format = AV_PIX_FMT_P010LE; sw->width = 1920; sw->height = 1080;
    assert(av_frame_get_buffer(sw, 32) >= 0);
    for (int p = 0; p < 2; ++p)
        for (int y = 0; y < (p ? 540 : 1080); ++y)
            for (int x = 0; x < 1920; ++x)
                ((uint16_t *)(sw->data[p] + y * sw->linesize[p]))[x] =
                    (p ? (x & 1 ? 640 : 384) : ycode + (x < 960 ? -64 : 64)) << 6;
    assert(av_hwframe_transfer_data(hw, sw, 0) >= 0);
    av_frame_free(&sw); av_buffer_unref(&pool);
    return hw;
}

static void *capture(const struct dvbridge_fel_vpp_image *image)
{
    const size_t bytes = (size_t)image->width * image->height * 8;
    void *pixels = malloc(bytes); assert(pixels);
    GLuint fbo; glGenFramebuffers(1, &fbo); glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, image->plane.texture, 0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
    glReadPixels(0, 0, image->width, image->height, GL_RGBA, GL_UNSIGNED_SHORT, pixels);
    assert(glGetError() == GL_NO_ERROR);
    glBindFramebuffer(GL_FRAMEBUFFER, 0); glDeleteFramebuffers(1, &fbo);
    return pixels;
}

static void sample(const struct dvbridge_fel_vpp_image *image, int ycode)
{
    GLuint fbo; uint16_t pixel[4];
    glGenFramebuffers(1, &fbo); glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    for (int side = 0; side < 2; ++side) {
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, image->plane.texture, 0);
        assert(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
        glReadPixels(side ? 3000 : 500, 1000, 1, 1, GL_RGBA, GL_UNSIGNED_SHORT, pixel);
        assert(glGetError() == GL_NO_ERROR);
        assert(abs((int)pixel[0] - (384 << 6)) <= 64);
        assert(abs((int)pixel[1] - ((ycode + (side ? 64 : -64)) << 6)) <= 64);
        assert(abs((int)pixel[2] - (640 << 6)) <= 64);
    }
    glBindFramebuffer(GL_FRAMEBUFFER, 0); glDeleteFramebuffers(1, &fbo);
}

int main(void)
{
    av_log_set_level(AV_LOG_DEBUG);
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (!eglInitialize(display, NULL, NULL)) return 77;
    assert(eglBindAPI(EGL_OPENGL_ES_API));
    EGLConfig config; EGLint n;
    const EGLint attr[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, 0x40, EGL_NONE};
    const EGLint sa[] = {EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE}, ca[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    assert(eglChooseConfig(display, attr, &config, 1, &n) && n);
    EGLSurface surface = eglCreatePbufferSurface(display, config, sa);
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, ca);
    assert(eglMakeCurrent(display, surface, surface, context));
    AVBufferRef *device = NULL;
    if (av_hwdevice_ctx_create(&device, AV_HWDEVICE_TYPE_VAAPI, "/dev/dri/renderD128", NULL, 0) < 0)
        return 77;
    assert(!dvbridge_fel_vpp_create(NULL, 3840, 2160));
    assert(!dvbridge_fel_vpp_create(device, 0, 2160));
    struct dvbridge_fel_vpp *vpp = dvbridge_fel_vpp_create(device, 3840, 2160);
    if (getenv("VPP_EXPECT_UNAVAILABLE") || !vpp) {
        assert(!vpp);
        av_buffer_unref(&device);
        eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        eglDestroyContext(display, context); eglDestroySurface(display, surface); eglTerminate(display);
        puts("FEL VPP: unsupported output rejected cleanly");
        return getenv("VPP_EXPECT_UNAVAILABLE") ? 0 : 77;
    }
    assert(vpp);
    AVFrame *a = input(device, 256), *b = input(device, 768);
    const struct dvbridge_fel_vpp_image *first = NULL, *second = NULL, *third = NULL;
    GLuint sentinel; glGenTextures(1, &sentinel); glBindTexture(GL_TEXTURE_2D, sentinel);
    assert(dvbridge_fel_vpp_acquire(vpp, a, &first) == DVBRIDGE_VPP_OK);
    GLint binding; glGetIntegerv(GL_TEXTURE_BINDING_2D, &binding); assert((GLuint)binding == sentinel);
    assert(first && first->width == 3840 && first->height == 2160);
    pl_opengl gl = pl_opengl_create(NULL, pl_opengl_params(
        .get_proc_addr = (pl_voidfunc_t (*)(const char *))eglGetProcAddress,
        .egl_display = display, .egl_context = context));
    assert(gl);
    struct dvbridge_gl_frame wrapped = {0};
    const struct dvbridge_gl_plane planes[3] = {first->plane};
    assert(dvbridge_gl_frame_import(&wrapped, gl->gpu, DVBRIDGE_Y416, 3840, 2160, planes));
    assert(wrapped.frame.num_planes == 1 && wrapped.frame.repr.bits.color_depth == 10 &&
           wrapped.frame.repr.bits.bit_shift == 6 && wrapped.frame.planes[0].components == 3);
    assert(wrapped.frame.planes[0].component_mapping[0] == 1 &&
           wrapped.frame.planes[0].component_mapping[1] == 0 && wrapped.frame.planes[0].component_mapping[2] == 2 &&
           wrapped.frame.planes[0].shift_x == -0.5f);
    dvbridge_gl_frame_release(&wrapped);
    assert(dvbridge_fel_vpp_acquire(vpp, b, &second) == DVBRIDGE_VPP_OK);
    assert(first != second && first->plane.texture != second->plane.texture);
    assert(dvbridge_fel_vpp_acquire(vpp, a, &third) == DVBRIDGE_VPP_BUSY && !third);
    assert(!dvbridge_fel_vpp_destroy(&vpp) && vpp);
    sample(first, 256); sample(second, 768);
    glFinish(); dvbridge_fel_vpp_release(vpp, first);
    assert(dvbridge_fel_vpp_acquire(vpp, b, &third) == DVBRIDGE_VPP_OK && third == first);
    sample(third, 768);
    puts("FEL VPP Y416: colored planes, bounded leases and reuse passed");
    dvbridge_fel_vpp_release(vpp, second); glFinish(); dvbridge_fel_vpp_release(vpp, third);
    AVFrame *fixtures[] = {a, b};
    for (unsigned i = 0; i < 2; ++i) {
        assert(dvbridge_fel_vpp_acquire_chroma(vpp, fixtures[i], PL_CHROMA_LEFT, &first) == DVBRIDGE_VPP_OK);
        void *expected = capture(first);
        glFinish(); dvbridge_fel_vpp_release(vpp, first);
        assert(dvbridge_fel_vpp_prefetch_chroma(vpp, fixtures[i], PL_CHROMA_LEFT, &second) == DVBRIDGE_VPP_PENDING);
        assert(!dvbridge_fel_vpp_destroy(&vpp) && vpp);
        assert(dvbridge_fel_vpp_finish(vpp, second) == DVBRIDGE_VPP_OK);
        void *actual = capture(second);
        assert(!memcmp(expected, actual, (size_t)3840 * 2160 * 8));
        free(expected); free(actual);
        glFinish(); dvbridge_fel_vpp_release(vpp, second);
    }
    assert(dvbridge_fel_vpp_prefetch_chroma(vpp, b, PL_CHROMA_LEFT, &first) == DVBRIDGE_VPP_PENDING);
    dvbridge_fel_vpp_release(vpp, first);
    assert(dvbridge_fel_vpp_acquire(vpp, a, &first) == DVBRIDGE_VPP_OK);
    sample(first, 256); glFinish(); dvbridge_fel_vpp_release(vpp, first);
    puts("FEL VPP prefetch: complete RGBA16 bytes equal blocking output; cancellation/reuse passed");
    AVFrame invalid = {0};
    assert(dvbridge_fel_vpp_acquire(vpp, &invalid, &first) == DVBRIDGE_VPP_FAILED && !first);
    assert(dvbridge_fel_vpp_destroy(&vpp) && !vpp);
    pl_opengl_destroy(&gl);
    av_frame_free(&a); av_frame_free(&b); av_buffer_unref(&device);
    glDeleteTextures(1, &sentinel);
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(display, context); eglDestroySurface(display, surface); eglTerminate(display);
}
