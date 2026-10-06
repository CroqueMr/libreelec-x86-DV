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
    AVDRMFrameDescriptor bad = d;
    bad.objects[0].size--;
    assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
    bad = d; bad.layers[1].planes[0].pitch = 127;
    assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
    bad = d; bad.layers[1].planes[0].object_index = 4;
    assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
    bad = d; bad.layers[0].planes[0].offset = -1;
    assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
    bad = d; bad.layers[1].format = DRM_FORMAT_RG1616;
    assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
    bad = d; bad.nb_objects = AV_DRM_MAX_PLANES + 1;
    assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
    bad = d; bad.objects[0].fd = -1;
    assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
    bad = d; bad.layers[0].nb_planes = 2;
    assert(!dvbridge_dmabuf_validate_p010(&bad, 64, 64));
    d.nb_objects = 2;
    d.objects[1] = d.objects[0];
    d.objects[1].size = 4096;
    d.layers[1].planes[0].object_index = 1;
    d.layers[1].planes[0].offset = 0;
    assert(dvbridge_dmabuf_validate_p010(&d, 64, 64));
    puts("PASS: P010 DMA-BUF layout, split/shared objects, bounds, channel order, malformed descriptors");
}
