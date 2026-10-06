/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_hdr10_extrema.h"
#include <time.h>
static const struct cb1_ai_identity id = {1,2,3};
static unsigned resized;
extern bool __real_pl_tex_recreate(pl_gpu,pl_tex*,const struct pl_tex_params*);
bool __wrap_pl_tex_recreate(pl_gpu gpu,pl_tex *tex,const struct pl_tex_params *params)
{
    if(!*tex || (*tex)->params.w!=params->w || (*tex)->params.h!=params->h)++resized;
    return __real_pl_tex_recreate(gpu,tex,params);
}

static enum cb1_ai_status wait_result(struct cb1_hdr10_extrema *ctx,
                                     struct cb1_hdr10_bounds *out)
{
    for (unsigned i = 0; i < 10000; ++i) {
        enum cb1_ai_status status = cb1_hdr10_extrema_poll(ctx, id, out);
        if (status != CB1_AI_PENDING) return status;
        nanosleep(&(struct timespec){.tv_nsec=1000000}, NULL);
    }
    assert(!"GPU analysis timed out");
    return CB1_AI_INVALID;
}

static void check(struct reference_gpu *gpu, struct cb1_hdr10_extrema *ctx,
                  int w, int h, const float *image, struct cb1_hdr10_bounds expected)
{
    pl_tex texture = reference_texture(gpu->gl->gpu, w, h, image);
    struct cb1_hdr10_bounds out = {19, 23, 29, 31, 37, 41};
    assert(cb1_hdr10_extrema_submit(ctx, texture, id) == CB1_AI_PENDING);
    assert(cb1_hdr10_extrema_submit(ctx, texture, id) == CB1_AI_PENDING);
    /* Texture destruction must not invalidate pending libplacebo work. */
    pl_tex_destroy(gpu->gl->gpu, &texture);
    assert(wait_result(ctx, &out) == CB1_AI_READY);
    assert(out.x0 == expected.x0 && out.y0 == expected.y0 &&
           out.x1 == expected.x1 && out.y1 == expected.y1 &&
           out.minimum == expected.minimum && out.maximum == expected.maximum);
    assert(cb1_hdr10_extrema_poll(ctx, id, &out) == CB1_AI_INVALID);
}

