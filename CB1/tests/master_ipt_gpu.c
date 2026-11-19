/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"
static unsigned render_calls;
static unsigned reference_contract;
static bool counted_render(pl_renderer renderer,const struct pl_frame *source,
    const struct pl_frame *target,const struct pl_render_params *params)
{
    ++render_calls;
    if(params->cb1_dovi_reference)reference_contract=params->cb1_dovi_reference->contract;
    return pl_render_image(renderer,source,target,params);
}
static bool counted_active_rows(pl_renderer renderer,const struct pl_frame *source,
    const struct pl_frame *target,const struct pl_render_params *params,int top,int bottom)
{
    ++render_calls;
    if(params->cb1_dovi_reference)reference_contract=params->cb1_dovi_reference->contract;
    return pl_render_image_cb1_active_rows(renderer,source,target,params,top,bottom);
}
#define pl_render_image counted_render
#define pl_render_image_cb1_active_rows counted_active_rows
#include "../src/dvbridge_render.c"
#undef pl_render_image
#undef pl_render_image_cb1_active_rows

static void table_layout(struct dvbridge_renderer *r,bool compact)
{
    r->master_ipt_compact=compact;
    for(int i=0;i<2;i++)pl_tex_destroy(r->gpu,&r->ipt_pq[i]);
}

