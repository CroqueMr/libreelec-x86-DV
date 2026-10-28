"""HDR10+ requires a dynamic transport, not just static PQ support."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class HDR10PlusSelectionTests(unittest.TestCase):
    def test_dynamic_output_admission_preserves_other_routes(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSelection.h').read_text()
        implementation=body(source,'inline OutputSelection SelectOutput(')
        window=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        wants=body(window,'bool DVBRIDGE::WantsNativeOutput(const VideoPicture* picture)')
        renderer=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp').read_text()
        configure=body(renderer,'bool CLinuxRendererGLES::ConfigureVideoOutput(const VideoPicture& picture)')
        settings=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        profile=body(settings,'bool ProfileValid() const')
        program=r'''
#define HAVE_DVBRIDGE
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include "dvbridge_policy.h"
#include <atomic>
#include <cassert>
#include <cmath>
namespace DVBRIDGE {
enum class OutputMode {Standard,HDR10,Disabled};
enum class HDR10SourceMode {Native,ReferenceDV};
enum class OutputRoute {Vanilla,NativeDV,HDR10};
struct OutputSelection {OutputRoute route{};dvbridge_policy policy{};OutputReason reason{};};
struct OutputPreferences {
 OutputMode output=OutputMode::HDR10;HDR10SourceMode hdr10Source=HDR10SourceMode::Native;
 bool allowMasterFallback=true;dvbridge_mode mode=DVBRIDGE_MODE_HDR10PLUS;
 double peak=1000;int panel=0,gamut=2;
 bool ProfileValid()const PROFILE
 dvbridge_policy Policy()const{return {.revision=1,.mode=mode};}
 dvbridge_policy HDR10Policy()const{return Policy();}
};
using Caps=OutputCapabilities;
OutputSelection select(const OutputPreferences& preferences,const Caps& caps) BODY
OutputSelection SelectOutput(const OutputPreferences& p,const Caps& c){return select(p,c);}
OutputPreferences preferences;Caps capabilities;
struct Binding {bool Valid()const{return true;}};
}
struct VideoPicture {
 DVBRIDGE::Binding doviSourceBinding;
 struct {DVBRIDGE::Binding Binding()const{return {};}} doviMetadata;
 unsigned iFlags=0;std::string stereoMode;int color_transfer=16;
};
namespace DVBRIDGE {bool WantsNativeOutput(const ::VideoPicture*);}
constexpr int DVP_FLAG_INTERLACED=1,LOGWARNING=1,LOGERROR=2,LOGDEBUG=3;
struct CLog {template<class... T>static void Log(T...) {}};
namespace DVBRIDGE {OutputPreferences FrameOutputSettings(){return preferences;}}
bool NativeDVEligible(bool,bool,bool,bool){return true;}
struct Window {virtual ~Window()=default;};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext:Window {
 int hdrSignals=0;
 auto SelectedDVOutput(const ::VideoPicture*){return DVBRIDGE::select(DVBRIDGE::preferences,DVBRIDGE::capabilities);}
 auto GetDVOutputCapabilities(const ::VideoPicture*,bool){return DVBRIDGE::capabilities;}
 static bool DVBridgeRequested(const ::VideoPicture* p){return DVBRIDGE::WantsNativeOutput(p);}
 bool HasPendingDVBridgeRestore(){return false;}
 bool SetVideoOutput(const ::VideoPicture*){return true;}
 void SetColorimetry(const ::VideoPicture*){}
 bool SetHDR(const ::VideoPicture*){++hdrSignals;return true;}
 bool SetGuiCompositing(int){return true;}
 bool ConfigureHDR10Conversion(const ::VideoPicture&){return true;}
};
}
using KODI::WINDOWING::GBM::CWinSystemGbmGLESContext;
CWinSystemGbmGLESContext window;
struct CServiceBroker {static auto* GetWinSystem(){return &window;}};
bool DVBRIDGE::WantsNativeOutput(const ::VideoPicture* picture) WANTS
struct CLinuxRendererGLES {
 bool m_bConfigured=false,m_dvRequested=false,m_passthroughHDR=false,m_hdrFboActive=false;
 bool ConfigureVideoOutput(const ::VideoPicture& picture) CONFIGURE
};
int main(){
 using namespace DVBRIDGE;OutputPreferences p;Caps c;
 c.sourceKnown=c.isDV=c.processingKnown=c.hdr10=c.nativeDV=true;
 for(auto& mode:c.processing)mode={true,OutputReason::None};
 auto r=select(p,c);
 assert(r.route==OutputRoute::HDR10 && r.policy.mode==DVBRIDGE_MODE_HDR10_BASIC && r.reason!=OutputReason::None);
 c.hdr10plus=true;r=select(p,c);
 assert(r.route==OutputRoute::HDR10 && r.policy.mode==DVBRIDGE_MODE_HDR10PLUS && r.reason==OutputReason::None);
 c.hdr10=false;r=select(p,c);assert(r.route==OutputRoute::Vanilla);
 c.hdr10=true;p.mode=DVBRIDGE_MODE_HDR10_EXPERT;c.hdr10plus=false;
 r=select(p,c);assert(r.policy.mode==DVBRIDGE_MODE_HDR10_EXPERT && r.reason==OutputReason::None);
 p.peak=0;r=select(p,c);
 assert(r.route==OutputRoute::Vanilla && r.reason==OutputReason::TVProfileRequired);
 // Expert with default/unset TV peak must configure ordinary HDR immediately,
 // not provisionally claim CB1 output while waiting for the first import.
 c.processingKnown=false;c.nativeDV=false;preferences=p;capabilities=c;
 CLinuxRendererGLES renderer;::VideoPicture picture;
 assert(renderer.ConfigureVideoOutput(picture));
 assert(window.hdrSignals==1 && !renderer.m_dvRequested && renderer.m_passthroughHDR);
 assert(select(p,c).reason==OutputReason::TVProfileRequired);
 p.peak=1000;preferences=p;
 assert(DVBRIDGE::WantsNativeOutput(&picture));
 c.processingKnown=true;capabilities=c;
 assert(select(p,c).route==OutputRoute::HDR10);
 p.peak=0;
 p.mode=DVBRIDGE_MODE_HDR10_BASIC;r=select(p,c);
 assert(r.route==OutputRoute::HDR10 && r.reason==OutputReason::None);
 p.mode=DVBRIDGE_MODE_HDR10_EXPERT;r=select(p,c);
 assert(r.route==OutputRoute::Vanilla && r.reason==OutputReason::TVProfileRequired);
 p.peak=1000;r=select(p,c);
 assert(r.route==OutputRoute::HDR10 && r.policy.mode==DVBRIDGE_MODE_HDR10_EXPERT);
 c.nativeDV=true;p.output=OutputMode::Standard;p.mode=DVBRIDGE_MODE_MASTER_REFERENCE;
 r=select(p,c);assert(r.route==OutputRoute::NativeDV && r.policy.mode==DVBRIDGE_MODE_MASTER_REFERENCE);
 c.stereoSource=true;assert(select(p,c).route==OutputRoute::Vanilla);
}
'''.replace('BODY',implementation).replace('WANTS',wants).replace('CONFIGURE',configure).replace('PROFILE',profile)
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);code=root/'check.cpp';binary=root/'check'
            code.write_text(program)
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+str(repo/'CB1/src'),str(code),'-o',str(binary)],
                capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
