/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <libavutil/mem.h>
#include "cb1_hdr10plus.h"

static AVDynamicHDRPlus *fixture(void)
{
    AVDynamicHDRPlus *m=av_dynamic_hdr_plus_alloc(NULL);
    assert(m);
    m->itu_t_t35_country_code=0xb5;
    m->application_version=1;
    m->num_windows=1;
    m->targeted_system_display_maximum_luminance=(AVRational){1000,1};
    AVHDRPlusColorTransformParams *p=&m->params[0];
    for(unsigned c=0;c<3;c++)p->maxscl[c]=(AVRational){20480,100000};
    p->average_maxrgb=(AVRational){1600,100000};
    p->fraction_bright_pixels=(AVRational){0,1000};
    p->num_distribution_maxrgb_percentiles=9;
    const unsigned percentages[]={1,5,10,25,50,75,90,95,99};
    const int values[]={160,0,255,640,1280,2560,5120,10240,20480};
    for(unsigned i=0;i<9;i++)p->distribution_maxrgb[i]=(AVHDRPlusPercentile){percentages[i],{values[i],100000}};
    return m;
}

/* FF Pictures' public hdr10+test_lake_2021_02_01.mp4, first frame (0.4s).
 * MP4 SHA256: ff0aa117f4622387d7d76a33fb6094cb576dab8b8cb59fe18047a614c0e92a5f.
 * This is the 300-nit / 2094 / 96 metadata reported in the RC1.1 forum log.
 * Rejecting ordinary V1 Y99/Y100nit fields must fail this exact reproduction. */
static void ff_pictures_first_frame(void)
{
    AVDynamicHDRPlus *m=fixture();
    m->targeted_system_display_maximum_luminance=(AVRational){300,1};
    AVHDRPlusColorTransformParams *p=&m->params[0];
    const unsigned maxscl[]={3956,2063,2047};
    const unsigned distribution[]={0,2094,96,3,4,5,88,720,2888};
    const unsigned anchors[]={102,205,307,410,512,614,717,819,922};
    for(unsigned i=0;i<3;i++)p->maxscl[i]=(AVRational){maxscl[i],100000};
    p->average_maxrgb=(AVRational){93,100000};
    for(unsigned i=0;i<9;i++){
        p->distribution_maxrgb[i].percentile=(AVRational){distribution[i],100000};
        p->bezier_curve_anchors[i]=(AVRational){anchors[i],1023};
    }
    p->tone_mapping_flag=1;p->num_bezier_curve_anchors=9;
    p->knee_point_x=p->knee_point_y=(AVRational){0,4095};
    const AVDynamicHDRPlus original=*m;
    uint8_t packet[31];
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_OK);
    /* Independent 16-nit statistics and quarter-step curve quantization. */
    const uint8_t expected_payload[]={0x8b,0x84,0x90,0x52,1,0,13,96,0,0,0,1,5,18,
        0x90,0,0,26,51,77,103,128,154,179,205,231,0x40};
    assert(!memcmp(packet+4,expected_payload,sizeof(expected_payload)));
    unsigned sum=0;for(unsigned i=0;i<31;i++)sum+=packet[i];assert(!(sum&255));
    assert(!memcmp(m,&original,sizeof(*m)));
    av_free(m);
}

