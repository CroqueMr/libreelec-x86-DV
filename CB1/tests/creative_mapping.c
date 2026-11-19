/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "task3_fixture.h"
#include "dvbridge_creative.h"
#include "dvbridge_metadata.h"

static AVDOVIMetadata *fixture(size_t *bytes)
{
    AVDOVIMetadata *m=task3_fixture(bytes);m->num_ext_blocks=3;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);c->source_max_pq=3500;
    AVDOVIDmData *e=av_dovi_get_ext(m,0);e->level=1;
    e->l1.min_pq=200;e->l1.max_pq=3200;e->l1.avg_pq=1600;
    for(int i=1;i<3;i++){
        e=av_dovi_get_ext(m,i);e->level=2;e->l2.target_max_pq=2000+i*500;
        e->l2.trim_slope=e->l2.trim_offset=e->l2.trim_power=2048;
        e->l2.trim_chroma_weight=e->l2.trim_saturation_gain=2048;e->l2.ms_weight=-1;
    }
    av_dovi_get_ext(m,1)->l2.trim_power=2200;
    return m;
}

/* Remote MS commands must not change the selected Expert plan or its pixels. */
static void selected_l2_detail(void)
{
    size_t bytes;AVDOVIMetadata *m=fixture(&bytes);m->num_ext_blocks=4;
    *av_dovi_get_ext(m,3)=*av_dovi_get_ext(m,1);
    av_dovi_get_ext(m,3)->l2.target_max_pq=2000;
    av_dovi_get_ext(m,3)->l2.ms_weight=4095;
    struct dvbridge_policy policy={.revision=4,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={.peak_nits=300,.panel=DVBRIDGE_PANEL_OLED,.gamut=DVBRIDGE_GAMUT_P3_D65}};
    struct dvbridge_creative_plan p;
    void *before=av_memdup(m,bytes);assert(before);
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.reason==DVBRIDGE_CREATIVE_OK && "unselected L2 MS must not warn");
    assert(p.l2_coverage.present==63 && p.l2_coverage.applied==31 && p.l2_coverage.preserved==32);
