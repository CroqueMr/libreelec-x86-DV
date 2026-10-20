"""Exercise window teardown with an unpresented ordinary output surface."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class OutputWindowTeardownTests(unittest.TestCase):
    def test_pending_surface_and_failed_recreation(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        destroy = body(source, 'bool CWinSystemGbmGLESContext::DestroyWindow()')
        fullscreen = body(source, 'bool CWinSystemGbmGLESContext::SetFullScreen(')
        program = r'''
#include <cassert>
#include <memory>
#include <stdexcept>
enum {LOGDEBUG, LOGERROR, D3DPRESENTFLAG_MODE3DSBS=4, D3DPRESENTFLAG_MODE3DTB=8};
enum class RenderStereoMode {MONO};
struct RESOLUTION_INFO {int iWidth=1920,iHeight=1080,dwFlags=0;};
struct CLog {template<class... T> static void Log(T...) {}};
struct CEGLUtils {template<class... T> static void Log(T...) {}};
struct CRenderSystemGLES {static void ResetRenderSystem(int,int) {}};
struct DRM {virtual ~DRM()=default;};
struct CDRMAtomic : DRM {bool IsSelectedModeCommitted(){return true;}};
struct CWinSystemGbm {static bool SetFullScreen(bool,RESOLUTION_INFO&,bool){return true;}};
struct CWinSystemGbmEGLContext {
 bool pending=false,retired=false; int destroyed=0;
 bool DestroyWindow(){assert(!pending && retired); ++destroyed; return true;}
};
struct CWinSystemGbmGLESContext : CWinSystemGbmEGLContext {
 struct {void Cancel(){}} m_modeHold;
 bool m_dvOrdinaryFrame=false,m_dvStopPending=false,endOK=true,retireOK=true,rollbackOK=true;
 bool recreateOK=true; int rollbacks=0,swaps=0,m_nWidth=1280,m_nHeight=720;
 struct EGL {int* swaps; bool TrySwapBuffers(){++*swaps; return true;}} m_eglContext{&swaps};
 std::shared_ptr<DRM> m_DRM;
 bool EndDVBridge(){return endOK;}
 bool RetireDVContext(){retired=retireOK; return retireOK;}
 bool HasPendingDVOutputSurface(){return pending;}
 bool CompleteDVOutputSurface(bool submitted){assert(retired && !submitted); ++rollbacks;
   if(!rollbackOK) return false; pending=false; return true;}
 void ObserveDVImport(int,int,bool){}
 bool CreateNewWindow(const char*,bool,RESOLUTION_INFO&){return recreateOK;}
 struct Graphics {void SetStereoMode(RenderStereoMode){}} graphics;
 Graphics& GetGfxContext(){return graphics;}
 bool DestroyWindow(); bool SetFullScreen(bool,RESOLUTION_INFO&,bool);
};
bool CWinSystemGbmGLESContext::DestroyWindow() DESTROY
bool CWinSystemGbmGLESContext::SetFullScreen(bool fullScreen,RESOLUTION_INFO& res,
                                          bool blankOtherDisplays) FULLSCREEN
int main() {
 CWinSystemGbmGLESContext ordinary;
 ordinary.pending=ordinary.m_dvOrdinaryFrame=ordinary.m_dvStopPending=true;
 assert(ordinary.DestroyWindow());
 assert(ordinary.destroyed==1 && ordinary.rollbacks==1 && !ordinary.m_dvOrdinaryFrame && !ordinary.m_dvStopPending);
 CWinSystemGbmGLESContext failed;
 failed.pending=failed.m_dvOrdinaryFrame=true; failed.rollbackOK=false;
 assert(!failed.DestroyWindow() && failed.destroyed==0 && failed.pending);
 CWinSystemGbmGLESContext busy;
 busy.pending=busy.m_dvOrdinaryFrame=true; busy.retireOK=false;
 assert(!busy.DestroyWindow() && busy.rollbacks==0 && busy.destroyed==0);
 CWinSystemGbmGLESContext video;
 video.pending=true;
 assert(!video.DestroyWindow() && video.rollbacks==0 && video.destroyed==0);
 CWinSystemGbmGLESContext window; RESOLUTION_INFO resolution;
 window.recreateOK=false;
 assert(!window.SetFullScreen(true,resolution,false) && window.swaps==0);
 window.recreateOK=true;
 assert(window.SetFullScreen(true,resolution,false) && window.swaps==1);
}
'''.replace('DESTROY', destroy).replace('FULLSCREEN', fullscreen)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'),
                                    '-o', str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
