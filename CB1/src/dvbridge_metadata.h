/* SPDX-License-Identifier: GPL-2.0-or-later
 * Metadata wire format: ETSI GS CCM 001 V1.1.1, clauses 6.2 and 6.3.
 * FFmpeg supplies the metadata layout, byte-order accessors and CRC primitive.
 * See docs/GPL2-MIGRATION.md for replacement provenance and compatibility.
 */
#ifndef MPV_DVBRIDGE_DV_H
#define MPV_DVBRIDGE_DV_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <stdio.h>
#include <limits.h>
#ifdef __cplusplus
extern "C" {
#endif
#include <libavutil/dovi_meta.h>
#include <libavutil/intreadwrite.h>
#include <libavutil/bswap.h>
#include <libavutil/crc.h>
#ifdef __cplusplus
}
#endif
#include "dvbridge_metadata_bounds.h"
#include "mpv_dvbridge_cm4.h"
#include "cb1_master_ipt.h"

static const int16_t dvbridge_output_ycc[9]={9574,0,13802,9574,-1540,-5348,9574,17610,0};
static const uint16_t dvbridge_output_lms[9]={7222,8771,390,2654,12430,1300,0,422,15962};
#define DVBRIDGE_SOURCE_TRANSPORT 1

/* Public state layout retained for the player's transactional frame owner. */
struct dvbridge_dv {
    uint8_t payload[512],previous[512];
    unsigned size,previous_size,id;
    uint32_t packets[640],count;
    uint64_t frames,changes;
    double last_pts;
    int source_w,source_h,dest_x,dest_y,dest_w,dest_h;
    bool fel_verified,source_transport,profile5_transport,ipt_transport;
    unsigned compatibility_omissions;
};

static inline bool dvbridge_dv_wire_rational(AVRational value,int64_t scale,int64_t low,int64_t high)
{
    if(value.den<=0)return false;
    int64_t numerator=(int64_t)value.num*scale;
    return numerator%value.den==0 && numerator/value.den>=low && numerator/value.den<=high;
}

static inline bool dvbridge_dv_profile5(const AVDOVIMetadata *metadata)
{
    const AVDOVIRpuDataHeader *header=av_dovi_get_header(metadata);
    return header->vdr_rpu_profile==0 && header->bl_video_full_range_flag;
}

static inline bool cb1_wire_signal_space(const AVDOVIMetadata *metadata,bool ipt)
{
    const AVDOVIColorMetadata *color=av_dovi_get_color(metadata);
    return av_dovi_get_header(metadata)->vdr_bit_depth==12 && color->signal_bit_depth==12 &&
        color->signal_color_space==(ipt?2:0) && color->signal_full_range_flag==1 &&
        color->signal_eotf==65535 && color->signal_eotf_param0==0 &&
        color->signal_eotf_param1==0 && color->signal_eotf_param2==0;
}

static inline bool cb1_wire_signal(const AVDOVIMetadata *metadata)
{
    return cb1_wire_signal_space(metadata,false);
}

static inline bool cb1_wire_offsets_space(const AVDOVIColorMetadata *color,bool ipt)
{
    for(unsigned channel=0;channel<3;channel++){
        AVRational value=color->ycc_to_rgb_offset[channel];
        if(value.den<=0 || (ipt && !channel?value.num!=0:
            (int64_t)value.num*(channel?2:16)!=value.den))return false;
    }
    return true;
}

static inline bool cb1_wire_offsets(const AVDOVIColorMetadata *color)
{
    return cb1_wire_offsets_space(color,false);
}

static inline bool dvbridge_dv_source_transport_valid(const AVDOVIMetadata *metadata,bool ipt)
{
    const AVDOVIColorMetadata *color=av_dovi_get_color(metadata);
    if(!cb1_wire_signal_space(metadata,ipt) || color->signal_chroma_format ||
       !cb1_wire_offsets_space(color,ipt))return false;
    const AVRational *matrix[2]={color->ycc_to_rgb_matrix,color->rgb_to_lms_matrix};
    for(unsigned index=0;index<2;index++){
        double values[9];
        for(unsigned element=0;element<9;element++){
            AVRational value=matrix[index][element];
            if(!dvbridge_dv_wire_rational(value,index?16384:8192,INT16_MIN,INT16_MAX))return false;
            values[element]=(double)value.num/value.den;
        }
        double a=values[4]*values[8]-values[5]*values[7];
        double b=values[3]*values[8]-values[5]*values[6];
        double c=values[3]*values[7]-values[4]*values[6];
        double determinant=values[0]*a-values[1]*b+values[2]*c;
        if(!isfinite(determinant) || fabs(determinant)<1e-8)return false;
    }
    return true;
}

