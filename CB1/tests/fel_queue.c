/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_fel.h"
#include <libavutil/hwcontext.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "synthetic_idr.h"

/* Real FFmpeg splitter and ownership; deterministic decoder replaces VAAPI ioctls. */
static int64_t ready[64];
static unsigned count;
static bool end, bad_pts, send_error;
int __wrap_avcodec_open2(AVCodecContext *ctx, const AVCodec *codec, AVDictionary **options)
{
    (void)codec; (void)options;
    assert(ctx->hw_device_ctx && ctx->get_format && ctx->thread_count == 1);
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
    if (send_error)
        return AVERROR_INVALIDDATA;
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
    if (!count)
        return end ? AVERROR_EOF : AVERROR(EAGAIN);
    frame->format = AV_PIX_FMT_VAAPI;
    frame->width = 1920;
    frame->height = 1080;
    frame->best_effort_timestamp = bad_pts ? AV_NOPTS_VALUE : ready[0];
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
    ((AVHWDeviceContext *)device->data)->type = AV_HWDEVICE_TYPE_VAAPI;
    assert(dvbridge_fel_device(f, device));
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
    dvbridge_fel_reset(f);
    assert(frame->pts == 3 * 41708 && frame->buf[0]); /* downstream ref survives seek */
    av_frame_free(&frame);
    p->pts = p->dts = 0;
    assert(dvbridge_fel_submit(f, p));
    assert(dvbridge_fel_take(f, 0, &frame) == 1);
    av_frame_free(&frame);
    assert(dvbridge_fel_drain(f));
    assert(dvbridge_fel_take(f, 1, &frame) == -1 && !frame);
    assert(!dvbridge_fel_submit(f, p));
    dvbridge_fel_reset(f);
    bad_pts = true;
    assert(!dvbridge_fel_submit(f, p) && dvbridge_fel_failed(f));
    bad_pts = false;
    dvbridge_fel_reset(f);
    send_error = true;
    assert(!dvbridge_fel_submit(f, p) && dvbridge_fel_failed(f));
    send_error = false;
    dvbridge_fel_reset(f);
    assert(!dvbridge_fel_failed(f));
    dvbridge_fel_destroy(f);
    av_buffer_unref(&device);
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
    dvbridge_fel_reset(f);
    assert(dvbridge_fel_submit(f, p));
    dvbridge_fel_destroy(f);
    av_packet_free(&p);
    puts("PASS: real EL split, immutable input, bounded queue, exact PTS, reset, EOF and errors");
}
