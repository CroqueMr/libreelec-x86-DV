"""Joined HEVC with in-band parameter sets must use Kodi's native parser."""
import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dual_carriage import mp4
from test_native_video_source import TREE, body


class JoinedHeaders(unittest.TestCase):
    def test_native_parser_publishes_first_joined_picture_only_after_headers(self):
        prefix=os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:self.skipTest('Matched FFmpeg libraries required')
        native=(TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text()
        ff=(TREE/'xbmc/cores/FFmpeg.cpp').read_text()
        header=(TREE/'xbmc/cores/FFmpeg.h').read_text()
        extra=header[header.index('class FFmpegExtraData'):header.index('FFmpegExtraData GetPacketExtradata')]
        extra+=ff[ff.index('FFmpegExtraData::FFmpegExtraData(size_t'):ff.index('FFmpegExtraData GetPacketExtradata')]
        extra+='FFmpegExtraData GetPacketExtradata(const AVPacket* pkt,const AVCodecParameters* codecPar)'+body(ff,'FFmpegExtraData GetPacketExtradata')
        join=native[native.index('void CDVDDemuxFFmpeg::InitBlurayDovi('):native.index('\n#endif',native.index('void CDVDDemuxFFmpeg::InitBlurayDovi('))]
        add=native[native.index('CDemuxStream* CDVDDemuxFFmpeg::AddStream(int streamIdx)'):]
        add=add[:add.index('  CDemuxStream* stream =')]
        program=r'''
#define HAVE_DVBRIDGE 1
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
#include <climits>
#include <string>
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/dovi_meta.h>
}
enum {LOGINFO,LOGWARNING,LOGERROR,LOGDEBUG,DVDSTREAM_TYPE_BLURAY};
struct CLog {template<class... T>static void Log(T&&...){} template<class... T>static void LogF(T&&...){} };
EXTRA_DATA
struct Settings {int GetInt(const char*){return 0;}};
struct Component {Settings* GetSettings(){static Settings s;return &s;}};
struct CServiceBroker {static Component* GetSettingsComponent(){static Component c;return &c;}};
struct Input {bool IsStreamType(int){return false;}};
struct CDemuxStream {FFmpegExtraData extraData;};
struct CDemuxParserFFmpeg {
 AVCodecParserContext* m_parserCtx{};AVCodecContext* m_codecCtx{};
 ~CDemuxParserFFmpeg(){av_parser_close(m_parserCtx);avcodec_free_context(&m_codecCtx);}
};
struct CDVDDemuxFFmpeg {
 AVFormatContext* m_pFormatContext{};bool m_bMatroska{};Input input;Input* m_pInput{&input};
 std::unique_ptr<CBlurayDovi> m_blurayDovi;int m_blurayBase{-1},m_blurayEnhancement{-1};
 unsigned m_doviGroups=0;bool m_blurayAwaitBase=false;
 std::map<int,std::unique_ptr<CDemuxParserFFmpeg>> m_parsers;
 std::map<int,CDemuxStream> streams;
 struct AVCodecParametersDeleter {void operator()(AVCodecParameters* p)const{avcodec_parameters_free(&p);}};
 void InitBlurayDovi(unsigned);int ReadBlurayDovi(AVPacket*);void ParsePacket(AVPacket*);
 CDemuxStream* AddStream(int);CDemuxStream* GetStream(int i){auto it=streams.find(i);return it==streams.end()?nullptr:&it->second;}
};
JOIN_CODE
void CDVDDemuxFFmpeg::ParsePacket(AVPacket* pkt) PARSE_BODY
ADD_PREFIX
 auto& stream=streams[streamIdx];
 stream.extraData=FFmpegExtraData(pStream->codecpar->extradata,pStream->codecpar->extradata_size);
 return &stream; // Unchanged stream-construction boundary.
 }
 return nullptr;
}
int main(int argc,char** argv){
 assert(argc==2);av_log_set_level(AV_LOG_ERROR);
 assert(av_bsf_get_by_name("extract_extradata") && "Native header extraction must be available");
 CDVDDemuxFFmpeg d;assert(avformat_open_input(&d.m_pFormatContext,argv[1],nullptr,nullptr)==0);
 d.InitBlurayDovi(UINT_MAX);assert(d.m_blurayDovi);
 auto* cp=d.m_pFormatContext->streams[d.m_blurayBase]->codecpar;
 assert(!cp->extradata && "Parameter sets are in-band, not in hvcC");
 assert(!d.AddStream(d.m_blurayBase) && "Do not publish an unopenable HEVC stream");
 assert(!d.AddStream(d.m_blurayEnhancement));
 AVPacket* packet=av_packet_alloc();assert(packet && d.ReadBlurayDovi(packet)==0);
 const std::vector<uint8_t> original(packet->data,packet->data+packet->size);
 const int64_t pts=packet->pts,dts=packet->dts;
 d.ParsePacket(packet);
 assert(cp->extradata && cp->extradata_size>23 && cp->extradata[0]==0);
 assert(cp->width==64 && cp->height==64);
 auto* visible=d.AddStream(d.m_blurayBase);assert(visible && visible->extraData);
 assert(visible->extraData.GetSize()==unsigned(cp->extradata_size));
 assert(!memcmp(visible->extraData.GetData(),cp->extradata,cp->extradata_size));
 assert(packet->pts==pts && packet->dts==dts && packet->size==int(original.size()));
 assert(!memcmp(packet->data,original.data(),original.size()) && "Native parser must preserve the first joined AU");
 assert(cp->nb_coded_side_data>=2 && d.m_pFormatContext->streams[d.m_blurayEnhancement]->discard==AVDISCARD_NONE);
 // Missing headers must not become an invented valid configuration.
 d.streams.clear();av_freep(&cp->extradata);cp->extradata_size=0;
 const uint8_t noHeaders[]={0,0,0,1,0x26,1,0xaa};
 av_packet_unref(packet);assert(av_new_packet(packet,sizeof(noHeaders))==0);
 memcpy(packet->data,noHeaders,sizeof(noHeaders));packet->stream_index=d.m_blurayBase;
 d.ParsePacket(packet);assert(!cp->extradata && !d.AddStream(d.m_blurayBase));
 av_packet_free(&packet);avformat_close_input(&d.m_pFormatContext);
}
'''.replace('EXTRA_DATA',extra).replace('JOIN_CODE',join).replace('PARSE_BODY',body(native,'void CDVDDemuxFFmpeg::ParsePacket(')).replace('ADD_PREFIX',add)
        # A tiny generated HEVC picture with VPS/SPS/PPS in-band, no source media.
        packet=base64.b64decode('AAAAF0ABDAH//wQIAAADAJ+oAAADAAAeugJAAAAAJ0IBAQQIAAADAJ+oAAADAAAeoCCBBZbpKTC8BaAgAAADACAAAAMAIQAAAAZEAcBxgRIAAAALKAGt4NEXznMji4A=')
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);source=folder/'check.cpp';source.write_text(program)
            sample=folder/'inband.mp4';sample.write_bytes(mp4('paired',[packet,packet+b'\0\0\0\3\x7c\1\xcc'],sample_entry=b'hev1'))
            binary=folder/'check'
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined','-I'+str(TREE/'xbmc'),
                '-I'+prefix+'/include',str(source),'-L'+prefix+'/lib','-lavformat','-lavcodec','-lavutil','-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(binary),str(sample)],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)


if __name__=='__main__':unittest.main()
