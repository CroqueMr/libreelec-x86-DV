/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_core.h"
#include <assert.h>
#include <limits.h>
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <stdio.h>
#include <string.h>

static void assert_same_next(struct dvbridge_context *context, struct dvbridge_context *reference,
                             AVDOVIMetadata *m, size_t size, struct dvbridge_geometry geometry)
{
    struct dvbridge_candidate *a = dvbridge_prepare(context, m, size, 2., geometry, false);
    struct dvbridge_candidate *b = dvbridge_prepare(reference, m, size, 2., geometry, false);
    assert(a && b);
    unsigned ac, bc;
    const uint32_t *ap = dvbridge_packets(a, &ac), *bp = dvbridge_packets(b, &bc);
    assert(ac == bc && !memcmp(ap, bp, ac * 128 * sizeof(*ap)));
    dvbridge_candidate_destroy(a); dvbridge_candidate_destroy(b);
}

int main(void)
{
    struct dvbridge_context *context = dvbridge_create(), *other = dvbridge_create();
    assert(context && other);
    size_t size;
    AVDOVIMetadata *m = av_dovi_metadata_alloc(&size);
    assert(m);
    av_dovi_get_header(m)->disable_residual_flag = 1;
    av_dovi_get_color(m)->signal_eotf = 65535;
    av_dovi_get_color(m)->source_max_pq = 3000;
    m->num_ext_blocks = 1;
    av_dovi_get_ext(m, 0)->level = 1;
    av_dovi_get_ext(m, 0)->l1.max_pq = 3000;
    av_dovi_get_ext(m, 0)->l1.avg_pq = 1000;
    struct dvbridge_geometry geometry = {3840, 2160, 0, 0, 3840, 2160};
    struct dvbridge_candidate *first = dvbridge_prepare(context, m, size, 1., geometry, false);
    struct dvbridge_candidate *pending = dvbridge_prepare(context, m, size, 2., geometry, false);
    assert(first && pending);
    unsigned count;
    assert(dvbridge_packets(first, &count) && count > 0);
    assert(!dvbridge_commit(other, first));
    assert_same_next(context, other, m, size, geometry);
    struct dvbridge_candidate *other_first = dvbridge_prepare(other, m, size, 1., geometry, false);
    assert(other_first && dvbridge_commit(other, other_first));
    dvbridge_candidate_destroy(other_first);
    assert(dvbridge_commit(context, first));
    assert(!dvbridge_commit(context, first));
    assert(!dvbridge_commit(context, pending));
    assert_same_next(context, other, m, size, geometry);
    dvbridge_candidate_destroy(first);
    dvbridge_candidate_destroy(pending);

    pending = dvbridge_prepare(context, m, size, 2., geometry, false);
    assert(pending);
    uint32_t reference[512];
    memcpy(reference, dvbridge_packets(pending, NULL), sizeof(reference));
    av_dovi_get_ext(m, 0)->l1.avg_pq = 4000;
    assert(!dvbridge_prepare(context, m, size, 3., geometry, false));
    assert(memcmp(reference, dvbridge_packets(pending, NULL), sizeof(reference)) == 0);
    assert(dvbridge_commit(context, pending));
    dvbridge_candidate_destroy(pending);
    av_dovi_get_ext(m, 0)->l1.avg_pq = 1000;

    pending = dvbridge_prepare(context, m, size, 4., geometry, false);
    assert(pending);
    dvbridge_reset(context);
    assert(!dvbridge_commit(context, pending));
    dvbridge_reset(other);
    assert_same_next(context, other, m, size, geometry);
    dvbridge_candidate_destroy(pending);
    assert(!dvbridge_prepare(context, (const char *)m + 1, size - 1, 0., geometry, false));
    geometry.x = INT_MAX;
    assert(!dvbridge_prepare(context, m, size, 0., geometry, false));
    geometry.x = 0;
    geometry.width = INT_MAX;
    assert(!dvbridge_prepare(context, m, size, 0., geometry, false));
    geometry.width = 3840;
    for (size_t truncated = 0; truncated < sizeof(*m); ++truncated)
        assert(!dvbridge_prepare(context, m, truncated, 0., geometry, false));
    av_free(m);
    dvbridge_destroy(context);
    dvbridge_destroy(other);
    puts("PASS: no advance on prepare/failure, no stale/cross-context/double commit, seek invalidation");
}
