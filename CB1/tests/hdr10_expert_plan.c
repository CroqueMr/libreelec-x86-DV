/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_hdr10_expert.h"
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "hdr10_expert_fixture.h"

int main(void)
{
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
