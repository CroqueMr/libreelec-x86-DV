/* SPDX-License-Identifier: MIT */
#include "dvbridge_fel.h"
#include <assert.h>
static int receives;
static int terminal_mode, terminal_eof;
static int receive_then_fail(AVCodecContext *ctx,AVFrame *frame)
{
    (void)ctx;
    if(terminal_mode)return terminal_eof?AVERROR_EOF:AVERROR(EAGAIN);
    if(receives++)return AVERROR(ENOMEM);
    frame->format=AV_PIX_FMT_VAAPI;frame->pts=9;
    return 0;
}
static int terminal_send(AVCodecContext *ctx,const AVPacket *packet)
{
    if(!terminal_mode)return avcodec_send_packet(ctx,packet);
    assert(!packet);terminal_eof++;return 0;
}
#define avcodec_send_packet terminal_send
#define avcodec_receive_frame receive_then_fail
#include "dvbridge_fel.c"
#undef avcodec_receive_frame
#undef avcodec_send_packet
#include "synthetic_idr.h"

static AVCodecParserContext *reordered_base;
int __real_av_parser_parse2(AVCodecParserContext*,AVCodecContext*,uint8_t**,int*,const uint8_t*,int,int64_t,int64_t,int64_t);
int __wrap_av_parser_parse2(AVCodecParserContext *parser,AVCodecContext *context,uint8_t **out,int *size,
    const uint8_t *data,int bytes,int64_t pts,int64_t dts,int64_t pos)
{
    int result=__real_av_parser_parse2(parser,context,out,size,data,bytes,pts,dts,pos);
    if(parser==reordered_base){parser->output_picture_number=21;parser->key_frame=0;}
    return result;
}

static void unanchored_mel(void)
{
    AVCodecParameters *parameters = avcodec_parameters_alloc();
    assert(parameters);
    parameters->codec_id = AV_CODEC_ID_HEVC;
    parameters->codec_type = AVMEDIA_TYPE_VIDEO;
    struct dvbridge_fel *fel = dvbridge_fel_create(parameters, (AVRational){1, 1000000});
    avcodec_parameters_free(&parameters);
    assert(fel);
    size_t size;
    AVDOVIMetadata *metadata = av_dovi_metadata_alloc(&size);
    assert(metadata);
    AVDOVIRpuDataHeader *header = av_dovi_get_header(metadata);
    AVDOVIDataMapping *mapping = av_dovi_get_mapping(metadata);
    header->coef_log2_denom = 23;
    mapping->nlq_method_idc = AV_DOVI_NLQ_LINEAR_DZ;
    for (unsigned i = 0; i < 3; ++i)
        mapping->nlq[i].vdr_in_max = UINT64_C(1) << header->coef_log2_denom;
    AVPacket *base = av_packet_alloc();
    assert(base && av_new_packet(base, sizeof(synthetic_base)) == 0);
    memcpy(base->data, synthetic_base, sizeof(synthetic_base));
    AVFrame *frame = NULL;
    for (int i = 0; i < 1100; ++i) {
        base->pts = base->dts = i;
        assert(dvbridge_fel_submit(fel, base));
        assert(dvbridge_fel_take_mel(fel, i, &frame, metadata, size) == 3 && !frame);
    }
    assert(dvbridge_fel_drain(fel, NULL));
    assert(dvbridge_fel_exhausted(fel));
    for (int residual = 0; residual < 2; ++residual) {
        dvbridge_fel_reset(fel);
        base->pts = base->dts = 2000;
        assert(dvbridge_fel_submit(fel, base));
        assert(dvbridge_fel_take_mel(fel, 2000, &frame, metadata, size) == 3);
        base->pts = base->dts = 2001;
        assert(dvbridge_fel_submit(fel, base));
        mapping->nlq[0].nlq_offset = residual;
        assert(dvbridge_fel_take_mel(fel, 2001, &frame, residual ? metadata : NULL, size) == 2);
        assert(!dvbridge_fel_drain(fel, NULL));
        mapping->nlq[0].nlq_offset = 0;
    }
    dvbridge_fel_reset(fel);
    base->pts = base->dts = 3000;
    assert(dvbridge_fel_submit(fel, base));
    assert(dvbridge_fel_take_mel(fel, 3000, &frame, metadata, size) == 3);
    AVPacket *paired = av_packet_alloc();
    assert(paired && av_new_packet(paired, sizeof(synthetic_paired)) == 0);
    memcpy(paired->data, synthetic_paired, sizeof(synthetic_paired));
    paired->pts = paired->dts = 3001;
    assert(dvbridge_fel_submit(fel, paired) && !fel->synchronizing);
    assert(fel->num_packets == 1 && fel->packet_order[0] == fel->base_order.maximum);
    assert(dvbridge_fel_take_mel(fel, 3001, &frame, metadata, size) == 0 && !frame);
    av_packet_free(&paired);
    av_packet_free(&base);
    av_free(metadata);
    dvbridge_fel_destroy(fel);
}

