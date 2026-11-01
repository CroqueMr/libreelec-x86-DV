"""Execute both NVIDIA restore callers with the native GBM buffer ownership."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class NvidiaBufferRestore(unittest.TestCase):
    def test_restore_uses_the_buffer_already_locked_by_its_caller(self):
        base = TREE / 'xbmc/windowing/gbm'
        window = (base / 'WinSystemGbm.cpp').read_text()
        header = (base / 'WinSystemGbm.h').read_text()
        context = (base / 'WinSystemGbmGLESContext.cpp').read_text()
        surface = (base / 'GBMUtils.cpp').read_text()
        present = body(context, 'void CWinSystemGbmGLESContext::PresentFrame(')
        ordinary = present.split('  if (m_dvOrdinaryFrame)\n', 1)[1]
        ordinary = ordinary[:ordinary.index('    if (!submitted)')]
        ordinary = ordinary[ordinary.index('{') + 1:].replace('return;', 'return false;') + '\nreturn submitted;'
        hdr = present.split('  if (m_hdrConversion)\n', 1)[1]
        hdr = hdr[hdr.index('        auto drm ='):hdr.index('      }\n      else if (asynchronous)')]
        signature = re.search(r'bool FlipDVBridgePage\([^;]+;', header).group()
        program = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <queue>
struct gbm_bo {unsigned format=1;};
constexpr unsigned DRM_FORMAT_XRGB8888=1,DRM_FORMAT_ARGB8888=2;
constexpr unsigned DRM_MODE_FLAG_INTERLACE=1,DRM_MODE_FLAG_DBLSCAN=2;
unsigned gbm_bo_get_format(gbm_bo* bo){return bo->format;}
unsigned gbm_bo_get_width(gbm_bo*){return 3840;}
unsigned gbm_bo_get_height(gbm_bo*){return 2160;}
struct CResolutionUtils {static bool IsCB1RefreshRate(double){return true;}};
struct DRM {virtual ~DRM()=default;};
struct CDRMAtomic:DRM {
 struct Connector {bool SupportsProperty(const char*){return false;}}connector;
 struct Mode {unsigned hdisplay=3840,vdisplay=2160,flags=0,htotal=4400,vtotal=2250,clock=594000;}mode;
 bool stageOK=true,commitOK=true,active=false;unsigned accepted=0,missing=0;
 gbm_bo* acceptedBuffer=nullptr;
 auto* GetConnector(){return &connector;} auto* GetSelectedMode(){return &mode;}
 bool AddProperty(Connector*,const char*,int){return true;}
 bool IsActive(){return active;} bool IsSelectedModeCommitted(){return true;}
 void SetActive(bool value){active=value;}
 bool HasPendingCB1Page(){return false;}
 bool FlipPageTransactional(gbm_bo* bo,bool,bool=false){
   if(!bo){++missing;return false;}if(!commitOK)return false;
   ++accepted;acceptedBuffer=bo;return true;
 }
 void StageHDR10Plus(int,int){}
 bool HDR10PlusActive(){return false;}
};
struct CDVBridgeState {
 enum class Backend{KERNEL,NVIDIA};Backend backend=Backend::NVIDIA;bool captured=true;
 bool Captured(){return captured;}Backend CapturedBackend(){return backend;}
 bool Stage(CDRMAtomic& drm,bool){return drm.stageOK;}
 void Restored(){captured=false;}
};
struct Surface {
 struct CGBMSurfaceBuffer {
   gbm_bo buffer;bool available;explicit CGBMSurfaceBuffer(bool available):available(available){}
   gbm_bo* Get(){return available?&buffer:nullptr;}
 };
 bool m_surface=true;
 std::unique_ptr<CGBMSurfaceBuffer> m_pendingBuffer,m_scanoutBuffer;
 std::queue<std::unique_ptr<CGBMSurfaceBuffer>> m_buffers;
 Surface& GetDevice(){return *this;}Surface& GetSurface(){return *this;}
 gbm_bo* LockTransactionalBuffer() @LOCK@
 void CompleteTransactionalBuffer(bool presented) @COMPLETE@
 void EndTransactionalMode() @END@
};
namespace DVBRIDGE {struct PlaybackNotification{static void OrdinaryOutputAccepted(bool){}};}
struct Window {
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
 std::shared_ptr<Surface> m_GBM=std::make_shared<Surface>();
 CDVBridgeState m_dvState;bool m_dvStopPending=false;
 struct EGL {bool TrySwapBuffers(){return true;}} m_eglContext;
 bool StageOrdinaryDVOutput(void*){return true;}
 bool CompleteDVBridgePage(){return true;}bool SupportsDVOutputMode(){return true;}
 bool RequeueOutputProperties(){return true;}bool FloatOutputUsable(){return true;}
 void AnnounceCB1Mode(bool){}void CompleteCB1Mode(bool,bool){}
 @SIGNATURE@
 bool Ordinary(bool rendered){@ORDINARY@}
 bool HDR(){bool presented=false,asynchronous=false;
   struct {int hdr10plus=0,informationGeneration=1;bool hdr10plusAccepted=false;}submitted;
   @HDR@
   return presented;
 }
};
@FLIP@
int main(){
 for(bool hdr:{false,true})for(bool nvidia:{true,false})for(bool active:{false,true}){
   Window window;auto drm=std::dynamic_pointer_cast<CDRMAtomic>(window.m_DRM);
   window.m_dvState.backend=nvidia?CDVBridgeState::Backend::NVIDIA:CDVBridgeState::Backend::KERNEL;
   drm->active=active;
   bool result=hdr?window.HDR():window.Ordinary(true);
   assert(result && "NVIDIA restoration must not acquire the same GBM buffer twice");
   assert(drm->missing==0 && drm->acceptedBuffer);
   assert(drm->accepted==(nvidia&&active?2u:1u));
   assert(!window.m_GBM->m_pendingBuffer);
   auto& surface=*window.m_GBM;
   assert(drm->acceptedBuffer==(nvidia?surface.m_buffers.back()->Get():surface.m_scanoutBuffer->Get()));
   assert(nvidia ? !window.m_dvState.captured : window.m_dvState.captured);
   Window failed;auto fd=std::dynamic_pointer_cast<CDRMAtomic>(failed.m_DRM);
   fd->commitOK=false;
   assert(!(hdr?failed.HDR():failed.Ordinary(true)) && failed.m_dvState.captured);
   assert(!failed.m_GBM->m_pendingBuffer);
   fd->commitOK=true;
   assert(hdr?failed.HDR():failed.Ordinary(true));
   Window absent;absent.m_GBM->m_surface=false;
   assert(!(hdr?absent.HDR():absent.Ordinary(true)) && absent.m_dvState.captured);
 }
}
'''
        for marker, value in {
            'LOCK': body(surface, 'gbm_bo* CGBMUtils::CGBMDevice::CGBMSurface::LockTransactionalBuffer('),
            'COMPLETE': body(surface, 'void CGBMUtils::CGBMDevice::CGBMSurface::CompleteTransactionalBuffer('),
            'END': body(surface, 'void CGBMUtils::CGBMDevice::CGBMSurface::EndTransactionalMode('),
            'SIGNATURE': signature, 'ORDINARY': ordinary, 'HDR': hdr,
            'FLIP': 'bool Window::FlipDVBridgePage' +
                window.split('bool CWinSystemGbm::FlipDVBridgePage', 1)[1].split('{', 1)[0] +
                body(window, 'bool CWinSystemGbm::FlipDVBridgePage('),
        }.items():
            program = program.replace('@' + marker + '@', value)
        with tempfile.TemporaryDirectory(prefix='nvidia-restore-') as temporary:
            code, binary = Path(temporary)/'check.cpp', Path(temporary)/'check'
            code.write_text(program)
            build = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(code), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