static inline bool dvbridge_dv_source_transport(const AVDOVIMetadata *metadata)
{
    return dvbridge_dv_source_transport_valid(metadata,false);
}

/* Exact Master P5 IPT carrier; Standard alone uses characterized Fast reshaping. */
static inline bool dvbridge_dv_profile5_transport(const AVDOVIMetadata *metadata)
{
    const AVDOVIRpuDataHeader *header=av_dovi_get_header(metadata);
    return dvbridge_dv_profile5(metadata) && header->bl_bit_depth==10 &&
        header->disable_residual_flag && dvbridge_dv_source_transport_valid(metadata,true);
}

static inline bool dvbridge_dv_source_matches_output(const AVDOVIMetadata *metadata)
{
    if(!cb1_wire_signal(metadata))return false;
    const AVDOVIColorMetadata *color=av_dovi_get_color(metadata);
    for(unsigned element=0;element<9;element++){
        AVRational ycc=color->ycc_to_rgb_matrix[element],lms=color->rgb_to_lms_matrix[element];
        if(ycc.den<=0 || lms.den<=0 ||
           (int64_t)ycc.num*8192!=(int64_t)dvbridge_output_ycc[element]*ycc.den ||
           (int64_t)lms.num*16384!=(int64_t)dvbridge_output_lms[element]*lms.den)return false;
    }
    return cb1_wire_offsets(color);
}

static inline bool dvbridge_dv_bounds(const AVDOVIMetadata *metadata,size_t bytes)
{
    return dvbridge_metadata_bounds(metadata,bytes) && metadata->num_ext_blocks>0;
}

static inline bool dvbridge_dv_geometry(struct dvbridge_dv *state,int w,int h,int x,int y,int dw,int dh)
{
    if(w<=0 || h<=0 || w>3840 || h>2160 || dw<=0 || dh<=0 || x<0 || y<0 ||
       dw>3840 || dh>2160 || x>3840-dw || y>2160-dh || (x&1) || (dw&1) ||
       fabs((double)dw*h/w-dh)>1.01)return false;
    state->source_w=w;state->source_h=h;state->dest_x=x;state->dest_y=y;state->dest_w=dw;state->dest_h=dh;
    return true;
}

static inline bool dvbridge_dv_area(struct dvbridge_dv *state,unsigned left,unsigned right,
                                   unsigned top,unsigned bottom,unsigned out[4])
{
    unsigned w=state->source_w?state->source_w:3840,h=state->source_h?state->source_h:2160;
    int dw=state->dest_w?state->dest_w:3840,dh=state->dest_h?state->dest_h:2160;
    if(left>=w || right>=w-left || top>=h || bottom>=h-top)return false;
    out[0]=state->dest_x+lround((double)left*dw/w);
    out[1]=3840-state->dest_x-dw+lround((double)right*dw/w);
    out[2]=state->dest_y+lround((double)top*dh/h);
    out[3]=2160-state->dest_y-dh+lround((double)bottom*dh/h);
    return out[0]+out[1]<3840 && out[2]+out[3]<2160;
}

static inline bool dvbridge_dv_is_mel(const AVDOVIMetadata *metadata)
{
    if(!metadata)return false;
    const AVDOVIRpuDataHeader *header=av_dovi_get_header(metadata);
    const AVDOVIDataMapping *mapping=av_dovi_get_mapping(metadata);
    if(header->disable_residual_flag || header->coef_log2_denom>32 ||
       mapping->nlq_method_idc!=AV_DOVI_NLQ_LINEAR_DZ)return false;
    uint64_t maximum=UINT64_C(1)<<header->coef_log2_denom;
    for(unsigned channel=0;channel<3;channel++){
        const AVDOVINLQParams *nlq=&mapping->nlq[channel];
        if(nlq->nlq_offset || nlq->vdr_in_max!=maximum ||
           nlq->linear_deadzone_slope || nlq->linear_deadzone_threshold)return false;
    }
    return true;
}

static inline void dvbridge_dv_u16(struct dvbridge_dv *state,unsigned value)
{
    AV_WB16(state->payload+state->size,value);state->size+=2;
}
static inline void dvbridge_dv_u32(struct dvbridge_dv *state,unsigned value)
{
    AV_WB32(state->payload+state->size,value);state->size+=4;
}
static inline uint32_t dvbridge_dv_crc(const uint8_t *data,size_t size)
{
    return av_bswap32(av_crc(av_crc_get_table(AV_CRC_32_IEEE),UINT32_MAX,data,size));
}

