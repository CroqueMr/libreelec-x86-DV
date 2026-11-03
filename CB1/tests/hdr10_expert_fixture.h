/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <assert.h>
static AVDOVIMetadata *expert_fixture(size_t *bytes,bool residual)
{
    AVDOVIMetadata *m=av_dovi_metadata_alloc(bytes);assert(m);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->disable_residual_flag=!residual;h->bl_bit_depth=h->el_bit_depth=10;
    h->vdr_bit_depth=12;h->coef_log2_denom=12;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    c->signal_eotf=65535;c->source_min_pq=7;c->source_max_pq=3696;
    for(unsigned row=0;row<3;row++){
        c->ycc_to_rgb_offset[row]=(AVRational){0,1};
        for(unsigned col=0;col<3;col++)c->ycc_to_rgb_matrix[3*row+col]=
            c->rgb_to_lms_matrix[3*row+col]=(AVRational){row==col,1};
        AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(m)->curves[row];
        curve->num_pivots=2;curve->pivots[1]=1023;curve->poly_order[0]=1;
        curve->mapping_idc[0]=AV_DOVI_MAPPING_POLYNOMIAL;curve->poly_coef[0][1]=4096;
        av_dovi_get_mapping(m)->nlq[row].vdr_in_max=4096;
        av_dovi_get_mapping(m)->nlq[row].linear_deadzone_slope=residual?4096:0;
    }
    av_dovi_get_mapping(m)->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,3079,1500}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    m->num_ext_blocks=2;
    return m;
}

