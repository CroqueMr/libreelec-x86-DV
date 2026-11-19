/* SPDX-License-Identifier: GPL-2.0-or-later
 * Decision rules adapted from avdvplus/xbmc e0614d7a, BitstreamConverterDoVi.cpp
 * and HDR10PlusConvert.cpp,
 * Copyright (C) 2010-2018 Team Kodi, GPL-2.0-or-later.
 * Neutral blocks/PQ formulas adapted from quietvoid/dovi_tool d1abe0e2, MIT.
 * Copyright (c) 2026 quietvoid. See LICENSES/MIT-dovi-tool-cmv40.txt.
 */
#include "cb1_cmv40.h"
#include "dvbridge_metadata_bounds.h"
#include <libavutil/mem.h>
#include <math.h>
#include <string.h>

static unsigned mastering_nits(unsigned pq)
{
    if(pq<2055)return 96;
    switch(pq){
    case 3079:return 1000;case 3388:return 2000;case 3696:return 4000;case 4095:return 10000;
    }
    double p=pow(pq/4095.0,1.0/78.84375);
    return (unsigned)lround(10000.0*pow(fmax(p-0.8359375,0)/(18.8515625-18.6875*p),1.0/0.1593017578125));
}

enum cb1_cmv40_status cb1_cmv40_decide(const struct cb1_cmv40_options *o,
    const AVDOVIMetadata *m,size_t bytes)
{
    if(!o || !dvbridge_metadata_bounds(m,bytes) ||
       o->mode<CB1_CMV40_DISABLED || o->mode>CB1_CMV40_AUTO2 || o->headroom>50 ||
       (o->trigger && o->trigger!=1000 && o->trigger!=2000 && o->trigger!=4000 && o->trigger!=10000))
        return CB1_CMV40_INVALID;
    if(o->mode==CB1_CMV40_DISABLED)return CB1_CMV40_OFF;
    bool has_l2=false,cm4=false;const AVDOVIDmData *l1=NULL;
    for(int i=0;i<m->num_ext_blocks;i++){
        const AVDOVIDmData *b=av_dovi_get_ext(m,i);
        has_l2|=b->level==2;
        cm4|=b->level==3 || (b->level>=8 && b->level<=11) || b->level==254;
        if(b->level==1)l1=b;
    }
    if(cm4)return CB1_CMV40_EXISTING;
    if(!has_l2 || o->mode==CB1_CMV40_ALWAYS)return CB1_CMV40_APPEND;
    if(o->mode==CB1_CMV40_NO_L2)return CB1_CMV40_NOT_SELECTED;
    bool tv_valid=isfinite(o->tv_peak) && o->tv_peak>0 && o->tv_peak<=10000;
    if(o->mode==CB1_CMV40_AUTO2){
        if(!tv_valid)return CB1_CMV40_NEEDS_TV;
        /* CE appends when L1 is absent, provided the TV peak is known. */
        if(!l1)return CB1_CMV40_APPEND;
        if(l1->l1.max_pq>4095)return CB1_CMV40_INVALID;
        double n=fmin(10000,o->tv_peak*(100+o->headroom)/100.0)/10000;
        double p=pow(n,0.1593017578125);
        unsigned threshold=(unsigned)lround(4095*pow((0.8359375+18.8515625*p)/(1+18.6875*p),78.84375));
        return l1->l1.max_pq<=threshold?CB1_CMV40_APPEND:CB1_CMV40_NOT_SELECTED;
    }
    if(!o->trigger && !tv_valid)return CB1_CMV40_NEEDS_TV;
    unsigned pq=av_dovi_get_color(m)->source_max_pq;
    if(pq>4095)return CB1_CMV40_INVALID;
    double threshold=o->trigger?o->trigger:o->tv_peak;
    return mastering_nits(pq)<=threshold?CB1_CMV40_APPEND:CB1_CMV40_NOT_SELECTED;
}

bool cb1_cmv40_output(const struct cb1_cmv40_options *o,const AVDOVIMetadata *m,
    size_t bytes,bool disable_l2,AVDOVIMetadata **copy,size_t *copy_bytes,
    enum cb1_cmv40_status *status)
{
    if(!copy || !copy_bytes || !status)return false;
    *copy=NULL;*copy_bytes=0;
    *status=cb1_cmv40_decide(o,m,bytes);
    if(*status==CB1_CMV40_INVALID)return false;
    unsigned removed=0;
    if(disable_l2)for(int i=0;i<m->num_ext_blocks;i++)removed+=av_dovi_get_ext(m,i)->level==2;
    unsigned added=*status==CB1_CMV40_APPEND?4:0;
    if(!removed && !added)return true;
    unsigned count=m->num_ext_blocks-removed+added;
    if(count>AV_DOVI_MAX_EXT_BLOCKS ||
       m->ext_block_offset<sizeof(*m) || m->ext_block_offset>bytes ||
       m->ext_block_offset%_Alignof(AVDOVIDmData) ||
       m->ext_block_size<sizeof(AVDOVIDmData) || m->ext_block_size%_Alignof(AVDOVIDmData) ||
       (count && m->ext_block_size>(SIZE_MAX-m->ext_block_offset)/count))return false;
    size_t need=m->ext_block_offset+(size_t)count*m->ext_block_size;
    const size_t offsets[]={m->header_offset,m->mapping_offset,m->color_offset};
    const size_t sizes[]={sizeof(AVDOVIRpuDataHeader),sizeof(AVDOVIDataMapping),sizeof(AVDOVIColorMetadata)};
    for(unsigned i=0;i<3;i++)
        if(m->ext_block_offset<offsets[i]+sizes[i] && offsets[i]<need)return false;
    size_t capacity=bytes>need?bytes:need;
    AVDOVIMetadata *out=av_mallocz(capacity);if(!out)return false;
    memcpy(out,m,bytes);out->num_ext_blocks=0;
    for(int i=0;i<m->num_ext_blocks;i++){
        const AVDOVIDmData *b=av_dovi_get_ext(m,i);
        if(disable_l2 && b->level==2)continue;
        memcpy(av_dovi_get_ext(out,out->num_ext_blocks++),b,m->ext_block_size);
    }
    /* Same packed fields as CmV40DmData::default_safe(), no invented L8 trims. */
    static const struct {uint8_t level,length,data[5];} defaults[]={
        {3,5,{0x80,0x08,0x00,0x80,0x00}}, {9,1,{0}}, {254,2,{0,2}}, {11,4,{1,0,0,0}}
    };
    if(added)for(unsigned i=0;i<4;i++){
        AVDOVIDmData *b=av_dovi_get_ext(out,out->num_ext_blocks++);
        memset(b,0,m->ext_block_size);
        b->level=defaults[i].level;b->dvbridge_raw_magic=0x41424456;
        b->dvbridge_original_length=defaults[i].length;
        memcpy(b->dvbridge_original_bytes,defaults[i].data,defaults[i].length);
        if(b->level==3)b->l3.min_pq_offset=b->l3.max_pq_offset=b->l3.avg_pq_offset=2048;
    }
    *copy=out;*copy_bytes=capacity;return true;
}
