// SPDX-License-Identifier: MIT
#ifndef CB1_LLDV_CPU_H
#define CB1_LLDV_CPU_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct cb1_lldv_cpu;

/* The caller owns GPU completion, DMA-BUF synchronization and buffer lifetime.
 * Input is a complete 3840x2160 RGBA32F image. The output is a linear 4-byte
 * carrier with a 32-byte-aligned pointer and byte stride. NULL matrix is BT.2020. */
struct cb1_lldv_cpu_frame {
    const float *linear;
    uint32_t *carrier;
    size_t stride;
    const float *to_bt2020; /* row-major 3x3, copied on submit */
    float peak_nits;
    unsigned bits;
    bool xrgb;
    bool flip_y;
};

struct cb1_lldv_cpu *cb1_lldv_cpu_create(unsigned threads);
bool cb1_lldv_cpu_submit(struct cb1_lldv_cpu *cpu, const struct cb1_lldv_cpu_frame *frame);
bool cb1_lldv_cpu_ready(struct cb1_lldv_cpu *cpu, bool wait);
void cb1_lldv_cpu_destroy(struct cb1_lldv_cpu *cpu);

#ifdef __cplusplus
}
#endif
#endif
