/* SPDX-License-Identifier: GPL-3.0-or-later */
/* GUI/subtitle overlays clear only the transmitted L5; masking keeps the source area. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <libavutil/mem.h>
#include "dvbridge_metadata.h"
#include "dvbridge_core.h"

static const struct dvbridge_geometry full = {3840, 2160, 0, 0, 3840, 2160};

/* Letterboxed 2.40:1 picture: L1, an unrelated L2 trim and L5. */
static AVDOVIMetadata *fixture(size_t *bytes, unsigned top, unsigned bottom)
{
    AVDOVIMetadata *m = av_dovi_metadata_alloc(bytes);
    assert(m);
    av_dovi_get_header(m)->disable_residual_flag = 1;
    AVDOVIColorMetadata *c = av_dovi_get_color(m);
    c->signal_eotf = 65535;
    c->source_max_pq = 3079;
    m->num_ext_blocks = 3;
    AVDOVIDmData *l1 = av_dovi_get_ext(m, 0), *l2 = av_dovi_get_ext(m, 1), *l5 = av_dovi_get_ext(m, 2);
    l1->level = 1;
    l1->l1.max_pq = 3079;
    l1->l1.avg_pq = 1800;
    l2->level = 2;
    l2->l2.target_max_pq = 2081;
    l2->l2.trim_slope = 2100;
    l2->l2.trim_offset = 2000;
    l2->l2.trim_power = 1990;
    l2->l2.trim_chroma_weight = 2048;
    l2->l2.trim_saturation_gain = 2050;
    l2->l2.ms_weight = 2048;
    l5->level = 5;
    l5->l5.top_offset = top;
    l5->l5.bottom_offset = bottom;
    return m;
}

/* Reassemble the transmitted payload, checking every packet CRC on the way. */
static unsigned payload(const struct dvbridge_candidate *candidate, uint8_t out[512])
{
    unsigned count, size = 0, off = 0;
    const uint32_t *packets = dvbridge_packets(candidate, &count);
    assert(packets && count >= 1 && count <= 4);
    for (unsigned i = 0; i < count; ++i) {
        uint8_t p[128];
        for (unsigned j = 0; j < 128; ++j) p[j] = (uint8_t)packets[i * 128 + j];
        assert(dvbridge_dv_crc(p, sizeof(p)) == 0);
        if (!i) size = (unsigned)p[3] << 8 | p[4];
        unsigned start = i ? 3 : 5, room = i ? 121 : 119, take = size - off;
        if (take > room) take = room;
        memcpy(out + off, p + start, take);
        off += take;
    }
    assert(off == size && size > 71);
    return size;
}

/* Offset of the single L5 body, or 0 without one. */
static unsigned find_l5(const uint8_t *p, unsigned size)
{
    unsigned at = 71, found = 0;
    for (unsigned i = 0; i < p[70]; ++i) {
        assert(at + 5 <= size);
        unsigned n = (unsigned)p[at] << 24 | (unsigned)p[at + 1] << 16 | (unsigned)p[at + 2] << 8 | p[at + 3];
        if (p[at + 4] == 5) { assert(!found && n == 8); found = at + 5; }
        at += 5 + n;
    }
    assert(at == size);
    return found;
}

static const uint8_t zero[8];

/* Present one picture on both contexts; return the overlay picture's payload. */
static unsigned present(struct dvbridge_context *context, struct dvbridge_context *plain,
                        const AVDOVIMetadata *m, size_t bytes, double pts,
                        struct dvbridge_geometry geometry, bool overlay, uint8_t out[512], uint8_t ref[512])
{
    dvbridge_set_overlay_visible(context, overlay);
    struct dvbridge_candidate *a = dvbridge_prepare(context, m, bytes, pts, geometry, false);
    struct dvbridge_candidate *b = dvbridge_prepare(plain, m, bytes, pts, geometry, false);
    assert(a && b);
    unsigned size = payload(a, out), plain_size = payload(b, ref);
    assert(size == plain_size);
    unsigned area[4], plain_area[4];
    assert(dvbridge_active_area(a, area) && dvbridge_active_area(b, plain_area));
    assert(!memcmp(area, plain_area, sizeof(area)));
    assert(dvbridge_commit(context, a) && dvbridge_commit(plain, b));
    dvbridge_candidate_destroy(a);
    dvbridge_candidate_destroy(b);
    return size;
}

/* Everything except the refresh flag and the L5 body must equal the plain output. */
static void check(const uint8_t *p, const uint8_t *ref, unsigned size, bool overlay, bool refresh)
{
    unsigned l5 = find_l5(p, size);
    assert(l5 && l5 == find_l5(ref, size));
    assert(p[1] == (refresh ? 1 : ref[1]));
    assert(!memcmp(p + 2, ref + 2, l5 - 2));
    assert(!memcmp(p + l5, overlay ? zero : ref + l5, 8));
    assert(!memcmp(p + l5 + 8, ref + l5 + 8, size - l5 - 8));
}

