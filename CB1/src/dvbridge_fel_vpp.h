/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DVBRIDGE_FEL_VPP_H
#define DVBRIDGE_FEL_VPP_H
#include "dvbridge_gl_frame.h"
#include <libavutil/frame.h>

struct dvbridge_fel_vpp;
struct dvbridge_fel_vpp_image {
    struct dvbridge_gl_plane plane;
    int width, height;
};
enum dvbridge_fel_vpp_result { DVBRIDGE_VPP_OK, DVBRIDGE_VPP_BUSY, DVBRIDGE_VPP_FAILED, DVBRIDGE_VPP_PENDING };

/* One GL thread/context. Two reusable Y416 surfaces, no CPU pixel transfers.
 * Release each image only after the caller's GPU source-read fence completes. */
struct dvbridge_fel_vpp *dvbridge_fel_vpp_create(AVBufferRef *device, int width, int height);
enum dvbridge_fel_vpp_result dvbridge_fel_vpp_acquire(struct dvbridge_fel_vpp *vpp,
    const AVFrame *source, const struct dvbridge_fel_vpp_image **image);
enum dvbridge_fel_vpp_result dvbridge_fel_vpp_acquire_chroma(struct dvbridge_fel_vpp *vpp,
    const AVFrame *source, enum pl_chroma_location chroma,
    const struct dvbridge_fel_vpp_image **image);
/* PENDING reserves one existing surface and retains its input. Finish before
 * importing/sampling the image. Release also finishes abandoned submissions. */
enum dvbridge_fel_vpp_result dvbridge_fel_vpp_prefetch_chroma(struct dvbridge_fel_vpp *vpp,
    const AVFrame *source, enum pl_chroma_location chroma,
    const struct dvbridge_fel_vpp_image **image);
enum dvbridge_fel_vpp_result dvbridge_fel_vpp_finish(struct dvbridge_fel_vpp *vpp,
    const struct dvbridge_fel_vpp_image *image);
void dvbridge_fel_vpp_release(struct dvbridge_fel_vpp *vpp, const struct dvbridge_fel_vpp_image *image);
/* Refuses destruction while a surface is leased. */
bool dvbridge_fel_vpp_destroy(struct dvbridge_fel_vpp **vpp);
#endif
