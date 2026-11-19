/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_PROCESSING_H
#define CB1_PROCESSING_H
#include <libplacebo/renderer.h>
#include <libplacebo/shaders/colorspace.h>

enum cb1_processing_group {
    CB1_PROCESSING_MMR=0x01, CB1_PROCESSING_SINGLE=0x02,
    CB1_PROCESSING_FEL=0x04, CB1_PROCESSING_COLOUR=0x08,
    CB1_PROCESSING_STORAGE=0x10, CB1_PROCESSING_ALL=0x1f
};

struct cb1_processing_layout {
    struct pl_rect2df crop;
    struct pl_bit_encoding bits;
    int levels, planes;
    struct {
        int width, height, type, components, mapping[4], depth[4];
        float shift_x, shift_y;
        bool flipped;
    } plane[4];
};

struct cb1_processing {
    struct pl_cb1_dovi_processing view;
    struct cb1_processing_layout layout;
    uint32_t requested_groups, selected_groups, rejected_groups, narrow_components;
    uint64_t cache_generation;
    bool metadata_present, enhancement_active, lookup_supported, compute_supported;
    pl_tex mmr_texture;
    pl_tex pq_texture[2];
    struct pl_cb1_dovi_processing cached_contract;
    struct cb1_processing_layout cached_layout;
};

bool cb1_mmr_certify(const struct pl_cb1_dovi_component *component, unsigned denominator);
int64_t cb1_mmr_term(const int64_t coefficients[3], unsigned order, unsigned sample);

bool cb1_processing_prepare(struct cb1_processing *state, pl_gpu gpu,
    const struct pl_frame *source, const void *metadata, size_t bytes,
    bool enhancement_layer_paired, uint32_t requested_groups);
pl_tex cb1_processing_pq_encoder(struct cb1_processing *state, pl_gpu gpu);
void cb1_processing_reset(struct cb1_processing *state, pl_gpu gpu);
#endif
