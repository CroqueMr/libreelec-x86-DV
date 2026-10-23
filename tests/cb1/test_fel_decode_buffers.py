"""Run native VAAPI allocation and pool consumers with delayed exact FEL pairing.

Removing the FEL-only reserve must strand BL eight before its EL can arrive;
native playback and the existing AI allocation must keep their original budgets.
Only VA/FFmpeg allocation and refcount APIs are replaced: pool decisions run as
shipped, without a display, decoder device, or playback settings.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class FELDecodeBufferTests(unittest.TestCase):
    def test_paired_layers_skip_late_output_not_layer_decoding(self):
        source = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        function = body(source, 'void CDVDVideoCodecFFmpeg::SetCodecControl(int flags)')
        drop = 'if (m_codecControlFlags & DVD_CODEC_CTRL_DROP)'+body(source,
            'if (m_codecControlFlags & DVD_CODEC_CTRL_DROP)')
        forwards=re.findall(r'int flags = m_codecControlFlags;.*?m_pHardware->SetCodecControl\(flags\);',
                            body(source,'CDVDVideoCodec::VCReturn CDVDVideoCodecFFmpeg::GetBasePicture('),re.S)
        self.assertEqual(len(forwards),2)
        program = r'''
#include <cassert>
#define HAVE_DVBRIDGE 1
constexpr int DVD_CODEC_CTRL_DROP_ANY=1,DVD_CODEC_CTRL_DROP=2,DVD_CODEC_CTRL_HURRY=4;
constexpr int DVD_CODEC_CTRL_DRAIN=128;
constexpr int AVDISCARD_DEFAULT=0,AVDISCARD_NONREF=8;
constexpr int DVP_FLAG_DROPPED=32;
struct VideoPicture {int iFlags=0;};
struct AVCodecContext {int skip_frame=0,skip_idct=0,skip_loop_filter=0;};
struct Hardware {
 bool deint=false;int flags=-1;
 bool CanSkipDeint(){return deint;}
 void SetCodecControl(int value){flags=value;}
};
struct CDVDVideoCodecFFmpeg {
 AVCodecContext context;AVCodecContext* m_pCodecContext=&context;
 Hardware hardware;Hardware* m_pHardware=&hardware;
 bool m_dvFel=false,m_requestSkipDeint=false;int m_codecControlFlags=-1;
 void SetCodecControl(int flags) FUNCTION
 void Forward(){FORWARD}
 void Drain(){DRAIN}
 bool Dropped()const {VideoPicture picture;auto* pVideoPicture=&picture;DROP_BLOCK;return picture.iFlags&DVP_FLAG_DROPPED;}
};
int main(){
 for(bool paired:{false,true})for(bool deint:{false,true}){
  CDVDVideoCodecFFmpeg codec;codec.m_dvFel=paired;codec.hardware.deint=deint;
  codec.SetCodecControl(DVD_CODEC_CTRL_DROP_ANY|DVD_CODEC_CTRL_HURRY);
  const int expected=paired || deint?AVDISCARD_DEFAULT:AVDISCARD_NONREF;
  assert(codec.context.skip_frame==expected && codec.context.skip_idct==expected &&
         codec.context.skip_loop_filter==expected);
  assert(codec.m_codecControlFlags==(DVD_CODEC_CTRL_DROP_ANY|DVD_CODEC_CTRL_HURRY));
  assert(codec.hardware.flags==(paired?DVD_CODEC_CTRL_HURRY:codec.m_codecControlFlags));
  codec.Forward();
  assert(codec.hardware.flags==(paired?DVD_CODEC_CTRL_HURRY:codec.m_codecControlFlags));
  codec.Drain();
  assert(codec.hardware.flags==((paired?DVD_CODEC_CTRL_HURRY:codec.m_codecControlFlags)|DVD_CODEC_CTRL_DRAIN));
  assert(codec.m_requestSkipDeint==(!paired && deint));
  assert(!codec.Dropped());
  codec.SetCodecControl(DVD_CODEC_CTRL_DROP_ANY);
  assert(codec.m_codecControlFlags==DVD_CODEC_CTRL_DROP_ANY);
  assert(codec.hardware.flags==(paired?0:DVD_CODEC_CTRL_DROP_ANY));
  assert(!codec.Dropped());
  codec.SetCodecControl(DVD_CODEC_CTRL_DROP|DVD_CODEC_CTRL_HURRY);
  assert(codec.hardware.flags==(DVD_CODEC_CTRL_DROP|DVD_CODEC_CTRL_HURRY));
  assert(codec.context.skip_frame==AVDISCARD_DEFAULT);
  assert(codec.Dropped());
  codec.context.skip_frame=codec.context.skip_idct=codec.context.skip_loop_filter=AVDISCARD_NONREF;
  codec.m_dvFel=true;
  codec.SetCodecControl(DVD_CODEC_CTRL_DROP_ANY|DVD_CODEC_CTRL_HURRY|8|16);
  assert(codec.m_codecControlFlags==(DVD_CODEC_CTRL_DROP_ANY|DVD_CODEC_CTRL_HURRY|8|16));
  assert(codec.hardware.flags==(DVD_CODEC_CTRL_HURRY|8|16));
  assert(codec.context.skip_frame==AVDISCARD_DEFAULT && codec.context.skip_idct==AVDISCARD_DEFAULT &&
         codec.context.skip_loop_filter==AVDISCARD_DEFAULT);
  assert(!codec.Dropped());
  codec.SetCodecControl(0);
  assert(codec.m_codecControlFlags==0 && codec.hardware.flags==0 && !codec.Dropped());
 }
 CDVDVideoCodecFFmpeg software;software.m_pHardware=nullptr;software.m_dvFel=true;
 software.SetCodecControl(DVD_CODEC_CTRL_DROP_ANY);
 assert(software.context.skip_frame==AVDISCARD_DEFAULT);
}
'''.replace('FUNCTION', function).replace('DROP_BLOCK',drop).replace('FORWARD',forwards[0]).replace('DRAIN}',forwards[1]+'}')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'test.cpp').write_text('#include <initializer_list>\n'+program)
            built = subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],
                                   capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran = subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_late_pair_drop_uses_current_picture_deadline(self):
        source = (TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        function = body(source, 'CVideoPlayerVideo::EOutputState CVideoPlayerVideo::OutputPicture(')
        start = function.rfind('#ifdef HAVE_DVBRIDGE', 0, function.index('  const bool latePairedPicture'))
        end = function.index('  auto timeToDisplay', start)
        program = r'''
#include <cassert>
#include <cmath>
#include <limits>
#include <initializer_list>
#define HAVE_DVBRIDGE 1
constexpr int DVD_NOPTS_VALUE=-1000,DVD_PLAYSPEED_NORMAL=1000,DVP_FLAG_DROPPED=32;
constexpr int DVD_CODEC_CTRL_DROP_ANY=64;
constexpr int LOGDEBUG=0,OUTPUT_DROPPED=1;
enum class ESyncState {SYNC_STARTING,SYNC_INSYNC};
struct VideoPicture {bool doviEnhancement=true;int iFlags=DVD_CODEC_CTRL_DROP_ANY;double pts=100,iDuration=10;};
struct CLog {template<class... T>static void Log(T...) {}};
struct Player {
 bool m_bAllowDrop=true;int m_speed=DVD_PLAYSPEED_NORMAL;ESyncState m_syncState=ESyncState::SYNC_INSYNC;
 struct Stats {int gains=0;void AddOutputDropGain(double,int n){gains+=n;}}m_droppingStats;
 int OutputPicture(const VideoPicture* pPicture,double iPlayingClock){
 DECISION
 return 0;}
};
int main(){
 for(bool paired:{false,true})for(double clock:{99.,100.,109.,110.,111.}){
  Player player;VideoPicture picture;picture.doviEnhancement=paired;
  assert(player.OutputPicture(&picture,clock)==(paired&&clock>=110));
  assert(player.m_droppingStats.gains==(paired&&clock>=110));
 }
 Player player;VideoPicture picture;
 for(int speed:{0,-1000,2000}){player.m_speed=speed;assert(!player.OutputPicture(&picture,200));}
 player.m_speed=DVD_PLAYSPEED_NORMAL;player.m_bAllowDrop=false;assert(!player.OutputPicture(&picture,200));
 player.m_bAllowDrop=true;player.m_syncState=ESyncState::SYNC_STARTING;assert(!player.OutputPicture(&picture,200));
 player.m_syncState=ESyncState::SYNC_INSYNC;picture.pts=DVD_NOPTS_VALUE;assert(!player.OutputPicture(&picture,200));
 picture.pts=100;picture.iDuration=0;assert(!player.OutputPicture(&picture,200));
 picture.iDuration=10;picture.iFlags=0;assert(!player.OutputPicture(&picture,200));
 picture.iFlags=DVD_CODEC_CTRL_DROP_ANY;picture.iDuration=std::numeric_limits<double>::infinity();
 assert(!player.OutputPicture(&picture,200));picture.iDuration=10;
 assert(!player.OutputPicture(&picture,std::numeric_limits<double>::quiet_NaN()));
 picture.iFlags=DVP_FLAG_DROPPED;assert(player.OutputPicture(&picture,50)==OUTPUT_DROPPED);
}
'''.replace('DECISION', function[start:end])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_delayed_el_does_not_starve_native_render_pool(self):
        base = TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        source = (base/'VAAPI.cpp').read_text()
        allocation = source.split('  // add an extra surface for safety,', 1)[1]
        allocation = allocation[allocation.index('  m_vaapiConfig.maxReferences += 6;'):]
        allocation = allocation.split('  if (!ConfigVAAPI())', 1)[0]
        budget = body((base/'HDR10AIBuffers.h').read_text(), 'struct HDR10AIBuffers')
        limit = re.search(r'static constexpr unsigned DVEnhancementPendingPictures\s*=\s*\d+;',
            (base/'DVDVideoCodecFFmpeg.h').read_text()).group()
        methods = '\n'.join(signature+body(source, signature) for signature in (
            'CVideoBuffer* CVaapiBufferPool::Get()',
            'bool CVaapiBufferPool::HasFree()',
            'void CVaapiBufferPool::Init(unsigned count)',
            'void CVaapiBufferPool::QueueReturnPicture(CVaapiRenderPicture *pic)',
            'CVaapiRenderPicture* CVaapiBufferPool::ProcessSyncPicture()'))
        work = 'bool COutput::HasWork()'+body(source, 'bool COutput::HasWork()')
        program = r'''
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <deque>
#include <vector>
#define HAVE_DVBRIDGE 1
AI_DEFINE
#define NUM_RENDER_PICS 7
namespace DVBRIDGE {
 enum class HDR10SourceMode {Native,ReferenceDV,EnhancedDV};
 struct HDR10AIActivation {static unsigned BufferCount(double) {return 24;}};
 struct HDR10AIBuffers BUDGET;
}
struct ICallbackHWAccel {
 virtual ~ICallbackHWAccel()=default;
 unsigned ai=6;
 unsigned GetHDR10AIBufferCount() const {return ai;}
};
struct CDVDVideoCodecFFmpeg : ICallbackHWAccel {
 LIMIT
 bool fel=false;
 bool NeedsDVEnhancement() const {return fel;}
};
struct AVCodecContext {void* opaque;};
struct Config {unsigned maxReferences=16,renderPictures=7;};
Config configure(CDVDVideoCodecFFmpeg& decoder) {
 AVCodecContext context{static_cast<ICallbackHWAccel*>(&decoder)};
 auto* avctx=&context;
 Config m_vaapiConfig;
 unsigned m_hdr10AIBuffers=6;
 ALLOCATION
 return m_vaapiConfig;
}
constexpr int LOGWARNING=0,LOGERROR=1,LOGDEBUG=2,LOGVIDEO=0;
struct CLog {template<class... T> static void Log(T...) {}};
struct CVideoBuffer {virtual ~CVideoBuffer()=default;void Acquire(void*) {}};
struct CVaapiRenderPicture : CVideoBuffer {
 explicit CVaapiRenderPicture(unsigned) {}
 void* avFrame=nullptr;
 unsigned renderBufferCount=6;
 bool valid=false;
};
void* av_frame_alloc() {static int allocation;return &allocation;}
struct Decoder {void Acquire() {}};
struct CVaapiBufferPool {
 Decoder m_vaapi;
 std::vector<CVaapiRenderPicture*> allRenderPics;
 std::deque<int> usedRenderPics,freeRenderPics,syncRenderPics;
 std::deque<int> processedPics,decodedPics;
 int procPicId=0;
 void* GetPtr() {return this;}
 CVideoBuffer* Get();bool HasFree();void Init(unsigned count);
 void QueueReturnPicture(CVaapiRenderPicture* pic);
 CVaapiRenderPicture* ProcessSyncPicture();
 ~CVaapiBufferPool() {for(auto* p:allRenderPics) delete p;}
};
METHODS
struct Postproc {bool WantsPic() {return true;}};
struct COutput {
 CVaapiBufferPool* m_bufferPool;Postproc* m_pp=nullptr;
 bool HasWork();
};
WORK
int main() {
 CDVDVideoCodecFFmpeg decoder;
 auto ordinary=configure(decoder);
 assert(ordinary.maxReferences==22 && ordinary.renderPictures==7);
 decoder.ai=24;
 auto ai=configure(decoder);
#ifdef CB1_HAS_HDR10_AI
 assert(ai.maxReferences==40 && ai.renderPictures==25);
#else
 assert(ai.maxReferences==22 && ai.renderPictures==7);
#endif
 decoder.ai=6;decoder.fel=true;
 auto fel=configure(decoder);
 CVaapiBufferPool pool;pool.Init(fel.renderPictures);
 pool.processedPics={1,2,3};
 COutput output{&pool};
 std::vector<CVaapiRenderPicture*> held;
 // No EL exists for the first BL until input eight. Each BL owns the actual
 // native output-pool slot while pairing waits, not a fictitious decode slot.
 for(unsigned i=0;i<8;++i) {
   auto* pic=dynamic_cast<CVaapiRenderPicture*>(pool.Get());
   if(!pic) {fprintf(stderr,"FEL starved at BL %u before delayed EL arrived\n",i+1);return 1;}
   pic->valid=true;held.push_back(pic);
 }
 assert(output.HasWork()); // proc=3 can progress; EL input is not blocked.
 // Release exactly the paired BL and verify the real native return queue
 // makes its slot available. No EL substitution or increased timeout.
 pool.QueueReturnPicture(held.front());
 assert(pool.ProcessSyncPicture()==held.front());
 held.erase(held.begin());
 // Worst bounded lookahead: sixteen unmatched BL plus seven unchanged native
 // downstream slots. Three already processed frames need an output slot to
 // progress, and must not block ingress before the pairing bound is reached.
 while(held.size()<22) {
   auto* pic=dynamic_cast<CVaapiRenderPicture*>(pool.Get());
   if(!pic) {fprintf(stderr,"FEL reserve exhausted at %zu held BL/render slots\n",held.size());return 2;}
   pic->valid=true;held.push_back(pic);
 }
 assert(output.HasWork()); // 16 pending + 6 downstream, one output slot left.
 auto* last=dynamic_cast<CVaapiRenderPicture*>(pool.Get());
 assert(last);last->valid=true;held.push_back(last);
 assert(!pool.HasFree());
 assert(!output.HasWork()); // Only normal downstream backpressure remains.
 pool.QueueReturnPicture(held.front());
 assert(pool.ProcessSyncPicture()==held.front() && pool.HasFree() && output.HasWork());
 assert(fel.maxReferences==38); // 16 HEVC + 6 native safety + 16 retained BL.
 puts("PASS: delayed EL at BL8; 16 pending BL + 7 native slots; native/AI unchanged");
}
'''.replace('BUDGET', budget).replace('ALLOCATION', allocation).replace('METHODS', methods)
        program = program.replace('LIMIT', limit).replace('WORK', work)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for ai_enabled in (False, True):
                with self.subTest(ai_enabled=ai_enabled):
                    (root/'test.cpp').write_text(program.replace('AI_DEFINE',
                        '#define CB1_HAS_HDR10_AI 1' if ai_enabled else ''))
                    built = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra',
                        str(root/'test.cpp'), '-o', str(root/'test')], capture_output=True, text=True)
                    self.assertEqual(built.returncode, 0, built.stderr)
                    ran = subprocess.run([str(root/'test')], capture_output=True, text=True)
                    self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
