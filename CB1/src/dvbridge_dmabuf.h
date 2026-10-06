/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DVBRIDGE_DMABUF_H
#define DVBRIDGE_DMABUF_H
#include "dvbridge_gl_frame.h"
#include <EGL/egl.h>
#include <libavutil/frame.h>
#include <libavutil/hwcontext_drm.h>

struct dvbridge_dmabuf {
    EGLDisplay display;
    AVFrame *mapping;
    EGLImage images[2];
    struct dvbridge_gl_plane planes[3];
    enum dvbridge_gl_layout layout;
};
bool dvbridge_dmabuf_validate_p010(const AVDRMFrameDescriptor *desc, int width, int height);
/* Current EGL/GLES context required. Does not transfer pixels through the CPU. */
bool dvbridge_dmabuf_import(struct dvbridge_dmabuf *out, const AVFrame *frame);
void dvbridge_dmabuf_release(struct dvbridge_dmabuf *frame);
#endif
