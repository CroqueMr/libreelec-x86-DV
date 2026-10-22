/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"
#include "dvbridge_placebo.h"

/* ST 2084 is the oracle here, not the engine's mapper or scalar reference. */
static double encode(double nits)
{
    double x=pow(nits/10000.0,2610.0/16384.0);
    return pow((3424.0/4096.0+2413.0/128.0*x)/(1+2392.0/128.0*x),2523.0/32.0);
}

int main(void)
{
    const double ramp[]={0,.0001,.001,.005,.01,.02,.05,.1,.2,.5,1,2,5,10,100,1000};
    const unsigned minima[]={0,1,50,1000};
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *renderer=dvbridge_renderer_create(g.gl->gpu);assert(renderer);
    float pixels[64];
    for(unsigned i=0;i<16;i++){
        for(unsigned c=0;c<3;c++)pixels[4*i+c]=encode(ramp[i]);
        pixels[4*i+3]=1;
    }
    pl_tex texture=reference_texture(g.gl->gpu,16,1,pixels);
    struct pl_frame source=reference_frame(texture,16,1);
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);
    av_dovi_get_color(metadata)->source_min_pq=7;
    av_dovi_get_color(metadata)->source_max_pq=3079;
    *av_dovi_get_ext(metadata,0)=(AVDOVIDmData){.level=1,.l1={0,2873,1060}};
    *av_dovi_get_ext(metadata,2)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2081,
        .trim_slope=2271,.trim_offset=2085,.trim_power=2048,
        .trim_chroma_weight=2048,.trim_saturation_gain=1556,.ms_weight=-1}};
    struct dvbridge_policy policy=reference_policy();
    policy.tv.peak_nits=2300;policy.tv.gamut=DVBRIDGE_GAMUT_BT2020;
    for(unsigned anchor=0;anchor<2;anchor++)for(unsigned black=0;black<4;black++){
        metadata->num_ext_blocks=anchor?3:2;
        *av_dovi_get_ext(metadata,1)=(AVDOVIDmData){.level=6,
            .l6={.min_luminance=minima[black],.max_luminance=1000}};
        void *saved=av_memdup(metadata,bytes);assert(saved);
        struct dvbridge_identity identity={1,1+anchor*4+black,1};
        assert(dvbridge_render_hdr10_policy_rgb(renderer,&policy,&identity,&source,
            metadata,bytes,0,0,(struct dvbridge_geometry){16,1,0,0,16,1}));
        float output[64];reference_read(g.gl->gpu,dvbridge_render_texture(renderer),0,0,16,1,output);
        for(unsigned i=0;i<16;i++)for(unsigned c=0;c<3;c++){
            double expected=i?encode(ramp[i]):0;
            double error=fabs(output[4*i+c]-expected);
            if(error>5e-5)fprintf(stderr,"Expert shadow lost: L6min=%u anchor=%u input=%.6f channel=%u expectedPQ=%.9f actualPQ=%.9f\n",
                minima[black],anchor,ramp[i],c,expected,output[4*i+c]);
            assert(error<=5e-5 && "Mastering black must not erase valid Expert shadow samples");
        }
        assert(!memcmp(saved,metadata,bytes));av_free(saved);
        /* This Expert correction must not change the other policy mapper. */
        struct dvbridge_policy other=policy;other.mode=DVBRIDGE_MODE_ENHANCED_DV;
        struct dvbridge_color color;struct pl_color_space target;struct dvbridge_hdr10_metadata signal;
        assert(dvbridge_reference_map(&color,&target,&signal,&other,metadata,bytes,false));
        assert(fabs(color.color.hdr.min_luma-minima[black]/10000.0)<1e-8);
    }
    av_free(metadata);pl_tex_destroy(g.gl->gpu,&texture);
    dvbridge_renderer_destroy(renderer);reference_gpu_destroy(&g);
    puts("PASS Expert absolute-PQ shadows independent of mastering black, with and without neutral trims");
}
