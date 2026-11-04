/* SPDX-License-Identifier: MIT */
#include "dvbridge_fel.h"
static int receives;
static int receive_then_fail(AVCodecContext *ctx,AVFrame *frame)
{
    (void)ctx;
    if(receives++)return AVERROR(ENOMEM);
    frame->format=AV_PIX_FMT_VAAPI;frame->pts=9;
    return 0;
}
#define avcodec_receive_frame receive_then_fail
#include "dvbridge_fel.c"
#undef avcodec_receive_frame
#include <assert.h>
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

int main(void)
{
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
