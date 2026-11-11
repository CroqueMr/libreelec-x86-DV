// SPDX-License-Identifier: MIT
/* 4K FEL decode, reference rendering and packed carrier timing with surfaceless EGL. */
#include "reference_test.h"
#include "dvbridge_dmabuf.h"
#include "dvbridge_fel.h"
#include "dvbridge_metadata.h"
#include "cb1_master_reference.h"
#include <libavformat/avformat.h>
#include <libavutil/hwcontext.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <gbm.h>
#include <errno.h>
#include <EGL/eglext.h>
#include <GLES2/gl2ext.h>
#include <linux/dma-buf.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
void cb1_host_frame_store(struct dvbridge_renderer *,pl_buf);
void cb1_cpu_init(unsigned,unsigned);
void cb1_cpu_start(float *,uint32_t *);
int cb1_cpu_ready(int);
void cb1_cpu_destroy(void);
enum { SLOTS=6, WIDTH=3840, HEIGHT=2160 };

static double clock_ms(void)
{
    struct timespec t; assert(!clock_gettime(CLOCK_MONOTONIC,&t));
    return t.tv_sec*1000.0+t.tv_nsec/1e6;
}

static enum AVPixelFormat hardware(AVCodecContext *ctx,const enum AVPixelFormat *formats)
{
    (void)ctx;
    for(;*formats!=AV_PIX_FMT_NONE;formats++)if(*formats==AV_PIX_FMT_VAAPI)return *formats;
    return AV_PIX_FMT_NONE;
}

struct pending {
    struct dvbridge_dmabuf imports[2];
    struct dvbridge_gl_frame frames[2];
    AVFrame *refs[2];
    GLsync fence;
    pl_buf host;
    struct gbm_bo *bo;
    int dma_fd;
    void *pixels;
    EGLImageKHR image;
    GLuint texture,fbo;
    enum {FREE, RENDERED, CPU, OUTPUT} phase;
    double deadline;
};
static unsigned observed_late, observed;
static double max_late_ms;
static const char *render_node;
static int render_fd;
static struct gbm_device *gbm;
static GLuint probe_fbo,probe_texture;
static PFNEGLCREATEIMAGEKHRPROC create_image;
static PFNEGLDESTROYIMAGEKHRPROC destroy_image;
static PFNGLEGLIMAGETARGETTEXTURE2DOESPROC bind_image;