/* Independent long-double oracle, with Gauss-Jordan inversion of wire matrices. */
static void solve(const int16_t matrix[9],long double scale,long double v[3])
{
    long double a[3][4];
    for(int i=0;i<3;i++){for(int j=0;j<3;j++)a[i][j]=matrix[i*3+j]/scale;a[i][3]=v[i];}
    for(int i=0;i<3;i++) {
        long double d=a[i][i]; assert(fabsl(d)>1e-12L);
        for(int j=i;j<4;j++)a[i][j]/=d;
        for(int k=0;k<3;k++)if(k!=i){d=a[k][i];for(int j=i;j<4;j++)a[k][j]-=d*a[i][j];}
    }
    for(int i=0;i<3;i++)v[i]=a[i][3];
}
static long double transfer(long double x,bool encode)
{
    x=fminl(1,fmaxl(0,x));
    long double p=powl(x,encode?2610.L/16384:32.L/2523);
    return encode?powl((3424.L/4096+2413.L/128*p)/(1+2392.L/128*p),2523.L/32):
        powl(fmaxl(p-3424.L/4096,0)/(2413.L/128-2392.L/128*p),16384.L/2610);
}
static void oracle(const AVDOVIColorMetadata *m,const double input[3],long double out[3])
{
    static const int16_t a[9]={8194,799,1681,8194,-933,1091,8194,267,-5545};
    static const int16_t b[9]={17080,-348,-348,-348,17080,-348,-348,-348,17080};
    long double rgb[3]={0};
    for(int i=0;i<3;i++) {
        for(int j=0;j<3;j++)rgb[i]+=(long double)m->ycc_to_rgb_matrix[i*3+j].num/m->ycc_to_rgb_matrix[i*3+j].den*
            (input[j]-(long double)m->ycc_to_rgb_offset[j].num/m->ycc_to_rgb_offset[j].den);
        rgb[i]=transfer(rgb[i],false);
    }
    for(int i=0;i<3;i++) {out[i]=0;for(int j=0;j<3;j++)out[i]+=(long double)m->rgb_to_lms_matrix[3*i+j].num/m->rgb_to_lms_matrix[3*i+j].den*rgb[j];}
    solve(b,16384,out);
    for(int i=0;i<3;i++)out[i]=transfer(out[i],true);
    solve(a,8192,out);out[1]+=.5L;out[2]+=.5L;
}
static void scaled_ipt_witness(struct reference_gpu *g,struct dvbridge_renderer *r)
{
    const int sizes[][2]={{1920,1080},{2560,1440},{3840,2020},{1920,800},{2048,1152}};
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    av_dovi_get_header(m)->vdr_bit_depth=12;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    c->signal_bit_depth=12;c->signal_full_range_flag=1;
    for(int i=0;i<9;i++){
        c->ycc_to_rgb_matrix[i]=(AVRational){dvbridge_output_ycc[i],8192};
        c->rgb_to_lms_matrix[i]=(AVRational){dvbridge_output_lms[i],16384};
    }
    for(int i=0;i<3;i++)c->ycc_to_rgb_offset[i]=(AVRational){1,i?2:16};
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1200}};
    pl_tex target=pl_tex_create(g->gl->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(g->gl->gpu,"rgba8"),.renderable=true));assert(target);
    size_t count=(size_t)3840*2160*4;
    uint8_t *a=malloc(count),*b=malloc(count);assert(a&&b);
    GLuint fbo;glGenFramebuffers(1,&fbo);
    for(unsigned test=0;test<sizeof(sizes)/sizeof(*sizes);test++){
        int w=sizes[test][0],h=sizes[test][1],height=(int)((int64_t)h*3840/w);
        struct pl_frame frame={.num_planes=2,.crop={0,0,w,h},
            .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
        for(int p=0;p<2;p++){
            frame.planes[p]=(struct pl_plane){.components=p?2:1,.component_mapping={p,2},.shift_x=p?-.5f:0};
            frame.planes[p].texture=pl_tex_create(g->gl->gpu,pl_tex_params(
                .w=p?w/2:w,.h=p?h/2:h,.format=pl_find_fmt(g->gl->gpu,PL_FMT_UNORM,p?2:1,16,16,PL_FMT_CAP_SAMPLEABLE),
                .sampleable=true,.blit_dst=true,.host_writable=true));assert(frame.planes[p].texture);
            if(p)pl_tex_clear(g->gl->gpu,frame.planes[p].texture,(float[4]){32768.f/65535,32768.f/65535,0,1});
            else{
                uint16_t *y=malloc((size_t)w*h*2);assert(y);
                for(int row=0;row<h;row++)for(int x=0;x<w;x++)
                    y[row*w+x]=(row<h/4?256:row>3*h/4?768:512)<<6;
                assert(pl_tex_upload(g->gl->gpu,pl_tex_transfer_params(.tex=frame.planes[p].texture,.ptr=y)));free(y);
            }
        }
        struct dvbridge_geometry geometry={w,h,0,(2160-height)/2,3840,height};
        for(int flip=0;flip<2;flip++){
            dvbridge_renderer_reset(r);
            enum cb1_master_status status=dvbridge_render_master_reference_ipt(r,&frame,m,bytes,test+1,NAN,geometry,target,flip,NULL);
            if(status!=CB1_MASTER_READY)fprintf(stderr,"IPT geometry %dx%d flip%d status%d\n",w,h,flip,status);
            assert(status==CB1_MASTER_READY);
            unsigned packets;const uint32_t *wire=dvbridge_packets(dvbridge_render_candidate(r),&packets);
            assert(packets && wire[5+61]==2);
            glBindFramebuffer(GL_FRAMEBUFFER,fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g->gl->gpu,target,NULL,NULL,NULL),0);
            glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,flip?b:a);
            assert(glGetError()==GL_NO_ERROR);glBindFramebuffer(GL_FRAMEBUFFER,0);
            assert(dvbridge_render_commit(r));
        }
        for(int row=0;row<2160;row++)assert(!memcmp(a+(size_t)row*3840*4,b+(size_t)(2159-row)*3840*4,3840*4));
        /* Flat bands have an independent colour oracle and known placement. */
        for(int band=0;band<3;band++){
            const double levels[]={.25,.5,.75},positions[]={.125,.5,.875};
            double input[3]={levels[band],.5,.5};long double expected[3];
            oracle(c,input,expected);
            int row=geometry.y+(int)(positions[band]*height);
            const uint8_t *pixel=a+((size_t)row*3840+2000)*4;
            for(int x=0;x<2;x++){
                int values[]={pixel[4*x+1]*16+(pixel[4*x+2]&15),
                              pixel[4*x]*16+(pixel[4*x+2]>>4)};
                for(int k=0;k<2;k++)assert(abs(values[k]-(int)floorl(expected[k?x+1:0]*4096+.5L))<=1);
            }
        }
        for(int p=0;p<2;p++)pl_tex_destroy(g->gl->gpu,&frame.planes[p].texture);
    }
    glDeleteFramebuffers(1,&fbo);free(a);free(b);pl_tex_destroy(g->gl->gpu,&target);av_free(m);
    puts("PASS IPT-only 1080p/1440p/cropped/noninteger geometries, exact orientation and IPT metadata");
}

