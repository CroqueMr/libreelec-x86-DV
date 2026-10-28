"""Decoded T.35 metadata must survive the native frame-to-HDMI boundary."""
import base64
from pathlib import Path
import re
import unittest
from test_native_video_sidedata import SideDataTests as SnapshotChecks


# One synthetic 16x16, lossless Main10 black IDR, generated with libx265.
# No user data, film frames or external encoder is needed to run the test.
BLACK_HEVC = base64.b64decode(
    'AAAAAUABDAH//wQIAAADAJ2oAAADAAD/ugJAAAAAAUIBAQQIAAADAJ2oAAADAAD/'
    'oIhE2W6q8rwFoCAAAAMAIAAAAwAhAAAAAUQBwXGJEgAAASgBrwW4JJj/Azf//+'
    'DVfBebAtJ+VPgs+Cz4LPgs+I94j3iPeI94j3iPeI94j+mWo5GtR8A=')


def hdr_sei(version, country=0xb5, truncated=False):
    # ST2094-40 single-window syntax. Expectations below are independent HDMI bytes.
    fields = [(version, 8), (1, 2), (500, 27), (0, 1)]
    fields += [(10000, 17)] * 3 + [(581, 17), (9, 4)]
    values = (160, 0, 255, 640, 1280, 2560, 5120, 10240, 20480)
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
    def test_real_decoder_country_and_picture_survive_native_capture(self):
        serializer = Path(__file__).resolve().parents[2] / 'CB1/src/cb1_hdr10plus.c'
        arrays = '\n'.join('const uint8_t ' + name + '[]={' + ','.join(map(str, data)) + '};'
            for name, data in (
                ('plain', BLACK_HEVC),
                ('v0', access_unit(hdr_sei(0))),
                ('v1', access_unit(hdr_sei(1))),
                ('foreign', access_unit(hdr_sei(1, country=0))),
                ('truncated', access_unit(hdr_sei(1, truncated=True)))))
        SnapshotChecks().compile_run(r'''
#include "cores/VideoSourceSideData.h"
#include <cassert>
#include <cstring>
#include <vector>
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/imgutils.h>
#include "SERIALIZER"
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
 for(int version=0;version<=1;++version) {
  AVFrame* frame=version?decode(v1,sizeof(v1)):decode(v0,sizeof(v0));
  assert(pixels(frame)==expected && "metadata must not alter the decoded picture");
  auto source=VideoSourceSideData::Capture(7,version+1,AV_CODEC_ID_HEVC,frame,nullptr);
  assert(source && source->HDR10Plus() && "real decoder metadata must reach native capture");
  av_frame_free(&frame);
  uint8_t packet[31];
  assert(cb1_hdr10plus_vsif(packet,source->HDR10Plus(),false,true)==CB1_HDR10PLUS_OK &&
         "valid decoded HDR10+ must reach HDMI without inventing its country in Kodi");
  assert(source->HDR10Plus()->itu_t_t35_country_code==0xb5);
  assert(packet[7]==(version?0x60:0x20) && packet[8]==4 && packet[9]==1);
  assert(packet[10]==(version?0:2) && packet[11]==(version?255:3));
  unsigned sum=0;for(auto byte:packet)sum+=byte;assert(!(sum&255));
 }
 for(const auto pair:{std::pair{foreign,sizeof(foreign)},std::pair{truncated,sizeof(truncated)}}) {
  AVFrame* frame=decode(pair.first,pair.second);assert(pixels(frame)==expected);
  assert(!av_frame_get_side_data(frame,AV_FRAME_DATA_DYNAMIC_HDR_PLUS));av_frame_free(&frame);
 }
 AVDynamicHDRPlus invalid{};uint8_t packet[31];
 assert(cb1_hdr10plus_vsif(packet,&invalid,false,true)==CB1_HDR10PLUS_INVALID);
}
'''.replace('SERIALIZER', str(serializer)).replace('ARRAYS', arrays), libraries=('avcodec',))


if __name__ == '__main__':
    unittest.main()
