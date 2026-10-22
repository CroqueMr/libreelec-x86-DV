/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"

/* Inverse of the pinned HPE LMS-to-BT.2020 matrix. */
static void input_pixels(float pixels[32],double peak)
{
    pl_matrix3x3 rgb2lms={{{3.06441879,-2.16597676,.10155818},
        {-.65612108,1.78554118,-.12943749},{.01736321,-.04725154,1.03004253}}};
    pl_matrix3x3_invert(&rgb2lms);
    const double rgb[8][3]={{0,0,0},{1,1,1},{1,0,0},{0,1,0},{0,0,1},
        {1,1,0},{0,1,1},{1,0,1}};
    for(int i=0;i<8;i++) {
        for(int c=0;c<3;c++) {
            double lms=0;for(int j=0;j<3;j++)lms+=rgb2lms.m[c][j]*rgb[i][j]*peak;
            pixels[4*i+c]=pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,lms);
        }
        pixels[4*i+3]=1;
    }
}

int main(void)
{
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    const double targets[]={600,1000,2000,2300,10000,600};unsigned count=0;
    for(int master=1000;master<=4000;master+=3000) {
        float pixels[32];input_pixels(pixels,master);
        pl_tex input=reference_texture(gpu,8,1,pixels);
        struct pl_frame frame=reference_frame(input,8,1);
        size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
        unsigned peak=lround(pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,master)*4095);
        av_dovi_get_color(m)->source_max_pq=peak;
        *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=peak,.avg_pq=2081}};
        *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=6,.l6={.max_luminance=master}};
        void *copy=av_memdup(m,bytes);assert(copy);
        for(int gamut=DVBRIDGE_GAMUT_P3_D65;gamut<=DVBRIDGE_GAMUT_BT2020;gamut++)
            for(unsigned k=0;k<sizeof(targets)/sizeof(*targets);k++) {
                struct dvbridge_policy policy=reference_policy();
                policy.tv.peak_nits=targets[k];policy.tv.gamut=gamut;
                struct dvbridge_identity id={1,++count,1};
                assert(dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&frame,m,bytes,0,0,
                    (struct dvbridge_geometry){8,1,0,0,8,1}));
                float out[32];reference_read(gpu,dvbridge_render_texture(r),0,0,8,1,out);
                double maximum=0,white=0;
                for(int i=0;i<8;i++) {
                    double y=0;const double weights[]={.2627,.678,.0593};
                    for(int c=0;c<3;c++) {
                        assert(isfinite(out[4*i+c]) && out[4*i+c]>=0 && out[4*i+c]<=1);
                        double n=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,out[4*i+c]);
                        y+=n*weights[c];
                        if(i==0)assert(out[c]==0);
                    }
                    if(y>maximum)maximum=y;
                    if(i==1)white=y;
                }
                fprintf(stderr,"Expert master=%d target=%.0f gamut=%d maxY=%.6f white=%.6f\n",
                    master,targets[k],gamut,maximum,white);
                assert(maximum<=targets[k]+1);
                if(targets[k]>master)assert(fabs(white-master)<2);
                assert(!memcmp(copy,m,bytes));
            }
        av_free(copy);av_free(m);pl_tex_destroy(gpu,&input);
    }
    /* Exercise the direct 10-bit scanout path with the saturating yellow case. */
    float patches[32];input_pixels(patches,4000);
    float *full=malloc(3840u*2160*4*sizeof(float));assert(full);
    for(unsigned i=0;i<3840u*2160;i++)memcpy(full+4*i,patches+5*4,4*sizeof(float));
    pl_tex input=reference_texture(gpu,3840,2160,full);free(full);
    pl_tex output=reference_texture(gpu,3840,2160,NULL);
    struct pl_frame frame=reference_frame(input,3840,2160);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    av_dovi_get_color(m)->source_max_pq=3696;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3696,.avg_pq=2081}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=6,.l6={.max_luminance=4000}};
    for(unsigned k=0;k<3;k++) {
        struct dvbridge_policy p=reference_policy();p.tv.peak_nits=targets[k];p.tv.gamut=DVBRIDGE_GAMUT_BT2020;
        struct dvbridge_identity id={1,++count,1};
        assert(dvbridge_render_hdr10_policy_direct(r,&p,&id,&frame,m,bytes,0,0,
            (struct dvbridge_geometry){3840,2160,0,0,3840,2160},output,false,true,10));
        float sample[4];reference_read(gpu,output,1920,1080,1,1,sample);
        double cap=ceil(pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,targets[k])*876+64);
        for(int c=0;c<3;c++) {
            double code=round(sample[c]*1023);
            assert(isfinite(sample[c]) && code>=64 && code<=cap);
        }
    }
    av_free(m);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&output);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);
    printf("PASS %u Expert peak cases, unchanged metadata and no inverse expansion\n",count);
}