int main(void)
{
    ff_pictures_first_frame();
    AVDynamicHDRPlus *m=fixture();
    uint8_t packet[31]; memset(packet,0xa5,sizeof(packet));
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_OK);
    /* Hand-derived HDMI fields, including the reserved v1 value 255. */
    const uint8_t expected[31]={0x81,1,27,0,0x8b,0x84,0x90,0x7e,
        10,1,0,255,4,8,16,32,64,128,0,0,0,0,0,0,0,0,0,0,0,0,0x40};
    assert(!memcmp(packet,expected,sizeof(packet)));
    /* Reported V1 Y99 / Y100nit pairs, with hand-derived wire bytes/checksum. */
    const unsigned modern[][4]={{6123,98,38,119},{4768,82,30,143},{1298,93,8,154}};
    for(unsigned i=0;i<3;i++){
        m->params[0].distribution_maxrgb[1].percentile=(AVRational){modern[i][0],100000};
        m->params[0].distribution_maxrgb[2].percentile=(AVRational){modern[i][1],100000};
        AVDynamicHDRPlus original=*m;
        uint8_t wire[31];memcpy(wire,expected,sizeof(wire));
        wire[3]=modern[i][3];wire[10]=modern[i][2];wire[11]=modern[i][1];
        assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_OK);
        assert(!memcmp(packet,wire,sizeof(wire)) && !memcmp(m,&original,sizeof(*m)));
    }
    m->params[0].distribution_maxrgb[1].percentile=(AVRational){0,100000};
    const unsigned allowed[]={0,100,255},rejected[]={101,254,256};
    for(unsigned i=0;i<3;i++){
        m->params[0].distribution_maxrgb[2].percentile=(AVRational){allowed[i],100000};
        assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_OK && packet[11]==allowed[i]);
        uint8_t retained[31];memcpy(retained,packet,sizeof(retained));
        m->params[0].distribution_maxrgb[2].percentile=(AVRational){rejected[i],100000};
        assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_UNREPRESENTABLE);
        assert(!memcmp(packet,retained,sizeof(packet)));
    }
    m->params[0].distribution_maxrgb[2].percentile=(AVRational){255,100000};
    /* The v0 ten-entry form carries 98% as well; HDMI retains the last peak. */
    m->application_version=0;
    AVHDRPlusColorTransformParams *v0=&m->params[0];
    v0->distribution_maxrgb[1].percentile=(AVRational){320,100000};
    v0->distribution_maxrgb[2].percentile=(AVRational){480,100000};
    v0->distribution_maxrgb[9]=v0->distribution_maxrgb[8];
    v0->distribution_maxrgb[8]=(AVHDRPlusPercentile){98,{15360,100000}};
    v0->num_distribution_maxrgb_percentiles=10;
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_OK);
    assert(packet[7]==62 && packet[10]==2 && packet[11]==3 && packet[17]==128);
    v0->distribution_maxrgb[8]=v0->distribution_maxrgb[9];
    v0->num_distribution_maxrgb_percentiles=9;
    v0->distribution_maxrgb[1].percentile=(AVRational){0,100000};
    v0->distribution_maxrgb[2].percentile=(AVRational){255,100000};
    m->application_version=1;
    AVDynamicHDRPlus copy=*m;
    assert(cb1_hdr10plus_vsif(packet,m,true,false)==CB1_HDR10PLUS_OK);
    assert(packet[30]==0x80 && !memcmp(&copy,m,sizeof(copy)));
    unsigned sum=0;for(unsigned i=0;i<31;i++)sum+=packet[i];assert(!(sum&255));

    AVHDRPlusColorTransformParams *p=&m->params[0];
    p->tone_mapping_flag=1;p->num_bezier_curve_anchors=2;
    p->knee_point_x=(AVRational){1024,4095};p->knee_point_y=(AVRational){2048,4095};
    p->bezier_curve_anchors[0]=(AVRational){256,1023};
    p->bezier_curve_anchors[1]=(AVRational){768,1023};
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_OK);
    assert(packet[18]==0x24 && packet[19]==2 && packet[20]==0);
    assert(packet[21]==64 && packet[22]==192 && packet[23]==0);
    p->tone_mapping_flag=0;
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_OK);
    for(unsigned i=18;i<30;i++)assert(packet[i]==0);

    uint8_t before[31];memcpy(before,packet,sizeof(before));
    p->average_maxrgb.den=0;
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_INVALID);
    assert(!memcmp(packet,before,sizeof(packet)));p->average_maxrgb.den=100000;
    p->distribution_maxrgb[2].percentile.num=256;
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_UNREPRESENTABLE);
    p->distribution_maxrgb[2].percentile.num=255;
    m->num_windows=2;
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_UNREPRESENTABLE);
    m->num_windows=1;m->application_version=2;
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_UNREPRESENTABLE);
    m->application_version=1;p->average_maxrgb=(AVRational){-1,100000};
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_INVALID);
    p->average_maxrgb=(AVRational){1,1};
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_OK);
    assert(packet[8]==255);
    p->tone_mapping_flag=1;p->knee_point_x=(AVRational){0,4095};
    p->knee_point_y=(AVRational){0,4095};
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_OK);
    assert(packet[18]==0x20 && packet[19]==0 && packet[20]==0);
    assert(cb1_hdr10plus_vsif(NULL,m,false,true)==CB1_HDR10PLUS_INVALID);
    assert(cb1_hdr10plus_vsif(packet,NULL,false,true)==CB1_HDR10PLUS_INVALID);
    p->num_bezier_curve_anchors=3;
    p->bezier_curve_anchors[0]=(AVRational){1023,1023};
    p->bezier_curve_anchors[1]=p->bezier_curve_anchors[2]=(AVRational){0,1023};
    memcpy(before,packet,sizeof(before));
    assert(cb1_hdr10plus_vsif(packet,m,false,true)==CB1_HDR10PLUS_UNREPRESENTABLE);
    assert(!memcmp(packet,before,sizeof(packet)));
    av_free(m);
    puts("hdr10plus transport: pass");
}
