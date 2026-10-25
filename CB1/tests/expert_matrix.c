/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reference_test.h"
#include <libplacebo/shaders/custom.h>
static bool baseline;
static enum pl_color_primaries nominal=PL_COLOR_PRIM_DISPLAY_P3;
static bool cache_failure;
static bool cache_storage;
static bool cache_warp;
static unsigned rejected_allocations;
static unsigned fused_calls;
static bool compare_conversion(pl_shader sh,const struct pl_custom_shader *params)
{
    if(cache_warp && !baseline && params->description &&
       !strcmp(params->description,"Cached CM2.9 HDR10 chroma and output mapping"))
        assert(params->num_descriptors==2 && "Reuse the PQ encoder for AMD's cache coordinates");
    if(!params->description || strcmp(params->description,
        "Expert nominal LINEAR to BT2020 PQ before caller overlays"))
        return pl_shader_custom(sh,params);
    if(!baseline || cache_failure || cache_storage){
        assert(params->num_variables==3 && "Compose Expert's colour matrices before the pixel shader");
        fused_calls++;
        return pl_shader_custom(sh,params);
    }
    pl_matrix3x3 xyz=pl_get_rgb2xyz_matrix(pl_raw_primaries_get(nominal));
    pl_matrix3x3 bt=pl_get_xyz2rgb_matrix(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
    for(unsigned i=0;i<3;i++)for(unsigned j=i+1;j<3;j++){
        float v=xyz.m[i][j];xyz.m[i][j]=xyz.m[j][i];xyz.m[j][i]=v;
        v=bt.m[i][j];bt.m[i][j]=bt.m[j][i];bt.m[j][i]=v;
    }
    struct pl_shader_var vars[4];memcpy(vars,params->variables,3*sizeof(*vars));
    vars[0].data=&bt;
    vars[3]=(struct pl_shader_var){.var=pl_var_mat3("reference_xyz"),.data=&xyz,.dynamic=true};
    struct pl_custom_shader old=*params;old.variables=vars;old.num_variables=4;
    old.header="#define CB1_REFERENCE_TRANSFORM(v) (reference_bt2020*(reference_xyz*(v)))\n";
    return pl_shader_custom(sh,&old);
}
#define pl_shader_custom compare_conversion
static bool compare_image(pl_renderer,const struct pl_frame *,const struct pl_frame *,const struct pl_render_params *);
#define pl_render_image compare_image
static pl_tex test_texture(pl_gpu,const struct pl_tex_params *);
#define pl_tex_create test_texture
#define DVBRIDGE_PQ_ENCODER_TEST 1
#include "../src/dvbridge_render.c"
#undef pl_shader_custom
#undef pl_render_image
#undef pl_tex_create

static pl_tex test_texture(pl_gpu gpu,const struct pl_tex_params *p)
{
    if(cache_failure && !baseline && p->w==8*CM29_GPU_MAP_GRID &&
       p->h==CM29_GPU_MAP_GRID*CM29_GPU_MAP_GRID/8){rejected_allocations++;return NULL;}
    if(cache_storage && baseline && p->w==8*CM29_GPU_MAP_GRID &&
       p->h==CM29_GPU_MAP_GRID*CM29_GPU_MAP_GRID/8){
        struct pl_tex_params old=*p;
        old.format=pl_find_fmt(gpu,PL_FMT_FLOAT,4,32,32,p->format->caps);
        assert(old.format);return pl_tex_create(gpu,&old);
    }
    return pl_tex_create(gpu,p);
}

static bool compare_image(pl_renderer r,const struct pl_frame *s,const struct pl_frame *t,const struct pl_render_params *p)
{
    if(!baseline || cache_storage)return pl_render_image(r,s,t,p);
    struct pl_render_params candidate=*p;struct pl_frame target=*t;
    const struct pl_hook *hooks[4];struct pl_hook replaced;struct reference_hook copy,*original=NULL;
    assert(p->num_hooks<=4);
    for(int i=0;i<p->num_hooks;i++){
        hooks[i]=p->hooks[i];
        if(hooks[i]->hook==reference_output){
            assert(!original);original=hooks[i]->priv;copy=*original;
            assert(!copy.cm4);copy.gpu_map_eligible=false;copy.neutral_cm29=true;
            if(!cache_failure)copy.neutral_target.primaries=nominal;
            replaced=*hooks[i];replaced.priv=&copy;hooks[i]=&replaced;
        }
    }
    assert(original);candidate.hooks=hooks;target.color=copy.neutral_target;
    bool ok=pl_render_image(r,s,&target,&candidate);*original=copy;return ok;
}

/* Independent display-referred BT.2124 metric, not libplacebo's IPT mapper.
 * https://www.itu.int/rec/R-REC-BT.2124/en */
static double metric_eotf(double q)
{
    double t=pow(fmax(q,0),32.0/2523);
    return 10000*pow(fmax(t-3424.0/4096,0)/(2413.0/128-2392.0/128*t),16384.0/2610);
}
static double metric_pq(double n)
{
    double t=pow(fmax(n,0)/10000,2610.0/16384);
    return pow((3424.0/4096+2413.0/128*t)/(1+2392.0/128*t),2523.0/32);
}
static void metric_itp(const float *pixel,double itp[3],double *luma)
{
    double r=metric_eotf(pixel[0]),g=metric_eotf(pixel[1]),b=metric_eotf(pixel[2]);
    double l=metric_pq((1688*r+2146*g+262*b)/4096);
    double m=metric_pq((683*r+2951*g+462*b)/4096);
    double s=metric_pq((99*r+309*g+3688*b)/4096);
    itp[0]=.5*(l+m);itp[1]=.5*(6610*l-13613*m+7003*s)/4096;
    itp[2]=(17933*l-17390*m-543*s)/4096;
    *luma=.2627*r+.6780*g+.0593*b;
}
static int metric_order(const void *a,const void *b)
{double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y);}
static void metric_compare(const float *candidate,const float *reference)
{
    assert(fabs(metric_eotf(.751827096247041)-1000)<1e-8);
    const size_t n=64u*64*64;double *errors=malloc(n*sizeof(*errors));assert(errors);
    double shadow=0,relative=0,previous_gray=0;size_t over=0,k=0;
    for(unsigned r=0;r<64;r++)for(unsigned g=0;g<64;g++)for(unsigned b=0;b<64;b++){
        unsigned xb=g<60?g:59,yb=g-xb;
        size_t pixel=((size_t)(64*yb+b)*3840+64*xb+r)*4;
        double a[3],v[3],ya,yb_nits;
        metric_itp(candidate+pixel,a,&ya);metric_itp(reference+pixel,v,&yb_nits);
        if(r==g && g==b){assert(ya+1e-6>=previous_gray);previous_gray=ya;}
        double de=720*sqrt((a[0]-v[0])*(a[0]-v[0])+(a[1]-v[1])*(a[1]-v[1])+(a[2]-v[2])*(a[2]-v[2]));
        assert(isfinite(de));errors[k++]=de;over+=de>1;
        if(yb_nits<10)shadow=fmax(shadow,fabs(ya-yb_nits));
        if(yb_nits>=1)relative=fmax(relative,fabs(ya-yb_nits)/yb_nits);
    }
    qsort(errors,n,sizeof(*errors),metric_order);
    fprintf(stderr,"BT2124 colours=%zu max=%.9f p99=%.9f p95=%.9f median=%.9f above1=%zu shadow_delta_nits=%.9f relativeY=%.9f\n",
        n,errors[n-1],errors[n*99/100],errors[n*95/100],errors[n/2],over,shadow,relative);
    assert(errors[n-1]<=2 && errors[n*99/100]<=1 && errors[n*95/100]<=.5 &&
           over<=n/100 && shadow<=.15 && relative<=.025 &&
           "Conversion-only precision budget; Master always remains exact");
    free(errors);
}

