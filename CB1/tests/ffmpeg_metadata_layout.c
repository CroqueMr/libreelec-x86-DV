/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Actual pinned extension parser and side-data producer, not a fabricated AV struct.
 * This test-only inclusion exposes a static parser without changing its API. */
#include "libavcodec/dovi_rpudec.c"
/* FFmpeg internal.h may define NDEBUG; fixture checks must remain executable. */
#undef NDEBUG
#include <assert.h>
#include "dvbridge_metadata_bounds.h"
#include "dvbridge_core.h"
#include "mpv_dvbridge_cm4.h"

static void bits(uint8_t *data, unsigned *position, unsigned value, unsigned count)
{
    while (count--) {
        data[*position / 8] |= ((value >> count) & 1) << (7 - *position % 8);
        ++*position;
    }
}

static void extension(const uint8_t raw[25], int available)
{
    uint8_t encoded[64 + AV_INPUT_BUFFER_PADDING_SIZE] = {0};
    unsigned position = 0;
    bits(encoded, &position, 2, 3); /* ue(1): one block */
    position = 8; /* block count alignment */
    bits(encoded, &position, 26, 9); /* ue(25): 25-byte L8 */
    bits(encoded, &position, 8, 8);
    for (unsigned i = 0; i < 25; ++i) bits(encoded, &position, raw[i], 8);
    DOVIContext producer = {0};
    GetBitContext reader;
    /* Parse L1 too, so the separately compiled engine can serialize the frame. */
    uint8_t l1[32 + AV_INPUT_BUFFER_PADDING_SIZE] = {0};
    unsigned l1_position = 0;
    bits(l1, &l1_position, 2, 3);
    l1_position = 8;
    bits(l1, &l1_position, 6, 5); /* ue(5) */
    bits(l1, &l1_position, 1, 8);
    bits(l1, &l1_position, 0, 12);
    bits(l1, &l1_position, 3079, 12);
    bits(l1, &l1_position, 1800, 12);
    bits(l1, &l1_position, 0, 4);
    assert(init_get_bits(&reader, l1, l1_position) == 0);
    assert(parse_ext_blocks(&producer, &reader, 1, 0, AV_EF_EXPLODE) == 0);
    assert(init_get_bits(&reader, encoded, available ? position : position - 8) == 0);
    int result = parse_ext_blocks(&producer, &reader, 2, 0, AV_EF_EXPLODE);
    if (!available) {
        assert(result == AVERROR_INVALIDDATA);
        ff_dovi_ctx_unref(&producer);
        return;
    }
    assert(result == 0);
    assert(producer.ext_blocks && producer.ext_blocks->num_dynamic == 2);
    AVDOVIDataMapping mapping = {0};
    AVDOVIColorMetadata color = {.signal_eotf = 65535, .source_max_pq = 3079};
    producer.header.disable_residual_flag = 1;
    producer.mapping = &mapping;
    producer.color = &color;
    AVFrame *frame = av_frame_alloc();
    assert(frame && ff_dovi_attach_side_data(&producer, frame) == 0);
    AVFrameSideData *side = av_frame_get_side_data(frame, AV_FRAME_DATA_DOVI_METADATA);
    assert(side && dvbridge_metadata_bounds(side->data, side->size));
    AVDOVIMetadata *metadata = (void *)side->data;
    assert(metadata->num_ext_blocks == 2);
    AVDOVIDmData *dm = av_dovi_get_ext(metadata, 1);
    assert(dm->level == 8 && dm->l8.target_display_index == raw[0]);
    assert(dm->dvbridge_raw_magic == 0x41424456);
    assert(dm->dvbridge_original_length == 25);
    assert(!memcmp(dm->dvbridge_original_bytes, raw, 25));
    uint8_t wire[32];
    assert(dvbridge_cm4_wire(dm->level, dm->dvbridge_original_bytes,
                           dm->dvbridge_original_length, wire) == 29);
    assert(wire[0] == raw[0]);
    unsigned margins[4];
    struct dvbridge_geometry geometry = {3840, 2160, 0, 0, 3840, 2160};
    assert(dvbridge_frame_area(margins, side->data, side->size, geometry));
    struct dvbridge_context *consumer = dvbridge_create();
    assert(consumer);
    struct dvbridge_candidate *candidate = dvbridge_prepare(consumer, side->data,
        side->size, 0, geometry, false);
    assert(candidate);
    unsigned packet_count;
    assert(dvbridge_packets(candidate, &packet_count) && packet_count > 0);
    dvbridge_candidate_destroy(candidate);
    dm->dvbridge_raw_magic = 0;
    assert(!dvbridge_prepare(consumer, side->data, side->size, 0, geometry, false));
    dm->dvbridge_raw_magic = 0x41424456;
    assert(!memcmp(dm->dvbridge_original_bytes, raw, 25));
    dvbridge_destroy(consumer);
    if (!raw[0]) {
        assert(dm->l8.target_mid_contrast == 0 && dm->l8.clip_trim == 0);
        for (unsigned i = 0; i < 29; ++i) assert(wire[i] == 0);
    }
    assert(!dvbridge_metadata_bounds(side->data, metadata->ext_block_offset + sizeof(*dm) - 1));
    size_t offset = metadata->ext_block_offset;
    metadata->ext_block_offset = SIZE_MAX;
    assert(!dvbridge_metadata_bounds(side->data, side->size));
    metadata->ext_block_offset = offset;
    av_frame_free(&frame);
    ff_dovi_ctx_unref(&producer);
}

int main(void)
{
    const uint8_t nonzero[25] = {3, 0x12, 0x34, 0x56, 0x78, 0x90, 0x12, 0x34,
        0x56, 0x78, 0x90, 0x12, 0x30, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12};
    const uint8_t present_zero[25] = {0};
    extension(nonzero, 1);
    extension(present_zero, 1);
    extension(nonzero, 0);
    puts("PASS: parsed nonzero/present-zero L8, producer side data, raw trailer, consumer bounds, truncation");
}
