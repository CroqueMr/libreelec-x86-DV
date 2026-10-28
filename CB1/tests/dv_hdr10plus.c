/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "task3_fixture.h"
#include "cb1_dv_hdr10plus.h"
#include <stdio.h>
#include <string.h>

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
    AVDynamicHDRPlus old=out;s.histogram[0]++;
    assert(!cb1_dv_hdr10plus_metadata(&out,&r,m,bytes,&s));assert(!memcmp(&out,&old,sizeof(out)));
    av_free(source);av_free(m);
    puts("DV to HDR10+: linear statistics, L1/L3 ownership and trim coverage passed");
}
