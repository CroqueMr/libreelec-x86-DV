/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DVBRIDGE_FEL_SEEK_H
#define DVBRIDGE_FEL_SEEK_H
#include <libavformat/avformat.h>
#include <libavcodec/bsf.h>
#include <libavcodec/avcodec.h>
#include <libavutil/time.h>
#include <limits.h>
#include <stdbool.h>

/* Header-only bounded random-access probe. The caller must perform its final
 * av_seek_frame after this probe, including on failure. No pixels are decoded.
 * Target and result use the selected video stream's time base. */
static int64_t dvbridge_fel_seek_point_at(AVFormatContext *format, int video, int64_t target,
                                        int64_t *position, const AVCodecParameters *original_base)
{
    if (position) *position = -1;
    AVStream *stream = format->streams[video];
    int enhancement = -1;
    for (unsigned i = 0; i < format->nb_stream_groups; ++i) {
        const AVStreamGroup *group = format->stream_groups[i];
        if (group->type != AV_STREAM_GROUP_PARAMS_DOLBY_VISION || group->nb_streams != 2 ||
            !group->params.layered_video || group->params.layered_video->el_index > 1)
            continue;
        unsigned el = group->params.layered_video->el_index;
        if (group->streams[1-el] == stream &&
            group->streams[el]->codecpar->codec_id == AV_CODEC_ID_HEVC)
            enhancement = group->streams[el]->index;
    }
    const int windows[] = {0, 2, 8, 32, 128};
    int64_t deadline = av_gettime_relative() + 3000000;
    size_t bytes = 0;
    int64_t found = AV_NOPTS_VALUE;
    int64_t found_position = -1;
    const AVRational seconds = {1,1};
    for (unsigned attempt = 0; attempt < sizeof(windows)/sizeof(*windows); ++attempt) {
        int64_t start = target - av_rescale_q(windows[attempt], seconds, stream->time_base);
        if (stream->start_time != AV_NOPTS_VALUE && start < stream->start_time)
            start = stream->start_time;
        if (av_seek_frame(format, video, start, AVSEEK_FLAG_BACKWARD) < 0)
            break;
        AVBSFContext *split = NULL, *base = NULL;
        AVCodecParserContext *bp = av_parser_init(AV_CODEC_ID_HEVC);
        AVCodecParserContext *ep = av_parser_init(AV_CODEC_ID_HEVC);
        AVCodecContext *bc = avcodec_alloc_context3(NULL), *ec = avcodec_alloc_context3(NULL);
        AVPacket *packet = av_packet_alloc(), *el = av_packet_alloc();
        int64_t base_key = AV_NOPTS_VALUE, el_key = AV_NOPTS_VALUE;
        int64_t base_position = -1, el_position = -1;
        unsigned passed = 0;
        if (!bp || !ep || !bc || !ec || !packet || !el ||
            av_bsf_list_parse_str(enhancement < 0 ? "dovi_split=mode=el" : "hevc_mp4toannexb", &split) < 0 ||
            avcodec_parameters_copy(split->par_in, enhancement < 0 ? stream->codecpar :
                format->streams[enhancement]->codecpar) < 0)
            goto cleanup;
        split->time_base_in = enhancement < 0 ? stream->time_base : format->streams[enhancement]->time_base;
        if (av_bsf_init(split) < 0 ||
            avcodec_parameters_to_context(ec, split->par_out) < 0)
            goto cleanup;
        if (enhancement >= 0) {
            if (av_bsf_list_parse_str("hevc_mp4toannexb", &base) < 0 ||
                avcodec_parameters_copy(base->par_in, original_base ? original_base : stream->codecpar) < 0)
                goto cleanup;
            base->time_base_in = stream->time_base;
            if (av_bsf_init(base) < 0) goto cleanup;
        }
        if (avcodec_parameters_to_context(bc, base ? base->par_out : stream->codecpar) < 0)
            goto cleanup;
        bp->flags = ep->flags = PARSER_FLAG_COMPLETE_FRAMES;
        for (unsigned count = 0; count < 12000 && bytes < 256u*1024u*1024u &&
             av_gettime_relative() < deadline; ++count) {
            if (av_read_frame(format, packet) < 0)
                break;
            bytes += packet->size > 0 ? packet->size : 0;
            if (enhancement >= 0) {
                bool is_el = packet->stream_index == enhancement;
                if (packet->stream_index != video && !is_el) { av_packet_unref(packet); continue; }
                AVBSFContext *filter = is_el ? split : base;
                AVCodecParserContext *parser = is_el ? ep : bp;
                AVCodecContext *codec = is_el ? ec : bc;
                if (av_bsf_send_packet(filter, packet) < 0) break;
                while (av_bsf_receive_packet(filter, el) >= 0) {
                    int64_t pts = av_rescale_q(el->pts, filter->time_base_out, stream->time_base);
                    uint8_t *out; int size;
                    if (el->pts != AV_NOPTS_VALUE && pts > target) passed |= is_el ? 2 : 1;
                    if (el->pts != AV_NOPTS_VALUE && pts <= target &&
                        av_parser_parse2(parser,codec,&out,&size,el->data,el->size,
                            el->pts,el->dts,el->pos) == el->size && size > 0 && parser->key_frame == 1) {
                        if (is_el) { el_key = pts; el_position = el->pos; }
                        else { base_key = pts; base_position = el->pos; }
                        if (base_key != AV_NOPTS_VALUE && base_key == el_key) {
                            found = base_key;
                            found_position = base_position >= 0 && el_position >= 0 ?
                                (base_position < el_position ? base_position : el_position) : -1;
                        }
                    }
                    av_packet_unref(el);
                }
                if (passed == 3) break;
                continue;
            }
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
        avcodec_free_context(&bc); avcodec_free_context(&ec); av_bsf_free(&split); av_bsf_free(&base);
        if (found != AV_NOPTS_VALUE || av_gettime_relative() >= deadline || bytes >= 256u*1024u*1024u)
            break;
    }
    if (position) *position = found_position;
    return found;
}
static int64_t dvbridge_fel_seek_point(AVFormatContext *format, int video, int64_t target)
{ return dvbridge_fel_seek_point_at(format, video, target, NULL, NULL); }
#endif
