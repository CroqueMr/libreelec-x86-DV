/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_master_reference.h"
#include "dvbridge_placebo.h"
#include "dvbridge_metadata_bounds.h"
#include "dvbridge_metadata.h"
#include <libavutil/dovi_meta.h>
#include <limits.h>
#include <string.h>

static unsigned __int128 magnitude(int64_t value)
{
    return value<0?-( __int128)value:value;
}

bool cb1_master_reference_transport(const void *metadata,size_t bytes)
{
    return metadata && !((uintptr_t)metadata%_Alignof(AVDOVIMetadata)) &&
        dvbridge_metadata_bounds(metadata,bytes) &&
        (dvbridge_dv_source_transport(metadata) || dvbridge_dv_profile5_transport(metadata));
}

enum cb1_master_status cb1_master_reference_map(struct pl_cb1_dovi_reference *out,
    const void *metadata,size_t bytes,bool paired)
{
    if(!out)return CB1_MASTER_INVALID;
    memset(out,0,sizeof(*out));
    struct dvbridge_color validated;
    if(!metadata || (uintptr_t)metadata%_Alignof(AVDOVIMetadata) ||
       !dvbridge_metadata_bounds(metadata,bytes))return CB1_MASTER_INVALID;
    const AVDOVIMetadata *m=metadata;
    const AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    const AVDOVIDataMapping *map=av_dovi_get_mapping(m);
    const AVDOVIColorMetadata *color=av_dovi_get_color(m);
    const bool residual=!h->disable_residual_flag && !dvbridge_dv_is_mel(m);
    const bool profile5=dvbridge_dv_profile5(m);
    if((h->bl_bit_depth!=8 && h->bl_bit_depth!=10) ||
       (h->vdr_bit_depth!=10 && h->vdr_bit_depth!=12) ||
       h->coef_log2_denom>23 ||
       (profile5 ? !dvbridge_dv_profile5_transport(m) : color->signal_color_space!=0) ||
       color->signal_eotf!=65535 || color->signal_eotf_param0 ||
       color->signal_eotf_param1 || color->signal_eotf_param2 ||
       map->mapping_color_space || map->mapping_chroma_format_idc ||
       map->num_x_partitions>1 || map->num_y_partitions>1 ||
       h->spatial_resampling_filter_flag || h->el_spatial_resampling_filter_flag>1 ||
       h->chroma_resampling_explicit_filter_flag)return CB1_MASTER_UNSUPPORTED;
    if(!dvbridge_map_color(&validated,metadata,bytes,true))return CB1_MASTER_INVALID;
    struct pl_cb1_dovi_reference next={.contract=1,.bl_depth=h->bl_bit_depth,
        .el_depth=h->el_bit_depth,.output_depth=h->vdr_bit_depth,.denom=h->coef_log2_denom};
    for(int c=0;c<3;c++)next.residual|=residual && map->nlq[c].vdr_in_max;
    if(next.residual && !paired)return CB1_MASTER_INVALID;
    if(next.residual && h->el_bit_depth!=8 && h->el_bit_depth!=10)return CB1_MASTER_UNSUPPORTED;
    for(int c=0;c<3;c++){
        const AVDOVIReshapingCurve *in=&map->curves[c];
        struct pl_cb1_dovi_component *dest=&next.comp[c];
        dest->num_pivots=in->num_pivots;
        memcpy(dest->pivots,in->pivots,in->num_pivots*sizeof(*in->pivots));
        for(int p=0;p+1<in->num_pivots;p++){
            unsigned __int128 bound=0;
            dest->method[p]=in->mapping_idc[p];
            if(in->mapping_idc[p]==AV_DOVI_MAPPING_POLYNOMIAL){
                dest->order[p]=in->poly_order[p];
                memcpy(dest->poly[p],in->poly_coef[p],sizeof(dest->poly[p]));
                for(int i=0;i<=in->poly_order[p];i++)bound+=magnitude(in->poly_coef[p][i]);
            }else{
                if(c==0)return CB1_MASTER_UNSUPPORTED;
                dest->order[p]=in->mmr_order[p];dest->constant[p]=in->mmr_constant[p];
                memcpy(dest->mmr[p],in->mmr_coef[p],sizeof(dest->mmr[p]));
                bound=magnitude(in->mmr_constant[p]);
                for(int order=0;order<in->mmr_order[p];order++)
                    for(int term=0;term<7;term++)bound+=magnitude(in->mmr_coef[p][order][term]);
            }
            if((bound<<20)>INT64_MAX)return CB1_MASTER_UNSUPPORTED;
        }
        if(next.residual){
            const AVDOVINLQParams *q=&map->nlq[c];
            unsigned bits=11-h->el_bit_depth;
            unsigned __int128 bound=((unsigned __int128)131071*q->linear_deadzone_slope<<
                (10-h->el_bit_depth))+((unsigned __int128)q->linear_deadzone_threshold<<bits);
            unsigned __int128 limit=(unsigned __int128)q->vdr_in_max<<bits;
            if(bound>INT64_MAX || limit>INT64_MAX)return CB1_MASTER_UNSUPPORTED;
            int shift=h->coef_log2_denom-5-h->el_bit_depth;
            unsigned __int128 residual=shift>=0?limit>>shift:limit<<-shift;
            if(residual>65535)return CB1_MASTER_UNSUPPORTED;
            next.nlq[c].offset=q->nlq_offset;next.nlq[c].slope=q->linear_deadzone_slope;
            next.nlq[c].threshold=q->linear_deadzone_threshold;next.nlq[c].maximum=q->vdr_in_max;
        }
    }
    *out=next;return CB1_MASTER_READY;
}
