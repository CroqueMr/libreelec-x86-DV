/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2024 Niklas Haas
 * Copyright (C) 2001-2003 Michael Niedermayer <michaelni@gmx.at>
 * Bilinear-only adaptation of FFmpeg 9.0 libswscale/utils.c initFilter.
 * Retains coefficient quantization and border folding for analysis parity.
 */
#include "cb1_hdr10_filter.h"
#include <stdlib.h>
#include <string.h>

void cb1_hdr10_filter_free(struct cb1_hdr10_filter *filter)
{
    if (!filter)return;
    free(filter->positions);free(filter->weights);memset(filter,0,sizeof(*filter));
}

bool cb1_hdr10_filter_build(int source,int target,int precision,struct cb1_hdr10_filter *out)
{
    if (!out || source<4 || source>4096 || target<1 || target>128 ||
        (precision!=12 && precision!=14))return false;
    const int increment=(int)(((int64_t)source*65536+target/2)/target);
    unsigned ratio=(unsigned)(source/target),log_ratio=0;
    while(ratio>1){ratio>>=1;++log_ratio;}
    const int64_t one=1LL<<(54-(log_ratio<8?log_ratio:8));
    int taps=increment<=65536?3:1+(2*source+target-1)/target;
    if(taps>source-2)taps=source-2;
    int64_t *values=calloc((size_t)target*taps,sizeof(*values));
    int32_t *positions=calloc((size_t)target,sizeof(*positions));
    if(!values || !positions){free(values);free(positions);return false;}
    int64_t centre=increment-65536;
    for(int i=0;i<target;++i){
        positions[i]=(int32_t)((centre-(taps-2)*65536LL)/131072);
        for(int j=0;j<taps;++j){
            int64_t distance=llabs((positions[i]+j)*131072LL-centre)*8192;
            if(increment>65536)distance=distance*target/source;
            int64_t coefficient=(1LL<<30)-distance;
            values[i*taps+j]=(coefficient>0?coefficient:0)*(one>>30);
        }
        centre+=2LL*increment;
    }
    if(llabs(increment-65536)<10){
        memset(values,0,(size_t)target*taps*sizeof(*values));
        for(int i=0;i<target;++i){positions[i]=i;values[i*taps]=one;}
    }
    int reduced=0;
    for(int i=target-1;i>=0;--i){
        int used=taps;int64_t cutoff=0;
        for(int j=0;j<taps;++j){
            cutoff+=llabs(values[i*taps]);
            if(cutoff>0.002*one || (i<target-1 && positions[i]>=positions[i+1]))break;
            memmove(values+i*taps,values+i*taps+1,(size_t)(taps-1)*sizeof(*values));
            values[i*taps+taps-1]=0;++positions[i];
        }
        cutoff=0;
        for(int j=taps-1;j>0;--j){
            cutoff+=llabs(values[i*taps+j]);if(cutoff>0.002*one)break;--used;
        }
        if(used>reduced)reduced=used;
    }
    int16_t *weights=calloc((size_t)target*reduced,sizeof(*weights));
    if(!weights){free(values);free(positions);return false;}
    for(int i=0;i<target;++i){
        int64_t *v=values+i*taps;
        if(positions[i]<0){
            for(int j=1;j<reduced;++j){int left=j+positions[i];if(left<0)left=0;v[left]+=v[j];v[j]=0;}
            positions[i]=0;
        }
        if(positions[i]+reduced>source){
            int shift=positions[i]+(reduced<source?reduced-source:0);int64_t accumulator=0;
            for(int j=reduced-1;j>=0;--j)if(positions[i]+j>=source){accumulator+=v[j];v[j]=0;}
            for(int j=reduced-1;j>=0;--j)v[j]=j<shift?0:v[j-shift];
            positions[i]-=shift;v[source-1-positions[i]]+=accumulator;
        }
        int64_t sum=0,error=0;
        for(int j=0;j<reduced;++j)sum+=v[j];
        const int normalization=1<<precision;
        sum=(sum+normalization/2)/normalization;if(!sum)sum=1;
        for(int j=0;j<reduced;++j){
            int64_t value=v[j]+error;
            int64_t weight=(value+sum/2)/sum;
            if(weight<INT16_MIN || weight>INT16_MAX){free(weights);free(values);free(positions);return false;}
            weights[i*reduced+j]=(int16_t)weight;error=value-weight*sum;
        }
    }
    free(values);*out=(struct cb1_hdr10_filter){reduced,target,positions,weights};return true;
}
