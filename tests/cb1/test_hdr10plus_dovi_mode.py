"""Run native HDR10+-guided selection and selected-picture metadata ownership."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body

REPO = Path(__file__).resolve().parents[2]


class HDR10PlusDVModeTests(unittest.TestCase):
    def test_primed_guided_picture_reaches_render_with_its_source_preferences(self):
        native = TREE/'xbmc/cores/VideoPlayer/VideoRenderers'
        settings = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        enums = '\n'.join(re.findall(r'enum class (?:OutputMode|HDR10SourceMode)[^;]+;', settings))
        preferences = 'struct OutputPreferences '+body(settings, 'struct OutputPreferences')+';'
        source = (native/'HDR10AISource.cpp').read_text()
        render = body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                      'bool CWinSystemGbmGLESContext::RenderDVBridge(')
        snapshot = re.search(r'  const auto preferences = DVBRIDGE::FrameOutputSettings\([\s\S]*?;', render).group()
        gate = render[render.index('  const bool aiFrame ='):render.index('#endif', render.index('  const bool aiFrame ='))]
        program = r'''
#define HAVE_DVBRIDGE
#include "dvbridge_policy.h"
#include "cb1_hdr10_ai.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
#include "cores/VideoPlayer/DVDCodecs/Video/HDR10AIActivation.h"
#include <algorithm>
#include <bit>
#include <cassert>
#include <chrono>
#include <cmath>
#include <limits>
#include <optional>
namespace DVBRIDGE {
ENUMS
PREFERENCES
OutputPreferences stored;
OutputPreferences FrameOutputSettings(bool plus=false){
 auto p=stored;if(plus)p.hdr10Source=p.hdr10PlusSource;return p;
}
uint64_t DiagnosticNowMs(){return 1;}
}
struct HDR10AISource {
 using Decision=DVBRIDGE::HDR10AIActivation::Decision;
 DVBRIDGE::OutputPreferences m_preferences;
 DVBRIDGE::SourceBinding m_binding{7,1,11},m_preparedBinding{7,1,11};
 uint64_t m_revision=13;bool m_active=true,m_fallback=false;
 cb1_hdr10_ai* m_context=nullptr;
 std::optional<cb1_ai_result> m_prepared,m_committed;
 DVBRIDGE::HDR10AIActivation m_activation;
 bool HDR10Plus()const{return m_preferences.hdr10Source==DVBRIDGE::HDR10SourceMode::HDR10PlusDV;}
 bool Matches(DVBRIDGE::SourceBinding binding)const MATCHES
 cb1_ai_identity Identity(DVBRIDGE::SourceBinding binding)const IDENTITY
 cb1_ai_status Collect(){assert(false);return CB1_AI_INCOMPATIBLE;}
 void RecordStatus(const char*,cb1_ai_status,bool){}
 Decision Prediction(DVBRIDGE::SourceBinding binding,const DVBRIDGE::OutputPreferences& preferences,
     uint64_t now,cb1_ai_result* result,bool required=true) PREDICTION
 void Prime(bool plus){
  m_preferences=DVBRIDGE::FrameOutputSettings(plus);
  m_prepared=cb1_ai_result{};m_prepared->id={7,1,13};
  m_prepared->source_flags=plus?CB1_SOURCE_HDR10PLUS:0;
  m_activation.Begin(7,13,0);
 }
};
extern "C" cb1_ai_status cb1_hdr10_ai_poll(cb1_hdr10_ai*,cb1_ai_identity,cb1_ai_result*){
 assert(false);return CB1_AI_INCOMPATIBLE;
}
struct Context {HDR10AISource source;auto& HDR10AI(){return source;}};
struct Bridge {
 Context* context;
 auto PredictHDR10AI(DVBRIDGE::SourceBinding binding,const DVBRIDGE::OutputPreferences& p,
     uint64_t now,cb1_ai_result* result){return context->source.Prediction(binding,p,now,result);}
};
struct Window {
 Context context;Context* m_dvContext=&context;Bridge bridge{&context};Bridge* m_dvBridge=&bridge;
 bool Render(bool authored=false){
  struct {bool authored;bool Data()const{return authored;}}metadata{authored};
  struct {DVBRIDGE::SourceBinding binding{7,1,11};}layer;
  SNAPSHOT
  GATE
  return true; // The real rendering body can now submit/present the primed image.
 }
};
int main(){
 using namespace DVBRIDGE;
 stored.hdr10PlusSource=HDR10SourceMode::HDR10PlusDV;
 for(auto plain:{HDR10SourceMode::Native,HDR10SourceMode::ReferenceDV,HDR10SourceMode::EnhancedDV}){
  stored.hdr10Source=plain;Window guided;guided.context.source.Prime(true);
  assert(guided.Render()); // A plain-HDR10 preference must never veto selected HDR10+.
 }
 for(auto plain:{HDR10SourceMode::ReferenceDV,HDR10SourceMode::EnhancedDV}){
  stored.hdr10Source=plain;Window ordinary;ordinary.context.source.Prime(false);
  assert(ordinary.Render()); // The sibling HDR10 path keeps its own preference.
 }
 Window authored;authored.context.source.Prime(true);assert(authored.Render(true));
}
'''
        replacements = dict(ENUMS=enums,PREFERENCES=preferences,SNAPSHOT=snapshot,GATE=gate,
            MATCHES=body(source,'bool HDR10AISource::Matches('),
            IDENTITY=body(source,'cb1_ai_identity HDR10AISource::Identity('),
            PREDICTION=body(source,'HDR10AISource::Decision HDR10AISource::Prediction('))
        for name,value in replacements.items():
            program = re.sub(r'\b'+name+r'\b',lambda unused:value,program)
        self.compile_run(program)

    def test_missing_snapshot_keeps_the_existing_activation_fallback(self):
        headers=TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        settings=(headers/'DVOutputSettings.h').read_text()
        enums='\n'.join(re.findall(r'enum class (?:OutputMode|HDR10SourceMode)[^;]+;',settings))
        preferences='struct OutputPreferences '+body(settings,'struct OutputPreferences')+';'
        selector=body((headers/'DVOutputSelection.h').read_text(),'inline OutputSelection SelectOutput(')
        preparation=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
            'bool CWinSystemGbmGLESContext::PrepareHDR10AIQueue(')
        ingress=preparation[:preparation.index('  // The ordinary commit')]+ 'return false;\n}'
        self.compile_run(r'''
#define HAVE_DVBRIDGE
#include "dvbridge_policy.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
#include <bit>
#include <cassert>
#include <cmath>
#include <memory>
#include <mutex>
namespace DVBRIDGE { ENUMS
PREFERENCES
enum class OutputRoute {Vanilla,NativeDV,HDR10};
struct OutputSelection {OutputRoute route{};dvbridge_policy policy{};OutputReason reason{};};
OutputSelection SelectOutput(const OutputPreferences& preferences,const OutputCapabilities& caps) SELECTOR
OutputPreferences prefs;
OutputPreferences FrameOutputSettings(bool plus=false){auto value=prefs;if(plus)value.hdr10Source=value.hdr10PlusSource;return value;}
}
enum class StreamHdrType {HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS};
struct Picture {DVBRIDGE::SourceBinding doviSourceBinding;StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;};
struct Context {unsigned stops{};bool StopHDR10AI(){++stops;return true;}};
struct Window {
 DVBRIDGE::OutputCapabilities caps;
 DVBRIDGE::SourceBinding m_aiActivation;
 uint64_t m_aiPolicy{},m_aiSelectionPolicy{};
 bool m_aiActive{},m_aiReady{},m_aiFallback{};
 std::mutex m_dvCapabilityMutex;std::shared_ptr<Context> m_dvContext=std::make_shared<Context>();
 auto GetDVOutputCapabilities(const Picture*,const DVBRIDGE::OutputPreferences&){return caps;}
 bool prepare(const Picture& picture) INGRESS
};
int main(){
 using namespace DVBRIDGE;Window w;Picture p{{7,14,11}};
 prefs.hdr10PlusSource=HDR10SourceMode::HDR10PlusDV;prefs.revision=9;
 w.caps.sourceKnown=w.caps.isHDR10=w.caps.hdr10PlusSource=w.caps.nativeDV=true;
 w.m_aiActivation=p.doviSourceBinding;w.m_aiPolicy=prefs.revision;
 w.m_aiActive=w.m_aiReady=true;
 assert(w.prepare(p) && w.m_aiFallback && !w.m_aiReady && !w.m_aiActive);
 assert(w.m_aiSelectionPolicy==prefs.revision && w.m_aiActivation==p.doviSourceBinding);
 assert(w.prepare(p) && w.m_aiFallback); // repeated rejection cannot clear it
 w.caps.isHDR10Plus=w.caps.processingKnown=true;for(auto& v:w.caps.processing)v={true,OutputReason::None};
 assert(!w.prepare(p) && w.m_aiFallback); // valid snapshot does not reset activation
 w.caps.isHDR10Plus=false;++p.doviSourceBinding.stream;
 assert(w.prepare(p) && !w.m_aiFallback && !w.m_aiActivation.Valid());
 assert(w.m_aiSelectionPolicy==0); // a genuine new source may retry
}
'''.replace('ENUMS',enums).replace('PREFERENCES',preferences).replace('SELECTOR',selector).replace('INGRESS',ingress))

    def test_direct_metadata_uses_accepted_scene_without_ai_or_stale_reuse(self):
        renderer=TREE/'xbmc/cores/VideoPlayer/VideoRenderers'
        settings=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        enums='\n'.join(re.findall(r'enum class (?:OutputMode|HDR10SourceMode)[^;]+;',settings))
        preferences='struct OutputPreferences '+body(settings,'struct OutputPreferences')+';'
        declaration='class HDR10AISource '+body((renderer/'HDR10AISource.h').read_text(),'class HDR10AISource')+';'
        source=(renderer/'HDR10AISource.cpp').read_text()
        methods=source[source.index('HDR10AISource::~HDR10AISource()'):]
        self.compile_run(r'''
#define HAVE_DVBRIDGE
#include "dvbridge_policy.h"
#include "cb1_hdr10_ai.h"
#include "cb1_hdr10plus_dovi.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
#include "cores/VideoPlayer/DVDCodecs/Video/HDR10AIActivation.h"
#include <algorithm>
#include <bit>
#include <cassert>
#include <chrono>
#include <cmath>
#include <limits>
#include <memory>
#include <optional>
namespace DVBRIDGE { ENUMS
PREFERENCES
}
CLASS
static unsigned creates{};
static bool allowCreate{};
static uint16_t predictedAverage=1000;
extern "C" {
cb1_ai_status cb1_hdr10_ai_create(pl_gpu,const char*,cb1_hdr10_ai** p){++creates;if(!allowCreate)return CB1_AI_INCOMPATIBLE;*p=reinterpret_cast<cb1_hdr10_ai*>(1);return CB1_AI_READY;}
void cb1_hdr10_ai_destroy(cb1_hdr10_ai** p){*p=nullptr;}
void cb1_hdr10_ai_reset(cb1_hdr10_ai*,uint64_t,uint64_t){}
bool cb1_hdr10_ai_set_coalesced_bounds(cb1_hdr10_ai*,bool){return true;}
cb1_ai_status cb1_hdr10_ai_submit(cb1_hdr10_ai*,const pl_frame*,cb1_ai_identity,double){assert(false);return CB1_AI_INVALID;}
cb1_ai_status cb1_hdr10_ai_advance(cb1_hdr10_ai*,double){assert(false);return CB1_AI_INVALID;}
void cb1_hdr10_ai_end(cb1_hdr10_ai*){assert(false);}
cb1_ai_status cb1_hdr10_ai_poll(cb1_hdr10_ai*,cb1_ai_identity id,cb1_ai_result* p){*p={};p->id=id;p->raw={0,3000,predictedAverage,2048,2048,2048};return CB1_AI_READY;}
void cb1_hdr10_ai_metrics(const cb1_hdr10_ai*,struct cb1_hdr10_ai_metrics*){assert(false);}
}
METHODS
int main(){
 HDR10AISource s;using D=HDR10AISource::Decision;
 DVBRIDGE::OutputPreferences p;p.hdr10Source=DVBRIDGE::HDR10SourceMode::HDR10PlusDV;
 DVBRIDGE::SourceBinding b{7,1,11};cb1_ai_result result{};
 auto hdr=std::make_shared<AVDynamicHDRPlus>();hdr->itu_t_t35_country_code=0xb5;
 hdr->application_version=1;hdr->num_windows=1;hdr->targeted_system_display_maximum_luminance={4000,1};auto& w=hdr->params[0];
 w.num_distribution_maxrgb_percentiles=3;
 const unsigned points[]={1,50,99};
 for(unsigned i=0;i<3;i++){w.maxscl[i]={1,100};w.distribution_maxrgb[i].percentage=points[i];w.distribution_maxrgb[i].percentile={1,100};}
 w.average_maxrgb={1,100};
 assert(s.Begin(reinterpret_cast<pl_gpu>(1),"unused",p,b,0,0,true,true)==CB1_AI_READY);
 assert(s.MetadataOnly() && s.Active() && !creates);
 assert(s.DescribeHDR10Plus(b,hdr,0,0,&result)==D::Prepare);
 assert(result.source_flags==7 && result.raw.l1_min==0 && result.raw.l1_avg==2081);
 assert(s.Describes(b,result) && result.id.revision!=b.revision);
 assert(s.Presented(b,true));
 ++b.picture;
 assert(s.DescribeHDR10Plus(b,hdr,1./60,10,&result)==D::Prepare);
 assert(result.source_flags==5 && s.Presented(b,true));
 auto next=std::make_shared<AVDynamicHDRPlus>(*hdr);
 for(unsigned i=0;i<3;i++){next->params[0].maxscl[i]={1,50};next->params[0].distribution_maxrgb[i].percentile={1,50};}
 next->params[0].average_maxrgb={1,50};++b.picture;
 assert(s.DescribeHDR10Plus(b,next,2./60,20,&result)==D::Prepare);
 assert(result.source_flags==7 && result.raw.l1_avg>2081);
 ++b.picture;s.DiscardBefore(b,25);
 assert(s.DescribeHDR10Plus(b,next,3./60,30,&result)==D::Prepare);
 assert(result.source_flags==7 && s.Presented(b,true));
 ++b.picture;assert(s.DescribeHDR10Plus(b,next,4./60,40,&result)==D::Prepare);
 assert(result.source_flags==5 && s.Presented(b,true));
 // A contradictory distribution must not latch native output when peak/mean
 // still permit a metadata-only estimate; subsequent valid statistics recover.
 auto contradictory=std::make_shared<AVDynamicHDRPlus>(*next);
 contradictory->params[0].average_maxrgb={1,10000};
 ++b.picture;
 assert(s.DescribeHDR10Plus(b,contradictory,5./60,45,&result)==D::Prepare);
 assert(result.raw.l1_avg==614 && result.raw.l1_min==0 && result.source_flags==3);
 assert(s.Presented(b,true) && !creates && !s.Metrics().gpu_submissions);
 ++b.picture;
 assert(s.DescribeHDR10Plus(b,next,6./60,48,&result)==D::Prepare);
 assert(result.raw.l1_avg>2081 && result.source_flags==7 && s.Presented(b,true));
 auto bad=std::make_shared<AVDynamicHDRPlus>(*next);bad->params[0].maxscl[0].den=0;
 ++b.picture;assert(s.DescribeHDR10Plus(b,bad,7./60,50,&result)==D::Native);
 assert(s.Committed()->id.picture==7);
 assert(s.DescribeHDR10Plus(b,next,7./60,60,&result)==D::Native);
 assert(!creates && !s.Metrics().gpu_submissions);
 s.ReleaseRetired();assert(!s.Active());
 ++b.stream;assert(s.Begin(reinterpret_cast<pl_gpu>(1),"unused",p,b,0,70,true,true)==CB1_AI_READY);
 assert(s.DescribeHDR10Plus(b,next,0,70,&result)==D::Prepare && result.source_flags==7);
 s.ReleaseRetired();p.hdr10Source=DVBRIDGE::HDR10SourceMode::ReferenceDV;
 assert(s.Begin(reinterpret_cast<pl_gpu>(1),"unused",p,b,0,80)==CB1_AI_INCOMPATIBLE);
 assert(creates==1);
 // Sparse HDR10+ retains each picture's AI mean even when authored metadata is static.
 s.ReleaseRetired();allowCreate=true;++b.stream;
 p.hdr10Source=DVBRIDGE::HDR10SourceMode::HDR10PlusDV;
 auto sparse=std::make_shared<AVDynamicHDRPlus>(*hdr);
 sparse->params[0].num_distribution_maxrgb_percentiles=0;
 assert(s.Begin(reinterpret_cast<pl_gpu>(1),"unused",p,b,0,90)==CB1_AI_READY);
 assert(s.Prediction(b,p,90,&result)==D::Prepare);
 assert(s.DescribeHDR10Plus(b,sparse,0,90,&result)==D::Prepare);
 assert(result.raw.l1_avg==1000 && s.Presented(b,true));
 ++b.picture;predictedAverage=1500;
 assert(s.Prediction(b,p,100,&result)==D::Prepare);
 assert(s.DescribeHDR10Plus(b,sparse,1./60,100,&result)==D::Prepare);
 assert(result.raw.l1_avg==1500 && result.source_flags==1 && s.Presented(b,true));
}
'''.replace('ENUMS',enums).replace('PREFERENCES',preferences).replace('CLASS',declaration).replace('METHODS',methods),
            sources=(REPO/'CB1/src/cb1_hdr10plus_dovi.c',))

    def snapshot_sources(self):
        native = Path(os.environ.get('KODI_TEST_SUPPORT_TREE', str(TREE)))
        return (REPO/'CB1/src/cb1_hdr10plus_dovi.c', TREE/'xbmc/cores/VideoSourceSideData.cpp',
                native/'xbmc/utils/Base64.cpp', native/'xbmc/utils/Variant.cpp',
                native/'xbmc/utils/JSONVariantWriter.cpp')

    def compile_run(self, program, sources=(), includes=(), libraries=()):
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, binary = root/'check.cpp', root/'check'
            code.write_text('#include "cb1_cmv40.h"\n'+program)
            objects = []
            for index, source in enumerate(sources):
                if source.suffix != '.c':
                    objects.append(source)
                    continue
                obj = root/f'unit{index}.o'
                compiled = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-sign-compare',
                    '-fsanitize=address,undefined', '-I'+str(REPO/'CB1/src'),
                    '-I'+str(prefix/'include'), '-c', str(source), '-o', str(obj)],
                    capture_output=True, text=True)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                objects.append(obj)
            built = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra',
                '-Werror', '-Wno-unused-parameter', '-fsanitize=address,undefined', '-I'+str(TREE/'xbmc'),
                '-I'+str(REPO/'CB1/src'), '-I'+str(prefix/'include'),
                *('-I'+str(path) for path in includes), str(code), *map(str, objects),
                '-L'+str(prefix/'lib'), '-lavutil', '-lm', *libraries, '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr[-8000:])
            env = dict(os.environ, LD_LIBRARY_PATH=str(prefix/'lib')+':'+os.environ.get('LD_LIBRARY_PATH', ''))
            ran = subprocess.run([str(binary)], capture_output=True, text=True, env=env)
            self.assertEqual(ran.returncode, 0, ran.stderr[-8000:])

    def test_selected_hdr10plus_reuses_reference_without_touching_other_modes(self):
        headers = TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        settings = (headers/'DVOutputSettings.h').read_text()
        enums = '\n'.join(re.findall(r'enum class (?:OutputMode|HDR10SourceMode)[^;]+;', settings))
        preferences = 'struct OutputPreferences '+body(settings, 'struct OutputPreferences')+';'
        selector = body((headers/'DVOutputSelection.h').read_text(), 'inline OutputSelection SelectOutput(')
        budget = 'struct HDR10AIBuffers '+body((headers/'HDR10AIBuffers.h').read_text(), 'struct HDR10AIBuffers')+';'
        program = r'''
#define HAVE_DVBRIDGE
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include "cores/VideoPlayer/DVDCodecs/Video/HDR10AIActivation.h"
#include <cassert>
#include <cmath>
#include <bit>
#include <algorithm>
namespace DVBRIDGE {
ENUMS
PREFERENCES
BUDGET
enum class OutputRoute { Vanilla, NativeDV, HDR10 };
struct OutputSelection { OutputRoute route{};dvbridge_policy policy{};OutputReason reason{}; };
OutputSelection select(const OutputPreferences& preferences,const OutputCapabilities& caps) SELECTOR
}
template<class T> void source_plus(T& caps,bool value) {
 if constexpr(requires { caps.isHDR10Plus; }) caps.isHDR10Plus=value;
 if constexpr(requires { caps.hdr10PlusSource; }) caps.hdr10PlusSource=value;
}
int main(){
 using namespace DVBRIDGE;
 OutputPreferences p;OutputCapabilities c;
 c.sourceKnown=c.isHDR10=c.processingKnown=c.nativeDV=c.hdr10=true;
 for(auto& v:c.processing)v={true,OutputReason::None};
 p.hdr10PlusSource=HDR10SourceMode::HDR10PlusDV;source_plus(c,true);
 auto selected=select(p,c);
 assert(selected.route==OutputRoute::NativeDV && selected.policy.mode==DVBRIDGE_MODE_STANDARD);
 assert(!selected.policy.master_ipt && selected.policy.adaptive==DVBRIDGE_ADAPTIVE_A);
 p.hdr10PlusSource=HDR10SourceMode::Native;
 assert(select(p,c).route==OutputRoute::Vanilla);
 p.hdr10PlusSource=HDR10SourceMode::HDR10PlusDV;
 p.hdr10Source=static_cast<HDR10SourceMode>(3);
 assert(HDR10AIBuffers::Count(true,p.hdr10Source,24,false)>HDR10AIBuffers::Native);
 assert(HDR10AIBuffers::Count(true,p.hdr10Source,24,true)==HDR10AIBuffers::Native);
 source_plus(c,false);selected=select(p,c);
 assert(selected.route==OutputRoute::Vanilla && selected.reason==OutputReason::SourceIneligible);
 p.hdr10Source=HDR10SourceMode::ReferenceDV;
 assert(select(p,c).route==OutputRoute::NativeDV);
 p.hdr10Source=HDR10SourceMode::Native;
 assert(select(p,c).route==OutputRoute::Vanilla);
 p.hdr10Source=static_cast<HDR10SourceMode>(3);source_plus(c,true);c.nativeDV=false;
 assert(select(p,c).reason==OutputReason::NoDVTransport);
 c.nativeDV=true;c.stereoSource=true;
 assert(select(p,c).route==OutputRoute::Vanilla);
}
'''.replace('ENUMS',enums).replace('PREFERENCES',preferences).replace('BUDGET',budget).replace('SELECTOR',selector)
        self.compile_run(program)

    def test_circuit_append_does_not_change_existing_ids_or_engine(self):
        self.compile_run(r'''
#include "cb1_circuit.h"
#include <cassert>
#include <cstring>
int main(){
 assert(!std::strcmp(cb1_engine_version(),"CB1 0.5"));
 assert(CB1_DV_HDR10PLUS==12 && CB1_HDR10_DV_REFERENCE==7 && CB1_HDR10_DV_ADAPTIVE==8);
 const char* guided=cb1_circuit_version(static_cast<cb1_circuit>(13));
 assert(guided && !std::strcmp(guided,"CB1-HDR10PDVR.0.2"));
}
''', sources=(REPO/'CB1/src/cb1_circuit.c',))

    def test_prediction_epoch_is_not_confused_with_source_binding_revision(self):
        headers = TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        settings = (headers/'DVOutputSettings.h').read_text()
        enums = '\n'.join(re.findall(r'enum class (?:OutputMode|HDR10SourceMode)[^;]+;', settings))
        preferences = 'struct OutputPreferences '+body(settings, 'struct OutputPreferences')+';'
        renderer = TREE/'xbmc/cores/VideoPlayer/VideoRenderers'
        source = (renderer/'HDR10AISource.cpp').read_text()
        header = (renderer/'HDR10AISource.h').read_text()
        matches = body(source, 'bool HDR10AISource::Matches(')
        identity = body(source, 'cb1_ai_identity HDR10AISource::Identity(')
        current = body(header, 'bool Current(')
        describes = body(header, 'bool Describes(')
        result_type = re.search(r'struct cb1_ai_result\s*\{[^}]+};',
            (REPO/'CB1/src/cb1_hdr10_ai.h').read_text()).group()
        self.compile_run(r'''
#define HAVE_DVBRIDGE
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cb1_l1l3_model.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
#include <cassert>
#include <bit>
#include <cmath>
RESULT_TYPE
namespace DVBRIDGE { ENUMS
PREFERENCES
}
struct Source {
 bool m_active=true;DVBRIDGE::SourceBinding m_binding{7,14,11};
 uint64_t m_revision=31;DVBRIDGE::OutputPreferences m_preferences;
 bool Matches(DVBRIDGE::SourceBinding binding)const MATCHES
 cb1_ai_identity Identity(DVBRIDGE::SourceBinding binding)const IDENTITY
 bool Current(DVBRIDGE::SourceBinding binding,const DVBRIDGE::OutputPreferences& preferences)const CURRENT
 bool Describes(DVBRIDGE::SourceBinding binding,const cb1_ai_result& prediction)const DESCRIBES
};
int main(){
 Source s;DVBRIDGE::SourceBinding b{7,14,11};cb1_ai_result p{};p.id={7,14,31};
 assert(s.Current(b,s.m_preferences) && s.Describes(b,p));
 p.id.revision=11;assert(!s.Describes(b,p));
 p.id.revision=31;b.revision=12;assert(!s.Describes(b,p));
 b.revision=11;p.id.picture=15;assert(!s.Describes(b,p));
 p.id.picture=14;p.id.stream=8;assert(!s.Describes(b,p));
 p.id.stream=7;s.m_active=false;assert(!s.Describes(b,p));
}
'''.replace('RESULT_TYPE',result_type).replace('ENUMS',enums).replace('PREFERENCES',preferences)
            .replace('MATCHES',matches).replace('IDENTITY',identity).replace('CURRENT',current)
            .replace('DESCRIBES',describes))

    def test_guided_rejection_reason_survives_the_native_activation_gate(self):
        headers = TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        settings = (headers/'DVOutputSettings.h').read_text()
        enums = '\n'.join(re.findall(r'enum class (?:OutputMode|HDR10SourceMode)[^;]+;', settings))
        preferences = 'struct OutputPreferences '+body(settings, 'struct OutputPreferences')+';'
        selector = body((headers/'DVOutputSelection.h').read_text(), 'inline OutputSelection SelectOutput(')
        window = (TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        selection = body(window,'DVBRIDGE::OutputSelection CWinSystemGbmGLESContext::SelectedDVOutput(const VideoPicture* picture,')
        begin = selection.index('  if (caps.isHDR10)')
        gate = selection[begin:selection.index('#endif', begin)]
        self.compile_run(r'''
#define HAVE_DVBRIDGE
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
#include <cassert>
#include <cmath>
#include <bit>
#include <mutex>
namespace DVBRIDGE {
ENUMS
PREFERENCES
enum class OutputRoute {Vanilla,NativeDV,HDR10};
struct OutputSelection {OutputRoute route{};dvbridge_policy policy{};OutputReason reason{};};
OutputSelection select(const OutputPreferences& preferences,const OutputCapabilities& caps) SELECTOR
OutputSelection gated(const OutputPreferences& preferences,OutputCapabilities caps,bool m_aiReady){
 auto result=select(preferences,caps);
 SourceBinding binding{7,14,11},m_aiActivation=binding;
 uint64_t m_aiPolicy=preferences.revision;bool m_aiFallback=false;std::mutex m_dvCapabilityMutex;
 GATE
 return result;
}
}
int main(){
 using namespace DVBRIDGE;OutputPreferences p;OutputCapabilities c;
 c.sourceKnown=c.isHDR10=c.processingKnown=c.nativeDV=c.hdr10=true;
 for(auto& v:c.processing)v={true,OutputReason::None};
 p.hdr10PlusSource=HDR10SourceMode::HDR10PlusDV;c.hdr10PlusSource=true;
 assert(gated(p,c,false).reason==OutputReason::SourceIneligible);
 c.isHDR10Plus=true;c.nativeDV=false;
 assert(gated(p,c,false).reason==OutputReason::NoDVTransport);
 c.nativeDV=true;assert(gated(p,c,true).route==OutputRoute::NativeDV);
 c.hdr10PlusSource=false;p.hdr10Source=HDR10SourceMode::ReferenceDV;
 assert(gated(p,c,false).route==OutputRoute::Vanilla && gated(p,c,false).reason==OutputReason::None);
}
'''.replace('ENUMS',enums).replace('PREFERENCES',preferences).replace('SELECTOR',selector).replace('GATE',gate))

    def test_quick_menu_refuses_guided_for_plain_hdr10(self):
        settings = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        enums = '\n'.join(re.findall(r'enum class (?:OutputMode|HDR10SourceMode)[^;]+;', settings))
        preferences = 'struct OutputPreferences '+body(settings, 'struct OutputPreferences')+';'
        options = body((TREE/'xbmc/settings/SettingConditions.cpp').read_text(),
                       'void CSettingConditions::DVOutputOptions(')
        # External service lookups precede this native per-option admission loop.
        context = options[options.index('  const bool menu='):options.index('  const auto preferences=')]
        admission = context + options[options.index('  const bool method='):options.rindex('}')]
        admission = admission.replace('!data.transaction.identity.Valid()', 'pending')
        self.compile_run(r'''
#define HAVE_DVBRIDGE
#define CB1_HAS_HDR10_AI
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include <cassert>
#include <cmath>
#include <bit>
#include <memory>
#include <vector>
namespace DVBRIDGE { ENUMS
PREFERENCES
}
enum class StreamHdrType {HDR_TYPE_NONE,HDR_TYPE_HDR10PLUS};
struct CDVPlaybackModes {static StreamHdrType SourceType(){return StreamHdrType::HDR_TYPE_NONE;}};
struct Setting {std::string id;const std::string& GetId()const{return id;}};
struct Option {explicit Option(int n):value(n){} int value;std::string label,label2;
 std::vector<std::pair<std::string,bool>> properties;};
struct Localizer {std::string Get(int id)const{return std::to_string(id);}};
void admit(const std::shared_ptr<const Setting>& setting,std::vector<Option>& list,
 const DVBRIDGE::OutputCapabilities& caps){
 const DVBRIDGE::OutputPreferences preferences;const Localizer localizer;
 constexpr bool pending=false;
 ADMISSION
}
int main(){
 DVBRIDGE::OutputCapabilities caps;
 caps.sourceKnown=caps.isHDR10=caps.processingKnown=caps.nativeDV=caps.hdr10=true;
 for(auto& p:caps.processing)p={true,DVBRIDGE::OutputReason::None};
 for(auto& p:caps.hdr10Processing)p={true,DVBRIDGE::OutputReason::None};
 {
  for(bool plus:{false,true}){
   auto setting=std::make_shared<Setting>(plus ? "dvbridge.hdr10plusplaybackchoice" : "dvbridge.hdr10playbackchoice");
   caps.isHDR10Plus=plus;caps.hdr10PlusSource=plus;
   std::vector<Option> list;for(int i=0;i<(plus?2:3);++i)list.emplace_back(i);
   admit(setting,list,caps);
   const int native=plus?1:2;
   assert(!list[native].properties.back().second);
   if(plus){
    const int reference=0;
    assert(!list[reference].properties.back().second);
   }
   if(plus)assert(list[0].label2=="40971");
  }
 }
}
'''.replace('ENUMS',enums).replace('PREFERENCES',preferences).replace('ADMISSION',admission))

    def test_only_captured_selected_metadata_can_guide_a_full_source_picture(self):
        helper = TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HDR10PlusDVSource.h'
        self.assertTrue(helper.exists(), 'selected-picture HDR10+ owner is not implemented')
        native = Path(os.environ.get('KODI_TEST_SUPPORT_TREE', str(TREE)))
        self.compile_run(r'''
#include "cores/VideoPlayer/VideoRenderers/HDR10PlusDVSource.h"
#include <cassert>
#include <cstring>
int main(){
 AVFrame* frame=av_frame_alloc();assert(frame);
 auto* hdr=av_dynamic_hdr_plus_create_side_data(frame);assert(hdr);
 hdr->itu_t_t35_country_code=0xb5;hdr->application_version=1;hdr->num_windows=1;
 hdr->targeted_system_display_maximum_luminance={4000,1};
 auto& p=hdr->params[0];for(auto& v:p.maxscl)v={1,10};
 p.average_maxrgb={1,100};p.fraction_bright_pixels={0,1};
 p.tone_mapping_flag=1;p.knee_point_x=p.knee_point_y={2048,4095};
 p.num_bezier_curve_anchors=1;p.bezier_curve_anchors[0]={512,1023};
 p.color_saturation_mapping_flag=1;p.color_saturation_weight={1,1};
 const DVBRIDGE::SourceBinding binding{7,14,11};
 const cb1_l1l3 estimate{12,3200,1200,2048,2048,2048};
 auto source=VideoSourceSideData::Capture(9,91,AV_CODEC_ID_HEVC,frame,nullptr);
 assert(source && source->HDR10Plus());
 cb1_hdr10plus_dovi_result result{};
 float crop[4]{};
 assert(DVBRIDGE::HDR10PlusDVWholeSource(crop,3840,2160));
 assert(DVBRIDGE::DescribeHDR10PlusDV(result,estimate,source,binding,binding,9,91,true));
 assert(result.metadata.l1_max==3079 && result.metadata.l1_avg==1200);
 assert(result.source_fields==2 && result.estimated_fields==5);
 assert(result.untranslated_curve && result.untranslated_saturation);
 // Serial 91 and binding.picture 14 are deliberately different domains.
 const auto saved=result;const auto original=*source->HDR10Plus();
 for(int failure=0;failure<5;++failure){
  auto selected=binding;uint64_t generation=9,serial=91;bool whole=true;
  if(failure==0)++selected.picture;
  if(failure==1)++selected.revision;
  if(failure==2)++generation;
  if(failure==3)++serial;
  if(failure==4)whole=false;
  assert(!DVBRIDGE::DescribeHDR10PlusDV(result,estimate,source,selected,binding,generation,serial,whole));
  assert(!std::memcmp(&saved,&result,sizeof(result)));
 }
 // Destination zoom is not an input: only source crop changes admission.
 crop[2]=3840;crop[3]=2160;assert(DVBRIDGE::HDR10PlusDVWholeSource(crop,3840,2160));
 crop[0]=1;assert(!DVBRIDGE::HDR10PlusDVWholeSource(crop,3840,2160));
 for(int malformed=0;malformed<3;++malformed){
  *hdr=original;
  if(malformed==0)hdr->params[0].tone_mapping_flag=2;
  if(malformed==1)hdr->params[0].knee_point_x={0,0};
  if(malformed==2)hdr->mastering_display_actual_peak_luminance_flag=2;
  auto invalid=VideoSourceSideData::Capture(9,92,AV_CODEC_ID_HEVC,frame,nullptr);
  assert(invalid && !invalid->HDR10Plus() && invalid->RejectedSections());
  assert(!DVBRIDGE::DescribeHDR10PlusDV(result,estimate,invalid,binding,binding,9,92,true));
  assert(!std::memcmp(&saved,&result,sizeof(result)));
 }
 // Mutation of the AVFrame cannot change the immutable captured owner.
 assert(!std::memcmp(&original,source->HDR10Plus(),sizeof(original)));
 *hdr=original;for(auto& v:hdr->params[0].maxscl)v={0,1};
 auto missing=VideoSourceSideData::Capture(9,93,AV_CODEC_ID_HEVC,frame,nullptr);
 assert(DVBRIDGE::DescribeHDR10PlusDV(result,estimate,missing,binding,binding,9,93,true));
 assert(result.source_fields==0 && result.estimated_fields==7 && result.metadata.l1_max==3200);
 av_frame_free(&frame);
}
''', sources=self.snapshot_sources(), includes=(native/'xbmc',))

    def test_real_decoder_implicit_full_frame_window_preserves_pixels(self):
        from test_hdr10plus_decoded_source import access_unit, hdr_sei
        arrays = '\n'.join('const uint8_t v'+str(version)+'[]={'+','.join(map(str,
            access_unit(hdr_sei(version))))+'};' for version in (0,1))
        native = Path(os.environ.get('KODI_TEST_SUPPORT_TREE', str(TREE)))
        decoder = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        begin = decoder.index('  if (pVideoPicture->hdrType == StreamHdrType::HDR_TYPE_HDR10 ||')
        classification = decoder[begin:decoder.index('\n#ifdef CB1_HAS_HDR10_AI',begin)]
        binding = body(decoder, 'void CDVDVideoCodecFFmpeg::BindHDR10AISource(')
        source_type = TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/HDR10SourceType.h'
        type_contract = '#include "cores/VideoPlayer/DVDCodecs/Video/HDR10SourceType.h"' if source_type.exists() else re.search(
            r'enum class StreamHdrType\s*\{[^}]+};',
            (TREE/'xbmc/cores/VideoPlayer/Interface/StreamInfo.h').read_text()).group()
        program = r'''
#include "cores/VideoPlayer/VideoRenderers/HDR10PlusDVSource.h"
#include <cassert>
#include <cstring>
#include <vector>
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/imgutils.h>
}
TYPE_CONTRACT
struct Picture {
 StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10,hdrTypeAlt=StreamHdrType::HDR_TYPE_NONE;
 DVBRIDGE::SourceInfo doviSourceInfo{};
 DVBRIDGE::SourceBinding doviSourceBinding{};
 int64_t doviSourcePts=AV_NOPTS_VALUE;
};
struct DecoderFlow {
 AVFrame* m_pFrame;DVBRIDGE::SourceOwner m_dvSourceOwner;
 struct {StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;}m_hints;
 explicit DecoderFlow(AVFrame* frame):m_pFrame(frame){m_dvSourceOwner.BeginStream();}
 void BindHDR10AISource(Picture& picture) BINDING
 void Classify(Picture* pVideoPicture){
  const AVFrameSideData* sd=nullptr;
  CLASSIFICATION
  BindHDR10AISource(*pVideoPicture);
 }
};
ARRAYS
int main(){
 for(auto fixture:{std::pair{v0,sizeof(v0)},std::pair{v1,sizeof(v1)}}){
  auto* decoder=avcodec_find_decoder(AV_CODEC_ID_HEVC);assert(decoder);
  auto* context=avcodec_alloc_context3(decoder);assert(context);
  context->thread_count=1;context->thread_type=0;assert(avcodec_open2(context,decoder,nullptr)==0);
  AVPacket* packet=av_packet_alloc();assert(av_new_packet(packet,fixture.second)==0);
  packet->pts=packet->dts=1000;
  std::memcpy(packet->data,fixture.first,fixture.second);assert(avcodec_send_packet(context,packet)==0);
  AVFrame* frame=av_frame_alloc();int status=avcodec_receive_frame(context,frame);
  if(status==AVERROR(EAGAIN)){assert(avcodec_send_packet(context,nullptr)==0);status=avcodec_receive_frame(context,frame);}
  assert(status==0);
  Picture picture;picture.doviSourcePts=frame->best_effort_timestamp;
  DecoderFlow flow(frame);flow.Classify(&picture);
  assert(picture.hdrType==StreamHdrType::HDR_TYPE_HDR10PLUS);
  assert(flow.m_hints.hdrType==StreamHdrType::HDR_TYPE_HDR10PLUS);
  assert(picture.doviSourceBinding.Valid());
  auto format=static_cast<AVPixelFormat>(frame->format);
  std::vector<uint8_t> before(av_image_get_buffer_size(format,16,16,1)),after(before.size());
  assert(av_image_copy_to_buffer(before.data(),before.size(),frame->data,frame->linesize,format,16,16,1)>0);
  auto source=VideoSourceSideData::Capture(13,103,AV_CODEC_ID_HEVC,frame,nullptr);
  assert(source && source->HDR10Plus());
  const auto& window=source->HDR10Plus()->params[0];
  assert(window.window_lower_right_corner_x.den==0); // Native implicit window, not 1/1.
  cb1_hdr10plus_dovi_result result{};cb1_l1l3 estimate{0,3200,1200,2048,2048,2048};
  const auto selected=picture.doviSourceBinding;
  assert(DVBRIDGE::DescribeHDR10PlusDV(result,estimate,source,selected,selected,13,103,true));
  assert(result.metadata.l1_max==3079 && result.source_fields==2 && result.estimated_fields==5);
  assert(av_image_copy_to_buffer(after.data(),after.size(),frame->data,frame->linesize,format,16,16,1)>0);
  assert(before==after);
  av_frame_free(&frame);av_packet_free(&packet);avcodec_free_context(&context);
 }
}
'''.replace('ARRAYS',arrays).replace('TYPE_CONTRACT',type_contract).replace('BINDING',binding).replace('CLASSIFICATION',classification)
        self.compile_run(program, sources=self.snapshot_sources(), includes=(native/'xbmc',),
                         libraries=('-lavcodec',))

    def test_native_hdr10plus_import_bootstraps_guided_and_pool_reopen(self):
        native = Path(os.environ.get('KODI_TEST_SUPPORT_TREE', str(TREE)))
        headers = TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        settings = (headers/'DVOutputSettings.h').read_text()
        enums = '\n'.join(re.findall(r'enum class (?:OutputMode|HDR10SourceMode)[^;]+;', settings))
        preferences = 'struct OutputPreferences '+body(settings, 'struct OutputPreferences')+';'
        selector = body((headers/'DVOutputSelection.h').read_text(), 'inline OutputSelection SelectOutput(')
        budget = 'struct HDR10AIBuffers '+body((headers/'HDR10AIBuffers.h').read_text(), 'struct HDR10AIBuffers')+';'
        decoder = (headers/'DVDVideoCodecFFmpeg.cpp').read_text()
        count = body(decoder, 'unsigned CDVDVideoCodecFFmpeg::GetHDR10AIBufferCount() const')
        reopen = body(decoder, 'void CDVDVideoCodecFFmpeg::PrepareHDR10AIReopen()')
        common = body(decoder, 'bool CDVDVideoCodecFFmpeg::GetPictureCommon(')
        promotion = common[common.index('  if (pVideoPicture->hdrType == StreamHdrType::HDR_TYPE_HDR10 ||'):
                           common.index('#ifdef CB1_HAS_HDR10_AI', common.index('  if (pVideoPicture->hdrType == StreamHdrType::HDR_TYPE_HDR10 ||'))]
        vaapi = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/VAAPI.cpp').read_text()
        check = body(vaapi, 'CDVDVideoCodec::VCReturn CDecoder::Check(')
        check = check[check.index('  if (state == VAAPI_OPEN &&'):check.index('#endif')]
        renderer = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp').read_text()
        upload = body(renderer, 'bool CRendererVAAPIGLES::UploadTexture(')
        publication = upload[upload.index('  if (window && buf.doviSourcePicture)'):upload.rindex('#endif')]
        layer = body(renderer, 'bool CRendererVAAPIGLES::BuildDVBridgeLayer(')
        layer_gate = layer[layer.index('  hdr10 ='):layer.index('#endif')]
        window = (TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        capability = body(window, 'DVBRIDGE::OutputCapabilities CWinSystemGbmGLESContext::GetDVOutputCapabilities(\n    const VideoPicture* picture, const')
        capability = capability[capability.index('  caps.sourceKnown ='):capability.index('  if (!caps.isDV) return caps;')]
        program = r'''
#define HAVE_DVBRIDGE
#define CB1_HAS_HDR10_AI
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cores/VideoPlayer/DVDCodecs/Video/HDR10SourceType.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include "cores/VideoPlayer/DVDCodecs/Video/HDR10AIActivation.h"
#include "cores/VideoPlayer/VideoRenderers/HDR10PlusDVSource.h"
#include <cassert>
#include <atomic>
#include "dvbridge_core.h"
extern "C" {
#include <libavcodec/avcodec.h>
}
#include <bit>
#include <cmath>
#include <algorithm>
constexpr unsigned DVP_FLAG_INTERLACED=1;
constexpr unsigned GL_TEXTURE_2D=1,VA_FOURCC_NV12=1,VA_FOURCC_P010=2,VA_FOURCC_P012=3,VA_FOURCC_P016=4;
namespace DVBRIDGE {
ENUMS
PREFERENCES
BUDGET
inline OutputPreferences current;
inline std::atomic<HDR10SourceMode> hdr10PlaybackMode{HDR10SourceMode::Native};
inline std::atomic<HDR10SourceMode> hdr10PlusPlaybackMode{HDR10SourceMode::Native};
OutputPreferences FrameOutputSettings(bool plus=false){auto value=current;if(plus)value.hdr10Source=value.hdr10PlusSource;return value;}
enum class OutputRoute {Vanilla,NativeDV,HDR10};
struct OutputSelection {OutputRoute route{};dvbridge_policy policy{};OutputReason reason{};};
OutputSelection select(const OutputPreferences& preferences,const OutputCapabilities& caps) SELECTOR
}
struct Picture {
 StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;
 StreamHdrType hdrTypeAlt=StreamHdrType::HDR_TYPE_NONE;
 DVBRIDGE::SourceInfo doviSourceInfo{};DVBRIDGE::SourceBinding doviSourceBinding{5,6,7};
 int64_t doviSourcePts=1000;unsigned iFlags=0;std::string stereoMode;
 std::shared_ptr<const VideoSourceSideData> sourceSideData;
};
struct Window {
 bool m_dvImportUsable=false;DVBRIDGE::SourceBinding m_dvImportBinding{};
 uint64_t m_dvImportGeneration=0;
 dvbridge_geometry m_dvImportGeometry{};
 DVBRIDGE::OutputCapabilities base;
 void ObserveDVImport(DVBRIDGE::SourceBinding binding,dvbridge_geometry geometry,bool usable){
  m_dvImportBinding=binding;m_dvImportGeometry=geometry;m_dvImportUsable=usable;m_dvImportGeneration=base.generation;
 }
 DVBRIDGE::OutputCapabilities Caps(const Picture* picture){
  auto caps=base;
  CAPABILITY
  return caps;
 }
};
bool DVBridgeOrientationSupported(unsigned orientation){return orientation==0;}
bool LayerEligible(const Picture& source){
 bool hdr10=false;
 LAYER_GATE
 return hdr10;
}
void Import(Window* window,const Picture& picture){
 struct Metadata{DVBRIDGE::SourceBinding Binding()const{return {};}} metadata;
 struct Buffer{const Picture* doviSourcePicture;decltype(metadata) doviMetadata;} buf{&picture,{}};
 unsigned m_vaapiFourcc=VA_FOURCC_P010,m_textureTarget=GL_TEXTURE_2D,m_renderOrientation=0;
 auto DVBridgeGeometry=[] {dvbridge_geometry geometry{};geometry.source_width=16;geometry.source_height=16;return geometry;};
 PUBLICATION
}
struct ICallbackHWAccel {virtual unsigned GetHDR10AIBufferCount()const=0;virtual void PrepareHDR10AIReopen()=0;};
struct Decoder:ICallbackHWAccel{
 struct Hints{StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;
  struct{bool rpu_present_flag=false;}dovi;int fpsrate=24,fpsscale=1;}m_hints;
 bool m_interlaced=false;enum{STATE_NONE,STATE_HW}m_decoderState=STATE_HW;
 unsigned GetHDR10AIBufferCount()const override COUNT
 void PrepareHDR10AIReopen()override REOPEN
 void Observe(Picture& picture,AVFrame* m_pFrame){
  auto* pVideoPicture=&picture;AVFrameSideData* sd=nullptr;
  picture.hdrType=m_hints.hdrType;
  PROMOTION
 }
};
struct CDVDVideoCodec {enum VCReturn{VC_NONE,VC_REOPEN};};
std::mutex m_DecoderSection;int m_DisplayState=0;
void Reset(){}
CDVDVideoCodec::VCReturn Check(AVCodecContext* avctx,unsigned m_hdr10AIBuffers){
 enum{VAAPI_OPEN};int state=VAAPI_OPEN;
 CHECK
 return CDVDVideoCodec::VC_NONE;
}
int main(){
 using namespace DVBRIDGE;
 AVFrame* frame=av_frame_alloc();auto* hdr=av_dynamic_hdr_plus_create_side_data(frame);assert(hdr);
 hdr->itu_t_t35_country_code=0xb5;hdr->num_windows=1;
 hdr->targeted_system_display_maximum_luminance={4000,1};
 auto& p=hdr->params[0];for(auto& v:p.maxscl)v={1,10};
 p.average_maxrgb={1,100};p.fraction_bright_pixels={0,1};
 Picture picture;picture.doviSourceInfo.informationGeneration=9;
 picture.sourceSideData=VideoSourceSideData::Capture(9,91,AV_CODEC_ID_HEVC,frame,nullptr);
 assert(picture.sourceSideData && picture.sourceSideData->HDR10Plus());
 Window window;window.base.generation=17;
 window.base.sourceKnown=window.base.processingKnown=window.base.nativeDV=window.base.hdr10=true;
 for(auto& mode:window.base.hdr10Processing)mode={true,OutputReason::None};
 // Native presentation publishes identity/geometry before any AI mode is selected.
 assert(current.hdr10Source==HDR10SourceMode::Native);
 assert(!window.Caps(&picture).isHDR10Plus);
 Import(&window,picture);
 auto caps=window.Caps(&picture);
 assert(caps.isHDR10 && caps.hdr10PlusSource && caps.isHDR10Plus);
 picture.iFlags=DVP_FLAG_INTERLACED;assert(!window.Caps(&picture).isHDR10Plus);picture.iFlags=0;
 ++window.m_dvImportBinding.picture;assert(!window.Caps(&picture).isHDR10Plus);
 window.m_dvImportBinding=picture.doviSourceBinding;
 window.m_dvImportGeometry.crop[0]=1;assert(!window.Caps(&picture).isHDR10Plus);
 window.m_dvImportGeometry.crop[0]=0;
 assert(select(current,caps).route==OutputRoute::Vanilla && !LayerEligible(picture));
 Decoder decoder;AVCodecContext context{};context.opaque=&decoder;
 decoder.Observe(picture,frame);
 assert(decoder.m_hints.hdrType==StreamHdrType::HDR_TYPE_HDR10PLUS);
 unsigned buffers=decoder.GetHDR10AIBufferCount();assert(buffers==HDR10AIBuffers::Native);
 current.hdr10PlusSource=HDR10SourceMode::HDR10PlusDV;hdr10PlusPlaybackMode.store(current.hdr10PlusSource);
 assert(LayerEligible(picture) && select(current,caps).route==OutputRoute::NativeDV);
 assert(decoder.GetHDR10AIBufferCount()==27);
 assert(Check(&context,buffers)==CDVDVideoCodec::VC_REOPEN && decoder.m_decoderState==Decoder::STATE_NONE);
 buffers=decoder.GetHDR10AIBufferCount();assert(Check(&context,buffers)==CDVDVideoCodec::VC_NONE);
 for(auto mode:{HDR10SourceMode::ReferenceDV,HDR10SourceMode::EnhancedDV}){
  current.hdr10PlusSource=mode;hdr10PlusPlaybackMode.store(mode);assert(!LayerEligible(picture));
  assert(decoder.GetHDR10AIBufferCount()==HDR10AIBuffers::Native);
  assert(select(current,caps).route==OutputRoute::Vanilla);
 }
 current.hdr10PlusSource=HDR10SourceMode::Native;hdr10PlusPlaybackMode.store(current.hdr10PlusSource);
 decoder.m_decoderState=Decoder::STATE_HW;
 assert(Check(&context,buffers)==CDVDVideoCodec::VC_NONE);
 assert(decoder.m_decoderState==Decoder::STATE_HW); // A smaller request can reuse this file's pool.
 assert(decoder.GetHDR10AIBufferCount()==HDR10AIBuffers::Native);
 assert(select(current,caps).route==OutputRoute::Vanilla && !LayerEligible(picture));
 AVFrame* withoutMetadata=av_frame_alloc();
 decoder.Observe(picture,withoutMetadata);
 assert(picture.hdrType==StreamHdrType::HDR_TYPE_HDR10PLUS);
 assert(decoder.m_hints.hdrType==StreamHdrType::HDR_TYPE_HDR10PLUS);
 decoder.m_hints.hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;
 decoder.Observe(picture,frame);
 assert(decoder.m_hints.hdrType==StreamHdrType::HDR_TYPE_DOLBYVISION);
 assert(picture.hdrTypeAlt==StreamHdrType::HDR_TYPE_HDR10PLUS);
 decoder.m_hints.hdrType=StreamHdrType::HDR_TYPE_HDR10;
 decoder.Observe(picture,withoutMetadata);
 assert(picture.hdrType==StreamHdrType::HDR_TYPE_HDR10);
 hdr10PlaybackMode.store(HDR10SourceMode::ReferenceDV);
 assert(decoder.GetHDR10AIBufferCount()==27);
 av_frame_free(&withoutMetadata);
 current.hdr10Source=HDR10SourceMode::HDR10PlusDV;
 for(auto type:{StreamHdrType::HDR_TYPE_NONE,StreamHdrType::HDR_TYPE_DOLBYVISION,StreamHdrType::HDR_TYPE_HLG}){
  picture.hdrType=type;decoder.m_hints.hdrType=type;hdr10PlaybackMode.store(current.hdr10Source);
  assert(!LayerEligible(picture) && !window.Caps(&picture).isHDR10);
  assert(decoder.GetHDR10AIBufferCount()==HDR10AIBuffers::Native);
 }
 picture.hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;picture.doviSourceInfo.profile=5;
 assert(!LayerEligible(picture) && !window.Caps(&picture).isHDR10);
 av_frame_free(&frame);
}
'''
        for name, value in dict(ENUMS=enums,PREFERENCES=preferences,BUDGET=budget,SELECTOR=selector,
                COUNT=count,REOPEN=reopen,CHECK=check,PUBLICATION=publication,LAYER_GATE=layer_gate,
                CAPABILITY=capability,PROMOTION=promotion).items():
            program = re.sub(r'\b'+name+r'\b',lambda unused:value,program)
        self.compile_run(program, sources=self.snapshot_sources(), includes=(native/'xbmc',
            Path('/home/dvbuild/resolution-contract-20261022/prefix/include')))

    def test_accepted_native_information_keeps_guidance_distinct_from_dv_source(self):
        native = TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        snapshot = 'struct StreamSnapshot '+body((native/'DVStreamTelemetry.h').read_text(), 'struct StreamSnapshot')+';'
        conversion = body((native/'DVProcessingInfo.h').read_text(), 'inline VideoProcessingInfo NativeProcessingInfo(')
        self.compile_run(r'''
#define CB1_HAS_HDR10_AI 1
#include "cb1_circuit.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
#include "cores/VideoProcessingInfo.h"
extern "C" {
#include <libavutil/pixfmt.h>
}
#include <cassert>
#include <cstring>
namespace DVBRIDGE {
SNAPSHOT
VideoProcessingInfo NativeProcessingInfo(const StreamSnapshot& source) CONVERSION
}
int main(){
 DVBRIDGE::StreamSnapshot s;s.informationGeneration=17;
 auto& o=s.output;o.flags=CDVPlaybackInfo::HDMI;o.effective=1;o.hdr10AI=true;
 o.hdr10PlusDV=true;o.guidedSourceFields=2;o.guidedEstimatedFields=5;
 o.untranslatedCurve=true;o.untranslatedSaturation=true;
 o.emittedL1Known=true;o.emittedL1={12,3079,1200};
 s.metadata=true;s.profile=0;
 auto result=DVBRIDGE::NativeProcessingInfo(s);
 assert(result.informationGeneration==17 && !result.metadata && result.output.hdr10PlusDV);
 assert(result.output.guidedSourceFields==2 && result.output.guidedEstimatedFields==5);
 assert(result.output.untranslatedCurve && result.output.untranslatedSaturation);
 assert(result.output.circuit=="CB1-HDR10PDVR.0.2" && result.output.engine=="CB1 0.5");
 assert(result.output.emittedL1[1]==3079);
 assert(CDVPlaybackInfo::Mode(result.output)=="Dolby Vision Rendering");
 // Display mapping is a committed-frame fact, independent of later preferences.
 o.flags=CDVPlaybackInfo::HDR10;o.effective=3;o.gamut=2;
 o.manualPeak=1234.5;o.target=1234.5;o.displayBlack=0.0042;
 result=DVBRIDGE::NativeProcessingInfo(s);
 assert(result.output.gamut==2 && result.output.target==1234.5);
 assert(result.output.manualPeak==1234.5 && result.output.displayBlack==0.0042);
 s.output={};result=DVBRIDGE::NativeProcessingInfo(s);
 assert(result.output.displayBlack==0 && result.output.manualPeak==0);
 assert(!result.output.hdr10PlusDV && result.output.circuit.empty() && !result.output.guidedSourceFields);
}
'''.replace('SNAPSHOT',snapshot).replace('CONVERSION',conversion),
            sources=(REPO/'CB1/src/cb1_circuit.c',))

    def test_native_mode_and_selection_log_preserve_guided_identity_before_generic_ai(self):
        gui = (TREE/'xbmc/guilib/guiinfo/VideoProcessingInfoGUI.h').read_text()
        mode = body(gui, 'static std::string Mode(')
        renderer = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        start = renderer.index('DVBRIDGE::DiagnosticLog(LOGINFO,"DVBridge output selection:')
        selection = renderer[start:renderer.index(';', start)]
        calls = re.findall(r'CDVPlaybackInfo::RequestedPolicy\([^\n]+\)', selection)
        self.assertEqual(len(calls), 2)
        origin = selection.split('m_pendingSourceInfo.rpu,', 1)[1].rsplit(')', 1)[0].strip()
        self.compile_run(r'''
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include "cores/VideoProcessingInfo.h"
#include "cb1_hdr10plus_dovi.h"
#include <cassert>
struct Localizer {std::string Get(int id)const {
 return id==40867 ? "localized Reference AI" : "localized Adaptive AI";
}};
struct Resources {Localizer GetLocalizeStrings()const{return {};}};
struct CServiceBroker {static Resources GetResourcesComponent(){return {};}};
struct VideoProcessingInfoGUI {static std::string Mode(const VideoProcessingInfo& info) MODE};
using Output=decltype(VideoProcessingInfo{}.output);
std::string Requested(const Output& acceptedOutput){return REQUESTED;}
std::string Effective(const Output& acceptedOutput){return EFFECTIVE;}
std::string Origin(const Output& acceptedOutput){return ORIGIN;}
int main(){
 VideoProcessingInfo info;auto& output=info.output;
 output.flags=CDVPlaybackInfo::HDMI;output.requested=output.effective=1;
 output.hdr10AI=true;output.hdr10PlusDV=true;
 assert(VideoProcessingInfoGUI::Mode(info)=="Dolby Vision Rendering");
 assert(Requested(output)=="Dolby Vision Rendering");
 assert(Effective(output)=="Dolby Vision Rendering");
 assert(Origin(output)=="source-HDR10+-and-estimates");
 output.guidedSourceFields=CB1_HDR10PLUS_DOVI_MAX|CB1_HDR10PLUS_DOVI_AVG;
 assert(Origin(output)=="source-HDR10+-statistics");
 output.hdr10PlusDV=false;
 assert(VideoProcessingInfoGUI::Mode(info)=="localized Reference AI");
 assert(Requested(output)=="Dolby Vision Rendering");
 output.requested=output.effective=4;
 assert(VideoProcessingInfoGUI::Mode(info)=="localized Adaptive AI");
 assert(Effective(output)=="Dolby Vision Adaptive HDR Mapping (AI)");
 output.hdr10AI=false;output.requested=output.effective=1;
 assert(VideoProcessingInfoGUI::Mode(info)=="Dolby Vision Reference");
 assert(Requested(output)=="Dolby Vision Reference");assert(Origin(output)=="source-RPU");
 output.flags=0;assert(VideoProcessingInfoGUI::Mode(info).empty());
 output.flags=CDVPlaybackInfo::HDR10;output.requested=output.effective=2;
 assert(VideoProcessingInfoGUI::Mode(info)=="HDR10 Rendering");
 assert(Origin(output)=="reference-default");
 output.level6=true;assert(Origin(output)=="source-L6");
 output.requested=output.effective=3;assert(Origin(output)=="manual-tv-profile");
 output.requested=output.effective=7;assert(Origin(output)=="reconstructed-picture-statistics");
}
'''.replace('MODE', mode).replace('REQUESTED', calls[0]).replace('EFFECTIVE', calls[1]).replace('ORIGIN', origin))

    def test_low_source_peak_survives_actual_output_metadata_and_wire_serializer(self):
        native = Path(os.environ.get('KODI_TEST_SUPPORT_TREE', str(TREE)))
        source = (REPO/'CB1/src/dvbridge_render.c').read_text()
        functions = '\n'.join(signature+body(source,signature) for signature in (
            'static uint16_t dv_wire_code(double pq)', 'static double dv_ideal_pq(double nits)\n',
            'static AVDOVIMetadata *ai_output_metadata('))
        # Keep the real multiline signature for the metadata producer.
        start = functions.index('static AVDOVIMetadata *ai_output_metadata(')
        original = source.index('static AVDOVIMetadata *ai_output_metadata(')
        signature = source[original:source.index('{',original)]
        functions = functions[:start]+signature+body(source,'static AVDOVIMetadata *ai_output_metadata(')
        ipt_constants = '\n'.join(re.findall(r'^const int16_t cb1_ipt_output_\w+\[9\]=[^;]+;',
            (REPO/'CB1/src/cb1_master_ipt.c').read_text(), re.M))
        result_type = re.search(r'struct cb1_ai_result\s*\{[^}]+};',
            (REPO/'CB1/src/cb1_hdr10_ai.h').read_text()).group()
        self.compile_run(r'''
#include <libplacebo/colorspace.h>
#include "cores/VideoPlayer/VideoRenderers/HDR10PlusDVSource.h"
#include <cassert>
#include <math.h>
extern "C" {
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include "cb1_l1l3_model.h"
#include "dvbridge_core.h"
#include "cb1_hdr10_ai.h"
extern const int16_t cb1_ipt_output_ycc[9],cb1_ipt_output_lms[9];
IPT_CONSTANTS
}
FUNCTIONS
int main(){
 AVFrame* frame=av_frame_alloc();assert(frame);
 auto* hdr=av_dynamic_hdr_plus_create_side_data(frame);assert(hdr);
 hdr->itu_t_t35_country_code=0xb5;hdr->application_version=1;hdr->num_windows=1;
 hdr->targeted_system_display_maximum_luminance={4000,1};
 for(auto& value:hdr->params[0].maxscl)value={1,10000};
 hdr->params[0].average_maxrgb={0,1};hdr->params[0].fraction_bright_pixels={0,1};
 auto source=VideoSourceSideData::Capture(9,91,AV_CODEC_ID_HEVC,frame,nullptr);
 cb1_ai_result prediction{};prediction.id={7,14,31};prediction.raw={12,3200,1200,2048,2048,2048};
 cb1_hdr10plus_dovi_result described{};DVBRIDGE::SourceBinding binding{7,14,11};
 assert(DVBRIDGE::DescribeHDR10PlusDV(described,prediction.raw,source,binding,binding,9,91,true));
 prediction.raw=described.metadata;assert(prediction.raw.l1_max==614);
 pl_color_space color{};color.hdr.max_luma=1000;
 const unsigned margins[4]{};size_t bytes{};
 AVDOVIMetadata* metadata=ai_output_metadata(&prediction,&color,margins,&bytes);assert(metadata);
 const auto* l1=av_dovi_find_level(metadata,1);assert(l1 && l1->l1.max_pq==614);
 // Known mastering minimum belongs to the source description, not content L1.
 color.hdr.min_luma=0.005;
 assert(av_dovi_get_color(metadata)->source_min_pq==0);
 av_free(metadata);prediction.source_flags=3;
 metadata=ai_output_metadata(&prediction,&color,margins,&bytes);assert(metadata);
 assert(av_dovi_get_color(metadata)->source_min_pq==62);
 assert(av_dovi_get_color(metadata)->scene_refresh_flag==1);
 auto* context=dvbridge_create();assert(context);
 dvbridge_geometry geometry{};geometry.source_width=geometry.width=3840;
 geometry.source_height=geometry.height=2160;
 auto* candidate=dvbridge_prepare_output(context,metadata,bytes,0,geometry,false,true);assert(candidate);
 unsigned count{};const auto* packet=dvbridge_packets(candidate,&count);assert(packet && count==1);
 assert(packet[80]==1 && (packet[83]<<8|packet[84])==614);
 assert((packet[85]<<8|packet[86])==614);
 // Model-only 100-nit minimum (2081) must never be re-applied after description.
 assert((packet[83]<<8|packet[84])!=2081);
 dvbridge_candidate_destroy(candidate);dvbridge_destroy(context);av_free(metadata);av_frame_free(&frame);
}
'''.replace('RESULT_TYPE',result_type).replace('FUNCTIONS',functions).replace('IPT_CONSTANTS',ipt_constants),
            sources=(*self.snapshot_sources(),REPO/'CB1/src/dvbridge_core.c'),
            includes=(native/'xbmc',Path(os.environ.get('CB1_PLACEBO_INCLUDE',
                '/home/dvbuild/resolution-contract-20261022/prefix/include'))))


if __name__ == '__main__':
    unittest.main()
