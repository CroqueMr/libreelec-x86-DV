/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include <libavutil/mem.h>
#include "dvbridge_metadata.h"
#include "dvbridge_core.h"

static AVDOVIMetadata *fixture(size_t *bytes)
{
    AVDOVIMetadata *m = av_dovi_metadata_alloc(bytes);
    assert(m);
    av_dovi_get_header(m)->disable_residual_flag = 1;
    AVDOVIColorMetadata *c = av_dovi_get_color(m);
    c->signal_eotf = 65535;
    c->source_min_pq = 0;
    c->source_max_pq = 3079;
    m->num_ext_blocks = 1;
    AVDOVIDmData *l1 = av_dovi_get_ext(m, 0);
    l1->level = 1;
    l1->l1.min_pq = 0;
    l1->l1.max_pq = 3079;
    l1->l1.avg_pq = 1800;
    return m;
}

int main(void)
{
    size_t bytes;
    AVDOVIMetadata *m = fixture(&bytes);
    struct dvbridge_dv state = {0};
    unsigned margins[4];
    struct dvbridge_geometry geometry = {3840, 2160, 0, 0, 3840, 2160};
    assert(dvbridge_frame_area(margins, m, bytes, geometry));
    assert(dvbridge_dv_bounds(m, bytes));
    assert(!dvbridge_dv_bounds(m, sizeof(*m) - 1));
    size_t offset = m->header_offset;
    m->header_offset = SIZE_MAX;
    assert(!dvbridge_dv_bounds(m, bytes));
    m->header_offset = offset;
    assert(dvbridge_dv_geometry(&state, 3840, 2160, 0, 0, 3840, 2160));
    assert(!dvbridge_dv_geometry(&state, 3840, 2160, 1, 0, 3840, 2160));
    assert(dvbridge_dv_metadata(&state, m, 0.0, margins));
    assert(state.payload[1] == 1 && state.count >= 1 && state.count <= 4);
    uint8_t previous[512];
    memcpy(previous, state.payload, state.size);
    unsigned size = state.size;
    assert(dvbridge_dv_metadata(&state, m, 0.0, margins));
    assert(state.size == size && memcmp(previous, state.payload, size) == 0);
    assert(dvbridge_dv_metadata(&state, m, 1001.0 / 24000, margins));
    assert(state.payload[1] == 0);
    assert(dvbridge_dv_metadata(&state, m, 50.0, margins));
    assert(state.payload[1] == 1);
    assert(dvbridge_dv_metadata(&state, m, 2.0, margins));
    assert(state.payload[1] == 1);
    assert(!dvbridge_dv_metadata(&state, m, NAN, margins));

    av_dovi_get_header(m)->disable_residual_flag = 0;
    assert(!dvbridge_dv_metadata(&state, m, 3.0, margins));
    av_dovi_get_header(m)->disable_residual_flag = 1;

    m->num_ext_blocks = 2;
    AVDOVIDmData *cm4 = av_dovi_get_ext(m, 1);
    cm4->level = 8;
    cm4->dvbridge_raw_magic = 0x41424456;
    cm4->dvbridge_original_length = 25;
    assert(dvbridge_frame_area(margins, m, bytes, geometry));
    assert(dvbridge_dv_metadata(&state, m, 4.0, margins));
    assert(state.size > size);
    cm4->dvbridge_raw_magic = 0;
    assert(!dvbridge_dv_metadata(&state, m, 5.0, margins));

    for (unsigned i = 0; i < state.count; ++i) {
        uint8_t packet[128];
        for (unsigned j = 0; j < 128; ++j)
            packet[j] = state.packets[i * 128 + j];
        assert(dvbridge_dv_crc(packet, sizeof(packet)) == 0);
    }
    av_free(m);
    puts("PASS: metadata bounds, geometry, repeat, seek refresh, FEL rejection, CM4 presence, packet CRC");
    return 0;
}
