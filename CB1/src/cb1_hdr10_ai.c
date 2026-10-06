/* SPDX-License-Identifier: GPL-3.0-or-later */
#define _POSIX_C_SOURCE 200809L
#include "cb1_hdr10_ai.h"
#include "cb1_hdr10_ingress.h"
#include "cb1_hdr10_statistics.h"
#include "cb1_hdr10_quantiles.h"
#include "cb1_hdr10_spatial.h"
#include "cb1_hdr10_temporal.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

struct cb1_hdr10_ai {
    struct cb1_l1l3_model *model;
    struct cb1_hdr10_ingress *ingress;
    struct cb1_hdr10_extrema *extrema;
    struct cb1_hdr10_statistics *statistics;
    struct cb1_hdr10_quantiles *quantiles;
    struct cb1_hdr10_spatial *spatial;
    struct cb1_hdr10_temporal *temporal;
    uint64_t stream,revision;
    bool active,pending,failed,ended,bounded,statistics_ready,quantiles_ready,spatial_ready;
    bool last_valid,result_valid,residual_valid;
    struct cb1_ai_identity id,last;
    double pts,last_pts;
    pl_tex rgb;
    struct cb1_hdr10_descriptor descriptor;
    struct cb1_hdr10_spatial_result spatial_result;
    float quantile_values[7];
    float calibration[222];double residual[6];
    struct cb1_ai_result result;
    struct cb1_hdr10_ai_metrics metrics;
    uint64_t submitted_ns;
};
static uint64_t now_ns(void)
{
    struct timespec now;
    return clock_gettime(CLOCK_MONOTONIC,&now) ? 0 :
        (uint64_t)now.tv_sec*1000000000+(uint64_t)now.tv_nsec;
}
static uint64_t elapsed_ns(uint64_t start)
{ uint64_t end=now_ns();return start && end>=start ? end-start : 0; }
static bool same(struct cb1_ai_identity a,struct cb1_ai_identity b)
{ return a.stream==b.stream && a.picture==b.picture && a.revision==b.revision; }
void cb1_hdr10_ai_destroy(struct cb1_hdr10_ai **ctx)
{
    if(!ctx || !*ctx)return;
    struct cb1_hdr10_ai *c=*ctx;
    cb1_hdr10_spatial_destroy(&c->spatial);cb1_hdr10_quantiles_destroy(&c->quantiles);
    cb1_hdr10_statistics_destroy(&c->statistics);cb1_hdr10_extrema_destroy(&c->extrema);
    cb1_hdr10_ingress_destroy(&c->ingress);cb1_hdr10_temporal_destroy(&c->temporal);
    cb1_l1l3_model_close(&c->model);free(c);*ctx=NULL;
}
enum cb1_ai_status cb1_hdr10_ai_create(pl_gpu gpu,const char *bundle,struct cb1_hdr10_ai **out)
{
    if(!gpu || !bundle || !out)return CB1_AI_INVALID;
    struct cb1_hdr10_ai *c=calloc(1,sizeof(*c));if(!c)return CB1_AI_INVALID;
    enum cb1_ai_status status=cb1_l1l3_model_open(bundle,&c->model);
    if(status!=CB1_AI_READY)goto fail;
    c->ingress=cb1_hdr10_ingress_create(gpu);c->extrema=cb1_hdr10_extrema_create(gpu);
    c->statistics=cb1_hdr10_statistics_create(gpu);c->quantiles=cb1_hdr10_quantiles_create(gpu);
    c->spatial=cb1_hdr10_spatial_create(gpu);c->temporal=cb1_hdr10_temporal_create();
    if(!c->ingress || !c->extrema || !c->statistics || !c->quantiles || !c->spatial || !c->temporal){
        status=CB1_AI_INCOMPATIBLE;goto fail;
    }
    *out=c;return CB1_AI_READY;
fail:
    cb1_hdr10_ai_destroy(&c);return status;
}
void cb1_hdr10_ai_reset(struct cb1_hdr10_ai *c,uint64_t stream,uint64_t revision)
{
    if(!c)return;
    c->stream=stream;c->revision=revision;c->active=true;c->pending=c->ended=c->failed=false;
    c->last_valid=c->result_valid=c->residual_valid=false;
    c->bounded=c->statistics_ready=c->quantiles_ready=c->spatial_ready=false;
    cb1_hdr10_extrema_reset(c->extrema,stream,revision);
    cb1_hdr10_statistics_reset(c->statistics,stream,revision);
    cb1_hdr10_quantiles_reset(c->quantiles,stream,revision);
    cb1_hdr10_spatial_reset(c->spatial,stream,revision);
    cb1_hdr10_temporal_reset(c->temporal,stream,revision);
}
static enum cb1_ai_status collect(struct cb1_hdr10_ai *c)
{
    if(c->failed)return CB1_AI_INVALID;
    if(!c->pending)return CB1_AI_READY;
    enum cb1_ai_status status;
    if(!c->bounded){
        struct cb1_hdr10_bounds bounds;
        status=cb1_hdr10_extrema_poll(c->extrema,c->id,&bounds);
        if(status==CB1_AI_PENDING)return status;
        if(status!=CB1_AI_READY)goto fail;
        c->metrics.readback_bytes+=16;
        const uint64_t dispatch=now_ns();
        ++c->metrics.gpu_submissions;
        status=cb1_hdr10_statistics_submit(c->statistics,c->rgb,bounds,c->id);
        if(status!=CB1_AI_PENDING)goto fail;
        status=cb1_hdr10_quantiles_submit(c->quantiles,c->rgb,bounds,c->id);
        if(status!=CB1_AI_PENDING)goto fail;
        c->bounded=true;
        c->metrics.analysis_submit_ns+=elapsed_ns(dispatch);
    }
    if(!c->statistics_ready){
        status=cb1_hdr10_statistics_poll(c->statistics,c->id,c->descriptor.global);
        if(status!=CB1_AI_READY && status!=CB1_AI_PENDING)goto fail;
        if(status==CB1_AI_READY){c->statistics_ready=true;c->metrics.readback_bytes+=128;}
    }
    if(!c->quantiles_ready){
        status=cb1_hdr10_quantiles_poll(c->quantiles,c->id,c->quantile_values);
        if(status!=CB1_AI_READY && status!=CB1_AI_PENDING)goto fail;
        if(status==CB1_AI_READY){c->quantiles_ready=true;c->metrics.readback_bytes+=56;}
    }
    if(!c->spatial_ready){
        status=cb1_hdr10_spatial_poll(c->spatial,c->id,&c->spatial_result);
        if(status!=CB1_AI_READY && status!=CB1_AI_PENDING)goto fail;
        if(status==CB1_AI_READY){c->spatial_ready=true;c->metrics.readback_bytes+=7072;}
    }
    if(!c->statistics_ready || !c->quantiles_ready || !c->spatial_ready)return CB1_AI_PENDING;
    if(c->submitted_ns){
        c->metrics.readback_latency_ns+=elapsed_ns(c->submitted_ns);c->submitted_ns=0;
    }
    memcpy(c->descriptor.global+4,c->quantile_values,sizeof(c->quantile_values));
    memcpy(c->descriptor.spatial,c->spatial_result.features,sizeof(c->descriptor.spatial));
    status=cb1_hdr10_temporal_push(c->temporal,&c->descriptor,c->spatial_result.motion,c->id);
    if(status==CB1_AI_PENDING)return status;
    if(status!=CB1_AI_READY)goto fail;
    c->last=c->id;c->last_pts=c->pts;c->last_valid=true;c->pending=false;++c->metrics.pictures;
    if(c->ended)cb1_hdr10_temporal_end(c->temporal);
    return CB1_AI_READY;
fail:
    c->failed=true;return status==CB1_AI_INCOMPATIBLE?status:CB1_AI_INVALID;
}
enum cb1_ai_status cb1_hdr10_ai_submit(struct cb1_hdr10_ai *c,const struct pl_frame *frame,
    struct cb1_ai_identity id,double pts)
{
    if(!c || !c->active || c->failed || id.stream!=c->stream || id.revision!=c->revision ||
        !isfinite(pts) || pts<0)return CB1_AI_INVALID;
    enum cb1_ai_status status=collect(c);if(status!=CB1_AI_READY)return status;
    if(c->last_valid && same(id,c->last))return pts==c->last_pts?CB1_AI_READY:CB1_AI_INVALID;
    if(!frame || c->ended || (c->last_valid && (id.picture<=c->last.picture || pts<=c->last_pts)))return CB1_AI_INVALID;
    const uint64_t dispatch=now_ns();
    ++c->metrics.gpu_submissions;
    status=cb1_hdr10_ingress_rgb(c->ingress,frame,&c->rgb);if(status!=CB1_AI_READY)goto submit_fail;
    pl_tex small;
    status=cb1_hdr10_ingress_small(c->ingress,frame,&small);if(status!=CB1_AI_READY)goto submit_fail;
    status=cb1_hdr10_extrema_submit(c->extrema,c->rgb,id);if(status!=CB1_AI_PENDING)goto submit_fail;
    status=cb1_hdr10_spatial_submit(c->spatial,small,id);
    if(status!=CB1_AI_PENDING)goto submit_fail;
    c->id=id;c->pts=pts;c->descriptor=(struct cb1_hdr10_descriptor){.pts=pts};
    c->bounded=c->statistics_ready=c->quantiles_ready=c->spatial_ready=false;
    c->submitted_ns=dispatch;c->metrics.analysis_submit_ns+=elapsed_ns(dispatch);
    c->pending=true;return CB1_AI_PENDING;
submit_fail:
    c->failed=true;return status;
}
enum cb1_ai_status cb1_hdr10_ai_advance(struct cb1_hdr10_ai *c,double pts)
{
    if(!c || !c->active)return CB1_AI_INVALID;
    enum cb1_ai_status status=collect(c);
    return status==CB1_AI_READY?cb1_hdr10_temporal_advance(c->temporal,pts):status;
}
void cb1_hdr10_ai_end(struct cb1_hdr10_ai *c)
{ if(c){c->ended=true;if(!c->pending)cb1_hdr10_temporal_end(c->temporal);} }
enum cb1_ai_status cb1_hdr10_ai_poll(struct cb1_hdr10_ai *c,struct cb1_ai_identity id,struct cb1_ai_result *out)
{
    if(!c || !c->active || !out || id.stream!=c->stream || id.revision!=c->revision)return CB1_AI_INVALID;
    enum cb1_ai_status status=collect(c);
    if(status!=CB1_AI_READY && status!=CB1_AI_PENDING)return status;
    /* A future analysis job does not invalidate a sealed presentation window. */
    if(c->result_valid && same(id,c->result.id)){*out=c->result;return CB1_AI_READY;}
    if(status==CB1_AI_PENDING && same(id,c->id))return CB1_AI_PENDING;
    struct cb1_hdr10_temporal_result temporal;
    status=cb1_hdr10_temporal_poll(c->temporal,id,&temporal);if(status!=CB1_AI_READY)return status;
    if(!c->residual_valid || memcmp(c->calibration,temporal.calibration,sizeof(c->calibration))){
        double features[222];for(unsigned i=0;i<222;++i)features[i]=temporal.calibration[i];
        const uint64_t inference=now_ns();
        status=cb1_l1l3_model_residual(c->model,features,222,c->residual);if(status!=CB1_AI_READY)return status;
        c->metrics.inference_ns+=elapsed_ns(inference);
        memcpy(c->calibration,temporal.calibration,sizeof(c->calibration));c->residual_valid=true;++c->metrics.inferences;
    }
    struct cb1_ai_result result={.id=id,.pts=temporal.pts};
    status=cb1_l1l3_project(temporal.base,c->residual,temporal.peak,&result.raw);
    if(status!=CB1_AI_READY)return status;
    c->result=result;c->result_valid=true;*out=result;return CB1_AI_READY;
}
void cb1_hdr10_ai_metrics(const struct cb1_hdr10_ai *c,struct cb1_hdr10_ai_metrics *out)
{ if(c && out)*out=c->metrics; }
