/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include <time.h>

/* Instrument the real public library submission only in this test binary.
 * Count actual dispatch callbacks and CPU elapsed time; no wait or readback. */
static unsigned measured_passes;
static double measured_ms;
static void count_pass(void *priv,const struct pl_render_info *info)
{ (void)priv;assert(info->pass);++measured_passes; }
extern bool __real_pl_render_image(pl_renderer,const struct pl_frame *,const struct pl_frame *,const struct pl_render_params *);
bool __wrap_pl_render_image(pl_renderer renderer,const struct pl_frame *source,const struct pl_frame *target,const struct pl_render_params *params)
{
    struct pl_render_params copy=*params;copy.info_callback=count_pass;copy.info_priv=NULL;
    struct timespec start,end;clock_gettime(CLOCK_MONOTONIC,&start);measured_passes=0;
    bool ok=__real_pl_render_image(renderer,source,target,&copy);
    clock_gettime(CLOCK_MONOTONIC,&end);measured_ms=1000.0*(end.tv_sec-start.tv_sec)+(end.tv_nsec-start.tv_nsec)/1e6;
    return ok;
}

static int compare_time(const void *a,const void *b)
{ double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y); }

/* Literal neutral pixels 0,4,7,3 from the pre-runtime independent C images. */
static const double natural[12]={0,0,0,.5080784424997636,.5080766760667212,.5080938965490098,
    .7583570230577172,.7583551037201055,.7583738147382495,.299699108978648,.29969772127860467,.29971124967457685};
static const double intense[12]={0,0,0,.511525466126865,.511523695594911,.511540956035129,
    .763856473065509,.763854553180373,.763873269534413,.299699108978648,.29969772127860467,.29971124967457685};
static const double high_key[12]={0,0,0,.50807844254673,.508076676125817,.508093896489926,
    .755140656034355,.7551387370514,.755157444613101,.299699108978648,.29969772127860467,.29971124967457685};
static const double p3[12]={0,0,0,.508065270019041,.508079095712878,.508106344257989,
    .758343843222351,.758357484386267,.758386239163689,.299685411929736,.299699627092763,.299723192843273};

static void image(pl_gpu gpu,struct dvbridge_renderer *r,const double expected[12],float pixels[16])
{
    reference_read(gpu,dvbridge_render_texture(r),0,0,2,2,pixels);
    for(int p=0;p<4;p++)for(int c=0;c<3;c++) {
        assert(fabs(pixels[4*p+c]-expected[3*p+c])<=1.0/65535);
        if(!p)assert(pixels[c]==0);
    }
}

int main(void)
{
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    float source[]={0,0,0,1,.508078421517399,.508078421517399,.508078421517399,1,
        .751827096247041,.751827096247041,.751827096247041,1,.29969909242098597,.29969909242098597,.29969909242098597,1};
    pl_tex input=reference_texture(gpu,2,2,source),a=reference_texture(gpu,3840,2160,NULL),b=reference_texture(gpu,3840,2160,NULL);
    struct pl_frame frame=reference_frame(input,2,2);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0),*l6=av_dovi_get_ext(m,1);
    *l1=(AVDOVIDmData){.level=1,.l1={.min_pq=0,.avg_pq=1667,.max_pq=3079}};
    *l6=(AVDOVIDmData){.level=6,.l6={.max_luminance=1000}};
    void *original=av_memdup(m,bytes);assert(original);
    struct dvbridge_policy policy=reference_policy();policy.mode=DVBRIDGE_MODE_ENHANCED_HDR10;policy.tv.gamut=DVBRIDGE_GAMUT_BT2020;
    struct dvbridge_identity id={1,7,1};struct dvbridge_geometry geometry={2,2,0,0,2,2};
    struct dvbridge_hdr10_policy_output saved,snapshot;
    float before[16],after[16],final[16];
