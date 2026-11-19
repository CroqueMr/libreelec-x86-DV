/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_hdr10_statistics.h"
#include <time.h>

static const struct cb1_ai_identity id={7,11,13};
static enum cb1_ai_status wait_result(struct cb1_hdr10_statistics *ctx, float out[35])
{
    for (unsigned i=0; i<10000; ++i) {
        enum cb1_ai_status status=cb1_hdr10_statistics_poll(ctx,id,out);
        if (status!=CB1_AI_PENDING) return status;
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"GPU statistics timed out"); return CB1_AI_INVALID;
}

int main(void)
{
    struct reference_gpu gpu=reference_gpu_create();
    struct cb1_hdr10_statistics *ctx=cb1_hdr10_statistics_create(gpu.gl->gpu);
    assert(ctx); cb1_hdr10_statistics_reset(ctx,id.stream,id.revision);
    /* The crop contains two constant rows, with different RGB peaks. */
    float pixels[6*4*4]={0};
    for (unsigned y=1; y<3; ++y) for (unsigned x=1; x<5; ++x) {
        pixels[4*(y*6+x)]=y==1?0.2f:0.8f;
        pixels[4*(y*6+x)+1]=y==1?0.4f:0.6f;
        pixels[4*(y*6+x)+2]=0.2f;
    }
    pl_tex texture=reference_texture(gpu.gl->gpu,6,4,pixels);
    const struct cb1_hdr10_bounds area={1,1,5,3,13107,52428};
    assert(cb1_hdr10_statistics_submit(ctx,texture,area,id)==CB1_AI_PENDING);
    pl_tex_destroy(gpu.gl->gpu,&texture);
    float out[35]; assert(wait_result(ctx,out)==CB1_AI_READY);
    /* Quantiles are supplied by the separate exact integer-histogram helper. */
    assert(out[0]==.2f && out[1]==.8f);
    assert(fabsf(out[2]-.6f)<2e-6f && fabsf(out[3]-.2f)<2e-6f);
    assert(fabsf(out[13]-.5f)<2e-6f && fabsf(out[14]-.5f)<2e-6f);
    assert(fabsf(out[15]-.2f)<2e-6f && fabsf(out[16]-.2f)<2e-6f);
    assert(fabsf(out[17]-.4f)<2e-6f && out[18]==1.f/3.f);
    for (unsigned i=0; i<16; ++i) assert(out[19+i]==((i==6||i==12)?.5f:0.f));
    /* Independent binary64 ST 2084/luminance oracle. Highp transcendental
     * error is bounded at 5e-5; linear statistics at 2e-6. */
    assert(fabsf(out[11]-0.51699552f)<5e-5f);
    assert(fabsf(out[12]-0.17293756f)<5e-5f);
    float black[4]={0}; texture=reference_texture(gpu.gl->gpu,1,1,black);
    assert(cb1_hdr10_statistics_submit(ctx,texture,(struct cb1_hdr10_bounds){0,0,1,1,0,0},id)==CB1_AI_PENDING);
    struct cb1_ai_identity wrong={7,12,13};
    out[0]=.375f; assert(cb1_hdr10_statistics_poll(ctx,wrong,out)==CB1_AI_INVALID && out[0]==.375f);
    assert(wait_result(ctx,out)==CB1_AI_READY);
    assert(out[0]==0 && out[1]==0 && out[2]==0 && out[3]==0 && out[11]==0 && out[12]==0);
    assert(out[17]==0 && out[18]==1 && out[19]==1);
    assert(cb1_hdr10_statistics_submit(ctx,texture,(struct cb1_hdr10_bounds){0,0,1,1,0,0},id)==CB1_AI_PENDING);
    cb1_hdr10_statistics_reset(ctx,8,13);
    assert(cb1_hdr10_statistics_poll(ctx,id,out)==CB1_AI_INVALID);
    pl_tex_destroy(gpu.gl->gpu,&texture);
    cb1_hdr10_statistics_reset(ctx,id.stream,id.revision);
    /* Just below the next striding threshold is the largest statistics grid. */
    float *large=calloc(511*287*4,sizeof(float)); assert(large);
    for (unsigned i=0; i<511*287; ++i) large[4*i]=1.f;
    texture=reference_texture(gpu.gl->gpu,511,287,large);free(large);
    assert(cb1_hdr10_statistics_submit(ctx,texture,
        (struct cb1_hdr10_bounds){0,0,511,287,0,65535},id)==CB1_AI_PENDING);
    pl_tex_destroy(gpu.gl->gpu,&texture); assert(wait_result(ctx,out)==CB1_AI_READY);
    assert(out[2]==1 && out[3]==0 && out[13]==1 && out[14]==0 && out[15]==0 && out[34]==1);
    cb1_hdr10_statistics_destroy(&ctx); reference_gpu_destroy(&gpu);
    puts("GPU global descriptors passed");
}
