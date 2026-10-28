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
        window = (tree/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        probe = re.search(r'auto policy = preferences.Policy\(\);.*?(?=\s*policy.tv =)', window, re.S).group(0)
        program = '''
#define HAVE_DVBRIDGE
#include "dvbridge_policy.h"
#include <cassert>
#include <bit>
#include <cmath>
#include <cstdint>
#include "utils/DVBridgePresentation.h"
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
  const auto& preferences=a;
  auto probe=[&](int mode){@@PROBE@@ return policy;};
  assert(probe(DVBRIDGE_MODE_HDR10_EXPERT).adaptive==DVBRIDGE_ADAPTIVE_A);
  assert(probe(DVBRIDGE_MODE_ENHANCED_DV).adaptive==DVBRIDGE_ADAPTIVE_B_FP16);
  assert(!a.disableL2Trims && !a.L2TrimsDisabled(DVBRIDGE_MODE_STANDARD));
  a.disableL2Trims=true;
  for(int mode=0;mode<DVBRIDGE_MODE_COUNT;++mode){
    assert(a.L2TrimsDisabled(static_cast<dvbridge_mode>(mode))==
        (mode==DVBRIDGE_MODE_STANDARD || mode==DVBRIDGE_MODE_MASTER_REFERENCE));
    assert(!a.L2TrimsDisabled(static_cast<dvbridge_mode>(mode),true));
  }
  auto b=a;b.disableL2Trims=false;assert(!a.SameValues(b));
}
'''.replace('ENUMS',enums).replace('PREFS',preferences).replace('@@PROBE@@',probe)
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
        self.assertEqual([int(value) for value in re.findall(r'\{(\d+),', choices)], [0, 4, 5, 2, 1, 1, 1])

    def test_legacy_fast_values_cannot_change_output_policy(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        header=(tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        header='\n'.join(line for line in header.splitlines() if not line.startswith('#include'))
        program=r"""
#include <atomic>
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
struct Settings {
 std::map<std::string,int> ints;
 int GetInt(const char* key){return ints[key];}
 double GetNumber(const char*){return 2500;}
 bool GetBool(const char* key){return ints[key];}
};
auto stored=std::make_shared<Settings>();
struct Component{auto GetSettings(){return stored;}} component;
struct CServiceBroker{static auto GetSettingsComponent(){return &component;}};
namespace DVBRIDGE {uint64_t NextRevision(){static uint64_t id=1;return ++id;}}
@HEADER@
int main(){using namespace DVBRIDGE;
 assert(!OutputPreferences{}.allowMasterFallback);
 for(int saved:{0,1,2,3,4,5})for(int ai:{0,1,2}){
  stored->ints["dvbridge.outputmode"]=saved;stored->ints["dvbridge.hdr10source"]=ai;
  auto initial=FrameOutputSettings();
  for(int oldFast:{0,1,2}){
   stored->ints["dvbridge.fastchroma"]=oldFast;
   auto current=FrameOutputSettings();
   assert(current.SameValues(initial) && current.revision==initial.revision);
   assert(current.Policy().mode==initial.Policy().mode);
   assert(current.HDR10Policy().mode==initial.HDR10Policy().mode);
  }
 }
 stored->ints["dvbridge.masterfallback"]=1;
 assert(FrameOutputSettings().allowMasterFallback);
 stored->ints["dvbridge.masterfallback"]=0;
 assert(!FrameOutputSettings().allowMasterFallback);
 auto original=FrameOutputSettings();
 stored->ints["dvbridge.disablel2"]=1;
 auto stripped=FrameOutputSettings();
 assert(stripped.disableL2Trims && stripped.revision!=original.revision);
 assert(!stripped.L2TrimsDisabled(DVBRIDGE_MODE_STANDARD,true));
 stored->ints["dvbridge.disablel2"]=0;
 auto restored=FrameOutputSettings();
 assert(!restored.disableL2Trims && restored.revision!=stripped.revision);
}
""".replace('@HEADER@',header)
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(repo/'CB1/src'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_requested_labels_compile_against_actual_cached_contract(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (tree/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        requested = source.split('    SetProperty("DV.RequestedPolicy",',1)[1].split(';',1)[0]
        from test_native_video_source import body
        native = body((tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVStreamTelemetry.h').read_text(), 'struct Output')
        renderer = (tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        # Native telemetry omits AI fields when the AI feature is not compiled.
        declarations = '''
#include <array>
#include "dvbridge_policy.h"
enum class OutputReason { None };
struct NativeOutput @@NATIVE@@;

'''.replace('@@NATIVE@@', native)
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
 assert(CDVPlaybackInfo::IsHDR10AI(data.output));}
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
#include "utils/DVBridgePresentation.h"
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
int main(){for(bool reverse:{false,true})for(int saved:{0,1,2,3,4,5,6}){
 TiXmlElement root;
 if(reverse)root.Add("dvbridge.fastchroma","true");
 root.Add("dvbridge.outputmode",std::to_string(saved));
 if(!reverse)root.Add("dvbridge.fastchroma","true");
 CSettings settings;bool updated=false;assert(settings.Load(&root,updated));
 assert(settings.loaded["dvbridge.outputmode"]==std::to_string(saved==3||saved==6?5:saved));
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
