/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "task4_api.h"
#include "task3_fixture.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    assert(argc == 2);
    size_t bytes;
    AVDOVIMetadata *m = task3_fixture(&bytes);
    m->num_ext_blocks = 1;
    AVDOVIDmData *l6 = av_dovi_get_ext(m, 0);
    l6->level = 6; l6->l6.max_luminance = 4000;
    l6->l6.max_cll = 9000; l6->l6.max_fall = 3000;
    struct dvbridge_hdr10_session session;
    assert(dvbridge_hdr10_session_init(&session, m, bytes));
    assert(session.target.hdr.max_luma == 4000.0f);
    assert(session.output.max_luminance == 4000);
    assert(session.output.max_cll == 0 && session.output.max_fall == 0);
    assert(session.output.level6);
    if (!strcmp(argv[1], "precedence")) {
        l6->l6.max_luminance = 10001;
        assert(dvbridge_hdr10_session_init(&session,m,bytes));
        assert(session.target.hdr.max_luma == 10000 && !session.output.level6);
        m->num_ext_blocks = 0;
        av_dovi_get_color(m)->source_max_pq = 3079;
        assert(dvbridge_hdr10_session_init(&session,m,bytes));
        assert(fabsf(session.target.hdr.max_luma-1000) < 2);
        assert(session.output.max_luminance >= 999 && session.output.max_luminance <= 1002);
        av_dovi_get_color(m)->source_max_pq = 0;
        struct dvbridge_hdr10_session before = session;
        assert(!dvbridge_hdr10_session_init(&session,m,bytes));
        assert(!memcmp(&before,&session,sizeof(session)));
        assert(!dvbridge_hdr10_session_init(NULL,m,bytes));
        assert(!dvbridge_hdr10_session_init(&session,m,1));
        assert(!memcmp(&before,&session,sizeof(session)));
    } else if (!strcmp(argv[1], "malformed")) {
        struct dvbridge_hdr10_session before = session;
        av_dovi_get_mapping(m)->curves[0].poly_order[0] = 3;
        assert(!dvbridge_hdr10_session_init(&session,m,bytes));
        assert(!memcmp(&before,&session,sizeof(session)));
    } else assert(0);
    av_free(m);
    puts("PASS: session policy target precedence, unknown output light levels and atomic failure");
}
