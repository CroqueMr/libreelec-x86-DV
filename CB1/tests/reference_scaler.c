/* SPDX-License-Identifier: MIT */
/* Observe existing SCALED output without changing source or filter equations. */
#include "reference_test.h"
#include <libplacebo/shaders/custom.h>
#include <libplacebo/shaders/colorspace.h>
struct capture { pl_shader sh; bool called,linear; };
static struct pl_hook_res capture_scaler(void *priv,const struct pl_hook_params *p)
{
    struct capture *c=priv;
    if(p->stage==PL_HOOK_SCALED) {
        c->called=true;c->sh=p->sh;c->linear=p->color.transfer==PL_COLOR_TRC_LINEAR;
        struct pl_custom_shader s={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
            .header="vec3 cb1_scaler_sample;\n",.body="cb1_scaler_sample=color.rgb;\n"};
        return (struct pl_hook_res){.failed=!pl_shader_custom(p->sh,&s),.output=PL_HOOK_SIG_NONE};
    }
    assert(c->called && c->sh==p->sh);
    struct pl_custom_shader s={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,.body="color.rgb=cb1_scaler_sample;\n"};
    bool ok=pl_shader_custom(p->sh,&s);
    /* Expose the source boundary with its existing negative-only transfer
     * guard. No upper clamp. Encode the observed value for the renderer's
     * final representation swizzle (which otherwise clips PQ >1); decode
     * this observation transport in the test, not in production. */
    if(!c->linear)pl_shader_linearize(p->sh,pl_color_space(.transfer=PL_COLOR_TRC_PQ));
    pl_shader_delinearize(p->sh,pl_color_space(.transfer=PL_COLOR_TRC_PQ));
    s.body="color.rgb=0.25+0.5*color.rgb;\n";ok=pl_shader_custom(p->sh,&s)&&ok;
    return (struct pl_hook_res){.failed=!ok,.output=PL_HOOK_SIG_NONE};
}
int main(void)
{
    int sw,sh,dw,dh;assert(scanf("%d%d%d%d",&sw,&sh,&dw,&dh)==4 && sw*sh>0 && sw*sh<=4096 && dw*dh>0 && dw*dh<=4096);
    float *pixels=calloc(sw*sh*4,sizeof(float));assert(pixels);
    for(int i=0;i<sw*sh;i++){for(int c=0;c<3;c++)assert(scanf("%f",&pixels[4*i+c])==1);pixels[4*i+3]=1;}
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    pl_tex input=reference_texture(gpu,sw,sh,pixels),target=reference_texture(gpu,dw,dh,NULL);free(pixels);
    struct pl_frame image=reference_frame(input,sw,sh),out=reference_frame(target,dw,dh);
    image.repr=out.repr=pl_color_repr_rgb;
    image.color=out.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=10000}};
    struct capture capture={0};const struct pl_hook hook={.stages=PL_HOOK_SCALED|PL_HOOK_PRE_OUTPUT,
        .input=PL_HOOK_SIG_COLOR,.priv=&capture,.hook=capture_scaler,.signature=0x4342315343414c45ULL};
    const struct pl_hook *hooks[]={&hook};struct pl_render_params params=pl_render_default_params;
    params.hooks=hooks;params.num_hooks=1;params.peak_detect_params=NULL;params.sigmoid_params=NULL;
    params.dither_params=NULL;params.frame_mixer=NULL;params.border=PL_CLEAR_SKIP;
    params.min_fbo_precision=32;params.cb1_stable_pq=true;params.cb1_nearest_identity=true;
    pl_renderer renderer=pl_renderer_create(g.log,gpu);assert(renderer);
    assert(pl_render_image(renderer,&image,&out,&params) && capture.called);
    assert(capture.linear==(dw<sw || dh<sh));
    pixels=calloc(dw*dh*4,sizeof(float));assert(pixels);reference_read(gpu,target,0,0,dw,dh,pixels);
    printf("{\"rgb\":[");for(int i=0;i<dw*dh;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",pixels[4*i],pixels[4*i+1],pixels[4*i+2]);puts("]}");
    free(pixels);pl_renderer_destroy(&renderer);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&target);reference_gpu_destroy(&g);
}