#ifdef DVBRIDGE_L2_DETAIL_API
    assert(p.l2_detail.level==2 && p.l2_detail.state==DVBRIDGE_DETAIL_SENTINEL);
    assert(p.l2_detail.num_anchors==2 && p.l2_detail.target_pq[0]==2500 && p.l2_detail.target_pq[1]==3000);
    assert(p.l2_detail.codes[0]==-1 && p.l2_detail.codes[1]==-1 && !p.l2_detail.executed);
    double original[5];memcpy(original,p.codes,sizeof(original));
    const int values[]={-2,-1,0,2048,4095,4096};
    for(unsigned i=0;i<sizeof(values)/sizeof(values[0]);i++){
        av_dovi_get_ext(m,1)->l2.ms_weight=values[i];
        enum dvbridge_creative_status status=dvbridge_creative_resolve(&p,m,bytes,&policy);
        if(values[i]<-1 || values[i]>4095){assert(status==DVBRIDGE_CREATIVE_INVALID);continue;}
        assert(status==DVBRIDGE_CREATIVE_READY && !memcmp(original,p.codes,sizeof(original)));
        assert(p.l2_detail.codes[0]==values[i] && p.l2_detail.codes[1]==-1);
        assert(p.l2_detail.state==(values[i]==-1?DVBRIDGE_DETAIL_SENTINEL:DVBRIDGE_DETAIL_UNRESOLVED));
        assert(!p.l2_detail.executed && p.l2_coverage.preserved==32 && p.l2_coverage.applied==31);
    }
    av_dovi_get_ext(m,1)->l2.ms_weight=0;av_dovi_get_ext(m,2)->l2.ms_weight=4095;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.l2_detail.state==DVBRIDGE_DETAIL_NUMERIC && p.l2_detail.upper_weight>0 && p.l2_detail.upper_weight<1);
    assert(fabs(p.l2_detail.code-4095*(p.target_pq-2500)/500)<1e-9);
    assert(p.reason==DVBRIDGE_CREATIVE_SPATIAL_UNQUALIFIED && !p.l2_detail.executed);
    /* Reordering metadata cannot change the selected descriptor. */
    struct dvbridge_l2_detail selected=p.l2_detail;
    AVDOVIDmData swap=*av_dovi_get_ext(m,1);*av_dovi_get_ext(m,1)=*av_dovi_get_ext(m,3);*av_dovi_get_ext(m,3)=swap;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(selected.state==p.l2_detail.state && selected.level==p.l2_detail.level &&
        selected.num_anchors==p.l2_detail.num_anchors && selected.upper_weight==p.l2_detail.upper_weight &&
        selected.code==p.l2_detail.code && selected.executed==p.l2_detail.executed &&
        !memcmp(selected.codes,p.l2_detail.codes,sizeof(selected.codes)) &&
        !memcmp(selected.target_pq,p.l2_detail.target_pq,sizeof(selected.target_pq)));
    memcpy(m,before,bytes);
    /* 10000 nits is exactly PQ 4095: the opposite sentinel has zero influence. */
    av_dovi_get_color(m)->source_max_pq=4095;policy.tv.peak_nits=10000;
    av_dovi_get_ext(m,2)->l2.target_max_pq=4095;av_dovi_get_ext(m,2)->l2.ms_weight=0;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.l2_detail.state==DVBRIDGE_DETAIL_NUMERIC && p.l2_detail.num_anchors==1 && p.l2_detail.code==0);
    assert(p.l2_detail.codes[0]==0 && p.l2_detail.target_pq[0]==4095 && !p.l2_detail.executed);
    /* A single-sided numeric command is preserved, never extrapolated to a master. */
    policy.tv.peak_nits=1000;av_dovi_get_ext(m,2)->l2.target_max_pq=3000;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.l2_detail.state==DVBRIDGE_DETAIL_UNRESOLVED && p.l2_detail.num_anchors==1);
    assert(p.l2_detail.target_pq[0]==3000 && p.l2_detail.codes[0]==0 && !p.l2_detail.executed);
    policy.tv.peak_nits=10000;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.l2_detail.state==DVBRIDGE_DETAIL_UNRESOLVED && p.l2_detail.num_anchors==1);
    policy.tv.peak_nits=50;av_dovi_get_ext(m,3)->l2.ms_weight=2048;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.l2_detail.state==DVBRIDGE_DETAIL_UNRESOLVED && p.l2_detail.target_pq[0]==2000);
    m->num_ext_blocks=2;av_dovi_get_ext(m,1)->l2.ms_weight=2048;policy.tv.peak_nits=300;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.l2_detail.state==DVBRIDGE_DETAIL_UNRESOLVED && p.l2_detail.num_anchors==1 &&
        p.l2_detail.codes[0]==2048 && p.l2_detail.target_pq[0]==2500 && !p.l2_detail.executed);
    /* The historical Enhanced report and reason stay untouched. */
    policy.mode=DVBRIDGE_MODE_ENHANCED_DV;policy.tv.peak_nits=300;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.l2_detail.state==DVBRIDGE_DETAIL_ABSENT && p.l2_detail.level==0);
    assert(p.l2_coverage.present==31 && p.l2_coverage.applied==31 && !p.l2_coverage.preserved);
    assert(p.reason==DVBRIDGE_CREATIVE_SPATIAL_UNQUALIFIED);
    memcpy(m,before,bytes);m->num_ext_blocks=1;policy.mode=DVBRIDGE_MODE_HDR10_EXPERT;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_NEUTRAL);
    assert(p.l2_detail.state==DVBRIDGE_DETAIL_ABSENT && !p.l2_detail.num_anchors && !p.l2_coverage.present);
#else
    assert(!"selected L2 detail descriptor is not implemented");
#endif
    memcpy(m,before,bytes);
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(!memcmp(before,m,bytes));av_free(before);av_free(m);
}

