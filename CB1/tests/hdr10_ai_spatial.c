/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_hdr10_spatial.h"
#include <time.h>
#include "spatial_reference.h"
static const struct cb1_ai_identity id={3,5,7};
static enum cb1_ai_status wait_result(struct cb1_hdr10_spatial *ctx,struct cb1_hdr10_spatial_result *out)
{
    for(unsigned i=0;i<10000;++i){
        enum cb1_ai_status status=cb1_hdr10_spatial_poll(ctx,id,out);
        if(status!=CB1_AI_PENDING)return status;
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"Spatial reduction timed out");return CB1_AI_INVALID;
}
int main(void)
{
    struct reference_gpu gpu=reference_gpu_create();
    struct cb1_hdr10_spatial *ctx=cb1_hdr10_spatial_create(gpu.gl->gpu);assert(ctx);
    cb1_hdr10_spatial_reset(ctx,id.stream,id.revision);
    float *pixels=calloc(128*72*4,sizeof(float));assert(pixels);
    for(unsigned i=0;i<128*72;++i){pixels[4*i]=.25f;pixels[4*i+1]=.5f;pixels[4*i+2]=.75f;}
    pl_tex texture=reference_texture(gpu.gl->gpu,128,72,pixels);
    assert(cb1_hdr10_spatial_submit(ctx,texture,id)==CB1_AI_PENDING);
    struct cb1_hdr10_spatial_result out;
    assert(wait_result(ctx,&out)==CB1_AI_READY);
    for(unsigned i=0;i<32;++i)assert(out.features[i]==.75f);
    assert(out.features[32]==1 && out.features[33]==1 && out.features[34]==0 && out.features[35]==0);
    assert(fabsf(out.features[36])<2e-6f && fabsf(out.features[37])<2e-6f);
    for(unsigned c=0;c<3;++c)for(unsigned i=0;i<576;++i)assert(out.motion[c*576+i]==(c+1)*.25f);
    assert(cb1_hdr10_spatial_submit(ctx,texture,id)==CB1_AI_PENDING);
    out.features[0]=.125f;
    cb1_hdr10_spatial_reset(ctx,4,7);
    assert(cb1_hdr10_spatial_poll(ctx,id,&out)==CB1_AI_INVALID && out.features[0]==.125f);
    cb1_hdr10_spatial_reset(ctx,id.stream,id.revision);
    for(unsigned test=0;test<3;++test){
        for(unsigned i=0;i<128*72;++i)for(unsigned c=0;c<3;++c){
            unsigned value=(i*1723u+c*319u)%65536u;
            pixels[4*i+c]=test==0?(float)value/65535.f:
                test==1?((i%83u)==0u?1.f:0.f):.75f;
        }
        pl_tex_destroy(gpu.gl->gpu,&texture);
        texture=reference_texture(gpu.gl->gpu,128,72,pixels);
        float expected[1768];spatial_reference(gpu.gl->gpu,texture,expected);
        assert(cb1_hdr10_spatial_submit(ctx,texture,id)==CB1_AI_PENDING);
        assert(wait_result(ctx,&out)==CB1_AI_READY);
        assert(!memcmp(out.features,expected,sizeof(out.features)));
        assert(!memcmp(out.motion,expected+38,sizeof(out.motion)));
    }
    out.features[0]=.125f;
    pixels[0]=NAN;pl_tex_destroy(gpu.gl->gpu,&texture);
    texture=reference_texture(gpu.gl->gpu,128,72,pixels);free(pixels);
    assert(cb1_hdr10_spatial_submit(ctx,texture,id)==CB1_AI_PENDING);
    assert(wait_result(ctx,&out)==CB1_AI_INVALID && out.features[0]==.125f);
    pl_tex_destroy(gpu.gl->gpu,&texture);cb1_hdr10_spatial_destroy(&ctx);reference_gpu_destroy(&gpu);
    puts("GPU spatial descriptors and compact motion identity passed");
}
