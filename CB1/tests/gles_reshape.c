/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <EGL/egl.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <libplacebo/opengl.h>
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/colorspace.h>
#include <libplacebo/shaders/custom.h>

int main(void)
{
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display, NULL, NULL));
    assert(eglBindAPI(EGL_OPENGL_ES_API));
    EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, 0x40, EGL_NONE};
    EGLConfig config;
    EGLint count;
    assert(eglChooseConfig(display, attributes, &config, 1, &count) && count);
    EGLint surface_attributes[] = {EGL_WIDTH, 64, EGL_HEIGHT, 1, EGL_NONE};
    EGLSurface surface = eglCreatePbufferSurface(display, config, surface_attributes);
    EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attributes);
    assert(context != EGL_NO_CONTEXT && surface != EGL_NO_SURFACE);
    assert(eglMakeCurrent(display, surface, surface, context));
    pl_opengl gl = pl_opengl_create(NULL, pl_opengl_params(
        .get_proc_addr = (pl_voidfunc_t (*)(const char *))eglGetProcAddress,
        .egl_display = display, .egl_context = context, .allow_software = true,
        .max_glsl_version = 300));
    assert(gl);
    pl_dispatch dispatch = pl_dispatch_create(NULL, gl->gpu);
    assert(dispatch);
    pl_fmt format = pl_find_fmt(gl->gpu, PL_FMT_FLOAT, 4, 32, 32, PL_FMT_CAP_RENDERABLE);
    if (!format) {
        for (int i = 0; i < gl->gpu->num_formats; ++i) {
            pl_fmt f = gl->gpu->formats[i];
            fprintf(stderr, "%s type=%d depth=%d host=%d caps=%x\n", f->name,
                    f->type, f->component_depth[0], f->host_bits[0], f->caps);
        }
    }
    assert(format);
    pl_tex output = pl_tex_create(gl->gpu, pl_tex_params(
        .w = 64, .h = 1, .format = format, .renderable = true, .host_readable = true));
    assert(output);
    unsigned samples = 0;
    for (int iteration = 0; iteration < 6; ++iteration) {
        bool quadratic = iteration % 2;
        struct pl_dovi_metadata dovi = {0};
        for (int c = 0; c < 3; ++c) {
            dovi.comp[c].num_pivots = 2;
            dovi.comp[c].pivots[1] = 1.0f;
            dovi.comp[c].poly_coeffs[0][quadratic ? 2 : 1] = 1.0f;
        }
        pl_shader shader = pl_dispatch_begin(dispatch);
        assert(pl_shader_custom(shader, &(struct pl_custom_shader){
            .input = PL_SHADER_SIG_NONE, .output = PL_SHADER_SIG_COLOR,
            .body = "color = vec4(gl_FragCoord.x / 64.0, 0.25, 0.75, 1.0);"}));
        pl_shader_dovi_reshape(shader, &dovi);
        assert(pl_dispatch_finish(dispatch, pl_dispatch_params(.shader = &shader, .target = output)));
        float pixels[64][4];
        assert(pl_tex_download(gl->gpu, pl_tex_transfer_params(.tex = output, .ptr = pixels)));
        for (int x = 0; x < 64; ++x) {
            float expected[] = {(x + 0.5f) / 64, .25f, .75f, 1};
            for (int c = 0; c < 4; ++c) {
                float value = quadratic && c != 3 ? expected[c] * expected[c] : expected[c];
                assert(isfinite(pixels[x][c]) && fabsf(pixels[x][c] - value) <= 1e-6f);
                ++samples;
            }
        }
    }
    pl_tex_destroy(gl->gpu, &output);
    pl_dispatch_destroy(&dispatch);
    pl_opengl_destroy(&gl);
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(display, context);
    eglDestroySurface(display, surface);
    eglTerminate(display);
    printf("PASS: GLES300 DV polynomial reshaping, %u scalar comparisons, alternating metadata\n", samples);
}
