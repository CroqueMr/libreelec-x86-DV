"""Run the production transport-seek branch, including its timestamp fallback."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class DualSeek(unittest.TestCase):
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
