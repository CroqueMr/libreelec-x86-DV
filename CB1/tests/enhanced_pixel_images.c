/* SPDX-License-Identifier: GPL-3.0-only */
#include "reference_test.h"
#include "cb1_processing.h"
static bool reject_pq_lookup;
static pl_tex test_pq_encoder(struct cb1_processing *state,pl_gpu gpu)
{return reject_pq_lookup?NULL:cb1_processing_pq_encoder(state,gpu);}
static bool reject_wrap;
static pl_tex test_wrap(pl_gpu gpu,const struct pl_opengl_wrap_params *params)
{return reject_wrap?NULL:pl_opengl_wrap(gpu,params);}
#define pl_opengl_wrap test_wrap
#define cb1_processing_pq_encoder test_pq_encoder
#include "../src/dvbridge_render.c"
#undef pl_opengl_wrap
#undef cb1_processing_pq_encoder
#include <time.h>
int main(void)
{
#ifndef CB1_DVE_GPU
    assert(!"Dense Enhanced GPU processing required");
#else
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    reject_wrap=true;assert(!dve_allocate(r,3,2,false,false));
    assert(!r->enhanced_texture && "Failed texture wrapping must release native storage");reject_wrap=false;
    GLint limits[3];GLint64 storage;
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT,0,&limits[0]);
    glGetIntegerv(GL_MAX_COMPUTE_IMAGE_UNIFORMS,&limits[1]);
    glGetIntegerv(GL_MAX_COMPUTE_UNIFORM_COMPONENTS,&limits[2]);
    glGetInteger64v(GL_MAX_SHADER_STORAGE_BLOCK_SIZE,&storage);
    fprintf(stderr,"dense caps groups=%d images=%d uniforms=%d storage=%lld format=%p base=%d error=%x\n",
        limits[0],limits[1],limits[2],(long long)storage,(void *)pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,32,32,
        PL_FMT_CAP_STORABLE|PL_FMT_CAP_SAMPLEABLE),dv_gpu_requirements(r->gpu),glGetError());
    struct cb1_dv_enhanced_source source={.master=1000,.l1_present=true,
        .analysis={0,3080,1463},.family=8,.count=1,.weights={1}};
    source.anchors[0]=(struct dvbridge_cm4_anchor){.present=true,
        .target={.max_pq=2851,.primaries=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020),.transfer=PL_COLOR_TRC_PQ},
        .controls={.primary={2048,2048,2048,2048,2048,2048},.present_fields=1}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct cb1_dv_enhanced_plan plan;assert(cb1_dv_enhanced_build(&plan,&source,&policy)==CB1_DVE_READY);
    const double pairs[][2]={{500,600},{500,2300},{1000,600},{1000,2300},{4000,1000},{4000,10000}};
    for(unsigned transfer=0;transfer<4;transfer++)
    for(unsigned pair=0;pair<6;pair++)for(unsigned control=0;control<3;control++)
    for(unsigned preset=1;preset<2;preset++)for(unsigned guard=0;guard<3;guard++){
        reject_pq_lookup=transfer&1;r->enhanced_linear=transfer>=2;
        source.master=pairs[pair][0];policy.tv.peak_nits=pairs[pair][1];
        struct dvbridge_cm4_controls *c=&source.anchors[0].controls;
        *c=(struct dvbridge_cm4_controls){.primary={2048,2048,2048,2048,2048,2048},.present_fields=31,
            .mid_contrast=2048,.clip_trim=2048,.saturation={128,128,128,128,128,128},.hue={128,128,128,128,128,128}};
        if(control==1){c->primary[2]=2304;c->mid_contrast=2400;}
        if(control==2){c->primary[3]=3000;c->primary[4]=2700;c->saturation[0]=220;c->hue[4]=200;}
        source.anchors[0].target.primaries=*pl_raw_primaries_get(control==2?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020);
        policy.tv.gamut=control==2?DVBRIDGE_GAMUT_P3_D65:DVBRIDGE_GAMUT_BT2020;
        
        r->enhanced_authored_curve=true;
        if(cb1_dv_enhanced_build(&plan,&source,&policy)==CB1_DVE_IDENTITY)continue;
        assert(cb1_dv_enhanced_build(&plan,&source,&policy)==CB1_DVE_READY);
        double m=source.master;
        const double input[6][3]={{.5*m,.5*m,.5*m},{m,m,m},{.7*m,.12*m,.005*m},{0,0,0},{10,10,10},{.4*m,.2*m,.1*m}};
        float pixels[24];
        for(unsigned i=0;i<6;i++)for(unsigned j=0;j<4;j++)pixels[4*i+j]=j==3?1:
            r->enhanced_linear?input[i][j]/10000:dv_ideal_pq(input[i][j]);
        if(guard)pixels[4]=pixels[5]=pixels[6]=r->enhanced_linear?(m+1)/10000:dv_ideal_pq(m+1);
        pl_tex tex=reference_texture(g.gl->gpu,3,2,pixels);
        assert(dve_allocate(r,3,2,false,false));
        r->dv.output.value.identity=(struct dvbridge_identity){3,7,1};
        unsigned area[4]={0,0,guard==2?1:0,0};
        assert(dve_run(r,&plan,tex,area));
        glFinish();uint32_t record[12];memcpy(record,r->dv.mapped,sizeof(record));
        assert(record[10]==1 && record[11]==(guard==1));
        assert(record[3]==(guard==2?3:6));
        /* A guarded scratch image is discarded as a whole by the public
         * policy path; enhanced_pixel_lifecycle verifies its native output. */
        if(guard==1){pl_tex_destroy(g.gl->gpu,&tex);dv_release(r);continue;}
        float output[24];reference_read(g.gl->gpu,r->enhanced_rgb,0,0,3,2,output);
        double peak=0;
        for(unsigned i=0;i<6;i++){
            double expected[3];assert(cb1_dv_enhanced_pixel(&plan,input[i],expected));
            for(unsigned j=0;j<3;j++){
                if((guard==2 && i<3) || i==3 || i==4){
                    if(r->enhanced_linear)assert(fabs(output[4*i+j]-dv_ideal_pq(pixels[4*i+j]*10000))*4096<=1);
                    else assert(output[4*i+j]==pixels[4*i+j]);
                }
                else assert(fabs(output[4*i+j]-dv_ideal_pq(expected[j]))*4096<=1);
            }
            if(!(guard==2 && i<3)){
                pl_matrix3x3 lms=pl_ipt_rgb2lms(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
                for(unsigned j=0;j<3;j++){
                    const double *rgb=guard==1?input[i]:expected;
                    double value=lms.m[j][0]*rgb[0]+lms.m[j][1]*rgb[1]+lms.m[j][2]*rgb[2];
                    if(guard==1 && i==1)value=m+1;
                    peak=fmax(peak,dv_ideal_pq(value));
                }
            }
        }
        float maximum;memcpy(&maximum,&record[2],4);
        assert(fabs(maximum-peak)*4096<=1);
        pl_tex_destroy(g.gl->gpu,&tex);dv_release(r);
    }
    reject_pq_lookup=false;r->enhanced_linear=false;r->enhanced_authored_curve=false;
    source.master=1000;policy.tv.peak_nits=2300;
    assert(cb1_dv_enhanced_build(&plan,&source,&policy)==CB1_DVE_READY);
    /* Exercise both tile boundaries and partial tiles with varying colours.
     * Compare dense statistics independently of the GPU reduction order. */
    enum{W=131,H=17,N=W*H};float input[N*4],actual[N*4];
    double minimum=1,maximum=0,sum=0;
    pl_matrix3x3 matrix=pl_ipt_rgb2lms(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
    for(unsigned i=0;i<N;i++)for(unsigned j=0;j<4;j++)
        input[4*i+j]=j==3?1:dv_ideal_pq(((i*(j*19+13)+j*71)%997)+.01);
    pl_tex varied=reference_texture(g.gl->gpu,W,H,input);
    assert(dve_allocate(r,W,H,false,false));assert(dve_run(r,&plan,varied,(unsigned[4]){0}));glFinish();
    assert(r->dv.mapped[3]==N && r->dv.mapped[10]==1 && !r->dv.mapped[11]);
    reference_read(g.gl->gpu,r->enhanced_rgb,0,0,W,H,actual);
    for(unsigned i=0;i<N;i++){
        double rgb[3],expected[3];
        for(unsigned j=0;j<3;j++)rgb[j]=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,input[4*i+j]);
        assert(cb1_dv_enhanced_pixel(&plan,rgb,expected));double cone=0;
        for(unsigned j=0;j<3;j++){
            assert(fabs(actual[4*i+j]-dv_ideal_pq(expected[j]))*4096<=1);
            cone=fmax(cone,matrix.m[j][0]*expected[0]+matrix.m[j][1]*expected[1]+matrix.m[j][2]*expected[2]);
        }
        double q=dv_ideal_pq(cone);minimum=fmin(minimum,q);maximum=fmax(maximum,q);sum+=q;
    }
    float statistics[3];memcpy(statistics,r->dv.mapped,sizeof(statistics));
    assert(fabs(statistics[0]-minimum)*4096<=1 && fabs(statistics[2]-maximum)*4096<=1);
    assert(fabs(statistics[1]/N-sum/N)*4096<=1);
    /* Both guard bits must survive the final partial tile and all reductions. */
    input[4*(N-1)]=input[4*(N-1)+1]=input[4*(N-1)+2]=dv_ideal_pq(1001);
    pl_tex_destroy(r->gpu,&varied);varied=reference_texture(g.gl->gpu,W,H,input);
    assert(dve_run(r,&plan,varied,(unsigned[4]){0}));glFinish();
    assert(r->dv.mapped[3]==N && r->dv.mapped[10]==1 && r->dv.mapped[11]==1);
    input[4*(N-1)]=NAN;
    pl_tex_destroy(r->gpu,&varied);varied=reference_texture(g.gl->gpu,W,H,input);
    assert(dve_run(r,&plan,varied,(unsigned[4]){0}));glFinish();
    assert(r->dv.mapped[3]==N && !r->dv.mapped[10]);
    pl_tex_destroy(r->gpu,&varied);dv_release(r);
    assert(ensure_rgb(r)); /* The full-raster fixture supplies its own input pixels. */
    GLuint fill;glGenFramebuffers(1,&fill);glBindFramebuffer(GL_FRAMEBUFFER,fill);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(r->gpu,r->rgb,NULL,NULL,NULL),0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
    glClearColor(.5,.5,.5,1);glClear(GL_COLOR_BUFFER_BIT);
    glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fill);
    assert(dve_allocate(r,3840,2160,false,false) && dve_run(r,&plan,r->rgb,(unsigned[4]){0}));
    glFinish();assert(r->dv.mapped[3]==8294400 && r->dv.mapped[10]==1);
    dv_release(r);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);
    puts("PASS GPU expansion, dense sparse peaks, global identity guard and L5 exclusion");
#endif
}
