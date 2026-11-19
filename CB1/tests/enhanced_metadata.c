/* SPDX-License-Identifier: MIT */
#include "task3_fixture.h"
#include "dvbridge_core.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct dvbridge_candidate *prepare(struct dvbridge_context *c,
    const void *m,size_t bytes,double pts,bool force)
{
#ifdef DVBRIDGE_OUTPUT_METADATA_API
    return dvbridge_prepare_output(c,m,bytes,pts,
        (struct dvbridge_geometry){3840,2160,0,0,3840,2160},false,force);
#else
    (void)force;
    return dvbridge_prepare(c,m,bytes,pts,
        (struct dvbridge_geometry){3840,2160,0,0,3840,2160},false);
#endif
}

static void packet_matches(const struct dvbridge_candidate *candidate,const char *hex)
{
    unsigned count;const uint32_t *p=dvbridge_packets(candidate,&count);
    assert(p && count==1 && strlen(hex)==256);
    for(unsigned i=0;i<128;i++) {
        unsigned value;assert(sscanf(hex+2*i,"%2x",&value)==1);
        assert(p[i]==value);
    }
}

int main(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    av_dovi_get_color(m)->source_max_pq=3261;
    m->num_ext_blocks=1;AVDOVIDmData *l1=av_dovi_get_ext(m,0);
    l1->level=1;l1->l1.min_pq=2254;l1->l1.max_pq=3044;l1->l1.avg_pq=2730;
    void *original=malloc(bytes);assert(original);memcpy(original,m,bytes);
    struct dvbridge_context *c=dvbridge_create();assert(c);
    struct dvbridge_candidate *a=prepare(c,m,bytes,0,true);assert(a);
    /* Frozen Decimal-analysis / polynomial-division packet, Task 6B pair 0. */
    packet_matches(a,"000000005f00012566000035ea2566f9fceb1c256644ca00000100000008000000080000001c36224301860a5e308e0514000001a63e5affff00000000000000000c00010100000cbd002a02000000060108ce0be40aaa00000008050000000000000000000000000000000000000000000000000000000000000000f60f5468");
    assert(!memcmp(original,m,bytes));assert(dvbridge_commit(c,a));dvbridge_candidate_destroy(a);
    a=prepare(c,m,bytes,.04,false);assert(a);unsigned count;
    const uint32_t *p=dvbridge_packets(a,&count);assert(p[6]==0 && p[1]==17);
    assert(dvbridge_commit(c,a));dvbridge_candidate_destroy(a);
    l1->l1.min_pq=2327;l1->l1.max_pq=3064;l1->l1.avg_pq=2771;
    struct dvbridge_candidate *failed=prepare(c,m,bytes,.04,true);assert(failed);
    p=dvbridge_packets(failed,&count);
    assert(p[6]==1 && p[1]==34); /* Changed revision, equal actual PTS. */
    dvbridge_candidate_destroy(failed);
    a=prepare(c,m,bytes,.04,true);assert(a);p=dvbridge_packets(a,&count);
    assert(p[6]==1 && p[1]==34); /* Failed submission never advances reference. */
    assert(dvbridge_commit(c,a));dvbridge_candidate_destroy(a);
    a=prepare(c,m,bytes,.04,false);assert(a);p=dvbridge_packets(a,&count);
    assert(p[6]==1 && p[1]==34); /* Coherent paused packet is unchanged. */
    dvbridge_candidate_destroy(a);dvbridge_reset(c);
    a=prepare(c,m,bytes,.04,true);assert(a);p=dvbridge_packets(a,&count);
    assert(p[6]==1 && p[1]==0);
    dvbridge_candidate_destroy(a);dvbridge_destroy(c);free(original);av_free(m);
    puts("PASS literal packet and transactional real-PTS force refresh");
}
