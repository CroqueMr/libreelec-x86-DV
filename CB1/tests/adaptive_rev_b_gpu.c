/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Offline A/B substitution; no runtime renderer call site is changed. */
#include "reference_test.h"
#include "cb1_dv_adaptive_rev_b.h"
#include <GLES2/gl2ext.h>
#include <libavformat/avformat.h>
#define PL_LIBAV_IMPLEMENTATION 1
#include <libplacebo/utils/libav.h>
#include <time.h>

static bool use_rev_b;
static enum cb1_dv_enhanced_status selected_plan(struct cb1_dv_enhanced_plan *p,
    const struct cb1_dv_enhanced_source *s,const struct dvbridge_policy *policy)
{
    return use_rev_b?cb1_dv_enhanced_build_rev_b(p,s,policy):cb1_dv_enhanced_build(p,s,policy);
}
#define cb1_dv_enhanced_build selected_plan
#include "../src/dvbridge_render.c"
#undef cb1_dv_enhanced_build

static double now(void)
{struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static uint16_t wire(double n){return lround(4095*dv_ideal_pq(n));}
static struct dvbridge_policy policy(void)
{
    return (struct dvbridge_policy){.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,
        .tv={2500,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
}
static struct cb1_dv_enhanced_source guidance(bool colors)
{
    struct cb1_dv_enhanced_source s={.master=1000,.l1_present=true,
        .analysis={0,wire(800),wire(30)},.family=8,.count=1,.weights={1}};
    s.anchors[0]=(struct dvbridge_cm4_anchor){.present=true,
        .target={.max_pq=wire(600),.primaries=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020),
            .transfer=PL_COLOR_TRC_PQ},.controls={.primary={2048,2048,2048,2300,2200,2048},
            .present_fields=DVBRIDGE_CM4_PRIMARY|(colors?DVBRIDGE_CM4_HUE|DVBRIDGE_CM4_SATURATION:0),
            .saturation={220,128,128,128,128,128},.hue={128,128,128,128,200,128}}};
    return s;
}
static enum dvbridge_dv_policy_status finish(struct dvbridge_renderer *r)
{
    for(unsigned i=0;i<10000;i++){
        enum dvbridge_dv_policy_status s=dvbridge_render_dv_policy_poll(r);
        if(s!=DVBRIDGE_DV_PENDING && s!=DVBRIDGE_DV_BUSY)return s;
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"Completion timeout");return DVBRIDGE_DV_FAILED;
}

static void kernel(struct reference_gpu *g,bool bench)
{
    unsigned w=bench?3840:256,h=bench?2160:16,n=w*h;
    float *input=malloc((size_t)n*4*sizeof(float)),*output=bench?NULL:malloc((size_t)n*4*sizeof(float)),
          *baseline=bench?NULL:malloc((size_t)n*4*sizeof(float));
    assert(input && (bench || (output && baseline)));
    for(unsigned i=0;i<n;i++){
        unsigned col=i%256;double v=col<16?10.0*col/15:800.0*(col-16)/239;
        input[4*i]=v/10000;input[4*i+1]=((i/w)&1?v*.4:v)/10000;
        input[4*i+2]=((i/w)&1?v*.05:v)/10000;input[4*i+3]=1;
    }
    pl_tex texture=reference_texture(g->gl->gpu,w,h,input);
    struct dvbridge_renderer *r=dvbridge_renderer_create(g->gl->gpu);assert(r);
    struct dvbridge_policy p=policy();
    struct cb1_dv_enhanced_plan plans[2];
    struct cb1_dv_enhanced_source s=guidance(true);
    /* Match only this arithmetic PQ proxy; this is not Dolby shot analysis. */
    pl_matrix3x3 source_lms=pl_ipt_rgb2lms(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
    double source_mean=0;
    for(unsigned row=0;row<2;row++)for(unsigned col=0;col<256;col++){
        const float *v=input+4*(row*w+col);double peak=0;
        for(unsigned c=0;c<3;c++)peak=fmax(peak,10000*(source_lms.m[c][0]*v[0]+source_lms.m[c][1]*v[1]+source_lms.m[c][2]*v[2]));
        source_mean+=dv_ideal_pq(peak)/512;
    }
    s.analysis[2]=lround(source_mean*4095);
    assert(cb1_dv_enhanced_build(&plans[0],&s,&p)==CB1_DVE_READY);
    assert(cb1_dv_enhanced_build_rev_b(&plans[1],&s,&p)==CB1_DVE_READY);
    const char *ext=(const char*)glGetString(GL_EXTENSIONS);
    bool timer=ext && strstr(ext,"GL_EXT_disjoint_timer_query");
    PFNGLGENQUERIESEXTPROC gen=(void*)eglGetProcAddress("glGenQueriesEXT");
    PFNGLBEGINQUERYEXTPROC begin=(void*)eglGetProcAddress("glBeginQueryEXT");
    PFNGLENDQUERYEXTPROC end=(void*)eglGetProcAddress("glEndQueryEXT");
    PFNGLGETQUERYOBJECTUI64VEXTPROC result=(void*)eglGetProcAddress("glGetQueryObjectui64vEXT");
    PFNGLDELETEQUERIESEXTPROC destroy=(void*)eglGetProcAddress("glDeleteQueriesEXT");
    timer=timer && gen && begin && end && result && destroy;
    for(unsigned analytic=0;analytic<2;analytic++){
        r->enhanced_linear=r->enhanced_authored=r->enhanced_authored_curve=true;
        r->reuse_authored_storage=false;
        assert(dve_allocate(r,w,h,false,analytic));
        if(bench)assert(r->enhanced_prepack && !r->enhanced_skip_aux &&
            texture->params.format->component_depth[0]==32 &&
            r->enhanced_rgb->params.format->component_depth[0]==32);
        r->dv.output.value.identity=(struct dvbridge_identity){77,13,1};
        GLuint query=0;if(timer)gen(1,&query);
        for(unsigned trial=0;trial<(bench?28:1);trial++)for(unsigned order=0;order<2;order++){
            unsigned mode=order^(trial&1);const struct cb1_dv_enhanced_plan *plan=&plans[mode];
            glFinish();if(timer)begin(GL_TIME_ELAPSED_EXT,query);double start=now();
            assert(dve_run(r,plan,texture,(unsigned[4]){0}));
            if(timer)end(GL_TIME_ELAPSED_EXT);glFinish();double wall_ms=1000*(now()-start);
            GLuint64 elapsed=0;GLint disjoint=0;
            if(timer){result(query,GL_QUERY_RESULT_EXT,&elapsed);glGetIntegerv(GL_GPU_DISJOINT_EXT,&disjoint);}
            assert(glGetError()==GL_NO_ERROR && r->dv.mapped[3]==n && r->dv.mapped[10]==1 && !r->dv.mapped[11]);
            if(bench){
                if(trial>=4)printf("{\"kind\":\"timing\",\"mode\":%u,\"analytic\":%u,\"trial\":%u,\"gpu_timer\":%s,\"disjoint\":%d,\"gpu_ms\":%.9g,\"wall_ms\":%.9g,\"prepack\":%s,\"auxiliary_write\":%s,\"input_bits\":%d}\n",
                    mode,analytic,trial,timer?"true":"false",disjoint,elapsed/1e6,wall_ms,
                    r->enhanced_prepack?"true":"false",r->enhanced_skip_aux?"false":"true",texture->params.format->component_depth[0]);
                continue;
            }
            reference_read(g->gl->gpu,r->enhanced_rgb,0,0,w,h,output);
            double max_error=0,black_error=0,max_ratio=0,mean_in=0,mean_out=0,min_out=1,max_out=0;
            unsigned protected=0;pl_matrix3x3 lms=pl_ipt_rgb2lms(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
            for(unsigned i=0;i<n;i++){
                double rgb[3],want[3],linear[3];
                for(unsigned c=0;c<3;c++)rgb[c]=input[4*i+c]*10000.0;
                assert(cb1_dv_enhanced_pixel(plan,rgb,want));
                double y=.262700212*rgb[0]+.677998072*rgb[1]+.059301716*rgb[2];
                for(unsigned c=0;c<3;c++){
                    max_error=fmax(max_error,fabs(output[4*i+c]-dv_ideal_pq(want[c]))*4095);
                    linear[c]=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,output[4*i+c]);
                    if(y<=10){
                        black_error=fmax(black_error,fabs(linear[c]-rgb[c]));protected++;
                        if(mode)assert(output[4*i+c]==baseline[4*i+c] && "rev B must not alter protected pixels");
                    }
                    assert(linear[c]+.02>=rgb[c] && linear[c]<=2500.1);
                }
                if(rgb[0]>20)for(unsigned c=1;c<3;c++)
                    max_ratio=fmax(max_ratio,fabs(linear[c]/linear[0]-rgb[c]/rgb[0]));
                double before=0,after=0;
                for(unsigned c=0;c<3;c++){
                    before=fmax(before,lms.m[c][0]*rgb[0]+lms.m[c][1]*rgb[1]+lms.m[c][2]*rgb[2]);
                    after=fmax(after,lms.m[c][0]*linear[0]+lms.m[c][1]*linear[1]+lms.m[c][2]*linear[2]);
                }
                mean_in+=dv_ideal_pq(before)/n;mean_out+=dv_ideal_pq(after)/n;
                min_out=fmin(min_out,dv_ideal_pq(after));max_out=fmax(max_out,dv_ideal_pq(after));
            }
            assert(max_error<=1.0 && black_error<=.002 && max_ratio<=.001);
            if(!mode)memcpy(baseline,output,(size_t)n*4*sizeof(float));
            uint16_t l1[3];assert(cb1_dv_enhanced_analysis(plan,l1));
            printf("{\"kind\":\"pixels\",\"mode\":%u,\"analytic\":%u,\"max_error_code12\":%.9g,\"black_error_nits\":%.9g,\"protected_components\":%u,\"max_rgb_ratio_error\":%.9g,\"measured_pq\":[%.9g,%.9g,%.9g],\"source_mean_pq\":%.9g,\"projected_L1\":[%u,%u,%u]}\n",
                mode,analytic,max_error,black_error,protected,max_ratio,min_out,max_out,mean_out,mean_in,l1[0],l1[1],l1[2]);
        }
        if(timer)destroy(1,&query);dv_release(r);
    }
    dvbridge_renderer_destroy(r);pl_tex_destroy(g->gl->gpu,&texture);free(input);free(output);free(baseline);
}

static void pipeline(struct reference_gpu *g,struct pl_frame *frame,AVDOVIMetadata *m,size_t bytes,double pts,unsigned number)
{
    struct dvbridge_policy p=policy();
    void *original=av_memdup(m,bytes);assert(original);
    float *baseline=NULL;unsigned saved_width=0;
    for(unsigned mode=0;mode<2;mode++){
        use_rev_b=mode;
        struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(g->gl->gpu);assert(owner);
        struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
        struct dvbridge_identity id={91,number,1};
        struct dvbridge_geometry geometry={(unsigned)(frame->crop.x1-frame->crop.x0),
            (unsigned)(frame->crop.y1-frame->crop.y0),0,0,3840,2160};
        double scale=fmin(3840.0/geometry.source_width,2160.0/geometry.source_height);
        geometry.width=4*(unsigned)(geometry.source_width*scale/4);
        geometry.height=lround((double)geometry.width*geometry.source_height/geometry.source_width);
        geometry.x=(3840-geometry.width)/2;geometry.y=(2160-geometry.height)/2;
        enum dvbridge_dv_policy_status prepared=dvbridge_render_dv_policy_prepare(r,&p,&id,frame,m,bytes,pts,pts,geometry);
        assert(prepared==DVBRIDGE_DV_PENDING && finish(r)==DVBRIDGE_DV_READY);
        const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
        const AVDOVIMetadata *wire_m=out->output_metadata;
        for(unsigned i=0;i<m->num_ext_blocks;i++){
            const AVDOVIDmData *a=av_dovi_get_ext(m,i),*b=av_dovi_get_ext(wire_m,i);
            if(a->level!=1 && a->level!=3 && a->level!=5)assert(b && !memcmp(a,b,sizeof(*a)));
        }
        const AVDOVIDmData *l3=av_dovi_find_level(wire_m,3);
        if(l3)assert(l3->l3.min_pq_offset==2048 && l3->l3.max_pq_offset==2048 && l3->l3.avg_pq_offset==2048);
        uint16_t projected[3];assert(cb1_dv_enhanced_analysis(&r->dv.enhanced_plan,projected));
        const AVDOVIDmData *l1=av_dovi_find_level(wire_m,1);assert(l1);
        assert(l1->l1.min_pq==projected[0] && l1->l1.max_pq==projected[1] && l1->l1.avg_pq==projected[2]);
        assert(dvbridge_identity_equal(&out->value.identity,&id) && !memcmp(original,m,bytes));
        printf("{\"kind\":\"pipeline\",\"mode\":%u,\"picture\":%u,\"pts\":%.6f,\"reason\":%d,\"L1\":[%u,%u,%u],\"source_max_pq\":%u,\"measured_proxy\":[%.9g,%.9g,%.9g],\"analysis_model\":\"%s\",\"trim_family\":%u,\"trim_anchors\":%u,\"same_picture\":true,\"source_immutable\":true,\"trims_preserved\":true}\n",
            mode,number,pts,out->value.expansion_reason,projected[0],projected[1],projected[2],av_dovi_get_color(wire_m)->source_max_pq,
            out->value.statistics[0],out->value.statistics[1],out->value.statistics[2],out->value.analysis_model,
            r->dv.enhanced_plan.family,r->dv.enhanced_plan.count);
        pl_tex picture=out->intermediate;
        assert(picture && r->enhanced_linear && r->enhanced_input);
        unsigned w=picture->params.w,h=picture->params.h;
        if(!mode){baseline=malloc((size_t)4*w*4*sizeof(float));assert(baseline);saved_width=w;}
        assert(saved_width==w);
        float *row=malloc((size_t)w*4*sizeof(float)),*source=malloc((size_t)w*4*sizeof(float));assert(row && source);
        double max_difference=0,sum_difference=0,protected_error=0,minimum_gain=1e9;
        unsigned compared=0,protected_count=0;
        for(unsigned slice=0;slice<4;slice++){
            unsigned y=(2*slice+1)*h/8;
            reference_read(g->gl->gpu,picture,0,y,w,1,row);
            reference_read(g->gl->gpu,r->enhanced_input,0,y,w,1,source);
            if(!mode)memcpy(baseline+(size_t)slice*w*4,row,(size_t)w*4*sizeof(float));
            for(unsigned x=0;x<w;x+=8){
                double luminance=10000*(.262700212*source[4*x]+.677998072*source[4*x+1]+.059301716*source[4*x+2]);
                for(unsigned c=0;c<3;c++){
                    double input=10000*source[4*x+c],output=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,row[4*x+c]);
                    if(input>1)minimum_gain=fmin(minimum_gain,output/input);
                    if(luminance<=10){protected_error=fmax(protected_error,fabs(output-input));protected_count++;}
                    if(mode){
                        double d=fabs(row[4*x+c]-baseline[((size_t)slice*w+x)*4+c])*4095;
                        max_difference=fmax(max_difference,d);sum_difference+=d;compared++;
                        if(luminance<=10)assert(row[4*x+c]==baseline[((size_t)slice*w+x)*4+c]);
                    }
                }
            }
        }
        assert(protected_error<.03 && minimum_gain>.995);
        printf("{\"kind\":\"clip_pixels_sampled\",\"mode\":%u,\"picture\":%u,\"sampled_components\":%u,\"protected_components\":%u,\"protected_roundtrip_nits\":%.9g,\"minimum_gain\":%.9g,\"max_difference_code12\":%.9g,\"mean_difference_code12\":%.9g}\n",
            mode,number,4*((w+7)/8)*3,protected_count,protected_error,minimum_gain,max_difference,compared?sum_difference/compared:0);
        free(row);free(source);
        dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
        dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
    }
    free(original);free(baseline);
}
static void clip(struct reference_gpu *g,const char *path,double from)
{
    AVFormatContext *fmt=NULL;assert(avformat_open_input(&fmt,path,NULL,NULL)>=0);
    assert(avformat_find_stream_info(fmt,NULL)>=0);
    int track=av_find_best_stream(fmt,AVMEDIA_TYPE_VIDEO,-1,-1,NULL,0);assert(track>=0);
    AVStream *st=fmt->streams[track];
    AVCodecContext *decoder=avcodec_alloc_context3(avcodec_find_decoder(st->codecpar->codec_id));assert(decoder);
    assert(avcodec_parameters_to_context(decoder,st->codecpar)>=0);
    decoder->thread_count=4;decoder->pkt_timebase=st->time_base;
    assert(avcodec_open2(decoder,decoder->codec,NULL)>=0);
    if(from>0)assert(av_seek_frame(fmt,track,from/av_q2d(st->time_base),AVSEEK_FLAG_BACKWARD)>=0);
    AVPacket *packet=av_packet_alloc();AVFrame *frame=av_frame_alloc();assert(packet && frame);
    unsigned decoded=0,samples=0;
    while(samples<6 && av_read_frame(fmt,packet)>=0){
        if(packet->stream_index!=track){av_packet_unref(packet);continue;}
        assert(avcodec_send_packet(decoder,packet)>=0);av_packet_unref(packet);
        while(samples<6 && avcodec_receive_frame(decoder,frame)>=0){
            double pts=frame->best_effort_timestamp*av_q2d(st->time_base);decoded++;
            if(pts<from || decoded%24){av_frame_unref(frame);continue;}
            AVFrameSideData *sd=av_frame_get_side_data(frame,AV_FRAME_DATA_DOVI_METADATA);assert(sd);
            const AVDOVIRpuDataHeader *header=av_dovi_get_header((void*)sd->data);
            assert(header->disable_residual_flag && "Clip probe requires single-layer DV; no FEL omission allowed");
            struct pl_frame image;pl_tex textures[4]={0};
            assert(pl_map_avframe_ex(g->gl->gpu,&image,pl_avframe_params(.frame=frame,.tex=textures,.map_dovi=false)));
            image.repr.dovi=NULL;
            pipeline(g,&image,(void*)sd->data,sd->size,pts,decoded);samples++;
            pl_unmap_avframe(g->gl->gpu,&image);
            for(unsigned i=0;i<4;i++)pl_tex_destroy(g->gl->gpu,&textures[i]);
            av_frame_unref(frame);
        }
    }
    assert(samples>0);av_frame_free(&frame);av_packet_free(&packet);avcodec_free_context(&decoder);avformat_close_input(&fmt);
}
int main(int argc,char **argv)
{
    struct reference_gpu g=reference_gpu_create();
    printf("{\"kind\":\"identity\",\"title\":\"%s\",\"algorithm\":\"%s\",\"renderer\":\"%s\"}\n",
        CB1_DVE_REV_B_TITLE,CB1_DVE_REV_B_ALGORITHM,glGetString(GL_RENDERER));
    if(argc>=3 && !strcmp(argv[1],"--clip"))clip(&g,argv[2],argc>3?atof(argv[3]):0);
    else kernel(&g,argc==2 && !strcmp(argv[1],"--bench"));
    reference_gpu_destroy(&g);
}
