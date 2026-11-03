/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Split and hardware-decode the enhancement layer; pair surfaces by exact presentation time. */
#include "dvbridge_fel.h"
#include <libavcodec/bsf.h>
#include <libavutil/hwcontext.h>
#include <libavutil/hwcontext_vaapi.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

#define QUEUE_MAX 32
#define PACKET_BYTES_MAX (64u * 1024u * 1024u)
#define MAP_MAX (QUEUE_MAX * 2)

/* Independently coded layers can have different decode
 * order and IDR boundaries. Use FFmpeg's HEVC parser rather than assigning
 * the BL packet timestamp blindly to the encapsulated EL access unit. */
struct picture_order {
    AVCodecParserContext *parser;
    AVCodecContext *context;
    int64_t offset, maximum;
    bool seen;
};

static bool picture_identity(struct picture_order *order, const AVPacket *packet, int64_t *identity)
{
    uint8_t *output;
    int output_size;
    order->parser->output_picture_number = INT_MIN;
    int used = av_parser_parse2(order->parser, order->context, &output, &output_size,
                               packet->data, packet->size, packet->pts, packet->dts, packet->pos);
    int poc = order->parser->output_picture_number;
    if (used != packet->size || output_size <= 0 || poc == INT_MIN)
        return false;
    if (order->seen && poc == 0 && order->parser->key_frame == 1) {
        if (order->maximum == INT64_MAX)
            return false;
        order->offset = order->maximum + 1;
    }
    if (poc > 0 && order->offset > INT64_MAX - poc)
        return false;
    *identity = order->offset + poc;
    if (!order->seen || *identity > order->maximum)
        order->maximum = *identity;
    order->seen = true;
    return true;
}

struct dvbridge_fel {
    AVBSFContext *split;
    AVCodecContext *decoder;
    AVPacket *packets[QUEUE_MAX];
    AVFrame *frames[QUEUE_MAX];
    unsigned num_packets, num_frames;
    size_t packet_bytes;
    bool opened, failed, draining, sent_eof, eof, recovering, harvesting;
    struct picture_order base_order, enhancement_order;
    int64_t packet_order[QUEUE_MAX];
    bool packet_key[QUEUE_MAX];
    struct { int64_t order, pts; bool key; } times[MAP_MAX];
    unsigned num_times;
    bool synchronizing;
    int64_t anchor_pts;
    unsigned preroll_packets;
    int64_t output_order;
};

static enum AVPixelFormat hardware_format(AVCodecContext *ctx, const enum AVPixelFormat *formats)
{
    bool found = false;
    for (; *formats != AV_PIX_FMT_NONE; ++formats)
        found |= *formats == AV_PIX_FMT_VAAPI;
    if (!found || !ctx->hw_device_ctx)
        return AV_PIX_FMT_NONE;
    AVBufferRef *frames = NULL;
    if (avcodec_get_hw_frames_parameters(ctx, ctx->hw_device_ctx, AV_PIX_FMT_VAAPI, &frames) < 0)
        return AV_PIX_FMT_NONE;
    AVHWFramesContext *hw = (void *)frames->data;
    /* Zero selects FFmpeg's dynamic VAAPI pool; only extend a fixed pool. */
    if (hw->initial_pool_size)
        hw->initial_pool_size += QUEUE_MAX + 4;
    if (av_hwframe_ctx_init(frames) < 0) {
        av_buffer_unref(&frames);
        return AV_PIX_FMT_NONE;
    }
    av_buffer_unref(&ctx->hw_frames_ctx);
    ctx->hw_frames_ctx = frames;
    return AV_PIX_FMT_VAAPI;
}

static void clear_queues(struct dvbridge_fel *f)
{
    for (unsigned i = 0; i < f->num_packets; ++i)
        av_packet_free(&f->packets[i]);
    for (unsigned i = 0; i < f->num_frames; ++i)
        av_frame_free(&f->frames[i]);
    f->num_packets = f->num_frames = 0;
    f->packet_bytes = 0;
    f->failed = f->draining = f->sent_eof = f->eof = f->recovering = f->harvesting = false;
    f->num_times = 0;
    f->output_order = AV_NOPTS_VALUE;
}

