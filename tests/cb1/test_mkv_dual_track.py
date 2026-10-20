"""Exercise real Matroska groups, Kodi admission and HEVC packet normalization."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


def matroska(tracks, el=-1):
    def raw(n):
        return n.to_bytes(max(1, (n.bit_length()+7)//8), 'big')
    def element(n, data):
        size = (0x80 | len(data)).to_bytes(1, 'big') if len(data)<127 else (0x4000 | len(data)).to_bytes(2, 'big')
        return raw(n)+size+data
    def number(n, value):
        return element(n, raw(value))
    entries = b''
    for i in range(tracks):
        hvcc = bytes([1])+bytes(20)+bytes([3, 0])
        entry = number(0xd7,i+1)+number(0x73c5,100+i)+number(0x83,1)
        entry += element(0x86,b'V_MPEGH/ISO/HEVC')+element(0x63a2,hvcc)
        entry += element(0xe0,number(0xb0,1920 if i else 3840)+number(0xba,1080 if i else 2160))
        if i==el:
            flags = (7<<9)|(6<<3)|7
            config = bytes([1,0,flags>>8,flags&255,0x60])+bytes(19)
            entry += element(0x41e4,number(0x41e7,0x64766343)+element(0x41ed,config))
        entries += element(0xae,entry)
    header = number(0x4286,1)+number(0x42f7,1)+number(0x42f2,4)+number(0x42f3,8)
    header += element(0x4282,b'matroska')+number(0x4287,4)+number(0x4285,2)
    # Tiny framing fixtures, not decodable or third-party video.
    cluster = number(0xe7,0)
    for i in range(tracks):
        cluster += element(0xa3,bytes([0x81+i,0,0,0x80,0,0,0,3,0x26,1,0x55]))
    return element(0x1a45dfa3,header)+element(0x18538067,
        element(0x1549a966,number(0x2ad7b1,1000000))+element(0x1654ae6b,entries)+element(0x1f43b675,cluster))


class MatroskaDualTrack(unittest.TestCase):
    def test_group_admission_normalized_layers_and_vanilla_rejection(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX') or not os.environ.get('FFMPEG_MATCHED_SOURCE'):
            self.skipTest('Matched FFmpeg libraries and BSF producer source required')
        prefix=Path(os.environ['FFMPEG_TEST_PREFIX'])
        ff=Path(os.environ['FFMPEG_MATCHED_SOURCE'])
        code=(TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text()
        start=code.index('void CDVDDemuxFFmpeg::InitBlurayDovi(')
        end=code.index('int CDVDDemuxFFmpeg::ReadBlurayDovi(',start)
        add_start=code.index('CDemuxStream* CDVDDemuxFFmpeg::AddStream(int streamIdx)')
        add_end=code.index('  AVStream* pStream =',add_start)
        add_prefix=code[add_start:add_end]
        program=r'''
#define HAVE_DVBRIDGE 1
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <climits>
#include <cassert>
extern "C" {
#include <libavformat/avformat.h>
#include <libavutil/dovi_meta.h>
#include <libavcodec/bsf_internal.h>
extern const FFBitStreamFilter ff_hevc_mp4toannexb_bsf;
const AVBitStreamFilter* __real_av_bsf_get_by_name(const char*);
const AVBitStreamFilter* __wrap_av_bsf_get_by_name(const char* name) {
  // Use the unchanged real filter if the minimal host prefix omitted its registration.
  const auto* filter=__real_av_bsf_get_by_name(name);
  return filter?filter:!strcmp(name,"hevc_mp4toannexb")?&ff_hevc_mp4toannexb_bsf.p:nullptr;
}
}
enum {DVDSTREAM_TYPE_BLURAY=1};
enum {LOGINFO,LOGWARNING,LOGERROR};
struct CLog {template<class... T> static void Log(T&&...) {}};
static int mode;
struct Settings {int GetInt(const char*) {return mode;}};
struct Component {Settings* GetSettings(){static Settings s;return &s;}};
struct CServiceBroker {static Component* GetSettingsComponent(){static Component c;return &c;}};
struct Input {bool IsStreamType(int){return false;}};
struct CDemuxStream {int index;};
struct CDVDDemuxFFmpeg {
  AVFormatContext* m_pFormatContext{};bool m_bMatroska{true};Input input;Input* m_pInput{&input};
  std::unique_ptr<CBlurayDovi> m_blurayDovi;int m_blurayBase{-1},m_blurayEnhancement{-1};
  struct AVCodecParametersDeleter {void operator()(AVCodecParameters* p)const{avcodec_parameters_free(&p);}};
  void InitBlurayDovi(unsigned int program);
  CDemuxStream* AddStream(int streamIdx);
};
'''+code[start:end]+add_prefix+r'''
  return new CDemuxStream{streamIdx}; // Unchanged downstream stream construction boundary.
}
int main(int argc,char**argv) {
 assert(argc==5);av_log_set_level(AV_LOG_QUIET);
 for(int sample=1;sample<5;sample++)for(int disabled=0;disabled<2;disabled++) {
  CDVDDemuxFFmpeg d;assert(avformat_open_input(&d.m_pFormatContext,argv[sample],nullptr,nullptr)==0);
  mode=disabled?2:0;d.InitBlurayDovi(UINT_MAX);
  if(sample!=1 || disabled){assert(!d.m_blurayDovi);avformat_close_input(&d.m_pFormatContext);continue;}
  assert(d.m_blurayDovi && "MKV Dolby layer group must reach the existing assembler");
  d.InitBlurayDovi(UINT_MAX); // Stream-list rebuild must retain original container framing.
  assert(d.m_blurayDovi);
  assert(d.m_blurayBase==0 && d.m_blurayEnhancement==1);
  auto* visible=d.AddStream(0);assert(visible && visible->index==0);delete visible;
  auto* hidden=d.AddStream(1);assert(!hidden && "Consumed EL must not be exposed as selectable video");
  assert(d.m_pFormatContext->streams[1]->discard==AVDISCARD_NONE);
  const auto* bl=d.m_pFormatContext->streams[0]->codecpar;
  const auto* config=av_packet_side_data_get(bl->coded_side_data,bl->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF);
  assert(config && config->size>=sizeof(AVDOVIDecoderConfigurationRecord));
  const auto* dv=reinterpret_cast<const AVDOVIDecoderConfigurationRecord*>(config->data);
  assert(dv->dv_profile==7 && dv->dv_level==6 && dv->dv_bl_signal_compatibility_id==6);
  assert(dv->rpu_present_flag && dv->el_present_flag && dv->bl_present_flag);
  assert(bl->extradata_size==0 || bl->extradata[0]!=1); // Annex-B combined decoder input.
  const auto* el=av_packet_side_data_get(bl->coded_side_data,bl->nb_coded_side_data,AV_PKT_DATA_HEVC_CONF);
  assert(el && el->size==23 && el->data[0]==1); // Keep original EL hvcC for dovi_split.
  AVPacket *base=av_packet_alloc(),*layer=av_packet_alloc(),*out=av_packet_alloc();
  assert(base && layer && out && av_new_packet(base,7)==0 && av_new_packet(layer,14)==0);
  const unsigned char b[]={0,0,0,3,0x26,1,0xaa};
  const unsigned char e[]={0,0,0,3,0x26,1,0xbb,0,0,0,3,0x7c,1,0xcc};
  memcpy(base->data,b,7);memcpy(layer->data,e,14);
  for(int epoch=0;epoch<2;epoch++) {
   d.m_blurayDovi->Reset(epoch!=0);
   for(int frame=0;frame<3;frame++) {
    base->pts=layer->pts=100+frame;base->dts=layer->dts=90+frame;
    base->duration=layer->duration=1;base->flags=layer->flags=AV_PKT_FLAG_KEY;
    assert(d.m_blurayDovi->Push(base,false) && d.m_blurayDovi->Push(layer,true));
    assert(d.m_blurayDovi->Take(out)==0);
    const unsigned char expected[]={0,0,0,1,0x26,1,0xaa,0,0,0,1,0x7e,1,0x26,1,0xbb,0,0,0,1,0x7c,1,0xcc};
    assert(out->size==sizeof(expected) && !memcmp(out->data,expected,sizeof(expected)));
    assert(out->pts==base->pts && out->dts==base->dts && out->duration==1 && (out->flags&AV_PKT_FLAG_KEY));
    av_packet_unref(out);
   }
  }
  av_packet_free(&base);av_packet_free(&layer);av_packet_free(&out);
  mode=2;d.InitBlurayDovi(UINT_MAX);assert(!d.m_blurayDovi);
  assert(bl->extradata_size==23 && bl->extradata[0]==1);
  assert(!av_packet_side_data_get(bl->coded_side_data,bl->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF));
  avformat_close_input(&d.m_pFormatContext);
 }
 // Both layers must belong to the selected program.
 CDVDDemuxFFmpeg d;assert(avformat_open_input(&d.m_pFormatContext,argv[1],nullptr,nullptr)==0);
 AVProgram* p=av_new_program(d.m_pFormatContext,1);assert(p);av_program_add_stream_index(d.m_pFormatContext,1,0);
 mode=0;d.InitBlurayDovi(0);assert(!d.m_blurayDovi);avformat_close_input(&d.m_pFormatContext);
 // Exact layer-clock conversion and malformed framing use the same packet path.
 AVCodecParameters *base=avcodec_parameters_alloc(),*el=avcodec_parameters_alloc();assert(base && el);
 base->codec_type=el->codec_type=AVMEDIA_TYPE_VIDEO;base->codec_id=el->codec_id=AV_CODEC_ID_HEVC;
 for(int length : {1,2,4}) {
  for(auto* cp : {base,el}) {
   av_freep(&cp->extradata);cp->extradata_size=31;cp->extradata=(uint8_t*)av_mallocz(31+AV_INPUT_BUFFER_PADDING_SIZE);
   cp->extradata[0]=1;cp->extradata[21]=length-1;cp->extradata[22]=1;
   const uint8_t vps[]={32,0,1,0,3,0x40,1,uint8_t(cp==base?0xa1:0xb1)};
   memcpy(cp->extradata+23,vps,sizeof(vps));
  }
  CBlurayDovi pair;assert(pair.Configure(base,el,{1,1000},{1,1000000}));
  const uint8_t expectedVps[]={0,0,0,1,0x40,1,0xa1};
  assert(pair.BaseParameters()->extradata_size==sizeof(expectedVps));
  assert(!memcmp(pair.BaseParameters()->extradata,expectedVps,sizeof(expectedVps)));
  AVPacket *b=av_packet_alloc(),*e=av_packet_alloc(),*out=av_packet_alloc();
  assert(b && e && out && av_new_packet(b,length+3)==0 && av_new_packet(e,2*(length+3))==0);
  memset(b->data,0,b->size);memset(e->data,0,e->size);
  b->data[length-1]=e->data[length-1]=e->data[2*length+2]=3;
  memcpy(b->data+length,"\x26\x01\xaa",3);
  memcpy(e->data+length,"\x26\x01\xbb",3);memcpy(e->data+2*length+3,"\x7c\x01\xcc",3);
  b->pts=42;b->dts=40;b->duration=2;e->pts=42000;e->dts=40000;e->duration=2000;
  assert(pair.Push(b,false) && pair.Push(e,true) && pair.Take(out)==0);
  assert(out->pts==42 && out->dts==40 && out->duration==2);
  assert(!memcmp(out->data,expectedVps,sizeof(expectedVps)));
  assert(out->data[out->size-1]==0xcc);av_packet_unref(out);
  pair.Reset();
  e->data[length-1]=100;assert(!pair.Push(e,true));
  assert(!strcmp(pair.LastError(),"hevc-normalization"));
  pair.Reset();e->data[length-1]=3;e->pts=42001;
  assert(!pair.Push(e,true) && !strcmp(pair.LastError(),"layer-time-base"));
  av_packet_free(&b);av_packet_free(&e);av_packet_free(&out);
 }
 avcodec_parameters_free(&base);avcodec_parameters_free(&el);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            inputs=[('paired',2,1),('independent',2,-1),('ambiguous',3,1),('single',1,0)]
            for name,n,el in inputs:
                (root/(name+'.mkv')).write_bytes(matroska(n,el))
            source=root/'test.cpp';source.write_text(program)
            obj=root/'hevc.o'
            compile_filter=subprocess.run(['cc','-fsanitize=address,undefined','-I'+str(ff),'-c',
                str(ff/'libavcodec/bsf/hevc_mp4toannexb.c'),'-o',str(obj)],capture_output=True,text=True)
            self.assertEqual(compile_filter.returncode,0,compile_filter.stderr)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined','-I'+str(TREE/'xbmc'),
                '-I'+str(prefix/'include'),'-I'+str(ff),str(source),str(obj),'-Wl,--wrap=av_bsf_get_by_name',
                '-L'+str(prefix/'lib'),'-lavformat','-lavcodec','-lavutil','-lm','-latomic','-pthread','-o',str(root/'check')],
                capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'check'),*[str(root/(name+'.mkv')) for name,_,_ in inputs]],
                capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
