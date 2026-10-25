/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_hdr10plus_analysis.h"
#include "cb1_dv_hdr10plus.h"
#include <time.h>

static bool force_busy;
extern GLenum __real_glClientWaitSync(GLsync,GLbitfield,GLuint64);
GLenum __wrap_glClientWaitSync(GLsync fence,GLbitfield flags,GLuint64 timeout)
{
    return force_busy ? GL_TIMEOUT_EXPIRED : __real_glClientWaitSync(fence,flags,timeout);
}

static double pq(double nits)
{
    double x=pow(nits/10000.0,2610.0/16384.0);
    return pow((3424.0/4096.0+2413.0/128.0*x)/(1+2392.0/128.0*x),2523.0/32.0);
}

static struct cb1_hdr10plus_statistics result(struct cb1_hdr10plus_analysis *ctx,
                                             struct dvbridge_identity id)
{
    struct cb1_hdr10plus_statistics out={0};
    for(unsigned i=0;i<10000;i++){
        enum cb1_hdr10plus_analysis_status s=cb1_hdr10plus_analysis_poll(ctx,id,&out);
        if(s!=CB1_HDR10PLUS_ANALYSIS_PENDING){assert(s==CB1_HDR10PLUS_ANALYSIS_READY);return out;}
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"HDR10+ analysis timeout");return out;
}

static double nits(double q)
{
    double x=pow(q,32.0/2523);
    return 10000*pow(fmax(0,x-3424.0/4096)/(2413.0/128-2392.0/128*x),16384.0/2610);
}

static void reconstructed(struct reference_gpu *gpu,struct cb1_hdr10plus_analysis *analysis)
{
    enum {W=32,H=32};
    float input[W*H*4],residual[W*H*4],before[W*H*4],after[W*H*4];
    for(unsigned i=0;i<W*H;i++)for(unsigned c=0;c<4;c++){
        input[4*i+c]=c==3?1:.4f+.01f*c;
        residual[4*i+c]=c==3?1:.55f;
    }
    pl_tex bl=reference_texture(gpu->gl->gpu,W,H,input);
    pl_tex el=reference_texture(gpu->gl->gpu,W,H,residual);
    struct pl_frame frame=reference_frame(bl,W,H),enhancement=reference_frame(el,W,H);
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu->gl->gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,3079,1500}};
    struct dvbridge_geometry geometry={W,H,0,0,W,H};
    double plain_average=0;
    for(unsigned mode=0;mode<3;mode++){
        av_dovi_get_header(m)->disable_residual_flag=mode!=1;
        frame.enhancement_layer=mode==1?&enhancement:NULL;
        if(mode==1){
            AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);
            mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
            for(unsigned c=0;c<3;c++)mapping->nlq[c]=(AVDOVINLQParams){
                .nlq_offset=512,.linear_deadzone_slope=4096,.vdr_in_max=1023*4096};
        }
        if(mode==2){
            AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
            h->rpu_type=2;h->rpu_format=18;h->vdr_rpu_profile=0;
            h->bl_video_full_range_flag=1;h->vdr_bit_depth=12;
            AVDOVIColorMetadata *color=av_dovi_get_color(m);
            color->signal_color_space=2;color->signal_bit_depth=12;color->signal_full_range_flag=1;
            color->ycc_to_rgb_offset[1]=color->ycc_to_rgb_offset[2]=(AVRational){1,2};
            const int matrix[]={8192,799,1681,8192,-933,1091,8192,267,-5545};
            for(unsigned i=0;i<9;i++){
                color->ycc_to_rgb_matrix[i]=(AVRational){matrix[i],8192};
                color->rgb_to_lms_matrix[i]=(AVRational){i%4==0?17081:-349,16384};
            }
        }
        void *saved=av_memdup(m,bytes);assert(saved);
        assert(dvbridge_render_rgb(r,&frame,m,bytes,mode,mode,geometry));
        pl_tex rgb=dvbridge_render_texture(r);assert(rgb);
        reference_read(gpu->gl->gpu,rgb,0,0,W,H,before);
        struct dvbridge_identity id={13,mode+1,1};
        assert(cb1_hdr10plus_analysis_submit(analysis,rgb,(pl_rect2d){0,0,W,H},id)==CB1_HDR10PLUS_ANALYSIS_PENDING);
        struct cb1_hdr10plus_statistics stats=result(analysis,id);
        double sum=0;for(unsigned i=0;i<W*H;i++)sum+=nits(fmax(before[4*i],fmax(before[4*i+1],before[4*i+2])));
        assert(stats.count==W*H && fabs(stats.average_maxrgb-sum/(W*H))<.1);
        if(!mode)plain_average=stats.average_maxrgb;
        if(mode==1)assert(fabs(stats.average_maxrgb-plain_average)>1);
        AVDynamicHDRPlus plus;struct cb1_dv_hdr10plus_report report;uint8_t packet[31];
        assert(cb1_dv_hdr10plus_metadata(&plus,&report,m,bytes,&stats));
        assert(cb1_hdr10plus_vsif(packet,&plus,false,true)==CB1_HDR10PLUS_OK);
        reference_read(gpu->gl->gpu,rgb,0,0,W,H,after);
        assert(!memcmp(before,after,sizeof(before)) && !memcmp(saved,m,bytes));av_free(saved);
    }
    dvbridge_renderer_destroy(r);av_free(m);
    pl_tex_destroy(gpu->gl->gpu,&bl);pl_tex_destroy(gpu->gl->gpu,&el);
}

