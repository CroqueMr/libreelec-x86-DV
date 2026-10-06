/* SPDX-License-Identifier: GPL-3.0-or-later */
#define _POSIX_C_SOURCE 200809L
#include "cb1_l1l3_model.h"
#include "cb1_l1l3_bundle.h"
#include <LightGBM/c_api.h>
#include <libavutil/mem.h>
#include <libavutil/sha.h>
#include <fenv.h>
#include <float.h>
#include <fcntl.h>
#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

_Static_assert(sizeof(float) == 4, "The frozen model requires binary32 normalization");
_Static_assert(CB1_L1L3_FEATURE_COUNT == 222 && CB1_L1L3_HEAD_COUNT == 6,
               "Unsupported fitted ensemble");
struct cb1_l1l3_model {
    BoosterHandle heads[CB1_L1L3_HEAD_COUNT];
    float mean[CB1_L1L3_FEATURE_COUNT], scale[CB1_L1L3_FEATURE_COUNT];
};
const char *cb1_l1l3_bundle_id(void) { return CB1_L1L3_BUNDLE_ID; }

/* Hash the same bounded bytes consumed by inference, not a second path read. */
static unsigned char *read_pinned(int directory, const char *name, const char *expected,
                                 size_t *bytes)
{
    int fd = openat(directory, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    struct stat st;
    unsigned char *data = NULL;
    struct AVSHA *sha = NULL;
    if (fd < 0)
        return NULL;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size <= 0 || st.st_size > 1024*1024)
        goto done;
    const size_t size = (size_t)st.st_size;
    data = malloc(size+1);
    if (!data)
        goto done;
    size_t offset = 0;
    while (offset < size) {
        ssize_t count = read(fd, data+offset, size-offset);
        if (count <= 0)
            goto invalid;
        offset += (size_t)count;
    }
    unsigned char trailing;
    if (read(fd, &trailing, 1) != 0)
        goto invalid;
    sha = av_sha_alloc();
    if (!sha || av_sha_init(sha, 256))
        goto invalid;
    unsigned char digest[32];
    char text[65];
    av_sha_update(sha, data, size);
    av_sha_final(sha, digest);
    for (unsigned i = 0; i < 32; ++i)
        snprintf(text+2*i, 3, "%02x", digest[i]);
    if (strcmp(text, expected))
        goto invalid;
    data[size] = 0;
    *bytes = size;
    goto done;
invalid:
    free(data);
    data = NULL;
done:
    av_free(sha);
    close(fd);
    return data;
}

void cb1_l1l3_model_close(struct cb1_l1l3_model **model)
{
    if (!model || !*model)
        return;
    for (unsigned i = 0; i < CB1_L1L3_HEAD_COUNT; ++i)
        if ((*model)->heads[i])
            LGBM_BoosterFree((*model)->heads[i]);
    free(*model);
    *model = NULL;
}

