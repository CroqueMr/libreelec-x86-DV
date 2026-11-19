/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Optional full-source reproduction: compile with cb1_hdr10plus.c and matched
 * libavformat/libavcodec/libavutil, then pass the public FF Pictures MP4.
 * Inspect compressed SEI only: never decode, process or rewrite movie pixels. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <libavformat/avformat.h>
#include "cb1_hdr10plus.h"

#ifdef CB1_TEST_NATIVE_CAPTURE
void cb1_hdr10plus_sample_capture(const AVDynamicHDRPlus *metadata);
void cb1_hdr10plus_sample_decode(const char *path);
#endif

static unsigned metadata_count, rejected, invalid;

static void sei(const uint8_t *nal, unsigned size, int64_t pts)
{
    assert(size>=2);
    uint8_t *rbsp=av_malloc(size);assert(rbsp);
    unsigned bytes=0,zeros=0;
    for(unsigned i=2;i<size;i++){
        if(zeros==2 && nal[i]==3){zeros=0;continue;}
        rbsp[bytes++]=nal[i];zeros=nal[i]==0?zeros+1:0;
    }
    for(unsigned pos=0;pos+1<bytes;){
        unsigned type=0,length=0;
        while(pos<bytes && rbsp[pos]==255){type+=255;pos++;}
        assert(pos<bytes);type+=rbsp[pos++];
        while(pos<bytes && rbsp[pos]==255){length+=255;pos++;}
        assert(pos<bytes);length+=rbsp[pos++];assert(length<=bytes-pos);
        const uint8_t *data=rbsp+pos;pos+=length;
        static const uint8_t header[]={0xb5,0,0x3c,0,1,4};
        if(type!=4 || length<sizeof(header) || memcmp(data,header,sizeof(header)))continue;
        AVDynamicHDRPlus m={0};
        assert(av_dynamic_hdr_plus_from_t35(&m,data+6,length-6)==0);
        m.itu_t_t35_country_code=data[0];
#ifdef CB1_TEST_NATIVE_CAPTURE
        cb1_hdr10plus_sample_capture(&m);
#endif
        const AVDynamicHDRPlus original=m;
        uint8_t packet[31],before[31];memset(packet,0xa5,sizeof(packet));
        memcpy(before,packet,sizeof(before));
        enum cb1_hdr10plus_status status=cb1_hdr10plus_vsif(packet,&m,false,true);
        assert(!memcmp(&m,&original,sizeof(m)));
        if(status==CB1_HDR10PLUS_OK){
            unsigned sum=0;for(unsigned i=0;i<31;i++)sum+=packet[i];assert(!(sum&255));
        }else{
            assert(!memcmp(packet,before,sizeof(packet)));
            if(status==CB1_HDR10PLUS_INVALID)invalid++;else rejected++;
            if(rejected+invalid<=12){
                printf("rejected metadata=%u pts=%lld status=%d anchors=",metadata_count,(long long)pts,status);
                for(unsigned i=0;i<m.params[0].num_bezier_curve_anchors;i++)
                    printf("%d,",m.params[0].bezier_curve_anchors[i].num);
                puts("");
            }
        }
        metadata_count++;
    }
    av_free(rbsp);
}

int main(int argc,char **argv)
{
    assert(argc==2);
#ifdef CB1_TEST_NATIVE_CAPTURE
    cb1_hdr10plus_sample_decode(argv[1]);
#endif
    AVFormatContext *format=NULL;assert(avformat_open_input(&format,argv[1],NULL,NULL)==0);
    unsigned video=0;while(video<format->nb_streams &&
        format->streams[video]->codecpar->codec_type!=AVMEDIA_TYPE_VIDEO)video++;
    assert(video<format->nb_streams);
    const AVCodecParameters *params=format->streams[video]->codecpar;
    assert(params->codec_id==AV_CODEC_ID_HEVC && params->extradata_size>=23);
    unsigned length_size=(params->extradata[21]&3)+1;
    AVPacket *packet=av_packet_alloc();assert(packet);
    while(av_read_frame(format,packet)>=0){
        if(packet->stream_index==(int)video){
            unsigned pos=0;
            while(pos<(unsigned)packet->size){
                assert(length_size<=(unsigned)packet->size-pos);
                unsigned size=0;for(unsigned i=0;i<length_size;i++)size=(size<<8)|packet->data[pos++];
                assert(size>=2 && size<=(unsigned)packet->size-pos);
                unsigned type=(packet->data[pos]>>1)&63;
                if(type==39 || type==40)sei(packet->data+pos,size,packet->pts);
                pos+=size;
            }
        }
        av_packet_unref(packet);
    }
    av_packet_free(&packet);avformat_close_input(&format);
    printf("HDR10+ source metadata: total=%u accepted=%u unrepresentable=%u invalid=%u; inputs unchanged\n",
        metadata_count,metadata_count-rejected-invalid,rejected,invalid);
    assert(metadata_count && !rejected && !invalid);
}
