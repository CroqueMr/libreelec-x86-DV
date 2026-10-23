/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "task3_fixture.h"
#include "cb1_master_reference.h"
#include "dvbridge_core.h"
#include "dvbridge_metadata.h"
#include <assert.h>

static AVDOVIMetadata *profile5(size_t *bytes)
{
    AVDOVIMetadata *m=task3_fixture(bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->rpu_type=2;h->rpu_format=18;h->vdr_rpu_profile=0;
    h->bl_video_full_range_flag=1;h->vdr_bit_depth=12;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    c->signal_color_space=2;c->signal_bit_depth=12;c->signal_full_range_flag=1;c->source_diagonal=42;
    c->ycc_to_rgb_offset[0]=(AVRational){0,1};
    c->ycc_to_rgb_offset[1]=c->ycc_to_rgb_offset[2]=(AVRational){1,2};
    const int ycc[9]={8192,799,1681,8192,-933,1091,8192,267,-5545};
    for(int i=0;i<9;i++){
        c->ycc_to_rgb_matrix[i]=(AVRational){ycc[i],8192};
        c->rgb_to_lms_matrix[i]=(AVRational){i%4==0?17081:-349,16384};
    }
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.min_pq=12,.max_pq=3079,.avg_pq=1200}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2100,.trim_power=2000,.trim_chroma_weight=2048,.trim_saturation_gain=2048}};
    return m;
}

static void metadata(void)
{
    size_t bytes;AVDOVIMetadata *m=profile5(&bytes);
    void *saved=av_memdup(m,bytes);assert(saved);
    struct dvbridge_context *ctx=dvbridge_create();assert(ctx);
    struct dvbridge_geometry g={3840,2160,0,0,3840,2160};
    assert(!dvbridge_prepare_source_output(ctx,m,bytes,0,g,false,false));
    struct dvbridge_candidate *p=dvbridge_prepare_master_source_output(ctx,m,bytes,0,g,false,false);
    assert(p);unsigned count;const uint32_t *wire=dvbridge_packets(p,&count);assert(count==1);
    uint8_t packet[128];for(int i=0;i<128;i++)packet[i]=wire[i];
    assert(dvbridge_dv_crc(packet,128)==0);
    const uint8_t *dm=packet+5;
    const AVDOVIColorMetadata *c=av_dovi_get_color(m);
    for(int i=0;i<9;i++){
        assert((int16_t)((dm[2+i*2]<<8)|dm[3+i*2])==(int64_t)c->ycc_to_rgb_matrix[i].num*8192/c->ycc_to_rgb_matrix[i].den);
        assert((int16_t)((dm[32+i*2]<<8)|dm[33+i*2])==(int64_t)c->rgb_to_lms_matrix[i].num*16384/c->rgb_to_lms_matrix[i].den);
    }
    assert(!dm[20] && !dm[21] && !dm[22] && !dm[23]);
    assert(dm[24]==8 && dm[28]==8 && dm[60]==12 && dm[61]==2 && dm[62]==1 && dm[63]==1);
    struct dvbridge_dv direct={.source_transport=true,.profile5_transport=true},control={0};
    unsigned margins[4]={0};
    assert(dvbridge_dv_metadata_output(&direct,m,0,margins,false));
    assert(dvbridge_dv_metadata_output(&control,m,0,margins,false));
    assert(direct.size==control.size && !memcmp(direct.payload+64,control.payload+64,direct.size-64));
    assert(!memcmp(saved,m,bytes));
    assert(dvbridge_commit(ctx,p));dvbridge_candidate_destroy(p);
    /* No retained IPT state after changing sources. */
    av_dovi_get_header(m)->vdr_rpu_profile=1;
    av_dovi_get_color(m)->signal_color_space=0;
    av_dovi_get_color(m)->ycc_to_rgb_offset[0]=(AVRational){1,16};
    p=dvbridge_prepare_source_output(ctx,m,bytes,1.0/25,g,false,false);assert(p);
    wire=dvbridge_packets(p,&count);assert(wire[5+61]==0 && wire[5+20]==1);
    dvbridge_candidate_destroy(p);dvbridge_destroy(ctx);av_free(saved);av_free(m);
}

int main(void)
{
    size_t bytes;AVDOVIMetadata *m=profile5(&bytes);
    struct pl_cb1_dovi_reference raw;
    assert(cb1_master_reference_map(&raw,m,bytes,false)==CB1_MASTER_READY);
    assert(cb1_master_reference_transport(m,bytes));
    /* The generic source shortcut must not acquire a new input contract. */
    assert(!dvbridge_dv_source_transport(m));
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->vdr_rpu_profile=1;
    assert(cb1_master_reference_map(&raw,m,bytes,false)==CB1_MASTER_UNSUPPORTED);
    assert(!cb1_master_reference_transport(m,bytes));
    h->vdr_rpu_profile=0;h->disable_residual_flag=0;
    assert(cb1_master_reference_map(&raw,m,bytes,false)==CB1_MASTER_UNSUPPORTED);
    h->disable_residual_flag=1;
    av_dovi_get_color(m)->ycc_to_rgb_offset[0]=(AVRational){1,16};
    assert(!cb1_master_reference_transport(m,bytes));
    av_free(m);
    metadata();
    return 0;
}
