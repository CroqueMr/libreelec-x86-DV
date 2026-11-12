/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_MASTER_REFERENCE_H
#define CB1_MASTER_REFERENCE_H
#include <stdbool.h>
#include <stddef.h>
#include <libplacebo/renderer.h>
#ifdef __cplusplus
extern "C" {
#endif
#define CB1_MASTER_REFERENCE_API 1
enum cb1_master_status {
    CB1_MASTER_READY, CB1_MASTER_INVALID, CB1_MASTER_UNSUPPORTED,
    CB1_MASTER_GPU_UNAVAILABLE, CB1_MASTER_FAILED
};
/* Copies validated raw coefficients; no float round trip or input mutation. */
enum cb1_master_status cb1_master_reference_map(struct pl_cb1_dovi_reference *out,
    const void *metadata,size_t bytes,bool enhancement_layer_paired);
bool cb1_master_reference_transport(const void *metadata,size_t bytes);
/* Native-size RGBA32F. RGB lanes carry reconstructed source-domain codes
 * divided by (2^vdr_bit_depth - 1). An optional output hook can consume the
 * codes in the same pass before they are written to the target. Active rows
 * are optional and require the hook to blank all other rows. */
enum cb1_master_status cb1_master_reconstruct(pl_renderer renderer,
    const struct pl_frame *source,const void *metadata,size_t bytes,
    double pts,double el_pts,pl_tex target,const struct pl_hook *finish,const int active_rows[2]);
#ifdef __cplusplus
}
#endif
#endif
