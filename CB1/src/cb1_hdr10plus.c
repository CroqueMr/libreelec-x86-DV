/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_hdr10plus.h"
#include <string.h>

/* FFmpeg rationals describe values, not unscaled wire integers. */
static bool code(AVRational value, unsigned scale, unsigned maximum, unsigned *out)
{
    if(value.den<=0 || value.num<0)return false;
    int64_t n=(int64_t)value.num*scale;
    if(n%value.den || n/value.den>maximum)return false;
    *out=(unsigned)(n/value.den);
    return true;
}

static unsigned saturate(unsigned n,unsigned maximum)
{
    return n<maximum?n:maximum;
}

/* HDMI statistics have 16-nit steps; source statistics have 0.1-nit steps. */
static unsigned luminance(unsigned n)
{
    return saturate((n/10+8)/16,255);
}

enum cb1_hdr10plus_status cb1_hdr10plus_vsif(uint8_t out[CB1_HDR10PLUS_VSIF_BYTES],
    const AVDynamicHDRPlus *m, bool overlay, bool no_delay)
{
    if(!out || !m || m->itu_t_t35_country_code!=0xb5 || !m->num_windows || m->num_windows>3)
        return CB1_HDR10PLUS_INVALID;
    if(m->num_windows!=1 || m->application_version>1 ||
       m->targeted_system_display_actual_peak_luminance_flag ||
       m->mastering_display_actual_peak_luminance_flag)return CB1_HDR10PLUS_UNREPRESENTABLE;
    const AVHDRPlusColorTransformParams *p=&m->params[0];
    if(p->tone_mapping_flag>1 || p->num_distribution_maxrgb_percentiles>15 ||
       p->num_bezier_curve_anchors>15)return CB1_HDR10PLUS_INVALID;
    const bool v0_ten=m->application_version==0 && p->num_distribution_maxrgb_percentiles==10;
    if(p->color_saturation_mapping_flag || (!v0_ten && p->num_distribution_maxrgb_percentiles!=9) ||
       (p->tone_mapping_flag && p->num_bezier_curve_anchors>9))return CB1_HDR10PLUS_UNREPRESENTABLE;
    unsigned target,average,unused,distribution[9];
    if(!code(m->targeted_system_display_maximum_luminance,10000,100000000,&target) ||
       !code(p->average_maxrgb,100000,100000,&average) ||
       !code(p->fraction_bright_pixels,1000,1000,&unused))return CB1_HDR10PLUS_INVALID;
    for(unsigned i=0;i<3;i++)if(!code(p->maxscl[i],100000,100000,&unused))return CB1_HDR10PLUS_INVALID;
    static const uint8_t percentages[]={1,5,10,25,50,75,90,95,99};
    if(v0_ten && (p->distribution_maxrgb[8].percentage!=98 ||
       !code(p->distribution_maxrgb[8].percentile,100000,100000,&unused)))
        return CB1_HDR10PLUS_UNREPRESENTABLE;
    for(unsigned i=0;i<9;i++){
        const unsigned index=v0_ten && i==8?9:i;
        if(p->distribution_maxrgb[index].percentage!=percentages[i])return CB1_HDR10PLUS_UNREPRESENTABLE;
        if(!code(p->distribution_maxrgb[index].percentile,100000,100000,&distribution[i]))
            return CB1_HDR10PLUS_INVALID;
    }
    if(m->application_version==1 && (distribution[1]!=0 || distribution[2]!=255))
        return CB1_HDR10PLUS_UNREPRESENTABLE;
    uint8_t packet[31]={0x81,1,27,0,0x8b,0x84,0x90};
    uint8_t *payload=packet+4;
    payload[3]=(m->application_version<<6)|(saturate((target/10000+16)/32,31)<<1);
    payload[4]=luminance(average);
    for(unsigned i=0;i<9;i++)payload[5+i]=m->application_version==1 && i==2?
        distribution[i]:luminance(distribution[i]);
    if(p->tone_mapping_flag){
        unsigned x,y;
        if(!code(p->knee_point_x,4095,4095,&x) ||
           !code(p->knee_point_y,4095,4095,&y))return CB1_HDR10PLUS_INVALID;
        x=saturate((x+2)/4,1023);y=saturate((y+2)/4,1023);
        payload[14]=(p->num_bezier_curve_anchors<<4)|(x>>6);
        payload[15]=((x&63)<<2)|(y>>8);payload[16]=y&255;
        for(unsigned i=0;i<p->num_bezier_curve_anchors;i++){
            unsigned anchor;
            if(!code(p->bezier_curve_anchors[i],1023,1023,&anchor))return CB1_HDR10PLUS_INVALID;
            payload[17+i]=saturate((anchor+2)/4,255);
            /* A monotone control polygon proves monotonicity after HDMI
             * quantization; unsupported polygons retain the HDR10 fallback. */
            if(i && payload[17+i]<payload[16+i])return CB1_HDR10PLUS_UNREPRESENTABLE;
        }
    }
    payload[26]=(overlay?0x80:0)|(no_delay?0x40:0);
    unsigned sum=0;for(unsigned i=0;i<31;i++)sum+=packet[i];
    packet[3]=(uint8_t)(0u-sum);
    memcpy(out,packet,sizeof(packet));
    return CB1_HDR10PLUS_OK;
}
