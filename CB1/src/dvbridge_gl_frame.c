/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Map native decoded planes to renderer textures while preserving layout and bit depth. */
#include "dvbridge_gl_frame.h"
#include <GLES3/gl3.h>
#include <string.h>

void dvbridge_gl_frame_release(struct dvbridge_gl_frame *frame)
{
    if (!frame)
        return;
    for (int i = 0; i < frame->frame.num_planes; ++i)
        pl_tex_destroy(frame->gpu, &frame->frame.planes[i].texture);
    memset(frame, 0, sizeof(*frame));
}

bool dvbridge_gl_frame_import(struct dvbridge_gl_frame *out, pl_gpu gpu,
                             enum dvbridge_gl_layout layout, int width, int height,
                             const struct dvbridge_gl_plane planes[3])
{
    if (!out || !gpu || !planes || width <= 0 || width > 3840 || height <= 0 || height > 2160)
        return false;
    /* Refuse to overwrite live wrappers. Initialize to zero before first import. */
    if (out->gpu)
        return false;
    int depth, shift, storage;
    bool planar = false, subsampled = true;
    switch (layout) {
    case DVBRIDGE_NV12: depth = storage = 8; shift = 0; break;
    case DVBRIDGE_P010: depth = 10; storage = 16; shift = 6; break;
    case DVBRIDGE_P012: depth = 12; storage = 16; shift = 4; break;
    case DVBRIDGE_P016: depth = storage = 16; shift = 0; break;
    case DVBRIDGE_YUV420P10: depth = 10; storage = 16; shift = 0; planar = true; break;
    case DVBRIDGE_YUV444P10:
        depth = 10; storage = 16; shift = 0; planar = true; subsampled = false; break;
    default: return false;
    }
    struct dvbridge_gl_frame candidate = {.gpu = gpu};
    candidate.frame.num_planes = planar ? 3 : 2;
    candidate.frame.crop = (pl_rect2df){0, 0, width, height};
    candidate.frame.repr.bits = (struct pl_bit_encoding){
        .sample_depth = storage, .color_depth = depth, .bit_shift = shift};
    for (int i = 0; i < candidate.frame.num_planes; ++i) {
        int pw = i && subsampled ? (width + 1) / 2 : width;
        int ph = i && subsampled ? (height + 1) / 2 : height;
        int tw = i && subsampled ? (planes[0].width + 1) / 2 : planes[0].width;
        int th = i && subsampled ? (planes[0].height + 1) / 2 : planes[0].height;
        if (!planes[i].texture || planes[i].width < pw || planes[i].height < ph ||
            planes[i].width != tw || planes[i].height != th || tw > 4096 || th > 2304)
            goto fail;
        int components = !planar && i == 1 ? 2 : 1;
        int format = storage == 8 ? (components == 2 ? GL_RG8 : GL_R8) :
                                   (components == 2 ? 0x822C : 0x822A); /* RG16/R16 */
        struct pl_plane *plane = &candidate.frame.planes[i];
        plane->texture = pl_opengl_wrap(gpu, pl_opengl_wrap_params(
            .texture = planes[i].texture, .target = GL_TEXTURE_2D,
            .iformat = format, .width = tw, .height = th));
        if (!plane->texture || !plane->texture->params.sampleable)
            goto fail;
        plane->components = components;
        plane->component_mapping[0] = i;
        if (components == 2)
            plane->component_mapping[1] = 2;
    }
    *out = candidate;
    return true;
fail:
    dvbridge_gl_frame_release(&candidate);
    return false;
}
