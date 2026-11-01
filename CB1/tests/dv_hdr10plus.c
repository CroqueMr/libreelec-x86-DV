/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "task3_fixture.h"
#include "cb1_dv_hdr10plus.h"
#include <stdio.h>
#include <string.h>

static AVDOVIDmData vector_anchor(unsigned index)
{
    AVDOVIDmData a={.level=8,.l8={.target_display_index=index,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,
        .trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=2048,
        .target_mid_contrast=2048,.clip_trim=2048},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=25,
        .dvbridge_original_bytes={index,0x80,0x08,0,0x80,0x08,0,0x80,0x08,0,0x80,0x08,0}};
    memset(a.dvbridge_original_bytes+13,128,12);
    memset(a.l8.saturation_vector_field,128,6);
    memset(a.l8.hue_vector_field,128,6);
    return a;
}

static void neutral_vectors(AVDOVIMetadata *m,size_t bytes,
    const struct cb1_hdr10plus_statistics *s)
{
    AVDynamicHDRPlus out;struct cb1_dv_hdr10plus_report r;
    const unsigned peaks[][2]={{3000,3200},{3079,3200},{2800,3000}};
    for(unsigned scenario=0;scenario<3;scenario++){
        m->num_ext_blocks=5;
        for(unsigned anchor=0;anchor<2;anchor++){
            unsigned index=50+anchor,peak=peaks[scenario][anchor];
            *av_dovi_get_ext(m,1+2*anchor)=vector_anchor(index);
            *av_dovi_get_ext(m,2+2*anchor)=(AVDOVIDmData){.level=10,
                .l10={.target_display_index=index,.target_max_pq=peak,
                    .target_min_pq=0,.target_primary_index=2},
                .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
                .dvbridge_original_bytes={index,peak>>4,(peak&15)<<4,0,2}};
        }
        void *before=av_memdup(m,bytes);assert(before);
        assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,s));
        assert(r.coverage==CB1_DV_HDR10PLUS_L8 && r.reason==CB1_DV_HDR10PLUS_OK);
        assert(!memcmp(before,m,bytes));av_free(before);
        /* 992 nits lies between, below both or above both target anchors. */
        const unsigned contributors[]={3,1,2};
        for(unsigned anchor=0;anchor<2;anchor++)for(unsigned family=0;family<2;family++){
            AVDOVIDmData *a=av_dovi_get_ext(m,1+2*anchor);
            for(unsigned component=0;component<6;component++){
                unsigned offset=13+6*family+component;
                uint8_t *parsed=family?a->l8.hue_vector_field:a->l8.saturation_vector_field;
                a->dvbridge_original_bytes[offset]=parsed[component]=129;
                assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,s));
                bool contributes=contributors[scenario]&(1u<<anchor);
                assert((r.coverage==CB1_DV_HDR10PLUS_L8)==!contributes);
                if(contributes)assert(r.reason==CB1_DV_HDR10PLUS_UNREPRESENTABLE_TRIMS);
                a->dvbridge_original_bytes[offset]=parsed[component]=128;
            }
        }
    }
}

