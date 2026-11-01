/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include "dvbridge_placebo.h"
#include "cb1_master_reference.h"

int main(void)
{
    size_t bytes;
    AVDOVIMetadata *m = av_dovi_metadata_alloc(&bytes);
    assert(m);
    m->num_ext_blocks = 1;
    av_dovi_get_ext(m, 0)->level = 1;
    AVDOVIRpuDataHeader *h = av_dovi_get_header(m);
    h->disable_residual_flag = 1;
    h->bl_bit_depth = h->el_bit_depth = 10;
    h->coef_log2_denom = 12;
    AVDOVIDataMapping *map = av_dovi_get_mapping(m);
    AVDOVIColorMetadata *color = av_dovi_get_color(m);
    color->signal_eotf = 65535;
    color->source_max_pq = 3079;
    for (int i = 0; i < 9; ++i) {
        color->ycc_to_rgb_matrix[i] = (AVRational){i % 4 == 0, 1};
        color->rgb_to_lms_matrix[i] = (AVRational){i % 4 == 0, 1};
    }
    for (int c = 0; c < 3; ++c) {
        color->ycc_to_rgb_offset[c] = (AVRational){0, 1};
        map->curves[c].num_pivots = 2;
        map->curves[c].pivots[1] = 1023;
        map->curves[c].mapping_idc[0] = AV_DOVI_MAPPING_POLYNOMIAL;
        map->curves[c].poly_order[0] = 1;
        map->curves[c].poly_coef[0][1] = 4096;
    }
    struct dvbridge_color out = {0};
    assert(dvbridge_map_color(&out, m, bytes, false));
    assert(out.repr.dovi == &out.dovi);
    assert(out.repr.sys == PL_COLOR_SYSTEM_DOLBYVISION);
    assert(out.dovi.comp[0].poly_coeffs[0][1] == 1.0f);
    assert(out.dovi.comp[0].pivots[1] == 1.0f);
    struct dvbridge_color saved = out;
    /* Transformers FEL's parsed luma pivots are {0, 0, 1023}. FFmpeg
     * permits a zero pivot delta; libplacebo selects the upper interval at
     * equality. Keep the empty interval and both coefficient sets intact. */
    AVDOVIReshapingCurve original = map->curves[0];
    AVDOVIReshapingCurve *curve = &map->curves[0];
    curve->num_pivots = 3;
    curve->pivots[0] = curve->pivots[1] = 0;
    curve->pivots[2] = 1023;
    curve->mapping_idc[1] = AV_DOVI_MAPPING_POLYNOMIAL;
    curve->poly_order[1] = 2;
    curve->poly_coef[1][2] = 4096;
    struct dvbridge_color duplicate = {0};
    assert(dvbridge_map_color(&duplicate, m, bytes, false));
    assert(duplicate.dovi.comp[0].num_pivots == 3);
    assert(duplicate.dovi.comp[0].pivots[0] == 0.0f);
    assert(duplicate.dovi.comp[0].pivots[1] == 0.0f);
    assert(duplicate.dovi.comp[0].poly_coeffs[0][1] == 1.0f);
    assert(duplicate.dovi.comp[0].poly_coeffs[1][2] == 1.0f);
    struct dvbridge_hdr10_session hdr10;
    assert(dvbridge_hdr10_session_init(&hdr10, m, bytes));
    h->vdr_bit_depth = 12;
    struct pl_cb1_dovi_reference raw;
    assert(cb1_master_reference_map(&raw, m, bytes, false) == CB1_MASTER_READY);
    assert(raw.comp[0].num_pivots == 3 && raw.comp[0].pivots[1] == 0);
    assert(raw.comp[0].poly[0][1] == 4096 && raw.comp[0].poly[1][2] == 4096);
    curve->pivots[1] = 1;
    curve->pivots[2] = 0;
    assert(!dvbridge_map_color(&duplicate, m, bytes, false));
    assert(cb1_master_reference_map(&raw, m, bytes, false) == CB1_MASTER_INVALID);
    curve->pivots[2] = 1024;
    assert(!dvbridge_map_color(&duplicate, m, bytes, false));
    assert(!dvbridge_hdr10_session_init(&hdr10, m, bytes));
    assert(cb1_master_reference_map(&raw, m, bytes, false) == CB1_MASTER_INVALID);
    map->curves[0] = original;
    h->vdr_bit_depth = 0;
    map->curves[0].num_pivots = 255;
    assert(!dvbridge_map_color(&out, m, bytes, false));
    assert(memcmp(&out, &saved, sizeof(out)) == 0);
    map->curves[0].num_pivots = 2;
    h->coef_log2_denom = 63;
    assert(!dvbridge_map_color(&out, m, bytes, false));
    h->coef_log2_denom = 12;
    h->disable_residual_flag = 0;
    map->nlq_method_idc = AV_DOVI_NLQ_LINEAR_DZ;
    map->nlq[0].linear_deadzone_slope = 4096;
    assert(!dvbridge_map_color(&out, m, bytes, false));
    assert(dvbridge_map_color(&out, m, bytes, true));
    assert(out.dovi.nlq_active);
    assert(out.dovi.nlq[0].deadzone_slope == 1023.0f);
    assert(!dvbridge_map_color(&out, m, sizeof(*m) - 1, true));
    av_free(m);
    assert(out.dovi.comp[0].poly_coeffs[0][1] == 1.0f);
    puts("PASS: owned render mapping, malformed input rejection, FEL pairing gate");
}
