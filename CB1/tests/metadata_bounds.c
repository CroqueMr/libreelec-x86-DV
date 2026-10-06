/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_metadata_bounds.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#ifdef __cplusplus
extern "C" {
#endif
#include <libavutil/mem.h>
#ifdef __cplusplus
}
#define TEST_ALIGN(type) alignof(type)
#else
#define TEST_ALIGN(type) _Alignof(type)
#endif

int main(void)
{
    size_t bytes;
    AVDOVIMetadata *m = av_dovi_metadata_alloc(&bytes);
    assert(m);
    assert(dvbridge_metadata_bounds(m, bytes));
    assert(!dvbridge_metadata_bounds(NULL, bytes));
    assert(!dvbridge_metadata_bounds((char *)m + 1, bytes - 1));
    for (size_t n = 0; n < sizeof(*m); ++n)
        assert(!dvbridge_metadata_bounds(m, n));
    /* Zero count does not describe or authorize any extension access. */
    size_t fixed_bytes = m->color_offset + sizeof(AVDOVIColorMetadata);
    assert(fixed_bytes <= m->ext_block_offset);
    size_t ext_offset = m->ext_block_offset, stride = m->ext_block_size;
    m->ext_block_offset = SIZE_MAX; m->ext_block_size = 0;
    assert(dvbridge_metadata_bounds(m, fixed_bytes));
    m->ext_block_offset = ext_offset; m->ext_block_size = stride;
    size_t *fields[] = {&m->header_offset, &m->mapping_offset, &m->color_offset};
    const size_t sizes[] = {sizeof(AVDOVIRpuDataHeader), sizeof(AVDOVIDataMapping), sizeof(AVDOVIColorMetadata)};
    for (unsigned i = 0; i < 3; ++i) {
        size_t saved = *fields[i];
        const size_t bad[] = {0, sizeof(*m) - 1, bytes, bytes + 1, SIZE_MAX, saved + 1};
        for (unsigned j = 0; j < sizeof(bad) / sizeof(*bad); ++j) {
            *fields[i] = bad[j]; assert(!dvbridge_metadata_bounds(m, bytes));
        }
        *fields[i] = saved;
        assert(!dvbridge_metadata_bounds(m, saved + sizes[i] - 1));
    }
    m->num_ext_blocks = -1; assert(!dvbridge_metadata_bounds(m, bytes));
    m->num_ext_blocks = AV_DOVI_MAX_EXT_BLOCKS + 1; assert(!dvbridge_metadata_bounds(m, bytes));
    m->num_ext_blocks = 1; assert(dvbridge_metadata_bounds(m, bytes));
    const size_t bad_offsets[] = {0, sizeof(*m)-1, bytes, bytes+1, SIZE_MAX, ext_offset+1};
    for (unsigned i = 0; i < sizeof(bad_offsets)/sizeof(*bad_offsets); ++i) {
        m->ext_block_offset = bad_offsets[i]; assert(!dvbridge_metadata_bounds(m, bytes));
    }
    m->ext_block_offset = ext_offset;
    const size_t bad_strides[] = {0, sizeof(AVDOVIDmData)-1, stride+1, SIZE_MAX};
    for (unsigned i = 0; i < sizeof(bad_strides)/sizeof(*bad_strides); ++i) {
        m->ext_block_size = bad_strides[i]; assert(!dvbridge_metadata_bounds(m, bytes));
    }
    m->ext_block_size = stride;
    assert(!dvbridge_metadata_bounds(m, ext_offset + stride - 1));
    m->num_ext_blocks = 2;
    assert(!dvbridge_metadata_bounds(m, ext_offset + 2*stride - 1));
    m->ext_block_size = stride + TEST_ALIGN(AVDOVIDmData);
    assert(dvbridge_metadata_bounds(m, bytes));
    m->ext_block_size = (SIZE_MAX / TEST_ALIGN(AVDOVIDmData))*TEST_ALIGN(AVDOVIDmData);
    assert(!dvbridge_metadata_bounds(m, bytes));
    av_free(m);
    puts("PASS: standalone metadata storage contract");
}
