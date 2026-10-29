"""Master waits for the packed GUI route without inventing a render failure."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class MasterStartupTests(unittest.TestCase):
    def run_entry(self, checks):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        # The production entry is kept real up to the independent geometry work.
        entry = body(source, 'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(')
        entry = entry.split('  // Capture the proven observation key')[0] + 'return FrameStatus::Ready;}'
        signature = 'void CDVBridgeGLES::BeginDiagnosticStream('
        begin = body(source, signature) if signature in source else '{}'
        summary = body(source, 'void CDVBridgeGLES::Summary(')
        program = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>
#include <string_view>
#define FMT_HEADER_ONLY
#include <fmt/format.h>
#include "utils/DVBridgeDiagnosticState.h"
#include "dvbridge_policy.h"
namespace DVBRIDGE {
enum class OutputMode{Disabled,Standard,HDR10,MasterReference};
struct Binding {uint64_t stream=1,picture=1,revision=1;bool Valid()const{return stream!=0;}
 bool operator==(const Binding&)const=default;};
struct OutputPreferences {uint64_t revision=1;OutputMode output=OutputMode::MasterReference;
 bool valid=true;dvbridge_mode mode=DVBRIDGE_MODE_MASTER_REFERENCE;
 dvbridge_policy Policy()const{return {.revision=revision,.mode=mode};}
 bool ProfileValid()const{return valid;}};
inline std::string stage;
inline std::vector<std::string> messages;
template<class...T>void ObserveDiagnostic(T...){}
inline void DiagnosticStage(const char* value){stage=value;}
template<class...T>void DiagnosticLog(int,fmt::format_string<T...> f,T&&...a){
 messages.push_back(fmt::format(f,std::forward<T>(a)...));}
}
enum {LOGINFO};
struct CDVMetadataBuffer {DVBRIDGE::Binding binding;auto Binding()const{return binding;}};
struct dvbridge_geometry {};
struct CDVBridgeGLES {
 enum class FrameStatus{Ready,Pending,Busy,Failed,Reused,Unsupported};
 struct Layer {DVBRIDGE::Binding binding;double pts=1;};
 struct Context {bool bad=false;bool Quarantined()const{return bad;}
 bool AsyncPreparation(uint64_t)const{return true;}}context;
 Context* m_context=&context;int m_renderer=1;
 struct {bool asyncEligible=false;}m_submission;
 bool m_asyncEligible=true,m_firstFrame=false,m_fallback=false,m_advanced=false;
 uint64_t m_diagnosticStream=0,m_prepares=5,m_directFrames=5,m_presentations=4,
 m_failedPresentations=1,m_lastSummary=10,m_lastReported=5,m_rawELImports=3,m_rawELHits=7;
 DVBRIDGE::DiagnosticFailures m_failures;
 DVBRIDGE::DiagnosticInterval m_hdr10plusDiagnostics;
 int errors=0,summaries=0;
 bool Failure(const char* stage){++errors;m_failures.Record(1,stage);return false;}
 void Summary(const char* event){++summaries; SUMMARY }
 void BeginDiagnosticStream(uint64_t stream) BEGIN
 FrameStatus PrepareFrame(const Layer& base,const Layer* enhancement,
 const CDVMetadataBuffer& metadata,dvbridge_geometry geometry,
 const DVBRIDGE::OutputPreferences& preferences,bool allowPacked,
 const dvbridge_policy* selected,bool allowAsync) ENTRY
};
int main(){
 CDVBridgeGLES renderer;CDVBridgeGLES::Layer layer;CDVMetadataBuffer metadata;
 DVBRIDGE::OutputPreferences preferences;
 CHECKS
}
'''.replace('BEGIN', begin).replace('ENTRY', entry).replace('CHECKS', checks).replace('SUMMARY',summary)
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, binary = root / 'check.cpp', root / 'check'
            code.write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'), '-I'+str(repo/'CB1/src'), str(code), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_master_retries_gui_readiness_but_rejects_invalid_sources(self):
        # Returning Failed or entering render work before the GUI is ready is the bug.
        self.run_entry(r'''
 using Status=CDVBridgeGLES::FrameStatus;
 assert(renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,false,nullptr,true)==Status::Busy);
 assert(renderer.errors==0 && DVBRIDGE::stage=="master-await-overlay");
 assert(renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,true,nullptr,true)==Status::Ready);
 for(auto mode:{DVBRIDGE_MODE_STANDARD,DVBRIDGE_MODE_HDR10_BASIC,DVBRIDGE_MODE_HDR10_EXPERT}){
  preferences.mode=mode;
  assert(renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,false,nullptr,true)==Status::Ready);
 }
 preferences.mode=DVBRIDGE_MODE_MASTER_REFERENCE;metadata.binding.picture=2;
 assert(renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,false,nullptr,true)==Status::Failed);
 assert(renderer.errors==1);
 metadata.binding=layer.binding;renderer.context.bad=true;
 assert(renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,false,nullptr,true)==Status::Failed);
 assert(renderer.errors==2);
''')

    def test_counters_belong_to_a_file_not_a_seek_or_policy_change(self):
        self.run_entry(r'''
 assert(renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,true,nullptr,true)==CDVBridgeGLES::FrameStatus::Ready);
 assert(renderer.m_diagnosticStream==1 && renderer.m_prepares==0 && renderer.m_failures.Count()==0);
 renderer.m_prepares=3;renderer.m_presentations=2;renderer.m_failures.Record(1,"real-error");
 ++layer.binding.revision;metadata.binding=layer.binding;++preferences.revision;
 renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,true,nullptr,true);
 assert(renderer.m_prepares==3 && renderer.m_failures.Count()==1 && renderer.summaries==0);
 ++layer.binding.stream;metadata.binding=layer.binding;
 renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,true,nullptr,true);
 assert(renderer.summaries==1 && renderer.m_diagnosticStream==2);
 assert(renderer.m_prepares==0 && renderer.m_directFrames==0 && renderer.m_presentations==0);
 assert(renderer.m_failedPresentations==0 && renderer.m_failures.Count()==0 && renderer.m_firstFrame);
 assert(renderer.m_rawELImports==0 && renderer.m_rawELHits==0);
''')

    def test_previous_file_summary_identifies_its_counter_owner(self):
        self.run_entry(r'''
 renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,true,nullptr,true);
 renderer.m_prepares=3;renderer.m_presentations=2;
 ++layer.binding.stream;metadata.binding=layer.binding;
 renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,true,nullptr,true);
 assert(DVBRIDGE::messages.size()==1);
 assert(DVBRIDGE::messages.back().find("counter_stream=1")!=std::string::npos);
 assert(DVBRIDGE::messages.back().find("prepared=3")!=std::string::npos);
''')

    def test_first_bad_metadata_is_counted_after_a_valid_retry(self):
        self.run_entry(r'''
 renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,true,nullptr,true);
 ++layer.binding.stream; // Metadata still belongs to the previous file.
 assert(renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,true,nullptr,true)==CDVBridgeGLES::FrameStatus::Failed);
 assert(renderer.m_diagnosticStream==2 && renderer.m_failures.Count()==1);
 metadata.binding=layer.binding;
 assert(renderer.PrepareFrame(layer,nullptr,metadata,{},preferences,true,nullptr,true)==CDVBridgeGLES::FrameStatus::Ready);
 assert(renderer.m_failures.Count()==1);
''')


if __name__ == '__main__':
    unittest.main()
