/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "reference_test.h"
#include "cb1_hdr10_ai.h"
#include "cb1_hdr10_features.h"
#include "cb1_hdr10_statistics.h"
#include <time.h>

static unsigned gpu_errors;
static unsigned deferred;
static bool reject_statistics;
static bool stall_statistics;
extern enum cb1_ai_status __real_cb1_hdr10_statistics_poll(struct cb1_hdr10_statistics *,struct cb1_ai_identity,float[35]);
/* Delay the real statistics poll so quantiles finish before its result. */
enum cb1_ai_status __wrap_cb1_hdr10_statistics_poll(struct cb1_hdr10_statistics *ctx,struct cb1_ai_identity id,float out[35])
{
    if(reject_statistics)return CB1_AI_INVALID;
    if(stall_statistics)return CB1_AI_PENDING;
    if((deferred++%3)!=2)return CB1_AI_PENDING;
    return __real_cb1_hdr10_statistics_poll(ctx,id,out);
}
static void log_error(void *priv,enum pl_log_level level,const char *message)
{ (void)priv;if(level<=PL_LOG_ERR){++gpu_errors;fprintf(stderr,"%s\n",message);} }
static struct pl_frame black_source(pl_gpu gpu)
{
    struct pl_frame frame={.num_planes=2,.crop={0,0,128,72},
        .repr={.sys=PL_COLOR_SYSTEM_BT_2020_NC,.levels=PL_COLOR_LEVELS_LIMITED,
            .bits={.sample_depth=16,.color_depth=10,.bit_shift=6}},
        .color={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ}};
    for(unsigned plane=0;plane<2;++plane){
        int w=plane?64:128,h=plane?36:72,c=plane?2:1;
        uint16_t *pixels=calloc(w*h*c,2);assert(pixels);
        for(int i=0;i<w*h*c;++i)pixels[i]=plane?32768:38400;
        pl_fmt format=pl_find_fmt(gpu,PL_FMT_UNORM,c,16,16,PL_FMT_CAP_SAMPLEABLE);assert(format);
        frame.planes[plane]=(struct pl_plane){.components=c,.component_mapping={plane,plane+1},
            .texture=pl_tex_create(gpu,pl_tex_params(.w=w,.h=h,.format=format,.sampleable=true,.initial_data=pixels))};
        free(pixels);assert(frame.planes[plane].texture);
    }
    return frame;
}
int main(int argc,char **argv)
{
    assert(argc==2);setenv("CB1_REFERENCE_TRACE","1",1);
    struct reference_gpu gpu=reference_gpu_create();
    pl_log_update(gpu.log,pl_log_params(.log_cb=log_error,.log_level=PL_LOG_ERR));
    struct cb1_hdr10_ai *ctx=NULL;
    assert(cb1_hdr10_ai_create(gpu.gl->gpu,"/missing-cb1-bundle",&ctx)==CB1_AI_INCOMPATIBLE && !ctx);
    assert(cb1_hdr10_ai_create(gpu.gl->gpu,argv[1],&ctx)==CB1_AI_READY && ctx);
    cb1_hdr10_ai_reset(ctx,7,3);
    for(unsigned i=0;i<25;++i){
        struct pl_frame frame=black_source(gpu.gl->gpu);
        struct cb1_ai_identity id={7,i+1,3};
        struct cb1_hdr10_ai_metrics before,submitted,completed;
        cb1_hdr10_ai_metrics(ctx,&before);
        enum cb1_ai_status status=cb1_hdr10_ai_submit(ctx,&frame,id,i*.04);
        assert(status==CB1_AI_PENDING);
        cb1_hdr10_ai_metrics(ctx,&submitted);
        assert(submitted.gpu_submissions>before.gpu_submissions);
        for(unsigned p=0;p<2;++p)pl_tex_destroy(gpu.gl->gpu,&frame.planes[p].texture);
        for(unsigned wait=0;status==CB1_AI_PENDING && wait<10000;++wait){
            nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
            status=cb1_hdr10_ai_submit(ctx,NULL,id,i*.04);
        }
        assert(status==CB1_AI_READY);
        cb1_hdr10_ai_metrics(ctx,&completed);
        assert(completed.gpu_submissions>submitted.gpu_submissions);
        assert(cb1_hdr10_ai_submit(ctx,NULL,id,i*.04)==CB1_AI_READY);
    }
    struct cb1_ai_result actual={.pts=123};
    struct cb1_ai_identity first={7,1,3};
    assert(cb1_hdr10_ai_poll(ctx,first,&actual)==CB1_AI_PENDING && actual.pts==123);
    assert(cb1_hdr10_ai_advance(ctx,1.)==CB1_AI_READY);
    assert(cb1_hdr10_ai_poll(ctx,first,&actual)==CB1_AI_READY && actual.pts==0 && actual.id.picture==1);
    struct cb1_hdr10_descriptor descriptors[25]={0};
    float value=(float)((4*(600-64)*9539+256)>>9)/65535.f;
    double p=pow(value,1./(2523./32)),nits=10000*pow(fmax(p-3424./4096,0)/(2413./128-2392./128*p),1./(2610./16384));
    for(unsigned i=0;i<25;++i){
        descriptors[i].pts=i*.04;
        float *g=descriptors[i].global;g[0]=g[1]=g[2]=value;
        for(unsigned j=4;j<=10;++j)g[j]=value;
        g[11]=(float)(log1p(nits)/log1p(10000));g[13]=g[14]=g[15]=value;g[18]=1;g[19+(unsigned)(value*16)]=1;
        float small=(float)(_Float16)value;
        for(unsigned j=0;j<32;++j)descriptors[i].spatial[j]=small;
        for(unsigned j=0;j<4;++j)descriptors[i].spatial[32+j]=small>=(float[]){.5,.7,.8,.9}[j];
    }
    uint16_t base[3];double peak;
    assert(cb1_hdr10_baseline(descriptors,25,NAN,base,&peak));
    float prefix[222];double features[222];
    assert(cb1_hdr10_prefix(descriptors,25,base,true,true,prefix));
    for(unsigned i=0;i<222;++i)features[i]=prefix[i];
    struct cb1_l1l3_model *model=NULL;struct cb1_l1l3 expected;
    assert(cb1_l1l3_model_open(argv[1],&model)==CB1_AI_READY);
    assert(cb1_l1l3_model_predict(model,features,222,base,peak,&expected)==CB1_AI_READY);
    if(memcmp(&actual.raw,&expected,sizeof(expected)))fprintf(stderr,"actual %u/%u/%u expected%u/%u/%u\n",actual.raw.l1_min,actual.raw.l1_avg,actual.raw.l1_max,expected.l1_min,expected.l1_avg,expected.l1_max);
    assert(!memcmp(&actual.raw,&expected,sizeof(expected)));
    struct cb1_ai_result repeated;
    assert(cb1_hdr10_ai_poll(ctx,first,&repeated)==CB1_AI_READY && !memcmp(&repeated.raw,&actual.raw,sizeof(actual.raw)));
    struct cb1_hdr10_ai_metrics metrics;cb1_hdr10_ai_metrics(ctx,&metrics);
    assert(metrics.pictures==25 && metrics.readback_bytes==25*7272 && metrics.inferences==1);
    assert(metrics.analysis_submit_ns>0 && metrics.readback_latency_ns>0 && metrics.inference_ns>0);
    struct cb1_hdr10_ai_metrics repeated_metrics;
    assert(cb1_hdr10_ai_poll(ctx,first,&repeated)==CB1_AI_READY);
    cb1_hdr10_ai_metrics(ctx,&repeated_metrics);
    assert(!memcmp(&metrics,&repeated_metrics,sizeof(metrics)));
    struct pl_frame future_frame=black_source(gpu.gl->gpu);
    struct cb1_ai_identity future={7,26,3};
    enum cb1_ai_status future_status=cb1_hdr10_ai_submit(ctx,&future_frame,future,1.);
    while(future_status==CB1_AI_PENDING){
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
        future_status=cb1_hdr10_ai_submit(ctx,NULL,future,1.);
    }
    assert(future_status==CB1_AI_READY && cb1_hdr10_ai_advance(ctx,1.04)==CB1_AI_READY);
    ++future.picture;
    assert(cb1_hdr10_ai_submit(ctx,&future_frame,future,1.04)==CB1_AI_PENDING);
    stall_statistics=true;
    struct cb1_ai_result pending_result={.pts=123};
    assert(cb1_hdr10_ai_poll(ctx,future,&pending_result)==CB1_AI_PENDING && pending_result.pts==123);
    assert(cb1_hdr10_ai_poll(ctx,(struct cb1_ai_identity){7,2,3},&pending_result)==CB1_AI_READY);
    assert(pending_result.id.picture==2);
    stall_statistics=false;
    future_status=cb1_hdr10_ai_submit(ctx,NULL,future,1.04);
    while(future_status==CB1_AI_PENDING){
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
        future_status=cb1_hdr10_ai_submit(ctx,NULL,future,1.04);
    }
    assert(future_status==CB1_AI_READY);
    for(unsigned p=0;p<2;++p)pl_tex_destroy(gpu.gl->gpu,&future_frame.planes[p].texture);
    assert(strlen(cb1_l1l3_bundle_id())==64);
    cb1_hdr10_ai_reset(ctx,8,4);
    assert(cb1_hdr10_ai_poll(ctx,first,&actual)==CB1_AI_INVALID);
    reject_statistics=true;
    struct pl_frame frame=black_source(gpu.gl->gpu);
    struct cb1_ai_identity failed={8,1,4};
    enum cb1_ai_status status=cb1_hdr10_ai_submit(ctx,&frame,failed,0);
    for(unsigned wait=0;status==CB1_AI_PENDING && wait<10000;++wait){
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
        status=cb1_hdr10_ai_submit(ctx,NULL,failed,0);
    }
    assert(status==CB1_AI_INVALID);
    for(unsigned p=0;p<2;++p)pl_tex_destroy(gpu.gl->gpu,&frame.planes[p].texture);
    reject_statistics=false;
    cb1_hdr10_ai_reset(ctx,8,5); // Explicit reselection may restart a failed activation.
    frame=black_source(gpu.gl->gpu);
    struct cb1_ai_identity recovered={8,1,5};
    status=cb1_hdr10_ai_submit(ctx,&frame,recovered,0);
    assert(status==CB1_AI_PENDING);
    for(unsigned p=0;p<2;++p)pl_tex_destroy(gpu.gl->gpu,&frame.planes[p].texture);
    for(unsigned wait=0;status==CB1_AI_PENDING && wait<10000;++wait){
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
        status=cb1_hdr10_ai_submit(ctx,NULL,recovered,0);
    }
    assert(status==CB1_AI_READY);
    cb1_hdr10_ai_end(ctx);
    assert(cb1_hdr10_ai_poll(ctx,recovered,&actual)==CB1_AI_READY);
    assert(cb1_hdr10_ai_poll(ctx,failed,&actual)==CB1_AI_INVALID);
    cb1_hdr10_ai_destroy(&ctx);assert(!ctx);
    cb1_l1l3_model_close(&model);assert(gpu_errors==0);
    reference_gpu_destroy(&gpu);
    puts("Live GPU analysis, native inference, borrowed planes and identity reset passed");
}
