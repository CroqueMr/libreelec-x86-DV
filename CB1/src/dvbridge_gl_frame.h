/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DVBRIDGE_GL_FRAME_H
#define DVBRIDGE_GL_FRAME_H
#include <libplacebo/opengl.h>
#include <libplacebo/renderer.h>

enum dvbridge_gl_layout {
    DVBRIDGE_NV12, DVBRIDGE_P010, DVBRIDGE_P012, DVBRIDGE_P016,
    DVBRIDGE_YUV420P10, DVBRIDGE_YUV444P10,
};
struct dvbridge_gl_plane {
    unsigned texture;
    int width, height;
};
struct dvbridge_gl_frame {
    pl_gpu gpu;
    struct pl_frame frame;
};
/* Current GL context required. The decoder retains ownership of all textures. */
bool dvbridge_gl_frame_import(struct dvbridge_gl_frame *out, pl_gpu gpu,
                             enum dvbridge_gl_layout layout, int width, int height,
                             const struct dvbridge_gl_plane planes[3]);
void dvbridge_gl_frame_release(struct dvbridge_gl_frame *frame);
#endif
