"""Execute the shipped revision admission and renderer setup order without KMS."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import body


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi tree')
class MasterPanelSurface(unittest.TestCase):
    def run_cpp(self, program):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'),
                                    '-o', str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_master_panel_redraw_keeps_fenced_async_admission(self):
        source = (Path(os.environ['KODI_NATIVE_SOURCE_TREE']) /
                  'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        prepare = body(source, 'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(')
        admission = prepare[prepare.index('  const bool sameGeometry ='):
                            prepare.index('  if (m_dvPolicyActive)')]
        self.run_cpp(r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
enum {DVBRIDGE_MODE_DISABLED=0,DVBRIDGE_MODE_STANDARD=1,DVBRIDGE_MODE_MASTER_REFERENCE=5};
namespace DVBRIDGE { uint64_t NextRevisionAfter(uint64_t value){return value+1;} }
struct Binding {uint64_t stream=1,picture=42,revision=7;bool operator==(const Binding&)const=default;};
struct Layer {Binding binding;bool lease=true;int scalingMethod=0;};
struct Geometry {int source_width=3840,source_height=2160,x=0,y=0,width=3840,height=2160;
 int target_width=3840,target_height=2160;float crop[4]{};};
enum class FrameStatus {Failed,Ready,Pending};
struct Admission {
 Layer base;Layer* enhancement=nullptr;Geometry geometry,m_sourceGeometry;
 bool m_geometryKnown=true,m_pending=false,m_hasCommitted=true,allowPacked=true;
 bool m_committedPacked=true,m_direct=true,m_dvPolicyActive=false;
 bool m_overlayVisible=true,m_pendingOverlayVisible=true;
 bool m_nativeOverlayEnabled=true;int m_nativeOverlay=0;
 int m_effectiveMode=5,m_committedMode=5;struct {int mode=5;}policy;
 int m_spatialMethod=0;
 struct {uint64_t revision=3;} preferences;
 Binding m_committedBinding,m_pendingBinding,m_failedIdentity{0,0,0},m_pendingIdentity;
 uint64_t m_committedRevision=7,m_geometryRevision=0;
 uint64_t m_nativeOverlayRevision=2,m_committedOverlayRevision=1,m_pendingOverlayRevision=2;
 bool allowAsync=true,asyncSetting=true,fallback=false,m_fallback=false;
 bool m_pendingHDR10Fallback=false,m_directUsable=false,m_pendingMetadata=false;
 void* m_renderer=nullptr;
 bool PollReady(){return true;}void Cancel(){m_pending=false;}
 bool result=false;uint64_t selectedRevision=0;
 FrameStatus run(){
  @@ADMISSION@@
  result=eligible;selectedRevision=revision;return FrameStatus::Ready;
 }
};
int main(){
 Admission panel;
 for(unsigned i=0;i<1000;++i){
  panel.result=false;panel.run();
  assert(panel.result && "Master GUI refresh lost async admission");
  assert(panel.selectedRevision>panel.m_committedRevision);
  panel.m_committedRevision=panel.selectedRevision;
  panel.m_committedOverlayRevision=panel.m_nativeOverlayRevision++;
 }
 Admission next;next.base.binding.picture++;next.run();assert(next.result);
 Admission paused;paused.m_nativeOverlayRevision=1;paused.run();assert(paused.result);
 Admission standard;standard.policy.mode=standard.m_committedMode=1;standard.m_directUsable=true;
 standard.run();assert(!standard.result);
 Admission changed;changed.preferences.revision=20;changed.run();assert(!changed.result);
 Admission resized;resized.geometry.width=3000;resized.run();assert(!resized.result);
 Admission target;target.geometry.target_width=1920;target.run();assert(!target.result);
 Admission crop;crop.geometry.crop[0]=1;crop.run();assert(!crop.result);
 Admission filter;filter.base.scalingMethod=1;filter.run();assert(!filter.result);
 Admission stream;stream.base.binding.stream=2;stream.run();assert(!stream.result);
 Admission lease;lease.base.lease=false;lease.run();assert(!lease.result);
 Admission mode;mode.m_committedMode=1;mode.run();assert(!mode.result);
 Admission disabled;disabled.asyncSetting=false;disabled.run();assert(!disabled.result);
 Admission fallback;fallback.fallback=true;fallback.run();assert(!fallback.result);
 Admission composed;composed.m_committedPacked=false;composed.run();assert(!composed.result);
 Admission unpacked;unpacked.allowPacked=false;unpacked.run();assert(!unpacked.result);
 std::cout<<"1000 panel redraws retain async; transition/lease guards retained\n";
}
'''.replace('@@ADMISSION@@', admission).replace('m_pendingMetadata.Data()', 'm_pendingMetadata')
            .replace('dvbridge_render_dv_policy_update_overlay(m_renderer,',
                     '[](void*,int*,bool){return true;}(m_renderer,')
            .replace('DVBRIDGE_MODE_ENHANCED_DV', '3'))

    def test_dv_configure_defers_renderer_until_import_and_eight_bit_surface(self):
        source = (Path(os.environ['KODI_NATIVE_SOURCE_TREE']) /
                  'xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp').read_text()
        configure = body(source, 'bool CLinuxRendererGLES::ConfigureVideoOutput(')
        self.run_cpp(r'''
#include <cassert>
#include <iostream>
enum {LOGWARNING,LOGERROR,LOGDEBUG,AVCOL_TRC_SMPTE2084=16};
struct VideoPicture {int color_transfer=16;};
struct CLog {template<class...T>static void Log(T...) {}};
namespace DVBRIDGE {enum class OutputRoute {NativeDV,HDR10,Vanilla};}
struct WindowBase {virtual ~WindowBase()=default;
 virtual bool SetVideoOutput(const VideoPicture*)=0;
 virtual void SetColorimetry(const VideoPicture*)=0;
 virtual bool SetHDR(const VideoPicture*)=0;
 virtual bool SetGuiCompositing(int)=0;
};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext:WindowBase {
 bool requested=true,ready=false;int depth=10,initCalls=0;
 DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::NativeDV;
 static bool DVBridgeRequested(const VideoPicture*);
 bool SetVideoOutput(const VideoPicture*)override {return true;}
 void SetColorimetry(const VideoPicture*)override {}
 bool SetHDR(const VideoPicture*)override {return true;}
 bool SetGuiCompositing(int)override {return true;}
 bool HasPendingDVBridgeRestore(){return false;}
 struct Selection {DVBRIDGE::OutputRoute route;};
 Selection SelectedDVOutput(const VideoPicture*){return {route};}
 bool BeginDVBridge(){++initCalls;return ready && depth==8;}
 bool ConfigureHDR10Conversion(const VideoPicture&){++initCalls;return ready && depth>=10;}
};
}
using Window=KODI::WINDOWING::GBM::CWinSystemGbmGLESContext;
Window window;
bool Window::DVBridgeRequested(const VideoPicture*){return window.requested;}
struct CServiceBroker {static WindowBase* GetWinSystem(){return &window;}};
struct CLinuxRendererGLES {
 bool m_dvRequested=false,m_passthroughHDR=false,m_hdrFboActive=false,m_bConfigured=true;
 bool ConfigureVideoOutput(const VideoPicture& picture) @@CONFIGURE@@
};
int main(){
 VideoPicture picture;
 for(int depth:{8,10}){
  window=Window{};window.depth=depth;CLinuxRendererGLES renderer;
  assert(renderer.ConfigureVideoOutput(picture) && "DV setup must admit import before surface activation");
  assert(window.initCalls==0 && renderer.m_bConfigured && renderer.m_dvRequested);
  // The render-side import owns the subsequent native surface transaction.
  window.ready=true;window.depth=8;
  assert(window.BeginDVBridge() && window.initCalls==1);
 }
 window=Window{};window.route=DVBRIDGE::OutputRoute::HDR10;
 window.ready=true;window.depth=10;CLinuxRendererGLES hdr;
 assert(hdr.ConfigureVideoOutput(picture) && window.initCalls==1);
 window=Window{};window.route=DVBRIDGE::OutputRoute::HDR10;
 CLinuxRendererGLES failed;assert(!failed.ConfigureVideoOutput(picture));
 window=Window{};window.requested=false;CLinuxRendererGLES vanilla;
 assert(vanilla.ConfigureVideoOutput(picture) && window.initCalls==0);
 std::cout<<"DV import precedes native activation; HDR10 and vanilla retain setup\n";
}
'''.replace('@@CONFIGURE@@', configure).replace('#ifdef HAVE_DVBRIDGE', '#if 1'))


if __name__ == '__main__':
    unittest.main()
