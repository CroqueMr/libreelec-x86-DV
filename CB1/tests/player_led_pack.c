/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reference_test.h"
#include "cb1_hdr10_expert.h"

static unsigned compute_dispatches;
void __real_glDispatchCompute(GLuint x, GLuint y, GLuint z);
void __wrap_glDispatchCompute(GLuint x, GLuint y, GLuint z)
{
    compute_dispatches++;
    __real_glDispatchCompute(x, y, z);
}

enum { WIDTH = 8, HEIGHT = 4, SIZE = WIDTH * HEIGHT * 4 };

static double pq(double linear, double peak)
{
    double normalized = fmin(fmax(linear, 0), 1) * peak / 10000;
    double power = pow(normalized, 2610.0 / 16384);
    return pow((3424.0 / 4096 + (2413.0 / 128) * power) /
               (1 + (2392.0 / 128) * power), 2523.0 / 32);
}

static void reference_codes(const float *pixels, const double matrix[3][3], double peak,
                            unsigned bits, unsigned codes[WIDTH * HEIGHT][2])
{
    double signal[WIDTH * HEIGHT][3];
    for (int i = 0; i < WIDTH * HEIGHT; i++) {
        double rgb[3];
        for (int c = 0; c < 3; c++) {
            double linear = 0;
            for (int k = 0; k < 3; k++)
                linear += matrix[c][k] * pixels[4 * i + k];
            rgb[c] = pq(linear, peak);
        }
        double y = .2627 * rgb[0] + .6780 * rgb[1] + .0593 * rgb[2];
        signal[i][0] = y;
        signal[i][1] = (rgb[2] - y) / 1.8814;
        signal[i][2] = (rgb[0] - y) / 1.4746;
    }
    unsigned step = 1u << (12 - bits);
    for (int i = 0; i < WIDTH * HEIGHT; i++) {
        int even = i & ~1, left = even % WIDTH ? even - 1 : even;
        int c = 1 + (i % 2);
        double chroma = (signal[left][c] + 2 * signal[even][c] + signal[even + 1][c]) / 4;
        codes[i][0] = (unsigned)round((256 + 3504 * signal[i][0]) / step) * step;
        codes[i][1] = (unsigned)round((2048 + 3584 * chroma) / step) * step;
    }
}