static void transitions(void)
{
    size_t bytes;
    AVDOVIMetadata *m = fixture(&bytes, 276, 276);
    void *original = av_memdup(m, bytes);
    struct dvbridge_context *context = dvbridge_create(), *plain = dvbridge_create();
    assert(context && plain && original);
    uint8_t p[512], ref[512];
    const bool states[] = {false, true, true, false, false, true, false};
    bool previous = false;
    double pts = 0;
    for (unsigned i = 0; i < sizeof(states) / sizeof(*states); ++i) {
        pts = i * (1001.0 / 24000);
        unsigned size = present(context, plain, m, bytes, pts, full, states[i], p, ref);
        unsigned l5 = find_l5(ref, size);
        assert(memcmp(ref + l5, zero, 8));
        check(p, ref, size, states[i], !i || states[i] != previous);
        if (i && states[i] == previous) assert(p[1] == 0);
        previous = states[i];
    }
    /* A paused picture repeats its PTS; overlay edges still refresh. */
    for (int overlay = 1; overlay >= 0; --overlay) {
        unsigned size = present(context, plain, m, bytes, pts, full, overlay, p, ref);
        check(p, ref, size, overlay, true);
    }
    assert(!memcmp(m, original, bytes));
    av_free(original);
    av_free(m);
    dvbridge_destroy(context);
    dvbridge_destroy(plain);
}

static void missing_and_zero(void)
{
    size_t bytes;
    AVDOVIMetadata *m = fixture(&bytes, 0, 0);
    struct dvbridge_context *context = dvbridge_create(), *plain = dvbridge_create();
    assert(context && plain);
    uint8_t p[512], ref[512];
    /* Zero L5: the overlay output is byte-identical apart from the edge refresh. */
    unsigned size = present(context, plain, m, bytes, 0., full, true, p, ref);
    assert(!memcmp(p, ref, size));
    size = present(context, plain, m, bytes, .04, full, true, p, ref);
    assert(!memcmp(p, ref, size) && !p[1]);
    size = present(context, plain, m, bytes, .08, full, false, p, ref);
    check(p, ref, size, false, true);
    assert(!ref[1]);
    /* Missing L5 on a full raster still yields the canonical zero-area L5. */
    m->num_ext_blocks = 2;
    size = present(context, plain, m, bytes, .12, full, true, p, ref);
    check(p, ref, size, true, true);
    assert(!memcmp(ref + find_l5(ref, size), zero, 8));
    /* Missing L5 with player letterboxing: the synthesized margins are cleared too. */
    struct dvbridge_geometry letterbox = {3840, 1600, 0, 280, 3840, 1600};
    dvbridge_reset(context);
    dvbridge_reset(plain);
    size = present(context, plain, m, bytes, 3., letterbox, true, p, ref);
    assert(memcmp(ref + find_l5(ref, size), zero, 8));
    check(p, ref, size, true, true);
    av_free(m);
    dvbridge_destroy(context);
    dvbridge_destroy(plain);
}

static void malformed(void)
{
    size_t bytes;
    AVDOVIMetadata *m = fixture(&bytes, 276, 276);
    struct dvbridge_context *context = dvbridge_create(), *plain = dvbridge_create();
    assert(context && plain);
    uint8_t p[512], ref[512];
    present(context, plain, m, bytes, 0., full, false, p, ref);
    dvbridge_set_overlay_visible(context, true);
    /* Truncated, duplicate and out-of-range L5 are rejected before any output. */
    for (size_t n = 0; n < m->ext_block_offset + 3 * m->ext_block_size; ++n)
        assert(!dvbridge_prepare(context, m, n, 1., full, false));
    m->num_ext_blocks = 4;
    *av_dovi_get_ext(m, 3) = *av_dovi_get_ext(m, 2);
    void *saved = av_memdup(m, bytes);
    assert(saved && !dvbridge_prepare(context, m, bytes, 1., full, false));
    assert(!memcmp(m, saved, bytes));
    av_free(saved);
    m->num_ext_blocks = 3;
    av_dovi_get_ext(m, 2)->l5.top_offset = 1100;
    av_dovi_get_ext(m, 2)->l5.bottom_offset = 1100;
    assert(!dvbridge_prepare(context, m, bytes, 1., full, false));
    av_dovi_get_ext(m, 2)->l5.top_offset = 276;
    av_dovi_get_ext(m, 2)->l5.bottom_offset = 276;
    /* Rejection left the presented state alone: the next edge still refreshes. */
    unsigned size = present(context, plain, m, bytes, 1001.0 / 24000, full, true, p, ref);
    check(p, ref, size, true, true);
    av_free(m);
    dvbridge_destroy(context);
    dvbridge_destroy(plain);
}

int main(void)
{
    transitions();
    missing_and_zero();
    malformed();
    puts("PASS: overlay L5 enter/hold/leave, paused edges, missing/zero L5, malformed rejection, "
         "packet CRC, unrelated extensions and active area preserved");
    return 0;
}