int main(void)
{
    struct reference_gpu gpu=reference_gpu_create();
    struct cb1_hdr10plus_analysis *ctx=cb1_hdr10plus_analysis_create(gpu.log,gpu.gl->gpu);
    assert(ctx);
    {
        enum {W=256,H=128,N=W*H};
        float *pixels=calloc(N*4,sizeof(float));assert(pixels);
        for(unsigned i=0;i<N;i++){
            pixels[4*i]=(float)pq(i<16384?0:i<24576?160:4000);
            pixels[4*i+3]=1;
        }
        pl_tex t=reference_texture(gpu.gl->gpu,W,H,pixels);free(pixels);
        struct dvbridge_identity id={99,1,1};
        assert(cb1_hdr10plus_analysis_submit(ctx,t,(pl_rect2d){0,0,W,H},id)==CB1_HDR10PLUS_ANALYSIS_PENDING);
        struct cb1_hdr10plus_statistics s=result(ctx,id);
        assert(s.count==N && s.histogram[0]==16384 && s.histogram[10]==8192 && s.histogram[250]==8192);
        assert(fabs(s.average_maxrgb-1040)<.1);
        pl_tex_destroy(gpu.gl->gpu,&t);
    }
    const struct dvbridge_identity id={3,7,11};
    pl_tex missing_channels=pl_tex_create(gpu.gl->gpu,pl_tex_params(
        .w=2,.h=2,.sampleable=true,
        .format=pl_find_fmt(gpu.gl->gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE)));
    assert(missing_channels);
    assert(cb1_hdr10plus_analysis_submit(ctx,missing_channels,(pl_rect2d){0,0,2,2},id)==
           CB1_HDR10PLUS_ANALYSIS_INVALID);
    pl_tex_destroy(gpu.gl->gpu,&missing_channels);
    float pixels[66*34*4]={0};
    /* Bright border is outside the selected film. Interior is equally split
     * between black, red at 160 nits, green at 800 nits and blue at 4000 nits. */
    for(unsigned y=0;y<34;y++)for(unsigned x=0;x<66;x++){
        float *p=pixels+4*(y*66+x);
        p[0]=p[1]=p[2]=1;
        if(x>0 && x<65 && y>0 && y<33){
            p[0]=p[1]=p[2]=0;unsigned q=(x-1)/16;
            if(q)p[q-1]=(float)pq(q==1?160:q==2?800:4000);
        }
    }
    pl_tex t=reference_texture(gpu.gl->gpu,66,34,pixels);
    pl_rect2d area={1,1,65,33};
    assert(cb1_hdr10plus_analysis_submit(ctx,t,area,id)==CB1_HDR10PLUS_ANALYSIS_PENDING);
    struct cb1_hdr10plus_statistics untouched={.count=99};
    assert(cb1_hdr10plus_analysis_poll(ctx,(struct dvbridge_identity){3,8,11},&untouched)==CB1_HDR10PLUS_ANALYSIS_INVALID);
    assert(untouched.count==99);
    assert(cb1_hdr10plus_analysis_submit(ctx,t,area,id)==CB1_HDR10PLUS_ANALYSIS_PENDING);
    struct cb1_hdr10plus_statistics out=result(ctx,id);
    fprintf(stderr,"linear statistics: count=%llu avg=%.6f max=%.6f %.6f %.6f\n",
        (unsigned long long)out.count,out.average_maxrgb,out.maxscl[0],out.maxscl[1],out.maxscl[2]);
    for(unsigned i=0;i<256;i++)if(out.histogram[i])fprintf(stderr,"bin %u: %u\n",i,out.histogram[i]);
    assert(out.count==2048);
    for(unsigned i=0;i<256;i++)assert(out.histogram[i]==((i==0||i==10||i==50||i==250)?512u:0u));
    assert(fabs(out.average_maxrgb-1240)<.1);
    assert(fabs(out.maxscl[0]-160)<.02 && fabs(out.maxscl[1]-800)<.05 && fabs(out.maxscl[2]-4000)<.3);
    AVDynamicHDRPlus m={0};uint8_t wire[31];
    assert(cb1_hdr10plus_describe(&m,&out,992));
    assert(m.application_version==1 && m.num_windows==1 && m.params[0].tone_mapping_flag==0);
    assert(m.params[0].distribution_maxrgb[1].percentile.num==0);
    assert(m.params[0].distribution_maxrgb[2].percentile.num==255);
    assert(cb1_hdr10plus_vsif(wire,&m,false,true)==CB1_HDR10PLUS_OK);
    assert(wire[7]==126 && wire[8]==78);
    assert(wire[9]==0 && wire[12]==0 && wire[13]==10 && wire[14]==50 && wire[17]==250);
    struct cb1_hdr10plus_statistics impossible=out;
    impossible.average_maxrgb=5000;
    AVDynamicHDRPlus saved=m;
    assert(!cb1_hdr10plus_describe(&m,&impossible,992));
    assert(!memcmp(&m,&saved,sizeof(m)));
    assert(!cb1_hdr10plus_describe(&m,&out,1000)); /* Curve target must match wire units. */
    out.histogram[0]++;assert(!cb1_hdr10plus_describe(&m,&out,992));
    cb1_hdr10plus_analysis_reset(ctx);
    assert(cb1_hdr10plus_analysis_poll(ctx,id,&untouched)==CB1_HDR10PLUS_ANALYSIS_INVALID);
    assert(cb1_hdr10plus_analysis_submit(ctx,t,(pl_rect2d){0,0,67,34},id)==CB1_HDR10PLUS_ANALYSIS_INVALID);
    assert(cb1_hdr10plus_analysis_submit(ctx,t,area,id)==CB1_HDR10PLUS_ANALYSIS_PENDING);
    cb1_hdr10plus_analysis_reset(ctx);
    /* A cancelled GPU job may still own the buffer. PENDING must mean this
     * identity was admitted, never that an old job is merely being drained. */
    const struct dvbridge_identity next={4,1,1};
    force_busy=true;
    assert(cb1_hdr10plus_analysis_submit(ctx,t,area,next)==CB1_HDR10PLUS_ANALYSIS_BUSY);
    force_busy=false;
    enum cb1_hdr10plus_analysis_status admitted;
    do {
        admitted=cb1_hdr10plus_analysis_submit(ctx,t,area,next);
        if (admitted==CB1_HDR10PLUS_ANALYSIS_BUSY) nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    } while (admitted==CB1_HDR10PLUS_ANALYSIS_BUSY);
    assert(admitted==CB1_HDR10PLUS_ANALYSIS_PENDING);
    out=result(ctx,next);assert(out.count==2048);
    float after[66*34*4];reference_read(gpu.gl->gpu,t,0,0,66,34,after);
    assert(!memcmp(after,pixels,sizeof(after)));
    pl_tex_destroy(gpu.gl->gpu,&t);
    reconstructed(&gpu,ctx);
    cb1_hdr10plus_analysis_destroy(&ctx);reference_gpu_destroy(&gpu);
    puts("HDR10+ linear statistics, crop, identity and HDMI quantization passed");
}
