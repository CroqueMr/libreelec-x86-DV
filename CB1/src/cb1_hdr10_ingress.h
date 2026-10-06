/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_INGRESS_H
#define CB1_HDR10_INGRESS_H
#include <libplacebo/renderer.h>
#include "cb1_l1l3_model.h"
#ifdef __cplusplus
extern "C" {
#endif
struct cb1_hdr10_ingress;
struct cb1_hdr10_ingress *cb1_hdr10_ingress_create(pl_gpu gpu);
void cb1_hdr10_ingress_destroy(struct cb1_hdr10_ingress **ctx);
/* Analysis-only RGB48 representation matching the frozen swscale producer.
 * Never use this texture as the film's rendering source. Borrowed until next
 * call/destruction; the caller retains decoded planes during submission. */
enum cb1_ai_status cb1_hdr10_ingress_rgb(struct cb1_hdr10_ingress *ctx,
    const struct pl_frame *source,pl_tex *out);
/* Direct source-plane downsampling, quantized through binary16 for the model. */
enum cb1_ai_status cb1_hdr10_ingress_small(struct cb1_hdr10_ingress *ctx,
    const struct pl_frame *source,pl_tex *out);
#ifdef __cplusplus
}
#endif
#endif
