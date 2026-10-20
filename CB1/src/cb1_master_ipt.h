/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_MASTER_IPT_H
#define CB1_MASTER_IPT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <libplacebo/gpu.h>
#ifdef __cplusplus
extern "C" {
#endif
struct cb1_master_ipt;
#ifdef CB1_ENABLE_MASTER_IPT
#define CB1_MASTER_IPT_API 1
/* Quantized IPT-PQc2 TV-led decode convention, shared with the serializer. */
extern const int16_t cb1_ipt_output_ycc[9], cb1_ipt_output_lms[9];
struct cb1_master_ipt {
    double decode[9], linear[9], encode[9], offset[3]; /* row-major */
};
bool cb1_master_ipt_prepare(struct cb1_master_ipt *out,const void *metadata,size_t bytes);
/* Input reconstructed codes / 4096. Output I, P+0.5, T+0.5, before clipping. */
void cb1_master_ipt_convert(const struct cb1_master_ipt *,const double in[3],double out[3]);
/* FP32 tables generated in double; explicit interpolation avoids sampler precision. */
bool cb1_master_ipt_tables(pl_gpu gpu,pl_tex tables[2]);
#endif
#ifdef __cplusplus
}
#endif
#endif
