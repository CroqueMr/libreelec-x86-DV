/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Validate parsed Dolby Vision metadata before handing reshaping parameters to libplacebo. */
#include "dvbridge_placebo.h"
#include "dvbridge_metadata.h"
#include "dvbridge_creative.h"
#include <libplacebo/utils/libav.h>
#include <math.h>

bool dvbridge_hdr10_target(struct pl_color_space *out, const void *metadata, size_t bytes)
{
    if (!out || !metadata || (uintptr_t)metadata % _Alignof(AVDOVIMetadata) ||
        !dvbridge_metadata_bounds(metadata, bytes))
        return false;
    const AVDOVIColorMetadata *color = av_dovi_get_color(metadata);
    const AVDOVIDmData *l6 = av_dovi_find_level(metadata, 6);
    float peak = l6 && l6->l6.max_luminance > 0 && l6->l6.max_luminance <= 10000
        ? l6->l6.max_luminance : 0;
    if (!peak && color->source_max_pq > 0 && color->source_max_pq <= 4095)
        peak = pl_hdr_rescale(PL_HDR_PQ, PL_HDR_NITS, color->source_max_pq / 4095.0f);
    if (!isfinite(peak) || peak < 1 || peak > 10000)
        return false;
    *out = (struct pl_color_space){
        .primaries = PL_COLOR_PRIM_BT_2020, .transfer = PL_COLOR_TRC_PQ,
        .hdr = {.min_luma = PL_COLOR_HDR_BLACK, .max_luma = peak},
    };
    return true;
}

bool dvbridge_get_hdr10_metadata(struct dvbridge_hdr10_metadata *out,
                                const void *metadata, size_t bytes)
{
    if (!out || !metadata || (uintptr_t)metadata % _Alignof(AVDOVIMetadata) ||
        !dvbridge_metadata_bounds(metadata, bytes))
        return false;
    *out = (struct dvbridge_hdr10_metadata){0};
    struct pl_color_space target;
    if (!dvbridge_hdr10_target(&target, metadata, bytes))
        return false;
    out->max_luminance = (unsigned)ceilf(target.hdr.max_luma);
    const AVDOVIDmData *l6 = av_dovi_find_level(metadata, 6);
    if (l6 && l6->l6.max_luminance > 0 && l6->l6.max_luminance <= 10000) {
        out->level6 = true;
    }
    /* Source CLL/FALL do not measure the tone-mapped output. Zero means unknown. */
    return true;
}

bool dvbridge_hdr10_session_init(struct dvbridge_hdr10_session *out,
                                 const void *metadata, size_t bytes)
{
    struct dvbridge_color mapped;
    struct dvbridge_hdr10_session candidate = {0};
    if (!out || !dvbridge_map_color(&mapped, metadata, bytes, true) ||
        !dvbridge_hdr10_target(&candidate.target, metadata, bytes) ||
        !dvbridge_get_hdr10_metadata(&candidate.output, metadata, bytes))
        return false;
    *out = candidate;
    return true;
}

bool dvbridge_map_color(struct dvbridge_color *out, const void *metadata,
                       size_t bytes, bool enhancement_layer_paired)
{
    if (!out || !metadata || (uintptr_t)metadata % _Alignof(AVDOVIMetadata))
        return false;
    const AVDOVIMetadata *m = metadata;
    if (!dvbridge_metadata_bounds(m, bytes))
        return false;
    const AVDOVIRpuDataHeader *h = av_dovi_get_header(m);
    const AVDOVIDataMapping *map = av_dovi_get_mapping(m);
    const AVDOVIColorMetadata *color = av_dovi_get_color(m);
    if ((h->disable_residual_flag != 0 && h->disable_residual_flag != 1) ||
        color->signal_eotf != 65535 ||
        (color->signal_color_space != 0 && color->signal_color_space != 2) ||
        color->signal_eotf_param0 || color->signal_eotf_param1 || color->signal_eotf_param2 ||
        color->source_min_pq > color->source_max_pq || color->source_max_pq > 4095)
        return false;
    if (h->bl_bit_depth < 8 || h->bl_bit_depth > 16 || h->coef_log2_denom > 30)
        return false;
    if (!h->disable_residual_flag &&
        (h->el_bit_depth < 8 || h->el_bit_depth > 16 ||
         map->nlq_method_idc != AV_DOVI_NLQ_LINEAR_DZ))
        return false;
    for (int c = 0; c < 3; ++c) {
        const AVDOVIReshapingCurve *curve = &map->curves[c];
        if (curve->num_pivots < 2 || curve->num_pivots > 9)
            return false;
        if (!color->ycc_to_rgb_offset[c].den)
            return false;
        for (int p = 0; p < curve->num_pivots; ++p) {
            if (curve->pivots[p] >= (1u << h->bl_bit_depth) ||
                (p && curve->pivots[p] <= curve->pivots[p - 1]))
                return false;
        }
        for (int p = 0; p + 1 < curve->num_pivots; ++p) {
            if (curve->mapping_idc[p] == AV_DOVI_MAPPING_POLYNOMIAL) {
                if (curve->poly_order[p] > 2)
                    return false;
            } else if (curve->mapping_idc[p] == AV_DOVI_MAPPING_MMR) {
                if (curve->mmr_order[p] < 1 || curve->mmr_order[p] > 3)
                    return false;
            } else {
                return false;
            }
        }
    }
    for (int i = 0; i < 9; ++i)
        if (!color->ycc_to_rgb_matrix[i].den || !color->rgb_to_lms_matrix[i].den)
            return false;
    struct dvbridge_color candidate = {0};
    pl_map_avdovi_metadata(&candidate.color, &candidate.repr, &candidate.dovi, m);
    if (candidate.dovi.nlq_active && !enhancement_layer_paired)
        return false;
    *out = candidate;
    out->repr.dovi = &out->dovi;
    return true;
}

