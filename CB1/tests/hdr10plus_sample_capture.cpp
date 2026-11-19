/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Optional adapter for hdr10plus_sample.c, compiled with CB1_TEST_NATIVE_CAPTURE.
 * Link the real Kodi VideoSourceSideData.cpp and its JSON/Base64 dependencies. */
#include "cores/VideoSourceSideData.h"
#include "cb1_hdr10plus.h"
#include <cassert>
#include <cstring>
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
}

extern "C" void cb1_hdr10plus_sample_capture(const AVDynamicHDRPlus *metadata)
{
    AVFrame *frame=av_frame_alloc();assert(frame);
    AVFrameSideData *sd=av_frame_new_side_data(frame,AV_FRAME_DATA_DYNAMIC_HDR_PLUS,sizeof(*metadata));
    assert(sd);std::memcpy(sd->data,metadata,sizeof(*metadata));
    const AVDynamicHDRPlus original=*metadata;
    auto source=VideoSourceSideData::Capture(7,1,AV_CODEC_ID_HEVC,frame,nullptr);
    assert(source && !source->RejectedSections() && source->HDR10Plus());
    assert(!std::memcmp(source->HDR10Plus(),&original,sizeof(original)));
    std::memset(sd->data,0xff,sd->size);av_frame_free(&frame);
    uint8_t expected[31],captured[31];
    assert(cb1_hdr10plus_vsif(expected,metadata,false,true)==CB1_HDR10PLUS_OK);
    assert(cb1_hdr10plus_vsif(captured,source->HDR10Plus(),false,true)==CB1_HDR10PLUS_OK);
    assert(!std::memcmp(expected,captured,sizeof(expected)));
    assert(source->JSON().find("hdr10plus")!=std::string::npos);
    assert(!std::memcmp(source->HDR10Plus(),&original,sizeof(original)));
    assert(cb1_hdr10plus_vsif(captured,source->HDR10Plus(),false,true)==CB1_HDR10PLUS_OK);
    assert(!std::memcmp(expected,captured,sizeof(expected)));
}

extern "C" void cb1_hdr10plus_sample_decode(const char *path)
{
    AVFormatContext *format=nullptr;assert(!avformat_open_input(&format,path,nullptr,nullptr));
    unsigned video=0;while(video<format->nb_streams &&
        format->streams[video]->codecpar->codec_type!=AVMEDIA_TYPE_VIDEO)video++;
    assert(video<format->nb_streams);
    const auto *codec=avcodec_find_decoder(AV_CODEC_ID_HEVC);assert(codec);
    AVCodecContext *decoder=avcodec_alloc_context3(codec);assert(decoder);
    assert(!avcodec_parameters_to_context(decoder,format->streams[video]->codecpar));
    decoder->thread_count=1;decoder->thread_type=0;
    assert(!avcodec_open2(decoder,codec,nullptr));
    AVPacket *packet=av_packet_alloc();AVFrame *frame=av_frame_alloc();assert(packet && frame);
    bool decoded=false;
    while(!decoded && av_read_frame(format,packet)>=0){
        if(packet->stream_index==static_cast<int>(video)){
            assert(!avcodec_send_packet(decoder,packet));
            const int status=avcodec_receive_frame(decoder,frame);
            assert(status==0 || status==AVERROR(EAGAIN));decoded=status==0;
        }
        av_packet_unref(packet);
    }
    assert(decoded);
    const auto *sd=av_frame_get_side_data(frame,AV_FRAME_DATA_DYNAMIC_HDR_PLUS);assert(sd);
    assert(sd->size==sizeof(AVDynamicHDRPlus));
    const auto *m=reinterpret_cast<const AVDynamicHDRPlus*>(sd->data);
    assert(m->itu_t_t35_country_code==0xb5 && m->application_version==1 && m->num_windows==1);
    assert(m->targeted_system_display_maximum_luminance.num==300);
    assert(m->params[0].distribution_maxrgb[1].percentile.num==2094);
    assert(m->params[0].distribution_maxrgb[2].percentile.num==96);
    cb1_hdr10plus_sample_capture(m);
    av_frame_free(&frame);av_packet_free(&packet);avcodec_free_context(&decoder);avformat_close_input(&format);
    puts("Exact FF Pictures opening frame: HEVC decoder -> native Capture -> JSON -> HDMI passed");
}
