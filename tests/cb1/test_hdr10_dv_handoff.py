# SPDX-License-Identifier: MIT
"""The renderer may hand off a committed HDR10-to-DV output on reconfiguration."""
import unittest

from test_ai_reentry import execute
from test_native_video_source import TREE, body


class HDR10DVHandoffTests(unittest.TestCase):
    def test_bluray_reopen_dispatches_probe_flush_before_first_packet(self):
        source = (TREE / "xbmc/cores/VideoPlayer/VideoPlayer.cpp").read_text()
        process = body(source, "void CVideoPlayer::Process()")
        start = process.index("    // should we open a new demuxer?")
        end = process.index("    // handle eventual seeks", start)
        execute(r'''
#include <algorithm>
#include <cassert>
#include <vector>
struct CDVDMsg { enum Message { GENERAL_FLUSH }; };
enum class StreamType { AUDIO };
struct CDemuxStream { StreamType type; bool disabled; int dvdNavId; };
struct Player
{
  struct CDVDInputStream { enum { NEXTSTREAM_NONE, NEXTSTREAM_OPEN, DVDSTREAM_TYPE_PVRMANAGER }; };
  static constexpr int DVDSTREAM_TYPE_PVRMANAGER = CDVDInputStream::DVDSTREAM_TYPE_PVRMANAGER;
  struct Input
  {
    int NextStream() const { return CDVDInputStream::NEXTSTREAM_OPEN; }
    bool IsEOF() const { return false; }
    bool IsStreamType(int) const { return false; }
  } input, *m_pInputStream = &input;
  struct { struct { bool empty() const { return true; } } m_Streams; } m_SelectionStreams;
  struct ProcessInfo { void SetStateStreaming(bool){} } *m_processInfo = nullptr;
  struct Queue
  {
    bool flush = false;
    int GetPacketCount(CDVDMsg::Message) const { return flush; }
  } m_messenger;
  struct Demuxer
  {
    std::vector<CDemuxStream*> GetStreams() { return {}; }
  } demuxer, *m_pDemuxer = nullptr;
  struct { int iSelectedAudioStream = -1; } m_dvd;
  int m_CurrentAudio{};
  bool m_bdjAudioHandoff = false;
  bool bluray, probeFlush, m_bAbortRequest = false;
  void CloseStream(int&, bool) { m_bdjAudioHandoff = false; }
  bool flushedBeforeRead = false;
  bool IsBlurayInput() const { return bluray; }
  bool EvaluateIsStreaming() const { return false; }
  bool OpenDemuxStream()
  {
    m_pDemuxer = &demuxer;
    m_messenger.flush = probeFlush;
    return true;
  }
  void OpenDefaultStreams() {}
  void UpdatePlayState(int) {}
  void Reopen()
  {
    for (int pass=0; pass<2; ++pass)
    {
      const bool flushed = m_messenger.flush;
      m_messenger.flush = false;
      REOPEN
      flushedBeforeRead = flushed;
      return;
    }
    assert(false);
  }
};
int main()
{
  Player disc{.bluray=true, .probeFlush=true};
  disc.Reopen(); assert(disc.flushedBeforeRead);
  Player ordinary{.bluray=true, .probeFlush=false};
  ordinary.Reopen(); assert(!ordinary.flushedBeforeRead);
  Player other{.bluray=false, .probeFlush=true};
  other.Reopen(); assert(!other.flushedBeforeRead);
}
'''.replace("REOPEN", process[start:end]))

    def test_flush_waits_only_for_running_stream_players(self):
        source = (TREE / "xbmc/cores/VideoPlayer/VideoPlayer.cpp").read_text()
        flush = body(source, "void CVideoPlayer::FlushBuffers(")
        # Exercise the actual worker barrier, after the decoder queues are flushed.
        start = flush.index("    // make sure players are properly flushed")
        end = flush.index("    // purge any pending", start)
        execute(r'''
#include <cassert>
#include <chrono>
#include <memory>
using namespace std::chrono_literals;
constexpr unsigned SYNCSOURCE_AUDIO = 1, SYNCSOURCE_VIDEO = 2;
struct CDVDMsgGeneralSynchronize {
 static inline unsigned waited = 0;
 unsigned expected, reached = 0;
 CDVDMsgGeneralSynchronize(std::chrono::milliseconds timeout, unsigned sources)
   : expected(sources) { assert(timeout == 1s); }
 void Wait(bool, int) { assert(reached == expected); waited = reached; }
};
struct Worker {
 unsigned source, messages = 0;
 bool ready;
 bool IsInited() const { return ready; }
 void SendMessage(const std::shared_ptr<CDVDMsgGeneralSynchronize>& msg, int priority)
 {
   assert(ready && priority == 1);
   msg->reached |= source;
   ++messages;
 }
};
void check(bool audioReady, bool videoReady)
{
  Worker audio{SYNCSOURCE_AUDIO, 0, audioReady}, video{SYNCSOURCE_VIDEO, 0, videoReady};
  auto* m_VideoPlayerAudio = &audio;
  auto* m_VideoPlayerVideo = &video;
  const bool m_bStop = false;
  CDVDMsgGeneralSynchronize::waited = 0;
  { BARRIER }
  assert(audio.messages == audioReady && video.messages == videoReady);
  assert(CDVDMsgGeneralSynchronize::waited ==
         ((audioReady ? SYNCSOURCE_AUDIO : 0) | (videoReady ? SYNCSOURCE_VIDEO : 0)));
}
int main()
{
  check(true, true);
  check(false, true);
  check(true, false);
  check(false, false);
}
'''.replace("BARRIER", flush[start:end]))

    def test_video_drains_before_waiting_for_outgoing_audio(self):
        source = (TREE / "xbmc/cores/VideoPlayer/VideoPlayer.cpp").read_text()
        handoff = body(source, "if(next == CDVDInputStream::NEXTSTREAM_OPEN)")
        execute(r'''
#include <cassert>
#include <memory>
#define CB1_HAS_HDR10_AI
struct CDVDMsg { enum { VIDEO_DRAIN, GENERAL_EOF }; explicit CDVDMsg(int) {} };
constexpr int DVD_PLAYSPEED_NORMAL = 1000;
struct IDVDStreamPlayer { enum { SYNC_INSYNC }; };
struct Player {
 enum { CACHESTATE_DONE, LOGINFO };
 int m_playSpeed=DVD_PLAYSPEED_NORMAL;
 bool m_bdjAudioHandoff=false, m_HasAudio=true;
 struct Stream { bool inited=true; int id=1, syncState=IDVDStreamPlayer::SYNC_INSYNC; void Clear(){} };
 Stream m_CurrentAudio, m_CurrentVideo, m_CurrentSubtitle;
 struct { void reset(){} } m_syncStartPtsWait;
 struct { void clear(){} } m_bdjPresentationEvents;
 bool m_bdjDraining=false;
 struct Renderer {
  bool ai=true;
  bool HDR10AILookahead(){return ai;}
 } m_renderManager;
 struct Video {
  int drains=0;
  void SendMessage(std::shared_ptr<CDVDMsg>){++drains;}
 } video, *m_VideoPlayerVideo=&video;
 struct Audio {
  bool passthrough=false;
  int drains=0;
  bool IsPassthrough() const { return passthrough; }
  void SendMessage(std::shared_ptr<CDVDMsg>) { ++drains; }
 } audio, *m_VideoPlayerAudio=&audio;
 struct CLog { template<class... A> static void Log(A...){} };
 bool demuxClosed=false;
 int drainsAtAudioClose=-1;
 void CloseDemuxer(){demuxClosed=true;}
 void SetCaching(int){}
 void CloseStream(Stream& stream,bool wait) {
  assert(demuxClosed && (wait || &stream==&m_CurrentSubtitle));
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
 Player natural;
 natural.m_bdjDraining=true;
 natural.Handoff();
 assert(natural.audio.drains==1 && natural.drainsAtAudioClose==-1 && natural.m_bdjAudioHandoff);
 Player passthrough;
 passthrough.m_bdjDraining=true;
 passthrough.audio.passthrough=true;
 passthrough.Handoff();
 assert(passthrough.audio.drains==0 && passthrough.drainsAtAudioClose==1);
}
'''.replace("HANDOFF", handoff))

    def test_only_matching_vaapi_sources_can_retain_the_active_output(self):
        source = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp").read_text()
        handoff = body(source, "CRendererVAAPIGLES::DVHandoff CRendererVAAPIGLES::RetainDVOutput(")
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
struct VideoPicture {
 VideoBuffer* videoBuffer;
 int iWidth=3840,iHeight=2160,colorBits=10,color_range=0,color_primaries=9;
 unsigned iFlags=0;
};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext {
 virtual ~CWinSystemGbmGLESContext()=default;
 bool native=false, ai=true, hdr10=false;
 bool CanRetainHDR10Output(const VideoPicture&){return hdr10;}
 bool RetainNativeDVOutput(const VideoPicture&){return native;}
 bool RetainHDR10DVOutput(const VideoPicture&){return ai;}
};
}
using Window=KODI::WINDOWING::GBM::CWinSystemGbmGLESContext;
Window window;
struct CServiceBroker { static Window* GetWinSystem(){return &window;} };
struct Renderer {
 enum class DVHandoff {None, HDR10AI, Native, HDR10};
 bool m_dvRequested=true,m_aiLookahead=true,m_bConfigured=true,m_isVAAPIBuffer=true;
 bool m_passthroughHDR=false,m_srcFullRange=false;
 int m_srcPrimaries=9;
 int m_sourceWidth=3840,m_sourceHeight=2160,m_vaapiFourcc=10,m_srcColorBits=10;
 float m_fps=24;
 bool DVBridgeOrientationSupported(unsigned orientation)const{return orientation==0;}
 DVHandoff RetainDVOutput(const VideoPicture& picture,float fps,unsigned orientation) HANDOFF
};
int main(){
 using H=Renderer::DVHandoff;
 CVaapiRenderPicture va;
 VideoPicture p{&va};
 Renderer r;
 assert(r.RetainDVOutput(p,25,0)==H::None);
 assert(r.RetainDVOutput(p,24,90)==H::None && r.m_dvRequested && r.m_bConfigured);
 p.iWidth=1920; assert(r.RetainDVOutput(p,24,0)==H::None);p.iWidth=3840;
 p.iFlags=DVP_FLAG_INTERLACED;assert(r.RetainDVOutput(p,24,0)==H::None);p.iFlags=0;
 va.procPic.fourcc=8;assert(r.RetainDVOutput(p,24,0)==H::None);va.procPic.fourcc=10;
 va.procPic.videoSurface=VA_INVALID_ID;assert(r.RetainDVOutput(p,24,0)==H::None);va.procPic.videoSurface=1;
 p.colorBits=8;assert(r.RetainDVOutput(p,24,0)==H::None);p.colorBits=10;
 window.ai=false;assert(r.RetainDVOutput(p,24,0)==H::None);window.ai=true;
 assert(r.RetainDVOutput(p,24,0)==H::HDR10AI && !r.m_dvRequested && !r.m_bConfigured);
 r=Renderer{};
 va.renderBufferCount=NUM_BUFFERS;
 assert(r.RetainDVOutput(p,24,0)==H::None && r.m_dvRequested);
 window.native=true;
 r.m_aiLookahead=false;
 assert(r.RetainDVOutput(p,24,0)==H::Native && !r.m_dvRequested && !r.m_bConfigured);
 r=Renderer{};
 r.m_dvRequested=false;
 r.m_passthroughHDR=true;
 assert(r.RetainDVOutput(p,24,0)==H::None && r.m_bConfigured);
 window.hdr10=true;
 p.color_range=1;
 assert(r.RetainDVOutput(p,24,0)==H::None && r.m_bConfigured);
 p.color_range=0;
 assert(r.RetainDVOutput(p,24,0)==H::HDR10 && !r.m_bConfigured);
}
'''.replace("HANDOFF", handoff))
