"""Execute the real SDR GUI owner fast paths, rollback and immutable source preference selection."""
from pathlib import Path
import subprocess,tempfile,unittest
from test_native_video_source import TREE,body
ROOT=Path(__file__).resolve().parents[2]

def compile_run(test,program,cases=('',),flags=()):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);(root/'check.cpp').write_text(program,encoding='utf-8')
        build=subprocess.run(['c++','-std=c++20','-I'+str(ROOT/'CB1/src'),'-I'+str(TREE/'xbmc'),*flags,
            str(root/'check.cpp'),str(ROOT/'CB1/src/dvbridge_policy.c'),'-o',str(root/'check')],capture_output=True,text=True)
        test.assertEqual(build.returncode,0,build.stderr)
        for case in cases:
            with test.subTest(case=case):
                run=subprocess.run([str(root/'check'),*([case] if case else [])],capture_output=True,text=True)
                test.assertEqual(run.returncode,0,run.stderr)

class SDRLiveSettingsTests(unittest.TestCase):
    def test_same_mode_live_pause_failure_and_rollback_use_the_matching_gui_gamma(self):
        source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(encoding='utf-8')
        shader=body((TREE/'xbmc/rendering/gles/GuiCompositeShaderGLES.cpp').read_text(encoding='utf-8'),
                    'bool CGuiCompositeShaderGLES::CreateLUTs(')
        start=source.index('  if (m_dvConfiguredOutput == m_dvSelection.policy.mode && !m_dvOutputRetiring')
        prepare=source[start:source.index('  if (!HasPendingDVOutputSurface() && !SetVideoOutput',start)]
        start=source.index('  if (m_dvBridge && m_dvConfiguredOutput ==')
        begin=source[start:source.index('  if (!CompleteDVBridgePage()',start)]
        start=source.index('      m_dvPriorConfiguredOutput =')
        snapshot=source[start:source.index('      m_dvPendingStream =',start)]
        program=r"""
#include <cassert>
#include <cmath>
#include <string>
#include <memory>
#include <optional>
#include <vector>
#include <limits>
#include "dvbridge_policy.h"
constexpr int AVCOL_TRC_GAMMA22=4,AVCOL_TRC_SMPTE2084=16,AVCOL_TRC_ARIB_STD_B67=18,LOGERROR=1,LOGDEBUG=2,DVBRIDGE_DV_IDLE=0,DVBRIDGE_DV_FAILED=3;
struct CLog{template<class... A>static void Log(A...){}};
bool failLUT=false;unsigned textures=0;
void glDeleteTextures(int,const unsigned*){}
struct CGuiCompositeShaderGLES{
 unsigned m_lutDegammaTexId{},m_lutTFTexId{};float m_ootfGamma{},m_sdrPeak=.0203;static constexpr unsigned LUT_SIZE=256;
 explicit CGuiCompositeShaderGLES(const std::string&){}bool CompileAndLink(){return true;}
 unsigned CreateLUTTexture(const std::vector<float>&){++textures;return failLUT?0:1;}
 std::vector<float>GenerateDegammaLUT(){return {0,1};}std::vector<float>GeneratePQLUT(float){return {0,1};}
 bool CreateLUTs(int colorTransfer,float sdrGamma) SHADER
};
namespace DVBRIDGE {enum class OutputRoute{Vanilla,NativeDV,HDR10,SDR, PlayerLed};}
struct State{bool Captured()const{return false;}};
struct Bridge{bool RebindOutputSurface(bool,bool,unsigned){return true;}bool PlayerLed()const{return false;}};
struct Context{int Poll(){return DVBRIDGE_DV_IDLE;}};
struct FBO{void Cleanup(){}};
struct Picture{};
struct Window{
 struct {DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::SDR;dvbridge_policy policy{};}m_dvSelection;
 State m_dvState;bool m_sdrConversion=true,m_hdrConversion=true,m_dvPriorHDRConversion=true,m_dvPriorSDRConversion=true,m_dvPriorGuiCompositing=true;
 bool m_pascalHDRActive=false,m_priorPascalHDRActive=false;
 unsigned HDR10Framebuffer()const{return 0;}
 bool m_guiCacheValid=false,m_guiCompositing=false,m_compositeShaderLimited=false,m_dvOutputRetiring=false,m_dvRejectedSurface=true,m_dvRollbackFailed=false;
 bool m_dvPQGuiMergeAttempted=false,m_dvPQGuiComposed=false,m_dvPQSubtitleRendering=false,m_dvPQSubtitleCleared=false,m_dvNativeGui=false;
 int m_guiColorTransfer=0,m_dvPQSubtitleWidth=0,m_dvPQSubtitleHeight=0,m_dvPQSubtitleDraws=0,m_guiFboWidth=0,m_guiFboHeight=0;
 float m_guiSDRGamma=2.4f,m_dvPriorGuiSDRGamma=2.4f;FBO m_guiFbo,m_dvPQSubtitleFbo;
 std::optional<int>m_dvConfiguredOutput=DVBRIDGE_MODE_SDR,m_dvPriorConfiguredOutput,m_hdr10Signal;
 std::unique_ptr<CGuiCompositeShaderGLES>m_compositeShader;std::unique_ptr<Bridge>m_dvBridge=std::make_unique<Bridge>();std::unique_ptr<Context>m_dvContext=std::make_unique<Context>();
 bool UseLimitedColor(){return false;}bool CompleteDVOutputSurface(bool){return true;}bool CompleteDVBridgePage(){return true;}
 bool DVBridgeRequested(const Picture*){return true;}bool HasPendingDVOutputSurface(){return false;}
 bool SetGuiCompositing(int colorTransfer) SETGUI
 bool ConfigureGuiCompositing(int colorTransfer,float gamma) CONFIGGUI
 bool Prepare(){Picture picture;PREPARE return false;}
 bool Begin(){[[maybe_unused]] const bool sdr=m_dvSelection.route==DVBRIDGE::OutputRoute::SDR;BEGIN return false;}
 void Snapshot(){SNAPSHOT}
 bool Rollback() ROLLBACK
 Window(){m_dvSelection.policy.mode=DVBRIDGE_MODE_SDR;m_dvSelection.policy.sdr.preset=DVBRIDGE_SDR_REFERENCE;assert(SetGuiCompositing(AVCOL_TRC_GAMMA22));}
};
int main(int argc,char**argv){assert(argc==2);std::string test=argv[1];Window w;const auto initial=textures;w.m_guiCacheValid=true;
 if(test=="live"){w.m_dvSelection.policy.sdr.preset=DVBRIDGE_SDR_BRIGHT;assert(w.Prepare());assert(w.m_compositeShader->m_ootfGamma==-2.2f&&!w.m_guiCacheValid);}
 if(test=="paused"){w.m_dvSelection.policy.sdr={DVBRIDGE_SDR_CUSTOM,120,2.6,.01,DVBRIDGE_GAMUT_UNSET};assert(w.Begin());assert(w.m_compositeShader->m_ootfGamma==-2.6f&&!w.m_guiCacheValid);}
 if(test=="unchanged"){for(unsigned i=0;i<100;++i){assert(w.Prepare()&&w.Begin());}assert(textures==initial&&w.m_guiCacheValid);}
 if(test=="lut-failure"){w.m_dvSelection.policy.sdr.preset=DVBRIDGE_SDR_BRIGHT;failLUT=true;assert(!w.Prepare()&&!w.Begin());failLUT=false;assert(w.Begin());assert(w.m_compositeShader->m_ootfGamma==-2.2f);}
 if(test=="invalid-target"){w.m_dvSelection.policy.sdr={DVBRIDGE_SDR_CUSTOM,120,NAN,.01,DVBRIDGE_GAMUT_UNSET};assert(!w.Prepare()&&!w.Begin());}
 if(test=="rollback"){w.Snapshot();w.m_dvSelection.policy.sdr={DVBRIDGE_SDR_CUSTOM,120,2.6,.01,DVBRIDGE_GAMUT_UNSET};assert(w.SetGuiCompositing(AVCOL_TRC_GAMMA22));assert(w.Rollback());assert(w.m_compositeShader->m_ootfGamma==-2.4f);}
 if(test=="rollback-failure"){w.Snapshot();w.m_dvSelection.policy.sdr={DVBRIDGE_SDR_CUSTOM,120,2.6,.01,DVBRIDGE_GAMUT_UNSET};assert(w.SetGuiCompositing(AVCOL_TRC_GAMMA22));failLUT=true;assert(!w.Rollback()&&w.m_dvRollbackFailed&&w.m_dvRejectedSurface);}
}
"""
        program=program.replace('SHADER',shader).replace('SETGUI',body(source,'bool CWinSystemGbmGLESContext::SetGuiCompositing(')).replace(
            'CONFIGGUI',body(source,'bool CWinSystemGbmGLESContext::ConfigureGuiCompositing(')).replace(
            'PREPARE',prepare).replace('BEGIN',begin).replace('SNAPSHOT',snapshot).replace(
            'ROLLBACK',body(source,'bool CWinSystemGbmGLESContext::PollRejectedDVSurface()'))
        compile_run(self,program,('live','paused','unchanged','lut-failure','invalid-target','rollback','rollback-failure'),
                    ('-DHAVE_DVBRIDGE','-Wall','-Wextra','-Werror'))

    def test_requested_hdr10plus_sdr_policy_comes_from_the_immutable_source(self):
        source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(encoding='utf-8')
        start=source.index('  const auto preferences = DVBRIDGE::FrameOutputSettings(',source.index('bool CWinSystemGbmGLESContext::RenderDVBridge('))
        preferences=source[start:source.index(';',start)+1]
        header=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text(encoding='utf-8')
        header='\n'.join(line for line in header.splitlines() if not line.startswith('#include'))
        selector=body((TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSelection.h').read_text(encoding='utf-8'),'inline OutputSelection SelectOutput(')
        program=r"""
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
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
namespace DVBRIDGE {uint64_t NextRevision(){static uint64_t n=1;return ++n;}}
HEADER
namespace DVBRIDGE {
enum class OutputRoute {Vanilla,NativeDV,HDR10,SDR, PlayerLed};
struct OutputSelection {OutputRoute route{};dvbridge_policy policy{};OutputReason reason{};int lldvFormat{};};
OutputSelection SelectOutput(const OutputPreferences& preferences,const OutputCapabilities& caps) SELECTOR
}

enum class StreamHdrType{HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG,HDR_TYPE_DOLBYVISION};
int main(){using namespace DVBRIDGE;
 struct {StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;}source;
 struct {struct {unsigned profile{};}sourceInfo;bool hdr10PlusSource{},hlg{};}layer;
 struct {void* Data(){return nullptr;}}metadata;
 struct AI{bool HDR10Plus(){return false;}};struct Context{AI value;AI& HDR10AI(){return value;}}context;
 [[maybe_unused]] auto* m_dvContext=&context;
 auto policy=[&]{PREFS return PolicyCode(preferences.HDR10Policy());};
 for(bool plus:{false,true}){
  source.hdrType=plus?StreamHdrType::HDR_TYPE_HDR10PLUS:StreamHdrType::HDR_TYPE_HDR10;
  PRODUCER layer.hlg=false;
  stored->ints["dvbridge.hdr10source"]=0;stored->ints["dvbridge.hdr10plussource"]=4;
  assert(policy()==(plus?8:0));
  stored->ints["dvbridge.hdr10source"]=4;stored->ints["dvbridge.hdr10plussource"]=0;
  assert(policy()==(plus?0:8));
 }
 // Source classification is independent of successful/zero-average/rejected source statistics.
 source.hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;PRODUCER
 stored->ints["dvbridge.hdr10source"]=0;stored->ints["dvbridge.hdr10plussource"]=4;
 assert(policy()==8);
}
"""
        for path in ('LinuxRendererGLES.cpp','HwDecRender/RendererVAAPIGLES.cpp'):
            producer=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers'/path).read_text(encoding='utf-8')
            assignment=next(line for line in producer.splitlines() if 'layer.hdr10PlusSource =' in line)
            with self.subTest(producer=path):
                code=program.replace('HEADER',header).replace('SELECTOR',selector).replace('PREFS',preferences).replace('PRODUCER',assignment)
                compile_run(self,code)
