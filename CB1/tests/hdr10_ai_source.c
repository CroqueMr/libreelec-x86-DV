/* SPDX-License-Identifier: MIT */
/* Source-plane analysis must match the RGB48 producer exactly. */
#include "reference_test.h"
#include "cb1_hdr10_ingress.h"
#include "cb1_hdr10_extrema.h"
#include "cb1_hdr10_statistics.h"
/* Reject an unnecessary half-resolution temporary while checking the complete
 * preview against independently computed, block-constant limited-range Y. */
static bool preview_budget;
bool __real_pl_tex_recreate(pl_gpu,pl_tex *,const struct pl_tex_params *);
bool __wrap_pl_tex_recreate(pl_gpu gpu,pl_tex *texture,const struct pl_tex_params *p)
{
    if(preview_budget && p->w*p->h>128*72)return false;
    return __real_pl_tex_recreate(gpu,texture,p);
}
static void check_preview_footprint(pl_gpu gpu)
{
    struct pl_frame source={.num_planes=2,.crop={0,0,512,288},
        .repr={.sys=PL_COLOR_SYSTEM_BT_2020_NC,.levels=PL_COLOR_LEVELS_LIMITED,
            .bits={.sample_depth=16,.color_depth=10,.bit_shift=6}},
        .color={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ}};
    for(unsigned plane=0;plane<2;plane++){
        unsigned w=plane?256:512,h=plane?144:288,components=plane?2:1;
        uint16_t *data=malloc(w*h*components*sizeof(*data));assert(data);
        for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)for(unsigned c=0;c<components;c++)
            data[(y*w+x)*components+c]=(plane?512:64+((x/4)*3+(y/4)*5)%875)<<6;
        pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_UNORM,components,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR);assert(fmt);
        source.planes[plane]=(struct pl_plane){.components=components,.component_mapping={plane,plane+1},
            .texture=pl_tex_create(gpu,pl_tex_params(.w=w,.h=h,.format=fmt,.sampleable=true,.initial_data=data))};
        free(data);assert(source.planes[plane].texture);
    }
    struct cb1_hdr10_ingress *ctx=cb1_hdr10_ingress_create(gpu);assert(ctx);pl_tex output;
    preview_budget=true;
    assert(cb1_hdr10_ingress_preview_u16(ctx,&source,&output)==CB1_AI_READY);
    preview_budget=false;
    float data[128*72*4];GLuint fbo;GLint previous;
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&previous);
    assert(pl_opengl_unwrap(gpu,output,NULL,NULL,&fbo));
    glBindFramebuffer(GL_READ_FRAMEBUFFER,fbo);
    glReadPixels(0,0,128,72,GL_RGBA,GL_FLOAT,data);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,previous);assert(glGetError()==GL_NO_ERROR);
    for(unsigned y=0;y<72;y++)for(unsigned x=0;x<128;x++){
        float expected=(float)(_Float16)((float)((x*3+y*5)%875)*9539.f/(128.f*65535.f));
        /* The model's preview is binary16; a final halfway value can round to
         * either adjacent code after the source-plane float arithmetic. */
        for(unsigned c=0;c<3;c++)assert(fabsf(data[(y*128+x)*4+c]-expected)<=0x1p-11f);
        assert(data[(y*128+x)*4+3]==1.f);
    }
    cb1_hdr10_ingress_destroy(&ctx);
    for(unsigned p=0;p<2;p++)pl_tex_destroy(gpu,&source.planes[p].texture);
}
static bool no_compact;
static unsigned compact_denials;
static pl_fmt test_format(pl_gpu gpu,enum pl_fmt_type type,int components,int depth,int host,enum pl_fmt_caps caps)
{
    if(no_compact && type==PL_FMT_UNORM && components==4 && depth==16){++compact_denials;return NULL;}
    return pl_find_fmt(gpu,type,components,depth,host,caps);
}
#define pl_find_fmt test_format
#include "../src/cb1_hdr10_extrema.c"
#undef pl_find_fmt
#include "../src/cb1_hdr10_ai.c"
static void check_producer(pl_gpu gpu,const struct pl_frame *source,const float expected[35],bool benchmark,bool calibration)
{
    struct cb1_hdr10_ai *c=calloc(1,sizeof(*c));assert(c);
    c->ingress=cb1_hdr10_ingress_create(gpu);c->extrema=cb1_hdr10_extrema_create(gpu);
    c->statistics=cb1_hdr10_statistics_create(gpu);c->quantiles=cb1_hdr10_quantiles_create(gpu);
    c->spatial=cb1_hdr10_spatial_create(gpu);c->temporal=cb1_hdr10_temporal_create();
    assert(c->ingress && c->extrema && c->statistics && c->quantiles && c->spatial && c->temporal);
    for(unsigned i=0;i<(benchmark?24:1);i++){
        cb1_hdr10_ai_reset(c,1,1);
        c->last_valid=!calibration;c->last=(struct cb1_ai_identity){1,1,1};c->last_pts=1;
        c->calibration_until=1;
        pl_gpu_finish(gpu);uint64_t start=now_ns();
        assert(cb1_hdr10_ai_submit(c,source,(struct cb1_ai_identity){1,2,1},1.04)==CB1_AI_PENDING);
        pl_gpu_finish(gpu);assert(collect(c)==CB1_AI_READY);
        uint64_t elapsed=elapsed_ns(start);
        if(calibration)assert(!memcmp(c->descriptor.global,expected,35*sizeof(float)));
        else{
            assert(!memcmp(c->descriptor.global,expected,3*sizeof(float)) && c->descriptor.global[18]==expected[18]);
            for(unsigned j=3;j<35;j++)if(j!=18)assert(c->descriptor.global[j]==0);
        }
        if(benchmark && i>=8)printf("ANALYSIS,calibration=%u,%u,%.6f\n",calibration,i-8,elapsed/1e6);
    }
    if(!benchmark)assert(!c->rgb && "Native-plane calibration and steady analysis must not materialize RGB");
    cb1_hdr10_ai_destroy(&c);
}
static unsigned gpu_errors;
static void strict_log(void *priv,enum pl_log_level level,const char *message)
{(void)priv;if(level<=PL_LOG_ERR){++gpu_errors;fprintf(stderr,"%s\n",message);}}
int main(int argc,char **argv){
    bool benchmark=argc>1 && !strcmp(argv[1],"bench");
    setenv("CB1_REFERENCE_TRACE","1",1);
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    check_preview_footprint(gpu);
    pl_log_update(g.log,pl_log_params(.log_cb=strict_log,.log_level=PL_LOG_ERR));
    struct cb1_hdr10_ingress *legacy=cb1_hdr10_ingress_create(gpu);
    struct cb1_hdr10_extrema *ext[2]={cb1_hdr10_extrema_create(gpu),cb1_hdr10_extrema_create(gpu)};
    struct cb1_hdr10_statistics *stat[2]={cb1_hdr10_statistics_create(gpu),cb1_hdr10_statistics_create(gpu)};
    struct cb1_hdr10_quantiles *quant[2]={cb1_hdr10_quantiles_create(gpu),cb1_hdr10_quantiles_create(gpu)};
    assert(legacy && ext[0] && ext[1] && stat[0] && stat[1] && quant[0] && quant[1]);
    unsigned compared=0;double maximum_error=0;
    for(unsigned fixture=0;fixture<50;fixture++){
        if(benchmark && fixture!=4)continue;
        int width=fixture<4?3840:fixture<8?1920:256;
        int height=fixture<4?(fixture%2?1600:2160):fixture<8?1080:144;
        if(fixture==12){width=3842;height=1602;}
        if(fixture==13){width=3840;height=1080;}
        if(fixture>=14){width=3840;height=1080;}
        if(fixture==48){width=3841;height=1081;}
        int padding=fixture%3==0?8:0,depth=fixture&1?12:10;
        bool packed=(fixture%3)!=2,sub=fixture%4!=3;
        bool directed=fixture>=14;
        unsigned dx0=0,dy0=0,dx1=width,dy1=height;
        if(directed){
            padding=8;depth=10;packed=true;sub=fixture!=48;
            if(fixture==15){dx0=3;dy0=1;dx1=4;dy1=2;}
            if(fixture>=16 && fixture<48){
                unsigned n=fixture-16;
                dx0=1+n%4;dy0=1+(n/4)%2;
                dx1=dx0+1+(n/8)%4;dy1=dy0+1+(n/16)%2;
            }
            if(fixture==48){dx0=3;dy0=1;dx1=width-2;dy1=height-2;}
            if(fixture==49){dx0=width/2;dy0=height/2;dx1=dx0+1;dy1=dy0+1;}
        }
        struct pl_frame frame={.num_planes=packed?2:3,.crop={padding,padding,width+padding,height+padding},
            .repr={.sys=PL_COLOR_SYSTEM_BT_2020_NC,.levels=PL_COLOR_LEVELS_LIMITED,
                .bits={.sample_depth=16,.color_depth=depth,.bit_shift=packed?16-depth:0}},
            .color={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ}};
        int fw=width+2*padding,fh=height+2*padding,scale=1<<(depth-8);
        for(int plane=0;plane<frame.num_planes;plane++){
            int w=plane && sub?fw/2:fw,h=plane && sub?fh/2:fh,components=plane && packed?2:1;
            uint16_t *values=calloc((size_t)w*h*components,sizeof(*values));assert(values);
            for(int y=0;y<h;y++)for(int x=0;x<w;x++)for(int c=0;c<components;c++){
                int q;
                if(!plane){
                    bool border=y<padding+16 || y>=fh-padding-16 || x<padding+2 || x>=fw-padding-2;
                    q=border?16*scale:16*scale+(x*13+y*29+fixture*31)%(219*scale+1);
                    if(x==fw-padding-1 && y==fh-padding-1)q=235*scale;
                }else q=128*scale+(fixture%2?0:((x*7+y*23+(plane+c)*101)%(128*scale+1)-64*scale));
                if(directed){
                    bool active=fixture!=14 && x>=padding+(int)dx0 && x<padding+(int)dx1 &&
                        y>=padding+(int)dy0 && y<padding+(int)dy1;
                    q=plane?128*scale:(active?235*scale:16*scale);
                    /* Chroma outside a cropped picture must not bleed into its bounds. */
                    if(fixture==49 && plane && (y<padding/2 || y>=h-padding/2))q=255*scale;
                }
                values[((size_t)y*w+x)*components+c]=q<<(packed?16-depth:0);
            }
            pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_UNORM,components,16,16,PL_FMT_CAP_SAMPLEABLE);assert(fmt);
            frame.planes[plane]=(struct pl_plane){.components=components,.component_mapping={plane,plane+1},
                .texture=pl_tex_create(gpu,pl_tex_params(.w=w,.h=h,.format=fmt,.sampleable=true,.initial_data=values))};
            free(values);assert(frame.planes[plane].texture);
        }
        struct cb1_ai_identity id={fixture+1,1,9};
        cb1_hdr10_extrema_reset(ext[0],id.stream,id.revision);cb1_hdr10_extrema_reset(ext[1],id.stream,id.revision);
        assert(cb1_hdr10_extrema_set_coalesced(ext[0],false));
        const bool optimized=getenv("CB1_REFERENCE_BOUNDS")==NULL;
        assert(cb1_hdr10_extrema_set_coalesced(ext[1],optimized));
        cb1_hdr10_statistics_reset(stat[0],id.stream,id.revision);cb1_hdr10_statistics_reset(stat[1],id.stream,id.revision);
        cb1_hdr10_quantiles_reset(quant[0],id.stream,id.revision);cb1_hdr10_quantiles_reset(quant[1],id.stream,id.revision);
        pl_tex rgb;
        assert(cb1_hdr10_ingress_rgb(legacy,&frame,&rgb)==CB1_AI_READY);
        assert(cb1_hdr10_extrema_submit(ext[0],rgb,id)==CB1_AI_PENDING);
        if(!sub){
            assert(cb1_hdr10_extrema_submit_source(ext[1],&frame,id)==CB1_AI_INCOMPATIBLE);
            for(int plane=0;plane<frame.num_planes;plane++)pl_tex_destroy(gpu,&frame.planes[plane].texture);
            continue;
        }
        /* Kodi can leave alpha blending enabled before an analysis-only pass. */
        glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
        no_compact=getenv("CB1_TEST_NO_COMPACT")!=NULL;
        assert(cb1_hdr10_extrema_submit_source(ext[1],&frame,id)==CB1_AI_PENDING);
        no_compact=false;
        assert(!cb1_hdr10_extrema_set_coalesced(ext[1],!optimized));
        assert(glIsEnabled(GL_BLEND)==GL_TRUE);
        pl_tex pending=cb1_hdr10_extrema_pending(ext[1],id);assert(pending);
        pl_gpu_finish(gpu);
        struct cb1_hdr10_bounds bounds[2];
        assert(cb1_hdr10_extrema_poll(ext[0],id,&bounds[0])==CB1_AI_READY);
        assert(cb1_hdr10_extrema_poll(ext[1],id,&bounds[1])==CB1_AI_READY);
        if(memcmp(bounds,bounds+1,sizeof(bounds[0])))for(unsigned i=0;i<2;i++)
            fprintf(stderr,"bounds variant=%u x=%u..%u y=%u..%u min=%u max=%u\n",i,
                bounds[i].x0,bounds[i].x1,bounds[i].y0,bounds[i].y1,bounds[i].minimum,bounds[i].maximum);
        assert(!memcmp(bounds,bounds+1,sizeof(bounds[0])));
        if(directed){
            assert(bounds[1].x0==dx0 && bounds[1].x1==dx1 &&
                bounds[1].y0==dy0 && bounds[1].y1==dy1);
            if(fixture==14)assert(bounds[1].minimum==0 && bounds[1].maximum==0);
        }
        assert(cb1_hdr10_statistics_submit(stat[0],rgb,bounds[0],id)==CB1_AI_PENDING);
        assert(cb1_hdr10_statistics_queue_source(stat[1],&frame,pending,id,true)==CB1_AI_PENDING);
        assert(cb1_hdr10_quantiles_submit(quant[0],rgb,bounds[0],id)==CB1_AI_PENDING);
        assert(cb1_hdr10_quantiles_queue_source(quant[1],&frame,pending,id)==CB1_AI_PENDING);
        pl_gpu_finish(gpu);float out[2][35];
        assert(gpu_errors==0);
        assert(cb1_hdr10_statistics_poll(stat[0],id,out[0])==CB1_AI_READY);
        assert(cb1_hdr10_statistics_poll_bounds(stat[1],id,bounds[1],out[1])==CB1_AI_READY);
        float ranks[2][7];
        assert(cb1_hdr10_quantiles_poll(quant[0],id,ranks[0])==CB1_AI_READY);
        assert(cb1_hdr10_quantiles_poll_bounds(quant[1],id,bounds[1],ranks[1])==CB1_AI_READY);
        assert(!memcmp(ranks[0],ranks[1],sizeof(ranks[0])) && "Native-plane calibration quantiles must match RGB48 exactly");
        for(unsigned j=0;j<35;j++){
            double error=fabs((double)out[0][j]-out[1][j]);maximum_error=fmax(maximum_error,error);
            if(error!=0)fprintf(stderr,"fixture=%u field=%u old=%.9g new=%.9g\n",fixture,j,out[0][j],out[1][j]);
            assert(error==0);
        }
        cb1_hdr10_statistics_reset(stat[1],id.stream,id.revision);
        assert(cb1_hdr10_statistics_queue_source(stat[1],&frame,pending,id,false)==CB1_AI_PENDING);
        pl_gpu_finish(gpu);float luma[35];
        assert(cb1_hdr10_statistics_poll_bounds(stat[1],id,bounds[1],luma)==CB1_AI_READY);
        assert(!memcmp(luma,out[0],3*sizeof(float)) && luma[18]==out[0][18]);
        for(unsigned j=3;j<35;j++)if(j!=18)assert(luma[j]==0);
        if(fixture>=4 && fixture<=6){
            check_producer(gpu,&frame,out[0],benchmark,false);
            float calibration[35];memcpy(calibration,out[0],sizeof(calibration));
            memcpy(calibration+4,ranks[0],sizeof(ranks[0]));
            check_producer(gpu,&frame,calibration,benchmark,true);
        }
        ++compared;
        printf("fixture=%u %dx%d depth=%d packed=%d sub=%d crop=%d bounds_exact=true mean_exact=%s\n",
            fixture,width,height,depth,packed,sub,padding,out[0][2]==out[1][2]?"true":"false");fflush(stdout);
        for(int plane=0;plane<frame.num_planes;plane++)pl_tex_destroy(gpu,&frame.planes[plane].texture);
    }
    printf("compared=%u max_descriptor_error=%.9g\n",compared,maximum_error);
    if(getenv("CB1_TEST_NO_COMPACT"))assert(compact_denials>0);
    cb1_hdr10_ingress_destroy(&legacy);
    cb1_hdr10_extrema_destroy(&ext[0]);cb1_hdr10_extrema_destroy(&ext[1]);
    cb1_hdr10_statistics_destroy(&stat[0]);cb1_hdr10_statistics_destroy(&stat[1]);
    cb1_hdr10_quantiles_destroy(&quant[0]);cb1_hdr10_quantiles_destroy(&quant[1]);reference_gpu_destroy(&g);
}