enum cb1_ai_status cb1_l1l3_model_open(const char *bundle_dir, struct cb1_l1l3_model **out)
{
    if (!bundle_dir || !out)
        return CB1_AI_INVALID;
    int directory = open(bundle_dir, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory < 0)
        return CB1_AI_INCOMPATIBLE;
    struct cb1_l1l3_model *model = calloc(1, sizeof(*model));
    enum cb1_ai_status status = CB1_AI_INCOMPATIBLE;
    if (!model) {
        status = CB1_AI_INVALID;
        goto done;
    }
    for (unsigned i = 0; i < CB1_L1L3_BUNDLE_FILES; ++i) {
        const char *name = cb1_bundle_files[i].name;
        size_t bytes = 0;
        unsigned char *data = read_pinned(directory, name, cb1_bundle_files[i].sha256, &bytes);
        if (!data)
            goto done;
        bool valid = true;
        if (!strcmp(name, "normalization.f32")) {
            valid = bytes == 2*CB1_L1L3_FEATURE_COUNT*sizeof(float);
            for (unsigned j = 0; valid && j < 2*CB1_L1L3_FEATURE_COUNT; ++j) {
                const unsigned char *p = data+4*j;
                uint32_t bits = (uint32_t)p[0] | (uint32_t)p[1]<<8 |
                                (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
                float value;
                memcpy(&value, &bits, sizeof(value));
                valid = isfinite(value) && (j < CB1_L1L3_FEATURE_COUNT || value >= 1e-6f);
                if (j < CB1_L1L3_FEATURE_COUNT)
                    model->mean[j] = value;
                else
                    model->scale[j-CB1_L1L3_FEATURE_COUNT] = value;
            }
        } else if (!strncmp(name, "field-", 6)) {
            unsigned head = (unsigned)(name[6]-'0');
            int iterations = 0, features = 0;
            valid = head < CB1_L1L3_HEAD_COUNT && !memchr(data, 0, bytes) &&
                !LGBM_BoosterLoadModelFromString((const char *)data, &iterations, &model->heads[head]) &&
                iterations > 0 && !LGBM_BoosterGetNumFeature(model->heads[head], &features) &&
                features == CB1_L1L3_FEATURE_COUNT;
        }
        free(data);
        if (!valid)
            goto done;
    }
    *out = model;
    model = NULL;
    status = CB1_AI_READY;
done:
    cb1_l1l3_model_close(&model);
    close(directory);
    return status;
}

static double bounded(double value, double low, double high)
{
    return fmin(high, fmax(low, value));
}

static double even_round(double value)
{
    double whole = floor(value), fraction = value-whole;
    return whole+(fraction > .5 || (fraction == .5 && fmod(whole, 2.) != 0.));
}

enum cb1_ai_status cb1_l1l3_project(const uint16_t base[3], const double residual[6],
                                  double peak, struct cb1_l1l3 *out)
{
    if (!base || !residual || !out || !isfinite(peak) || peak < 0 || peak > 1 ||
        base[2] > 4095 || base[0] > base[1] || base[1] > base[2])
        return CB1_AI_INVALID;
    for (unsigned i = 0; i < 6; ++i)
        if (!isfinite(residual[i]))
            return CB1_AI_INVALID;
    int rounding = fegetround();
    if (rounding < 0 || (rounding != FE_TONEAREST && fesetround(FE_TONEAREST)))
        return CB1_AI_INVALID;
    double raw[3], offsets[3];
    enum cb1_ai_status status = CB1_AI_INVALID;
    for (unsigned i = 0; i < 3; ++i) {
        raw[i] = base[i]+residual[i]*4095.;
        if (!isfinite(raw[i]))
            goto done;
        raw[i] = even_round(raw[i]);
    }
    /* These are fitted research guards, not general Dolby parsing constraints. */
    raw[0] = bounded(raw[0], 0, 12);
    raw[2] = bounded(fmax(raw[2], ceil(peak*4095.-.5)), 2081, 4095);
    raw[1] = bounded(raw[1], 819, raw[2]-1);
    for (unsigned i = 0; i < 3; ++i) {
        double q = base[i]/4095.+residual[i+3];
        offsets[i] = 2048.+(q-raw[i]/4095.)*2048.;
        if (!isfinite(offsets[i]))
            goto done;
        offsets[i] = bounded(even_round(offsets[i]), 0, 4095);
    }
    *out = (struct cb1_l1l3){.l1_min=(uint16_t)raw[0], .l1_max=(uint16_t)raw[2],
        .l1_avg=(uint16_t)raw[1], .l3_min=(uint16_t)offsets[0],
        .l3_max=(uint16_t)offsets[2], .l3_avg=(uint16_t)offsets[1]};
    status = CB1_AI_READY;
done:
    if (rounding != FE_TONEAREST)
        fesetround(rounding);
    return status;
}

enum cb1_ai_status cb1_l1l3_model_residual(struct cb1_l1l3_model *model,
    const double *features, size_t count, double out[6])
{
    if (!model || !features || !out || count != CB1_L1L3_FEATURE_COUNT)
        return CB1_AI_INVALID;
    int rounding = fegetround();
    if (rounding < 0 || (rounding != FE_TONEAREST && fesetround(FE_TONEAREST)))
        return CB1_AI_INVALID;
    float normalized[CB1_L1L3_FEATURE_COUNT];
    double residual[CB1_L1L3_HEAD_COUNT];
    enum cb1_ai_status status = CB1_AI_INVALID;
    for (unsigned i = 0; i < CB1_L1L3_FEATURE_COUNT; ++i) {
        if (!isfinite(features[i]) || fabs(features[i]) > FLT_MAX)
            goto done;
        float value = (float)features[i];
        float difference = value-model->mean[i];
        normalized[i] = difference/model->scale[i];
        if (!isfinite(value) || !isfinite(normalized[i]))
            goto done;
    }
    for (unsigned i = 0; i < CB1_L1L3_HEAD_COUNT; ++i) {
        int64_t length = 0;
        if (LGBM_BoosterPredictForMat(model->heads[i], normalized, C_API_DTYPE_FLOAT32,
                1, CB1_L1L3_FEATURE_COUNT, 1, C_API_PREDICT_NORMAL, 0, -1,
                "num_threads=1", &length, &residual[i]) || length != 1 || !isfinite(residual[i]))
            goto done;
        residual[i] *= CB1_L1L3_STRENGTH;
    }
    memcpy(out, residual, sizeof(residual));
    status = CB1_AI_READY;
done:
    if (rounding != FE_TONEAREST)
        fesetround(rounding);
    return status;
}

enum cb1_ai_status cb1_l1l3_model_predict(struct cb1_l1l3_model *model,
    const double *features, size_t count, const uint16_t base[3],
    double peak, struct cb1_l1l3 *out)
{
    if (!out)
        return CB1_AI_INVALID;
    double residual[6];
    enum cb1_ai_status status = cb1_l1l3_model_residual(model, features, count, residual);
    return status == CB1_AI_READY ? cb1_l1l3_project(base, residual, peak, out) : status;
}
