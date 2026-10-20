"""Ordinary frame preparation must not masquerade as a mode transition."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code

ROOT=Path(__file__).resolve().parents[2]


class PendingInfoTests(unittest.TestCase):
    def test_pending_transition_and_failure_are_distinct_from_next_frame(self):
        code=shipped_code('xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp')
        block=code.split('    const bool transaction=',1)[1].split('    SetProperty("DV.ReferenceWarning"',1)[0]
        metadata=(ROOT/'projects/Generic/patches/kodi/kodi-9990-native-dv.patch').read_text()
        additions='\n'.join(line[1:] for line in metadata.splitlines() if line.startswith('+') and not line.startswith('+++'))
        binding='struct SourceBinding'+additions.split('struct SourceBinding',1)[1].split('struct SourceInfo',1)[0]
        program=r'''
#include <cassert>
#include <map>
#include <string>
#include <string_view>
#include <cstdint>
namespace DVBRIDGE { enum class OutputReason {None,NoDVTransport,ActivationFailed,RestoreFailed}; SOURCE_BINDING }
using VideoProcessingReason=DVBRIDGE::OutputReason;
using Identity=DVBRIDGE::SourceBinding;
struct Transaction { Identity identity; int requested{},effective{},enhancement{},atomicError{}; unsigned retryCount{};
  bool restored{}; DVBRIDGE::OutputReason reason{DVBRIDGE::OutputReason::None}; const char* stage="";
  bool hdr10AI{}; };
struct Output { unsigned flags{},stream{},revision{}; int requested{},effective{},enhancement{};
  DVBRIDGE::OutputReason reason{DVBRIDGE::OutputReason::None}; bool hdr10AI{}; };
struct Data { Transaction transaction; Output output; };
struct CDVPlaybackInfo { static const char* RequestedPolicy(int,bool=false) {return "policy";} };
struct StringUtils { template<class... T> static std::string Format(const char*,T...) {return "error";} };
std::map<std::string,std::string> properties;
void SetProperty(const char* key,const std::string& value) {properties[key]=value;}
void SetProperty(const char* key,const char* value) {properties[key]=value;}
void SetProperty(const char* key,bool value) {properties[key]=value ? "true" : "false";}
void update(Data data) {
  const auto active=data.output.flags;
  const auto reasonText=[](DVBRIDGE::OutputReason reason) {return reason==DVBRIDGE::OutputReason::None ? "" : "reason";};
  const auto yesno=[](bool value) {return value ? "Yes" : "No";};
  const bool transaction=BLOCK
}
int main() {
  Data data;
  data.output={1,7,3,1,1,0};
  data.transaction.identity={7,1,3}; data.transaction.requested=1; data.transaction.effective=1;
  for (const char* stage : {"Admission checked","Prepared","Requested","Committed"}) {
    data.transaction.stage=stage; update(data);
    assert(properties["DV.OutputStage"].empty());
    assert(properties["DV.AdmissionReason"].empty());
  }
  // Admission may use the preference revision before source/geometry binding.
  data.transaction.identity.revision=1; data.transaction.stage="Admission checked";
  update(data); assert(properties["DV.OutputStage"].empty());
  data.transaction.identity.revision=4; data.transaction.requested=0; data.transaction.effective=0;
  update(data); assert(!properties["DV.OutputStage"].empty());
  data.transaction.identity.revision=3; data.transaction.requested=1; data.transaction.effective=1;
  data.output.reason=data.transaction.reason=DVBRIDGE::OutputReason::NoDVTransport;
  for (const char* stage : {"Admission checked","Prepared","Requested"}) {
    data.transaction.stage=stage; update(data); assert(properties["DV.OutputStage"].empty());
  }
  data.output.reason=data.transaction.reason=DVBRIDGE::OutputReason::None;
  data.transaction.identity.revision=4; data.transaction.requested=2; data.transaction.effective=2;
  data.transaction.stage="Prepared"; update(data); assert(!properties["DV.OutputStage"].empty());
  data.transaction.identity.revision=3; data.transaction.requested=1; data.transaction.effective=1;
  data.transaction.stage="Failed commit"; update(data);
  assert(!properties["DV.OutputStage"].empty());
  data.transaction.atomicError=22; data.transaction.stage="Activation failed";
  data.transaction.reason=DVBRIDGE::OutputReason::ActivationFailed;
  update(data); assert(!properties["DV.AtomicResult"].empty() && !properties["DV.AdmissionReason"].empty());
  data={}; data.transaction.identity={8,1,1}; data.transaction.stage="Admission checked";
  update(data); assert(properties["DV.OutputStage"].empty());
  data.transaction.requested=1; data.transaction.reason=DVBRIDGE::OutputReason::NoDVTransport;
  update(data); assert(!properties["DV.OutputStage"].empty() && !properties["DV.AdmissionReason"].empty());
  data={}; update(data); assert(properties["DV.OutputStage"].empty());
  assert(properties["DV.ProcessingVisible"]=="false");
}
'''.replace('BLOCK',block).replace('SOURCE_BINDING',binding)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'check.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'check.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'check')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)


if __name__=='__main__': unittest.main()