int main(int argc,char **argv)
{
    struct reference_gpu g=reference_gpu_create();
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    av_dovi_get_header(m)->vdr_bit_depth=12;c->signal_bit_depth=12;c->signal_full_range_flag=1;
    for(int i=0;i<9;i++) {
        c->ycc_to_rgb_matrix[i]=(AVRational){dvbridge_output_ycc[i],8192};
        c->rgb_to_lms_matrix[i]=(AVRational){dvbridge_output_lms[i],16384};
    }
    const int witness=argc>1?atoi(argv[1]):0;
    if(witness==1)for(int i=0;i<9;i++)c->rgb_to_lms_matrix[i]=(AVRational){i%4==0?16384:0,16384};
    if(witness==2) {
        const int16_t lms[]={6988,8676,720,2692,12116,1576,200,828,15356};
        for(int i=0;i<9;i++)c->rgb_to_lms_matrix[i]=(AVRational){lms[i],16384};
        c->ycc_to_rgb_matrix[2].num+=3;c->ycc_to_rgb_matrix[7].num-=7;
    }
    for(int i=0;i<3;i++)c->ycc_to_rgb_offset[i]=(AVRational){1,i?2:16};
    m->num_ext_blocks=1;*av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1200}};
    struct cb1_master_ipt plan;assert(cb1_master_ipt_prepare(&plan,m,bytes));
    /* Full-width ramps include distinct pair luminances and saturated excursions. */
    float *input=malloc(3840*4*sizeof(float));assert(input);
    long double expected[3840][3]; double max_cpu=0;
    for(int x=0;x<3840;x++) {
        double v[3]={(256+(x%877)*4)/4096.,(.5+(x/877-2)*.1),(.5+(x/439%5-2)*.1)},actual[3];
        if(x<1024){v[0]=(256+x*3.425)/4096.;v[1]=v[2]=.5;}
        oracle(c,v,expected[x]);cb1_master_ipt_convert(&plan,v,actual);
        for(int k=0;k<3;k++){input[x*4+k]=v[k]*(4096./4095);max_cpu=fmax(max_cpu,fabs(actual[k]-(double)expected[x][k])*4096);}
        input[x*4+3]=1;
    }
    pl_tex source=reference_texture(g.gl->gpu,3840,1,input);
    pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);
    pl_tex target=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true,.sampleable=true));assert(target);
    pl_dispatch dp=pl_dispatch_create(NULL,g.gl->gpu);pl_shader sh=pl_dispatch_begin(dp);
    uint32_t empty[128]={0};
    pl_tex pq[2]={0};assert(cb1_master_ipt_tables(g.gl->gpu,pq,false));
    for(int encode=0;encode<2;encode++) {
        const int indices[]={24576,255,65536};
        for(size_t sample=0;sample<sizeof(indices)/sizeof(indices[0]);sample++) {
            float samples[4];int i=indices[sample];
            reference_read(g.gl->gpu,pq[encode],i%pq[encode]->params.w,i/pq[encode]->params.w,1,1,samples);
            for(int side=0;side<2;side++) {
                long double x=(i+side<65536?i+side:65536)/65536.L;
                long double expected=transfer(encode?x*x*x*x:x,encode);
                assert(fabsl(samples[side]-expected)<1e-7L);
            }
        }
    }
    struct active_mask mask={.packets=empty,.rect={0,0,3840,2160},.source_domain=true,.reference_transport=true,.ipt=&plan,
        .ipt_pq=pq,.scaled_reference=source,.scaled_rect={0,0,1,0}};
    struct pl_hook_params hook={.sh=sh,.stage=PL_HOOK_OUTPUT};
    assert(!pack_active_area(&mask,&hook).failed);
    assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=&sh,.target=target)));
    uint8_t pixels[3840*4];GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,target,NULL,NULL,NULL),0);
    glReadPixels(0,10,3840,1,GL_RGBA,GL_UNSIGNED_BYTE,pixels);assert(glGetError()==GL_NO_ERROR);
    int max_error=0,different=0;
    for(int x=0;x<3840;x++) {
        int got[]={pixels[4*x+1]*16+(pixels[4*x+2]&15),pixels[4*x]*16+(pixels[4*x+2]>>4)};
        long double e[]={expected[x][0],expected[x&~1][(x&1)?2:1]};
        for(int k=0;k<2;k++) {
            int wanted=(int)fminl(4095,fmaxl(0,floorl(e[k]*4096+.5L))),err=abs(wanted-got[k]);
            if(err>max_error){max_error=err;fprintf(stderr,"max x=%d component=%d expected=%d actual=%d\n",x,k,wanted,got[k]);}if(err)different++;
        }
    }
    printf("IPT oracle matrix %d: CPU max %.9g codes; GPU max %d codes; differing %d / 7680 components\n",witness,max_cpu,max_error,different);
    fflush(stdout);
    assert(max_cpu<1e-6 && max_error<=1);
    glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);pl_dispatch_destroy(&dp);
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    struct pl_frame frame={.num_planes=2,.crop={0,0,3840,2160},
        .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
    for(int i=0;i<2;i++) {
        pl_fmt format=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,i?2:1,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
        frame.planes[i]=(struct pl_plane){.components=i?2:1,.component_mapping={i,2},.shift_x=i?-.5f:0};
        frame.planes[i].texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=i?1920:3840,.h=i?1080:2160,
            .format=format,.sampleable=true,.renderable=true,.blit_dst=true));assert(frame.planes[i].texture);
        pl_tex_clear(g.gl->gpu,frame.planes[i].texture,(float[4]){32768.f/65535,32768.f/65535,0,1});
    }
    struct dvbridge_geometry geo={3840,2160,0,0,3840,2160};
    uint8_t *before=malloc((size_t)3840*2160*4),*after=malloc((size_t)3840*2160*4);assert(before&&after);
    glGenFramebuffers(1,&fbo);
    for(int pass=0;pass<3;pass++) {
        dvbridge_renderer_reset(r);
        render_calls=0;
        const enum cb1_master_status status=pass==1?
            dvbridge_render_master_reference_ipt(r,&frame,m,bytes,1,NAN,geo,target,false,NULL):
            dvbridge_render_master_reference(r,&frame,m,bytes,1,NAN,geo,target,false,NULL);
        assert(status==CB1_MASTER_READY);
        if(pass==1 && r->fragment_quad) {
            const char *renderer=(const char *)glGetString(GL_RENDERER);
            assert(r->ipt_pq[0]->params.format->num_components==
                (renderer && strstr(renderer,"radeonsi")?1:2));
            fprintf(stderr,"full-frame IPT render submissions: %u\n",render_calls);
            assert(render_calls==1);
            unsigned (*paired_rows)(void)=dlsym(RTLD_DEFAULT,"pl_cb1_dovi_reference_paired_rows_abi");
            assert(paired_rows && paired_rows()==1 && reference_contract==2);
        }
        if(pass!=1)assert(reference_contract==2);
        glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,target,NULL,NULL,NULL),0);
        if(pass!=1)glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,pass?after:before);
        else {
            uint8_t pixel[8];glReadPixels(2000,1000,2,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
            double v[3]={.5,.5,.5};long double e[3];oracle(c,v,e);
            for(int x=0;x<2;x++) {
                int values[]={pixel[4*x+1]*16+(pixel[4*x+2]&15),pixel[4*x]*16+(pixel[4*x+2]>>4)};
                for(int k=0;k<2;k++)assert(abs(values[k]-(int)floorl(e[k?x+1:0]*4096+.5L))<=1);
            }
            unsigned count;const uint32_t *packets=dvbridge_packets(dvbridge_render_candidate(r),&count);
            assert(count && packets[5+61]==2);
        }
        assert(glGetError()==GL_NO_ERROR);glBindFramebuffer(GL_FRAMEBUFFER,0);
        assert(dvbridge_render_commit(r));
    }
    assert(!memcmp(before,after,(size_t)3840*2160*4));free(before);free(after);
    /* Compare the fused route with the preserved materialized route on edges. */
    const bool quad=r->fragment_quad;
    if(quad) {
        size_t frame_bytes=(size_t)3840*2160*4;
        uint16_t *samples=malloc((size_t)3840*2160*2);assert(samples);
        for(int plane=0;plane<2;plane++) {
            int w=plane?1920:3840,h=plane?1080:2160,components=plane?2:1;
            uint32_t seed=123456789;
            for(size_t i=0;i<(size_t)w*h*components;i++) {
                seed=1664525u*seed+1013904223u;
                samples[i]=(64+(seed>>16)%877)<<6;
            }
            glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,frame.planes[plane].texture,NULL,NULL,NULL));
            glTexSubImage2D(GL_TEXTURE_2D,0,0,0,w,h,plane?GL_RG:GL_RED,GL_UNSIGNED_SHORT,samples);
        }
        free(samples);
        uint8_t *control=malloc(frame_bytes),*fused=malloc(frame_bytes);assert(control&&fused);
        m->num_ext_blocks=2;
        *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=5,.l5={.left_offset=128,.right_offset=120,.top_offset=276,.bottom_offset=277}};
        for(int flip=0;flip<2;flip++)for(int route=0;route<4;route++) {
            r->fragment_quad=(route&1)?quad:false;
            table_layout(r,(route&2)!=0);
            dvbridge_renderer_reset(r);
            assert(dvbridge_render_master_reference_ipt(r,&frame,m,bytes,2,NAN,geo,target,flip,NULL)==CB1_MASTER_READY);
            glBindFramebuffer(GL_FRAMEBUFFER,fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,target,NULL,NULL,NULL),0);
            glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,route?fused:control);
            assert(glGetError()==GL_NO_ERROR);
            if(route)assert(!memcmp(control,fused,frame_bytes));
            glBindFramebuffer(GL_FRAMEBUFFER,0);
            assert(dvbridge_render_commit(r));
        }
        free(control);free(fused);r->fragment_quad=quad;
        puts("PASS exact fused IPT carrier, random source, asymmetric L5, both orientations");
    }
    if(quad) {
        AVDOVIReshapingCurve saved[3];
        memcpy(saved,av_dovi_get_mapping(m)->curves,sizeof(saved));
        size_t frame_bytes=(size_t)3840*2160*4;
        uint8_t *control=malloc(frame_bytes),*fused=malloc(frame_bytes);assert(control&&fused);
        uint32_t packets[3*128];unsigned packet_count=0;
        for(int phase=0;phase<2;phase++)for(int revision=0;revision<4;revision++) {
            frame.planes[1].shift_y=phase?-.5f:0;
            for(int component=1;component<3;component++) {
                AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(m)->curves[component];
                memset(curve,0,sizeof(*curve));curve->num_pivots=2;
                curve->pivots[0]=64;curve->pivots[1]=940;
                curve->mapping_idc[0]=AV_DOVI_MAPPING_MMR;
                curve->mmr_order[0]=revision<3?revision+1:3;
                curve->mmr_constant[0]=256;
                for(int order=0;order<curve->mmr_order[0];order++)for(int axis=0;axis<7;axis++)
                    curve->mmr_coef[0][order][axis]=(axis&1?-1:1)*(25+axis*7+order*13+revision*5);
                curve->mmr_coef[0][0][component]+=3000;
            }
            for(int flip=0;flip<2;flip++)for(int route=0;route<4;route++) {
                r->fragment_quad=(route&1)?quad:false;table_layout(r,(route&2)!=0);dvbridge_renderer_reset(r);
                assert(dvbridge_render_master_reference_ipt(r,&frame,m,bytes,2,NAN,geo,target,flip,NULL)==CB1_MASTER_READY);
                glBindFramebuffer(GL_FRAMEBUFFER,fbo);
                glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,route?fused:control);
                assert(glGetError()==GL_NO_ERROR);
                unsigned count;const uint32_t *current=dvbridge_packets(dvbridge_render_candidate(r),&count);
                assert(count<=3);
                if(route) {
                    assert(!memcmp(control,fused,frame_bytes));assert(count==packet_count);
                    assert(!memcmp(packets,current,count*128*sizeof(*packets)));
                } else {packet_count=count;memcpy(packets,current,count*128*sizeof(*packets));}
                glBindFramebuffer(GL_FRAMEBUFFER,0);assert(dvbridge_render_commit(r));
            }
        }
        memcpy(av_dovi_get_mapping(m)->curves,saved,sizeof(saved));
        frame.planes[1].shift_y=0;r->fragment_quad=quad;free(control);free(fused);
        puts("PASS exact MMR LUT carrier/packets, orders 1/2/3, coefficient changes, both phases/orientations");
    }
    if(quad) {
        AVDOVIRpuDataHeader saved_header=*av_dovi_get_header(m);
        AVDOVIDataMapping saved_mapping=*av_dovi_get_mapping(m);
        AVDOVIRpuDataHeader *header=av_dovi_get_header(m);
        header->disable_residual_flag=0;header->el_bit_depth=10;
        header->el_spatial_resampling_filter_flag=1;header->coef_log2_denom=23;
        AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);
        mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
        for(int c=0;c<3;c++)mapping->nlq[c]=(AVDOVINLQParams){.nlq_offset=512,
            .vdr_in_max=131072,.linear_deadzone_slope=8192,.linear_deadzone_threshold=4096};
        struct pl_frame enhancement=frame;
        enhancement.crop=(pl_rect2df){0,0,1920,1080};
        for(int plane=0;plane<2;plane++){
            int w=plane?960:1920,h=plane?540:1080,lanes=plane?2:1;
            uint16_t *samples=malloc((size_t)w*h*lanes*2);assert(samples);
            for(int i=0;i<w*h*lanes;i++)samples[i]=((i*29+i/w*107)%1024)<<6;
            enhancement.planes[plane].texture=pl_tex_create(g.gl->gpu,pl_tex_params(
                .w=w,.h=h,.format=frame.planes[plane].texture->params.format,
                .sampleable=true,.initial_data=samples));
            free(samples);assert(enhancement.planes[plane].texture);
        }
        frame.enhancement_layer=&enhancement;
        size_t n=(size_t)3840*2160*4;
        uint8_t *control=malloc(n),*fused=malloc(n);assert(control&&fused);
        for(int phase=0;phase<2;phase++)for(int flip=0;flip<2;flip++)for(int route=0;route<4;route++){
            frame.planes[1].shift_y=enhancement.planes[1].shift_y=phase?-.5f:0;
            r->fragment_quad=(route&1)?quad:false;table_layout(r,(route&2)!=0);dvbridge_renderer_reset(r);
            assert(dvbridge_render_master_reference_ipt(r,&frame,m,bytes,2,2,geo,target,flip,NULL)==CB1_MASTER_READY);
            glBindFramebuffer(GL_FRAMEBUFFER,fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,
                pl_opengl_unwrap(g.gl->gpu,target,NULL,NULL,NULL),0);
            glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,route?fused:control);
            assert(glGetError()==GL_NO_ERROR);
            if(route)assert(!memcmp(control,fused,n));
            glBindFramebuffer(GL_FRAMEBUFFER,0);assert(dvbridge_render_commit(r));
        }
        for(int p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&enhancement.planes[p].texture);
        frame.enhancement_layer=NULL;frame.planes[1].shift_y=0;r->fragment_quad=quad;
        *av_dovi_get_header(m)=saved_header;*av_dovi_get_mapping(m)=saved_mapping;
        free(control);free(fused);
        puts("PASS exact FEL IPT carrier with reference filters, both phases/orientations");
    }
    /* L5 must not hide overlays, including the odd pixel of a chroma pair. */
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=5,.l5={.top_offset=280,.bottom_offset=280}};
    pl_tex gui=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.sampleable=true,
        .renderable=true,.blit_dst=true,.format=pl_find_fmt(g.gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE)));
    assert(gui);
    pl_tex_clear(g.gl->gpu,gui,(float[4]){0,0,0,0});
    float tile[4*2*4];for(int i=0;i<8;i++)memcpy(tile+i*4,(float[4]){.5,.5,.5,1},4*sizeof(float));
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,gui,NULL,NULL,NULL));
    glTexSubImage2D(GL_TEXTURE_2D,0,100,2058,4,2,GL_RGBA,GL_FLOAT,tile);
    pl_tex lut=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
    pl_tex lut2=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
    struct dvbridge_native_overlay overlay={.texture=gui,.degamma=lut,.pq=lut2,.rect={100,100,104,102},.input_pq=true};
    uint16_t *stripe=malloc(3840*32*sizeof(uint16_t));assert(stripe);
    for(int i=0;i<3840*32;i++)stripe[i]=700<<6;
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,frame.planes[0].texture,NULL,NULL,NULL));
    glTexSubImage2D(GL_TEXTURE_2D,0,0,1400,3840,32,GL_RED,GL_UNSIGNED_SHORT,stripe);free(stripe);
    dvbridge_renderer_reset(r);
    dvbridge_renderer_set_overlay_visible(r,true);
    render_calls=0;
    assert(dvbridge_render_master_reference_ipt(r,&frame,m,bytes,2,NAN,geo,target,false,&overlay)==CB1_MASTER_READY);
    if(quad)assert(render_calls==1);
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,target,NULL,NULL,NULL),0);
    uint8_t band[8],blank[4];glReadPixels(100,100,2,1,GL_RGBA,GL_UNSIGNED_BYTE,band);
    glReadPixels(2000,100,1,1,GL_RGBA,GL_UNSIGNED_BYTE,blank);assert(glGetError()==GL_NO_ERROR);
    for(int x=0;x<2;x++)assert(band[4*x+1]*16+(band[4*x+2]&15)>100);
    if(blank[0]!=128 || blank[1]!=0 || blank[2]!=0)fprintf(stderr,"blank %u %u %u\n",blank[0],blank[1],blank[2]);
    assert(blank[0]==128 && blank[1]==0 && blank[2]==0);
    size_t frame_bytes=(size_t)3840*2160*4;
    uint8_t *upright=malloc(frame_bytes),*flipped=malloc(frame_bytes);assert(upright&&flipped);
    glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,upright);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    assert(dvbridge_render_commit(r));
    if(quad) {
        r->fragment_quad=false;dvbridge_renderer_reset(r);
        assert(dvbridge_render_master_reference_ipt(r,&frame,m,bytes,2,NAN,geo,target,false,&overlay)==CB1_MASTER_READY);
        glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,flipped);
        assert(glGetError()==GL_NO_ERROR);
        size_t differences=0;
        for(size_t i=0;i<frame_bytes;i++)if(upright[i]!=flipped[i]) {
            if(differences<4)fprintf(stderr,"overlay diff x=%zu y=%zu channel=%zu %u/%u\n",i/4%3840,i/4/3840,i%4,upright[i],flipped[i]);
            differences++;
        }
        fprintf(stderr,"overlay carrier differences: %zu\n",differences);
        assert(!differences);
        glBindFramebuffer(GL_FRAMEBUFFER,0);assert(dvbridge_render_commit(r));
        r->fragment_quad=quad;
    }
    assert(dvbridge_render_master_reference_ipt(r,&frame,m,bytes,2,NAN,geo,target,true,&overlay)==CB1_MASTER_READY);
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,flipped);assert(glGetError()==GL_NO_ERROR);
    for(int y=0;y<2160;y++)assert(!memcmp(upright+(size_t)y*3840*4,flipped+(size_t)(2159-y)*3840*4,3840*4));
    free(upright);free(flipped);glBindFramebuffer(GL_FRAMEBUFFER,0);
    pl_tex_destroy(g.gl->gpu,&gui);pl_tex_destroy(g.gl->gpu,&lut);pl_tex_destroy(g.gl->gpu,&lut2);
    glDeleteFramebuffers(1,&fbo);
    for(int i=0;i<2;i++)pl_tex_destroy(g.gl->gpu,&frame.planes[i].texture);
    scaled_ipt_witness(&g,r);
    dvbridge_renderer_destroy(r);
    puts("PASS full Master -> IPT -> Master render, exact original carrier restored");
    pl_tex_destroy(g.gl->gpu,&source);pl_tex_destroy(g.gl->gpu,&target);
    for(int i=0;i<2;i++)pl_tex_destroy(g.gl->gpu,&pq[i]);
    free(input);av_free(m);reference_gpu_destroy(&g);
}

