"""Decoded T.35 metadata must survive the native frame-to-HDMI boundary."""
import base64
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import test_native_video_sidedata as snapshot


# One synthetic 16x16, lossless Main10 black IDR, generated with libx265.
# No user data, film frames or external encoder is needed to run the test.
BLACK_HEVC = base64.b64decode(
    'AAAAAUABDAH//wQIAAADAJ2oAAADAAD/ugJAAAAAAUIBAQQIAAADAJ2oAAADAAD/'
    'oIhE2W6q8rwFoCAAAAMAIAAAAwAhAAAAAUQBwXGJEgAAASgBrwW4JJj/Azf//+'
    'DVfBebAtJ+VPgs+Cz4LPgs+I94j3iPeI94j3iPeI94j+mWo5GtR8A=')


def hdr_sei(version, country=0xb5, truncated=False, system_fields=(0, 255)):
    # ST2094-40 single-window syntax. Expectations below are independent HDMI bytes.
    fields = [(version, 8), (1, 2), (500, 27), (0, 1)]
    fields += [(10000, 17)] * 3 + [(581, 17), (9, 4)]
    values = (160, *system_fields, 640, 1280, 2560, 5120, 10240, 20480)
    if version == 0:
        values = (160, 320, 480, 640, 1280, 2560, 5120, 10240, 20480)
    for percent, value in zip((1, 5, 10, 25, 50, 75, 90, 95, 99), values):
        fields += [(percent, 7), (value, 17)]
    fields += [(0, 10), (0, 1), (0, 1), (0, 1)]
    bits = ''.join(f'{value:0{width}b}' for value, width in fields)
    bits += '0' * (-len(bits) % 8)
    data = bytes([country, 0, 0x3c, 0, 1, 4])
    data += int(bits, 2).to_bytes(len(bits) // 8, 'big')
    if truncated:
        data = data[:9]
    rbsp = bytes([4, len(data)]) + data + b'\x80'
    escaped = bytearray()
    zeros = 0
    for value in rbsp:
        if zeros == 2 and value <= 3:
            escaped.append(3)
            zeros = 0
        escaped.append(value)
        zeros = zeros + 1 if value == 0 else 0
    return b'\x00\x00\x00\x01\x4e\x01' + escaped


def access_unit(sei):
    for nal in re.finditer(b'\x00\x00(?:\x00)?\x01', BLACK_HEVC):
        if (BLACK_HEVC[nal.end()] >> 1) & 63 <= 31:
            return BLACK_HEVC[:nal.start()] + sei + BLACK_HEVC[nal.start():]
    raise AssertionError('synthetic fixture has no coded picture')


class DecodedHDR10PlusTests(unittest.TestCase):
    def test_matroska_block_addition_preserves_validated_t35_country(self):
        if not os.environ.get('KODI_NATIVE_SOURCE_TREE'):
            self.skipTest('Set patched Kodi tree and matched FFmpeg prefix')
        from test_hdr10plus_dovi_mode import HDR10PlusDVModeTests

        def vint(n):
            width=1
            while n >= (1 << (7*width))-1:
                width+=1
            return (n | (1 << (7*width))).to_bytes(width,'big')

        def element(ident,payload):
            return ident.to_bytes((ident.bit_length()+7)//8,'big')+vint(len(payload))+payload

        def integer(ident,n):
            return element(ident,n.to_bytes(max(1,(n.bit_length()+7)//8),'big'))

        rbsp=bytearray()
        zeros=0
        for value in hdr_sei(1)[6:]:
            if zeros==2 and value==3:
                zeros=0
                continue
            rbsp.append(value)
            zeros=zeros+1 if value==0 else 0
        t35=bytes(rbsp[2:-1])
        self.assertEqual(t35[:6],bytes([181,0,60,0,1,4]))
        header=element(0x1a45dfa3,integer(0x4286,1)+integer(0x42f7,1)+integer(0x42f2,4)+
                       integer(0x42f3,8)+element(0x4282,b'matroska')+integer(0x4287,4)+integer(0x4285,2))
        info=element(0x1549a966,integer(0x2ad7b1,1000000)+element(0x4d80,b'cb1-test')+element(0x5741,b'cb1-test'))
        mapping=element(0x41e4,integer(0x41f0,4)+integer(0x41e7,4))
        video=element(0xe0,integer(0xb0,16)+integer(0xba,16)+element(0x55b0,
                      integer(0x55b1,9)+integer(0x55b2,10)+integer(0x55ba,16)+integer(0x55bb,9)))
        tracks=element(0x1654ae6b,element(0xae,integer(0xd7,1)+integer(0x73c5,1)+integer(0x83,1)+
                       element(0x86,b'V_MPEGH/ISO/HEVC')+integer(0x55ee,4)+mapping+video))
        block=element(0xa1,bytes([0x81,0,0,0])+BLACK_HEVC)
        addition=element(0x75a1,element(0xa6,integer(0xee,4)+element(0xa5,t35)))
        cluster=element(0x1f43b675,integer(0xe7,0)+element(0xa0,block+addition))
        container=header+element(0x18538067,info+tracks+cluster)
        program=r'''
#include "cores/VideoPlayer/VideoRenderers/HDR10PlusDVSource.h"
#include <cassert>
#include <cstring>
#include <algorithm>
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/mem.h>
}
static const uint8_t data[]={ARRAY};
struct Input {size_t pos{};};
int read_data(void* opaque,uint8_t* p,int n){
 auto& x=*static_cast<Input*>(opaque);
 if(x.pos==sizeof(data))return AVERROR_EOF;
 size_t take=std::min(size_t(n),sizeof(data)-x.pos);
 std::memcpy(p,data+x.pos,take);x.pos+=take;return take;
}
int main(){
 Input input;
 auto* io=avio_alloc_context(static_cast<unsigned char*>(av_malloc(4096)),4096,0,&input,read_data,nullptr,nullptr);assert(io);
 auto* format=avformat_alloc_context();assert(format);
 format->pb=io;format->flags|=AVFMT_FLAG_CUSTOM_IO;
 assert(avformat_open_input(&format,nullptr,av_find_input_format("matroska"),nullptr)==0);
 auto* packet=av_packet_alloc();assert(packet);
 assert(av_read_frame(format,packet)==0);
 size_t bytes=0;
 const auto* raw=av_packet_get_side_data(packet,AV_PKT_DATA_DYNAMIC_HDR10_PLUS,&bytes);
 assert(raw && bytes==sizeof(AVDynamicHDRPlus));
 const auto* hdr=reinterpret_cast<const AVDynamicHDRPlus*>(raw);
 assert(hdr->itu_t_t35_country_code==0xb5);
 auto* codec=avcodec_alloc_context3(avcodec_find_decoder(AV_CODEC_ID_HEVC));assert(codec);
 assert(avcodec_parameters_to_context(codec,format->streams[0]->codecpar)==0);
 codec->thread_count=1;codec->thread_type=0;
 assert(avcodec_open2(codec,codec->codec,nullptr)==0);
 assert(avcodec_send_packet(codec,packet)==0);
 assert(avcodec_send_packet(codec,nullptr)==0);
 auto* frame=av_frame_alloc();assert(frame && avcodec_receive_frame(codec,frame)==0);
 auto source=VideoSourceSideData::Capture(1,1,AV_CODEC_ID_HEVC,frame,nullptr);
 cb1_hdr10plus_dovi_result described{};
 const cb1_l1l3 estimate{0,3200,1200,2048,2048,2048};
 DVBRIDGE::SourceBinding b{1,1,1};
 assert(DVBRIDGE::DescribeHDR10PlusDV(described,estimate,source,b,b,1,1,true));
 assert(described.metadata.l1_max==3079);
 av_frame_free(&frame);av_packet_free(&packet);avcodec_free_context(&codec);
 avformat_close_input(&format);av_freep(&io->buffer);avio_context_free(&io);
}
'''.replace('ARRAY',','.join(map(str,container)))
        helper=HDR10PlusDVModeTests()
        helper.compile_run(program,sources=helper.snapshot_sources(),libraries=('-lavformat','-lavcodec'))

    def test_real_decoder_country_and_picture_survive_native_capture(self):
        self.check_chain(False)

    def test_decoded_modern_v1_reaches_the_actual_kernel_packet_validator(self):
        self.check_chain(True)

    def check_chain(self, check_kernel):
        if check_kernel and not os.environ.get('CB1_KERNEL_SOURCE'):
            self.skipTest('requires the matched patched kernel')
        serializer = Path(__file__).resolve().parents[2] / 'CB1/src/cb1_hdr10plus.c'
        arrays = '\n'.join('const uint8_t ' + name + '[]={' + ','.join(map(str, data)) + '};'
            for name, data in (
                ('plain', BLACK_HEVC),
                ('v0', access_unit(hdr_sei(0))),
                ('v1', access_unit(hdr_sei(1))),
                ('v1a', access_unit(hdr_sei(1, system_fields=(6123,98)))),
                ('v1b', access_unit(hdr_sei(1, system_fields=(4768,82)))),
                ('v1c', access_unit(hdr_sei(1, system_fields=(1298,93)))),
                ('foreign', access_unit(hdr_sei(1, country=0))),
                ('truncated', access_unit(hdr_sei(1, truncated=True)))))
        program=r'''
#include "cores/VideoSourceSideData.h"
#include <cassert>
#include <cstring>
#include <vector>
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/imgutils.h>
#include "SERIALIZER"
bool kernel_packet_valid(const void*,unsigned long);
}
ARRAYS
AVFrame* decode(const uint8_t* data,size_t size) {
 const auto* decoder=avcodec_find_decoder(AV_CODEC_ID_HEVC);
 assert(decoder && "test prefix must enable the HEVC decoder");
 AVCodecContext* ctx=avcodec_alloc_context3(decoder);assert(ctx);
 ctx->thread_count=1;ctx->thread_type=0;assert(avcodec_open2(ctx,decoder,nullptr)==0);
 AVPacket* packet=av_packet_alloc();assert(packet && av_new_packet(packet,size)==0);
 std::memcpy(packet->data,data,size);assert(avcodec_send_packet(ctx,packet)==0);
 AVFrame* frame=av_frame_alloc();assert(frame);
 int result=avcodec_receive_frame(ctx,frame);
 if(result==AVERROR(EAGAIN)){assert(avcodec_send_packet(ctx,nullptr)==0);result=avcodec_receive_frame(ctx,frame);}
 assert(result==0 && frame->width==16 && frame->height==16);
 av_packet_free(&packet);avcodec_free_context(&ctx);return frame;
}
std::vector<uint8_t> pixels(const AVFrame* frame) {
 auto format=static_cast<AVPixelFormat>(frame->format);
 std::vector<uint8_t> bytes(av_image_get_buffer_size(format,16,16,1));
 assert(av_image_copy_to_buffer(bytes.data(),bytes.size(),frame->data,frame->linesize,format,16,16,1)>0);
 return bytes;
}
int main() {
 AVFrame* reference=decode(plain,sizeof(plain));const auto expected=pixels(reference);
 assert(!av_frame_get_side_data(reference,AV_FRAME_DATA_DYNAMIC_HDR_PLUS));av_frame_free(&reference);
 struct Fixture {const uint8_t* data;size_t size;int version,slot1,slot2;};
 const Fixture fixtures[]={{v0,sizeof(v0),0,2,3},{v1,sizeof(v1),1,0,255},
  {v1a,sizeof(v1a),1,38,98},{v1b,sizeof(v1b),1,30,82},{v1c,sizeof(v1c),1,8,93}};
 unsigned serial=0;
 for(const auto& fixture:fixtures) {
  const int version=fixture.version;
  AVFrame* frame=decode(fixture.data,fixture.size);
  assert(pixels(frame)==expected && "metadata must not alter the decoded picture");
  auto source=VideoSourceSideData::Capture(7,++serial,AV_CODEC_ID_HEVC,frame,nullptr);
  assert(source && source->HDR10Plus() && "real decoder metadata must reach native capture");
  av_frame_free(&frame);
  uint8_t packet[31];
  assert(cb1_hdr10plus_vsif(packet,source->HDR10Plus(),false,true)==CB1_HDR10PLUS_OK &&
         "valid decoded HDR10+ must reach HDMI without inventing its country in Kodi");
  assert(source->HDR10Plus()->itu_t_t35_country_code==0xb5);
  assert(packet[7]==(version?0x60:0x20) && packet[8]==4 && packet[9]==1);
  assert(packet[10]==fixture.slot1 && packet[11]==fixture.slot2);
  unsigned sum=0;for(auto byte:packet)sum+=byte;assert(!(sum&255));
  KERNEL_ASSERT
  AVDynamicHDRPlus invalid=*source->HDR10Plus();invalid.itu_t_t35_country_code=0;
  uint8_t saved[31];std::memcpy(saved,packet,sizeof(saved));
  assert(cb1_hdr10plus_vsif(packet,&invalid,false,true)==CB1_HDR10PLUS_INVALID);
  assert(!std::memcmp(saved,packet,sizeof(saved)));
 }
 for(const auto pair:{std::pair{foreign,sizeof(foreign)},std::pair{truncated,sizeof(truncated)}}) {
  AVFrame* frame=decode(pair.first,pair.second);assert(pixels(frame)==expected);
  assert(!av_frame_get_side_data(frame,AV_FRAME_DATA_DYNAMIC_HDR_PLUS));av_frame_free(&frame);
 }
}
'''.replace('SERIALIZER', str(serializer)).replace('ARRAYS', arrays)
        program=program.replace('KERNEL_ASSERT',
            'assert(kernel_packet_valid(packet,sizeof(packet)) && "valid decoded V1 rejected downstream");' if check_kernel else '')
        with tempfile.TemporaryDirectory() as temporary:
            objects=[]
            if check_kernel:
                root=Path(temporary);code=root/'validator.c';obj=root/'validator.o'
                header=Path(os.environ['CB1_KERNEL_SOURCE'])/'include/drm/drm_hdr10plus.h'
                code.write_text('#include <stdbool.h>\n#include "'+str(header)+'"\n'
                    'bool kernel_packet_valid(const void* p,unsigned long n){return drm_hdr10plus_infoframe_valid(p,n);}\n')
                built=subprocess.run(['cc','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-c',str(code),'-o',str(obj)],capture_output=True,text=True)
                self.assertEqual(built.returncode,0,built.stderr)
                objects=[obj]
            snapshot.SideDataTests().compile_run(program,libraries=('avcodec',),objects=objects)


if __name__ == '__main__':
    unittest.main()
