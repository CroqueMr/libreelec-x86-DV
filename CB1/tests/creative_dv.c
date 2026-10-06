/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"
#include "dvbridge_metadata.h"
#include <time.h>

static void retire(struct dvbridge_renderer *r)
{
    dvbridge_render_dv_policy_cancel(r);
    for(unsigned i=0;i<10000;i++){
        enum dvbridge_dv_policy_status s=dvbridge_render_dv_policy_poll(r);
        if(s==DVBRIDGE_DV_IDLE)return;
        assert(s==DVBRIDGE_DV_BUSY);nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"GPU retirement timed out");
}
int main(void)
{
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner),*standard=dvbridge_renderer_create(gpu);
    assert(r && standard);
    pl_tex input=reference_texture(gpu,2,2,(float[16]){.2,.3,.4,1,.3,.4,.5,1,.4,.5,.6,1,.5,.6,.7,1});
    struct pl_frame f=reference_frame(input,2,2);struct dvbridge_geometry geometry={2,2,0,0,2,2};
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0);l1->level=1;l1->l1.max_pq=3079;l1->l1.avg_pq=1667;
    AVDOVIDmData *l2=av_dovi_get_ext(m,1);*l2=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3000,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=-1}};
    void *before=av_memdup(m,bytes);assert(before);
    assert(dvbridge_render_rgb(standard,&f,m,bytes,0,0,geometry));
    float expected[16],actual[16];reference_read(gpu,dvbridge_render_texture(standard),0,0,2,2,expected);
    struct dvbridge_policy p=reference_policy();p.mode=DVBRIDGE_MODE_ENHANCED_DV;p.tv.peak_nits=800;
    struct dvbridge_identity id={4,8,p.revision};
    enum dvbridge_dv_policy_status status=dvbridge_render_dv_policy_prepare(r,&p,&id,&f,m,bytes,0,0,geometry);
    while(status==DVBRIDGE_DV_PENDING)status=dvbridge_render_dv_policy_poll(r);
    assert(status==DVBRIDGE_DV_READY);
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
    reference_read(gpu,out->intermediate,0,0,2,2,actual);
    assert(!memcmp(actual,expected,sizeof(actual)) && !memcmp(m,before,bytes));
    assert(!memcmp(av_dovi_get_ext(out->output_metadata,0),l1,sizeof(*l1)));
    assert(!memcmp(av_dovi_get_color(out->output_metadata),av_dovi_get_color(m),sizeof(AVDOVIColorMetadata)));
    assert(out->value.creative_edit.status!=DVBRIDGE_CREATIVE_INVALID);
    assert(out->value.creative_edit.status!=DVBRIDGE_CREATIVE_UNSUPPORTED || !memcmp(out->output_metadata,m,bytes));
    assert(!out->value.measured && out->value.sample_count==0);
    unsigned count;const uint32_t *packets=dvbridge_packets(out->candidate,&count);assert(packets && count);
    for(unsigned i=0;i<count;i++){
        uint8_t packet[128];for(unsigned j=0;j<128;j++)packet[j]=packets[i*128+j];
        assert(dvbridge_dv_crc(packet,128)==0);
    }
    struct dvbridge_creative_edit_report first=out->value.creative_edit;
    assert(!first.cache_hit && first.candidate_evaluations>0);
    void *edited_before=av_memdup(out->output_metadata,bytes);assert(edited_before);
    retire(r);id.picture++;
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&f,m,bytes,0,0,geometry)==DVBRIDGE_DV_READY);
    out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.creative_edit.cache_hit && !out->value.creative_edit.fit_ns && !out->value.creative_edit.candidate_evaluations);
    assert(out->value.identity.picture==id.picture && !memcmp(edited_before,out->output_metadata,bytes));
    assert(out->value.creative_edit.maximum_pq_error==first.maximum_pq_error);av_free(edited_before);
    retire(r);l2->l2.trim_power++;
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&f,m,bytes,0,0,geometry)==DVBRIDGE_DV_READY);
    out=dvbridge_render_dv_policy_output(r);assert(out && !out->value.creative_edit.cache_hit);
    retire(r);l2->l2.trim_power--;
    p.revision++;id.revision++;
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&f,m,bytes,0,0,geometry)==DVBRIDGE_DV_READY);
    out=dvbridge_render_dv_policy_output(r);assert(out && !out->value.creative_edit.cache_hit);
    retire(r);p.enhancement=DVBRIDGE_ENHANCEMENT_INTENSE;p.revision++;id.revision++;
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&f,m,bytes,0,0,geometry)==DVBRIDGE_DV_READY);
    out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.creative_edit.status!=DVBRIDGE_CREATIVE_INVALID);retire(r);
    m->num_ext_blocks=3;AVDOVIDmData *cm=av_dovi_get_ext(m,2);
    *cm=(AVDOVIDmData){.level=254,.dvbridge_raw_magic=0x41424456,.dvbridge_original_length=2};
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&f,m,bytes,0,0,geometry)==DVBRIDGE_DV_READY);
    out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.creative_edit.status!=DVBRIDGE_CREATIVE_UNSUPPORTED || !memcmp(out->output_metadata,m,bytes));retire(r);
    /* A repeated key never bypasses raw source validation. */
    *cm=(AVDOVIDmData){.level=3,.l3={2048,2048,2048},.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=5,.dvbridge_original_bytes={0x80,0x08,0x00,0x80,0x00}};
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&f,m,bytes,0,0,geometry)==DVBRIDGE_DV_READY);
    retire(r);cm->l3.max_pq_offset=1;
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&f,m,bytes,0,0,geometry)==DVBRIDGE_DV_FAILED);
    assert(!dvbridge_render_dv_policy_output(r));
    dvbridge_renderer_destroy(r);dvbridge_renderer_destroy(standard);assert(dvbridge_retirement_owner_destroy(&owner));
    pl_tex_destroy(gpu,&input);av_free(m);av_free(before);reference_gpu_destroy(&g);
    puts("PASS metadata-first identical pixels, source facts, exact source copy, packets and zero analysis");
}
