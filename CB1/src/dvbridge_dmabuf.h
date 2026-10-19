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
    int width, height;
};
struct dvbridge_dmabuf_key {
    uint64_t display, context, pool, width, height, objects_count;
    uint64_t objects[AV_DRM_MAX_PLANES][4];
    uint64_t layers[2][5];
};
bool dvbridge_dmabuf_make_key(struct dvbridge_dmabuf_key *out,
    const AVDRMFrameDescriptor *desc, int width, int height, const void *pool,
    EGLDisplay display, EGLContext context);
bool dvbridge_dmabuf_key_equal(const struct dvbridge_dmabuf_key *a,
                              const struct dvbridge_dmabuf_key *b);
bool dvbridge_dmabuf_validate_p010(const AVDRMFrameDescriptor *desc, int width, int height);
/* Current EGL/GLES context required. Does not transfer pixels through the CPU. */
bool dvbridge_dmabuf_import(struct dvbridge_dmabuf *out, const AVFrame *frame);
/* Mapping synchronizes each new decoder picture even when its EGL import is reused. */
bool dvbridge_dmabuf_map(struct dvbridge_dmabuf *out, const AVFrame *frame);
bool dvbridge_dmabuf_import_mapped(struct dvbridge_dmabuf *frame);
void dvbridge_dmabuf_release(struct dvbridge_dmabuf *frame);
#endif
