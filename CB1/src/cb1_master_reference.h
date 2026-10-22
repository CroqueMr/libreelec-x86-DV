/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_MASTER_REFERENCE_H
#define CB1_MASTER_REFERENCE_H
#include <stdbool.h>
#include <stddef.h>
#include <libplacebo/colorspace.h>
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
#ifdef __cplusplus
}
#endif
#endif
