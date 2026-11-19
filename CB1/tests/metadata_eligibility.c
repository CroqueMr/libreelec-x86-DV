/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_core.h"
#include "dvbridge_placebo.h"
#include "task3_fixture.h"
#include <stdio.h>
#include <string.h>

int main(void)
{
    size_t bytes;
    AVDOVIMetadata *m = task3_fixture(&bytes);
    void *original = av_memdup(m, bytes);
    assert(original);
    struct dvbridge_color mapped;
    struct dvbridge_hdr10_session session;
    struct dvbridge_context *context = dvbridge_create();
    const struct dvbridge_geometry geometry = {64, 64, 840, 0, 2160, 2160};
    assert(context);
    /* No L1 or creative blocks: reconstruction and a real source target exist. */
    assert(dvbridge_map_color(&mapped, m, bytes, false));
    assert(dvbridge_hdr10_session_init(&session, m, bytes));
    assert(session.target.hdr.max_luma == 10000);
    assert(!session.output.level6 && !session.output.max_cll && !session.output.max_fall);
    assert(!dvbridge_prepare(context, m, bytes, 0, geometry, false));
    assert(!memcmp(original, m, bytes));
    /* Native needs L1, not optional L2/L3/L8 or MaxCLL. */
    m->num_ext_blocks = 1;
    AVDOVIDmData *l1 = av_dovi_get_ext(m, 0);
    l1->level = 1; l1->l1.max_pq = 3000; l1->l1.avg_pq = 1000;
    memcpy(original, m, bytes);
    struct dvbridge_candidate *candidate = dvbridge_prepare(context, m, bytes, 0, geometry, false);
    assert(candidate);
    assert(dvbridge_map_color(&mapped, m, bytes, false));
    assert(dvbridge_hdr10_session_init(&session, m, bytes));
    assert(!memcmp(original, m, bytes));
    dvbridge_candidate_destroy(candidate);
    /* Essential reconstruction failure is not missing optional trims. */
    av_dovi_get_mapping(m)->curves[0].poly_order[0] = 3;
    assert(!dvbridge_map_color(&mapped, m, bytes, false));
    assert(!dvbridge_hdr10_session_init(&session, m, bytes));
    assert(!dvbridge_prepare(context, NULL, 0, 0, geometry, false));
    av_dovi_get_mapping(m)->curves[0].poly_order[0] = 1;
    av_dovi_get_header(m)->disable_residual_flag = 0;
    assert(!dvbridge_map_color(&mapped, m, bytes, false));
    assert(!dvbridge_prepare(context, m, bytes, 0, geometry, false));
    av_dovi_get_header(m)->disable_residual_flag = 1;
    /* Without L6 or source_max_pq no output target may be invented. */
    av_dovi_get_color(m)->source_max_pq = 0;
    assert(!dvbridge_hdr10_session_init(&session, m, bytes));
    dvbridge_destroy(context); av_free(original); av_free(m);
    puts("PASS: real operation inputs, optional absence and immutable source metadata");
}
