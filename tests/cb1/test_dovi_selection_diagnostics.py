"""Selection diagnostics must explain rejection without pairing or leaking source URLs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class DoviSelectionDiagnostics(unittest.TestCase):
    def test_native_admission_reports_once_and_bounds_unassociated_inventory(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX') or not os.environ.get('CB1_FMT_INCLUDE'):
            self.skipTest('Matched FFmpeg and fmt headers required')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        source = (TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text()
        start = source.index('void CDVDDemuxFFmpeg::InitBlurayDovi(')
        end = source.index('int CDVDDemuxFFmpeg::ReadBlurayDovi(', start)
        program = r'''
#define FMT_HEADER_ONLY
#include <fmt/format.h>
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
#include <climits>
#include <string>
extern "C" {
#include <libavformat/avformat.h>
#include <libavutil/dovi_meta.h>
}
enum {DVDSTREAM_TYPE_BLURAY=1,LOGINFO,LOGWARNING,LOGERROR};
std::vector<std::string> logs;
struct CLog {
 template<class... T> static void Log(int,const char* pattern,T&&... args) {
  logs.push_back(fmt::format(fmt::runtime(pattern),std::forward<T>(args)...));
 }
};
int mode;
struct Settings {int GetInt(const char*){return mode;}};
struct Component {Settings* GetSettings(){static Settings s;return &s;}};
struct CServiceBroker {static Component* GetSettingsComponent(){static Component c;return &c;}};
struct Input {bool bluray{true};bool IsStreamType(int){return bluray;}};
struct CDVDDemuxFFmpeg {
 AVFormatContext* m_pFormatContext{avformat_alloc_context()};bool m_bMatroska{};
 Input input;Input* m_pInput{&input};std::unique_ptr<CBlurayDovi> m_blurayDovi;
 int m_blurayBase{-1},m_blurayEnhancement{-1};
 unsigned m_doviGroups=0;
 bool m_blurayAwaitBase=false;
 struct AVCodecParametersDeleter {void operator()(AVCodecParameters* p)const{avcodec_parameters_free(&p);}};
 void InitBlurayDovi(unsigned int);
 CDVDDemuxFFmpeg(){assert(m_pFormatContext);static const AVInputFormat format{.name="mpegts"};m_pFormatContext->iformat=&format;
  m_pFormatContext->url=av_strdup("http://private.example/t/SECRET_TOKEN/movie.iso");}
 ~CDVDDemuxFFmpeg(){m_blurayDovi.reset();avformat_free_context(m_pFormatContext);}
};
''' + source[start:end] + r'''
void streams(CDVDDemuxFFmpeg& d,int count){
 for(int i=0;i<count;i++){
  auto* s=avformat_new_stream(d.m_pFormatContext,nullptr);assert(s);
  s->id=0x1011+i*4;s->time_base={1,90000};
  s->codecpar->codec_type=AVMEDIA_TYPE_VIDEO;s->codecpar->codec_id=AV_CODEC_ID_HEVC;
  s->codecpar->codec_tag=MKTAG('h','v','c','1');
 }
}
void group(CDVDDemuxFFmpeg& d){
 auto* g=avformat_stream_group_create(d.m_pFormatContext,AV_STREAM_GROUP_PARAMS_DOLBY_VISION,nullptr);assert(g);
 for(int i=0;i<2;i++)assert(avformat_stream_group_add_stream(g,d.m_pFormatContext->streams[i])==0);
 g->params.layered_video->el_index=1;
}
void check(CDVDDemuxFFmpeg& d,const char* reason,int inventory,bool joined=false,const char* inventoryConfig=nullptr){
 logs.clear();d.InitBlurayDovi(UINT_MAX);assert(bool(d.m_blurayDovi)==joined);
 int summaries=0,rows=0,configurations=0;
 for(const auto& line:logs){
  assert(line.find("SECRET_TOKEN")==std::string::npos && line.find("private.example")==std::string::npos);
  if(line.starts_with("DV input selection:")){
   summaries++;assert(line.find(std::string("reason=")+reason)!=std::string::npos);
   assert(line.find("format=mpegts")!=std::string::npos && line.find("qualified_groups=")!=std::string::npos);
   if(joined)assert(line.find("BL=4113 EL=4117")!=std::string::npos);
  }
  if(line.starts_with("DV input stream:")){
   rows++;
   assert(line.find("codec_tag=0x31637668")!=std::string::npos);
   if(inventoryConfig && line.find("pid=4117 ")!=std::string::npos){
    configurations++;assert(line.find(inventoryConfig)!=std::string::npos);
   }
  }
 }
 assert(summaries==1 && "Every stream-list rebuild needs exactly one selection outcome");
 assert(rows==inventory && "Unassociated multi-HEVC inventory must be bounded to sixteen rows");
 assert(configurations==(inventoryConfig?1:0));
}
int main(){
 av_log_set_level(AV_LOG_QUIET);
 {CDVDDemuxFFmpeg d;streams(d,20);check(d,"no-dv-group",16);}
 {CDVDDemuxFFmpeg d;streams(d,1);check(d,"no-dv-group",0);}
 {CDVDDemuxFFmpeg d;streams(d,2);group(d);check(d,"joined",0,true);}
 {CDVDDemuxFFmpeg d;streams(d,2);group(d);d.m_pFormatContext->streams[1]->codecpar->codec_id=AV_CODEC_ID_H264;
  check(d,"invalid-layer-codecs",0);}
 {CDVDDemuxFFmpeg d;streams(d,2);group(d);d.input.bluray=false;
  auto* el=d.m_pFormatContext->streams[1]->codecpar;
  assert(av_packet_side_data_new(&el->coded_side_data,&el->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF,1,0));
  check(d,"truncated-dv-config",2,false,"dv_profile=0 dv_bl=0 dv_el=0 dv_rpu=0 extradata=0");}
 {CDVDDemuxFFmpeg d;streams(d,2);group(d);d.input.bluray=false;
  auto* el=d.m_pFormatContext->streams[1]->codecpar;
  auto* sd=av_packet_side_data_new(&el->coded_side_data,&el->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF,sizeof(AVDOVIDecoderConfigurationRecord),0);assert(sd);
  auto* config=(AVDOVIDecoderConfigurationRecord*)sd->data;*config={};config->dv_profile=8;config->el_present_flag=config->rpu_present_flag=1;
  check(d,"invalid-dv-config",2,false,"dv_profile=8 dv_bl=0 dv_el=1 dv_rpu=1 extradata=0");
  config->dv_profile=7;config->bl_present_flag=1;config->rpu_present_flag=0;
  check(d,"invalid-dv-config",2,false,"dv_profile=7 dv_bl=1 dv_el=1 dv_rpu=0 extradata=0");}
 {CDVDDemuxFFmpeg d;streams(d,2);group(d);group(d);d.input.bluray=false;check(d,"ambiguous-dv-groups",2);}
 {CDVDDemuxFFmpeg d;streams(d,2);group(d);mode=2;check(d,"output-disabled",2);mode=0;}
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder/'check.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'), '-I'+str(prefix/'include'),
                '-I'+os.environ['CB1_FMT_INCLUDE'], str(folder/'check.cpp'),
                '-L'+str(prefix/'lib'), '-lavformat', '-lavcodec', '-lavutil', '-lm',
                '-o', str(folder/'check')], text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(folder/'check')], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
