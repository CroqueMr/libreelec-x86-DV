"""CB1's video crop must not clip Kodi's following GUI or its clear."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from shipped_kodi import shipped_code
from test_native_video_source import body


class GUICompositeClip(unittest.TestCase):
    def test_gui_clear_and_subtitles_use_kodi_clip_after_cb1(self):
        source = shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        begin = body(source, 'bool CWinSystemGbmGLESContext::BeginGuiComposite(bool guiWillRender)')
        program = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#define HAVE_DVBRIDGE 1
struct CRect {
  int x1=0,y1=0,x2=0,y2=0;
  bool contains(int x,int y) const {return x>=x1 && x<x2 && y>=y1 && y<y2;}
};
CRect rawClip{0,276,3840,1884};
bool bottomCleared=false;
constexpr int GL_TEXTURE_2D=1,GL_RGBA=2,GL_COLOR_BUFFER_BIT=4,LOGERROR=0,LOGDEBUG=1;
void glClearColor(float,float,float,float) {}
void glClear(int) {bottomCleared=rawClip.contains(1900,1950);}
struct CLog {template<class... T> static void Log(T...) {}};
struct CRenderSystemGLES {static void SetScissors(const CRect& r) {rawClip=r;}};
struct CGraphicContext {
  CRect scissors{0,0,3840,2160};
  CRect GetScissors() const {return scissors;}
  CRect StereoCorrection(CRect r) const {return r;}
};
struct FBO {
  bool begin=true;
  bool IsValid() const {return true;}
  bool Initialize() {return false;}
  bool CreateAndBindToTexture(int,int,int,int) {return false;}
  bool AttachDepthBuffer(int,int) {return false;}
  void Cleanup() {}
  bool BeginRender() {return begin;}
};
struct DVState {bool captured=true;bool Captured() const {return captured;}};
struct CWinSystemGbmGLESContext : CRenderSystemGLES {
  bool m_guiCompositing=true,m_guiWillRender=false,m_guiFboClean=false;
  int m_nWidth=3840,m_nHeight=2160,m_guiFboWidth=3840,m_guiFboHeight=2160;
  FBO m_guiFbo,m_dvPQSubtitleFbo;
  CGraphicContext context;
  DVState m_dvState;
  bool m_hdrConversion=false,m_cb1FramePending=false,m_dvFrame=false,m_dvNativeGui=false;
  bool m_dvPQSubtitleCleared=false;
  bool m_dvPQGuiMergeAttempted=false,m_dvPQGuiComposed=false;
  unsigned m_dvGUIContentGeneration=0,m_dvSubtitleDraws=0,m_dvSubtitleContent=0,m_dvPQSubtitleDraws=0;
  int m_dvPQSubtitleWidth=3840,m_dvPQSubtitleHeight=2160;
  CRect m_dvSubtitleBounds;
  CGraphicContext& GetGfxContext() {return context;}
  bool GetEnabledFrontToBackRendering() const {return false;}
  bool HasDVBridgeScreenshot() const {return false;}
  bool BeginDVPQSubtitle() {return false;}
  void EndDVPQSubtitle() {}
  bool BeginGuiComposite(bool guiWillRender) @@BEGIN@@
};
int main() {
  CWinSystemGbmGLESContext master;
  assert(master.BeginGuiComposite(true));
  assert(bottomCleared && "the bottom subtitle region was excluded from the GUI clear");
  assert(rawClip.contains(1900,1950) && "subtitle in the black bar is still clipped");
  // A requested Kodi clip is preserved, not replaced by an unconditional full-screen clip.
  CWinSystemGbmGLESContext clipped;
  clipped.context.scissors={100,200,3000,2000};
  assert(clipped.BeginGuiComposite(true));
  assert(rawClip.contains(1900,1950) && !rawClip.contains(50,1950));
  CWinSystemGbmGLESContext hdr;
  hdr.m_dvState.captured=false;hdr.m_hdrConversion=true;
  rawClip={0,276,3840,1884};bottomCleared=false;
  assert(hdr.BeginGuiComposite(true) && bottomCleared);
  // Vanilla compositing retains its existing clip; no CB1 state is owned here.
  CWinSystemGbmGLESContext vanilla;
  vanilla.m_dvState.captured=false;rawClip={100,200,3000,1800};
  assert(vanilla.BeginGuiComposite(true));
  assert(rawClip.contains(200,300) && !rawClip.contains(1900,1950));
  // Skipped and failed GUI passes must not change the active framebuffer's clip.
  assert(master.BeginGuiComposite(false));
  assert(!rawClip.contains(1900,1950));
  master.m_guiFbo.begin=false;
  assert(!master.BeginGuiComposite(true) && !rawClip.contains(1900,1950));
}
'''.replace('@@BEGIN@@', begin)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'check.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root / 'check.cpp'),
                                    '-o', str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
