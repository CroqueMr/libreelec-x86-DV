/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "task3_fixture.h"
#include "dvbridge_core.h"
#include "dvbridge_metadata.h"
#if __has_include("cb1_master_ipt.h")
#include "cb1_master_ipt.h"
#endif

int main(void)
{
#ifndef CB1_MASTER_IPT_API
    assert(!"Master IPT colour transform and output metadata API missing");
#else
    size_t bytes; AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    h->vdr_bit_depth=12; c->signal_bit_depth=12; c->signal_full_range_flag=1;
    for(int i=0;i<9;i++) {
        c->ycc_to_rgb_matrix[i]=(AVRational){dvbridge_output_ycc[i],8192};
        c->rgb_to_lms_matrix[i]=(AVRational){dvbridge_output_lms[i],16384};
    }
    for(int i=0;i<3;i++) c->ycc_to_rgb_offset[i]=(AVRational){1,i?2:16};
    m->num_ext_blocks=1; AVDOVIDmData *l1=av_dovi_get_ext(m,0);
    *l1=(AVDOVIDmData){.level=1,.l1={.min_pq=0,.max_pq=3079,.avg_pq=1200}};
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2100,.trim_power=2000,.trim_chroma_weight=2048,.trim_saturation_gain=2048}};
    struct dvbridge_dv original={.source_transport=true},converted={.ipt_transport=true};
    unsigned margins[4]={0};
    assert(dvbridge_dv_metadata(&original,m,0,margins) && dvbridge_dv_metadata(&converted,m,0,margins));
    assert(original.size==converted.size && !memcmp(original.payload+64,converted.payload+64,original.size-64));
    void *saved=av_memdup(m,bytes); assert(saved);
    struct cb1_master_ipt plan;
    assert(cb1_master_ipt_prepare(&plan,m,bytes));
    /* Legal black remains neutral and uses the 4096 code scale. */
    double black[3]={256.0/4096,.5,.5},out[3];
    cb1_master_ipt_convert(&plan,black,out);
    assert(fabs(out[0])<1e-5 && fabs(out[1]-.5)<1e-6 && fabs(out[2]-.5)<1e-6);
    struct dvbridge_context *ctx=dvbridge_create();
    struct dvbridge_geometry g={3840,2160,0,0,3840,2160};
    struct dvbridge_candidate *p=dvbridge_prepare_ipt_output(ctx,m,bytes,0,g,false,false);
    assert(p); unsigned count; const uint32_t *wire=dvbridge_packets(p,&count);
    uint8_t packet[128]; for(int j=0;j<128;j++)packet[j]=wire[j];
    assert(dvbridge_dv_crc(packet,128)==0);
    const uint8_t *dm=packet+5;
    for(int i=0;i<9;i++) {
        assert((int16_t)((dm[2+2*i]<<8)|dm[3+2*i])==cb1_ipt_output_ycc[i]);
        assert((int16_t)((dm[32+2*i]<<8)|dm[33+2*i])==cb1_ipt_output_lms[i]);
    }
    assert(dm[20]==0 && dm[21]==0 && dm[22]==0 && dm[23]==0);
    assert(dm[24]==8 && dm[28]==8); /* 0.5 in Q28. */
    assert(dm[60]==12 && dm[61]==2 && dm[62]==1 && dm[63]==1);
    assert(dvbridge_commit(ctx,p)); dvbridge_candidate_destroy(p);
    /* Switching back cannot retain the IPT declaration. */
    p=dvbridge_prepare_source_output(ctx,m,bytes,1.0/24,g,false,false); assert(p);
    wire=dvbridge_packets(p,&count);
    assert(wire[5+61]==0 && wire[5+20]==1);
    assert(!memcmp(saved,m,bytes));
    dvbridge_candidate_destroy(p); dvbridge_destroy(ctx); av_free(saved); av_free(m);
    puts("PASS Master IPT colour contract, packet CRC, metadata and return to Master");
#endif
}
