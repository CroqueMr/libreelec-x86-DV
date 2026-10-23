/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DVBRIDGE_METADATA_BOUNDS_H
#define DVBRIDGE_METADATA_BOUNDS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#include <libavutil/dovi_meta.h>
#ifdef __cplusplus
}
#define DVBRIDGE_META_ALIGN(T) alignof(T)
#else
#define DVBRIDGE_META_ALIGN(T) _Alignof(T)
#endif

/* Validate the matched FFmpeg storage layout before using its offset accessors.
 * No pointed-to region is read here; transport eligibility is a separate check. */
static inline bool dvbridge_metadata_bounds(const void *metadata, size_t bytes)
{
    if (!metadata || bytes < sizeof(AVDOVIMetadata) ||
        (uintptr_t)metadata % DVBRIDGE_META_ALIGN(AVDOVIMetadata))
        return false;
    const AVDOVIMetadata *m = (const AVDOVIMetadata *)metadata;
    if (m->num_ext_blocks < 0 || m->num_ext_blocks > AV_DOVI_MAX_EXT_BLOCKS)
        return false;
    const size_t offsets[] = {
        m->header_offset, m->mapping_offset, m->color_offset, m->ext_block_offset
    };
    const size_t sizes[] = {
        sizeof(AVDOVIRpuDataHeader), sizeof(AVDOVIDataMapping),
        sizeof(AVDOVIColorMetadata), sizeof(AVDOVIDmData)
    };
    const size_t alignments[] = {
        DVBRIDGE_META_ALIGN(AVDOVIRpuDataHeader), DVBRIDGE_META_ALIGN(AVDOVIDataMapping),
        DVBRIDGE_META_ALIGN(AVDOVIColorMetadata), DVBRIDGE_META_ALIGN(AVDOVIDmData)
    };
    unsigned regions = m->num_ext_blocks ? 4 : 3;
    for (unsigned i = 0; i < regions; ++i) {
        size_t offset = offsets[i];
        if (offset < sizeof(*m) || offset > bytes || offset % alignments[i] ||
            sizes[i] > bytes - offset)
            return false;
    }
    if (!m->num_ext_blocks)
        return true;
    size_t stride = m->ext_block_size;
    return stride >= sizeof(AVDOVIDmData) && stride % DVBRIDGE_META_ALIGN(AVDOVIDmData) == 0 &&
           (size_t)m->num_ext_blocks <= (bytes - m->ext_block_offset) / stride;
}
#undef DVBRIDGE_META_ALIGN
#endif
