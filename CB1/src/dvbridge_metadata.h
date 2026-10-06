/* SPDX-License-Identifier: GPL-3.0-or-later
 * Player-independent metadata serializer derived from the reviewed mpv adapter.
 */
#ifndef MPV_DVBRIDGE_DV_H
#define MPV_DVBRIDGE_DV_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <libavutil/dovi_meta.h>
#include "dvbridge_metadata_bounds.h"
#include "mpv_dvbridge_cm4.h"
#include <stdio.h>

struct dvbridge_dv {
    uint8_t payload[512], previous[512];
    unsigned size, previous_size, id;
    uint32_t packets[512], count;
    uint64_t frames, changes;
    double last_pts;
    int source_w, source_h, dest_x, dest_y, dest_w, dest_h;
    bool fel_verified;
    unsigned compatibility_omissions;
};
#define DV_REQUIRE(x) do { if (!(x)) return false; } while (0)
static inline bool dvbridge_dv_bounds(const AVDOVIMetadata *m, size_t bytes)
{
    return dvbridge_metadata_bounds(m, bytes) && m->num_ext_blocks > 0;
}
/* All scaling/letterboxing precedes transport packing. L5 describes the
 * final HDMI raster, not the dimensions of a cropped source file. */
static inline bool dvbridge_dv_geometry(struct dvbridge_dv *d, int w, int h,
                              int x, int y, int dw, int dh)
{
    DV_REQUIRE(w > 0 && h > 0 && w <= 3840 && h <= 2160);
    DV_REQUIRE(dw > 0 && dh > 0 && x >= 0 && y >= 0 && x+dw <= 3840 && y+dh <= 2160);
    DV_REQUIRE(!(x & 1) && !(dw & 1));
    DV_REQUIRE(fabs((double)dw*h/w - dh) <= 1.01);
    d->source_w=w;d->source_h=h;d->dest_x=x;d->dest_y=y;d->dest_w=dw;d->dest_h=dh;
    return true;
}
static inline bool dvbridge_dv_area(struct dvbridge_dv *d, unsigned l, unsigned r,
                          unsigned t, unsigned b, unsigned v[4])
{
    int w=d->source_w ? d->source_w : 3840, h=d->source_h ? d->source_h : 2160;
    int dw=d->dest_w ? d->dest_w : 3840, dh=d->dest_h ? d->dest_h : 2160;
    DV_REQUIRE(l < (unsigned)w && r < (unsigned)w-l && t < (unsigned)h && b < (unsigned)h-t);
    v[0]=d->dest_x+lround((double)l*dw/w);
    v[1]=3840-d->dest_x-dw+lround((double)r*dw/w);
    v[2]=d->dest_y+lround((double)t*dh/h);
    v[3]=2160-d->dest_y-dh+lround((double)b*dh/h);
    return v[0]+v[1]<3840 && v[2]+v[3]<2160;
}
/* Same canonical no-residual criterion as libplacebo's DOVI mapper.
 * P7 MEL can carry disable_residual_flag=0 while its NLQ is exactly trivial.
 * Do not mistake it for FEL, and do not accept non-trivial NLQ without EL.
 * Caller already validated the metadata buffer and its mapping region. */
static inline bool dvbridge_dv_is_mel(const AVDOVIMetadata *m)
{
    if (!m) return false;
    const AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    const AVDOVIDataMapping *map=av_dovi_get_mapping(m);
    if (h->disable_residual_flag || h->coef_log2_denom > 32 ||
        map->nlq_method_idc != AV_DOVI_NLQ_LINEAR_DZ) return false;
    uint64_t maximum=UINT64_C(1) << h->coef_log2_denom;
    for (int c=0;c<3;c++) {
        const AVDOVINLQParams *n=&map->nlq[c];
        if (n->nlq_offset || n->vdr_in_max != maximum ||
            n->linear_deadzone_slope || n->linear_deadzone_threshold) return false;
    }
    return true;
}
static inline void dvbridge_dv_u16(struct dvbridge_dv *d, unsigned v)
{ d->payload[d->size++] = v >> 8; d->payload[d->size++] = v; }
static inline void dvbridge_dv_u32(struct dvbridge_dv *d, unsigned v)
{ dvbridge_dv_u16(d, v >> 16); dvbridge_dv_u16(d, v & 65535); }
static inline uint32_t dvbridge_dv_crc(const uint8_t *p, size_t n)
{
    uint32_t c = 0xffffffff;
    for (size_t j = 0; j < n; j++) {
        c ^= (uint32_t)p[j] << 24;
        for (int i = 0; i < 8; i++) c = (c << 1) ^ ((c >> 31) ? 0x04c11db7u : 0);
    }
    return c;
}
/* Called with metadata from the exact pl_frame being rendered, not the
 * decoder's newest frame. Repeated PTS keeps a stable payload while paused.
 * A discontinuity forces scene refresh; no stale RPU across a seek. */
