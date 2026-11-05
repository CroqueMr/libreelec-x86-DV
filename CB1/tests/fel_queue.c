/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_fel.c"
#include <libavutil/hwcontext.h>
#include <libavutil/hwcontext_vaapi.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "synthetic_idr.h"

/* Real FFmpeg splitter and ownership; deterministic decoder replaces VAAPI ioctls. */
static int64_t ready[64];
static unsigned count, submissions;
static bool end, bad_pts, send_error, invalid_send_once, invalid_receive_once;
static int native_pool, initialized_pool = -1;
/* Owned synthetic HEVC: nonkey BL prefix and a present EL CRA before its IDR. */
static const uint8_t seek_config[] = {0,0,0,1,64,1,12,1,255,255,1,96,0,0,3,0,144,0,0,3,0,0,3,0,30,146,128,144,0,0,0,1,66,1,1,1,96,0,0,3,0,144,0,0,3,0,0,3,0,30,160,16,32,32,89,100,169,36,202,240,22,128,128,0,0,3,0,128,0,0,12,4,0,0,0,1,68,1,193,114,180,34,64};
static const uint8_t seek_base[][17] = {{0,0,1,2,1,208,9,126,16,198,59,249,139,232,0},
    {0,0,1,2,1,208,17,255,212,67,6,57,249,139,232,0},
    {0,0,1,2,1,208,24,159,253,196,48,24,228,249,139,232,0}};
static const uint8_t seek_el_cra[] = {0,0,0,1,126,1,64,1,12,1,255,255,1,96,0,0,3,0,144,0,0,3,0,0,3,0,30,146,128,144,0,0,0,1,126,1,66,1,1,1,96,0,0,3,0,144,0,0,3,0,0,3,0,30,160,16,32,32,89,100,169,36,202,240,22,128,128,0,0,3,0,128,0,0,12,4,0,0,0,1,126,1,68,1,193,114,180,34,64,0,0,0,1,126,1,42,1,172,16,77,92,86,247,1,196,125,63,251,241,176,136,192,148,236,36,224,0};

static void present_seek_preroll_is_not_missing(AVBufferRef *device)
{
    AVCodecParameters *parameters=avcodec_parameters_alloc();assert(parameters);
    parameters->codec_type=AVMEDIA_TYPE_VIDEO;parameters->codec_id=AV_CODEC_ID_HEVC;
    struct dvbridge_fel *f=dvbridge_fel_create(parameters,(AVRational){1,1000000});
    avcodec_parameters_free(&parameters);assert(f&&dvbridge_fel_device(f,device));
    size_t idr=0;
    while(idr+5<sizeof(synthetic_paired)&&memcmp(synthetic_paired+idr,"\0\0\1\x7e\1",5))++idr;
    assert(idr+5<sizeof(synthetic_paired));
    for(unsigned i=0;i<3;++i){
        const size_t headers=i?0:sizeof(seek_config),base=15+i;
        const uint8_t *el=i==2?synthetic_paired+idr:seek_el_cra;
        const size_t bytes=i==2?sizeof(synthetic_paired)-idr:sizeof(seek_el_cra);
        AVPacket *p=av_packet_alloc();assert(p&&av_new_packet(p,headers+base+bytes)==0);
        memcpy(p->data,seek_config,headers);memcpy(p->data+headers,seek_base[i],base);
        memcpy(p->data+headers+base,el,bytes);p->pts=p->dts=1000*(i+1);
        assert(dvbridge_fel_submit(f,p));av_packet_free(&p);
        assert(!f->epoch_uncertain && "Parsed EL preroll must never be reported missing");
    }
    AVFrame *frame=NULL;
    assert(dvbridge_fel_take(f,3000,&frame)==1&&frame&&frame->pts==3000);
    av_frame_free(&frame);dvbridge_fel_destroy(f);
}
int __wrap_avcodec_get_hw_frames_parameters(AVCodecContext *ctx, AVBufferRef *device,
                                           enum AVPixelFormat format, AVBufferRef **frames)
{
    assert(ctx && device == ctx->hw_device_ctx && format == AV_PIX_FMT_VAAPI);
    *frames = av_buffer_allocz(sizeof(AVHWFramesContext));
    assert(*frames);
    ((AVHWFramesContext *)(*frames)->data)->initial_pool_size = native_pool;
    return 0;
}
int __wrap_av_hwframe_ctx_init(AVBufferRef *frames)
{
    initialized_pool = ((AVHWFramesContext *)frames->data)->initial_pool_size;
    return 0;
}
int __wrap_avcodec_open2(AVCodecContext *ctx, const AVCodec *codec, AVDictionary **options)
{
    (void)codec; (void)options;
    assert(ctx->hw_device_ctx && ctx->get_format && ctx->thread_count == 1);
    const enum AVPixelFormat formats[] = {AV_PIX_FMT_VAAPI, AV_PIX_FMT_NONE};
    assert(ctx->get_format(ctx, formats) == AV_PIX_FMT_VAAPI);
    return 0;
}
void __wrap_avcodec_flush_buffers(AVCodecContext *ctx)
{
    (void)ctx;
    count = 0;
    end = false;
}
int __wrap_avcodec_send_packet(AVCodecContext *ctx, const AVPacket *packet)
{
    (void)ctx;
    ++submissions;
    if (send_error)
        return AVERROR(ENOMEM);
    if (invalid_send_once) {
        invalid_send_once = false;
        return AVERROR_INVALIDDATA;
    }
    if (!packet) {
        end = true;
        return 0;
    }
    assert(packet->size == sizeof(synthetic_base));
    assert(memcmp(packet->data, synthetic_base, sizeof(synthetic_base)) == 0);
    assert(count < 64);
    ready[count++] = packet->pts;
    return 0;
}
int __wrap_avcodec_receive_frame(AVCodecContext *ctx, AVFrame *frame)
{
    (void)ctx;
    if (invalid_receive_once) {
        invalid_receive_once = false;
        return AVERROR_INVALIDDATA;
    }
    if (!count)
        return end ? AVERROR_EOF : AVERROR(EAGAIN);
    frame->format = AV_PIX_FMT_VAAPI;
    frame->width = 1920;
    frame->height = 1080;
    frame->best_effort_timestamp = bad_pts ? AV_NOPTS_VALUE : ready[0];
    frame->pts = frame->best_effort_timestamp;
    frame->buf[0] = av_buffer_alloc(8);
    assert(frame->buf[0]);
    --count;
    memmove(ready, ready + 1, count * sizeof(*ready));
    return 0;
}

