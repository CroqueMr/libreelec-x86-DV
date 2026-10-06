/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_core.h"
#include "dvbridge_metadata.h"
#include "task3_fixture.h"
#include <stdio.h>

int main(void)
{
    size_t bytes; AVDOVIMetadata *m=task3_fixture(&bytes);
    struct dvbridge_context *context=dvbridge_create(); assert(context);
    struct dvbridge_geometry geometry={3840,2160,0,0,3840,2160};
    assert(!dvbridge_dv_bounds(m,bytes));
    assert(!dvbridge_prepare(context,m,bytes,0,geometry,false));
    m->num_ext_blocks=1;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0);
    l1->level=1; l1->l1.max_pq=4095; l1->l1.avg_pq=3079;
    struct dvbridge_candidate *c=dvbridge_prepare(context,m,bytes,0,geometry,false); assert(c);
    uint32_t words[512]; memcpy(words,dvbridge_packets(c,NULL),sizeof(words)); dvbridge_candidate_destroy(c);
    AVDOVIDmData *e=av_dovi_get_ext(m,1); *e=*l1; m->num_ext_blocks=2;
    assert(!dvbridge_prepare(context,m,bytes,0,geometry,false));
    *e=(AVDOVIDmData){0}; e->level=42;
    assert(!dvbridge_prepare(context,m,bytes,0,geometry,false));
    e->level=2; e->l2.target_max_pq=3079;
    *av_dovi_get_ext(m,2)=*e; m->num_ext_blocks=3;
    assert(!dvbridge_prepare(context,m,bytes,0,geometry,false));
    *e=(AVDOVIDmData){0}; e->level=5; e->l5.left_offset=10; e->l5.right_offset=20;
    e->l5.top_offset=30; e->l5.bottom_offset=40; m->num_ext_blocks=2;
    c=dvbridge_prepare(context,m,bytes,0,geometry,false); assert(c);
    unsigned margins[4]; assert(dvbridge_active_area(c,margins));
    assert(margins[0]==10 && margins[1]==20 && margins[2]==30 && margins[3]==40);
    dvbridge_candidate_destroy(c);
    *av_dovi_get_ext(m,2)=*e; m->num_ext_blocks=3;
    assert(!dvbridge_prepare(context,m,bytes,0,geometry,false));
    m->num_ext_blocks=2; *e=(AVDOVIDmData){0}; e->level=8;
    e->dvbridge_raw_magic=0x41424456; e->dvbridge_original_length=12;
    e->dvbridge_original_bytes[11]=1;
    assert(!dvbridge_prepare(context,m,bytes,0,geometry,false));
    *e=(AVDOVIDmData){0}; e->level=8; e->dvbridge_raw_magic=0x41424456;
    e->dvbridge_original_length=25;
    for(int i=1;i<=11;++i) *av_dovi_get_ext(m,i)=*e;
    m->num_ext_blocks=12;
    c=dvbridge_prepare(context,m,bytes,0,geometry,false); assert(c);
    unsigned count; const uint32_t *packets=dvbridge_packets(c,&count);
    assert(count==4 && packets[3]*256+packets[4]==469);
    for(unsigned i=0;i<count;++i) {
        uint8_t packet[128]; for(unsigned j=0;j<128;++j) packet[j]=packets[i*128+j];
        assert(!dvbridge_dv_crc(packet,sizeof(packet)));
    }
    dvbridge_candidate_destroy(c);
    *av_dovi_get_ext(m,12)=*e; m->num_ext_blocks=13;
    assert(!dvbridge_prepare(context,m,bytes,0,geometry,false));
    m->num_ext_blocks=1;
    c=dvbridge_prepare(context,m,bytes,0,geometry,false); assert(c);
    assert(!memcmp(words,dvbridge_packets(c,NULL),sizeof(words)));
    dvbridge_candidate_destroy(c); dvbridge_destroy(context); av_free(m);
    puts("PASS: strict native grammar, common L5 margins, 469-byte four-packet boundary and no advance on rejection");
}