int main(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,3696,1700}};
    struct cb1_hdr10plus_statistics s={.maxscl={4000,4000,4000},.average_maxrgb=120,
        .count=10000,.histogram={[0]=9500,[10]=400,[250]=100}};
    AVDynamicHDRPlus out={0};struct cb1_dv_hdr10plus_report r;
    void *source=av_memdup(m,bytes);assert(source);
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(!memcmp(m,source,bytes));
    assert(out.application_version==1 && out.params[0].average_maxrgb.num==1200);
    assert(r.effective_l1[1]==3696 && !r.l3_used);
    assert(r.coverage==CB1_DV_HDR10PLUS_STATISTICS &&
           r.reason==CB1_DV_HDR10PLUS_UNREPRESENTABLE_CURVE);
    uint8_t packet[31];assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK);
    AVDynamicHDRPlus v1=out;
    assert(cb1_dv_hdr10plus_metadata_for_version(&out,&r,m,bytes,&s,1));
    assert(!memcmp(&v1,&out,sizeof(v1)));
    struct cb1_hdr10plus_statistics graded=s;
    memset(graded.histogram,0,sizeof(graded.histogram));
    graded.histogram[1]=50;graded.histogram[2]=450;graded.histogram[3]=500;
    graded.histogram[10]=8900;graded.histogram[250]=100;
    assert(cb1_dv_hdr10plus_metadata_for_version(&out,&r,m,bytes,&graded,0));
    assert(out.application_version==0);
    assert(out.params[0].distribution_maxrgb[1].percentile.num==320);
    assert(out.params[0].distribution_maxrgb[2].percentile.num==480);
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK);
    assert(packet[10]==2 && packet[11]==3 && (packet[7]>>6)==0);
    AVDynamicHDRPlus unchanged=out;
    assert(!cb1_dv_hdr10plus_metadata_for_version(&out,&r,m,bytes,&graded,2));
    assert(!memcmp(&unchanged,&out,sizeof(out)));
    /* Missing L1 retains measured descriptive metadata, not guessed L1. */
    m->num_ext_blocks=0;
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(r.coverage==CB1_DV_HDR10PLUS_STATISTICS && r.reason==CB1_DV_HDR10PLUS_NO_ANALYSIS);
    assert(!out.params[0].tone_mapping_flag);
    /* L3 offsets are resolved once through the existing validated decoder. */
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=3,.l3={2048,2058,2068},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
        .dvbridge_original_bytes={0x80,0x08,0x0a,0x81,0x40}};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(r.effective_l1[1]==3716 && r.effective_l1[2]==1740);
    /* An explicit chroma edit must not be reported as translated. */
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=3072,.ms_weight=-1}};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(r.coverage!=CB1_DV_HDR10PLUS_L2 && r.coverage!=CB1_DV_HDR10PLUS_L8);
    assert(r.reason==CB1_DV_HDR10PLUS_UNREPRESENTABLE_TRIMS);
    /* A sub-target linear response cannot retain its endpoint after HDMI
     * quantization. Keep measured metadata instead of a false curve. */
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,2769,1700}};
    s=(struct cb1_hdr10plus_statistics){.maxscl={496,496,496},.average_maxrgb=100,
        .count=10000,.histogram={[0]=9500,[10]=400,[31]=100}};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(r.coverage==CB1_DV_HDR10PLUS_STATISTICS && !out.params[0].tone_mapping_flag);
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,3076,1700}};
    s=(struct cb1_hdr10plus_statistics){.maxscl={992,992,992},.average_maxrgb=100,
        .count=10000,.histogram={[0]=9500,[10]=400,[62]=100}};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(r.coverage==CB1_DV_HDR10PLUS_L1 && out.params[0].tone_mapping_flag);
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2044,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(r.coverage==CB1_DV_HDR10PLUS_L2 && r.maximum_color_pq_error<2.0/1023);
    /* Chroma weight has no effect when saturation is neutral. Keep the
     * luminous trim and its exact output instead of rejecting the family. */
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK);
    uint8_t neutral_chroma[31];memcpy(neutral_chroma,packet,sizeof(packet));
    av_dovi_get_ext(m,1)->l2.trim_chroma_weight=3000;
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(r.coverage==CB1_DV_HDR10PLUS_L2 && r.reason==CB1_DV_HDR10PLUS_OK);
    assert(av_dovi_get_ext(m,1)->l2.trim_chroma_weight==3000);
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK);
    assert(!memcmp(packet,neutral_chroma,sizeof(packet)));
    /* Neutral CM4 controls use the same checked representation, not L2 twice. */
    m->num_ext_blocks=3;
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=8,.l8={.target_display_index=20,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,
        .trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=2048},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=10,
        .dvbridge_original_bytes={20,0x80,0x08,0x00,0x80,0x08,0x00,0x80,0x08,0x00}};
    *av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=10,.l10={.target_display_index=20,
        .target_max_pq=3079,.target_min_pq=0,.target_primary_index=2},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
        .dvbridge_original_bytes={20,0xc0,0x70,0x00,2}};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(r.coverage==CB1_DV_HDR10PLUS_L8 && out.params[0].tone_mapping_flag);
    void *saved=av_memdup(m,bytes);assert(saved);
    neutral_vectors(m,bytes,&s);
    memcpy(m,saved,bytes);av_free(saved);
    AVDynamicHDRPlus old=out;s.histogram[0]++;
    assert(!cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));assert(!memcmp(&out,&old,sizeof(out)));
    /* Descriptive metadata keeps its target even when no curve is available. */
    m->num_ext_blocks=0;
    s=(struct cb1_hdr10plus_statistics){.count=10000,.histogram={[0]=10000}};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(out.targeted_system_display_maximum_luminance.num==992);
    assert(!out.params[0].tone_mapping_flag && r.reason==CB1_DV_HDR10PLUS_NO_ANALYSIS);
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK);
    assert(packet[7]==126 && packet[8]==0 && packet[10]==0 && packet[11]==255);
    uint8_t black[31];memcpy(black,packet,sizeof(black));
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK);
    assert(!memcmp(black,packet,sizeof(black)));
    s=(struct cb1_hdr10plus_statistics){.maxscl={160,160,160},.average_maxrgb=160,
        .count=10000,.histogram={[10]=10000}};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK);
    assert(packet[8]==10 && packet[9]==10 && packet[17]==10);
    assert(memcmp(black,packet,sizeof(black)));
    /* #64: changing sub-quantization statistics can legitimately retain
     * exactly the measured packet. Never invent per-frame packet changes. */
    s=(struct cb1_hdr10plus_statistics){.maxscl={272,24,4},.average_maxrgb=50.88,
        .count=10000,.histogram={[2]=6000,[3]=3300,[13]=500,[17]=200}};
    const uint8_t reported[31]={0x81,1,0x1b,0xda,0x8b,0x84,0x90,0x7e,3,2,0,255,
        2,2,3,3,13,17,[30]=0x40};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK);
    assert(!memcmp(packet,reported,sizeof(packet)));
    s.histogram[3]++;s.histogram[13]--;s.average_maxrgb=50.864;s.maxscl[0]=279;
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK);
    assert(!memcmp(packet,reported,sizeof(packet)));
    s.average_maxrgb=55.9;
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK && packet[8]==3);
    s.average_maxrgb=56;
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK && packet[8]==4);
    s=(struct cb1_hdr10plus_statistics){.maxscl={272,272,272},.average_maxrgb=32.048,
        .count=10000,.histogram={[2]=9998,[17]=2}};
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK && packet[17]==2);
    s.histogram[2]--;s.histogram[17]++;s.average_maxrgb=32.072;
    assert(cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));
    assert(cb1_hdr10plus_vsif(packet,&out,false,true)==CB1_HDR10PLUS_OK && packet[17]==17);
    av_free(source);av_free(m);
    puts("DV to HDR10+: linear statistics, L1/L3 ownership and trim coverage passed");
}
