/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef CB1_HDR10_FILTER_H
#define CB1_HDR10_FILTER_H
#include <stdbool.h>
#include <stdint.h>
struct cb1_hdr10_filter { int size, length; int32_t *positions; int16_t *weights; };
/* Frozen bilinear analysis kernel; coefficients only, never CPU image processing. */
bool cb1_hdr10_filter_build(int source,int target,int precision,struct cb1_hdr10_filter *out);
void cb1_hdr10_filter_free(struct cb1_hdr10_filter *filter);
#endif
