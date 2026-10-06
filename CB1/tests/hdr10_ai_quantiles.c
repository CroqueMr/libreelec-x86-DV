/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_hdr10_quantiles.h"
#include <time.h>

static const struct cb1_ai_identity id={7,11,13};
static enum cb1_ai_status wait_result(struct cb1_hdr10_quantiles *ctx, float out[7])
{
    for (unsigned i=0; i<10000; ++i) {
        enum cb1_ai_status result=cb1_hdr10_quantiles_poll(ctx,id,out);
        if (result!=CB1_AI_PENDING) return result;
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"GPU quantiles timed out"); return CB1_AI_INVALID;
}

int main(void)
{
    struct reference_gpu gpu=reference_gpu_create();
    struct cb1_hdr10_quantiles *ctx=cb1_hdr10_quantiles_create(gpu.gl->gpu);
    assert(ctx);
    cb1_hdr10_quantiles_reset(ctx,id.stream,id.revision);
    float pixels[513*4]={0};
    for (uint32_t i=0; i<513; ++i)
        pixels[4*i]=(float)((i*1103515245u+12345u)%65536u)/65535.f;
    pl_tex texture=reference_texture(gpu.gl->gpu,513,1,pixels);
    const struct cb1_hdr10_bounds area={0,0,513,1,0,65535};
    assert(cb1_hdr10_quantiles_submit(ctx,texture,area,id)==CB1_AI_PENDING);
    pl_tex_destroy(gpu.gl->gpu,&texture);
    float out[7];
    assert(wait_result(ctx,out)==CB1_AI_READY);
    /* Independent NumPy RGB48 oracle uses the frozen strided grid. */
    const float expected[7]={0x1.8bc7f2p-5f,0x1.f709f8p-3f,0x1.fcedfcp-2f,
        0x1.808780p-1f,0x1.e58d80p-1f,0x1.f94fa6p-1f,0x1.fd1328p-1f};
    for (unsigned i=0; i<7; ++i) {
        if (out[i]!=expected[i]) fprintf(stderr,"quantile %u: %.9g != %.9g\n",i,out[i],expected[i]);
        assert(out[i]==expected[i]);
    }
    /* Reused histogram and cropped, odd active geometry. */
    float crop[5*4*4]={0};
    for (unsigned y=1; y<3; ++y)
        for (unsigned x=1; x<4; ++x) crop[4*(y*5+x)+1]=.8f;
    texture=reference_texture(gpu.gl->gpu,5,4,crop);
    assert(cb1_hdr10_quantiles_submit(ctx,texture,
        (struct cb1_hdr10_bounds){1,1,4,3,0,52428},id)==CB1_AI_PENDING);
    pl_tex_destroy(gpu.gl->gpu,&texture);
    assert(wait_result(ctx,out)==CB1_AI_READY);
    for (unsigned i=0; i<7; ++i) assert(out[i]==.8f);
    /* Full-resolution extrema and sampled quantiles intentionally differ. */
    float *large=calloc(3840*2160*4,sizeof(float)); assert(large);
    for (unsigned i=0; i<3840*2160; ++i) large[4*i]=.2f;
    large[4*(3840*2160-1)+2]=1.f;
    texture=reference_texture(gpu.gl->gpu,3840,2160,large); free(large);
    assert(cb1_hdr10_quantiles_submit(ctx,texture,
        (struct cb1_hdr10_bounds){0,0,3840,2160,0,65535},id)==CB1_AI_PENDING);
    pl_tex_destroy(gpu.gl->gpu,&texture);
    assert(wait_result(ctx,out)==CB1_AI_READY);
    for (unsigned i=0; i<7; ++i) assert(out[i]==.2f);
    /* Pixel validation does not overwrite outputs or contaminate the next job. */
    float bad[]={NAN,INFINITY,-.1f,1.1f};
    for (unsigned b=0; b<4; ++b) {
        float pixel[]={bad[b],0,0,1};
        texture=reference_texture(gpu.gl->gpu,1,1,pixel);
        assert(cb1_hdr10_quantiles_submit(ctx,texture,
            (struct cb1_hdr10_bounds){0,0,1,1,0,65535},id)==CB1_AI_PENDING);
        pl_tex_destroy(gpu.gl->gpu,&texture);
        for (unsigned i=0; i<7; ++i) out[i]=.375f;
        assert(wait_result(ctx,out)==CB1_AI_INVALID);
        for (unsigned i=0; i<7; ++i) assert(out[i]==.375f);
    }
    float black[4]={0}; texture=reference_texture(gpu.gl->gpu,1,1,black);
    assert(cb1_hdr10_quantiles_submit(ctx,texture,(struct cb1_hdr10_bounds){0,0,1,1,0,0},id)==CB1_AI_PENDING);
    const struct cb1_ai_identity wrong={7,12,13};
    assert(cb1_hdr10_quantiles_poll(ctx,wrong,out)==CB1_AI_INVALID);
    for (unsigned i=0; i<7; ++i) assert(out[i]==.375f);
    assert(wait_result(ctx,out)==CB1_AI_READY);
    for (unsigned i=0; i<7; ++i) assert(out[i]==0);
    assert(cb1_hdr10_quantiles_submit(ctx,texture,(struct cb1_hdr10_bounds){0,0,1,1,0,0},id)==CB1_AI_PENDING);
    cb1_hdr10_quantiles_reset(ctx,8,13);
    assert(cb1_hdr10_quantiles_poll(ctx,id,out)==CB1_AI_INVALID);
    assert(cb1_hdr10_quantiles_submit(ctx,texture,(struct cb1_hdr10_bounds){0,0,1,1,0,0},id)==CB1_AI_INVALID);
    pl_tex_destroy(gpu.gl->gpu,&texture);
    cb1_hdr10_quantiles_destroy(&ctx);
    reference_gpu_destroy(&gpu);
    puts("Exact RGB48 GPU quantiles passed");
}
