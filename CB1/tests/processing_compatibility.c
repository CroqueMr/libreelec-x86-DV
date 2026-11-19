/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include <libplacebo/shaders/colorspace.h>

int main(void)
{
    enum{W=128,H=64};float pixels[W*H*4],output[W*H*4];
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    for(unsigned i=0;i<W*H;i++)for(unsigned c=0;c<4;c++)
        pixels[4*i+c]=c==3?1:(float)((i*(31+c*17)+997*c)%4096)/4095;
    pl_tex input=reference_texture(gpu,W,H,pixels),target=reference_texture(gpu,W,H,NULL);
    float *table=malloc(1024*9*4*sizeof(float));assert(table);
    for(unsigned row=0;row<9;row++)for(unsigned x=0;x<1024;x++)for(unsigned c=0;c<4;c++)
        table[4*(row*1024+x)+c]=(.01f*(row+1)+(float)x/1023*.25f);
#ifdef CB1_MUTATE_LOOKUP
    for(unsigned x=0;x<1024;x++)table[4*x]+=.1f;
#endif
    pl_tex mmr=reference_texture(gpu,1024,9,table);free(table);
    table=malloc(4096*4*sizeof(float));assert(table);
    for(unsigned x=0;x<4096;x++)for(unsigned c=0;c<4;c++)table[4*x+c]=powf((float)x/4095,2.4f);
    pl_tex decode=reference_texture(gpu,4096,1,table);
    for(unsigned x=0;x<4096;x++)for(unsigned c=0;c<4;c++)table[4*x+c]=powf((float)x/4095,4/2.4f);
    pl_tex encode=reference_texture(gpu,4096,1,table);free(table);
    pl_dispatch dp=pl_dispatch_create(g.log,gpu);assert(dp);
    const unsigned groups[]={0,1,2,3,8,9,10,11};unsigned records=0;
    for(unsigned stable=0;stable<2;stable++)for(unsigned order=1;order<=3;order++)
    for(unsigned mode=0;mode<8;mode++){
        struct pl_dovi_metadata d={0};
        for(unsigned c=0;c<3;c++){
            d.nonlinear.m[c][c]=1;d.linear.m[c][c]=1;
            d.comp[c].num_pivots=2;d.comp[c].pivots[0]=.01f;d.comp[c].pivots[1]=.99f;
            d.comp[c].method[0]=c?1:0;d.comp[c].mmr_order[0]=order;
            d.comp[c].poly_coeffs[0][0]=.01f;d.comp[c].poly_coeffs[0][1]=.98f;
            d.comp[c].mmr_constant[0]=.02f;
            for(unsigned o=0;o<3;o++)for(unsigned term=0;term<7;term++)
                d.comp[c].mmr_coeffs[0][o][term]=.01f*(term+1)/(o+1);
        }
        /* Both an ordinary linear domain and cancellation-sensitive samples. */
        if(stable)d.linear.m[1][0]=-.5f;
        struct pl_cb1_dovi_processing p={.groups=groups[mode],.poly_components=1,.narrow_components=6,
            .mmr_texture=mmr,.pq_texture={decode,encode}};
        struct pl_color_repr repr={.sys=PL_COLOR_SYSTEM_DOLBYVISION,.levels=PL_COLOR_LEVELS_FULL,
            .bits={.sample_depth=16,.color_depth=16},.alpha=PL_ALPHA_INDEPENDENT,.dovi=&d};
        pl_dispatch_mark_cb1_stable_pq(dp,stable);
        pl_shader sh=pl_dispatch_begin(dp);assert(sh);
        assert(pl_shader_sample_direct(sh,pl_sample_src(.tex=input)));
        pl_shader_decode_color_ex(sh,pl_color_decode_args(.repr=&repr,.cb1_processing=&p));
        assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=&sh,.target=target)));
        reference_read(gpu,target,0,0,W,H,output);
        assert(fwrite(output,sizeof(output),1,stdout)==1);records++;
    }
    fprintf(stderr,"Processing captures: %u full FP32 records\n",records);
    pl_dispatch_destroy(&dp);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&target);
    pl_tex_destroy(gpu,&mmr);pl_tex_destroy(gpu,&decode);pl_tex_destroy(gpu,&encode);reference_gpu_destroy(&g);
}
