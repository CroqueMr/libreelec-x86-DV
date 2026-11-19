#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <libavcodec/avcodec.h>
#include <libavutil/file.h>
#include <libavutil/mem.h>
#include <libavutil/pixdesc.h>

static int callbacks, frames;

static enum AVPixelFormat select_format(AVCodecContext *ctx, const enum AVPixelFormat *formats)
{
    (void)ctx;
    callbacks++;
    for (; *formats != AV_PIX_FMT_NONE; formats++) {
        if (!(av_pix_fmt_desc_get(*formats)->flags & AV_PIX_FMT_FLAG_HWACCEL))
            return *formats;
    }
    return AV_PIX_FMT_NONE;
}

static int receive(AVCodecContext *codec, AVFrame *frame)
{
    int ret;
    while ((ret = avcodec_receive_frame(codec, frame)) == 0) {
        frames++;
        av_frame_unref(frame);
    }
    return ret;
}

int main(int argc, char **argv)
{
    const AVCodec *hevc = avcodec_find_decoder(AV_CODEC_ID_HEVC);
    AVCodecContext *codec = avcodec_alloc_context3(hevc);
    AVPacket *packet = av_packet_alloc();
    AVFrame *frame = av_frame_alloc();

    if (argc < 3 || !hevc || !codec || !packet || !frame)
        return 1;
    codec->thread_count = atoi(argv[1]);
    codec->get_format = select_format;
    if (avcodec_open2(codec, hevc, NULL) < 0)
        return 1;

    for (int i = 2; i < argc; i++) {
        uint8_t *data;
        size_t size;
        if (av_file_map(argv[i], &data, &size, 0, NULL) < 0 || size > INT_MAX ||
            av_new_packet(packet, (int)size) < 0)
            return 1;
        memcpy(packet->data, data, size);
        av_file_unmap(data, size);
        if (avcodec_send_packet(codec, packet) < 0 || receive(codec, frame) != AVERROR(EAGAIN))
            return 1;
        av_packet_unref(packet);
    }
    if (avcodec_send_packet(codec, NULL) < 0 || receive(codec, frame) != AVERROR_EOF)
        return 1;
    printf("%d callbacks, %d frames\n", callbacks, frames);
    av_frame_free(&frame);
    av_packet_free(&packet);
    avcodec_free_context(&codec);
    return 0;
}