static inline bool dvbridge_dv_metadata_output(struct dvbridge_dv *d, const AVDOVIMetadata *m,
                                       double pts, const unsigned margins[4], bool force_refresh)
{
    DV_REQUIRE(m && isfinite(pts));
    const AVDOVIColorMetadata *c = av_dovi_get_color(m);
    const AVDOVIRpuDataHeader *h = av_dovi_get_header(m);
    DV_REQUIRE(c && h && (h->disable_residual_flag == 1 || d->fel_verified || dvbridge_dv_is_mel(m)));
    DV_REQUIRE(c->signal_eotf == 65535 && (c->signal_color_space == 0 || c->signal_color_space == 2));
    DV_REQUIRE(!c->signal_eotf_param0 && !c->signal_eotf_param1 && !c->signal_eotf_param2);
    DV_REQUIRE(c->source_min_pq <= c->source_max_pq && c->source_max_pq <= 4095);
    DV_REQUIRE(m->num_ext_blocks > 0 && m->num_ext_blocks <= AV_DOVI_MAX_EXT_BLOCKS);
    bool repeat = d->frames && pts == d->last_pts;
    bool refresh = !d->frames || pts < d->last_pts || pts - d->last_pts > 0.1;
    d->size = 0;
    d->payload[d->size++] = 0;
    d->payload[d->size++] = force_refresh ? 1 : repeat ? d->previous[1] : refresh ? 1 : c->scene_refresh_flag;
    const int matrix[] = {9574,0,13802,9574,-1540,-5348,9574,17610,0};
    const unsigned lms[] = {7222,8771,390,2654,12430,1300,0,422,15962};
    for (int i = 0; i < 9; i++) dvbridge_dv_u16(d, (uint16_t)matrix[i]);
    dvbridge_dv_u32(d, 16777216); dvbridge_dv_u32(d, 134217728); dvbridge_dv_u32(d, 134217728);
    for (int i = 0; i < 9; i++) dvbridge_dv_u16(d, lms[i]);
    dvbridge_dv_u16(d, 65535); dvbridge_dv_u32(d, 0); dvbridge_dv_u32(d, 0);
    d->payload[d->size++] = 12; d->payload[d->size++] = 0;
    d->payload[d->size++] = 1; d->payload[d->size++] = 1;
    dvbridge_dv_u16(d, c->source_min_pq); dvbridge_dv_u16(d, c->source_max_pq);
    dvbridge_dv_u16(d, 42);
    unsigned count_pos = d->size++;
    d->payload[count_pos] = 0;
    unsigned l1 = 0, area = 0, targets[AV_DOVI_MAX_EXT_BLOCKS], ntargets = 0;
    const AVDOVIDmData *ordered[AV_DOVI_MAX_EXT_BLOCKS];
    unsigned order[AV_DOVI_MAX_EXT_BLOCKS];
    for(int i=0;i<m->num_ext_blocks;i++) {
        const AVDOVIDmData *e=av_dovi_get_ext(m,i);
        unsigned rank=e->level;
        if(e->level==3 || (e->level>=8 && e->level<=11) || e->level==254)rank+=256;
        int j=i;
        while(j>0 && order[j-1]>rank) {ordered[j]=ordered[j-1];order[j]=order[j-1];j--;}
        ordered[j]=e;order[j]=rank;
    }
    for (int i = 0; i < m->num_ext_blocks; i++) {
        const AVDOVIDmData *e = ordered[i];
        unsigned v[7] = {0}, n = 0;
        DV_REQUIRE(d->size + 20 < sizeof(d->payload));
        switch (e->level) {
        case 1:
            DV_REQUIRE(!area); l1++; n = 3;
            v[0] = e->l1.min_pq; v[1] = e->l1.max_pq; v[2] = e->l1.avg_pq;
            DV_REQUIRE(v[0] <= v[2] && v[2] <= v[1]); break;
        case 2:
            DV_REQUIRE(!area); n = 7;
            v[0] = e->l2.target_max_pq; v[1] = e->l2.trim_slope; v[2] = e->l2.trim_offset;
            v[3] = e->l2.trim_power; v[4] = e->l2.trim_chroma_weight;
            v[5] = e->l2.trim_saturation_gain; v[6] = (uint16_t)e->l2.ms_weight;
            for (unsigned j = 0; j < ntargets; j++) DV_REQUIRE(targets[j] != v[0]);
            targets[ntargets++] = v[0]; break;
        case 5:
            area++; DV_REQUIRE(l1 == 1 && area == 1); n = 4;
            memcpy(v, margins, 4 * sizeof(*margins)); break;
        case 4: case 3: case 8: case 9: case 10: case 11: case 254: {
            uint8_t wire[32];
            DV_REQUIRE(e->dvbridge_raw_magic==0x41424456);
            int size=dvbridge_cm4_wire(e->level,e->dvbridge_original_bytes,e->dvbridge_original_length,wire);
            if(size<0) {
                fprintf(stderr,"DVBRIDGE_CM4_REJECT level=%d length=%u\n",e->level,e->dvbridge_original_length);
                return false;
            }
            DV_REQUIRE(d->size+5+size<=482);
            dvbridge_dv_u32(d,size);d->payload[d->size++]=e->level;
            memcpy(d->payload+d->size,wire,size);d->size+=size;d->payload[count_pos]++;
            continue;
        }
        case 6: continue; /* Static HDR10 fallback, not dynamic DV wire data. */
        default: fprintf(stderr,"DVBRIDGE_DV_UNSUPPORTED_METADATA level=%d\n",e->level); return false;
        }
        for (unsigned j = 0; j < n; j++)
            DV_REQUIRE(v[j] <= 4095 || (e->level == 2 && j == 6 && v[j] == 65535));
        dvbridge_dv_u32(d, n * 2); d->payload[d->size++] = e->level;
        for (unsigned j = 0; j < n; j++) dvbridge_dv_u16(d, v[j]);
        d->payload[count_pos]++;
    }
    DV_REQUIRE(l1 == 1);
    if (!area) {
        DV_REQUIRE(d->size+13 < sizeof(d->payload));
        dvbridge_dv_u32(d,8);d->payload[d->size++]=5;
        for (int j=0;j<4;j++) dvbridge_dv_u16(d,margins[j]);
        d->payload[count_pos]++;
    }
    DV_REQUIRE(d->size<=482 && d->payload[count_pos]<=AV_DOVI_MAX_EXT_BLOCKS);
    if (d->frames && (d->previous_size != d->size || memcmp(d->previous, d->payload, d->size))) {
        d->id = (d->id + 1) & 15; d->changes++;
    }
    memcpy(d->previous, d->payload, d->size); d->previous_size = d->size;
    d->count = d->size <= 119 ? 1 : 1 + (d->size - 119 + 120) / 121;
    DV_REQUIRE(d->count <= 4);
    memset(d->packets, 0, sizeof(d->packets));
    unsigned off = 0;
    for (unsigned i = 0; i < d->count; i++) {
        uint8_t p[128] = {0};
        p[0] = (d->count == 1 ? 0 : i == 0 ? 1 : i + 1 == d->count ? 3 : 2) << 6;
        p[1] = (d->id << 4) | d->id;
        unsigned start = i ? 3 : 5, room = i ? 121 : 119;
        unsigned take = d->size - off; if (take > room) take = room;
        if (!i) { p[3] = d->size >> 8; p[4] = d->size; }
        memcpy(p + start, d->payload + off, take); off += take;
        uint32_t crc = dvbridge_dv_crc(p, 124);
        for (int j = 0; j < 4; j++) p[124+j] = crc >> (24-j*8);
        DV_REQUIRE(!dvbridge_dv_crc(p, 128));
        for (unsigned j = 0; j < 128; j++) d->packets[i*128+j] = p[j];
    }
    d->last_pts = pts; d->frames++;
    return true;
}

static inline bool dvbridge_dv_metadata(struct dvbridge_dv *d, const AVDOVIMetadata *m,
                                       double pts, const unsigned margins[4])
{
    return dvbridge_dv_metadata_output(d,m,pts,margins,false);
}


#endif
