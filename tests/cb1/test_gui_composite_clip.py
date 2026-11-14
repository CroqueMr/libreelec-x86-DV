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
#include <cstdlib>
#include <memory>
#define HAVE_DVBRIDGE 1
using GLint=int;
namespace DVBRIDGE {
bool DiagnosticsEnabled(){return false;}
uint64_t DiagnosticNowMs(){return 0;}
struct DiagnosticInterval{bool Due(uint64_t){return false;}void Emitted(uint64_t){}};
template<class...T>void DiagnosticLog(T...){}
}
struct CRect {
  int x1=0,y1=0,x2=0,y2=0;
  bool contains(int x,int y) const {return x>=x1 && x<x2 && y>=y1 && y<y2;}
};
CRect rawClip{0,276,3840,1884};
bool bottomCleared=false;
bool scissorEnabled=false; // libplacebo's raster pass leaves it disabled.
constexpr int GL_TEXTURE_2D=1,GL_RGBA=2,GL_COLOR_BUFFER_BIT=4,LOGERROR=0,LOGDEBUG=1,LOGINFO=2;
constexpr int GL_VIEWPORT=5,GL_FRAMEBUFFER_BINDING=6,GL_SCISSOR_TEST=7;
void glEnable(int cap) {assert(cap==GL_SCISSOR_TEST);scissorEnabled=true;}
bool drawsAt(int x,int y) {return !scissorEnabled || rawClip.contains(x,y);}
void glGetIntegerv(int,int*){assert(false && "Disabled diagnostics queried GL");}
void glClearColor(float,float,float,float) {}
void glClear(int) {bottomCleared=drawsAt(1900,1950);}
struct CLog {template<class... T> static void Log(T...) {}};
struct CRenderSystemGLES {
  inline static unsigned m_GUIElementCount=0;
  static void SetScissors(const CRect& r) {rawClip=r;}
  static void GetViewPort(CRect& r) {r={0,0,3840,2160};}
  static void SetViewPort(const CRect& r) {rawClip=r;}
};
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
// These geometry fixtures keep one fixed native full-range shader.
struct CServiceBroker {
 struct GUI {GUI& GetWindowManager(){return *this;}void MarkDirty(){assert(false);}};
 static GUI* GetGUI(){static GUI gui;return &gui;}
};
struct CWinSystemGbmGLESContext : CRenderSystemGLES {
  bool m_guiCompositing=true,m_guiWillRender=false,m_guiFboClean=false;
  bool m_guiCacheValid=false;unsigned m_guiCachedElementCount=0;
  int m_nWidth=3840,m_nHeight=2160,m_guiFboWidth=3840,m_guiFboHeight=2160;
  FBO m_guiFbo,m_dvPQSubtitleFbo;
  void* m_dvContext=nullptr;
  std::shared_ptr<int> m_compositeShader=std::make_shared<int>(1);
  bool m_compositeShaderLimited=false;int m_guiColorTransfer=0;
  bool UseLimitedColor()const{return false;}
  bool SetGuiCompositing(int){assert(false);return false;}
  CGraphicContext context;
  DVState m_dvState;
  bool m_hdrConversion=false,m_cb1FramePending=false,m_dvFrame=false,m_dvNativeGui=false;
  bool m_dvPQSubtitleCleared=false;
  bool m_dvPQGuiMergeAttempted=false,m_dvPQGuiComposed=false;
  unsigned m_dvGUIContentGeneration=0,m_dvSubtitleDraws=0,m_dvSubtitleContent=0,m_dvPQSubtitleDraws=0;
  int m_dvPQSubtitleWidth=3840,m_dvPQSubtitleHeight=2160;
  CRect m_dvSubtitleBounds;
  DVBRIDGE::DiagnosticInterval m_dvGuiDiagnostic;
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
  scissorEnabled=false;
  assert(clipped.BeginGuiComposite(true));
  assert(drawsAt(1900,1950) && !drawsAt(50,1950) && !drawsAt(1900,100) &&
         "GUI text escapes Kodi's clip");
  CWinSystemGbmGLESContext hdr;
  hdr.m_dvState.captured=false;hdr.m_hdrConversion=true;
  rawClip={0,276,3840,1884};bottomCleared=false;scissorEnabled=false;
  assert(hdr.BeginGuiComposite(true) && bottomCleared && scissorEnabled);
  // Recovery can clear the scanout with scissors disabled before a CB1
  // renderer is initialized. The ordinary GUI draw must reapply Kodi's clip.
  CWinSystemGbmGLESContext vanilla;
  vanilla.m_dvState.captured=false;
  vanilla.context.scissors={100,200,3000,1800};
  rawClip={0,0,3840,2160};
  scissorEnabled=false;
  assert(vanilla.BeginGuiComposite(true) && scissorEnabled);
  assert(drawsAt(200,300) && !drawsAt(50,300) && !drawsAt(1900,1950));
  // The ordinary path can draw directly instead of binding the GUI FBO.
  vanilla.m_guiCompositing=false;
  scissorEnabled=false;
  rawClip={0,0,3840,2160};
  assert(!vanilla.BeginGuiComposite(true) && scissorEnabled);
  assert(drawsAt(200,300) && !drawsAt(50,300) && !drawsAt(1900,1950));
  // No GUI drawing leaves the active framebuffer's clip alone.
  scissorEnabled=false;
  assert(master.BeginGuiComposite(false) && !scissorEnabled);
  assert(!rawClip.contains(1900,1950));
  // Failure to bind the GUI FBO falls through to native GUI drawing, which
  // still needs Kodi's clip; the failed pass must not clear any framebuffer.
  master.m_guiFbo.begin=false;
  bottomCleared=false;
  assert(!master.BeginGuiComposite(true) && scissorEnabled && rawClip.contains(1900,1950) && !bottomCleared);
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
