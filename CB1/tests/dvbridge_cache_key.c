/* SPDX-License-Identifier: GPL-3.0-only */
#include "../src/dvbridge_render.c"

#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

static size_t bezier_padding_start(void)
{
    return offsetof(struct pl_color_space, hdr) +
           offsetof(struct pl_hdr_metadata, ootf) +
           offsetof(struct pl_hdr_bezier, num_anchors) +
           sizeof(((struct pl_hdr_bezier *) 0)->num_anchors);
}

static size_t bezier_padding_end(void)
{
    return offsetof(struct pl_color_space, hdr) +
           offsetof(struct pl_hdr_metadata, ootf) + sizeof(struct pl_hdr_bezier);
}

static void flip_bezier_padding(struct pl_color_space *c)
{
    const size_t offset = bezier_padding_start();
    assert(offset < bezier_padding_end());
    ((unsigned char *) c)[offset] ^= 0x5a;
}

#define CHECK_CHANGE(expr) do {                                             \
    struct reference_hook variant = h;                                      \
    expr;                                                                    \
    struct cm29_tail_cache_key changed;                                     \
    cm29_gpu_map_make_key(&changed, &variant);                              \
    assert(!cm29_gpu_map_key_equal(&base, &changed));                       \
} while (0)

int main(void)
{
    assert(!cm29_tail_gain_eligible(0));
    assert(!cm29_tail_gain_eligible(1));
    assert(!cm29_tail_gain_eligible(2047.999));
    assert(cm29_tail_gain_eligible(2048));
    assert(cm29_tail_gain_eligible(4095));
    struct reference_hook h = {0};
    h.creative_plan.codes[3] = 3120;
    h.creative_plan.codes[4] = 2048;
    h.creative_plan.policy.tv.peak_nits = 1000;
    h.creative_target = (struct pl_color_space) {
        .primaries = PL_COLOR_PRIM_BT_2020,
        .transfer = PL_COLOR_TRC_LINEAR,
        .hdr = {.min_luma = .005f, .max_luma = 1000,
                .max_pq_y = .75f, .avg_pq_y = .25f},
    };
    h.neutral_target = (struct pl_color_space) {
        .primaries = PL_COLOR_PRIM_BT_2020,
        .transfer = PL_COLOR_TRC_PQ,
        .hdr = {.min_luma = .005f, .max_luma = 1000,
                .max_pq_y = .75f, .avg_pq_y = .25f, .max_cll = 1200},
    };
    h.neutral_target.hdr.ootf.num_anchors = 1;
    h.neutral_target.hdr.ootf.anchors[0] = .25f;
    h.final_mapper = pl_color_map_default_params;
    h.to_xyz.m[0][0] = 1;
    h.to_bt2020.m[1][1] = 1;
    h.pq_encoder = (pl_tex) (uintptr_t) 1;
    h.creative_gamut_state = (pl_shader_obj *) (uintptr_t) 2;

    struct cm29_tail_cache_key base;
    cm29_gpu_map_make_key(&base, &h);
    assert(cm29_gpu_map_key_equal(&base, &base));

    CHECK_CHANGE(variant.creative_plan.codes[3]++);
    CHECK_CHANGE(variant.creative_plan.codes[4]++);
    CHECK_CHANGE(variant.creative_plan.policy.tv.peak_nits++);
    CHECK_CHANGE(variant.creative_target.primaries = PL_COLOR_PRIM_DISPLAY_P3);
    CHECK_CHANGE(variant.creative_target.transfer = PL_COLOR_TRC_PQ);
    CHECK_CHANGE(variant.creative_target.hdr.max_luma++);
    CHECK_CHANGE(variant.neutral_target.primaries = PL_COLOR_PRIM_DISPLAY_P3);
    CHECK_CHANGE(variant.neutral_target.transfer = PL_COLOR_TRC_LINEAR);
    CHECK_CHANGE(variant.neutral_target.hdr.min_luma += .001f);
    CHECK_CHANGE(variant.neutral_target.hdr.max_cll++);
    CHECK_CHANGE(variant.neutral_target.hdr.avg_pq_y += .01f);
    CHECK_CHANGE(variant.neutral_target.hdr.ootf.anchors[0] += .01f);
    CHECK_CHANGE(variant.final_mapper.gamut_expansion =
                 !variant.final_mapper.gamut_expansion);
    CHECK_CHANGE(variant.final_mapper.lut_size++);
    CHECK_CHANGE(variant.to_xyz.m[0][0]++);
    CHECK_CHANGE(variant.to_bt2020.m[1][1]++);
    CHECK_CHANGE(variant.pq_encoder = (pl_tex) (uintptr_t) 3);
    CHECK_CHANGE(variant.creative_gamut_state = (pl_shader_obj *) (uintptr_t) 4);

    struct reference_hook frame = h;
    frame.creative_plan.codes[0]++;
    frame.creative_plan.codes[1]++;
    frame.creative_plan.analysis[1]++;
    frame.creative_source.hdr.max_pq_y = .9f;
    frame.early_l5_black = true;
    struct cm29_tail_cache_key frame_key;
    cm29_gpu_map_make_key(&frame_key, &frame);
    assert(cm29_gpu_map_key_equal(&base, &frame_key));

    struct cm29_tail_cache_key output_pad = base, input_pad = base;
    flip_bezier_padding(&output_pad.output);
    flip_bezier_padding(&input_pad.input);
    assert(pl_color_space_equal(&base.output, &output_pad.output));
    assert(pl_color_space_equal(&base.input, &input_pad.input));
    assert(cm29_gpu_map_key_equal(&base, &output_pad));
    assert(cm29_gpu_map_key_equal(&base, &input_pad));

    puts("CM29 cache key: semantic fields invalidate; padding and per-frame fields do not");
    return 0;
}

#undef CHECK_CHANGE

