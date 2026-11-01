/* SPDX-License-Identifier: GPL-2.0-or-later
 * Scalar numerical contract: docs/ALGORITHMS.md, CM2.9.
 * Input control words and PQ anchor positions are not luminance samples.
 */
#ifndef CB1_TRIM_MATH_H
#define CB1_TRIM_MATH_H
#include <math.h>
#include <stdbool.h>
#include <stddef.h>

static inline void cb1_trim_decode(double decoded[5],const double words[5])
{
    const double bias[5]={.5,-.5,.5,-.5,-.5};
    for(unsigned i=0;i<5;i++)decoded[i]=words[i]/4096+bias[i];
}

static inline double cb1_trim_weight(double position,double low,double high)
{
    if(high<=low)return position>low?1:0;
    return fmax(0,fmin(1,(position-low)/(high-low)));
}

static inline void cb1_trim_blend(double *out,const double *low,const double *high,
                                  size_t count,double weight)
{
    for(size_t i=0;i<count;i++)out[i]=low[i]+weight*(high[i]-low[i]);
}

static inline bool cb1_trim_rgb(double out[3],const double input[3],double peak,
                                const double words[5])
{
    double coefficients[5],signal[3],luma=0;
    const double weights[3]={.22897,.69174,.07929};
    cb1_trim_decode(coefficients,words);
    for(unsigned i=0;i<3;i++){
        if(!isfinite(input[i]))return false;
        double level=input[i]/peak*coefficients[0]+coefficients[1];
        signal[i]=peak*pow(fmax(0,fmin(1,level)),coefficients[2]);
        luma+=weights[i]*signal[i];
    }
    for(unsigned i=0;i<3;i++){
        out[i]=signal[i];
        if(coefficients[4]!=0 && luma>0 && signal[i]>0)
            out[i]*=pow((1+coefficients[3])*signal[i]/luma,coefficients[4]);
    }
    return isfinite(out[0]) && isfinite(out[1]) && isfinite(out[2]);
}
#endif
