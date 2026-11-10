/* SPDX-License-Identifier: MIT */
/* Private Phase A: link this unchanged fixture separately to the frozen
 * staged owner and prototype. No newly shared color construction oracle. */
#include "reference_test.h"
#include <stdio.h>

int main(int argc,char **argv)
{
    assert(argc==3);
    bool direct=strcmp(argv[1],"direct")==0;
    const int w=256,h=4,n=w*h*4;
    float *pixels=malloc(n*sizeof(float)),*actual=malloc(n*sizeof(float));
    float *expected=malloc(n*sizeof(float));assert(pixels&&actual&&expected);
    for(int y=0;y<h;y++)for(int x=0;x<w;x++){
        float v=x/255.f;
        int i=4*(y*w+x);
        pixels[i]=v;pixels[i+1]=y==0?v:y==1?.25f:y==2?.5f:.75f;
        pixels[i+2]=y==0?v:1-v;pixels[i+3]=1;
    }
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu.gl->gpu);assert(r);
    pl_tex input=reference_texture(gpu.gl->gpu,w,h,pixels);
    pl_tex output=reference_texture(gpu.gl->gpu,w,h,NULL);
    struct pl_frame frame=reference_frame(input,w,h);
    frame.repr.alpha=PL_ALPHA_NONE;
    const struct dvbridge_geometry geometry={w,h,0,0,w,h,w,h};
    const struct dvbridge_identity id={1,1,3};
    const struct dvbridge_policy policy={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);
    bool ok=direct?dvbridge_render_hdr10_policy_direct(r,&policy,&id,&frame,metadata,bytes,
        1,1,geometry,output,false,false,16):
        (dvbridge_render_sdr_policy_rgb(r,&policy,&id,&frame,metadata,bytes,1,1,geometry)&&
         dvbridge_render_sdr_policy_resolve(r,output,false,false,16));
    if(!ok){fprintf(stderr,"%s path rejected valid identity SDR input\n",argv[1]);return 2;}
    const struct dvbridge_hdr10_policy_output *pending=dvbridge_render_policy_output(r);
    assert(pending&&pending->resolved&&pending->final_target==output);
    pl_tex reconstructed_texture=direct?NULL:dvbridge_render_texture(r);
    assert(dvbridge_render_policy_commit(r,&id,output));
    reference_read(gpu.gl->gpu,output,0,0,w,h,actual);
    /* Artifact capture only: preserve exact input, RPU, reconstructed stage and
     * direct output for failure classification, without changing either draw. */
    char path[1024];
    snprintf(path,sizeof(path),"%s.%s.bin",argv[2],direct?"direct":"input");
    FILE *capture=fopen(path,"wb");assert(capture);
    assert(fwrite(direct?actual:pixels,sizeof(float),n,capture)==n);fclose(capture);
    if(!direct){
        float *reconstructed=malloc(n*sizeof(float));assert(reconstructed);
        assert(reconstructed_texture);
        reference_read(gpu.gl->gpu,reconstructed_texture,0,0,w,h,reconstructed);
        snprintf(path,sizeof(path),"%s.reconstruction.bin",argv[2]);
        capture=fopen(path,"wb");assert(capture);
        assert(fwrite(reconstructed,sizeof(float),n,capture)==n);fclose(capture);free(reconstructed);
        snprintf(path,sizeof(path),"%s.rpu.bin",argv[2]);capture=fopen(path,"wb");assert(capture);
        assert(fwrite(metadata,1,bytes,capture)==bytes);fclose(capture);
    }
    FILE *f=fopen(argv[2],direct?"rb":"wb");assert(f);
    if(!direct){assert(fwrite(actual,sizeof(float),n,f)==n);fclose(f);return 0;}
    assert(fread(expected,sizeof(float),n,f)==n);fclose(f);
    unsigned failed=0,endpoints=0;double max_abs=0,max_ratio=0;int worst=-1;
    for(int i=0;i<n;i++)if(i%4!=3){
        double e=fabs((double)actual[i]-expected[i]);
        double limit=fmax(1e-7,2e-6*fabs(expected[i]));
        if(!isfinite(actual[i])||!isfinite(expected[i])||e>limit)failed++;
        if((expected[i]==0||expected[i]==1)&&actual[i]!=expected[i])endpoints++;
        if(e>max_abs){max_abs=e;worst=i;}max_ratio=fmax(max_ratio,e/limit);
    }
    printf("{\"pixels\":%d,\"failed_channels\":%u,\"endpoint_mismatches\":%u,"
        "\"max_abs\":%.12g,\"max_gate_ratio\":%.12g,\"worst_index\":%d,"
        "\"worst_reference\":%.12g,\"worst_actual\":%.12g}\n",
        w*h,failed,endpoints,max_abs,max_ratio,worst,expected[worst<0?0:worst],actual[worst<0?0:worst]);
    return failed||endpoints?1:0;
}