#define PREPARE() dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&frame,m,bytes,0,0,geometry)
#define REVISION() (++id.revision,++policy.revision)
    assert(PREPARE());image(gpu,r,natural,before);
    assert(dvbridge_render_hdr10_policy_resolve(r,a,false,true,10));
    assert(dvbridge_render_policy_commit(r,&id,a));
    assert(dvbridge_render_policy_committed(r,&saved));reference_read(gpu,a,0,0,2,2,final);
    /* An unchanged pause re-presents the retained caller surface, without prepare. */
    for(int i=0;i<8;i++) {reference_read(gpu,a,0,0,2,2,after);assert(!memcmp(final,after,sizeof(final)));
        assert(!dvbridge_render_policy_output(r) && dvbridge_render_policy_committed(r,&snapshot));}
    /* Equal identity is not proof that the exposed image is original. */
    assert(PREPARE());pl_tex borrowed=dvbridge_render_texture(r);
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(gpu,borrowed,NULL,NULL,NULL));
    glTexSubImage2D(GL_TEXTURE_2D,0,0,0,2,2,GL_RGBA,GL_FLOAT,(float[16]){.9,.1,.7,1,.9,.1,.7,1,.9,.1,.7,1,.9,.1,.7,1});
    assert(glGetError()==GL_NO_ERROR);glBindTexture(GL_TEXTURE_2D,0);
    for(int i=0;i<3;i++){assert(PREPARE());image(gpu,r,natural,after);assert(!memcmp(before,after,sizeof(before)));}
    REVISION();policy.enhancement=DVBRIDGE_ENHANCEMENT_INTENSE;assert(PREPARE());image(gpu,r,intense,after);
    assert(dvbridge_render_policy_output(r)->hdr10.max_luminance==saved.hdr10.max_luminance);
    assert(dvbridge_render_policy_output(r)->nominal_target.primaries==saved.nominal_target.primaries);
    assert(dvbridge_render_hdr10_policy_resolve(r,b,false,true,10));
    struct dvbridge_identity stale=id;--stale.revision;assert(!dvbridge_render_policy_commit(r,&stale,b));
    assert(dvbridge_render_policy_committed(r,&snapshot) && snapshot.final_target==a);
    dvbridge_render_policy_cancel(r);assert(!dvbridge_render_texture(r));
    REVISION();policy.enhancement=DVBRIDGE_ENHANCEMENT_NATURAL;l1->l1.avg_pq=2771;
    assert(PREPARE());image(gpu,r,high_key,after);assert(after[8]<before[8]);
    REVISION();l1->l1.avg_pq=1667;policy.tv.gamut=DVBRIDGE_GAMUT_P3_D65;
    assert(PREPARE());image(gpu,r,p3,after);
    REVISION();policy.tv.peak_nits=1000.25;assert(PREPARE());
    assert(dvbridge_render_policy_output(r)->hdr10.max_luminance==1001);
    assert(dvbridge_render_hdr10_policy_resolve(r,b,false,false,12));
    ++id.picture;assert(PREPARE());assert(!dvbridge_render_policy_commit(r,&stale,b));
    assert(!dvbridge_render_hdr10_policy_resolve(r,b,false,false,8));
    assert(!dvbridge_render_policy_output(r));assert(dvbridge_render_policy_committed(r,&snapshot) && snapshot.final_target==a);
    policy.tv.peak_nits=1500;policy.tv.gamut=DVBRIDGE_GAMUT_BT2020;REVISION();
    m->num_ext_blocks=1;assert(PREPARE());image(gpu,r,natural,after); /* Optional mastering absent. */
    m->num_ext_blocks=2;l6->level=8;assert(PREPARE());image(gpu,r,natural,after); /* Zero creative trim. */
    l6->level=254;assert(PREPARE());image(gpu,r,natural,after); /* CM4 provenance, no creative stack. */
    memcpy(m,original,bytes);l1->l1.max_pq=0;assert(!PREPARE());
    assert(dvbridge_render_policy_committed(r,&snapshot) && snapshot.final_target==a);memcpy(m,original,bytes);
    policy.mode=DVBRIDGE_MODE_ENHANCED_DV;assert(!PREPARE());policy.mode=DVBRIDGE_MODE_ENHANCED_HDR10;
    dvbridge_renderer_reset(r);++id.stream;id.picture=0;
    assert(!dvbridge_render_policy_committed(r,&snapshot));assert(PREPARE());image(gpu,r,natural,after);
    assert(dvbridge_render_hdr10_policy_resolve(r,b,false,true,10));assert(dvbridge_render_policy_commit(r,&id,b));
    assert(!dvbridge_render_policy_commit(r,&id,b));
    unsigned reference_passes=0;
    for(int mode=0;mode<3;mode++) {
        policy.mode=mode ? DVBRIDGE_MODE_ENHANCED_HDR10 : DVBRIDGE_MODE_HDR10_EXPERT;
        policy.enhancement=mode==2 ? DVBRIDGE_ENHANCEMENT_INTENSE : DVBRIDGE_ENHANCEMENT_NATURAL;REVISION();
        assert(PREPARE()); /* Warm shader/LUT cache before the timed samples. */
        double elapsed[7];
        for(int n=0;n<7;n++){assert(PREPARE());elapsed[n]=measured_ms;
            if(!mode)reference_passes=measured_passes;else assert(measured_passes==reference_passes);}
        qsort(elapsed,7,sizeof(*elapsed),compare_time);
        fprintf(stderr,"OFFLINE_SUBMISSION mode=%d actual_passes=%u CPU_median_ms=%.6f samples=7 no_explicit_wait_or_readback\n",mode,measured_passes,elapsed[3]);
    }
    assert(!memcmp(m,original,bytes));reference_read(gpu,input,0,0,2,2,after);assert(!memcmp(source,after,sizeof(source)));
    dvbridge_renderer_destroy(r);
    assert(glIsTexture(pl_opengl_unwrap(gpu,a,NULL,NULL,NULL)) && glIsTexture(pl_opengl_unwrap(gpu,b,NULL,NULL,NULL)));
    pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&a);pl_tex_destroy(gpu,&b);av_free(original);av_free(m);reference_gpu_destroy(&g);
    puts("PASS Enhanced frozen images, pause/original-source, scene/preset/TV, cancellation, seek and borrowed final lifetimes");
}
