/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_master_reference.h"
#include "dvbridge_placebo.h"
#include "dvbridge_metadata_bounds.h"
#include "dvbridge_metadata.h"
#include <libavutil/dovi_meta.h>
#include <libplacebo/shaders/colorspace.h>
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

static enum cb1_master_status reference_map(struct pl_cb1_dovi_reference *out,
    struct dvbridge_color *color_map,const void *metadata,size_t bytes,bool paired)
{
    if(!out)return CB1_MASTER_INVALID;
    memset(out,0,sizeof(*out));
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
    if(!dvbridge_map_color(color_map,metadata,bytes,true))return CB1_MASTER_INVALID;
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
            /* Bound each reachable sign separately: positive shifts round down,
             * negative arithmetic shifts round away from zero in magnitude. */
            for(unsigned negative=0;negative<2;negative++){
                unsigned delta=negative?q->nlq_offset:65535-q->nlq_offset;
                if(!delta)continue;
                unsigned __int128 reachable=((unsigned __int128)(2*delta-1)*
                    q->linear_deadzone_slope<<(10-h->el_bit_depth))+
                    ((unsigned __int128)q->linear_deadzone_threshold<<bits);
                if(reachable>limit)reachable=limit;
                if(shift>=0?(negative?reachable>((unsigned __int128)65535<<shift):
                                      (reachable>>shift)>65535):
                             (reachable<<-shift)>65535)return CB1_MASTER_UNSUPPORTED;
            }
            next.nlq[c].offset=q->nlq_offset;next.nlq[c].slope=q->linear_deadzone_slope;
            next.nlq[c].threshold=q->linear_deadzone_threshold;next.nlq[c].maximum=q->vdr_in_max;
        }
    }
    *out=next;return CB1_MASTER_READY;
}

enum cb1_master_status cb1_master_reference_map(struct pl_cb1_dovi_reference *out,
    const void *metadata,size_t bytes,bool paired)
{
    struct dvbridge_color mapped;
    return reference_map(out,&mapped,metadata,bytes,paired);
}

enum cb1_master_status cb1_master_reconstruct(pl_renderer renderer,
    const struct pl_frame *source,const void *metadata,size_t bytes,
    double pts,double el_pts,pl_tex target,const struct pl_hook *finish,const int active_rows[2])
{
    if(!renderer || !source || !target || !isfinite(pts))return CB1_MASTER_INVALID;
    const struct pl_frame *el=source->enhancement_layer;
    struct pl_cb1_dovi_reference raw;
    struct dvbridge_color mapped;
    enum cb1_master_status status=reference_map(&raw,&mapped,metadata,bytes,el && pts==el_pts);
    if(status!=CB1_MASTER_READY)return status;
    if(!pl_cb1_dovi_reference_frame_supported(source,raw.bl_depth) || source->num_overlays ||
       (raw.residual && (!pl_cb1_dovi_reference_frame_supported(el,raw.el_depth) || el->num_overlays)))
        return CB1_MASTER_UNSUPPORTED;
    if(raw.residual){
        int scale=av_dovi_get_header(metadata)->el_spatial_resampling_filter_flag?2:1;
        if(el->crop.x1*scale!=source->crop.x1 || el->crop.y1*scale!=source->crop.y1)
            return CB1_MASTER_UNSUPPORTED;
    }
    const struct pl_tex_params *out=&target->params;
    const pl_fmt fmt=out->format;
    if(!out->renderable || out->w!=source->crop.x1 || out->h!=source->crop.y1 ||
       fmt->type!=PL_FMT_FLOAT || fmt->num_components!=4 ||
       fmt->component_depth[0]!=32 || fmt->component_depth[1]!=32 || fmt->component_depth[2]!=32)
        return CB1_MASTER_UNSUPPORTED;

    struct pl_frame image=*source;
    image.enhancement_layer=raw.residual?el:NULL;
    if(raw.residual){
        /* libplacebo acquires the EL only for a DOVI frame with active NLQ.
         * The exact shader still reads the original decoder storage bits. */
        image.repr=mapped.repr;
        image.repr.bits=source->repr.bits;
        image.color=mapped.color;
    }
    struct pl_frame output={.num_planes=1,.planes={{.texture=target,.components=4,
        .component_mapping={0,1,2,3}}},.repr=pl_color_repr_rgb,.crop=source->crop};
    /* Transport here only disables libplacebo colour conversion. The texture
     * contains components, with no packing, HDMI signaling or metadata edits. */
    raw.contract=2;
    struct pl_render_params params=pl_render_default_params;
    params.cb1_dovi_reference=&raw;
    params.cb1_dovi_transport=true;
    params.min_fbo_precision=32;
    params.disable_linear_scaling=true;
    params.sigmoid_params=NULL;
    params.peak_detect_params=NULL;
    params.dither_params=NULL;
    params.frame_mixer=NULL;
    if(finish){
        params.hooks=&finish;
        params.num_hooks=1;
    }
    const bool prune=finish && active_rows && out->w==3840 && out->h==2160 &&
        !output.crop.x0 && !output.crop.y0 && !image.rotation &&
        (active_rows[0]>0 || active_rows[1]<out->h);
    const bool ok=prune?pl_render_image_cb1_active_rows(renderer,&image,&output,&params,
        active_rows[0],active_rows[1]):pl_render_image(renderer,&image,&output,&params);
    return ok?CB1_MASTER_READY:CB1_MASTER_FAILED;
}
