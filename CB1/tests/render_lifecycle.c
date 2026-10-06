#include "task4_legacy_calls.h"
/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <libplacebo/opengl.h>
#include "dvbridge_render.h"
#include "dvbridge_gl_frame.h"
#include "dvbridge_gl_pack.h"
#include "dvbridge_placebo.h"

static char *load_source(const char *path)
{
    FILE *f = fopen(path, "rb");
    assert(f && !fseek(f, 0, SEEK_END));
    long size = ftell(f);
    assert(size > 0 && size < 65536);
    rewind(f);
    char *data = calloc(size + 1, 1);
    assert(data && fread(data, 1, size, f) == (size_t)size);
    fclose(f);
    return data;
}

static void read_pixel(pl_gpu gpu, pl_tex tex, int x, int y, float pixel[4])
{
    GLuint id = pl_opengl_unwrap(gpu, tex, NULL, NULL, NULL);
    assert(id);
    GLint previous;
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &previous);
    GLuint fbo;
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, id, 0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
    glReadPixels(x, y, 1, 1, GL_RGBA, GL_FLOAT, pixel);
    assert(glGetError() == GL_NO_ERROR);
    for (int i = 0; i < 4; ++i)
        assert(isfinite(pixel[i]));
    glBindFramebuffer(GL_FRAMEBUFFER, previous);
    glDeleteFramebuffers(1, &fbo);
}

static void check_pixel(pl_gpu gpu, pl_tex tex, int x, int y, bool blank)
{
    float pixel[4];
    read_pixel(gpu, tex, x, y, pixel);
    if (blank && (pixel[0] != 0 || pixel[1] != 0 || pixel[2] != 0))
        fprintf(stderr,"Non-black pixel at %d,%d: %.9f %.9f %.9f\n",x,y,pixel[0],pixel[1],pixel[2]);
    if (blank)
        assert(pixel[0] == 0 && pixel[1] == 0 && pixel[2] == 0);
    else
        assert(pixel[0] > 0 && pixel[1] > 0 && pixel[2] > 0);
}