int main(void)
{
    struct reference_gpu gpu = reference_gpu_create();
    fprintf(stderr, "GLSL=%d transfer=%u compute=%u threads=%u group=%u shared=%zu ssbo=%zu\n",
        gpu.gl->gpu->glsl.version, gpu.gl->gpu->limits.buf_transfer,
        gpu.gl->gpu->glsl.compute, gpu.gl->gpu->glsl.max_group_threads,
        gpu.gl->gpu->glsl.max_group_size[0], gpu.gl->gpu->glsl.max_shmem_size,
        gpu.gl->gpu->limits.max_ssbo_size);
    struct cb1_hdr10_extrema *ctx = cb1_hdr10_extrema_create(gpu.gl->gpu);
    assert(ctx);
    cb1_hdr10_extrema_reset(ctx, id.stream, id.revision);
    struct cb1_hdr10_bounds out = {19, 23, 29, 31, 37, 41}, saved = out;
    assert(cb1_hdr10_extrema_poll(ctx, id, &out) == CB1_AI_INVALID);
    assert(!memcmp(&out, &saved, sizeof(out)));
    assert(cb1_hdr10_extrema_submit(ctx, NULL, id) == CB1_AI_INVALID);
    pl_fmt eight = pl_find_fmt(gpu.gl->gpu, PL_FMT_UNORM, 4, 8, 8, PL_FMT_CAP_SAMPLEABLE);
    assert(eight);
    pl_tex low_precision = pl_tex_create(gpu.gl->gpu,
        pl_tex_params(.w=1,.h=1,.format=eight,.sampleable=true));
    assert(low_precision);
    assert(cb1_hdr10_extrema_submit(ctx, low_precision, id) == CB1_AI_INCOMPATIBLE);
    pl_tex_destroy(gpu.gl->gpu, &low_precision);
    pl_fmt sixteen = pl_find_fmt(gpu.gl->gpu, PL_FMT_UNORM, 4, 16, 16, PL_FMT_CAP_SAMPLEABLE);
    assert(sixteen);
    const uint16_t codes[] = {1,1,1,65535, 44,97,65535,65535};
    pl_tex integer_texture = pl_tex_create(gpu.gl->gpu,
        pl_tex_params(.w=2,.h=1,.format=sixteen,.sampleable=true,.initial_data=codes));
    assert(integer_texture);
    assert(cb1_hdr10_extrema_submit(ctx, integer_texture, id) == CB1_AI_PENDING);
    pl_tex_destroy(gpu.gl->gpu, &integer_texture);
    assert(wait_result(ctx, &out) == CB1_AI_READY);
    assert(out.x0 == 1 && out.x1 == 2 && out.y0 == 0 && out.y1 == 1 &&
           out.minimum == 44 && out.maximum == 65535);
    float image[17*13*4] = {0};
    check(&gpu, ctx, 17, 13, image, (struct cb1_hdr10_bounds){0,0,17,13,0,0});
    /* Black borders do not lower the crop minimum; channels still do. */
    for (unsigned y = 2; y < 11; ++y)
        for (unsigned x = 3; x < 14; ++x)
            for (unsigned c = 0; c < 3; ++c)
                image[4*(y*17+x)+c] = (float)(97+c)/65535.f;
    image[4*(5*17+8)+1] = 1.f;
    check(&gpu, ctx, 17, 13, image, (struct cb1_hdr10_bounds){3,2,14,11,97,65535});
    /* Internal black and one-code borders obey the same digital-black rule. */
    image[4*(4*17+4)] = 0.f;
    image[4*(0*17+0)+2] = 1.f/65535.f;
    check(&gpu, ctx, 17, 13, image, (struct cb1_hdr10_bounds){3,2,14,11,0,65535});
    image[4*(0*17+0)+2] = 2.f/65535.f;
    check(&gpu, ctx, 17, 13, image, (struct cb1_hdr10_bounds){0,0,14,11,0,65535});
    /* Full raster and odd dimensions must not lose a corner highlight. */
    for (unsigned i = 0; i < 17*13; ++i)
        for (unsigned c = 0; c < 3; ++c) image[4*i+c] = 400.f/65535.f;
    image[4*(17*13-1)+2] = 1.f;
    check(&gpu, ctx, 17, 13, image, (struct cb1_hdr10_bounds){0,0,17,13,400,65535});
    for (unsigned i = 0; i < 24; ++i)
        check(&gpu, ctx, 17, 13, image, (struct cb1_hdr10_bounds){0,0,17,13,400,65535});
    const float bad[] = {NAN, INFINITY, -.1f, 1.1f};
    for (unsigned i = 0; i < sizeof(bad)/sizeof(*bad); ++i) {
        image[0] = bad[i];
        pl_tex texture = reference_texture(gpu.gl->gpu, 17, 13, image);
        assert(cb1_hdr10_extrema_submit(ctx, texture, id) == CB1_AI_PENDING);
        pl_tex_destroy(gpu.gl->gpu, &texture);
        out = saved;
        assert(wait_result(ctx, &out) == CB1_AI_INVALID);
        assert(!memcmp(&out, &saved, sizeof(out)));
    }
    float *large = calloc(3840*2160*4, sizeof(float));
    assert(large);
    large[4*(3840*2160-1)+2] = 1.f;
    check(&gpu, ctx, 3840, 2160, large,
          (struct cb1_hdr10_bounds){3839,2159,3840,2160,0,65535});
    unsigned warmed=resized;
    check(&gpu, ctx, 3840, 2160, large,
          (struct cb1_hdr10_bounds){3839,2159,3840,2160,0,65535});
    assert(resized==warmed);
    free(large);
    /* Pending destruction is legal; GPU resource references outlive the owner. */
    float pixel[4] = {.3f,.4f,.5f,1.f};
    pl_tex pending = reference_texture(gpu.gl->gpu, 1, 1, pixel);
    assert(cb1_hdr10_extrema_submit(ctx, pending, id) == CB1_AI_PENDING);
    pl_tex_destroy(gpu.gl->gpu, &pending);
    cb1_hdr10_extrema_destroy(&ctx);
    cb1_hdr10_extrema_destroy(&ctx);
    assert(!ctx);
    reference_gpu_destroy(&gpu);
    puts("GPU extrema, active bounds, invalid-input and borrowed-texture tests passed");
}