static void read_carrier(pl_gpu gpu, pl_tex carrier, uint8_t *bytes)
{
    GLuint fbo = 0;
    pl_opengl_unwrap(gpu, carrier, NULL, NULL, &fbo);
    assert(fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glReadPixels(0, 0, WIDTH, HEIGHT, GL_RGBA, GL_UNSIGNED_BYTE, bytes);
    assert(glGetError() == GL_NO_ERROR);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
}

static unsigned compare(const uint8_t *bytes, const unsigned codes[WIDTH * HEIGHT][2], bool flip)
{
    unsigned low_bits = 0;
    for (int i = 0; i < WIDTH * HEIGHT; i++) {
        int row = i / WIDTH;
        int ref = (flip ? HEIGHT - 1 - row : row) * WIDTH + i % WIDTH;
        const uint8_t *pixel = bytes + 4 * i;
        unsigned y = 16 * pixel[1] + (pixel[2] & 15);
        unsigned c = 16 * pixel[0] + (pixel[2] >> 4);
        if (y != codes[ref][0] || c != codes[ref][1])
            fprintf(stderr, "pixel %d: Y/C %u/%u, expected %u/%u\n",
                    i, y, c, codes[ref][0], codes[ref][1]);
        assert(y == codes[ref][0] && c == codes[ref][1] && pixel[3] == 255);
        low_bits |= y | c;
    }
    return low_bits & 3;
}

int main(void)
{
    const float pixels[SIZE] = {
        0,0,0,1, 1,1,1,1, .03,.03,.03,1, .07,.07,.07,1,
        .13,.13,.13,1, .27,.27,.27,1, .51,.51,.51,1, .91,.91,.91,1,
        0,0,0,1, 0,0,1,1, 0,0,0,1, 0,0,0,1,
        0,0,0,1, 0,0,0,1, 0,0,.000001,1, 0,0,0,1,
        1,0,0,1, 0,0,1,1, 0,1,0,1, 1,0,1,1,
        1,1,0,1, 0,1,1,1, .7,.2,.1,1, .23,.1,.67,1,
        -.1,.07,1.2,1, .12,.32,.77,1, .09,.03,.4,1, .24,.57,.32,1,
        .7,.01,.3,1, .44,.2,.36,1, .78,.88,.34,1, .05,.89,.31,1,
    };
    const double bt2020[3][3] = {{1,0,0},{0,1,0},{0,0,1}};
    const double p3[3][3] = {
        {.753833034,.198597369,.047569597},
        {.045743849,.941777219,.012478932},
        {-.001210340,.017601717,.983608623},
    };
    const double bt709[3][3] = {
        {.627403896,.329283038,.043313066},
        {.069097289,.919540395,.011362316},
        {.016391439,.088013308,.895595253},
    };
    struct reference_gpu g = reference_gpu_create();
    pl_gpu gpu = g.gl->gpu;
    struct dvbridge_renderer *renderer = dvbridge_renderer_create(gpu);
    pl_tex source = reference_texture(gpu, WIDTH, HEIGHT, pixels);
    pl_fmt rgba8 = pl_find_fmt(gpu, PL_FMT_UNORM, 4, 8, 8, PL_FMT_CAP_RENDERABLE);
    assert(renderer && rgba8);
    pl_tex carrier = pl_tex_create(gpu, pl_tex_params(.w=WIDTH,.h=HEIGHT,.format=rgba8,.renderable=true));
    pl_tex wrong_size = reference_texture(gpu, WIDTH - 1, HEIGHT, NULL);
    assert(carrier);
    uint8_t bytes[SIZE], baseline[SIZE];
    unsigned codes[WIDTH * HEIGHT][2], codes10[WIDTH * HEIGHT][2];
    struct dvbridge_policy policy = reference_policy();

    policy.tv.gamut = DVBRIDGE_GAMUT_BT2020;
    policy.tv.peak_nits = 10000;
    const GLint viewport[4] = {1, 2, 5, 7}, scissor[4] = {2, 3, 1, 1};
    GLint restored[4];
    GLboolean mask[4];
    glEnable(GL_BLEND);
    glEnable(GL_SCISSOR_TEST);
    glEnable(GL_RASTERIZER_DISCARD);
    glColorMask(GL_FALSE, GL_TRUE, GL_FALSE, GL_TRUE);
    glViewport(viewport[0], viewport[1], viewport[2], viewport[3]);
    glScissor(scissor[0], scissor[1], scissor[2], scissor[3]);
    assert(dvbridge_pack_player_led_422(renderer, &policy, source, carrier, 10, false));
    assert(glIsEnabled(GL_BLEND) && glIsEnabled(GL_SCISSOR_TEST) && glIsEnabled(GL_RASTERIZER_DISCARD));
    glGetBooleanv(GL_COLOR_WRITEMASK, mask);
    assert(!mask[0] && mask[1] && !mask[2] && mask[3]);
    glGetIntegerv(GL_VIEWPORT, restored);
    assert(!memcmp(restored, viewport, sizeof(restored)));
    glGetIntegerv(GL_SCISSOR_BOX, restored);
    assert(!memcmp(restored, scissor, sizeof(restored)));
    glDisable(GL_BLEND);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_RASTERIZER_DISCARD);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    read_carrier(gpu, carrier, baseline);
    reference_codes(pixels, bt2020, 10000, 10, codes10);
    assert(codes10[0][0] == 256 && codes10[1][0] == 3760);
    assert(!compare(baseline, codes10, false));

    assert(dvbridge_pack_player_led_422(renderer, &policy, source, carrier, 12, false));
    read_carrier(gpu, carrier, bytes);
    reference_codes(pixels, bt2020, 10000, 12, codes);
    assert(compare(bytes, codes, false) == 3);
    bool rounded_not_truncated = false;
    for (int i = 0; i < WIDTH * HEIGHT; i++)
        for (int c = 0; c < 2; c++)
            rounded_not_truncated |= codes10[i][c] != (codes[i][c] & ~3u);
    assert(rounded_not_truncated);

    uint8_t before_failure[SIZE];
    memcpy(before_failure, bytes, SIZE);
    assert(!dvbridge_pack_player_led_422(renderer, &policy, source, carrier, 11, false));
    assert(!dvbridge_pack_player_led_422(renderer, &policy, wrong_size, carrier, 12, false));
    assert(!dvbridge_pack_player_led_422(renderer, &policy, source, source, 12, false));
    /* A wrapped framebuffer reports 8-bit UNORM even for an sRGB attachment. */
    GLuint nonlinear_tex, nonlinear_fbo;
    glGenTextures(1, &nonlinear_tex);
    glBindTexture(GL_TEXTURE_2D, nonlinear_tex);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_SRGB8_ALPHA8, WIDTH, HEIGHT);
    glGenFramebuffers(1, &nonlinear_fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, nonlinear_fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, nonlinear_tex, 0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    pl_tex nonlinear = pl_opengl_wrap(gpu, pl_opengl_wrap_params(
        .width=WIDTH, .height=HEIGHT, .framebuffer=nonlinear_fbo));
    assert(nonlinear && nonlinear->params.renderable);
    assert(!dvbridge_pack_player_led_422(renderer, &policy, source, nonlinear, 12, false));
    pl_tex_destroy(gpu, &nonlinear);
    glDeleteFramebuffers(1, &nonlinear_fbo);
    glDeleteTextures(1, &nonlinear_tex);
    policy.mode = DVBRIDGE_MODE_SDR;
    assert(!dvbridge_pack_player_led_422(renderer, &policy, source, carrier, 12, false));
    read_carrier(gpu, carrier, bytes);
    assert(!memcmp(bytes, before_failure, SIZE));

    policy.mode = DVBRIDGE_MODE_HDR10_EXPERT;
    policy.tv.gamut = DVBRIDGE_GAMUT_P3_D65;
    policy.tv.peak_nits = 1000;
    assert(dvbridge_pack_player_led_422(renderer, &policy, source, carrier, 12, true));
    read_carrier(gpu, carrier, bytes);
    reference_codes(pixels, p3, 1000, 12, codes);
    compare(bytes, codes, true);

    policy.tv.gamut = DVBRIDGE_GAMUT_BT709;
    policy.tv.peak_nits = 100;
    assert(dvbridge_pack_player_led_422(renderer, &policy, source, carrier, 10, false));
    read_carrier(gpu, carrier, bytes);
    reference_codes(pixels, bt709, 100, 10, codes);
    assert(!compare(bytes, codes, false));

    policy.mode = DVBRIDGE_MODE_PLAYER_LED;
    policy.lldv_edid_version = 2;
    policy.tv.peak_nits = 2484;
    const double edid_xy[] = {.68687,.31183,.24609,.703125,.14874,.05320};
    memcpy(policy.lldv_primaries, edid_xy, sizeof(edid_xy));
    const struct pl_raw_primaries edid = cb1_display_primaries(&policy);
    const pl_matrix3x3 edid_to_2020 = pl_get_color_mapping_matrix(&edid,
        pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020), PL_INTENT_RELATIVE_COLORIMETRIC);
    double edid_matrix[3][3];
    for (int i=0;i<3;i++) for (int j=0;j<3;j++) edid_matrix[i][j]=edid_to_2020.m[i][j];
    for (unsigned bits=10;bits<=12;bits+=2) {
        assert(dvbridge_pack_player_led_422(renderer, &policy, source, carrier, bits, false));
        read_carrier(gpu, carrier, bytes);
        reference_codes(pixels, edid_matrix, 2484, bits, codes);
        compare(bytes, codes, false);
        for (int i=0;i<WIDTH;i++) assert(codes[i][1]==2048);
    }
    policy.mode = DVBRIDGE_MODE_HDR10_EXPERT;
    policy.lldv_edid_version = 0;
    dvbridge_renderer_reset(renderer);
    policy.tv.gamut = DVBRIDGE_GAMUT_BT2020;
    policy.tv.peak_nits = 10000;
    assert(dvbridge_pack_player_led_422(renderer, &policy, source, carrier, 10, false));
    read_carrier(gpu, carrier, bytes);
    assert(!memcmp(bytes, baseline, SIZE));

    assert(!compute_dispatches);
    if (gpu->glsl.gles && gpu->glsl.version >= 310) {
        GLuint packed_name, other_image, sampler;
        glGenTextures(1, &packed_name);
        glBindTexture(GL_TEXTURE_2D, packed_name);
        glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, WIDTH, HEIGHT);
        pl_tex packed = pl_opengl_wrap(gpu, pl_opengl_wrap_params(
            .width=WIDTH,.height=HEIGHT,.texture=packed_name,
            .target=GL_TEXTURE_2D,.iformat=GL_RGBA8));
        assert(packed);
        glGenTextures(1, &other_image);
        glBindTexture(GL_TEXTURE_2D, other_image);
        glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, WIDTH, HEIGHT);
        glBindImageTexture(0, other_image, 0, GL_FALSE, 0, GL_READ_ONLY, GL_RGBA8);
        glGenSamplers(1, &sampler);
        glBindSampler(0, sampler);
        glActiveTexture(GL_TEXTURE1);
        assert(glGetError() == GL_NO_ERROR);

        unsigned before_compute = compute_dispatches;
        assert(dvbridge_pack_player_led_422(renderer, &policy, source, packed, 10, false));
        assert(compute_dispatches == before_compute + 1);
        GLint binding;
        glGetIntegerv(GL_ACTIVE_TEXTURE, &binding);
        assert(binding == GL_TEXTURE1);
        glGetIntegeri_v(GL_IMAGE_BINDING_NAME, 0, &binding);
        assert((GLuint)binding == other_image);
        glGetIntegeri_v(GL_IMAGE_BINDING_ACCESS, 0, &binding);
        assert(binding == GL_READ_ONLY);
        glActiveTexture(GL_TEXTURE0);
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &binding);
        assert((GLuint)binding == other_image);
        glGetIntegerv(GL_SAMPLER_BINDING, &binding);
        assert((GLuint)binding == sampler);
        read_carrier(gpu, packed, bytes);
        assert(!memcmp(bytes, baseline, SIZE));

        policy.tv.gamut = DVBRIDGE_GAMUT_P3_D65;
        policy.tv.peak_nits = 1000;
        assert(dvbridge_pack_player_led_422(renderer, &policy, source, packed, 12, true));
        assert(compute_dispatches == before_compute + 2);
        read_carrier(gpu, packed, bytes);
        reference_codes(pixels, p3, 1000, 12, codes);
        compare(bytes, codes, true);

        policy.tv.gamut = DVBRIDGE_GAMUT_BT709;
        policy.tv.peak_nits = 100;
        assert(dvbridge_pack_player_led_422(renderer, &policy, source, packed, 10, false));
        assert(compute_dispatches == before_compute + 3);
        read_carrier(gpu, packed, bytes);
        reference_codes(pixels, bt709, 100, 10, codes);
        assert(!compare(bytes, codes, false));

        glBindImageTexture(0, 0, 0, GL_FALSE, 0, GL_READ_ONLY, GL_RGBA8);
        glBindSampler(0, 0);
        glDeleteSamplers(1, &sampler);
        pl_tex_destroy(gpu, &packed);
        glDeleteTextures(1, &packed_name);
        glDeleteTextures(1, &other_image);
    }

    pl_tex_destroy(gpu, &wrong_size);
    pl_tex_destroy(gpu, &carrier);
    pl_tex_destroy(gpu, &source);
    dvbridge_renderer_destroy(renderer);
    reference_gpu_destroy(&g);
}
