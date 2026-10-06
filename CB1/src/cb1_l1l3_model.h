/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_L1L3_MODEL_H
#define CB1_L1L3_MODEL_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum cb1_ai_status {
    CB1_AI_READY, CB1_AI_PENDING, CB1_AI_INVALID, CB1_AI_INCOMPATIBLE
};
struct cb1_ai_identity {
    uint64_t stream, picture, revision;
};
struct cb1_l1l3 {
    uint16_t l1_min, l1_max, l1_avg;
    uint16_t l3_min, l3_max, l3_avg;
};
struct cb1_l1l3_model;
const char *cb1_l1l3_bundle_id(void);
/* Caller-confined. Failure leaves output pointers and values unchanged. */
enum cb1_ai_status cb1_l1l3_model_open(const char *bundle_dir, struct cb1_l1l3_model **out);
void cb1_l1l3_model_close(struct cb1_l1l3_model **model);
/* Evaluate once per calibrated span; project its correction per picture. */
enum cb1_ai_status cb1_l1l3_model_residual(struct cb1_l1l3_model *model,
    const double *features, size_t count, double out[6]);
enum cb1_ai_status cb1_l1l3_model_predict(struct cb1_l1l3_model *model,
    const double *features, size_t count, const uint16_t base[3],
    double measured_peak_pq, struct cb1_l1l3 *out);
/* Research projection: base and residual coordinates use min/avg/max order. */
enum cb1_ai_status cb1_l1l3_project(const uint16_t base[3], const double residual[6],
                                  double measured_peak_pq, struct cb1_l1l3 *out);
#ifdef __cplusplus
}
#endif
#endif
