/* SPDX-License-Identifier: GPL-3.0-or-later */
#define _POSIX_C_SOURCE 200809L
#include "cb1_l1l3_model.h"
#include "cb1_native_fixtures.h"
#include <assert.h>
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void unchanged(struct cb1_l1l3_model *model, const double *features,
                      size_t count, const uint16_t base[3], double peak)
{
    struct cb1_l1l3 out;
    memset(&out, 0x5a, sizeof(out));
    const struct cb1_l1l3 before = out;
    assert(cb1_l1l3_model_predict(model, features, count, base, peak, &out) != CB1_AI_READY);
    assert(memcmp(&out, &before, sizeof(out)) == 0);
}

int main(int argc, char **argv)
{
    if (argc == 3 && !strcmp(argv[2], "reject")) {
        struct cb1_l1l3_model *sentinel = (void *)1;
        assert(cb1_l1l3_model_open(argv[1], &sentinel) == CB1_AI_INCOMPATIBLE);
        assert(sentinel == (void *)1);
        return 0;
    }
    assert(argc == 2);
    struct cb1_l1l3_model *model = NULL;
    assert(cb1_l1l3_model_open(argv[1], &model) == CB1_AI_READY && model);
    for (size_t i = 0; i < sizeof(cb1_native_fixtures)/sizeof(cb1_native_fixtures[0]); ++i) {
        const struct cb1_native_fixture *f = &cb1_native_fixtures[i];
        struct cb1_l1l3 out;
        double residual[6];
        assert(cb1_l1l3_model_residual(model, f->features, 222, residual) == CB1_AI_READY);
        for (unsigned head = 0; head < 6; ++head)
            assert(fabs(residual[head]-f->residual[head]) <=
                   150*DBL_EPSILON*(1+fabs(f->residual[head])));
        assert(cb1_l1l3_model_predict(model, f->features, 222, f->base, f->peak, &out) == CB1_AI_READY);
        const uint16_t actual[] = {out.l1_min, out.l1_max, out.l1_avg,
                                   out.l3_min, out.l3_max, out.l3_avg};
        assert(memcmp(actual, f->raw, sizeof(actual)) == 0);
        struct cb1_l1l3 projected;
        assert(cb1_l1l3_project(f->base, f->residual, f->peak, &projected) == CB1_AI_READY);
        assert(memcmp(&projected, &out, sizeof(out)) == 0);
    }
    const struct cb1_native_fixture *f = &cb1_native_fixtures[0];
    unchanged(model, f->features, 221, f->base, f->peak);
    unchanged(model, f->features, 223, f->base, f->peak);
    unchanged(model, NULL, 222, f->base, f->peak);
    unchanged(NULL, f->features, 222, f->base, f->peak);
    unchanged(model, f->features, 222, f->base, NAN);
    unchanged(model, f->features, 222, f->base, -0.01);
    unchanged(model, f->features, 222, f->base, 1.01);
    uint16_t invalid_base[] = {4096, 819, 2081};
    unchanged(model, f->features, 222, invalid_base, .5);
    double changed[222];
    memcpy(changed, f->features, sizeof(changed));
    changed[0] = DBL_MAX;
    unchanged(model, changed, 222, f->base, f->peak);
    changed[0] = -DBL_MAX;
    unchanged(model, changed, 222, f->base, f->peak);
    changed[0] = f->features[0];
    for (size_t i = 0; i < 222; ++i) {
        const double original = changed[i];
        changed[i] = NAN;
        unchanged(model, changed, 222, f->base, f->peak);
        changed[i] = INFINITY;
        unchanged(model, changed, 222, f->base, f->peak);
        changed[i] = original;
    }
    /* Rounding must not depend on a caller's floating-point environment. */
    uint16_t base[] = {0, 1000, 3000};
    double residual[] = {2.5/4095, 0, 0, 0, 0, 0};
    for (int i = 0; i < 3; ++i) {
        const int rounding[] = {FE_TONEAREST, FE_UPWARD, FE_DOWNWARD};
        assert(fesetround(rounding[i]) == 0);
        struct cb1_l1l3 out;
        assert(cb1_l1l3_project(base, residual, .5, &out) == CB1_AI_READY);
        assert(out.l1_min == 2 && fegetround() == rounding[i]);
    }
    assert(fesetround(FE_TONEAREST) == 0);
    cb1_l1l3_model_close(&model);
    assert(!model);
    cb1_l1l3_model_close(&model);
    cb1_l1l3_model_close(NULL);
    for (int i = 0; i < 20; ++i) {
        assert(cb1_l1l3_model_open(argv[1], &model) == CB1_AI_READY);
        cb1_l1l3_model_close(&model);
    }
    struct cb1_l1l3_model *sentinel = (void *)1;
    assert(cb1_l1l3_model_open("/missing-cb1-bundle", &sentinel) == CB1_AI_INCOMPATIBLE);
    assert(sentinel == (void *)1);
    assert(cb1_l1l3_model_open(NULL, &sentinel) == CB1_AI_INVALID);
    assert(sentinel == (void *)1);
    assert(cb1_l1l3_model_open(argv[1], NULL) == CB1_AI_INVALID);
    printf("Exact native parity: %zu independent cases\n",
           sizeof(cb1_native_fixtures)/sizeof(cb1_native_fixtures[0]));
    return 0;
}
