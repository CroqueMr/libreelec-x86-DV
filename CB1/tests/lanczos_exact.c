/* SPDX-License-Identifier: MIT */
/* Compare aligned tap fetches to the original linear path before quantization. */
#include <EGL/egl.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libplacebo/opengl.h>
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/sampling.h>

static void compare(pl_gpu gpu, pl_dispatch dispatch, pl_fmt format,
                    const struct pl_sample_src *src, unsigned index,
                    float clamp, float taper)
{
    pl_tex output = pl_tex_create(gpu, pl_tex_params(
        .w = src->new_w, .h = src->new_h, .format = format,
        .renderable = true, .host_readable = true));
    assert(output);
    size_t bytes = (size_t) src->new_w * src->new_h * 4 * sizeof(float);
    void *pixels[2] = {malloc(bytes), malloc(bytes)};
    assert(pixels[0] && pixels[1]);
    for (int reference = 0; reference < 2; reference++) {
        struct pl_filter_config filter = pl_filter_lanczos;
        filter.clamp = clamp;
        filter.taper = taper;
        // Explicit unity blur is mathematically identical to the default, but
        // excludes the optimized path. Each path owns its shader/LUT state.
        filter.blur = reference ? 1.0f : 0.0f;
        pl_shader_obj lut = NULL;
        pl_shader shader = pl_dispatch_begin(dispatch);
        assert(pl_shader_sample_ortho2(shader, src,
            pl_sample_filter_params(.filter = filter, .lut = &lut)));
        assert(pl_dispatch_finish(dispatch,
            pl_dispatch_params(.shader = &shader, .target = output)));
        assert(pl_tex_download(gpu,
            pl_tex_transfer_params(.tex = output, .ptr = pixels[reference])));
        pl_shader_obj_destroy(&lut);
    }
    if (memcmp(pixels[0], pixels[1], bytes)) {
        fprintf(stderr, "Lanczos FP32 mismatch in case %u\n", index);
        const float *actual = pixels[0], *expected = pixels[1];
        for (size_t i = 0; i < bytes / sizeof(float); ++i) {
            uint32_t actual_bits, expected_bits;
            memcpy(&actual_bits, actual + i, sizeof(actual_bits));
            memcpy(&expected_bits, expected + i, sizeof(expected_bits));
            if (actual_bits == expected_bits) continue;
            fprintf(stderr, "first difference pixel=(%zu,%zu) channel=%zu optimized=%.9g (0x%08x) unity-blur=%.9g (0x%08x)\n",
                (i / 4) % src->new_w, (i / 4) / src->new_w, i % 4,
                actual[i], actual_bits, expected[i], expected_bits);
            fprintf(stderr, "geometry input=%dx%d output=%dx%d rect=(%.9g,%.9g,%.9g,%.9g) clamp=%.9g taper=%.9g\n",
                src->tex->params.w, src->tex->params.h, src->new_w, src->new_h,
                src->rect.x0, src->rect.y0, src->rect.x1, src->rect.y1, clamp, taper);
            break;
        }
        abort();
    }
    free(pixels[0]);
    free(pixels[1]);
    pl_tex_destroy(gpu, &output);
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display, NULL, NULL));
    assert(eglBindAPI(EGL_OPENGL_ES_API));
    EGLint attrs[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                     EGL_RENDERABLE_TYPE, 0x40, EGL_NONE};
    EGLConfig config;
    EGLint count;
    assert(eglChooseConfig(display, attrs, &config, 1, &count) && count);
    EGLint surface_attrs[] = {EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE};
    EGLint context_attrs[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    EGLSurface surface = eglCreatePbufferSurface(display, config, surface_attrs);
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attrs);
    assert(eglMakeCurrent(display, surface, surface, context));
    pl_log log = pl_log_create(PL_API_VER,
        pl_log_params(.log_cb = pl_log_simple, .log_level = PL_LOG_WARN));
    pl_opengl gl = pl_opengl_create(log, pl_opengl_params(
        .get_proc_addr = (pl_voidfunc_t (*)(const char *)) eglGetProcAddress,
        .egl_display = display, .egl_context = context));
    assert(gl);
    pl_dispatch dispatch = pl_dispatch_create(log, gl->gpu);
    pl_fmt format = pl_find_fmt(gl->gpu, PL_FMT_FLOAT, 4, 32, 32,
        PL_FMT_CAP_RENDERABLE | PL_FMT_CAP_HOST_READABLE);
    assert(format);
    const int widths[] = {960, 1920, 2048}, heights[] = {540, 1080, 1088};
    const float shifts[] = {0, -0.5f, -0.25f, 0.125f};
    unsigned cases = 0;
    for (int dim = 0; dim < 3; dim++) {
        for (int floating = 0; floating < 2; floating++) {
            for (int comps = 1; comps <= 2; comps++) {
                int w = widths[dim], h = heights[dim];
                size_t samples = (size_t) w * h * comps;
                float *fp = malloc(samples * sizeof(*fp));
                uint16_t *up = malloc(samples * sizeof(*up));
                assert(fp && up);
                uint32_t seed = 817291;
                for (size_t i = 0; i < samples; i++) {
                    seed = 1664525u * seed + 1013904223u;
                    fp[i] = (seed >> 8) / (float) 0xffffff;
                    up[i] = ((seed >> 16) % 1024u) << 6;
                }
                pl_fmt input_format = pl_find_fmt(gl->gpu,
                    floating ? PL_FMT_FLOAT : PL_FMT_UNORM, comps,
                    floating ? 32 : 16, floating ? 32 : 16,
                    PL_FMT_CAP_SAMPLEABLE | PL_FMT_CAP_LINEAR);
                assert(input_format);
                pl_tex input = pl_tex_create(gl->gpu, pl_tex_params(
                    .w = w, .h = h, .format = input_format, .sampleable = true,
                    .initial_data = floating ? (void *) fp : (void *) up));
                assert(input);
                free(fp);
                free(up);
                for (int axis = 0; axis < 2; axis++) {
                    for (int scale = 2; scale <= 4; scale += 2) {
                        for (int shift = 0; shift < 4; shift++) {
                            struct pl_sample_src src = {
                                .tex = input, .components = comps,
                                .new_w = axis ? w : w * scale,
                                .new_h = axis ? h * scale : h,
                                .rect = {0, 0, w, h}};
                            if (axis) {
                                src.rect.y0 += shifts[shift];
                                src.rect.y1 += shifts[shift];
                            } else {
                                src.rect.x0 += shifts[shift];
                                src.rect.x1 += shifts[shift];
                            }
                            compare(gl->gpu, dispatch, format, &src, cases++, 0, 0);
                        }
                    }
                }
                // Identity, cropped identity, unaligned orthogonal axis,
                // mirrored input, near-identity tolerance, downscaling and
                // custom kernel settings which must retain linear sampling.
                for (int edge = 0; edge < 8; edge++) {
                    struct pl_sample_src src = {
                        .tex = input, .components = comps,
                        .new_w = w, .new_h = h, .rect = {0, 0, w, h}};
                    switch (edge) {
                    case 0: src.rect.x0 += 0.25f; src.rect.x1 += 0.25f; break;
                    case 1: src.new_w -= 2; src.rect.x0 = 0.25f;
                            src.rect.x1 = w - 1.75f; break;
                    case 2: src.new_w *= 2; src.rect.y0 += 0.25f;
                            src.rect.y1 += 0.25f; break;
                    case 3: src.rect.x0 = w; src.rect.x1 = 0; break;
                    case 4: src.rect.x0 = 0.25f;
                            src.rect.x1 = w + 0.250244140625f; break;
                    case 5: src.new_w /= 2; break;
                    case 6: case 7: src.new_w *= 2; break;
                    }
                    compare(gl->gpu, dispatch, format, &src, cases++,
                            edge == 6 ? 1.0f : 0, edge == 7 ? 0.5f : 0);
                }
                pl_tex_destroy(gl->gpu, &input);
                printf("Verified %u exact FP32 cases\n", cases);
            }
        }
    }
    assert(cases == 288);
    pl_dispatch_destroy(&dispatch);
    pl_opengl_destroy(&gl);
    pl_log_destroy(&log);
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(display, context);
    eglDestroySurface(display, surface);
    eglTerminate(display);
    return 0;
}
