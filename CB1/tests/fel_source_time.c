/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Native splitter/parser; reuse only the existing VAAPI ioctl test boundary. */
#define main legacy_fel_queue_checks
#include "fel_queue.c"
#undef main
#define submit_source dvbridge_fel_submit_source

static void nonkey_dispositions(AVBufferRef *device)
{
    AVCodecParameters *p=avcodec_parameters_alloc();assert(p);
    p->codec_type=AVMEDIA_TYPE_VIDEO;p->codec_id=AV_CODEC_ID_HEVC;
    struct dvbridge_fel *f=dvbridge_fel_create(p,(AVRational){1,1000000});
    avcodec_parameters_free(&p);assert(f&&dvbridge_fel_device(f,device));
    uint8_t wrapped[sizeof(seek_config)+32];size_t n=0;
    for(size_t i=0;i<sizeof(seek_config);++i) {
        wrapped[n++]=seek_config[i];
        if(i>=3&&!memcmp(seek_config+i-3,"\0\0\0\1",4)){
            wrapped[n++]=0x7e;wrapped[n++]=1;
        }
    }
    for(int i=0;i<24;++i) {
        AVPacket *packet=av_packet_alloc();assert(packet);
        const size_t slice=15+i%3;
        assert(av_new_packet(packet,sizeof(synthetic_base)+n+2+slice)==0);
        uint8_t *out=packet->data;
        memcpy(out,synthetic_base,sizeof(synthetic_base));out+=sizeof(synthetic_base);
        memcpy(out,wrapped,n);out+=n;
        memcpy(out,"\0\0\1\x7e\1",5);out+=5;
        memcpy(out,seek_base[i%3]+3,slice-3);
        packet->pts=packet->dts=1000+i;
        struct dvbridge_fel_source source={100+i,100+i,{1,90000},1,true};
        if(!i) {
            AVPacket *first=av_packet_alloc();assert(first);
            assert(av_new_packet(first,packet->size-sizeof(synthetic_base))==0);
            memcpy(first->data,packet->data+sizeof(synthetic_base),first->size);
            first->pts=first->dts=AV_NOPTS_VALUE;
            struct dvbridge_fel_source earlier={AV_NOPTS_VALUE,100,{1,90000},1,false};
            assert(submit_source(f,first,&earlier));av_packet_free(&first);
            av_shrink_packet(packet,sizeof(synthetic_base));source.enhancement_pts=AV_NOPTS_VALUE;
        }
        assert(submit_source(f,packet,&source));av_packet_free(&packet);
        AVFrame *frame=NULL;
        assert(dvbridge_fel_take(f,1000+i,&frame)==2&&!frame);
    }
    assert(f->synchronizing && !f->num_times && !f->num_packets);
    dvbridge_fel_destroy(f);
}

