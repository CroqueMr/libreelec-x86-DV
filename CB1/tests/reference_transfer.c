/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/colorspace.h>
#include <libplacebo/shaders/sampling.h>

static void check(pl_shader sh,bool stable)
{
    struct pl_color_space pq={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=1000}};
    pl_shader_linearize(sh,&pq);pl_shader_delinearize(sh,&pq);
    const struct pl_shader_res *result=pl_shader_finalize(sh);assert(result);
    assert((strstr(result->glsl,"0.1640625")!=NULL)==stable);
    assert((strstr(result->glsl,"0.84375")!=NULL)==stable);
    /* Catch loss of the positive-only primitive and its fixed four doublings. */
    assert((strstr(result->glsl,"log(cb1_pq_q)")!=NULL)==stable);
    if(stable){
        assert(strstr(result->glsl,"if (cb1_pq_q <= 0.0)") && strstr(result->glsl,"else {"));
        const char *p=result->glsl;unsigned n=0;
        while((p=strstr(p,"cb1_pq_d = cb1_pq_d * (2.0 - cb1_pq_d);"))){++n;++p;}
        assert(n==4);
        fprintf(stderr,"QUALIFIED_INVERSE_GLSL\n%s\n",result->glsl);
    }
}

/* Independent original ST2084 inverse; not the production P5/doubling path. */
static double ideal_inverse(double q)
{
    double r=pow(fmax(q,0),1/78.84375);
    return 10000*pow(fmax(r-.8359375,0)/(18.8515625-18.6875*r),1/.1593017578125);
}
static double ideal_forward(double nits)
{
    double a=pow(nits/10000,.1593017578125);
    return pow((.8359375+18.8515625*a)/(1+18.6875*a),78.84375);
}
static void inverse_domain(struct reference_gpu *g)
{
    /* Below the original pole; no new mapper ceiling or tiny-value floor. */
    const float q[]={-.1f,0,0x1p-149f,1e-9f,.01f,.5f,.6853817105293274f,1,1.1f};
    float input[sizeof(q)/sizeof(*q)*4],pixels[sizeof(input)/sizeof(*input)];
    unsigned n=sizeof(q)/sizeof(*q);
    for(unsigned i=0;i<n;i++){for(int c=0;c<3;c++)input[4*i+c]=q[i];input[4*i+3]=1;}
    pl_gpu gpu=g->gl->gpu;pl_tex src=reference_texture(gpu,n,1,input),target=reference_texture(gpu,n,1,NULL);
    pl_dispatch dp=pl_dispatch_create(g->log,gpu);assert(dp);pl_dispatch_mark_cb1_stable_pq(dp,true);
    pl_shader sh=pl_dispatch_begin(dp);
    assert(pl_shader_sample_nearest(sh,pl_sample_src(.tex=src,.new_w=n,.new_h=1,.components=4)));
    struct pl_color_space pq={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ};
    pl_shader_linearize(sh,&pq);
    assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=&sh,.target=target)));
    reference_read(gpu,target,0,0,n,1,pixels);
    for(unsigned i=0;i<n;i++)for(int c=0;c<3;c++){
        double actual=203.0*pixels[4*i+c],expected=ideal_inverse(q[i]);assert(isfinite(actual)&&actual>=0);
        if(expected==0)assert(actual==0);
        else assert(fabs(ideal_forward(actual)-q[i])<=1.0/65535);
        if(q[i]>1)assert(actual>10000);
        fprintf(stderr,"INVERSE_DOMAIN q=%.17g c=%d actual_nits=%.17g original_nits=%.17g\n",q[i],c,actual,expected);
    }
    pl_dispatch_destroy(&dp);pl_tex_destroy(gpu,&src);pl_tex_destroy(gpu,&target);
}
struct propagation {bool expected;unsigned passes;};
static void renderer_pass(void *priv,const struct pl_render_info *info)
{
    struct propagation *state=priv;assert(info->pass && info->pass->shader);
    assert(info->pass->shader->params.cb1_stable_pq==state->expected);++state->passes;
}
static void renderer_reset(struct reference_gpu *g)
{
    pl_gpu gpu=g->gl->gpu;float input[]={.5f,.6f,.7f,1},baseline[4],pixels[4];
    pl_tex src=reference_texture(gpu,1,1,input),target=reference_texture(gpu,1,1,NULL);
    struct pl_frame image=reference_frame(src,1,1),output=reference_frame(target,1,1);
    image.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=1000}};
    output.color=image.color;image.repr=output.repr=(struct pl_color_repr){.sys=PL_COLOR_SYSTEM_RGB,
        .levels=PL_COLOR_LEVELS_FULL,.alpha=PL_ALPHA_INDEPENDENT};
    pl_renderer rr=pl_renderer_create(g->log,gpu);assert(rr);
    struct propagation state={0};struct pl_render_params params=pl_render_default_params;
    params.info_callback=renderer_pass;params.info_priv=&state;params.dither_params=NULL;
    const struct pl_frame *frames[]={&image};uint64_t signature=1;float timestamp=0;
    struct pl_frame_mix mix={.num_frames=1,.frames=frames,.signatures=&signature,.timestamps=&timestamp,.vsync_duration=1};
    for(int route=0;route<2;route++)for(int step=0;step<4;step++){
        state.expected=params.cb1_stable_pq=step%2!=0;state.passes=0;
        bool ok=route?pl_render_image_mix(rr,&mix,&output,&params):pl_render_image(rr,&image,&output,&params);
        assert(ok&&state.passes);reference_read(gpu,target,0,0,1,1,pixels);
        if(step==0)memcpy(baseline,pixels,sizeof(pixels));
        if(step==2)assert(!memcmp(baseline,pixels,sizeof(pixels)));
        fprintf(stderr,"RENDERER_PQ_PROPAGATION mix=%d step=%d opt_in=%d passes=%u\n",route,step,state.expected,state.passes);
    }
    pl_renderer_destroy(&rr);pl_tex_destroy(gpu,&src);pl_tex_destroy(gpu,&target);
}
int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    assert(!pl_render_default_params.cb1_stable_pq);
    struct pl_shader_params params={.gpu=g.gl->gpu,.cb1_stable_pq=true};
    pl_shader sh=pl_shader_alloc(g.log,&params);assert(sh);check(sh,true);
    params.cb1_stable_pq=false;pl_shader_reset(sh,&params);check(sh,false);pl_shader_free(&sh);
    pl_dispatch dp=pl_dispatch_create(g.log,g.gl->gpu);assert(dp);
    sh=pl_dispatch_begin(dp);check(sh,false);pl_dispatch_abort(dp,&sh);
    pl_dispatch_mark_cb1_stable_pq(dp,true);sh=pl_dispatch_begin(dp);check(sh,true);pl_dispatch_abort(dp,&sh);
    pl_dispatch_mark_cb1_stable_pq(dp,false);sh=pl_dispatch_begin(dp);check(sh,false);pl_dispatch_abort(dp,&sh);
    inverse_domain(&g);renderer_reset(&g);
    pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);
    puts("PASS bounded inverse domain, default-off emission, shader/dispatch reset and both renderer routes false after true");
}
