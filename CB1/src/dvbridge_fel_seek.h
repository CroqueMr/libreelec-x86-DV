/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DVBRIDGE_FEL_SEEK_H
#define DVBRIDGE_FEL_SEEK_H
#include <libavformat/avformat.h>
#include <libavcodec/bsf.h>
#include <libavutil/time.h>
#include <limits.h>
#include <stdbool.h>

/* Header-only bounded random-access probe. The caller must perform its final
 * av_seek_frame after this probe, including on failure. No pixels are decoded.
 * Target and result use the selected video stream's time base. */
static int64_t dvbridge_fel_seek_point(AVFormatContext *format, int video, int64_t target)
{
    AVStream *stream = format->streams[video];
    const int windows[] = {0, 2, 8, 32, 128};
    int64_t deadline = av_gettime_relative() + 3000000;
    size_t bytes = 0;
    int64_t found = AV_NOPTS_VALUE;
    const AVRational seconds = {1,1};
    for (unsigned attempt = 0; attempt < sizeof(windows)/sizeof(*windows); ++attempt) {
        int64_t start = target - av_rescale_q(windows[attempt], seconds, stream->time_base);
        if (stream->start_time != AV_NOPTS_VALUE && start < stream->start_time)
            start = stream->start_time;
        if (av_seek_frame(format, video, start, AVSEEK_FLAG_BACKWARD) < 0)
            break;
        AVBSFContext *split = NULL;
        AVCodecParserContext *bp = av_parser_init(AV_CODEC_ID_HEVC);
        AVCodecParserContext *ep = av_parser_init(AV_CODEC_ID_HEVC);
        AVCodecContext *bc = avcodec_alloc_context3(NULL), *ec = avcodec_alloc_context3(NULL);
        AVPacket *packet = av_packet_alloc(), *el = av_packet_alloc();
        int64_t base_key = AV_NOPTS_VALUE;
        if (!bp || !ep || !bc || !ec || !packet || !el ||
            av_bsf_list_parse_str("dovi_split=mode=el", &split) < 0 ||
            avcodec_parameters_copy(split->par_in, stream->codecpar) < 0)
            goto cleanup;
        split->time_base_in = stream->time_base;
        if (av_bsf_init(split) < 0 ||
            avcodec_parameters_to_context(bc, stream->codecpar) < 0 ||
            avcodec_parameters_to_context(ec, split->par_out) < 0)
            goto cleanup;
        bp->flags = ep->flags = PARSER_FLAG_COMPLETE_FRAMES;
        for (unsigned count = 0; count < 12000 && bytes < 256u*1024u*1024u &&
             av_gettime_relative() < deadline; ++count) {
            if (av_read_frame(format, packet) < 0)
                break;
            bytes += packet->size > 0 ? packet->size : 0;
            if (packet->stream_index != video) { av_packet_unref(packet); continue; }
            int64_t pts = packet->pts;
            if (pts == AV_NOPTS_VALUE) { av_packet_unref(packet); break; }
            if (pts > target) { av_packet_unref(packet); break; }
            uint8_t *out; int size;
            bp->output_picture_number = INT_MIN;
            if (av_parser_parse2(bp,bc,&out,&size,packet->data,packet->size,
                                 pts,packet->dts,packet->pos) != packet->size ||
                !size || bp->output_picture_number == INT_MIN)
                break;
            if (bp->key_frame == 1) base_key = pts;
            if (av_bsf_send_packet(split, packet) < 0) break;
            while (av_bsf_receive_packet(split, el) >= 0) {
                ep->output_picture_number = INT_MIN;
                int used = av_parser_parse2(ep,ec,&out,&size,el->data,el->size,pts,el->dts,el->pos);
                bool common = bp->key_frame == 1 && ep->key_frame == 1 &&
                              bp->output_picture_number == ep->output_picture_number;
                bool idr = stream->codecpar->video_delay == 0 && ep->key_frame == 1 &&
                           ep->output_picture_number == 0;
                if (used == el->size && size > 0 && base_key != AV_NOPTS_VALUE && (common || idr))
                    found = base_key;
                av_packet_unref(el);
            }
            av_packet_unref(packet);
            if (windows[attempt] == 0 || pts == target) break;
        }
cleanup:
        av_packet_free(&packet); av_packet_free(&el);
        av_parser_close(bp); av_parser_close(ep);
        avcodec_free_context(&bc); avcodec_free_context(&ec); av_bsf_free(&split);
        if (found != AV_NOPTS_VALUE || av_gettime_relative() >= deadline || bytes >= 256u*1024u*1024u)
            break;
    }
    return found;
}
#endif
