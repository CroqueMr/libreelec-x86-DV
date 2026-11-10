"""Execute native source admission for independent SDR and plain-HLG preferences."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class SDRHLGRoutes(unittest.TestCase):
    def test_native_admission_and_saved_preferences(self):
        header=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        header='\n'.join(l for l in header.splitlines() if not l.startswith('#include'))
        selector=body((TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSelection.h').read_text(),
                      'inline OutputSelection SelectOutput(')
        window=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(encoding='utf-8')
        start=window.index('    caps.processing=caps.hdr10Processing;')
        qualified=window[start:window.index('#endif',start)]
        program=r'''
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>
#include <memory>
#include <mutex>
#include <map>
#include <string>
#include <cassert>
#include <limits>
#define HAVE_DVBRIDGE
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
struct Settings {
 std::map<std::string,int> ints;
 int GetInt(const char* id){return ints[id];}
 double GetNumber(const char*){return 0;}
 bool GetBool(const char*){return false;}
};
auto stored=std::make_shared<Settings>();
struct Component {auto GetSettings(){return stored;}} component;
struct CServiceBroker {static auto GetSettingsComponent(){return &component;}};
namespace DVBRIDGE {uint64_t NextRevision(){static uint64_t n=1;return ++n;}
 bool HDR10PlusDVWholeSource(const float(&)[4],int width,int height){return width>0&&height>0;}
}
HEADER
namespace DVBRIDGE {
enum class OutputRoute {Vanilla,NativeDV,HDR10,SDR};
struct OutputSelection {OutputRoute route{};dvbridge_policy policy{};OutputReason reason{};};
OutputSelection SelectOutput(const OutputPreferences& preferences,const OutputCapabilities& caps) SELECTOR
}
int main(){
 using namespace DVBRIDGE;
 static_assert(int(OutputMode::SDR)==6 && int(HDR10SourceMode::SDR)==4);
 OutputPreferences p; p.output=OutputMode::SDR;
 OutputCapabilities c; c.sourceKnown=c.processingKnown=c.isDV=true;
 for(auto& a:c.processing)a={true,OutputReason::None};
 for(auto& a:c.hdr10Processing)a={true,OutputReason::None};
 // SDR is admitted on a sink with no HDR or Dolby Vision transport.
 assert(!c.nativeDV && !c.hdr10 && !c.hdr10plus);
 auto selected=SelectOutput(p,c);
 assert(selected.route==OutputRoute::SDR && selected.policy.mode==DVBRIDGE_MODE_SDR);
 assert(PolicyCode(selected.policy)==8);
 p.sdrPreset=2;p.sdrPeak=120;p.sdrGamma=2.35;p.sdrBlack=.02;
 selected=SelectOutput(p,c);
 assert(selected.route==OutputRoute::SDR && selected.policy.sdr.gamma==2.35);
 for(double invalid:{0.,501.,std::numeric_limits<double>::quiet_NaN()}){
  p.sdrPeak=invalid;
  assert(SelectOutput(p,c).route==OutputRoute::Vanilla);
  assert(SelectOutput(p,c).reason==OutputReason::SDRTargetInvalid);
 }
 p.sdrPreset=0;p.sdrPeak=0; // Presets do not consume hidden custom values.
 c.isDV=false;c.isHDR10=true;p.hdr10Source=HDR10SourceMode::SDR;
 assert(SelectOutput(p,c).route==OutputRoute::SDR);
 c.hdr10PlusSource=c.isHDR10Plus=true;p.hdr10PlusSource=HDR10SourceMode::SDR;
 assert(SelectOutput(p,c).route==OutputRoute::SDR);
 c.processingKnown=false;
 assert(SelectOutput(p,c).reason==OutputReason::ProcessingPending);
 p.hdr10PlusSource=HDR10SourceMode::Native;
 assert(SelectOutput(p,c).reason==OutputReason::None);
 p.hdr10PlusSource=HDR10SourceMode::SDR;c.processingKnown=true;
 c.processing[DVBRIDGE_MODE_SDR].usable=false;
 assert(SelectOutput(p,c).reason==OutputReason::NoGPUProcessing);
 c.processing[DVBRIDGE_MODE_SDR].reason=OutputReason::ActivationFailed;
 assert(SelectOutput(p,c).reason==OutputReason::ActivationFailed);
 c.processing[DVBRIDGE_MODE_SDR].reason=OutputReason::RestoreFailed;
 assert(SelectOutput(p,c).reason==OutputReason::RestoreFailed);
 assert(p.hdr10Source==HDR10SourceMode::SDR && p.hdr10PlusSource==HDR10SourceMode::SDR);
 c.isHDR10=c.hdr10PlusSource=c.isHDR10Plus=false;c.isHLG=true;
 assert(SelectOutput(p,c).route==OutputRoute::Vanilla);
 c.processingKnown=false;
 assert(SelectOutput(p,c).reason==OutputReason::None);
 c.processingKnown=true;
 p.hlgSource=HLGSourceMode::ReferenceDV;
 assert(SelectOutput(p,c).reason==OutputReason::NoDVTransport);
 c.nativeDV=true;
 c.processingKnown=false;
 assert(SelectOutput(p,c).reason==OutputReason::ProcessingPending);
 // The producer preserves raw GPU availability but disqualifies the current picture's processing array.
 for(int failure=0;failure<5;++failure){
  auto current=c;current.processingKnown=true;current.generation=9;
  struct Binding{unsigned picture=1;bool Valid()const{return picture!=0;}bool operator==(const Binding&)const=default;};
  struct Picture{Binding doviSourceBinding;long doviSourcePts=0;unsigned iFlags=0;std::string stereoMode;}sample;
  auto* picture=&sample;auto& caps=current;
  bool m_dvImportUsable=true;Binding m_dvImportBinding;unsigned m_dvImportGeneration=9;
  struct{float crop[4]{};int source_width=3840,source_height=2160;}m_dvImportGeometry;
  constexpr long AV_NOPTS_VALUE=-1;constexpr unsigned DVP_FLAG_INTERLACED=1;
  if(failure==0)m_dvImportUsable=false;
  if(failure==1)m_dvImportBinding.picture=2;
  if(failure==2)m_dvImportGeneration=10;
  if(failure==3)sample.doviSourcePts=AV_NOPTS_VALUE;
  if(failure==4)sample.iFlags=DVP_FLAG_INTERLACED;
  QUALIFIED
  assert(current.hdr10Processing[DVBRIDGE_MODE_STANDARD].usable);
  assert(!current.processing[DVBRIDGE_MODE_STANDARD].usable);
  auto invalid=SelectOutput(p,current);assert(invalid.route==OutputRoute::Vanilla&&invalid.reason==OutputReason::SourceIneligible);
 }
 c.processingKnown=true;c.processing[DVBRIDGE_MODE_STANDARD]={false,OutputReason::SourceIneligible};
 assert(SelectOutput(p,c).reason==OutputReason::SourceIneligible);
 c.processing[DVBRIDGE_MODE_STANDARD]={true,OutputReason::None};
 selected=SelectOutput(p,c);
 assert(selected.route==OutputRoute::NativeDV && selected.policy.mode==DVBRIDGE_MODE_STANDARD);
 for(int saved=0;saved<=6;++saved){
  p.output=static_cast<OutputMode>(saved);selected=SelectOutput(p,c);
  assert(selected.route==OutputRoute::NativeDV && selected.policy.mode==DVBRIDGE_MODE_STANDARD);
  assert(selected.policy.adaptive==DVBRIDGE_ADAPTIVE_A && !selected.policy.master_ipt);
  assert(dvbridge_policy_validate(&selected.policy)==DVBRIDGE_POLICY_VALID);
 }
 p.output=OutputMode::SDR;
 // HLG-base Dolby Vision with RPU stays on full DV reconstruction / SDR.
 c.isDV=true;
 assert(SelectOutput(p,c).route==OutputRoute::Vanilla); // SDR renderer unavailable, no BL-only HLG success.
 c.processing[DVBRIDGE_MODE_SDR].usable=true;
 assert(SelectOutput(p,c).route==OutputRoute::SDR);
 p.output=OutputMode::Disabled;c.processingKnown=false;
 assert(SelectOutput(p,c).route==OutputRoute::Vanilla && SelectOutput(p,c).reason==OutputReason::None);
 p.output=OutputMode::SDR;c.processingKnown=true;
 c.stereoSource=true;assert(SelectOutput(p,c).route==OutputRoute::Vanilla);
 stored->ints["dvbridge.outputmode"]=6;
 stored->ints["dvbridge.hdr10source"]=4;
 stored->ints["dvbridge.hdr10plussource"]=4;
 stored->ints["dvbridge.hlgsource"]=1;
 auto before=FrameOutputSettings();
 assert(before.hdr10Source==HDR10SourceMode::SDR);
 for(int i=0;i<10;++i){
  auto hlg=FrameOutputSettings(false,true),plus=FrameOutputSettings(true),dv=FrameOutputSettings();
  assert(hlg.hdr10Source==HDR10SourceMode::ReferenceDV);
  assert(plus.hdr10Source==HDR10SourceMode::SDR && dv.output==OutputMode::SDR);
  assert(hlg.revision==before.revision && plus.revision==before.revision && dv.revision==before.revision);
 }
}
'''.replace('HEADER',header).replace('SELECTOR',selector).replace('QUALIFIED',qualified)
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(repo/'CB1/src'),
                '-I'+str(TREE/'xbmc'),str(root/'test.cpp'),str(repo/'CB1/src/dvbridge_policy.c'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_sdr_composition_uses_resolved_target_before_gui(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        prepare=body(source,'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(')
        start=prepare.index('    if (m_prepared && policy.mode==DVBRIDGE_MODE_SDR && !m_direct)')
        resolve=prepare[start:prepare.index('    const bool fenced',start)]
        header=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h').read_text()
        target=body(header,'bool GetHDR10OutputTarget(')
        program=r'''
#include <cassert>
#include "dvbridge_policy.h"
int calls=0;bool accept=true;
bool dvbridge_render_sdr_policy_resolve(int*,int target,bool flip,bool limited,unsigned bits){
 assert(target==42 && flip && !limited && bits==10);++calls;return accept;
}
struct Renderer {
 int renderer{},*m_renderer=&renderer,m_scanout=42;unsigned m_scanoutFramebuffer=17,m_outputBits=10;
 bool m_prepared=true,m_direct=false,m_hdr10Limited=false,m_hdr10=true,m_live=true,m_guiComposed=false;
 void prepare(){dvbridge_policy policy{};policy.mode=DVBRIDGE_MODE_SDR;RESOLVE}
 bool target(unsigned& framebuffer,unsigned& bits) TARGET
};
int main(){
 Renderer r;unsigned fb=0,bits=0;
 assert(!r.target(fb,bits));r.prepare();assert(calls==1 && r.m_direct && r.m_prepared);
 assert(r.target(fb,bits) && fb==17 && bits==10 && r.m_guiComposed);
 // A rejected resolve cannot expose the reconstructed PQ texture as SDR GUI output.
 accept=false;Renderer failed;failed.prepare();assert(!failed.m_prepared && !failed.m_direct);
 assert(!failed.target(fb,bits));
}
'''.replace('RESOLVE',resolve).replace('TARGET',target)
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(repo/'CB1/src'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_processing_labels_keep_clean_unicode(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h').read_text(encoding='utf8')
        self.assertIn(' \u00b7 ',source)
        self.assertNotIn('\u00c3',source)
        self.assertNotIn('\ufffd',source)


if __name__=='__main__':unittest.main()