bool dvbridge_reference_map(struct dvbridge_color *out, struct pl_color_space *nominal,
                           struct dvbridge_hdr10_metadata *signal,
                           const struct dvbridge_policy *policy,
                           const void *metadata, size_t bytes, bool paired)
{
    if (!out || !nominal || !signal || dvbridge_policy_validate(policy) != DVBRIDGE_POLICY_VALID ||
        (policy->mode != DVBRIDGE_MODE_HDR10_EXPERT &&
         policy->mode != DVBRIDGE_MODE_ENHANCED_DV))
        return false;
    float peak = policy->tv.peak_nits;
    if (!isfinite(peak) || policy->tv.peak_nits <= 1e-6 || peak <= PL_COLOR_HDR_BLACK ||
        pl_hdr_rescale(PL_HDR_NITS, PL_HDR_PQ, peak) <=
        pl_hdr_rescale(PL_HDR_NITS, PL_HDR_PQ, PL_COLOR_HDR_BLACK))
        return false;
    struct dvbridge_color mapped;
    if (!dvbridge_map_color(&mapped, metadata, bytes, paired))
        return false;
    const AVDOVIMetadata *m = metadata;
    const AVDOVIColorMetadata *source = av_dovi_get_color(m);
    if (source->source_min_pq >= source->source_max_pq)
        return false;
    const AVDOVIDmData *l1 = NULL, *l6 = NULL;
    for (int i = 0; i < m->num_ext_blocks; i++) {
        const AVDOVIDmData *e = av_dovi_get_ext(m, i);
        if (e->level == 1) { if (l1) return false; l1 = e; }
        if (e->level == 6) { if (l6) return false; l6 = e; }
    }
    if (!l1 || !l1->l1.max_pq || l1->l1.max_pq > 4095 ||
        l1->l1.min_pq > l1->l1.avg_pq || l1->l1.avg_pq > l1->l1.max_pq)
        return false;
    if (l6) {
        float minimum = l6->l6.min_luminance / 10000.0f;
        if (!l6->l6.max_luminance || l6->l6.max_luminance > 10000 || minimum >= l6->l6.max_luminance)
            return false;
        mapped.color.hdr.min_luma = minimum;
        mapped.color.hdr.max_luma = l6->l6.max_luminance;
    }
    /* Explicit primaries prevent inference from inventing a source gamut. */
    mapped.color.hdr.prim = *pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020);
    if(policy->mode==DVBRIDGE_MODE_HDR10_EXPERT){
        struct dvbridge_creative_plan creative;
        enum dvbridge_creative_status status=dvbridge_creative_resolve(&creative,m,bytes,policy);
        if(status==DVBRIDGE_CREATIVE_INVALID || status==DVBRIDGE_CREATIVE_UNSUPPORTED)return false;
        if(creative.mastering_primaries_present)mapped.color.hdr.prim=creative.mastering_primaries;
        if(creative.l1_present){
            mapped.color.hdr.max_pq_y=creative.analysis[1]/4095.0f;
            mapped.color.hdr.avg_pq_y=creative.analysis[2]/4095.0f;
        }
    }
    mapped.color.hdr.max_cll = mapped.color.hdr.max_fall = 0;
    enum pl_color_primaries prim = policy->tv.gamut == DVBRIDGE_GAMUT_BT709 ? PL_COLOR_PRIM_BT_709 :
        policy->tv.gamut == DVBRIDGE_GAMUT_P3_D65 ? PL_COLOR_PRIM_DISPLAY_P3 : PL_COLOR_PRIM_BT_2020;
    struct pl_color_space target = {.primaries=prim, .transfer=PL_COLOR_TRC_LINEAR,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK, .max_luma=peak, .prim=*pl_raw_primaries_get(prim)}};
    *out = mapped; out->repr.dovi = &out->dovi;
    *nominal = target;
    *signal = (struct dvbridge_hdr10_metadata){.max_luminance=(unsigned)ceil(policy->tv.peak_nits)};
    return true;
}
