/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_hdr10_features.h"
#include <math.h>
#include <fenv.h>
#include <string.h>

bool cb1_hdr10_baseline(const struct cb1_hdr10_descriptor *samples, size_t count,
                       double boundary, uint16_t out[3], double *measured_peak)
{
    if (!samples || !count || !out || !measured_peak ||
        !isfinite(samples[0].pts) || samples[0].pts < 0)
        return false;
    for (size_t i=0; i<count; ++i) {
        if (!isfinite(samples[i].pts) || samples[i].pts-samples[0].pts > 1.+1e-9 ||
            (i && samples[i].pts <= samples[i-1].pts))
            return false;
        const float *f=samples[i].global;
        if (!isfinite(f[0]) || !isfinite(f[1]) || !isfinite(f[2]) ||
            f[0] < 0 || f[1] > 1 || f[0] > f[2] || f[2] > f[1])
            return false;
    }
    if (!isnan(boundary) && (!isfinite(boundary) || boundary <= samples[count-1].pts ||
        boundary-samples[0].pts > 1.+1e-9))
        return false;
    const int rounding=fegetround();
    if (rounding < 0 || fesetround(FE_TONEAREST)) return false;
    double low=samples[0].global[0], high=samples[0].global[1], energy=0, mass=0;
    for (size_t i=0; i<count; ++i) {
        low=fmin(low,samples[i].global[0]);
        high=fmax(high,samples[i].global[1]);
        if (i+1<count) {
            const double dt=samples[i+1].pts-samples[i].pts;
            energy += dt*samples[i].global[2];
            mass += dt;
        }
    }
    const double tail=!isnan(boundary) ? boundary-samples[count-1].pts :
        count>1 ? samples[count-1].pts-samples[count-2].pts : 1./24.;
    double average=(energy+tail*samples[count-1].global[2])/(mass+tail);
    average=fmin(high,fmax(low,average));
    uint16_t result[3];
    result[0]=(uint16_t)fmin(12,nearbyint(low*4095));
    result[2]=(uint16_t)fmax(2081,nearbyint(high*4095));
    result[1]=(uint16_t)fmin(result[2]-1,fmax(819,nearbyint(average*4095)));
    if (fesetround(rounding)) return false;
    memcpy(out,result,sizeof(result));
    *measured_peak=high;
    return true;
}

static double duration(const struct cb1_hdr10_descriptor *samples, size_t count, size_t index)
{
    if (index+1 < count)
        return samples[index+1].pts-samples[index].pts;
    return count > 1 ? samples[count-1].pts-samples[count-2].pts : 1./24.;
}

/* NumPy 2.5.3 duration reduction order, BSD-3-Clause.
 * Copyright (c) 2005-2025, NumPy Developers. See LICENSES/BSD-NumPy.txt. */
static double duration_sum(const struct cb1_hdr10_descriptor *samples, size_t total,
                           size_t first, size_t count)
{
    if (count < 8) {
        double sum = -0.;
        for (size_t i = 0; i < count; ++i)
            sum += duration(samples, total, first+i);
        return sum;
    }
    if (count > 128) {
        size_t half = count/2;
        half -= half%8;
        return duration_sum(samples, total, first, half)+
               duration_sum(samples, total, first+half, count-half);
    }
    double lanes[8];
    for (unsigned j = 0; j < 8; ++j)
        lanes[j] = duration(samples, total, first+j);
    size_t i = 8;
    for (; i < count-count%8; i += 8)
        for (unsigned j = 0; j < 8; ++j)
            lanes[j] += duration(samples, total, first+i+j);
    double sum = ((lanes[0]+lanes[1])+(lanes[2]+lanes[3]))+
                 ((lanes[4]+lanes[5])+(lanes[6]+lanes[7]));
    for (; i < count; ++i)
        sum += duration(samples, total, first+i);
    return sum;
}

bool cb1_hdr10_prefix(const struct cb1_hdr10_descriptor *samples, size_t count,
                     const uint16_t base[3], bool left, bool right, float out[222])
{
    if (!samples || !count || !base || !out || base[2] > 4095 ||
        base[0] > base[1] || base[1] > base[2] ||
        !isfinite(samples[0].pts) || samples[0].pts < 0)
        return false;
    for (size_t i = 0; i < count; ++i) {
        if (!isfinite(samples[i].pts) || samples[i].pts-samples[0].pts > 1.+1e-9 ||
            (i && samples[i].pts <= samples[i-1].pts))
            return false;
        for (unsigned j = 0; j < 35; ++j)
            if (!isfinite(samples[i].global[j]))
                return false;
        for (unsigned j = 0; j < 38; ++j)
            if (!isfinite(samples[i].spatial[j]))
                return false;
    }
    double mass = duration_sum(samples, count, 0, count);
    double mean[73] = {0}, variance[73] = {0};
    float minimum[35], maximum[35], result[222];
    memcpy(minimum, samples[0].global, sizeof(minimum));
    memcpy(maximum, minimum, sizeof(maximum));
    for (size_t i = 0; i < count; ++i) {
        const double weight = duration(samples, count, i);
        for (unsigned j = 0; j < 73; ++j) {
            const double value = j < 35 ? samples[i].global[j] : samples[i].spatial[j-35];
            mean[j] += weight*value;
            if (j < 35) {
                minimum[j] = fminf(minimum[j], (float)value);
                maximum[j] = fmaxf(maximum[j], (float)value);
            }
        }
    }
    if (!isfinite(mass) || mass <= 0)
        return false;
    for (unsigned j = 0; j < 73; ++j)
        mean[j] /= mass;
    for (size_t i = 0; i < count; ++i) {
        const double weight = duration(samples, count, i);
        for (unsigned j = 0; j < 73; ++j) {
            const double value = j < 35 ? samples[i].global[j] : samples[i].spatial[j-35];
            const double delta = value-mean[j];
            variance[j] += weight*(delta*delta);
        }
    }
    for (unsigned j = 0; j < 35; ++j) {
        result[j] = (float)mean[j];
        result[35+j] = (float)sqrt(variance[j]/mass);
        result[70+j] = minimum[j];
        result[105+j] = maximum[j];
    }
    result[140] = (float)log1p(mass);
    result[141] = left;
    result[142] = right;
    for (unsigned j = 0; j < 3; ++j)
        result[143+j] = (float)(base[j]/4095.);
    for (unsigned j = 0; j < 38; ++j) {
        result[146+j] = (float)mean[35+j];
        result[184+j] = (float)sqrt(variance[35+j]/mass);
    }
    for (unsigned j = 0; j < 222; ++j)
        if (!isfinite(result[j]))
            return false;
    memcpy(out, result, sizeof(result));
    return true;
}
