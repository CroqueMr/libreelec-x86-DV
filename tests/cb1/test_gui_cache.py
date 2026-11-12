"""Persistent CB1 GUI: real native cache, dirty gates and presentation prefixes."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code
from test_native_video_source import body


class GUICache(unittest.TestCase):
    def run_cpp(self, program):
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory)/'check.cpp', Path(directory)/'check'
            source.write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(source), '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)

    def test_cached_gui_keeps_counts_subtitles_and_generation(self):
        source = shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        capability = ('{return false;}' if 'bool CWinSystemGbmGLESContext::CanReuseGuiComposite()' not in source
                      else body(source, 'bool CWinSystemGbmGLESContext::CanReuseGuiComposite()'))
        render = body(source, 'bool CWinSystemGbmGLESContext::RenderDVBridge(')
        available = re.search(r'  const bool guiAvailable = .*?;', render, re.S)
        overlay = re.search(r'  const bool overlayFree = .*?;', render, re.S)[0]
        route = render[render.index('  const bool mergedPQGUI ='):render.index('  // The TV masks L5 margins.')]
        visible = re.search(r'm_dvBridge->SetOverlayVisible\((.*?)\);',render,re.S)[1]
        transfer = body(source,'bool CWinSystemGbmGLESContext::ConfigureGuiCompositing(')
        transfer = transfer[transfer.index('  m_guiCacheValid = false;'):transfer.index('  if (m_guiCompositing)')]
        program = r'''
#define HAVE_DVBRIDGE 1
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <memory>
#include <vector>
using GLint=int;
constexpr int GL_VIEWPORT=1,GL_FRAMEBUFFER_BINDING=2,GL_TEXTURE_2D=3,GL_RGBA=4,GL_COLOR_BUFFER_BIT=5;
constexpr int LOGERROR=0,LOGDEBUG=1,LOGINFO=2,DVBRIDGE_MODE_MASTER_REFERENCE=5,DVBRIDGE_MODE_ENHANCED_DV=4;
constexpr int DIRTYREGION_SOLVER_FILL_VIEWPORT_ALWAYS=0,DIRTYREGION_SOLVER_FILL_VIEWPORT_ON_CHANGE=3;
unsigned binds=0,clears=0;
constexpr int GL_SCISSOR_TEST=7;
void glEnable(int cap){assert(cap==GL_SCISSOR_TEST);}
void glGetIntegerv(int,int*){}void glClearColor(float,float,float,float){}void glClear(int){++clears;}
struct CLog{template<class...T>static void Log(T...){}};
namespace KODI::RENDERING::CAPTURE {enum class CaptureContent {VIDEO,COMPOSITE};}
struct Capture {bool video=false,composite=false;
 std::vector<int> TakeActive(KODI::RENDERING::CAPTURE::CaptureContent c){
 return (c==KODI::RENDERING::CAPTURE::CaptureContent::VIDEO?video:composite)?std::vector<int>{1}:std::vector<int>{};}};
std::shared_ptr<Capture> capture=std::make_shared<Capture>();
struct CApplicationPlayer{bool visible=false;bool HasVisibleOverlay()const{return visible;}}player;
struct Components{template<class T>auto GetComponent()const{return &player;}}components;
struct Advanced{int m_guiAlgorithmDirtyRegions=3;bool m_guiVisualizeDirtyRegions=false;}advanced;
struct SettingsComponent{auto*GetAdvancedSettings(){return &advanced;}}settings;
struct CServiceBroker{static auto GetCaptureService(){return capture;}static auto&GetAppComponents(){return components;}
 static auto*GetSettingsComponent(){return &settings;}
 struct GUI {GUI& GetWindowManager(){return *this;}void MarkDirty(){assert(false);}};
 static auto*GetGUI(){static GUI gui;return &gui;}};
namespace DVBRIDGE {
bool optimized=true;struct Preferences{bool optimizedGUI;};Preferences FrameOutputSettings(){return {optimized};}
bool DiagnosticsEnabled(){return false;}uint64_t DiagnosticNowMs(){return 0;}
struct DiagnosticInterval{bool Due(uint64_t){return false;}void Emitted(uint64_t){}};
unsigned auditReports=0;
template<class...T>void DiagnosticLog(T...){++auditReports;}
}
struct CRect {int x1=0,y1=0,x2=0,y2=0;};
struct CRenderSystemGLES {
 inline static unsigned m_GUIElementCount=0;
 unsigned GetGUIElementCount()const{return m_GUIElementCount;}
 static void GetViewPort(CRect&){}static void SetViewPort(const CRect&){}static void SetScissors(const CRect&){}
};
struct FBO {
 bool valid=true,bound=true,begin=true;
 bool IsValid()const{return valid;}bool IsBound()const{return bound;}
 bool BeginRender(){++binds;return begin;}void EndRender(){}
 void Cleanup(){}bool Initialize(){return true;}bool CreateAndBindToTexture(int,int,int,int){return true;}
 bool AttachDepthBuffer(int,int){return true;}
};
struct DRM{void* GetVideoPlane(){return nullptr;}void* GetGuiPlane(){return nullptr;}};
struct CDVBridgeGLES {
 static bool CanComposeSDRGUI(bool enabled,bool hdr,bool capturing,int w,int h,unsigned pq){return enabled&&!hdr&&!capturing&&w>0&&h>0&&!pq;}
};
struct CWinSystemGbmGLESContext:CRenderSystemGLES {
 bool m_guiCompositing=true,m_guiWillRender=true,m_guiFboClean=false,m_guiCacheValid=false;
 unsigned m_guiCachedElementCount=0;
 bool m_hdrConversion=false,m_cb1FramePending=false,m_dvFrame=false,m_dvNativeGui=false,m_dvOverlays=false;
 bool m_dvPQGuiMergeAttempted=false,m_dvPQGuiComposed=false,m_dvPQSubtitleCleared=false;
 unsigned m_dvGUIContentGeneration=0,m_dvSubtitleDraws=0,m_dvSubtitleContent=0,m_dvPQSubtitleDraws=0;
 CRect m_dvSubtitleBounds;FBO m_guiFbo,m_dvPQSubtitleFbo;
 int m_nWidth=3840,m_nHeight=2160,m_guiFboWidth=3840,m_guiFboHeight=2160,m_dvPQSubtitleWidth=3840,m_dvPQSubtitleHeight=2160;
 void* m_dvContext=nullptr;std::shared_ptr<int> m_compositeShader=std::make_shared<int>(1);
 bool m_compositeShaderLimited=false;int m_guiColorTransfer=0;
 bool UseLimitedColor()const{return false;}
 bool SetGuiCompositing(int){assert(false);return false;}
 struct State{bool captured=true;bool Captured()const{return captured;}}m_dvState;
 struct Gfx{bool fullscreen=true;bool IsFullScreenVideo()const{return fullscreen;}
 CRect GetScissors()const{return {};}CRect StereoCorrection(CRect r)const{return r;}}gfx;
 const auto& GetGfxContext()const{return gfx;}
 DRM drm;DRM* m_DRM=&drm;DVBRIDGE::DiagnosticInterval m_dvGuiDiagnostic;
 bool GetEnabledFrontToBackRendering()const{return false;}
 bool HasDVBridgeScreenshot()const{return false;}bool BeginDVPQSubtitle(){return false;}void EndDVPQSubtitle(){}
 bool CanReuseGuiComposite()const @CAPABILITY@
 void SetTransfer(int colorTransfer){@TRANSFER@}
 bool BeginGuiComposite(bool guiWillRender) @BEGIN@
 void EndGuiComposite() @END@
 bool ComposeDVPQGUI(){return m_dvPQGuiComposed;}
 bool Visible(){bool capturing=false,masterCapture=false,m_dvOverlays=false;
 struct{bool optimizedDV=true;}preferences;
 struct{struct{int mode=5;}policy;}m_dvSelection;
 struct{void*Data(){return this;}}metadata;
 @AVAILABLE@
 @OVERLAY@
 @ROUTE@
 assert(!overlayFree && fullGUI);
 return @VISIBLE@;}
};
int main(){
 CWinSystemGbmGLESContext w;
 assert(!w.CanReuseGuiComposite()); // An allocated but never-drawn FBO is not a cache.
 assert(w.BeginGuiComposite(true));
 w.m_GUIElementCount=5;w.m_dvSubtitleDraws=0;w.m_dvPQSubtitleDraws=0;w.m_dvSubtitleContent=71;
 w.m_dvSubtitleBounds={10,20,30,40};w.EndGuiComposite();
 assert(w.CanReuseGuiComposite());
 // Partial-damage algorithms would redraw only scissored controls after a full FBO clear.
 for(int algorithm:{0,1,2,3,4,-1}){
  advanced.m_guiAlgorithmDirtyRegions=algorithm;
  assert(w.CanReuseGuiComposite()==(algorithm==0||algorithm==3));
 }
 advanced.m_guiAlgorithmDirtyRegions=3;
 advanced.m_guiVisualizeDirtyRegions=true;assert(!w.CanReuseGuiComposite());
 advanced.m_guiVisualizeDirtyRegions=false;
 const auto generation=w.m_dvGUIContentGeneration,draws=binds,clearCount=clears;
 for(unsigned frame=0;frame<4;frame++){
  w.m_GUIElementCount=0; // Actual CRenderSystemGLES::BeginRender reset.
  assert(w.BeginGuiComposite(false));w.EndGuiComposite();
  assert(w.GetGUIElementCount()==5 && w.m_dvSubtitleDraws==0 && w.m_dvSubtitleContent==71);
  assert(w.m_dvSubtitleBounds.x1==10 && w.m_dvSubtitleBounds.y2==40);
  assert(w.m_dvGUIContentGeneration==generation && binds==draws && clears==clearCount);
  assert(w.Visible()); // Cached controls still reserve L5 and use the native compositor.
 }
 for(unsigned bad=0;bad<10;bad++){
  CWinSystemGbmGLESContext invalid=w;
  if(bad==0)invalid.m_guiCompositing=false;
  if(bad==1)invalid.m_guiFbo.valid=false;
  if(bad==2)invalid.m_guiFbo.bound=false;
  if(bad==3)invalid.m_guiFboWidth=1920;
  if(bad==4)invalid.m_guiFboHeight=1080;
  if(bad==5)invalid.m_compositeShader=nullptr;
  if(bad==6)invalid.m_dvState.captured=false; // Ordinary native HDR must remain unchanged.
  if(bad==7)invalid.gfx.fullscreen=false; // Embedded video still owns GUI-walk drawing.
  if(bad==8)capture->composite=true;
  if(bad==9)capture->video=true;
  assert(!invalid.CanReuseGuiComposite());capture->video=capture->composite=false;
 }
 DVBRIDGE::optimized=false;assert(w.CanReuseGuiComposite());DVBRIDGE::optimized=true; // Obsolete off cannot disable eligible caching.
 // Caption appearance, change and disappearance all retain the live GUI/reset path.
 player.visible=true;assert(!w.CanReuseGuiComposite());
 assert(w.BeginGuiComposite(true));assert(w.m_dvSubtitleDraws==0 && !w.m_dvPQSubtitleCleared);
 w.m_dvSubtitleDraws=w.m_dvPQSubtitleDraws=1;w.m_dvPQSubtitleCleared=true;w.EndGuiComposite();
 assert(!w.CanReuseGuiComposite());
 assert(w.BeginGuiComposite(true));assert(w.m_dvPQSubtitleDraws==0 && !w.m_dvPQSubtitleCleared);
 w.m_dvSubtitleDraws=1;w.EndGuiComposite();player.visible=false;
 assert(!w.CanReuseGuiComposite());
 assert(w.BeginGuiComposite(true));w.EndGuiComposite();assert(w.CanReuseGuiComposite());
 w.m_guiFboWidth=1920;assert(!w.CanReuseGuiComposite());
 w.m_guiFboWidth=3840;w.m_dvState.captured=false;w.m_hdrConversion=true;assert(w.CanReuseGuiComposite());
 assert(w.BeginGuiComposite(true));w.m_GUIElementCount=0;w.EndGuiComposite();
 assert(w.m_dvGUIContentGeneration==generation+4 && w.m_guiCachedElementCount==0);
 w.m_GUIElementCount=77;assert(w.BeginGuiComposite(false));assert(w.GetGUIElementCount()==0);
 w.SetTransfer(16);assert(!w.CanReuseGuiComposite()); // Mode setup invalidates even an allocated matching FBO.
 assert(w.BeginGuiComposite(true));w.EndGuiComposite();assert(w.CanReuseGuiComposite());
 w.SetTransfer(0);assert(!w.CanReuseGuiComposite());w.SetTransfer(16);assert(!w.CanReuseGuiComposite());
 assert(w.BeginGuiComposite(true));w.EndGuiComposite();assert(w.CanReuseGuiComposite());
 assert(DVBRIDGE::auditReports==0);
 setenv("CB1_PRESENTATION_AUDIT","1",1);
 for(unsigned i=0;i<240;i++)assert(w.BeginGuiComposite(false));
 assert(DVBRIDGE::auditReports==2);unsetenv("CB1_PRESENTATION_AUDIT");
 for(unsigned i=0;i<120;i++)assert(w.BeginGuiComposite(false));
 assert(DVBRIDGE::auditReports==2);
}
'''
        for key,value in {'CAPABILITY':capability,'BEGIN':body(source,'bool CWinSystemGbmGLESContext::BeginGuiComposite('),
                          'END':body(source,'void CWinSystemGbmGLESContext::EndGuiComposite()'),
                          'AVAILABLE':available[0] if available else '', 'OVERLAY':overlay,'ROUTE':route,'VISIBLE':visible,
                          'TRANSFER':transfer}.items():
            program=program.replace('@'+key+'@',value)
        self.run_cpp(program)

    def test_real_dirty_gates_do_not_skip_dirty_or_animated_gui(self):
        application=shipped_code('xbmc/application/Application.cpp')
        start=application.index('    // Dirty-driven skip:')
        gate=application[start:application.index('    CServiceBroker::GetGUI()->GetWindowManager().FrameMove();',start)]
        fullscreen=shipped_code('xbmc/video/windows/GUIWindowFullScreen.cpp')
        process=body(fullscreen,'void CGUIWindowFullScreen::Process(')
        render=body(application,'void CApplication::Render()')
        late=render[render.index('  // Subtitle/input invalidations'):render.index('  const bool guiWillRender =')]
        begin=body(shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp'),
                   'bool CWinSystemGbmGLESContext::BeginRender()')
        self.run_cpp(r'''
#include <cassert>
#include <initializer_list>
using CDirtyRegionList=int;
bool dirty=false,cache=true,layer=false,animated=false;
struct Player{bool IsRenderingVideoLayer()const{return layer;}}player;
struct Services{Services&GetWindowManager(){return *this;}bool HasDirtyRegions(){return dirty;}
 Services&GetGfxContext(){return *this;}int GetWidth(){return 3840;}int GetHeight(){return 2160;}
 bool CanReuseGuiComposite(){return cache;}template<class T>Player*GetComponent()const{return &player;}}services;
struct CApplicationPlayer{};
struct CServiceBroker{static auto*GetGUI(){return &services;}static auto*GetWinSystem(){return &services;}
 static auto&GetAppComponents(){return services;}};
struct CRenderSystemGLES{unsigned passes=0;bool BeginRender(){++passes;return true;}};
struct CWinSystemGbmGLESContext:CRenderSystemGLES{
 bool m_cb1FramePending=true,m_dvFrame=true,held=true;bool&m_guiCacheValid=cache;unsigned commits=0;
 void PresentFrame(bool,bool){if(!held){++commits;m_cb1FramePending=m_dvFrame=false;}}
 bool BeginRender() @BEGIN@
};
struct CGUIWindow{void Process(unsigned,CDirtyRegionList&){dirty|=animated;}};
struct CGUIWindowFullScreen:CGUIWindow{
 struct Stats{void Reset(){}}stats;Stats*m_controlStats=&stats;
 struct Region{void SetRect(int,int,float,float){}}m_renderRegion;
 void MarkDirtyRegion(){dirty=true;}
 void Process(unsigned int currentTime,CDirtyRegionList&dirtyregion) @PROCESS@
};
bool skip(){bool m_skipGuiRender=false;auto*appPlayer=&player;
 @GATE@
 return m_skipGuiRender;}
bool late(bool m_skipGuiRender){auto*appPlayer=&player;@LATE@return m_skipGuiRender;}
int main(){for(bool videoLayer:{false,true})for(bool reusable:{false,true})for(bool animation:{false,true}){
 layer=videoLayer;cache=reusable;animated=animation;dirty=false;int regions=0;
 CGUIWindowFullScreen window;window.Process(1,regions);
 assert(skip()==((layer||cache)&&!animation));
 dirty=true;assert(!skip()); // Late input, seek, menu change and subtitle invalidations win.
}
 layer=false;cache=true;dirty=false;assert(late(true));
 dirty=true;assert(!late(true)); // Input/caption dirtied after the first check.
 dirty=false;cache=false;assert(!late(true)); // Capture, mode, resize or new caption invalidates reuse.
 layer=true;assert(late(true)); // Existing native video-plane behavior is unchanged.
 // A one-shot dirty change must survive a held prepared film and the next clean Process.
 layer=false;cache=true;dirty=true;animated=false;
 CWinSystemGbmGLESContext held;assert(!held.BeginRender()&&!cache&&held.passes==0&&held.commits==0);
 dirty=false;int regions=0;CGUIWindowFullScreen fullscreen;fullscreen.Process(2,regions);
 assert(dirty&&!skip()); // Invalid cache recreates full damage after tracker cleared the original event.
 held.held=false;assert(!held.BeginRender()&&held.commits==1&&held.passes==0);
 dirty=false;fullscreen.Process(3,regions);assert(dirty&&!skip());
 assert(held.BeginRender()&&held.passes==1); // Only the real following GUI pass may restore the cache.
}
'''.replace('@PROCESS@',process).replace('@GATE@',gate).replace('@LATE@',late).replace('@BEGIN@',begin))

    def test_cached_gui_still_reaches_actual_hdr_and_dv_swap_prefixes(self):
        native=shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        present=body(native,'void CWinSystemGbmGLESContext::PresentFrame(')
        prefixes=[]
        for marker in ['if (m_hdrConversion)','if (m_dvState.Captured())']:
            route=body(present,marker)
            end=route.index('      if (m_eglContext.TrySwapBuffers())') if marker.startswith('if (m_hdrConversion)') else route.index('      if (m_eglContext.TrySwapBuffers())')
            end=route.index('{',end)+1
            prefix=route[:end]+' ++swapped;'
            prefix+='}'*(prefix.count('{')-prefix.count('}'))
            prefixes.append(prefix)
        self.run_cpp(r'''
#include <cassert>
#include <memory>
void glFinish(){}
struct DRM{virtual~DRM()=default;};struct CDRMAtomic:DRM{};
struct CDVBridgeGLES{
 struct Submission{int sourceSideData=0;};
 unsigned resolves=0;bool ResolveHDR10(bool){++resolves;return true;}
 bool Pack(int,int,int,bool){++resolves;return true;}
 Submission CaptureSubmission(){return {};}bool Advanced(){return true;}
};
struct Window{
 bool m_dvFrame=true;int m_nWidth=3840,m_nHeight=2160,m_videoSourceSideData=1;
 std::shared_ptr<DRM>m_DRM=std::make_shared<CDRMAtomic>();
 CDVBridgeGLES bridge;CDVBridgeGLES*m_dvBridge=&bridge;unsigned swaps=0,swapped=0;
 struct EGL{unsigned*counter;bool TrySwapBuffers(){++*counter;return true;}}m_eglContext{&swaps};
 bool StageCB1ConnectorPreferences(bool){return true;}
 bool UseLimitedColor(){return false;}bool CreateCB1GPUFence(CDVBridgeGLES::Submission&){return true;}
 void HDR(bool rendered) @HDR@
 void DV(bool rendered) @DV@
};
int main(){for(bool rendered:{false,true}){Window w;
 for(unsigned film=0;film<3;film++){w.HDR(rendered);w.DV(rendered);}
 assert(w.swaps==6&&w.swapped==6&&w.bridge.resolves==6);
 w.m_dvFrame=false;w.HDR(rendered);w.DV(rendered);assert(w.swaps==6);
}}
'''.replace('@HDR@',prefixes[0]).replace('@DV@',prefixes[1]))


if __name__=='__main__':unittest.main()
