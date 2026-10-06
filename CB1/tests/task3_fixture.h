/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>

static AVDOVIMetadata *task3_fixture(size_t *bytes)
{
    AVDOVIMetadata *m = av_dovi_metadata_alloc(bytes);
    assert(m);
    AVDOVIRpuDataHeader *h = av_dovi_get_header(m);
    h->disable_residual_flag = 1;
    h->bl_bit_depth = h->el_bit_depth = 10;
    h->coef_log2_denom = 12;
    AVDOVIColorMetadata *c = av_dovi_get_color(m);
    c->signal_eotf = 65535;
    c->source_max_pq = 4095;
    for (int i = 0; i < 9; ++i) {
        c->ycc_to_rgb_matrix[i].num = c->rgb_to_lms_matrix[i].num = i % 4 == 0;
        c->ycc_to_rgb_matrix[i].den = c->rgb_to_lms_matrix[i].den = 1;
    }
    for (int i = 0; i < 3; ++i) {
        c->ycc_to_rgb_offset[i].den = 1;
        AVDOVIReshapingCurve *curve = &av_dovi_get_mapping(m)->curves[i];
        curve->num_pivots = 2;
        curve->pivots[1] = 1023;
        curve->mapping_idc[0] = AV_DOVI_MAPPING_POLYNOMIAL;
        curve->poly_order[0] = 1;
        curve->poly_coef[0][1] = 4096;
    }
    return m;
}
