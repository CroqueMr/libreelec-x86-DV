/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_hdr10_expert.h"
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "hdr10_expert_fixture.h"

static void player_led_plan(void)
{
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={1000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    size_t bytes;AVDOVIMetadata *m=expert_fixture(&bytes,false);
    av_dovi_get_ext(m,1)->l2.trim_slope=3072;
    *av_dovi_get_ext(m,2)=player_led_l3();
    *av_dovi_get_ext(m,3)=player_led_l8(3072,2048);
    m->num_ext_blocks=4;
    struct cb1_hdr10_expert_plan p;
    struct dvbridge_cm4_coefficients cm4;
    assert(cb1_player_led_prepare(&p,&cm4,&policy,m,bytes,false));
    assert(p.creative.analysis[1]==3015 && p.creative.analysis[2]==1564);
    assert(p.creative.applied_levels&(1u<<3));
    assert(fabs(p.tone.input_avg-1564.f/4095)<1e-7);
    assert(p.creative.backend==DVBRIDGE_CREATIVE_CM4 && cm4.sop[0]==1.25);
    assert(!p.tone_shape[0] && !p.creative.l2_coverage.applied);
    assert(p.creative.l8_coverage.applied==0xdf && p.creative.l8_coverage.preserved==0x320);
    av_dovi_get_ext(m,3)->l8.target_display_index=av_dovi_get_ext(m,3)->dvbridge_original_bytes[0]=48;
    assert(cb1_player_led_prepare(&p,&cm4,&policy,m,bytes,false));
    assert(p.creative.backend==DVBRIDGE_CREATIVE_CM29_COMPATIBILITY && p.tone_shape[0]==.5);
    assert(!p.creative.l8_coverage.applied && !cm4.peak_nits);
    struct dvbridge_policy edid={.mode=DVBRIDGE_MODE_PLAYER_LED,
        .tv={2484,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020},
        .expert_black_nits=.8,.lldv_edid_version=1,
        .lldv_primaries={.68,.31,.246,.703,.15,.052}};
    assert(cb1_player_led_prepare(&p,&cm4,&edid,m,bytes,false));
    assert(fabs(p.target.hdr.prim.green.x-.246)<1e-6 && cm4.sop[0]==1.25);
    assert(p.creative.l8_coverage.applied && p.creative.cm4_output.primaries.red.x==
        pl_raw_primaries_get(PL_COLOR_PRIM_DISPLAY_P3)->red.x);
    assert(p.tone.output_min==pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,.8));
    *av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=3,.l3={2064,2048,2048},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
        .dvbridge_original_bytes={0x81,0x08,0x00,0x80,0x00}};
    assert(cb1_player_led_prepare(&p,&cm4,&policy,m,bytes,false));
    assert(p.creative.analysis[0]==32 && !(p.creative.applied_levels&(1u<<3)));
    av_dovi_get_ext(m,2)->l3.min_pq_offset=2032;
    av_dovi_get_ext(m,2)->dvbridge_original_bytes[0]=0x7f;
    assert(cb1_player_led_prepare(&p,&cm4,&policy,m,bytes,false));
    assert(p.creative.analysis[0]==0 && p.creative.analysis[1]==3079 && p.creative.l1_present);
    assert(!(p.creative.applied_levels&(1u<<3)));
    av_dovi_get_ext(m,2)->level=0;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,0,0}};
    assert(cb1_player_led_prepare(&p,&cm4,&policy,m,bytes,false));
    assert(p.creative.l1_present && p.tone.function==&pl_tone_map_clip);
    av_free(m);
}

int main(void)
{
    player_led_plan();
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={600,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020},.expert_black_nits=.005};
    for(unsigned residual=0;residual<2;residual++){
        size_t bytes;AVDOVIMetadata *m=expert_fixture(&bytes,residual);
        void *saved=av_memdup(m,bytes);assert(saved);
        struct cb1_hdr10_expert_plan p;
        assert(cb1_hdr10_expert_prepare(&p,&policy,m,bytes,residual));
        assert(p.source.repr.dovi==&p.source.dovi);
        assert(p.tone.input_scaling==PL_HDR_PQ && p.tone.output_scaling==PL_HDR_PQ);
        assert(p.tone.function==&pl_tone_map_st2094_10 && p.tone.lut_size==1024);
        assert(fabs(pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,p.tone.output_min)-.005)<1e-6);
        assert(p.target.hdr.min_luma==PL_COLOR_HDR_BLACK);
        assert(p.signal.max_luminance==600 && p.signal.min_luminance==50);
        assert(!p.signal.max_cll && !p.signal.max_fall && !p.signal.level6);
        assert(p.source.color.hdr.max_pq_y==0 && p.source.color.hdr.avg_pq_y==0);
        assert(p.creative.analysis[1]==3079 && !(p.creative.applied_levels&(1u<<3)));
        assert(!memcmp(m,saved,bytes));
        if(residual){
            struct cb1_hdr10_expert_plan before=p;
            assert(!cb1_hdr10_expert_prepare(&p,&policy,m,bytes,false));
            assert(!memcmp(&p,&before,sizeof(p)));
        }
        const double invalid[]={49.9,10000.1,NAN,INFINITY};
        for(unsigned i=0;i<4;i++){
            policy.tv.peak_nits=invalid[i];
            assert(!cb1_hdr10_expert_prepare(&p,&policy,m,bytes,residual));
        }
        policy.tv.peak_nits=600;
        av_dovi_get_ext(m,0)->level=0;
        memcpy(saved,m,bytes);
        assert(cb1_hdr10_expert_prepare(&p,&policy,m,bytes,residual));
        assert(!p.creative.l1_present && p.tone.input_avg==0);
        assert(!memcmp(m,saved,bytes));
        *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,0,0}};
        assert(cb1_hdr10_expert_prepare(&p,&policy,m,bytes,residual));
        assert(p.creative.l1_present && p.creative.reason!=DVBRIDGE_CREATIVE_STATIC_UNUSABLE_L1);
        assert(p.tone.function==&pl_tone_map_clip && p.tone.input_avg==0);
        *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,3079,1500}};
        av_free(saved);av_free(m);
    }
    puts("PASS Expert plan, native curve, derived HDR10 and required FEL pairing");
}