int main(int argc,char **argv)
{
    cache_failure=argc==2 && !strcmp(argv[1],"cache-failure");
    cache_storage=argc==2 && !strcmp(argv[1],"cache-storage");
    cache_warp=argc==2 && !strcmp(argv[1],"cache-warp");
    assert(argc==1 || argc==3 || argc==4 || cache_failure || cache_storage || cache_warp);
    double peak=argc>=3?atof(argv[1]):2500;
    double master=argc==4?atof(argv[3]):4000;
    enum dvbridge_gamut gamut=argc>=3?atoi(argv[2]):DVBRIDGE_GAMUT_P3_D65;
    assert(master>=100 && master<=10000);
    assert(peak>=100 && peak<=10000 &&
           (gamut==DVBRIDGE_GAMUT_P3_D65 || gamut==DVBRIDGE_GAMUT_BT709));
    if(gamut==DVBRIDGE_GAMUT_BT709)nominal=PL_COLOR_PRIM_BT_709;
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    if(cache_warp && !strstr((const char *)glGetString(GL_RENDERER),"radeonsi"))return 77;
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=3;
    unsigned source_peak=lround(dv_ideal_pq(master)*4095);
    av_dovi_get_color(m)->source_max_pq=source_peak;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,source_peak,1500}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=6,.l6={.max_luminance=master}};
    *av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,
        .trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=-1}};
    if(cache_storage){
        av_dovi_get_ext(m,2)->l2=(AVDOVIDmLevel2){.target_max_pq=3079,
            .trim_slope=2176,.trim_offset=2016,.trim_power=1984,
            .trim_chroma_weight=1960,.trim_saturation_gain=2304,.ms_weight=-1};
        av_dovi_get_header(m)->disable_residual_flag=0;
        av_dovi_get_mapping(m)->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
        for(unsigned c=0;c<3;c++)av_dovi_get_mapping(m)->nlq[c]=
            (AVDOVINLQParams){.vdr_in_max=4096,.nlq_offset=512,.linear_deadzone_slope=1};
    }
    void *original=av_memdup(m,bytes);assert(original);
    const size_t count=3840u*2160;float *data=malloc(count*4*sizeof(*data));assert(data);
    pl_matrix3x3 matrix={{{3.06441879,-2.16597676,.10155818},
        {-.65612108,1.78554118,-.12943749},{.01736321,-.04725154,1.03004253}}};
    pl_matrix3x3_invert(&matrix);
    double levels[64];for(unsigned k=0;k<64;k++)levels[k]=master*pow(k/63.0,4);
    for(unsigned y=0;y<2160;y++)for(unsigned x=0;x<3840;x++){
        double rgb[3]={levels[x%64],levels[(x/64+y/64)%64],levels[y%64]};
        for(unsigned c=0;c<3;c++){
            double cone=0;for(unsigned j=0;j<3;j++)cone+=matrix.m[c][j]*rgb[j];
            data[4*((size_t)y*3840+x)+c]=dv_ideal_pq(fmax(0,cone));
        }
        data[4*((size_t)y*3840+x)+3]=1;
    }
    pl_tex input=reference_texture(gpu,3840,2160,data);free(data);
    struct pl_frame source=reference_frame(input,3840,2160);
    pl_tex el=NULL;struct pl_frame enhancement;
    if(cache_storage){
        float residual[16];for(unsigned i=0;i<16;i++)residual[i]=i%4==3?1:512.0f/1023;
        el=reference_texture(gpu,2,2,residual);enhancement=reference_frame(el,2,2);
        source.enhancement_layer=&enhancement;
    }
    struct dvbridge_policy p=reference_policy();p.tv.peak_nits=peak;p.tv.gamut=gamut;
    struct dvbridge_identity id={1,1,p.revision};
    pl_tex out=reference_texture(gpu,3840,2160,NULL);
    float *first=malloc(count*4*sizeof(*first)),*second=malloc(count*4*sizeof(*second));assert(first && second);
    for(unsigned pass=0;pass<2;pass++){
        baseline=pass;
        if(cache_storage && pass){
            assert(r->cm29_tail_atlas->params.format->type==PL_FMT_UNORM);
            dvbridge_renderer_destroy(r);r=dvbridge_renderer_create(gpu);assert(r);
        }
        assert(dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,m,bytes,0,0,
            (struct dvbridge_geometry){3840,2160,0,0,3840,2160},out,false,false,10));
        reference_read(gpu,out,0,0,3840,2160,pass?second:first);id.picture++;
    }
    double maximum=0;unsigned changed=0;
    for(size_t i=0;i<count*4;i++){
        assert(isfinite(first[i]) && isfinite(second[i]));
        maximum=fmax(maximum,fabs(first[i]-second[i])*1023);
        changed+=first[i]!=second[i];
        size_t pixel=i/4*4;
        if(second[pixel]==0 && second[pixel+1]==0 && second[pixel+2]==0)
            assert(first[i]==second[i]);
    }
    fprintf(stderr,"Expert composed matrix max10=%.9f changed=%u\n",maximum,changed);
    assert(fused_calls && !memcmp(m,original,bytes));metric_compare(first,second);
    if(!cache_failure && !cache_storage && peak<=2500){
        baseline=false;
        assert(dvbridge_render_hdr10_policy_direct(r,&p,&id,&source,m,bytes,0,0,
            (struct dvbridge_geometry){3840,2160,0,0,3840,2160},out,false,false,10));
        reference_read(gpu,out,0,0,3840,2160,second);
        assert(!memcmp(first,second,count*4*sizeof(*first)) &&
               "Cold and reused neutral-cache pictures must match exactly");
    }
    if(cache_failure){
        assert(rejected_allocations==1 && !r->cm29_tail_atlas && !r->cm29_tail_key_valid);
        assert(!memcmp(first,second,count*4*sizeof(*first)) &&
            "An unavailable Expert cache must restore the fused dense path exactly");
    }else if(cache_storage){
        assert(r->cm29_tail_key_valid && cm29_gpu_map_build_count==2 &&
               r->cm29_tail_atlas->params.format->type==PL_FMT_FLOAT);
    }else if(peak<=2500){
        assert(r->cm29_tail_key_valid && cm29_gpu_map_build_count==1);
        assert(r->cm29_tail_atlas->params.format->type==PL_FMT_UNORM &&
               r->cm29_tail_atlas->params.format->component_depth[0]==16);
    }else assert(!r->cm29_tail_atlas && !r->cm29_tail_key_valid);
    free(first);free(second);av_free(original);av_free(m);
    pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&el);pl_tex_destroy(gpu,&out);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);
}
