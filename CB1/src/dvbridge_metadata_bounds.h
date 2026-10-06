/* SPDX-License-Identifier: GPL-3.0-or-later */
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
#define DVBRIDGE_ALIGNOF(type) alignof(type)
#else
#define DVBRIDGE_ALIGNOF(type) _Alignof(type)
#endif

/* Readable storage for the matched FFmpeg ABI, not transport eligibility. */
static inline bool dvbridge_metadata_bounds(const void *metadata, size_t bytes)
{
    if (!metadata || bytes < sizeof(AVDOVIMetadata) ||
        (uintptr_t)metadata % DVBRIDGE_ALIGNOF(AVDOVIMetadata))
        return false;
    const AVDOVIMetadata *m = (const AVDOVIMetadata *)metadata;
#define DVBRIDGE_REGION(field, type) \
    do { if (m->field < sizeof(*m) || m->field > bytes || \
             bytes - m->field < sizeof(type) || \
             m->field % DVBRIDGE_ALIGNOF(type)) return false; } while (0)
    DVBRIDGE_REGION(header_offset, AVDOVIRpuDataHeader);
    DVBRIDGE_REGION(mapping_offset, AVDOVIDataMapping);
    DVBRIDGE_REGION(color_offset, AVDOVIColorMetadata);
    if (m->num_ext_blocks < 0 || m->num_ext_blocks > AV_DOVI_MAX_EXT_BLOCKS)
        return false;
    if (!m->num_ext_blocks)
        return true;
    DVBRIDGE_REGION(ext_block_offset, AVDOVIDmData);
#undef DVBRIDGE_REGION
    if (m->ext_block_size < sizeof(AVDOVIDmData) ||
        m->ext_block_size % DVBRIDGE_ALIGNOF(AVDOVIDmData))
        return false;
    return (size_t)m->num_ext_blocks <= (bytes - m->ext_block_offset) / m->ext_block_size;
}
#undef DVBRIDGE_ALIGNOF
#endif