static AVPacket *packet(int64_t pts)
{
    /* Real synthetic IDR BL plus encapsulated EL, for picture-order parsing. */
    AVPacket *p = av_packet_alloc();
    assert(p && av_new_packet(p, sizeof(synthetic_paired)) == 0);
    memcpy(p->data, synthetic_paired, sizeof(synthetic_paired));
    p->pts = p->dts = pts;
    return p;
}

int main(void)
{
    if(!avcodec_find_decoder(AV_CODEC_ID_HEVC)){
        fputs("SKIP FEL queue witness requires an FFmpeg build with the HEVC decoder\n",stderr);
        return 77;
    }
    AVCodecParameters *parameters = avcodec_parameters_alloc();
    assert(parameters);
    parameters->codec_type = AVMEDIA_TYPE_VIDEO;
    parameters->codec_id = AV_CODEC_ID_HEVC;
    parameters->width = 3840;
    parameters->height = 2160;
    struct dvbridge_fel *f = dvbridge_fel_create(parameters, (AVRational){1,1000000});
    avcodec_parameters_free(&parameters);
    assert(f);
    AVPacket *p = packet(0);
    AVFrame *frame = NULL;
    assert(dvbridge_fel_submit(f, p));
    assert(p->size == sizeof(synthetic_paired));
    assert(memcmp(p->data, synthetic_paired, sizeof(synthetic_paired)) == 0);
    assert(dvbridge_fel_take(f, 0, &frame) == 0 && !frame);
    AVBufferRef *device = av_buffer_allocz(sizeof(AVHWDeviceContext));
    assert(device);
    int display_token, other_display_token;
    AVVAAPIDeviceContext va_device = {.display = &display_token};
    ((AVHWDeviceContext *)device->data)->type = AV_HWDEVICE_TYPE_VAAPI;
    ((AVHWDeviceContext *)device->data)->hwctx = &va_device;
    assert(dvbridge_fel_device(f, device));
    assert(initialized_pool == 0); /* Preserve FFmpeg's dynamically growing VAAPI pool. */
    assert(submissions == 0); /* Device binding must not submit EL before a BL request. */
    assert(dvbridge_fel_take(f, 0, &frame) == 1 && frame->pts == 0);
    assert(dvbridge_fel_take(f, 0, &frame) == -1); /* refuse overwriting ownership */
    av_frame_free(&frame);
    assert(dvbridge_fel_take(f, 0, &frame) == 0);
    for (int i = 1; i <= 3; ++i) {
        p->pts = p->dts = i * 41708;
        assert(dvbridge_fel_submit(f, p));
    }
    assert(dvbridge_fel_take(f, 2 * 41708, &frame) == 1); /* skip stale EL after BL drop */
    av_frame_free(&frame);
    /* Released API waits for a missing identity while lookahead remains bounded. */
    assert(dvbridge_fel_take(f, 2 * 41708 + 1, &frame) == 0 && !frame);
    assert(dvbridge_fel_take(f, 3 * 41708, &frame) == 1);
    /* A renewed BL decoder may wrap the same VA display in a new AVBuffer. */
    AVBufferRef *renewed = av_buffer_allocz(sizeof(AVHWDeviceContext));
    assert(renewed);
    AVVAAPIDeviceContext va_renewed = {.display = &display_token};
    ((AVHWDeviceContext *)renewed->data)->type = AV_HWDEVICE_TYPE_VAAPI;
    ((AVHWDeviceContext *)renewed->data)->hwctx = &va_renewed;
    assert(dvbridge_fel_device(f, renewed));
    av_frame_free(&frame);
    p->pts = p->dts = 4 * 41708;
    assert(dvbridge_fel_submit(f, p));
    assert(dvbridge_fel_device(f, renewed));
    assert(dvbridge_fel_take(f, 4 * 41708, &frame) == 1 && frame->pts == 4 * 41708);
    va_renewed.display = &other_display_token;
    assert(!dvbridge_fel_device(f, renewed));
    va_renewed.display = NULL;
    assert(!dvbridge_fel_device(f, renewed));
    ((AVHWDeviceContext *)renewed->data)->type = AV_HWDEVICE_TYPE_CUDA;
    assert(!dvbridge_fel_device(f, renewed));
    assert(dvbridge_fel_device(f, device) && !dvbridge_fel_failed(f));
    av_buffer_unref(&renewed);
    dvbridge_fel_reset(f);
    assert(frame->pts == 4 * 41708 && frame->buf[0]); /* downstream ref survives seek */
    av_frame_free(&frame);
    p->pts = p->dts = 0;
    assert(dvbridge_fel_submit(f, p));
    assert(dvbridge_fel_take(f, 0, &frame) == 1);
    av_frame_free(&frame);
    assert(dvbridge_fel_drain(f));
    assert(dvbridge_fel_take(f, 1, &frame) == -1 && !frame);
    assert(!dvbridge_fel_submit(f, p));
    dvbridge_fel_reset(f);
    unsigned queued = submissions;
    for (int i = 0; i < 3; ++i) {
        p->pts = p->dts = i * 41708;
        assert(dvbridge_fel_submit(f, p));
    }
    assert(submissions == queued);
    assert(dvbridge_fel_drain(f)); /* EOF must submit and retain all deferred pictures. */
    for (int i = 0; i < 3; ++i) {
        assert(dvbridge_fel_take(f, i * 41708, &frame) == 1 && frame->pts == i * 41708);
        av_frame_free(&frame);
    }
    assert(dvbridge_fel_exhausted(f));
    assert(dvbridge_fel_take(f, 3 * 41708, &frame) == -1 && !frame);
    dvbridge_fel_reset(f);
    p->pts = p->dts = 0;
    bad_pts = true;
    assert(dvbridge_fel_submit(f, p));
    assert(dvbridge_fel_take(f, p->pts, &frame) == -1 && dvbridge_fel_failed(f));
    bad_pts = false;
    dvbridge_fel_reset(f);
    send_error = true;
    assert(dvbridge_fel_submit(f, p));
    assert(dvbridge_fel_take(f, p->pts, &frame) == -1 && dvbridge_fel_failed(f));
    send_error = false;
    dvbridge_fel_reset(f);
    assert(!dvbridge_fel_failed(f));
    p->pts = p->dts = 0; assert(dvbridge_fel_submit(f, p));
    p->pts = p->dts = 41708; assert(dvbridge_fel_submit(f, p));
    assert(dvbridge_fel_take(f, 0, &frame) == 1 && frame->pts == 0);
    av_frame_free(&frame);
    p->pts = p->dts = 83416; assert(dvbridge_fel_submit(f, p));
    unsigned before = submissions;
    send_error = true;
    assert(dvbridge_fel_take(f, 41708, &frame) == 1 && frame->pts == 41708);
    assert(submissions == before); /* A ready picture does not wait for future EL work. */
    av_frame_free(&frame);
    assert(dvbridge_fel_take(f, 83416, &frame) == -1 && dvbridge_fel_failed(f));
    assert(!dvbridge_fel_device(f, device));
    send_error = false;
    dvbridge_fel_destroy(f);
    native_pool = 5;
    parameters = avcodec_parameters_alloc();
    assert(parameters);
    parameters->codec_type = AVMEDIA_TYPE_VIDEO;
    parameters->codec_id = AV_CODEC_ID_HEVC;
    parameters->width = 3840;
    parameters->height = 2160;
    f = dvbridge_fel_create(parameters, (AVRational){1,1000000});
    avcodec_parameters_free(&parameters);
    assert(f && dvbridge_fel_device(f, device));
    assert(initialized_pool == 41); /* Fixed pools retain the existing 32+4 headroom. */
    dvbridge_fel_destroy(f);
    parameters = avcodec_parameters_alloc();
    parameters->codec_type = AVMEDIA_TYPE_VIDEO;
    parameters->codec_id = AV_CODEC_ID_HEVC;
    parameters->width = 3840;
    parameters->height = 2160;
    f = dvbridge_fel_create(parameters, (AVRational){1,1000000});
    avcodec_parameters_free(&parameters);
    assert(f);
    for (int i = 0; i < 32; ++i) {
        p->pts = i;
        assert(dvbridge_fel_submit(f, p));
    }
    p->pts = 32;
    assert(!dvbridge_fel_submit(f, p) && dvbridge_fel_failed(f));
    assert(!dvbridge_fel_device(f, device)); /* Failure before the first binding stays terminal. */
    dvbridge_fel_reset(f);
    assert(dvbridge_fel_submit(f, p));
    dvbridge_fel_destroy(f);

    /* Corrupt EL input must consume forward, not leave Kodi retrying forever.
     * Ready exact pairs survive; recovery never substitutes a neighbouring EL. */
    parameters = avcodec_parameters_alloc();
    assert(parameters);
    parameters->codec_type = AVMEDIA_TYPE_VIDEO;
    parameters->codec_id = AV_CODEC_ID_HEVC;
    parameters->width = 3840;
    parameters->height = 2160;
    f = dvbridge_fel_create(parameters, (AVRational){1,1000000});
    avcodec_parameters_free(&parameters);
    assert(f && dvbridge_fel_device(f, device));
    for (int i=0; i<3; ++i) {
        p->pts=p->dts=100*i;
        assert(dvbridge_fel_submit(f,p));
    }
    assert(dvbridge_fel_take(f,0,&frame)==1 && frame->pts==0);
    av_frame_free(&frame);
    p->pts=p->dts=300;
    assert(dvbridge_fel_submit(f,p));
    invalid_send_once=true;
    assert(dvbridge_fel_take(f,1,&frame)==2 && !frame && !dvbridge_fel_failed(f));
    for (int i=1; i<3; ++i) {
        assert(dvbridge_fel_take(f,100*i,&frame)==1 && frame->pts==100*i);
        av_frame_free(&frame);
    }
    p->pts=p->dts=400;
    assert(dvbridge_fel_submit(f,p));
    assert(dvbridge_fel_take(f,300,&frame)==2 && !frame);
    assert(dvbridge_fel_take(f,400,&frame)==1 && frame->pts==400);
    av_frame_free(&frame);
    p->pts=p->dts=500;
    assert(dvbridge_fel_submit(f,p));
    invalid_receive_once=true;
    assert(dvbridge_fel_take(f,500,&frame)==1 && frame->pts==500);
    av_frame_free(&frame);
    assert(!dvbridge_fel_failed(f));
    dvbridge_fel_destroy(f);
    /* Authored epoch-loss witness: the absent last EL AU leaves its next IDR
     * at identity 31, although BL's next epoch starts at 32. It must never be
     * attached to nonkey BL31 merely because the inherited counters agree. */
    for (int variant=0; variant<3; ++variant) {
        parameters=avcodec_parameters_alloc();
        parameters->codec_type=AVMEDIA_TYPE_VIDEO;
        parameters->codec_id=AV_CODEC_ID_HEVC;
        parameters->width=3840;parameters->height=2160;
        f=dvbridge_fel_create(parameters,(AVRational){1,1000000});
        avcodec_parameters_free(&parameters);
        assert(f && dvbridge_fel_device(f,device));
        p->pts=p->dts=0;assert(dvbridge_fel_submit(f,p));
        f->base_order.maximum=31;f->base_order.seen=true;
        f->enhancement_order.maximum=30;f->enhancement_order.seen=true;
        int64_t bl,el;
        assert(picture_identity(&f->base_order,p,&bl) && bl==32);
        assert(picture_identity(&f->enhancement_order,p,&el) && el==31);
        f->packet_order[0]=el;
        f->times[0].order=31;f->times[0].pts=3100;
        f->times[0].key=variant==2;
        f->base_order.context->has_b_frames=variant!=1;
        unsigned sent=submissions;
        int result=dvbridge_fel_take(f,3100,&frame);
        if(variant==0) {
            assert(result==-1 && !frame && dvbridge_fel_failed(f));
            assert(submissions==sent); /* Do not send ambiguous pixels at all. */
        } else {
            /* Healthy asymmetric IDR with a non-reordered BL, and a shared
             * key with reordered BL, retain their exact existing admission. */
            assert(result==1 && frame->pts==3100 && !dvbridge_fel_failed(f));
            av_frame_free(&frame);
        }
        dvbridge_fel_destroy(f);
    }
    present_seek_preroll_is_not_missing(device);
    av_buffer_unref(&device);
    av_packet_free(&p);
    puts("PASS: real EL split, immutable input, bounded queue, exact PTS, reset, EOF and errors");
}
