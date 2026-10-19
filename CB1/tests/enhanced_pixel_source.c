/* SPDX-License-Identifier: GPL-3.0-only */
#include "cb1_dv_enhanced.h"
#include "task3_fixture.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static AVDOVIDmData trim(unsigned length,unsigned index)
{
    return (AVDOVIDmData){.level=8,.l8={.target_display_index=index,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=2048},.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=length,
        .dvbridge_original_bytes={index,0x80,0x08,0x00,0x80,0x08,0x00,0x80,0x08,0x00}};
}
int main(void)
{
    assert(dvbridge_creative_enhanced_source && "Validated Enhanced source resolver required");
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    struct dvbridge_policy p={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    av_dovi_get_color(m)->source_max_pq=3079;
    m->num_ext_blocks=4;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3000,.avg_pq=1500,.min_pq=0}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=3,.l3={2048,2080,2048},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
        .dvbridge_original_bytes={0x80,0x08,0x20,0x80,0}};
    *av_dovi_get_ext(m,2)=trim(10,28);*av_dovi_get_ext(m,3)=trim(10,250);
    struct cb1_dv_enhanced_source source;
    const unsigned lengths[]={10,12,13,19,25},fields[]={1,3,7,15,31};
    for(unsigned i=0;i<5;i++){
        *av_dovi_get_ext(m,2)=trim(lengths[i],28);
        void *before=av_memdup(m,bytes);
        struct dvbridge_creative_plan expert_before,expert_after;
        struct dvbridge_policy expert=p;expert.mode=DVBRIDGE_MODE_HDR10_EXPERT;
        dvbridge_creative_resolve(&expert_before,m,bytes,&expert);
        assert(dvbridge_creative_enhanced_source(&source,m,bytes,&p));
        assert(source.count==1 && source.family==8 && source.analysis[1]==3064);
        assert(source.anchors[0].controls.present_fields==fields[i]);
        dvbridge_creative_resolve(&expert_after,m,bytes,&expert);
        assert(!memcmp(before,m,bytes) && !memcmp(&expert_before,&expert_after,sizeof(expert_before)));
        av_free(before);
    }
    av_dovi_get_ext(m,2)->l8.trim_power++;
    assert(!dvbridge_creative_enhanced_source(&source,m,bytes,&p));
    *av_dovi_get_ext(m,2)=trim(10,27); /* Known P3 target cannot masquerade as BT.2020. */
    assert(dvbridge_creative_enhanced_source(&source,m,bytes,&p) && source.count==0);
    struct cb1_dv_enhanced_source guided;
    assert(dvbridge_creative_enhanced_source_b(&guided,m,bytes,&p) && guided.count==1 && guided.family==8);
    assert(guided.analysis[1]==3064 && "L3 is applied once in B too");
    p.tv.gamut=DVBRIDGE_GAMUT_P3_D65;
    assert(dvbridge_creative_enhanced_source(&source,m,bytes,&p) && source.count==1);
    *av_dovi_get_ext(m,2)=trim(10,20);
    *av_dovi_get_ext(m,3)=(AVDOVIDmData){.level=10,.l10={.target_display_index=20,
        .target_max_pq=3079,.target_min_pq=0,.target_primary_index=0},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
        .dvbridge_original_bytes={20,0xc0,0x70,0,0}};
    assert(dvbridge_creative_enhanced_source(&source,m,bytes,&p) && source.count==1);
    assert(source.anchors[0].target.origin==DVBRIDGE_CM4_CUSTOM);
    p.tv.gamut=DVBRIDGE_GAMUT_BT2020;m->num_ext_blocks=2;
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2851,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    assert(dvbridge_creative_enhanced_source(&source,m,bytes,&p) && source.count==1 && source.family==2);
    struct cb1_dv_enhanced_source l2=source;
    const enum dvbridge_gamut gamuts[]={DVBRIDGE_GAMUT_P3_D65,DVBRIDGE_GAMUT_BT709};
    for(unsigned i=0;i<2;i++){
        p.tv.gamut=gamuts[i];
        struct dvbridge_policy expert=p;expert.mode=DVBRIDGE_MODE_HDR10_EXPERT;
        struct dvbridge_creative_plan before,after;
        dvbridge_creative_resolve(&before,m,bytes,&expert);
        assert(dvbridge_creative_enhanced_source(&source,m,bytes,&p));
        assert(source.count==1 && source.family==2);
        assert(!memcmp(&source,&l2,sizeof(source)));
        dvbridge_creative_resolve(&after,m,bytes,&expert);
        assert(!memcmp(&before,&after,sizeof(before)));
    }
    av_free(m);puts("PASS validated L3 once, optional lengths, L2, unknown extras, P3/L10, Expert isolation");
}