struct cb1_wire_block {const AVDOVIDmData *data;unsigned rank,index;};
static inline int cb1_wire_block_compare(const void *first,const void *second)
{
    const struct cb1_wire_block *a=(const struct cb1_wire_block *)first,*b=(const struct cb1_wire_block *)second;
    if(a->rank!=b->rank)return a->rank>b->rank?1:-1;
    return (a->index>b->index)-(a->index<b->index);
}

static inline bool cb1_wire_append(struct dvbridge_dv *state,unsigned level,const uint8_t *bytes,unsigned count)
{
    if(count>sizeof(state->payload)-5 || state->size>sizeof(state->payload)-5-count)return false;
    dvbridge_dv_u32(state,count);state->payload[state->size++]=level;
    memcpy(state->payload+state->size,bytes,count);state->size+=count;
    state->payload[70]++;
    return true;
}

/* Failed operations have no output payload. The owner commits only success. */
static inline bool dvbridge_dv_metadata_output(struct dvbridge_dv *state,const AVDOVIMetadata *metadata,
                                              double pts,const unsigned margins[4],bool force_refresh)
{
    if(!metadata || !isfinite(pts))return false;
    const AVDOVIRpuDataHeader *header=av_dovi_get_header(metadata);
    const AVDOVIColorMetadata *color=av_dovi_get_color(metadata);
    if((header->disable_residual_flag!=1 && !state->fel_verified && !dvbridge_dv_is_mel(metadata)) ||
       color->signal_eotf!=65535 || (color->signal_color_space!=0 && color->signal_color_space!=2) ||
       color->signal_eotf_param0 || color->signal_eotf_param1 || color->signal_eotf_param2 ||
       color->source_min_pq>color->source_max_pq || color->source_max_pq>4095 ||
       metadata->num_ext_blocks<=0 || metadata->num_ext_blocks>AV_DOVI_MAX_EXT_BLOCKS ||
       (state->source_transport && !(state->profile5_transport?
           dvbridge_dv_profile5_transport(metadata):dvbridge_dv_source_transport(metadata))) ||
       (state->ipt_transport && (state->source_transport || !dvbridge_dv_source_transport(metadata))))return false;
    uint8_t base[71]={0};
    bool repeat=state->frames && pts==state->last_pts;
    bool discontinuity=!state->frames || pts<state->last_pts || pts-state->last_pts>0.1;
    base[1]=force_refresh?1:repeat?state->previous[1]:discontinuity?1:color->scene_refresh_flag;
    for(unsigned element=0;element<9;element++){
        AVRational a=color->ycc_to_rgb_matrix[element],b=color->rgb_to_lms_matrix[element];
        unsigned ycc=state->source_transport?(uint16_t)((int64_t)a.num*8192/a.den):
            (uint16_t)(state->ipt_transport?cb1_ipt_output_ycc[element]:dvbridge_output_ycc[element]);
        unsigned lms=state->source_transport?(uint16_t)((int64_t)b.num*16384/b.den):
            (uint16_t)(state->ipt_transport?cb1_ipt_output_lms[element]:dvbridge_output_lms[element]);
        AV_WB16(base+2+element*2,ycc);AV_WB16(base+32+element*2,lms);
    }
    AV_WB32(base+20,state->profile5_transport || state->ipt_transport?0:16777216);AV_WB32(base+24,134217728);AV_WB32(base+28,134217728);
    AV_WB16(base+50,65535);base[60]=12;base[61]=state->profile5_transport || state->ipt_transport?2:0;base[62]=1;base[63]=1;
    AV_WB16(base+64,color->source_min_pq);AV_WB16(base+66,color->source_max_pq);
    AV_WB16(base+68,state->source_transport || state->ipt_transport?color->source_diagonal:42);
    memcpy(state->payload,base,sizeof(base));state->size=sizeof(base);
    struct cb1_wire_block blocks[AV_DOVI_MAX_EXT_BLOCKS];
    for(int index=0;index<metadata->num_ext_blocks;index++){
        const AVDOVIDmData *data=av_dovi_get_ext(metadata,index);
        unsigned level=data->level;
        unsigned rank=level+((level==3 || (level>=8 && level<=11) || level==254)?256:0);
        blocks[index]=(struct cb1_wire_block){data,rank,(unsigned)index};
    }
    qsort(blocks,metadata->num_ext_blocks,sizeof(*blocks),cb1_wire_block_compare);
    unsigned l1_count=0,l5_count=0,targets[AV_DOVI_MAX_EXT_BLOCKS],target_count=0;
    for(int index=0;index<metadata->num_ext_blocks;index++){
        const AVDOVIDmData *data=blocks[index].data;
        unsigned values[7],words=0;uint8_t bytes[32];
        switch(data->level){
        case 1:
            if(l5_count)return false;
            l1_count++;words=3;
            values[0]=data->l1.min_pq;values[1]=data->l1.max_pq;values[2]=data->l1.avg_pq;
            if(values[0]>values[2] || values[2]>values[1])return false;
            break;
        case 2:
            if(l5_count)return false;
            words=7;values[0]=data->l2.target_max_pq;values[1]=data->l2.trim_slope;
            values[2]=data->l2.trim_offset;values[3]=data->l2.trim_power;
            values[4]=data->l2.trim_chroma_weight;values[5]=data->l2.trim_saturation_gain;
            values[6]=(uint16_t)data->l2.ms_weight;
            for(unsigned t=0;t<target_count;t++)if(targets[t]==values[0])return false;
            targets[target_count++]=values[0];break;
        case 5:
            if(l1_count!=1 || l5_count++)return false;
            words=4;memcpy(values,margins,4*sizeof(*margins));break;
        case 6:continue;
        case 3:case 4:case 8:case 9:case 10:case 11:case 254:{
            if(data->dvbridge_raw_magic!=0x41424456)return false;
            int length=dvbridge_cm4_wire(data->level,data->dvbridge_original_bytes,data->dvbridge_original_length,bytes);
            if(length<0){
                fprintf(stderr,"DVBRIDGE_CM4_REJECT level=%d length=%u\n",data->level,data->dvbridge_original_length);
                return false;
            }
            if(!cb1_wire_append(state,data->level,bytes,(unsigned)length))return false;
            continue;
        }
        default:
            fprintf(stderr,"DVBRIDGE_DV_UNSUPPORTED_METADATA level=%d\n",data->level);return false;
        }
        for(unsigned word=0;word<words;word++){
            if(values[word]>4095 && !(data->level==2 && word==6 && values[word]==65535))return false;
            AV_WB16(bytes+word*2,values[word]);
        }
        if(!cb1_wire_append(state,data->level,bytes,words*2))return false;
    }
    if(l1_count!=1)return false;
    if(!l5_count){
        uint8_t bytes[8];for(unsigned i=0;i<4;i++)AV_WB16(bytes+i*2,margins[i]);
        if(!cb1_wire_append(state,5,bytes,sizeof(bytes)))return false;
    }
    if(state->payload[70]>AV_DOVI_MAX_EXT_BLOCKS)return false;
    if(state->frames && (state->previous_size!=state->size || memcmp(state->previous,state->payload,state->size))){
        state->id=(state->id+1)&15;state->changes++;
    }
    memcpy(state->previous,state->payload,state->size);state->previous_size=state->size;
    state->count=1+(state->size>119?(state->size-119+120)/121:0);
    if(state->count>5)return false;
    memset(state->packets,0,sizeof(state->packets));
    unsigned consumed=0;
    for(unsigned index=0;index<state->count;index++){
        uint8_t packet[128]={0};
        unsigned type=state->count==1?0:index==0?1:index+1==state->count?3:2;
        packet[0]=type<<6;packet[1]=(state->id<<4)|state->id;
        unsigned start=index?3:5,room=124-start;
        unsigned remaining=state->size-consumed,take=remaining<room?remaining:room;
        if(!index)AV_WB16(packet+3,state->size);
        memcpy(packet+start,state->payload+consumed,take);consumed+=take;
        AV_WB32(packet+124,dvbridge_dv_crc(packet,124));
        if(dvbridge_dv_crc(packet,sizeof(packet)))return false;
        for(unsigned byte=0;byte<sizeof(packet);byte++)state->packets[index*128+byte]=packet[byte];
    }
    state->last_pts=pts;state->frames++;
    return true;
}

static inline bool dvbridge_dv_metadata(struct dvbridge_dv *state,const AVDOVIMetadata *metadata,
                                       double pts,const unsigned margins[4])
{
    return dvbridge_dv_metadata_output(state,metadata,pts,margins,false);
}
#endif
