"""Held display changes notify around commits, including refused first output."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class ModeHoldTests(unittest.TestCase):
    def test_held_start_does_not_queue_an_unpresented_egl_buffer(self):
        method=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                    'bool CWinSystemGbmGLESContext::SetFullScreen(')
        program=r'''
#define HAVE_DVBRIDGE
#include "ModeChangeHold.h"
#include "rendering/RenderSystemTypes.h"
#include <atomic>
#include <cassert>
#include <memory>
#include <stdexcept>
#include <string>
using namespace KODI::WINDOWING::GBM;
struct RESOLUTION_INFO {int iWidth=3840,iHeight=2160,dwFlags=0; std::string strId="mode";};
using RESOLUTION=int;
constexpr int D3DPRESENTFLAG_MODE3DSBS=1,D3DPRESENTFLAG_MODE3DTB=2,LOGERROR=0,LOGDEBUG=1;
struct CLog {template<class... T> static void Log(T...) {}};
struct CEGLUtils {template<class... T> static void Log(T...) {}};
namespace DVBRIDGE {std::atomic<int> modeChangeResolution{0}; int DiagnosticNowMs(){return 0;}}
struct CDisplaySettings {
 static CDisplaySettings& GetInstance(){static CDisplaySettings value;return value;}
 RESOLUTION_INFO GetResolutionInfo(RESOLUTION) const{return {};}
};
struct Base {virtual ~Base()=default;};
struct CDRMAtomic:Base {bool IsSelectedModeCommitted()const{return true;}};
struct CWinSystemGbm {int commits=0; bool SetFullScreen(bool,RESOLUTION_INFO&,bool){++commits;return true;}};
struct CRenderSystemGLES {static void ResetRenderSystem(int,int){}};
struct EGL {int swaps=0;bool TrySwapBuffers(){++swaps;return true;}};
struct Gfx {void SetStereoMode(RenderStereoMode){}};
struct Window:CWinSystemGbm,CRenderSystemGLES {
 CModeChangeHold m_modeHold;CHeldModeAnnouncement m_modeAnnouncement;
 std::shared_ptr<int> m_dvBridge;
 std::shared_ptr<Base> m_DRM=std::make_shared<CDRMAtomic>();
 EGL m_eglContext;int m_nWidth=3840,m_nHeight=2160;bool held=true;
 bool HoldCB1Mode(RESOLUTION_INFO&){return held;}
 bool EndDVBridge(){return true;} bool RetireDVContext(){return true;}
 bool PrepareNvidiaModeRestore(const RESOLUTION_INFO&) {return true;}
 bool SupportsDVOutputMode(){return true;}
 bool CreateNewWindow(const char*,bool,RESOLUTION_INFO&){return true;}
 Gfx& GetGfxContext(){static Gfx gfx;return gfx;}
 void RefreshDVOutputCapabilities(){}
 bool set(bool fullScreen,RESOLUTION_INFO& res,bool blankOtherDisplays) METHOD
};
int main(){
 Window window;RESOLUTION_INFO res;
 assert(window.set(true,res,false));
 assert(window.m_modeHold.Holding()==CModeChangeHold::Kind::START);
 assert(window.m_eglContext.swaps==0 && window.commits==0);
 window.held=false;assert(window.set(true,res,false));
 assert(window.m_eglContext.swaps==1 && window.commits==1);
}
'''.replace('METHOD',method)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc'),
                '-I'+str(TREE/'xbmc/windowing/gbm'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_native_2d_mode_is_admitted_and_stereo_is_excluded(self):
        method=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                    'bool CWinSystemGbmGLESContext::CB1ModeCanJoin(')
        program=r'''
#include "rendering/RenderSystemTypes.h"
#include <cassert>
#include <cmath>
#include <memory>
#include <optional>
struct RESOLUTION_INFO {int iWidth=3840,iHeight=2160,dwFlags=0; float fRefreshRate=60;};
constexpr int D3DPRESENTFLAG_MODE3DSBS=1,D3DPRESENTFLAG_MODE3DTB=2;
struct Base {virtual ~Base()=default;};
struct Crtc {std::optional<int> GetPropertyValue(const char*) const {return 1;}};
struct CDRMAtomic:Base {
 Crtc crtc; const Crtc* GetCrtc() const {return &crtc;}
 bool HasPendingCB1Page() const {return false;}
 bool IsSelectedModeCommitted() const {return true;}
 RESOLUTION_INFO GetCurrentMode() const {return {};}
};
struct Gfx {RenderStereoMode mode=RenderStereoMode::OFF; RenderStereoMode GetStereoMode() const {return mode;}};
struct Window {
 std::shared_ptr<Base> m_DRM=std::make_shared<CDRMAtomic>();
 int m_nWidth=3840,m_nHeight=2160; Gfx gfx;
 const Gfx& GetGfxContext() const {return gfx;}
 bool joins(const RESOLUTION_INFO& res) const METHOD
};
int main() {
 Window window; RESOLUTION_INFO target; target.fRefreshRate=24;
 assert(window.joins(target));
 window.gfx.mode=RenderStereoMode::MONO; assert(!window.joins(target));
 window.gfx.mode=RenderStereoMode::SPLIT_HORIZONTAL; assert(!window.joins(target));
 window.gfx.mode=RenderStereoMode::OFF;
 target.dwFlags=D3DPRESENTFLAG_MODE3DSBS; assert(!window.joins(target));
 target.dwFlags=0; target.fRefreshRate=60; assert(!window.joins(target));
}
'''.replace('METHOD',method)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_selected_mode_can_prepare_before_its_first_atomic_commit(self):
        source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        method=body(source,'bool CWinSystemGbmGLESContext::BeginDVBridge()')
        gate='auto drm ='+method.split('auto drm =',1)[1].split('CDVWindowRetirement::PollOnce();',1)[0]
        program=r'''
#include "ModeChangeHold.h"
#include <cassert>
#include <memory>
using namespace KODI::WINDOWING::GBM;
struct CDRMAtomic { bool committed=false; bool IsSelectedModeCommitted() const {return committed;} };
struct Window {
 std::shared_ptr<CDRMAtomic> m_DRM=std::make_shared<CDRMAtomic>();
 CModeChangeHold m_modeHold;
 bool begin() { auto failure=[](const char*){return false;}; GATE return true; }
};
int main() {
 Window window; assert(!window.begin());
 window.m_modeHold.Start(0); assert(window.begin());
 window.m_modeHold.Cancel(); assert(!window.begin());
 window.m_DRM->committed=true; assert(window.begin());
 window.m_DRM.reset(); assert(!window.begin());
}
'''.replace('GATE',gate)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc/windowing/gbm'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_plain_completed_present_stall_thresholds(self):
        self.assertTrue((TREE/'xbmc/windowing/gbm/DVPresentStall.h').is_file(),
                        'completed presentation stall policy is missing')
        program=r'''
#include "DVPresentStall.h"
#include <cassert>
using namespace KODI::WINDOWING::GBM;
int main() {
 CDVPresentStall stall;
 using V=CDVPresentStall::Verdict;
 assert(stall.Presented(false,10000)==V::NONE);
 assert(stall.Presented(true,1999)==V::NONE);
 assert(stall.Presented(true,2000)==V::STALLED);
 assert(stall.Presented(true,40)==V::NONE && stall.Stalls()==0);
 assert(stall.Presented(true,3000)==V::STALLED);
 assert(stall.Presented(true,3000)==V::GIVE_UP);
 assert(stall.Presented(true,5000)==V::GIVE_UP);
 stall.Reset(); assert(stall.Stalls()==0);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc/windowing/gbm'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_deadline_cancellation_and_balanced_notifications(self):
        self.assertTrue((TREE/'xbmc/windowing/gbm/ModeChangeHold.h').is_file(),
                        'coherent mode-change policy is missing')
        program=r'''
#include "ModeChangeHold.h"
#include <cassert>
using namespace KODI::WINDOWING::GBM;
int main() {
 CModeChangeHold hold;
 CModeChangeHold::Change change{true,true,true,false,false,false,true};
 assert(CModeChangeHold::StartHolds(CModeChangeHold::Video::NATIVE_DV,change));
 assert(!CModeChangeHold::StartHolds(CModeChangeHold::Video::ORDINARY,change));
 change.sameWindow=false;
 assert(!CModeChangeHold::StartHolds(CModeChangeHold::Video::HDR,change));
 hold.Start(100); assert(!hold.Commits(3099)); assert(hold.Commits(3100));
 assert(hold.Take().second==CModeChangeHold::End::DEADLINE);
 hold.Start(100); assert(hold.Configured() && hold.Commits(101));
 assert(hold.Take().second==CModeChangeHold::End::CONFIGURED);
 hold.Stop(200); assert(!hold.Commits(2199)); assert(hold.ModeChange());
 assert(hold.Take().second==CModeChangeHold::End::MODE);
 hold.Start(0); assert(hold.Cancel()); assert(hold.Commits(1));
 CHeldModeAnnouncement announcement;
 announcement.Held(); assert(announcement.Before(true));
 announcement.After(false,true); assert(!announcement.Before(true));
 assert(announcement.Before(false)); announcement.After(true,false);
 assert(!announcement.Before(false));
 announcement.Held(); announcement.Dropped(); assert(!announcement.Before(true));
 announcement.Held(); assert(announcement.Before(true)); announcement.After(true,true);
 assert(!announcement.Before(true));
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc/windowing/gbm'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
