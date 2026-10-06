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

int main(void)
{
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
    puts("PASS creative anchors, immutable edits, compatibility selection, invalid padding");
}