void dvbridge_fel_reset(struct dvbridge_fel *f)
{
    if (!f)
        return;
    clear_queues(f);
    f->synchronizing = true;
    f->anchor_pts = AV_NOPTS_VALUE;
    f->preroll_packets = 0;
    struct picture_order *orders[] = {&f->base_order, &f->enhancement_order};
    for (unsigned i = 0; i < 2; ++i) {
        struct picture_order *order = orders[i];
        av_parser_close(order->parser);
        order->parser = av_parser_init(AV_CODEC_ID_HEVC);
        if (order->parser)
            order->parser->flags = PARSER_FLAG_COMPLETE_FRAMES;
        else
            f->failed = true;
        order->offset = order->maximum = 0;
        order->seen = false;
    }
    if (f->split)
        av_bsf_flush(f->split);
    if (f->opened)
        avcodec_flush_buffers(f->decoder);
}

void dvbridge_fel_destroy(struct dvbridge_fel *f)
{
    if (!f)
        return;
    clear_queues(f);
    av_parser_close(f->base_order.parser);
    av_parser_close(f->enhancement_order.parser);
    avcodec_free_context(&f->base_order.context);
    avcodec_free_context(&f->enhancement_order.context);
    avcodec_free_context(&f->decoder);
    av_bsf_free(&f->split);
    free(f);
}

struct dvbridge_fel *dvbridge_fel_create(const AVCodecParameters *p, AVRational time_base)
{
    if (!p || p->codec_id != AV_CODEC_ID_HEVC || time_base.num <= 0 || time_base.den <= 0)
        return NULL;
    const AVCodec *codec = avcodec_find_decoder(AV_CODEC_ID_HEVC);
    if (!codec)
        return NULL;
    struct dvbridge_fel *f = calloc(1, sizeof(*f));
    if (!f)
        return NULL;
    f->synchronizing = true;
    f->anchor_pts = AV_NOPTS_VALUE;
    f->output_order = AV_NOPTS_VALUE;
    if (av_bsf_list_parse_str("dovi_split=mode=el", &f->split) < 0 ||
        avcodec_parameters_copy(f->split->par_in, p) < 0)
        goto fail;
    f->split->time_base_in = time_base;
    if (av_bsf_init(f->split) < 0)
        goto fail;
    f->decoder = avcodec_alloc_context3(codec);
    if (!f->decoder || avcodec_parameters_to_context(f->decoder, f->split->par_out) < 0)
        goto fail;
    f->decoder->pkt_timebase = time_base;
    f->decoder->get_format = hardware_format;
    f->decoder->thread_count = 1;
    f->decoder->err_recognition |= AV_EF_EXPLODE;
    struct picture_order *orders[] = {&f->base_order, &f->enhancement_order};
    const AVCodecParameters *parameters[] = {p, f->split->par_out};
    for (unsigned i = 0; i < 2; ++i) {
        orders[i]->parser = av_parser_init(AV_CODEC_ID_HEVC);
        orders[i]->context = avcodec_alloc_context3(NULL);
        if (!orders[i]->parser || !orders[i]->context ||
            avcodec_parameters_to_context(orders[i]->context, parameters[i]) < 0)
            goto fail;
        orders[i]->parser->flags = PARSER_FLAG_COMPLETE_FRAMES;
    }
    return f;
fail:
    dvbridge_fel_destroy(f);
    return NULL;
}

/* Continuous recovery preserves parser history and ready exact pairs. */
static void recover(struct dvbridge_fel *f)
{
    if (!f->recovering)
        av_log(f->decoder, AV_LOG_WARNING,
               "FEL decode: damaged enhancement data; waiting for a shared random-access picture\n");
    f->recovering = true;
    f->anchor_pts = AV_NOPTS_VALUE;
    f->harvesting = true;
    f->sent_eof = false;
    f->eof = false;
}

