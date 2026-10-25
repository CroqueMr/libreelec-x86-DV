"""Display existing stored mode/profile values through the native player helper."""
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class AdaptiveNamesTests(unittest.TestCase):
    def test_authored_variant_and_precision_do_not_leak_into_ai_policy(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        enums = source.split('enum class OutputMode',1)[1].split('// Decoder ingress',1)[0]
        preferences = source.split('struct OutputPreferences',1)[1].split('inline std::mutex&',1)[0]
        program = '''
#define HAVE_DVBRIDGE
#include "dvbridge_policy.h"
#include <cassert>
#include <bit>
#include <cmath>
#include <cstdint>
#include "utils/DVBridgeFastRendering.h"
enum class OutputMode ENUMS
struct OutputPreferences PREFS
int main() {
  OutputPreferences a; a.output=OutputMode::AdaptiveB; a.peak=2500; a.gamut=2;
  assert(a.Policy().adaptive==DVBRIDGE_ADAPTIVE_B_FP16);
  a.hdr10Source=HDR10SourceMode::ReferenceDV;
  assert(a.HDR10Policy().adaptive==DVBRIDGE_ADAPTIVE_A && a.HDR10Policy().mode==DVBRIDGE_MODE_STANDARD);
  a.output=OutputMode::EnhancedDV;
  assert(a.Policy().adaptive==DVBRIDGE_ADAPTIVE_B_FP16);
  a.hdr10Source=HDR10SourceMode::EnhancedDV;
  assert(a.HDR10Policy().adaptive==DVBRIDGE_ADAPTIVE_A && a.HDR10Policy().mode==DVBRIDGE_MODE_ENHANCED_DV);
}
'''.replace('ENUMS',enums).replace('PREFS',preferences)
        core = Path(__file__).resolve().parents[2]/'CB1/src'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(core),'-I'+str(tree/'xbmc'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_saved_adaptive_mode_and_profiles_keep_their_meaning(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        program = r'''
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include <cassert>
struct Output { int effective{}; unsigned flags{}; bool fallback{}; };
int main() {
  Output saved{4,CDVPlaybackInfo::HDMI,false};
  assert(std::string(CDVPlaybackInfo::RequestedPolicy(4)) == "Dolby Vision Adaptive HDR Mapping");
  assert(std::string(CDVPlaybackInfo::Policy(saved)) == "Dolby Vision Adaptive HDR Mapping");
  assert(CDVPlaybackInfo::Mode(saved) == "Dolby Vision Adaptive HDR Mapping");
  saved.effective=6;
  assert(CDVPlaybackInfo::Mode(saved) == "Dolby Vision Adaptive HDR Mapping");
  assert(std::string(CDVPlaybackInfo::RequestedPolicy(6)) == "Dolby Vision Adaptive HDR Mapping");
  saved.flags=0;
  assert(CDVPlaybackInfo::Mode(saved) == "Kodi default");
  saved={3,CDVPlaybackInfo::HDR10,false};
  assert(CDVPlaybackInfo::Mode(saved) == "HDR10 Reference Expert");
  saved={1,CDVPlaybackInfo::HDMI,false};
 assert(CDVPlaybackInfo::Mode(saved) == "Dolby Vision Standard");
  assert(std::string(CDVPlaybackInfo::RequestedPolicy(1)) == "Dolby Vision Standard");
  assert(std::string(CDVPlaybackInfo::RequestedPolicy(1, true)) == "Dolby Vision Reference (AI)");
  assert(std::string(CDVPlaybackInfo::RequestedPolicy(4, true)) == "Dolby Vision Adaptive HDR Mapping (AI)");
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', '-I' + str(tree / 'xbmc'),
                                    str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_public_choices_have_one_adaptive_and_no_precision_toggle(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        settings = ET.parse(tree / 'system/settings/settings.xml')
        options = settings.findall(".//setting[@id='dvbridge.outputmode']/constraints/options/option")
        self.assertEqual([int(option.text) for option in options], [0, 4, 5, 2, 1])
        self.assertIsNone(settings.find(".//setting[@id='dvbridge.adaptivefp16']"))
        menu = (tree / 'xbmc/dialogs/DVPlaybackModes.cpp').read_text()
        choices = re.search(r'dvChoices\[\]=\{(.*?)\};', menu, re.S).group(1)
        self.assertEqual([int(value) for value in re.findall(r'\{(\d+),', choices)], [0, 4, 5, 2, 1, 1])

    def test_active_pipelines_require_fast_except_exact_master(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        from test_native_video_source import body
        header = (tree / 'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        header = '\n'.join(line for line in header.splitlines() if not line.startswith('#include'))
        renderer = (tree / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        paths = [('bool CDVBridgeGLES::Prepare(', 'm_requested', 'm_effectiveMode'),
                 ('CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(', 'preferences', 'policy.mode'),
                 ('CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareHDR10AIFrame(', 'preferences', 'policy.mode')]
        expressions = []
        for signature, _, _ in paths:
            expressions.append(re.search(r'dvbridge_renderer_set_fast_chroma\(m_renderer,(.*?)\);',
                                         body(renderer, signature)).group(1))
        telemetry = re.search(r'output.fastChroma = (.*?);', renderer).group(1)
        fast_mode = re.search(r'output.fastRenderingMode = (.*?);', renderer).group(1)
        program = r'''
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
#include "dvbridge_policy.h"
#include "utils/DVBridgeFastRendering.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
struct Settings {
 std::map<std::string,int> ints;
 int GetInt(const char* key){return ints[key];} double GetNumber(const char*){return 2500;}
 bool GetBool(const char*){return false;}
};
auto stored=std::make_shared<Settings>();
struct Component{auto GetSettings(){return stored;}} component;
struct CServiceBroker{static auto GetSettingsComponent(){return &component;}};
namespace DVBRIDGE {uint64_t NextRevision(){static uint64_t id=1;return ++id;}}
@@HEADER@@
bool prepare(DVBRIDGE::OutputPreferences m_requested,dvbridge_mode m_effectiveMode){return @@PREPARE@@;}
bool frame(DVBRIDGE::OutputPreferences preferences,dvbridge_mode mode){struct {dvbridge_mode mode;}policy{mode};return @@FRAME@@;}
bool ai(DVBRIDGE::OutputPreferences preferences,dvbridge_mode mode){struct {dvbridge_mode mode;}policy{mode};return @@AI@@;}
void telemetry(DVBRIDGE::OutputPreferences m_requested,dvbridge_mode m_effectiveMode,bool hdr10AI,bool expected,int expectedMode){
 struct {bool fastChroma{},hdr10AI{};int fastRenderingMode{};}output;output.hdr10AI=hdr10AI;
 output.fastChroma=@@TELEMETRY@@;output.fastRenderingMode=@@FASTMODE@@;
 assert(output.fastChroma==expected && output.fastRenderingMode==expectedMode);
}
int main(){using namespace DVBRIDGE;
 for(int global=0;global<3;++global){
  stored->ints["dvbridge.fastchroma"]=global;
  for(int saved:{0,1,2,3,4,5}){
   stored->ints["dvbridge.outputmode"]=saved;FrameOutputSettings();
   auto p=FrameOutputSettings();
   assert(int(p.output)==(saved==3?5:saved));
   for(auto mode:{DVBRIDGE_MODE_STANDARD,DVBRIDGE_MODE_MASTER_REFERENCE,DVBRIDGE_MODE_HDR10_BASIC,DVBRIDGE_MODE_HDR10_EXPERT,DVBRIDGE_MODE_ENHANCED_DV}){
    const bool expected=mode!=DVBRIDGE_MODE_MASTER_REFERENCE;
    assert(prepare(p,mode)==expected);assert(frame(p,mode)==expected);
    assert(ai(p,mode)==expected);
    telemetry(p,mode,false,expected,expected?1:0);
    telemetry(p,mode,true,expected,expected?1:0);
   }
   assert(!p.EffectiveFastChroma(DVBRIDGE_MODE_DISABLED));
  }
 }
}
'''.replace('@@HEADER@@', header).replace('@@PREPARE@@', expressions[0]).replace('@@FRAME@@', expressions[1]).replace('@@AI@@', expressions[2]).replace('@@TELEMETRY@@', telemetry).replace('@@FASTMODE@@', fast_mode)
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-I'+str(tree/'xbmc'), '-I'+str(repo/'CB1/src'),
                                    str(root/'test.cpp'), '-o', str(root/'test')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_requested_labels_compile_against_actual_cached_contract(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (tree/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        requested = source.split('    SetProperty("DV.RequestedPolicy",',1)[1].split(';',1)[0]
        from test_native_video_source import body
        native = body((tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVStreamTelemetry.h').read_text(), 'struct Output')
        renderer = (tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        telemetry = re.search(r'output.fastChroma = (.*?);', renderer).group(1)
        fast_mode = re.search(r'output.fastRenderingMode = (.*?);', renderer).group(1)
        # Native telemetry omits AI fields when the AI feature is not compiled.
        declarations = '''
#include <array>
#include "dvbridge_policy.h"
enum class OutputReason { None };
struct NativeOutput @@NATIVE@@;
struct Preferences {
 bool EffectiveFastChroma(dvbridge_mode, bool ai)const{return ai;}
 int EffectiveFastRenderingMode(dvbridge_mode,bool ai)const{return ai?2:1;}
};
void nativeTelemetry(){NativeOutput output;Preferences m_requested;auto m_effectiveMode=DVBRIDGE_MODE_STANDARD;
 output.fastChroma=@@TELEMETRY@@;output.fastRenderingMode=@@FASTMODE@@;
 assert(!output.fastChroma && output.fastRenderingMode==1);}
'''.replace('@@NATIVE@@', native).replace('@@TELEMETRY@@', telemetry).replace('@@FASTMODE@@', fast_mode)
        program = r'''
#include "cores/VideoProcessingInfo.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include <cassert>
@@DECLARATIONS@@
std::string label(VideoProcessingInfo data){bool transaction=true,active=true;return @@REQUESTED@@;}
int main(){VideoProcessingInfo data;data.transaction.requested=1;
 assert(label(data)=="Dolby Vision Standard");
 data.transaction.hdr10AI=true;assert(label(data)=="Dolby Vision Reference (AI)");
 data.transaction.requested=4;assert(label(data)=="Dolby Vision Adaptive HDR Mapping (AI)");
 assert(!CDVPlaybackInfo::IsHDR10AI(data.output));data.output.hdr10AI=true;
 assert(CDVPlaybackInfo::IsHDR10AI(data.output));nativeTelemetry();}
'''.replace('@@REQUESTED@@', requested.rstrip()[:-1]).replace('@@DECLARATIONS@@', declarations)
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'test.cpp').write_text(program)
            built = subprocess.run(['c++','-std=c++20','-I'+str(tree/'xbmc'),'-I'+str(repo/'CB1/src'),str(root/'test.cpp'),
                                    '-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run = subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_saved_legacy_output_migrates_alongside_boolean_fast(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        from test_native_video_source import body
        implementation = body((tree/'xbmc/settings/Settings.cpp').read_text(),
                              'bool CSettings::Load(const TiXmlElement* root, bool& updated)')
        program = r'''
#include <cassert>
#include <map>
#include <memory>
#include <string>
#include <vector>
#include "utils/DVBridgeFastRendering.h"
#define HAVE_DVBRIDGE
struct TiXmlNode {virtual ~TiXmlNode()=default;};
struct TiXmlText {std::string value;explicit TiXmlText(const char* text):value(text){}};
struct TiXmlElement:TiXmlNode {
 std::string id,text;bool hasDefault=true;TiXmlElement* next{};
 std::vector<std::unique_ptr<TiXmlElement>> children;
 TiXmlElement()=default;TiXmlElement(std::string key,std::string value):id(key),text(value){}
 const char* Attribute(const char* key)const{return std::string(key)=="id"?id.c_str():nullptr;}
 const char* GetText()const{return text.c_str();}
 TiXmlElement* FirstChildElement(const char*)const{return children.empty()?nullptr:children.front().get();}
 TiXmlElement* NextSiblingElement(const char*)const{return next;}
 TiXmlElement* ToElement(){return this;}
 TiXmlElement* Clone()const{auto* copy=new TiXmlElement(id,text);copy->hasDefault=hasDefault;
  for(const auto& child:children)copy->Add(child->id,child->text);return copy;}
 void Add(std::string key,std::string value){auto child=std::make_unique<TiXmlElement>(key,value);
  if(!children.empty())children.back()->next=child.get();children.push_back(std::move(child));}
 void Clear(){text.clear();}
 void LinkEndChild(TiXmlText* value){text=value->value;delete value;}
 void RemoveAttribute(const char*){hasDefault=false;}
};
struct CSettingsBase {inline static std::map<std::string,std::string> loaded;
 static bool LoadValuesFromXml(const TiXmlElement* root,bool&){loaded.clear();
  for(const auto& child:root->children)loaded[child->id]=child->text;
  return loaded["dvbridge.outputmode"]!="3";}
};
struct CSettings:CSettingsBase {
 bool Load(const TiXmlNode*){return true;}
 bool Load(const TiXmlElement* root,bool& updated) @@LOAD@@
};
int main(){for(bool reverse:{false,true})for(int saved:{0,1,2,3,4,5}){
 TiXmlElement root;
 if(reverse)root.Add("dvbridge.fastchroma","true");
 root.Add("dvbridge.outputmode",std::to_string(saved));
 if(!reverse)root.Add("dvbridge.fastchroma","true");
 CSettings settings;bool updated=false;assert(settings.Load(&root,updated));
 assert(settings.loaded["dvbridge.outputmode"]==std::to_string(saved==3?5:saved));
 assert(settings.loaded["dvbridge.fastchroma"]=="true"); // Retired, never read or migrated.
 assert(root.children[reverse?1:0]->text==std::to_string(saved));
}}
'''.replace('@@LOAD@@', implementation)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'test.cpp').write_text(program)
            built = subprocess.run(['c++','-std=c++20','-I'+str(tree/'xbmc'),str(root/'test.cpp'),
                                    '-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run = subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)


if __name__ == '__main__':
    unittest.main()
