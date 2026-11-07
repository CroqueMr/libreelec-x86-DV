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

/* Splitter output is Annex-B; only identify the first VCL NAL header. The
 * native HEVC parser still validates the complete access unit below. */
static int vcl_type(const AVPacket *packet)
{
    for (int i=0;i+4<packet->size;++i)
        if (!packet->data[i] && !packet->data[i+1] && packet->data[i+2]==1) {
            int type=(packet->data[i+3]>>1)&63;
            if (type<32) return type;
        }
    return -1;
}

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
    bool opened, failed, draining, sent_eof, eof, recovering, harvesting, epoch_uncertain;
    struct picture_order base_order, enhancement_order;
    int64_t packet_order[QUEUE_MAX];
    bool packet_key[QUEUE_MAX];
    struct { int64_t order, pts; bool key, presentable; } times[MAP_MAX];
    unsigned num_times;
    bool synchronizing;
    int64_t anchor_pts;
    unsigned preroll_packets;
    int64_t output_order;
    uint64_t source_epoch;
    AVRational source_clock;
    bool source_timed;
    bool source_no_rasl;
    int64_t source_taken;
};

/* Keep exact discarded EL identities in the existing bounded map, including
 * an EL arriving before its BL. A decoder error without an identity is fatal. */
static bool discard_source(struct dvbridge_fel *f, int64_t source)
{
    if (source == AV_NOPTS_VALUE) return false;
    if (source <= f->source_taken) return true;
    unsigned i=0;
    while (i<f->num_times && f->times[i].order!=source) ++i;
    if (i==f->num_times) {
        if (i==MAP_MAX) return false;
        f->times[i].order=source;
        f->times[i].pts=AV_NOPTS_VALUE;
        f->times[i].key=false;
        ++f->num_times;
    }
    f->times[i].presentable=false;
    return true;
}

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
    f->epoch_uncertain = false;
    f->num_times = 0;
    f->output_order = AV_NOPTS_VALUE;
    f->source_epoch = 0;
    f->source_timed = false;
    f->source_no_rasl = false;
    f->source_taken = AV_NOPTS_VALUE;
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
    f->source_taken = AV_NOPTS_VALUE;
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
                if (f->source_timed) return false; // No exact identity to discard.
                recover(f);
                return !f->failed;
            }
            if (result == AVERROR_EOF)
                f->eof = true;
            return result == AVERROR(EAGAIN) || result == AVERROR_EOF;
        }
        if ((frame->flags & AV_FRAME_FLAG_CORRUPT) || (f->source_timed && frame->decode_error_flags)) {
            const bool identified = !f->source_timed || discard_source(f, frame->pts);
            av_frame_free(&frame);
            if (!identified) return false;
            if (f->harvesting)
                continue;
            recover(f);
            return !f->failed;
        }
        /* The private decoder timestamp is the stable HEVC identity. Restore
         * the exact original BL time only after native POC reordering. */
        if (!f->source_timed && frame->pts == AV_NOPTS_VALUE)
            frame->pts = frame->best_effort_timestamp;
        if (frame->format != AV_PIX_FMT_VAAPI || frame->pts == AV_NOPTS_VALUE) {
            av_frame_free(&frame);
            return false;
        }
        unsigned match = 0;
        if (!f->source_timed)
            while (match < f->num_times && f->times[match].order != frame->pts)
                ++match;
        if ((!f->source_timed && match == f->num_times) ||
            (f->output_order != AV_NOPTS_VALUE && frame->pts <= f->output_order)) {
            av_frame_free(&frame);
            return false;
        }
        f->output_order = frame->pts;
        if (!f->source_timed) {
            frame->pts = f->times[match].pts;
            frame->best_effort_timestamp = frame->pts;
            --f->num_times;
            memmove(f->times + match, f->times + match + 1,
                    (f->num_times - match) * sizeof(*f->times));
        }
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
        if (!f->source_timed && f->packet_key[0] && match < f->num_times && !f->times[match].key &&
            f->base_order.context->has_b_frames > 0) {
            av_log(f->decoder, AV_LOG_ERROR,
                   "FEL decode: ambiguous enhancement epoch at picture %lld; refusing an unproven pair\n",
                   (long long)f->packet_order[0]);
            goto fail;
        }
        const int type=f->source_timed ? vcl_type(packet) : -1;
        if (f->recovering || (f->source_timed && f->source_no_rasl && (type==8 || type==9))) {
            if (!f->source_timed && f->packet_key[0] && match == f->num_times && !f->draining)
                break; /* Independent EL IDR can precede the matching BL key. */
            if (!f->packet_key[0] || (!f->source_timed &&
                (match == f->num_times || !f->times[match].key))) {
                if (f->source_timed) {
                    if (!discard_source(f, f->packet_order[0])) goto fail;
                } else if (match < f->num_times) {
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
            f->anchor_pts = f->source_timed ? f->packet_order[0] : f->times[match].pts;
            int64_t anchor_order = f->source_timed ? f->packet_order[0] : f->times[match].order;
            for (unsigned i = 0; i < f->num_times;) {
                if (f->source_timed || f->times[i].order >= anchor_order) {
                    ++i;
                    continue;
                }
                --f->num_times;
                memmove(f->times + i, f->times + i + 1,
                        (f->num_times - i) * sizeof(*f->times));
            }
            match = 0;
            while (!f->source_timed && f->times[match].order != anchor_order)
                ++match;
            f->recovering = false;
            if (f->source_timed) f->source_no_rasl=true;
            av_log(f->decoder, AV_LOG_INFO,
                   "FEL decode: resumed exact pairing at picture %lld, source PTS %lld\n",
                   (long long)anchor_order, (long long)f->anchor_pts);
        }
        if (!f->source_timed && match == f->num_times) {
            if (!f->draining)
                break; /* A reference EL picture can precede its corresponding BL. */
            /* Drain closes this input epoch (submit rejects further BL). A cut
             * may retain an EL-only suffix; no queued dependent BL may need it.
             * Internal holes still fail, and native EOF releases the valid DPB. */
            if (!f->base_order.seen) goto fail;
            for (unsigned i=0;i<f->num_packets;++i)
                if (f->packet_order[i] <= f->base_order.maximum) goto fail;
            av_log(f->decoder, AV_LOG_DEBUG,
                   "FEL decode: retiring %u terminal EL units beyond BL %lld\n",
                   f->num_packets, (long long)f->base_order.maximum);
            for (unsigned i=0;i<f->num_packets;++i) av_packet_free(&f->packets[i]);
            f->num_packets=0;
            f->packet_bytes=0;
            break;
        }
        packet->pts = f->packet_order[0];
        packet->dts = AV_NOPTS_VALUE;
        int result = avcodec_send_packet(f->decoder, packet);
        if (result == AVERROR(EAGAIN))
            break;
        if (result < 0 && result != AVERROR_INVALIDDATA)
            goto fail;
        if (result==0 && f->source_timed && type>=0 && type<16 && type!=6 && type!=7 &&
            type!=8 && type!=9)
            f->source_no_rasl=false;
        if (result == AVERROR_INVALIDDATA && f->source_timed &&
            !discard_source(f, f->packet_order[0]))
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


static bool submit(struct dvbridge_fel *f, const AVPacket *packet,
                   const struct dvbridge_fel_source *source)
{
    if (!f || !packet || f->failed || f->draining || packet->size <= 0 ||
        (packet->pts == AV_NOPTS_VALUE && (!source || source->base_pts != AV_NOPTS_VALUE)))
        return false;
    if (source) {
        if ((source->base_pts == AV_NOPTS_VALUE && source->enhancement_pts == AV_NOPTS_VALUE) ||
            source->time_base.num <= 0 ||
            source->time_base.den <= 0 || !source->epoch ||
            (!f->source_timed && f->base_order.seen) ||
            (source->base_pts != AV_NOPTS_VALUE && source->base_pts <= f->source_taken) ||
            (f->source_epoch && (source->epoch != f->source_epoch ||
                                av_cmp_q(source->time_base, f->source_clock))))
            goto fail;
        f->source_timed = true;
        f->source_epoch = source->epoch;
        f->source_clock = source->time_base;
        f->decoder->pkt_timebase = source->time_base;
    } else if (f->source_timed) goto fail;
    int64_t base_identity = source ? source->base_pts : 0;
    if (!source || source->base_pts != AV_NOPTS_VALUE) {
        if (!source && !picture_identity(&f->base_order, packet, &base_identity))
            goto fail;
        unsigned match=f->num_times;
        for (unsigned i=0;i<f->num_times;++i) {
            if (source && f->times[i].pts == packet->pts) goto fail;
            if (f->times[i].order != base_identity) continue;
            if (!source || f->times[i].pts != AV_NOPTS_VALUE) goto fail;
            match=i;
        }
        if (match==f->num_times) {
            if (f->num_times==MAP_MAX) goto fail;
            ++f->num_times;
            f->times[match].presentable=true;
        }
        f->times[match].order=base_identity;
        f->times[match].key=f->base_order.parser->key_frame==1;
        f->times[match].presentable &= !source || source->presentable;
        f->times[match].pts=packet->pts;
    }
    AVPacket *copy = av_packet_clone(packet);
    if (!copy)
        goto fail;
    int result = av_bsf_send_packet(f->split, copy);
    av_packet_free(&copy);
    if (result < 0)
        goto fail;
    bool received_enhancement = false;
    while (true) {
        copy = av_packet_alloc();
        if (!copy)
            goto fail;
        result = av_bsf_receive_packet(f->split, copy);
        if (result < 0) {
            av_packet_free(&copy);
            if (result == AVERROR(EAGAIN)) {
                if (source && !received_enhancement && source->enhancement_pts != AV_NOPTS_VALUE)
                    goto fail;
                if (!source && !received_enhancement)f->epoch_uncertain = true;
                return true; /* Submit EL when a decoded BL requests its matching picture. */
            }
            goto fail;
        }
        if (f->num_packets == QUEUE_MAX || copy->size <= 0 ||
            (size_t)copy->size > PACKET_BYTES_MAX - f->packet_bytes ||
            !picture_identity(&f->enhancement_order, copy, &f->packet_order[f->num_packets])) {
            av_packet_free(&copy);
            goto fail;
        }
        /* Present seek preroll is not a missing enhancement access unit. */
        if (source) {
            if (received_enhancement || source->enhancement_pts == AV_NOPTS_VALUE) {
                av_packet_free(&copy);
                goto fail;
            }
            received_enhancement = true;
            f->packet_order[f->num_packets] = source->enhancement_pts;
            const bool key = f->enhancement_order.parser->key_frame == 1;
            if (f->synchronizing) {
                if (!key) {
                    av_packet_free(&copy);
                    if (!discard_source(f, source->enhancement_pts)) goto fail;
                    if (++f->preroll_packets > 1024) goto fail;
                    continue;
                }
                f->anchor_pts = source->enhancement_pts;
                f->source_no_rasl = true;
                f->synchronizing = false;
            }
            f->packet_key[f->num_packets] = key;
            f->packet_bytes += copy->size;
            f->packets[f->num_packets++] = copy;
            continue;
        }
        received_enhancement = true;
        /* Reordered layers cannot corroborate an epoch with independent
         * max+1 counters. A common key AU proves the new offset even if an
         * entire enhancement GOP was absent. Never bind it to a stale BL key. */
        const AVCodecParserContext *bp = f->base_order.parser;
        const AVCodecParserContext *ep = f->enhancement_order.parser;
        bool common_key = bp->key_frame == 1 && ep->key_frame == 1 &&
                          bp->output_picture_number == ep->output_picture_number;
        bool el_idr = ep->key_frame == 1 && ep->output_picture_number == 0 &&
                      f->base_order.context->has_b_frames == 0;
        /* Complete AU input preserves the earlier independent-key counter
         * proof. A real missing EL AU invalidates it until a verified anchor. */
        if (ep->key_frame == 1 && f->epoch_uncertain && !common_key && !el_idr) {
            av_log(f->decoder, AV_LOG_WARNING,
                   "FEL decode: missing enhancement AU makes this key ambiguous; waiting for a shared key\n");
            av_packet_free(&copy);
            recover(f);
            continue;
        }
        if (common_key || el_idr) {
            if (f->packet_order[f->num_packets] != base_identity)
                av_log(f->decoder, AV_LOG_WARNING,
                       "FEL decode: verified key reanchors enhancement picture %lld to base %lld\n",
                       (long long)f->packet_order[f->num_packets], (long long)base_identity);
            f->enhancement_order.offset = base_identity - ep->output_picture_number;
            f->enhancement_order.maximum = base_identity;
            f->packet_order[f->num_packets] = base_identity;
            f->epoch_uncertain = false;
        }
        if (f->synchronizing) {
            /* A non-reordered BL gives the IDR packet an unambiguous display
             * time. Never use this shortcut for a BL with reordered pictures. */
            if (!common_key && !el_idr) {
                av_packet_free(&copy);
                f->num_times = 0;
                if (++f->preroll_packets > 1024)
                    goto fail;
                continue;
            }
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

bool dvbridge_fel_submit(struct dvbridge_fel *f, const AVPacket *packet)
{
    return submit(f, packet, NULL);
}

bool dvbridge_fel_submit_source(struct dvbridge_fel *f, const AVPacket *packet,
                               const struct dvbridge_fel_source *source)
{
    return source && submit(f, packet, source);
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

static int take_source(struct dvbridge_fel *f, int64_t pts, AVFrame **frame)
{
    unsigned match = 0;
    while (match < f->num_times && f->times[match].pts != pts) ++match;
    if (match == f->num_times) return -1;
    const int64_t source = f->times[match].order;
    const bool presentable = f->times[match].presentable;
    for (unsigned i = 0; i < f->num_times;) {
        if (f->times[i].order >= source) {++i;continue;}
        --f->num_times;
        memmove(f->times+i, f->times+i+1, (f->num_times-i)*sizeof(*f->times));
    }
    if (presentable && !f->failed) pump(f);
    int result = 0;
    if (!presentable)
        result = 2;
    else if (take_ready(f, source, frame)) {
        (*frame)->pts = (*frame)->best_effort_timestamp = pts;
        result = 1;
    } else if (f->failed || (f->eof && !f->recovering) ||
               (f->output_order != AV_NOPTS_VALUE && source < f->output_order))
    {
        result = !f->failed && f->anchor_pts != AV_NOPTS_VALUE && source < f->anchor_pts ? 2 : -1;
        av_log(f->decoder,result < 0 ? AV_LOG_ERROR : AV_LOG_DEBUG,
               "FEL source: absent source=%lld output=%lld anchor=%lld failed=%d eof=%d\n",
               (long long)source,(long long)f->output_order,(long long)f->anchor_pts,f->failed,f->eof);
    }
    if (result > 0) {
        f->source_taken = source;
        for (unsigned i = 0; i < f->num_times; ++i) if (f->times[i].order == source) {
            --f->num_times;
            memmove(f->times+i, f->times+i+1, (f->num_times-i)*sizeof(*f->times));
            break;
        }
    }
    return result;
}

int dvbridge_fel_take(struct dvbridge_fel *f, int64_t pts, AVFrame **frame)
{
    if (!f || !frame || *frame || pts == AV_NOPTS_VALUE)
        return -1;
    if (f->source_timed) return take_source(f, pts, frame);
    /* Return available work before submitting future enhancement pictures. */
    if (take_ready(f, pts, frame))
        return 1;
    if (f->failed || (f->eof && f->recovering))
        return -1;
    if (f->synchronizing || (f->anchor_pts != AV_NOPTS_VALUE && pts < f->anchor_pts))
        return 2; /* Preroll before a recoverable EL picture, not a substitute. */
    bool ok = pump(f);
    if (take_ready(f, pts, frame))
        return 1;
    if (!ok || (f->eof && f->recovering))
        return -1;
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