static bool receive_frames(struct dvbridge_fel *f)
{
    while (f->num_frames < QUEUE_MAX) {
        AVFrame *frame = av_frame_alloc();
        if (!frame)
            return false;
        int result = avcodec_receive_frame(f->decoder, frame);
        if (result < 0) {
            av_frame_free(&frame);
            if (result == AVERROR_INVALIDDATA && !f->harvesting) {
                recover(f);
                return !f->failed;
            }
            if (result == AVERROR_EOF)
                f->eof = true;
            return result == AVERROR(EAGAIN) || result == AVERROR_EOF;
        }
        if (frame->flags & AV_FRAME_FLAG_CORRUPT) {
            av_frame_free(&frame);
            if (f->harvesting)
                continue;
            recover(f);
            return !f->failed;
        }
        /* The private decoder timestamp is the stable HEVC identity. Restore
         * the exact original BL time only after native POC reordering. */
        if (frame->pts == AV_NOPTS_VALUE)
            frame->pts = frame->best_effort_timestamp;
        if (frame->format != AV_PIX_FMT_VAAPI || frame->pts == AV_NOPTS_VALUE) {
            av_frame_free(&frame);
            return false;
        }
        unsigned match = 0;
        while (match < f->num_times && f->times[match].order != frame->pts)
            ++match;
        if (match == f->num_times ||
            (f->output_order != AV_NOPTS_VALUE && frame->pts <= f->output_order)) {
            av_frame_free(&frame);
            return false;
        }
        f->output_order = frame->pts;
        frame->pts = f->times[match].pts;
        frame->best_effort_timestamp = frame->pts;
        --f->num_times;
        memmove(f->times + match, f->times + match + 1,
                (f->num_times - match) * sizeof(*f->times));
        for (unsigned i = 0; i < f->num_frames; ++i) {
            if (f->frames[i]->pts == frame->pts) {
                av_frame_free(&frame);
                return false;
            }
        }
        f->frames[f->num_frames++] = frame;
    }
    return true;
}

/* Preserve native DPB output through EAGAIN and a full ready array. Recovery
 * flushes only after decoder EOF, never merely after the queue has filled. */
static bool harvest(struct dvbridge_fel *f)
{
    while (f->harvesting && f->num_frames < QUEUE_MAX) {
        if (!f->sent_eof) {
            int result = avcodec_send_packet(f->decoder, NULL);
            if (result == AVERROR(EAGAIN)) {
                unsigned before = f->num_frames;
                if (!receive_frames(f) || f->num_frames == before)
                    return false; /* Native send/receive must make progress. */
                continue;
            }
            if (result < 0 && result != AVERROR_EOF)
                return false;
            f->sent_eof = true;
        }
        if (!receive_frames(f))
            return false;
        if (f->eof) {
            avcodec_flush_buffers(f->decoder);
            f->harvesting = f->sent_eof = f->eof = false;
        } else if (f->num_frames < QUEUE_MAX)
            return false; /* Accepted drain must end in EOF, not EAGAIN. */
    }
    return true;
}

static bool pump(struct dvbridge_fel *f)
{
    if (f->failed)
        return false;
    if (!f->opened)
        return true;
    if (!receive_frames(f))
        goto fail;
    if (!harvest(f))
        goto fail;
    if (f->harvesting)
        return true;
    while (f->num_packets && f->num_frames < QUEUE_MAX) {
        AVPacket *packet = f->packets[0];
        unsigned match = 0;
        while (match < f->num_times && f->times[match].order != f->packet_order[0])
            ++match;
        /* With reordered BL, an EL epoch starting on a nonkey BL is ambiguous:
         * a lost terminal EL AU can make its max+1 counter one picture early.
         * Non-reordered independently coded IDRs keep their existing admission.
         * Never decode an ambiguous IDR into a previous BL's exact-time slot. */
        if (f->packet_key[0] && match < f->num_times && !f->times[match].key &&
            f->base_order.context->has_b_frames > 0) {
            av_log(f->decoder, AV_LOG_ERROR,
                   "FEL decode: ambiguous enhancement epoch at picture %lld; refusing an unproven pair\n",
                   (long long)f->packet_order[0]);
            goto fail;
        }
        if (f->recovering) {
            if (f->packet_key[0] && match == f->num_times && !f->draining)
                break; /* Independent EL IDR can precede the matching BL key. */
            if (!f->packet_key[0] || match == f->num_times || !f->times[match].key) {
                if (match < f->num_times) {
                    --f->num_times;
                    memmove(f->times + match, f->times + match + 1,
                            (f->num_times - match) * sizeof(*f->times));
                }
                f->packet_bytes -= packet->size;
                av_packet_free(&packet);
                --f->num_packets;
                memmove(f->packets, f->packets + 1, f->num_packets * sizeof(*f->packets));
                memmove(f->packet_order, f->packet_order + 1,
                        f->num_packets * sizeof(*f->packet_order));
                memmove(f->packet_key, f->packet_key + 1,
                        f->num_packets * sizeof(*f->packet_key));
                continue;
            }
            f->anchor_pts = f->times[match].pts;
            int64_t anchor_order = f->times[match].order;
            for (unsigned i = 0; i < f->num_times;) {
                if (f->times[i].order >= anchor_order) {
                    ++i;
                    continue;
                }
                --f->num_times;
                memmove(f->times + i, f->times + i + 1,
                        (f->num_times - i) * sizeof(*f->times));
            }
            match = 0;
            while (f->times[match].order != anchor_order)
                ++match;
            f->recovering = false;
            av_log(f->decoder, AV_LOG_INFO,
                   "FEL decode: resumed exact pairing at picture %lld, source PTS %lld\n",
                   (long long)anchor_order, (long long)f->anchor_pts);
        }
        if (match == f->num_times) {
            if (f->draining)
                goto fail;
            break; /* A reference EL picture can precede its corresponding BL. */
        }
        packet->pts = f->packet_order[0];
        packet->dts = AV_NOPTS_VALUE;
        int result = avcodec_send_packet(f->decoder, packet);
        if (result == AVERROR(EAGAIN))
            break;
        if (result < 0 && result != AVERROR_INVALIDDATA)
            goto fail;
        f->packet_bytes -= packet->size;
        av_packet_free(&packet);
        --f->num_packets;
        memmove(f->packets, f->packets + 1, f->num_packets * sizeof(*f->packets));
        memmove(f->packet_order, f->packet_order + 1, f->num_packets * sizeof(*f->packet_order));
        memmove(f->packet_key, f->packet_key + 1, f->num_packets * sizeof(*f->packet_key));
        if (result == AVERROR_INVALIDDATA) {
            recover(f);
            if (!harvest(f))
                goto fail;
            if (f->harvesting)
                return true;
            continue;
        }
        if (!receive_frames(f))
            goto fail;
        if (!harvest(f))
            goto fail;
        if (f->harvesting)
            return true;
    }
    if (f->draining && !f->num_packets && !f->sent_eof && f->num_frames < QUEUE_MAX) {
        int result = avcodec_send_packet(f->decoder, NULL);
        if (result != AVERROR(EAGAIN)) {
            if (result < 0 && result != AVERROR_EOF)
                goto fail;
            f->sent_eof = true;
        }
        if (!receive_frames(f))
            goto fail;
    }
    return true;
fail:
    f->failed = true;
    return false;
}

