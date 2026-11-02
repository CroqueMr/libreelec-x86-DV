"""Execute native Kodi resolution rollback against NVIDIA restore and GPU retirement."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class NvidiaRefreshCycle(unittest.TestCase):
    def test_gpu_retirement_cannot_hide_a_committed_refresh_from_kodi(self):
        window=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        graphics=(TREE/'xbmc/windowing/GraphicContext.cpp').read_text()
        program=r'''
#define HAVE_DVBRIDGE
#include "ModeChangeHold.h"
#include "rendering/RenderSystemTypes.h"
#include <atomic>
#include <cassert>
#include <iostream>
#include <memory>
#include <optional>
#include <mutex>
#include <stdexcept>
#include <string>
using namespace KODI::WINDOWING::GBM;
using RESOLUTION=int;
constexpr int RES_WINDOW=-1,RES_DESKTOP=0,FILM=1;
constexpr int D3DPRESENTFLAG_MODE3DSBS=1,D3DPRESENTFLAG_MODE3DTB=2,LOGERROR=0,LOGDEBUG=1,LOGINFO=2;
constexpr int GUI_MSG_NOTIFY_ALL=0,GUI_MSG_WINDOW_RESIZE=1;
constexpr int DVBRIDGE_DV_IDLE=0,DVBRIDGE_DV_BUSY=1,DVBRIDGE_DV_FAILED=2;
struct RESOLUTION_INFO {
 int id=FILM,iWidth=3840,iHeight=2160,dwFlags=0;std::string strId="film";
 double fRefreshRate=23.976;
};
struct CDisplaySettings {
 RESOLUTION_INFO modes[2]{{0,3840,2160,0,"desktop",60},{1,3840,2160,0,"film",23.976}};
 static CDisplaySettings& GetInstance(){static CDisplaySettings value;return value;}
 const RESOLUTION_INFO& GetResolutionInfo(RESOLUTION id){return modes[id];}
};
struct CLog {template<class... T>static void Log(T...){}};
struct CEGLUtils {template<class... T>static void Log(T...){}};
namespace DVBRIDGE {std::atomic<int> modeChangeResolution{-1};
inline thread_local std::optional<int> guiModeChangeResolution;int DiagnosticNowMs(){return 0;}}
bool gpuReady=false,gpuBroken=false;unsigned finishes=0;
void glFinish(){++finishes;if(!gpuBroken)gpuReady=true;}
struct CDRMAtomic {
 virtual ~CDRMAtomic()=default;
 RESOLUTION_INFO mode;int committed=FILM;bool accepts=true;
 RESOLUTION_INFO GetCurrentMode(){return mode;}
 bool SetMode(const RESOLUTION_INFO& next){if(!accepts && next.id==0)return false;mode=next;return true;}
 bool SetVideoMode(const RESOLUTION_INFO&,void*){return true;}
 bool IsSelectedModeCommitted(){return mode.id==committed;}
};
struct CDVBridgeState {
 enum class Backend{NONE,KERNEL,NVIDIA};Backend backend=Backend::NVIDIA;
 Backend CapturedBackend(){return backend;}
};
struct Context {
 bool open=true;Context* GL(){return open?this:nullptr;}
 bool Quarantined(){return gpuBroken;}
 bool FenceLastUse(){gpuReady=false;return !gpuBroken;}
 int Poll(){return gpuBroken?DVBRIDGE_DV_FAILED:gpuReady?DVBRIDGE_DV_IDLE:DVBRIDGE_DV_BUSY;}
 bool Close(){if(gpuBroken || !gpuReady)return false;open=false;return true;}
};
struct Bridge {void Cancel(){}};
struct CWinSystemGbm {
 std::shared_ptr<CDRMAtomic> m_DRM=std::make_shared<CDRMAtomic>();
 bool SetFullScreen(bool,RESOLUTION_INFO& next,bool){
  if(!m_DRM->SetMode(next))return false;m_DRM->committed=next.id;return true;
 }
};
struct CRenderSystemGLES {static void ResetRenderSystem(int,int){}};
struct CWinSystemGbmGLESContext:CWinSystemGbm,CRenderSystemGLES {
 CModeChangeHold m_modeHold;CHeldModeAnnouncement m_modeAnnouncement;
 CDVBridgeState m_dvState;
 std::unique_ptr<Bridge> m_dvBridge=std::make_unique<Bridge>();
 std::shared_ptr<Context> m_dvContext=std::make_shared<Context>();bool m_dvShutdownFence=false;
 int m_nWidth=3840,m_nHeight=2160;bool restoreOK=true;
 struct EGL{bool TrySwapBuffers(){return true;}}m_eglContext;
 bool EndDVBridge(){
  if(!restoreOK)return false;
  if(m_dvState.backend==CDVBridgeState::Backend::NVIDIA){
   m_DRM->committed=m_DRM->mode.id;m_dvState.backend=CDVBridgeState::Backend::NONE;
  }
  return true;
 }
 bool CompleteDVBridgePage(){return true;}
 bool HoldCB1Mode(RESOLUTION_INFO&){return false;}
 bool SupportsDVOutputMode(){return true;}
 bool CreateNewWindow(const char*,bool,RESOLUTION_INFO&){return true;}
 struct Gfx{void SetStereoMode(RenderStereoMode){}}gfx;
 Gfx& GetGfxContext(){return gfx;}
 void RefreshDVOutputCapabilities(){}
 bool ResizeWindow(int,int,int,int){return false;}
 bool RetireDVContext() @RETIRE@
 bool PrepareNvidiaModeRestore(const RESOLUTION_INFO&);
 bool SetFullScreen(bool,RESOLUTION_INFO&,bool);
};
struct Settings {
 bool m_fullScreen=true;Settings* GetAdvancedSettings(){return this;}Settings* GetSettings(){return this;}
};
struct Input {void SetMouseResolution(int,int,int,int){}};
struct CGUIComponent {
 CGUIComponent& GetWindowManager(){return *this;}template<class... T>void SendMessage(T...){}
};
struct CServiceBroker {
 static inline CWinSystemGbmGLESContext* window=nullptr;
 static Settings* GetSettingsComponent(){static Settings value;return &value;}
 static CWinSystemGbmGLESContext* GetWinSystem(){return window;}
 static Input& GetInputManager(){static Input value;return value;}
 static CGUIComponent* GetGUI(){static CGUIComponent value;return &value;}
};
struct CGraphicContext:std::recursive_mutex {
 RESOLUTION m_Resolution=FILM;bool m_bFullScreenRoot=true;
 int m_iScreenWidth=3840,m_iScreenHeight=2160;float m_fFPSOverride=0;
 struct Rect{void SetRect(int,int,float,float){}}m_scissors;
 bool IsValidResolution(RESOLUTION res){return res==0 || res==1;}
 void SetStereoView(RenderStereoView){}
 RESOLUTION_INFO GetResInfo(RESOLUTION res){return CDisplaySettings::GetInstance().GetResolutionInfo(res);}
 void UpdateInternalStateWithResolution(RESOLUTION res) @UPDATE@
 bool SetVideoResolutionInternal(RESOLUTION res,bool forceUpdate) @GRAPHICS@
};
bool CWinSystemGbmGLESContext::PrepareNvidiaModeRestore(const RESOLUTION_INFO& res) @NVIDIA@
bool CWinSystemGbmGLESContext::SetFullScreen(bool fullScreen,RESOLUTION_INFO& res,bool blankOtherDisplays) @WINDOW@
int main(){
 CWinSystemGbmGLESContext window;CServiceBroker::window=&window;CGraphicContext graphics;
 bool desktop=graphics.SetVideoResolutionInternal(0,false);
 bool replay=graphics.SetVideoResolutionInternal(1,false);
 std::cout<<"desktop_result="<<desktop<<" replay_result="<<replay
          <<" kodi_mode="<<graphics.m_Resolution<<" committed_mode="<<window.m_DRM->committed<<std::endl;
 assert(replay && window.m_DRM->committed==FILM &&
        "Kodi skipped the next 23.976 switch while HDMI was already restored to 60");
 assert(desktop && "Pending GPU retirement must finish before the synchronous mode change");
 for(unsigned cycle=0;cycle<32;++cycle){
  window.m_dvState.backend=CDVBridgeState::Backend::NVIDIA;
  window.m_dvContext=std::make_shared<Context>();window.m_dvShutdownFence=false;
  gpuReady=false;
  assert(graphics.SetVideoResolutionInternal(0,false));
  assert(graphics.m_Resolution==0 && window.m_DRM->committed==0);
  assert(graphics.SetVideoResolutionInternal(1,false));
  assert(graphics.m_Resolution==1 && window.m_DRM->committed==1);
 }
 // An unrecoverable retirement cannot partially change the selected/committed mode.
 CWinSystemGbmGLESContext broken;CServiceBroker::window=&broken;CGraphicContext bg;
 gpuBroken=true;gpuReady=false;
 assert(!bg.SetVideoResolutionInternal(0,false));
 assert(bg.m_Resolution==FILM && broken.m_DRM->committed==FILM && broken.m_DRM->mode.id==FILM);
 gpuBroken=false;
 // Driver and restoration refusals must preserve timing and permit a later retry.
 for(bool driverRefusal:{true,false}){
  CWinSystemGbmGLESContext refused;CServiceBroker::window=&refused;CGraphicContext rg;
  refused.m_DRM->accepts=!driverRefusal;refused.restoreOK=driverRefusal;
  assert(!rg.SetVideoResolutionInternal(0,false));
  assert(rg.m_Resolution==FILM && refused.m_DRM->committed==FILM && refused.m_DRM->mode.id==FILM);
  refused.m_DRM->accepts=true;refused.restoreOK=true;
  assert(rg.SetVideoResolutionInternal(0,false));
  assert(rg.m_Resolution==0 && refused.m_DRM->committed==0);
  assert(rg.SetVideoResolutionInternal(1,false) && refused.m_DRM->committed==FILM);
 }
 // The kernel-backend path retains its existing nonblocking retirement behavior.
 CWinSystemGbmGLESContext kernel;CServiceBroker::window=&kernel;CGraphicContext kg;
 kernel.m_dvState.backend=CDVBridgeState::Backend::KERNEL;unsigned before=finishes;
 assert(!kg.SetVideoResolutionInternal(0,false) && finishes==before);
 assert(kg.m_Resolution==FILM && kernel.m_DRM->committed==FILM);
}
'''
        for key,value in {
            'RETIRE':body(window,'bool CWinSystemGbmGLESContext::RetireDVContext('),
            'NVIDIA':body(window,'bool CWinSystemGbmGLESContext::PrepareNvidiaModeRestore('),
            'WINDOW':body(window,'bool CWinSystemGbmGLESContext::SetFullScreen('),
            'GRAPHICS':body(graphics,'bool CGraphicContext::SetVideoResolutionInternal('),
            'UPDATE':body(graphics,'void CGraphicContext::UpdateInternalStateWithResolution('),
        }.items():
            program=program.replace('@'+key+'@',value)
        with tempfile.TemporaryDirectory(prefix='nvidia-refresh-') as temporary:
            code,binary=Path(temporary)/'check.cpp',Path(temporary)/'check'
            code.write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc'),
                '-I'+str(TREE/'xbmc/windowing/gbm'),'-fsanitize=address,undefined',
                str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