static void init_gbm(void)
{
    render_fd=open(render_node,O_RDWR|O_CLOEXEC);
    assert(render_fd>=0);
    gbm=gbm_create_device(render_fd);
    assert(gbm);
    create_image=(PFNEGLCREATEIMAGEKHRPROC)eglGetProcAddress("eglCreateImageKHR");
    destroy_image=(PFNEGLDESTROYIMAGEKHRPROC)eglGetProcAddress("eglDestroyImageKHR");
    bind_image=(PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)eglGetProcAddress("glEGLImageTargetTexture2DOES");
    assert(create_image && destroy_image && bind_image);
    if(getenv("CB1_PROBE_CARRIER")){
        glGenTextures(1,&probe_texture);
        glBindTexture(GL_TEXTURE_2D,probe_texture);
        glTexStorage2D(GL_TEXTURE_2D,1,GL_RGBA8,1,1);
        glBindTexture(GL_TEXTURE_2D,0);
        glGenFramebuffers(1,&probe_fbo);
        glBindFramebuffer(GL_FRAMEBUFFER,probe_fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,probe_texture,0);
        assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
        glBindFramebuffer(GL_FRAMEBUFFER,0);
    }
}
static void create_carrier(struct pending *p)
{
    p->bo=gbm_bo_create(gbm,WIDTH,HEIGHT,GBM_FORMAT_ABGR8888,
        GBM_BO_USE_RENDERING|GBM_BO_USE_SCANOUT|GBM_BO_USE_LINEAR);
    assert(p->bo);
    unsigned stride=gbm_bo_get_stride(p->bo);
    uint64_t modifier=gbm_bo_get_modifier(p->bo);
    assert(stride==WIDTH*4 && modifier==0);
    p->dma_fd=gbm_bo_get_fd(p->bo);
    assert(p->dma_fd>=0);
    p->pixels=mmap(NULL,(size_t)stride*HEIGHT,PROT_READ|PROT_WRITE,MAP_SHARED,p->dma_fd,0);
    assert(p->pixels!=MAP_FAILED);
    EGLint attrs[]={EGL_WIDTH,WIDTH,EGL_HEIGHT,HEIGHT,
        EGL_LINUX_DRM_FOURCC_EXT,GBM_FORMAT_ABGR8888,
        EGL_DMA_BUF_PLANE0_FD_EXT,p->dma_fd,EGL_DMA_BUF_PLANE0_OFFSET_EXT,0,
        EGL_DMA_BUF_PLANE0_PITCH_EXT,stride,EGL_DMA_BUF_PLANE0_MODIFIER_LO_EXT,0,
        EGL_DMA_BUF_PLANE0_MODIFIER_HI_EXT,0,EGL_NONE};
    p->image=create_image(eglGetCurrentDisplay(),EGL_NO_CONTEXT,EGL_LINUX_DMA_BUF_EXT,NULL,attrs);
    assert(p->image!=EGL_NO_IMAGE_KHR);
    glGenTextures(1,&p->texture);
    glBindTexture(GL_TEXTURE_2D,p->texture);
    bind_image(GL_TEXTURE_2D,p->image);
    glBindTexture(GL_TEXTURE_2D,0);
    if(probe_fbo){
        glGenFramebuffers(1,&p->fbo);
        glBindFramebuffer(GL_READ_FRAMEBUFFER,p->fbo);
        glFramebufferTexture2D(GL_READ_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,p->texture,0);
        assert(glCheckFramebufferStatus(GL_READ_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
        glBindFramebuffer(GL_READ_FRAMEBUFFER,0);
    }
    assert(glGetError()==GL_NO_ERROR);
}
static void sync_carrier(struct pending *p,uint64_t mode)
{
    struct dma_buf_sync sync={.flags=mode|DMA_BUF_SYNC_WRITE};
    int status;
    do {
        status=ioctl(p->dma_fd,DMA_BUF_IOCTL_SYNC,&sync);
    } while(status<0 && (errno==EINTR || errno==EAGAIN));
    assert(status==0);
}
static void destroy_carrier(struct pending *p)
{
    if(!p->bo)return;
    glDeleteFramebuffers(1,&p->fbo);
    glDeleteTextures(1,&p->texture);
    destroy_image(eglGetCurrentDisplay(),p->image);
    munmap(p->pixels,(size_t)WIDTH*HEIGHT*4);
    close(p->dma_fd);
    gbm_bo_destroy(p->bo);
}
static void dump_carrier(struct pending *p)
{
    uint8_t *pixels=malloc((size_t)WIDTH*HEIGHT*4);
    assert(pixels);
    GLuint fbo;
    glGenFramebuffers(1,&fbo);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_READ_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,p->texture,0);
    assert(glCheckFramebufferStatus(GL_READ_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
    glReadPixels(0,0,WIDTH,HEIGHT,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
    assert(glGetError()==GL_NO_ERROR);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,0);
    glDeleteFramebuffers(1,&fbo);
    FILE *out=fopen("pipeline-cpu.rgba","wb");assert(out);
    assert(fwrite(pixels,4,(size_t)WIDTH*HEIGHT,out)==(size_t)WIDTH*HEIGHT);
    assert(!fclose(out));
    free(pixels);
}

static unsigned submitted,to_cpu,retired;
static struct pending *cpu_slot;
static double cpu_start_ms,cpu_observed_ms,handoff_ms;
static unsigned packed_frames;

static bool ready(struct pending *p,bool wait)
{
    if(!p->fence){assert(p->phase==OUTPUT);return true;}
    GLenum result=glClientWaitSync(p->fence,GL_SYNC_FLUSH_COMMANDS_BIT,wait?1000000000:0);
    if(result==GL_TIMEOUT_EXPIRED && !wait)return false;
    assert(result==GL_ALREADY_SIGNALED || result==GL_CONDITION_SATISFIED);
    glDeleteSync(p->fence);p->fence=NULL;
    return true;
}
static void release_picture(struct pending *p)
{
    for(int i=!!p->refs[1];i>=0;i--){
        dvbridge_gl_frame_release(&p->frames[i]);
        dvbridge_dmabuf_release(&p->imports[i]);
        av_frame_free(&p->refs[i]);
    }
}
static void pump(struct pending q[SLOTS],bool wait)
{
    bool changed=false;
    for(;;){
        if(cpu_slot && cb1_cpu_ready(0)){
            struct pending *p=cpu_slot;
            double t=clock_ms();
            cpu_observed_ms+=t-cpu_start_ms;
            packed_frames++;
            sync_carrier(p,DMA_BUF_SYNC_END);
            // Wait for the optional GPU consumer before recycling this carrier.
            if(probe_fbo){
                glBindFramebuffer(GL_READ_FRAMEBUFFER,p->fbo);
                glBindFramebuffer(GL_DRAW_FRAMEBUFFER,probe_fbo);
                glBlitFramebuffer(WIDTH/2,HEIGHT/2,WIDTH/2+1,HEIGHT/2+1,0,0,1,1,
                                  GL_COLOR_BUFFER_BIT,GL_NEAREST);
                glBindFramebuffer(GL_FRAMEBUFFER,0);
                p->fence=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0);
                assert(p->fence);
                glFlush();
                assert(glGetError()==GL_NO_ERROR);
            }
            p->phase=OUTPUT;
            handoff_ms+=clock_ms()-t;
            cpu_slot=NULL;changed=true;
        }
        if(!cpu_slot && to_cpu<submitted){
            struct pending *p=&q[to_cpu%SLOTS];
            assert(p->phase==RENDERED);
            if(ready(p,false)){
                release_picture(p);
                if(!p->bo)create_carrier(p);
                sync_carrier(p,DMA_BUF_SYNC_START);
                cpu_start_ms=clock_ms();
                cb1_cpu_start((float *)p->host->data,(uint32_t *)p->pixels);
                p->phase=CPU;cpu_slot=p;to_cpu++;changed=true;
            }
        }
        while(retired<submitted && q[retired%SLOTS].phase==OUTPUT){
            struct pending *p=&q[retired%SLOTS];
            if(!ready(p,false))break;
            if(p->deadline>0){
                double late=clock_ms()-p->deadline;
                observed++;observed_late+=late>0;
                if(late>max_late_ms)max_late_ms=late;
            }
            p->deadline=0;p->phase=FREE;retired++;changed=true;
        }
        if(changed || !wait || retired==submitted)return;
        if(cpu_slot){
            cb1_cpu_ready(1);
        }else{
            // A consumer blit can be queued behind renders already ready for the CPU.
            unsigned next = to_cpu < submitted ? to_cpu : retired;
            struct pending *p=&q[next%SLOTS];
            assert(p->fence);
            GLenum result=glClientWaitSync(p->fence,GL_SYNC_FLUSH_COMMANDS_BIT,1000000000);
            assert(result==GL_ALREADY_SIGNALED || result==GL_CONDITION_SATISFIED);
        }
    }
}
static void drain(struct pending q[SLOTS])
{
    while(retired<submitted)pump(q,true);
}

static void render(struct reference_gpu *g,struct dvbridge_renderer *renderer,pl_tex target,
                   const AVFrame *base,const AVFrame *el,struct pending *slot)
{
    const AVFrame *layers[]={base,el};
    struct dvbridge_dmabuf *imports=slot->imports;
    struct dvbridge_gl_frame *frames=slot->frames;
    for(int i=0;i<1+!!el;i++){
        const AVFrame *frame=layers[i];
        slot->refs[i]=av_frame_clone(frame);assert(slot->refs[i]);
        assert(dvbridge_dmabuf_import(&imports[i],frame));
        assert(dvbridge_gl_frame_import(&frames[i],g->gl->gpu,imports[i].layout,frame->width,frame->height,imports[i].planes));
        enum pl_chroma_location location=dvbridge_map_chroma(frame->chroma_location);
        if(location==PL_CHROMA_UNKNOWN)location=el?PL_CHROMA_TOP_LEFT:PL_CHROMA_LEFT;
        dvbridge_gl_frame_set_chroma(&frames[i],location);
    }
    if(el)frames[0].frame.enhancement_layer=&frames[1].frame;
    const AVFrameSideData *sd=av_frame_get_side_data(base,AV_FRAME_DATA_DOVI_METADATA);
    assert(sd);
    const struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={1000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    double pts=base->pts*av_q2d(base->time_base);
    if(!slot->host){
        pl_gpu gpu=g->gl->gpu;
        slot->host=pl_buf_create(gpu,pl_buf_params(.size=(size_t)base->width*base->height*16,
            .host_mapped=true,.storable=true,.memory_type=PL_BUF_MEM_HOST));
        assert(slot->host && slot->host->data);
    }
    cb1_host_frame_store(renderer,slot->host);
    enum cb1_master_status status=dvbridge_render_player_led(renderer,&policy,&frames[0].frame,
        sd->data,sd->size,pts,el?pts:NAN,target,NULL);
    if(status!=CB1_MASTER_READY){fprintf(stderr,"render status=%d pts=%.6f\n",status,pts);abort();}
    cb1_host_frame_store(renderer,NULL);
    // The persistent SSBO is coherent. Wait for this draw before starting the CPU pack.
    slot->fence=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0);assert(slot->fence);
    slot->phase=RENDERED;
    glFlush();assert(glGetError()==GL_NO_ERROR);
}

int main(int argc,char **argv)
{
    alarm(180);
    assert(__builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma"));
    render_node=getenv("CB1_RENDER_NODE");
    if(!render_node)render_node="/dev/dri/renderD128";
    assert(argc==6 && (!strcmp(argv[1],"single") || !strcmp(argv[1],"fel")));
    bool paired=!strcmp(argv[1],"fel");
    const unsigned bits=atoi(argv[5]);assert(bits==10 || bits==12);
    unsigned samples=atoi(argv[3]),warmup=atoi(argv[4]);
    assert(samples && samples<=1800 && (samples%300==0 || getenv("CB1_CPU_DUMP")) && warmup<=500);
    AVBufferRef *device=NULL;
    assert(av_hwdevice_ctx_create(&device,AV_HWDEVICE_TYPE_VAAPI,render_node,NULL,0)>=0);
    AVFormatContext *file=NULL;assert(!avformat_open_input(&file,argv[2],NULL,NULL));
    assert(avformat_find_stream_info(file,NULL)>=0);
    int index=av_find_best_stream(file,AVMEDIA_TYPE_VIDEO,-1,-1,NULL,0);assert(index>=0);
    AVStream *stream=file->streams[index];
    assert(stream->codecpar->codec_id==AV_CODEC_ID_HEVC);
    AVCodecContext *decoder=avcodec_alloc_context3(avcodec_find_decoder(AV_CODEC_ID_HEVC));assert(decoder);
    assert(!avcodec_parameters_to_context(decoder,stream->codecpar));
    decoder->hw_device_ctx=av_buffer_ref(device);decoder->get_format=hardware;
    decoder->pkt_timebase=stream->time_base;decoder->thread_count=1;decoder->extra_hw_frames=32;
    assert(!avcodec_open2(decoder,decoder->codec,NULL));
    struct dvbridge_fel *fel=paired?dvbridge_fel_create(stream->codecpar,stream->time_base):NULL;
    if(paired)assert(fel && dvbridge_fel_device(fel,device));
    struct reference_gpu g=reference_gpu_create();
    init_gbm();
    struct dvbridge_renderer *renderer=dvbridge_renderer_create(g.gl->gpu);assert(renderer);
    pl_tex target=NULL;
    AVFrame *queue[32]={0};
    AVPacket *packet=av_packet_alloc();assert(packet);
    unsigned count=0,pictures=0,discarded=0;
    struct pending pending[SLOTS]={0};
    const char *worker_count=getenv("CB1_CPU_THREADS");
    cb1_cpu_init(worker_count?atoi(worker_count):4,bits);
    double started=0,first_deadline=0;
    int64_t first_pts=AV_NOPTS_VALUE;
    double pace=getenv("CB1_TARGET_FPS")?atof(getenv("CB1_TARGET_FPS")):0;
    puts("frames,elapsed_ms");

    while(pictures<samples+warmup && av_read_frame(file,packet)>=0) {
        if(packet->stream_index!=index){av_packet_unref(packet);continue;}
        if(fel)assert(dvbridge_fel_submit(fel,packet));
        assert(avcodec_send_packet(decoder,packet)>=0);
        av_packet_unref(packet);
        while(true) {
            AVFrame *frame=av_frame_alloc();assert(frame);
            int rc=avcodec_receive_frame(decoder,frame);
            if(rc==AVERROR(EAGAIN)){av_frame_free(&frame);break;}
            assert(rc>=0 && count<32);frame->time_base=stream->time_base;queue[count++]=frame;
        }
        while(count && pictures<samples+warmup) {
            AVFrame *el=NULL;
            AVFrame *base=queue[0];
            int rc=fel?dvbridge_fel_take(fel,base->pts,&el):1;
            assert(rc>=0);if(!rc)break;
            if(rc==1){
                assert(base->format==AV_PIX_FMT_VAAPI && (!paired || (el && el->pts==base->pts)));
                if(!target){
                    pl_gpu gpu=g.gl->gpu;
                    pl_fmt rgba=pl_find_fmt(gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE);
                    assert(rgba);
                    target=pl_tex_create(gpu,pl_tex_params(.w=base->width,.h=base->height,
                        .format=rgba,.renderable=true));assert(target);
                    assert(base->width==WIDTH && base->height==HEIGHT);
                }
                if(pictures>=warmup && (pictures-warmup)%300==0){
                    drain(pending);
                    double now=clock_ms();
                    if(started)printf("300,%.9f\n",now-started);
                    started=now;
                }
                pump(pending,false);
                struct pending *slot=&pending[pictures%SLOTS];
                while(slot->phase!=FREE)pump(pending,true);
                if(pictures>=warmup){
                    assert(base->pts!=AV_NOPTS_VALUE);
                    if(first_pts==AV_NOPTS_VALUE){
                        first_pts=base->pts;
                        first_deadline=started+100.0;
                    }
                    slot->deadline=first_deadline+(pace>0?1000*(pictures-warmup)/pace:
                        1000*(base->pts-first_pts)*av_q2d(base->time_base));
                }
                render(&g,renderer,target,base,el,slot);
                pictures++;submitted++;
            }else discarded++;
            av_frame_free(&el);av_frame_free(&base);
            memmove(queue,queue+1,(--count)*sizeof(*queue));
        }
    }
    drain(pending);
    cb1_cpu_destroy();
    fprintf(stderr,"CPU observed avg %.3f ms; carrier handoff avg %.3f ms\n",
        cpu_observed_ms/packed_frames,handoff_ms/packed_frames);
    assert(started);
    printf("%u,%.9f\n",samples%300?samples%300:300,clock_ms()-started);
    fprintf(stderr,"pictures=%u discarded_preroll=%u samples=%u\n",pictures,discarded,samples);
    assert(pictures==samples+warmup && observed==samples);
    fprintf(stderr,"observed_late=%u/%u lead_ms=100 max_late_ms=%.3f\n",observed_late,observed,max_late_ms);
    if(getenv("CB1_CPU_DUMP"))dump_carrier(&pending[(pictures-1)%SLOTS]);
    for(int i=0;i<SLOTS;i++){
        pl_buf_destroy(g.gl->gpu,&pending[i].host);
        destroy_carrier(&pending[i]);
    }
    for(unsigned i=0;i<count;i++)av_frame_free(&queue[i]);
    dvbridge_renderer_destroy(renderer);pl_tex_destroy(g.gl->gpu,&target);glDeleteFramebuffers(1,&probe_fbo);glDeleteTextures(1,&probe_texture);
    gbm_device_destroy(gbm);close(render_fd);reference_gpu_destroy(&g);
    av_packet_free(&packet);dvbridge_fel_destroy(fel);avcodec_free_context(&decoder);
    avformat_close_input(&file);av_buffer_unref(&device);
}