bool dvbridge_fel_device(struct dvbridge_fel *f, AVBufferRef *device)
{
    if (!f || f->failed || !device || ((AVHWDeviceContext *)device->data)->type != AV_HWDEVICE_TYPE_VAAPI)
        return false;
    if (f->opened) {
        const AVHWDeviceContext *bound = (void *)f->decoder->hw_device_ctx->data;
        const AVHWDeviceContext *current = (void *)device->data;
        const AVVAAPIDeviceContext *a = bound->hwctx, *b = current->hwctx;
        /* BL decoder renewal can replace the wrapper without changing the VA display. */
        return a && b && a->display && a->display == b->display;
    }
    f->decoder->hw_device_ctx = av_buffer_ref(device);
    if (!f->decoder->hw_device_ctx || avcodec_open2(f->decoder, f->decoder->codec, NULL) < 0) {
        f->failed = true;
        return false;
    }
    f->opened = true;
    return true;
}


bool dvbridge_fel_submit(struct dvbridge_fel *f, const AVPacket *packet)
{
    if (!f || !packet || f->failed || f->draining || packet->size <= 0 ||
        packet->pts == AV_NOPTS_VALUE)
        return false;
    int64_t base_identity;
    if (f->num_times == MAP_MAX || !picture_identity(&f->base_order, packet, &base_identity))
        goto fail;
    for (unsigned i = 0; i < f->num_times; ++i)
        if (f->times[i].order == base_identity)
            goto fail;
    f->times[f->num_times].order = base_identity;
    f->times[f->num_times].key = f->base_order.parser->key_frame == 1;
    f->times[f->num_times++].pts = packet->pts;
    AVPacket *copy = av_packet_clone(packet);
    if (!copy)
        goto fail;
    int result = av_bsf_send_packet(f->split, copy);
    av_packet_free(&copy);
    if (result < 0)
        goto fail;
    while (true) {
        copy = av_packet_alloc();
        if (!copy)
            goto fail;
        result = av_bsf_receive_packet(f->split, copy);
        if (result < 0) {
            av_packet_free(&copy);
            if (result == AVERROR(EAGAIN))
                return true; /* Submit EL when a decoded BL requests its matching picture. */
            goto fail;
        }
        if (f->num_packets == QUEUE_MAX || copy->size <= 0 ||
            (size_t)copy->size > PACKET_BYTES_MAX - f->packet_bytes ||
            !picture_identity(&f->enhancement_order, copy, &f->packet_order[f->num_packets])) {
            av_packet_free(&copy);
            goto fail;
        }
        if (f->synchronizing) {
            const AVCodecParserContext *bp = f->base_order.parser;
            const AVCodecParserContext *ep = f->enhancement_order.parser;
            bool common_key = bp->key_frame == 1 && ep->key_frame == 1 &&
                              bp->output_picture_number == ep->output_picture_number;
            /* A non-reordered BL gives the IDR packet an unambiguous display
             * time. Never use this shortcut for a BL with reordered pictures. */
            bool el_idr = ep->key_frame == 1 && ep->output_picture_number == 0 &&
                          f->base_order.context->has_b_frames == 0;
            if (!common_key && !el_idr) {
                av_packet_free(&copy);
                f->num_times = 0;
                if (++f->preroll_packets > 1024)
                    goto fail;
                continue;
            }
            f->enhancement_order.offset = base_identity - ep->output_picture_number;
            f->enhancement_order.maximum = base_identity;
            f->packet_order[f->num_packets] = base_identity;
            f->anchor_pts = packet->pts;
            f->synchronizing = false;
        }
        f->packet_key[f->num_packets] = f->enhancement_order.parser->key_frame == 1;
        f->packet_bytes += copy->size;
        f->packets[f->num_packets++] = copy;
    }
fail:
    f->failed = true;
    return false;
}