int main(void)
{
    unanchored_mel();
    /* Draining closes this input epoch: only a proved out-of-range EL suffix
     * may be retired. Never discard an internal hole or a future reference. */
    terminal_mode=1;
    for(int scenario=0;scenario<4;scenario++){
        struct dvbridge_fel end={.opened=true,.draining=scenario!=1,
            .anchor_pts=AV_NOPTS_VALUE,.output_order=AV_NOPTS_VALUE,.num_packets=2,.packet_bytes=2};
        end.decoder=avcodec_alloc_context3(NULL);assert(end.decoder);
        end.base_order.seen=true;end.base_order.maximum=9;
        end.packet_order[0]=scenario==2?8:10;
        end.packet_order[1]=scenario==3?9:18;
        for(int i=0;i<2;i++){end.packets[i]=av_packet_alloc();assert(end.packets[i]&&av_new_packet(end.packets[i],1)==0);}
        end.num_frames=2;
        AVFrame *saved[2];
        for(int i=0;i<2;i++){
            end.frames[i]=saved[i]=av_frame_alloc();assert(saved[i]);saved[i]->pts=800+100*i;
            AVFrameSideData *sd=av_frame_new_side_data(saved[i],AV_FRAME_DATA_DOVI_RPU_BUFFER,5);assert(sd);
            memcpy(sd->data,(const uint8_t[]){25,8,0,0,0x80},5);
        }
        terminal_eof=0;
        bool ok=pump(&end);
        if(scenario==0)assert(ok&&!end.failed&&end.eof&&!end.num_packets&&!end.packet_bytes&&terminal_eof==1);
        else if(scenario==1)assert(ok&&!end.failed&&end.num_packets==2&&!terminal_eof);
        else assert(!ok&&end.failed&&end.num_packets==2&&!terminal_eof);
        for(int i=0;i<2;i++){
            AVFrame *ready=NULL;assert(dvbridge_fel_take(&end,800+100*i,&ready)==1&&ready==saved[i]);
            assert(!memcmp(av_frame_get_side_data(ready,AV_FRAME_DATA_DOVI_RPU_BUFFER)->data,
                           (const uint8_t[]){25,8,0,0,0x80},5));
            av_frame_free(&ready);
        }
        for(unsigned i=0;i<end.num_packets;i++)av_packet_free(&end.packets[i]);
        avcodec_free_context(&end.decoder);
    }
    terminal_mode=0;
    struct dvbridge_fel f={.failed=true,.num_frames=2};
    AVFrame *frame=NULL;
    for(unsigned i=0;i<2;i++){
        f.frames[i]=av_frame_alloc();assert(f.frames[i]);
        f.frames[i]->pts=100+i;
    }
    assert(dvbridge_fel_take(&f,100,&frame)==1 && frame->pts==100);
    av_frame_free(&frame);
    assert(dvbridge_fel_take(&f,101,&frame)==1 && frame->pts==101);
    av_frame_free(&frame);
    assert(dvbridge_fel_take(&f,102,&frame)==-1 && !frame);
    f=(struct dvbridge_fel){.opened=true,.num_times=1,.output_order=AV_NOPTS_VALUE,
        .anchor_pts=AV_NOPTS_VALUE};
    f.decoder=avcodec_alloc_context3(NULL);assert(f.decoder);
    f.times[0].order=9;f.times[0].pts=900;
    assert(dvbridge_fel_take(&f,900,&frame)==1 && frame->pts==900 && f.failed);
    av_frame_free(&frame);
    assert(dvbridge_fel_take(&f,901,&frame)==-1 && !frame);
    avcodec_free_context(&f.decoder);
    for(int reordered=0;reordered<2;reordered++){
    AVCodecParameters *parameters=avcodec_parameters_alloc();assert(parameters);
    parameters->codec_type=AVMEDIA_TYPE_VIDEO;parameters->codec_id=AV_CODEC_ID_HEVC;
    parameters->width=3840;parameters->height=2160;
    struct dvbridge_fel *epoch=dvbridge_fel_create(parameters,(AVRational){1,1000000});
    avcodec_parameters_free(&parameters);assert(epoch);
    AVPacket *p=av_packet_alloc();assert(p && av_new_packet(p,sizeof(synthetic_paired))==0);
    memcpy(p->data,synthetic_paired,sizeof(synthetic_paired));p->pts=p->dts=0;
    assert(dvbridge_fel_submit(epoch,p));
    av_packet_free(&epoch->packets[0]);epoch->num_packets=0;epoch->packet_bytes=0;
    /* A whole enhancement GOP went missing. The retained BL4 is itself key;
     * independent max+1 counters would wrongly put the next EL8 in its slot. */
    epoch->num_times=0;epoch->base_order.maximum=epoch->enhancement_order.maximum=3;
    epoch->base_order.context->has_b_frames=reordered;
    AVPacket *bare=av_packet_alloc();assert(bare && av_new_packet(bare,sizeof(synthetic_base))==0);
    memcpy(bare->data,synthetic_base,sizeof(synthetic_base));
    for(int i=4;i<8;i++){
        bare->pts=bare->dts=100*i;assert(dvbridge_fel_submit(epoch,bare));
        assert(epoch->epoch_uncertain && !epoch->num_packets);
    }
    p->pts=p->dts=800;assert(dvbridge_fel_submit(epoch,p));
    assert(epoch->num_packets==1 && epoch->packet_order[0]==8 && !epoch->epoch_uncertain);
    assert(epoch->times[0].order==4 && epoch->times[0].pts==400);
    assert(epoch->packets[0]->size==sizeof(synthetic_base));
    assert(!memcmp(epoch->packets[0]->data,synthetic_base,sizeof(synthetic_base)));
    av_packet_free(&bare);av_packet_free(&p);dvbridge_fel_destroy(epoch);
    }
    /* A continuous independently coded EL key can precede its reordered BL
     * key. Preserve it when no enhancement AU was lost; after a gap, wait
     * instead of guessing or declaring an immediately unrecoverable failure. */
    for(int gap=0;gap<2;gap++){
        AVCodecParameters *parameters=avcodec_parameters_alloc();assert(parameters);
        parameters->codec_type=AVMEDIA_TYPE_VIDEO;parameters->codec_id=AV_CODEC_ID_HEVC;
        struct dvbridge_fel *epoch=dvbridge_fel_create(parameters,(AVRational){1,1000000});
        avcodec_parameters_free(&parameters);assert(epoch);
        epoch->synchronizing=false;epoch->epoch_uncertain=gap;
        epoch->base_order.seen=epoch->enhancement_order.seen=true;
        epoch->base_order.maximum=epoch->enhancement_order.maximum=71;
        epoch->base_order.offset=48;epoch->base_order.context->has_b_frames=3;
        reordered_base=epoch->base_order.parser;
        AVPacket *p=av_packet_alloc();assert(p && av_new_packet(p,sizeof(synthetic_paired))==0);
        memcpy(p->data,synthetic_paired,sizeof(synthetic_paired));p->pts=p->dts=6900;
        assert(dvbridge_fel_submit(epoch,p) && !epoch->failed);
        reordered_base=NULL;
        if(gap)assert(!epoch->num_packets && epoch->recovering);
        else assert(epoch->num_packets==1 && epoch->packet_order[0]==72);
        av_packet_free(&p);dvbridge_fel_destroy(epoch);
    }
    f=(struct dvbridge_fel){.eof=true,.recovering=true,.anchor_pts=AV_NOPTS_VALUE};
    assert(dvbridge_fel_take(&f,102,&frame)==-1 && !frame);
    return 0;
}
