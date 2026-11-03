"""Persistent HDR10/HDR10+ choices survive alternating sources and fallback."""
from pathlib import Path
import os
import re
import shlex
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE, body


class SourcePreferencesTests(unittest.TestCase):
    def test_settings_offer_independent_source_appropriate_choices(self):
        settings = ET.parse(TREE / 'system/settings/settings.xml')
        plain = settings.find(".//setting[@id='dvbridge.hdr10source']")
        plus = settings.find(".//setting[@id='dvbridge.hdr10plussource']")
        self.assertIsNotNone(plus, 'HDR10+ requires its own saved preference')
        self.assertEqual([x.text for x in plain.findall('constraints/options/option')], ['1','2','0'])
        self.assertEqual([x.text for x in plus.findall('constraints/options/option')], ['3','0'])
        self.assertEqual(plain.findtext('default'), '0')
        self.assertEqual(plus.findtext('default'), '0')

    def test_paired_snapshots_preserve_requested_modes_through_fallback(self):
        header = (TREE / 'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        header = '\n'.join(line for line in header.splitlines() if not line.startswith('#include'))
        selector = body((TREE / 'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSelection.h').read_text(),
                        'inline OutputSelection SelectOutput(')
        source=(TREE/'xbmc/dialogs/DVPlaybackModes.cpp').read_text()
        menu = body(source, 'bool CDVPlaybackModes::ShowMenu(')
        definitions=re.search(r'struct Choice.*?dvChoices\[\].*?;',source,re.S).group()
        choices = definitions+menu[menu.index('  const auto nativeSource='):
                                   menu.index('  const auto choiceSetting=')]
        writes = menu[menu.index('    const auto& choice=choices[selected];'):menu.index('    settings->Save();')]
        program = r'''
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
#define CB1_HAS_HDR10_AI
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
struct Settings {
 std::map<std::string,int> ints;
 int GetInt(const char* id){return ints[id];}
 double GetNumber(const char*){return 2000;}
 bool GetBool(const char* id){return ints[id];}
 bool SetInt(const char* id,int value){ints[id]=value;return true;}
};
auto stored=std::make_shared<Settings>();
struct Component {auto GetSettings(){return stored;}} component;
struct CServiceBroker {static auto GetSettingsComponent(){return &component;}};
namespace DVBRIDGE {uint64_t NextRevision(){static uint64_t id=1;return ++id;}}
HEADER
namespace DVBRIDGE {
enum class OutputRoute {Vanilla,NativeDV,HDR10};
struct OutputSelection {OutputRoute route{};dvbridge_policy policy{};OutputReason reason{};};
OutputSelection SelectOutput(const OutputPreferences& preferences,const OutputCapabilities& caps) SELECTOR
struct StreamTelemetry {struct Snapshot {struct {OutputCapabilities capabilities;} transaction;};
 static Snapshot Read(){return {};}};
}
enum class StreamHdrType {HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_DOLBYVISION,HDR_TYPE_NONE};
bool choose(StreamHdrType type,int selected,bool settingsMenu=false){
 auto settings=stored;auto SourceType=[&]{return type;};
 CHOICES
 assert(selected>=0 && selected<count);(void)source;
 WRITES
 return true;
}
int main(){
 using namespace DVBRIDGE;
 stored->ints["dvbridge.hdr10source"]=1;
 stored->ints["dvbridge.hdr10plussource"]=3;
 stored->ints["dvbridge.outputmode"]=1;
 stored->ints["dvbridge.hdr10method"]=1;
 stored->ints["dvbridge.tvgamut"]=2;
 stored->ints["dvbridge.expertgamut"]=2;
 auto initial=FrameOutputSettings();
 assert(initial.hdr10Source==HDR10SourceMode::ReferenceDV);
 assert(initial.hdr10PlusSource==HDR10SourceMode::HDR10PlusDV);
 for(int i=0;i<10;++i){
  auto plus=FrameOutputSettings(true),plain=FrameOutputSettings();
  assert(plus.hdr10Source==HDR10SourceMode::HDR10PlusDV);
  assert(plain.hdr10Source==HDR10SourceMode::ReferenceDV);
  assert(plus.revision==initial.revision && plain.revision==initial.revision);
 }
 assert(hdr10PlaybackMode.load()==HDR10SourceMode::ReferenceDV);
 assert(hdr10PlusPlaybackMode.load()==HDR10SourceMode::HDR10PlusDV);
 OutputCapabilities caps;caps.sourceKnown=caps.isHDR10=caps.processingKnown=caps.nativeDV=true;
 for(auto& mode:caps.processing)mode={true,OutputReason::None};
 assert(SelectOutput(initial,caps).route==OutputRoute::NativeDV);
 caps.hdr10PlusSource=true;caps.isHDR10Plus=true;
 assert(SelectOutput(initial,caps).route==OutputRoute::NativeDV);
 caps.nativeDV=false;
 assert(SelectOutput(initial,caps).route==OutputRoute::Vanilla);
 assert(stored->ints["dvbridge.hdr10source"]==1 && stored->ints["dvbridge.hdr10plussource"]==3);
 assert(FrameOutputSettings(true).hdr10Source==HDR10SourceMode::HDR10PlusDV);
 caps.nativeDV=true;caps.isHDR10Plus=false;
 assert(SelectOutput(initial,caps).reason==OutputReason::SourceIneligible);
 assert(FrameOutputSettings(true).hdr10Source==HDR10SourceMode::HDR10PlusDV);
 caps.isHDR10Plus=true;assert(SelectOutput(FrameOutputSettings(),caps).route==OutputRoute::NativeDV);
 stored->ints["dvbridge.hdr10plussource"]=0;
 auto nativePlus=FrameOutputSettings();
 assert(nativePlus.hdr10Source==HDR10SourceMode::ReferenceDV);
 assert(SelectOutput(nativePlus,caps).route==OutputRoute::Vanilla);
 caps.hdr10PlusSource=caps.isHDR10Plus=false;
 assert(SelectOutput(nativePlus,caps).route==OutputRoute::NativeDV);
 stored->ints["dvbridge.hdr10source"]=2;
 assert(FrameOutputSettings().hdr10Source==HDR10SourceMode::EnhancedDV);
 assert(FrameOutputSettings(true).hdr10Source==HDR10SourceMode::Native);
 caps.isDV=true;caps.isHDR10=false;caps.hdr10=true;
 auto dv=FrameOutputSettings();
 assert(dv.output==OutputMode::HDR10 && dv.method==1);
 assert(SelectOutput(dv,caps).policy.mode==DVBRIDGE_MODE_HDR10_EXPERT);
 caps.hdr10=false;
 assert(SelectOutput(dv,caps).route==OutputRoute::Vanilla);
 assert(FrameOutputSettings().output==OutputMode::HDR10 && FrameOutputSettings().method==1);
 caps.hdr10=true;
 assert(SelectOutput(FrameOutputSettings(),caps).policy.mode==DVBRIDGE_MODE_HDR10_EXPERT);
 assert(stored->ints["dvbridge.outputmode"]==1 && stored->ints["dvbridge.hdr10method"]==1);
 // Exercise the real quick-switch choices and save path, alternating input families.
 assert(choose(StreamHdrType::HDR_TYPE_DOLBYVISION,5));
 assert(choose(StreamHdrType::HDR_TYPE_HDR10PLUS,0));
 assert(choose(StreamHdrType::HDR_TYPE_HDR10,1));
 assert(FrameOutputSettings().output==OutputMode::HDR10 && FrameOutputSettings().method==1);
 assert(FrameOutputSettings().hdr10Source==HDR10SourceMode::EnhancedDV);
 assert(FrameOutputSettings(true).hdr10Source==HDR10SourceMode::HDR10PlusDV);
 assert(choose(StreamHdrType::HDR_TYPE_HDR10PLUS,1));
 assert(FrameOutputSettings(true).hdr10Source==HDR10SourceMode::Native);
 assert(FrameOutputSettings().hdr10Source==HDR10SourceMode::EnhancedDV);
 assert(choose(StreamHdrType::HDR_TYPE_DOLBYVISION,1));
 assert(FrameOutputSettings().output==OutputMode::MasterReference);
 assert(FrameOutputSettings().hdr10Source==HDR10SourceMode::EnhancedDV);
 // The same native dialog can set DV preferences while stopped or on HDR input.
 assert(choose(StreamHdrType::HDR_TYPE_NONE,5,true));
 assert(FrameOutputSettings().output==OutputMode::HDR10 && FrameOutputSettings().method==1);
 assert(choose(StreamHdrType::HDR_TYPE_HDR10PLUS,6,true));
 assert(FrameOutputSettings().output==OutputMode::HDR10 && FrameOutputSettings().method==2);
 // Kodi default bypasses CB1 independently for all three input families.
 assert(choose(StreamHdrType::HDR_TYPE_DOLBYVISION,3));
 caps.isDV=true;caps.isHDR10=false;
 assert(SelectOutput(FrameOutputSettings(),caps).route==OutputRoute::Vanilla);
 assert(choose(StreamHdrType::HDR_TYPE_HDR10,2));
 caps.isDV=false;caps.isHDR10=true;caps.hdr10PlusSource=caps.isHDR10Plus=false;
 assert(SelectOutput(FrameOutputSettings(),caps).route==OutputRoute::Vanilla);
 assert(choose(StreamHdrType::HDR_TYPE_HDR10PLUS,1));
 caps.hdr10PlusSource=caps.isHDR10Plus=true;
 assert(SelectOutput(FrameOutputSettings(true),caps).route==OutputRoute::Vanilla);
}
'''.replace('HEADER', header).replace('SELECTOR', selector).replace('CHOICES', choices).replace('WRITES', writes)
        root_repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-I'+str(root_repo/'CB1/src'),
                '-I'+str(TREE/'xbmc'), str(root/'test.cpp'), '-o', str(root/'test')],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_legacy_guided_choice_migrates_without_overwriting_explicit_preference(self):
        implementation = body((TREE / 'xbmc/settings/Settings.cpp').read_text(),
                              'bool CSettings::Load(const TiXmlElement* root, bool& updated)')
        program = r'''
#include "tinyxml.h"
#include <cassert>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#define HAVE_DVBRIDGE
struct CSettingsBase {
 inline static std::map<std::string,std::string> loaded;
 static bool LoadValuesFromXml(const TiXmlElement* root,bool&) {
  loaded.clear();
  for(auto* e=root->FirstChildElement("setting");e;e=e->NextSiblingElement("setting"))
   loaded[e->Attribute("id")]=e->GetText();
  return true;
 }
};
struct CSettings:CSettingsBase {
 bool Load(const TiXmlNode*) {return true;}
 bool Load(const TiXmlElement* root,bool& updated) IMPLEMENTATION
};
int main(){
 for(int old:{0,1,2,3})for(int explicitPlus:{-1,0,3})for(bool plusFirst:{false,true}){
  const auto plain="<setting id='dvbridge.hdr10source' default='true'>"+std::to_string(old)+"</setting>";
  const auto plus=explicitPlus<0 ? std::string{} :
   "<setting id='dvbridge.hdr10plussource'>"+std::to_string(explicitPlus)+"</setting>";
  const auto xml="<settings>"+(plusFirst?plus+plain:plain+plus)+
   "<setting id='dvbridge.outputmode'>4</setting><setting id='dvbridge.hdr10method'>1</setting></settings>";
  TiXmlDocument doc;doc.Parse(xml.c_str());assert(!doc.Error());
  CSettings settings;bool updated=false;assert(settings.Load(doc.RootElement(),updated));
  assert(settings.loaded["dvbridge.hdr10source"]==std::to_string(old==3?0:old));
  if(explicitPlus>=0 || old==3)
   assert(settings.loaded["dvbridge.hdr10plussource"]==std::to_string(explicitPlus>=0?explicitPlus:3));
  else assert(!settings.loaded.contains("dvbridge.hdr10plussource"));
  assert(updated==(old==3));
  assert(settings.loaded["dvbridge.outputmode"]=="4" && settings.loaded["dvbridge.hdr10method"]=="1");
  assert(std::string(doc.RootElement()->FirstChildElement("setting")->Attribute("id"))==
   (plusFirst && explicitPlus>=0 ? "dvbridge.hdr10plussource" : "dvbridge.hdr10source"));
 }
}
'''.replace('IMPLEMENTATION', implementation)
        # Use the pinned TinyXML implementation, not an XML-shaped mock.
        if os.environ.get('TINYXML_TEST_SOURCE'):
            tinyxml = Path(os.environ['TINYXML_TEST_SOURCE'])
            xml_args = ['-I'+str(tinyxml/'include'), *(str(tinyxml/'src'/name) for name in
                ('tinyxml.cpp','tinyxmlparser.cpp','tinyxmlerror.cpp','tinystr.cpp'))]
        else:
            xml_args = shlex.split(subprocess.check_output(
                ['pkg-config','--cflags','--libs','tinyxml'],text=True))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-DTIXML_USE_STL',
                str(root/'test.cpp'), *xml_args,
                '-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran = subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__ == '__main__':
    unittest.main()