int main(void)
{
    selected_l2_detail();
    size_t bytes;AVDOVIMetadata *m=fixture(&bytes);
    struct dvbridge_policy policy={.revision=4,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={.peak_nits=300,.panel=DVBRIDGE_PANEL_OLED,.gamut=DVBRIDGE_GAMUT_P3_D65}};
    struct dvbridge_creative_plan p;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.backend==DVBRIDGE_CREATIVE_CM29 && p.analysis[0]==200 && p.analysis[1]==3200);
    assert(p.codes[2]>2048 && p.codes[2]<2200);
    double rgb[3]={20,40,80},out[3];
    assert(dvbridge_creative_trim_rgb(&p,rgb,out));
    assert(out[0]<rgb[0] && out[1]<rgb[1] && out[2]<rgb[2]);
    void *before=av_memdup(m,bytes),*edited=NULL;size_t output_bytes=0;assert(before);
    policy.mode=DVBRIDGE_MODE_ENHANCED_DV;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    struct dvbridge_creative_edit_report report;
    enum dvbridge_creative_status status=dvbridge_creative_edit(&edited,&output_bytes,m,bytes,&p,&report);
    assert(status!=DVBRIDGE_CREATIVE_INVALID);
    assert(edited!=m && output_bytes==bytes && !memcmp(m,before,bytes));
    assert(status!=DVBRIDGE_CREATIVE_UNSUPPORTED || !memcmp(m,edited,bytes));
    assert(status!=DVBRIDGE_CREATIVE_READY || report.maximum_pq_error<=2.0/1024);
    assert(!memcmp(av_dovi_get_color(m),av_dovi_get_color(edited),sizeof(AVDOVIColorMetadata)));
    av_free(edited);edited=NULL;
    av_dovi_get_ext(m,2)->l2.target_max_pq=2500;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    assert(dvbridge_creative_edit(&edited,&output_bytes,m,bytes,&p,NULL)==DVBRIDGE_CREATIVE_INVALID && !edited);
    av_dovi_get_ext(m,2)->l2.target_max_pq=3000;
    m->num_ext_blocks=4;AVDOVIDmData *l8=av_dovi_get_ext(m,3);l8->level=8;
    l8->dvbridge_raw_magic=0x41424456;l8->dvbridge_original_length=10;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(p.reason==DVBRIDGE_CREATIVE_CM4_EDIT_UNQUALIFIED);
    assert(dvbridge_creative_edit(&edited,&output_bytes,m,bytes,&p,NULL)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(!memcmp(m,edited,bytes));av_free(edited);
    policy.mode=DVBRIDGE_MODE_HDR10_EXPERT;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    assert(p.backend==DVBRIDGE_CREATIVE_CM29_COMPATIBILITY && p.preserved_levels&(1u<<8));
    l8->dvbridge_original_length=12;l8->dvbridge_original_bytes[11]=1;
    assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_INVALID);
    const unsigned lengths[]={10,12,13,19,25};
    policy.mode=DVBRIDGE_MODE_ENHANCED_DV;
    for(unsigned i=0;i<5;i++){
        memset(l8->dvbridge_original_bytes,0,32);l8->dvbridge_original_length=lengths[i];
        assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_UNSUPPORTED);
        assert(dvbridge_creative_edit(&edited,&output_bytes,m,bytes,&p,NULL)==DVBRIDGE_CREATIVE_UNSUPPORTED);
        assert(!memcmp(edited,m,bytes));av_free(edited);
    }
    m->num_ext_blocks=3;assert(dvbridge_creative_resolve(&p,m,bytes,&policy)==DVBRIDGE_CREATIVE_READY);
    av_dovi_get_ext(m,1)->l2.trim_power++;
    assert(dvbridge_creative_edit(&edited,&output_bytes,m,bytes,&p,NULL)==DVBRIDGE_CREATIVE_INVALID && !edited);
    av_free(before);av_free(m);
    puts("PASS selected L2 detail, creative anchors, immutable edits, compatibility selection, invalid padding");
}
