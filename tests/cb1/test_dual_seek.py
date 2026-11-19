"""Run the production transport-seek branch, including its timestamp fallback."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class DualSeek(unittest.TestCase):
    def test_proved_prefix_survives_sparse_keys_without_starving_local_seek(self):
        prefix=os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:self.skipTest('Matched FFmpeg headers/libraries required')
        repo=Path(__file__).resolve().parents[2]
        program=r'''
#include <assert.h>
#include <string.h>
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include "synthetic_idr.h"
static int scenario, reads, calls, prefix_reads;
static int64_t current,origin;
static int fake_seek(AVFormatContext* f,int stream,int64_t pts,int flags) {
 (void)f;(void)stream;(void)flags;calls++;reads=0;current=pts;
 return scenario==1&&pts==origin?-1:0;
}
static int fake_read(AVFormatContext* f,AVPacket* p) {
 (void)f;
 if(reads++ && !(scenario==2&&current==origin))return AVERROR_EOF;
 if(current==origin)prefix_reads++;
 assert(av_new_packet(p,sizeof(synthetic_paired))==0);
 memcpy(p->data,synthetic_paired,sizeof(synthetic_paired));
 p->stream_index=0;p->pts=p->dts=current;p->pos=123;return 0;
}
static int fake_parse(AVCodecParserContext* parser,AVCodecContext* context,
 uint8_t** out,int* size,const uint8_t* data,int bytes,int64_t pts,int64_t dts,int64_t pos) {
 (void)context;(void)pts;(void)dts;(void)pos;
 parser->key_frame=scenario==3 || (scenario==0&&current==origin) ||
                   ((scenario==1||scenario==2)&&current==233000+origin);
 parser->output_picture_number=0;*out=(uint8_t*)data;*size=bytes;return bytes;
}
#define av_seek_frame fake_seek
#define av_read_frame fake_read
#define av_parser_parse2 fake_parse
#include "dvbridge_fel_seek.h"
int main(void) {
 AVFormatContext* f=avformat_alloc_context();assert(f);
 AVStream* stream=avformat_new_stream(f,NULL);assert(stream);
 stream->time_base=(AVRational){1,1000};stream->start_time=0;
 stream->codecpar->codec_id=AV_CODEC_ID_HEVC;stream->codecpar->codec_type=AVMEDIA_TYPE_VIDEO;
 const int64_t origins[]={-2000,0,4200000};
 for(unsigned i=0;i<3;i++)for(scenario=0;scenario<4;scenario++) {
  stream->start_time=origin=origins[i];
  reads=calls=prefix_reads=0;
  int64_t position=-1,anchor=dvbridge_fel_seek_point_at(f,0,235000+origin,&position,NULL);
  if(scenario==0)assert(anchor==origin); /* no later common key, never invent one */
  if(scenario==1)assert(anchor==233000+origin); /* optional prefix seek can fail */
  if(scenario==2)assert(anchor==233000+origin&&prefix_reads>0&&prefix_reads<=1500);
  if(scenario==3)assert(anchor==235000+origin&&calls==1); /* native fast case */
 }
 avformat_free_context(f);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.c').write_text(program)
            command=['cc','-std=c11','-fsanitize=address,undefined',str(root/'test.c'),
                '-I'+str(repo/'CB1/src'),'-I'+str(repo/'CB1/tests'),'-I'+str(Path(prefix)/'include'),
                '-L'+str(Path(prefix)/'lib'),'-lavformat','-lavcodec','-lavutil','-o',str(root/'test')]
            compiled=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            executed=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(executed.returncode,0,executed.stdout+executed.stderr)

    def test_native_preroll_default_and_multi_source_delegation(self):
        directory=TREE/'xbmc/cores/VideoPlayer/DVDDemuxers'
        base=body((directory/'DVDDemux.h').read_text(),'virtual bool HasSeekPreroll(')
        ffmpeg=body((directory/'DVDDemuxFFmpeg.h').read_text(),'bool HasSeekPreroll(')
        multi=(directory/'DemuxMultiSource.h').read_text()
        override='bool HasSeekPreroll() const override '+body(multi,'bool HasSeekPreroll(') if 'bool HasSeekPreroll(' in multi else ''
        program=r'''
#include <cassert>
#include <map>
#include <memory>
struct Demux{virtual bool HasSeekPreroll()const BASE};
struct Native:Demux{bool m_seekPreroll=false;bool HasSeekPreroll()const override FFMPEG};
struct Multi:Demux{std::map<int,std::shared_ptr<Demux>>m_demuxerMap;MULTI};
int main(){
 Demux vanilla;assert(!vanilla.HasSeekPreroll());Multi empty;assert(!empty.HasSeekPreroll());
 auto video=std::make_shared<Native>(),audio=std::make_shared<Native>();
 Multi m;m.m_demuxerMap={{0,video},{1,audio}};
 for(int flags=0;flags<4;++flags){
  video->m_seekPreroll=flags&1;audio->m_seekPreroll=flags&2;
  assert(m.HasSeekPreroll()==bool(flags));
 }
 video->m_seekPreroll=audio->m_seekPreroll=false;assert(!m.HasSeekPreroll());
}
'''.replace('BASE',base).replace('FFMPEG',ffmpeg).replace('MULTI',override)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_deliberate_preroll_keeps_target_for_every_native_stream(self):
        native=body((TREE/'xbmc/cores/VideoPlayer/VideoPlayer.cpp').read_text(),
                    'bool CVideoPlayer::CheckPlayerInit(')
        program=r'''
#include <cassert>
#include <initializer_list>
constexpr double DVD_NOPTS_VALUE=-1e100;
constexpr int LOGDEBUG=0;
#define DVD_SEC_TO_TIME(t) ((t)*1000000.0)
struct CLog{template<class... T> static void Log(T...) {}};
struct CCurrentStream {bool inited=false;double dts=2000000,startpts=DVD_NOPTS_VALUE;int player=0;};
struct Demuxer {bool preroll=false;bool HasSeekPreroll()const{return preroll;}};
struct CVideoPlayer {
 Demuxer demuxer;Demuxer* m_pDemuxer=&demuxer;
 CCurrentStream m_CurrentAudio,m_CurrentVideo,m_CurrentSubtitle,m_CurrentTeletext,m_CurrentRadioRDS,m_CurrentAudioID3;
 bool CheckPlayerInit(CCurrentStream& current) BODY
};
int main(){
 for(bool preroll:{false,true})for(double target:{45000000.,120000000.})for(int first=0;first<6;++first){
  CVideoPlayer p;
  CCurrentStream* streams[]={&p.m_CurrentAudio,&p.m_CurrentVideo,&p.m_CurrentSubtitle,
      &p.m_CurrentTeletext,&p.m_CurrentRadioRDS,&p.m_CurrentAudioID3};
  for(auto* s:streams)s->startpts=target;
  p.demuxer.preroll=preroll;
  assert(p.CheckPlayerInit(*streams[first])==preroll);
  for(auto* s:streams)assert(s->startpts==(preroll?target:2000000.));
  if(preroll){
   for(auto* s:streams){s->dts=target;assert(!p.CheckPlayerInit(*s));assert(s->inited);}
  }
 }
 CVideoPlayer external;
 external.demuxer.preroll=true;
 external.m_CurrentVideo.startpts=external.m_CurrentSubtitle.startpts=120000000.;
 assert(external.CheckPlayerInit(external.m_CurrentSubtitle));
 assert(external.m_CurrentSubtitle.startpts==120000000. && external.m_CurrentVideo.startpts==120000000.);
}
'''.replace('BODY',native)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_joined_probe_does_not_require_display_admission(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text()
        start=source.index('          if (hints.dovi.dv_profile != 7')
        end=source.index('          AVStream* video',start)
        guard=source[start:end].replace('continue;', 'return false;')
        program=r'''
#include <cassert>
#include <initializer_list>
struct Hint {struct {int dv_profile;bool el_present_flag;} dovi;};
bool retain;
namespace DVBRIDGE {bool RetainsDVSource(const Hint&){return retain;}}
bool admits(const Hint& hints,bool m_blurayDovi){
GUARD
 return true;
}
int main(){
 for(int profile:{5,7})for(bool el:{false,true})
 for(bool joined:{false,true})for(bool display:{false,true}){
  retain=display;
  assert(admits(Hint{{profile,el}},joined)==(profile==7 && el && (joined||display)));
 }
}
'''.replace('GUARD',guard)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_transport_anchor_and_vanilla_fallback(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text()
        start=source.index('      // A transport PCR seek may land after the layer IRAP')
        end=source.index('\n    }',start)
        branch=source[start:end]
        program=r'''
#include <cassert>
#include <cstring>
constexpr int AVIO_SEEKABLE_NORMAL=1,AVSEEK_FLAG_BYTE=2,AVSEEK_FLAG_BACKWARD=4;
struct IO {int seekable;};struct Format {const char* name;};
struct Context {IO* pb;Format* iformat;};
int calls,flags[2],streams[2];long long positions[2];bool fail;
int av_seek_frame(Context*,int stream,long long position,int flag){
 streams[calls]=stream;positions[calls]=position;flags[calls++]=flag;
 return flag==AVSEEK_FLAG_BYTE && fail ? -1 : 0;
}
int main(){
 for(bool enabled:{false,true})for(bool seekable:{false,true})
 for(bool transport:{false,true})for(bool found:{false,true})for(bool failure:{false,true}){
  IO io{seekable?1:0};Format format{transport?"mpegts":"mov"};Context context{&io,&format};
  auto* m_pFormatContext=&context;bool m_blurayDovi=enabled;int m_seekStream=-1;
  long long layerPosition=found?123456:-1,seek_pts=900000;bool backwards=true;int ret=0;
  calls=0;fail=failure;
#ifdef HAVE_DVBRIDGE
BRANCH
#ifdef HAVE_DVBRIDGE
  bool use=enabled && seekable && transport && found;
#else
  bool use=false;
#endif
  assert(ret==0 && calls==(use && failure?2:1));
  assert(flags[0]==(use?AVSEEK_FLAG_BYTE:AVSEEK_FLAG_BACKWARD));
  assert(positions[0]==(use?123456:900000));
  if(calls==2)assert(flags[1]==AVSEEK_FLAG_BACKWARD && positions[1]==900000);
 }
}
'''.replace('BRANCH',branch).replace('#include <cstring>','#include <cstring>\n#include <initializer_list>')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            for definitions in ([],['-DHAVE_DVBRIDGE']):
                build=subprocess.run(['c++',*definitions,'-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
                self.assertEqual(build.returncode,0,build.stderr)
                run=subprocess.run([str(root/'test')],capture_output=True,text=True)
                self.assertEqual(run.returncode,0,run.stderr)
