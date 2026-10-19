/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_dmabuf.h"
#include <assert.h>
#include <limits.h>
#include <libdrm/drm_fourcc.h>
#include <stdio.h>

int main(void)
{
    AVDRMFrameDescriptor d = {.nb_objects = 1, .nb_layers = 2,
        .objects = {{.fd = 5, .size = 64 * 64 * 3, .format_modifier = DRM_FORMAT_MOD_LINEAR}},
        .layers = {{.format = DRM_FORMAT_R16, .nb_planes = 1,
                    .planes = {{.object_index = 0, .offset = 0, .pitch = 128}}},
                   {.format = DRM_FORMAT_GR1616, .nb_planes = 1,
                    .planes = {{.object_index = 0, .offset = 8192, .pitch = 128}}}}};
    assert(dvbridge_dmabuf_validate_p010(&d, 64, 64));
    assert(!dvbridge_dmabuf_validate_p010(NULL, 64, 64));
    assert(!dvbridge_dmabuf_validate_p010(&d, INT_MAX, 64));
    assert(!dvbridge_dmabuf_validate_p010(&d, 64, 0));
    /* Both driver layouts must keep exactly the same descriptor bounds. */
    const uint32_t chroma[] = {DRM_FORMAT_GR1616, DRM_FORMAT_RG1616};
    for (unsigned format = 0; format < sizeof(chroma) / sizeof(chroma[0]); ++format) {
        d.layers[1].format = chroma[format];
        assert(dvbridge_dmabuf_validate_p010(&d, 64, 64));
        AVDRMFrameDescriptor bad = d;
        bad.objects[0].size--;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[1].planes[0].pitch = 127;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[1].planes[0].object_index = 4;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[0].planes[0].offset = -1;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[1].format = DRM_FORMAT_R16;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[0].format = chroma[format];
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[1].planes[0].offset = bad.objects[0].size;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[1].planes[0].object_index = -1;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[1].planes[0].pitch = 0;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[1].planes[0].pitch = -1;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
#if PTRDIFF_MAX > INT_MAX
        bad = d; bad.layers[1].planes[0].offset = (ptrdiff_t)INT_MAX + 1;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[1].planes[0].pitch = (ptrdiff_t)INT_MAX + 1;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
#endif
        bad = d; bad.nb_objects = AV_DRM_MAX_PLANES + 1;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.objects[0].fd = -1;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.layers[0].nb_planes = 2;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.nb_layers = 1;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad = d; bad.nb_objects = 0;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        AVDRMFrameDescriptor split = d;
        split.nb_objects = 2;
        split.objects[1] = split.objects[0];
        split.objects[1].size = 4096;
        split.layers[1].planes[0].object_index = 1;
        split.layers[1].planes[0].offset = 0;
        assert(dvbridge_dmabuf_validate_p010(&split, 64, 64));
        split.objects[1].size--;
        assert(!dvbridge_dmabuf_validate_p010(&split, 64, 64));
        /* 63x63: 126 luma bytes and 128 chroma bytes per row, 32 chroma rows. */
        assert(dvbridge_dmabuf_validate_p010(&d, 63, 63));
        bad = d; bad.layers[1].planes[0].pitch = 126;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 63, 63));
        bad = d; bad.objects[0].format_modifier = DRM_FORMAT_MOD_INVALID;
        assert(dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        bad.layers[1].planes[0].offset = bad.objects[0].size;
        assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
        assert(!dvbridge_dmabuf_validate_p010(&d, 4097, 64));
        assert(!dvbridge_dmabuf_validate_p010(&d, 64, 2305));
    }
    puts("PASS: P010 GR1616/RG1616 descriptors, shared/split objects and unchanged bounds");
}