bool dvbridge_fel_drain(struct dvbridge_fel *f)
{
    if (!f)
        return false;
    if (f->synchronizing) {
        f->failed = true;
        return false; /* EOF cannot supply the missing random-access picture. */
    }
    f->draining = true;
    return pump(f);
}

static int take_ready(struct dvbridge_fel *f, int64_t pts, AVFrame **frame)
{
    for (unsigned i = 0; i < f->num_frames;) {
        AVFrame *candidate = f->frames[i];
        if (candidate->pts > pts) {
            ++i;
            continue;
        }
        --f->num_frames;
        memmove(f->frames + i, f->frames + i + 1,
                (f->num_frames - i) * sizeof(*f->frames));
        if (candidate->pts == pts) {
            *frame = candidate;
            return 1;
        }
        av_frame_free(&candidate);
    }
    return 0;
}

int dvbridge_fel_take(struct dvbridge_fel *f, int64_t pts, AVFrame **frame)
{
    if (!f || !frame || *frame || pts == AV_NOPTS_VALUE || f->failed)
        return -1;
    /* Return available work before submitting future enhancement pictures. */
    if (take_ready(f, pts, frame))
        return 1;
    if (f->synchronizing || (f->anchor_pts != AV_NOPTS_VALUE && pts < f->anchor_pts))
        return 2; /* Preroll before a recoverable EL picture, not a substitute. */
    if (!pump(f))
        return -1;
    if (take_ready(f, pts, frame))
        return 1;
    if ((f->recovering && !f->harvesting) ||
        (f->anchor_pts != AV_NOPTS_VALUE && pts < f->anchor_pts)) {
        /* Retain possible independent common-key anchors, not discarded BL
         * nonkeys whose EL cannot be used during this recovery interval. */
        for (unsigned i = 0; i < f->num_times; ++i) {
            if (f->times[i].pts == pts && !f->times[i].key) {
                --f->num_times;
                memmove(f->times + i, f->times + i + 1,
                        (f->num_times - i) * sizeof(*f->times));
                break;
            }
        }
        return 2;
    }
    /* Native HEVC outputs in POC order. An absent identity behind that frontier
     * cannot become a later valid picture; a future *packet* proves nothing. */
    for (unsigned i = 0; i < f->num_times; ++i) {
        if (f->times[i].pts == pts && f->times[i].order < f->output_order) {
            av_log(f->decoder, AV_LOG_WARNING,
                   "FEL decode: absent enhancement picture %lld at source PTS %lld; no replacement\n",
                   (long long)f->times[i].order, (long long)pts);
            --f->num_times;
            memmove(f->times + i, f->times + i + 1,
                    (f->num_times - i) * sizeof(*f->times));
            return 2;
        }
    }
    /* Future packets alone cannot prove a missing picture or justify substitution. */
    return f->eof || f->num_frames == QUEUE_MAX ? -1 : 0;
}

bool dvbridge_fel_failed(const struct dvbridge_fel *f)
{
    return !f || f->failed;
}

bool dvbridge_fel_exhausted(const struct dvbridge_fel *f)
{
    return f && !f->failed && f->eof && !f->num_frames && !f->num_packets;
}
