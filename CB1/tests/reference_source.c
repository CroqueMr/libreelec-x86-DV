/* SPDX-License-Identifier: MIT */
/* Public pinned source primitive, not a replacement for engine image tests. */
#include "reference_test.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/colorspace.h>
#include <libplacebo/shaders/sampling.h>

int main(void)
{
    struct pl_dovi_metadata d={0};
    int w,h; assert(scanf("%d%d",&w,&h)==2 && w>0 && h>0 && w*h<=4096);
    for(int c=0;c<3;c++)assert(scanf("%f",&d.nonlinear_offset[c])==1);
    for(int y=0;y<3;y++)for(int x=0;x<3;x++)assert(scanf("%f",&d.nonlinear.m[y][x])==1);
    for(int y=0;y<3;y++)for(int x=0;x<3;x++)assert(scanf("%f",&d.linear.m[y][x])==1);
    for(int c=0;c<3;c++) {
        unsigned n;assert(scanf("%u",&n)==1 && n>=2 && n<=9);d.comp[c].num_pivots=n;
        for(unsigned i=0;i<n;i++)assert(scanf("%f",&d.comp[c].pivots[i])==1);
        for(unsigned i=0;i<n-1;i++) {
            unsigned method,order;assert(scanf("%u%u",&method,&order)==2 && method<=1 && order<=3);
            d.comp[c].method[i]=method;d.comp[c].mmr_order[i]=order;
            assert(scanf("%f",&d.comp[c].mmr_constant[i])==1);
            for(int j=0;j<3;j++)assert(scanf("%f",&d.comp[c].poly_coeffs[i][j])==1);
            for(int j=0;j<3;j++)for(int k=0;k<7;k++)assert(scanf("%f",&d.comp[c].mmr_coeffs[i][j][k])==1);
        }
    }
    float *pixels=calloc(w*h*4,sizeof(float));assert(pixels);
    for(int i=0;i<w*h;i++){for(int c=0;c<3;c++)assert(scanf("%f",&pixels[4*i+c])==1);pixels[4*i+3]=1;}
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    pl_tex input=reference_texture(gpu,w,h,pixels),target=reference_texture(gpu,w,h,NULL);free(pixels);
    pl_dispatch dp=pl_dispatch_create(g.log,gpu);assert(dp);
    pl_dispatch_mark_cb1_stable_pq(dp,true);pl_shader sh=pl_dispatch_begin(dp);assert(sh);
    assert(pl_shader_sample_nearest(sh,pl_sample_src(.tex=input,.new_w=w,.new_h=h,.components=4)));
    /* Frozen source-equation offsets are normalized signal offsets. Public DV
     * descriptors use code / 2^depth, and decode multiplies by 2^depth/(2^depth-1).
     * Encode that distinction explicitly; this is not a different source image.
     */
    for(int c=0;c<3;c++)d.nonlinear_offset[c]*=65535.0f/65536.0f;
    struct pl_color_repr repr={.sys=PL_COLOR_SYSTEM_DOLBYVISION,.levels=PL_COLOR_LEVELS_FULL,
        .bits={.sample_depth=16,.color_depth=16},.alpha=PL_ALPHA_INDEPENDENT,.dovi=&d};
    pl_shader_decode_color_ex(sh,pl_color_decode_args(.repr=&repr));
    assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=&sh,.target=target)));
    pixels=calloc(w*h*4,sizeof(float));assert(pixels);reference_read(gpu,target,0,0,w,h,pixels);
    printf("{\"rgb\":[");
    for(int i=0;i<w*h;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",pixels[4*i],pixels[4*i+1],pixels[4*i+2]);
    puts("]}");free(pixels);pl_dispatch_destroy(&dp);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&target);reference_gpu_destroy(&g);
}