int main(void)
{
    for (int offset=-1000;offset<=0;offset+=1000)
    for (int primer=0;primer<2;++primer) {
        count=0;end=false;
        AVCodecParameters *p=avcodec_parameters_alloc();assert(p);
        p->codec_type=AVMEDIA_TYPE_VIDEO;p->codec_id=AV_CODEC_ID_HEVC;
        struct dvbridge_fel *f=dvbridge_fel_create(p,(AVRational){1,1000000});
        avcodec_parameters_free(&p);assert(f);
        AVBufferRef *device=av_buffer_allocz(sizeof(AVHWDeviceContext));assert(device);
        ((AVHWDeviceContext*)device->data)->type=AV_HWDEVICE_TYPE_VAAPI;
        assert(dvbridge_fel_device(f,device));
        if(offset==-1000&&!primer)nonkey_dispositions(device);
        AVPacket *packet=av_packet_alloc();assert(packet);
        assert(av_new_packet(packet,sizeof(synthetic_paired))==0);
        memcpy(packet->data,synthetic_paired,sizeof(synthetic_paired));
        const int64_t base[]={103,101,102},kodi[]={3000,1000,2000};
        for(int i=0;i<3;++i) {
            packet->pts=packet->dts=kodi[i];
            struct dvbridge_fel_source source={base[i]+offset,101+i+offset,{1,90000},1,!(primer&&i==0)};
            assert(submit_source(f,packet,&source));
        }
        for(int i=1;i<=3;++i) {
            AVFrame *frame=NULL;
            int result=dvbridge_fel_take(f,1000*i,&frame);
            if(result!=1 && !(primer&&i==3))
                fprintf(stderr,"source test offset=%d primer=%d picture=%d result=%d failed=%d maps=%u packets=%u frames=%u\n",offset,primer,i,result,f->failed,f->num_times,f->num_packets,f->num_frames);
            if(primer&&i==3)assert(result==2&&!frame);
            else {assert(result==1&&frame&&frame->pts==1000*i);av_frame_free(&frame);}
        }
        if(primer) {
            packet->pts=packet->dts=3000;
            struct dvbridge_fel_source late={103+offset,104+offset,{1,90000},1,true};
            assert(!submit_source(f,packet,&late));
        }
        packet->pts=packet->dts=4000;
        struct dvbridge_fel_source stale={104+offset,104+offset,{1,90000},2,true};
        assert(!submit_source(f,packet,&stale));
        dvbridge_fel_reset(f);
        assert(submit_source(f,packet,&stale));
        AVFrame *frame=NULL;
        assert(dvbridge_fel_take(f,4000,&frame)==1&&frame&&frame->pts==4000);
        av_frame_free(&frame);
        dvbridge_fel_reset(f);
        // An EL-only terminal unit can satisfy a previously accepted BL.
        struct dvbridge_fel_source head={501,500,{1,90000},3,true};
        packet->pts=packet->dts=5000;
        assert(submit_source(f,packet,&head));
        size_t el=0;
        while(el+5<sizeof(synthetic_paired)&&memcmp(synthetic_paired+el,"\0\0\1\x7e\1",5))++el;
        assert(el+5<sizeof(synthetic_paired));
        av_packet_unref(packet);assert(av_new_packet(packet,sizeof(synthetic_paired)-el)==0);
        memcpy(packet->data,synthetic_paired+el,packet->size);
        packet->pts=packet->dts=AV_NOPTS_VALUE;
        struct dvbridge_fel_source tail={AV_NOPTS_VALUE,501,{1,90000},3,false};
        assert(submit_source(f,packet,&tail));
        assert(dvbridge_fel_take(f,5000,&frame)==1&&frame&&frame->pts==5000);
        av_frame_free(&frame);
        assert(dvbridge_fel_drain(f));
        dvbridge_fel_reset(f);
        // A genuinely decoded leading picture is exact despite a later RAP PTS.
        f->source_timed=true;f->anchor_pts=100;f->num_times=1;
        f->times[0].order=99;f->times[0].pts=9000;f->times[0].presentable=true;
        f->frames[0]=av_frame_alloc();assert(f->frames[0]);
        f->frames[0]->pts=99;f->num_frames=1;
        assert(dvbridge_fel_take(f,9000,&frame)==1&&frame&&frame->pts==9000);
        av_frame_free(&frame);
        // Proven absent acquisition picture, not a missing in-range pair.
        f->output_order=AV_NOPTS_VALUE;f->num_times=1;
        f->times[0].order=99;f->times[0].pts=9001;f->times[0].presentable=true;
        assert(dvbridge_fel_take(f,9001,&frame)==0&&!frame);
        f->output_order=102;f->failed=true;
        assert(dvbridge_fel_take(f,9001,&frame)==-1&&!frame);
        f->failed=false;
        assert(dvbridge_fel_take(f,9001,&frame)==2&&!frame);
        f->num_times=1;
        f->times[0].order=101;f->times[0].pts=9002;f->times[0].presentable=true;
        assert(dvbridge_fel_take(f,9002,&frame)==-1&&!frame);
        av_packet_free(&packet);
        dvbridge_fel_destroy(f);av_buffer_unref(&device);
    }
    puts("PASS: independent source times, immutable primer and explicit epoch reset");
}