static void write_pixel(pl_gpu gpu, pl_tex tex, const float pixel[4])
{
    GLuint id = pl_opengl_unwrap(gpu, tex, NULL, NULL, NULL);
    assert(id);
    glBindTexture(GL_TEXTURE_2D, id);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 32, 32, 1, 1, GL_RGBA, GL_FLOAT, pixel);
    assert(glGetError() == GL_NO_ERROR);
    glBindTexture(GL_TEXTURE_2D, 0);
}

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    assert(argc == 3);
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display, NULL, NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, 0x40, EGL_NONE};
    EGLConfig config;
    EGLint count;
    assert(eglChooseConfig(display, attributes, &config, 1, &count) && count);
    EGLint sa[] = {EGL_WIDTH, 64, EGL_HEIGHT, 64, EGL_NONE};
    EGLint ca[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    EGLSurface surface = eglCreatePbufferSurface(display, config, sa);
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, ca);
    assert(eglMakeCurrent(display, surface, surface, context));
    pl_log log = getenv("DVBRIDGE_TEST_TRACE") ? pl_log_create(PL_API_VER, pl_log_params(
        .log_cb = pl_log_simple, .log_level = PL_LOG_TRACE)) : NULL;
    pl_opengl gl = pl_opengl_create(log, pl_opengl_params(
        .get_proc_addr = (pl_voidfunc_t (*)(const char *))eglGetProcAddress,
        .egl_display = display, .egl_context = context, .allow_software = true));
    assert(gl);
    struct dvbridge_renderer *renderer = dvbridge_renderer_create(gl->gpu);
    assert(renderer);
    pl_fmt fmt = pl_find_fmt(gl->gpu, PL_FMT_FLOAT, 4, 32, 32, PL_FMT_CAP_SAMPLEABLE);
    float pixels[64 * 64 * 4];
    for (unsigned i = 0; i < sizeof(pixels) / sizeof(*pixels); ++i)
        pixels[i] = i % 4 == 3 ? 1.0f : 0.5f;
    pl_tex input = pl_tex_create(gl->gpu, pl_tex_params(.w = 64, .h = 64, .format = fmt,
        .sampleable = true, .initial_data = pixels));
    assert(input);
    struct pl_frame frame = {.num_planes = 1,
        .planes = {{.texture = input, .components = 4, .component_mapping = {0, 1, 2, 3}}},
        .crop = {0, 0, 64, 64}};
    size_t bytes;
    AVDOVIMetadata *m = av_dovi_metadata_alloc(&bytes);
    assert(m);
    m->num_ext_blocks = 1;
    av_dovi_get_ext(m, 0)->level = 1;
    AVDOVIRpuDataHeader *h = av_dovi_get_header(m);
    h->disable_residual_flag = 1;
    h->bl_bit_depth = h->el_bit_depth = 10;
    h->coef_log2_denom = 12;
    AVDOVIColorMetadata *color = av_dovi_get_color(m);
    color->signal_eotf = 65535;
    color->source_max_pq = 3079;
    for (int i = 0; i < 9; ++i) {
        color->ycc_to_rgb_matrix[i] = (AVRational){i % 4 == 0, 1};
        color->rgb_to_lms_matrix[i] = (AVRational){i % 4 == 0, 1};
    }
    for (int c = 0; c < 3; ++c) {
        color->ycc_to_rgb_offset[c] = (AVRational){0, 1};
        AVDOVIReshapingCurve *curve = &av_dovi_get_mapping(m)->curves[c];
        curve->num_pivots = 2;
        curve->pivots[1] = 1023;
        curve->mapping_idc[0] = AV_DOVI_MAPPING_POLYNOMIAL;
        curve->poly_order[0] = 1;
        curve->poly_coef[0][1] = 4096;
    }
    struct dvbridge_geometry geometry = {64, 64, 840, 0, 2160, 2160};
    struct pl_color_space reference;
    assert(dvbridge_hdr10_target(&reference, m, bytes));
    assert(reference.hdr.max_luma > 999 && reference.hdr.max_luma < 1002);
    m->num_ext_blocks = 2;
    AVDOVIDmData *master = av_dovi_get_ext(m, 1);
    master->level = 6;
    master->l6.max_luminance = 4000;
    assert(dvbridge_hdr10_target(&reference, m, bytes));
    assert(reference.hdr.max_luma == 4000 && !reference.hdr.max_pq_y);
    struct dvbridge_hdr10_metadata signal;
    master->l6.max_cll = 9000;
    master->l6.max_fall = 1000;
    assert(dvbridge_get_hdr10_metadata(&signal, m, bytes));
    assert(signal.max_luminance == 4000 && !signal.max_cll && !signal.max_fall);
    AVDOVIDmData *dynamic = av_dovi_get_ext(m, 0);
    dynamic->l1.min_pq = 12;
    dynamic->l1.avg_pq = 2000;
    dynamic->l1.max_pq = 3079;
    float native_low[4], native_high[4], mapped_low[4], mapped_high[4];
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 0, NAN, geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 1080, native_low);
    assert(legacy_hdr10(renderer, &frame, m, bytes, 0, NAN, geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 1080, mapped_low);
    dynamic->l1.avg_pq = 3079;
    dynamic->l1.max_pq = 4095;
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 0, NAN, geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 1080, native_high);
    assert(legacy_hdr10(renderer, &frame, m, bytes, 0, NAN, geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 1080, mapped_high);
    for (int c = 0; c < 3; ++c) {
        assert(fabsf(native_low[c] - native_high[c]) < 1e-6f);
        assert(mapped_low[c] <= native_low[c] + 0.002f);
        assert(mapped_high[c] < mapped_low[c] - 0.001f);
    }
    printf("PASS L1: native %.6f/%.6f, HDR10 %.6f/%.6f at 4000 nits\n",
           native_low[1], native_high[1], mapped_low[1], mapped_high[1]);
    dynamic->l1.avg_pq = 2000;
    dynamic->l1.max_pq = 3079;
    assert(legacy_hdr10(renderer, &frame, m, bytes, 0, NAN, geometry));
    float restored[4];
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 1080, restored);
    for (int c = 0; c < 3; ++c)
        assert(fabsf(restored[c] - mapped_low[c]) < 1e-6f);
    dynamic->l1.avg_pq = 4096;
    assert(!dvbridge_render_rgb(renderer, &frame, m, bytes, 0, NAN, geometry));
    assert(legacy_hdr10(renderer, &frame, m, bytes, 0, NAN, geometry));
    assert(dvbridge_render_texture(renderer) && !dvbridge_render_candidate(renderer));
    assert(dvbridge_render_commit(renderer));
    assert(!dvbridge_render_commit(renderer));
    master->l6.max_luminance = 65535;
    assert(dvbridge_hdr10_target(&reference, m, bytes));
    assert(reference.hdr.max_luma < 1002);
    color->source_max_pq = 0;
    assert(!dvbridge_hdr10_target(&reference, m, bytes));
    color->source_max_pq = 3079;
    m->num_ext_blocks = 1;
    *master = (AVDOVIDmData){0};
    dynamic->l1.min_pq = dynamic->l1.avg_pq = dynamic->l1.max_pq = 0;
    dvbridge_renderer_reset(renderer);
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 0, NAN, geometry));
    assert(dvbridge_render_texture(renderer) && dvbridge_render_candidate(renderer));
    assert(dvbridge_render_commit(renderer));
    assert(!dvbridge_render_commit(renderer));
    assert(!dvbridge_render_rgb(renderer, &frame, m, 1, 1, NAN, geometry));
    assert(!dvbridge_render_texture(renderer) && !dvbridge_render_candidate(renderer));
    assert(!dvbridge_render_commit(renderer));
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 2, NAN, geometry));
    dvbridge_renderer_reset(renderer);
    assert(!dvbridge_render_texture(renderer) && !dvbridge_render_commit(renderer));
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 0, NAN, geometry));
    check_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 100, false);
    float without_el[4], with_el[4], expected[4];
    /* Compare composition without introducing a separate spatial scaling pass. */
    struct dvbridge_geometry fel_geometry = {64, 64, 0, 0, 64, 64};
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 1, NAN, fel_geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 32, 32, without_el);
    pl_fmt el_fmt = pl_find_fmt(gl->gpu, PL_FMT_UNORM, 4, 16, 16,
                              PL_FMT_CAP_SAMPLEABLE | PL_FMT_CAP_LINEAR);
    assert(el_fmt);
    uint16_t el_pixels[32 * 32 * 4];
    for (unsigned i = 0; i < 32 * 32 * 4; ++i)
        el_pixels[i] = i % 4 == 3 ? UINT16_MAX : 512 << 6;
    pl_tex el_tex = pl_tex_create(gl->gpu, pl_tex_params(.w = 32, .h = 32, .format = el_fmt,
        .sampleable = true, .initial_data = el_pixels));
    assert(el_tex);
    struct pl_frame el_frame = {.num_planes = 1,
        .repr.bits = {.sample_depth = 16, .color_depth = 10, .bit_shift = 6},
        .planes = {{.texture = el_tex, .components = 4, .component_mapping = {0,1,2,3}}},
        .crop = {0,0,32,32}};
    h->disable_residual_flag = 0;
    AVDOVIDataMapping *mapping = av_dovi_get_mapping(m);
    mapping->nlq_method_idc = AV_DOVI_NLQ_LINEAR_DZ;
    for (int c = 0; c < 3; ++c) {
        mapping->nlq[c].nlq_offset = 512;
        mapping->nlq[c].linear_deadzone_slope = 1;
        mapping->nlq[c].linear_deadzone_threshold = 0;
    }
    assert(!dvbridge_render_rgb(renderer, &frame, m, bytes, 3, NAN, geometry));
    frame.enhancement_layer = &el_frame;
    assert(!dvbridge_render_rgb(renderer, &frame, m, bytes, 3, 4, geometry));
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 3, 3, fel_geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 32, 32, with_el);
    pl_tex hdr_target = pl_tex_create(gl->gpu, pl_tex_params(
        .w=3840, .h=2160, .format=fmt, .renderable=true, .sampleable=true));
    assert(hdr_target);
    assert(!dvbridge_render_hdr10(renderer, hdr_target, false, false, 8));
    assert(!dvbridge_render_commit(renderer));
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 3, 3, fel_geometry));
    assert(dvbridge_render_hdr10(renderer, hdr_target, false, false, 10));
    float hdr_pixel[4];
    read_pixel(gl->gpu, hdr_target, 32, 32, hdr_pixel);
    for (int c = 0; c < 3; ++c) {
        fprintf(stderr, "HDR10 full channel %d: reconstructed %.9g output %.9g\n", c, with_el[c], hdr_pixel[c]);
        assert(fabsf(hdr_pixel[c] - with_el[c]) <= 1.5f / 1023.0f);
    }
    assert(dvbridge_render_hdr10(renderer, hdr_target, true, true, 10));
    read_pixel(gl->gpu, hdr_target, 32, 2160-1-32, hdr_pixel);
    for (int c = 0; c < 3; ++c)
        assert(fabsf(hdr_pixel[c] - (with_el[c] * 876.0f + 64.0f) / 1023.0f) <= 1.5f / 1023.0f);
    pl_tex_destroy(gl->gpu, &hdr_target);
    hdr_target = pl_tex_create(gl->gpu, pl_tex_params(
        .w=3840, .h=2160, .format=fmt, .renderable=true, .sampleable=true));
    const float peaks[] = {0.7518270962f, 0.8274246449f, 0.9025723933f, 1.0f};
    for (unsigned i=0; i<4; ++i) {
        float input_pq[4] = {peaks[i], peaks[i], peaks[i], 1};
        write_pixel(gl->gpu, dvbridge_render_texture(renderer), input_pq);
        assert(dvbridge_render_hdr10(renderer, hdr_target, false, false, 10));
        read_pixel(gl->gpu, hdr_target, 32, 32, hdr_pixel);
        for (int c=0; c<3; ++c)
            assert(fabsf(hdr_pixel[c] - peaks[i]) <= 1.5f/1023.0f);
    }
    write_pixel(gl->gpu, dvbridge_render_texture(renderer), with_el);
    pl_tex_destroy(gl->gpu, &hdr_target);
    puts("HDR10 identity verified at 1000, 2000, 4000 and 10000 nits; source mastering metadata does not cap pixels.");
    for (int c = 0; c < 3; ++c) {
        fprintf(stderr, "FEL neutral channel %d: baseline %.9g result %.9g\n", c, without_el[c], with_el[c]);
        assert(fabsf(with_el[c] - without_el[c]) < 0.00001f);
    }
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 3.1, 3.1, geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 1080, with_el);
    h->disable_residual_flag = 1;
    frame.enhancement_layer = NULL;
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 3.2, NAN, geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 1080, expected);
    for (int c = 0; c < 3; ++c) {
        fprintf(stderr, "FEL scaled channel %d: baseline %.9g result %.9g\n", c, expected[c], with_el[c]);
        assert(fabsf(with_el[c] - expected[c]) < 0.00001f);
    }
    h->disable_residual_flag = 0;
    frame.enhancement_layer = &el_frame;
    pl_tex_destroy(gl->gpu, &el_tex);
    for (unsigned i = 0; i < 32 * 32 * 4; ++i)
        el_pixels[i] = i % 4 == 3 ? UINT16_MAX : 576 << 6;
    el_tex = pl_tex_create(gl->gpu, pl_tex_params(.w = 32, .h = 32, .format = el_fmt,
        .sampleable = true, .initial_data = el_pixels));
    assert(el_tex);
    el_frame.planes[0].texture = el_tex;
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 4, 4, fel_geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 32, 32, with_el);
    dynamic->l1.min_pq = 12;
    dynamic->l1.avg_pq = 3079;
    dynamic->l1.max_pq = 4095;
    m->num_ext_blocks = 2;
    master->level = 6;
    master->l6.max_luminance = 4000;
    float mapped_fel[4];
    assert(legacy_hdr10(renderer, &frame, m, bytes, 4, 4, fel_geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 32, 32, mapped_fel);
    h->disable_residual_flag = 1;
    frame.enhancement_layer = NULL;
    float expected_pixels[64 * 64 * 4];
    for (unsigned i = 0; i < 64 * 64 * 4; ++i)
        expected_pixels[i] = i % 4 == 3 ? 1.0f : 0.5f + 63.5f / 4096.0f;
    pl_tex expected_tex = pl_tex_create(gl->gpu, pl_tex_params(.w = 64, .h = 64, .format = fmt,
        .sampleable = true, .initial_data = expected_pixels));
    assert(expected_tex);
    frame.planes[0].texture = expected_tex;
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 5, NAN, fel_geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 32, 32, expected);
    for (int c = 0; c < 3; ++c) {
        assert(fabsf(with_el[c] - expected[c]) < 0.00001f);
        assert(fabsf(with_el[c] - without_el[c]) > 0.001f);
    }
    assert(legacy_hdr10(renderer, &frame, m, bytes, 5, NAN, fel_geometry));
    read_pixel(gl->gpu, dvbridge_render_texture(renderer), 32, 32, expected);
    for (int c = 0; c < 3; ++c)
        assert(fabsf(mapped_fel[c] - expected[c]) < 0.00001f);
    puts("PASS: HDR10 mapping follows FEL reconstruction and matches the reconstructed reference.");
    m->num_ext_blocks = 1;
    *master = (AVDOVIDmData){0};
    dynamic->l1.min_pq = dynamic->l1.avg_pq = dynamic->l1.max_pq = 0;
    frame.planes[0].texture = input;
    pl_tex_destroy(gl->gpu, &el_tex);
    pl_tex_destroy(gl->gpu, &expected_tex);
    /* A real one-code residual must survive the neutral roundoff guard. */
    for (int direction = -1; direction <= 1; direction += 2) {
        h->disable_residual_flag = 0;
        frame.enhancement_layer = &el_frame;
        for (unsigned i = 0; i < 32 * 32 * 4; ++i)
            el_pixels[i] = i % 4 == 3 ? UINT16_MAX : (512 + direction) << 6;
        el_tex = pl_tex_create(gl->gpu, pl_tex_params(.w = 32, .h = 32, .format = el_fmt,
            .sampleable = true, .initial_data = el_pixels));
        assert(el_tex);
        el_frame.planes[0].texture = el_tex;
        double time = direction == -1 ? 6 : 8;
        assert(dvbridge_render_rgb(renderer, &frame, m, bytes, time, time, fel_geometry));
        read_pixel(gl->gpu, dvbridge_render_texture(renderer), 32, 32, with_el);
        h->disable_residual_flag = 1;
        frame.enhancement_layer = NULL;
        for (unsigned i = 0; i < 64 * 64 * 4; ++i)
            expected_pixels[i] = i % 4 == 3 ? 1.0f : 0.5f + direction * 0.5f / 4096.0f;
        expected_tex = pl_tex_create(gl->gpu, pl_tex_params(.w = 64, .h = 64, .format = fmt,
            .sampleable = true, .initial_data = expected_pixels));
        assert(expected_tex);
        frame.planes[0].texture = expected_tex;
        assert(dvbridge_render_rgb(renderer, &frame, m, bytes, time + 1, NAN, fel_geometry));
        read_pixel(gl->gpu, dvbridge_render_texture(renderer), 32, 32, expected);
        for (int c = 0; c < 3; ++c) {
            assert(fabsf(with_el[c] - expected[c]) < 0.00001f);
            assert(direction * (with_el[c] - without_el[c]) > 0.00008f);
        }
        frame.planes[0].texture = input;
        pl_tex_destroy(gl->gpu, &el_tex);
        pl_tex_destroy(gl->gpu, &expected_tex);
    }
    dvbridge_renderer_reset(renderer);
    m->num_ext_blocks = 2;
    AVDOVIDmData *l5 = av_dovi_get_ext(m, 1);
    l5->level = 5;
    l5->l5.top_offset = 8;
    l5->l5.bottom_offset = 4;
    assert(dvbridge_render_rgb(renderer, &frame, m, bytes, 1, NAN, geometry));
    unsigned margins[4];
    assert(dvbridge_active_area(dvbridge_render_candidate(renderer), margins));
    assert(margins[0] == 840 && margins[1] == 840 && margins[2] == 270 && margins[3] == 135);
    check_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 100, true);
    check_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 1080, false);
    check_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 2100, true);
    check_pixel(gl->gpu, dvbridge_render_texture(renderer), 100, 1080, true);
    GLuint native[2];
    glGenTextures(2, native);
    uint16_t native_data[64 * 64];
    for (unsigned i = 0; i < 64 * 64; ++i)
        native_data[i] = 512 << 6;
    for (int i = 0; i < 2; ++i) {
        glBindTexture(GL_TEXTURE_2D, native[i]);
        glTexImage2D(GL_TEXTURE_2D, 0, i ? 0x822C : 0x822A, i ? 32 : 64,
                     i ? 32 : 64, 0, i ? GL_RG : GL_RED, GL_UNSIGNED_SHORT, native_data);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    }
    assert(glGetError() == GL_NO_ERROR);
    struct dvbridge_gl_plane planes[3] = {{native[0], 64, 64}, {native[1], 32, 32}};
    struct dvbridge_gl_frame imported = {0};
    assert(dvbridge_gl_frame_import(&imported, gl->gpu, DVBRIDGE_P010, 64, 64, planes));
    assert(imported.frame.repr.bits.bit_shift == 6 && imported.frame.num_planes == 2);
    assert(!dvbridge_gl_frame_import(&imported, gl->gpu, DVBRIDGE_P010, 64, 64, planes));
    assert(dvbridge_render_rgb(renderer, &imported.frame, m, bytes, 2, NAN, geometry));
    check_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 1080, false);
    check_pixel(gl->gpu, dvbridge_render_texture(renderer), 1920, 100, true);
    dvbridge_gl_frame_release(&imported);
    assert(glIsTexture(native[0]) && glIsTexture(native[1]));
    assert(dvbridge_gl_frame_import(&imported, gl->gpu, DVBRIDGE_P010, 60, 60, planes));
    assert(imported.frame.crop.x1 == 60 && imported.frame.crop.y1 == 60);
    assert(imported.frame.planes[0].texture->params.w == 64);
    dvbridge_gl_frame_release(&imported);
    planes[1].width = 31;
    assert(!dvbridge_gl_frame_import(&imported, gl->gpu, DVBRIDGE_P010, 64, 64, planes));
    assert(!imported.gpu && glIsTexture(native[0]));
    char *vs = load_source(argv[1]), *fs = load_source(argv[2]);
    struct dvbridge_gl_packer *packer = dvbridge_gl_packer_create(vs, fs);
    free(vs);
    free(fs);
    assert(packer);
    GLuint packed, destination;
    glGenTextures(1, &packed);
    glBindTexture(GL_TEXTURE_2D, packed);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, 3840, 2160);
    glGenFramebuffers(1, &destination);
    glBindFramebuffer(GL_FRAMEBUFFER, destination);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, packed, 0);
    unsigned packets;
    const uint32_t *words = dvbridge_packets(dvbridge_render_candidate(renderer), &packets);
    GLuint pq = pl_opengl_unwrap(gl->gpu, dvbridge_render_texture(renderer), NULL, NULL, NULL);
    assert(dvbridge_gl_pack(packer, pq, destination, 3840, 2160, words, packets, false));
    unsigned char black[4];
    glReadPixels(1920, 100, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, black);
    assert(glGetError() == GL_NO_ERROR);
    assert(black[0] == 128 && black[1] == 16 && black[2] == 0 && black[3] == 255);
    assert(dvbridge_render_commit(renderer));
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glDeleteFramebuffers(1, &destination);
    glDeleteTextures(1, &packed);
    dvbridge_gl_packer_destroy(packer);
    glDeleteTextures(2, native);
    pl_gpu_finish(gl->gpu);
    dvbridge_renderer_destroy(renderer);
    pl_tex_destroy(gl->gpu, &input);
    av_free(m);
    pl_opengl_destroy(&gl);
    pl_log_destroy(&log);
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(display, context);
    eglDestroySurface(display, surface);
    eglTerminate(display);
    puts("PASS: native P010 import -> DV render/L5 -> RGB8 transport, ownership, invalidation, commit/reset");
}
