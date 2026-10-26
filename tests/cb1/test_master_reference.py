"""Master is an appended DV-only policy, never an alias for AI or Adaptive."""
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class MasterReferenceTests(unittest.TestCase):
    def test_master_async_uses_its_own_direct_admission(self):
        from test_native_video_source import body
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        cpp=(tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        prepare=body(cpp,'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(')
        eligible=re.search(r'const bool eligible = (.*?);',prepare,re.S).group(1)
        direct=body(body(cpp,'bool CDVBridgeGLES::Pack('),'if (m_direct)')
        receipt=re.search(r'm_submission = \{m_pendingIdentity,m_scanout,0,\+\+m_submissionSequence,(.*?)\};',direct,re.S).group(1)
        program=r'''
#include <cassert>
enum {DVBRIDGE_MODE_DISABLED=0,DVBRIDGE_MODE_MASTER_REFERENCE=5};
bool eligible(int mode,bool m_directUsable,bool lease=true){
 bool allowAsync=true,asyncSetting=true,fallback=false,m_fallback=false,m_pendingHDR10Fallback=false;
 bool m_hasCommitted=true,sameGeometry=true,masterOverlayRefresh=false;struct{int mode;}policy{mode};int m_committedMode=mode;
 struct Binding{int stream=1,revision=1;};struct Layer{bool lease;Binding binding;};
 Layer base{lease,{}},*enhancement=nullptr;Binding m_committedBinding;int revision=1,m_committedRevision=1;
 return @@ELIGIBLE@@;
}
bool receipt(int m_effectiveMode,bool m_directUsable,bool m_asyncEligible=true){return @@RECEIPT@@;}
int main(){assert(eligible(5,false) && receipt(5,false));assert(!eligible(1,false) && !receipt(1,false));
 assert(eligible(1,true) && receipt(1,true));assert(!eligible(5,false,false) && !receipt(5,false,false));}
'''.replace('@@ELIGIBLE@@',eligible).replace('@@RECEIPT@@',receipt)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],text=True,capture_output=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_master_source_phase_admission_matches_raw_import(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        window=(tree/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        # Compile the actual source admission, including unspecified defaults.
        phase=re.search(r'const auto masterChroma = .*?const bool masterPhase = .*?;',window,re.S)
        self.assertIsNotNone(phase,'Master phase admission must precede output selection')
        program=r'''
#include <cassert>
enum {AVCHROMA_LOC_UNSPECIFIED,AVCHROMA_LOC_LEFT,AVCHROMA_LOC_TOPLEFT,AVCHROMA_LOC_CENTER};
struct EL {int chroma_location;};struct Picture{int chroma_position;struct{int profile;}doviSourceInfo;EL* doviEnhancement;};
bool admits(Picture* picture,bool residual){struct{bool residual;}raw{residual};@@PHASE@@ return masterPhase;}
int main(){EL el{AVCHROMA_LOC_LEFT};Picture p{AVCHROMA_LOC_LEFT,{7},&el};
 assert(admits(&p,true));p.chroma_position=AVCHROMA_LOC_TOPLEFT;assert(!admits(&p,true) && admits(&p,false));
 p.chroma_position=AVCHROMA_LOC_UNSPECIFIED;assert(!admits(&p,true) && admits(&p,false));
 p.chroma_position=AVCHROMA_LOC_LEFT;el.chroma_location=AVCHROMA_LOC_UNSPECIFIED;assert(!admits(&p,true));
 el.chroma_location=AVCHROMA_LOC_TOPLEFT;assert(!admits(&p,true));
 p.chroma_position=AVCHROMA_LOC_TOPLEFT;assert(admits(&p,true));
 p.chroma_position=el.chroma_location=AVCHROMA_LOC_UNSPECIFIED;assert(admits(&p,true));
 p.doviEnhancement=nullptr;assert(!admits(&p,true) && admits(&p,false));
 p.chroma_position=AVCHROMA_LOC_CENTER;assert(!admits(&p,false));
}
'''.replace('@@PHASE@@',phase.group(0))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],text=True,capture_output=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_master_gui_and_direct_admission_ignore_native_optimization_latches(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        from test_native_video_source import body
        cpp=(tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        header=(tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h').read_text()
        window=(tree/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        gui=re.search(r'const bool fullGUI = (.*?);',window,re.S).group(1)
        master_capture=re.search(r'const bool masterCapture=.*?;',window,re.S).group(0)
        prepare=body(cpp,'bool CDVBridgeGLES::Prepare(')
        condition=re.search(r'if \(!m_hdr10 && allowPacked.*?\n\s*\{',prepare,re.S).group(0)
        direct=body(prepare,condition[:-1].strip())
        failure=body(direct,'if (!m_direct)')
        compose=body(header,'static constexpr bool CanComposeSDRGUI(')
        program=r'''
#include <cassert>
constexpr int DVBRIDGE_MODE_MASTER_REFERENCE=5;
struct CDVBridgeGLES {static bool CanComposeSDRGUI(bool enabled,bool hdr10,bool capture,int width,int height,unsigned pqDraws) @@COMPOSE@@;};
bool gui(int mode,bool optimized,bool capturing=false) {
 bool m_guiWillRender=true,m_hdrConversion=false;int m_guiFboWidth=3840,m_guiFboHeight=2160;
 unsigned m_dvPQSubtitleDraws=0;auto GetGUIElementCount=[](){return 3;};
 struct {bool optimizedDV;} preferences{optimized};struct {struct {int mode;} policy;} m_dvSelection{{mode}};
 @@MASTER_CAPTURE@@
 return @@GUI@@;
}
bool direct(int m_effectiveMode,bool m_directUsable) {
 bool m_hdr10=false,allowPacked=true,m_scanout=true;struct {int x,y,width,height;} geometry{0,0,3840,2160};
 @@CONDITION@@ return true;}return false;
}
bool failure(int m_effectiveMode) {
 bool m_directUsable=true,m_asyncEligible=true;
 auto Failure=[](const char*){};void* m_renderer=nullptr;
 auto dvbridge_renderer_reset=[](void*){};
 @@FAILURE@@
 return m_directUsable;
}
int main(){
 assert(gui(5,false) && gui(5,true));assert(!gui(1,false) && gui(1,true));assert(gui(5,false,true));
 assert(!gui(1,true,true));
 assert(direct(5,false) && direct(5,true));assert(!direct(1,false) && direct(1,true));
 assert(failure(5));assert(!failure(1));
}
'''.replace('@@COMPOSE@@',compose).replace('@@GUI@@',gui).replace('@@MASTER_CAPTURE@@',master_capture).replace('@@CONDITION@@',condition).replace('@@FAILURE@@',failure)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],text=True,capture_output=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_real_selection_and_saved_values(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        headers=tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        settings=(headers/'DVOutputSettings.h').read_text()
        settings='\n'.join(line for line in settings.splitlines() if not line.startswith('#include'))
        selection=(headers/'DVOutputSelection.h').read_text().replace('#include "DVOutputSettings.h"','')
        program=r'''
#include <atomic>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <memory>
#include <mutex>
#include <map>
#include <string>
#include <cassert>
#define HAVE_DVBRIDGE
extern "C" {
#include "dvbridge_policy.h"
}
#include "utils/DVBridgePresentation.h"
struct Settings {
 std::map<std::string,int> ints;
 int GetInt(const char* k){return ints[k];} double GetNumber(const char*){return 0;}
 bool GetBool(const char* k){return ints[k];}
};
auto stored=std::make_shared<Settings>();
struct Component{auto GetSettings(){return stored;}} component;
struct CServiceBroker{static auto GetSettingsComponent(){return &component;}};
namespace DVBRIDGE {uint64_t NextRevision(){static uint64_t id=1;return ++id;}}
@@SETTINGS@@
@@SELECTION@@
int main(){
 using namespace DVBRIDGE;
 static_assert(int(OutputMode::Standard)==0 && int(OutputMode::HDR10)==1 &&
  int(OutputMode::Disabled)==2 && int(OutputMode::EnhancedDV)==3 && int(OutputMode::MasterReference)==4);
 stored->ints["dvbridge.outputmode"]=4;stored->ints["dvbridge.fastchroma"]=1;
 stored->ints["dvbridge.felupscaling"]=1;
 auto p=FrameOutputSettings();assert(p.output==OutputMode::MasterReference);
 assert(p.Policy().mode==DVBRIDGE_MODE_MASTER_REFERENCE && p.Policy().tv.peak_nits==0);
 assert(p.felUpscaling==1);
 OutputCapabilities caps{};caps.sourceKnown=caps.isDV=caps.nativeDV=caps.processingKnown=caps.hdr10=true;
 for(auto& mode:caps.processing)mode={true,OutputReason::None};
 auto out=SelectOutput(p,caps);assert(out.route==OutputRoute::NativeDV && out.policy.mode==5);
 const auto revision=p.revision;
 for(int legacy:{0,1,2}){
  stored->ints["dvbridge.fastchroma"]=legacy;p=FrameOutputSettings();
  assert(p.revision==revision && "Unused legacy Fast values must not invalidate a frame transaction");
  assert(SelectOutput(p,caps).policy.mode==5);
 }
 assert(p.output==OutputMode::MasterReference && p.Policy().mode==5);
 assert(!p.masterIPT && !p.allowMasterFallback);
 stored->ints["dvbridge.masteroutput"]=1;p=FrameOutputSettings();
 assert(p.masterIPT && p.Policy().master_ipt && p.revision!=revision);
 const auto iptRevision=p.revision;
 assert(FrameOutputSettings().revision==iptRevision);
 assert(!p.HDR10Policy().master_ipt);
 stored->ints["dvbridge.masteroutput"]=0;p=FrameOutputSettings();
 assert(!p.masterIPT && !p.Policy().master_ipt && p.revision!=iptRevision);
 assert(SelectOutput(p,caps).policy.mode==5);
 caps.processing[5]={false,OutputReason::SourceIneligible};
 p.allowMasterFallback=true;
 out=SelectOutput(p,caps);assert(out.route==OutputRoute::HDR10 && out.policy.mode==2);
 assert(out.reason==OutputReason::SourceIneligible);
 p.allowMasterFallback=false;out=SelectOutput(p,caps);
 assert(out.route==OutputRoute::Vanilla && out.policy.mode==DVBRIDGE_MODE_MASTER_REFERENCE);
 assert(out.reason==OutputReason::SourceIneligible);
 p.allowMasterFallback=true;
 caps.isDV=false;caps.isHDR10=true;
 out=SelectOutput(p,caps);assert(out.route==OutputRoute::Vanilla);
 p.hdr10Source=HDR10SourceMode::ReferenceDV;
 out=SelectOutput(p,caps);assert(out.route==OutputRoute::NativeDV && out.policy.mode==1);
 caps.isHDR10=false;caps.stereoSource=true;
 assert(SelectOutput(p,caps).route==OutputRoute::Vanilla);
}
'''.replace('@@SETTINGS@@',settings).replace('@@SELECTION@@',selection)
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(tree/'xbmc'),'-I'+str(headers),
                '-I'+str(repo/'CB1/src'),str(root/'test.cpp'),'-o',str(root/'test')],text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],text=True,capture_output=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_master_option_and_actual_output_labels(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        settings=ET.parse(tree/'system/settings/settings.xml')
        node=settings.find(".//setting[@id='dvbridge.outputmode']")
        self.assertEqual(node.findtext('default'),'0')
        self.assertIn('4',[o.text for o in node.findall('constraints/options/option')])
        bridge=(tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        self.assertIn('dvbridge_render_master_reference;',bridge)
        self.assertIn('dvbridge_render_master_reference_ipt',bridge)
        self.assertIn('master-reference-unavailable',bridge)
        panel=(tree/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        self.assertIn('Reference GPU',panel)


if __name__=='__main__':unittest.main()
