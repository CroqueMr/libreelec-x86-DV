# SPDX-License-Identifier: MIT
"""The renderer may hand off a committed HDR10-to-DV output on reconfiguration."""
import unittest

from test_ai_reentry import execute
from test_native_video_source import TREE, body


class HDR10DVHandoffTests(unittest.TestCase):
    def test_video_drains_before_waiting_for_outgoing_audio(self):
        source = (TREE / "xbmc/cores/VideoPlayer/VideoPlayer.cpp").read_text()
        handoff = body(source, "if(next == CDVDInputStream::NEXTSTREAM_OPEN)")
        execute(r'''
#include <cassert>
#include <memory>
#define CB1_HAS_HDR10_AI
struct CDVDMsg { enum { VIDEO_DRAIN }; explicit CDVDMsg(int) {} };
struct Player {
 enum { CACHESTATE_DONE, LOGINFO };
 struct Stream { bool inited=true; void Clear(){} };
 Stream m_CurrentAudio, m_CurrentVideo;
 struct { void reset(){} } m_syncStartPtsWait;
 struct { void Clear(){} } m_CurrentSubtitle;
 struct Renderer {
  bool ai=true;
  bool HDR10AILookahead(){return ai;}
 } m_renderManager;
 struct Video {
  int drains=0;
  void SendMessage(std::shared_ptr<CDVDMsg>){++drains;}
 } video, *m_VideoPlayerVideo=&video;
 struct CLog { static void Log(int,const char*){} };
 bool demuxClosed=false;
 int drainsAtAudioClose=-1;
 void CloseDemuxer(){demuxClosed=true;}
 void SetCaching(int){}
 void CloseStream(Stream& stream,bool wait) {
  assert(demuxClosed && wait);
  if (&stream==&m_CurrentAudio) drainsAtAudioClose=video.drains;
 }
 void Handoff() {
  for (int once=0;once<1;++once) HANDOFF
 }
};
int main() {
 Player ai;
 ai.Handoff(); assert(ai.drainsAtAudioClose==1 && ai.video.drains==1);
 Player native;
 native.m_renderManager.ai=false;
 native.Handoff(); assert(native.drainsAtAudioClose==0);
 Player uninitialized;
 uninitialized.m_CurrentVideo.inited=false;
 uninitialized.Handoff(); assert(uninitialized.drainsAtAudioClose==0);
}
'''.replace("HANDOFF", handoff))

    def test_only_matching_vaapi_sources_can_retain_the_active_output(self):
        source = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp").read_text()
        self.assertIn("bool CRendererVAAPIGLES::RetainHDR10DVOutput(", source)
        handoff = body(source, "bool CRendererVAAPIGLES::RetainHDR10DVOutput(")
        execute(r'''
#include <cassert>
#include <cmath>
struct VideoBuffer { virtual ~VideoBuffer() = default; };
struct CVaapiRenderPicture : VideoBuffer {
 bool valid=true; unsigned renderBufferCount=30;
 struct {int videoSurface=1, fourcc=10;} procPic;
};
constexpr int VA_INVALID_ID=-1, NUM_BUFFERS=6;
constexpr unsigned DVP_FLAG_INTERLACED=8;
enum class StreamHdrType {HDR_TYPE_HDR10, HDR_TYPE_HLG, HDR_TYPE_HDR10PLUS, SDR};
struct VideoPicture {
 VideoBuffer* videoBuffer;
 int iWidth=3840,iHeight=2160;
 unsigned iFlags=0;
 StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;
 struct {int profile=0;} doviSourceInfo;
};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext {
 virtual ~CWinSystemGbmGLESContext()=default;
 bool keep=true;
 bool RetainHDR10DVOutput(const VideoPicture&){return keep;}
};
}
using Window=KODI::WINDOWING::GBM::CWinSystemGbmGLESContext;
Window window;
struct CServiceBroker { static Window* GetWinSystem(){return &window;} };
struct Renderer {
 bool m_dvRequested=true,m_aiLookahead=true,m_bConfigured=true;
 int m_sourceWidth=3840,m_sourceHeight=2160,m_vaapiFourcc=10; float m_fps=24;
 bool DVBridgeOrientationSupported(unsigned orientation)const{return orientation==0;}
 bool RetainHDR10DVOutput(const VideoPicture& picture,float fps,unsigned orientation) HANDOFF
};
int main(){
 CVaapiRenderPicture va;
 VideoPicture p{&va};
 Renderer r;
 assert(!r.RetainHDR10DVOutput(p,25,0));
 assert(!r.RetainHDR10DVOutput(p,24,90) && r.m_dvRequested && r.m_bConfigured);
 p.iWidth=1920; assert(!r.RetainHDR10DVOutput(p,24,0));p.iWidth=3840;
 p.iFlags=DVP_FLAG_INTERLACED;assert(!r.RetainHDR10DVOutput(p,24,0));p.iFlags=0;
 va.procPic.fourcc=8;assert(!r.RetainHDR10DVOutput(p,24,0));va.procPic.fourcc=10;
 va.procPic.videoSurface=VA_INVALID_ID;assert(!r.RetainHDR10DVOutput(p,24,0));va.procPic.videoSurface=1;
 window.keep=false;assert(!r.RetainHDR10DVOutput(p,24,0));window.keep=true;
 assert(r.RetainHDR10DVOutput(p,24,0) && !r.m_dvRequested && !r.m_bConfigured);
}
'''.replace("HANDOFF", handoff))
